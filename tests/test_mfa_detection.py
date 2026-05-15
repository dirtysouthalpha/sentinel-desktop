"""Tests for core/mfa_detection.py — MFA/UAC/credential prompt detection."""

from unittest.mock import MagicMock, patch

from core.mfa_detection import (
    AUTH_WINDOW_TITLES,
    MFA_PATTERNS,
    UAC_KEYWORDS,
    DetectionResult,
    MFADetector,
    _classify_action,
    _empty_result,
    _extract_excerpt,
    _match_window_title,
)


class TestDetectionResult:
    def test_default_values(self):
        r = DetectionResult()
        assert r.detected is False
        assert r.type == ""
        assert r.prompt_text == ""
        assert r.window_title == ""
        assert r.confidence == 0.0
        assert r.action == "none"

    def test_empty_result(self):
        r = _empty_result()
        assert isinstance(r, DetectionResult)
        assert r.detected is False


class TestClassifyAction:
    def test_empty_type_returns_none(self):
        assert _classify_action("", 0.9) == "none"

    def test_low_confidence_returns_none(self):
        assert _classify_action("mfa", 0.1) == "none"

    def test_uac_always_pauses(self):
        assert _classify_action("uac", 0.3) == "pause_agent"

    def test_credential_always_pauses(self):
        assert _classify_action("credential", 0.4) == "pause_agent"

    def test_mfa_high_confidence_pauses(self):
        assert _classify_action("mfa", 0.6) == "pause_agent"

    def test_mfa_low_confidence_notifies(self):
        assert _classify_action("mfa", 0.4) == "notify_user"

    def test_2fa_high_confidence_pauses(self):
        assert _classify_action("2fa", 0.5) == "pause_agent"

    def test_pin_high_confidence_pauses(self):
        assert _classify_action("pin", 0.7) == "pause_agent"


class TestMatchWindowTitle:
    def test_windows_security_detected(self):
        result = _match_window_title(["Chrome", "Windows Security"])
        assert result is not None
        assert result.detected is True
        assert result.type == "credential"
        assert result.confidence == 0.95

    def test_uac_detected(self):
        result = _match_window_title(["User Account Control"])
        assert result is not None
        assert result.type == "uac"

    def test_mfa_detected(self):
        result = _match_window_title(["Verify your identity"])
        assert result is not None
        assert result.type == "mfa"

    def test_2fa_detected(self):
        result = _match_window_title(["Two-factor authentication required"])
        assert result is not None
        assert result.type == "2fa"

    def test_pin_detected(self):
        result = _match_window_title(["Windows Hello"])
        assert result is not None
        assert result.type == "pin"

    def test_generic_credential_keyword(self):
        result = _match_window_title(["Enter credential details"])
        assert result is not None
        assert result.type == "credential"
        assert result.confidence == 0.85

    def test_generic_authentication_keyword(self):
        result = _match_window_title(["Authentication portal"])
        assert result is not None
        assert result.type == "mfa"

    def test_no_match_returns_none(self):
        result = _match_window_title(["Chrome", "Notepad", "VS Code"])
        assert result is None

    def test_case_insensitive(self):
        result = _match_window_title(["windows security"])
        assert result is not None
        assert result.type == "credential"

    def test_empty_list_returns_none(self):
        assert _match_window_title([]) is None


class TestExtractExcerpt:
    def test_finds_pattern(self):
        text = "Hello world. Please verify your identity to continue. Thank you."
        excerpt = _extract_excerpt(text, "verify your identity")
        assert "verify your identity" in excerpt

    def test_pattern_not_found_returns_truncated(self):
        text = "Short text"
        excerpt = _extract_excerpt(text, "not found")
        assert excerpt == "Short text"

    def test_long_text_truncates_with_ellipsis(self):
        text = "x" * 300 + "verify your identity" + "y" * 300
        excerpt = _extract_excerpt(text, "verify your identity")
        assert "verify your identity" in excerpt
        assert len(excerpt) < len(text)

    def test_empty_text(self):
        excerpt = _extract_excerpt("", "pattern")
        assert excerpt == ""


class TestMFADetector:
    def test_check_screen_non_windows(self):
        with patch("core.mfa_detection._IS_WINDOWS", False):
            detector = MFADetector()
            result = detector.check_screen(MagicMock())
            assert result.detected is False

    def test_check_window_titles_non_windows(self):
        with patch("core.mfa_detection._IS_WINDOWS", False):
            detector = MFADetector()
            result = detector.check_window_titles()
            assert result.detected is False

    @patch("core.mfa_detection._match_window_title")
    @patch("core.mfa_detection._get_window_titles")
    def test_check_window_titles_detected(self, mock_titles, mock_match):
        mock_titles.return_value = ["Windows Security"]
        mock_match.return_value = DetectionResult(detected=True, type="credential", confidence=0.95)
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()
            result = detector.check_window_titles()
            assert result.detected is True

    @patch("core.mfa_detection._match_window_title")
    @patch("core.mfa_detection._get_window_titles")
    def test_check_window_titles_not_detected(self, mock_titles, mock_match):
        mock_titles.return_value = ["Chrome"]
        mock_match.return_value = None
        with patch("core.mfa_detection._IS_WINDOWS", True):
            detector = MFADetector()
            result = detector.check_window_titles()
            assert result.detected is False

    def test_get_last_detection_initially_none(self):
        detector = MFADetector()
        assert detector.get_last_detection() is None

    def test_start_stop_monitoring(self):
        detector = MFADetector()
        callback = MagicMock()
        with patch("core.mfa_detection._IS_WINDOWS", False):
            detector.start_monitoring(callback, interval=0.5)
            assert detector._monitor_thread is not None
            detector.stop_monitoring()
            assert detector._monitor_thread is None

    def test_constants_not_empty(self):
        assert len(AUTH_WINDOW_TITLES) > 0
        assert len(MFA_PATTERNS) > 0
        assert len(UAC_KEYWORDS) > 0
