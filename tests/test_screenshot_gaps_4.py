"""Gap tests for screenshot.py — resolve_monitor auto fallback, capture_focused_window target
path, image_to_base64 encoding failure.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.screenshot import (
    capture_focused_window,
    image_to_base64,
    resolve_monitor,
)


class TestResolveMonitorAutoFallback:
    """resolve_monitor('auto') falls back to 1 when no monitor contains center."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific mss library test")
    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.mss", create=True)
    def test_auto_no_monitor_contains_center_returns_1(self, mock_mss):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 2160},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        from core import window_manager as wm

        with patch.object(wm, "get_focused_window_rect", return_value=(5000, 5000, 100, 100)):
            result = resolve_monitor("auto")
        assert result == 1  # line 66


class TestCaptureFocusedWindowTargetPath:
    """capture_focused_window uses get_target_window_rect result (line 196)."""

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (100, 100)))
    def test_target_window_rect_path(self, mock_cap):
        from core import window_manager as wm

        with patch.object(wm, "get_target_window_rect", return_value=(10, 20, 200, 300, "Test")):
            result = capture_focused_window()
        assert result is not None
        mock_cap.assert_called_once_with(10, 20, 200, 300)

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (100, 100)))
    def test_target_window_zero_size_returns_none(self, mock_cap):
        from core import window_manager as wm

        with patch.object(wm, "get_target_window_rect", return_value=(10, 20, 0, 300, "Test")):
            result = capture_focused_window()
        assert result is None

    def test_target_window_none_falls_to_focused(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=None),
            patch.object(wm, "get_focused_window_rect", return_value=None),
        ):
            result = capture_focused_window()
        assert result is None

    @patch("core.screenshot.capture_region", side_effect=OSError("capture fail"))
    def test_capture_region_oserror_returns_none(self, mock_cap):
        from core import window_manager as wm

        with patch.object(wm, "get_target_window_rect", return_value=(10, 20, 200, 300, "Test")):
            result = capture_focused_window()
        assert result is None


class TestImageToBase64EncodingFailure:
    """image_to_base64 raises ValueError when PIL save fails (lines 303-304)."""

    def test_save_oserror_raises_valueerror(self):
        img = MagicMock()
        img.save.side_effect = OSError("disk full")
        import pytest

        with pytest.raises(ValueError, match="Image encoding"):
            image_to_base64(img, fmt="PNG")

    def test_save_valueerror_raises_valueerror(self):
        img = MagicMock()
        img.save.side_effect = ValueError("bad params")
        import pytest

        with pytest.raises(ValueError, match="Image encoding"):
            image_to_base64(img, fmt="PNG")


class TestCaptureFocusedWindowWithTitleTarget:
    """capture_focused_window_with_title target path."""

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (50, 50)))
    def test_with_target_window(self, mock_cap):
        from core import window_manager as wm

        with patch.object(wm, "get_target_window_rect", return_value=(0, 0, 800, 600, "Chrome")):
            from core.screenshot import capture_focused_window_with_title

            result = capture_focused_window_with_title()
        assert result is not None
        img, title = result
        assert title == "Chrome"

    @patch("core.screenshot.capture_region", side_effect=OSError("fail"))
    def test_capture_oserror_returns_none(self, mock_cap):
        from core import window_manager as wm

        with patch.object(wm, "get_target_window_rect", return_value=(0, 0, 800, 600, "Chrome")):
            from core.screenshot import capture_focused_window_with_title

            result = capture_focused_window_with_title()
        assert result is None

    def test_target_none_focused_none_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=None),
            patch.object(wm, "get_focused_window_rect", return_value=None),
        ):
            from core.screenshot import capture_focused_window_with_title

            result = capture_focused_window_with_title()
        assert result is None
