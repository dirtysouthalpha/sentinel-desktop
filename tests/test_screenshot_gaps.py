"""Gap tests for screenshot.py — capture_focused_window, capture_window error handling."""

from unittest.mock import patch

from PIL import Image

from core.screenshot import (
    capture_focused_window,
    capture_focused_window_with_title,
    capture_window,
    list_monitors,
    wait_for_template,
)


class TestCaptureFocusedWindowErrors:
    """capture_focused_window catches capture_region OSError."""

    @patch("core.screenshot.capture_region", side_effect=OSError("mss failed"))
    @patch("core.window_manager.get_focused_window_rect", return_value=(0, 0, 100, 100))
    @patch("core.window_manager.get_target_window_rect", return_value=None)
    def test_capture_region_oserror_returns_none(self, mock_target, mock_focused, mock_cap):
        assert capture_focused_window() is None

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (10, 10)))
    @patch("core.window_manager.get_focused_window_rect", return_value=(0, 0, 100, 100))
    @patch("core.window_manager.get_target_window_rect", return_value=None)
    def test_capture_success_returns_image(self, mock_target, mock_focused, mock_cap):
        result = capture_focused_window()
        assert result is not None
        assert result.size == (10, 10)

    @patch("core.window_manager.get_target_window_rect", return_value=None)
    @patch("core.window_manager.get_focused_window_rect", return_value=None)
    def test_no_window_rects_returns_none(self, mock_focused, mock_target):
        assert capture_focused_window() is None

    @patch("core.window_manager.get_target_window_rect", return_value=None)
    @patch("core.window_manager.get_focused_window_rect", return_value=(0, 0, 0, 0))
    def test_zero_size_returns_none(self, mock_focused, mock_target):
        assert capture_focused_window() is None


class TestCaptureFocusedWindowWithTitleErrors:
    """capture_focused_window_with_title error handling."""

    @patch("core.screenshot.capture_region", side_effect=OSError("failed"))
    @patch("core.window_manager.get_target_window_rect", return_value=(10, 20, 100, 100, "Title"))
    def test_capture_region_oserror_returns_none(self, mock_target, mock_cap):
        assert capture_focused_window_with_title() is None

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (10, 10)))
    @patch("core.window_manager.get_target_window_rect", return_value=(10, 20, 100, 100, "Title"))
    def test_success_returns_tuple(self, mock_target, mock_cap):
        result = capture_focused_window_with_title()
        assert result is not None
        img, title = result
        assert title == "Title"
        assert img.size == (10, 10)

    @patch("core.window_manager.get_target_window_rect", return_value=None)
    @patch("core.window_manager.get_focused_window_rect", return_value=None)
    def test_fallback_to_focused_rect(self, mock_focused, mock_target):
        assert capture_focused_window_with_title() is None

    @patch("core.window_manager.get_target_window_rect", return_value=(10, 20, 0, 100, "T"))
    def test_zero_size_returns_none(self, mock_target):
        assert capture_focused_window_with_title() is None


class TestCaptureWindowErrors:
    """capture_window error handling."""

    @patch("core.screenshot.capture_region", side_effect=OSError("failed"))
    @patch("core.window_manager.get_window_rect", return_value=(0, 0, 100, 100))
    @patch("core.window_manager.restore_window", return_value=True)
    def test_capture_region_oserror_returns_none(self, mock_restore, mock_rect, mock_cap):
        assert capture_window("test") is None

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (50, 50)))
    @patch("core.window_manager.get_window_rect", return_value=(0, 0, 50, 50))
    @patch("core.window_manager.restore_window", return_value=True)
    def test_success_returns_image(self, mock_restore, mock_rect, mock_cap):
        result = capture_window("test")
        assert result is not None
        assert result.size == (50, 50)

    @patch("core.window_manager.get_window_rect", return_value=None)
    @patch("core.window_manager.restore_window", return_value=False)
    def test_no_matching_window_returns_none(self, mock_restore, mock_rect):
        assert capture_window("nonexistent") is None

    @patch("core.window_manager.get_window_rect", return_value=(0, 0, 0, 0))
    @patch("core.window_manager.restore_window", return_value=True)
    def test_zero_size_returns_none(self, mock_restore, mock_rect):
        assert capture_window("test") is None


class TestListMonitorsFallback:
    """list_monitors falls back gracefully."""

    @patch("core.screenshot._HAS_MSS", False)
    def test_without_mss_returns_primary(self):
        monitors = list_monitors()
        assert len(monitors) >= 1
        assert monitors[0]["is_primary"] is True


class TestWaitForTemplate:
    """wait_for_template polling behavior."""

    @patch("core.screenshot.find_template", return_value=None)
    def test_timeout_returns_none(self, mock_find):
        result = wait_for_template("test.png", timeout=0.1, poll_interval=0.05)
        assert result is None

    @patch("core.screenshot.find_template", return_value=(50, 50))
    def test_immediate_match_returns_pos(self, mock_find):
        result = wait_for_template("test.png", timeout=1.0)
        assert result == (50, 50)
