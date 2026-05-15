"""
Sentinel Desktop v2 — Agent Engine.

The main agent loop: user provides a goal, the engine takes screenshots,
sends them to the LLM, receives action decisions, executes them, and
repeats until completion or step budget exhaustion.

Supports both sync and async usage:
  - sync: engine.run(goal)           — blocks until done, used by GUI/API
  - async: await engine.run_goal(goal) — for future async callers
"""

import json
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from core import failsafe
from core import system_info as sysinfo
from core import window_manager as wm
from core.action_executor import ActionExecutor
from core.action_schemas import validate_action
from core.app_profiles import detect_profile
from core.approval_gate import ApprovalDecision, ApprovalGate
from core.checkpoint import CheckpointManager
from core.forensic_log import ForensicLog
from core.llm_client import LLMClient, LLMError
from core.mfa_detection import MFADetector
from core.recovery import RecoveryEngine
from core.screenshot import capture_to_base64, get_capture_offset
from core.smart_wait import SmartWait
from core.tool_schemas import TOOL_CAPABLE_PROVIDERS
from core.tool_schemas import TOOLS as ACTION_TOOLS

logger = logging.getLogger(__name__)

# Maximum number of screenshot messages kept in-context at once. Older
# screenshots get rewritten to a short text stub so the token budget doesn't
# grow unboundedly across long runs.
DEFAULT_IMAGE_HISTORY = 3

# Actions the agent can request that we always show to the user before
# executing when approval_mode is on. Read-only actions like screenshot,
# note, find_image, etc. are not gated.
APPROVAL_REQUIRED_ACTIONS = {
    "click",
    "double_click",
    "right_click",
    "drag",
    "click_image",
    "type_text",
    "press_key",
    "hotkey",
    "scroll",
    "open_app",
    "start_process",
    "close_app",
    "kill_process",
    "close_window",
    "write_file",
}

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a desktop automation agent. You see screenshots of a Windows desktop \
and take actions to accomplish the user's goal.

## Environment
{env_context}
{app_context}

## Loop
1. LOOK at the screenshot.
2. Return ONE JSON action.
3. Observe the next screenshot.
4. Repeat until done, then finish.

## Actions — return ONE JSON object per step. No markdown. No commentary.

### Mouse
{"action": "click", "x": 500, "y": 300}
{"action": "click", "x": 500, "y": 300, "button": "right"}
{"action": "double_click", "x": 500, "y": 300}
{"action": "right_click", "x": 500, "y": 300}
{"action": "drag", "from_x": 100, "from_y": 200, "to_x": 300, "to_y": 400, "duration": 0.5}
{"action": "scroll", "amount": -3}

### Mouse by content (not coords)
{"action": "click_text", "text": "Save"}
{"action": "click_text", "text": "File", "button": "right"}
{"action": "click_control", "name": "OK"} or {"action": "click_control", "automation_id": "btnOK", "control_type": "ButtonControl"}
{"action": "list_controls"} — returns accessible controls in the foreground window. Use when you can't find the right coordinates.

### Keyboard
{"action": "type_text", "text": "Hello World"}
{"action": "press_key", "key": "enter"}
Keys: enter, tab, escape, space, backspace, up, down, left, right, home, end, pageup, pagedown, delete, insert, f1-f12
{"action": "hotkey", "keys": ["ctrl", "c"]}
{"action": "hotkey", "keys": ["alt", "f4"]}

### Text input by control name
{"action": "set_text", "text": "query terms", "name": "Search"}
Use set_text instead of click+type when you know the field name. More reliable than coords.

### Screen reading
{"action": "screenshot"} — take a fresh screenshot
{"action": "read_text"} — OCR the focused window (default). Returns {"scope": "focused"}.
{"action": "read_text", "scope": "all"} — OCR the entire screen
{"action": "read_text", "window": "Notepad"} — OCR a specific window by title
{"action": "read_window", "title": "Calculator"} — OCR a specific window
IMPORTANT: You are a vision model. READ THE SCREENSHOT DIRECTLY. Use read_text only as a supplement when the screenshot is unclear. If OCR returns low_confidence, ignore it and trust your eyes.

### Image matching
{"action": "find_image", "template_path": "C:/path/to/button.png", "confidence": 0.8}

### Waiting (prefer over fixed wait)
{"action": "smart_wait", "timeout": 10} — wait until the screen changes
{"action": "wait_for_stable", "timeout": 10, "stable_time": 1.5} — wait until the screen stops changing (use after opening apps, clicking links, loading pages)
{"action": "wait_for_text", "text": "Loading complete", "timeout": 10}
{"action": "wait_for_image", "template_path": "C:/path/to/icon.png", "timeout": 10}
{"action": "wait", "seconds": 2} — fixed wait, LAST RESORT

