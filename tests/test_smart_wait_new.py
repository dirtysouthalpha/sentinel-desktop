"""Tests for core/smart_wait.py -- additional edge cases for visual diff, stability, and wait_for_change."""

from unittest.mock import patch

from PIL import Image

from core.smart_wait import (
    SmartWait,
    WaitResult,
    _compute_change_score,
    _downsample,
    _save_snapshot,
)

# ---------------------------------------------------------------------------
# Visual diff edge cases
# ---------------------------------------------------------------------------


class TestComputeChangeScoreEdgeCases:
    def test_single_channel_diff_below_threshold(self):
        """Only one channel differs, but it's below threshold → 0.0."""
        a = Image.new("RGB", (10, 10), (100, 100, 100))
        b = Image.new("RGB", (10, 10), (100, 100, 130))
        score = _compute_change_score(a, b)
        assert score == 0.0

    def test_single_channel_diff_above_threshold(self):
        """Only one channel differs and exceeds threshold → some change."""
        a = Image.new("RGB", (10, 10), (100, 100, 100))
        b = Image.new("RGB", (10, 10), (100, 100, 200))
        score = _compute_change_score(a, b)
        assert score > 0.0

    def test_1x1_images_identical(self):
        a = Image.new("RGB", (1, 1), (50, 50, 50))
        b = Image.new("RGB", (1, 1), (50, 50, 50))
        assert _compute_change_score(a, b) == 0.0

    def test_1x1_images_different(self):
        a = Image.new("RGB", (1, 1), (0, 0, 0))
        b = Image.new("RGB", (1, 1), (255, 255, 255))
        assert _compute_change_score(a, b) == 1.0

    def test_larger_images_performance(self):
        """Ensure large images don't hang — basic performance sanity."""
        a = Image.new("RGB", (400, 300), (10, 10, 10))
        b = Image.new("RGB", (400, 300), (200, 200, 200))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_grayscale_vs_rgb(self):
        """Ensure mode conversion works; 'L' mode images should work."""
        a = Image.new("L", (10, 10), 128)
        b = Image.new("RGB", (10, 10), (128, 128, 128))
        # Both convert to RGB for comparison
        score = _compute_change_score(a, b)
        assert score == 0.0

    def test_rgba_images(self):
        """RGBA images should be handled via .convert('RGB')."""
        a = Image.new("RGBA", (10, 10), (100, 100, 100, 255))
        b = Image.new("RGBA", (10, 10), (100, 100, 100, 255))
        score = _compute_change_score(a, b)
        assert score == 0.0


class TestDownsampleEdgeCases:
    def test_large_image_downscaled(self):
        img = Image.new("RGB", (1920, 1080))
        result = _downsample(img, factor=4)
        assert result.size == (480, 270)

    def test_odd_dimensions(self):
        img = Image.new("RGB", (7, 5))
        result = _downsample(img, factor=2)
        assert result.size == (3, 2)

    def test_factor_greater_than_dimension(self):
        img = Image.new("RGB", (2, 2))
        result = _downsample(img, factor=10)
        assert result.size == (1, 1)


# ---------------------------------------------------------------------------
# wait_for_change — additional scenarios
# ---------------------------------------------------------------------------


