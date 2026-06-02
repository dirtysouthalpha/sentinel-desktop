"""Sentinel Desktop v2 — Action executor.

Takes structured action dicts from the LLM and dispatches them to
the appropriate desktop, file, window, or process functions.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from core import clipboard as clip
from core import desktop as desktop_mod
from core import file_ops, launcher, ocr, stealth_input, ui_tree
from core import process_manager as pm
from core import system_info as sysinfo
from core import window_manager as wm
from core.screenshot import capture_to_base64, find_template, wait_for_template

_FailSafeException = desktop_mod._FailSafeException

logger = logging.getLogger(__name__)

# Sensitive field keywords — skip typing into these
SENSITIVE_FIELDS = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "credit_card",
    "ssn",
    "social_security",
    "pin",
]

# Click constants
DOUBLE_CLICK_COUNT = 2

# Preview/sanitization length limits
MAX_PREVIEW_LENGTH = 200
MAX_STRING_VALUE_LENGTH = 200
MAX_COLLECTION_STRING_LENGTH = 500

# Timeout constants
DEFAULT_ACTION_TIMEOUT = 60.0
EXECUTE_WITH_LOGGING_TIMEOUT = 65.0
APPROVAL_CALLBACK_TIMEOUT = 300.0  # 5 minutes for user approval

# Actions that *change state* on the user's machine. In dry-run mode these
# are logged instead of executed. Read-only actions (screenshot, find_image,
# list_*, system_info, read_file, clipboard_read, note) still run for real
# so the agent can observe.
STATE_CHANGING_ACTIONS = {
    "click",
    "click_text",
    "click_image",
    "click_control",
    "type_text",
    "set_text",
    "press_key",
    "hotkey",
    "scroll",
    "drag",
    "open_app",
    "smart_open",
    "start_process",
    "close_app",
    "kill_process",
    "focus_window",
    "close_window",
    "write_file",
    "clipboard_write",
}


class ActionExecutor:
    """Execute desktop actions returned by the LLM."""

    def __init__(
        self,
        approval_callback: Callable | None = None,
        dry_run: bool = False,
        pre_action_callback: Callable[[dict[str, Any]], None] | None = None,
        click_offset: tuple = (0, 0),
        monitor: int | None = None,
        stealth: bool = False,
    ) -> None:
        """Initialize the action executor.

        Args:
            approval_callback: Async callable(action_dict) → bool.
                If provided, actions are sent for approval before execution.
            dry_run: When True, state-changing actions are logged but not
                executed. Useful for safely testing prompts.
            pre_action_callback: Optional sync callable(action_dict) invoked
                immediately before each action is dispatched. Used by the GUI
                to flash an on-screen overlay over the target location.
            click_offset: (x, y) screen-coord offset of the captured image's
                origin. Required for multi-monitor mode where the virtual
                desktop top-left may have negative coords. Defaults to (0, 0).
            monitor: Monitor index for multi-monitor setups. When None,
                uses the primary monitor.
            stealth: If True, uses stealth input methods (PostMessage/UIA)
                instead of physical mouse/keyboard movements. Falls back to
                physical input on stealth mode failures.

        """
        self.approval_callback = approval_callback
        self.dry_run = dry_run
        self.pre_action_callback = pre_action_callback
        self.click_offset = click_offset
        self.monitor = monitor
        # stealth: don't move the cursor / keyboard if False routes via win32
        # PostMessage / UIA Invoke. Falls back to physical input on failure.
        self.stealth = bool(stealth)
        self._desktop = desktop_mod.DesktopEngine()
        self._log: list[dict[str, Any]] = []

    @property
    def log(self) -> list[dict[str, Any]]:
        """Return a shallow copy of the action execution log.

        Returns:
            List of dicts, one per executed action, containing action name,
            result, and timing information.

        """
        return list(self._log)

    async def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute a single action.

        .. deprecated:: 3.1.0
            The async ``execute()`` method is not used by the engine loop,
            which calls ``execute_sync()`` instead. Kept for backward
            compatibility. Prefer ``execute_sync()`` for new code.

        Args:
            action: Dict with at least 'action' key and relevant params.

        Returns:
            Result dict: {success, output, error}

        """
        try:
            return await asyncio.wait_for(
                self._execute_with_logging(action),
                timeout=EXECUTE_WITH_LOGGING_TIMEOUT,
            )
        except asyncio.TimeoutError:
            action_type = action.get("action", "").lower()
            params = {k: v for k, v in action.items() if k != "action"}
            error_msg = f"Action '{action_type}' timed out"
            result = {"success": False, "output": error_msg, "error": "timeout"}
            self._log_entry(action_type, params, result)
            return result

    async def _execute_with_logging(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute action with approval checks and logging."""
        action_type = action.get("action", "").lower()
        params = {k: v for k, v in action.items() if k != "action"}

        if self.approval_callback:
            try:
                approved = await asyncio.wait_for(
                    self.approval_callback(action),
                    timeout=APPROVAL_CALLBACK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                error_msg = "Action approval timed out"
                result = {"success": False, "output": error_msg, "error": "timeout"}
                self._log_entry(action_type, params, result)
                return result
            if not approved:
                error_msg = "Action rejected by user"
                result = {"success": False, "output": error_msg, "error": "rejected"}
                self._log_entry(action_type, params, result)
                return result

        self._fire_pre_action_hook(action)

        if self.dry_run and action_type in STATE_CHANGING_ACTIONS:
            result = _dry_run_result(action_type, params)
            self._log_entry(action_type, params, result)
            return result

        result = await self._dispatch_action_async(action_type, params)
        self._log_entry(action_type, params, result)
        return result

    def _fire_pre_action_hook(self, action: dict[str, Any]) -> None:
        """Invoke pre_action_callback if set, swallowing any exceptions."""
        if self.pre_action_callback is not None:
            try:
                self.pre_action_callback(action)
            except Exception as exc:
                logger.debug("pre_action_callback failed: %s", exc)

    async def _dispatch_action_async(
        self, action_type: str, params: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch *action_type* to its handler with a 60-second timeout."""
        handler = self._dispatch_table.get(action_type)
        if not handler:
            error_msg = f"Unknown action: {action_type}"
            return {"success": False, "output": error_msg, "error": "unknown_action"}
        try:
            if asyncio.iscoroutinefunction(handler):
                return await asyncio.wait_for(
                    handler(self, **params),
                    timeout=DEFAULT_ACTION_TIMEOUT,
                )
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, lambda: handler(self, **params)),
                timeout=DEFAULT_ACTION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timeout_msg = f"Action '{action_type}' timed out"
            return {"success": False, "output": timeout_msg, "error": "timeout"}
        except Exception as exc:
            logger.exception("Action '%s' failed", action_type)
            return {"success": False, "output": str(exc), "error": type(exc).__name__}

    def execute_sync(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute action directly without event loop (synchronous wrapper)."""
        action_type = action.get("action", "").lower()
        params = {k: v for k, v in action.items() if k != "action"}

        self._fire_pre_action_hook(action)

        # Dry-run short-circuit
        if self.dry_run and action_type in STATE_CHANGING_ACTIONS:
            result = _dry_run_result(action_type, params)
            self._log_entry(action_type, params, result)
            return result

        handler = self._dispatch_table.get(action_type)
        if handler:
            try:
                result = handler(self, **params)
            except Exception as exc:
                logger.exception("Action '%s' failed", action_type)
                result = {"success": False, "output": str(exc), "error": type(exc).__name__}
        else:
            result = {
                "success": False,
                "output": f"Unknown action: {action_type}",
                "error": "unknown_action",
            }

        self._log_entry(action_type, params, result)
        return result

    def _log_entry(self, action_type: str, params: dict, result: dict) -> None:
        """Append an action log entry with sanitized params and truncated output preview."""
        entry = {
            "action": action_type,
            "params": _sanitize_params(params),
            "success": result.get("success", False),
            "output_preview": str(result.get("output", ""))[:200],
        }
        self._log.append(entry)
        logger.info("Action: %-20s → %s", action_type, "OK" if result.get("success") else "FAIL")

    # -------------------------------------------------------------------
    # Action handlers (sync — wrapped by execute())
    # -------------------------------------------------------------------
    def _click(
        self, *, x: int, y: int, button: str = "left", clicks: int = 1, **_,
    ) -> dict[str, Any]:
        """Click at screen coordinates with optional stealth mode via PostMessage."""
        # Translate from captured-image coords to absolute screen coords for
        # multi-monitor virtual-desktop capture.
        sx = int(x) + self.click_offset[0]
        sy = int(y) + self.click_offset[1]
        try:
            # In stealth mode, try the no-cursor-move path first.
            if (
                self.stealth
                and stealth_input.is_available()
                and stealth_input.post_click(sx, sy, button=button)
            ):
                if clicks == DOUBLE_CLICK_COUNT:
                    desc = "Double-clicked"
                elif button == "right":
                    desc = "Right-clicked"
                else:
                    desc = "Clicked"
                return {"success": True, "output": f"{desc} ({sx}, {sy}) — stealth"}
            # PostMessage failed; fall through to physical click.
            self._desktop.click(sx, sy, button=button, clicks=clicks)
            desc = (
                "Double-clicked"
                if clicks == DOUBLE_CLICK_COUNT
                else "Right-clicked"
                if button == "right"
                else "Clicked"
            )
            return {"success": True, "output": f"{desc} ({sx}, {sy})"}
        except (OSError, RuntimeError, _FailSafeException) as exc:
            return {
                "success": False,
                "output": f"click error at ({sx},{sy}): {exc}",
                "error": "click_failed",
            }

    def _try_ocr_click(self, *, text: str, button: str, fuzzy: bool) -> dict | None:
        """Attempt OCR-based click on text.

        Returns None if OCR fails to find the text.
        """
        pos = ocr.find_text(text, fuzzy=fuzzy)
        if pos is None:
            return None

        x, y = pos
        sx = x + self.click_offset[0]
        sy = y + self.click_offset[1]

        if (
            self.stealth
            and stealth_input.is_available()
            and stealth_input.post_click(sx, sy, button=button)
        ):
            return {
                "success": True,
                "output": f"Clicked text {text!r} at ({sx}, {sy}) — stealth",
                "position": [sx, sy],
            }

        self._desktop.click(sx, sy, button=button)
        return {
            "success": True,
            "output": f"Clicked text {text!r} at ({sx}, {sy})",
            "position": [sx, sy],
        }

    def _try_uia_click(self, *, text: str, button: str) -> dict | None:
        """Attempt UIAutomation click by name as fallback.

        Returns None if UIA fails to find the control.
        """
        try:
            ui_pos = ui_tree.click_control(name=text, button=button)
            if ui_pos is not None:
                return {
                    "success": True,
                    "output": f"Clicked text {text!r} via UIAutomation at {ui_pos}",
                    "position": list(ui_pos),
                    "fallback": "uia",
                }
        except (OSError, AttributeError, RuntimeError, TypeError) as exc:
            logger.debug("click_text UIA fallback failed: %s", exc)
        return None

    def _click_text_not_found_response(self, *, text: str) -> dict:
        """Return error response when text is not found."""
        return {
            "success": False,
            "output": f"Text {text!r} not found via OCR or UIAutomation",
            "error": "text_not_found",
            "hint": (
                "Try list_controls() to find the element, or use "
                "click(x,y) with coordinates from the screenshot"
            ),
        }

    def _click_text(self, *, text: str, button: str = "left", fuzzy: bool = True, **_) -> dict:
        """OCR-backed click: locate visible text and click its centre.

        Self-healing: if OCR fails, tries UIAutomation click by name.
        """
        try:
            # Try OCR-based click
            ocr_result = self._try_ocr_click(text=text, button=button, fuzzy=fuzzy)
            if ocr_result is not None:
                return ocr_result

            # Try UIAutomation fallback
            uia_result = self._try_uia_click(text=text, button=button)
            if uia_result is not None:
                return uia_result

            return self._click_text_not_found_response(text=text)
        except (OSError, RuntimeError, ValueError, _FailSafeException) as exc:
            return {
                "success": False,
                "output": f"click_text error: {exc}",
                "error": "click_text_failed",
            }

    def _read_text(self, *, scope: str = "focused", window: str | None = None, **_) -> dict:
        """OCR text from the screen.

        Args:
            scope: ``"focused"`` (default) reads only the foreground window —
                far more useful than full-screen OCR on multi-monitor setups
                where the screen contains many apps. ``"all"`` reads the
                entire screen / virtual desktop.
            window: When provided, OCR a specific window by partial title
                match (overrides ``scope``).

        """
        try:
            if window:
                text = ocr.read_window_text(window)
                origin = f"window {window!r}"
            elif scope == "all":
                text = ocr.read_screen_text()
                origin = "full screen"
            else:
                text, title = ocr.read_focused_window_text_with_title()
                origin = f"focused window: {title!r}" if title else "focused window"
            if not text:
                return {
                    "success": False,
                    "output": f"No text found in {origin} (or Tesseract OCR unavailable)",
                    "error": "ocr_unavailable",
                }
            result = {
                "success": True,
                "output": text[:8000],
                "length": len(text),
                "source": origin,
            }
            # Flag suspect output so the LLM knows to trust the screenshot over
            # this garbled text. The prompt teaches it how to react.
            if ocr.looks_low_confidence(text):
                result["low_confidence"] = True
                result["hint"] = (
                    "OCR output looks garbled. Trust the screenshot vision "
                    "instead — read content directly from the image and act on "
                    "coordinates rather than OCR text."
                )
            return result
        except Exception as exc:
            return {
                "success": False,
                "output": f"read_text error: {exc}",
                "error": "read_text_failed",
            }

    def _read_window(self, *, title: str, **_) -> dict:
        """OCR a specific window by partial title match — convenience for the LLM."""
        try:
            text = ocr.read_window_text(title)
            if not text:
                return {
                    "success": False,
                    "output": f"Window {title!r} not found or contained no text",
                    "error": "window_not_found",
                }
            result = {"success": True, "output": text[:8000], "length": len(text), "window": title}
            if ocr.looks_low_confidence(text):
                result["low_confidence"] = True
                result["hint"] = (
                    "OCR output looks garbled. Read content from the screenshot "
                    "directly and act on coordinates instead of relying on this text."
                )
            return result
        except Exception as exc:
            return {
                "success": False,
                "output": f"read_window error: {exc}",
                "error": "read_window_failed",
            }

    # ---- UIAutomation handlers ---------------------------------------

    def _click_control(
        self,
        *,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        window_title: str | None = None,
        button: str = "left",
        **_,
    ) -> dict:
        """Click a native Windows control by its accessibility name/id/type.

        Self-healing: if UIAutomation fails, tries OCR text click.
        """
        try:
            pos = ui_tree.click_control(
                name=name,
                automation_id=automation_id,
                control_type=control_type,
                window_title=window_title,
                button=button,
            )
            if pos is not None:
                return {
                    "success": True,
                    "output": f"Clicked control at {pos}",
                    "position": list(pos),
                }
            return self._click_control_ocr_fallback(name, automation_id, control_type, button)
        except Exception as exc:
            return {
                "success": False,
                "output": f"click_control error: {exc}",
                "error": "click_control_failed",
            }

    def _click_control_ocr_fallback(
        self,
        name: str | None,
        automation_id: str | None,
        control_type: str | None,
        button: str,
    ) -> dict:
        """Fallback: try OCR text click when UIA found no matching control."""
        if name:
            try:
                ocr_pos = ocr.find_text(name, fuzzy=True)
                if ocr_pos:
                    sx = ocr_pos[0] + self.click_offset[0]
                    sy = ocr_pos[1] + self.click_offset[1]
                    self._desktop.click(sx, sy, button=button)
                    return {
                        "success": True,
                        "output": f"Clicked control {name!r} via OCR at ({sx},{sy})",
                        "position": [sx, sy],
                        "fallback": "ocr",
                    }
            except Exception as exc:
                logger.debug("click_control OCR fallback failed: %s", exc)
        return {
            "success": False,
            "output": (
                f"No control matched (name={name!r}, automation_id={automation_id!r}, "
                f"control_type={control_type!r})"
            ),
            "error": "control_not_found",
            "hint": (
                "Try list_controls() to see available controls, "
                "or click(x,y) with screenshot coordinates"
            ),
        }

    def _list_controls(
        self, *, window_title: str | None = None, max_results: int = 60, **_,
    ) -> dict:
        """List accessible controls in a window for the LLM to choose from."""
        try:
            controls = ui_tree.list_controls(window_title=window_title, max_results=max_results)
            if not controls:
                return {
                    "success": False,
                    "output": "UIAutomation unavailable or window has no controls",
                    "error": "uia_unavailable",
                }
            # Trim to what's useful for the LLM (drop offscreen controls, big text).
            slim = [
                {
                    "name": c["name"][:120],
                    "control_type": c["control_type"],
                    "automation_id": c["automation_id"],
                    "x": c["x"],
                    "y": c["y"],
                    "width": c["width"],
                    "height": c["height"],
                }
                for c in controls
                if not c.get("is_offscreen") and c.get("is_enabled", True)
            ]
            return {"success": True, "output": slim, "count": len(slim)}
        except (OSError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
            return {
                "success": False,
                "output": f"list_controls error: {exc}",
                "error": "list_controls_failed",
            }

    def _set_text(
        self,
        *,
        text: str,
        name: str | None = None,
        automation_id: str | None = None,
        window_title: str | None = None,
        **_,
    ) -> dict:
        """Set the value of a named edit/textbox control deterministically.

        Self-healing: if UIAutomation set_text fails, tries click+Ctrl+A+type.
        """
        if _contains_sensitive(text):
            return {
                "success": False,
                "output": "Blocked: text appears sensitive",
                "error": "sensitive_field",
            }
        try:
            ok = ui_tree.set_text(
                text,
                name=name,
                automation_id=automation_id,
                window_title=window_title,
            )
            if ok:
                return {"success": True, "output": f"Set text on {name or automation_id!r}"}
            return self._set_text_click_fallback(window_title, name, automation_id, text)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            return {
                "success": False,
                "output": f"set_text error: {exc}",
                "error": "set_text_failed",
            }

    def _set_text_click_fallback(
        self,
        window_title: str | None,
        name: str | None,
        automation_id: str | None,
        text: str,
    ) -> dict:
        """Fallback: find edit control via UIA, click it, select-all, then type."""
        try:
            controls = ui_tree.list_controls(window_title=window_title, max_results=30)
            target = None
            for c in controls:
                cname = (c.get("name") or "").lower()
                cid = (c.get("automation_id") or "").lower()
                if name and name.lower() in cname:
                    target = c
                    break
                if automation_id and automation_id.lower() in cid:
                    target = c
                    break
                if c.get("control_type") == "Edit" and not name and not automation_id:
                    target = c
                    break
            if target and not target.get("is_offscreen"):
                import time as _t
                cx = target["x"] + target["width"] // 2
                cy = target["y"] + target["height"] // 2
                sx = cx + self.click_offset[0]
                sy = cy + self.click_offset[1]
                self._desktop.click(sx, sy)
                _t.sleep(0.15)
                self._desktop.hotkey("ctrl", "a")
                _t.sleep(0.1)
                self._desktop.type_text(text)
                return {
                    "success": True,
                    "output": f"Set text via click+type on control at ({sx},{sy})",
                    "fallback": "click_and_type",
                }
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            logger.debug("set_text click+type fallback failed: %s", exc)
        return {
            "success": False,
            "output": f"No editable control matched (name={name!r})",
            "error": "control_not_found",
            "hint": "Try click_text() on the field label, then type_text()",
        }

    def _click_image(self, *, template_path: str, confidence: float = 0.8, **_) -> dict:
        """Find a template image on screen and click it, using stealth if available."""
        # Find the template position; click via stealth if enabled so the
        # cursor stays put.
        try:
            if self.stealth and stealth_input.is_available():
                pos = find_template(template_path, confidence)
                if pos:
                    sx = pos[0] + self.click_offset[0]
                    sy = pos[1] + self.click_offset[1]
                    if stealth_input.post_click(sx, sy):
                        return {
                            "success": True,
                            "output": f"Clicked template at ({sx},{sy}) — stealth",
                        }
            found = self._desktop.click_image(template_path, confidence)
            return {
                "success": found,
                "output": f"Template {'found and clicked' if found else 'not found'}",
            }
        except (OSError, RuntimeError, ValueError) as exc:
            return {
                "success": False,
                "output": f"click_image error: {exc}",
                "error": "click_image_failed",
            }

    def _type_text(self, *, text: str, **_) -> dict:
        """Type text via keyboard input, falling back to clipboard paste if needed."""
        # Sensitive field check
        if _contains_sensitive(text):
            return {
                "success": False,
                "output": "Blocked: text appears to contain sensitive data",
                "error": "sensitive_field",
            }
        if self.stealth and stealth_input.is_available() and stealth_input.post_text(text):
            return {"success": True, "output": f"Typed {len(text)} chars — stealth"}
        try:
            self._desktop.type_text(text)
            return {"success": True, "output": f"Typed {len(text)} characters"}
        except Exception as exc:
            logger.debug("pyautogui type_text failed, trying clipboard: %s", exc)
            try:
                import pyperclip

                pyperclip.copy(text)
                self._desktop.hotkey("ctrl", "v")
                return {
                    "success": True,
                    "output": f"Typed {len(text)} chars via clipboard",
                    "fallback": "clipboard",
                }
            except Exception as exc2:
                return {"success": False, "output": f"Type failed: {exc2}", "error": "type_failed"}

    def _press_key(self, *, key: str, **_) -> dict:
        """Press a single named key (e.g. 'enter', 'tab', 'escape')."""
        try:
            if self.stealth and stealth_input.is_available() and stealth_input.post_named_key(key):
                return {"success": True, "output": f"Pressed {key} — stealth"}
            self._desktop.press_key(key)
            return {"success": True, "output": f"Pressed {key}"}
        except Exception as exc:
            logger.debug("press_key failed for %r: %s", key, exc)
            return {
                "success": False,
                "output": f"Press key failed: {exc}",
                "error": "press_key_failed",
            }

    def _hotkey(self, *, keys: list, **_) -> dict:
        """Press a keyboard shortcut combination (e.g. ['ctrl', 'c'])."""
        try:
            if self.stealth and stealth_input.is_available() and stealth_input.post_hotkey(keys):
                return {"success": True, "output": f"Hotkey: {'+'.join(keys)} — stealth"}
            self._desktop.hotkey(*keys)
            return {"success": True, "output": f"Hotkey: {'+'.join(keys)}"}
        except Exception as exc:
            logger.debug("hotkey failed for %s: %s", keys, exc)
            return {"success": False, "output": f"Hotkey failed: {exc}", "error": "hotkey_failed"}

    def _drag(
        self,
        *,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration: float = 0.5,
        button: str = "left",
        **_,
    ) -> dict:
        """Drag from one screen position to another with stealth PostMessage support."""
        sx = int(from_x) + self.click_offset[0]
        sy = int(from_y) + self.click_offset[1]
        tx = int(to_x) + self.click_offset[0]
        ty = int(to_y) + self.click_offset[1]
        if self.stealth and stealth_input.is_available():
            result = self._stealth_drag_win32(sx, sy, tx, ty, duration, button)
            if result is not None:
                return result
        try:
            self._desktop.drag(sx, sy, tx, ty, duration=duration, button=button)
            return {"success": True, "output": f"Dragged ({from_x},{from_y})→({to_x},{to_y})"}
        except Exception as exc:
            return {"success": False, "output": f"Drag failed: {exc}", "error": "drag_failed"}

    def _stealth_drag_win32(
        self,
        sx: int,
        sy: int,
        tx: int,
        ty: int,
        duration: float,
        button: str,
    ) -> dict | None:
        """Attempt a stealth drag via Win32 PostMessage; returns result dict or None on failure."""
        try:
            import time as _t

            import win32api
            import win32con
            import win32gui

            hwnd = win32gui.WindowFromPoint((sx, sy))
            cx, cy = win32gui.ScreenToClient(hwnd, (sx, sy))
            cx2, cy2 = win32gui.ScreenToClient(hwnd, (tx, ty))
            lparam_down = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
            lparam_up = ((cy2 & 0xFFFF) << 16) | (cx2 & 0xFFFF)
            mk = win32con.MK_LBUTTON if button == "left" else win32con.MK_RBUTTON
            win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, mk, lparam_down)
            steps = max(1, int(duration / 0.01))
            for i in range(1, steps + 1):
                mx = int(cx + (cx2 - cx) * i / steps)
                my = int(cy + (cy2 - cy) * i / steps)
                lparam_move = ((my & 0xFFFF) << 16) | (mx & 0xFFFF)
                win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, mk, lparam_move)
                _t.sleep(duration / steps)
            win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam_up)
            return {"success": True, "output": f"Dragged ({sx},{sy})→({tx},{ty}) — stealth"}
        except Exception as exc:
            logger.debug("Stealth drag failed, falling back: %s", exc)
            return None

    def _scroll(self, *, amount: int, **_) -> dict:
        """Scroll the mouse wheel by the given amount (positive = up, negative = down)."""
        try:
            self._desktop.scroll(amount)
            return {"success": True, "output": f"Scrolled {amount}"}
        except Exception as exc:
            return {"success": False, "output": f"Scroll failed: {exc}", "error": "scroll_failed"}

    def _screenshot(self, **_) -> dict:
        """Capture a screenshot and return it as a base64-encoded string."""
        try:
            b64 = capture_to_base64(monitor=self.monitor)
            return {
                "success": True,
                "output": f"Screenshot captured ({len(b64)} chars base64)",
                "screenshot": b64,
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"Screenshot failed: {exc}",
                "error": "capture_failed",
            }

    def _find_image(self, *, template_path: str, confidence: float = 0.8, **_) -> dict:
        """Locate a template image on screen and return its position."""
        try:
            pos = find_template(template_path, confidence)
            if pos:
                return {
                    "success": True,
                    "output": f"Found at ({pos[0]}, {pos[1]})",
                    "position": list(pos),
                }
            return {
                "success": False,
                "output": "Image not found on screen",
                "error": "image_not_found",
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"find_image error: {exc}",
                "error": "find_image_failed",
            }

    def _wait(self, *, seconds: float = 1.0, **_) -> dict:
        """Sleep for the given duration, capped at 60s to prevent runaway waits."""
        import time as _time

        seconds = max(0.0, float(seconds))
        # Cap the wait so a runaway LLM can't lock the agent for hours.
        seconds = min(seconds, 60.0)
        try:
            _time.sleep(seconds)
            return {"success": True, "output": f"Waited {seconds}s"}
        except Exception as exc:
            return {"success": False, "output": f"Wait failed: {exc}", "error": "wait_failed"}

    def _wait_for_image(self, *, template_path: str, timeout: int = 30, **_) -> dict:
        """Poll until a template image appears on screen or timeout elapses."""
        try:
            pos = wait_for_template(template_path, float(timeout))
            if pos:
                return {
                    "success": True,
                    "output": f"Image appeared at ({pos[0]}, {pos[1]})",
                    "position": list(pos),
                }
            return {"success": False, "output": f"Timed out after {timeout}s", "error": "timeout"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"wait_for_image error: {exc}",
                "error": "wait_for_image_failed",
            }

    def _smart_wait(self, *, timeout: float = 10, region: list | None = None, **_) -> dict:
        """Wait until the screen changes (visual diff)."""
        try:
            from core.smart_wait import SmartWait

            sw = SmartWait()
            region_tuple = tuple(region) if region else None
            result = sw.wait_for_change(timeout=float(timeout), region=region_tuple)
            return {
                "success": result.success,
                "output": (
                    f"Screen changed after {result.elapsed:.1f}s ({result.frames_checked} frames)"
                    if result.success
                    else "Screen did not change within timeout"
                ),
                "elapsed": result.elapsed,
                "frames_checked": result.frames_checked,
            }
        except Exception as exc:
            import time as _t

            _t.sleep(min(float(timeout), 5.0))
            return {
                "success": False,
                "output": f"Smart wait fallback: {exc}",
                "error": "smart_wait_failed",
            }

    def _wait_for_stable(
        self, *, timeout: float = 10, stable_time: float = 1.5, region: list | None = None, **_,
    ) -> dict:
        """Wait until the screen stops changing."""
        try:
            from core.smart_wait import SmartWait

            sw = SmartWait()
            region_tuple = tuple(region) if region else None
            result = sw.wait_for_stable(
                timeout=float(timeout), stable_time=float(stable_time), region=region_tuple,
            )
            return {
                "success": result.success,
                "output": f"Screen stable after {result.elapsed:.1f}s"
                if result.success
                else f"Still changing after {result.elapsed:.1f}s",
                "elapsed": result.elapsed,
            }
        except Exception as exc:
            import time as _t

            _t.sleep(3.0)
            return {
                "success": False,
                "output": f"Wait-for-stable fallback: {exc}",
                "error": "wait_for_stable_failed",
            }

    def _wait_for_text(
        self, *, text: str, timeout: float = 10, region: list | None = None, **_,
    ) -> dict:
        """Wait until specific text appears on screen via OCR."""
        try:
            from core.smart_wait import SmartWait

            sw = SmartWait()
            region_tuple = tuple(region) if region else None
            result = sw.wait_for_text(text, timeout=float(timeout), region=region_tuple)
            return {
                "success": result.success,
                "output": f"Text '{text}' found after {result.elapsed:.1f}s"
                if result.success
                else f"Text '{text}' not found after {result.elapsed:.1f}s",
                "elapsed": result.elapsed,
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"Wait-for-text fallback: {exc}",
                "error": "wait_for_text_failed",
            }

    def _open_app(self, *, path: str, args: list | None = None, **_) -> dict:
        """Launch an application by executable path with optional arguments."""
        try:
            pid = pm.start_process(path, args)
            if pid:
                return {"success": True, "output": f"Started process (pid {pid})"}
            return {"success": False, "output": "Failed to start process"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"open_app error: {exc}",
                "error": "open_app_failed",
            }

    def _smart_open(self, *, name: str, **_) -> dict:
        """Focus an existing window if the app is already running, else launch.

        Self-healing: if normal launch fails, tries PowerShell Start-Process.
        """
        result = launcher.smart_open(name)
        if result.get("success"):
            return result

        # Fallback: PowerShell Start-Process
        import subprocess

        try:
            subprocess.Popen(
                ["powershell", "-Command", f"Start-Process '{name}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "output": f"Launched {name!r} via PowerShell Start-Process",
                "fallback": "powershell",
            }
        except Exception as exc:
            logger.debug("smart_open PowerShell fallback failed: %s", exc)

        result["hint"] = "Try open_app() with the full executable path"
        return result

    def _close_app(self, *, name: str | None = None, pid: int | None = None, **_) -> dict:
        """Kill a running process by name or PID."""
        target = pid or name
        if target is None:
            return {
                "success": False,
                "output": "Provide 'name' or 'pid'",
                "error": "missing_target",
            }
        try:
            killed = pm.kill_process(target)
            return {
                "success": killed,
                "output": f"Process {target} {'killed' if killed else 'not found'}",
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"close_app error: {exc}",
                "error": "close_app_failed",
            }

    def _focus_window(self, *, title: str, **_) -> dict:
        """Focus a window by partial title match.

        Self-healing: if exact focus fails, scans visible windows for
        the best partial match and tries harder (Alt-Tab style).
        """
        try:
            ok = wm.focus_window(title)
            if ok:
                return {"success": True, "output": f"Window '{title}' focused"}

            # Fallback: search all windows and try closest match
            windows = wm.list_windows()
            candidates = []
            needle = title.lower()
            for w in windows:
                wtitle = (w.get("title") or "").lower()
                if needle in wtitle or wtitle in needle:
                    candidates.append(w)
            if candidates:
                # Try focusing the best candidate directly
                best = candidates[0]
                if wm.focus_window(best["title"]):
                    return {
                        "success": True,
                        "output": f"Focused window '{best['title']}' (partial match for '{title}')",
                        "matched_title": best["title"],
                    }

            return {
                "success": False,
                "output": f"Window '{title}' not found",
                "error": "window_not_found",
                "hint": "Try list_windows() to see what's actually open",
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"focus_window error: {exc}",
                "error": "focus_window_failed",
            }

    def _close_window(self, *, title: str, **_) -> dict:
        """Close a window by partial title match."""
        try:
            ok = wm.close_window(title)
            return {"success": ok, "output": f"Window '{title}' {'closed' if ok else 'not found'}"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"close_window error: {exc}",
                "error": "close_window_failed",
            }

    def _list_windows(self, **_) -> dict:
        """List all visible windows with titles and positions."""
        try:
            windows = wm.list_windows()
            return {"success": True, "output": windows}
        except Exception as exc:
            return {
                "success": False,
                "output": f"list_windows error: {exc}",
                "error": "list_windows_failed",
            }

    def _read_file(self, *, path: str, **_) -> dict:
        """Read a file's contents and return up to 5000 chars as a preview."""
        try:
            content = file_ops.read_file(path)
            if content is not None:
                preview = content[:5000]
                return {"success": True, "output": preview, "length": len(content)}
            return {
                "success": False,
                "output": "File not found or unreadable",
                "error": "file_not_found",
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"read_file error: {exc}",
                "error": "read_file_failed",
            }

    def _write_file(self, *, path: str, content: str, **_) -> dict:
        """Write content to a file on disk."""
        try:
            ok = file_ops.write_file(path, content)
            return {"success": ok, "output": f"File {'written' if ok else 'write failed'}"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"write_file error: {exc}",
                "error": "write_file_failed",
            }

    def _list_directory(self, *, path: str = ".", **_) -> dict:
        """List files and subdirectories in the given directory path."""
        try:
            entries = file_ops.list_directory(path)
            if entries is not None:
                return {"success": True, "output": entries}
            return {"success": False, "output": "Directory not found", "error": "dir_not_found"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"list_directory error: {exc}",
                "error": "list_directory_failed",
            }

    def _clipboard_read(self, **_) -> dict:
        """Read the current contents of the system clipboard."""
        try:
            text = clip.clipboard_read()
            return {"success": text is not None, "output": text or ""}
        except Exception as exc:
            return {
                "success": False,
                "output": f"clipboard_read error: {exc}",
                "error": "clipboard_failed",
            }

    def _clipboard_write(self, *, text: str, **_) -> dict:
        """Write text to the system clipboard."""
        try:
            ok = clip.clipboard_write(text)
            return {"success": ok, "output": f"Clipboard {'updated' if ok else 'failed'}"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"clipboard_write error: {exc}",
                "error": "clipboard_failed",
            }

    def _system_info(self, **_) -> dict:
        """Return OS, CPU, memory, and disk information."""
        try:
            info = sysinfo.system_info()
            return {"success": True, "output": info}
        except Exception as exc:
            return {
                "success": False,
                "output": f"system_info error: {exc}",
                "error": "system_info_failed",
            }

    def _list_processes(self, **_) -> dict:
        """List running processes (up to 100 entries)."""
        try:
            procs = pm.list_processes()
            return {"success": True, "output": procs[:100]}
        except Exception as exc:
            return {
                "success": False,
                "output": f"list_processes error: {exc}",
                "error": "list_processes_failed",
            }

    def _start_process(self, *, path: str, args: list | None = None, **_) -> dict:
        """Start a new process by executable path and return its PID."""
        try:
            pid = pm.start_process(path, args)
            return {"success": pid is not None, "output": f"pid={pid}"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"start_process error: {exc}",
                "error": "start_process_failed",
            }

    def _kill_process(self, *, pid: int | None = None, name: str | None = None, **_) -> dict:
        """Terminate a process by PID or name."""
        target = pid or name
        try:
            killed = pm.kill_process(target)
            return {
                "success": killed,
                "output": f"Process {target} {'killed' if killed else 'not found'}",
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"kill_process error: {exc}",
                "error": "kill_process_failed",
            }

    def _note(self, *, text: str, **_) -> dict:
        """Agent makes a note to itself — no-op for execution, logged."""
        logger.info("Agent note: %s", text)
        return {"success": True, "output": text}

    def _finish(self, *, summary: str = "", **_) -> dict:
        """Signal that the agent is done."""
        return {"success": True, "output": summary, "done": True}

    def _powershell(self, *, command: str, **_) -> dict:
        """Run a PowerShell command and return output."""
        try:
            from core.powershell import get_default_runner

            runner = get_default_runner()
            result = runner.run_command(command)
            return {
                "success": result.success,
                "output": result.stdout[:2000] if result.success else result.stderr[:1000],
                "exit_code": result.exit_code,
                "objects": result.objects[:50] if result.objects else [],
            }
        except Exception as exc:
            return {
                "success": False,
                "output": f"PowerShell error: {exc}",
                "error": "powershell_failed",
            }

    def _run_script(self, *, path: str, params: dict | None = None, **_) -> dict:
        """Replay a recorded script from a JSON file."""
        try:
            from core.script_engine import ScriptEngine

            engine = ScriptEngine(self)
            result = engine.run_script(path, params)
            return {
                "success": result.success,
                "output": f"Script completed: {result.steps_completed}/{result.steps_total} steps",
                "steps_completed": result.steps_completed,
                "steps_total": result.steps_total,
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "output": f"Script error: {exc}", "error": "script_failed"}

    # Dispatch table
    _dispatch_table: dict[str, Callable] = {
        "click": _click,
        "double_click": _click,
        "right_click": _click,
        "click_text": _click_text,
        "click_image": _click_image,
        "click_control": _click_control,
        "list_controls": _list_controls,
        "set_text": _set_text,
        "read_text": _read_text,
        "read_window": _read_window,
        "type_text": _type_text,
        "press_key": _press_key,
        "hotkey": _hotkey,
        "scroll": _scroll,
        "drag": _drag,
        "screenshot": _screenshot,
        "find_image": _find_image,
        "wait": _wait,
        "wait_for_image": _wait_for_image,
        "smart_wait": _smart_wait,
        "wait_for_stable": _wait_for_stable,
        "wait_for_text": _wait_for_text,
        "open_app": _open_app,
        "smart_open": _smart_open,
        "close_app": _close_app,
        "focus_window": _focus_window,
        "close_window": _close_window,
        "list_windows": _list_windows,
        "read_file": _read_file,
        "write_file": _write_file,
        "list_directory": _list_directory,
        "clipboard_read": _clipboard_read,
        "clipboard_write": _clipboard_write,
        "system_info": _system_info,
        "list_processes": _list_processes,
        "start_process": _start_process,
        "kill_process": _kill_process,
        "note": _note,
        "finish": _finish,
        "powershell": _powershell,
        "run_script": _run_script,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dry_run_result(action_type: str, params: dict) -> dict:
    """Return a synthetic success result for a state-changing action in dry-run mode."""
    preview = ", ".join(f"{k}={v!r}" for k, v in list(params.items())[:4])
    if len(preview) > MAX_PREVIEW_LENGTH:
        preview = preview[:MAX_PREVIEW_LENGTH] + "…"
    msg = f"[DRY-RUN] would have run {action_type}({preview})"
    logger.info(msg)
    return {"success": True, "output": msg, "dry_run": True}


def _contains_sensitive(text: str) -> bool:
    """Check if text looks like it contains sensitive data.

    Used to prevent accidental typing of secrets.
    """
    lower = text.lower()
    return any(keyword in lower for keyword in SENSITIVE_FIELDS)


def _sanitize_params(params: dict) -> dict:
    """Remove potentially large data from params for logging."""
    sanitized = {}
    for k, v in params.items():
        if isinstance(v, str) and len(v) > MAX_STRING_VALUE_LENGTH:
            sanitized[k] = v[:MAX_STRING_VALUE_LENGTH] + "..."
        elif isinstance(v, (list, dict)) and len(str(v)) > MAX_COLLECTION_STRING_LENGTH:
            sanitized[k] = f"<{type(v).__name__} len={len(v)}>"
        else:
            sanitized[k] = v
    return sanitized
