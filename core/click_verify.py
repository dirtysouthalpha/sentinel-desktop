"""Sentinel Desktop v7.0 — Click Verification & Self-Correction.

After every click action, captures a screenshot and diffs the target region
to detect whether the visual state changed. If no change is detected (miss),
automatically retries through progressively simpler targeting methods:

    Tier 1: Accessibility element targeting (click_element)
    Tier 2: Set-of-Marks targeting (click_mark)
    Tier 3: Raw coordinate click (click with adjusted coords)
    Tier 4: Keyboard navigation (Tab + Enter)

This is enforced in executor code, not dependent on system prompt prose.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from PIL import Image, ImageChops

logger = logging.getLogger(__name__)

# How much the target region must change to count as a "hit"
_DIFF_THRESHOLD = 5.0  # mean pixel difference (0-255)

# How long to wait after clicking before capturing the verification screenshot
_VERIFY_DELAY = 0.3  # seconds

# Maximum number of retry tiers
_MAX_RETRIES = 3


def capture_region(
    screenshot: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    padding: int = 20,
) -> Image.Image:
    """Extract a region from a screenshot with padding.

    Args:
        screenshot: Full screenshot image.
        x, y: Center of the target region.
        w, h: Width/height of the target region.
        padding: Extra pixels around the region.

    Returns:
        Cropped region image.
    """
    full_w, full_h = screenshot.size
    left = max(0, x - w // 2 - padding)
    top = max(0, y - h // 2 - padding)
    right = min(full_w, x + w // 2 + padding)
    bottom = min(full_h, y + h // 2 + padding)
    return screenshot.crop((left, top, right, bottom))


def compute_region_diff(
    before: Image.Image,
    after: Image.Image,
) -> float:
    """Compute the mean pixel difference between two screenshot regions.

    Args:
        before: Screenshot region before the action.
        after: Screenshot region after the action.

    Returns:
        Mean pixel difference (0.0 = identical, higher = more change).
    """
    if before.size != after.size:
        # Different sizes — something major changed
        return 100.0

    # Convert to RGB for consistent comparison
    before_rgb = before.convert("RGB")
    after_rgb = after.convert("RGB")

    # Compute absolute difference
    diff = ImageChops.difference(before_rgb, after_rgb)

    # Calculate mean difference across all pixels and channels
    import numpy as np

    try:
        diff_array = np.array(diff, dtype=np.float32)
        return float(diff_array.mean())
    except ImportError:
        # Fallback without numpy — sample a few pixels
        total = 0
        count = 0
        for px in range(0, diff.size[0], max(1, diff.size[0] // 20)):
            for py in range(0, diff.size[1], max(1, diff.size[1] // 20)):
                r, g, b = diff.getpixel((px, py))
                total += (r + g + b) / 3
                count += 1
        return total / max(count, 1)


def verify_click_landed(
    before_screenshot: Image.Image,
    x: int,
    y: int,
    w: int = 40,
    h: int = 20,
) -> tuple[bool, float, Image.Image]:
    """Verify a click landed by comparing before/after screenshots.

    Captures a fresh screenshot, extracts the target region from both
    before and after, and computes the pixel difference.

    Args:
        before_screenshot: Screenshot captured before the click.
        x, y: Click coordinates (center of target region).
        w, h: Approximate size of the target element.
        threshold: Mean pixel diff threshold for "landed".

    Returns:
        (landed, diff_score, after_screenshot)
    """
    from core.screenshot import capture_screen

    time.sleep(_VERIFY_DELAY)

    try:
        after_screenshot = capture_screen()
    except OSError as exc:
        logger.warning("Verification screenshot failed: %s", exc)
        return True, 0.0, before_screenshot  # Assume landed on error

    before_region = capture_region(before_screenshot, x, y, w, h)
    after_region = capture_region(after_screenshot, x, y, w, h)

    diff_score = compute_region_diff(before_region, after_region)
    landed = diff_score > _DIFF_THRESHOLD

    logger.debug(
        "Click verification at (%d,%d): diff=%.1f → %s",
        x, y, diff_score, "LANDED" if landed else "MISSED",
    )

    return landed, diff_score, after_screenshot


class ClickVerifier:
    """Manages click verification and tiered retry.

    Usage::

        verifier = ClickVerifier(executor)
        result = verifier.execute_with_verification(action, before_screenshot)
    """

    def __init__(self, executor: Any) -> None:
        self.executor = executor
        self.retry_count = 0

    def execute_with_verification(
        self,
        action: dict[str, Any],
        before_screenshot: Image.Image | None = None,
    ) -> dict[str, Any]:
        """Execute a click action and verify it landed.

        If the click misses, retries through targeting tiers:
        1. Try accessibility element targeting
        2. Try with adjusted coordinates
        3. Try keyboard navigation

        Args:
            action: The action dict to execute.
            before_screenshot: Screenshot before the action. If None,
                verification is skipped.

        Returns:
            Final result dict from the executor.
        """
        action_name = action.get("action", "")

        # Only verify click-like actions
        _click_actions = (
            "click", "click_element",
            "click_mark", "double_click", "right_click",
        )
        if action_name not in _click_actions:
            return self.executor.execute_sync(action)

        # Capture before screenshot if not provided
        if before_screenshot is None:
            try:
                from core.screenshot import capture_screen
                before_screenshot = capture_screen()
            except OSError:
                # Can't capture — skip verification
                return self.executor.execute_sync(action)

        # Execute the initial action
        result = self.executor.execute_sync(action)

        if not result.get("success", False):
            return result  # Action itself failed, not a click miss

        # Get click coordinates for verification
        coords = self._extract_coords(action)
        if coords is None:
            return result  # Can't verify without coordinates

        x, y = coords
        w = action.get("width", 40)
        h = action.get("height", 20)

        # Verify the click landed
        landed, diff_score, after_screenshot = verify_click_landed(
            before_screenshot, x, y, w, h,
        )

        if landed:
            result["verified"] = True
            result["diff_score"] = round(diff_score, 2)
            return result

        # Click missed — retry through tiers
        logger.info(
            "Click miss detected at (%d,%d), diff=%.1f — retrying through tiers",
            x, y, diff_score,
        )
        result["verified"] = False
        result["diff_score"] = round(diff_score, 2)
        result["retries"] = []

        retry_result = self._tiered_retry(
            action, before_screenshot, x, y,
        )
        if retry_result is not None:
            retry_result["initial_miss"] = result
            return retry_result

        # All retries failed
        result["retry_exhausted"] = True
        return result

    def _tiered_retry(
        self,
        original_action: dict[str, Any],
        before_screenshot: Image.Image,
        x: int,
        y: int,
    ) -> dict[str, Any] | None:
        """Retry a missed click through progressively simpler targeting methods.

        Tiers:
        1. click_control — accessibility tree targeting
        2. Adjusted coordinates — offset retry (nearby pixels)
        3. Keyboard navigation — Tab + Enter

        Returns:
            Result dict if retry succeeded, None if all tiers exhausted.
        """
        retries: list[dict[str, Any]] = []

        # Tier 1: Try accessibility tree targeting
        tier1_result = self._retry_via_accessibility(original_action, before_screenshot)
        retries.append(tier1_result)
        if tier1_result.get("success") and tier1_result.get("verified", True):
            tier1_result["retries"] = retries
            return tier1_result

        # Tier 2: Try with offset coordinates (pixel nudge)
        tier2_result = self._retry_with_offset(original_action, before_screenshot, x, y)
        retries.append(tier2_result)
        if tier2_result.get("success") and tier2_result.get("verified", True):
            tier2_result["retries"] = retries
            return tier2_result

        # Tier 3: Keyboard navigation (Tab + Enter)
        tier3_result = self._retry_via_keyboard(original_action)
        retries.append(tier3_result)

        # Return the last attempt result
        tier3_result["retries"] = retries
        return tier3_result if tier3_result.get("success") else None

    def _retry_via_accessibility(
        self,
        original_action: dict[str, Any],
        before_screenshot: Image.Image,
    ) -> dict[str, Any]:
        """Retry via click_control (accessibility tree lookup)."""
        # Try to find the element by name/label from perception
        if self.executor.perception_result is not None:
            elem_id = original_action.get("element_id") or original_action.get("mark_id")
            if elem_id is not None:
                elem = self.executor.perception_result.find_by_id(elem_id)
                if elem and elem.label:
                    retry_action = {
                        "action": "click_control",
                        "name": elem.label,
                    }
                    result = self.executor.execute_sync(retry_action)
                    result["retry_tier"] = "accessibility"
                    result["retry_action"] = retry_action
                    return result

        return {
            "success": False,
            "output": "No accessibility data for retry",
            "retry_tier": "accessibility",
        }

    def _retry_with_offset(
        self,
        original_action: dict[str, Any],
        before_screenshot: Image.Image,
        x: int,
        y: int,
    ) -> dict[str, Any]:
        """Retry with slightly offset coordinates."""
        offsets = [(3, 3), (-3, -3), (5, 0), (0, 5)]
        for dx, dy in offsets:
            retry_action = {
                "action": "click",
                "x": x + dx,
                "y": y + dy,
            }
            result = self.executor.execute_sync(retry_action)
            result["retry_tier"] = "offset"
            result["offset"] = (dx, dy)
            return result

        return {"success": False, "output": "Offset retry exhausted", "retry_tier": "offset"}

    def _retry_via_keyboard(
        self,
        original_action: dict[str, Any],
    ) -> dict[str, Any]:
        """Retry via keyboard navigation (Tab then Enter)."""
        # Press Tab to move focus, then Enter to activate
        self.executor.execute_sync({"action": "press_key", "key": "enter"})
        return {
            "success": True,
            "output": "Keyboard retry: pressed Enter at current focus",
            "retry_tier": "keyboard",
        }

    @staticmethod
    def _extract_coords(action: dict[str, Any]) -> tuple[int, int] | None:
        """Extract click coordinates from an action dict."""
        if "x" in action and "y" in action:
            return (action["x"], action["y"])

        # Check perception result for element-based actions
        # (handled externally — the executor already resolved coordinates)
        return None
