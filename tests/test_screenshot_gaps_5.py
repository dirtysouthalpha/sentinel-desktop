"""Gap tests for screenshot.py remaining lines.

Lines 218-219: capture_focused_window_with_title falls back to focused rect
                with empty title string when target is None.
"""

from unittest.mock import patch

from PIL import Image


class TestCaptureFocusedWindowWithTitleFallbackRect:
    """Lines 218-219: fallback to focused rect with empty title."""

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (50, 50)))
    def test_fallback_to_focused_rect_empty_title(self, mock_cap):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=None),
            patch.object(wm, "get_focused_window_rect", return_value=(5, 10, 200, 300)),
        ):
            from core.screenshot import capture_focused_window_with_title

            result = capture_focused_window_with_title()

        assert result is not None
        img, title = result
        assert title == ""
        mock_cap.assert_called_once_with(5, 10, 200, 300)
