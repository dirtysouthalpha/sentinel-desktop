"""Sentinel Desktop v2 — Action executor.

Takes structured action dicts from the LLM and dispatches them to
the appropriate desktop, file, window, or process functions.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core import clipboard as clip
from core import desktop as desktop_mod
from core import file_ops, launcher, ocr, stealth_input, ui_tree
from core import process_manager as pm
from core import system_info as sysinfo
from core import window_manager as wm
from core.browser import BrowserManager
from core.dpi import transform_action_coordinates
from core.screenshot import capture_to_base64, find_template, wait_for_template


@dataclass
class ExecutorCallbacks:
    """Callbacks for action executor lifecycle events."""

    approval_callback: Callable | None = None
    pre_action_callback: Callable[[dict[str, Any]], None] | None = None


@dataclass
class ExecutorConfig:
    """Configuration for action executor behavior."""

    dry_run: bool = False
    stealth: bool = False
    click_offset: tuple = (0, 0)
    monitor: int | None = None


@dataclass
class DragCoordinates:
    """Coordinates for drag operation."""

    from_x: int
    from_y: int
    to_x: int
    to_y: int
    duration: float = 0.5
    button: str = "left"


@dataclass
class WebClickParams:
    """Parameters for web click actions."""

    selector: str | None = None
    text: str | None = None
    role: str | None = None
    name: str | None = None
    button: str = "left"
    click_count: int = 1


@dataclass
class WebTypeParams:
    """Parameters for web type actions."""

    text: str
    selector: str | None = None
    label: str | None = None
    role: str | None = None
    name: str | None = None
    clear: bool = True


@dataclass
class HttpRequestParams:
    """Parameters for HTTP requests."""

    url: str
    json: dict | list | None = None
    body: str | None = None
    headers: dict | None = None
    params: dict | None = None
    timeout: float = 30.0
    verify_ssl: bool = True


@dataclass
class SkillInstallParams:
    """Parameters for skill installation."""

    name: str
    description: str
    script: dict | None = None
    version: str = "1.0.0"
    author: str = ""
    category: str = "general"
    tags: list | None = None


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
    "click_element",
    "click_mark",
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
    # v14-v17
    "config_set",
    "resize_window",
    "move_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "http_post",
    "http_download",
    "volume_set",
    "mute_toggle",
    "speak",
}


def _build_dispatch_table(**handlers: Callable) -> dict[str, Callable]:
    """Seed the action registry and return the dispatch dict.

    v18: this is the bridge from the v17 hand-maintained dict literal to the
    decorator-based registry (``core/action_registry.py``). Each keyword is an
    action name and each value its unbound handler. Calling this registers
    every name→handler pair in the module-level registry and returns the same
    mapping for use as ``ActionExecutor._dispatch_table``. New actions in v19+
    should use ``@register_action`` directly instead of extending this call.
    """
    from core.action_registry import _REGISTRY, ActionAlreadyRegisteredError

    table: dict[str, Callable] = {}
    for name, handler in handlers.items():
        existing = _REGISTRY.get(name)
        if existing is not None and existing is not handler:
            raise ActionAlreadyRegisteredError(
                f"action {name!r} already registered by {existing.__qualname__}",
            )
        _REGISTRY[name] = handler
        table[name] = handler
    return table


class ActionExecutor:
    """Execute desktop actions returned by the LLM."""

    def __init__(
        self,
        callbacks: ExecutorCallbacks | None = None,
        config: ExecutorConfig | None = None,
    ) -> None:
        """Initialize the action executor.

        Args:
            callbacks: ExecutorCallbacks containing approval_callback and
                pre_action_callback. approval_callback is an async callable
                (action_dict) → bool that, if provided, sends actions for
                approval before execution. pre_action_callback is an optional
                sync callable (action_dict) invoked immediately before each
                action is dispatched, used by GUI to flash an on-screen overlay.
            config: ExecutorConfig containing behavioral settings:
                dry_run (bool) — When True, state-changing actions are logged
                but not executed. stealth (bool) — If True, uses stealth input
                methods (PostMessage/UIA) instead of physical mouse/keyboard
                movements. click_offset (tuple) — (x, y) screen-coord offset
                of the captured image's origin, required for multi-monitor mode.
                monitor (int | None) — Monitor index for multi-monitor setups.
        """
        # Initialize callbacks with defaults
        callbacks = callbacks or ExecutorCallbacks()
        config = config or ExecutorConfig()

        self.approval_callback = callbacks.approval_callback
        self.pre_action_callback = callbacks.pre_action_callback

        # Initialize configuration
        self.dry_run = config.dry_run
        self.stealth = bool(config.stealth)
        self.click_offset = config.click_offset
        self.monitor = config.monitor
        self._desktop = desktop_mod.DesktopEngine()
        self._log: list[dict[str, Any]] = []
        # Perception: the engine stores the latest PerceptionResult here so
        # click_element / click_mark can resolve IDs to coordinates.
        self.perception_result: Any | None = None
        # Browser: lazy-initialized on first web action
        self._browser_manager: BrowserManager | None = None
        # Netops: lazy-initialized SSH client
        self._ssh_clients: dict[str, Any] = {}  # hostname → SSHClient
        # Memory: lazy-initialized semantic memory
        self._semantic_memory: Any | None = None

    @property
    def log(self) -> list[dict[str, Any]]:
        """Return a shallow copy of the action execution log.

        Returns:
            List of dicts, one per executed action, containing action name,
            result, and timing information.

        """
        return list(self._log)

    async def _execute_with_logging(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute action with approval checks and logging."""
        action_type = action.get("action", "").lower()

        # DPI: transform screenshot coordinates to logical space
        action = transform_action_coordinates(action)

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
        self,
        action_type: str,
        params: dict[str, Any],
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

        # DPI: transform screenshot coordinates to logical (pyautogui) space
        # before dispatching. No-op when all monitors are at 100% scaling.
        action = transform_action_coordinates(action)

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
        self,
        *,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        target_size: tuple[int, int] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Click at screen coordinates with optional stealth mode via PostMessage.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.
            button: Mouse button to click ("left", "right", "middle").
            clicks: Number of times to click (1 for single, 2 for double-click).
            target_size: Optional target dimensions (width, height) for stealth-tier
                Fitts's-Law timing and overshoot/correction.
        """
        # Translate from captured-image coords to absolute screen coords for
        # multi-monitor virtual-desktop capture.
        sx = int(x) + self.click_offset[0]
        sy = int(y) + self.click_offset[1]

        # Stealth-tier: attention pause before click
        _apply_attention_pause(f"clicking_at_{sx}_{sy}")

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
            self._desktop.click(sx, sy, button=button, clicks=clicks, target_size=target_size)
            desc = (
                "Double-clicked"
                if clicks == DOUBLE_CLICK_COUNT
                else "Right-clicked"
                if button == "right"
                else "Clicked"
            )
            return {"success": True, "output": f"{desc} ({sx}, {sy})"}
        except (OSError, RuntimeError, desktop_mod._FailSafeException) as exc:
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

    def _click_text(
        self, *, text: str, button: str = "left", fuzzy: bool = True, **kwargs: Any
    ) -> dict:
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
        except (OSError, RuntimeError, ValueError, desktop_mod._FailSafeException) as exc:
            return {
                "success": False,
                "output": f"click_text error: {exc}",
                "error": "click_text_failed",
            }

    def _read_text(
        self, *, scope: str = "focused", window: str | None = None, **kwargs: Any
    ) -> dict:
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

    def _read_window(self, *, title: str, **kwargs: Any) -> dict:
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
        **kwargs: Any,
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
        self,
        *,
        window_title: str | None = None,
        max_results: int = 60,
        **kwargs: Any,
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

    def _click_element(
        self,
        *,
        element_id: int,
        button: str = "left",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Click a perception element by its numeric ID.

        Resolves the element ID from the latest perception result to screen
        coordinates and delegates to _click. Falls back to raw coordinate mode
        if no perception data is available.
        """
        if self.perception_result is None:
            return {
                "success": False,
                "output": "No perception data available — use click with coordinates instead",
                "error": "no_perception",
            }

        elem = self.perception_result.find_by_id(element_id)
        if elem is None:
            return {
                "success": False,
                "output": f"Element ID {element_id} not found in current perception",
                "error": "element_not_found",
            }

        cx, cy = elem.center
        return self._click(x=cx, y=cy, button=button)

    def _click_mark(
        self,
        *,
        mark_id: int,
        button: str = "left",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Click a Set-of-Marks target by its numbered mark ID.

        Alias for click_element — both resolve numbered IDs from the
        perception pipeline. Kept as a separate action so the LLM can use
        the more intuitive 'click_mark' when working with SoM screenshots.
        """
        return self._click_element(element_id=mark_id, button=button)

    def _list_elements(self, **kwargs: Any) -> dict[str, Any]:
        """Return the current perception element list for the LLM.

        Provides a compact summary of all detected elements with their IDs,
        types, labels, and interactability. The LLM uses this to pick targets.
        """
        if self.perception_result is None:
            return {
                "success": False,
                "output": "No perception data available",
                "error": "no_perception",
            }

        elements = [elem.to_dict() for elem in self.perception_result.elements]

        return {
            "success": True,
            "output": elements,
            "count": len(elements),
            "interactable": len(self.perception_result.interactable_elements()),
            "text_description": self.perception_result.to_llm_context(),
        }

    def _set_text(
        self,
        *,
        text: str,
        name: str | None = None,
        automation_id: str | None = None,
        window_title: str | None = None,
        **kwargs: Any,
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

    def _click_image(self, *, template_path: str, confidence: float = 0.8, **kwargs: Any) -> dict:
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

    def _type_text(self, *, text: str, field_type: str = "unknown", **kwargs: Any) -> dict:
        """Type text via keyboard input, falling back to clipboard paste if needed.

        Args:
            text: The text to type.
            field_type: Type of field being typed into (e.g., "email", "password",
                "username"). Used for stealth-tier re-read pause simulation.
        """
        # Sensitive field check
        if _contains_sensitive(text):
            return {
                "success": False,
                "output": "Blocked: text appears to contain sensitive data",
                "error": "sensitive_field",
            }

        # Stealth-tier: re-read pause before typing into sensitive fields
        _apply_re_read_pause(field_type)

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

    def _press_key(self, *, key: str, **kwargs: Any) -> dict:
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

    def _hotkey(self, *, keys: list, **kwargs: Any) -> dict:
        """Press a keyboard shortcut combination (e.g. ['ctrl', 'c'])."""
        try:
            if self.stealth and stealth_input.is_available() and stealth_input.post_hotkey(keys):
                return {"success": True, "output": f"Hotkey: {'+'.join(keys)} — stealth"}
            self._desktop.hotkey(*keys)
            return {"success": True, "output": f"Hotkey: {'+'.join(keys)}"}
        except Exception as exc:
            logger.debug("hotkey failed for %s: %s", keys, exc)
            return {"success": False, "output": f"Hotkey failed: {exc}", "error": "hotkey_failed"}

    def _mouse_move(
        self,
        *,
        x: int,
        y: int,
        **kwargs: Any,
    ) -> dict:
        """Move the mouse cursor to screen coordinates without clicking."""
        sx = int(x) + self.click_offset[0]
        sy = int(y) + self.click_offset[1]
        try:
            self._desktop.move_to(sx, sy)
            return {"success": True, "output": f"Moved to ({sx}, {sy})"}
        except (OSError, RuntimeError, desktop_mod._FailSafeException) as exc:
            return {
                "success": False,
                "output": f"mouse_move error to ({sx},{sy}): {exc}",
                "error": "mouse_move_failed",
            }

    def _drag(
        self,
        *,
        coords: DragCoordinates | None = None,
        from_x: int = 0,
        from_y: int = 0,
        to_x: int = 0,
        to_y: int = 0,
        duration: float = 0.5,
        button: str = "left",
        **kwargs: Any,
    ) -> dict:
        """Drag from one screen position to another with stealth PostMessage support."""
        if coords is None:
            coords = DragCoordinates(
                from_x=int(from_x),
                from_y=int(from_y),
                to_x=int(to_x),
                to_y=int(to_y),
                duration=duration,
                button=button,
            )

        sx = int(coords.from_x) + self.click_offset[0]
        sy = int(coords.from_y) + self.click_offset[1]
        tx = int(coords.to_x) + self.click_offset[0]
        ty = int(coords.to_y) + self.click_offset[1]
        if self.stealth and stealth_input.is_available():
            result = self._stealth_drag_win32((sx, sy), (tx, ty), coords)
            if result is not None:
                return result
        try:
            self._desktop.drag(sx, sy, tx, ty, duration=coords.duration, button=coords.button)
            return {
                "success": True,
                "output": f"Dragged ({coords.from_x},{coords.from_y})→({coords.to_x},{coords.to_y})",
            }
        except Exception as exc:
            return {"success": False, "output": f"Drag failed: {exc}", "error": "drag_failed"}

    def _stealth_drag_win32(
        self,
        start_coords: tuple[int, int],
        end_coords: tuple[int, int],
        drag_params: DragCoordinates,
    ) -> dict | None:
        """Attempt a stealth drag via Win32 PostMessage; returns result dict or None on failure.

        Args:
            start_coords: (x, y) starting screen coordinates.
            end_coords: (x, y) ending screen coordinates.
            drag_params: DragCoordinates containing duration and button.
        """
        try:
            import time as _t

            import win32api
            import win32con
            import win32gui

            sx, sy = start_coords
            tx, ty = end_coords

            hwnd = win32gui.WindowFromPoint((sx, sy))
            cx, cy = win32gui.ScreenToClient(hwnd, (sx, sy))
            cx2, cy2 = win32gui.ScreenToClient(hwnd, (tx, ty))
            lparam_down = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
            lparam_up = ((cy2 & 0xFFFF) << 16) | (cx2 & 0xFFFF)
            if drag_params.button == "right":
                msg_down, msg_up, mk = win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON
            elif drag_params.button == "middle":
                msg_down, msg_up, mk = win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP, win32con.MK_MBUTTON
            else:
                msg_down, msg_up, mk = win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON
            win32api.PostMessage(hwnd, msg_down, mk, lparam_down)
            steps = max(1, int(drag_params.duration / 0.01))
            for i in range(1, steps + 1):
                mx = int(cx + (cx2 - cx) * i / steps)
                my = int(cy + (cy2 - cy) * i / steps)
                lparam_move = ((my & 0xFFFF) << 16) | (mx & 0xFFFF)
                win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, mk, lparam_move)
                _t.sleep(drag_params.duration / steps)
            win32api.PostMessage(hwnd, msg_up, 0, lparam_up)
            return {"success": True, "output": f"Dragged ({sx},{sy})→({tx},{ty}) — stealth"}
        except Exception as exc:
            logger.debug("Stealth drag failed, falling back: %s", exc)
            return None

    def _scroll(self, *, amount: int, **kwargs: Any) -> dict:
        """Scroll the mouse wheel by the given amount (positive = up, negative = down)."""
        try:
            self._desktop.scroll(amount)
            return {"success": True, "output": f"Scrolled {amount}"}
        except Exception as exc:
            return {"success": False, "output": f"Scroll failed: {exc}", "error": "scroll_failed"}

    def _screenshot(self, **kwargs: Any) -> dict:
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

    def _find_image(self, *, template_path: str, confidence: float = 0.8, **kwargs: Any) -> dict:
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

    def _wait(self, *, seconds: float = 1.0, **kwargs: Any) -> dict:
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

    def _wait_for_image(self, *, template_path: str, timeout: int = 30, **kwargs: Any) -> dict:
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

    def _smart_wait(
        self, *, timeout: float = 10, region: list | None = None, **kwargs: Any
    ) -> dict:
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
        self,
        *,
        timeout: float = 10,
        stable_time: float = 1.5,
        region: list | None = None,
        **kwargs: Any,
    ) -> dict:
        """Wait until the screen stops changing."""
        try:
            from core.smart_wait import SmartWait

            sw = SmartWait()
            region_tuple = tuple(region) if region else None
            result = sw.wait_for_stable(
                timeout=float(timeout),
                stable_time=float(stable_time),
                region=region_tuple,
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
        self,
        *,
        text: str,
        timeout: float = 10,
        region: list | None = None,
        **kwargs: Any,
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

    def _open_app(self, *, path: str, args: list | None = None, **kwargs: Any) -> dict:
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

    def _smart_open(self, *, name: str, **kwargs: Any) -> dict:
        """Focus an existing window if the app is already running, else launch.

        Self-healing: if normal launch fails, tries PowerShell Start-Process.
        """
        result = launcher.smart_open(name)
        if result.get("success"):
            return result

        # Fallback: PowerShell Start-Process
        import shutil
        import subprocess

        ps_exe = shutil.which("powershell") or shutil.which("pwsh")
        if not ps_exe:
            logger.debug("PowerShell not found for smart_open fallback")
            result["hint"] = "Try open_app() with the full executable path"
            return result

        try:
            # Escape single quotes for PowerShell's single-quoted string literal
            # (PS doubling rule) so a name containing ' cannot break out and
            # inject arbitrary commands. The argv list form is also used so the
            # shell itself is never invoked.
            safe_name = name.replace("'", "''")
            subprocess.Popen(  # noqa: S603 - Intentional process execution for desktop automation
                [ps_exe, "-Command", f"Start-Process '{safe_name}'"],
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

    def _close_app(self, *, name: str | None = None, pid: int | None = None, **kwargs: Any) -> dict:
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

    def _focus_window(self, *, title: str, **kwargs: Any) -> dict:
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

    def _close_window(self, *, title: str, **kwargs: Any) -> dict:
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

    def _list_windows(self, **kwargs: Any) -> dict:
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

    def _read_file(self, *, path: str, **kwargs: Any) -> dict:
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

    def _write_file(self, *, path: str, content: str, **kwargs: Any) -> dict:
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

    def _list_directory(self, *, path: str = ".", **kwargs: Any) -> dict:
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

    # -------------------------------------------------------------------
    # File Operations Plus (v13.0 — extended file management)
    # -------------------------------------------------------------------

    def _delete_file(self, *, path: str, force: bool = False, **kwargs: Any) -> dict:
        """Delete a file or directory."""
        ok = file_ops.delete_file(path, force=force)
        if ok:
            return {"success": True, "output": f"Deleted {path}"}
        return {"success": False, "output": f"Failed to delete {path}"}

    def _move_file(self, *, src: str, dst: str, **kwargs: Any) -> dict:
        """Move or rename a file."""
        ok = file_ops.move_file(src, dst)
        if ok:
            return {"success": True, "output": f"Moved {src} → {dst}"}
        return {"success": False, "output": f"Failed to move {src} → {dst}"}

    def _copy_file(self, *, src: str, dst: str, **kwargs: Any) -> dict:
        """Copy a file to a new location."""
        ok = file_ops.copy_file(src, dst)
        if ok:
            return {"success": True, "output": f"Copied {src} → {dst}"}
        return {"success": False, "output": f"Failed to copy {src} → {dst}"}

    def _mkdir(self, *, path: str, parents: bool = True, **kwargs: Any) -> dict:
        """Create a directory."""
        ok = file_ops.mkdir(path, parents=parents)
        if ok:
            return {"success": True, "output": f"Created directory {path}"}
        return {"success": False, "output": f"Failed to create {path}"}

    def _stat_file(self, *, path: str, **kwargs: Any) -> dict:
        """Get file metadata."""
        info = file_ops.stat_file(path)
        if info is not None:
            return {"success": True, "output": info}
        return {
            "success": False,
            "output": f"Failed to stat {path}",
            "error": "stat_failed",
        }

    def _find_files(
        self,
        *,
        pattern: str,
        root: str = ".",
        max_results: int = 100,
        **kwargs: Any,
    ) -> dict:
        """Search for files matching a glob pattern."""
        results = file_ops.find_files(
            pattern,
            root=root,
            max_results=max_results,
        )
        if results is not None:
            return {
                "success": True,
                "output": results,
                "count": len(results),
            }
        return {
            "success": False,
            "output": f"Failed to search {pattern}",
            "error": "find_failed",
        }

    def _archive_create(
        self,
        *,
        archive_path: str,
        files: list[str],
        base_dir: str = ".",
        **kwargs: Any,
    ) -> dict:
        """Create a zip archive."""
        ok = file_ops.archive_create(
            archive_path,
            files,
            base_dir=base_dir,
        )
        if ok:
            return {
                "success": True,
                "output": f"Created {archive_path} ({len(files)} files)",
            }
        return {
            "success": False,
            "output": f"Failed to create {archive_path}",
        }

    def _archive_extract(
        self,
        *,
        archive_path: str,
        dest_dir: str = ".",
        **kwargs: Any,
    ) -> dict:
        """Extract a zip archive."""
        ok = file_ops.archive_extract(archive_path, dest_dir=dest_dir)
        if ok:
            return {
                "success": True,
                "output": f"Extracted {archive_path} → {dest_dir}",
            }
        return {
            "success": False,
            "output": f"Failed to extract {archive_path}",
        }

    # -------------------------------------------------------------------
    # Process & Service Control (v13.0)
    # -------------------------------------------------------------------

    def _set_priority(self, *, pid: int, priority: str, **kwargs: Any) -> dict:
        """Set process priority."""
        from core.process_manager import set_priority

        ok = set_priority(pid, priority)
        return {
            "success": ok,
            "output": f"Priority {'set' if ok else 'failed'} for PID {pid}",
        }

    def _get_env(self, *, name: str, **kwargs: Any) -> dict:
        """Read an environment variable."""
        from core.process_manager import get_env

        value = get_env(name)
        if value is not None:
            return {"success": True, "output": value, "name": name}
        return {
            "success": False,
            "output": f"Variable {name} not set",
            "error": "env_not_found",
        }

    def _set_env(
        self,
        *,
        name: str,
        value: str,
        permanent: bool = False,
        **kwargs: Any,
    ) -> dict:
        """Set an environment variable."""
        from core.process_manager import set_env

        ok = set_env(name, value, permanent=permanent)
        return {
            "success": ok,
            "output": f"{'Set' if ok else 'Failed to set'} {name}",
        }

    def _service_control(
        self,
        *,
        name: str,
        control_action: str,
        **kwargs: Any,
    ) -> dict:
        """Control a Windows service."""
        from core.process_manager import service_control

        return service_control(name, control_action)

    # -------------------------------------------------------------------
    # Credential Vault (v13.0)
    # -------------------------------------------------------------------

    def _cred_store(self, *, key: str, value: str, **kwargs: Any) -> dict:
        """Store a credential in the vault."""
        from core.encryption import CredentialVault

        vault = CredentialVault()
        ok = vault.store(key, value)
        return {
            "success": ok,
            "output": f"{'Stored' if ok else 'Failed'} {key}",
        }

    def _cred_read(self, *, key: str, **kwargs: Any) -> dict:
        """Read a credential from the vault."""
        from core.encryption import CredentialVault

        vault = CredentialVault()
        value = vault.retrieve(key)
        if value is not None:
            return {"success": True, "output": value, "key": key}
        return {
            "success": False,
            "output": f"Key {key} not found",
            "error": "cred_not_found",
        }

    # -------------------------------------------------------------------
    # Registry (v13.0)
    # -------------------------------------------------------------------

    def _registry_read(
        self,
        *,
        path: str,
        value_name: str = "",
        **kwargs: Any,
    ) -> dict:
        """Read a registry value."""
        from core.registry import registry_read

        result = registry_read(path, value_name)
        if result is not None:
            return {"success": True, "output": result}
        return {
            "success": False,
            "output": f"Failed to read {path}",
            "error": "registry_read_failed",
        }

    def _registry_write(
        self,
        *,
        path: str,
        value_name: str,
        data: str,
        reg_type: str = "REG_SZ",
        **kwargs: Any,
    ) -> dict:
        """Write a registry value."""
        from core.registry import registry_write

        ok = registry_write(path, value_name, data, reg_type)
        return {
            "success": ok,
            "output": f"{'Wrote' if ok else 'Failed'} {path}",
        }

    def _registry_delete(
        self,
        *,
        path: str,
        value_name: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Delete a registry key or value."""
        from core.registry import registry_delete

        ok = registry_delete(path, value_name)
        return {
            "success": ok,
            "output": f"{'Deleted' if ok else 'Failed'} {path}",
        }

    def _clipboard_read(self, **kwargs: Any) -> dict:
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

    def _clipboard_write(self, *, text: str, **kwargs: Any) -> dict:
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

    def _system_info(self, **kwargs: Any) -> dict:
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

    def _list_processes(self, **kwargs: Any) -> dict:
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

    def _start_process(self, *, path: str, args: list | None = None, **kwargs: Any) -> dict:
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

    def _kill_process(
        self, *, pid: int | None = None, name: str | None = None, **kwargs: Any
    ) -> dict:
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

    def _note(self, *, text: str, **kwargs: Any) -> dict:
        """Agent makes a note to itself — no-op for execution, logged."""
        logger.info("Agent note: %s", text)
        return {"success": True, "output": text}

    # -------------------------------------------------------------------
    # Browser actions (v8.0 — Playwright web automation)
    # -------------------------------------------------------------------

    @property
    def browser(self) -> BrowserManager:
        """Lazy-initialized browser manager."""
        if self._browser_manager is None:
            self._browser_manager = BrowserManager(headless=True, ignore_https_errors=True)
        return self._browser_manager

    def _web_open(self, *, url: str, wait_until: str = "load", **kwargs: Any) -> dict:
        """Navigate to a URL in the managed browser."""
        return self.browser.open(url, wait_until=wait_until)

    def _web_click(
        self,
        *,
        params: WebClickParams | None = None,
        selector: str | None = None,
        text: str | None = None,
        role: str | None = None,
        name: str | None = None,
        button: str = "left",
        click_count: int = 1,
        **kwargs: Any,
    ) -> dict:
        """Click an element in the browser by selector, text, or ARIA role."""
        if params is None:
            params = WebClickParams(
                selector=selector,
                text=text,
                role=role,
                name=name,
                button=button,
                click_count=click_count,
            )
        return self.browser.click(
            selector=params.selector,
            text=params.text,
            role=params.role,
            name=params.name,
            button=params.button,
            click_count=params.click_count,
        )

    def _web_type(
        self,
        *,
        params: WebTypeParams | None = None,
        text: str = "",
        selector: str | None = None,
        label: str | None = None,
        role: str | None = None,
        name: str | None = None,
        clear: bool = True,
        **kwargs: Any,
    ) -> dict:
        """Type text into a browser form field."""
        if params is None:
            params = WebTypeParams(
                text=text,
                selector=selector,
                label=label,
                role=role,
                name=name,
                clear=clear,
            )
        return self.browser.type_text(
            text=params.text,
            selector=params.selector,
            label=params.label,
            role=params.role,
            name=params.name,
            clear=params.clear,
        )

    def _web_read(
        self, *, selector: str | None = None, full_page: bool = False, **kwargs: Any
    ) -> dict:
        """Read text content from the browser page or element."""
        return self.browser.read(selector=selector, full_page=full_page)

    def _web_extract(self, *, selector: str = "table", format: str = "json", **kwargs: Any) -> dict:
        """Extract structured data from the browser page."""
        return self.browser.extract(selector=selector, format=format)

    def _web_wait_for(
        self,
        *,
        selector: str | None = None,
        text: str | None = None,
        state: str = "visible",
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> dict:
        """Wait for an element or condition in the browser."""
        return self.browser.wait_for(
            selector=selector,
            text=text,
            state=state,
            timeout=timeout * 1000,
        )

    def _web_screenshot(
        self, *, selector: str | None = None, full_page: bool = False, **kwargs: Any
    ) -> dict:
        """Capture a screenshot of the browser viewport or element."""
        return self.browser.screenshot(selector=selector, full_page=full_page)

    def _web_eval_js(self, *, expression: str, **kwargs: Any) -> dict:
        """Execute JavaScript in the browser context."""
        return self.browser.eval_js(expression=expression)

    def _web_download(
        self, *, url: str | None = None, save_path: str | None = None, **kwargs: Any
    ) -> dict:
        """Download a file from the browser."""
        return self.browser.download(url=url, save_path=save_path)

    def _web_upload(self, *, selector: str, file_paths: list[str], **kwargs: Any) -> dict:
        """Upload files to a web form."""
        return self.browser.upload(selector=selector, file_paths=file_paths)

    def _web_tabs(
        self,
        *,
        action: str = "list",
        index: int | None = None,
        url: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Manage browser tabs."""
        return self.browser.tabs(action=action, index=index, url=url)

    def _finish(self, *, summary: str = "", **kwargs: Any) -> dict:
        """Signal that the agent is done."""
        return {"success": True, "output": summary, "done": True}

    def _powershell(self, *, command: str, **kwargs: Any) -> dict:
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

    def _run_script(self, *, path: str, params: dict | None = None, **kwargs: Any) -> dict:
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

    # -------------------------------------------------------------------
    # Netops actions (v9.0 — SSH network device control)
    # -------------------------------------------------------------------

    def _ssh_connect(
        self,
        *,
        hostname: str,
        username: str = "",
        password: str = "",
        port: int = 22,
        key_filename: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Connect to a network device via SSH."""
        try:
            from core.netops.ssh_client import SSHClient

            client = SSHClient(
                hostname=hostname,
                username=username,
                password=password,
                port=port,
                key_filename=key_filename,
            )
            client.connect()
            self._ssh_clients[hostname] = client
            return {"success": True, "output": f"Connected to {hostname}"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"SSH connect error: {exc}",
                "error": "ssh_connect_failed",
            }

    def _ssh_disconnect(self, *, hostname: str, **kwargs: Any) -> dict:
        """Disconnect from an SSH device."""
        client = self._ssh_clients.pop(hostname, None)
        if client is None:
            return {"success": False, "output": f"No connection to {hostname}"}
        client.close()
        return {"success": True, "output": f"Disconnected from {hostname}"}

    def _ssh_run(
        self,
        *,
        hostname: str,
        command: str,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict:
        """Run a command on a connected SSH device."""
        client = self._ssh_clients.get(hostname)
        if client is None:
            return {
                "success": False,
                "output": f"Not connected to {hostname}",
                "error": "ssh_not_connected",
            }
        result = client.run_command(command, timeout=timeout)
        return {
            "success": result.success,
            "output": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "exit_code": result.exit_code,
        }

    def _ssh_show(
        self,
        *,
        hostname: str,
        what: str,
        device_type: str = "generic",
        **kwargs: Any,
    ) -> dict:
        """Run a device-aware show command on an SSH device."""
        from core.netops.command_runner import CommandRunner
        from core.netops.output_parser import (
            parse_arp_table,
            parse_interfaces,
            parse_routing_table,
            parse_version,
        )

        client = self._ssh_clients.get(hostname)
        if client is None:
            return {
                "success": False,
                "output": f"Not connected to {hostname}",
                "error": "ssh_not_connected",
            }

        runner = CommandRunner(client, device_type=device_type)
        parsers = {
            "version": (runner.show_version, parse_version),
            "interfaces": (runner.show_interfaces, parse_interfaces),
            "routing": (runner.show_routing, parse_routing_table),
            "arp": (runner.show_arp, parse_arp_table),
            "cpu": (runner.show_cpu, None),
            "logging": (runner.show_logging, None),
            "config": (runner.show_running_config, None),
        }

        if what not in parsers:
            return {
                "success": False,
                "output": f"Unknown show command: {what}. Options: {list(parsers.keys())}",
            }

        cmd_fn, parser_fn = parsers[what]
        result = cmd_fn()
        if not result.success:
            return {"success": False, "output": result.stderr or result.stdout}

        if parser_fn:
            parsed = parser_fn(result.stdout)
            return {"success": True, "output": parsed, "raw": result.stdout[:3000]}

        return {"success": True, "output": result.stdout[:5000]}

    def _ssh_ping(
        self,
        *,
        hostname: str,
        target: str,
        count: int = 4,
        device_type: str = "generic",
        **kwargs: Any,
    ) -> dict:
        """Ping a target from a connected SSH device."""
        from core.netops.command_runner import CommandRunner
        from core.netops.output_parser import parse_ping

        client = self._ssh_clients.get(hostname)
        if client is None:
            return {
                "success": False,
                "output": f"Not connected to {hostname}",
                "error": "ssh_not_connected",
            }

        runner = CommandRunner(client, device_type=device_type)
        result = runner.ping(target, count=count)
        parsed = parse_ping(result.stdout)
        return {"success": parsed["success"], "output": parsed, "raw": result.stdout}

    def _ssh_traceroute(
        self,
        *,
        hostname: str,
        target: str,
        device_type: str = "generic",
        **kwargs: Any,
    ) -> dict:
        """Traceroute to a target from a connected SSH device."""
        from core.netops.command_runner import CommandRunner
        from core.netops.output_parser import parse_traceroute

        client = self._ssh_clients.get(hostname)
        if client is None:
            return {
                "success": False,
                "output": f"Not connected to {hostname}",
                "error": "ssh_not_connected",
            }

        runner = CommandRunner(client, device_type=device_type)
        result = runner.traceroute(target)
        parsed = parse_traceroute(result.stdout)
        return {
            "success": parsed["success"],
            "output": parsed,
            "raw": result.stdout,
        }

    # -------------------------------------------------------------------
    # Memory actions (v11.0 — persistent memory)
    # -------------------------------------------------------------------

    def _memory_store(
        self,
        *,
        key: str,
        value: str,
        category: str = "",
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Store a fact in semantic memory."""
        try:
            mem = self._get_semantic_memory()
            fact_id = mem.store(key=key, value=value, category=category, tags=tags)
            return {"success": True, "fact_id": fact_id, "key": key}
        except Exception as exc:
            return {
                "success": False,
                "output": f"Memory store error: {exc}",
                "error": "memory_store_failed",
            }

    def _memory_recall(self, *, key: str, **kwargs: Any) -> dict:
        """Recall a fact from semantic memory by key."""
        try:
            mem = self._get_semantic_memory()
            result = mem.recall(key)
            if result is None:
                return {"success": False, "output": f"No fact found for key: {key}"}
            return {"success": True, "fact": result}
        except Exception as exc:
            return {
                "success": False,
                "output": f"Memory recall error: {exc}",
                "error": "memory_recall_failed",
            }

    def _memory_search(self, *, query: str, limit: int = 10, **kwargs: Any) -> dict:
        """Search semantic memory by keyword."""
        try:
            mem = self._get_semantic_memory()
            results = mem.query(query, limit=limit)
            return {"success": True, "results": results, "count": len(results)}
        except Exception as exc:
            return {
                "success": False,
                "output": f"Memory search error: {exc}",
                "error": "memory_search_failed",
            }

    def _memory_forget(self, *, key: str, **kwargs: Any) -> dict:
        """Delete a fact from semantic memory."""
        try:
            mem = self._get_semantic_memory()
            deleted = mem.delete(key)
            if deleted:
                return {"success": True, "output": f"Forgot: {key}"}
            return {"success": False, "output": f"Key not found: {key}"}
        except Exception as exc:
            return {
                "success": False,
                "output": f"Memory forget error: {exc}",
                "error": "memory_forget_failed",
            }

    def _get_semantic_memory(self) -> Any:
        """Lazy-init semantic memory."""
        if self._semantic_memory is None:
            from core.memory.semantic import SemanticMemory

            self._semantic_memory = SemanticMemory()
        return self._semantic_memory

    # -------------------------------------------------------------------
    # Conductor actions (v12.0 — multi-agent orchestration)
    # -------------------------------------------------------------------

    async def _conductor_run(
        self,
        *,
        goal: str,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> dict:
        """Decompose and execute a complex goal via conductor."""
        try:
            from core.conductor.coordinator import Conductor

            conductor = Conductor()
            result = await conductor.run(goal, timeout=timeout)
            return result
        except Exception as exc:
            return {
                "goal": goal,
                "status": "failed",
                "success": False,
                "summary": f"Conductor error: {exc}",
                "error": "conductor_run_failed",
            }

    def _conductor_run_sync(
        self,
        *,
        goal: str,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> dict:
        """Synchronous wrapper for conductor_run."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                self._conductor_run(goal=goal, timeout=timeout),
            )
            return future.result(timeout=timeout + 10)

    # -------------------------------------------------------------------
    # Resilience actions (v14.0)
    # -------------------------------------------------------------------

    def _retry_last(self, **kwargs: Any) -> dict:
        """Retry the last failed action in the execution log."""
        for entry in reversed(self._log):
            if not entry.get("success", True):
                action_type = entry["action"]
                params = entry.get("params", {})
                logger.info("retry_last: re-running '%s'", action_type)
                return self.execute_sync({"action": action_type, **params})
        return {"success": False, "output": "No failed action in log to retry"}

    def _get_circuit_breakers(self, **kwargs: Any) -> dict:
        """Return state of all circuit breakers."""
        from core.resilience import get_all_breaker_stats

        stats = get_all_breaker_stats()
        return {"success": True, "output": stats, "breakers": stats}

    # -------------------------------------------------------------------
    # Config actions (v15.0)
    # -------------------------------------------------------------------

    def _config_get(self, *, key: str, default: Any = None, **kwargs: Any) -> dict:
        """Read a persisted config value."""
        from core.config_store import get_default_store

        val = get_default_store().get(key, default)
        return {"success": True, "key": key, "value": val, "output": str(val)}

    def _config_set(self, *, key: str, value: Any, **kwargs: Any) -> dict:
        """Persist a config value."""
        from core.config_store import get_default_store

        get_default_store().set(key, value)
        return {"success": True, "key": key, "value": value, "output": f"Set {key} = {value!r}"}

    # -------------------------------------------------------------------
    # Network diagnostic actions (v15.0)
    # -------------------------------------------------------------------

    def _dns_lookup(
        self,
        *,
        hostname: str,
        record_type: str = "A",
        server: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Resolve a hostname via DNS."""
        from core.net_tools import dns_lookup

        result = dns_lookup(hostname, record_type=record_type, server=server)
        result["success"] = not bool(result.get("error"))
        result["output"] = result.get("addresses", [])
        return result

    def _ping(
        self,
        *,
        host: str,
        count: int = 4,
        timeout: int = 3,
        **kwargs: Any,
    ) -> dict:
        """Ping a host."""
        from core.net_tools import ping_host

        result = ping_host(host, count=count, timeout=timeout)
        result["output"] = result.get("output", "")
        return result

    def _port_scan(
        self,
        *,
        host: str,
        ports: list[int],
        timeout: float = 2.0,
        **kwargs: Any,
    ) -> dict:
        """Scan TCP ports on a host."""
        from core.net_tools import scan_ports

        results = scan_ports(host, ports, timeout=timeout)
        open_ports = [p for p, open_ in results.items() if open_]
        return {
            "success": True,
            "host": host,
            "results": results,
            "open_ports": open_ports,
            "output": f"{len(open_ports)}/{len(ports)} ports open on {host}",
        }

    # -------------------------------------------------------------------
    # Window management actions (v16.0)
    # -------------------------------------------------------------------

    def _resize_window(self, *, title: str, width: int, height: int, **kwargs: Any) -> dict:
        """Resize a window by title."""
        from core.window_control import resize_window

        return resize_window(title, width, height)

    def _move_window(self, *, title: str, x: int, y: int, **kwargs: Any) -> dict:
        """Move a window by title."""
        from core.window_control import move_window

        return move_window(title, x, y)

    def _minimize_window(self, *, title: str, **kwargs: Any) -> dict:
        """Minimize a window by title."""
        from core.window_control import minimize_window

        return minimize_window(title)

    def _maximize_window(self, *, title: str, **kwargs: Any) -> dict:
        """Maximize a window by title."""
        from core.window_control import maximize_window

        return maximize_window(title)

    def _restore_window(self, *, title: str, **kwargs: Any) -> dict:
        """Restore a window by title."""
        from core.window_control import restore_window

        return restore_window(title)

    def _get_window_state(self, *, title: str, **kwargs: Any) -> dict:
        """Get window geometry and state."""
        from core.window_control import get_window_state

        return get_window_state(title)

    def _get_monitors(self, **kwargs: Any) -> dict:
        """Return all connected monitor info."""
        from core.window_control import get_monitors

        monitors = get_monitors()
        return {"success": True, "monitors": monitors, "count": len(monitors), "output": monitors}

    # -------------------------------------------------------------------
    # HTTP client actions (v16.0)
    # -------------------------------------------------------------------

    def _http_get(
        self,
        *,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        timeout: float = 30.0,
        verify_ssl: bool = True,
        **kwargs: Any,
    ) -> dict:
        """HTTP GET request."""
        from core.http_client import http_get

        return http_get(url, headers=headers, params=params, timeout=timeout, verify_ssl=verify_ssl)

    def _http_post(
        self,
        *,
        params: HttpRequestParams | None = None,
        url: str = "",
        body: str | None = None,
        json: dict | list | None = None,
        headers: dict | None = None,
        timeout: float = 30.0,
        verify_ssl: bool = True,
        **kwargs: Any,
    ) -> dict:
        """HTTP POST request."""
        from core.http_client import http_post

        if params is None:
            params = HttpRequestParams(
                url=url,
                body=body,
                json=json,
                headers=headers,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )
        return http_post(
            params.url,
            body=params.body,
            json=params.json,
            headers=params.headers,
            params=params.params,
            timeout=params.timeout,
            verify_ssl=params.verify_ssl,
        )

    def _http_download(
        self,
        *,
        url: str,
        save_path: str,
        headers: dict | None = None,
        timeout: float = 120.0,
        verify_ssl: bool = True,
        **kwargs: Any,
    ) -> dict:
        """Download file via HTTP."""
        from core.http_client import http_download

        return http_download(
            url, save_path, headers=headers, timeout=timeout, verify_ssl=verify_ssl
        )

    # -------------------------------------------------------------------
    # File / process monitoring actions (v16.0)
    # -------------------------------------------------------------------

    def _watch_file(
        self,
        *,
        path: str,
        event: str = "modify",
        timeout: float = 60.0,
        poll_interval: float = 0.5,
        **kwargs: Any,
    ) -> dict:
        """Wait for a file event (modify/create/delete)."""
        from core.file_watcher import watch_file

        return watch_file(path, timeout=timeout, poll_interval=poll_interval, event=event)

    def _watch_file_content(
        self,
        *,
        path: str,
        contains: str,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> dict:
        """Wait until a file contains a specific string."""
        from core.file_watcher import watch_file_content

        return watch_file_content(path, contains, timeout=timeout)

    def _watch_process(
        self,
        *,
        name: str,
        event: str = "start",
        pid: int | None = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> dict:
        """Wait for a process event (start/stop/cpu_spike)."""
        from core.file_watcher import watch_process

        return watch_process(name, event=event, pid=pid, timeout=timeout)

    # -------------------------------------------------------------------
    # Audio / voice actions (v17.0)
    # -------------------------------------------------------------------

    def _speak(
        self,
        *,
        text: str,
        blocking: bool = True,
        rate: int = 0,
        volume: int = 100,
        **kwargs: Any,
    ) -> dict:
        """Speak text via Windows TTS."""
        from core.audio import speak

        ok = speak(text, blocking=blocking, rate=rate, volume=volume)
        return {"success": ok, "output": f"Spoke: {text[:80]}" if ok else "TTS failed"}

    def _listen(
        self,
        *,
        timeout: float = 5.0,
        phrase_limit: float = 10.0,
        **kwargs: Any,
    ) -> dict:
        """Capture microphone input and return transcription."""
        from core.audio import listen

        text = listen(timeout=timeout, phrase_limit=phrase_limit)
        if text:
            return {"success": True, "text": text, "output": text}
        return {"success": False, "text": "", "output": "No speech detected"}

    def _volume_get(self, **kwargs: Any) -> dict:
        """Get system master volume."""
        from core.audio import volume_get

        level = volume_get()
        if level < 0:
            return {"success": False, "output": "Volume unavailable on this platform"}
        return {"success": True, "level": level, "output": f"Volume: {level}%"}

    def _volume_set(self, *, level: int, **kwargs: Any) -> dict:
        """Set system master volume."""
        from core.audio import volume_set

        ok = volume_set(level)
        return {
            "success": ok,
            "level": level,
            "output": f"Set volume to {level}%" if ok else "Volume set failed",
        }

    def _mute_toggle(self, **kwargs: Any) -> dict:
        """Toggle system mute."""
        from core.audio import mute_toggle

        muted = mute_toggle()
        return {"success": True, "muted": muted, "output": "Muted" if muted else "Unmuted"}

    def _list_voices(self, **kwargs: Any) -> dict:
        """List available TTS voices."""
        from core.audio import list_voices

        voices = list_voices()
        return {"success": True, "voices": voices, "count": len(voices), "output": voices}

    # -------------------------------------------------------------------
    # Neuralis Brain actions (v18.0 — fleet-wide shared memory)
    # -------------------------------------------------------------------

    def _brain_think(self, *, content: str, region: str = "knowledge", **kwargs: Any) -> dict:
        """Persist a thought to the Neuralis Brain (auto-write, no gate)."""
        from core import brain

        try:
            result = brain.think(content=content, region=region, source="sentinel-desktop")
            neuron_id = result.get("neuron", {}).get("id")
            return {
                "success": True,
                "output": f"Stored in brain (neuron {neuron_id})",
                "neuron_id": neuron_id,
                "op": "brain_think",
            }
        except brain.BrainUnavailableError:
            return {
                "success": False,
                "error": "brain_unavailable",
                "output": "Brain API unreachable (homeserver:8000).",
            }
        except brain.BrainError as exc:
            return {"success": False, "error": "brain_error", "output": str(exc)}

    def _brain_recall(self, *, context: str, **kwargs: Any) -> dict:
        """Retrieve the most relevant thoughts from the fleet brain."""
        from core import brain

        try:
            result = brain.recall(context=context)
            direct = result.get("direct", [])
            associated = result.get("associated", [])
            total = len(direct) + len(associated)
            return {
                "success": True,
                "output": result,
                "count": total,
                "op": "brain_recall",
            }
        except brain.BrainUnavailableError:
            return {
                "success": False,
                "error": "brain_unavailable",
                "output": "Brain API unreachable (homeserver:8000).",
            }
        except brain.BrainError as exc:
            return {"success": False, "error": "brain_error", "output": str(exc)}

    def _brain_search(self, *, q: str, **kwargs: Any) -> dict:
        """Free-text search across all neurons in the fleet brain."""
        from core import brain

        try:
            result = brain.search(q=q)
            count = result.get("count", len(result.get("results", [])))
            return {
                "success": True,
                "output": result,
                "count": count,
                "op": "brain_search",
            }
        except brain.BrainUnavailableError:
            return {
                "success": False,
                "error": "brain_unavailable",
                "output": "Brain API unreachable (homeserver:8000).",
            }
        except brain.BrainError as exc:
            return {"success": False, "error": "brain_error", "output": str(exc)}

    def _brain_stats(self, **kwargs: Any) -> dict:
        """Return fleet brain health stats."""
        from core import brain

        try:
            result = brain.stats()
            totals = result.get("totals", {})
            return {
                "success": True,
                "output": result,
                "neurons": totals.get("neurons", 0),
                "synapses": totals.get("synapses", 0),
                "op": "brain_stats",
            }
        except brain.BrainUnavailableError:
            return {
                "success": False,
                "error": "brain_unavailable",
                "output": "Brain API unreachable (homeserver:8000).",
            }
        except brain.BrainError as exc:
            return {"success": False, "error": "brain_error", "output": str(exc)}

    def _brain_fire(self, *, neuron_id: int, **kwargs: Any) -> dict:
        """Fire (reinforce) a neuron by ID."""
        from core import brain

        try:
            result = brain.fire(neuron_id=neuron_id)
            return {
                "success": True,
                "output": result,
                "neuron_id": neuron_id,
                "op": "brain_fire",
            }
        except brain.BrainUnavailableError:
            return {
                "success": False,
                "error": "brain_unavailable",
                "output": "Brain API unreachable (homeserver:8000).",
            }
        except brain.BrainError as exc:
            return {"success": False, "error": "brain_error", "output": str(exc)}

    # ------------------------------------------------------------------
    # Cost tracker (v21.0)
    # ------------------------------------------------------------------

    def _cost_summary(self, **kwargs: Any) -> dict:
        """Return LLM token and dollar usage for the current session."""
        from core.cost_tracker import get_cost_tracker

        summary = get_cost_tracker().session_summary()
        return {"success": True, "output": summary, **summary}

    def _cost_history(self, *, limit: int = 50, **kwargs: Any) -> dict:
        """Return recent LLM usage records from persisted history."""
        from core.cost_tracker import get_cost_tracker

        records = get_cost_tracker().history(limit=int(limit))
        return {"success": True, "output": records, "count": len(records)}

    def _cost_reset(self, **kwargs: Any) -> dict:
        """Clear in-memory session cost counters."""
        from core.cost_tracker import get_cost_tracker

        get_cost_tracker().reset_session()
        return {"success": True, "output": "Session cost counters reset."}

    # ------------------------------------------------------------------
    # Eval harness (v21.0)
    # ------------------------------------------------------------------

    def _eval_list(self, **kwargs: Any) -> dict:
        """List available evaluation scenarios."""
        from eval.registry import EvalRegistry

        registry = EvalRegistry()
        names = registry.list_scenarios()
        return {"success": True, "output": names, "count": len(names)}

    def _eval_run(self, *, name: str, stop_on_failure: bool = False, **kwargs: Any) -> dict:
        """Run an evaluation scenario by name and return the result.

        Args:
            name: Scenario name (file stem under eval/scenarios/).
            stop_on_failure: Abort after the first failing step.
        """
        from eval.registry import EvalRegistry
        from eval.runner import ScenarioRunner

        registry = EvalRegistry()
        try:
            scenario = registry.load(name)
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}

        def _exec(action: str, **params: Any) -> dict[str, Any]:
            return self.execute_sync({"action": action, **params})

        runner = ScenarioRunner(_exec, stop_on_failure=bool(stop_on_failure))
        result = runner.run(scenario)
        registry.save_result(result)
        comparison = registry.compare_to_baseline(result)
        return {
            "success": True,
            "output": result.to_dict(),
            "score": result.score,
            "passed": result.passed,
            "steps_passed": result.steps_passed,
            "steps_total": result.steps_total,
            "regression": comparison.get("regression", False),
            "score_delta": comparison.get("score_delta"),
        }

    def _eval_results(self, *, name: str, limit: int = 10, **kwargs: Any) -> dict:
        """Return recent run results for a scenario."""
        from eval.registry import EvalRegistry

        registry = EvalRegistry()
        records = registry.list_results(name, limit=int(limit))
        return {"success": True, "output": records, "count": len(records)}

    # ------------------------------------------------------------------
    # Skill marketplace (v21.0)
    # ------------------------------------------------------------------

    def _skill_list(self, *, category: str | None = None, **kwargs: Any) -> dict:
        """List installed skills, optionally filtered by category."""
        from core.skill_marketplace import get_marketplace

        skills = get_marketplace().list_skills(category=category)
        return {
            "success": True,
            "output": [s.to_dict() for s in skills],
            "count": len(skills),
        }

    def _skill_search(self, *, query: str, **kwargs: Any) -> dict:
        """Search installed skills by name, description, or tags."""
        from core.skill_marketplace import get_marketplace

        skills = get_marketplace().find_skills(query)
        return {
            "success": True,
            "output": [s.to_dict() for s in skills],
            "count": len(skills),
        }

    def _skill_install(
        self,
        *,
        params: SkillInstallParams | None = None,
        **kwargs: Any,
    ) -> dict:
        """Install a skill into the local marketplace.

        Args:
            params: SkillInstallParams containing installation parameters:
                name (str) — Unique skill identifier.
                description (str) — Short human-readable description.
                script (dict | None) — Automation script dict (ScriptEngine format).
                version (str) — Semantic version string.
                author (str) — Author name.
                category (str) — Skill category.
                tags (list | None) — Searchable tags.
        """
        from core.skill_marketplace import SkillManifest, get_marketplace

        params = params or SkillInstallParams(name="", description="")

        if params.script is None:
            return {"success": False, "error": "skill_install requires 'script'"}

        manifest = SkillManifest(
            name=params.name,
            description=params.description,
            version=params.version,
            author=params.author,
            category=params.category,
            tags=params.tags or [],
        )
        try:
            skill_dir = get_marketplace().install_skill(manifest, script=params.script)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "output": f"Skill '{params.name}' installed → {skill_dir}",
            "skill_dir": str(skill_dir),
        }

    def _skill_get(self, *, name: str, **kwargs: Any) -> dict:
        """Retrieve a skill's manifest and script by name."""
        from core.skill_marketplace import get_marketplace

        try:
            manifest, script = get_marketplace().get_skill(name)
            return {
                "success": True,
                "output": {"manifest": manifest.to_dict(), "script": script},
                "manifest": manifest.to_dict(),
            }
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

    def _skill_export(self, *, name: str, **kwargs: Any) -> dict:
        """Export a skill as a portable dict (manifest + script)."""
        from core.skill_marketplace import get_marketplace

        try:
            bundle = get_marketplace().export_skill(name)
            return {"success": True, "output": bundle}
        except (FileNotFoundError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

    def _skill_uninstall(self, *, name: str, **kwargs: Any) -> dict:
        """Remove an installed skill by name."""
        from core.skill_marketplace import get_marketplace

        try:
            removed = get_marketplace().uninstall_skill(name)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        if removed:
            return {"success": True, "output": f"Skill '{name}' uninstalled."}
        return {"success": False, "error": f"Skill '{name}' not found."}

    def _skill_run(self, *, name: str, params: dict | None = None, **kwargs: Any) -> dict:
        """Run an installed skill through the ScriptEngine.

        Args:
            name: Installed skill name.
            params: Template substitution parameters for the script.
        """
        from core.script_engine import ScriptEngine
        from core.skill_marketplace import get_marketplace

        try:
            _, script = get_marketplace().get_skill(name)
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}

        engine = ScriptEngine(self)
        result = engine.run_script_from_dict(script, params=params or {})
        return {
            "success": result.success,
            "output": {
                "steps_completed": result.steps_completed,
                "steps_total": result.steps_total,
                "duration_ms": result.duration_ms,
            },
            "error": result.error,
        }

    # ------------------------------------------------------------------
    # Triggers (v22.0)
    # ------------------------------------------------------------------

    def _trigger_add(
        self,
        *,
        name: str,
        event_type: str,
        condition: dict | None = None,
        action: dict | None = None,
        description: str = "",
        **kwargs: Any,
    ) -> dict:
        """Register a new event trigger.

        Args:
            name:        Human-readable trigger name.
            event_type:  One of spoken_keyword, file_change, process_start,
                         process_stop, schedule, custom.
            condition:   Event-type-specific matching criteria.
            action:      Executor action payload to fire when triggered.
            description: Optional description.
        """
        from core.triggers import EventType, Trigger, get_trigger_registry

        try:
            et = EventType(event_type)
        except ValueError:
            valid = [e.value for e in EventType]
            return {"success": False, "error": f"Unknown event_type. Valid: {valid}"}

        t = Trigger(
            name=name,
            event_type=et,
            condition=condition or {},
            action=action or {},
            description=description,
        )
        get_trigger_registry().add(t)
        return {"success": True, "output": t.to_dict(), "id": t.id}

    def _trigger_remove(self, *, id: str, **kwargs: Any) -> dict:  # noqa: A002
        """Remove a trigger by ID."""
        from core.triggers import get_trigger_registry

        removed = get_trigger_registry().remove(id)
        if removed:
            return {"success": True, "output": f"Trigger '{id}' removed."}
        return {"success": False, "error": f"Trigger '{id}' not found."}

    def _trigger_list(self, **kwargs: Any) -> dict:
        """List all registered triggers."""
        from core.triggers import get_trigger_registry

        triggers = get_trigger_registry().list_all()
        return {
            "success": True,
            "output": [t.to_dict() for t in triggers],
            "count": len(triggers),
        }

    def _trigger_enable(self, *, id: str, **kwargs: Any) -> dict:  # noqa: A002
        """Enable a trigger by ID."""
        from core.triggers import get_trigger_registry

        ok = get_trigger_registry().enable(id)
        if ok:
            return {"success": True, "output": f"Trigger '{id}' enabled."}
        return {"success": False, "error": f"Trigger '{id}' not found."}

    def _trigger_disable(self, *, id: str, **kwargs: Any) -> dict:  # noqa: A002
        """Disable a trigger by ID."""
        from core.triggers import get_trigger_registry

        ok = get_trigger_registry().disable(id)
        if ok:
            return {"success": True, "output": f"Trigger '{id}' disabled."}
        return {"success": False, "error": f"Trigger '{id}' not found."}

    def _trigger_fire_custom(self, *, event_name: str, **kwargs: Any) -> dict:
        """Queue a named custom event in the TriggerEngine."""
        from core.triggers import get_trigger_engine

        engine = get_trigger_engine(executor_fn=lambda a: self.execute_sync(a))
        if not engine.running:
            engine.start()
        engine.fire_custom(event_name)
        return {"success": True, "output": f"Custom event '{event_name}' queued."}

    # ------------------------------------------------------------------
    # Voice engine (v22.0)
    # ------------------------------------------------------------------

    def _voice_start_ambient(self, *, wake_word: str = "sentinel", **kwargs: Any) -> dict:
        """Start background wake-word listening.

        Args:
            wake_word: Keyword/phrase to detect (case-insensitive, default "sentinel").
        """
        from core.voice import get_voice_engine

        engine = get_voice_engine()
        engine.wake_word = wake_word.lower()
        started = engine.start_ambient()
        if started:
            return {
                "success": True,
                "output": f"Ambient listening started (wake_word={wake_word!r}).",
            }
        return {"success": False, "output": "Ambient mode already running."}

    def _voice_stop_ambient(self, **kwargs: Any) -> dict:
        """Stop background wake-word listening."""
        from core.voice import get_voice_engine

        stopped = get_voice_engine().stop_ambient()
        if stopped:
            return {"success": True, "output": "Ambient listening stopped."}
        return {"success": False, "output": "Ambient mode was not running."}

    def _voice_status(self, **kwargs: Any) -> dict:
        """Return current voice engine state."""
        from core.voice import get_voice_engine

        status = get_voice_engine().status()
        return {"success": True, "output": status, **status}

    # Dispatch table (v18): derived from the action registry
    # (core/action_registry.py). Each entry is an unbound handler function;
    # callers pass ``self`` explicitly. The mapping below is the registration
    # seed — handlers register their canonical name plus aliases. Future
    # versions add actions with @register_action instead of editing this table.
    _dispatch_table: dict[str, Callable] = _build_dispatch_table(
        click=_click,
        double_click=_click,
        right_click=_click,
        click_text=_click_text,
        click_image=_click_image,
        click_control=_click_control,
        click_element=_click_element,
        click_mark=_click_mark,
        list_controls=_list_controls,
        list_elements=_list_elements,
        web_open=_web_open,
        web_click=_web_click,
        web_type=_web_type,
        web_read=_web_read,
        web_extract=_web_extract,
        web_wait_for=_web_wait_for,
        web_screenshot=_web_screenshot,
        web_eval_js=_web_eval_js,
        web_download=_web_download,
        web_upload=_web_upload,
        web_tabs=_web_tabs,
        # Netops (v9.0)
        ssh_connect=_ssh_connect,
        ssh_disconnect=_ssh_disconnect,
        ssh_run=_ssh_run,
        ssh_show=_ssh_show,
        ssh_ping=_ssh_ping,
        ssh_traceroute=_ssh_traceroute,
        # Memory (v11.0)
        memory_store=_memory_store,
        memory_recall=_memory_recall,
        memory_search=_memory_search,
        memory_forget=_memory_forget,
        # Conductor (v12.0)
        conductor_run=_conductor_run_sync,
        set_text=_set_text,
        read_text=_read_text,
        read_window=_read_window,
        type_text=_type_text,
        press_key=_press_key,
        hotkey=_hotkey,
        scroll=_scroll,
        mouse_move=_mouse_move,
        drag=_drag,
        screenshot=_screenshot,
        find_image=_find_image,
        wait=_wait,
        wait_for_image=_wait_for_image,
        smart_wait=_smart_wait,
        wait_for_stable=_wait_for_stable,
        wait_for_text=_wait_for_text,
        open_app=_open_app,
        smart_open=_smart_open,
        close_app=_close_app,
        focus_window=_focus_window,
        close_window=_close_window,
        list_windows=_list_windows,
        read_file=_read_file,
        write_file=_write_file,
        list_directory=_list_directory,
        # File Operations Plus (v13.0)
        delete_file=_delete_file,
        move_file=_move_file,
        copy_file=_copy_file,
        mkdir=_mkdir,
        stat_file=_stat_file,
        find_files=_find_files,
        archive_create=_archive_create,
        archive_extract=_archive_extract,
        # Process & Service Control (v13.0)
        set_priority=_set_priority,
        get_env=_get_env,
        set_env=_set_env,
        service_control=_service_control,
        # Credential Vault (v13.0)
        cred_store=_cred_store,
        cred_read=_cred_read,
        # Registry (v13.0)
        registry_read=_registry_read,
        registry_write=_registry_write,
        registry_delete=_registry_delete,
        clipboard_read=_clipboard_read,
        clipboard_write=_clipboard_write,
        system_info=_system_info,
        list_processes=_list_processes,
        start_process=_start_process,
        kill_process=_kill_process,
        note=_note,
        finish=_finish,
        powershell=_powershell,
        run_script=_run_script,
        # Resilience (v14.0)
        retry_last=_retry_last,
        get_circuit_breakers=_get_circuit_breakers,
        # Config (v15.0)
        config_get=_config_get,
        config_set=_config_set,
        # Network diagnostics (v15.0)
        dns_lookup=_dns_lookup,
        ping=_ping,
        port_scan=_port_scan,
        # Window management (v16.0)
        resize_window=_resize_window,
        move_window=_move_window,
        minimize_window=_minimize_window,
        maximize_window=_maximize_window,
        restore_window=_restore_window,
        get_window_state=_get_window_state,
        get_monitors=_get_monitors,
        # HTTP client (v16.0)
        http_get=_http_get,
        http_post=_http_post,
        http_download=_http_download,
        # File / process monitoring (v16.0)
        watch_file=_watch_file,
        watch_file_content=_watch_file_content,
        watch_process=_watch_process,
        # Audio / voice (v17.0)
        speak=_speak,
        listen=_listen,
        volume_get=_volume_get,
        volume_set=_volume_set,
        mute_toggle=_mute_toggle,
        list_voices=_list_voices,
        # Neuralis Brain (fleet-wide shared memory)
        brain_think=_brain_think,
        brain_recall=_brain_recall,
        brain_search=_brain_search,
        brain_stats=_brain_stats,
        brain_fire=_brain_fire,
        # v21 — cost tracker
        cost_summary=_cost_summary,
        cost_history=_cost_history,
        cost_reset=_cost_reset,
        # v21 — eval harness
        eval_list=_eval_list,
        eval_run=_eval_run,
        eval_results=_eval_results,
        # v21 — skill marketplace
        skill_list=_skill_list,
        skill_search=_skill_search,
        skill_install=_skill_install,
        skill_get=_skill_get,
        skill_export=_skill_export,
        skill_uninstall=_skill_uninstall,
        skill_run=_skill_run,
        # v22 — triggers
        trigger_add=_trigger_add,
        trigger_remove=_trigger_remove,
        trigger_list=_trigger_list,
        trigger_enable=_trigger_enable,
        trigger_disable=_trigger_disable,
        trigger_fire_custom=_trigger_fire_custom,
        # v22 — voice engine
        voice_start_ambient=_voice_start_ambient,
        voice_stop_ambient=_voice_stop_ambient,
        voice_status=_voice_status,
    )


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


def _apply_attention_pause(action_context: str) -> None:
    """Apply attention pause for StealthProfile before an action.

    This is called before clicks, typing, and other actions to simulate
    human-like gaze patterns and hesitation. Only active for StealthProfile.

    Args:
        action_context: Human-readable description of the action (e.g.,
            "clicking_submit_button", "typing_password"). Used for context-aware
            pause probability.
    """
    try:
        from core.humanize import attention
        from core.humanize.profile import get_default_profile

        profile = get_default_profile()
        pause_duration = attention.attention_pause(
            action_context,
            rng=attention.rng.get_rng()
            if hasattr(attention, "rng")
            else __import__("random").Random(),
            profile=profile,
        )
        if pause_duration > 0:
            import time

            time.sleep(pause_duration)
    except Exception:  # noqa: BLE001
        # Attention pause is optional; never let it break an action
        pass


def _apply_re_read_pause(field_type: str) -> None:
    """Apply re-read pause for StealthProfile before typing.

    This is called before typing into sensitive fields to simulate
    operators double-checking their input. Only active for StealthProfile.

    Args:
        field_type: Type of field being typed into (e.g., "email", "password",
            "username"). Used for context-aware pause probability.
    """
    try:
        from core.humanize import attention
        from core.humanize.profile import get_default_profile

        profile = get_default_profile()
        pause_duration = attention.re_read_pause(
            field_type,
            rng=attention.rng.get_rng()
            if hasattr(attention, "rng")
            else __import__("random").Random(),
            profile=profile,
        )
        if pause_duration > 0:
            import time

            time.sleep(pause_duration)
    except Exception:  # noqa: BLE001
        # Re-read pause is optional; never let it break an action
        pass