### Apps and windows
{"action": "smart_open", "name": "chrome"} — focus if open, else launch. Supports: outlook, chrome, edge, excel, word, teams, slack, notepad, vscode, etc.
{"action": "open_app", "path": "C:/Program Files/App/app.exe", "args": ""}
{"action": "focus_window", "title": "Chrome"}
{"action": "close_window", "title": "Notepad"}
{"action": "list_windows"} — all visible windows with positions

### System
{"action": "system_info"} — OS, CPU, RAM, disk
{"action": "list_processes"}
{"action": "kill_process", "name": "notepad"} or {"action": "kill_process", "pid": 1234}
{"action": "powershell", "command": "Get-Process | Select-Object -First 5"}

### Files
{"action": "read_file", "path": "C:/Users/user/doc.txt"}
{"action": "write_file", "path": "C:/Users/user/doc.txt", "content": "text"}
{"action": "list_directory", "path": "C:/Users/user"}

### Clipboard
{"action": "clipboard_read"}
{"action": "clipboard_write", "text": "copied text"}

### Meta
{"action": "run_script", "path": "scripts/myscript.json"}
{"action": "note", "text": "observation — no side effects"}
{"action": "finish", "summary": "Task completed. Opened Chrome and navigated to example.com."}

## Self-Healing — ALWAYS try alternatives before reporting failure

Wrong click / nothing happened:
  1. Take a screenshot to see current state
  2. Re-identify the target coordinates
  3. Try click_control with the button name
  4. Try keyboard: tab to the control then press enter

OCR garbled / text not found:
  1. IGNORE the OCR output — read the screenshot directly with your vision
  2. Use coordinates from the screenshot to click
  3. Use list_controls() to find the target by accessibility metadata

App didn't open:
  1. wait_for_stable(3) then screenshot
  2. smart_open again
  3. open_app with full path
  4. powershell "Start-Process appname"

Window not found:
  1. list_windows() to see actual titles
  2. Use partial title from the list
  3. hotkey ["alt", "tab"] to cycle

Unexpected popup / dialog:
  1. Read the popup from the screenshot
  2. Handle it (escape, click OK, click X)
  3. wait_for_stable(2) then continue original task

UAC / credential prompt:
  1. note("UAC prompt — requires manual intervention")
  2. finish("Blocked by UAC")

Minimized window:
  1. focus_window with title
  2. If that fails, powershell to restore it
  3. screenshot to verify

NEVER give up silently. Try at least 2 different approaches before finish() with a failure summary.

## Stopping Rules
- Finish IMMEDIATELY when the goal is met. A 3-step success beats a 15-step success.
- If you can see the answer in the current screenshot, finish NOW.
- Extra steps compound errors — stop as soon as the goal is met.

## Safety
- Never type passwords unless explicitly instructed.
- Never delete files or kill processes unless explicitly instructed.
- If unsure about a destructive action, use note() and wait for guidance.
- Report failures honestly with [UNVERIFIED] for uncertain results.

