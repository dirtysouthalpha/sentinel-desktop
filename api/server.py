"""
Sentinel Desktop v2 — FastAPI Headless Control Server.

Run with: python main.py --api
Endpoints:
  POST /goal       — start agent run
  POST /command    — single desktop command
  GET  /screenshot — capture current screen as PNG
  GET  /status     — agent status
  GET  /windows    — list visible windows
  GET  /processes  — list running processes
  GET  /system     — system info
  GET  /config     — read config
  PUT  /config     — update config
  GET  /log        — get forensic run log
  POST /stop       — stop running agent
  WS   /ws         — live status feed
"""

import asyncio
import json
import logging
import os
import threading
import time
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import Config
from core import process_manager as pm
from core import system_info as sysinfo
from core import window_manager as wm
from core.engine import AgentEngine
from core.screenshot import capture_to_base64

logger = logging.getLogger(__name__)

# Optional shared-secret auth. Set SENTINEL_API_TOKEN in the environment to
# require an Authorization: Bearer <token> header on every request. Unset →
# no auth (legacy behaviour, OK for localhost-only use).
API_TOKEN_ENV = "SENTINEL_API_TOKEN"  # noqa: S105


# ── Request models ──────────────────────────────────────────────────────


class GoalRequest(BaseModel):
    goal: str
    max_steps: int | None = None
    approval_mode: bool | None = None


class CommandRequest(BaseModel):
    command: str  # JSON action dict or natural language


class ConfigUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    max_steps: int | None = None
    approval_mode: bool | None = None
    theme: str | None = None


class ScriptRunRequest(BaseModel):
    path: str
    params: dict[str, Any] | None = None


class PowerShellRequest(BaseModel):
    command: str = Field(max_length=2000)


class RecorderStopRequest(BaseModel):
    name: str = "Untitled"
    description: str = ""


class WorkflowRunRequest(BaseModel):
    path: str
    variables: dict[str, Any] | None = None


class ScheduleAddRequest(BaseModel):
    name: str
    goal: str
    cron: str | None = None
    delay_seconds: float | None = None


class ScheduleRemoveRequest(BaseModel):
    task_id: str


class ScheduleRunRequest(BaseModel):
    task_id: str


class NotifyRequest(BaseModel):
    title: str = "Sentinel"
    message: str
    level: str = "info"


class PluginReloadRequest(BaseModel):
    name: str


class AgentSubmitRequest(BaseModel):
    goal: str
    config: dict[str, Any] | None = None
    priority: str = "normal"


class AgentCancelRequest(BaseModel):
    session_id: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthLogoutRequest(BaseModel):
    token: str


# ── Server class ────────────────────────────────────────────────────────


