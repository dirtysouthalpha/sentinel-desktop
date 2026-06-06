"""Gap tests for mfa_detection.py — probes, window titles, OCR, UIA, monitor loop."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import core.utils as utils
from core.mfa_detection import (
    DetectionResult,
    MFADetector,
    _empty_result,
    _extract_excerpt,
    _get_window_titles,
    _ocr_check,
    _uia_check,
)


class TestHaveTesseractProbe:
    """have_tesseract lazy probe."""

    def setup_method(self):
        utils._TESSERACT_OK = None
        utils._pytesseract = None

    def test_cached_true(self):
        utils._TESSERACT_OK = True
        assert utils.have_tesseract() is True

    def test_cached_false(self):
        utils._TESSERACT_OK = False
        assert utils.have_tesseract() is False

    def test_import_failure(self):
        with patch("builtins.__import__", side_effect=ImportError("nope")):
            assert utils.have_tesseract() is False
        assert utils._TESSERACT_OK is False


class TestHaveUiaProbe:
    """have_uia lazy probe."""

    def setup_method(self):
        utils._UIA_OK = None
        utils._auto = None

    def test_cached_true(self):
        # Old import pattern removed

        utils._UIA_OK = True
        assert utils.have_uia() is True

    def test_cached_false(self):
        # Old import pattern removed

        utils._UIA_OK = False
        assert utils.have_uia() is False

    def test_import_failure(self):
        with patch("builtins.__import__", side_effect=ImportError("nope")):
            assert utils.have_uia() is False

    def test_import_success_sets_auto(self):
        """Lines 139-140: a successful uiautomation import caches the module."""
        fake_uia = MagicMock()
        try:
            with (
                patch.dict(sys.modules, {"uiautomation": fake_uia}),
                patch("core.utils.platform.system", return_value="Windows"),
            ):
                assert utils.have_uia() is True
            assert utils._auto is fake_uia
            assert utils._UIA_OK is True
        finally:
            utils._UIA_OK = None
            utils._auto = None


class TestGetWindowTitles:
    """_get_window_titles on non-Windows."""

    def test_non_windows_returns_empty(self):
        with patch("core.mfa_detection._IS_WINDOWS", False):
            assert _get_window_titles() == []

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="requires win32gui")
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

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="requires win32gui")
    def test_win32gui_and_wm_both_fail(self):
        import win32gui

        with patch("core.mfa_detection._IS_WINDOWS", True):
            with patch.object(win32gui, "EnumWindows", side_effect=RuntimeError("fail")):
                with patch(
                    "core.window_manager.list_windows", side_effect=RuntimeError("also fail")
                ):
                    titles = _get_window_titles()
        assert titles == []


class TestOcrCheck:
    """_ocr_check with tesseract and without."""

    def setup_method(self):
        # Old import pattern removed

        utils._TESSERACT_OK = None
        utils._pytesseract = None

    def test_no_tesseract_returns_none(self):
        # Old import pattern removed

        utils._TESSERACT_OK = False
        assert _ocr_check(Image.new("RGB", (10, 10))) is None

    def test_tesseract_exception_returns_none(self):
        # Old import pattern removed

        utils._TESSERACT_OK = True
        utils._pytesseract = MagicMock()
        utils._pytesseract.image_to_string.side_effect = RuntimeError("ocr fail")
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is None

    def test_tesseract_empty_text_returns_none(self):
        # Old import pattern removed

        utils._TESSERACT_OK = True
        utils._pytesseract = MagicMock()
        utils._pytesseract.image_to_string.return_value = ""
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is None

    def test_tesseract_mfa_pattern_detected(self):
        # Old import pattern removed

        utils._TESSERACT_OK = True
        utils._pytesseract = MagicMock()
        utils._pytesseract.image_to_string.return_value = "Please verify your identity to continue"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is not None
        assert result.detected is True
        assert result.type == "mfa"

    def test_tesseract_uac_pattern_boosted(self):
        # Old import pattern removed

        utils._TESSERACT_OK = True
        utils._pytesseract = MagicMock()
        utils._pytesseract.image_to_string.return_value = (
            "User Account Control: Do you want to allow"
        )
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is not None
        assert result.type == "uac"
        assert result.confidence >= 0.85

    def test_tesseract_credential_pattern(self):
        # Old import pattern removed

        utils._TESSERACT_OK = True
        utils._pytesseract = MagicMock()
        utils._pytesseract.image_to_string.return_value = "Please enter your password"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is not None
        assert result.type == "credential"

    def test_tesseract_no_match_returns_none(self):
        # Old import pattern removed

        utils._TESSERACT_OK = True
        utils._pytesseract = MagicMock()
        utils._pytesseract.image_to_string.return_value = "Just normal text nothing special"
        with patch("core.ocr.preprocess_for_ocr", return_value=Image.new("RGB", (10, 10))):
            result = _ocr_check(Image.new("RGB", (10, 10)))
        assert result is None


class TestUiaCheck:
    """_uia_check without UIA or on non-Windows."""

    def setup_method(self):
        # Old import pattern removed

        utils._UIA_OK = None
        utils._auto = None

    def test_no_uia_returns_none(self):
        # Old import pattern removed

        utils._UIA_OK = False
        assert _uia_check() is None

    def test_non_windows_returns_none(self):
        # Old import pattern removed

        utils._UIA_OK = True
        with patch("core.mfa_detection._IS_WINDOWS", False):
            assert _uia_check() is None

    def test_uia_exception_returns_none(self):
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        mock_auto.GetRootControl.side_effect = RuntimeError("COM dead")
        utils._auto = mock_auto
        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None

    def test_uia_password_edit_detected(self):
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        utils._auto = mock_auto

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
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        utils._auto = mock_auto

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
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        utils._auto = mock_auto

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
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        utils._auto = mock_auto

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
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        utils._auto = mock_auto

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
        # Old import pattern removed

        utils._TESSERACT_OK = None
        utils._pytesseract = None
        utils._UIA_OK = None
        utils._auto = None

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

    def test_detection_without_callback_records_but_skips_invoke(self):
        """Branch 618->624: a detection with no registered callback is still
        recorded; the loop must not crash trying to invoke a None callback."""
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=100.0)

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
                            # No callback registered.
                            detector.start_monitoring(None, interval=0.1)  # type: ignore[arg-type]
                            detector._monitor_thread.join(timeout=5.0)

            recorded = detector.get_last_detection()
            assert recorded is not None
            assert recorded.detected is True

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


class TestGetWindowTitlesWin32Fallback:
    """Lines 219-230: win32gui EnumWindows failure → window_manager fallback.

    These run on any platform by injecting a fake ``win32gui`` into
    ``sys.modules`` so the in-function ``import win32gui`` binds the mock.
    """

    def test_enum_error_falls_back_to_window_manager(self):
        fake_win32gui = MagicMock()
        fake_win32gui.EnumWindows.side_effect = OSError("EnumWindows blew up")
        with (
            patch("core.mfa_detection._IS_WINDOWS", True),
            patch.dict(sys.modules, {"win32gui": fake_win32gui}),
            patch(
                "core.window_manager.list_windows",
                return_value=[{"title": "Chrome"}, {"title": ""}],
            ),
        ):
            titles = _get_window_titles()
        # The empty-title window is skipped (the ``if t:`` false branch).
        assert titles == ["Chrome"]

    def test_enum_and_window_manager_both_fail(self):
        fake_win32gui = MagicMock()
        fake_win32gui.EnumWindows.side_effect = OSError("EnumWindows blew up")
        with (
            patch("core.mfa_detection._IS_WINDOWS", True),
            patch.dict(sys.modules, {"win32gui": fake_win32gui}),
            patch("core.window_manager.list_windows", side_effect=OSError("wm dead")),
        ):
            titles = _get_window_titles()
        assert titles == []


class _FakeControl:
    """Minimal stand-in for a uiautomation control with raising properties.

    MagicMock attribute access never raises (``side_effect`` only fires on
    *call*), so to exercise the attribute-read ``except`` branches we need real
    properties that raise.
    """

    def __init__(
        self,
        type_name="",
        name="",
        is_password=False,
        raise_type=False,
        raise_name=False,
    ):
        self._type_name = type_name
        self._name = name
        self.IsPassword = is_password
        self._raise_type = raise_type
        self._raise_name = raise_name

    @property
    def ControlTypeName(self):
        if self._raise_type:
            raise RuntimeError("ControlTypeName read failed")
        return self._type_name

    @property
    def Name(self):
        if self._raise_name:
            raise RuntimeError("Name read failed")
        return self._name


class TestUiaCheckChildScanBranches:
    """Branches in _uia_check's child-control scan: 376-378, 383->389, 392->373, 399-400."""

    def setup_method(self):
        # Old import pattern removed

        utils._UIA_OK = None
        utils._auto = None

    def teardown_method(self):
        # Old import pattern removed

        utils._UIA_OK = None
        utils._auto = None

    def _run(self, children, win_name="ZZZ Unmatched Window 98765"):
        # Old import pattern removed

        utils._UIA_OK = True
        mock_auto = MagicMock()
        utils._auto = mock_auto
        win = MagicMock()
        win.Name = win_name
        win.GetChildren.return_value = children
        root = MagicMock()
        root.GetChildren.return_value = [win]
        mock_auto.GetRootControl.return_value = root
        with patch("core.mfa_detection._IS_WINDOWS", True):
            return _uia_check()

    def test_control_type_read_error_skips_control(self):
        """Lines 376-378: reading ControlTypeName raises → control skipped."""
        result = self._run([_FakeControl(raise_type=True)])
        assert result is None

    def test_edit_control_not_password_falls_through(self):
        """Branch 383->389: an EditControl that is not a password field."""
        result = self._run([_FakeControl(type_name="EditControl", is_password=False)])
        assert result is None

    def test_text_control_empty_name_skipped(self):
        """Branch 392->373: a TextControl with whitespace-only Name."""
        result = self._run([_FakeControl(type_name="TextControl", name="   ")])
        assert result is None

    def test_text_control_name_read_error(self):
        """Lines 399-400: reading a TextControl's Name raises → swallowed."""
        result = self._run([_FakeControl(type_name="TextControl", raise_name=True)])
        assert result is None
