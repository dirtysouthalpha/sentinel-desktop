"""Screen sensory agent — watches the desktop for changes.

Captures screenshots at intervals, compares them to detect visual changes,
and emits events when something on screen changes significantly.
Uses the existing core.platform.screen abstraction so it works on any OS.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScreenEvent:
    """Emitted when the screen changes."""

    timestamp: float
    change_percent: float
    changed: bool
    region: tuple[int, int, int, int] | None = None  # bounding box of change
    description: str = ""


@dataclass
class ScreenConfig:
    """Configuration for the screen agent."""

    capture_interval_seconds: float = 5.0
    change_threshold: float = 0.05  # 5% of pixels must differ to trigger event
    max_fps: float = 1.0  # max captures per second
    enabled: bool = True


class ScreenAgent:
    """Continuously monitors the desktop for visual changes."""

    def __init__(self, config: ScreenConfig | None = None) -> None:
        self._config = config or ScreenConfig()
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_hash: str = ""
        self._last_image: Any = None
        self._callbacks: list[Callable[[ScreenEvent], None]] = []

    def on_change(self, callback: Callable[[ScreenEvent], None]) -> None:
        """Register a callback for screen change events."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start the screen monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="sensory-screen")
        self._thread.start()
        logger.info("Screen agent started (interval=%ss)", self._config.capture_interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _capture_loop(self) -> None:
        while self._running:
            try:
                self._check_screen()
            except Exception as exc:
                logger.debug("Screen check failed: %s", exc)
            time.sleep(self._config.capture_interval_seconds)

    def _check_screen(self) -> None:
        from core.platform import platform
        screenshot = platform.screen.capture()
        if screenshot is None:
            return

        # Downscale and hash for fast comparison
        try:
            small = screenshot.convert("L").resize((64, 64))
            data = small.tobytes()
            current_hash = hashlib.md5(data, usedforsecurity=False).hexdigest()

            if self._last_hash and current_hash != self._last_hash:
                change_pct = self._estimate_change(screenshot)
                if change_pct >= self._config.change_threshold:
                    event = ScreenEvent(
                        timestamp=time.time(),
                        change_percent=change_pct,
                        changed=True,
                        description=f"Screen changed ({change_pct:.1%})",
                    )
                    self._emit(event)

            self._last_hash = current_hash
            self._last_image = screenshot
        except Exception as exc:
            logger.debug("Screen diff failed: %s", exc)

    def _estimate_change(self, current: Any) -> float:
        """Estimate percent of screen that changed (0.0 to 1.0)."""
        if self._last_image is None:
            return 0.0
        try:
            from PIL import ImageChops
            diff = ImageChops.difference(self._last_image.convert("RGB"), current.convert("RGB"))
            diff_gray = diff.convert("L")
            # Count non-zero pixels as changed
            changed_pixels = sum(1 for p in diff_gray.getdata() if p > 30)
            total_pixels = diff_gray.width * diff_gray.height
            return changed_pixels / total_pixels if total_pixels > 0 else 0.0
        except Exception:
            return 0.0

    def _emit(self, event: ScreenEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as exc:
                logger.error("Screen callback failed: %s", exc)

    @property
    def is_running(self) -> bool:
        return self._running

    def get_last_image(self) -> Any:
        return self._last_image


__all__ = ["ScreenEvent", "ScreenConfig", "ScreenAgent"]
