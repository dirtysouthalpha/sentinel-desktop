"""Gap tests for screenshot.py — capture_screen, capture_region, get_capture_offset, find_template."""

from unittest.mock import MagicMock, patch

from PIL import Image

from core.screenshot import (
    capture_region,
    capture_screen,
    find_template,
    get_capture_offset,
)


class TestCaptureScreenMssPaths:
    """capture_screen with mss available."""

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=1)
    @patch("core.screenshot.mss")
    def test_mss_capture_success(self, mock_mss, mock_resolve):
        mock_sct = MagicMock()
        mock_raw = MagicMock()
        mock_raw.size = (100, 100)
        mock_raw.rgb = b"\x00" * (100 * 100 * 3)
        mock_sct.grab.return_value = mock_raw
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        img = capture_screen()
        assert img.size == (100, 100)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=99)
    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot.mss")
    def test_mss_monitor_out_of_range_falls_back(self, mock_mss, mock_pag, mock_resolve):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        mock_pag.screenshot.return_value = Image.new("RGB", (50, 50))
        img = capture_screen()
        assert img.size == (50, 50)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=1)
    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot.mss")
    def test_mss_exception_falls_back_to_pyautogui(self, mock_mss, mock_pag, mock_resolve):
        mock_mss.mss.side_effect = RuntimeError("mss crashed")
        mock_pag.screenshot.return_value = Image.new("RGB", (30, 30))
        img = capture_screen()
        assert img.size == (30, 30)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=1)
    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot.mss")
    def test_mss_and_pyautogui_both_fail(self, mock_mss, mock_pag, mock_resolve):
        mock_mss.mss.side_effect = RuntimeError("mss dead")
        mock_pag.screenshot.side_effect = OSError("no screen")
        try:
            capture_screen()
            raise AssertionError("Should have raised OSError")
        except OSError as e:
            assert "All screen capture methods failed" in str(e)

    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot.resolve_monitor", return_value=None)
    @patch("core.screenshot.pyautogui")
    def test_no_mss_uses_pyautogui(self, mock_pag, mock_resolve):
        mock_pag.screenshot.return_value = Image.new("RGB", (40, 40))
        img = capture_screen()
        assert img.size == (40, 40)


class TestCaptureRegionMssPaths:
    """capture_region with mss available."""

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.mss")
    def test_mss_region_capture_success(self, mock_mss):
        mock_sct = MagicMock()
        mock_raw = MagicMock()
        mock_raw.size = (50, 50)
        mock_raw.rgb = b"\x00" * (50 * 50 * 3)
        mock_sct.grab.return_value = mock_raw
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        img = capture_region(0, 0, 50, 50)
        assert img.size == (50, 50)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot.mss")
    def test_mss_region_fails_falls_back(self, mock_mss, mock_pag):
        mock_mss.mss.side_effect = RuntimeError("region fail")
        mock_pag.screenshot.return_value = Image.new("RGB", (10, 10))
        img = capture_region(0, 0, 10, 10)
        assert img.size == (10, 10)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot.mss")
    def test_mss_and_pyautogui_region_both_fail(self, mock_mss, mock_pag):
        mock_mss.mss.side_effect = RuntimeError("mss dead")
        mock_pag.screenshot.side_effect = OSError("nope")
        try:
            capture_region(0, 0, 10, 10)
            raise AssertionError("Should have raised OSError")
        except OSError as e:
            assert "Region capture failed" in str(e)

    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot.pyautogui")
    def test_no_mss_region_uses_pyautogui(self, mock_pag):
        mock_pag.screenshot.return_value = Image.new("RGB", (20, 20))
        img = capture_region(0, 0, 20, 20)
        assert img.size == (20, 20)


