"""
Sentinel Desktop v2 — UIA-first action pipeline for non-interrupting desktop control.

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
    except Exception as exc:
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
    except Exception as exc:
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
        # Lazy-import heavy modules at first use (done in _probe_* above).
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _uia_ok() -> bool:
        return _probe_uia()

    @staticmethod
    def _postmessage_ok() -> bool:
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
        # --- Tier 1: UIA ---
        if self._uia_ok():
            try:
                from core.ui_tree import click_control

                result = click_control(
                    name=name,
                    control_type=control_type,
                    window_title=window_title,
                    button=button,
                )
                if result is not None:
                    return _result(True, {"x": result[0], "y": result[1]}, "uia")
            except Exception as exc:
                logger.debug("UIA click_element failed: %s", exc)

        # --- Tier 2: PostMessage at element centre ---
        if self._postmessage_ok():
            try:
                bounds = self._uia_bounds(name, control_type, window_title)
                if bounds is not None:
                    from core.stealth_input import post_click

                    ok = post_click(bounds["center_x"], bounds["center_y"], button=button)
                    if ok:
                        return _result(
                            True,
                            {"x": bounds["center_x"], "y": bounds["center_y"]},
                            "postmessage",
                        )
            except Exception as exc:
                logger.debug("PostMessage click_element failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            bounds = self._uia_bounds(name, control_type, window_title)
            if bounds is not None:
                self._get_physical_desktop().click(
                    bounds["center_x"],
                    bounds["center_y"],
                    button=button,
                )
                return _result(
                    True,
                    {"x": bounds["center_x"], "y": bounds["center_y"]},
                    "physical",
                )
        except Exception as exc:
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
            except Exception as exc:
                logger.debug("UIA type_into_field failed: %s", exc)

        # --- Tier 2: PostMessage WM_CHAR ---
        if self._postmessage_ok():
            try:
                hwnd = self._hwnd_for_element(name, window_title)
                if hwnd is not None:
                    from core.stealth_input import post_text

                    if post_text(text, hwnd=hwnd):
                        return _result(True, text, "postmessage")
            except Exception as exc:
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
        except Exception as exc:
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

        # --- Tier 1: UIA menu traversal ---
        if self._uia_ok():
            try:
                result = self._uia_menu_walk(segments, window_title)
                if result:
                    return _result(True, path, "uia")
            except Exception as exc:
                logger.debug("UIA select_menu_item failed: %s", exc)

        # --- Tier 2: PostMessage (limited — try to invoke menu via Alt+letter) ---
        if self._postmessage_ok():
            try:
                from core.stealth_input import post_hotkey

                # Press Alt to activate menu bar, then arrow down through items.
                # This is a best-effort approach; PostMessage menus are fragile.
                if post_hotkey(["alt"], hwnd=None):
                    time.sleep(0.1)
                    # We can't reliably navigate menus via PostMessage alone,
                    # so fall through to physical.
            except Exception as exc:
                logger.debug("PostMessage select_menu_item failed: %s", exc)

        # --- Tier 3: pyautogui fallback ---
        try:
            import pyautogui

            self._get_physical_desktop()
            # Press Alt to activate the menu bar, then navigate with arrows.
            pyautogui.press("alt")
            time.sleep(0.1)
            for segment in segments:
                # Try pressing the first letter of each segment for mnemonic match.
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
        except Exception as exc:
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
            except Exception as exc:
                logger.debug("PostMessage click_at failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().click(x, y, button=button, clicks=clicks)
            return _result(True, {"x": x, "y": y}, "physical")
        except Exception as exc:
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
            except Exception as exc:
                logger.debug("PostMessage type_text failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().type_text(text)
            return _result(True, text, "physical")
        except Exception as exc:
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
            except Exception as exc:
                logger.debug("PostMessage press_key failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().press_key(key)
            return _result(True, key, "physical")
        except Exception as exc:
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
            except Exception as exc:
                logger.debug("PostMessage hotkey failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().hotkey(*keys)
            return _result(True, list(keys), "physical")
        except Exception as exc:
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
            except Exception as exc:
                logger.debug("PostMessage scroll_at failed: %s", exc)

        # --- Tier 3: pyautogui ---
        try:
            self._get_physical_desktop().scroll(amount, x=x, y=y)
            return _result(
                True,
                {"x": x, "y": y, "amount": amount},
                "physical",
            )
        except Exception as exc:
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
            except Exception as exc:
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
            except Exception as exc:
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
        except Exception as exc:
            logger.debug("_control_to_dict failed: %s", exc)
            return {"name": getattr(ctrl, "Name", ""), "error": str(exc)}

    @staticmethod
    def _uia_bounds(
        name: str,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> dict[str, Any] | None:
        """Try to get bounding rectangle for a named control via UIA."""
        if not _probe_uia():
            return None
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
            return {
                "x": int(rect.left),
                "y": int(rect.top),
                "width": int(rect.right - rect.left),
                "height": int(rect.bottom - rect.top),
                "center_x": (rect.left + rect.right) // 2,
                "center_y": (rect.top + rect.bottom) // 2,
            }
        except Exception:
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
        except Exception:
            pass
        return None

    def _uia_menu_walk(
        self,
        segments: list[str],
        window_title: str | None = None,
    ) -> bool:
        """Walk a menu path via UIA, expanding / invoking each segment.

        Returns True if the full path was traversed successfully.
        """
        if _auto is None:
            return False
        try:
            from core.ui_tree import _find_window

            root = _find_window(window_title)
            if root is None:
                return False

            # Find the top-level menu bar.
            menu_bar = None
            for child in root.GetChildren():
                if child.ControlTypeName == "MenuBarControl":
                    menu_bar = child
                    break
            if menu_bar is None:
                # Some apps use a generic "menu" control type.
                for child in root.GetChildren():
                    ct = (child.ControlTypeName or "").lower()
                    if "menu" in ct:
                        menu_bar = child
                        break
            if menu_bar is None:
                return False

            current = menu_bar
            for i, segment in enumerate(segments):
                is_last = i == len(segments) - 1
                target = self._find_child_by_name(current, segment)
                if target is None:
                    return False

                if is_last:
                    # Invoke / click the final menu item.
                    try:
                        pattern = target.GetInvokePattern()
                        if pattern:
                            pattern.Invoke()
                            return True
                    except Exception:
                        pass
                    try:
                        target.Click(simulateMove=False)
                        return True
                    except Exception:
                        pass
                    return False
                else:
                    # Intermediate item — expand to reveal submenu.
                    try:
                        expand = target.GetExpandCollapsePattern()
                        if expand:
                            expand.Expand()
                            time.sleep(0.05)
                            current = target
                            continue
                    except Exception:
                        pass
                    # Fallback: click to open submenu.
                    try:
                        target.Click(simulateMove=False)
                        time.sleep(0.05)
                        current = target
                    except Exception:
                        return False

            return False  # shouldn't reach here
        except Exception as exc:
            logger.debug("_uia_menu_walk failed: %s", exc)
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
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------

pipeline = UIAActionPipeline()
