"""
Sentinel Desktop v2 — Screenshot capture and analysis utilities.

Multi-monitor support: when the optional ``mss`` library is installed, callers
can pick which monitor to capture or capture the union of all monitors. mss is
also faster than pyautogui's ImageGrab on Windows. Without mss we fall back to
pyautogui.screenshot() (primary monitor only).
"""

import base64
import io
import logging
import time

import pyautogui
from PIL import Image

logger = logging.getLogger(__name__)

# Try to load mss once; fall back to pyautogui if unavailable.
try:
    import mss  # type: ignore

    _HAS_MSS = True
except ImportError as exc:
    logger.debug("mss unavailable, falling back to pyautogui: %s", exc)
    _HAS_MSS = False


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
    except Exception as exc:
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
    except Exception as exc:
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
                    }
                )
            return out
        except Exception as exc:
            logger.debug("mss.monitors failed, falling back: %s", exc)

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
        }
    ]


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def capture_screen(monitor: int | str | None = None) -> Image.Image:
    """Capture the screen → PIL Image.

    Args:
        monitor: If ``None``, captures the primary monitor (pyautogui default).
            With mss available: ``0`` captures the virtual union of every
            monitor, ``1`` captures the primary monitor, ``2+`` captures
            secondary monitors, ``"auto"`` picks the monitor containing the
            foreground window (recommended default).
    """
    monitor = resolve_monitor(monitor)
    if monitor is not None and _HAS_MSS:
        try:
            with mss.mss() as sct:
                mons = sct.monitors
                if 0 <= monitor < len(mons):
                    raw = sct.grab(mons[monitor])
                    return Image.frombytes("RGB", raw.size, raw.rgb)
                logger.warning(
                    "monitor index %s out of range (have %d) — using primary",
                    monitor,
                    len(mons),
                )
        except Exception as exc:
            logger.warning("mss capture failed, falling back: %s", exc)
    try:
        return pyautogui.screenshot()
    except Exception as exc:
        logger.error("pyautogui screenshot failed: %s", exc)
        raise OSError(f"All screen capture methods failed: {exc}") from exc


def capture_focused_window() -> Image.Image | None:
    """Capture the *target* window's pixels — the foreground window, unless
    that's the Sentinel Desktop GUI itself (in which case fall back to the
    most recent other app).

    Returns None only when no suitable window can be found.
    """
    from core import window_manager as wm

    target = wm.get_target_window_rect()
    if target is None:
        # Last-resort fallback: try the raw focused window even if it's self.
        rect = wm.get_focused_window_rect()
        if rect is None:
            return None
        x, y, w, h = rect
    else:
        x, y, w, h, _title = target
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
    from core import window_manager as wm

    target = wm.get_target_window_rect()
    if target is None:
        rect = wm.get_focused_window_rect()
        if rect is None:
            return None
        x, y, w, h = rect
        title = ""
    else:
        x, y, w, h, title = target
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
    import time

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


def capture_region(x: int, y: int, w: int, h: int) -> Image.Image:
    """Capture a rectangular region of the screen → PIL Image."""
    if _HAS_MSS:
        try:
            with mss.mss() as sct:
                raw = sct.grab({"left": x, "top": y, "width": w, "height": h})
                return Image.frombytes("RGB", raw.size, raw.rgb)
        except Exception as exc:
            logger.debug("mss region capture failed, falling back: %s", exc)
    try:
        return pyautogui.screenshot(region=(x, y, w, h))
    except Exception as exc:
        logger.error("pyautogui region capture failed: %s", exc)
        raise OSError(f"Region capture failed for ({x},{y},{w},{h}): {exc}") from exc


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
    x: int, y: int, w: int, h: int, quality: int = 85, fmt: str = "PNG"
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
    template_path: str, confidence: float = 0.8, monitor: int | None = None
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
    except Exception as exc:
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
