"""
Tests for MFA Handler

Comprehensive test suite for multi-factor authentication resolution.
"""

import asyncio

import pytest

from core.web.mfa_detector import MFAField, MFAInputType
from core.web.mfa_handler import (
    MFAHandler,
    MFAResolutionMethod,
    MFAResolutionResult,
    TOTPProvider,
    create_mfa_handler,
)


class TestTOTPProvider:
    """Test TOTPProvider class."""

    def test_provider_initialization(self):
        """Test provider initialization."""
        provider = TOTPProvider()
        assert provider.secrets == {}
        assert provider.PROVIDERS is not None

    def test_add_secret(self):
        """Test adding a TOTP secret."""
        provider = TOTPProvider()
        provider.add_secret("github", "JBSWY3DPEHPK3PXP")
        assert provider.get_secret("github") == "JBSWY3DPEHPK3PXP"

    def test_remove_secret(self):
        """Test removing a TOTP secret."""
        provider = TOTPProvider()
        provider.add_secret("github", "JBSWY3DPEHPK3PXP")
        provider.remove_secret("github")
        assert provider.get_secret("github") is None

    def test_list_services(self):
        """Test listing services."""
        provider = TOTPProvider()
        provider.add_secret("github", "JBSWY3DPEHPK3PXP")
        provider.add_secret("aws", "JBSWY3DPEHPK3PXP")
        services = provider.list_services()
        assert len(services) == 2
        assert "github" in services
        assert "aws" in services

    def test_generate_totp_valid_secret(self):
        """Test generating TOTP with valid secret."""
        provider = TOTPProvider()
        provider.add_secret("test", "JBSWY3DPEHPK3PXP")
        code = provider.generate_totp("test")
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_totp_no_secret(self):
        """Test generating TOTP without secret."""
        provider = TOTPProvider()
        code = provider.generate_totp("nonexistent")
        assert code is None

    def test_verify_totp_valid_code(self):
        """Test verifying a valid TOTP code."""
        provider = TOTPProvider()
        provider.add_secret("test", "JBSWY3DPEHPK3PXP")
        code = provider.generate_totp("test")
        assert provider.verify_totp("test", code) is True

    def test_verify_totp_invalid_code(self):
        """Test verifying an invalid TOTP code."""
        provider = TOTPProvider()
        provider.add_secret("test", "JBSWY3DPEHPK3PXP")
        assert provider.verify_totp("test", "000000") is False

    def test_get_time_remaining(self):
        """Test getting time remaining in TOTP step."""
        provider = TOTPProvider()
        remaining = provider.get_time_remaining()
        assert 0 <= remaining <= 30
        assert isinstance(remaining, int)


