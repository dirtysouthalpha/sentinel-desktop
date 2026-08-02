"""
Sentinel Desktop v31.0.0 — FastAPI Headless Control Server.

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
import hmac
import ipaddress
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

# Explicit, documented opt-out for the loopback-bind requirement below.
ALLOW_INSECURE_BIND_ENV = "SENTINEL_ALLOW_INSECURE_BIND"


class InsecureBindError(RuntimeError):
    """Raised when the API would listen off-host with authentication disabled."""


def _safe_script_stem(name: str) -> str:
    """Reduce a caller-supplied script name to a safe single-segment filename.

    Pre-v31 ``/recorder/stop`` only replaced spaces, so ``name`` values such as
    ``../../core/engine`` or ``..\\..\\x`` escaped the ``scripts/`` directory
    and wrote JSON over arbitrary files. This mirrors the alphanumeric
    whitelist already used by ``gui/recorder_panel.py``.
    """
    stem = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in (name or ""))
    stem = stem.strip("._-")
    return stem.lower() or "untitled"


def _is_loopback_host(host: str) -> bool:
    """True if *host* can only be reached from this machine."""
    h = (host or "").strip().strip("[]").lower()
    if h in {"localhost", "localhost.localdomain", ""}:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        # A hostname we can't classify (or a wildcard like "*"): not loopback.
        return False


def require_secure_bind(host: str) -> None:
    """Refuse to listen on a non-loopback interface with auth disabled.

    ``_check_auth`` is a no-op when ``SENTINEL_API_TOKEN`` is unset, while
    ``/powershell`` and ``/command`` execute arbitrary code. Binding
    ``0.0.0.0`` in that state publishes unauthenticated remote code execution
    to every reachable network, so it is now a hard startup error rather than
    a silent default.

    Set ``SENTINEL_ALLOW_INSECURE_BIND=1`` to override (e.g. when an external
    firewall or reverse proxy provides the authentication instead).

    Raises:
        InsecureBindError: non-loopback host, no token, no explicit override.
    """
    if os.environ.get(API_TOKEN_ENV):
        return
    if _is_loopback_host(host):
        return
    if os.environ.get(ALLOW_INSECURE_BIND_ENV, "").strip().lower() in {"1", "true", "yes"}:
        logger.warning(
            "Binding %s with authentication DISABLED because %s is set. "
            "/powershell and /command are reachable without credentials.",
            host,
            ALLOW_INSECURE_BIND_ENV,
        )
        return
    raise InsecureBindError(
        f"Refusing to bind {host!r} with authentication disabled: "
        f"/powershell and /command would allow unauthenticated remote code "
        f"execution. Set {API_TOKEN_ENV} to require a bearer token, bind "
        f"127.0.0.1 instead, or set {ALLOW_INSECURE_BIND_ENV}=1 to accept "
        f"the risk explicitly."
    )


# ── Request models ──────────────────────────────────────────────────────


class GoalRequest(BaseModel):
    """Request body for POST /goal — start a new agent run."""

    goal: str
    max_steps: int | None = None
    approval_mode: bool | None = None


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


# ── Server class ────────────────────────────────────────────────────────


class SentinelServer:
    """FastAPI headless control server for Sentinel Desktop.

    Manages the agent engine lifecycle, exposes REST and WebSocket
    endpoints for remote control, and bridges step events to
    connected WebSocket clients in real time.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine: AgentEngine | None = None
        self._run_thread: threading.Thread | None = None
        self._ws_clients: list[WebSocket] = []
        self._ws_lock = threading.Lock()
        # Cache the loop so worker threads can schedule broadcasts onto it.
        self._loop: asyncio.AbstractEventLoop | None = None
        # Workflow builder store + templates (initialized here so tests that
        # bypass create_app() still have them available).
        from core.workflow_builder import TEMPLATES, workflow_store

        self._workflow_store = workflow_store
        self._workflow_templates = TEMPLATES

    # -- auth ------------------------------------------------------------

    def _check_auth(self, authorization: str | None) -> None:
        token = os.environ.get(API_TOKEN_ENV)
        if not token:
            return  # auth disabled — see require_secure_bind()
        expected = f"Bearer {token}"
        # Constant-time compare: `!=` on the token leaks length/prefix through
        # timing, and /powershell and /command run arbitrary code.
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(401, "Missing or invalid Authorization header")

    def create_app(self) -> FastAPI:
        """Build and return the configured FastAPI application instance."""
        # Rate-limiting state for login attempts: IP → [timestamp, ...]
        self._login_attempts: dict[str, list[float]] = defaultdict(list)
        self._login_limit = 5  # max attempts per window
        self._login_window = 300.0  # 5 minutes

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            """Manage the FastAPI application lifespan (startup / shutdown)."""
            self._loop = asyncio.get_running_loop()
            # Initialize a persistent engine at startup so engine-backed
            # endpoints (plugins, scheduled tasks, scripts, recorder, workflows,
            # notifications) work without first running an agent goal. Guarded so
            # any failure degrades gracefully instead of crashing API startup.
            if self.engine is None:
                try:
                    self.engine = AgentEngine(self.config.load())
                    logger.info("Engine initialized at startup")
                    try:
                        sched = getattr(self.engine, "scheduler", None)
                        if sched is not None and hasattr(sched, "start"):
                            sched.start()
                            logger.info("Task scheduler started")
                    except Exception:
                        logger.exception("Scheduler failed to start (non-fatal)")
                except Exception:
                    logger.exception("Engine init at startup failed (non-fatal)")
                    self.engine = None
            yield

        app = FastAPI(
            title="Sentinel Desktop",
            description="AI-powered Windows desktop automation API",
            version="31.0.0",
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
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        )

        # v24.0.0: Security headers
        @app.middleware("http")
        async def add_security_headers(request: Request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Server"] = "Sentinel-Desktop"
            return response

        # v24.0.0: Rate limiting (60 req/min per IP)
        _rate_limits: dict[str, list[float]] = defaultdict(list)
        _RATE_WINDOW = 60.0
        _RATE_MAX = 60

        @app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < _RATE_WINDOW]
            if len(_rate_limits[client_ip]) >= _RATE_MAX:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
            _rate_limits[client_ip].append(now)
            return await call_next(request)

        # Register routes
        app.post("/goal")(self._handle_goal)
        app.post("/command")(self._handle_command)
        app.get("/screenshot")(self._handle_screenshot)
        app.get("/status")(self._handle_status)
        app.get("/health")(self._handle_health)
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
        app.get("/update-check")(self._handle_update_check)
        # v30.0.0 — Telemetry
        app.get("/telemetry")(self._handle_telemetry_summary)
        app.get("/telemetry/summary")(self._handle_telemetry_summary)
        app.get("/telemetry/runs")(self._handle_telemetry_runs)
        # v30.0.0 — Marketplace
        app.get("/marketplace/list")(self._handle_marketplace_list)
        app.post("/marketplace/install")(self._handle_marketplace_install)
        app.post("/plugins/reload")(self._handle_plugins_reload)
        # v27.0.0 - Sandbox
        app.get("/sandbox/status")(self._handle_sandbox_status)
        app.post("/sandbox/kill/{name}")(self._handle_sandbox_kill)
        # v28.0.0 - Swarm
        app.post("/swarm/create")(self._handle_swarm_create)
        app.post("/swarm/{swarm_id}/assign")(self._handle_swarm_assign)
        app.get("/swarm/{swarm_id}/status")(self._handle_swarm_status)
        app.post("/swarm/{swarm_id}/stop")(self._handle_swarm_stop)
        app.get("/swarm")(self._handle_swarm_list)
        app.get("/memory/search")(self._handle_memory_search)
        app.get("/memory/stats")(self._handle_memory_stats)
        app.post("/vision/analyze")(self._handle_vision_analyze)
        # v29.0.0 - Fleet
        app.get("/fleet/nodes")(self._handle_fleet_nodes)
        app.post("/fleet/deploy")(self._handle_fleet_deploy)
        app.get("/fleet/health")(self._handle_fleet_health)
        app.get("/fleet/events")(self._handle_fleet_events)
        # v30.0.0 - Playbooks/Workflow/Voice
        app.get("/playbooks")(self._handle_playbooks_list)
        app.get("/playbooks/stats")(self._handle_playbooks_stats)
        app.post("/playbooks/learn")(self._handle_playbooks_learn)
        app.post("/workflows/generate")(self._handle_workflow_generate)
        app.get("/voice/status")(self._handle_voice_status)
        app.post("/voice/speak")(self._handle_voice_speak)
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
        # v3.1 — System Dashboard, Workflow Builder
        from core.dashboard import router as dashboard_router

        app.include_router(dashboard_router)
        from core.workflow_builder import TEMPLATES, workflow_store

        self._workflow_store = workflow_store
        self._workflow_templates = TEMPLATES
        app.get("/workflows/builder/list")(self._handle_workflow_builder_list)
        app.post("/workflows/builder/create")(self._handle_workflow_builder_create)
        app.get("/workflows/builder/templates")(self._handle_workflow_templates)
        app.post("/workflows/builder/{wf_id}/add-step")(self._handle_workflow_add_step)
        app.post("/workflows/builder/{wf_id}/remove-step")(self._handle_workflow_remove_step)
        app.delete("/workflows/builder/{wf_id}")(self._handle_workflow_builder_delete)
        app.post("/workflows/builder/{wf_id}/duplicate")(self._handle_workflow_duplicate)

        # v31.1.0 — Dashboard filesystem browsing (root-jailed, see core/filesystem.py)
        app.get("/api/files")(self._handle_files_list)
        app.get("/api/files/content")(self._handle_files_content)
        app.get("/api/files/download")(self._handle_files_download)
        # v31.1.0 — Conversation persistence
        app.get("/api/conversations")(self._handle_convs_list)
        app.post("/api/conversations")(self._handle_convs_create)
        app.get("/api/conversations/{conv_id}")(self._handle_conv_get)
        app.delete("/api/conversations/{conv_id}")(self._handle_conv_delete)
        app.get("/api/conversations/{conv_id}/messages")(self._handle_conv_messages)
        app.post("/api/conversations/{conv_id}/messages")(self._handle_conv_add_message)

        # v30.0.0 — Dashboard static files
        from pathlib import Path as _P

        from fastapi.staticfiles import StaticFiles
        _dash_dir = _P(__file__).parent.parent / "dashboard"
        if _dash_dir.exists():
            app.mount("/dashboard", StaticFiles(directory=str(_dash_dir), html=True), name="dashboard")

        # v31.1.0 — Command Center "Prime".
        #
        # Prime had no server at all: it existed only as a file in the
        # sentinel-override repo and was opened over file://. On a file:// page
        # `location.host` is the empty string, so the dashboard's
        # `new WebSocket(`${proto}//${location.host}/ws`)` built `ws:///ws`,
        # which can never connect — and ws.onmessage is the only path an
        # assistant reply has. Serving it from this origin is what makes the
        # chat able to receive a response at all.
        #
        # The sentinel-override repo stays the source of truth. Candidates are
        # tried in order because this package runs from two trees: the dev clone
        # at C:\AgentLink\sentinel-desktop (where ../sentinel-override is a
        # sibling) and the deployed copy at C:\SentinelDesktop (where it is not).
        # SENTINEL_PRIME_DIR overrides both.
        _prime_candidates = [
            os.environ.get("SENTINEL_PRIME_DIR"),
            _P(__file__).parent.parent.parent / "sentinel-override" / "web",
            _P(r"C:\AgentLink\sentinel-override\web"),
        ]
        _prime_index = None
        for _candidate in _prime_candidates:
            if not _candidate:
                continue
            _prime_dir = _P(_candidate)
            if _prime_dir.is_dir():
                app.mount("/prime", StaticFiles(directory=str(_prime_dir), html=True), name="prime")
                logger.info("Prime dashboard served from %s", _prime_dir)
                _idx = _prime_dir / "dashboard-prime.html"
                if _idx.is_file():
                    _prime_index = str(_idx)
                break
        else:
            logger.warning("Prime dashboard directory not found; /prime not mounted")

        # v32 — serve Prime at the ROOT and evict any stale service worker.
        #
        # prime.dirtysouthalpha.com reaches this origin at "/", which used to
        # 404 — so browsers kept running a CACHED older PWA (v17-boot.js /
        # council.js) from a registered service worker, complete with a syntax
        # error, instead of the current dashboard. Two fixes:
        #  1) serve the current dashboard at "/", so once the stale SW is gone
        #     the right app loads;
        #  2) ship a SELF-DESTRUCTING service worker at the paths a prior PWA is
        #     likely to have registered, so the browser's next SW update check
        #     unregisters it and drops its caches. The current dashboard
        #     registers no SW of its own.
        from starlette.responses import FileResponse as _FileResponse
        from starlette.responses import Response as _PlainResponse

        if _prime_index:
            @app.get("/", include_in_schema=False)
            async def _serve_prime_root():
                # no-store so Cloudflare never caches the cockpit HTML again —
                # a stale edge-cached copy of an old build is exactly what shadowed
                # this page (Cloudflare served a cached v17 app while the origin
                # was healthy). After a one-time cache purge, this keeps it fresh.
                return _FileResponse(_prime_index, headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "CDN-Cache-Control": "no-store",
                })

        _SW_KILL = (
            "self.addEventListener('install', () => self.skipWaiting());\n"
            "self.addEventListener('activate', async () => {\n"
            "  try { const ks = await caches.keys();\n"
            "        await Promise.all(ks.map(k => caches.delete(k))); } catch (e) {}\n"
            "  try { await self.registration.unregister(); } catch (e) {}\n"
            "  try { const cs = await self.clients.matchAll();\n"
            "        cs.forEach(c => c.navigate(c.url)); } catch (e) {}\n"
            "});\n"
        )

        async def _sw_kill():
            return _PlainResponse(
                _SW_KILL, media_type="application/javascript",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

        for _swpath in ("/sw.js", "/service-worker.js", "/v17-sw.js", "/worker.js"):
            app.add_api_route(_swpath, _sw_kill, methods=["GET"],
                              include_in_schema=False)


        # v31.1.1 — Brain API reverse proxy.
        #
        # The dashboard runs in the browser and cannot reach localhost:8001
        # (the Neuralis brain) directly. This proxy bridges the two: the
        # dashboard calls /__brain/* on this origin, and we forward to the
        # brain. Keeps the brain off the public internet while still letting
        # the dashboard panels (stats, health, fleet, cognition) load.
        from starlette.responses import Response as _StarletteResponse
        import httpx as _httpx

        _BRAIN_URL = "http://localhost:8001"

        @app.api_route("/__brain/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
        async def _brain_proxy(request: Request, path: str):
            """Proxy requests to the Neuralis brain."""
            target_url = f"{_BRAIN_URL}/{path}"
            if request.url.query:
                target_url += f"?{request.url.query}"
            headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
            body = await request.body()
            try:
                async with _httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.request(
                        method=request.method,
                        url=target_url,
                        headers=headers,
                        content=body,
                    )
                return _StarletteResponse(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                )
            except Exception as exc:
                logger.error("Brain proxy error: %s", exc)
                return _StarletteResponse(
                    content=f'{{"error":"brain proxy error: {exc}"}}',
                    status_code=502,
                    media_type="application/json",
                )

        app.websocket("/ws")(self._handle_ws)

        return app

    async def _handle_health(self) -> dict[str, Any]:
        """Health check endpoint for load balancers and monitoring."""
        import psutil

        from core import __version__ as ver
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        return {
            "status": "healthy" if mem.percent < 90 else "degraded",
            "version": ver,
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "engine_active": bool(self.engine and self.engine.running),
        }

    async def _handle_update_check(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Check if a newer version is available on GitHub."""
        self._check_auth(authorization)
        from core.updater import is_update_available
        available, latest = is_update_available()
        return {
            "update_available": available,
            "current_version": __import__("core", fromlist=["__version__"]).__version__,
            "latest_version": latest,
        }

    async def _handle_telemetry_summary(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return aggregated telemetry summary."""
        self._check_auth(authorization)
        from core.telemetry import get_collector
        tc = get_collector()
        return tc.get_summary()

    async def _handle_telemetry_runs(
        self, limit: int = 20, authorization: str | None = Header(default=None)
    ) -> list[dict[str, Any]]:
        """Return recent agent runs."""
        self._check_auth(authorization)
        from core.telemetry import get_collector
        tc = get_collector()
        return tc.get_recent_runs(limit=limit)

    async def _handle_marketplace_list(
        self, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List available plugins from marketplace registry."""
        self._check_auth(authorization)
        from core.marketplace import get_marketplace_listing
        return {"plugins": get_marketplace_listing()}

    async def _handle_marketplace_install(
        self, req: Request, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Install a plugin from the marketplace."""
        self._check_auth(authorization)
        from core.marketplace import install_plugin
        body = await req.json()
        name = body.get("name", "")
        if not name:
            raise HTTPException(400, "Plugin name required")
        return install_plugin(name)

    async def _handle_marketplace_uninstall(
        self, name: str, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Uninstall a plugin."""
        self._check_auth(authorization)
        from core.marketplace import uninstall_plugin
        return uninstall_plugin(name)

    # ── Agent control ───────────────────────────────────────────────

    async def _handle_goal(self, req: GoalRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        self._check_auth(authorization)
        if not req.goal or not req.goal.strip():
            raise HTTPException(400, "Goal must not be empty")
        if len(req.goal) > 10000:
            raise HTTPException(413, "Goal too long (max 10000 characters)")
        if self.engine and self.engine.running:
            raise HTTPException(409, "Agent already running — stop it first")

        cfg = self.config.load()
        if req.max_steps:
            cfg["max_steps"] = req.max_steps
        if req.approval_mode is not None:
            cfg["approval_mode"] = req.approval_mode

        # Create a fresh engine per goal for clean state, but clean up
        # any existing engine first to prevent resource leaks.
        if self.engine is not None:
            try:
                if hasattr(self.engine, "cleanup"):
                    self.engine.cleanup()
            except Exception:
                pass  # Best-effort cleanup
        self.engine = AgentEngine(cfg)
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
            except (OSError, RuntimeError, ValueError) as exc:
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

        try:
            return engine.executor.execute_sync(payload)
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, f"Invalid action payload: {exc}") from exc
        except OSError as exc:
            raise HTTPException(500, f"Action execution failed: {exc}") from exc
        except RuntimeError as exc:
            logger.exception("Unexpected error executing command")
            raise HTTPException(500, f"Internal error: {exc}") from exc

    async def _handle_stop(self, authorization: str | None = Header(default=None)) -> dict[str, str]:
        self._check_auth(authorization)
        if self.engine and self.engine.running:
            self.engine.stop()
            return {"status": "stopping"}
        return {"status": "not_running"}

    # ── Information endpoints ───────────────────────────────────────

    async def _handle_screenshot(self, authorization: str | None = Header(default=None)) -> dict[str, str]:
        self._check_auth(authorization)
        try:
            b64 = capture_to_base64()
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Screen capture failed: {exc}") from exc
        return {"screenshot": b64, "format": "png", "encoding": "base64"}

    async def _handle_status(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        # Intentionally unauthenticated: this returns only agent-loop liveness
        # ({"running": false, "step": 0, "max_steps": 100, "notes_count": 0}) and
        # is what fleet monitors poll. Gating it broke fleet health checks across
        # the mesh while /dashboard/overview - hostname, OS, CPU, RAM, disks -
        # stayed wide open, i.e. the gating was inverted. The recon endpoint is
        # now the authenticated one; see core.dashboard.require_token.
        if self.engine:
            return {
                "running": self.engine.running,
                "step": self.engine.step,
                "max_steps": self.engine.max_steps,
                "notes_count": len(self.engine.notes),
            }
        return {"running": False, "step": 0}

    async def _handle_windows(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        self._check_auth(authorization)
        try:
            windows = wm.list_windows()
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to list windows: {exc}") from exc
        return {"windows": windows}

    async def _handle_processes(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        self._check_auth(authorization)
        try:
            processes = pm.list_processes(limit=100)
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to list processes: {exc}") from exc
        return {"processes": processes}

    async def _handle_system(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        self._check_auth(authorization)
        try:
            info = sysinfo.system_info()
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Failed to get system info: {exc}") from exc
        return {"system": info}

    async def _handle_get_config(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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

    async def _handle_scripts_list(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        self, req: ScriptRunRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a script by path with optional parameters."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.script_engine import ScriptEngine

        engine = ScriptEngine(self.engine.executor)
        try:
            result = engine.run_script(req.path, req.params)
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
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("PowerShell execution failed")
            return {"success": False, "error": str(exc)}

    async def _handle_recorder_start(self, authorization: str | None = Header(default=None)) -> dict[str, str]:
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
        self, req: RecorderStopRequest, authorization: str | None = Header(default=None)
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
            path = os.path.join(scripts_dir, f"{_safe_script_stem(name)}.json")
            script.save(path)
            return {"status": "saved", "path": path, "steps": len(script.steps)}
        except OSError as exc:
            logger.exception("Failed to save recorded script")
            raise HTTPException(500, f"Failed to save script: {exc}") from exc

    # ── v3.0 Phase 2 endpoints ────────────────────────────────────────

    async def _handle_workflows_list(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        self, req: WorkflowRunRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a workflow."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        from core.workflow import WorkflowEngine

        wf = WorkflowEngine(self.engine.executor, self.engine.script_engine)
        try:
            result = wf.run_workflow(req.path, req.variables)
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

    async def _handle_schedule_list(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        try:
            task_id = self.engine.scheduler.add_task(req.model_dump())
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(400, f"Failed to add scheduled task: {exc}") from exc
        return {"status": "added", "task_id": task_id}

    async def _handle_schedule_remove(
        self, req: ScheduleRemoveRequest, authorization: str | None = Header(default=None)
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
        self, req: ScheduleRunRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Run a scheduled task immediately."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            return self.engine.scheduler.run_task_now(req.task_id)
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            raise HTTPException(500, f"Failed to run task: {exc}") from exc

    async def _handle_notify(
        self, req: NotifyRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, bool]:
        """Send a notification."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            success = self.engine.notifications.notify(
                title=req.title,
                message=req.message,
                level=req.level,
            )
        except (OSError, RuntimeError) as exc:
            raise HTTPException(500, f"Notification failed: {exc}") from exc
        return {"success": success}

    async def _handle_plugins_list(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        self, req: PluginReloadRequest, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Reload a plugin."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        name = req.name
        try:
            success = self.engine.plugin_loader.reload_plugin(name)
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            raise HTTPException(500, f"Failed to reload plugin: {exc}") from exc
        return {"success": success, "name": name}

    # ── v3.0 Phase 3+4 endpoints ──────────────────────────────────────

    async def _handle_agents_list(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        self, req: AgentCancelRequest, authorization: str | None = Header(default=None)
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
        self, session_id: str, authorization: str | None = Header(default=None)
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
        authorization: str | None = Header(default=None),
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
            user = self.engine.auth_manager.authenticate(req.username, req.password)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Authentication error: {exc}") from exc
        if not user:
            raise HTTPException(401, "Invalid credentials")
        try:
            token = self.engine.auth_manager.create_session(user)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"Session creation failed: {exc}") from exc
        return {"token": token, "role": user.role.value, "username": user.username}

    async def _handle_auth_logout(
        self, req: AuthLogoutRequest, authorization: str | None = Header(default=None)
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

    async def _handle_auth_users(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        """List users (admin only)."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            return {"users": self.engine.auth_manager.list_users()}
        except (OSError, ValueError) as exc:
            logger.exception("Failed to list users")
            raise HTTPException(500, f"Failed to list users: {exc}") from exc

    async def _handle_audit_export(
        self, authorization: str | None = Header(default=None), format: str = "html"
    ) -> dict[str, str]:
        """Export audit log as HTML/JSON/CSV/Text."""
        self._check_auth(authorization)
        if not self.engine:
            raise HTTPException(500, "Engine not initialized")
        try:
            log = self.engine.forensic_log if hasattr(self.engine, "forensic_log") else []
            path = self.engine.audit_exporter.generate_report(log, metadata={"goal": "audit"}, format=format)
            return {"path": path, "format": format}
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("Audit export failed")
            raise HTTPException(500, f"Audit export failed: {exc}") from exc

    async def _handle_vault_keys(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("WebSocket send failed, marking dead: %s", exc)
                dead.append(ws)
        if dead:
            with self._ws_lock:
                for ws in dead:
                    if ws in self._ws_clients:
                        self._ws_clients.remove(ws)

    # NOTE: every handler below takes ``authorization`` and calls
    # ``_check_auth``. Pre-v31 this whole block was unauthenticated even when
    # SENTINEL_API_TOKEN was set, so an anonymous caller could spawn swarms,
    # deploy fleet goals, read agent memory and install plugins (which execute
    # Python). Only ``/health`` is intentionally left open, for load balancers.

    async def _handle_sandbox_status(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.sandbox import list_active
        return {"plugins": list_active()}

    async def _handle_sandbox_kill(self, name: str, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.sandbox import kill_plugin
        return kill_plugin(name)

    async def _handle_swarm_create(self, req: Request, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.swarm import get_manager
        body = await req.json()
        swarm = get_manager().create_swarm(body.get("name", "swarm"), body.get("agents", 3))
        return swarm.get_status()

    async def _handle_swarm_assign(
        self, swarm_id: str, req: Request, authorization: str | None = Header(default=None)
    ):
        self._check_auth(authorization)
        from core.swarm import get_manager
        body = await req.json()
        return get_manager().assign_task(swarm_id, body.get("goal", ""))

    async def _handle_swarm_status(self, swarm_id: str, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.swarm import get_manager
        s = get_manager().get_swarm(swarm_id)
        if not s: raise HTTPException(404, "Swarm not found")
        return s.get_status()

    async def _handle_swarm_stop(self, swarm_id: str, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.swarm import get_manager
        return get_manager().stop_swarm(swarm_id)

    async def _handle_swarm_list(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.swarm import get_manager
        return {"swarms": get_manager().list_swarms()}

    async def _handle_memory_search(self, q: str = "", authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.memory.vector_store import get_store
        if not q: return {"results": [], "query": ""}
        return {"results": get_store().search(q, limit=5), "query": q}

    async def _handle_memory_stats(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.memory.vector_store import get_store
        return get_store().get_stats()

    async def _handle_vision_analyze(self, req: Request, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.vision.pipeline import analyze_screenshot
        body = await req.json()
        return analyze_screenshot(image_b64=body.get("image", "")).to_dict()

    async def _handle_fleet_nodes(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.fleet.redis_bus import get_fleet
        return {"nodes": get_fleet().list_nodes()}

    async def _handle_fleet_deploy(self, req: Request, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.fleet.redis_bus import get_fleet
        body = await req.json()
        return get_fleet().deploy_agent(body.get("node_id", ""), body.get("goal", ""))

    async def _handle_fleet_health(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.fleet.redis_bus import get_fleet
        return get_fleet().get_fleet_health()

    async def _handle_fleet_events(self, channel: str = "", authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.fleet.redis_bus import get_fleet
        return {"events": get_fleet().get_events(channel or None, limit=50)}

    async def _handle_playbooks_list(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.learning.playbook import get_manager
        return {"playbooks": get_manager().list_playbooks()}

    async def _handle_playbooks_stats(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.learning.playbook import get_manager
        return get_manager().get_stats()

    async def _handle_playbooks_learn(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.learning.playbook import get_manager  # noqa: F401
        return {"success": True, "playbooks_created": 0}

    async def _handle_workflow_generate(self, req: Request, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.nl_workflow import generate_workflow
        body = await req.json()
        return generate_workflow(body.get("description", ""))

    async def _handle_voice_status(self, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.voice.control import get_voice_status
        return get_voice_status()

    async def _handle_voice_speak(self, req: Request, authorization: str | None = Header(default=None)):
        self._check_auth(authorization)
        from core.voice.control import text_to_speech
        body = await req.json()
        r = text_to_speech(body.get("text", ""))
        return {"success": r.success, "text": r.text, "error": r.error}

    async def _handle_ws(self, ws: WebSocket) -> None:
        await ws.accept()
        # Require authentication via first message: {"type": "auth", "token": "..."}
        try:
            auth_msg = await asyncio.wait_for(ws.receive_text(), timeout=10)
            auth_data = json.loads(auth_msg)
            auth_token = auth_data.get("token", "")
            # Validate the token (constant-time — see _check_auth).
            api_token = os.environ.get(API_TOKEN_ENV)
            if api_token and not hmac.compare_digest(str(auth_token), api_token):
                await ws.send_json({"type": "auth_error", "message": "Invalid token"})
                await ws.close()
                return
        except asyncio.TimeoutError:
            logger.warning("WebSocket auth timed out — closing connection")
            await ws.close()
            return
        except json.JSONDecodeError:
            logger.warning("WebSocket auth message was not valid JSON — closing connection")
            await ws.close()
            return
        except (ConnectionError, RuntimeError):
            logger.exception("Unexpected error during WebSocket auth handshake")
            await ws.close()
            return

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

    async def _handle_workflow_builder_list(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        wf = self._workflow_store.create(
            name=name or "New Workflow",
            description=description,
        )
        return wf.to_dict()

    async def _handle_workflow_templates(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
        step = wf.add_step(action=action, name=name, params=params or {})
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

    # -- v31.1.0: dashboard filesystem -----------------------------------
    #
    # These three endpoints are what the Command Center's file explorer has
    # been calling since v8. They never existed, so the panel read "Cannot
    # list directory" on every load.
    #
    # They are arbitrary file read over HTTP on a Tailscale-reachable host,
    # so every path goes through core.filesystem's root jail. See that
    # module for why containment is checked after resolve() and not before.

    @staticmethod
    def _fs_error(exc) -> HTTPException:
        """Map a jail refusal onto its HTTP status.

        503 is preserved rather than flattened to 500: the dashboard's
        apiFetch() renders 'degraded' differently from 'error', and "no roots
        are configured" is a service-configuration problem, not a bad request.
        """
        return HTTPException(exc.status, exc.message)

    async def _handle_files_list(
        self,
        path: str | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core.filesystem import FilesystemError, allowed_roots, list_directory

        # No path → the first configured root, so the explorer opens somewhere
        # legal instead of at a hardcoded C:\ that the jail would refuse.
        if not (path or "").strip():
            roots = allowed_roots()
            if not roots:
                raise HTTPException(503, "No browsable roots are configured")
            path = str(roots[0])
        try:
            return list_directory(path)
        except FilesystemError as exc:
            raise self._fs_error(exc) from exc

    async def _handle_files_content(
        self,
        path: str | None = None,
        max_bytes: int | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core.filesystem import FilesystemError, read_file

        try:
            return read_file(path, max_bytes)
        except FilesystemError as exc:
            raise self._fs_error(exc) from exc

    async def _handle_files_download(
        self,
        path: str | None = None,
        authorization: str | None = Header(default=None),
    ):
        self._check_auth(authorization)
        from fastapi.responses import FileResponse

        from core.filesystem import FilesystemError, open_for_download

        try:
            target, filename = open_for_download(path)
        except FilesystemError as exc:
            raise self._fs_error(exc) from exc
        # application/octet-stream + attachment: never let the browser decide to
        # render a downloaded file inline on this origin.
        return FileResponse(
            str(target),
            media_type="application/octet-stream",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # -- v31.1.0: conversation persistence -------------------------------

    async def _handle_convs_list(
        self,
        q: str | None = None,
        limit: int = 200,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core import conversations

        if (q or "").strip():
            return {"conversations": conversations.search(q, limit)}
        return {"conversations": conversations.list_all(limit)}

    async def _handle_convs_create(
        self,
        req: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core import conversations

        title = None
        try:
            body = await req.json()
            if isinstance(body, dict):
                title = body.get("title")
        except Exception:
            pass  # the dashboard POSTs with no body at all
        return conversations.create(title)

    async def _handle_conv_get(
        self,
        conv_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core import conversations

        conv = conversations.get(conv_id)
        if conv is None:
            raise HTTPException(404, "Conversation not found")
        conv["messages"] = conversations.messages(conv_id)
        return conv

    async def _handle_conv_delete(
        self,
        conv_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core import conversations

        if not conversations.delete(conv_id):
            raise HTTPException(404, "Conversation not found")
        return {"deleted": True, "id": conv_id}

    async def _handle_conv_messages(
        self,
        conv_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core import conversations

        if conversations.get(conv_id) is None:
            raise HTTPException(404, "Conversation not found")
        return {"messages": conversations.messages(conv_id)}

    async def _handle_conv_add_message(
        self,
        conv_id: str,
        req: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        self._check_auth(authorization)
        from core import conversations

        try:
            body = await req.json()
        except Exception as exc:
            raise HTTPException(400, "Body must be JSON") from exc
        if not isinstance(body, dict):
            raise HTTPException(400, "Body must be a JSON object")
        try:
            return conversations.add_message(conv_id, body.get("role", ""), body.get("content", ""))
        except KeyError as exc:
            # A message for an unknown conversation is a 404, not an implicit
            # create: silently creating one lets a typo'd id fork the history.
            raise HTTPException(404, "Conversation not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
