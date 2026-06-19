"""Sentinel Desktop v7.0 — DPI & Coordinate Calibration.

Detects DPI scaling per monitor, transforms coordinates between logical
(screenshot) and physical (pyautogui/desktop) spaces, and runs a one-time
calibration probe for new display configurations.

Why this exists:
  On Windows with HiDPI scaling (125%, 150%, 200%), mss returns physical
  pixels while pyautogui.click() uses logical (scaled) coordinates. Without
  correction, a coordinate picked from a screenshot at 150% scaling will be
  1.5× off — the click lands in the wrong place. This module bridges that
  gap by tracking per-monitor scaling factors and transforming coordinates.

Coordinate spaces:
  - **Physical** (mss, UIAutomation): actual screen pixels.
  - **Logical** (pyautogui, pyautogui.click): scaled by DPI factor.
  - Transform: logical = physical / scale_factor
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Calibration state file — persists across sessions
_CALIBRATION_DIR = Path.home() / ".sentinel" / "calibration"
_CALIBRATION_FILE = _CALIBRATION_DIR / "displays.json"

# Lock for thread-safe calibration access
_calib_lock = threading.Lock()


@dataclass
class MonitorInfo:
    """DPI information for a single monitor.

    Attributes:
        index: Monitor index (0=virtual, 1=primary, 2+=secondary).
        x: Left edge in physical pixels.
        y: Top edge in physical pixels.
        width: Width in physical pixels.
        height: Height in physical pixels.
        scale_factor: DPI scale factor (1.0 = 100%, 1.5 = 150%, 2.0 = 200%).
        is_primary: Whether this is the primary monitor.
        device_id: Unique identifier for calibration persistence.
    """

    index: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    scale_factor: float = 1.0
    is_primary: bool = False
    device_id: str = ""

    @property
    def logical_width(self) -> int:
        """Width in logical (scaled) pixels."""
        return int(self.width / self.scale_factor)

    @property
    def logical_height(self) -> int:
        """Height in logical (scaled) pixels."""
        return int(self.height / self.scale_factor)


@dataclass
class CalibrationData:
    """Persisted calibration data for a display configuration.

    Attributes:
        config_hash: Hash of the monitor layout (for change detection).
        monitors: Per-monitor calibration data.
        calibrated_at: Timestamp of last calibration.
        verified: Whether the calibration has been manually verified.
    """

    config_hash: str = ""
    monitors: list[dict[str, Any]] = field(default_factory=list)
    calibrated_at: float = 0.0
    verified: bool = False


def _get_windows_dpi_scaling() -> dict[int, float]:
    """Detect DPI scaling per monitor on Windows using ctypes.

    Returns a dict of monitor_index → scale_factor.
    Falls back to 1.0 for each monitor if detection fails.
    """
    scales: dict[int, float] = {}

    if sys.platform != "win32":
        return scales

    try:
        import ctypes
        import ctypes.wintypes

        # Load user32 for DPI awareness
        user32 = ctypes.windll.user32

        # Enable per-monitor DPI awareness (V2 if available)
        try:
            # SetProcessDpiAwarenessContext(-4) = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                # Fallback: SetProcessDpiAwareness(2) = PROCESS_PER_MONITOR_DPI_AWARE
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                logger.debug("Could not set DPI awareness — may get virtualized values")

        # Enumerate monitors and get their DPI
        monitor_handles: list[int] = []

        # MONITORENUMPROC callback type
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_ulong,  # hMonitor
            ctypes.c_ulong,  # hdcMonitor
            ctypes.POINTER(ctypes.wintypes.RECT),  # lprcMonitor
            ctypes.c_double,  # dwData (lParam)
        )

        def _monitor_enum_callback(
            h_monitor: int,
            _hdc: int,
            _lprc: Any,
            _lparam: float,
        ) -> int:
            monitor_handles.append(h_monitor)
            return 1  # Continue enumeration

        callback = MONITORENUMPROC(_monitor_enum_callback)

        # EnumDisplayMonitors(NULL, NULL, callback, 0)
        user32.EnumDisplayMonitors(None, None, callback, 0)

        for i, h_monitor in enumerate(monitor_handles):
            try:
                # GetDpiForMonitor: MDT_EFFECTIVE_DPI = 0
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                ctypes.windll.shcore.GetDpiForMonitor(
                    h_monitor,
                    0,  # MDT_EFFECTIVE_DPI
                    ctypes.byref(dpi_x),
                    ctypes.byref(dpi_y),
                )
                scale = dpi_x.value / 96.0
                scales[i + 1] = scale  # 1-indexed to match mss
                logger.debug("Monitor %d: DPI=%d, scale=%.2f", i + 1, dpi_x.value, scale)
            except (AttributeError, OSError) as exc:
                logger.debug("GetDpiForMonitor failed for handle %d: %s", h_monitor, exc)
                scales[i + 1] = 1.0

    except (OSError, ImportError) as exc:
        logger.debug("Windows DPI detection failed: %s", exc)

    return scales


def _get_mss_monitors() -> list[dict[str, Any]]:
    """Get monitor geometry from mss.

    Returns list of monitor dicts from mss.monitors (index 0 = virtual desktop).
    """
    try:
        import mss

        with mss.mss() as sct:
            return list(sct.monitors)
    except (ImportError, OSError) as exc:
        logger.debug("mss monitor query failed: %s", exc)
        return []


def _compute_config_hash(monitors: list[dict[str, Any]]) -> str:
    """Compute a hash of the current monitor configuration for change detection.

    Uses position + resolution to detect layout changes.
    """
    parts = []
    for m in monitors:
        parts.append(
            f"{m.get('left', 0)}x{m.get('top', 0)}+{m.get('width', 0)}x{m.get('height', 0)}"
        )
    config_str = "|".join(parts)
    import hashlib

    return hashlib.md5(config_str.encode(), usedforsecurity=False).hexdigest()[:12]


def detect_monitors() -> list[MonitorInfo]:
    """Detect all monitors with their DPI scaling factors.

    Combines mss geometry with Windows DPI detection to produce
    per-monitor scaling information. Safe to call on any platform.

    Returns:
        List of MonitorInfo, sorted by index (0=virtual, 1=primary, ...).
    """
    mss_mons = _get_mss_monitors()
    dpi_scales = _get_windows_dpi_scaling()

    if not mss_mons:
        # Fallback: single primary monitor
        try:
            import pyautogui

            w, h = pyautogui.size()
        except OSError:
            w, h = 1920, 1080

        return [
            MonitorInfo(
                index=1,
                width=w,
                height=h,
                scale_factor=1.0,
                is_primary=True,
                device_id="fallback",
            ),
        ]

    result: list[MonitorInfo] = []
    for i, m in enumerate(mss_mons):
        scale = dpi_scales.get(i, 1.0)

        # Build device_id for persistence: use position+size as fingerprint
        device_id = (
            f"mon{i}_{m.get('width', 0)}x{m.get('height', 0)}@{m.get('left', 0)},{m.get('top', 0)}"
        )

        info = MonitorInfo(
            index=i,
            x=m.get("left", 0),
            y=m.get("top", 0),
            width=m.get("width", 0),
            height=m.get("height", 0),
            scale_factor=scale,
            is_primary=(i == 1),  # mss convention: index 1 = primary
            device_id=device_id,
        )
        result.append(info)

    logger.info(
        "Detected %d monitors: %s",
        len(result),
        ", ".join(f"M{m.index}={m.scale_factor:.0%}" for m in result if m.index > 0),
    )

    return result


def physical_to_logical(
    x: int,
    y: int,
    monitors: list[MonitorInfo] | None = None,
) -> tuple[int, int]:
    """Convert physical (screenshot) coordinates to logical (pyautogui) coordinates.

    Args:
        x: Physical X coordinate.
        y: Physical Y coordinate.
        monitors: Pre-detected monitor list. If None, detects fresh.

    Returns:
        (logical_x, logical_y) for use with pyautogui.click(), etc.
    """
    if monitors is None:
        monitors = detect_monitors()

    for mon in monitors:
        if mon.index == 0:
            continue  # Skip virtual desktop aggregate

        # Check if point is within this monitor's physical bounds
        if mon.x <= x < mon.x + mon.width and mon.y <= y < mon.y + mon.height:
            # Transform: subtract monitor origin, divide by scale, add back
            local_x = x - mon.x
            local_y = y - mon.y

            logical_x = int(local_x / mon.scale_factor) + int(mon.x / mon.scale_factor)
            logical_y = int(local_y / mon.scale_factor) + int(mon.y / mon.scale_factor)

            logger.debug(
                "Physical (%d,%d) → Logical (%d,%d) [M%d scale=%.2f]",
                x,
                y,
                logical_x,
                logical_y,
                mon.index,
                mon.scale_factor,
            )
            return (logical_x, logical_y)

    # Fallback: if no monitor matched, pass through unchanged
    logger.debug("No monitor matched for (%d,%d) — passing through", x, y)
    return (x, y)


def logical_to_physical(
    x: int,
    y: int,
    monitors: list[MonitorInfo] | None = None,
) -> tuple[int, int]:
    """Convert logical (pyautogui) coordinates to physical (screenshot) coordinates.

    Args:
        x: Logical X coordinate.
        y: Logical Y coordinate.
        monitors: Pre-detected monitor list. If None, detects fresh.

    Returns:
        (physical_x, physical_y) matching mss/UIAutomation coordinates.
    """
    if monitors is None:
        monitors = detect_monitors()

    for mon in monitors:
        if mon.index == 0:
            continue

        # Logical bounds of this monitor
        logical_x_start = int(mon.x / mon.scale_factor)
        logical_y_start = int(mon.y / mon.scale_factor)
        logical_w = int(mon.width / mon.scale_factor)
        logical_h = int(mon.height / mon.scale_factor)

        if (
            logical_x_start <= x < logical_x_start + logical_w
            and logical_y_start <= y < logical_y_start + logical_h
        ):
            # Transform: subtract logical origin, multiply by scale, add physical origin
            local_logical_x = x - logical_x_start
            local_logical_y = y - logical_y_start

            physical_x = int(local_logical_x * mon.scale_factor) + mon.x
            physical_y = int(local_logical_y * mon.scale_factor) + mon.y

            logger.debug(
                "Logical (%d,%d) → Physical (%d,%d) [M%d scale=%.2f]",
                x,
                y,
                physical_x,
                physical_y,
                mon.index,
                mon.scale_factor,
            )
            return (physical_x, physical_y)

    # Fallback
    return (x, y)


def load_calibration() -> CalibrationData | None:
    """Load persisted calibration data from disk.

    Returns:
        CalibrationData if file exists and is valid, None otherwise.
    """
    try:
        if not _CALIBRATION_FILE.exists():
            return None

        with _CALIBRATION_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return CalibrationData(
            config_hash=data.get("config_hash", ""),
            monitors=data.get("monitors", []),
            calibrated_at=data.get("calibrated_at", 0.0),
            verified=data.get("verified", False),
        )
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.debug("Calibration load failed: %s", exc)
        return None


def save_calibration(calib: CalibrationData) -> None:
    """Persist calibration data to disk.

    Args:
        calib: Calibration data to save.
    """
    try:
        _CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "config_hash": calib.config_hash,
            "monitors": calib.monitors,
            "calibrated_at": calib.calibrated_at,
            "verified": calib.verified,
        }

        # Atomic write via temp + rename
        tmp = _CALIBRATION_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        tmp.replace(_CALIBRATION_FILE)
        logger.info("Calibration saved to %s", _CALIBRATION_FILE)
    except OSError as exc:
        logger.warning("Calibration save failed: %s", exc)


def is_calibration_current(monitors: list[MonitorInfo] | None = None) -> bool:
    """Check if the persisted calibration matches the current display config.

    Args:
        monitors: Pre-detected monitors. If None, detects fresh.

    Returns:
        True if calibration file matches current layout.
    """
    if monitors is None:
        monitors = detect_monitors()

    mss_mons = _get_mss_monitors()
    current_hash = _compute_config_hash(mss_mons)

    calib = load_calibration()
    if calib is None:
        return False

    return calib.config_hash == current_hash


def run_calibration_probe(
    monitors: list[MonitorInfo] | None = None,
    force: bool = False,
) -> CalibrationData:
    """Run a calibration probe for the current display configuration.

    If a calibration already exists for this config and force=False,
    returns the existing calibration without re-running.

    The probe:
      1. Detects monitors and DPI scaling
      2. Checks if calibration exists for this config
      3. If new or forced, saves calibration with detected scaling
      4. Returns the calibration data

    Args:
        monitors: Pre-detected monitors. If None, detects fresh.
        force: Force re-calibration even if config hasn't changed.

    Returns:
        CalibrationData for the current display configuration.
    """
    with _calib_lock:
        if monitors is None:
            monitors = detect_monitors()

        mss_mons = _get_mss_monitors()
        current_hash = _compute_config_hash(mss_mons)

        # Check existing calibration
        existing = load_calibration()
        if existing and existing.config_hash == current_hash and not force:
            logger.info("Calibration current (hash=%s), skipping probe", current_hash)
            return existing

        # Build new calibration
        calib_monitors = []
        for m in monitors:
            if m.index == 0:
                continue  # Skip virtual desktop
            calib_monitors.append(
                {
                    "index": m.index,
                    "x": m.x,
                    "y": m.y,
                    "width": m.width,
                    "height": m.height,
                    "scale_factor": m.scale_factor,
                    "is_primary": m.is_primary,
                    "device_id": m.device_id,
                    "logical_width": m.logical_width,
                    "logical_height": m.logical_height,
                }
            )

        calib = CalibrationData(
            config_hash=current_hash,
            monitors=calib_monitors,
            calibrated_at=time.time(),
            verified=False,
        )

        save_calibration(calib)
        logger.info(
            "Calibration probe complete: %d monitors, hash=%s",
            len(calib_monitors),
            current_hash,
        )

        return calib


# ---------------------------------------------------------------------------
# Global monitor cache — refresh on config change
# ---------------------------------------------------------------------------

_cached_monitors: list[MonitorInfo] = []
_cached_config_hash: str = ""
_cache_timestamp: float = 0.0
_MONITOR_CACHE_TTL = 30.0  # seconds


def get_monitors() -> list[MonitorInfo]:
    """Get the cached monitor list, refreshing if stale or config changed.

    Thread-safe. Refreshes if:
      - Never queried before
      - TTL expired (>30s since last check)
      - Display configuration changed (hash mismatch)

    Returns:
        List of MonitorInfo for all monitors.
    """
    global _cached_monitors, _cached_config_hash, _cache_timestamp

    with _calib_lock:
        now = time.monotonic()
        elapsed = now - _cache_timestamp if _cache_timestamp else float("inf")

        # Check if we need to refresh
        if elapsed > _MONITOR_CACHE_TTL or not _cached_monitors:
            mss_mons = _get_mss_monitors()
            current_hash = _compute_config_hash(mss_mons)

            if current_hash != _cached_config_hash or not _cached_monitors:
                _cached_monitors = detect_monitors()
                _cached_config_hash = current_hash
                logger.info(
                    "Monitor cache refreshed: %d monitors, hash=%s",
                    len(_cached_monitors),
                    current_hash,
                )
            else:
                logger.debug("Monitor cache TTL refresh, config unchanged")

            _cache_timestamp = now

    return _cached_monitors


def clear_monitor_cache() -> None:
    """Clear the monitor cache. Useful for testing or after display changes."""
    global _cached_monitors, _cached_config_hash, _cache_timestamp
    with _calib_lock:
        _cached_monitors = []
        _cached_config_hash = ""
        _cache_timestamp = 0.0


def transform_action_coordinates(
    action: dict[str, Any],
    monitors: list[MonitorInfo] | None = None,
) -> dict[str, Any]:
    """Transform all coordinates in an action dict from physical to logical.

    Handles click, double_click, right_click, drag, and any other action
    with x/y or from_x/from_y/to_x/to_y coordinates.

    Args:
        action: LLM action dict with coordinates in physical (screenshot) space.
        monitors: Pre-detected monitors. If None, uses cached.

    Returns:
        New action dict with coordinates transformed to logical space.
    """
    if monitors is None:
        monitors = get_monitors()

    # Check if any scaling is needed (skip if all monitors are 1.0)
    needs_scaling = any(m.scale_factor != 1.0 for m in monitors if m.index > 0)
    if not needs_scaling:
        return action

    result = dict(action)
    coord_keys = {"x", "y"}
    from_to_keys = {"from_x", "from_y", "to_x", "to_y"}

    # Simple x/y actions (click, double_click, right_click, etc.)
    if coord_keys & result.keys():
        x = result.get("x", 0)
        y = result.get("y", 0)
        lx, ly = physical_to_logical(x, y, monitors)
        if "x" in result:
            result["x"] = lx
        if "y" in result:
            result["y"] = ly

    # Drag actions (from_x, from_y, to_x, to_y)
    if from_to_keys & result.keys():
        fx = result.get("from_x", 0)
        fy = result.get("from_y", 0)
        tx = result.get("to_x", 0)
        ty = result.get("to_y", 0)

        lfx, lfy = physical_to_logical(fx, fy, monitors)
        ltx, lty = physical_to_logical(tx, ty, monitors)

        if "from_x" in result:
            result["from_x"] = lfx
        if "from_y" in result:
            result["from_y"] = lfy
        if "to_x" in result:
            result["to_x"] = ltx
        if "to_y" in result:
            result["to_y"] = lty

    return result
