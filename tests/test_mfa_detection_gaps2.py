"""Gap tests for mfa_detection.py — uncovered lines: 119-120, 212-215, 356-358,
375-377, 384-385, 398-399, 594-596, 657, 674."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from PIL import Image

from core.mfa_detection import (
    DetectionResult,
    MFADetector,
    _empty_result,
    _get_window_titles,
    _uia_check,
)
from core.utils import have_tesseract as _have_tesseract

# -----------------------------------------------------------------------
# Lines 119-120: _have_tesseract() success path
# -----------------------------------------------------------------------


class TestHaveTesseractSuccess:
    """_have_tesseract sets _pytesseract and _TESSERACT_OK on successful import."""

    def setup_method(self):
        import core.mfa_detection as m

        m._TESSERACT_OK = None
        m._pytesseract = None

    def test_success_path_sets_globals(self):
        """Lines 119-120: import + get_tesseract_version succeed -> _pytesseract and _TESSERACT_OK."""
        import core.mfa_detection as m

        fake_pytesseract = MagicMock()
        fake_pytesseract.get_tesseract_version.return_value = "5.0.0"

        def fake_import(name, *args, **kwargs):
            if name == "pytesseract":
                return fake_pytesseract
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = _have_tesseract()

        assert result is True
        assert m._TESSERACT_OK is True
        assert m._pytesseract is fake_pytesseract
        fake_pytesseract.get_tesseract_version.assert_called_once()


# -----------------------------------------------------------------------
# Lines 212-215: _get_window_titles() win32gui _enum callback
# -----------------------------------------------------------------------


class TestGetWindowTitlesEnumCallback:
    """_get_window_titles _enum callback via win32gui.EnumWindows."""

    def test_enum_callback_collects_visible_titled_windows(self):
        """Lines 213-216: _enum checks IsWindowVisible, GetWindowText, appends title.

        Inject a self-contained fake ``win32gui`` into ``sys.modules`` so the
        in-function ``import win32gui`` binds it on any platform. ``patch.dict``
        removes it again afterwards, so the test neither depends on nor leaks
        global module state.
        """
        fake_win32gui = MagicMock()

        def fake_enum_windows(callback, lparam):
            callback(1001, None)  # visible + titled -> collected
            callback(1002, None)  # not visible -> skipped
            callback(1003, None)  # visible but empty title -> skipped

        fake_win32gui.EnumWindows.side_effect = fake_enum_windows
        fake_win32gui.IsWindowVisible.side_effect = lambda hwnd: hwnd in (1001, 1003)
        fake_win32gui.GetWindowText.side_effect = lambda hwnd: (
            "My App Window" if hwnd == 1001 else ""
        )

        with patch("core.mfa_detection._IS_WINDOWS", True), \
             patch.dict(sys.modules, {"win32gui": fake_win32gui}):
            titles = _get_window_titles()

        assert titles == ["My App Window"]


# -----------------------------------------------------------------------
# Lines 356-358: _uia_check() exception reading win.Name
# -----------------------------------------------------------------------


class TestUiaCheckWindowNameException:
    """Lines 356-358: _uia_check catches exception on win.Name."""

    def setup_method(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = None
        m._auto = None

    def test_window_name_exception_sets_empty_title(self):
        """When win.Name raises, title is set to '' and window is still processed."""
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        # Use a property-like mock: Name raises on access
        bad_win = MagicMock()
        type(bad_win).Name = property(lambda self: (_ for _ in ()).throw(RuntimeError("COM")))
        # Children have no auth-related controls, so no detection
        bad_win.GetChildren.return_value = []

        root = MagicMock()
        root.GetChildren.return_value = [bad_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None


# -----------------------------------------------------------------------
# Lines 375-377: _uia_check() exception reading ctrl.ControlTypeName
# -----------------------------------------------------------------------
# Already covered in test_mfa_detection_gaps.py::TestUiaCheck::test_uia_control_type_exception_skips
# But we verify it again for completeness.


class TestUiaCheckControlTypeException:
    """Lines 375-377: _uia_check catches exception on ctrl.ControlTypeName."""

    def setup_method(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = None
        m._auto = None

    def test_control_type_exception_skips_control(self):
        """When ctrl.ControlTypeName raises, control is skipped."""
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        bad_ctrl = MagicMock()
        type(bad_ctrl).ControlTypeName = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no type"))
        )

        mock_win = MagicMock()
        mock_win.Name = "Some App"
        mock_win.GetChildren.return_value = [bad_ctrl]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        assert result is None


# -----------------------------------------------------------------------
# Lines 384-385: _uia_check() IsPassword check exception
# -----------------------------------------------------------------------


class TestUiaCheckIsPasswordException:
    """Lines 384-385: _uia_check catches exception on IsPassword getattr."""

    def setup_method(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = None
        m._auto = None

    def test_is_password_exception_continues(self):
        """When IsPassword access raises, the control is skipped gracefully."""
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        # EditControl whose IsPassword raises
        edit_ctrl = MagicMock()
        edit_ctrl.ControlTypeName = "EditControl"
        # Make getattr(ctrl, "IsPassword", False) raise via property on the mock
        type(edit_ctrl).IsPassword = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("COM error"))
        )

        mock_win = MagicMock()
        mock_win.Name = "Login Dialog"
        mock_win.GetChildren.return_value = [edit_ctrl]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        # Password was not found due to exception, so no detection
        assert result is None


# -----------------------------------------------------------------------
# Lines 398-399: _uia_check() text pattern matching exception
# -----------------------------------------------------------------------


class TestUiaCheckTextPatternException:
    """Lines 398-399: _uia_check catches exception during text pattern matching."""

    def setup_method(self):
        import core.mfa_detection as m

        m._UIA_AVAILABLE = None
        m._auto = None

    def test_text_pattern_exception_continues(self):
        """When ctrl.Name raises during text pattern matching, control is skipped."""
        import core.mfa_detection as m

        m._UIA_AVAILABLE = True
        mock_auto = MagicMock()
        m._auto = mock_auto

        text_ctrl = MagicMock()
        text_ctrl.ControlTypeName = "TextControl"
        # Name access succeeds for the type check but we need the inner
        # ctrl.Name to raise during text reading
        call_count = [0]

        def name_side_effect():
            call_count[0] += 1
            if call_count[0] > 1:
                raise RuntimeError("COM lost")
            return "Some text"

        text_ctrl.Name = MagicMock(side_effect=name_side_effect)

        mock_win = MagicMock()
        mock_win.Name = "Dialog"
        mock_win.GetChildren.return_value = [text_ctrl]

        root = MagicMock()
        root.GetChildren.return_value = [mock_win]
        mock_auto.GetRootControl.return_value = root

        with patch("core.mfa_detection._IS_WINDOWS", True):
            result = _uia_check()
        # Text matching failed, so no detection
        assert result is None


# -----------------------------------------------------------------------
# Lines 594-596: _monitor_loop exception during _poll_once()
# -----------------------------------------------------------------------


class TestMonitorLoopPollOnceException:
    """Lines 594-596: _monitor_loop catches exception from _poll_once()."""

    def test_poll_once_exception_handled_gracefully(self):
        """When _poll_once raises, the loop catches it and sets empty result."""
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector(cooldown_seconds=0.0)
            callback = MagicMock()

            def fake_capture():
                return Image.new("RGB", (10, 10))

            # Make check_window_titles raise on the first call, succeed later
            call_count = [0]

            def flaky_check():
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("transient failure")
                detector._monitor_stop.set()
                return _empty_result()

            with patch.object(detector, "check_window_titles", side_effect=flaky_check):
                with patch("core.mfa_detection._ocr_check", return_value=None):
                    with patch("core.mfa_detection._uia_check", return_value=None):
                        with patch("core.screenshot.capture_screen", side_effect=fake_capture):
                            detector.start_monitoring(callback, interval=0.1)
                            detector._monitor_thread.join(timeout=5.0)

            # Monitor loop survived the exception without crashing
            assert callback.call_count == 0


# -----------------------------------------------------------------------
# Line 657: _poll_once returns early on Tier 1 (window title) match
# -----------------------------------------------------------------------


class TestPollOnceTier1EarlyReturn:
    """Line 657: _poll_once returns immediately when window title match is detected."""

    def test_tier1_match_returns_early(self):
        """When check_window_titles detects something, _poll_once returns it immediately."""
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()

            title_result = DetectionResult(
                detected=True,
                type="credential",
                confidence=0.95,
                action="pause_agent",
                prompt_text="Windows Security",
                window_title="Windows Security",
            )

            capture_fn = MagicMock()

            with patch.object(detector, "check_window_titles", return_value=title_result):
                result = detector._poll_once(capture_fn)

            assert result.detected is True
            assert result.type == "credential"
            # capture_fn should NOT have been called since Tier 1 matched
            capture_fn.assert_not_called()


# -----------------------------------------------------------------------
# Line 674: _poll_once returns UIA result
# -----------------------------------------------------------------------


class TestPollOnceUIAResult:
    """Line 674: _poll_once returns when UIA tier detects something."""

    def test_uia_result_returned(self):
        """When OCR misses but UIA hits, _poll_once returns the UIA result."""
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()

            uia_result = DetectionResult(
                detected=True,
                type="credential",
                confidence=0.8,
                action="pause_agent",
                prompt_text="password field",
                window_title="Login",
            )

            capture_fn = MagicMock(return_value=Image.new("RGB", (10, 10)))

            with patch.object(detector, "check_window_titles", return_value=_empty_result()):
                with patch("core.mfa_detection._ocr_check", return_value=None):
                    with patch("core.mfa_detection._uia_check", return_value=uia_result):
                        result = detector._poll_once(capture_fn)

            assert result.detected is True
            assert result.type == "credential"
            assert result.confidence == 0.8
