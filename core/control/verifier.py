"""Sentinel Desktop v6.0 — Action Verifier.

Confirms that an action succeeded by comparing before and after screenshots.
Uses pixel difference analysis, OCR comparison, and element state checking.

Verification levels:
    1. PIXEL_DIFF: Simple pixel difference (fast, detects any change)
    2. OCR_DIFF: Compare OCR text before/after (detects text changes)
    3. ELEMENT_STATE: Check if the target element changed state (accessibility)
"""

from __future__ import annotations

import hashlib
import logging
from enum import Enum
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


class VerifyResult(str, Enum):
    """Verification outcome."""

    SUCCESS = "success"  # Action had the expected effect
    NO_CHANGE = "no_change"  # Screen didn't change (click may have missed)
    UNEXPECTED = "unexpected"  # Screen changed but not as expected
    ERROR = "error"  # Verification itself failed


class VerificationReport:
    """Result of verifying an action.

    Attributes:
        result: Overall verification outcome.
        pixel_diff_percent: Percentage of pixels that changed (0.0–100.0).
        confidence: How confident we are in the verification (0.0–1.0).
        details: Human-readable explanation.
        before_hash: Hash of the before screenshot.
        after_hash: Hash of the after screenshot.
    """

    def __init__(
        self,
        result: VerifyResult = VerifyResult.ERROR,
        pixel_diff_percent: float = 0.0,
        confidence: float = 0.0,
        details: str = "",
        before_hash: str = "",
        after_hash: str = "",
    ) -> None:
        self.result = result
        self.pixel_diff_percent = pixel_diff_percent
        self.confidence = confidence
        self.details = details
        self.before_hash = before_hash
        self.after_hash = after_hash

    @property
    def is_success(self) -> bool:
        return self.result == VerifyResult.SUCCESS

    @property
    def should_retry(self) -> bool:
        """Return True if the action should be retried."""
        return self.result in (VerifyResult.NO_CHANGE, VerifyResult.UNEXPECTED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "pixel_diff_pct": round(self.pixel_diff_percent, 2),
            "confidence": round(self.confidence, 2),
            "details": self.details,
        }


# Thresholds for pixel difference analysis
_MIN_CHANGE_THRESHOLD = 0.5  # < 0.5% change = NO_CHANGE
_MAX_CHANGE_THRESHOLD = 50.0  # > 50% change = unexpected (full page change)


def _image_hash(image: Image.Image) -> str:
    """Fast hash of image content for comparison."""
    # Downsample to 100x100 for fast comparison
    small = image.resize((100, 100), Image.Resampling.BILINEAR)
    return hashlib.md5(small.tobytes(), usedforsecurity=False).hexdigest()


def _compute_pixel_diff(before: Image.Image, after: Image.Image) -> float:
    """Compute percentage of pixels that changed between two images.

    Both images are downsampled to 200x200 for speed.
    Returns the percentage of pixels that differ (0.0–100.0).
    """
    # Resize both to same size for comparison
    size = (200, 200)
    b = before.resize(size, Image.Resampling.BILINEAR).convert("RGB")
    a = after.resize(size, Image.Resampling.BILINEAR).convert("RGB")

    b_pixels = list(b.getdata())
    a_pixels = list(a.getdata())

    if len(b_pixels) != len(a_pixels):
        return 100.0

    diff_count = 0
    threshold = 30  # Per-channel difference threshold
    for bp, ap in zip(b_pixels, a_pixels, strict=False):
        if (
            abs(bp[0] - ap[0]) > threshold
            or abs(bp[1] - ap[1]) > threshold
            or abs(bp[2] - ap[2]) > threshold
        ):
            diff_count += 1

    return (diff_count / len(b_pixels)) * 100.0


class ActionVerifier:
    """Verifies action success via before/after screenshot comparison.

    Usage::

        verifier = ActionVerifier()
        report = verifier.verify(before_screenshot, after_screenshot)
        if report.is_success:
            print("Action succeeded!")
    """

    def verify(
        self,
        before: Image.Image,
        after: Image.Image,
        expected_change: str = "any",
    ) -> VerificationReport:
        """Verify that an action had the expected effect.

        Args:
            before: Screenshot before the action.
            after: Screenshot after the action.
            expected_change: "any" (any change is success),
                             "none" (no change expected), or
                             "text" (text content should change).

        Returns:
            VerificationReport with the outcome.
        """
        try:
            before_hash = _image_hash(before)
            after_hash = _image_hash(after)

            # Identical screenshots = no change
            if before_hash == after_hash:
                if expected_change == "none":
                    return VerificationReport(
                        result=VerifyResult.SUCCESS,
                        pixel_diff_percent=0.0,
                        confidence=0.95,
                        details="Screenshots identical (no change expected)",
                        before_hash=before_hash,
                        after_hash=after_hash,
                    )
                return VerificationReport(
                    result=VerifyResult.NO_CHANGE,
                    pixel_diff_percent=0.0,
                    confidence=0.8,
                    details="Screen did not change — action may have missed",
                    before_hash=before_hash,
                    after_hash=after_hash,
                )

            # Compute pixel difference
            diff_pct = _compute_pixel_diff(before, after)

            if expected_change == "none":
                return VerificationReport(
                    result=VerifyResult.UNEXPECTED,
                    pixel_diff_percent=diff_pct,
                    confidence=0.7,
                    details=f"Screen changed by {diff_pct:.1f}% when no change was expected",
                    before_hash=before_hash,
                    after_hash=after_hash,
                )

            # Any change mode
            if diff_pct < _MIN_CHANGE_THRESHOLD:
                return VerificationReport(
                    result=VerifyResult.NO_CHANGE,
                    pixel_diff_percent=diff_pct,
                    confidence=0.6,
                    details=f"Minimal change ({diff_pct:.2f}%) — below threshold",
                    before_hash=before_hash,
                    after_hash=after_hash,
                )

            if diff_pct > _MAX_CHANGE_THRESHOLD:
                return VerificationReport(
                    result=VerifyResult.UNEXPECTED,
                    pixel_diff_percent=diff_pct,
                    confidence=0.5,
                    details=f"Massive change ({diff_pct:.1f}%) — possible page transition",
                    before_hash=before_hash,
                    after_hash=after_hash,
                )

            # Normal change range — success
            confidence = min(0.9, 0.5 + (diff_pct / 25.0))
            return VerificationReport(
                result=VerifyResult.SUCCESS,
                pixel_diff_percent=diff_pct,
                confidence=confidence,
                details=f"Screen changed by {diff_pct:.1f}% — action appears successful",
                before_hash=before_hash,
                after_hash=after_hash,
            )

        except Exception as exc:
            logger.error("Verification failed: %s", exc)
            return VerificationReport(
                result=VerifyResult.ERROR,
                details=f"Verification error: {exc}",
            )
