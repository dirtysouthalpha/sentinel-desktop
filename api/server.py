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
import base64
import json
import logging
import io
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.engine import AgentEngine
from core.screenshot import capture_to_base64, capture_screen
from core import window_manager as wm
from core import process_manager as pm
from core import system_info as sysinfo
from core import clipboard as clip
from core import file_ops
from config import Config

logger = logging.getLogger(__name__)

# Optional shared-secret auth. Set SENTINEL_API_TOKEN in the environment to
# require an Authorization: Bearer <token> header on every request. Unset →
# no auth (legacy behaviour, OK for localhost-only use).
API_TOKEN_ENV = "SENTINEL_API_TOKEN"


# ── Request models ──────────────────────────────────────────────────────

class GoalRequest(BaseModel):
    goal: str
    max_steps: Optional[int] = None
    approval_mode: Optional[bool] = None

class CommandRequest(BaseModel):
    command: str  # JSON action dict or natural language

class ConfigUpdate(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    max_steps: Optional[int] = None
    approval_mode: Optional[bool] = None
    theme: Optional[str] = None


# ── Server class ────────────────────────────────────────────────────────

class SentinelServer:
    def __init__(self, config: Config):
        self.config = config
        self.engine: Optional[AgentEngine] = None
        self._run_thread: Optional[threading.Thread] = None
        self._ws_clients: List[WebSocket] = []
        self._ws_lock = threading.Lock()
        # Cache the loop so worker threads can schedule broadcasts onto it.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- auth ------------------------------------------------------------

    def _check_auth(self, authorization: Optional[str]) -> None:
        token = os.environ.get(API_TOKEN_ENV)
        if not token:
            return  # auth disabled
        expected = f"Bearer {token}"
        if not authorization or authorization != expected:
            raise HTTPException(401, "Missing or invalid Authorization header")

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="Sentinel Desktop v2",
            description="AI-powered Windows desktop automation API",
            version="2.0.0",
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
            origins = ["http://localhost", "http://127.0.0.1",
                       "http://localhost:*", "http://127.0.0.1:*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["*"],
        )

        @app.on_event("startup")
        async def _capture_loop():
            self._loop = asyncio.get_running_loop()

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
        app.websocket("/ws")(self._handle_ws)

        return app

    # ── Agent control ───────────────────────────────────────────────

    async def _handle_goal(self, req: GoalRequest,
                           authorization: Optional[str] = Header(default=None)):
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

        def _run():
            try:
                result = self.engine.run(req.goal)
                logger.info("Agent finished: %d steps", result.get("steps", 0))
                self._broadcast_event({
                    "type": "done",
                    "result": {
                        "steps": result.get("steps", 0),
                        "summary": result.get("finish_summary", ""),
                    },
                })
            except Exception as exc:
                logger.exception("Agent run crashed")
                self._broadcast_event({"type": "error", "message": str(exc)})

        self._run_thread = threading.Thread(target=_run, daemon=True)
        self._run_thread.start()

        return {"status": "started", "goal": req.goal}

    async def _handle_command(self, req: CommandRequest,
                              authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        cfg = self.config.load()
        engine = AgentEngine(cfg)

        text = (req.command or "").strip()
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise HTTPException(400, f"Invalid JSON action: {exc}")
            if not isinstance(payload, dict) or "action" not in payload:
                raise HTTPException(400, "JSON payload must be an object with an 'action' key")
        else:
            payload = {"action": "note", "text": text}

        return engine.executor.execute_sync(payload)

    async def _handle_stop(self, authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        if self.engine and self.engine.running:
            self.engine.stop()
            return {"status": "stopping"}
        return {"status": "not_running"}

    # ── Information endpoints ───────────────────────────────────────

    async def _handle_screenshot(self,
                                 authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        b64 = capture_to_base64()
        return {"screenshot": b64, "format": "png", "encoding": "base64"}

    async def _handle_status(self,
                             authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        if self.engine:
            return {
                "running": self.engine.running,
                "step": self.engine.step,
                "max_steps": self.engine.max_steps,
                "notes_count": len(self.engine.notes),
            }
        return {"running": False, "step": 0}

    async def _handle_windows(self,
                              authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        return {"windows": wm.list_windows()}

    async def _handle_processes(self,
                                authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        return {"processes": pm.list_processes(limit=100)}

    async def _handle_system(self,
                             authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        return {"system": sysinfo.system_info()}

    async def _handle_get_config(self,
                                 authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        # Never leak the API key over the wire.
        cfg = dict(self.config.load())
        if cfg.get("api_key"):
            cfg["api_key"] = "***"
        return cfg

    async def _handle_put_config(self, req: ConfigUpdate,
                                 authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        cfg = self.config.load()
        # Pydantic v2 prefers model_dump; v1 only has .dict(). Support both.
        dump = getattr(req, "model_dump", None) or req.dict
        for k, v in dump(exclude_none=True).items():
            cfg[k] = v
        self.config.save(cfg)
        return {"status": "saved"}

    async def _handle_log(self,
                          authorization: Optional[str] = Header(default=None)):
        self._check_auth(authorization)
        if self.engine:
            return {"log": self.engine.forensic_log}
        return {"log": []}

    # ── Script / Recorder / PowerShell endpoints ──────────────────────

    async def _handle_scripts_list(self,
                                    authorization: Optional[str] = Header(default=None)):
        """List all available scripts in the scripts/ directory."""
        self._check_auth(authorization)
        try:
            from core.recorder import ActionRecorder
            import os
            scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
            scripts = ActionRecorder.list_scripts(scripts_dir)
            return {"scripts": scripts}
        except Exception as exc:
            return {"scripts": [], "error": str(exc)}

    async def _handle_script_run(self, req: Dict,
                                  authorization: Optional[str] = Header(default=None)):
        """Run a script by path with optional parameters."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.script_engine import ScriptEngine
        engine = ScriptEngine(self.engine.executor)
        result = engine.run_script(req.get("path", ""), req.get("params"))
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
        }

    async def _handle_powershell(self, req: Dict,
                                  authorization: Optional[str] = Header(default=None)):
        """Run a PowerShell command."""
        self._check_auth(authorization)
        try:
            from core.powershell import get_default_runner
            runner = get_default_runner()
            ps_result = runner.run_command(req.get("command", ""))
            return {
                "success": ps_result.success,
                "stdout": ps_result.stdout[:5000],
                "stderr": ps_result.stderr[:2000],
                "exit_code": ps_result.exit_code,
                "objects": ps_result.objects[:100],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_recorder_start(self,
                                      authorization: Optional[str] = Header(default=None)):
        """Start recording actions."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        self.engine.recorder.start_recording("")
        return {"status": "recording"}

    async def _handle_recorder_stop(self, req: Dict,
                                     authorization: Optional[str] = Header(default=None)):
        """Stop recording and save the script."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        script = self.engine.recorder.stop_recording()
        name = req.get("name", "Untitled")
        desc = req.get("description", "")
        script.name = name
        script.description = desc or script.description
        import os
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        path = os.path.join(scripts_dir, f"{name.replace(' ', '_').lower()}.json")
        script.save(path)
        return {"status": "saved", "path": path, "steps": len(script.steps)}

    # ── v3.0 Phase 2 endpoints ────────────────────────────────────────

    async def _handle_workflows_list(self,
                                      authorization: Optional[str] = Header(default=None)):
        """List available workflows."""
        self._check_auth(authorization)
        try:
            from core.workflow import WorkflowEngine
            import os
            wf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")
            return {"workflows": WorkflowEngine.list_workflows(wf_dir)}
        except Exception as exc:
            return {"workflows": [], "error": str(exc)}

    async def _handle_workflow_run(self, req: Dict,
                                    authorization: Optional[str] = Header(default=None)):
        """Run a workflow."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.workflow import WorkflowEngine
        wf = WorkflowEngine(self.engine.executor, self.engine.script_engine)
        result = wf.run_workflow(req.get("path", ""), req.get("variables"))
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
            "elapsed": result.elapsed_seconds,
        }

    async def _handle_schedule_list(self,
                                     authorization: Optional[str] = Header(default=None)):
        """List scheduled tasks."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"tasks": self.engine.scheduler.list_tasks()}

    async def _handle_schedule_add(self, req: Dict,
                                    authorization: Optional[str] = Header(default=None)):
        """Add a scheduled task."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        task_id = self.engine.scheduler.add_task(req)
        return {"status": "added", "task_id": task_id}

    async def _handle_schedule_remove(self, req: Dict,
                                       authorization: Optional[str] = Header(default=None)):
        """Remove a scheduled task."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        removed = self.engine.scheduler.remove_task(req.get("task_id", ""))
        return {"status": "removed" if removed else "not_found"}

    async def _handle_schedule_run(self, req: Dict,
                                    authorization: Optional[str] = Header(default=None)):
        """Run a scheduled task immediately."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        result = self.engine.scheduler.run_task_now(req.get("task_id", ""))
        return result

    async def _handle_notify(self, req: Dict,
                              authorization: Optional[str] = Header(default=None)):
        """Send a notification."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        success = self.engine.notifications.notify(
            title=req.get("title", "Sentinel"),
            message=req.get("message", ""),
            level=req.get("level", "info"),
        )
        return {"success": success}

    async def _handle_plugins_list(self,
                                    authorization: Optional[str] = Header(default=None)):
        """List loaded plugins."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"plugins": self.engine.plugin_loader.list_plugins()}

    async def _handle_plugins_reload(self, req: Dict,
                                      authorization: Optional[str] = Header(default=None)):
        """Reload a plugin."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        name = req.get("name", "")
        success = self.engine.plugin_loader.reload_plugin(name)
        return {"success": success, "name": name}

    # ── WebSocket broadcasting ──────────────────────────────────────

    def _broadcast_step(self, **kwargs):
        """Engine step callback (runs on worker thread). Schedules a broadcast."""
        # Avoid sending raw base64 screenshots over WS — too large by default.
        kwargs.pop("screenshot", None)
        self._broadcast_event({"type": "step", **kwargs})

    def _broadcast_event(self, event: Dict[str, Any]):
        """Thread-safe broadcast to all WebSocket clients."""
        loop = self._loop
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._async_broadcast(event), loop)

    async def _async_broadcast(self, event: Dict[str, Any]):
        with self._ws_lock:
            clients = list(self._ws_clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            with self._ws_lock:
                for ws in dead:
                    if ws in self._ws_clients:
                        self._ws_clients.remove(ws)

    async def _handle_ws(self, ws: WebSocket):
        await ws.accept()
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
