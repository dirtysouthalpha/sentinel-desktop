"""Tests for core/screenshot.py — image conversion and monitor helpers."""

from PIL import Image

from core.screenshot import base64_to_image, image_to_base64


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
