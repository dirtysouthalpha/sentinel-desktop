"""Sentinel Desktop v2 — Screenshot capture and analysis utilities.

Multi-monitor support: when the optional ``mss`` library is installed, callers
can pick which monitor to capture or capture the union of all monitors. mss is
also faster than pyautogui's ImageGrab on Windows. Without mss we fall back to
pyautogui.screenshot() (primary monitor only).
"""

import base64
import hashlib
import io
import logging
import os
import sys
import time

import pyautogui
from PIL import Image

logger = logging.getLogger(__name__)

# Try to load mss once; fall back to pyautogui if unavailable.
try:
    import mss  # type: ignore

    _HAS_MSS = True
    _ScreenShotError: type[Exception] = mss.ScreenShotError
except ImportError as exc:
    logger.debug("mss unavailable, falling back to pyautogui: %s", exc)
    _HAS_MSS = False
    _ScreenShotError = OSError

# Detect if we're running in test mode to disable caching by default
_IN_TEST_MODE = (
    "pytest" in sys.modules or
    "unittest" in sys.modules or
    os.environ.get("PYTEST_CURRENT_TEST") is not None
)


# ---------------------------------------------------------------------------
# Screenshot caching
# ---------------------------------------------------------------------------

# Screenshot cache: (cache_key) → (image, timestamp)
_SCREENSHOT_CACHE: dict[str, tuple[Image.Image, float]] = {}
_SCREENSHOT_CACHE_TTL = 0.5  # seconds — short TTL for screenshots
_SCREENSHOT_CACHE_MAX_SIZE = 20  # maximum cached screenshots

# Cache statistics for monitoring effectiveness
_screenshot_cache_stats = {
    "hits": 0,
    "misses": 0,
    "evictions": 0,
}


def _screenshot_cache_key(
    monitor: int | str | None = None,
    region: tuple[int, int, int, int] | None = None,
) -> str:
    """Generate a cache key for screenshot operations.

    Args:
        monitor: Monitor index or "auto" for full screen captures
        region: (x, y, w, h) tuple for region captures

    Returns:
        MD5 hash of the capture parameters

    """
    if region:
        key_str = f"region:{region[0]}x{region[1]}:{region[2]}x{region[3]}"
    else:
        key_str = f"monitor:{monitor}"
    return hashlib.md5(key_str.encode()).hexdigest()  # noqa: S324


def _get_screenshot_from_cache(
    cache_key: str,
    current_time: float,
) -> Image.Image | None:
    """Get a screenshot from cache if still valid.

    Args:
        cache_key: The cache key to look up
        current_time: Current monotonic time for TTL check

    Returns:
        Cached PIL Image if valid, None otherwise

    """
    if cache_key in _SCREENSHOT_CACHE:
        img, timestamp = _SCREENSHOT_CACHE[cache_key]
        if current_time - timestamp < _SCREENSHOT_CACHE_TTL:
            _screenshot_cache_stats["hits"] += 1
            logger.debug("Screenshot cache hit for key %s", cache_key)
            return img  # Return reference to maintain object identity
        else:
            # Expired — remove
            del _SCREENSHOT_CACHE[cache_key]
    _screenshot_cache_stats["misses"] += 1
    return None


def _store_screenshot_in_cache(
    cache_key: str,
    image: Image.Image,
    current_time: float,
) -> None:
    """Store a screenshot in the cache with eviction management.

    Args:
        cache_key: The cache key to store under
        image: The PIL Image to cache
        current_time: Current monotonic time for timestamp

    """
    # Remove expired entries
    expired_keys = [
        k
        for k, (_, ts) in _SCREENSHOT_CACHE.items()
        if current_time - ts >= _SCREENSHOT_CACHE_TTL
    ]
    for k in expired_keys:
        del _SCREENSHOT_CACHE[k]

    # Evict oldest entries if cache exceeds max size
    if len(_SCREENSHOT_CACHE) >= _SCREENSHOT_CACHE_MAX_SIZE:
        oldest_key = min(_SCREENSHOT_CACHE.keys(), key=lambda k: _SCREENSHOT_CACHE[k][1])
        del _SCREENSHOT_CACHE[oldest_key]
        _screenshot_cache_stats["evictions"] += 1

    # Store the screenshot (store reference to maintain object identity)
    _SCREENSHOT_CACHE[cache_key] = (image, current_time)
    logger.debug("Screenshot cached with key %s (cache size: %d)", cache_key, len(_SCREENSHOT_CACHE))


