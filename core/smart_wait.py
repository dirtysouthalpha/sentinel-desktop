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
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field

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


# ---------------------------------------------------------------------------
# Visual diff helpers
# ---------------------------------------------------------------------------


def _crop_to_region(region: tuple[int, int, int, int] | None) -> Image.Image | None:
    """Capture a screenshot, optionally restricted to *region* (x, y, w, h)."""
    if region is not None:
        x, y, w, h = region
        return capture_region(x, y, w, h)
    return capture_screen()


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
    tmp_dir = tempfile.gettempdir()
    os.makedirs(tmp_dir, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    path = os.path.join(tmp_dir, filename)
    try:
        img.save(path, format="PNG")
        logger.debug("Snapshot saved: %s", path)
    except Exception as exc:
        logger.warning("Failed to save snapshot: %s", exc)
        return ""
    return path


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
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    # Core capture helper
    # ------------------------------------------------------------------

    def _capture(self, region: tuple[int, int, int, int] | None) -> Image.Image:
        """Capture a frame, possibly restricted to *region*."""
        return _crop_to_region(region)

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

        # Capture the initial baseline and track cumulative change from it.
        baseline = self._capture(region)
        baseline_small = _downsample(baseline)
        prev_small = baseline_small
        frames += 1

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return WaitResult(
                    success=False,
                    elapsed=elapsed,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )
            if self._cancelled():
                return WaitResult(
                    success=False,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )

            time.sleep(interval)
            current = self._capture(region)
            current_small = _downsample(current)
            frames += 1

            # Check both: cumulative change from baseline AND per-frame change.
            # This catches both sudden jumps and gradual drifts.
            cumulative_score = _compute_change_score(baseline_small, current_small)
            frame_score = _compute_change_score(prev_small, current_small)
            prev_small = current_small

            score = max(cumulative_score, frame_score)
            if score > 0.0:
                snap_path = _save_snapshot(current, prefix="change")
                return WaitResult(
                    success=True,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=score,
                    snapshot_path=snap_path or None,
                )

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
        prev_small = _downsample(prev)
        frames += 1

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return WaitResult(
                    success=False,
                    elapsed=elapsed,
                    frames_checked=frames,
                    change_score=last_score,
                    snapshot_path=None,
                )
            if self._cancelled():
                return WaitResult(
                    success=False,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=last_score,
                    snapshot_path=None,
                )

            time.sleep(interval)
            current = self._capture(region)
            current_small = _downsample(current)
            frames += 1

            score = _compute_change_score(prev_small, current_small)
            prev_small = current_small

            if score > 0.0:
                # Screen is still changing — reset the stability clock.
                last_change_time = time.monotonic()
                last_score = score
            else:
                # No change since last frame.  Have we been stable long
                # enough?
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

        # Import here to avoid hard dependency at module level.
        from core.screenshot import find_template

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return WaitResult(
                    success=False,
                    elapsed=elapsed,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )
            if self._cancelled():
                return WaitResult(
                    success=False,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )

            frames += 1
            pos = find_template(template_path, confidence)
            if pos is not None:
                current = capture_screen()
                snap_path = _save_snapshot(current, prefix="match")
                return WaitResult(
                    success=True,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=confidence,
                    snapshot_path=snap_path or None,
                )

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
        frames = 0
        needle = text.strip().lower()
        if not needle:
            return WaitResult(
                success=False,
                elapsed=0.0,
                frames_checked=0,
                change_score=0.0,
                snapshot_path=None,
            )

        # Lazy import — OCR is optional.
        try:
            from core.ocr import _ocr_image, read_screen_text  # type: ignore[attr-defined]

            _ocr_available = True
        except ImportError as exc:
            logger.debug("OCR import unavailable: %s", exc)
            _ocr_available = False

        if not _ocr_available:
            logger.warning("OCR unavailable — wait_for_text cannot proceed")
            return WaitResult(
                success=False,
                elapsed=0.0,
                frames_checked=0,
                change_score=0.0,
                snapshot_path=None,
            )

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return WaitResult(
                    success=False,
                    elapsed=elapsed,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )
            if self._cancelled():
                return WaitResult(
                    success=False,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )

            frames += 1
            try:
                if region is not None:
                    img = self._capture(region)
                    ocr_text = _ocr_image(img).lower()
                else:
                    ocr_text = read_screen_text().lower()
            except Exception as exc:
                logger.debug("OCR capture failed: %s", exc)
                ocr_text = ""

            if needle in ocr_text:
                snap = self._capture(region)
                snap_path = _save_snapshot(snap, prefix="text")
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

        # We use a tiny 1×1 capture via capture_region for efficiency.
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return WaitResult(
                    success=False,
                    elapsed=elapsed,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )
            if self._cancelled():
                return WaitResult(
                    success=False,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=0.0,
                    snapshot_path=None,
                )

            frames += 1
            try:
                # Capture a 1×1 region at (x, y).  We add a small
                # margin (e.g. 2×2) and sample the centre pixel because
                # some backends don't support truly 1×1 captures well.
                sample = capture_region(x, y, 2, 2)
                pixel = sample.getpixel((0, 0))[:3]
            except Exception as exc:
                logger.debug("Pixel capture failed at (%d, %d): %s", x, y, exc)
                time.sleep(0.1)
                continue

            r, g, b = pixel
            tr, tg, tb = target_rgb
            if abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance:
                # Save a slightly larger snapshot for context.
                snap = capture_region(max(0, x - 50), max(0, y - 50), 100, 100)
                snap_path = _save_snapshot(snap, prefix="color")
                return WaitResult(
                    success=True,
                    elapsed=time.monotonic() - start,
                    frames_checked=frames,
                    change_score=1.0,
                    snapshot_path=snap_path or None,
                )

            time.sleep(0.1)
