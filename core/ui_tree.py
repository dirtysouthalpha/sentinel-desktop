"""Sentinel Desktop v2 — Windows UIAutomation wrapper.

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
import time
from collections import deque
from typing import Any

from core.utils import get_uia_auto, have_uia

logger = logging.getLogger(__name__)

# Enhanced multi-layer UI element caching system with size limits and eviction
# UI scans are expensive (BFS over thousands of nodes); multi-layer caching avoids
# redundant scans when the agent performs similar operations in quick succession.

# Layer 1: Control lookup cache (find_control results)
_FIND_CONTROL_CACHE: dict[tuple[str | None, ...], tuple[Any, float]] = {}
_FIND_CONTROL_TTL = 0.5  # seconds
_FIND_CONTROL_MAX_SIZE = 100  # maximum cache entries

# Layer 2: UI tree traversal cache (list_controls results)
_LIST_CONTROLS_CACHE: dict[tuple[str | None, int, int], tuple[list[dict[str, Any]], float]] = {}
_LIST_CONTROLS_TTL = 1.0  # seconds (longer TTL for tree walks)
_LIST_CONTROLS_MAX_SIZE = 50  # maximum cache entries

# Layer 3: Window discovery cache (_find_window results)
_WINDOW_CACHE: dict[str | None, tuple[Any, float]] = {}
_WINDOW_TTL = 2.0  # seconds (windows change infrequently)
_WINDOW_MAX_SIZE = 20  # maximum cache entries

# Cache statistics for monitoring effectiveness
_cache_stats = {
    "find_control_hits": 0,
    "find_control_misses": 0,
    "list_controls_hits": 0,
    "list_controls_misses": 0,
    "window_hits": 0,
    "window_misses": 0,
}


def _evict_oldest_entry(
    cache: dict, max_size: int,
) -> None:
    """Evict the oldest entry from a cache when size limit is exceeded.

    Args:
        cache: The cache dictionary to evict from
        max_size: Maximum size before eviction starts

    """
    if len(cache) > max_size:
        # Find and remove the oldest entry (by timestamp)
        oldest_key = min(cache.keys(), key=lambda k: cache[k][1])
        del cache[oldest_key]


def _clear_expired_entries(
    cache: dict, ttl: float, current_time: float | None = None,
) -> None:
    """Remove expired entries from a cache.

    Args:
        cache: The cache dictionary to clean
        ttl: Time-to-live in seconds
        current_time: Current monotonic time (optional)

    """
    if current_time is None:
        current_time = time.monotonic()

    expired_keys = [
        key for key, (_, timestamp) in cache.items()
        if current_time - timestamp >= ttl
    ]
    for key in expired_keys:
        del cache[key]


def get_cache_stats() -> dict[str, int]:
    """Return cache hit/miss statistics for monitoring.

    Returns:
        Dictionary with cache statistics for each cache layer

    """
    return _cache_stats.copy()


def clear_all_caches() -> None:
    """Clear all UI element caches. Useful for testing or state resets."""
    _FIND_CONTROL_CACHE.clear()
    _LIST_CONTROLS_CACHE.clear()
    _WINDOW_CACHE.clear()
    # Reset statistics
    for key in _cache_stats:
        _cache_stats[key] = 0


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
    if not have_uia():
        return []

    # Check cache first
    cache_key = (window_title, max_depth, max_results)
    now = time.monotonic()

    # Clean expired entries periodically
    if len(_LIST_CONTROLS_CACHE) > _LIST_CONTROLS_MAX_SIZE // 2:
        _clear_expired_entries(_LIST_CONTROLS_CACHE, _LIST_CONTROLS_TTL, now)

    cached = _LIST_CONTROLS_CACHE.get(cache_key)
    if cached is not None and now - cached[1] < _LIST_CONTROLS_TTL:
        _cache_stats["list_controls_hits"] += 1
        return cached[0]

    _cache_stats["list_controls_misses"] += 1

    result = _walk_controls_tree(window_title, max_depth, max_results)

    # Cache the result (even if empty or partial)
    _LIST_CONTROLS_CACHE[cache_key] = (result, now)
    _evict_oldest_entry(_LIST_CONTROLS_CACHE, _LIST_CONTROLS_MAX_SIZE)

    return result


def _walk_controls_tree(
    window_title: str | None,
    max_depth: int,
    max_results: int,
) -> list[dict[str, Any]]:
    """Walk the UI tree and collect controls.

    Args:
        window_title: Partial title match. ``None`` uses the foreground window.
        max_depth: Recursion limit.
        max_results: Cap on returned controls.

    Returns:
        List of control dictionaries.

    """
    root = _find_window(window_title)
    if root is None:
        return []

    out: list[dict[str, Any]] = []
    try:
        _walk(root, out, depth=0, max_depth=max_depth, max_results=max_results)
    except (OSError, AttributeError, RuntimeError, TypeError) as exc:
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
    if not have_uia():
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
        _invoke_control(ctrl, button)
        return (cx, cy)
    except (OSError, AttributeError, RuntimeError, TypeError) as exc:
        logger.warning("click_control failed: %s", exc)
        return None


def _invoke_control(ctrl: Any, button: str) -> None:
    """Activate *ctrl* via the best available UIA pattern, then fall back to physical click.

    Tries InvokePattern first (no cursor movement), then SelectionItemPattern
    (for list-box rows and tabs), then a physical click as last resort.
    """
    invoked = False
    try:
        pattern = ctrl.GetInvokePattern()
        if pattern is not None:
            pattern.Invoke()
            invoked = True
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.debug("InvokePattern failed: %s", exc)

    if not invoked:
        try:
            sel = ctrl.GetSelectionItemPattern()
            if sel is not None:
                sel.Select()
                invoked = True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("SelectionItemPattern failed: %s", exc)

    if not invoked:
        if button == "right":
            ctrl.RightClick(simulateMove=False)
        elif button == "middle":
            ctrl.MiddleClick(simulateMove=False)
        else:
            ctrl.Click(simulateMove=False)


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
    if not have_uia():
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
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("ValuePattern failed, falling back to SendKeys: %s", exc)
        ctrl.SetFocus()
        # SendKeys with curly-brace escaping for safety.
        get_uia_auto().SendKeys(text, waitTime=0.02)  # type: ignore[union-attr]
        return True
    except (OSError, AttributeError, RuntimeError, TypeError) as exc:
        logger.warning("set_text failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _find_window(window_title: str | None) -> Any | None:
    """Return the root control for either the named window or the foreground.

    Results are cached for 2.0 s since window state changes infrequently.
    """
    if get_uia_auto() is None:
        return None

    # Check cache first
    now = time.monotonic()

    # Clean expired entries periodically
    if len(_WINDOW_CACHE) > _WINDOW_MAX_SIZE // 2:
        _clear_expired_entries(_WINDOW_CACHE, _WINDOW_TTL, now)

    cached = _WINDOW_CACHE.get(window_title)
    if cached is not None and now - cached[1] < _WINDOW_TTL:
        _cache_stats["window_hits"] += 1
        return cached[0]

    _cache_stats["window_misses"] += 1

    try:
        window = None
        if window_title:
            # WindowControl(searchDepth=1, Name=...) matches partial via 'searchFromControl'
            for w in get_uia_auto().GetRootControl().GetChildren():
                title = (w.Name or "").lower()
                if window_title.lower() in title:
                    window = w
                    break
        else:
            window = get_uia_auto().GetForegroundControl()

        # Cache the result
        _WINDOW_CACHE[window_title] = (window, now)
        _evict_oldest_entry(_WINDOW_CACHE, _WINDOW_MAX_SIZE)

        return window
    except (OSError, AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("_find_window failed: %s", exc)
        return None


def _walk(
    node: Any, out: list[dict[str, Any]], depth: int, max_depth: int, max_results: int,
) -> None:
    """Recursively collect UI node properties up to *max_depth* / *max_results*."""
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
            },
        )
    except (OSError, AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("_walk: failed to read node properties: %s", exc)
        return
    try:
        for child in node.GetChildren():
            _walk(child, out, depth + 1, max_depth, max_results)
    except (OSError, AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("_walk: failed to get children: %s", exc)


def _score_node(
    node: Any,
    needle_name: str,
    needle_id: str,
    needle_type: str,
) -> int:
    """Score a UIA node against search needles; return -1 to reject, ≥0 to accept."""
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


def _bfs_best_match(
    root: Any,
    needle_name: str,
    needle_id: str,
    needle_type: str,
) -> Any | None:
    """BFS over the UI tree and return the highest-scoring node (max depth 12, max 2000 nodes)."""
    best = None
    best_score = -1
    queue: deque = deque([(root, 0)])
    visited = 0
    max_depth = 12
    while queue and visited < 2000:
        node, depth = queue.popleft()
        visited += 1
        try:
            score = _score_node(node, needle_name, needle_id, needle_type)
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("Scoring failed for node: %s", exc)
            score = -1
        if score > best_score:
            best_score = score
            best = node
        if depth < max_depth:
            try:
                for child in node.GetChildren():
                    queue.append((child, depth + 1))
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("_find_best_match: failed to get children: %s", exc)
                continue
    return best


def _find_control(
    *,
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    window_title: str | None = None,
) -> Any | None:
    """Breadth-first search for a UI element matching the given criteria.

    Scoring: exact match = 3, substring = 2, type match = 1.  Returns the
    highest-scoring match or ``None`` if nothing clears the bar.

    Results are cached for 0.5 s to avoid redundant tree scans when the same
    lookup is issued multiple times in quick succession.
    """
    cache_key = (name, automation_id, control_type, window_title)
    now = time.monotonic()

    # Clean expired entries periodically
    if len(_FIND_CONTROL_CACHE) > _FIND_CONTROL_MAX_SIZE // 2:
        _clear_expired_entries(_FIND_CONTROL_CACHE, _FIND_CONTROL_TTL, now)

    cached = _FIND_CONTROL_CACHE.get(cache_key)
    if cached is not None and now - cached[1] < _FIND_CONTROL_TTL:
        _cache_stats["find_control_hits"] += 1
        return cached[0]

    _cache_stats["find_control_misses"] += 1

    root = _find_window(window_title)
    if root is None:
        _FIND_CONTROL_CACHE[cache_key] = (None, now)
        _evict_oldest_entry(_FIND_CONTROL_CACHE, _FIND_CONTROL_MAX_SIZE)
        return None

    best = _bfs_best_match(
        root,
        needle_name=(name or "").lower(),
        needle_id=(automation_id or "").lower(),
        needle_type=(control_type or "").lower(),
    )
    _FIND_CONTROL_CACHE[cache_key] = (best, now)
    _evict_oldest_entry(_FIND_CONTROL_CACHE, _FIND_CONTROL_MAX_SIZE)
    return best
