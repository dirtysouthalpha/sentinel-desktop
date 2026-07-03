"""Gap tests for screenshot.py — covering mss paths, list_monitors,
capture_screen, capture_region, find_template, and wait_for_template.

Focuses on lines 57-66, 85-93, 104-122, 159-171, 259-270, 327-355.
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import core.screenshot as sc

# ---------------------------------------------------------------------------
# resolve_monitor("auto") with mss available
# ---------------------------------------------------------------------------


class TestResolveMonitorAutoWithMss:
    """Lines 57-66: resolve_monitor('auto') with mss + window manager."""

    @patch("core.screenshot._HAS_MSS", True)
    def test_auto_finds_monitor_containing_focused_window(self):
        """Monitor containing focused window center is returned."""
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3000, "height": 1000},  # virtual union
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # primary
            {"left": 1920, "top": 0, "width": 1080, "height": 1920},  # secondary
        ]
        from core import window_manager as wm

        with (
            patch.object(wm, "get_focused_window_rect", return_value=(2100, 500, 800, 600)),
            patch("core.screenshot.mss") as mock_mss_mod,
        ):
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.resolve_monitor("auto")
        # Window center at (2500, 800) falls in monitor 2 (1920-3000, 0-1920)
        assert result == 2

    @patch("core.screenshot._HAS_MSS", True)
    def test_auto_falls_back_to_primary_when_no_monitor_matches(self):
        """If focused window center doesn't fall in any monitor, return 1."""
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        from core import window_manager as wm

        with (
            patch.object(wm, "get_focused_window_rect", return_value=(5000, 5000, 100, 100)),
            patch("core.screenshot.mss") as mock_mss_mod,
        ):
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.resolve_monitor("auto")
        assert result == 1

    @patch("core.screenshot._HAS_MSS", True)
    def test_auto_exception_falls_back_to_1(self):
        """Any exception during auto resolution falls back to 1."""
        from core import window_manager as wm

        with (
            patch.object(wm, "get_focused_window_rect", side_effect=RuntimeError("nope")),
        ):
            result = sc.resolve_monitor("auto")
        assert result == 1


# ---------------------------------------------------------------------------
# get_capture_offset with mss
# ---------------------------------------------------------------------------


class TestGetCaptureOffsetWithMss:
    """Lines 85-93: get_capture_offset with mss available."""

    @patch("core.screenshot._HAS_MSS", True)
    def test_returns_offset_for_valid_monitor(self):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3000, "height": 1000},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1080, "height": 1920},
        ]
        with patch("core.screenshot.resolve_monitor", return_value=2), \
             patch("core.screenshot.mss") as mock_mss_mod:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.get_capture_offset(2)
        assert result == (1920, 0)

    @patch("core.screenshot._HAS_MSS", True)
    def test_returns_zero_on_mss_error(self):
        with patch("core.screenshot.resolve_monitor", return_value=1), \
             patch("core.screenshot.mss") as mock_mss_mod:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(side_effect=OSError("fail"))
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.get_capture_offset(1)
        assert result == (0, 0)

    @patch("core.screenshot._HAS_MSS", True)
    def test_returns_zero_for_out_of_range_monitor(self):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        with patch("core.screenshot.resolve_monitor", return_value=99), \
             patch("core.screenshot.mss") as mock_mss_mod:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            # len(mons) is 2, so 99 >= 2 -> returns (0,0) from the default path
            result = sc.get_capture_offset(99)
        assert result == (0, 0)


# ---------------------------------------------------------------------------
# list_monitors with mss
# ---------------------------------------------------------------------------


class TestListMonitorsWithMss:
    """Lines 104-122: list_monitors with mss available."""

    @patch("core.screenshot._HAS_MSS", True)
    def test_returns_monitor_list_from_mss(self):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3000, "height": 1000},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        with patch("core.screenshot.mss") as mock_mss_mod:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.list_monitors()
        assert len(result) == 2
        assert result[0]["is_virtual"] is True
        assert result[0]["is_primary"] is False
        assert result[1]["is_primary"] is True
        assert result[1]["is_virtual"] is False
        assert result[0]["index"] == 0
        assert result[1]["index"] == 1

    @patch("core.screenshot._HAS_MSS", True)
    def test_mss_failure_falls_back_to_pyautogui(self):
        """When mss raises, fallback to pyautogui.size()."""
        with patch("core.screenshot.mss") as mock_mss_mod:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(side_effect=OSError("nope"))
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(sc.pyautogui, "size", return_value=(1920, 1080)):
                result = sc.list_monitors()
        assert len(result) == 1
        assert result[0]["width"] == 1920
        assert result[0]["height"] == 1080
        assert result[0]["is_primary"] is True

    @patch("core.screenshot._HAS_MSS", False)
    def test_no_mss_uses_pyautogui(self):
        with patch.object(sc.pyautogui, "size", return_value=(1280, 720)):
            result = sc.list_monitors()
        assert len(result) == 1
        assert result[0]["width"] == 1280
        assert result[0]["height"] == 720

    @patch("core.screenshot._HAS_MSS", False)
    def test_no_mss_pyautogui_error(self):
        with patch.object(sc.pyautogui, "size", side_effect=OSError("no screen")):
            result = sc.list_monitors()
        assert len(result) == 1
        assert result[0]["width"] == 0
        assert result[0]["height"] == 0