class SentinelServer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine: AgentEngine | None = None
        self._run_thread: threading.Thread | None = None
        self._ws_clients: list[WebSocket] = []
        self._ws_lock = threading.Lock()
        # Cache the loop so worker threads can schedule broadcasts onto it.
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- auth ------------------------------------------------------------

    def _check_auth(self, authorization: str | None) -> None:
        token = os.environ.get(API_TOKEN_ENV)
        if not token:
            return  # auth disabled
        expected = f"Bearer {token}"
        if not authorization or authorization != expected:
            raise HTTPException(401, "Missing or invalid Authorization header")

    def create_app(self) -> FastAPI:
        # Rate-limiting state for login attempts: IP → [timestamp, ...]
        self._login_attempts: dict[str, list[float]] = defaultdict(list)
        self._login_limit = 5  # max attempts per window
        self._login_window = 300.0  # 5 minutes

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            self._loop = asyncio.get_running_loop()
            yield

        app = FastAPI(
            title="Sentinel Desktop v2",
            description="AI-powered Windows desktop automation API",
            version="2.0.0",
            lifespan=lifespan,
        )

        # Tighten CORS: when no auth token is configured, restrict to
        # localhost; with a token, allow any origin. Operators who really
        # want a wide-open API can override via SENTINEL_CORS_ORIGINS.
        cors_env = os.environ.get("SENTINEL_CORS_ORIGINS")
        if cors_env:
            origins = [o.strip() for o in cors_env.split(",") if o.strip()]
        elif os.environ.get(API_TOKEN_ENV):
            origins = ["*"]
        else:
            origins = [
                "http://localhost",
                "http://127.0.0.1",
                "http://localhost:*",
                "http://127.0.0.1:*",
            ]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["*"],
        )

        # Register routes
        app.post("/goal")(self._handle_goal)
        app.post("/command")(self._handle_command)
        app.get("/screenshot")(self._handle_screenshot)
        app.get("/status")(self._handle_status)
        app.get("/windows")(self._handle_windows)
        app.get("/processes")(self._handle_processes)
        app.get("/system")(self._handle_system)
        app.get("/config")(self._handle_get_config)
        app.put("/config")(self._handle_put_config)
        app.get("/log")(self._handle_log)
        app.post("/stop")(self._handle_stop)
        # v3.0 — Script Recorder, Script Engine, PowerShell
        app.get("/scripts")(self._handle_scripts_list)
        app.post("/scripts/run")(self._handle_script_run)
        app.post("/powershell")(self._handle_powershell)
        app.post("/recorder/start")(self._handle_recorder_start)
        app.post("/recorder/stop")(self._handle_recorder_stop)
        # v3.0 Phase 2 — Workflow, Scheduler, Notifications, Plugins
        app.get("/workflows")(self._handle_workflows_list)
        app.post("/workflows/run")(self._handle_workflow_run)
        app.get("/schedule")(self._handle_schedule_list)
        app.post("/schedule/add")(self._handle_schedule_add)
        app.post("/schedule/remove")(self._handle_schedule_remove)
        app.post("/schedule/run")(self._handle_schedule_run)
        app.post("/notify")(self._handle_notify)
        app.get("/plugins")(self._handle_plugins_list)
        app.post("/plugins/reload")(self._handle_plugins_reload)
        # v3.0 Phase 3+4 — Agent Pool, Auth, Audit, Vault
        app.get("/agents")(self._handle_agents_list)
        app.post("/agents/submit")(self._handle_agents_submit)
        app.post("/agents/cancel")(self._handle_agents_cancel)
        app.get("/agents/{session_id}")(self._handle_agent_status)
        app.post("/auth/login")(self._handle_auth_login)
        app.post("/auth/logout")(self._handle_auth_logout)
        app.get("/auth/users")(self._handle_auth_users)
        app.get("/audit/export")(self._handle_audit_export)
        app.get("/vault/keys")(self._handle_vault_keys)
        app.websocket("/ws")(self._handle_ws)

        return app

    # ── Agent control ───────────────────────────────────────────────

    async def _handle_goal(
        self, req: GoalRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        if self.engine and self.engine.running:
            raise HTTPException(409, "Agent already running — stop it first")

        cfg = self.config.load()
        if req.max_steps:
            cfg["max_steps"] = req.max_steps
        if req.approval_mode is not None:
            cfg["approval_mode"] = req.approval_mode

        self.engine = AgentEngine(cfg)
        # Bridge engine step events to all connected WebSocket clients.
        self.engine.on_step_callback = self._broadcast_step

        def _run() -> None:
            try:
                result = self.engine.run(req.goal)
                logger.info("Agent finished: %d steps", result.get("steps", 0))
                self._broadcast_event(
                    {
                        "type": "done",
                        "result": {
                            "steps": result.get("steps", 0),
                            "summary": result.get("finish_summary", ""),
                        },
                    }
                )
            except Exception as exc:
                logger.exception("Agent run crashed")
                self._broadcast_event({"type": "error", "message": str(exc)})

        self._run_thread = threading.Thread(target=_run, daemon=True)
        self._run_thread.start()

        return {"status": "started", "goal": req.goal}

    async def _handle_command(
        self, req: CommandRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        cfg = self.config.load()
        engine = AgentEngine(cfg)

        text = (req.command or "").strip()
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise HTTPException(400, f"Invalid JSON action: {exc}") from exc
            if not isinstance(payload, dict) or "action" not in payload:
                raise HTTPException(400, "JSON payload must be an object with an 'action' key")
        else:
            payload = {"action": "note", "text": text}

        return engine.executor.execute_sync(payload)

    async def _handle_stop(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        self._check_auth(authorization)
        if self.engine and self.engine.running:
            self.engine.stop()
            return {"status": "stopping"}
        return {"status": "not_running"}

    # ── Information endpoints ───────────────────────────────────────

    async def _handle_screenshot(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        self._check_auth(authorization)
        b64 = capture_to_base64()
        return {"screenshot": b64, "format": "png", "encoding": "base64"}

    async def _handle_status(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        if self.engine:
            return {
                "running": self.engine.running,
                "step": self.engine.step,
                "max_steps": self.engine.max_steps,
                "notes_count": len(self.engine.notes),
            }
        return {"running": False, "step": 0}

    async def _handle_windows(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        return {"windows": wm.list_windows()}

    async def _handle_processes(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        return {"processes": pm.list_processes(limit=100)}

    async def _handle_system(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        return {"system": sysinfo.system_info()}

    async def _handle_get_config(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        # Never leak the API key over the wire.
        cfg = dict(self.config.load())
        if cfg.get("api_key"):
            cfg["api_key"] = "***"
        return cfg

    async def _handle_put_config(
        self, req: ConfigUpdate, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        self._check_auth(authorization)
        cfg = self.config.load()
        # Pydantic v2 prefers model_dump; v1 only has .dict(). Support both.
        dump = getattr(req, "model_dump", None) or req.dict
        for k, v in dump(exclude_none=True).items():
            cfg[k] = v
        self.config.save(cfg)
        return {"status": "saved"}

    async def _handle_log(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        self._check_auth(authorization)
        if self.engine:
            return {"log": self.engine.forensic_log}
        return {"log": []}

    # ── Script / Recorder / PowerShell endpoints ──────────────────────

    async def _handle_scripts_list(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List all available scripts in the scripts/ directory."""
        self._check_auth(authorization)
        try:
            import os

            from core.recorder import ActionRecorder

            scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
            scripts = ActionRecorder.list_scripts(scripts_dir)
            return {"scripts": scripts}
        except Exception as exc:
            return {"scripts": [], "error": str(exc)}

    async def _handle_script_run(
        self, req: ScriptRunRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a script by path with optional parameters."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.script_engine import ScriptEngine

        engine = ScriptEngine(self.engine.executor)
        result = engine.run_script(req.path, req.params)
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
        }

    async def _handle_powershell(
        self, req: PowerShellRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a PowerShell command."""
        self._check_auth(authorization)
        try:
            from core.powershell import get_default_runner

            runner = get_default_runner()
            ps_result = runner.run_command(req.command)
            return {
                "success": ps_result.success,
                "stdout": ps_result.stdout[:5000],
                "stderr": ps_result.stderr[:2000],
                "exit_code": ps_result.exit_code,
                "objects": ps_result.objects[:100],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_recorder_start(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        """Start recording actions."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        self.engine.recorder.start_recording("")
        return {"status": "recording"}

    async def _handle_recorder_stop(
        self, req: RecorderStopRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Stop recording and save the script."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        script = self.engine.recorder.stop_recording()
        name = req.name
        desc = req.description
        script.name = name
        script.description = desc or script.description
        import os

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        path = os.path.join(scripts_dir, f"{name.replace(' ', '_').lower()}.json")
        script.save(path)
        return {"status": "saved", "path": path, "steps": len(script.steps)}

    # ── v3.0 Phase 2 endpoints ────────────────────────────────────────

    async def _handle_workflows_list(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List available workflows."""
        self._check_auth(authorization)
        try:
            import os

            from core.workflow import WorkflowEngine

            wf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")
            return {"workflows": WorkflowEngine.list_workflows(wf_dir)}
        except Exception as exc:
            return {"workflows": [], "error": str(exc)}

    async def _handle_workflow_run(
        self, req: WorkflowRunRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a workflow."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.workflow import WorkflowEngine

        wf = WorkflowEngine(self.engine.executor, self.engine.script_engine)
        result = wf.run_workflow(req.path, req.variables)
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
            "elapsed": result.elapsed_seconds,
        }

    async def _handle_schedule_list(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List scheduled tasks."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"tasks": self.engine.scheduler.list_tasks()}

    async def _handle_schedule_add(
        self, req: ScheduleAddRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        """Add a scheduled task."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        task_id = self.engine.scheduler.add_task(req.model_dump())
        return {"status": "added", "task_id": task_id}

    async def _handle_schedule_remove(
        self, req: ScheduleRemoveRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        """Remove a scheduled task."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        removed = self.engine.scheduler.remove_task(req.task_id)
        return {"status": "removed" if removed else "not_found"}

    async def _handle_schedule_run(
        self, req: ScheduleRunRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a scheduled task immediately."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return self.engine.scheduler.run_task_now(req.task_id)

    async def _handle_notify(
        self, req: NotifyRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, bool]:
        """Send a notification."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        success = self.engine.notifications.notify(
            title=req.title,
            message=req.message,
            level=req.level,
        )
        return {"success": success}

    async def _handle_plugins_list(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List loaded plugins."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"plugins": self.engine.plugin_loader.list_plugins()}

    async def _handle_plugins_reload(
        self, req: PluginReloadRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Reload a plugin."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        name = req.name
        success = self.engine.plugin_loader.reload_plugin(name)
        return {"success": success, "name": name}

    # ── v3.0 Phase 3+4 endpoints ──────────────────────────────────────

    async def _handle_agents_list(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List all agent pool sessions."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"sessions": self.engine.agent_pool.list_sessions()}

    async def _handle_agents_submit(
        self, req: AgentSubmitRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        """Submit a goal to the agent pool."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        session_id = self.engine.agent_pool.submit(
            goal=req.goal,
            config=req.config,
            priority=req.priority,
        )
        return {"session_id": session_id, "status": "queued"}

    async def _handle_agents_cancel(
        self, req: AgentCancelRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, bool]:
        """Cancel an agent session."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        success = self.engine.agent_pool.cancel(req.session_id)
        return {"success": success}

    async def _handle_agent_status(
        self, session_id: str, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Get status of a specific agent session."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        status = self.engine.agent_pool.get_status(session_id)
        if not status:
            raise HTTPException(404, "Session not found")
        return status

    async def _handle_auth_login(
        self,
        req: AuthLoginRequest,
        request: Request = None,  # type: ignore[assignment]
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        """Authenticate and get a session token."""
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        # Rate-limit login attempts per client IP.
        client_id = self._get_client_ip(request) if request else "unknown"
        now = time.monotonic()
        attempts = self._login_attempts[client_id]
        # Prune expired attempts.
        attempts[:] = [t for t in attempts if now - t < self._login_window]
        if len(attempts) >= self._login_limit:
            raise HTTPException(429, "Too many login attempts — try again later")
        attempts.append(now)

        user = self.engine.auth_manager.authenticate(req.username, req.password)
        if not user:
            raise HTTPException(401, "Invalid credentials")
        token = self.engine.auth_manager.create_session(user)
        return {"token": token, "role": user.role.value, "username": user.username}

    async def _handle_auth_logout(
        self, req: AuthLogoutRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, str]:
        """Revoke a session token."""
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        self.engine.auth_manager.revoke_session(req.token)
        return {"status": "logged_out"}

    async def _handle_auth_users(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List users (admin only)."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"users": self.engine.auth_manager.list_users()}

    async def _handle_audit_export(
        self, authorization: str | None = Header(default=None), format: str = "html"
    ) -> dict[str, str]:
        """Export audit log as HTML/JSON/CSV/Text."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        log = self.engine.forensic_log if hasattr(self.engine, "forensic_log") else []
        path = self.engine.audit_exporter.generate_report(
            log, metadata={"goal": "audit"}, format=format
        )
        return {"path": path, "format": format}

    async def _handle_vault_keys(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List credential vault keys."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"keys": self.engine.vault.list_keys()}

    # ── WebSocket broadcasting ──────────────────────────────────────

    def _broadcast_step(self, **kwargs: Any) -> None:
        """Engine step callback (runs on worker thread). Schedules a broadcast."""
        # Avoid sending raw base64 screenshots over WS — too large by default.
        kwargs.pop("screenshot", None)
        self._broadcast_event({"type": "step", **kwargs})

    def _broadcast_event(self, event: dict[str, Any]) -> None:
        """Thread-safe broadcast to all WebSocket clients."""
        loop = self._loop
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._async_broadcast(event), loop)

    async def _async_broadcast(self, event: dict[str, Any]) -> None:
        with self._ws_lock:
            clients = list(self._ws_clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception as exc:
                logger.debug("WebSocket send failed, marking dead: %s", exc)
                dead.append(ws)
        if dead:
            with self._ws_lock:
                for ws in dead:
                    if ws in self._ws_clients:
                        self._ws_clients.remove(ws)

    async def _handle_ws(self, ws: WebSocket) -> None:
        await ws.accept()
        # Require authentication via first message: {"type": "auth", "token": "..."}
        try:
            auth_msg = await asyncio.wait_for(ws.receive_text(), timeout=10)
            auth_data = json.loads(auth_msg)
            auth_token = auth_data.get("token", "")
            # Validate the token.
            api_token = os.environ.get(API_TOKEN_ENV)
            if api_token and auth_token != api_token:
                await ws.send_json({"type": "auth_error", "message": "Invalid token"})
                await ws.close()
                return
        except asyncio.TimeoutError:
            logger.debug("WebSocket auth timed out — allowing through")
        except json.JSONDecodeError:
            logger.debug("WebSocket auth message was not valid JSON — allowing through")
        except Exception:
            logger.debug("Unexpected error during WebSocket auth handshake", exc_info=True)

        with self._ws_lock:
            self._ws_clients.append(ws)
        try:
            while True:
                data = await ws.receive_text()
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            with self._ws_lock:
                if ws in self._ws_clients:
                    self._ws_clients.remove(ws)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from a FastAPI Request object.

        Checks X-Forwarded-For and X-Real-IP headers first (for proxied
        setups), then falls back to ``request.client.host``.
        """
        if request is None:
            return "unknown"
        # Check X-Forwarded-For (may contain multiple IPs; first is the client)
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        # Check X-Real-IP (set by nginx and similar proxies)
        xri = request.headers.get("x-real-ip", "")
        if xri:
            return xri.strip()
        # Direct connection
        if request.client and request.client.host:
            return request.client.host
        return "unknown"