class TestMFAHandler:
    """Test MFAHandler class."""

    def test_handler_initialization(self):
        """Test handler initialization."""
        handler = MFAHandler()
        assert handler.totp_provider is not None
        assert handler.max_attempts == 3
        assert handler.resolution_history == []

    def test_add_totp_secret(self):
        """Test adding TOTP secret to handler."""
        handler = MFAHandler()
        handler.add_totp_secret("github", "JBSWY3DPEHPK3PXP")
        assert handler.totp_provider.get_secret("github") == "JBSWY3DPEHPK3PXP"

    def test_resolve_totp_auto_success(self):
        """Test automatic TOTP resolution success."""
        handler = MFAHandler()
        handler.add_totp_secret("test", "JBSWY3DPEHPK3PXP")

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        result = handler.resolve_mfa(field, "https://test.com/login", service_name="test")
        assert result.success is True
        assert result.code_used is not None
        assert len(result.code_used) == 6
        assert result.method_used == MFAResolutionMethod.TOTP_AUTO

    def test_resolve_totp_auto_no_secret(self):
        """Test automatic TOTP resolution without secret."""
        handler = MFAHandler()

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        result = handler.resolve_mfa(field, "https://test.com/login", service_name="test")
        assert result.success is False
        assert result.method_used == MFAResolutionMethod.TOTP_AUTO
        assert "No TOTP secret found" in result.error_message

    def test_resolve_totp_auto_url_extraction(self):
        """Test TOTP resolution with URL-based service detection."""
        handler = MFAHandler()
        handler.add_totp_secret("github", "JBSWY3DPEHPK3PXP")

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        # Should auto-detect "github" from URL
        result = handler.resolve_mfa(field, "https://github.com/login", service_name=None)
        assert result.success is True
        assert result.method_used == MFAResolutionMethod.TOTP_AUTO

    def test_code_caching(self):
        """Test that TOTP codes are cached."""
        handler = MFAHandler()
        handler.add_totp_secret("test", "JBSWY3DPEHPK3PXP")

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        # First call should generate and cache
        result1 = handler.resolve_mfa(field, "https://test.com", service_name="test")
        code1 = result1.code_used

        # Second call within cache window should return same code
        result2 = handler.resolve_mfa(field, "https://test.com", service_name="test")
        code2 = result2.code_used

        assert code1 == code2

    def test_user_prompt_callback(self):
        """Test user prompt callback resolution."""
        handler = MFAHandler()

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        async def mock_callback(prompt):
            return "123456"

        result = asyncio.run(handler._try_user_prompt(field, mock_callback))
        assert result.success is True
        assert result.code_used == "123456"
        assert result.method_used == MFAResolutionMethod.USER_PROMPT

    def test_user_prompt_empty_input(self):
        """Test user prompt with empty input."""
        handler = MFAHandler()

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        async def mock_callback(prompt):
            return ""

        result = asyncio.run(handler._try_user_prompt(field, mock_callback))
        assert result.success is False
        assert "did not provide" in result.error_message

    def test_user_prompt_exception(self):
        """Test user prompt with exception."""
        handler = MFAHandler()

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        async def mock_callback(prompt):
            raise ValueError("Test error")

        result = asyncio.run(handler._try_user_prompt(field, mock_callback))
        assert result.success is False
        assert "Error prompting user" in result.error_message

    def test_sms_retrieval_not_implemented(self):
        """Test SMS retrieval (not yet implemented)."""
        handler = MFAHandler()

        field = MFAField(
            element_id="sms-code",
            input_type=MFAInputType.SMS,
            confidence=0.8,
        )

        result = handler._try_code_retrieval(field)
        assert result.success is False
        assert result.method_used == MFAResolutionMethod.SMS_RETRIEVAL
        assert "not implemented" in result.error_message

    def test_email_retrieval_not_implemented(self):
        """Test email retrieval (not yet implemented)."""
        handler = MFAHandler()

        field = MFAField(
            element_id="email-code",
            input_type=MFAInputType.EMAIL,
            confidence=0.8,
        )

        result = handler._try_code_retrieval(field)
        assert result.success is False
        assert result.method_used == MFAResolutionMethod.EMAIL_RETRIEVAL
        assert "not implemented" in result.error_message

    def test_service_extraction_from_url(self):
        """Test service name extraction from URL."""
        handler = MFAHandler()

        # Test various URLs
        assert handler._extract_service_from_url("https://github.com/login") == "github"
        assert handler._extract_service_from_url("https://aws.amazon.com/console") == "aws"
        assert handler._extract_service_from_url("https://accounts.google.com") == "google"
        assert handler._extract_service_from_url("https://facebook.com") == "facebook"
        assert handler._extract_service_from_url("https://unknown.com") is None

    def test_generate_user_prompt_totp(self):
        """Test user prompt generation for TOTP."""
        handler = MFAHandler()

        field = MFAField(
            element_id="otp",
            input_type=MFAInputType.TOTP,
            confidence=0.9,
        )

        prompt = handler._generate_user_prompt(field)
        assert "authenticator" in prompt.lower()

    def test_generate_user_prompt_sms(self):
        """Test user prompt generation for SMS."""
        handler = MFAHandler()

        field = MFAField(
            element_id="sms",
            input_type=MFAInputType.SMS,
            confidence=0.9,
        )

        prompt = handler._generate_user_prompt(field)
        assert "sms" in prompt.lower() or "phone" in prompt.lower()

    def test_generate_user_prompt_email(self):
        """Test user prompt generation for email."""
        handler = MFAHandler()

        field = MFAField(
            element_id="email",
            input_type=MFAInputType.EMAIL,
            confidence=0.9,
        )

        prompt = handler._generate_user_prompt(field)
        assert "email" in prompt.lower()

    def test_select_best_result(self):
        """Test selecting best result from multiple attempts."""
        handler = MFAHandler()

        # Create mock results
        totp_result = MFAResolutionResult(
            success=True,
            code_used="123456",
            method_used=MFAResolutionMethod.TOTP_AUTO,
        )

        user_result = MFAResolutionResult(
            success=True,
            code_used="789012",
            method_used=MFAResolutionMethod.USER_PROMPT,
        )

        # User prompt should be preferred
        best = handler._select_best_result([user_result, totp_result])
        assert best.method_used == MFAResolutionMethod.USER_PROMPT


