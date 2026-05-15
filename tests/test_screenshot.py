"""Tests for core/screenshot.py — image conversion and monitor helpers."""

from unittest.mock import patch

from PIL import Image

from core.screenshot import base64_to_image, get_capture_offset, image_to_base64, resolve_monitor


class TestImageToBase64:
    def test_png_roundtrip(self):
        img = Image.new("RGB", (10, 10), (255, 0, 0))
        b64 = image_to_base64(img, fmt="PNG")
        assert isinstance(b64, str)
        assert len(b64) > 0
        restored = base64_to_image(b64)
        assert restored.size == (10, 10)

    def test_jpeg_roundtrip(self):
        img = Image.new("RGB", (10, 10), (0, 255, 0))
        b64 = image_to_base64(img, fmt="JPEG", quality=90)
        assert isinstance(b64, str)
        restored = base64_to_image(b64)
        assert restored.size == (10, 10)

    def test_default_is_png(self):
        img = Image.new("RGB", (5, 5), "blue")
        b64 = image_to_base64(img)
        # PNG has a known header when base64-decoded
        import base64

        raw = base64.b64decode(b64)
        assert raw[:4] == b"\x89PNG"


class TestBase64ToImage:
    def test_roundtrip_preserves_size(self):
        for size in [(1, 1), (50, 100), (200, 200)]:
            img = Image.new("RGB", size, "white")
            b64 = image_to_base64(img)
            restored = base64_to_image(b64)
            assert restored.size == size

    def test_handles_rgba_image(self):
        img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        b64 = image_to_base64(img, fmt="PNG")
        restored = base64_to_image(b64)
        assert restored.mode == "RGBA"

    def test_jpeg_quality_affects_size(self):
        img = Image.new("RGB", (100, 100))
        low = image_to_base64(img, fmt="JPEG", quality=10)
        high = image_to_base64(img, fmt="JPEG", quality=95)
        # Higher quality should produce larger output
        assert len(high) > len(low)


class TestResolveMonitor:
    def test_int_passthrough(self):
        assert resolve_monitor(2) == 2

    def test_none_passthrough(self):
        assert resolve_monitor(None) is None

    @patch("core.screenshot._HAS_MSS", False)
    def test_auto_without_mss_returns_none(self):
        assert resolve_monitor("auto") is None

    @patch("core.screenshot._HAS_MSS", True)
    def test_auto_with_no_focused_window(self):
        from core import window_manager

        with patch.object(window_manager, "get_focused_window_rect", return_value=None):
            assert resolve_monitor("auto") == 1


class TestGetCaptureOffset:
    def test_returns_zero_without_mss(self):
        with patch("core.screenshot._HAS_MSS", False):
            assert get_capture_offset(1) == (0, 0)

    def test_returns_zero_for_none(self):
        with patch("core.screenshot._HAS_MSS", True):
            assert get_capture_offset(None) == (0, 0)


class TestCaptureRegionToBase64:
    def test_produces_valid_png(self):
        import base64

        from core.screenshot import capture_region_to_base64

        # Mock capture_region to avoid actual screenshot
        with patch(
            "core.screenshot.capture_region", return_value=Image.new("RGB", (10, 10), "red")
        ):
            b64 = capture_region_to_base64(0, 0, 10, 10)
            raw = base64.b64decode(b64)
            assert raw[:4] == b"\x89PNG"
