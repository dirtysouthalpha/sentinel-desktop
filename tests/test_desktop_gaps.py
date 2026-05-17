"""Tests for desktop.py — covering module-level functions and uncovered methods."""

from unittest.mock import MagicMock, patch

import pytest

import core.desktop as desktop_module
from core.desktop import DesktopController


class TestGetMousePosition:
    """get_mouse_position returns pyautogui.position()."""

    @patch("core.desktop.pyautogui.position", return_value=(100, 200))
    def test_returns_position(self, mock_pos: MagicMock) -> None:
        ctrl = DesktopController()
        result = ctrl.get_mouse_position()
        assert result == (100, 200)


class TestFindOnScreenSuccess:
    """find_on_screen with cv2 returning a match."""

    @patch("core.desktop.pyautogui.screenshot")
    def test_find_match_returns_center(self, mock_ss: MagicMock) -> None:
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")

        mock_img = MagicMock()
        mock_ss.return_value = mock_img

        mock_cv2 = MagicMock()
        # 10x20 template
        mock_cv2.imread.return_value = np.zeros((20, 10), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = np.zeros((100, 100), dtype=np.uint8)
        # max_val above confidence, max_loc at (5, 5)
        mock_cv2.minMaxLoc.return_value = (0.0, 0.95, (5, 5), (50, 50))
        mock_cv2.TM_CCOEFF_NORMED = 5

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": np}):
            ctrl = DesktopController()
            result = ctrl.find_on_screen("template.png", confidence=0.8)
        assert result is not None
        # max_loc=(50,50), template shape (20,10): h=20 w=10
        # center = (50 + 10//2, 50 + 20//2) = (55, 60)
        assert result == (55, 60)


class TestWaitForImage:
    """wait_for_image loops until timeout or match."""

    @patch.object(DesktopController, "find_on_screen", return_value=None)
    @patch("core.desktop.time.sleep")
    @patch("core.desktop.time.time", side_effect=[0, 0.5, 1, 35])
    def test_timeout_returns_none(
        self, mock_time: MagicMock, mock_sleep: MagicMock, mock_find: MagicMock
    ) -> None:
        ctrl = DesktopController()
        result = ctrl.wait_for_image("t.png", timeout=30, interval=1)
        assert result is None

    @patch.object(DesktopController, "find_on_screen", return_value=(50, 60))
    @patch("core.desktop.time.time", side_effect=[0, 0.1])
    def test_immediate_match_returns_pos(self, mock_time: MagicMock, mock_find: MagicMock) -> None:
        ctrl = DesktopController()
        result = ctrl.wait_for_image("t.png", timeout=10)
        assert result == (50, 60)


class TestClickImageSuccess:
    """click_image finds image and clicks it."""

    @patch.object(DesktopController, "click")
    @patch.object(DesktopController, "find_on_screen", return_value=(150, 250))
    def test_click_image_clicks(self, mock_find: MagicMock, mock_click: MagicMock) -> None:
        ctrl = DesktopController()
        result = ctrl.click_image("t.png", button="right")
        assert result is True
        mock_click.assert_called_once_with(150, 250, button="right")

    @patch.object(DesktopController, "find_on_screen", return_value=None)
    def test_click_image_no_match(self, mock_find: MagicMock) -> None:
        ctrl = DesktopController()
        result = ctrl.click_image("t.png")
        assert result is False


class TestModuleLevelFunctions:
    """Module-level convenience functions delegate to singleton controller."""

    def setup_method(self) -> None:
        # Reset singleton so each test gets a fresh controller
        desktop_module._ctrl = None

    @patch("core.desktop.pyautogui.screenshot")
    def test_module_screenshot(self, mock_ss: MagicMock) -> None:
        mock_ss.return_value = MagicMock()
        desktop_module.screenshot()
        mock_ss.assert_called_once()

    @patch("core.desktop.pyautogui.screenshot")
    def test_module_screenshot_base64(self, mock_ss: MagicMock) -> None:
        from PIL import Image

        fake_img = Image.new("RGB", (10, 10), "red")
        mock_ss.return_value = fake_img
        result = desktop_module.screenshot_base64()
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("core.desktop.pyautogui.click")
    def test_module_click(self, mock_click: MagicMock) -> None:
        desktop_module.click(10, 20)
        mock_click.assert_called_once()

    @patch("core.desktop.pyautogui.write")
    def test_module_type_text(self, mock_write: MagicMock) -> None:
        desktop_module.type_text("hello")
        mock_write.assert_called_once()

    @patch("core.desktop.pyautogui.press")
    def test_module_press_key(self, mock_press: MagicMock) -> None:
        desktop_module.press_key("enter")
        mock_press.assert_called_once()

    @patch("core.desktop.pyautogui.hotkey")
    def test_module_hotkey(self, mock_hotkey: MagicMock) -> None:
        desktop_module.hotkey("ctrl", "c")
        mock_hotkey.assert_called_once()

    @patch("core.desktop.pyautogui.scroll")
    def test_module_scroll(self, mock_scroll: MagicMock) -> None:
        desktop_module.scroll(5, x=10, y=20)
        mock_scroll.assert_called_once()


class TestDesktopEngineAlias:
    """DesktopEngine is an alias for DesktopController."""

    def test_alias(self) -> None:
        from core.desktop import DesktopEngine

        assert DesktopEngine is DesktopController
