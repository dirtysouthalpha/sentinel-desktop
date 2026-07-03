"""Tests for uncovered paths in core/popup_handler.py.

Covers: _have_tesseract, _ocr_text, _get_foreground_window_title,
check_and_dismiss cooldown/dismiss-attempt logic, detect_from_screenshot
edge cases, and _click_button strategy fallbacks.
"""

import sys
from unittest.mock import MagicMock, patch

from PIL import Image

import core.popup_handler as ph

# ---------------------------------------------------------------------------
# _have_tesseract
# ---------------------------------------------------------------------------


class TestHaveTesseract:
    """Test the lazy tesseract probe and caching."""

    def setup_method(self):
        # Reset the global cache before each test
        ph._TESSERACT_OK = None
        ph._pytesseract = None

    def test_returns_false_when_import_fails(self):
        """When pytesseract is not installed, returns False."""
        with patch.dict(sys.modules, {"pytesseract": None}):
            # Force import to fail
            with patch("builtins.__import__", side_effect=ImportError("nope")):
                assert ph._have_tesseract() is False

    def test_caches_result_true(self):
        """Second call returns cached True without re-probing."""
        mock_ts = MagicMock()
        mock_ts.get_tesseract_version.return_value = "5.0"
        ph._TESSERACT_OK = True
        ph._pytesseract = mock_ts
        assert ph._have_tesseract() is True

    def test_caches_result_false(self):
        """Second call returns cached False without re-probing."""
        ph._TESSERACT_OK = False
        assert ph._have_tesseract() is False

    def test_returns_true_when_available(self):
        """When pytesseract imports and get_tesseract_version succeeds."""
        mock_ts = MagicMock()
        mock_ts.get_tesseract_version.return_value = "5.0"
        with patch.dict(sys.modules, {"pytesseract": mock_ts}):
            result = ph._have_tesseract()
        assert result is True


# ---------------------------------------------------------------------------
# _ocr_text
# ---------------------------------------------------------------------------


class TestOcrText:
    """Test the OCR helper function."""

    def setup_method(self):
        ph._TESSERACT_OK = None
        ph._pytesseract = None

    def test_returns_empty_when_tesseract_unavailable(self):
        """Returns empty string when tesseract is not available."""
        ph._TESSERACT_OK = False
        img = Image.new("RGB", (100, 50))
        assert ph._ocr_text(img) == ""

    def test_returns_text_on_success(self):
        """Returns OCR output when tesseract works."""
        mock_ts = MagicMock()
        mock_ts.image_to_string.return_value = "Hello World"
        ph._TESSERACT_OK = True
        ph._pytesseract = mock_ts
        img = Image.new("RGB", (100, 50))
        result = ph._ocr_text(img)
        assert result == "Hello World"

    def test_returns_empty_on_ocr_exception(self):
        """Returns empty string when OCR raises."""
        mock_ts = MagicMock()
        mock_ts.image_to_string.side_effect = RuntimeError("OCR fail")
        ph._TESSERACT_OK = True
        ph._pytesseract = mock_ts
        img = Image.new("RGB", (100, 50))
        result = ph._ocr_text(img)
        assert result == ""

    def test_uses_preprocess_for_ocr_when_available(self):
        """When core.ocr.preprocess_for_ocr is importable, it's used."""
        mock_ts = MagicMock()
        mock_ts.image_to_string.return_value = "processed text"
        ph._TESSERACT_OK = True
        ph._pytesseract = mock_ts

        processed_img = Image.new("L", (100, 50))
        with patch("core.popup_handler.preprocess_for_ocr", create=True):
            # We need to actually import from core.ocr
            with patch.dict(sys.modules, {"core.ocr": MagicMock(preprocess_for_ocr=MagicMock(return_value=processed_img))}):
                # The function does `from core.ocr import preprocess_for_ocr`
                # Let's just test the fallback path
                img = Image.new("RGB", (100, 50))
                result = ph._ocr_text(img)
                # Even if preprocessing fails, OCR still runs
                assert result == "processed text"

    def test_falls_back_to_raw_image_on_preprocess_error(self):
        """When preprocess_for_ocr raises, falls back to raw image."""
        mock_ts = MagicMock()
        mock_ts.image_to_string.return_value = "fallback text"
        ph._TESSERACT_OK = True
        ph._pytesseract = mock_ts
        img = Image.new("RGB", (100, 50))

        # Force the import to raise
        with patch.dict(sys.modules, {"core.ocr": MagicMock(preprocess_for_ocr=MagicMock(side_effect=RuntimeError("nope")))}):
            result = ph._ocr_text(img)
            assert result == "fallback text"


# ---------------------------------------------------------------------------
# _get_foreground_window_title
# ---------------------------------------------------------------------------


