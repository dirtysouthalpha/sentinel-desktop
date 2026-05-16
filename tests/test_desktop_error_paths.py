"""Tests for core/desktop.py — error paths and FailSafeException handling."""

from unittest.mock import MagicMock, patch

import pyautogui
import pytest

from core.desktop import DesktopController

# Use the stubbed FailSafeException from conftest
FailSafeException = pyautogui.FailSafeException


class TestInitFallback:
    def test_screen_size_fallback_on_oserror(self):
        with patch("core.desktop.pyautogui.size", side_effect=OSError("no display")):
            c = DesktopController()
            assert c.get_screen_size() == (1920, 1080)

    def test_screen_size_fallback_on_runtime_error(self):
        with patch("core.desktop.pyautogui.size", side_effect=RuntimeError("err")):
            c = DesktopController()
            assert c.get_screen_size() == (1920, 1080)

    def test_screen_size_fallback_on_value_error(self):
        with patch("core.desktop.pyautogui.size", side_effect=ValueError("err")):
            c = DesktopController()
            assert c.get_screen_size() == (1920, 1080)


class TestScreenshotErrorPaths:
    def test_screenshot_raises_on_failure(self):
        with patch("core.desktop.pyautogui.screenshot", side_effect=RuntimeError("fail")):
            c = DesktopController()
            with pytest.raises(RuntimeError, match="fail"):
                c.screenshot()

    def test_screenshot_base64_raises_on_failure(self):
        with patch("core.desktop.pyautogui.screenshot", side_effect=OSError("fail")):
            c = DesktopController()
            with pytest.raises(OSError):
                c.screenshot_base64()

    def test_screenshot_region_raises_on_failure(self):
        with patch("core.desktop.pyautogui.screenshot", side_effect=OSError("fail")):
            c = DesktopController()
            with pytest.raises(OSError):
                c.screenshot_region(0, 0, 10, 10)


class TestFailSafeException:
    """Test that FailSafeException is re-raised, not swallowed."""

    def test_click_propagates_failsafe(self):
        with patch("core.desktop.pyautogui.click", side_effect=FailSafeException):
            c = DesktopController()
            with pytest.raises(FailSafeException):
                c.click(0, 0)

    def test_double_click_propagates_failsafe(self):
        with patch("core.desktop.pyautogui.doubleClick", side_effect=FailSafeException):
            c = DesktopController()
            with pytest.raises(FailSafeException):
                c.double_click(0, 0)

    def test_right_click_propagates_failsafe(self):
        with patch("core.desktop.pyautogui.rightClick", side_effect=FailSafeException):
            c = DesktopController()
            with pytest.raises(FailSafeException):
                c.right_click(0, 0)

    def test_move_to_propagates_failsafe(self):
        with patch("core.desktop.pyautogui.moveTo", side_effect=FailSafeException):
            c = DesktopController()
            with pytest.raises(FailSafeException):
                c.move_to(0, 0)

    def test_drag_propagates_failsafe(self):
        with patch("core.desktop.pyautogui.moveTo", side_effect=FailSafeException):
            c = DesktopController()
            with pytest.raises(FailSafeException):
                c.drag(0, 0, 100, 100)

    def test_scroll_propagates_failsafe(self):
        with patch("core.desktop.pyautogui.scroll", side_effect=FailSafeException):
            c = DesktopController()
            with pytest.raises(FailSafeException):
                c.scroll(1)


class TestGenericErrorPaths:
    def test_click_raises_on_generic_error(self):
        with patch("core.desktop.pyautogui.click", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError, match="err"):
                c.click(5, 5)

    def test_double_click_raises_on_error(self):
        with patch("core.desktop.pyautogui.doubleClick", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.double_click(5, 5)

    def test_right_click_raises_on_error(self):
        with patch("core.desktop.pyautogui.rightClick", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.right_click(5, 5)

    def test_move_to_raises_on_error(self):
        with patch("core.desktop.pyautogui.moveTo", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.move_to(5, 5)

    def test_drag_raises_on_error(self):
        with patch("core.desktop.pyautogui.moveTo", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.drag(0, 0, 100, 100)

    def test_scroll_raises_on_error(self):
        with patch("core.desktop.pyautogui.scroll", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.scroll(1)

    def test_get_mouse_position_fallback(self):
        with patch("core.desktop.pyautogui.position", side_effect=OSError("err")):
            c = DesktopController()
            assert c.get_mouse_position() == (0, 0)

    def test_type_text_raises_on_error(self):
        with patch("core.desktop.pyautogui.write", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.type_text("hello")

    def test_press_key_raises_on_error(self):
        with patch("core.desktop.pyautogui.press", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.press_key("enter")

    def test_hotkey_raises_on_error(self):
        with patch("core.desktop.pyautogui.hotkey", side_effect=RuntimeError("err")):
            c = DesktopController()
            with pytest.raises(RuntimeError):
                c.hotkey("ctrl", "c")


class TestFindOnScreenErrorPaths:
    def test_template_read_failure(self):
        mock_cv2 = MagicMock()
        mock_cv2.imread.return_value = None
        mock_cv2.TM_CCOEFF_NORMED = 5
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            c = DesktopController()
            result = c.find_on_screen("bad.png")
            assert result is None

    def test_exception_during_matching(self):
        mock_cv2 = MagicMock()
        mock_cv2.imread.return_value = MagicMock()
        mock_cv2.cvtColor.side_effect = RuntimeError("fail")
        mock_cv2.TM_CCOEFF_NORMED = 5
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            c = DesktopController()
            result = c.find_on_screen("t.png")
            assert result is None


class TestWaitForImageErrorPaths:
    def test_scan_exception_logs_warning(self):
        with patch.object(
            DesktopController, "find_on_screen", side_effect=RuntimeError("scan fail")
        ):
            with patch("core.desktop.time.time", side_effect=[0, 35]):
                with patch("core.desktop.time.sleep"):
                    c = DesktopController()
                    result = c.wait_for_image("t.png", timeout=30)
                    assert result is None