class TestWaitForChangeAdditional:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_immediate_change_on_first_poll(self, mock_mono, mock_sleep, mock_capture):
        """Screen changes on the very first re-capture (after baseline)."""
        mock_mono.side_effect = [0.0, 0.1, 0.1]
        mock_capture.side_effect = [
            Image.new("RGB", (50, 50), (0, 0, 0)),
            Image.new("RGB", (50, 50), (255, 255, 255)),
        ]
        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is True
        assert result.frames_checked == 2

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_zero_timeout(self, mock_mono, mock_sleep, mock_capture):
        """Timeout of 0 should immediately return failure (elapsed >= timeout on first check)."""
        mock_mono.side_effect = [0.0, 0.001, 0.001]
        mock_capture.return_value = Image.new("RGB", (50, 50), (100, 100, 100))
        sw = SmartWait()
        result = sw.wait_for_change(timeout=0, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._save_snapshot")
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_snapshot_saved_on_change(self, mock_mono, mock_sleep, mock_capture, mock_snap):
        mock_mono.side_effect = [0.0, 0.1, 0.1]
        mock_snap.return_value = "/tmp/change_snap.png"  # noqa: S108
        mock_capture.side_effect = [
            Image.new("RGB", (50, 50), (0, 0, 0)),
            Image.new("RGB", (50, 50), (255, 255, 255)),
        ]
        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is True
        mock_snap.assert_called_once()


# ---------------------------------------------------------------------------
# wait_for_stable — additional scenarios
# ---------------------------------------------------------------------------


class TestWaitForStableAdditional:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_never_stable_timeout(self, mock_mono, mock_sleep, mock_capture):
        """Screen keeps changing until timeout."""
        same = Image.new("RGB", (50, 50), (100, 100, 100))
        diff = Image.new("RGB", (50, 50), (200, 200, 200))
        # baseline=same, then alternating same/diff to keep resetting stability clock
        # but we'll just timeout immediately
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 10.0, 10.0]
        mock_capture.side_effect = [same, diff, same]
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=5, stable_time=2.0, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._save_snapshot")
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_snapshot_saved_on_stable(self, mock_mono, mock_sleep, mock_capture, mock_snap):
        same = Image.new("RGB", (50, 50), (100, 100, 100))
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 0.2, 2.0, 2.0]
        mock_capture.side_effect = [same, same, same]
        mock_snap.return_value = "/tmp/stable_snap.png"  # noqa: S108
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=5, stable_time=1.5, interval=0.01)
        assert result.success is True
        mock_snap.assert_called_once()

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_zero_timeout(self, mock_mono, mock_sleep, mock_capture):
        mock_mono.side_effect = [0.0, 0.001, 0.001]
        mock_capture.return_value = Image.new("RGB", (50, 50), (100, 100, 100))
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=0, stable_time=1.0, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_stable_after_initial_change(self, mock_mono, mock_sleep, mock_capture):
        """First frame changes, then subsequent frames are stable."""
        same = Image.new("RGB", (50, 50), (100, 100, 100))
        diff = Image.new("RGB", (50, 50), (200, 200, 200))
        # baseline at t=0, first check at t=0.1 (different), second check at t=0.2 (same),
        # then stability check at t=2.0
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 0.3, 2.0, 2.0]
        mock_capture.side_effect = [same, diff, same, same]
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=10, stable_time=1.5, interval=0.01)
        assert result.success is True
        # change_score should reflect the last detected change
        assert result.change_score > 0.0


# ---------------------------------------------------------------------------
# Cancellation edge cases
# ---------------------------------------------------------------------------


class TestCancelEdgeCases:
    def test_cancel_before_wait(self):
        """wait_for_change resets the cancel flag before starting — verify _reset_cancel is called."""
        sw = SmartWait()
        sw.cancel()
        with patch("core.smart_wait._crop_to_region") as mock_capture, \
             patch("core.smart_wait.time.sleep"):
            mock_capture.return_value = Image.new("RGB", (50, 50))
            sw.wait_for_change(timeout=0.01, interval=0.001)
            assert not sw._cancelled()  # _reset_cancel was called

    def test_multiple_cancel_calls(self):
        sw = SmartWait()
        sw.cancel()
        sw.cancel()
        assert sw._cancelled()
        sw._reset_cancel()
        assert not sw._cancelled()


# ---------------------------------------------------------------------------
# _save_snapshot edge cases
# ---------------------------------------------------------------------------


class TestSaveSnapshotEdgeCases:
    def test_filename_contains_prefix(self, tmp_path):
        import core.smart_wait as sw

        orig = sw.tempfile.gettempdir
        sw.tempfile.gettempdir = lambda: str(tmp_path)
        try:
            img = Image.new("RGB", (10, 10), "blue")
            path = _save_snapshot(img, prefix="mytest")
            assert "mytest" in path
        finally:
            sw.tempfile.gettempdir = orig

    def test_returns_string_path(self, tmp_path):
        import core.smart_wait as sw

        orig = sw.tempfile.gettempdir
        sw.tempfile.gettempdir = lambda: str(tmp_path)
        try:
            img = Image.new("RGB", (10, 10))
            path = _save_snapshot(img)
            assert isinstance(path, str)
            assert path.endswith(".png")
        finally:
            sw.tempfile.gettempdir = orig


# ---------------------------------------------------------------------------
# WaitResult edge cases
# ---------------------------------------------------------------------------


class TestWaitResultDataclass:
    def test_all_fields_set(self):
        r = WaitResult(
            success=True,
            elapsed=3.14,
            frames_checked=42,
            change_score=0.75,
            snapshot_path="/tmp/snap.png",  # noqa: S108
        )
        assert r.success is True
        assert r.elapsed == 3.14
        assert r.frames_checked == 42
        assert r.change_score == 0.75
        assert r.snapshot_path == "/tmp/snap.png"  # noqa: S108

    def test_failure_result(self):
        r = WaitResult(
            success=False,
            elapsed=10.0,
            frames_checked=30,
            change_score=0.0,
        )
        assert r.success is False
        assert r.snapshot_path is None
