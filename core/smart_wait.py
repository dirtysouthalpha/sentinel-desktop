"""
Sentinel Desktop v2 — Visual-diff-based waiting.

Instead of fixed ``time.sleep(3)`` or ``wait(3)``, this module captures
screenshots and waits until the screen **actually** changes (or stops
changing).  Much more efficient for page loads, app launches, and
animations.

Thread-safe and cancelable via :class:`threading.Event`.

Typical usage::

    from core.smart_wait import SmartWait

    sw = SmartWait()

    # Wait for something to change (e.g. after clicking a link).
    result = sw.wait_for_change(timeout=10)
    if result.success:
        print(f"Screen changed after {result.elapsed:.1f}s")

    # Wait for the screen to settle (e.g. page finished loading).
    result = sw.wait_for_stable(timeout=15, stable_time=2.0)

    # Cancel an in-progress wait from another thread.
    sw.cancel()
"""

from __future__ import annotations

import logging
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from core.screenshot import capture_region, capture_screen

logger = logging.getLogger(__name__)

# Try to import numpy for fast pixel comparison; fall back to pure PIL.
try:
    import numpy as np  # type: ignore

    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

# Change-detection threshold per channel (0–255).  Pixels that differ by
# less than this on *every* channel are considered identical.
_CHANNEL_THRESHOLD = 30

# Downscale factor applied before comparison — trades a bit of precision
# for a large speed win (1/4 resolution = ~16× fewer pixels).
_DOWNSCALE = 4

# ---------------------------------------------------------------------------
# WaitResult
# ---------------------------------------------------------------------------


@dataclass
class WaitResult:
    """Result of a smart-wait operation.

    Attributes:
        success: Whether the wait condition was met before the timeout.
        elapsed: Wall-clock seconds elapsed during the wait.
        frames_checked: Number of screenshot frames captured and compared.
        change_score: Ratio of changed pixels (0.0 – 1.0).  For
            ``wait_for_change`` this is the score when change was first
            detected; for ``wait_for_stable`` it is the score of the last
            comparison before stability was confirmed.
        snapshot_path: Path to a PNG saved at the moment the condition was
            met, or ``None`` if the wait failed or snapshotting was skipped.
    """

    success: bool
    elapsed: float
    frames_checked: int
    change_score: float
    snapshot_path: str | None = field(default=None)


def _load_ocr_functions() -> tuple[object, object] | None:
    """Lazily import OCR helpers. Returns (ocr_image_fn, read_screen_fn) or None."""
    try:
        from core.ocr import _ocr_image, read_screen_text  # type: ignore[attr-defined]

        return _ocr_image, read_screen_text
    except ImportError as exc:
        logger.warning("OCR unavailable — wait_for_text cannot proceed: %s", exc)
        return None


def _fail(elapsed: float, frames: int, change_score: float = 0.0) -> WaitResult:
    """Return a failed WaitResult with no snapshot."""
    return WaitResult(
        success=False,
        elapsed=elapsed,
        frames_checked=frames,
        change_score=change_score,
        snapshot_path=None,
    )


# ---------------------------------------------------------------------------
# Visual diff helpers
# ---------------------------------------------------------------------------


def _crop_to_region(region: tuple[int, int, int, int] | None) -> Image.Image | None:
    """Capture a screenshot, optionally restricted to *region* (x, y, w, h)."""
    try:
        if region is not None:
            x, y, w, h = region
            return capture_region(x, y, w, h)
        return capture_screen()
    except (OSError, RuntimeError) as exc:
        logger.warning("Screenshot capture failed: %s", exc)
        return None


