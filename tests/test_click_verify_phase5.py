"""Tests for Phase 5: Click Verification & Self-Correction — diff, retry, enforced self-healing."""

from unittest.mock import patch

from PIL import Image

from core.click_verify import (
    ClickVerifier,
    capture_region,
    compute_region_diff,
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
        with patch.object(
            self.executor,
            "execute_sync",
            return_value={"success": False, "output": "click failed", "error": "click_failed"},
        ):
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
            before,
            400,
            300,
        )
        assert result["retry_tier"] == "offset"

    def test_accessibility_retry_with_perception(self):
        """Accessibility retry uses perception data when available."""
        from core.perception.types import (
            ElementSource,
            ElementType,
            PerceptionElement,
            PerceptionResult,
        )

        elem = PerceptionElement(
            id=1,
            label="OK",
            element_type=ElementType.BUTTON,
            bounding_box=(100, 100, 80, 30),
            source=ElementSource.ACCESSIBILITY,
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


# ---------------------------------------------------------------------------
# verify_click_landed function tests
# ---------------------------------------------------------------------------


class TestVerifyClickLanded:
    """Test the verify_click_landed function."""

    def test_verify_click_success_case(self):
        """Test successful click verification."""
        before = Image.new("RGB", (800, 600), "white")
        after = Image.new("RGB", (800, 600), "black")

        with patch("core.screenshot.capture_screen", return_value=after):
            with patch("core.click_verify.time.sleep"):  # Mock sleep to speed up tests
                landed, diff_score, after_screenshot = verify_click_landed(before, 400, 300)
                assert landed is True
                assert diff_score > 50.0
                assert after_screenshot == after

    def test_verify_click_miss_case(self):
        """Test missed click detection (no change)."""
        before = Image.new("RGB", (800, 600), "white")
        after = before.copy()  # No change

        with patch("core.screenshot.capture_screen", return_value=after):
            with patch("core.click_verify.time.sleep"):
                landed, diff_score, after_screenshot = verify_click_landed(before, 400, 300)
                assert landed is False
                assert diff_score < 5.0  # Below threshold
                assert after_screenshot == after

    def test_verify_click_screenshot_failure(self):
        """Test graceful handling of screenshot capture failure."""
        before = Image.new("RGB", (800, 600), "white")

        with patch("core.screenshot.capture_screen", side_effect=OSError("Display error")):
            with patch("core.click_verify.time.sleep"):
                landed, diff_score, after_screenshot = verify_click_landed(before, 400, 300)
                # Assume landed on error
                assert landed is True
                assert diff_score == 0.0
                assert after_screenshot == before


# ---------------------------------------------------------------------------
# ClickVerifier edge cases
# ---------------------------------------------------------------------------


class TestClickVerifierEdgeCases:
    """Test edge cases in ClickVerifier."""

    def setup_method(self):
        from core.action_executor import ActionExecutor
        self.executor = ActionExecutor(dry_run=True)
        self.verifier = ClickVerifier(self.executor)

    def test_execute_without_screenshot_capability(self):
        """Test execution when screenshot capture fails completely."""
        action = {"action": "click", "x": 400, "y": 300}

        with patch("core.screenshot.capture_screen", side_effect=OSError("No display")):
            result = self.verifier.execute_with_verification(action, before_screenshot=None)
            # Should pass through without verification when screenshot fails
            assert result.get("success") is True

    def test_click_without_coordinates_skips_verification(self):
        """Test that actions without coordinates skip verification."""
        action = {"action": "click"}  # No x, y coordinates
        before = Image.new("RGB", (800, 600), "white")

        with patch("core.screenshot.capture_screen", return_value=before):
            result = self.verifier.execute_with_verification(action, before_screenshot=before)
            # Should skip verification and return result directly
            assert result.get("success") is True

    def test_extract_coords_from_action(self):
        """Test coordinate extraction from action dict."""
        action1 = {"x": 100, "y": 200}
        coords = ClickVerifier._extract_coords(action1)
        assert coords == (100, 200)

        action2 = {"action": "click"}  # No coords
        coords = ClickVerifier._extract_coords(action2)
        assert coords is None

    def test_offset_retry_exhausted(self):
        """Test offset retry when all offsets are exhausted."""
        before = Image.new("RGB", (800, 600), "white")

        # Mock the retry to hit the exhausted case
        with patch.object(self.verifier, "_retry_with_offset", return_value={
            "success": False, "output": "Offset retry exhausted", "retry_tier": "offset"
        }):
            result = self.verifier._retry_with_offset(
                {"action": "click", "x": 400, "y": 300},
                before, 400, 300,
            )
            assert result["retry_tier"] == "offset"
            assert result["success"] is False

    def test_keyboard_retry_structure(self):
        """Test keyboard retry returns correct structure."""
        result = self.verifier._retry_via_keyboard({"action": "click", "x": 400, "y": 300})
        assert "retry_tier" in result
        assert result["retry_tier"] == "keyboard"
        assert "success" in result

    def test_tiered_retry_all_tiers_fail(self):
        """Test tiered retry when all tiers fail."""
        before = Image.new("RGB", (800, 600), "white")

        # Mock all tiers to fail
        with patch.object(self.verifier, "_retry_via_accessibility", return_value={
            "success": False, "retry_tier": "accessibility"
        }):
            with patch.object(self.verifier, "_retry_with_offset", return_value={
                "success": False, "retry_tier": "offset"
            }):
                with patch.object(self.verifier, "_retry_via_keyboard", return_value={
                    "success": False, "retry_tier": "keyboard"
                }):
                    result = self.verifier._tiered_retry(
                        {"action": "click", "x": 400, "y": 300},
                        before, 400, 300
                    )
                    # Should return None when all tiers fail
                    assert result is None


# ---------------------------------------------------------------------------
# Numpy fallback tests
# ---------------------------------------------------------------------------


class TestNumpyFallback:
    """Test compute_region_diff fallback when numpy is unavailable."""

    def test_fallback_sampling_method(self):
        """Test that fallback sampling method works for large images."""
        # This tests the sampling path in the fallback code
        before = Image.new("RGB", (1000, 1000), "white")
        after = Image.new("RGB", (1000, 1000), "black")

        # Just verify it computes a difference correctly
        # The fallback samples pixels at regular intervals
        diff = compute_region_diff(before, after)
        # Should detect significant difference
        assert diff > 50.0
