"""Sentinel Desktop v2 — UIA-first action pipeline for non-interrupting desktop control.

Provides a three-tier fallback strategy for every user action:

1. **UIA** — direct accessibility-tree manipulation via InvokePattern,
   ValuePattern, SelectionItemPattern, ExpandCollapsePattern, etc.
   No cursor movement, no real keystrokes.
2. **PostMessage** — window messages (WM_LBUTTONDOWN, WM_CHAR, WM_KEYDOWN,
   WM_VSCROLL, …) sent to specific HWNDs. Cursor stays put.
3. **pyautogui** — physical input. Last resort when the above fail.

Each public method returns ``{success: bool, output: Any, method_used: str}``
where *method_used* is one of ``"uia"``, ``"postmessage"``, or ``"physical"``.

Graceful degradation
--------------------
If ``uiautomation`` is not installed, tier 1 is skipped.
If ``win32gui`` / ``win32api`` are unavailable, tier 2 is skipped.
Tier 3 (pyautogui) is always available.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Short-lived bounds cache: (name, control_type, window_title) → (bounds_dict, timestamp)
# TTL is very short (0.5 s) — enough to avoid duplicate BFS walks within a single
# action sequence but short enough that stale entries don't survive UI transitions.
_bounds_cache: dict[tuple[str | None, ...], tuple[dict[str, Any], float]] = {}
_BOUNDS_CACHE_TTL = 0.5  # seconds

# ---------------------------------------------------------------------------
# Availability probes
# ---------------------------------------------------------------------------

_UIA_AVAILABLE: bool | None = None
_auto = None  # uiautomation module ref


def _probe_uia() -> bool:
    """Return True when the *uiautomation* package can be imported."""
    global _UIA_AVAILABLE, _auto
    if _UIA_AVAILABLE is not None:
        return _UIA_AVAILABLE
    try:
        import uiautomation as auto  # type: ignore

        _auto = auto
        _UIA_AVAILABLE = True
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        logger.info("UIA tier disabled — uiautomation not available (%s)", exc)
        _UIA_AVAILABLE = False
    return bool(_UIA_AVAILABLE)


_POSTMESSAGE_AVAILABLE: bool | None = None
_win32gui = None
_win32api = None
_win32con = None


def _probe_postmessage() -> bool:
    """Return True when win32gui/win32api are importable."""
    global _POSTMESSAGE_AVAILABLE, _win32gui, _win32api, _win32con
    if _POSTMESSAGE_AVAILABLE is not None:
        return _POSTMESSAGE_AVAILABLE
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore

        _win32gui = win32gui
        _win32api = win32api
        _win32con = win32con
        _POSTMESSAGE_AVAILABLE = True
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        logger.info("PostMessage tier disabled — win32 not available (%s)", exc)
        _POSTMESSAGE_AVAILABLE = False
    return bool(_POSTMESSAGE_AVAILABLE)


def _result(success: bool, output: Any, method: str) -> dict[str, Any]:
    """Normalised result dict."""
    return {"success": success, "output": output, "method_used": method}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class UIAActionPipeline:
    """Three-tier action pipeline: UIA → PostMessage → pyautogui.

    Import and use a single shared instance, or create your own::

        from core.uia_actions import pipeline
        res = pipeline.click_element("OK")
        print(res["method_used"], res["success"])
    """

    def __init__(self) -> None:
        """Initialize the pipeline. Heavy platform modules are imported lazily."""
        # Lazy-import heavy modules at first use (done in _probe_* above).
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _uia_ok() -> bool:
        """Return ``True`` if Windows UIAutomation is available."""
        return _probe_uia()

    @staticmethod
    def _postmessage_ok() -> bool:
        """Return ``True`` if the PostMessage Win32 API is probeable."""
        return _probe_postmessage()

    def _get_physical_desktop(self) -> Any:
        """Lazy getter for the core.desktop DesktopController."""
        from core.desktop import _get_controller

        return _get_controller()

    # ------------------------------------------------------------------
    # Element-level actions (Tier 1 → 3)
    # ------------------------------------------------------------------

    def click_element(
        self,
        name: str,
        control_type: str | None = None,
        window_title: str | None = None,
        *,
        button: str = "left",
    ) -> dict[str, Any]:
        """Click a control identified by *name* (and optionally *control_type*).

        Tries UIA Invoke / SelectionItem / physical click on the control first,
        then falls back to PostMessage at the control's centre, then pyautogui.
        """
        hit = self._click_element_uia(name, control_type, window_title, button)
        if hit is not None:
            return hit
        hit = self._click_element_postmessage(name, control_type, window_title, button)
        if hit is not None:
            return hit
        return self._click_element_physical(name, control_type, window_title, button)

    def _click_element_uia(
        self,
        name: str,
        control_type: str | None,
        window_title: str | None,
        button: str,
    ) -> dict[str, Any] | None:
        """Tier 1: attempt UIA click; return result dict or None on failure/unavailable."""
        if not self._uia_ok():
            return None
        try:
            from core.ui_tree import click_control

            result = click_control(
                name=name, control_type=control_type, window_title=window_title, button=button
            )
            if result is not None:
                return _result(True, {"x": result[0], "y": result[1]}, "uia")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("UIA click_element failed: %s", exc)
        return None

    def _click_element_postmessage(
        self,
        name: str,
        control_type: str | None,
        window_title: str | None,
        button: str,
    ) -> dict[str, Any] | None:
        """Tier 2: attempt PostMessage click; return result dict or None on failure/unavailable."""
        if not self._postmessage_ok():
            return None
        try:
            bounds = self._uia_bounds(name, control_type, window_title)
            if bounds is not None:
                from core.stealth_input import post_click

                if post_click(
                    bounds["center_x"], bounds["center_y"], button=button
                ):
                    return _result(  # noqa: E501
                        True, {"x": bounds["center_x"], "y": bounds["center_y"]}, "postmessage"
                    )
        except OSError as exc:
            logger.debug("PostMessage click_element failed: %s", exc)
        return None

    def _click_element_physical(
        self,
        name: str,
        control_type: str | None,
        window_title: str | None,
        button: str,
    ) -> dict[str, Any]:
        """Tier 3: attempt pyautogui physical click; returns failure result if element not found."""
        try:
            bounds = self._uia_bounds(name, control_type, window_title)
            if bounds is not None:
                self._get_physical_desktop().click(  # noqa: E501
                    bounds["center_x"], bounds["center_y"], button=button
                )
                return _result(True, {"x": bounds["center_x"], "y": bounds["center_y"]}, "physical")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical click_element failed: %s", exc)
        return _result(False, f"Element '{name}' not found or click failed", "physical")

    def type_into_field(
        self,
        name: str,
        text: str,
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """Set *text* into a named edit/text field.

        Tier 1 uses UIA ValuePattern. Tier 2 falls back to PostMessage WM_CHAR.
        Tier 3 uses pyautogui typing.
        """
        # --- Tier 1: UIA ValuePattern ---
        if self._uia_ok():
            try:
                from core.ui_tree import set_text

                if set_text(text, name=name, window_title=window_title):
                    return _result(True, text, "uia")
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("UIA type_into_field failed: %s", exc)

        # --- Tier 2: PostMessage WM_CHAR ---
        if self._postmessage_ok():
            try:
                hwnd = self._hwnd_for_element(name, window_title)
                if hwnd is not None:
                    from core.stealth_input import post_text

                    if post_text(text, hwnd=hwnd):
                        return _result(True, text, "postmessage")
            except OSError as exc:
                logger.debug("PostMessage type_into_field failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            bounds = self._uia_bounds(name, window_title=window_title)
            if bounds is not None:
                desktop = self._get_physical_desktop()
                desktop.click(bounds["center_x"], bounds["center_y"])
                time.sleep(0.05)
                desktop.type_text(text)
                return _result(True, text, "physical")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical type_into_field failed: %s", exc)

        return _result(False, f"Field '{name}' not found or typing failed", "physical")

    def select_menu_item(
        self,
        path: str,
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """Navigate a menu by *path* like ``"File > Export > Runtime Model"``.

        Uses UIA menu / menuItem traversal. Each segment is matched by name.
        Falls back to physical hotkey/arrow navigation if UIA is unavailable.
        """
        segments = [s.strip() for s in path.split(">") if s.strip()]
        if not segments:
            return _result(False, "Empty menu path", "uia")
        if self._uia_ok() and self._select_menu_uia(segments, window_title):
            return _result(True, path, "uia")
        self._select_menu_postmessage()
        return self._select_menu_physical(segments, path)

    def _select_menu_uia(
        self, segments: list[str], window_title: str | None,
    ) -> bool:
        """Tier 1: UIA menu traversal. Returns True on success."""
        try:
            return bool(self._uia_menu_walk(segments, window_title))
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("UIA select_menu_item failed: %s", exc)
            return False

    def _select_menu_postmessage(self) -> None:
        """Tier 2: press Alt via PostMessage to activate menu bar (best-effort)."""
        if not self._postmessage_ok():
            return
        try:
            from core.stealth_input import post_hotkey

            if post_hotkey(["alt"], hwnd=None):
                time.sleep(0.1)
        except OSError as exc:
            logger.debug("PostMessage select_menu_item failed: %s", exc)

    def _select_menu_physical(
        self, segments: list[str], path: str,
    ) -> dict[str, Any]:
        """Tier 3: pyautogui mnemonic navigation; returns failure result if unavailable."""
        try:
            import pyautogui

            self._get_physical_desktop()
            pyautogui.press("alt")
            time.sleep(0.1)
            for segment in segments:
                first_char = segment[0] if segment else ""
                if first_char.isalpha():
                    pyautogui.press(first_char.lower())
                    time.sleep(0.05)
                else:
                    pyautogui.press("down")
                    time.sleep(0.05)
                pyautogui.press("enter") if segment == segments[-1] else pyautogui.press("right")
                time.sleep(0.05)
            return _result(True, path, "physical")
        except (ImportError, OSError, AttributeError) as exc:
            logger.debug("Physical select_menu_item failed: %s", exc)
        return _result(False, f"Menu path '{path}' not found", "physical")

    # ------------------------------------------------------------------
    # Coordinate-level actions (Tier 2 → 3)
    # ------------------------------------------------------------------

    def click_at(
        self,
        x: int,
        y: int,
        hwnd: int | None = None,
        *,
        button: str = "left",
        clicks: int = 1,
    ) -> dict[str, Any]:
        """Click at screen coordinates (*x*, *y*).

        Tries PostMessage to the HWND under the point first, then pyautogui.
        """
        # --- Tier 2: PostMessage ---
        if self._postmessage_ok():
            try:
                from core.stealth_input import post_click

                if post_click(x, y, button=button, clicks=clicks):
                    return _result(True, {"x": x, "y": y}, "postmessage")
            except OSError as exc:
                logger.debug("PostMessage click_at failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().click(x, y, button=button, clicks=clicks)
            return _result(True, {"x": x, "y": y}, "physical")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical click_at failed: %s", exc)

        return _result(False, f"click_at({x}, {y}) failed", "physical")

    def type_text(
        self,
        text: str,
        hwnd: int | None = None,
    ) -> dict[str, Any]:
        """Type *text* character-by-character.

        Tries PostMessage WM_CHAR first, then pyautogui.
        """
        if not text:
            return _result(False, "Empty text", "postmessage")

        # --- Tier 2: PostMessage ---
        if self._postmessage_ok():
            try:
                from core.stealth_input import post_text

                if post_text(text, hwnd=hwnd):
                    return _result(True, text, "postmessage")
            except OSError as exc:
                logger.debug("PostMessage type_text failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().type_text(text)
            return _result(True, text, "physical")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical type_text failed: %s", exc)

        return _result(False, "type_text failed", "physical")

    def press_key(
        self,
        key: str,
        hwnd: int | None = None,
    ) -> dict[str, Any]:
        """Press a named key (e.g. ``"enter"``, ``"f5"``).

        Tries PostMessage WM_KEYDOWN/UP first, then pyautogui.
        """
        # --- Tier 2: PostMessage ---
        if self._postmessage_ok():
            try:
                from core.stealth_input import post_named_key

                if post_named_key(key, hwnd=hwnd):
                    return _result(True, key, "postmessage")
            except OSError as exc:
                logger.debug("PostMessage press_key failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().press_key(key)
            return _result(True, key, "physical")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical press_key failed: %s", exc)

        return _result(False, f"press_key('{key}') failed", "physical")

    def hotkey(
        self,
        keys: Sequence[str],
        hwnd: int | None = None,
    ) -> dict[str, Any]:
        """Send a chorded hotkey (e.g. ``["ctrl", "c"]``).

        Tries PostMessage WM_KEYDOWN/UP first, then pyautogui.
        """
        if not keys:
            return _result(False, "Empty hotkey", "postmessage")

        # --- Tier 2: PostMessage ---
        if self._postmessage_ok():
            try:
                from core.stealth_input import post_hotkey

                if post_hotkey(keys, hwnd=hwnd):
                    return _result(True, list(keys), "postmessage")
            except OSError as exc:
                logger.debug("PostMessage hotkey failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().hotkey(*keys)
            return _result(True, list(keys), "physical")
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical hotkey failed: %s", exc)

        return _result(False, f"hotkey({keys}) failed", "physical")

    def scroll_at(
        self,
        x: int,
        y: int,
        amount: int,
    ) -> dict[str, Any]:
        """Scroll at (*x*, *y*) by *amount* clicks.

        Positive *amount* scrolls up, negative scrolls down.
        Uses PostMessage WM_VSCROLL first, then pyautogui.
        """
        # --- Tier 2: PostMessage WM_VSCROLL ---
        if self._postmessage_ok():
            try:
                hwnd = _win32gui.WindowFromPoint((int(x), int(y)))
                if hwnd:
                    # WM_VSCROLL parameters
                    if amount > 0:
                        scroll_cmd = _win32con.SB_LINEUP
                    else:
                        scroll_cmd = _win32con.SB_LINEDOWN
                    repeats = abs(amount)
                    for _ in range(max(1, repeats)):
                        _win32api.PostMessage(
                            hwnd,
                            _win32con.WM_VSCROLL,
                            scroll_cmd,
                            0,
                        )
                    return _result(
                        True,
                        {"x": x, "y": y, "amount": amount},
                        "postmessage",
                    )
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("PostMessage scroll_at failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().scroll(amount, x=x, y=y)
            return _result(
                True,
                {"x": x, "y": y, "amount": amount},
                "physical",
            )
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Physical scroll_at failed: %s", exc)

        return _result(False, f"scroll_at({x}, {y}, {amount}) failed", "physical")

    # ------------------------------------------------------------------
    # Read-only / inspection methods (Tier 1 only, no side effects)
    # ------------------------------------------------------------------

    def find_element(
        self,
        name: str,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """Return element info dict for the first matching control.

        Returns ``{success, output, method_used}`` where *output* is the
        element dict or an error string.
        """
        if self._uia_ok():
            try:
                from core.ui_tree import _find_control

                ctrl = _find_control(
                    name=name,
                    control_type=control_type,
                    window_title=window_title,
                )
                if ctrl is not None:
                    info = self._control_to_dict(ctrl)
                    return _result(True, info, "uia")
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("UIA find_element failed: %s", exc)

        return _result(False, f"Element '{name}' not found", "uia")

    def list_controls(
        self,
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """Return all interactive controls in the focused or named window.

        Delegates to ``core.ui_tree.list_controls``.
        """
        if self._uia_ok():
            try:
                from core.ui_tree import list_controls as _list_controls

                controls = _list_controls(window_title)
                return _result(True, controls, "uia")
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("UIA list_controls failed: %s", exc)

        return _result(False, "UIA unavailable or no controls found", "uia")

    def get_element_bounds(
        self,
        name: str,
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """Return ``{x, y, width, height, center_x, center_y}`` for a control.

        Uses UIA bounding rectangle.
        """
        bounds = self._uia_bounds(name, window_title=window_title)
        if bounds is not None:
            return _result(True, bounds, "uia")
        return _result(False, f"Element '{name}' not found", "uia")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _control_to_dict(ctrl: Any) -> dict[str, Any]:
        """Convert a uiautomation Control to an info dict."""
        try:
            rect = ctrl.BoundingRectangle
            return {
                "name": ctrl.Name or "",
                "control_type": ctrl.ControlTypeName,
                "automation_id": getattr(ctrl, "AutomationId", "") or "",
                "class_name": getattr(ctrl, "ClassName", "") or "",
                "x": int(rect.left),
                "y": int(rect.top),
                "width": int(rect.right - rect.left),
                "height": int(rect.bottom - rect.top),
                "center_x": (rect.left + rect.right) // 2,
                "center_y": (rect.top + rect.bottom) // 2,
                "is_enabled": bool(getattr(ctrl, "IsEnabled", True)),
                "is_offscreen": bool(getattr(ctrl, "IsOffscreen", False)),
            }
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("_control_to_dict failed: %s", exc)
            return {"name": getattr(ctrl, "Name", ""), "error": str(exc)}

    @staticmethod
    def _uia_bounds(
        name: str,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> dict[str, Any] | None:
        """Try to get bounding rectangle for a named control via UIA.

        Results are cached for ``_BOUNDS_CACHE_TTL`` seconds to avoid
        redundant BFS walks when the same element is queried multiple times
        in quick succession (e.g. click then type into the same field).
        """
        if not _probe_uia():
            return None
        cache_key = (name, control_type, window_title)
        cached, ts = _bounds_cache.get(cache_key, (None, 0.0))
        if cached is not None and (time.monotonic() - ts) < _BOUNDS_CACHE_TTL:
            return cached
        try:
            from core.ui_tree import _find_control

            ctrl = _find_control(
                name=name,
                control_type=control_type,
                window_title=window_title,
            )
            if ctrl is None:
                return None
            rect = ctrl.BoundingRectangle
            bounds = {
                "x": int(rect.left),
                "y": int(rect.top),
                "width": int(rect.right - rect.left),
                "height": int(rect.bottom - rect.top),
                "center_x": (rect.left + rect.right) // 2,
                "center_y": (rect.top + rect.bottom) // 2,
            }
            _bounds_cache[cache_key] = (bounds, time.monotonic())
            return bounds
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Bounding box lookup failed: %s", exc)
            return None

    @staticmethod
    def _hwnd_for_element(
        name: str,
        window_title: str | None = None,
    ) -> int | None:
        """Best-effort: find the HWND of the native window containing an element."""
        if not _probe_postmessage():
            return None
        try:
            bounds = UIAActionPipeline._uia_bounds(name, window_title=window_title)
            if bounds is not None:
                hwnd = _win32gui.WindowFromPoint(
                    (bounds["center_x"], bounds["center_y"]),
                )
                return int(hwnd) if hwnd else None
        except OSError as exc:
            logger.debug("_uia_hwnd fallback failed: %s", exc)
        return None

    def _uia_menu_walk(
        self,
        segments: list[str],
        window_title: str | None = None,
    ) -> bool:
        """Walk a menu path via UIA, expanding / invoking each segment.

        Returns True if the full path was traversed successfully.
        """
        result = False

        if _auto is not None:
            try:
                from core.ui_tree import _find_window

                root = _find_window(window_title)
                if root is not None:
                    menu_bar = self._find_menu_bar(root)
                    if menu_bar is not None:
                        current = menu_bar
                        for i, segment in enumerate(segments):
                            target = self._find_child_by_name(current, segment)
                            if target is None:
                                result = False
                                break
                            if i == len(segments) - 1:
                                result = self._invoke_menu_item(target)
                                break
                            if not self._expand_menu_item(target):
                                result = False
                                break
                            current = target
                        else:
                            # Loop completed without hitting a break
                            result = False  # shouldn't reach here
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("_uia_menu_walk failed: %s", exc)
                result = False

        return result

    @staticmethod
    def _find_menu_bar(root: Any) -> Any | None:
        """Find the top-level menu bar control in *root*'s children."""
        for child in root.GetChildren():
            if child.ControlTypeName == "MenuBarControl":
                return child
        for child in root.GetChildren():
            if "menu" in (child.ControlTypeName or "").lower():
                return child
        return None

    @staticmethod
    def _invoke_menu_item(target: Any) -> bool:
        """Invoke or click a final menu item. Returns True on success."""
        try:
            pattern = target.GetInvokePattern()
            if pattern:
                pattern.Invoke()
                return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Invoke pattern failed, trying click: %s", exc)
        try:
            target.Click(simulateMove=False)
            return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Click fallback failed: %s", exc)
        return False

    @staticmethod
    def _expand_menu_item(target: Any) -> bool:
        """Expand or click an intermediate menu item. Returns True on success."""
        try:
            expand = target.GetExpandCollapsePattern()
            if expand:
                expand.Expand()
                time.sleep(0.05)
                return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Expand pattern failed, trying click: %s", exc)
        try:
            target.Click(simulateMove=False)
            time.sleep(0.05)
            return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Menu walk click fallback failed: %s", exc)
        return False

    @staticmethod
    def _find_child_by_name(parent: Any, name: str) -> Any | None:
        """Find the first direct child whose Name matches *name*."""
        needle = name.lower()
        try:
            for child in parent.GetChildren():
                if (child.Name or "").lower() == needle:
                    return child
                if needle in (child.Name or "").lower():
                    return child
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("_find_child_by_name failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------

pipeline = UIAActionPipeline()
