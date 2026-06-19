"""Sentinel Desktop v3 — FastAPI Headless Control Server.

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
  WS   /ws/terminal — interactive PTY shell
  GET  /           — master control dashboard
"""

import asyncio
import hmac
import json
import logging
import os
import signal
import struct
import threading
import time
from collections import defaultdict
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, NoReturn

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.routes import RouteRegistry
from config import Config
from core import __version__ as _CORE_VERSION
from core import process_manager as pm
from core import system_info as sysinfo
from core import window_manager as wm
from core.dashboard import router as dashboard_router
from core.engine import AgentEngine
from core.screenshot import capture_to_base64
from core.workflow_builder import TEMPLATES, workflow_store

# Unix-only modules for PTY terminal support (not available on Windows).
# The terminal WebSocket endpoint gracefully degrades on Windows.
_HAS_PTY = False
try:
    import fcntl  # type: ignore[import-not-found]
    import pty  # type: ignore[import-not-found]
    import termios  # type: ignore[import-not-found]

    _HAS_PTY = True
except ImportError:
    fcntl = None  # type: ignore[assignment]
    pty = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Timeout constants for API operations (seconds)
DEFAULT_API_TIMEOUT = 30
LONG_OPERATION_TIMEOUT = 300  # 5 minutes for complex operations

# Optional shared-secret auth. Set SENTINEL_API_TOKEN in the environment to
# require an Authorization: Bearer <token> header on every request. Unset →
# no auth (legacy behaviour, OK for localhost-only use).
API_TOKEN_ENV = "SENTINEL_API_TOKEN"  # noqa: S105 — env var name, not a hardcoded password

# Length limits for input validation
MAX_GOAL_LENGTH = 2000
MAX_WORKFLOW_NAME_LENGTH = 100
EMPTY_GOAL_ERROR = "Goal cannot be empty"


# ── Request models ──────────────────────────────────────────────────────


class GoalRequest(BaseModel):
    """Request body for POST /goal — start a new agent run."""

    goal: str
    max_steps: int | None = None
    approval_mode: bool | None = None

    def validate_goal(self) -> str:
        """Validate and sanitize goal input."""
        # Remove excessive whitespace and limit length
        clean_goal = " ".join(self.goal.split())  # Normalize whitespace
        if len(clean_goal) > MAX_GOAL_LENGTH:  # Prevent unreasonably long goals
            clean_goal = clean_goal[:MAX_GOAL_LENGTH]
        if not clean_goal.strip():
            raise ValueError(EMPTY_GOAL_ERROR)
        return clean_goal


class CommandRequest(BaseModel):
    """Request body for POST /command — execute a single desktop command."""

    command: str  # JSON action dict or natural language


class ConfigUpdate(BaseModel):
    """Request body for PUT /config — update runtime configuration."""

    provider: str | None = None
    model: str | None = None
    max_steps: int | None = None
    approval_mode: bool | None = None
    theme: str | None = None


class ScriptRunRequest(BaseModel):
    """Request body for POST /scripts/run — execute a saved script."""

    path: str
    params: dict[str, Any] | None = None

    def validate_path(self) -> str:
        """Validate and sanitize script path to prevent directory traversal."""
        # Remove any directory traversal attempts
        clean_path = self.path.replace("..", "").replace("~", "").strip()
        # Ensure path starts with scripts/ directory
        if not clean_path.startswith("scripts/"):
            clean_path = f"scripts/{clean_path}"
        return clean_path


class PowerShellRequest(BaseModel):
    """Request body for POST /powershell — run a PowerShell command."""

    command: str = Field(max_length=2000)


class RecorderStopRequest(BaseModel):
    """Request body for POST /recorder/stop — stop recording and save."""

    name: str = "Untitled"
    description: str = ""


class WorkflowRunRequest(BaseModel):
    """Request body for POST /workflows/run — execute a workflow."""

    path: str
    variables: dict[str, Any] | None = None


class ScheduleAddRequest(BaseModel):
    """Request body for POST /schedule/add — create a scheduled task."""

    name: str
    goal: str
    cron: str | None = None
    delay_seconds: float | None = None


class ScheduleRemoveRequest(BaseModel):
    """Request body for POST /schedule/remove — delete a scheduled task."""

    task_id: str


class ScheduleRunRequest(BaseModel):
    """Request body for POST /schedule/run — trigger a task immediately."""

    task_id: str


class NotifyRequest(BaseModel):
    """Request body for POST /notify — send a desktop notification."""

    title: str = "Sentinel"
    message: str
    level: str = "info"


class PluginReloadRequest(BaseModel):
    """Request body for POST /plugins/reload — reload a named plugin."""

    name: str


class AgentSubmitRequest(BaseModel):
    """Request body for POST /agents/submit — queue an agent goal."""

    goal: str
    config: dict[str, Any] | None = None
    priority: str = "normal"


class AgentCancelRequest(BaseModel):
    """Request body for POST /agents/cancel — cancel a running agent."""

    session_id: str


class AuthLoginRequest(BaseModel):
    """Request body for POST /auth/login — authenticate a user."""

    username: str
    password: str


class AuthLogoutRequest(BaseModel):
    """Request body for POST /auth/logout — revoke a session token."""

    token: str


class OIDCTokenRequest(BaseModel):
    """Request body for POST /auth/oidc/token — exchange an OIDC id_token for a session."""

    id_token: str


# ── Server class ────────────────────────────────────────────────────────


