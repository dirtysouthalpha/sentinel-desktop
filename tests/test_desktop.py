"""Tests for core/desktop.py — DesktopController and module-level helpers."""

from unittest.mock import patch

from core.desktop import DesktopController


class TestDesktopControllerInit:
    def test_screen_size_stored(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            assert ctrl.get_screen_size() == (1920, 1080)

    def test_screenshot(self):
        from PIL import Image

        fake_img = Image.new("RGB", (100, 100), "red")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            result = ctrl.screenshot()
            assert result is fake_img

    def test_screenshot_base64(self):
        from PIL import Image

        fake_img = Image.new("RGB", (10, 10), "blue")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            b64 = ctrl.screenshot_base64()
            assert isinstance(b64, str)
            assert len(b64) > 0

    def test_screenshot_region(self):
        from PIL import Image

        fake_img = Image.new("RGB", (50, 50), "green")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            ctrl.screenshot_region(10, 20, 50, 50)
            mock_pg.screenshot.assert_called_with(region=(10, 20, 50, 50))

    def test_click(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.click(100, 200, button="right", clicks=2)
            mock_pg.click.assert_called_with(x=100, y=200, button="right", clicks=2)

    def test_double_click(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.double_click(50, 60)
            mock_pg.doubleClick.assert_called_with(x=50, y=60)

    def test_right_click(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.right_click(30, 40)
            mock_pg.rightClick.assert_called_with(x=30, y=40)

    def test_move_to(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.move_to(100, 200, duration=0.5)
            mock_pg.moveTo.assert_called_with(x=100, y=200, duration=0.5)

    def test_drag(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.drag(10, 20, 100, 200, duration=0.3, button="left")
            mock_pg.moveTo.assert_called_with(10, 20)
            mock_pg.drag.assert_called_with(90, 180, duration=0.3, button="left")

    def test_scroll(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.scroll(3, x=100, y=200)
            mock_pg.scroll.assert_called_with(3, x=100, y=200)

    def test_type_text(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.type_text("hello", interval=0.05)
            mock_pg.write.assert_called_with("hello", interval=0.05)

    def test_press_key(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.press_key("enter")
            mock_pg.press.assert_called_with("enter")

    def test_hotkey(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.hotkey("ctrl", "c")
            mock_pg.hotkey.assert_called_with("ctrl", "c")

    def test_find_on_screen_no_cv2(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            result = ctrl.find_on_screen("nonexistent.png")
            assert result is None

    def test_click_image_no_match(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            result = ctrl.click_image("nonexistent.png")
            assert result is False
