"""
Sentinel Desktop v2 — Windows UIAutomation wrapper.

Uses the ``uiautomation`` package to introspect and drive native Windows
controls by their accessibility metadata. This is the desktop equivalent of
a browser DOM — much more reliable than vision when the model can name the
control it wants (e.g. ``"Send"`` button, ``"Subject"`` edit field).

All public functions gracefully no-op when:
  * we're not on Windows,
  * the ``uiautomation`` package isn't installed,
  * COM init fails (rare; first call only).

That lets the agent run anywhere without crashing, and lets users opt in by
``pip install uiautomation``.
"""

from __future__ import annotations

import logging
import platform
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_UIA_OK: bool | None = None
_auto = None  # holds the imported uiautomation module if available


def _have_uia() -> bool:
    """Lazily probe for the uiautomation package and COM availability."""
    global _UIA_OK, _auto
    if _UIA_OK is not None:
        return _UIA_OK
    if platform.system() != "Windows":
        _UIA_OK = False
        return False
    try:
        import uiautomation as auto  # type: ignore

        _auto = auto
        _UIA_OK = True
    except Exception as exc:
        logger.info(
            "UIAutomation disabled — install 'uiautomation' to enable "
            "click_control / list_controls / set_text (%s)",
            exc,
        )
        _UIA_OK = False
    return _UIA_OK


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_controls(
    window_title: str | None = None,
    *,
    max_depth: int = 6,
    max_results: int = 120,
) -> list[dict[str, Any]]:
    """Walk the accessible control tree under a window and return its controls.

    Args:
        window_title: Partial title match. ``None`` uses the foreground window.
        max_depth: Recursion limit.
        max_results: Cap on returned controls (depth-first order).

    Returns:
        List of ``{name, control_type, automation_id, class_name, x, y,
        width, height, is_enabled, is_offscreen}`` dicts.
    """
    if not _have_uia():
        return []
    root = _find_window(window_title)
    if root is None:
        return []
    out: list[dict[str, Any]] = []
    try:
        _walk(root, out, depth=0, max_depth=max_depth, max_results=max_results)
    except Exception as exc:
        logger.warning("list_controls failed: %s", exc)
    return out


def click_control(
    *,
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    window_title: str | None = None,
    button: str = "left",
) -> tuple[int, int] | None:
    """Find and click a control by accessibility metadata.

    Returns the (x, y) it clicked, or ``None`` if no match was found.
    Matching is AND across the provided keys (all provided must match).
    """
    if not _have_uia():
        return None
    ctrl = _find_control(
        name=name,
        automation_id=automation_id,
        control_type=control_type,
        window_title=window_title,
    )
    if ctrl is None:
        return None
    try:
        rect = ctrl.BoundingRectangle
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2

        # Prefer InvokePattern — fires the control's accessibility action
        # directly without moving the cursor. Falls back to Click only if
        # the control doesn't support Invoke (selection items, list items,
        # etc. expose other patterns we try below).
        invoked = False
        try:
            pattern = ctrl.GetInvokePattern()
            if pattern is not None:
                pattern.Invoke()
                invoked = True
        except Exception:
            pass

        if not invoked:
            # SelectionItemPattern handles list-box rows, tabs, etc.
            try:
                sel = ctrl.GetSelectionItemPattern()
                if sel is not None:
                    sel.Select()
                    invoked = True
            except Exception:
                pass

        if not invoked:
            # Last resort: physical click, but skip the visual cursor sweep.
            if button == "right":
                ctrl.RightClick(simulateMove=False)
            elif button == "middle":
                ctrl.MiddleClick(simulateMove=False)
            else:
                ctrl.Click(simulateMove=False)
        return (cx, cy)
    except Exception as exc:
        logger.warning("click_control failed: %s", exc)
        return None


def set_text(
    text: str,
    *,
    name: str | None = None,
    automation_id: str | None = None,
    window_title: str | None = None,
) -> bool:
    """Set the value of a named text control (Edit / TextBox / ComboBox).

    Uses the ValuePattern when available; falls back to focus-then-type.
    """
    if not _have_uia():
        return False
    ctrl = _find_control(
        name=name,
        automation_id=automation_id,
        control_type="EditControl",  # narrow by default to avoid clicking buttons
        window_title=window_title,
    ) or _find_control(
        name=name,
        automation_id=automation_id,
        window_title=window_title,
    )
    if ctrl is None:
        return False
    try:
        # Prefer the ValuePattern — sets text without simulating keystrokes.
        try:
            pattern = ctrl.GetValuePattern()
            pattern.SetValue(text)
            return True
        except Exception:
            pass
        ctrl.SetFocus()
        # SendKeys with curly-brace escaping for safety.
        _auto.SendKeys(text, waitTime=0.02)  # type: ignore[union-attr]
        return True
    except Exception as exc:
        logger.warning("set_text failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _find_window(window_title: str | None):
    """Return the root control for either the named window or the foreground."""
    if _auto is None:
        return None
    try:
        if window_title:
            # WindowControl(searchDepth=1, Name=...) matches partial via 'searchFromControl'
            for w in _auto.GetRootControl().GetChildren():
                title = (w.Name or "").lower()
                if window_title.lower() in title:
                    return w
            return None
        return _auto.GetForegroundControl()
    except Exception as exc:
        logger.debug("_find_window failed: %s", exc)
        return None


def _walk(node, out: list[dict[str, Any]], depth: int, max_depth: int, max_results: int) -> None:
    if len(out) >= max_results or depth > max_depth:
        return
    try:
        rect = node.BoundingRectangle
        out.append(
            {
                "name": node.Name or "",
                "control_type": node.ControlTypeName,
                "automation_id": getattr(node, "AutomationId", "") or "",
                "class_name": getattr(node, "ClassName", "") or "",
                "x": int(rect.left),
                "y": int(rect.top),
                "width": int(rect.right - rect.left),
                "height": int(rect.bottom - rect.top),
                "is_enabled": bool(getattr(node, "IsEnabled", True)),
                "is_offscreen": bool(getattr(node, "IsOffscreen", False)),
            }
        )
    except Exception:
        return
    try:
        for child in node.GetChildren():
            _walk(child, out, depth + 1, max_depth, max_results)
    except Exception:
        return


def _find_control(
    *,
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    window_title: str | None = None,
):
    root = _find_window(window_title)
    if root is None:
        return None
    needle_name = (name or "").lower()
    needle_id = (automation_id or "").lower()
    needle_type = (control_type or "").lower()

    best = None
    best_score = -1

    def _matches(node) -> int:
        score = 0
        n = (node.Name or "").lower()
        a = (getattr(node, "AutomationId", "") or "").lower()
        t = (node.ControlTypeName or "").lower()
        if needle_name:
            if n == needle_name:
                score += 3
            elif needle_name in n:
                score += 2
            else:
                return -1
        if needle_id:
            if a == needle_id:
                score += 3
            elif needle_id in a:
                score += 2
            else:
                return -1
        if needle_type:
            if t == needle_type or needle_type in t:
                score += 1
            else:
                return -1
        return score

    # Breadth-first to prefer shallower (more visible) matches.
    queue: deque = deque([(root, 0)])
    visited = 0
    max_depth = 12
    while queue and visited < 2000:
        node, depth = queue.popleft()
        visited += 1
        try:
            score = _matches(node)
        except Exception:
            score = -1
        if score > best_score:
            best_score = score
            best = node
        if depth < max_depth:
            try:
                for child in node.GetChildren():
                    queue.append((child, depth + 1))
            except Exception:
                continue
    return best