def _downsample(img: Image.Image, factor: int = _DOWNSCALE) -> Image.Image:
    """Shrink an image by *factor* using nearest-neighbour for speed."""
    w, h = img.size
    new_w = max(1, w // factor)
    new_h = max(1, h // factor)
    return img.resize((new_w, new_h), Image.NEAREST)


def _compute_change_score(
    img_a: Image.Image,
    img_b: Image.Image,
) -> float:
    """Return a 0–1 score indicating how much two images differ.

    * 0.0 means images are identical (within per-channel threshold).
    * 1.0 means every pixel differs beyond the threshold on at least one
      channel.

    Uses numpy when available for speed; otherwise falls back to a pure-PIL
    implementation.
    """
    # Ensure same size — if sizes differ, treat as fully changed.
    if img_a.size != img_b.size:
        return 1.0

    if _HAS_NUMPY:
        arr_a = np.asarray(img_a.convert("RGB"), dtype=np.int16)
        arr_b = np.asarray(img_b.convert("RGB"), dtype=np.int16)
        diff = np.abs(arr_a - arr_b)
        # A pixel is "changed" if *any* channel exceeds the threshold.
        changed_mask = np.any(diff > _CHANNEL_THRESHOLD, axis=2)
        if changed_mask.size == 0:
            return 0.0
        return float(np.count_nonzero(changed_mask)) / float(changed_mask.size)

    # Pure-PIL fallback — slower but dependency-free.
    a = img_a.convert("RGB")
    b = img_b.convert("RGB")
    pixels_a = a.load()
    pixels_b = b.load()
    w, h = a.size
    total = w * h
    if total == 0:
        return 0.0
    changed = 0
    for y in range(h):
        for x in range(w):
            pa = pixels_a[x, y]
            pb = pixels_b[x, y]
            if (
                abs(pa[0] - pb[0]) > _CHANNEL_THRESHOLD
                or abs(pa[1] - pb[1]) > _CHANNEL_THRESHOLD
                or abs(pa[2] - pb[2]) > _CHANNEL_THRESHOLD
            ):
                changed += 1
    return changed / total


def _save_snapshot(img: Image.Image, prefix: str = "smart_wait") -> str:
    """Save *img* to a temp file and return the path."""
    tmp_dir = Path(tempfile.gettempdir())
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    path = tmp_dir / filename
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        img.save(str(path), format="PNG")
        logger.debug("Snapshot saved: %s", path)
    except (OSError, RuntimeError) as exc:
        logger.warning("Failed to save snapshot: %s", exc)
        return ""
    return str(path)


def _eval_change_frame(
    baseline_small: Any,
    prev_small: Any,
    current: Image.Image,
    start: float,
    frames: int,
) -> tuple[Any, WaitResult | None]:
    """Downsample *current*, score against baseline and prev; return (new_prev, result_or_None)."""
    current_small = _downsample(current)
    # Check both: cumulative change from baseline AND per-frame change.
    # This catches both sudden jumps and gradual drifts.
    cumulative_score = _compute_change_score(baseline_small, current_small)
    frame_score = _compute_change_score(prev_small, current_small)
    score = max(cumulative_score, frame_score)
    if score > 0.0:
        snap_path = _save_snapshot(current, prefix="change")
        return current_small, WaitResult(
            success=True,
            elapsed=time.monotonic() - start,
            frames_checked=frames,
            change_score=score,
            snapshot_path=snap_path or None,
        )
    return current_small, None


def _build_match_result(
    template_path: str,
    confidence: float,
    start: float,
    frames: int,
) -> WaitResult | None:
    """Try template matching; return a WaitResult on match or None on miss/error."""
    from core.screenshot import find_template

    try:
        pos = find_template(template_path, confidence)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Template matching failed: %s", exc)
        pos = None
    if pos is None:
        return None
    try:
        current = capture_screen()
    except (OSError, RuntimeError) as exc:
        logger.warning("Capture for match snapshot failed: %s", exc)
        current = None
    snap_path = _save_snapshot(current, prefix="match") if current is not None else None
    return WaitResult(
        success=True,
        elapsed=time.monotonic() - start,
        frames_checked=frames,
        change_score=confidence,
        snapshot_path=snap_path or None,
    )


# ---------------------------------------------------------------------------
# SmartWait
# ---------------------------------------------------------------------------


class SmartWait:
    """Visual-diff-based waiting engine.

    Provides several wait strategies, all based on comparing screenshots
    over time:

    * :meth:`wait_for_change` — polls until pixels change.
    * :meth:`wait_for_stable` — polls until pixels **stop** changing.
    * :meth:`wait_for_match` — polls until a template image appears.
    * :meth:`wait_for_text` — polls until OCR detects specific text.
    * :meth:`wait_for_color` — polls until a single pixel matches a colour.

    All methods are thread-safe and can be canceled from another thread
    by calling :meth:`cancel`.

    Example::

        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.3)
        # ... from another thread ...
        sw.cancel()
    """

    def __init__(self) -> None:
        """Initialize the waiter with a clean (non-cancelled) state."""
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Signal an in-progress wait to abort and return immediately.

        Safe to call from any thread.  The running wait method will return
        a ``WaitResult`` with ``success=False``.
        """
        self._cancel_event.set()
        logger.debug("SmartWait cancel signalled")

    def _reset_cancel(self) -> None:
        """Clear the cancel flag so a new wait can proceed."""
        self._cancel_event.clear()

    def _cancelled(self) -> bool:
        """Return ``True`` if the wait has been cancelled via :meth:`cancel`."""
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    # Core capture helper
    # ------------------------------------------------------------------

    def _capture(self, region: tuple[int, int, int, int] | None) -> Image.Image | None:
        """Capture a frame, possibly restricted to *region*."""
        return _crop_to_region(region)

    def _loop_check(
        self, start: float, timeout: float, frames: int, extra_score: float = 0.0
    ) -> WaitResult | None:
        """Return a failure WaitResult if the loop should stop, else None.

        Centralises the timeout and cancellation checks shared by all
        ``wait_for_*`` polling loops.
        """
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return _fail(elapsed, frames, extra_score)
        if self._cancelled():
            return _fail(time.monotonic() - start, frames, extra_score)
        return None

    # ------------------------------------------------------------------
    # wait_for_change
    # ------------------------------------------------------------------

    def wait_for_change(
        self,
        timeout: float = 10,
        interval: float = 0.3,
        region: tuple[int, int, int, int] | None = None,
    ) -> WaitResult:
        """Wait until the screen (or a region) visually changes.

        Captures a baseline screenshot, then repeatedly captures and
        compares until the change score exceeds the channel threshold or
        the timeout is reached.

        Args:
            timeout: Maximum seconds to wait.
            interval: Seconds between screenshot polls.
            region: Optional ``(x, y, w, h)`` sub-region to watch.

        Returns:
            A :class:`WaitResult` indicating whether change was detected.
        """
        self._reset_cancel()
        start = time.monotonic()
        frames = 0

        baseline = self._capture(region)
        if baseline is None:
            return _fail(time.monotonic() - start, frames)
        baseline_small = _downsample(baseline)
        prev_small = baseline_small
        frames += 1

        while True:
            abort = self._loop_check(start, timeout, frames)
            if abort is not None:
                return abort
            time.sleep(interval)
            current = self._capture(region)
            if current is None:
                continue
            frames += 1
            prev_small, result = _eval_change_frame(baseline_small, prev_small, current, start, frames)
            if result is not None:
                return result

    # ------------------------------------------------------------------
    # wait_for_stable
    # ------------------------------------------------------------------

    def wait_for_stable(
        self,
        timeout: float = 10,
        stable_time: float = 1.5,
        interval: float = 0.3,
        region: tuple[int, int, int, int] | None = None,
    ) -> WaitResult:
        """Wait until the screen (or a region) stops changing.

        Continuously captures screenshots.  When *stable_time* seconds
        pass with no detected change, the wait succeeds.  Useful for
        waiting until a page finishes loading.

        Args:
            timeout: Maximum seconds to wait overall.
            stable_time: Seconds of no-change required to consider the
                screen stable.
            interval: Seconds between screenshot polls.
            region: Optional ``(x, y, w, h)`` sub-region to watch.

        Returns:
            A :class:`WaitResult`.  ``change_score`` is the score of the
            last comparison before stability was confirmed.
        """
        self._reset_cancel()
        start = time.monotonic()
        frames = 0
        last_change_time = time.monotonic()
        last_score = 0.0

        prev = self._capture(region)
        if prev is None:
            return _fail(time.monotonic() - start, frames, last_score)
        prev_small = _downsample(prev)
        frames += 1

        while True:
            abort = self._loop_check(start, timeout, frames, last_score)
            if abort is not None:
                return abort

            time.sleep(interval)
            current = self._capture(region)
            if current is None:
                continue
            current_small = _downsample(current)
            frames += 1

            score = _compute_change_score(prev_small, current_small)
            prev_small = current_small

            if score > 0.0:
                last_change_time = time.monotonic()
                last_score = score
            else:
                result = self._check_stable_duration(
                    current, start, frames, last_score, last_change_time, stable_time
                )
                if result is not None:
                    return result

    def _check_stable_duration(
        self,
        current: Image.Image,
        start: float,
        frames: int,
        last_score: float,
        last_change_time: float,
        stable_time: float,
    ) -> WaitResult | None:
        """Return a success WaitResult if the screen has been stable long enough, else None."""
        stable_for = time.monotonic() - last_change_time
        if stable_for >= stable_time:
            snap_path = _save_snapshot(current, prefix="stable")
            return WaitResult(
                success=True,
                elapsed=time.monotonic() - start,
                frames_checked=frames,
                change_score=last_score,
                snapshot_path=snap_path or None,
            )
        return None

    # ------------------------------------------------------------------
    # wait_for_match
    # ------------------------------------------------------------------

    def wait_for_match(
        self,
        template_path: str,
        timeout: float = 10,
        confidence: float = 0.8,
        interval: float = 0.5,
    ) -> WaitResult:
        """Wait until a template image appears on screen.

        Uses :func:`core.screenshot.find_template` for the actual
        matching (requires ``opencv-python`` and ``numpy``).

        Args:
            template_path: Path to the template image file on disk.
            timeout: Maximum seconds to wait.
            confidence: Minimum match confidence (0.0–1.0).
            interval: Seconds between polls.

        Returns:
            A :class:`WaitResult`.  ``change_score`` is set to the match
            confidence on success.
        """
        self._reset_cancel()
        start = time.monotonic()
        frames = 0

        while True:
            abort = self._loop_check(start, timeout, frames)
            if abort is not None:
                return abort
            frames += 1
            result = _build_match_result(template_path, confidence, start, frames)
            if result is not None:
                return result
            time.sleep(interval)

    # ------------------------------------------------------------------
    # wait_for_text
    # ------------------------------------------------------------------

    def wait_for_text(
        self,
        text: str,
        timeout: float = 10,
        interval: float = 0.5,
        region: tuple[int, int, int, int] | None = None,
    ) -> WaitResult:
        """Wait until specific text appears on screen (via OCR).

        Uses :mod:`core.ocr` for text recognition.  Falls back
        gracefully — if OCR is unavailable the method immediately
        returns an unsuccessful result.

        Args:
            text: The string to look for (case-insensitive substring).
            timeout: Maximum seconds to wait.
            interval: Seconds between polls.
            region: Optional ``(x, y, w, h)`` to restrict the OCR region.

        Returns:
            A :class:`WaitResult`.
        """
        self._reset_cancel()
        start = time.monotonic()
        needle = text.strip().lower()
        if not needle:
            return _fail(0.0, 0)

        ocr_fns = _load_ocr_functions()
        if ocr_fns is None:
            return _fail(0.0, 0)

        return self._poll_for_text(needle, timeout, interval, region, start, *ocr_fns)

    def _poll_for_text(
        self,
        needle: str,
        timeout: float,
        interval: float,
        region: tuple[int, int, int, int] | None,
        start: float,
        ocr_image_fn: object,
        read_screen_fn: object,
    ) -> WaitResult:
        """Poll until *needle* is found in the OCR output or time runs out."""
        frames = 0
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return _fail(elapsed, frames)
            if self._cancelled():
                return _fail(time.monotonic() - start, frames)

            frames += 1
            try:
                if region is not None:
                    img = self._capture(region)
                    ocr_text = ocr_image_fn(img).lower()  # type: ignore[operator]
                else:
                    ocr_text = read_screen_fn().lower()  # type: ignore[operator]
            except (OSError, RuntimeError) as exc:
                logger.debug("OCR capture failed: %s", exc)
                ocr_text = ""

            if needle in ocr_text:
                try:
                    snap = self._capture(region)
                except (OSError, RuntimeError) as exc:
                    logger.debug("Post-match snapshot capture failed: %s", exc)
                    snap = None
                snap_path = _save_snapshot(snap, prefix="text") if snap is not None else None
                return WaitResult(
                    success=True,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=1.0,
                    snapshot_path=snap_path or None,
                )

            time.sleep(interval)

    # ------------------------------------------------------------------
    # wait_for_color
    # ------------------------------------------------------------------

    def wait_for_color(
        self,
        x: int,
        y: int,
        target_rgb: tuple[int, int, int],
        tolerance: int = 30,
        timeout: float = 10,
    ) -> WaitResult:
        """Wait until a specific pixel reaches a target colour.

        Repeatedly samples the pixel at screen coordinates ``(x, y)``
        and compares it to ``target_rgb``.  Each channel must be within
        *tolerance* for the match to succeed.

        Args:
            x: Screen X coordinate.
            y: Screen Y coordinate.
            target_rgb: ``(R, G, B)`` target colour (0–255 each).
            tolerance: Per-channel tolerance (0–255).
            timeout: Maximum seconds to wait.

        Returns:
            A :class:`WaitResult`.  ``change_score`` is set to ``1.0``
            on success.
        """
        self._reset_cancel()
        start = time.monotonic()
        frames = 0
        while True:
            abort = self._loop_check(start, timeout, frames)
            if abort is not None:
                return abort
            frames += 1
            pixel = self._sample_pixel(x, y)
            if pixel is None:
                time.sleep(0.1)
                continue
            if all(abs(a - b) <= tolerance for a, b in zip(pixel, target_rgb, strict=False)):
                snap_path = self._capture_color_match_snapshot(x, y)
                return WaitResult(
                    success=True,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=1.0,
                    snapshot_path=snap_path,
                )
            time.sleep(0.1)

    @staticmethod
    def _sample_pixel(x: int, y: int) -> tuple[int, int, int] | None:
        """Capture a 2×2 region at (x, y) and return the top-left RGB, or None on error.

        Uses a 2×2 margin because some backends don't support truly 1×1 captures.
        """
        try:
            sample = capture_region(x, y, 2, 2)
            return sample.getpixel((0, 0))[:3]
        except (OSError, RuntimeError) as exc:
            logger.debug("Pixel capture failed at (%d, %d): %s", x, y, exc)
            return None

    @staticmethod
    def _capture_color_match_snapshot(x: int, y: int) -> str | None:
        """Capture a 100×100 context snapshot around a matched pixel. Returns path or None."""
        try:
            snap = capture_region(max(0, x - 50), max(0, y - 50), 100, 100)
        except (OSError, RuntimeError) as exc:
            logger.debug("Color match snapshot capture failed: %s", exc)
            return None
        return _save_snapshot(snap, prefix="color") or None