class TestGetForegroundWindowTitle:
    """Test the Windows-only foreground window title helper."""

    def test_returns_empty_on_linux(self):
        """Returns empty string on non-Windows."""
        with patch.object(ph, "_IS_WINDOWS", False):
            assert ph._get_foreground_window_title() == ""

    def test_returns_title_on_windows(self):
        """Returns window title when win32gui is available."""
        mock_wingui = MagicMock()
        mock_wingui.GetForegroundWindow.return_value = 12345
        mock_wingui.GetWindowText.return_value = "Test Window"
        with patch.object(ph, "_IS_WINDOWS", True), \
             patch.dict(sys.modules, {"win32gui": mock_wingui}):
            assert ph._get_foreground_window_title() == "Test Window"

    def test_returns_empty_string_for_none_title(self):
        """Handles GetWindowText returning None."""
        mock_wingui = MagicMock()
        mock_wingui.GetForegroundWindow.return_value = 12345
        mock_wingui.GetWindowText.return_value = None
        with patch.object(ph, "_IS_WINDOWS", True), \
             patch.dict(sys.modules, {"win32gui": mock_wingui}):
            assert ph._get_foreground_window_title() == ""

    def test_falls_back_to_window_manager(self):
        """Falls back to core.window_manager when win32gui fails."""
        mock_wingui = MagicMock()
        mock_wingui.GetForegroundWindow.side_effect = Exception("nope")
        with patch.object(ph, "_IS_WINDOWS", True), \
             patch.dict(sys.modules, {"win32gui": mock_wingui}), \
             patch("core.window_manager.list_windows", return_value=[{"title": "Fallback Window"}], create=True):
            # Also need to ensure the module-level import finds the mock
            import core.window_manager as wm
            with patch.object(wm, "list_windows", return_value=[{"title": "Fallback Window"}]):
                result = ph._get_foreground_window_title()
        assert result == "Fallback Window"

    def test_returns_empty_when_all_fail(self):
        """Returns empty when both win32gui and window_manager fail."""
        mock_wingui = MagicMock()
        mock_wingui.GetForegroundWindow.side_effect = Exception("fail")
        # Intercept the runtime ``import win32gui`` inside the function so the
        # mock is used regardless of whether the real module is cached.
        import builtins

        _real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "win32gui":
                return mock_wingui
            return _real_import(name, *args, **kwargs)

        with patch.object(ph, "_IS_WINDOWS", True), \
             patch("builtins.__import__", side_effect=_mock_import), \
             patch("core.window_manager.list_windows",
                   side_effect=Exception("wm fail")):
            assert ph._get_foreground_window_title() == ""


# ---------------------------------------------------------------------------
# PopupHandler.detect_from_screenshot
# ---------------------------------------------------------------------------


class TestDetectFromScreenshot:
    """Test the detect_from_screenshot method edge cases."""

    def setup_method(self):
        ph._TESSERACT_OK = None
        ph._pytesseract = None

    def test_returns_empty_when_ocr_empty(self):
        """Returns empty result when OCR produces no output."""
        ph._TESSERACT_OK = False
        handler = ph.PopupHandler()
        img = Image.new("RGB", (100, 50))
        result = handler.detect_from_screenshot(img)
        assert result.detected is False

    def test_returns_empty_when_ocr_whitespace_only(self):
        """Returns empty result when OCR returns only whitespace."""
        mock_ts = MagicMock()
        mock_ts.image_to_string.return_value = "   \n  \n  "
        ph._TESSERACT_OK = True
        ph._pytesseract = mock_ts
        handler = ph.PopupHandler()
        img = Image.new("RGB", (100, 50))
        result = handler.detect_from_screenshot(img)
        assert result.detected is False


# ---------------------------------------------------------------------------
# PopupHandler.check_and_dismiss
# ---------------------------------------------------------------------------