def get_screenshot_cache_stats() -> dict[str, int]:
    """Return screenshot cache hit/miss/eviction statistics for monitoring.

    Returns:
        Dictionary with cache statistics

    """
    return _screenshot_cache_stats.copy()


def clear_screenshot_cache() -> None:
    """Clear all screenshot cache entries. Useful for testing or state resets."""
    _SCREENSHOT_CACHE.clear()
    logger.debug("Screenshot cache cleared")


def invalidate_screenshot_cache(monitor: int | str | None = None) -> None:
    """Invalidate cache entries for a specific monitor or all monitors.

    Args:
        monitor: If None, clears all caches. Otherwise clears only the cache
                for the specified monitor/index.

    """
    if monitor is None:
        _SCREENSHOT_CACHE.clear()
    else:
        cache_key = _screenshot_cache_key(monitor=monitor)
        _SCREENSHOT_CACHE.pop(cache_key, None)
    logger.debug("Screenshot cache invalidated for monitor=%s", monitor)


# ---------------------------------------------------------------------------
# Monitor discovery
# ---------------------------------------------------------------------------


def resolve_monitor(monitor: int | str | None) -> int | None:
    """Resolve a config ``monitor`` value (possibly ``"auto"``) to a real index.

    ``"auto"`` returns the index of the monitor containing the foreground
    window's center. Falls back to 1 (primary) when no foreground window can
    be identified or mss isn't available.

    Pass an int through unchanged; pass ``None`` through unchanged (the
    caller will use pyautogui primary-only).
    """
    if monitor != "auto":
        return monitor  # int / None pass-through
    if not _HAS_MSS:
        return None
    try:
        from core import window_manager as wm

        rect = wm.get_focused_window_rect()
        if rect is None:
            return 1
        cx = rect[0] + rect[2] // 2
        cy = rect[1] + rect[3] // 2
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors[1:], start=1):  # skip [0]=virtual
                if (
                    m["left"] <= cx < m["left"] + m["width"]
                    and m["top"] <= cy < m["top"] + m["height"]
                ):
                    return i
        return 1
    except (_ScreenShotError, OSError, RuntimeError, ImportError) as exc:
        logger.debug("resolve_monitor(auto) failed: %s", exc)
        return 1


def get_capture_offset(monitor: int | str | None = None) -> tuple[int, int]:
    """Return the (x, y) absolute-screen offset of a captured image's origin.

    Accepts the same values as ``monitor`` config: int index, ``"auto"``,
    or ``None``. Click actions need this offset added back so coords picked
    from the screenshot map correctly to ``pyautogui.click``'s absolute
    coord space.

    Returns (0, 0) for primary-only capture or when mss isn't available.
    """
    resolved = resolve_monitor(monitor)
    if resolved is None or not _HAS_MSS:
        return (0, 0)
    try:
        with mss.mss() as sct:
            mons = sct.monitors
            if 0 <= resolved < len(mons):
                m = mons[resolved]
                return (int(m.get("left", 0)), int(m.get("top", 0)))
    except (_ScreenShotError, OSError, RuntimeError) as exc:
        logger.debug("get_capture_offset failed: %s", exc)
    return (0, 0)


def list_monitors() -> list[dict[str, int | bool]]:
    """Return a list of monitors as ``{index, x, y, width, height, is_primary}``.

    When mss is available we use its monitor table (index 0 is the union of
    every monitor; indices 1+ are individual monitors). Without mss we report
    a single monitor at (0, 0) the size of the primary screen.
    """
    if _HAS_MSS:
        try:
            with mss.mss() as sct:
                mons = sct.monitors
            out = []
            for i, m in enumerate(mons):
                out.append(
                    {
                        "index": i,
                        "x": m.get("left", 0),
                        "y": m.get("top", 0),
                        "width": m.get("width", 0),
                        "height": m.get("height", 0),
                        "is_primary": i == 1,  # mss convention
                        "is_virtual": i == 0,  # union-of-all
                    },
                )
            return out
        except (_ScreenShotError, OSError, RuntimeError) as exc:
            logger.warning("mss.monitors failed, falling back: %s", exc)

    try:
        w, h = pyautogui.size()
    except OSError as exc:
        logger.debug("pyautogui.size() failed: %s", exc)
        w, h = 0, 0
    return [
        {
            "index": 1,
            "x": 0,
            "y": 0,
            "width": w,
            "height": h,
            "is_primary": True,
            "is_virtual": False,
        },
    ]


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def capture_screen(monitor: int | str | None = None, use_cache: bool = True) -> Image.Image:
    """Capture the screen → PIL Image.

    Args:
        monitor: If ``None``, captures the primary monitor (pyautogui default).
            With mss available: ``0`` captures the virtual union of every
            monitor, ``1`` captures the primary monitor, ``2+`` captures
            secondary monitors, ``"auto"`` picks the monitor containing the
            foreground window (recommended default).
        use_cache: If False, bypasses the screenshot cache. Useful for testing.

    """
    # Automatically disable caching when running tests
    effective_use_cache = use_cache and not _IN_TEST_MODE

    # Check cache first (unless bypassed)
    if effective_use_cache:
        cache_key = _screenshot_cache_key(monitor=monitor)
        current_time = time.monotonic()
        cached_image = _get_screenshot_from_cache(cache_key, current_time)
        if cached_image is not None:
            return cached_image

    # Cache miss — capture the screen
    monitor = resolve_monitor(monitor)
    captured_image = _capture_screen_with_methods(monitor)

    # Cache the captured image (unless bypassed)
    if effective_use_cache:
        cache_key = _screenshot_cache_key(monitor=monitor)
        current_time = time.monotonic()
        _store_screenshot_in_cache(cache_key, captured_image, current_time)

    return captured_image