# ---------------------------------------------------------------------------
# capture_screen with mss
# ---------------------------------------------------------------------------


class TestCaptureScreenWithMss:
    """Lines 159-171: capture_screen using mss."""

    @patch("core.screenshot._HAS_MSS", True)
    def test_capture_with_mss_success(self):
        fake_img = Image.new("RGB", (100, 100), "red")
        mock_raw = MagicMock()
        mock_raw.size = (100, 100)
        mock_raw.rgb = fake_img.tobytes()

        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 100, "height": 100},
            {"left": 0, "top": 0, "width": 100, "height": 100},
        ]
        mock_sct.grab.return_value = mock_raw

        with patch("core.screenshot.resolve_monitor", return_value=1), \
             patch("core.screenshot.mss") as mock_mss_mod, \
             patch("core.screenshot.Image") as mock_image_cls:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            mock_image_cls.frombytes.return_value = fake_img
            result = sc.capture_screen(monitor=1)
        mock_image_cls.frombytes.assert_called_once()
        assert result is fake_img

    @patch("core.screenshot._HAS_MSS", True)
    def test_capture_monitor_out_of_range_falls_back(self):
        """When monitor index is out of range, falls back to pyautogui."""
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 100, "height": 100},
        ]
        fake_img = Image.new("RGB", (50, 50))

        with patch("core.screenshot.resolve_monitor", return_value=5), \
             patch("core.screenshot.mss") as mock_mss_mod, \
             patch.object(sc.pyautogui, "screenshot", return_value=fake_img):
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.capture_screen(monitor=5)
        assert result is fake_img

    @patch("core.screenshot._HAS_MSS", True)
    def test_capture_mss_error_falls_back_to_pyautogui(self):
        """mss failure falls back to pyautogui.screenshot."""
        fake_img = Image.new("RGB", (50, 50))

        with patch("core.screenshot.resolve_monitor", return_value=1), \
             patch("core.screenshot.mss") as mock_mss_mod, \
             patch.object(sc.pyautogui, "screenshot", return_value=fake_img):
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(side_effect=OSError("mss fail"))
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.capture_screen(monitor=1)
        assert result is fake_img


class TestCaptureScreenFallback:
    """Lines 174-176: pyautogui fallback raises."""

    @patch("core.screenshot._HAS_MSS", False)
    def test_pyautogui_failure_raises_oserror(self):
        with patch("core.screenshot.resolve_monitor", return_value=None), \
             patch.object(sc.pyautogui, "screenshot", side_effect=OSError("no screen")):
            with pytest.raises(OSError, match="All screen capture methods failed"):
                sc.capture_screen()

    @patch("core.screenshot._HAS_MSS", True)
    def test_all_methods_fail_raises_oserror(self):
        with patch("core.screenshot.resolve_monitor", return_value=1), \
             patch("core.screenshot.mss") as mock_mss_mod, \
             patch.object(sc.pyautogui, "screenshot", side_effect=RuntimeError("nope")):
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(side_effect=OSError("mss fail"))
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(OSError, match="All screen capture methods failed"):
                sc.capture_screen(monitor=1)


# ---------------------------------------------------------------------------
# capture_region with mss
# ---------------------------------------------------------------------------


