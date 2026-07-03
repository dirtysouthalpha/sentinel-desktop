"""Tests for core/screenshot.py — image conversion and monitor helpers."""

from unittest.mock import MagicMock, patch

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


class TestBase64ToImageErrors:
    def test_invalid_base64_raises_valueerror(self):
        import pytest

        with pytest.raises(ValueError, match="Invalid base64 image data"):
            base64_to_image("not-valid-base64!!!")

    def test_valid_base64_but_not_image_raises_valueerror(self):
        import base64

        import pytest

        # Valid base64 but not a valid image format
        bad_data = base64.b64encode(b"this is not an image").decode()
        with pytest.raises(ValueError, match="Invalid base64 image data"):
            base64_to_image(bad_data)

    def test_empty_string_raises_valueerror(self):
        import pytest

        with pytest.raises(ValueError, match="Invalid base64 image data"):
            base64_to_image("")


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

    def test_jpeg_format(self):
        from core.screenshot import capture_region_to_base64

        with patch(
            "core.screenshot.capture_region", return_value=Image.new("RGB", (10, 10), "red")
        ):
            b64 = capture_region_to_base64(0, 0, 10, 10, fmt="JPEG")
            assert isinstance(b64, str)
            assert len(b64) > 0


# ===========================================================================
# list_monitors
# ===========================================================================

class TestListMonitors:
    @patch("core.screenshot._HAS_MSS", False)
    def test_without_mss_returns_primary(self):
        from core.screenshot import list_monitors

        with patch("core.screenshot.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mons = list_monitors()
            assert len(mons) == 1
            assert mons[0]["is_primary"] is True
            assert mons[0]["width"] == 1920
            assert mons[0]["height"] == 1080

    @patch("core.screenshot._HAS_MSS", False)
    def test_without_mss_pyautogui_error(self):
        from core.screenshot import list_monitors

        with patch("core.screenshot.pyautogui") as mock_pg:
            mock_pg.size.side_effect = OSError("no display")
            mons = list_monitors()
            assert len(mons) == 1
            assert mons[0]["width"] == 0

    @patch("core.screenshot._HAS_MSS", True)
    def test_with_mss_returns_monitors(self):
        from core.screenshot import list_monitors

        mock_sct = MagicMock()
        mock_sct.__enter__ = lambda s: s
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        with patch("core.screenshot.mss") as mock_mss:
            mock_mss.mss.return_value = mock_sct
            mons = list_monitors()
            assert len(mons) == 2
            assert mons[0]["is_virtual"] is True
            assert mons[1]["is_primary"] is True

    @patch("core.screenshot._HAS_MSS", True)
    def test_with_mss_error_falls_back(self):
        from core.screenshot import list_monitors

        with patch("core.screenshot.mss") as mock_mss:
            mock_mss.mss.side_effect = RuntimeError("mss fail")
            mock_mss.ScreenShotError = RuntimeError
            with patch("core.screenshot.pyautogui") as mock_pg:
                mock_pg.size.return_value = (1920, 1080)
                mons = list_monitors()
                assert len(mons) == 1


# ===========================================================================
# capture_screen
# ===========================================================================

class TestCaptureScreen:
    @patch("core.screenshot._HAS_MSS", False)
    def test_fallback_to_pyautogui(self):
        from core.screenshot import capture_screen

        fake_img = Image.new("RGB", (100, 100), "blue")
        with patch("core.screenshot.pyautogui") as mock_pg:
            mock_pg.screenshot.return_value = fake_img
            result = capture_screen()
            assert result is fake_img

    @patch("core.screenshot._HAS_MSS", True)
    def test_mss_capture(self):
        from core.screenshot import capture_screen

        mock_raw = MagicMock()
        mock_raw.size = (100, 100)
        mock_raw.rgb = b"\x00" * (100 * 100 * 3)

        mock_sct = MagicMock()
        mock_sct.__enter__ = lambda s: s
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
        mock_sct.grab.return_value = mock_raw

        with patch("core.screenshot.mss") as mock_mss:
            mock_mss.mss.return_value = mock_sct
            result = capture_screen(monitor=0)
            assert isinstance(result, Image.Image)

    @patch("core.screenshot._HAS_MSS", True)
    def test_mss_out_of_range_falls_back(self):
        from core.screenshot import capture_screen

        fake_img = Image.new("RGB", (100, 100))
        mock_sct = MagicMock()
        mock_sct.__enter__ = lambda s: s
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]

        with patch("core.screenshot.mss") as mock_mss, \
             patch("core.screenshot.pyautogui") as mock_pg:
            mock_mss.mss.return_value = mock_sct
            mock_pg.screenshot.return_value = fake_img
            result = capture_screen(monitor=99)
            assert result is fake_img

    @patch("core.screenshot._HAS_MSS", False)
    def test_pyautogui_fails_raises(self):
        import pytest

        from core.screenshot import capture_screen

        with patch("core.screenshot.pyautogui") as mock_pg:
            mock_pg.screenshot.side_effect = OSError("no screen")
            with pytest.raises(OSError, match="All screen capture methods failed"):
                capture_screen()