Return ONLY a JSON object. No markdown fences. No commentary.
"""


class AgentEngine:
    """The main agent loop that drives desktop automation via LLM."""

    def __init__(
        self,
        config: dict | None = None,
        approval_callback: Callable[[dict], bool] | None = None,
        pre_action_callback: Callable[[dict], None] | None = None,
    ):
        self.config = config or {}
        self.llm = LLMClient()
        # approval_callback(action_dict) -> bool. When set AND
        # config['approval_mode'] is truthy, every action in
        # APPROVAL_REQUIRED_ACTIONS is shown to the user before execution.
        self.approval_callback = approval_callback
        # pre_action_callback(action_dict) -> None. Invoked just before each
        # action is dispatched. GUI uses it to flash an on-screen overlay.
        self.pre_action_callback = pre_action_callback
        self.executor = ActionExecutor(
            dry_run=bool(self.config.get("dry_run", False)),
            pre_action_callback=pre_action_callback,
            click_offset=get_capture_offset(self.config.get("monitor")),
            monitor=self.config.get("monitor"),
            stealth=bool(self.config.get("stealth_input", False)),
        )

        # Public state (accessed by GUI and API)
        self.running = False
        self.step = 0
        self.max_steps = self.config.get("max_steps", 100)
        self.image_history = int(self.config.get("image_history", DEFAULT_IMAGE_HISTORY))
        self.notes: list[str] = []
        self.forensic_log: list[dict] = []
        self.on_step_callback: Callable | None = None
        self.finish_summary: str = ""

        # ── Core subsystems (always needed) ──────────────────────────
        self.logger = ForensicLog()
        self.checkpoint = CheckpointManager()
        self.gate = ApprovalGate(
            enabled=bool(self.config.get("approval_mode") and not self.config.get("autonomous"))
        )
        if self.approval_callback:
            self.gate.set_callback(self.approval_callback)
        self.mfa_detector = MFADetector()
        self._mfa_paused = False
        self.smart_waiter = SmartWait()

        # Failure tracking and recovery
        self._consecutive_failures = 0
        self._recovery_engine = RecoveryEngine()

        # ── Lazy-loaded subsystems (only created when accessed) ──────
        self._recorder = None
        self._script_engine = None
        self._powershell = None
        self._workflow_engine = None
        self._scheduler = None
        self._notifications = None
        self._plugin_loader = None
        self._auth_manager = None
        self._vault = None
        self._audit_exporter = None
        self._agent_pool = None

    # ── Lazy subsystem accessors ─────────────────────────────────────

    @property
    def recorder(self):
        if self._recorder is None:
            from core.recorder import ActionRecorder

            self._recorder = ActionRecorder()
        return self._recorder

    @property
    def script_engine(self):
        if self._script_engine is None:
            from core.script_engine import ScriptEngine

            self._script_engine = ScriptEngine(self.executor)
        return self._script_engine

    @property
    def powershell(self):
        if self._powershell is None:
            from core.powershell import PowerShellRunner

            self._powershell = PowerShellRunner()
        return self._powershell

    @property
    def workflow_engine(self):
        if self._workflow_engine is None:
            from core.workflow import WorkflowEngine

            self._workflow_engine = WorkflowEngine(self.executor, self.script_engine)
        return self._workflow_engine

    @property
    def scheduler(self):
        if self._scheduler is None:
            from core.scheduler import TaskScheduler

            self._scheduler = TaskScheduler(self)
        return self._scheduler

    @property
    def notifications(self):
        if self._notifications is None:
            from core.notifications import NotificationManager

            notify_config = {
                "enabled_channels": self.config.get("notify_channels", ["toast", "log"]),
                "webhook_url": self.config.get("notify_webhook_url", ""),
                "discord_webhook": self.config.get("notify_discord_webhook", ""),
            }
            self._notifications = NotificationManager(notify_config)
        return self._notifications

    @property
    def plugin_loader(self):
        if self._plugin_loader is None:
            from core.plugin_loader import PluginLoader

            self._plugin_loader = PluginLoader(
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
            )
            try:
                loaded = self._plugin_loader.load_all()
                for p in loaded:
                    logger.info("Plugin loaded: %s v%s", p.get("name"), p.get("version"))
            except Exception as exc:
                logger.warning("Plugin loading failed: %s", exc)
        return self._plugin_loader

    @property
    def auth_manager(self):
        if self._auth_manager is None:
            from core.auth import AuthManager

            self._auth_manager = AuthManager()
        return self._auth_manager

    @property
    def vault(self):
        if self._vault is None:
            from core.encryption import CredentialVault

            self._vault = CredentialVault()
        return self._vault

    @property
    def audit_exporter(self):
        if self._audit_exporter is None:
            from core.audit_export import AuditExporter

            self._audit_exporter = AuditExporter()
        return self._audit_exporter

    @property
    def agent_pool(self):
        if self._agent_pool is None:
            from core.agent_pool import AgentPool

            self._agent_pool = AgentPool(max_agents=self.config.get("max_agents", 3))
        return self._agent_pool

    # ── Sync entry point ────────────────────────────────────────────────

    def run(self, goal: str) -> dict[str, Any]:
        """Execute agent loop synchronously. Blocks until done."""
        self.running = True
        self.step = 0
        self.notes = []
        self.forensic_log = []
        self.finish_summary = ""

        # Auto-start scheduler if configured
        if self.config.get("scheduler_enabled"):
            try:
                self.scheduler.start()
            except Exception as exc:
                logger.warning("Scheduler auto-start failed: %s", exc)

        # Optional: switch to a virtual desktop so agent doesn't interrupt user
        vd = None
        if self.config.get("virtual_desktop"):
            try:
                from core.virtual_desktop import VirtualDesktop

                vd = VirtualDesktop()
                vd.create("SentinelAgent")
                vd.switch_to("SentinelAgent")
                self.notes.append("Running on virtual desktop 'SentinelAgent'")
            except Exception as exc:
                logger.warning("Virtual desktop creation failed: %s", exc)
                self.notes.append(f"Virtual desktop unavailable: {exc}")

        try:
            return self._run_inner(goal)
        finally:
            # Switch back to default desktop when done
            if vd:
                try:
                    vd.switch_to("Default")
                except Exception as exc:
                    logger.debug("Failed to switch back to default desktop: %s", exc)

    def _run_inner(self, goal: str) -> dict[str, Any]:
        """Inner agent loop — called by run() with virtual desktop wrapping."""
        provider = self.config.get("provider", "")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "")

        if not api_key and provider not in ("ollama", "lmstudio", "custom"):
            self.notes = [
                "Error: API key not configured. Open ⚙ Settings, pick a "
                "provider, paste your API key, and choose a model."
            ]
            self.running = False
            return {"steps": 0, "notes": self.notes, "error": "api_key_missing"}
        if not provider:
            self.notes = ["Error: No LLM provider selected. Open ⚙ Settings."]
            self.running = False
            return {"steps": 0, "notes": self.notes, "error": "provider_missing"}
        if not model:
            self.notes = [
                f"Error: No model selected for provider {provider!r}. "
                "Open ⚙ Settings, click 🔍 Detect, or type a model name."
            ]
            self.running = False
            return {"steps": 0, "notes": self.notes, "error": "model_missing"}

        # Build system prompt. We use .replace() — NOT .format() — because
        # the prompt contains literal JSON examples like {"action":"click"}
        # whose braces would otherwise be interpreted as format placeholders
        # (Python's str.format raises KeyError: '"action"' on those).
        env_context = self._build_env_context()
        system_prompt = SYSTEM_PROMPT.replace("{env_context}", env_context)

        # Inject app profile context — detect active window and add profile hints
        app_context = self._build_app_context()
        system_prompt = system_prompt.replace("{app_context}", app_context)
        messages = [{"role": "system", "content": system_prompt}]

        # Initial screenshot + goal
        try:
            screenshot_b64 = capture_to_base64(monitor=self.config.get("monitor"))
        except OSError as exc:
            logger.warning("Initial screen capture failed: %s", exc)
            screenshot_b64 = ""
        self._add_vision_message(
            messages,
            screenshot_b64,
            f"Goal: {goal}\n\nI can see this screen. What should I do first?",
        )

        start_time = time.time()

        # Start structured forensic log
        self.logger.start_run(goal, provider, model)

        # Arm the Esc-x3 failsafe for the duration of this run. Safe no-op
        # if the keyboard package isn't installed or can't hook globally.
        failsafe.arm(self.stop)

        try:
            while self.running and self.step < self.max_steps:
                self.step += 1
                logger.info("Step %d/%d", self.step, self.max_steps)

                # Call LLM. Strip internal `_sentinel_*` markers so they
                # never reach the provider's API.
                use_tools = (
                    self.config.get("use_tools", True) and provider in TOOL_CAPABLE_PROVIDERS
                )
                tools = ACTION_TOOLS if use_tools else None

                # LLM call with exponential backoff retry for network/rate-limit errors.
                response_text = self._call_llm_with_retry(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    tools=tools,
                )
                if response_text is None:
                    # LLM call failed after all retries -- count as a failure
                    self._consecutive_failures += 1
                    logger.warning(
                        "LLM call failed (consecutive_failures=%d)", self._consecutive_failures
                    )
                    if self._consecutive_failures >= 8:
                        self.notes.append(
                            f"Terminating: {self._consecutive_failures} consecutive failures"
                        )
                        self.logger.log_event(
                            "abort",
                            {
                                "reason": "max_consecutive_failures",
                                "count": self._consecutive_failures,
                            },
                        )
                        break
                    if self._consecutive_failures >= 5:
                        # Inject a recovery prompt asking for a different strategy
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[SYSTEM] Multiple consecutive failures have occurred. "
                                    "Please take a completely different approach. "
                                    "Re-evaluate the situation from the current screenshot "
                                    "and try an alternative strategy."
                                ),
                            }
                        )
                    continue

                # Add to conversation
                messages.append({"role": "assistant", "content": response_text})

                # Parse action from response
                action = self._parse_action(response_text)
                if not action:
                    # LLM didn't return valid JSON, try to continue
                    self.notes.append(f"Step {self.step}: No valid action parsed from LLM response")
                    self._consecutive_failures += 1
                    messages.append(
                        {
                            "role": "user",
                            "content": "Please respond with a valid JSON action. Only JSON, no other text.",
                        }
                    )
                    if self._consecutive_failures >= 5:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[SYSTEM] Multiple parse failures. Please return a simple "
                                    'action like {"action": "finish", "summary": "..."} '
                                    'or {"action": "note", "text": "..."}.'
                                ),
                            }
                        )
                    if self._consecutive_failures >= 8:
                        self.notes.append(
                            f"Terminating: {self._consecutive_failures} consecutive failures"
                        )
                        break
                    continue

                # Schema-validate against per-action pydantic models. Modeled
                # actions get defaults filled in and out-of-range numeric fields
                # rejected. Unmodeled actions pass through. We warn-and-continue
                # on errors so the engine keeps making progress — tighten to
                # reject later once telemetry is clean.
                action, _schema_errors = validate_action(action)
                if _schema_errors:
                    err_msg = (
                        f"Step {self.step}: action {action.get('action')!r} failed schema validation: "
                        f"{'; '.join(_schema_errors)}"
                    )
                    logger.warning(err_msg)
                    self.notes.append(err_msg)

                action_name = action.get("action", "")

                # Check for finish
                if action_name == "finish":
                    self.finish_summary = action.get("summary", "Task completed")
                    self.notes.append(self.finish_summary)
                    self._log_step(action, {"ok": True, "msg": self.finish_summary})
                    self.running = False
                    break

                # Approval gate via ApprovalGate subsystem
                if self.gate.enabled and action_name in APPROVAL_REQUIRED_ACTIONS:
                    decision, approved_action = self.gate.evaluate(action, self.step)
                    if decision in (ApprovalDecision.SKIP, ApprovalDecision.ABORT):
                        rejection = {"ok": False, "msg": f"Action {decision.value} by user"}
                        self._log_step(action, rejection)
                        self.logger.log_step(self.step, action_name, str(action), action, rejection)
                        if decision == ApprovalDecision.ABORT:
                            self.running = False
                            break
                        messages.append(
                            {
                                "role": "user",
                                "content": "The user skipped that action. Try a different approach.",
                            }
                        )
                        continue
                    action = approved_action or action

                # MFA/UAC detection — pause if auth prompt is on screen
                mfa_result = self.mfa_detector.check_window_titles()
                if not mfa_result.detected:
                    try:
                        from core.screenshot import capture_screen

                        screen = capture_screen()
                        mfa_result = self.mfa_detector.check_screen(screen)
                    except Exception as exc:
                        logger.debug("MFA screen check failed: %s", exc)
                if mfa_result.detected:
                    self._mfa_paused = True
                    self.logger.log_event(
                        "mfa_pause",
                        {
                            "type": mfa_result.type,
                            "prompt": mfa_result.prompt_text,
                            "window": mfa_result.window_title,
                        },
                    )
                    if self.on_step_callback:
                        try:
                            self.on_step_callback(
                                step=self.step,
                                action={"action": "mfa_pause"},
                                result={
                                    "ok": False,
                                    "msg": f"🔐 {mfa_result.type.upper()} detected: {mfa_result.prompt_text}",
                                },
                            )
                        except Exception as exc:
                            logger.debug("MFA step callback failed: %s", exc)
                    # Wait for auth prompt to disappear (poll every 2s, up to 5 min)
                    for _ in range(150):
                        time.sleep(2)
                        if not self.running:
                            break
                        recheck = self.mfa_detector.check_window_titles()
                        if not recheck.detected:
                            self._mfa_paused = False
                            self.logger.log_event("mfa_resume", {"msg": "Auth prompt dismissed"})
                            break

                # Log the action
                self._log_step(action, {"pending": True})

                # Execute the action -- wrapped in try/except for per-action failure tracking
                action_error = None
                result = None
                try:
                    result = self.executor.execute_sync(action)
                except Exception as exc:
                    logger.exception("Action '%s' threw an exception", action_name)
                    action_error = exc
                    result = {
                        "success": False,
                        "output": f"Action execution error: {exc}",
                        "error": type(exc).__name__,
                    }

                # If action failed, run recovery analysis and handle failure tracking
                action_succeeded = result.get("success", True) and action_error is None
                if not action_succeeded:
                    self._consecutive_failures += 1
                    error_msg = result.get("output", str(action_error))
                    logger.warning(
                        "Action '%s' failed (consecutive_failures=%d): %s",
                        action_name,
                        self._consecutive_failures,
                        error_msg[:200],
                    )

                    # Consult recovery engine
                    suggestion = self._recovery_engine.analyze_failure(
                        action,
                        error_msg,
                        {"step": self.step, "consecutive_failures": self._consecutive_failures},
                    )
                    self.logger.log_event(
                        "recovery_suggestion",
                        {
                            "pattern": suggestion.pattern,
                            "strategy": suggestion.strategy,
                            "confidence": suggestion.confidence,
                            "action": action_name,
                        },
                    )

                    # Add error to message history so the LLM can adapt
                    recovery_msg = f"Action '{action_name}' failed: {error_msg[:300]}."
                    if suggestion.recovery_prompt:
                        recovery_msg += f"\n\nRecovery hint: {suggestion.recovery_prompt}"

                    # Inject recovery prompt into conversation
                    messages.append(
                        {
                            "role": "user",
                            "content": recovery_msg,
                        }
                    )

                    # Check failure thresholds
                    if self._consecutive_failures >= 8:
                        error_summary = (
                            f"Run terminated after {self._consecutive_failures} consecutive failures. "
                            f"Last error: {error_msg[:200]}"
                        )
                        self.notes.append(error_summary)
                        self.logger.log_event(
                            "abort",
                            {
                                "reason": "max_consecutive_failures",
                                "count": self._consecutive_failures,
                                "last_error": error_msg[:200],
                            },
                        )
                        break

                    if self._consecutive_failures >= 5:
                        # Inject a strong recovery prompt
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[SYSTEM RECOVERY] You have had multiple consecutive failures. "
                                    "Please completely change your approach. Consider: "
                                    "1) Taking a fresh screenshot to reassess, "
                                    "2) Using a different action type (e.g., list_controls, read_text), "
                                    "3) Trying keyboard navigation instead of mouse clicks, "
                                    "4) Finishing with a note if the goal is partially achieved."
                                ),
                            }
                        )
                    continue  # skip screenshot below, go to next iteration
                else:
                    # Action succeeded -- reset consecutive failure counter
                    self._consecutive_failures = 0

                # Capture for script recorder if recording
                if self.recorder.is_recording:
                    self.recorder.capture_action(action, result)

                log_result = {
                    "ok": result.get("success", True),
                    "msg": str(result.get("output", ""))[:500],
                }
                self._log_step_result(self.step, log_result)

                # Structured forensic log
                self.logger.log_step(
                    self.step,
                    action_name,
                    str(action.get("x", action.get("name", ""))),
                    action,
                    log_result,
                )

                # Checkpoint every 5 steps
                if self.checkpoint.should_auto_save(self.step):
                    try:
                        self.checkpoint.save(
                            goal=goal,
                            step_num=self.step,
                            agent_memory=self.notes,
                            last_screenshot_path=None,
                            config=self.config,
                            status="running",
                            messages=messages,
                        )
                    except Exception as exc:
                        logger.debug("Checkpoint save failed: %s", exc)

                # Note actions are no-ops at the executor level; record once
                # here so we don't double-log.
                if action_name == "note":
                    self.notes.append(action.get("text", ""))

                # Notify callback
                if self.on_step_callback:
                    try:
                        self.on_step_callback(
                            step=self.step,
                            action=action,
                            result=log_result,
                            screenshot=screenshot_b64,
                        )
                    except Exception as exc:
                        logger.debug("Step callback failed: %s", exc)

                # Take new screenshot for next iteration
                if self.running and self.config.get("auto_screenshot", True):
                    # Prune old screenshots before adding a new one so the
                    # conversation doesn't balloon to dozens of images.
                    self._prune_old_screenshots(messages)
                    screenshot_b64 = capture_to_base64(monitor=self.config.get("monitor"))
                    self._add_vision_message(
                        messages,
                        screenshot_b64,
                        f"Step {self.step} result: {log_result['msg'][:200]}. Current screen:",
                    )

        except Exception as exc:
            logger.exception("Agent run error")
            self.notes.append(f"Fatal error: {exc}")
            self.logger.log_event("error", {"message": str(exc)})
        finally:
            self.running = False
            failsafe.disarm()
            # Finalize structured forensic log
            status = "completed" if self.finish_summary else "error"
            self.logger.end_run(status, self.finish_summary or "Run ended", self.step)

        elapsed = time.time() - start_time
        logger.info("Agent run finished: steps=%d, elapsed=%.1fs", self.step, elapsed)

        # Sound notification
        try:
            from core.sound import play_sound

            play_sound("complete" if self.finish_summary else "error")
        except Exception as exc:
            logger.debug("Sound notification failed: %s", exc)

        return {
            "steps": self.step,
            "notes": self.notes,
            "log": self.forensic_log,
            "finish_summary": self.finish_summary,
            "elapsed_seconds": round(elapsed, 2),
            "report": self._generate_report(goal, elapsed),
        }

    # ------------------------------------------------------------------
    # LLM call with per-step exponential backoff
    # ------------------------------------------------------------------

    _LLM_RETRY_DELAYS = (2.0, 4.0, 8.0)  # seconds between retries

    def _call_llm_with_retry(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> str | None:
        """Call the LLM with per-step retry for network/rate-limit errors.

        Uses a separate retry loop (3 retries with 2s/4s/8s delays) that is
        independent of the LLMClient's own internal retry mechanism. Returns
        the response text, or None if the call failed after all retries.
        """
        for attempt, delay in enumerate((0, *self._LLM_RETRY_DELAYS)):
            if attempt > 0:
                logger.info(
                    "LLM retry attempt %d/%d (delay=%.1fs)",
                    attempt,
                    len(self._LLM_RETRY_DELAYS) + 1,
                    delay,
                )
                time.sleep(delay)
            try:
                return self.llm.chat(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    messages=_clean_messages_for_api(messages),
                    tools=tools,
                    temperature=0.1,
                    custom_url=self.config.get("custom_base_url") or None,
                    max_retries=0,  # disable client-level retry; we handle it here
                    retry_base_delay=0,
                )
            except LLMError as exc:
                # Non-retriable LLM errors (auth, model not found, etc.)
                logger.error("LLM error (non-retriable): %s", exc)
                self.notes.append(f"LLM error at step {self.step}: {exc}")
                return None
            except Exception as exc:
                # Network / transient errors -- retry
                logger.warning(
                    "LLM call attempt %d failed: %s: %s",
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                )
                if attempt >= len(self._LLM_RETRY_DELAYS):
                    # Exhausted all retries
                    logger.error(
                        "LLM call failed after %d retries: %s",
                        len(self._LLM_RETRY_DELAYS) + 1,
                        exc,
                    )
                    self.notes.append(
                        f"LLM error at step {self.step} (after {len(self._LLM_RETRY_DELAYS) + 1} attempts): {exc}"
                    )
                    return None
        return None  # unreachable, but satisfies type checker

    def _generate_report(self, goal: str, elapsed: float) -> dict[str, Any]:
        """Generate a structured run report for MSP work notes.

        Machine-parseable JSON with a human-readable text block for ticketing.
        An MSP tech reading this at 8am should know: what was attempted, what
        succeeded, what failed, and what to do next.
        """
        now = datetime.now()
        success = bool(self.finish_summary)
        errors = [e for e in self.forensic_log if not e.get("result", {}).get("ok", True)]
        provider = self.config.get("provider", "unknown")
        model = self.config.get("model", "unknown")

        action_counts: dict[str, int] = {}
        for entry in self.forensic_log:
            a = entry.get("action", "unknown")
            action_counts[a] = action_counts.get(a, 0) + 1

        step_trace = [
            {
                "step": e.get("step"),
                "action": e.get("action"),
                "params": {
                    k: v for k, v in (e.get("params") or {}).items() if k not in ("screenshot",)
                },
                "ok": e.get("result", {}).get("ok", True),
                "output_preview": str(e.get("result", {}).get("msg", ""))[:200],
                "timestamp": e.get("timestamp"),
            }
            for e in self.forensic_log
        ]

        report = {
            "session_id": now.strftime("%Y%m%d-%H%M%S"),
            "status": "success" if success else "failed",
            "started_at": step_trace[0]["timestamp"] if step_trace else now.isoformat(),
            "finished_at": now.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "goal": goal,
            "provider": provider,
            "model": model,
            "steps_total": self.step,
            "steps_failed": len(errors),
            "actions": action_counts,
            "summary": self.finish_summary or "Run ended without completion",
            "notes": self.notes,
            "step_trace": step_trace,
            "error_list": [
                {
                    "step": e.get("step"),
                    "action": e.get("action"),
                    "params": {
                        k: v for k, v in (e.get("params") or {}).items() if k not in ("screenshot",)
                    },
                    "error": e.get("result", {}).get("msg", "")[:300],
                    "timestamp": e.get("timestamp"),
                }
                for e in errors[:20]
            ],
        }

        # Human-readable text for ticketing
        lines = [
            "SENTINEL DESKTOP — AUTOMATION REPORT",
            f"Session: {report['session_id']}",
            f"Status: {'COMPLETED' if success else 'FAILED'}",
            f"Time: {report['started_at']} → {report['finished_at']} ({elapsed:.1f}s)",
            f"Provider: {provider} / {model}",
            f"Goal: {goal}",
            f"Steps: {self.step} ({len(errors)} failed)",
            f"Summary: {report['summary']}",
        ]
        if self.notes:
            lines.append("Notes:")
            for n in self.notes[:10]:
                lines.append(f"  - {n[:200]}")
        if errors:
            lines.append("Errors:")
            for e in errors[:5]:
                lines.append(
                    f"  Step {e.get('step')}: {e.get('action')} — {e.get('result', {}).get('msg', '')[:150]}"
                )
        report["text"] = "\n".join(lines)
        return report

    def stop(self):
        """Stop the agent loop."""
        self.running = False
        logger.info("Agent stop requested")

    # ── Internal ────────────────────────────────────────────────────────

    def _build_env_context(self) -> str:
        try:
            info = sysinfo.brief_system_info()
        except Exception as exc:
            logger.debug("brief_system_info failed: %s", exc)
            info = ""
        active_win = ""
        try:
            windows = wm.list_windows()
            for w in windows:
                if w.get("is_focused"):
                    active_win = f"\nActive Window: {w['title']}"
                    break
        except Exception as exc:
            logger.debug("Failed to detect active window: %s", exc)
        tenant = ""
        if self.config.get("tenant_name"):
            tenant = f"\nTenant: {self.config['tenant_name']}"
            if self.config.get("tenant_lockdown"):
                tenant += " (LOCKDOWN MODE)"
        return info + active_win + tenant

    def _build_app_context(self) -> str:
        """Build app-profile context for the system prompt."""
        try:
            windows = wm.list_windows()
            focused_title = ""
            for w in windows:
                if w.get("is_focused"):
                    focused_title = w.get("title", "")
                    break
            if not focused_title:
                return ""
            profile = detect_profile(focused_title)
            if not profile:
                return ""
            lines = [
                f"## Active App: {profile.display_name}",
                f"- Stealth compatibility: {profile.stealth_compatible}",
                f"- Preferred input method: {profile.preferred_input}",
            ]
            if profile.quirks:
                lines.append("- Quirks:")
                for q in profile.quirks:
                    lines.append(f"  - {q}")
            if profile.strategies:
                lines.append("- Suggested strategies:")
                for task, strategy in profile.strategies.items():
                    lines.append(f"  - {task}: {strategy}")
            if profile.menu_paths:
                lines.append("- Known menu paths:")
                for action, path in profile.menu_paths.items():
                    lines.append(f"  - {action}: {' → '.join(path)}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Failed to build app profile context: %s", exc)
            return ""

    def _add_vision_message(self, messages: list, screenshot_b64: str, text: str):
        """Add a vision message (screenshot + text) to the conversation.

        capture_to_base64() encodes PNG by default; the media type below must
        stay in sync with the screenshot encoding or Anthropic will reject.
        """
        provider = self.config.get("provider", "")
        if provider == "anthropic":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                    ],
                    # Marker so _prune_old_screenshots can find image messages.
                    "_sentinel_has_image": True,
                    "_sentinel_step": self.step,
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}",
                            },
                        },
                    ],
                    "_sentinel_has_image": True,
                    "_sentinel_step": self.step,
                }
            )

    def _prune_old_screenshots(self, messages: list) -> None:
        """Drop the image bytes from older screenshot messages, but PRESERVE
        any text in those messages (which often includes the original goal!).

        Earlier versions of this method replaced the whole message with a
        text stub — that erased the user's goal from the first message and
        the agent forgot what it was supposed to do. We now extract the text
        block and only discard the image payload.
        """
        keep = max(1, self.image_history)
        image_indices = [i for i, m in enumerate(messages) if m.get("_sentinel_has_image")]
        if len(image_indices) <= keep:
            return
        to_strip = image_indices[: len(image_indices) - keep]
        for idx in to_strip:
            msg = messages[idx]
            step = msg.get("_sentinel_step", "?")

            # Pull any plain-text content out of the vision message's
            # content-block list before we drop the image.
            preserved_text = ""
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        preserved_text = block.get("text", "")
                        break
            elif isinstance(content, str):
                preserved_text = content

            stub = f"[screenshot at step {step} omitted to save tokens]"
            new_content = f"{preserved_text}\n{stub}" if preserved_text else stub
            messages[idx] = {"role": "user", "content": new_content}

    def _parse_action(self, response: str) -> dict | None:
        """Extract an action dict from an LLM response.

        Handles three shapes:
          1. Tool-call envelope ``{"tool_calls":[{"function":{...}}]}`` —
             produced by LLMClient when the model used native function calls.
          2. A plain action dict ``{"action":"click","x":1,"y":2}``.
          3. The above wrapped in a markdown code fence.
        """
        text = response.strip()

        # 1) Native tool-call envelope from LLMClient.
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("tool_calls"):
            return self._action_from_tool_call(parsed["tool_calls"])
        if isinstance(parsed, dict) and "action" in parsed:
            return parsed

        # 2) JSON fenced in a markdown code block.
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                inner = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                inner = None
            if isinstance(inner, dict):
                if inner.get("tool_calls"):
                    return self._action_from_tool_call(inner["tool_calls"])
                if "action" in inner:
                    return inner

        # 3) Best-effort: find a balanced JSON object containing "action".
        obj = _find_balanced_json_with_key(text, "action")
        if obj is not None:
            return obj

        return None

    @staticmethod
    def _action_from_tool_call(tool_calls) -> dict | None:
        """Convert the first tool_call into an action dict for the executor.

        Defensive: tool_calls coming from real providers occasionally arrive
        in unexpected shapes (string, None, list of strings, etc.) — we never
        want any of those to crash the agent loop.
        """
        if not isinstance(tool_calls, list) or not tool_calls:
            return None
        call = tool_calls[0]
        if not isinstance(call, dict):
            return None
        # OpenAI shape: {"function": {"name": ..., "arguments": "<json>"}}
        func = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = func.get("name") or call.get("name")
        raw_args = func.get("arguments")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = call.get("input") if isinstance(call.get("input"), dict) else {}
        if not name:
            return None
        # The model occasionally re-includes "action" in its arguments — drop
        # it so we don't end up with two values for the same key.
        if isinstance(args, dict) and "action" in args:
            args = {k: v for k, v in args.items() if k != "action"}
        return {"action": str(name), **(args if isinstance(args, dict) else {})}

    def _log_step(self, action: dict, result: dict):
        self.forensic_log.append(
            {
                "step": self.step,
                "action": action.get("action"),
                "params": {k: v for k, v in action.items() if k != "action"},
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _log_step_result(self, step: int, result: dict):
        for entry in reversed(self.forensic_log):
            if entry.get("step") == step:
                entry["result"] = result
                break

    def export_log(self) -> str:
        return json.dumps(self.forensic_log, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_balanced_json_with_key(text: str, key: str) -> dict | None:
    """Scan *text* for a balanced ``{...}`` JSON object that contains *key*.

    Handles strings and escape characters so nested braces don't break the
    scanner the way the original regex did.
    """
    needle = f'"{key}"'
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                if needle in candidate:
                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        obj = None
                    if isinstance(obj, dict) and key in obj:
                        return obj
                start = -1
    return None


def _clean_messages_for_api(messages: list) -> list:
    """Return a copy of *messages* with internal ``_sentinel_*`` keys stripped.

    The engine attaches private markers like ``_sentinel_has_image`` so it can
    prune old screenshots; these must not appear in the JSON body sent to a
    provider's API.
    """
    cleaned = []
    for m in messages:
        if not isinstance(m, dict):
            cleaned.append(m)
            continue
        cleaned.append(
            {k: v for k, v in m.items() if not (isinstance(k, str) and k.startswith("_sentinel_"))}
        )
    return cleaned
