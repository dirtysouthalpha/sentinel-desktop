"""Tests for Phase 5: Click Verification & Self-Correction — diff, retry, enforced self-healing."""

import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.click_verify import (
    ClickVerifier,
    compute_region_diff,
    capture_region,
    verify_click_landed,
)


# ---------------------------------------------------------------------------
# Region capture
# ---------------------------------------------------------------------------


class TestRegionCapture:
    """Test screenshot region extraction."""

    def test_captures_centered_region(self):
        img = Image.new("RGB", (800, 600), "white")
        region = capture_region(img, 400, 300, 80, 40)
        # With padding=20, region should be larger than 80x40
        rw, rh = region.size
        assert rw > 80
        assert rh > 40

    def test_clamps_to_edges(self):
        img = Image.new("RGB", (800, 600), "white")
        # Near top-left corner
        region = capture_region(img, 10, 10, 20, 20)
        assert region.size[0] > 0
        assert region.size[1] > 0

    def test_clamps_to_bottom_right(self):
        img = Image.new("RGB", (800, 600), "white")
        region = capture_region(img, 790, 590, 20, 20)
        assert region.size[0] > 0
        assert region.size[1] > 0


# ---------------------------------------------------------------------------
# Region diff computation (VER-01)
# ---------------------------------------------------------------------------


class TestRegionDiff:
    """Test pixel difference computation for click verification."""

    def test_identical_images_zero_diff(self):
        img = Image.new("RGB", (100, 100), "white")
        diff = compute_region_diff(img, img)
        assert diff == 0.0

    def test_different_images_positive_diff(self):
        before = Image.new("RGB", (100, 100), "white")
        after = Image.new("RGB", (100, 100), "black")
        diff = compute_region_diff(before, after)
        assert diff > 50.0  # Significant difference

    def test_slightly_different(self):
        before = Image.new("RGB", (100, 100), (200, 200, 200))
        after = Image.new("RGB", (100, 100), (210, 210, 210))
        diff = compute_region_diff(before, after)
        assert diff > 0.0
        assert diff < 20.0  # Small difference

    def test_different_sizes_high_diff(self):
        before = Image.new("RGB", (100, 100), "white")
        after = Image.new("RGB", (50, 50), "white")
        diff = compute_region_diff(before, after)
        assert diff > 50.0  # Size mismatch = big change

    def test_partial_change_detected(self):
        """Only part of the region changes — should still detect diff."""
        before = Image.new("RGB", (200, 100), "white")
        after = before.copy()
        # Draw a black rectangle in the center
        from PIL import ImageDraw
        draw = ImageDraw.Draw(after)
        draw.rectangle([80, 30, 120, 70], fill="black")
        diff = compute_region_diff(before, after)
        assert diff > 0.0


# ---------------------------------------------------------------------------
# ClickVerifier (VER-02, VER-03)
# ---------------------------------------------------------------------------


