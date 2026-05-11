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
import threading
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
        self._ws_clients = []

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="Sentinel Desktop v2",
            description="AI-powered Windows desktop automation API",
            version="2.0.0",
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
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
        app.websocket("/ws")(self._handle_ws)

        return app

    # ── Agent control ───────────────────────────────────────────────

    async def _handle_goal(self, req: GoalRequest):
        if self.engine and self.engine.running:
            raise HTTPException(409, "Agent already running — stop it first")

        cfg = self.config.load()
        if req.max_steps:
            cfg["max_steps"] = req.max_steps
        if req.approval_mode is not None:
            cfg["approval_mode"] = req.approval_mode

        self.engine = AgentEngine(cfg)

        # Run in background thread
        def _run():
            result = self.engine.run(req.goal)
            logger.info("Agent finished: %d steps", result.get("steps", 0))

        self._run_thread = threading.Thread(target=_run, daemon=True)
        self._run_thread.start()

        return {"status": "started", "goal": req.goal}

    async def _handle_command(self, req: CommandRequest):
        cfg = self.config.load()
        engine = AgentEngine(cfg)
        return engine.executor.execute_sync(json.loads(req.command)
                                            if req.command.strip().startswith("{")
                                            else {"action": "note", "text": req.command})

    async def _handle_stop(self):
        if self.engine and self.engine.running:
            self.engine.stop()
            return {"status": "stopping"}
        return {"status": "not_running"}

    # ── Information endpoints ───────────────────────────────────────

    async def _handle_screenshot(self):
        b64 = capture_to_base64()
        return {"screenshot": b64, "format": "png", "encoding": "base64"}

    async def _handle_status(self):
        if self.engine:
            return {
                "running": self.engine.running,
                "step": self.engine.step,
                "max_steps": self.engine.max_steps,
                "notes_count": len(self.engine.notes),
            }
        return {"running": False, "step": 0}

    async def _handle_windows(self):
        return {"windows": wm.list_windows()}

    async def _handle_processes(self):
        return {"processes": pm.list_processes(limit=100)}

    async def _handle_system(self):
        return {"system": sysinfo.system_info()}

    async def _handle_get_config(self):
        return self.config.load()

    async def _handle_put_config(self, req: ConfigUpdate):
        cfg = self.config.load()
        for k, v in req.dict(exclude_none=True).items():
            cfg[k] = v
        self.config.save(cfg)
        return {"status": "saved"}

    async def _handle_log(self):
        if self.engine:
            return {"log": self.engine.forensic_log}
        return {"log": []}

    # ── WebSocket ───────────────────────────────────────────────────

    async def _handle_ws(self, ws: WebSocket):
        await ws.accept()
        self._ws_clients.append(ws)
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
        except WebSocketDisconnect:
            self._ws_clients.remove(ws)