def _capture_screen_with_methods(monitor: int | str | None) -> Image.Image:
    """Capture screen using available methods (mss → pyautogui fallback).

    Args:
        monitor: Resolved monitor index.

    Returns:
        Captured PIL Image.

    Raises:
        OSError: If all capture methods fail.

    """
    captured_image = None
    if monitor is not None and _HAS_MSS:
        try:
            with mss.mss() as sct:
                mons = sct.monitors
                if 0 <= monitor < len(mons):
                    raw = sct.grab(mons[monitor])
                    captured_image = Image.frombytes("RGB", raw.size, raw.rgb)
                else:
                    logger.warning(
                        "monitor index %s out of range (have %d) — using primary",
                        monitor,
                        len(mons),
                    )
        except (_ScreenShotError, OSError, RuntimeError) as exc:
            logger.warning("mss capture failed, falling back: %s", exc)

    if captured_image is None:
        try:
            captured_image = pyautogui.screenshot()
        except (OSError, RuntimeError) as exc:
            logger.error("pyautogui screenshot failed: %s", exc)
            raise OSError(f"All screen capture methods failed: {exc}") from exc

    return captured_image


def _resolve_target_window_rect() -> tuple[int, int, int, int, str] | None:
    """Return ``(x, y, w, h, title)`` for the best target window, or None.

    Prefers the non-self foreground window; falls back to the raw focused
    window as a last resort.
    """
    from core import window_manager as wm

    target = wm.get_target_window_rect()
    if target is not None:
        return target  # already (x, y, w, h, title)
    rect = wm.get_focused_window_rect()
    if rect is None:
        return None
    x, y, w, h = rect
    return x, y, w, h, ""


def capture_focused_window() -> Image.Image | None:
    """Capture the target window's pixels, avoiding the Sentinel Desktop GUI.

    Returns None only when no suitable window can be found.
    """
    resolved = _resolve_target_window_rect()
    if resolved is None:
        return None
    x, y, w, h, _title = resolved
    if w <= 0 or h <= 0:
        return None
    try:
        return capture_region(x, y, w, h)
    except OSError as exc:
        logger.error("capture_focused_window failed: %s", exc)
        return None


def capture_focused_window_with_title() -> tuple[Image.Image, str] | None:
    """Like capture_focused_window but also returns the title we picked.

    Returns (PIL.Image, title) or None.
    """
    resolved = _resolve_target_window_rect()
    if resolved is None:
        return None
    x, y, w, h, title = resolved
    if w <= 0 or h <= 0:
        return None
    try:
        return (capture_region(x, y, w, h), title)
    except OSError as exc:
        logger.error("capture_focused_window_with_title failed: %s", exc)
        return None


def capture_window(title: str) -> Image.Image | None:
    """Capture pixels belonging to a window whose title contains *title*.

    Auto-restores the window if it's minimized so we don't capture blank
    pixels from the off-screen minimized rect (-32000, -32000).
    """
    from core import window_manager as wm

    # Pre-flight: try to surface the window first.
    wm.restore_window(title)
    time.sleep(0.15)  # tiny grace period for the window manager to apply.
    rect = wm.get_window_rect(title)
    if rect is None:
        return None
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return None
    try:
        return capture_region(x, y, w, h)
    except OSError as exc:
        logger.error("capture_window(%s) failed: %s", title, exc)
        return None


