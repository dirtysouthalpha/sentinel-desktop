"""
Tests for MFA Detector

Comprehensive test suite for multi-factor authentication detection.
"""

from core.web.mfa_detector import (
    MFADetectionResult,
    MFADetector,
    MFAField,
    MFAInputType,
    detect_mfa,
)


class TestMFAField:
    """Test MFAField dataclass."""

    def test_create_totp_field(self):
        """Test creating a TOTP MFA field."""
        field = MFAField(
            element_id="otp-input",
            input_type=MFAInputType.TOTP,
            label="Authentication Code",
            placeholder="Enter 6-digit code",
            confidence=0.9,
        )
        assert field.element_id == "otp-input"
        assert field.input_type == MFAInputType.TOTP
        assert field.label == "Authentication Code"
        assert field.confidence == 0.9

    def test_create_sms_field(self):
        """Test creating an SMS MFA field."""
        field = MFAField(
            element_id="sms-code",
            input_type=MFAInputType.SMS,
            label="SMS Verification",
            confidence=0.8,
        )
        assert field.input_type == MFAInputType.SMS

    def test_create_email_field(self):
        """Test creating an email MFA field."""
        field = MFAField(
            element_id="email-otp",
            input_type=MFAInputType.EMAIL,
            label="Email Code",
            confidence=0.7,
        )
        assert field.input_type == MFAInputType.EMAIL