class TestMFAResolutionResult:
    """Test MFAResolutionResult dataclass."""

    def test_successful_result(self):
        """Test successful resolution result."""
        result = MFAResolutionResult(
            success=True,
            code_used="123456",
            method_used=MFAResolutionMethod.TOTP_AUTO,
        )
        assert result.success is True
        assert result.code_used == "123456"
        assert result.method_used == MFAResolutionMethod.TOTP_AUTO

    def test_failed_result(self):
        """Test failed resolution result."""
        result = MFAResolutionResult(
            success=False,
            code_used=None,
            method_used=MFAResolutionMethod.TOTP_AUTO,
            error_message="Secret not found",
            retry_allowed=True,
        )
        assert result.success is False
        assert result.code_used is None
        assert result.error_message == "Secret not found"
        assert result.retry_allowed is True


class TestMFAResolutionMethod:
    """Test MFAResolutionMethod enum."""

    def test_enum_values(self):
        """Test enum values exist."""
        assert MFAResolutionMethod.USER_PROMPT.value == "user_prompt"
        assert MFAResolutionMethod.TOTP_AUTO.value == "totp_auto"
        assert MFAResolutionMethod.SMS_RETRIEVAL.value == "sms_retrieval"
        assert MFAResolutionMethod.EMAIL_RETRIEVAL.value == "email_retrieval"
        assert MFAResolutionMethod.PUSH_APPROVAL.value == "push_approval"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_mfa_handler(self):
        """Test create_mfa_handler convenience function."""
        handler = create_mfa_handler()
        assert isinstance(handler, MFAHandler)
        assert handler.totp_provider is not None


class TestURLServiceExtraction:
    """Test comprehensive URL service extraction."""

    @pytest.mark.parametrize(
        "url,expected_service",
        [
            ("https://github.com/login", "github"),
            ("http://github.com/sessions", "github"),
            ("https://aws.amazon.com/console", "aws"),
            ("https://amazon.com/ap/signin", "amazon"),
            ("https://accounts.google.com", "google"),
            ("https://mail.google.com", "google"),
            ("https://facebook.com/login", "facebook"),
            ("https://twitter.com/login", "twitter"),
            ("https://x.com/login", "twitter"),
            ("https://linkedin.com/login", "linkedin"),
            ("https://login.microsoft.com", "microsoft"),
            ("https://live.com/login", "microsoft"),
            ("https://outlook.com/login", "microsoft"),
            ("https://dropbox.com/login", "dropbox"),
            ("https://stripe.com/login", "stripe"),
            ("https://paypal.com/login", "paypal"),
            ("https://ebay.com/login", "ebay"),
            ("https://reddit.com/login", "reddit"),
            ("https://unknown.com/login", None),
        ],
    )
    def test_extract_service(self, url, expected_service):
        """Test service extraction from various URLs."""
        handler = MFAHandler()
        result = handler._extract_service_from_url(url)
        assert result == expected_service