# ===========================================================================
# capture_region
# ===========================================================================

class TestCaptureRegion:
    @patch("core.screenshot._HAS_MSS", False)
    def test_fallback_to_pyautogui(self):
        from core.screenshot import capture_region

        fake_img = Image.new("RGB", (50, 50), "green")
        with patch("core.screenshot.pyautogui") as mock_pg:
            mock_pg.screenshot.return_value = fake_img
            capture_region(10, 20, 50, 50)
            mock_pg.screenshot.assert_called_with(region=(10, 20, 50, 50))

    @patch("core.screenshot._HAS_MSS", True)
    def test_mss_region_capture(self):
        from core.screenshot import capture_region

        mock_raw = MagicMock()
        mock_raw.size = (50, 50)
        mock_raw.rgb = b"\x00" * (50 * 50 * 3)

        mock_sct = MagicMock()
        mock_sct.__enter__ = lambda s: s
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_sct.grab.return_value = mock_raw

        with patch("core.screenshot.mss") as mock_mss:
            mock_mss.mss.return_value = mock_sct
            result = capture_region(0, 0, 50, 50)
            assert isinstance(result, Image.Image)

    @patch("core.screenshot._HAS_MSS", False)
    def test_pyautogui_fails_raises(self):
        import pytest

        from core.screenshot import capture_region

        with patch("core.screenshot.pyautogui") as mock_pg:
            mock_pg.screenshot.side_effect = OSError("nope")
            with pytest.raises(OSError, match="Region capture failed"):
                capture_region(0, 0, 10, 10)


# ===========================================================================
# capture_focused_window / capture_focused_window_with_title
# ===========================================================================

class TestCaptureFocusedWindow:
    def test_no_target_returns_none(self):
        from core.screenshot import capture_focused_window

        with patch("core.window_manager") as mock_wm:
            mock_wm.get_target_window_rect.return_value = None
            mock_wm.get_focused_window_rect.return_value = None
            result = capture_focused_window()
            assert result is None

    def test_zero_size_returns_none(self):
        from core.screenshot import capture_focused_window

        with patch("core.window_manager") as mock_wm:
            mock_wm.get_target_window_rect.return_value = None
            mock_wm.get_focused_window_rect.return_value = (10, 20, 0, 50)
            result = capture_focused_window()
            assert result is None

    def test_fallback_to_focused_window(self):
        from core.screenshot import capture_focused_window

        fake_img = Image.new("RGB", (100, 100))
        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", return_value=fake_img) as mock_cap:
            mock_wm.get_target_window_rect.return_value = None
            mock_wm.get_focused_window_rect.return_value = (10, 20, 100, 200)
            result = capture_focused_window()
            assert result is fake_img
            mock_cap.assert_called_with(10, 20, 100, 200)

    def test_target_window_with_title(self):
        from core.screenshot import capture_focused_window

        fake_img = Image.new("RGB", (100, 100))
        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", return_value=fake_img):
            mock_wm.get_target_window_rect.return_value = (50, 60, 100, 200, "Notepad")
            result = capture_focused_window()
            assert result is fake_img

    def test_capture_region_error_returns_none(self):
        from core.screenshot import capture_focused_window

        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", side_effect=OSError("fail")):
            mock_wm.get_target_window_rect.return_value = None
            mock_wm.get_focused_window_rect.return_value = (10, 20, 100, 200)
            result = capture_focused_window()
            assert result is None


class TestCaptureFocusedWindowWithTitle:
    def test_no_windows_returns_none(self):
        from core.screenshot import capture_focused_window_with_title

        with patch("core.window_manager") as mock_wm:
            mock_wm.get_target_window_rect.return_value = None
            mock_wm.get_focused_window_rect.return_value = None
            result = capture_focused_window_with_title()
            assert result is None

    def test_returns_image_and_title(self):
        from core.screenshot import capture_focused_window_with_title

        fake_img = Image.new("RGB", (100, 100))
        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", return_value=fake_img):
            mock_wm.get_target_window_rect.return_value = (0, 0, 100, 100, "Chrome")
            result = capture_focused_window_with_title()
            assert result is not None
            assert result[0] is fake_img
            assert result[1] == "Chrome"

    def test_fallback_empty_title(self):
        from core.screenshot import capture_focused_window_with_title

        fake_img = Image.new("RGB", (100, 100))
        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", return_value=fake_img):
            mock_wm.get_target_window_rect.return_value = None
            mock_wm.get_focused_window_rect.return_value = (0, 0, 100, 100)
            result = capture_focused_window_with_title()
            assert result is not None
            assert result[1] == ""