class TestMFADetector:
    """Test MFADetector class."""

    def test_detector_initialization(self):
        """Test detector initialization."""
        detector = MFADetector()
        assert detector.detection_history == []
        assert detector.MFA_KEYWORDS is not None
        assert len(detector.MFA_KEYWORDS) > 0

    def test_detect_no_inputs(self):
        """Test detection with no input fields."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com",
                "title": "Test Page",
                "text": "Some page text",
                "inputs": [],
                "forms": [],
            }
        )
        assert isinstance(result, MFADetectionResult)
        assert result.has_mfa is False
        assert len(result.mfa_fields) == 0

    def test_detect_totp_by_keywords(self):
        """Test TOTP detection via keywords."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/login",
                "title": "Login",
                "text": "Enter your authenticator app code",
                "inputs": [
                    {
                        "type": "text",
                        "name": "otp",
                        "id": "otp-input",
                        "label": "Authentication Code",
                        "placeholder": "123456",
                        "maxlength": "6",
                        "inputmode": "numeric",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is True
        assert len(result.mfa_fields) > 0
        assert any(f.input_type == MFAInputType.TOTP for f in result.mfa_fields)

    def test_detect_sms_by_keywords(self):
        """Test SMS detection via keywords."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/verify",
                "title": "Verify Phone",
                "text": "Enter the SMS code sent to your phone",
                "inputs": [
                    {
                        "type": "text",
                        "name": "sms_code",
                        "id": "sms-input",
                        "label": "SMS Verification Code",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is True
        assert any(f.input_type == MFAInputType.SMS for f in result.mfa_fields)

    def test_detect_email_by_keywords(self):
        """Test email detection via keywords."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/verify",
                "title": "Verify Email",
                "text": "Enter the code sent to your email",
                "inputs": [
                    {
                        "type": "text",
                        "name": "email_code",
                        "id": "email-input",
                        "label": "Email Verification Code",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is True
        assert any(f.input_type == MFAInputType.EMAIL for f in result.mfa_fields)

    def test_detect_by_dom_attributes(self):
        """Test detection via DOM attributes."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/2fa",
                "title": "Two Factor",
                "text": "Enter code",
                "inputs": [
                    {
                        "type": "text",
                        "name": "code",
                        "id": "auth-code",
                        "label": "",
                        "placeholder": "",
                        "maxlength": "6",
                        "inputmode": "numeric",
                        "autocomplete": "one-time-code",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is True
        assert len(result.mfa_fields) > 0

    def test_detect_by_structure(self):
        """Test detection via page structure."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://github.com/sessions/2fa",
                "title": "Two-factor authentication",
                "text": "Sign in with your authenticator app",
                "inputs": [
                    {
                        "type": "text",
                        "name": "otp",
                        "id": "otp",
                        "label": "",
                        "placeholder": "123456",
                        "maxlength": "6",
                        "inputmode": "numeric",
                        "autocomplete": "one-time-code",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is True
        assert result.page_type == "mfa"

    def test_no_mfa_detection(self):
        """Test page without MFA."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/contact",
                "title": "Contact Us",
                "text": "Send us a message",
                "inputs": [
                    {
                        "type": "text",
                        "name": "name",
                        "id": "name",
                        "label": "Your Name",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "name",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is False
        assert len(result.mfa_fields) == 0

    def test_multiple_mfa_fields(self):
        """Test detection with multiple MFA fields."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/verify",
                "title": "Verify Identity",
                "text": "Enter your authentication code and SMS code",
                "inputs": [
                    {
                        "type": "text",
                        "name": "totp",
                        "id": "totp-input",
                        "label": "Authenticator Code",
                        "placeholder": "",
                        "maxlength": "6",
                        "inputmode": "numeric",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    },
                    {
                        "type": "text",
                        "name": "sms",
                        "id": "sms-input",
                        "label": "SMS Code",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    },
                ],
                "forms": [],
            }
        )
        assert result.has_mfa is True
        assert len(result.mfa_fields) >= 2

    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/2fa",
                "title": "Two Factor",
                "text": "Enter your authenticator app verification code",
                "inputs": [
                    {
                        "type": "text",
                        "name": "otp",
                        "id": "otp",
                        "label": "Authentication Code",
                        "placeholder": "123456",
                        "maxlength": "6",
                        "inputmode": "numeric",
                        "autocomplete": "one-time-code",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.detection_methods) > 0

    def test_detection_history_tracking(self):
        """Test that detector tracks history."""
        detector = MFADetector()
        detector.detect_mfa(
            {
                "url": "https://example.com/1",
                "title": "Page 1",
                "text": "Text",
                "inputs": [],
                "forms": [],
            }
        )
        detector.detect_mfa(
            {
                "url": "https://example.com/2",
                "title": "Page 2",
                "text": "Text",
                "inputs": [],
                "forms": [],
            }
        )
        assert len(detector.detection_history) == 2


class TestDetectMFAConvenience:
    """Test detect_mfa convenience function."""

    def test_convenience_function(self):
        """Test the detect_mfa convenience function."""
        result = detect_mfa(
            {
                "url": "https://example.com/login",
                "title": "Login",
                "text": "Enter authenticator code",
                "inputs": [
                    {
                        "type": "text",
                        "name": "otp",
                        "id": "otp",
                        "label": "Code",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert isinstance(result, MFADetectionResult)
        assert result.has_mfa is True


class TestMFAInputTypeEnum:
    """Test MFAInputType enum."""

    def test_enum_values(self):
        """Test enum values exist."""
        assert MFAInputType.TOTP.value == "totp"
        assert MFAInputType.SMS.value == "sms"
        assert MFAInputType.EMAIL.value == "email"
        assert MFAInputType.PUSH.value == "push"
        assert MFAInputType.RECOVERY.value == "recovery"
        assert MFAInputType.UNKNOWN.value == "unknown"


class TestPageTypeClassification:
    """Test page type classification."""

    def test_classify_mfa_page(self):
        """Test MFA page classification."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://accounts.google.com/signin/2fa",
                "title": "2-Step Verification",
                "text": "Enter your verification code",
                "inputs": [
                    {
                        "type": "text",
                        "name": "code",
                        "id": "code",
                        "label": "",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.page_type == "mfa"

    def test_classify_login_page(self):
        """Test login page classification."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/login",
                "title": "Sign In",
                "text": "Please sign in to continue",
                "inputs": [
                    {
                        "type": "text",
                        "name": "username",
                        "id": "username",
                        "label": "",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.page_type == "login"

    def test_classify_registration_page(self):
        """Test registration page classification."""
        detector = MFADetector()
        result = detector.detect_mfa(
            {
                "url": "https://example.com/register",
                "title": "Create Account",
                "text": "Sign up for a new account",
                "inputs": [
                    {
                        "type": "text",
                        "name": "email",
                        "id": "email",
                        "label": "",
                        "placeholder": "",
                        "maxlength": "",
                        "inputmode": "",
                        "autocomplete": "",
                        "aria-label": "",
                        "title": "",
                    }
                ],
                "forms": [],
            }
        )
        assert result.page_type == "registration"
