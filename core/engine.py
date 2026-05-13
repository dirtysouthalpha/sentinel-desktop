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
You are Sentinel Desktop Agent v2 — an AI assistant that controls a Windows \
desktop to accomplish the user's goal. You can see the screen, move the mouse, \
type, and interact with applications.

## Environment
{env_context}
{app_context}

## Available Actions
Return a single JSON object with an "action" field and relevant parameters:

| Action | Parameters | Description |
|--------|-----------|-------------|
| click | x, y, button? | Click at screen coordinates |
| click_image | template_path, confidence? | Find and click a template image |
| type_text | text | Type text character by character |
| press_key | key | Press a single key (enter, tab, escape, etc.) |
| hotkey | keys (list) | Press key combo, e.g. ["ctrl","c"] |
| scroll | amount | Scroll (positive=up, negative=down) |
| drag | from_x, from_y, to_x, to_y, duration?, button? | Drag from one point to another |
| screenshot | (none) | Take a fresh screenshot |
| find_image | template_path, confidence? | Find image on screen, return position |
| wait_for_image | template_path, timeout? | Wait for image to appear |
| wait | seconds | Wait N seconds |
| smart_wait | timeout?, region? | Wait until the screen changes (faster than fixed wait) |
| wait_for_stable | timeout?, stable_time? | Wait until screen stops changing (page loads) |
| wait_for_text | text, timeout? | Wait until specific text appears on screen |
| smart_open | name | **PREFERRED** — focus the app's window if it's already open, else launch it. Works for outlook, chrome, edge, excel, word, teams, slack, notepad, vscode, etc. |
| open_app | path, args? | Start a raw program by path (use smart_open instead when you can) |
| focus_window | title | Bring window to front by title |
| close_window | title | Close a window by title |
| list_windows | (none) | List all visible windows |
| read_file | path | Read a text file |
| write_file | path, content | Write a text file |
| list_directory | path? | List directory contents |
| clipboard_read | (none) | Read clipboard text |
| clipboard_write | text | Write to clipboard |
| system_info | (none) | Get system details |
| list_processes | (none) | List running processes |
| kill_process | pid or name | Kill a process |
| powershell | command | Run a PowerShell command and return output |
| run_script | path, params? | Replay a recorded script from JSON file |
| note | text | Make a note (no side effects) |
| finish | summary | Signal task completion |

## Safety Rules (MSP)
1. **Sensitive fields**: Never type into password/credential fields without explicit instruction.
2. **Tenant lockdown**: In tenant mode, restrict file access to tenant-scoped paths.
3. **Destructive actions**: Always confirm before killing processes, closing windows, or deleting files.
4. **Honesty**: If you cannot see something clearly, say so. Tag unverified claims as [UNVERIFIED].

## Guidelines
- Look at the screenshot carefully before acting.
- Break complex goals into small, atomic steps.
- After each action, observe the result before proceeding.
- If something goes wrong, note it and try an alternative approach.
- Be efficient — don't take unnecessary screenshots or repeat actions.

## STOPPING — read this carefully
- The moment you have enough information to answer the user's question,
  call ``finish({"summary": "<your answer>"})``. Do NOT keep collecting more
  data after you have what you need.
- If the user asked "what are the last N emails" and ``read_window`` already
  returned the inbox text with N or more visible subjects, STOP and finish
  with what you saw. Don't read the window again. Don't take another
  screenshot. Just summarise.
- A 3-step run that finishes correctly is BETTER than a 15-step run that
  keeps gathering. Errors compound; extra steps usually make things worse.
- If ``read_window`` or ``read_text`` returned garbled OCR but you can still
  identify the answer from the screenshot you saw earlier, finish anyway —
  the user can ask for refinement.

## Reading content from a specific app — IMPORTANT
- After ``smart_open("outlook")`` returns ``"window_title": "Mail - ..."``, use
  ``read_window(title="Outlook")`` (or that exact title) instead of
  ``read_text(scope="focused")``. The latter can read the Sentinel Desktop
  agent window itself or whatever stole focus, while ``read_window`` always
  targets the named app deterministically.
- Same pattern for ``click_text`` inside a specific app — focus the window
  first, then click. If the result mentions OCR'd Chrome/Sentinel UI when you
  expected Outlook, the focus snapped away; use ``focus_window`` then retry.

## When OCR returns garbage — fall back to vision
- If a ``read_text``/``read_window`` result has ``low_confidence: true`` or
  the text looks like jumbled punctuation and stray characters, DO NOT
  retry OCR. The Tesseract output is unreliable for this content.
- Instead, look at the most recent screenshot yourself — you are a vision
  model and can read the rendered pixels directly. Identify the answer
  from what you see in the image.
- Pick coordinates from the screenshot for any clicks (use ``click(x, y)``).
  You don't need OCR to act; the screenshot tells you everything.
- This is normal — UI text with custom fonts, icons, or anti-aliasing often
  defeats OCR. Trust your eyes.