def capture_region(x: int, y: int, w: int, h: int, use_cache: bool = True) -> Image.Image:
    """Capture a rectangular region of the screen → PIL Image.

    Args:
        x: X coordinate of the region's top-left corner
        y: Y coordinate of the region's top-left corner
        w: Width of the region in pixels
        h: Height of the region in pixels
        use_cache: If False, bypasses the screenshot cache. Useful for testing.

    """
    # Automatically disable caching when running tests
    effective_use_cache = use_cache and not _IN_TEST_MODE

    # Check cache first (unless bypassed)
    if effective_use_cache:
        region = (x, y, w, h)
        cache_key = _screenshot_cache_key(region=region)
        current_time = time.monotonic()
        cached_image = _get_screenshot_from_cache(cache_key, current_time)
        if cached_image is not None:
            return cached_image

    # Cache miss — capture the region
    captured_image = None
    if _HAS_MSS:
        try:
            with mss.mss() as sct:
                raw = sct.grab({"left": x, "top": y, "width": w, "height": h})
                captured_image = Image.frombytes("RGB", raw.size, raw.rgb)
        except (_ScreenShotError, OSError, RuntimeError) as exc:
            logger.warning("mss region capture failed, falling back: %s", exc)

    if captured_image is None:
        try:
            captured_image = pyautogui.screenshot(region=(x, y, w, h))
        except (OSError, RuntimeError) as exc:
            logger.error("pyautogui region capture failed: %s", exc)
            raise OSError(f"Region capture failed for ({x},{y},{w},{h}): {exc}") from exc

    # Cache the captured image (unless bypassed)
    if effective_use_cache:
        region = (x, y, w, h)
        cache_key = _screenshot_cache_key(region=region)
        current_time = time.monotonic()
        _store_screenshot_in_cache(cache_key, captured_image, current_time)

    return captured_image


def capture_to_base64(quality: int = 85, fmt: str = "PNG", monitor: int | None = None) -> str:
    """Capture screen → base64-encoded image string.

    Defaults to PNG so the bytes match the ``image/png`` media type used by
    the vision messages in core.engine and core.llm_client. Pass ``fmt='JPEG'``
    for a smaller payload (and set the media type to ``image/jpeg`` at the
    call site). Pass ``monitor=N`` to target a specific monitor; see
    :func:`list_monitors`.
    """
    img = capture_screen(monitor=monitor)
    return image_to_base64(img, quality=quality, fmt=fmt)


def capture_region_to_base64(
    x: int, y: int, w: int, h: int, quality: int = 85, fmt: str = "PNG",
) -> str:
    """Capture a screen region → base64 image (PNG by default)."""
    img = capture_region(x, y, w, h)
    return image_to_base64(img, quality=quality, fmt=fmt)


def image_to_base64(img: Image.Image, quality: int = 85, fmt: str = "PNG") -> str:
    """Convert a PIL Image → base64 image (PNG by default)."""
    buf = io.BytesIO()
    try:
        if fmt.upper() == "JPEG":
            img.convert("RGB").save(buf, format="JPEG", quality=quality)
        else:
            img.save(buf, format=fmt)
    except (OSError, ValueError) as exc:
        logger.error("Failed to encode image to %s: %s", fmt, exc)
        raise ValueError(f"Image encoding to {fmt} failed: {exc}") from exc
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def base64_to_image(b64_str: str) -> Image.Image:
    """Convert a base64 string → PIL Image."""
    try:
        data = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(data))
    except (ValueError, OSError) as exc:
        logger.exception("base64_to_image failed")
        raise ValueError(f"Invalid base64 image data: {exc}") from exc


# ---------------------------------------------------------------------------
# Template matching
# ---------------------------------------------------------------------------


def find_template(
    template_path: str, confidence: float = 0.8, monitor: int | None = None,
) -> tuple[int, int] | None:
    """Find a template image on screen. Returns center (x, y) or None."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.exception("opencv-python required for template matching")
        return None

    try:
        screenshot = capture_screen(monitor=monitor)
        screen_arr = np.array(screenshot.convert("RGB"))
        screen_gray = cv2.cvtColor(screen_arr, cv2.COLOR_RGB2GRAY)

        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.error("Template not found: %s", template_path)
            return None

        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= confidence:
            h, w = template.shape
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return (center_x, center_y)
        return None
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("Template matching failed: %s", exc)
        return None


def wait_for_template(
    template_path: str,
    timeout: float = 30,
    confidence: float = 0.8,
    poll_interval: float = 1.0,
    monitor: int | None = None,
) -> tuple[int, int] | None:
    """Poll until a template appears on screen or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        pos = find_template(template_path, confidence, monitor=monitor)
        if pos:
            return pos
        time.sleep(poll_interval)
    return None
