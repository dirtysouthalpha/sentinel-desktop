"""Gap tests for mfa_detection.py — probes, window titles, OCR, UIA, monitor loop."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PIL import Image

from core.mfa_detection import (
    DetectionResult,
    MFADetector,
    _empty_result,
    _extract_excerpt,
    _get_window_titles,
    _have_tesseract,
    _have_uia,
    _ocr_check,
    _uia_check,
)


class TestHaveTesseractProbe:
    """_have_tesseract lazy probe."""

    def setup_method(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = None
        m._pytesseract = None

    def test_cached_true(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        assert _have_tesseract() is True

    def test_cached_false(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = False
        assert _have_tesseract() is False

    def test_import_failure(self):
        import core.mfa_detection as m

        with patch("builtins.__import__", side_effect=ImportError("nope")):
            assert _have_tesseract() is False
        assert m._TESSERACT_OK is False


class TestHaveUiaProbe:
    """_have_uia lazy probe."""

    def setup_method(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = None
        m._auto = None

    def test_cached_true(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        assert _have_uia() is True

    def test_cached_false(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = False
        assert _have_uia() is False

    def test_import_failure(self):
        with patch("builtins.__import__", side_effect=ImportError("nope")):
            assert _have_uia() is False


class TestGetWindowTitles:
    """_get_window_titles on non-Windows."""

    def test_non_windows_returns_empty(self):
        with patch("core.mfa_detection._IS_WINDOWS", False):
            assert _get_window_titles() == []

    def test_win32gui_exception_falls_back_to_wm(self):
        import win32gui

        with patch("core.mfa_detection._IS_WINDOWS", True):
            with patch.object(win32gui, "EnumWindows", side_effect=RuntimeError("fail")):
                with patch("core.window_manager.list_windows") as mock_lw:
                    mock_lw.return_value = [
                        {"title": "Chrome"},
                        {"title": ""},
                    ]
                    titles = _get_window_titles()
        assert "Chrome" in titles

    def test_win32gui_and_wm_both_fail(self):
        import win32gui

        with patch("core.mfa_detection._IS_WINDOWS", True):
            with patch.object(win32gui, "EnumWindows", side_effect=RuntimeError("fail")):
                with patch("core.window_manager.list_windows", side_effect=RuntimeError("also fail")):
                    titles = _get_window_titles()
        assert titles == []


class TestOcrCheck:
    """_ocr_check with tesseract and without."""

    def setup_method(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = None
        m._pytesseract = None

    def test_no_tesseract_returns_none(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = False
        assert _ocr_check(Image.new("RGB", (10, 10))) is None

    def test_tesseract_exception_returns_none(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        m._pytesseract = MagicMock()
        m._pytesseract.image_to_string.side_effect = RuntimeError("ocr fail")
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is None

    def test_tesseract_empty_text_returns_none(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        m._pytesseract = MagicMock()
        m._pytesseract.image_to_string.return_value = ""
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is None

    def test_tesseract_mfa_pattern_detected(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        m._pytesseract = MagicMock()
        m._pytesseract.image_to_string.return_value = "Please verify your identity to continue"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is not None
        assert result.detected is True
        assert result.type == "mfa"

    def test_tesseract_uac_pattern_boosted(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        m._pytesseract = MagicMock()
        m._pytesseract.image_to_string.return_value = "User Account Control: Do you want to allow"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is not None
        assert result.type == "uac"
        assert result.confidence >= 0.85

    def test_tesseract_credential_pattern(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        m._pytesseract = MagicMock()
        m._pytesseract.image_to_string.return_value = "Please enter your password"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is not None
        assert result.type == "credential"

    def test_tesseract_no_match_returns_none(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = True
        m._pytesseract = MagicMock()
        m._pytesseract.image_to_string.return_value = "Just normal text nothing special"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is None


class TestUiaCheck:
    """_uia_check without UIA or on non-Windows."""

    def setup_method(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = None
        m._auto = None

    def test_no_uia_returns_none(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = False
        assert _uia_check() is None

    def test_non_windows_returns_none(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        with patch("core.mfa_detection._IS_WINDOWS", False):
            assert _uia_check() is None

    def test_uia_exception_returns_none(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        mock_auto.GetRootControl.side_effect = RuntimeError("COM dead")
        m._auto = mock_auto
        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None

    def test_uia_password_edit_detected(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        password_edit = MagicMock()
        password_edit.ControlTypeName = "EditControl"
        password_edit.IsPassword = True

        mock_win = MagicMock()
        mock_win.Name = "Login"
        mock_win.GetChildren.return_value = [password_edit]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is not None
        assert result.detected is True
        assert result.type == "credential"
        assert result.confidence == 0.8

    def test_uia_auth_text_detected(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        text_ctrl = MagicMock()
        text_ctrl.ControlTypeName = "TextControl"
        text_ctrl.Name = "Please verify your identity"

        mock_win = MagicMock()
        mock_win.Name = "Security"
        mock_win.GetChildren.return_value = [text_ctrl]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is not None
        assert result.detected is True
        assert result.type == "mfa"
        assert result.confidence == 0.7

    def test_uia_window_name_exception_skips(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        bad_win = MagicMock()
        bad_win.Name = MagicMock(side_effect=RuntimeError("COM fail"))
        bad_win.GetChildren.return_value = []

        root = MagicMock()
        root.GetChildren.return_value = [bad_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None

    def test_uia_already_matched_title_skips(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        password_edit = MagicMock()
        password_edit.ControlTypeName = "EditControl"
        password_edit.IsPassword = True

        mock_win = MagicMock()
        mock_win.Name = "Windows Security"
        mock_win.GetChildren.return_value = [password_edit]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None  # skipped because title already matched

    def test_uia_control_type_exception_skips(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        bad_ctrl = MagicMock()
        bad_ctrl.ControlTypeName = MagicMock(side_effect=RuntimeError("COM"))

        mock_win = MagicMock()
        mock_win.Name = "Some App"
        mock_win.GetChildren.return_value = [bad_ctrl]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None


class TestCheckScreenTiers:
    """check_screen with OCR and UIA tiers on Windows."""

    def setup_method(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = None
        m._pytesseract = None
        m._UIA_AVAILABLE = None
        m._auto = None

    @patch("core.mfa_detection._match_window_title")
    @patch("core.mfa_detection._get_window_titles")
    def test_tier1_title_match_skips_ocr_uia(self, mock_titles, mock_match):
        mock_titles.return_value = ["Windows Security"]
        mock_match.return_value = DetectionResult(
            detected=True, type="credential", confidence=0.95, action="pause_agent"
        )
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()
            result = detector.check_screen(Image.new("RGB", (10, 10)))
        assert result.detected is True
        assert result.type == "credential"

    @patch("core.mfa_detection._uia_check", return_value=None)
    @patch("core.mfa_detection._ocr_check")
    @patch("core.mfa_detection._match_window_title", return_value=None)
    @patch("core.mfa_detection._get_window_titles", return_value=[])
    def test_tier2_ocr_match(self, mock_titles, mock_match, mock_ocr, mock_uia):
        mock_ocr.return_value = DetectionResult(
            detected=True, type="mfa", confidence=0.7, action="pause_agent"
        )
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()
            result = detector.check_screen(Image.new("RGB", (10, 10)))
        assert result.detected is True
        assert result.type == "mfa"

    @patch("core.mfa_detection._uia_check")
    @patch("core.mfa_detection._ocr_check", return_value=None)
    @patch("core.mfa_detection._match_window_title", return_value=None)
    @patch("core.mfa_detection._get_window_titles", return_value=[])
    def test_tier3_uia_match(self, mock_titles, mock_match, mock_ocr, mock_uia):
        mock_uia.return_value = DetectionResult(
            detected=True, type="credential", confidence=0.8, action="pause_agent"
        )
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()
            result = detector.check_screen(Image.new("RGB", (10, 10)))
        assert result.detected is True
        assert result.type == "credential"

    @patch("core.mfa_detection._uia_check", return_value=None)
    @patch("core.mfa_detection._ocr_check", return_value=None)
    @patch("core.mfa_detection._match_window_title", return_value=None)
    @patch("core.mfa_detection._get_window_titles", return_value=[])
    def test_no_tiers_match_returns_empty(self, mock_titles, mock_match, mock_ocr, mock_uia):
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()
            result = detector.check_screen(Image.new("RGB", (10, 10)))
        assert result.detected is False


class TestMonitorLoopDetection:
    """_monitor_loop detection and cooldown."""

    def test_detection_triggers_callback(self):
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=100.0)
            callback = MagicMock()

            call_count = 0

            def fake_capture():
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    detector._monitor_stop.set()
                return Image.new("RGB", (10, 10))

            detection = DetectionResult(
                detected=True,
                type="mfa",
                confidence=0.8,
                action="pause_agent",
                prompt_text="verify your identity",
                window_title="Login",
            )

            with patch.object(detector, "check_window_titles", return_value=_empty_result()):
                with patch("core.mfa_detection._ocr_check", return_value=detection):
                    with patch("core.mfa_detection._uia_check", return_value=None):
                        with patch("core.screenshot.capture_screen", side_effect=fake_capture):
                            detector.start_monitoring(callback, interval=0.1)
                            detector._monitor_thread.join(timeout=5.0)

            assert callback.called

    def test_cooldown_skips_duplicate(self):
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=100.0)
            callback = MagicMock()

            poll_count = 0

            def fake_capture():
                nonlocal poll_count
                poll_count += 1
                if poll_count >= 3:
                    detector._monitor_stop.set()
                return Image.new("RGB", (10, 10))

            detection = DetectionResult(
                detected=True,
                type="mfa",
                confidence=0.8,
                action="pause_agent",
                prompt_text="verify your identity",
                window_title="Login",
            )

            with patch.object(detector, "check_window_titles", return_value=_empty_result()):
                with patch("core.mfa_detection._ocr_check", return_value=detection):
                    with patch("core.mfa_detection._uia_check", return_value=None):
                        with patch("core.screenshot.capture_screen", side_effect=fake_capture):
                            detector.start_monitoring(callback, interval=0.1)
                            detector._monitor_thread.join(timeout=5.0)

            # First poll triggers, second+ are cooldown-suppressed
            assert callback.call_count == 1

    def test_auto_resume_clears_detection(self):
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=0.0)
            callback = MagicMock()

            poll_count = 0

            def fake_capture():
                nonlocal poll_count
                poll_count += 1
                if poll_count >= 3:
                    detector._monitor_stop.set()
                return Image.new("RGB", (10, 10))

            detection = DetectionResult(
                detected=True,
                type="mfa",
                confidence=0.8,
                action="pause_agent",
                prompt_text="verify",
                window_title="Login",
            )

            def fake_ocr(screenshot):
                nonlocal poll_count
                if poll_count <= 1:
                    return detection
                return None

            with patch.object(detector, "check_window_titles", return_value=_empty_result()):
                with patch("core.mfa_detection._ocr_check", side_effect=fake_ocr):
                    with patch("core.mfa_detection._uia_check", return_value=None):
                        with patch("core.screenshot.capture_screen", side_effect=fake_capture):
                            detector.start_monitoring(callback, interval=0.1)
                            detector._monitor_thread.join(timeout=5.0)

            # Detection cleared after prompt disappears
            assert detector._last_detection is None
            assert detector._last_prompt_sig == ""

    def test_callback_exception_handled(self):
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=0.0)
            callback = MagicMock(side_effect=RuntimeError("cb fail"))

            poll_count = 0

            def fake_capture():
                nonlocal poll_count
                poll_count += 1
                if poll_count >= 2:
                    detector._monitor_stop.set()
                return Image.new("RGB", (10, 10))

            detection = DetectionResult(
                detected=True,
                type="mfa",
                confidence=0.8,
                action="pause_agent",
                prompt_text="verify",
                window_title="Login",
            )

            with patch.object(detector, "check_window_titles", return_value=_empty_result()):
                with patch("core.mfa_detection._ocr_check", return_value=detection):
                    with patch("core.mfa_detection._uia_check", return_value=None):
                        with patch("core.screenshot.capture_screen", side_effect=fake_capture):
                            detector.start_monitoring(callback, interval=0.1)
                            detector._monitor_thread.join(timeout=5.0)

            # Should not crash even though callback raised
            assert callback.called

    def test_poll_once_capture_exception_handled(self):
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=0.0)

            def bad_capture():
                raise OSError("screen failed")

            with patch.object(detector, "check_window_titles", return_value=_empty_result()):
                with patch("core.mfa_detection._uia_check", return_value=None):
                    result = detector._poll_once(bad_capture)
            assert result.detected is False


class TestExtractExcerptEdge:
    """_extract_excerpt edge cases."""

    def test_pattern_at_start(self):
        excerpt = _extract_excerpt("verify your identity now", "verify your identity")
        assert "verify your identity" in excerpt

    def test_pattern_at_end(self):
        text = "x" * 200 + "verify your identity"
        excerpt = _extract_excerpt(text, "verify your identity")
        assert "verify your identity" in excerpt
