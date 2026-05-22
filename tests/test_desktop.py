"""Tests for core/desktop.py — DesktopController and module-level helpers."""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.desktop import DesktopController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_controller(**size_kwargs):
    """Create a DesktopController with pyautogui mocked out."""
    with patch("core.desktop.pyautogui") as mock_pg:
        mock_pg.size.return_value = size_kwargs.get("size", (1920, 1080))
        if "size_side_effect" in size_kwargs:
            mock_pg.size.side_effect = size_kwargs["size_side_effect"]
        mock_pg.PAUSE = 0
        mock_pg.FAILSAFE = True
        ctrl = DesktopController()
    # Patch pyautogui on the module for subsequent calls
    return ctrl


# ===========================================================================
# __init__ edge cases
# ===========================================================================

class TestDesktopControllerInit:
    def test_screen_size_stored(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            assert ctrl.get_screen_size() == (1920, 1080)

    def test_screen_size_oserror_fallback(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.side_effect = OSError("no display")
            ctrl = DesktopController()
            assert ctrl.get_screen_size() == (1920, 1080)

    def test_screen_size_runtime_error_fallback(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.side_effect = RuntimeError("headless")
            ctrl = DesktopController()
            assert ctrl.get_screen_size() == (1920, 1080)

    def test_screen_size_value_error_fallback(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.side_effect = ValueError("bad dims")
            ctrl = DesktopController()
            assert ctrl.get_screen_size() == (1920, 1080)


# ===========================================================================
# Screenshot methods
# ===========================================================================

class TestScreenshot:
    def test_screenshot_returns_image(self):
        fake_img = Image.new("RGB", (100, 100), "red")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            result = ctrl.screenshot()
            assert result is fake_img

    def test_screenshot_oserror_fallback(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.side_effect = OSError("no display")
            ctrl = DesktopController()
            result = ctrl.screenshot()
            assert isinstance(result, Image.Image)
            assert result.size == (1920, 1080)

    def test_screenshot_runtime_error_fallback(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.side_effect = RuntimeError("capture fail")
            ctrl = DesktopController()
            result = ctrl.screenshot()
            assert isinstance(result, Image.Image)


class TestScreenshotBase64:
    def test_screenshot_base64_returns_string(self):
        fake_img = Image.new("RGB", (10, 10), "blue")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            b64 = ctrl.screenshot_base64()
            assert isinstance(b64, str)
            assert len(b64) > 0

    def test_screenshot_base64_jpeg_format(self):
        fake_img = Image.new("RGB", (10, 10), "blue")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            b64 = ctrl.screenshot_base64(format="JPEG")
            assert isinstance(b64, str)
            assert len(b64) > 0

    def test_screenshot_base64_oserror_returns_empty(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.side_effect = OSError("fail")
            ctrl = DesktopController()
            # screenshot() returns blank, but base64 should still work
            result = ctrl.screenshot_base64()
            # Blank image from fallback should encode fine
            assert isinstance(result, str)


class TestScreenshotRegion:
    def test_screenshot_region(self):
        fake_img = Image.new("RGB", (50, 50), "green")
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            ctrl.screenshot_region(10, 20, 50, 50)
            mock_pg.screenshot.assert_called_with(region=(10, 20, 50, 50))

    def test_screenshot_region_oserror_fallback(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.side_effect = OSError("no region")
            ctrl = DesktopController()
            result = ctrl.screenshot_region(0, 0, 800, 600)
            assert isinstance(result, Image.Image)
            assert result.size == (800, 600)


# ===========================================================================
# Mouse actions — error handling
# ===========================================================================

class TestClickErrorHandling:
    def test_click_failsafe_exception_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.click.side_effect = RuntimeError("failsafe triggered")
            ctrl = DesktopController()
            # RuntimeError is caught and swallowed
            ctrl.click(100, 200)

    def test_click_oserror_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.click.side_effect = OSError("no input")
            ctrl = DesktopController()
            ctrl.click(50, 50)

    def test_double_click_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.doubleClick.side_effect = RuntimeError("fail")
            ctrl = DesktopController()
            ctrl.double_click(10, 20)

    def test_right_click_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.rightClick.side_effect = OSError("fail")
            ctrl = DesktopController()
            ctrl.right_click(10, 20)

    def test_move_to_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.moveTo.side_effect = RuntimeError("fail")
            ctrl = DesktopController()
            ctrl.move_to(100, 200)

    def test_drag_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.moveTo.side_effect = RuntimeError("fail")
            ctrl = DesktopController()
            ctrl.drag(0, 0, 100, 100)

    def test_scroll_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.scroll.side_effect = OSError("no wheel")
            ctrl = DesktopController()
            ctrl.scroll(5)


# ===========================================================================
# Mouse happy paths
# ===========================================================================

class TestClickHappyPaths:
    def test_click(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.click(100, 200, button="right", clicks=2)
            mock_pg.click.assert_called_with(x=100, y=200, button="right", clicks=2)

    def test_click_default_params(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.click(50, 60)
            mock_pg.click.assert_called_with(x=50, y=60, button="left", clicks=1)

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

    def test_move_to_custom_duration(self):
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

    def test_scroll_default_coords(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            ctrl.scroll(-2)
            mock_pg.scroll.assert_called_with(-2, x=None, y=None)


# ===========================================================================
# get_mouse_position
# ===========================================================================

class TestGetMousePosition:
    def test_returns_position(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.position.return_value = (500, 300)
            ctrl = DesktopController()
            assert ctrl.get_mouse_position() == (500, 300)

    def test_oserror_returns_zero(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.position.side_effect = OSError("no mouse")
            ctrl = DesktopController()
            assert ctrl.get_mouse_position() == (0, 0)

    def test_runtime_error_returns_zero(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.position.side_effect = RuntimeError("headless")
            ctrl = DesktopController()
            assert ctrl.get_mouse_position() == (0, 0)


# ===========================================================================
# Keyboard actions — error handling
# ===========================================================================

class TestKeyboardErrorHandling:
    def test_type_text_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.write.side_effect = RuntimeError("no keyboard")
            ctrl = DesktopController()
            ctrl.type_text("hello")

    def test_press_key_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.press.side_effect = OSError("no key")
            ctrl = DesktopController()
            ctrl.press_key("enter")

    def test_hotkey_error_swallowed(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.hotkey.side_effect = RuntimeError("no combo")
            ctrl = DesktopController()
            ctrl.hotkey("ctrl", "c")


class TestKeyboardHappyPaths:
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


# ===========================================================================
# find_on_screen / wait_for_image / click_image
# ===========================================================================

class TestFindOnScreen:
    def test_no_cv2_returns_none(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            result = ctrl.find_on_screen("nonexistent.png")
            assert result is None

    def test_with_cv2_no_match_returns_none(self):
        """When cv2 is available but template doesn't match, returns None."""
        fake_img = Image.new("RGB", (100, 100), "gray")
        mock_cv2 = MagicMock()
        mock_np = MagicMock()
        mock_cv2.imread.return_value = MagicMock(shape=(10, 10))
        mock_cv2.minMaxLoc.return_value = (0, 0.5, 0, (0, 0))  # below confidence

        with patch("core.desktop.pyautogui") as mock_pg, \
             patch("core.desktop.cv2", mock_cv2, create=True), \
             patch("core.desktop.np", mock_np, create=True):
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            result = ctrl.find_on_screen("template.png", confidence=0.8)
            assert result is None

    def test_with_cv2_match_returns_center(self):
        """When cv2 matches above confidence, returns center coords."""
        fake_img = Image.new("RGB", (100, 100), "gray")
        mock_cv2 = MagicMock()
        template_mock = MagicMock()
        template_mock.shape = (20, 30)  # h, w
        mock_cv2.imread.return_value = template_mock
        mock_cv2.minMaxLoc.return_value = (0, 0.95, 0, (50, 60))  # above confidence

        mock_arr = MagicMock()
        mock_np = MagicMock()
        mock_np.array.return_value = mock_arr

        with patch("core.desktop.pyautogui") as mock_pg, \
             patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": mock_np}):
            mock_pg.size.return_value = (1920, 1080)
            mock_pg.screenshot.return_value = fake_img
            ctrl = DesktopController()
            result = ctrl.find_on_screen("template.png", confidence=0.8)
            # center = (50 + 30//2, 60 + 20//2) = (65, 70)
            assert result == (65, 70)

    def test_imread_none_returns_none(self):
        """When cv2.imread returns None (bad file), returns None."""
        mock_cv2 = MagicMock()
        mock_cv2.imread.return_value = None

        with patch("core.desktop.pyautogui") as mock_pg, \
             patch.dict("sys.modules", {"cv2": mock_cv2}):
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            result = ctrl.find_on_screen("bad_template.png")
            assert result is None


class TestWaitForImage:
    def test_immediate_match(self):
        """If find_on_screen returns immediately, wait_for_image returns fast."""
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            with patch.object(ctrl, "find_on_screen", return_value=(100, 200)):
                result = ctrl.wait_for_image("img.png", timeout=5)
                assert result == (100, 200)

    def test_timeout_returns_none(self):
        """If template never appears, returns None after timeout."""
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            with patch.object(ctrl, "find_on_screen", return_value=None), \
                 patch("core.desktop.time.sleep"):
                result = ctrl.wait_for_image("missing.png", timeout=0.1, interval=0.05)
                assert result is None

    def test_scan_exception_continues(self):
        """If find_on_screen throws, wait_for_image keeps trying."""
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            call_count = 0

            def flaky_find(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise OSError("scan failed")
                return (50, 60)

            with patch.object(ctrl, "find_on_screen", side_effect=flaky_find), \
                 patch("core.desktop.time.sleep"):
                result = ctrl.wait_for_image("img.png", timeout=5)
                assert result == (50, 60)


class TestClickImage:
    def test_no_match_returns_false(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            with patch.object(ctrl, "find_on_screen", return_value=None):
                assert ctrl.click_image("missing.png") is False

    def test_match_clicks_and_returns_true(self):
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = DesktopController()
            with patch.object(ctrl, "find_on_screen", return_value=(100, 200)), \
                 patch.object(ctrl, "click") as mock_click:
                result = ctrl.click_image("found.png", button="right")
                assert result is True
                mock_click.assert_called_with(100, 200, button="right")


# ===========================================================================
# DesktopEngine alias
# ===========================================================================

class TestDesktopEngineAlias:
    def test_alias_is_same_class(self):
        from core.desktop import DesktopEngine
        assert DesktopEngine is DesktopController


# ===========================================================================
# Module-level convenience functions
# ===========================================================================

class TestModuleLevelFunctions:
    def test_module_screenshot(self):
        import core.desktop as mod
        fake_img = Image.new("RGB", (10, 10))
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_ctrl.screenshot.return_value = fake_img
            mock_get.return_value = mock_ctrl
            # Reset singleton
            mod._ctrl = None
            result = mod.screenshot()
            assert result is fake_img

    def test_module_screenshot_base64(self):
        import core.desktop as mod
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_ctrl.screenshot_base64.return_value = "abc123"
            mock_get.return_value = mock_ctrl
            result = mod.screenshot_base64()
            assert result == "abc123"

    def test_module_click(self):
        import core.desktop as mod
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_get.return_value = mock_ctrl
            mod.click(10, 20, button="right", clicks=2)
            mock_ctrl.click.assert_called_with(10, 20, button="right", clicks=2)

    def test_module_type_text(self):
        import core.desktop as mod
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_get.return_value = mock_ctrl
            mod.type_text("hi", interval=0.1)
            mock_ctrl.type_text.assert_called_with("hi", interval=0.1)

    def test_module_press_key(self):
        import core.desktop as mod
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_get.return_value = mock_ctrl
            mod.press_key("escape")
            mock_ctrl.press_key.assert_called_with("escape")

    def test_module_hotkey(self):
        import core.desktop as mod
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_get.return_value = mock_ctrl
            mod.hotkey("alt", "tab")
            mock_ctrl.hotkey.assert_called_with("alt", "tab")

    def test_module_scroll(self):
        import core.desktop as mod
        with patch.object(mod, "_get_controller") as mock_get:
            mock_ctrl = MagicMock()
            mock_get.return_value = mock_ctrl
            mod.scroll(-3, x=50, y=100)
            mock_ctrl.scroll.assert_called_with(-3, x=50, y=100)

    def test_get_controller_creates_singleton(self):
        import core.desktop as mod
        mod._ctrl = None
        with patch("core.desktop.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            ctrl = mod._get_controller()
            assert isinstance(ctrl, DesktopController)
            assert mod._ctrl is ctrl
            # Second call returns same instance
            ctrl2 = mod._get_controller()
            assert ctrl2 is ctrl
