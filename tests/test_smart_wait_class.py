"""Tests for core/smart_wait.py — SmartWait class methods with mocked capture."""

from unittest.mock import patch

from PIL import Image

from core.smart_wait import SmartWait


def _constant_image(color: tuple = (100, 100, 100)) -> Image.Image:
    return Image.new("RGB", (50, 50), color)


def _different_image() -> Image.Image:
    return Image.new("RGB", (50, 50), (200, 200, 200))


class TestCancel:
    def test_cancel_sets_event(self):
        sw = SmartWait()
        assert not sw._cancelled()
        sw.cancel()
        assert sw._cancelled()

    def test_reset_cancel_clears_event(self):
        sw = SmartWait()
        sw.cancel()
        assert sw._cancelled()
        sw._reset_cancel()
        assert not sw._cancelled()


class TestWaitForChange:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_detects_change(self, mock_mono, mock_sleep, mock_capture):
        # Simulate: 0.0 baseline, 0.1 first check (same), 0.2 second check (changed)
        mock_mono.side_effect = [0.0, 0.1, 0.1, 0.2, 0.2]
        same = _constant_image()
        diff = _different_image()
        mock_capture.side_effect = [same, same, diff]
        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is True
        assert result.change_score > 0.0
        assert result.frames_checked == 3

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_timeout_no_change(self, mock_mono, mock_sleep, mock_capture):
        # Timeout after first check
        mock_mono.side_effect = [0.0, 5.1, 5.1]
        mock_capture.return_value = _constant_image()
        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    def test_cancel_mid_wait(self, mock_sleep, mock_capture):
        mock_capture.return_value = _constant_image()
        sw = SmartWait()

        # Cancel immediately after first sleep
        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is False


class TestWaitForStable:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_stable_after_no_change(self, mock_mono, mock_sleep, mock_capture):
        # Two identical frames captured, enough stable_time passes
        # t=0 baseline, t=0.1 first check, t=0.2 stable check
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 0.2, 2.0, 2.0]
        same = _constant_image()
        mock_capture.side_effect = [same, same, same]
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=5, stable_time=1.5, interval=0.01)
        assert result.success is True
        assert result.frames_checked == 3

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_timeout_while_unstable(self, mock_mono, mock_sleep, mock_capture):
        # Simulate rapid monotonic progression: baseline, then immediate timeout
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 10.0, 10.0]
        # First two captures same (no change = stable clock resets),
        # third would be checked but we already timed out
        same = _constant_image()
        diff = _different_image()
        mock_capture.side_effect = [same, diff, same]
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=5, stable_time=2.0, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    def test_cancel_mid_stable_wait(self, mock_sleep, mock_capture):
        mock_capture.return_value = _constant_image()
        sw = SmartWait()

        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        result = sw.wait_for_stable(timeout=5, stable_time=2.0, interval=0.01)
        assert result.success is False