class TestGetCaptureOffsetWithMss:
    """get_capture_offset with mss returns real offsets."""

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=2)
    @patch("core.screenshot.mss")
    def test_returns_monitor_offset(self, mock_mss, mock_resolve):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
            {"left": 0, "top": 0, "width": 1280, "height": 720},
            {"left": 1280, "top": 0, "width": 1280, "height": 720},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        result = get_capture_offset(2)
        assert result == (1280, 0)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=1)
    @patch("core.screenshot.mss")
    def test_primary_monitor_returns_zero_offset(self, mock_mss, mock_resolve):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        result = get_capture_offset(1)
        assert result == (0, 0)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=99)
    @patch("core.screenshot.mss")
    def test_out_of_range_returns_zero(self, mock_mss, mock_resolve):
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_sct)
        mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
        result = get_capture_offset(99)
        assert result == (0, 0)

    @patch("core.screenshot._HAS_MSS", True)
    @patch("core.screenshot.resolve_monitor", return_value=1)
    @patch("core.screenshot.mss")
    def test_mss_exception_returns_zero(self, mock_mss, mock_resolve):
        mock_mss.mss.side_effect = RuntimeError("fail")
        result = get_capture_offset(1)
        assert result == (0, 0)


class TestFindTemplate:
    """find_template with opencv available and error paths."""

    def test_no_opencv_returns_none(self):
        with patch.dict("sys.modules", {"cv2": None, "numpy": None}):
            with patch("builtins.__import__", side_effect=ImportError("no cv2")):
                result = find_template("test.png")
        assert result is None

    @patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (100, 100)))
    def test_template_not_found_on_disk(self, mock_cap):
        cv2_mock = MagicMock()
        cv2_mock.imread.return_value = None
        np_mock = MagicMock()
        np_mock.array.return_value = MagicMock()
        with patch.dict("sys.modules", {"cv2": cv2_mock, "numpy": np_mock}):
            result = find_template("nonexistent.png")
        assert result is None

    @patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (100, 100)))
    def test_template_match_found(self, mock_cap):
        cv2_mock = MagicMock()
        template_mock = MagicMock()
        template_mock.shape = (20, 30)
        cv2_mock.imread.return_value = template_mock
        cv2_mock.COLOR_RGB2GRAY = 7
        cv2_mock.TM_CCOEFF_NORMED = 5
        cv2_mock.IMREAD_GRAYSCALE = 0
        cv2_mock.minMaxLoc.return_value = (0, 0.95, (0, 0), (50, 60))
        np_mock = MagicMock()
        arr_mock = MagicMock()
        np_mock.array.return_value = arr_mock
        with patch.dict("sys.modules", {"cv2": cv2_mock, "numpy": np_mock}):
            result = find_template("btn.png", confidence=0.8)
        assert result is not None
        cx, cy = result
        assert isinstance(cx, int)
        assert isinstance(cy, int)

    @patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (100, 100)))
    def test_template_match_below_confidence(self, mock_cap):
        cv2_mock = MagicMock()
        template_mock = MagicMock()
        template_mock.shape = (20, 30)
        cv2_mock.imread.return_value = template_mock
        cv2_mock.COLOR_RGB2GRAY = 7
        cv2_mock.TM_CCOEFF_NORMED = 5
        cv2_mock.IMREAD_GRAYSCALE = 0
        cv2_mock.minMaxLoc.return_value = (0, 0.5, (0, 0), (50, 60))
        np_mock = MagicMock()
        arr_mock = MagicMock()
        np_mock.array.return_value = arr_mock
        with patch.dict("sys.modules", {"cv2": cv2_mock, "numpy": np_mock}):
            result = find_template("btn.png", confidence=0.8)
        assert result is None

    @patch("core.screenshot.capture_screen", side_effect=RuntimeError("capture fail"))
    def test_capture_exception_returns_none(self, mock_cap):
        cv2_mock = MagicMock()
        np_mock = MagicMock()
        with patch.dict("sys.modules", {"cv2": cv2_mock, "numpy": np_mock}):
            result = find_template("btn.png")
        assert result is None