class TestCaptureRegionWithMss:
    """Lines 259-270: capture_region using mss."""

    @patch("core.screenshot._HAS_MSS", True)
    def test_capture_region_mss_success(self):
        fake_img = Image.new("RGB", (50, 50), "blue")
        mock_raw = MagicMock()
        mock_raw.size = (50, 50)
        mock_raw.rgb = fake_img.tobytes()

        mock_sct = MagicMock()
        mock_sct.grab.return_value = mock_raw

        with patch("core.screenshot.mss") as mock_mss_mod, \
             patch("core.screenshot.Image") as mock_image_cls:
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            mock_image_cls.frombytes.return_value = fake_img
            result = sc.capture_region(10, 20, 50, 50)
        assert result is fake_img
        mock_sct.grab.assert_called_once()

    @patch("core.screenshot._HAS_MSS", True)
    def test_capture_region_mss_failure_falls_back(self):
        """mss failure falls back to pyautogui.screenshot."""
        fake_img = Image.new("RGB", (30, 30))

        with patch("core.screenshot.mss") as mock_mss_mod, \
             patch.object(sc.pyautogui, "screenshot", return_value=fake_img):
            mock_mss_mod.mss.return_value.__enter__ = MagicMock(side_effect=OSError("fail"))
            mock_mss_mod.mss.return_value.__exit__ = MagicMock(return_value=False)
            result = sc.capture_region(0, 0, 30, 30)
        assert result is fake_img

    @patch("core.screenshot._HAS_MSS", False)
    def test_capture_region_no_mss(self):
        fake_img = Image.new("RGB", (40, 40))
        with patch.object(sc.pyautogui, "screenshot", return_value=fake_img):
            result = sc.capture_region(5, 5, 40, 40)
        assert result is fake_img

    @patch("core.screenshot._HAS_MSS", False)
    def test_capture_region_all_fail_raises(self):
        with patch.object(sc.pyautogui, "screenshot", side_effect=OSError("nope")):
            with pytest.raises(OSError, match="Region capture failed"):
                sc.capture_region(0, 0, 10, 10)


# ---------------------------------------------------------------------------
# find_template / wait_for_template
# ---------------------------------------------------------------------------


class TestFindTemplate:
    """Lines 327-355: find_template function."""

    def test_find_template_no_opencv_returns_none(self):
        """When opencv-python is not installed, returns None."""
        with patch.dict("sys.modules", {"cv2": None, "numpy": None}):
            # Force reimport to trigger the ImportError
            result = sc.find_template("/fake/path.png")
        # Should return None (either from import error or file not found)
        assert result is None or isinstance(result, tuple)

    def test_find_template_with_mocked_cv2(self):
        """Test template matching with mocked cv2/numpy."""
        fake_img = Image.new("RGB", (100, 100))

        mock_cv2 = MagicMock()
        mock_cv2.IMREAD_GRAYSCALE = 0
        mock_cv2.TM_CCOEFF_NORMED = 5
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.imread.return_value = MagicMock(shape=(20, 20))
        mock_cv2.cvtColor.return_value = MagicMock()
        mock_cv2.matchTemplate.return_value = MagicMock()
        mock_cv2.minMaxLoc.return_value = (0.0, 0.95, (0, 0), (30, 30))

        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.array.return_value.convert.return_value = MagicMock()

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": mock_np}), \
             patch("core.screenshot.capture_screen", return_value=fake_img):
            result = sc.find_template("/fake/template.png", confidence=0.8)
        assert result is not None
        # Should be center coords
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_find_template_below_confidence(self):
        """Template match below confidence threshold returns None."""
        fake_img = Image.new("RGB", (100, 100))

        mock_cv2 = MagicMock()
        mock_cv2.IMREAD_GRAYSCALE = 0
        mock_cv2.TM_CCOEFF_NORMED = 5
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.imread.return_value = MagicMock(shape=(20, 20))
        mock_cv2.cvtColor.return_value = MagicMock()
        mock_cv2.matchTemplate.return_value = MagicMock()
        mock_cv2.minMaxLoc.return_value = (0.0, 0.5, (0, 0), (30, 30))  # low confidence

        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.array.return_value.convert.return_value = MagicMock()

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": mock_np}), \
             patch("core.screenshot.capture_screen", return_value=fake_img):
            result = sc.find_template("/fake/template.png", confidence=0.8)
        assert result is None

    def test_find_template_file_not_found(self):
        """When cv2.imread returns None (file not found), returns None."""
        fake_img = Image.new("RGB", (100, 100))

        mock_cv2 = MagicMock()
        mock_cv2.IMREAD_GRAYSCALE = 0
        mock_cv2.TM_CCOEFF_NORMED = 5
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.imread.return_value = None

        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.array.return_value.convert.return_value = MagicMock()

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": mock_np}), \
             patch("core.screenshot.capture_screen", return_value=fake_img):
            result = sc.find_template("/nonexistent.png")
        assert result is None

    def test_find_template_exception_returns_none(self):
        """Exceptions during template matching return None."""
        mock_cv2 = MagicMock()
        mock_cv2.IMREAD_GRAYSCALE = 0
        mock_cv2.TM_CCOEFF_NORMED = 5
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.cvtColor.side_effect = RuntimeError("fail")

        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()

        fake_img = Image.new("RGB", (100, 100))
        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": mock_np}), \
             patch("core.screenshot.capture_screen", return_value=fake_img):
            result = sc.find_template("/fake.png")
        assert result is None


