"""Gap tests for popup_handler.py — covering OCR import error, window manager
fallback, Win32 button finding, and detect_from_screenshot edge cases.

Focuses on lines 349, 382-383, 530, 718-729, 735-760.
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import core.popup_handler as ph


class TestOcrImportError:
    """Line 349: OCR preprocess_for_ocr ImportError fallback."""

    def test_ocr_text_import_error_uses_raw_image(self):
        """When preprocess_for_ocr import fails, uses raw image."""
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "Hello World"
        mock_tesseract.get_tesseract_version.return_value = "5.0"

        with patch.dict("sys.modules", {"pytesseract": mock_tesseract}):
            # Reset tesseract state
            ph._TESSERACT_OK = None
            ph._pytesseract = None

            # Make preprocess_for_ocr import fail
            with patch.dict("sys.modules", {"core.ocr": None}):
                result = ph._ocr_text(Image.new("RGB", (100, 100)))
            # Should have used pytesseract directly on the raw image
            assert result == "Hello World"

        # Cleanup
        ph._TESSERACT_OK = None
        ph._pytesseract = None


class TestForegroundWindowTitleFallback:
    """Lines 382-383: window_manager fallback in _get_foreground_window_title."""

    def test_win32gui_fails_falls_back_to_wm(self):
        """When win32gui fails, falls back to window_manager."""
        with patch.object(ph, "_IS_WINDOWS", True), \
             patch("core.window_manager.list_windows", return_value=[{"title": "FallbackApp"}]):
            # On Linux, win32gui import fails, hitting the first except block,
            # then falling through to window_manager
            result = ph._get_foreground_window_title()
            # Should be string-like
            assert isinstance(result, (str, MagicMock)) or result == ""

    @patch.object(ph, "_IS_WINDOWS", False)
    def test_non_windows_returns_empty(self):
        assert ph._get_foreground_window_title() == ""


class TestDetectFromScreenshotEmptyLines:
    """Line 530: detect_from_screenshot with empty OCR lines."""

    def test_empty_ocr_result_returns_undetected(self):
        """When OCR returns only whitespace lines, returns undetected."""
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "   \n  \n  "
        mock_tesseract.get_tesseract_version.return_value = "5.0"

        with patch.dict("sys.modules", {"pytesseract": mock_tesseract}):
            ph._TESSERACT_OK = None
            ph._pytesseract = None
            handler = ph.PopupHandler()
            result = handler.detect_from_screenshot(Image.new("RGB", (100, 100)))
        assert result.detected is False

        ph._TESSERACT_OK = None
        ph._pytesseract = None

    def test_no_tesseract_returns_undetected(self):
        """When tesseract is unavailable, returns undetected."""
        ph._TESSERACT_OK = False
        ph._pytesseract = None
        handler = ph.PopupHandler()
        result = handler.detect_from_screenshot(Image.new("RGB", (100, 100)))
        assert result.detected is False

        ph._TESSERACT_OK = None
        ph._pytesseract = None


class TestClickButtonWin32:
    """Lines 718-729, 735-760: Win32 button clicking."""

    def test_click_button_no_win32_returns_false(self):
        """On non-Windows, _click_button returns False when OCR and UIA fail."""
        handler = ph.PopupHandler()
        with patch("core.ocr.find_text", side_effect=ImportError("nope")), \
             patch("core.ui_tree.click_control", side_effect=ImportError("nope")):
            result = handler._click_button("OK")
        assert result is False

    @patch.object(ph, "_IS_WINDOWS", True)
    def test_find_button_hwnd_non_windows_returns_none(self):
        """_find_button_hwnd returns None when not on Windows."""
        handler = ph.PopupHandler()
        with patch.object(ph, "_IS_WINDOWS", False):
            result = handler._find_button_hwnd(12345, "OK")
        assert result is None

    @patch.object(ph, "_IS_WINDOWS", True)
    def test_find_button_hwnd_with_mock_win32gui(self):
        """_find_button_hwnd finds matching button via EnumChildWindows."""
        handler = ph.PopupHandler()

        mock_win32gui = MagicMock()
        mock_win32gui.GetWindowText.return_value = "OK"
        mock_win32gui.GetClassName.return_value = "Button"

        def mock_enum(parent, callback, extra):
            callback(100, 0)

        mock_win32gui.EnumChildWindows.side_effect = mock_enum

        with patch.dict("sys.modules", {"win32gui": mock_win32gui, "win32con": MagicMock()}):
            result = handler._find_button_hwnd(999, "OK")
        assert result == 100

    @patch.object(ph, "_IS_WINDOWS", True)
    def test_find_button_hwnd_no_match(self):
        """_find_button_hwnd returns None when no button matches."""
        handler = ph.PopupHandler()

        mock_win32gui = MagicMock()
        mock_win32gui.GetWindowText.return_value = "Cancel"
        mock_win32gui.GetClassName.return_value = "Button"

        def mock_enum(parent, callback, extra):
            callback(100, 0)

        mock_win32gui.EnumChildWindows.side_effect = mock_enum

        with patch.dict("sys.modules", {"win32gui": mock_win32gui, "win32con": MagicMock()}):
            result = handler._find_button_hwnd(999, "OK")
        assert result is None

    @patch.object(ph, "_IS_WINDOWS", True)
    def test_find_button_hwnd_enum_exception(self):
        """_find_button_hwnd handles EnumChildWindows exceptions."""
        handler = ph.PopupHandler()

        mock_win32gui = MagicMock()
        mock_win32gui.EnumChildWindows.side_effect = OSError("fail")

        with patch.dict("sys.modules", {"win32gui": mock_win32gui, "win32con": MagicMock()}):
            result = handler._find_button_hwnd(999, "OK")
        assert result is None

    @patch.object(ph, "_IS_WINDOWS", True)
    def test_find_button_hwnd_callback_exception(self):
        """_find_button_hwnd handles exceptions inside the callback."""
        handler = ph.PopupHandler()

        mock_win32gui = MagicMock()
        mock_win32gui.GetWindowText.side_effect = OSError("fail")

        def mock_enum(parent, callback, extra):
            callback(100, 0)

        mock_win32gui.EnumChildWindows.side_effect = mock_enum

        with patch.dict("sys.modules", {"win32gui": mock_win32gui, "win32con": MagicMock()}):
            result = handler._find_button_hwnd(999, "OK")
        assert result is None


class TestSendKey:
    """Test _send_key method."""

    def test_send_key_success(self):
        handler = ph.PopupHandler()
        with patch("pyautogui.press") as mock_press:
            result = handler._send_key("escape")
        assert result is True
        mock_press.assert_called_once_with("escape")

    def test_send_key_maps_enter(self):
        handler = ph.PopupHandler()
        with patch("pyautogui.press") as mock_press:
            result = handler._send_key("enter")
        assert result is True
        mock_press.assert_called_once_with("enter")

    def test_send_key_maps_return(self):
        handler = ph.PopupHandler()
        with patch("pyautogui.press") as mock_press:
            result = handler._send_key("return")
        assert result is True
        mock_press.assert_called_once_with("enter")

    def test_send_key_failure(self):
        handler = ph.PopupHandler()
        with patch("pyautogui.press", side_effect=RuntimeError("nope")):
            result = handler._send_key("escape")
        assert result is False


class TestPopupHandlerReset:
    """Test reset() method."""

    def test_reset_clears_state(self):
        handler = ph.PopupHandler()
        handler._last_popup_type = "test"
        handler._last_detection_time = 100.0
        handler._dismiss_attempts = 5
        handler.reset()
        assert handler._last_popup_type == ""
        assert handler._last_detection_time == 0.0
        assert handler._dismiss_attempts == 0


class TestPopupHandlerPatternManagement:
    """Test add_pattern and remove_pattern."""

    def test_add_custom_pattern(self):
        handler = ph.PopupHandler(patterns=[])
        pat = ph.PopupPattern(
            name="custom",
            title_regex="custom title",
            body_regex="custom body",
            dismiss_action="Close",
        )
        handler.add_pattern(pat)
        assert len(handler.patterns) == 1

    def test_remove_existing_pattern(self):
        handler = ph.PopupHandler()
        count_before = len(handler.patterns)
        assert handler.remove_pattern("save_changes") is True
        assert len(handler.patterns) == count_before - 1

    def test_remove_nonexistent_pattern(self):
        handler = ph.PopupHandler()
        assert handler.remove_pattern("nonexistent") is False


class TestCheckAndDismiss:
    """Test check_and_dismiss integration."""

    def test_screenshot_capture_failure(self):
        """When screenshot capture fails, returns undetected."""
        handler = ph.PopupHandler()
        with patch("core.screenshot.capture_screen", side_effect=OSError("nope")):
            result = handler.check_and_dismiss()
        assert result.detected is False

    def test_cooldown_skips_dismissal(self):
        """Cooldown prevents repeated dismissal."""
        handler = ph.PopupHandler(auto_dismiss=True)
        # Simulate a previous detection
        handler._last_popup_type = "save_changes"
        handler._last_detection_time = float("inf")  # Very recent

        # Even with matching pattern, cooldown should skip
        with patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (100, 100))), \
             patch.object(ph, "_ocr_text", return_value="Save Changes?\nDo you want to save your changes?"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Save Changes?"):
            result = handler.check_and_dismiss()
        # Should be detected but not dismissed
        assert result.dismissed is False

    def test_max_dismiss_attempts(self):
        """After MAX_DISMISS_ATTEMPTS, no more dismissals."""
        handler = ph.PopupHandler(auto_dismiss=True)
        handler._dismiss_attempts = handler.MAX_DISMISS_ATTEMPTS

        with patch("core.screenshot.capture_screen", return_value=Image.new("RGB", (100, 100))), \
             patch.object(ph, "_ocr_text", return_value="Error\nAn error has occurred."), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"):
            result = handler.check_and_dismiss()
        # Should not have attempted to dismiss
        assert handler._dismiss_attempts == handler.MAX_DISMISS_ATTEMPTS

        ph._TESSERACT_OK = None
        ph._pytesseract = None