# ===========================================================================
# capture_window
# ===========================================================================

class TestCaptureWindow:
    def test_no_rect_returns_none(self):
        from core.screenshot import capture_window

        with patch("core.window_manager") as mock_wm:
            mock_wm.restore_window.return_value = None
            mock_wm.get_window_rect.return_value = None
            result = capture_window("Missing")
            assert result is None

    def test_zero_size_returns_none(self):
        from core.screenshot import capture_window

        with patch("core.window_manager") as mock_wm:
            mock_wm.restore_window.return_value = None
            mock_wm.get_window_rect.return_value = (10, 20, 0, 50)
            with patch("core.screenshot.time"):
                result = capture_window("Tiny")
            assert result is None

    def test_valid_window_captured(self):
        from core.screenshot import capture_window

        fake_img = Image.new("RGB", (200, 100))
        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", return_value=fake_img) as mock_cap, \
             patch("core.screenshot.time"):
            mock_wm.restore_window.return_value = None
            mock_wm.get_window_rect.return_value = (50, 60, 200, 100)
            result = capture_window("Notepad")
            assert result is fake_img
            mock_cap.assert_called_with(50, 60, 200, 100)

    def test_capture_error_returns_none(self):
        from core.screenshot import capture_window

        with patch("core.window_manager") as mock_wm, \
             patch("core.screenshot.capture_region", side_effect=OSError("nope")), \
             patch("core.screenshot.time"):
            mock_wm.restore_window.return_value = None
            mock_wm.get_window_rect.return_value = (50, 60, 200, 100)
            result = capture_window("Broken")
            assert result is None


# ===========================================================================
# capture_to_base64
# ===========================================================================

class TestCaptureToBase64:
    def test_produces_base64_string(self):
        import base64

        from core.screenshot import capture_to_base64

        fake_img = Image.new("RGB", (10, 10), "red")
        with patch("core.screenshot.capture_screen", return_value=fake_img):
            b64 = capture_to_base64()
            raw = base64.b64decode(b64)
            assert raw[:4] == b"\x89PNG"

    def test_jpeg_format(self):
        from core.screenshot import capture_to_base64

        fake_img = Image.new("RGB", (10, 10), "red")
        with patch("core.screenshot.capture_screen", return_value=fake_img):
            b64 = capture_to_base64(fmt="JPEG")
            assert isinstance(b64, str)
            assert len(b64) > 0


# ===========================================================================
# find_template / wait_for_template
# ===========================================================================

class TestFindTemplate:
    def test_no_cv2_returns_none(self):
        # Capture the real __import__ BEFORE patching to avoid infinite recursion.
        import builtins

        from core.screenshot import find_template

        _real_import = builtins.__import__

        def _block_cv2(name, *args, **kwargs):
            if name in ("cv2", "numpy"):
                raise ImportError("no %s" % name)
            return _real_import(name, *args, **kwargs)

        with patch.dict("sys.modules", {"cv2": None, "numpy": None}):
            with patch("builtins.__import__", side_effect=_block_cv2):
                result = find_template("test.png")
                assert result is None


class TestWaitForTemplate:
    def test_immediate_match(self):
        from core.screenshot import wait_for_template

        with patch("core.screenshot.find_template", return_value=(100, 200)):
            result = wait_for_template("found.png", timeout=5)
            assert result == (100, 200)

    def test_timeout_returns_none(self):
        from core.screenshot import wait_for_template

        with patch("core.screenshot.find_template", return_value=None), \
             patch("core.screenshot.time") as mock_time:
            # Simulate time passing beyond timeout
            mock_time.time.side_effect = [0, 0.5, 31]  # start, check, past timeout
            mock_time.sleep = MagicMock()
            result = wait_for_template("missing.png", timeout=30)
            assert result is None


# ===========================================================================
# get_capture_offset — additional coverage
# ===========================================================================

class TestGetCaptureOffsetExtra:
    @patch("core.screenshot._HAS_MSS", True)
    def test_mss_monitor_offset(self):
        from core.screenshot import get_capture_offset

        mock_sct = MagicMock()
        mock_sct.__enter__ = lambda s: s
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]

        with patch("core.screenshot.mss") as mock_mss, \
             patch("core.screenshot.resolve_monitor", return_value=1):
            mock_mss.mss.return_value = mock_sct
            result = get_capture_offset(1)
            assert result == (1920, 0)

    @patch("core.screenshot._HAS_MSS", True)
    def test_mss_error_returns_zero(self):
        from core.screenshot import get_capture_offset

        with patch("core.screenshot.mss") as mock_mss, \
             patch("core.screenshot.resolve_monitor", return_value=1):
            mock_mss.mss.side_effect = RuntimeError("fail")
            mock_mss.ScreenShotError = RuntimeError
            result = get_capture_offset(1)
            assert result == (0, 0)