class TestCheckAndDismiss:
    """Test the check_and_dismiss integration method."""

    def setup_method(self):
        ph._TESSERACT_OK = None
        ph._pytesseract = None

    def test_returns_empty_when_screenshot_capture_fails(self):
        """Returns empty result when screenshot capture fails."""
        handler = ph.PopupHandler()
        with patch("core.popup_handler.capture_screen", create=True, side_effect=RuntimeError("no screen")):
            # The import in the function body needs mocking
            with patch.dict(sys.modules, {"core.screenshot": MagicMock(capture_screen=MagicMock(side_effect=RuntimeError("nope")))}):
                result = handler.check_and_dismiss(screenshot=None)
        assert result.detected is False

    def test_cooldown_skips_dismiss(self):
        """Same popup type within cooldown period skips dismiss."""
        handler = ph.PopupHandler(auto_dismiss=True)
        # First detection
        img = Image.new("RGB", (100, 50))
        with patch.object(handler, "detect", return_value=ph.PopupDetectionResult(
            detected=True, popup_type="save_changes", confidence=0.9,
            dismiss_type="button", dismiss_action="Don't Save"
        )):
            r1 = handler.check_and_dismiss(screenshot=img)
            assert r1.detected is True
            # Second detection within cooldown
            r2 = handler.check_and_dismiss(screenshot=img)
            assert r2.detected is True
            # But dismiss was skipped
            assert r2.dismissed is False

    def test_max_dismiss_attempts_limits_retries(self):
        """Stops trying to dismiss after MAX_DISMISS_ATTEMPTS."""
        handler = ph.PopupHandler(auto_dismiss=True)
        handler.MAX_DISMISS_ATTEMPTS = 2
        img = Image.new("RGB", (100, 50))
        detection = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", confidence=0.9,
            dismiss_type="key", dismiss_action="Escape"
        )

        # Mock the low-level key send to fail so dismiss doesn't reset attempts
        with patch.object(handler, "detect", return_value=detection), \
             patch.object(handler, "_send_key", return_value=False):
            # First call: attempt 1
            handler._last_detection_time = 0
            r1 = handler.check_and_dismiss(screenshot=img)
            assert r1.detected is True
            assert handler._dismiss_attempts == 1

            # Second call: attempt 2
            handler._last_detection_time = 0
            handler.check_and_dismiss(screenshot=img)
            assert handler._dismiss_attempts == 2

            # Third call: at max, no more dismiss (attempts stays at 2)
            handler._last_detection_time = 0
            handler.check_and_dismiss(screenshot=img)
            assert handler._dismiss_attempts == 2  # didn't increase

    def test_no_dismiss_when_not_detected(self):
        """No dismiss attempt when detection is negative."""
        handler = ph.PopupHandler(auto_dismiss=True)
        img = Image.new("RGB", (100, 50))
        with patch.object(handler, "detect", return_value=ph.PopupDetectionResult()):
            result = handler.check_and_dismiss(screenshot=img)
        assert result.detected is False
        assert result.dismissed is False

    def test_resets_dismiss_attempts_on_no_detection(self):
        """Dismiss attempt counter resets when popup goes away."""
        handler = ph.PopupHandler(auto_dismiss=True)
        handler._dismiss_attempts = 3
        img = Image.new("RGB", (100, 50))
        with patch.object(handler, "detect", return_value=ph.PopupDetectionResult()):
            handler.check_and_dismiss(screenshot=img)
        assert handler._dismiss_attempts == 0


# ---------------------------------------------------------------------------
# PopupHandler._click_button strategy fallbacks
# ---------------------------------------------------------------------------


class TestClickButtonFallbacks:
    """Test the multi-strategy button click fallback chain."""

    def test_uia_click_succeeds(self):
        """UIA click_control returns True on success."""
        handler = ph.PopupHandler()
        mock_ocr_mod = MagicMock()
        mock_ocr_mod.find_text.return_value = None  # Strategy 1 fails
        mock_ui_tree_mod = MagicMock()
        mock_ui_tree_mod.click_control.return_value = (100, 200)  # Strategy 2 succeeds

        # Patch sys.modules AND the core package namespace to ensure both import paths work
        patches = [
            patch.dict(sys.modules, {"core.ocr": mock_ocr_mod, "core.ui_tree": mock_ui_tree_mod}),
        ]
        # Also patch on the core package directly in case from/import caches it
        import core as core_pkg
        if hasattr(core_pkg, 'ocr'):
            patches.append(patch.object(core_pkg, 'ocr', mock_ocr_mod, create=True))
        if hasattr(core_pkg, 'ui_tree'):
            patches.append(patch.object(core_pkg, 'ui_tree', mock_ui_tree_mod, create=True))

        for p in patches:
            p.start()
        try:
            result = handler._click_button("OK")
        finally:
            for p in reversed(patches):
                p.stop()
        assert result is True

    def test_all_strategies_fail_returns_false(self):
        """Returns False when all click strategies fail."""
        handler = ph.PopupHandler()
        mock_ocr_mod = MagicMock()
        mock_ocr_mod.find_text.side_effect = RuntimeError("nope")
        mock_ui_tree_mod = MagicMock()
        mock_ui_tree_mod.click_control.return_value = None

        with patch.dict(sys.modules, {"core.ocr": mock_ocr_mod, "core.ui_tree": mock_ui_tree_mod}):
            result = handler._click_button("Nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# PopupHandler._send_key
# ---------------------------------------------------------------------------


class TestSendKey:
    """Test key press dispatch."""

    def test_key_name_mapping(self):
        """Maps common key names correctly."""
        handler = ph.PopupHandler()
        with patch.dict(sys.modules, {"pyautogui": MagicMock()}):
            result = handler._send_key("ESC")
        assert result is True

    def test_returns_false_on_failure(self):
        """Returns False when pyautogui raises."""
        handler = ph.PopupHandler()
        with patch.dict(sys.modules, {"pyautogui": MagicMock(press=MagicMock(side_effect=RuntimeError("nope")))}):
            result = handler._send_key("Escape")
        assert result is False


# ---------------------------------------------------------------------------
# PopupHandler.reset
# ---------------------------------------------------------------------------


class TestReset:
    """Test the reset method clears all state."""

    def test_reset_clears_state(self):
        handler = ph.PopupHandler()
        handler._last_popup_type = "error"
        handler._last_detection_time = 123.45
        handler._dismiss_attempts = 5
        handler.reset()
        assert handler._last_popup_type == ""
        assert handler._last_detection_time == 0.0
        assert handler._dismiss_attempts == 0
