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
