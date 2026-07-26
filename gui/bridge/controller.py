"""AgentController — thin QObject bridge between core engine and QML.

One QObject sits between the engine and QML, emitting signals the UI binds
to. No business logic moves into the view.

Signals:
    step_changed(int, int)       — current step, max steps
    screenshot_ready(QImage)     — live view image
    action_logged(str, str, str) — kind, text, timestamp
    state_changed(str)           — running | paused | idle | error
    log_entry(str, str)          — tag, message (for chat display)
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage

logger = logging.getLogger(__name__)


class _EngineThread(QThread):
    """Run the agent engine in a background QThread."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        engine: Any,
        goal: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._goal = goal

    def run(self) -> None:
        try:
            result = self._engine.run(self._goal)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class AgentController(QObject):
    """Bridge between core engine and QML Steel UI."""

    step_changed = Signal(int, int)
    screenshot_ready = Signal(QImage)
    action_logged = Signal(str, str, str)
    state_changed = Signal(str)
    log_entry = Signal(str, str)
    goal_finished = Signal(str, int, str)
    error_occurred = Signal(str)
    approval_needed = Signal(str, str)
    approval_response = Signal(bool)
    system_metrics = Signal(float, float, float)

    def __init__(self, config: dict[str, Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._engine: Any = None
        self._engine_thread: _EngineThread | None = None
        self._start_time = time.monotonic()
        self._state = "idle"
        self._step = 0
        self._max_steps = 100
        self._approval_event = threading.Event()
        self._approval_result = False

    def state(self) -> str:
        return self._state

    def _set_state(self, new_state: str) -> None:
        if self._state != new_state:
            self._state = new_state
            self.state_changed.emit(new_state)

    def _on_step(self, **kwargs: Any) -> None:
        step = kwargs.get("step", 0)
        action = kwargs.get("action", {})
        action_name = action.get("action", "?")
        params = {k: v for k, v in action.items() if k != "action"}
        kind = "act"
        if action_name in ("screenshot", "read_text", "find_image", "list_windows", "system_info", "list_processes", "list_controls", "read_file", "list_directory", "clipboard_read", "web_read", "web_extract", "web_tabs", "note"):
            kind = "see"
        elif action_name in ("wait", "focus_window", "open_app"):
            kind = "plan"

        ts = time.strftime("%H:%M:%S")
        self.step_changed.emit(step, self._max_steps)
        self.action_logged.emit(kind, f"Step {step}: {action_name}({params})", ts)

        screenshot_b64 = kwargs.get("screenshot")
        if screenshot_b64:
            self._emit_screenshot(screenshot_b64)

    def _emit_screenshot(self, b64_data: str) -> None:
        try:
            img_data = base64.b64decode(b64_data)
            img = QImage()
            img.loadFromData(img_data)
            if not img.isNull():
                self.screenshot_ready.emit(img)
        except Exception as exc:
            logger.debug("Screenshot decode failed: %s", exc)

    def _on_approval(self, action: dict[str, Any]) -> bool:
        action_name = action.get("action", "?")
        params = {k: v for k, v in action.items() if k != "action"}
        import json
        self.approval_needed.emit(action_name, json.dumps(params, indent=2)[:500])
        self._approval_event.clear()
        self._approval_result = False
        self._approval_event.wait(timeout=60)
        return self._approval_result

    @Slot(str)
    def run_goal(self, goal: str) -> None:
        if self._engine and getattr(self._engine, "running", False):
            self.log_entry.emit("error", "Agent already running. Stop it first.")
            return

        self._set_state("running")
        self._step = 0

        try:
            from config import Config
            from core.engine import AgentEngine

            config = Config()
            cfg = config.load()
            self._max_steps = cfg.get("max_steps", 100)

            self._engine = AgentEngine(
                cfg,
                approval_callback=self._on_approval,
                pre_action_callback=None,
            )
            self._engine.on_step_callback = self._on_step
        except Exception as exc:
            self._set_state("error")
            self.error_occurred.emit(f"Engine init failed: {exc}")
            return

        self.log_entry.emit("user", goal)
        self._engine_thread = _EngineThread(self._engine, goal, self)
        self._engine_thread.finished.connect(self._on_goal_finished)
        self._engine_thread.error.connect(self._on_goal_error)
        self._engine_thread.start()

    @Slot()
    def stop_goal(self) -> None:
        if self._engine and getattr(self._engine, "running", False):
            self._engine.stop()
            self.log_entry.emit("system", "Agent stopped by user.")
            self._set_state("idle")

    @Slot(bool)
    def respond_approval(self, approved: bool) -> None:
        self._approval_result = approved
        self._approval_event.set()

    def _on_goal_finished(self, result: dict) -> None:
        steps = result.get("steps", 0)
        summary = result.get("finish_summary", "")
        notes = result.get("notes") or []
        error = result.get("error")

        if error:
            for n in notes:
                self.log_entry.emit("error", f"\u274c {n}")
            self._set_state("error")
        elif not summary:
            msg = f"\u26a0\ufe0f Run ended after {steps} step{'s' if steps != 1 else ''}."
            if notes:
                msg += "\n" + "\n".join(notes[-3:])
            self.log_entry.emit("error", msg)
            self._set_state("idle")
        else:
            self.log_entry.emit("assistant", f"\u2705 Completed in {steps} step{'s' if steps != 1 else ''}.\n{summary}")
            self._set_state("idle")
            self.goal_finished.emit(summary, steps, "completed")

        if self._engine:
            self._engine.running = False

    def _on_goal_error(self, msg: str) -> None:
        self.log_entry.emit("error", f"\u274c {msg}")
        self._set_state("error")
        if self._engine:
            self._engine.running = False

    @Slot(result=float)
    def uptime(self) -> float:
        return time.monotonic() - self._start_time

    @Slot(result=int)
    def step(self) -> int:
        return self._step

    @Slot(result=int)
    def max_steps(self) -> int:
        return self._max_steps

    @Slot(str, str, str, str, int, bool, bool, bool)
    def saveSettings(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        max_steps: int,
        autonomous: bool,
        dry_run: bool,
        stealth_input: bool,
    ) -> None:
        self._config["provider"] = provider
        self._config["api_key"] = api_key
        self._config["model"] = model
        self._config["custom_base_url"] = base_url
        self._config["max_steps"] = max_steps
        self._config["autonomous"] = autonomous
        self._config["dry_run"] = dry_run
        self._config["stealth_input"] = stealth_input
        self._max_steps = max_steps

        try:
            from config import Config
            cfg = Config()
            cfg.save(self._config)
            self.log_entry.emit("system", f"Settings saved: {provider} / {model}")
        except (OSError, ValueError) as exc:
            self.log_entry.emit("error", f"Failed to save settings: {exc}")

    @Slot(result=str)
    def getProvider(self) -> str:
        return self._config.get("provider", "OpenAI")

    @Slot(result=str)
    def getApiKey(self) -> str:
        return self._config.get("api_key", "")

    @Slot(result=str)
    def getModel(self) -> str:
        return self._config.get("model", "")

    @Slot(result=str)
    def getBaseUrl(self) -> str:
        return self._config.get("custom_base_url", "")

    @Slot(result=int)
    def getMaxSteps(self) -> int:
        return self._config.get("max_steps", 100)

    @Slot(result=bool)
    def getAutonomous(self) -> bool:
        return bool(self._config.get("autonomous", False))

    @Slot(result=bool)
    def getDryRun(self) -> bool:
        return bool(self._config.get("dry_run", False))

    @Slot(result=bool)
    def getStealthInput(self) -> bool:
        return bool(self._config.get("stealth_input", False))