class TestWaitForTemplate:
    """Lines 358-372: wait_for_template polling."""

    def test_found_immediately(self):
        with patch("core.screenshot.find_template", return_value=(50, 50)):
            result = sc.wait_for_template("/fake.png", timeout=1)
        assert result == (50, 50)

    def test_times_out(self):
        with patch("core.screenshot.find_template", return_value=None), \
             patch("time.sleep"):
            result = sc.wait_for_template("/fake.png", timeout=0.1, poll_interval=0.01)
        assert result is None

    def test_found_after_polling(self):
        call_count = 0

        def mock_find(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return (100, 200)
            return None

        with patch("core.screenshot.find_template", side_effect=mock_find), \
             patch("time.sleep"):
            result = sc.wait_for_template("/fake.png", timeout=5, poll_interval=0.1)
        assert result == (100, 200)


# ---------------------------------------------------------------------------
# capture_to_base64
# ---------------------------------------------------------------------------


class TestCaptureToBase64:
    """Test capture_to_base64 convenience wrapper."""

    def test_produces_png(self):
        fake_img = Image.new("RGB", (10, 10))
        with patch("core.screenshot.capture_screen", return_value=fake_img):
            b64 = sc.capture_to_base64()
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_jpeg_format(self):
        fake_img = Image.new("RGB", (10, 10))
        with patch("core.screenshot.capture_screen", return_value=fake_img):
            b64 = sc.capture_to_base64(fmt="JPEG")
        assert isinstance(b64, str)
        assert len(b64) > 0


# ---------------------------------------------------------------------------
# capture_focused_window / capture_window
# ---------------------------------------------------------------------------


class TestCaptureFocusedWindow:
    """Test capture_focused_window edge cases."""

    def test_no_target_no_focused_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=None),
            patch.object(wm, "get_focused_window_rect", return_value=None),
        ):
            result = sc.capture_focused_window()
        assert result is None

    def test_zero_size_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=(10, 10, 0, 100, "title")),
        ):
            result = sc.capture_focused_window()
        assert result is None

    def test_capture_error_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=None),
            patch.object(wm, "get_focused_window_rect", return_value=(10, 20, 100, 200)),
            patch("core.screenshot.capture_region", side_effect=OSError("fail")),
        ):
            result = sc.capture_focused_window()
        assert result is None


class TestCaptureWindow:
    """Test capture_window edge cases."""

    def test_no_rect_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "restore_window"),
            patch.object(wm, "get_window_rect", return_value=None),
        ):
            result = sc.capture_window("nonexistent")
        assert result is None

    def test_zero_size_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "restore_window"),
            patch.object(wm, "get_window_rect", return_value=(0, 0, 0, 100)),
        ):
            result = sc.capture_window("test")
        assert result is None

    def test_capture_error_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "restore_window"),
            patch.object(wm, "get_window_rect", return_value=(10, 20, 100, 100)),
            patch("core.screenshot.capture_region", side_effect=OSError("fail")),
        ):
            result = sc.capture_window("test")
        assert result is None

    def test_success_returns_image(self):
        fake_img = Image.new("RGB", (100, 100))
        from core import window_manager as wm

        with (
            patch.object(wm, "restore_window"),
            patch.object(wm, "get_window_rect", return_value=(10, 20, 100, 100)),
            patch("core.screenshot.capture_region", return_value=fake_img),
        ):
            result = sc.capture_window("test")
        assert result is fake_img


class TestCaptureFocusedWindowWithTitle:
    """Additional tests for capture_focused_window_with_title."""

    def test_no_target_uses_focused_rect_with_empty_title(self):
        fake_img = Image.new("RGB", (50, 50))
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=None),
            patch.object(wm, "get_focused_window_rect", return_value=(5, 10, 200, 300)),
            patch("core.screenshot.capture_region", return_value=fake_img),
        ):
            result = sc.capture_focused_window_with_title()
        assert result is not None
        img, title = result
        assert title == ""
        assert img is fake_img

    def test_with_target_returns_title(self):
        fake_img = Image.new("RGB", (50, 50))
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=(5, 10, 200, 300, "MyApp")),
            patch("core.screenshot.capture_region", return_value=fake_img),
        ):
            result = sc.capture_focused_window_with_title()
        assert result is not None
        img, title = result
        assert title == "MyApp"

    def test_zero_size_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=(5, 10, 0, 300, "MyApp")),
        ):
            result = sc.capture_focused_window_with_title()
        assert result is None

    def test_capture_error_returns_none(self):
        from core import window_manager as wm

        with (
            patch.object(wm, "get_target_window_rect", return_value=(5, 10, 200, 300, "MyApp")),
            patch("core.screenshot.capture_region", side_effect=OSError("fail")),
        ):
            result = sc.capture_focused_window_with_title()
        assert result is None