class SentinelServer:
    """FastAPI headless control server for Sentinel Desktop.

    Manages the agent engine lifecycle, exposes REST and WebSocket
    endpoints for remote control, and bridges step events to
    connected WebSocket clients in real time.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the API server with application config.

        Args:
            config: Application :class:`Config` used to load provider settings
                and API token configuration.

        """
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
            # API_TOKEN auth is disabled; still allow valid JWTs when the
            # engine's auth_manager can validate them.
            if self.engine and authorization:
                user = self.engine.auth_manager.validate_jwt_token(authorization)
                if user is not None:
                    return  # valid JWT — grant access
            return  # no auth configured → allow all (legacy localhost mode)
        expected = f"Bearer {token}"
        if authorization and hmac.compare_digest(authorization, expected):
            return  # static API token match
        # Fall back to JWT validation when the static token doesn't match.
        if self.engine and authorization:
            user = self.engine.auth_manager.validate_jwt_token(authorization)
            if user is not None:
                return
        raise HTTPException(401, "Missing or invalid Authorization header")

    def create_app(self) -> FastAPI:
        """Build and return the configured FastAPI application instance."""
        # Rate-limiting state for login attempts: IP → [timestamp, ...]
        self._login_attempts: dict[str, list[float]] = defaultdict(list)
        self._login_limit = 5  # max attempts per window
        self._login_window = 300.0  # 5 minutes

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
            """Manage the FastAPI application lifespan (startup / shutdown)."""
            self._loop = asyncio.get_running_loop()
            yield

        app = FastAPI(
            title="Sentinel Desktop",
            description="AI-powered Windows desktop automation API",
            version=_CORE_VERSION,
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

        self._register_routes(app)
        return app

    def _register_routes(self, app: FastAPI) -> None:
        """Wire all API endpoints onto *app* and record them in the registry.

        v18: each route is recorded in ``self._route_registry`` (api.routes)
        as it is wired, making the full route table queryable for parity
        checks and docs. ``_route()`` both registers on the app and records.
        """
        self._route_registry = RouteRegistry()
        self._register_core_routes(app)
        self._register_v3_routes(app)
        self._register_v31_routes(app)
        # Pull in any @api_route-decorated handlers (future extension point).
        self._route_registry.add_decorated(self)

    def _route(self, app: FastAPI, method: str, path: str, handler: Callable) -> None:
        """Wire *handler* onto *app* at (method, path) and record it."""
        getattr(app, method.lower())(path)(handler)
        self._route_registry.add(method, path, handler)

    def _register_core_routes(self, app: FastAPI) -> None:
        """Register core v1 + v3.0 script/recorder/workflow/scheduler routes."""
        self._route(app, "POST", "/goal", self._handle_goal)
        self._route(app, "POST", "/command", self._handle_command)
        self._route(app, "GET", "/screenshot", self._handle_screenshot)
        self._route(app, "GET", "/status", self._handle_status)
        self._route(app, "GET", "/windows", self._handle_windows)
        self._route(app, "GET", "/processes", self._handle_processes)
        self._route(app, "GET", "/system", self._handle_system)
        self._route(app, "GET", "/config", self._handle_get_config)
        self._route(app, "PUT", "/config", self._handle_put_config)
        self._route(app, "GET", "/log", self._handle_log)
        self._route(app, "POST", "/stop", self._handle_stop)
        self._route(app, "GET", "/scripts", self._handle_scripts_list)
        self._route(app, "POST", "/scripts/run", self._handle_script_run)
        self._route(app, "POST", "/powershell", self._handle_powershell)
        self._route(app, "POST", "/recorder/start", self._handle_recorder_start)
        self._route(app, "POST", "/recorder/stop", self._handle_recorder_stop)

    def _register_v3_routes(self, app: FastAPI) -> None:
        """Register v3.0 Phase 2-4 routes: workflow, scheduler, auth, agents, vault."""
        self._route(app, "GET", "/workflows", self._handle_workflows_list)
        self._route(app, "POST", "/workflows/run", self._handle_workflow_run)
        self._route(app, "GET", "/schedule", self._handle_schedule_list)
        self._route(app, "POST", "/schedule/add", self._handle_schedule_add)
        self._route(app, "POST", "/schedule/remove", self._handle_schedule_remove)
        self._route(app, "POST", "/schedule/run", self._handle_schedule_run)
        self._route(app, "POST", "/notify", self._handle_notify)
        self._route(app, "GET", "/plugins", self._handle_plugins_list)
        self._route(app, "POST", "/plugins/reload", self._handle_plugins_reload)
        self._route(app, "GET", "/agents", self._handle_agents_list)
        self._route(app, "POST", "/agents/submit", self._handle_agents_submit)
        self._route(app, "POST", "/agents/cancel", self._handle_agents_cancel)
        self._route(app, "GET", "/agents/{session_id}", self._handle_agent_status)
        self._route(app, "POST", "/auth/login", self._handle_auth_login)
        self._route(app, "POST", "/auth/logout", self._handle_auth_logout)
        self._route(app, "GET", "/auth/users", self._handle_auth_users)
        self._route(app, "POST", "/auth/oidc/token", self._handle_auth_oidc_token)
        self._route(app, "GET", "/audit/export", self._handle_audit_export)
        self._route(app, "GET", "/vault/keys", self._handle_vault_keys)

    def _register_v31_routes(self, app: FastAPI) -> None:
        """Register v3.1 dashboard router and workflow builder endpoints."""
        app.include_router(dashboard_router)
        self._workflow_store = workflow_store
        self._workflow_templates = TEMPLATES
        self._route(app, "GET", "/workflows/builder/list", self._handle_workflow_builder_list)
        self._route(app, "POST", "/workflows/builder/create", self._handle_workflow_builder_create)
        self._route(app, "GET", "/workflows/builder/templates", self._handle_workflow_templates)
        self._route(
            app, "POST", "/workflows/builder/{wf_id}/add-step", self._handle_workflow_add_step
        )
        self._route(
            app, "POST", "/workflows/builder/{wf_id}/remove-step", self._handle_workflow_remove_step
        )
        self._route(
            app, "DELETE", "/workflows/builder/{wf_id}", self._handle_workflow_builder_delete
        )
        self._route(
            app, "POST", "/workflows/builder/{wf_id}/duplicate", self._handle_workflow_duplicate
        )
        self._route(app, "WEBSOCKET", "/ws", self._handle_ws)
        self._route(app, "WEBSOCKET", "/ws/terminal", self._handle_terminal_ws)
        # v10.0 — Sentinel Server routes
        self._route(app, "GET", "/daemon/status", self._handle_daemon_status)
        self._route(app, "POST", "/daemon/start", self._handle_daemon_start)
        self._route(app, "POST", "/daemon/stop", self._handle_daemon_stop)
        self._route(app, "GET", "/fleet/nodes", self._handle_fleet_nodes)
        self._route(app, "POST", "/fleet/register", self._handle_fleet_register)
        self._route(app, "POST", "/fleet/unregister", self._handle_fleet_unregister)
        self._route(app, "GET", "/jobs", self._handle_jobs_list)
        self._route(app, "POST", "/jobs/submit", self._handle_jobs_submit)
        self._route(app, "GET", "/jobs/{job_id}", self._handle_job_status)
        self._route(app, "POST", "/jobs/{job_id}/cancel", self._handle_job_cancel)
        # v11.0 — Memory routes
        self._route(app, "GET", "/memory/facts", self._handle_memory_list)
        self._route(app, "GET", "/memory/facts/{key}", self._handle_memory_get)
        self._route(app, "POST", "/memory/facts", self._handle_memory_store)
        self._route(app, "DELETE", "/memory/facts/{key}", self._handle_memory_delete)
        self._route(app, "GET", "/memory/search", self._handle_memory_search)
        self._route(app, "GET", "/memory/episodes", self._handle_episodes_list)
        self._route(app, "GET", "/memory/episodes/search", self._handle_episodes_search)
        # v12.0 — Conductor route
        self._route(app, "POST", "/conductor/run", self._handle_conductor_run)
        # Dashboard UI — serve static files (must be last; mount catches all sub-paths)
        self._route(app, "GET", "/", self._handle_dashboard_index)
        static_dir = str(Path(__file__).parent / "static")
        if Path(static_dir).is_dir():
            app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # ── Dashboard UI ────────────────────────────────────────────────────

    async def _handle_dashboard_index(self) -> FileResponse:
        """Serve the dashboard HTML page."""
        return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

    # ── v10.0 — Sentinel Server handlers ────────────────────────────────

    async def _handle_daemon_status(self) -> dict:
        """GET /daemon/status — Get daemon service status."""
        try:
            from core.server.daemon import SentinelDaemon

            daemon = SentinelDaemon()
            return {"success": True, "data": daemon.get_status()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_daemon_start(self) -> dict:
        """POST /daemon/start — Start the daemon service."""
        try:
            from core.server.daemon import SentinelDaemon

            daemon = SentinelDaemon()
            result = daemon.start()
            return {"success": True, "data": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_daemon_stop(self) -> dict:
        """POST /daemon/stop — Stop the daemon service."""
        try:
            from core.server.daemon import SentinelDaemon

            daemon = SentinelDaemon()
            result = daemon.stop()
            return {"success": True, "data": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_fleet_nodes(self) -> dict:
        """GET /fleet/nodes — List all fleet nodes."""
        try:
            from core.server.fleet import FleetManager

            fleet = FleetManager()
            return {"success": True, "data": fleet.list_nodes()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_fleet_register(self, data: dict) -> dict:
        """POST /fleet/register — Register a fleet node."""
        try:
            from core.server.fleet import FleetManager

            fleet = FleetManager()
            result = fleet.register_node(
                node_id=data.get("node_id", ""),
                hostname=data.get("hostname", ""),
                ip_address=data.get("ip_address", ""),
                role=data.get("role", "agent"),
                tags=data.get("tags"),
            )
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_fleet_unregister(self, data: dict) -> dict:
        """POST /fleet/unregister — Unregister a fleet node."""
        try:
            from core.server.fleet import FleetManager

            fleet = FleetManager()
            return fleet.unregister_node(data.get("node_id", ""))
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_jobs_list(self, status: str | None = None) -> dict:
        """GET /jobs — List jobs."""
        try:
            from core.server.job_queue import JobQueue

            queue = JobQueue()
            return {"success": True, "data": queue.list_jobs(status=status)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_jobs_submit(self, data: dict) -> dict:
        """POST /jobs/submit — Submit a new job."""
        try:
            from core.server.job_queue import JobQueue

            queue = JobQueue()
            job_id = queue.submit(
                goal=data.get("goal", ""),
                priority=data.get("priority", 0),
                node_id=data.get("node_id"),
            )
            return {"success": True, "job_id": job_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_job_status(self, job_id: str) -> dict:
        """GET /jobs/{job_id} — Get job status."""
        try:
            from core.server.job_queue import JobQueue

            queue = JobQueue()
            job = queue.get_job(job_id)
            if job is None:
                return {"success": False, "error": "Job not found"}
            return {"success": True, "data": job}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_job_cancel(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/cancel — Cancel a job."""
        try:
            from core.server.job_queue import JobQueue

            queue = JobQueue()
            result = queue.cancel(job_id)
            return {"success": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── v11.0 — Memory handlers ──────────────────────────────────────────

    async def _handle_memory_list(self, category: str = "") -> dict:
        """GET /memory/facts — List all memory facts."""
        try:
            from core.memory.semantic import SemanticMemory

            mem = SemanticMemory()
            keys = mem.list_keys(category=category)
            return {"success": True, "keys": keys, "count": len(keys)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_memory_get(self, key: str) -> dict:
        """GET /memory/facts/{key} — Get a specific fact."""
        try:
            from core.memory.semantic import SemanticMemory

            mem = SemanticMemory()
            result = mem.recall(key)
            if result is None:
                return {"success": False, "error": "Key not found"}
            return {"success": True, "data": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_memory_store(self, data: dict) -> dict:
        """POST /memory/facts — Store a new fact."""
        try:
            from core.memory.semantic import SemanticMemory

            mem = SemanticMemory()
            fact_id = mem.store(
                key=data.get("key", ""),
                value=data.get("value", ""),
                category=data.get("category", ""),
                tags=data.get("tags"),
                source=data.get("source", "api"),
            )
            return {"success": True, "fact_id": fact_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_memory_delete(self, key: str) -> dict:
        """DELETE /memory/facts/{key} — Delete a fact."""
        try:
            from core.memory.semantic import SemanticMemory

            mem = SemanticMemory()
            deleted = mem.delete(key)
            return {"success": deleted}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_memory_search(
        self,
        query: str = "",
        limit: int = 20,
    ) -> dict:
        """GET /memory/search?query=... — Search memory facts."""
        try:
            from core.memory.semantic import SemanticMemory

            mem = SemanticMemory()
            results = mem.query(query, limit=limit)
            return {"success": True, "results": results, "count": len(results)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_episodes_list(self, limit: int = 20) -> dict:
        """GET /memory/episodes — List recent episodes."""
        try:
            from core.memory.episodic import EpisodicMemory

            mem = EpisodicMemory()
            episodes = mem.recall(limit=limit)
            return {"success": True, "data": episodes, "count": len(episodes)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _handle_episodes_search(
        self,
        query: str = "",
        limit: int = 10,
    ) -> dict:
        """GET /memory/episodes/search?query=... — Search episodes."""
        try:
            from core.memory.episodic import EpisodicMemory

            mem = EpisodicMemory()
            results = mem.search(query, limit=limit)
            return {"success": True, "data": results, "count": len(results)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── v12.0 — Conductor handler ─────────────────────────────────────────

    async def _handle_conductor_run(self, data: dict) -> dict:
        """POST /conductor/run — Decompose and execute a complex goal."""
        try:
            from core.conductor.coordinator import Conductor

            conductor = Conductor()
            goal = data.get("goal", "")
            timeout = data.get("timeout", 120.0)
            result = await conductor.run(goal, timeout=timeout)
            return {"success": True, "data": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── Dashboard ──────────────────────────────────────────────────────

    # ── Terminal WebSocket (PTY shell proxy) ────────────────────────────

    def _setup_pty_child(self, slave_fd: int) -> NoReturn:
        """Set up child process for PTY and exec the platform-appropriate shell.

        Only called when _HAS_PTY is True (Unix only).
        """
        assert _HAS_PTY, "_setup_pty_child called without PTY support"
        os.close(slave_fd)
        os.setsid()

        # Acquire controlling terminal
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

        # Set initial terminal size
        winsize = struct.pack("HHHH", 24, 80, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        # Set environment
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLUMNS"] = "80"
        env["LINES"] = "24"
        if "HOME" not in env:
            env["HOME"] = str(Path.home())

        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        # Find the best available shell for this platform
        shell_candidates = ["/bin/bash", "/bin/zsh", "/bin/sh"]
        # On some systems, bash is at /usr/bin/bash
        if os.name != "nt":
            import shutil

            for candidate in [shutil.which("bash"), shutil.which("zsh"), shutil.which("sh")]:
                if candidate and candidate not in shell_candidates:
                    shell_candidates.insert(0, candidate)

        try:
            for shell in shell_candidates:
                if os.path.isfile(shell):
                    os.execvpe(shell, [shell, "--login"], env)  # noqa: S606
            # Last resort: just /bin/sh
            os.execvpe("/bin/sh", ["/bin/sh"], env)  # noqa: S606
        except OSError:
            os._exit(1)

    def _configure_master_fd_nonblocking(self, master_fd: int) -> None:
        """Set master_fd to non-blocking mode (Unix only)."""
        if not _HAS_PTY:
            return
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)  # type: ignore[union-attr]
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)  # type: ignore[union-attr]

    async def _read_pty(self, master_fd: int, ws: WebSocket) -> None:
        """Read PTY output and forward to WebSocket."""
        while True:
            try:
                data = os.read(master_fd, 4096)
                if not data:
                    break
                await asyncio.wait_for(
                    ws.send_json({"type": "data", "data": data.decode("utf-8", errors="replace")}),
                    timeout=5.0,
                )
            except (BlockingIOError, InterruptedError):
                await asyncio.sleep(0.01)
            except (OSError, ValueError):
                break
            except (asyncio.TimeoutError, ConnectionError, RuntimeError):
                break

    async def _handle_ws_timeout(self, ws: WebSocket) -> bool:
        """Handle WebSocket timeout by sending keepalive ping."""
        try:
            await asyncio.wait_for(
                ws.send_json({"type": "ping"}),
                timeout=5.0,
            )
            return True
        except (OSError, RuntimeError, ConnectionError):
            return False

    async def _handle_input_message(self, master_fd: int, msg: dict) -> bool:
        """Handle input message from WebSocket."""
        text = msg.get("data", "")
        try:
            os.write(master_fd, text.encode("utf-8"))
            return True
        except OSError:
            return False

    async def _handle_resize_message(self, master_fd: int, msg: dict) -> bool:
        """Handle resize message from WebSocket."""
        rows = int(msg.get("rows", 24))
        cols = int(msg.get("cols", 80))
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
            return True
        except OSError:
            return True  # Resize failure is not critical

    async def _handle_ping_message(self, ws: WebSocket) -> bool:
        """Handle ping message from WebSocket."""
        try:
            await asyncio.wait_for(
                ws.send_json({"type": "pong"}),
                timeout=5.0,
            )
            return True
        except (OSError, RuntimeError, ConnectionError):
            return False

    async def _process_ws_message(self, master_fd: int, ws: WebSocket, msg: dict) -> bool:
        """Process a single WebSocket message. Return False to break the loop."""
        msg_type = msg.get("type", "")

        if msg_type == "input":
            return await self._handle_input_message(master_fd, msg)
        elif msg_type == "resize":
            return await self._handle_resize_message(master_fd, msg)
        elif msg_type == "ping":
            return await self._handle_ping_message(ws)
        return True  # Unknown message type, continue

    async def _read_ws(self, master_fd: int, ws: WebSocket) -> None:
        """Read WebSocket messages and forward to PTY."""
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                msg = json.loads(raw)
            except asyncio.TimeoutError:
                if not await self._handle_ws_timeout(ws):
                    break
                continue
            except (json.JSONDecodeError, WebSocketDisconnect):
                continue
            except (ConnectionError, RuntimeError):
                break

            if not await self._process_ws_message(master_fd, ws, msg):
                break

    async def _cleanup_pty(self, child_pid: int, master_fd: int) -> None:
        """Clean up PTY resources."""
        try:
            os.kill(child_pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            os.waitpid(child_pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass

    async def _handle_terminal_ws(self, ws: WebSocket) -> None:
        """Spawn a PTY shell and proxy I/O over WebSocket.

        Only available on Unix (Linux/macOS). On Windows, returns an
        error message since PTY is not supported.
        """
        await ws.accept()

        if not _HAS_PTY:
            await ws.send_json(
                {
                    "type": "error",
                    "data": "Terminal not available on Windows — PTY requires Unix",
                }
            )
            await ws.close()
            return

        master_fd, slave_fd = pty.openpty()  # type: ignore[union-attr]
        child_pid = os.fork()

        if child_pid == 0:
            # ── Child process ──────────────────────────────────────────
            self._setup_pty_child(slave_fd)
        else:
            # ── Parent process (async event loop) ──────────────────────
            os.close(slave_fd)
            self._configure_master_fd_nonblocking(master_fd)

            try:
                read_pty_task = asyncio.create_task(self._read_pty(master_fd, ws))
                read_ws_task = asyncio.create_task(self._read_ws(master_fd, ws))
                done, pending = await asyncio.wait(
                    [read_pty_task, read_ws_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
            except (WebSocketDisconnect, ConnectionError, RuntimeError):
                pass
            finally:
                await self._cleanup_pty(child_pid, master_fd)

    # ── Agent control ───────────────────────────────────────────────

    async def _handle_goal(
        self,
        req: GoalRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        if self.engine and self.engine.running:
            raise HTTPException(409, "Agent already running — stop it first")

        cfg = self.config.load()
        if req.max_steps:
            cfg["max_steps"] = req.max_steps
        if req.approval_mode is not None:
            cfg["approval_mode"] = req.approval_mode

        # Validate and sanitize the goal
        try:
            safe_goal = req.validate_goal()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        self.engine = AgentEngine(cfg)
        # Bridge engine step events to all connected WebSocket clients.
        self.engine.on_step_callback = self._broadcast_step

        def _run() -> None:
            try:
                result = self.engine.run(safe_goal)
                logger.info("Agent finished: %d steps", result.get("steps", 0))
                self._broadcast_event(
                    {
                        "type": "done",
                        "result": {
                            "steps": result.get("steps", 0),
                            "summary": result.get("finish_summary", ""),
                        },
                    },
                )
            except (OSError, RuntimeError, ValueError) as exc:
                logger.exception("Agent run crashed")
                self._broadcast_event({"type": "error", "message": str(exc)})

        self._run_thread = threading.Thread(target=_run, daemon=True)
        self._run_thread.start()

        return {"status": "started", "goal": req.goal}

    async def _handle_command(
        self,
        req: CommandRequest,
        authorization: str | None = Header(default=None),
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

        try:
            # execute_sync() is blocking (may run desktop actions); offload to thread.
            return await asyncio.wait_for(
                asyncio.to_thread(engine.executor.execute_sync, payload),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, f"Invalid action payload: {exc}") from exc
        except asyncio.TimeoutError:
            timeout_msg = f"Command execution timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except OSError as exc:
            raise HTTPException(500, f"Action execution failed: {exc}") from exc
        except RuntimeError as exc:
            logger.exception("Unexpected error executing command")
            raise HTTPException(500, f"Internal error: {exc}") from exc

    async def _handle_stop(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        self._check_auth(authorization)
        if self.engine and self.engine.running:
            self.engine.stop()
            return {"status": "stopping"}
        return {"status": "not_running"}

    # ── Information endpoints ───────────────────────────────────────

    async def _handle_screenshot(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        self._check_auth(authorization)
        try:
            b64 = await asyncio.wait_for(
                asyncio.to_thread(capture_to_base64),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"Screenshot capture timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Screen capture failed: {exc}") from exc
        return {"screenshot": b64, "format": "png", "encoding": "base64"}

    async def _handle_status(
        self,
        authorization: str | None = Header(default=None),
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
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        try:
            windows = await asyncio.wait_for(
                asyncio.to_thread(wm.list_windows),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"List windows timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to list windows: {exc}") from exc
        return {"windows": windows}

    async def _handle_processes(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        try:
            processes = await asyncio.wait_for(
                asyncio.to_thread(pm.list_processes, 100),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"List processes timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to list processes: {exc}") from exc
        return {"processes": processes}

    async def _handle_system(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        try:
            info = await asyncio.wait_for(
                asyncio.to_thread(sysinfo.system_info),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"System info timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to get system info: {exc}") from exc
        return {"system": info}

    async def _handle_get_config(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        # Never leak the API key over the wire.
        cfg = dict(self.config.load())
        if cfg.get("api_key"):
            cfg["api_key"] = "***"
        return cfg

    async def _handle_put_config(
        self,
        req: ConfigUpdate,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        self._check_auth(authorization)
        cfg = self.config.load()
        # Pydantic v2 prefers model_dump; v1 only has .dict(). Support both.
        dump = getattr(req, "model_dump", None) or req.dict
        for k, v in dump(exclude_none=True).items():
            cfg[k] = v
        try:
            self.config.save(cfg)
        except OSError as exc:
            raise HTTPException(500, f"Failed to save config: {exc}") from exc
        return {"status": "saved"}

    async def _handle_log(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        self._check_auth(authorization)
        if self.engine:
            return {"log": self.engine.forensic_log}
        return {"log": []}

    # ── Script / Recorder / PowerShell endpoints ──────────────────────

    async def _handle_scripts_list(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List all available scripts in the scripts/ directory."""
        self._check_auth(authorization)
        try:
            from core.recorder import ActionRecorder

            scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
            scripts = ActionRecorder.list_scripts(scripts_dir)
        except (OSError, ValueError, ImportError) as exc:
            logger.warning("Failed to list scripts: %s", exc)
            return {"scripts": [], "error": str(exc)}
        else:
            return {"scripts": scripts}

    async def _handle_script_run(
        self,
        req: ScriptRunRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Run a script by path with optional parameters."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.script_engine import ScriptEngine

        # Validate and sanitize the script path
        safe_path = req.validate_path()

        engine = ScriptEngine(self.engine.executor)
        try:
            # run_script() replays multi-step scripts with sleep() delays;
            # run in thread pool so the event loop stays responsive.
            result = await asyncio.wait_for(
                asyncio.to_thread(engine.run_script, safe_path, req.params),
                timeout=LONG_OPERATION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.exception("Script execution timed out")
            timeout_msg = f"Script execution timed out after {LONG_OPERATION_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError) as exc:
            logger.exception("Script execution failed")
            raise HTTPException(500, f"Script execution failed: {exc}") from exc
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
        }

    async def _handle_powershell(
        self,
        req: PowerShellRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Run a PowerShell command."""
        self._check_auth(authorization)
        try:
            from core.powershell import get_default_runner

            runner = get_default_runner()
            # run_command() is blocking (up to the runner's 300 s timeout);
            # offload to thread pool so the event loop stays responsive.
            ps_result = await asyncio.wait_for(
                asyncio.to_thread(runner.run_command, req.command),
                timeout=LONG_OPERATION_TIMEOUT,
            )
            return {
                "success": ps_result.success,
                "stdout": ps_result.stdout[:5000],
                "stderr": ps_result.stderr[:2000],
                "exit_code": ps_result.exit_code,
                "objects": ps_result.objects[:100],
            }
        except asyncio.TimeoutError:
            logger.exception("PowerShell execution timed out")
            error_msg = f"PowerShell execution timed out after {LONG_OPERATION_TIMEOUT}s"
            return {"success": False, "error": error_msg}
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("PowerShell execution failed")
            return {"success": False, "error": str(exc)}

    async def _handle_recorder_start(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        """Start recording actions."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            self.engine.recorder.start_recording("")
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(500, f"Failed to start recording: {exc}") from exc
        return {"status": "recording"}

    async def _handle_recorder_stop(
        self,
        req: RecorderStopRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Stop recording and save the script."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            script = self.engine.recorder.stop_recording()
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(500, f"Failed to stop recording: {exc}") from exc
        name = req.name
        desc = req.description
        script.name = name
        script.description = desc or script.description
        try:
            scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            path = os.path.join(scripts_dir, f"{name.replace(' ', '_').lower()}.json")
            script.save(path)
            return {"status": "saved", "path": path, "steps": len(script.steps)}
        except OSError as exc:
            logger.exception("Failed to save recorded script")
            raise HTTPException(500, f"Failed to save script: {exc}") from exc

    # ── v3.0 Phase 2 endpoints ────────────────────────────────────────

    async def _handle_workflows_list(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List available workflows."""
        self._check_auth(authorization)
        try:
            from core.workflow import WorkflowEngine

            wf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")
            return {"workflows": WorkflowEngine.list_workflows(wf_dir)}
        except (OSError, ValueError, ImportError) as exc:
            logger.warning("Failed to list workflows: %s", exc)
            return {"workflows": [], "error": str(exc)}

    async def _handle_workflow_run(
        self,
        req: WorkflowRunRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Run a workflow."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.workflow import WorkflowEngine

        wf = WorkflowEngine(self.engine.executor, self.engine.script_engine)
        try:
            # run_workflow() replays multi-step workflows with delays; offload to thread.
            result = await asyncio.wait_for(
                asyncio.to_thread(wf.run_workflow, req.path, req.variables),
                timeout=LONG_OPERATION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.exception("Workflow execution timed out")
            timeout_msg = f"Workflow execution timed out after {LONG_OPERATION_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError) as exc:
            logger.exception("Workflow execution failed")
            raise HTTPException(500, f"Workflow execution failed: {exc}") from exc
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
            "elapsed": result.elapsed_seconds,
        }

    async def _handle_schedule_list(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List scheduled tasks."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"tasks": self.engine.scheduler.list_tasks()}

    async def _handle_schedule_add(
        self,
        req: ScheduleAddRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        """Add a scheduled task."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            task_id = self.engine.scheduler.add_task(req.model_dump())
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(400, f"Failed to add scheduled task: {exc}") from exc
        return {"status": "added", "task_id": task_id}

    async def _handle_schedule_remove(
        self,
        req: ScheduleRemoveRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        """Remove a scheduled task."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            removed = self.engine.scheduler.remove_task(req.task_id)
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to remove task: {exc}") from exc
        return {"status": "removed" if removed else "not_found"}

    async def _handle_schedule_run(
        self,
        req: ScheduleRunRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Run a scheduled task immediately."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            # run_task_now() can invoke scripts/goals/powershell — offload to thread.
            return await asyncio.wait_for(
                asyncio.to_thread(self.engine.scheduler.run_task_now, req.task_id),
                timeout=LONG_OPERATION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"Task execution timed out after {LONG_OPERATION_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            raise HTTPException(500, f"Failed to run task: {exc}") from exc

    async def _handle_notify(
        self,
        req: NotifyRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, bool]:
        """Send a notification."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            # notify() may make HTTP webhook calls; offload to thread pool.
            nm = self.engine.notifications
            success = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: nm.notify(title=req.title, message=req.message, level=req.level),
                ),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"Notification timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Notification failed: {exc}") from exc
        return {"success": success}

    async def _handle_plugins_list(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List loaded plugins."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            plugins = self.engine.plugin_loader.list_plugins()
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to list plugins: {exc}") from exc
        return {"plugins": plugins}

    async def _handle_plugins_reload(
        self,
        req: PluginReloadRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Reload a plugin."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        name = req.name
        try:
            # reload_plugin() imports Python modules from disk; offload to thread.
            success = await asyncio.wait_for(
                asyncio.to_thread(self.engine.plugin_loader.reload_plugin, name),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"Plugin reload timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            raise HTTPException(500, f"Failed to reload plugin: {exc}") from exc
        return {"success": success, "name": name}

    # ── v3.0 Phase 3+4 endpoints ──────────────────────────────────────

    async def _handle_agents_list(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List all agent pool sessions."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        return {"sessions": self.engine.agent_pool.list_sessions()}

    async def _handle_agents_submit(
        self,
        req: AgentSubmitRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        """Submit a goal to the agent pool."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            session_id = self.engine.agent_pool.submit(
                goal=req.goal,
                config=req.config,
                priority=req.priority,
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, f"Failed to submit agent: {exc}") from exc
        return {"session_id": session_id, "status": "queued"}

    async def _handle_agents_cancel(
        self,
        req: AgentCancelRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, bool]:
        """Cancel an agent session."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            success = self.engine.agent_pool.cancel(req.session_id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to cancel agent: {exc}") from exc
        return {"success": success}

    async def _handle_agent_status(
        self,
        session_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Get status of a specific agent session."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            status = self.engine.agent_pool.get_status(session_id)
        except KeyError as exc:
            raise HTTPException(404, "Session not found") from exc
        if status is None:
            raise HTTPException(404, "Session not found")
        return status

    async def _handle_auth_login(
        self,
        req: AuthLoginRequest,
        request: Request,
        authorization: str | None = Header(default=None),  # noqa: ARG002
    ) -> dict[str, str]:
        """Authenticate and get a session token."""
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        # Rate-limit login attempts per client IP.
        client_id = self._get_client_ip(request)
        now = time.monotonic()
        attempts = self._login_attempts[client_id]
        # Prune expired attempts.
        attempts[:] = [t for t in attempts if now - t < self._login_window]
        if len(attempts) >= self._login_limit:
            raise HTTPException(429, "Too many login attempts — try again later")
        attempts.append(now)

        try:
            # authenticate() runs bcrypt verification (CPU-intensive); offload to thread.
            user = await asyncio.wait_for(
                asyncio.to_thread(
                    self.engine.auth_manager.authenticate,
                    req.username,
                    req.password,
                ),
                timeout=DEFAULT_API_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"Authentication timed out after {DEFAULT_API_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Authentication error: {exc}") from exc
        if not user:
            raise HTTPException(401, "Invalid credentials")
        try:
            token = self.engine.auth_manager.create_session(user)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Session creation failed: {exc}") from exc
        role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
        response: dict[str, str] = {
            "token": token,
            "role": role_value,
            "username": user.username,
        }
        jwt_token = self.engine.auth_manager.create_jwt_session(user)
        if jwt_token is not None:
            response["jwt"] = jwt_token
        return response

    async def _handle_auth_logout(
        self,
        req: AuthLogoutRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        """Revoke a session token."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            self.engine.auth_manager.revoke_session(req.token)
        except (OSError, ValueError) as exc:
            logger.exception("Logout failed")
            raise HTTPException(500, f"Logout failed: {exc}") from exc
        return {"status": "logged_out"}

    async def _handle_auth_users(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List users (admin only)."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            return {"users": self.engine.auth_manager.list_users()}
        except (OSError, ValueError) as exc:
            logger.exception("Failed to list users")
            raise HTTPException(500, f"Failed to list users: {exc}") from exc

    async def _handle_auth_oidc_token(
        self,
        req: OIDCTokenRequest,
    ) -> dict[str, str]:
        """Exchange an OIDC id_token for a Sentinel session token.

        Validates the id_token, auto-provisions the user if needed, and
        returns the same payload as POST /auth/login.
        """
        from core.oidc import OIDCError, OIDCNotConfigured, OIDCTokenInvalid

        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            user = await asyncio.to_thread(
                self.engine.auth_manager.provision_from_oidc,
                req.id_token,
            )
        except OIDCNotConfigured as exc:
            raise HTTPException(503, f"OIDC not configured: {exc}") from exc
        except OIDCTokenInvalid as exc:
            raise HTTPException(401, f"Invalid OIDC token: {exc}") from exc
        except OIDCError as exc:
            raise HTTPException(400, f"OIDC error: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"User provisioning failed: {exc}") from exc

        try:
            token = self.engine.auth_manager.create_session(user)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Session creation failed: {exc}") from exc

        role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
        response: dict[str, str] = {
            "token": token,
            "role": role_value,
            "username": user.username,
        }
        jwt_token = self.engine.auth_manager.create_jwt_session(user)
        if jwt_token is not None:
            response["jwt"] = jwt_token
        return response

    async def _handle_audit_export(
        self,
        authorization: str | None = Header(default=None),
        format: str = "html",
    ) -> dict[str, str]:
        """Export audit log as HTML/JSON/CSV/Text."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            log = self.engine.forensic_log if hasattr(self.engine, "forensic_log") else []
            # generate_report() writes a file — offload to thread pool.
            path = await asyncio.wait_for(
                asyncio.to_thread(
                    self.engine.audit_exporter.generate_report,
                    log,
                    {"goal": "audit"},
                    format,
                ),
                timeout=LONG_OPERATION_TIMEOUT,
            )
            return {"path": path, "format": format}
        except asyncio.TimeoutError:
            timeout_msg = f"Audit export timed out after {LONG_OPERATION_TIMEOUT}s"
            raise HTTPException(504, timeout_msg) from None
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("Audit export failed")
            raise HTTPException(500, f"Audit export failed: {exc}") from exc

    async def _handle_vault_keys(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List credential vault keys."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            return {"keys": self.engine.vault.list_keys()}
        except (OSError, ValueError) as exc:
            logger.exception("Failed to list vault keys")
            raise HTTPException(500, f"Failed to list vault keys: {exc}") from exc

    # ── WebSocket broadcasting ──────────────────────────────────────

    def _broadcast_step(self, **kwargs: Any) -> None:  # noqa: ANN401
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
                await asyncio.wait_for(ws.send_json(event), timeout=5.0)
            except (OSError, RuntimeError, ConnectionError, asyncio.TimeoutError) as exc:
                logger.warning("WebSocket send failed, marking dead: %s", exc)
                dead.append(ws)
        if dead:
            with self._ws_lock:
                for ws in dead:
                    if ws in self._ws_clients:
                        self._ws_clients.remove(ws)

    async def _authenticate_ws(self, ws: WebSocket) -> bool:
        """Perform the initial auth handshake on *ws*. Returns True if auth passed."""
        try:
            auth_msg = await asyncio.wait_for(ws.receive_text(), timeout=10)
            auth_data = json.loads(auth_msg)
            auth_token = auth_data.get("token", "")
            api_token = os.environ.get(API_TOKEN_ENV)
            if api_token and auth_token != api_token:
                await asyncio.wait_for(
                    ws.send_json({"type": "auth_error", "message": "Invalid token"}),
                    timeout=5.0,
                )
                await ws.close()
                return False
        except asyncio.TimeoutError:
            logger.warning("WebSocket auth timed out — closing connection")
            await ws.close()
            return False
        except json.JSONDecodeError:
            logger.warning("WebSocket auth message was not valid JSON — closing connection")
            await ws.close()
            return False
        except (ConnectionError, RuntimeError):
            logger.exception("Unexpected error during WebSocket auth handshake")
            await ws.close()
            return False
        return True

    async def _handle_ws(self, ws: WebSocket) -> None:
        await ws.accept()
        if not await self._authenticate_ws(ws):
            return

        with self._ws_lock:
            self._ws_clients.append(ws)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                except asyncio.TimeoutError:
                    # No message for 60s — send a server-side ping to confirm liveness.
                    try:
                        await asyncio.wait_for(ws.send_json({"type": "ping"}), timeout=5.0)
                    except (OSError, RuntimeError, ConnectionError, asyncio.TimeoutError):
                        break  # Client is gone; exit the loop so finally cleans up.
                    continue
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "ping":
                    await asyncio.wait_for(ws.send_json({"type": "pong"}), timeout=5.0)
        except (WebSocketDisconnect, OSError, RuntimeError, ConnectionError, asyncio.TimeoutError):
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

    # ── Workflow Builder (v3.1) ───────────────────────────────────────────

    async def _handle_workflow_builder_list(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        workflows = self._workflow_store.list_all()
        return {"workflows": [wf.to_dict() for wf in workflows]}

    async def _handle_workflow_builder_create(
        self,
        name: str = "",
        description: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        # Validate and sanitize workflow name
        workflow_name = (name or "New Workflow").strip()
        if len(workflow_name) > MAX_WORKFLOW_NAME_LENGTH:
            # Prevent unreasonably long workflow names
            workflow_name = workflow_name[:MAX_WORKFLOW_NAME_LENGTH]
        if not workflow_name:
            workflow_name = "New Workflow"
        # Limit description length to prevent unreasonably long descriptions
        desc = description[:500] if description else ""
        wf = self._workflow_store.create(
            name=workflow_name,
            description=desc,
        )
        return wf.to_dict()

    async def _handle_workflow_templates(
        self,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        return {"templates": self._workflow_templates}

    async def _handle_workflow_add_step(
        self,
        wf_id: str,
        action: str = "",
        name: str = "",
        params: dict | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        wf = self._workflow_store.get(wf_id)
        if not wf:
            raise HTTPException(404, "Workflow not found")
        # Validate and sanitize step inputs
        step_action = (action or "").strip()
        step_name = (name or "").strip()[:100]  # Limit step name length
        step_params = params or {}

        if not step_action:
            raise HTTPException(400, "Action type is required")

        step = wf.add_step(action=step_action, name=step_name, params=step_params)
        return {"step": step.to_dict(), "workflow": wf.to_dict()}

    async def _handle_workflow_remove_step(
        self,
        wf_id: str,
        step_id: str = "",
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        wf = self._workflow_store.get(wf_id)
        if not wf:
            raise HTTPException(404, "Workflow not found")
        removed = wf.remove_step(step_id)
        return {"removed": removed, "workflow": wf.to_dict()}

    async def _handle_workflow_builder_delete(
        self,
        wf_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        deleted = self._workflow_store.delete(wf_id)
        return {"deleted": deleted}

    async def _handle_workflow_duplicate(
        self,
        wf_id: str,
        new_name: str | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        dup = self._workflow_store.duplicate(wf_id, new_name)
        if not dup:
            raise HTTPException(404, "Workflow not found")
        return dup.to_dict()