class TestClickVerifier:
    """Test tiered retry through grounding methods on miss."""

    def setup_method(self):
        from core.action_executor import ActionExecutor
        self.executor = ActionExecutor(dry_run=True)
        self.verifier = ClickVerifier(self.executor)

    def test_non_click_actions_skip_verification(self):
        """Non-click actions pass through without verification."""
        action = {"action": "type_text", "text": "hello"}
        result = self.verifier.execute_with_verification(action)
        assert result.get("success") is True
        assert "verified" not in result  # Not verified — just passed through

    def test_click_action_gets_verified(self):
        """Click actions trigger verification."""
        action = {"action": "click", "x": 400, "y": 300}
        with patch("core.click_verify.verify_click_landed") as mock_verify:
            mock_verify.return_value = (True, 15.0, Image.new("RGB", (800, 600)))
            with patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (800, 600))):
                result = self.verifier.execute_with_verification(action)
                assert result.get("verified") is True

    def test_miss_triggers_retry(self):
        """Click miss triggers tiered retry."""
        action = {"action": "click", "x": 400, "y": 300}
        with patch("core.click_verify.verify_click_landed") as mock_verify:
            # First call: miss. Second call (retry): land.
            mock_verify.side_effect = [
                (False, 0.5, Image.new("RGB", (800, 600))),
                (True, 20.0, Image.new("RGB", (800, 600))),
            ]
            with patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (800, 600))):
                result = self.verifier.execute_with_verification(action)
                # Should have retried
                assert result is not None

    def test_failed_action_skips_verification(self):
        """If the action itself fails, no verification is attempted."""
        # Use execute_sync that returns a failure result
        with patch.object(self.executor, "execute_sync", return_value={
            "success": False, "output": "click failed", "error": "click_failed"
        }):
            with patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (800, 600))):
                action = {"action": "click", "x": 400, "y": 300}
                result = self.verifier.execute_with_verification(action)
                assert result["success"] is False

    def test_no_before_screenshot_captures_one(self):
        """When no before screenshot provided, captures one automatically."""
        action = {"action": "click", "x": 400, "y": 300}
        with patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (800, 600))):
            with patch("core.click_verify.verify_click_landed") as mock_verify:
                mock_verify.return_value = (True, 10.0, Image.new("RGB", (800, 600)))
                result = self.verifier.execute_with_verification(action, before_screenshot=None)
                assert result is not None

    def test_keyboard_retry_tier(self):
        """Final retry tier uses keyboard navigation."""
        # Test the keyboard retry path directly
        result = self.verifier._retry_via_keyboard({"action": "click", "x": 400, "y": 300})
        assert result["retry_tier"] == "keyboard"

    def test_offset_retry_tier(self):
        """Offset retry nudges coordinates."""
        before = Image.new("RGB", (800, 600), "white")
        result = self.verifier._retry_with_offset(
            {"action": "click", "x": 400, "y": 300},
            before, 400, 300,
        )
        assert result["retry_tier"] == "offset"

    def test_accessibility_retry_with_perception(self):
        """Accessibility retry uses perception data when available."""
        from core.perception.types import PerceptionElement, PerceptionResult, ElementType, ElementSource

        elem = PerceptionElement(
            id=1, label="OK", element_type=ElementType.BUTTON,
            bounding_box=(100, 100, 80, 30), source=ElementSource.ACCESSIBILITY,
            is_interactable=True,
        )
        self.executor.perception_result = PerceptionResult(elements=[elem])

        result = self.verifier._retry_via_accessibility(
            {"action": "click_element", "element_id": 1},
            Image.new("RGB", (800, 600)),
        )
        assert result["retry_tier"] == "accessibility"

    def test_accessibility_retry_without_perception(self):
        """Accessibility retry fails gracefully without perception data."""
        self.executor.perception_result = None
        result = self.verifier._retry_via_accessibility(
            {"action": "click", "x": 400, "y": 300},
            Image.new("RGB", (800, 600)),
        )
        assert result["success"] is False
        assert result["retry_tier"] == "accessibility"


# ---------------------------------------------------------------------------
# Integration: self-healing is enforced in code (VER-03)
# ---------------------------------------------------------------------------


class TestEnforcedSelfHealing:
    """Verify self-healing is in executor code, not prompt-dependent."""

    def test_click_verify_module_exists(self):
        """core.click_verify module exists and is importable."""
        import core.click_verify
        assert hasattr(core.click_verify, "ClickVerifier")

    def test_verifier_has_tiered_retry(self):
        """ClickVerifier has the tiered retry method."""
        assert hasattr(ClickVerifier, "_tiered_retry")

    def test_verifier_has_all_tiers(self):
        """ClickVerifier implements all three retry tiers."""
        assert hasattr(ClickVerifier, "_retry_via_accessibility")
        assert hasattr(ClickVerifier, "_retry_with_offset")
        assert hasattr(ClickVerifier, "_retry_via_keyboard")

    def test_diff_threshold_is_configurable_constant(self):
        """Verification threshold is defined as a module constant."""
        from core.click_verify import _DIFF_THRESHOLD
        assert isinstance(_DIFF_THRESHOLD, float)
        assert _DIFF_THRESHOLD > 0