IMPORTANT: Reply with ONLY a JSON object. No markdown, no explanation, just the JSON.
Example: {"action": "click", "x": 500, "y": 300}
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

        # ── Enhanced subsystems ───────────────────────────────────────
        self.logger = ForensicLog()
        self.checkpoint = CheckpointManager()
        self.gate = ApprovalGate(
            enabled=bool(self.config.get("approval_mode") and not self.config.get("autonomous"))
        )
        # Wire approval gate callback to the legacy approval_callback if set
        if self.approval_callback:
            self.gate.set_callback(self.approval_callback)

        # MFA/UAC detection — pauses agent when auth prompts appear
        self.mfa_detector = MFADetector()
        self._mfa_paused = False

        # Smart wait — visual-diff-based waiting instead of fixed timers
        self.smart_waiter = SmartWait()

        # Script recorder — captures actions for replay
        from core.recorder import ActionRecorder

        self.recorder = ActionRecorder()

        # Script engine — replays recorded scripts
        from core.script_engine import ScriptEngine

        self.script_engine = ScriptEngine(self.executor)

        # PowerShell runner — execute PS scripts/commands
        from core.powershell import PowerShellRunner

        self.powershell = PowerShellRunner()

        # Workflow engine — multi-step workflows with conditions/loops
        from core.workflow import WorkflowEngine

        self.workflow_engine = WorkflowEngine(self.executor, self.script_engine)

        # Task scheduler — cron-like scheduling
        from core.scheduler import TaskScheduler

        self.scheduler = TaskScheduler(self)

        # Notification manager — toast/email/webhook
        from core.notifications import NotificationManager

        notify_config = {
            "enabled_channels": self.config.get("notify_channels", ["toast", "log"]),
            "webhook_url": self.config.get("notify_webhook_url", ""),
            "discord_webhook": self.config.get("notify_discord_webhook", ""),
        }
        self.notifications = NotificationManager(notify_config)

        # Plugin loader — drop-in extensibility
        from core.plugin_loader import PluginLoader

        self.plugin_loader = PluginLoader(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
        )

        # Recovery manager — self-healing + popup auto-dismiss
        from core.recovery import RecoveryManager

        self.recovery = RecoveryManager(self.executor, self.config)

        # Load plugins
        try:
            loaded = self.plugin_loader.load_all()
            for p in loaded:
                logger.info("Plugin loaded: %s v%s", p.get("name"), p.get("version"))
        except Exception as exc:
            logger.warning("Plugin loading failed: %s", exc)

        # Start scheduler if configured
        if self.config.get("scheduler_enabled"):
            self.scheduler.start()

        # Auth manager — RBAC + session tokens
        from core.auth import AuthManager

        self.auth_manager = AuthManager()

        # Credential vault — DPAPI encryption for API keys
        from core.encryption import CredentialVault

        self.vault = CredentialVault()

        # Audit exporter — professional reports
        from core.audit_export import AuditExporter

        self.audit_exporter = AuditExporter()

        # Agent pool — multi-agent parallel execution
        from core.agent_pool import AgentPool

        self.agent_pool = AgentPool(max_agents=self.config.get("max_agents", 3))

    # ── Sync entry point ────────────────────────────────────────────────

    def run(self, goal: str) -> dict[str, Any]:
        """Execute agent loop synchronously. Blocks until done."""
        self.running = True
        self.step = 0
        self.notes = []
        self.forensic_log = []
        self.finish_summary = ""

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
                except Exception:
                    pass

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
        screenshot_b64 = capture_to_base64(monitor=self.config.get("monitor"))
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
                try:
                    response_text = self.llm.chat(
                        provider=provider,
                        api_key=api_key,
                        model=model,
                        messages=_clean_messages_for_api(messages),
                        tools=tools,
                        temperature=0.1,
                        custom_url=self.config.get("custom_base_url") or None,
                        max_retries=int(self.config.get("llm_max_retries", 3)),
                        retry_base_delay=float(self.config.get("llm_retry_base_delay", 1.0)),
                    )
                except LLMError as exc:
                    # Already a clean, user-facing message.
                    logger.error("LLM call failed: %s", exc)
                    self.notes.append(f"LLM error at step {self.step}: {exc}")
                    break
                except Exception as exc:
                    logger.error("LLM call failed: %s", exc)
                    self.notes.append(f"LLM error at step {self.step}: {exc}")
                    break

                # Add to conversation
                messages.append({"role": "assistant", "content": response_text})

                # Parse action from response
                action = self._parse_action(response_text)
                if not action:
                    # LLM didn't return valid JSON, try to continue
                    self.notes.append(f"Step {self.step}: No valid action parsed from LLM response")
                    messages.append(
                        {
                            "role": "user",
                            "content": "Please respond with a valid JSON action. Only JSON, no other text.",
                        }
                    )
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
                    except Exception:
                        pass
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
                        except Exception:
                            pass
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

                # Execute the action
                result = self.executor.execute_sync(action)

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
                    except Exception:
                        pass

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
        except Exception:
            pass

        return {
            "steps": self.step,
            "notes": self.notes,
            "log": self.forensic_log,
            "finish_summary": self.finish_summary,
            "elapsed_seconds": round(elapsed, 2),
        }

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
        except Exception:
            pass
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
        except Exception:
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
