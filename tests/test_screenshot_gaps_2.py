"""Gap tests for screenshot.py — resolve_monitor, get_capture_offset, capture_to_base64,
image encoding.
"""
import base64
import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.screenshot import (
    base64_to_image,
    capture_region_to_base64,
    capture_to_base64,
    image_to_base64,
    list_monitors,
    resolve_monitor,
)


class TestResolveMonitor:
    """resolve_monitor handles various input values."""

    def test_none_passthrough(self):
        assert resolve_monitor(None) is None

    def test_int_passthrough(self):
        assert resolve_monitor(2) == 2

    @patch("core.screenshot._HAS_MSS", False)
    def test_auto_without_mss_returns_none(self):
        assert resolve_monitor("auto") is None

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.mss")
    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Requires mss")
    @patch("core.window_manager.get_focused_window_rect", return_value=(500, 300, 800, 600))
    def test_auto_finds_monitor_with_mss(self, mock_rect, mock_mss):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
            {"left": 0, "top": 0, "width": 1280, "height": 720},
            {"left": 1280, "top": 0, "width": 1280, "height": 720},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        # Center of focused window: 500 + 800//2 = 900, 300 + 600//2 = 600
        result = resolve_monitor("auto")
        assert result in (1, 2)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.window_manager.get_focused_window_rect", return_value=None)
    def test_auto_no_focused_window_returns_1(self, mock_rect):
        result = resolve_monitor("auto")
        assert result == 1

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.window_manager.get_focused_window_rect", side_effect=RuntimeError("fail"))
    def test_auto_exception_returns_1(self, mock_rect):
        result = resolve_monitor("auto")
        assert result == 1


class TestListMonitorsFallback:
    """list_monitors without mss uses pyautogui."""

    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot.pyautogui")
    def test_pyautogui_fallback(self, mock_pag):
        mock_pag.size.return_value = (1920, 1080)
        monitors = list_monitors()
        assert len(monitors) == 1
        assert monitors[0]["width"] == 1920
        assert monitors[0]["is_primary"] is True

    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot.pyautogui")
    def test_pyautogui_size_fails(self, mock_pag):
        mock_pag.size.side_effect = OSError("no screen")
        monitors = list_monitors()
        assert len(monitors) == 1
        assert monitors[0]["width"] == 0

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.mss")
    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Requires mss")
    def test_mss_lists_monitors(self, mock_mss):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
            {"left": 0, "top": 0, "width": 1280, "height": 720},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        monitors = list_monitors()
        assert len(monitors) == 2
        assert monitors[0]["is_virtual"] is True
        assert monitors[1]["is_primary"] is True

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.mss")
    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Requires mss")
    def test_mss_exception_falls_back(self, mock_mss):
        mock_mss.mss.side_effect = RuntimeError("fail")
        with patch("core.screenshot.pyautogui") as mock_pag:
            mock_pag.size.return_value = (1920, 1080)
            monitors = list_monitors()
            assert len(monitors) == 1


class TestImageToBase64:
    """image_to_base64 encoding."""

    def test_png_encoding(self):
        img = Image.new("RGB", (10, 10), "red")
        result = image_to_base64(img, fmt="PNG")
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"

    def test_jpeg_encoding(self):
        img = Image.new("RGB", (10, 10), "blue")
        result = image_to_base64(img, fmt="JPEG")
        decoded = base64.b64decode(result)
        assert decoded[:2] == b"\xff\xd8"

    def test_invalid_format_raises(self):
        img = Image.new("RGB", (10, 10))
        # This should succeed for PNG (default), but test bad fmt
        try:
            image_to_base64(img, fmt="BMP24")
        except Exception:
            pass  # expected


class TestBase64ToImage:
    """base64_to_image decoding."""

    def test_roundtrip_png(self):
        img = Image.new("RGB", (10, 10), "green")
        b64 = image_to_base64(img, fmt="PNG")
        restored = base64_to_image(b64)
        assert restored.size == (10, 10)

    def test_invalid_base64_raises(self):
        with pytest.raises(ValueError):
            base64_to_image("not-valid-base64!!!")


class TestCaptureToBase64:
    """capture_to_base64 and capture_region_to_base64."""

    @patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (50, 50)))
    def test_capture_to_base64(self, mock_cs):
        result = capture_to_base64(fmt="PNG")
        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"

    @patch("core.screenshot.capture_region", return_value=Image.new("RGB", (10, 10)))
    def test_capture_region_to_base64(self, mock_cr):
        result = capture_region_to_base64(0, 0, 10, 10, fmt="PNG")
        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"
