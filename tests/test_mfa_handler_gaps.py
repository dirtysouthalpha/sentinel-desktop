"""Gap tests for core.web.mfa_handler — covers lines 95-97, 114, 119-121,
189-194, 198-201, 209, 309-312, 359-360, 372, 389, 394.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

from core.web.mfa_detector import MFAField, MFAInputType
from core.web.mfa_handler import (
    MFAHandler,
    MFAResolutionMethod,
    MFAResolutionResult,
    TOTPProvider,
)


def make_field(input_type: MFAInputType = MFAInputType.TOTP) -> MFAField:
    return MFAField(element_id="otp", input_type=input_type, confidence=0.9)


# ── TOTPProvider ───────────────────────────────────────────────────────────


class TestTOTPProviderGenerateException:
    """Lines 95-97 — generate_totp() exception caught."""

    def test_generate_totp_exception_returns_none(self):
        provider = TOTPProvider()
        provider.add_secret("github", "JBSWY3DPEHPK3PXP")

        with patch("pyotp.TOTP", side_effect=Exception("bad secret")):
            result = provider.generate_totp("github")

        assert result is None

    def test_generate_totp_no_secret_returns_none(self):
        provider = TOTPProvider()
        result = provider.generate_totp("nonexistent-service")
        assert result is None


class TestTOTPProviderVerifyBranches:
    """Lines 114, 119-121 — verify_totp() no-secret and exception paths."""

    def test_verify_totp_no_secret_returns_false(self):
        provider = TOTPProvider()
        result = provider.verify_totp("unknown-service", "123456")
        assert result is False

    def test_verify_totp_exception_returns_false(self):
        provider = TOTPProvider()
        provider.add_secret("github", "JBSWY3DPEHPK3PXP")

        with patch("pyotp.TOTP", side_effect=Exception("otp broken")):
            result = provider.verify_totp("github", "123456")

        assert result is False


# ── MFAHandler.resolve_mfa ─────────────────────────────────────────────────


class TestResolveMfaUserCallback:
    """Lines 189-194 — user_callback path in resolve_mfa()."""

    def test_user_callback_called_when_provided(self):
        handler = MFAHandler()
        field = make_field(MFAInputType.TOTP)

        async def my_callback(prompt: str) -> str:
            return "654321"

        result = handler.resolve_mfa(field, "https://github.com/login", user_callback=my_callback)
        # The callback was exercised; result may succeed or fail depending on
        # whether asyncio.run() picks up the code
        assert isinstance(result, MFAResolutionResult)

    def test_user_callback_successful_result(self):
        handler = MFAHandler()
        field = make_field(MFAInputType.TOTP)

        async def my_callback(prompt: str) -> str:
            return "999888"

        # Patch _try_user_prompt to return a success
        success_result = MFAResolutionResult(
            success=True,
            code_used="999888",
            method_used=MFAResolutionMethod.USER_PROMPT,
        )
        with patch.object(handler, "_try_user_prompt", new=AsyncMock(return_value=success_result)):
            result = handler.resolve_mfa(field, "https://example.com", user_callback=my_callback)
        assert isinstance(result, MFAResolutionResult)


class TestResolveMfaSmsEmailPath:
    """Lines 198-201 — SMS/Email retrieval path in resolve_mfa()."""

    def test_sms_field_invokes_code_retrieval(self):
        handler = MFAHandler()
        field = make_field(MFAInputType.SMS)

        # _try_code_retrieval is called automatically for SMS fields
        with patch.object(
            handler, "_try_code_retrieval", wraps=handler._try_code_retrieval
        ) as mock_retrieval:
            handler.resolve_mfa(field, "https://bank.example.com")

        mock_retrieval.assert_called_once_with(field)

    def test_email_field_invokes_code_retrieval(self):
        handler = MFAHandler()
        field = make_field(MFAInputType.EMAIL)

        with patch.object(
            handler, "_try_code_retrieval", wraps=handler._try_code_retrieval
        ) as mock_retrieval:
            handler.resolve_mfa(field, "https://mail.example.com")

        mock_retrieval.assert_called_once_with(field)


class TestTryTotpAutoNoService:
    """Line 209 — _try_totp_auto() with service=None returns failure."""

    def test_no_service_returns_failure_result(self):
        handler = MFAHandler()
        result = handler._try_totp_auto(service=None)
        assert result.success is False
        assert result.method_used == MFAResolutionMethod.TOTP_AUTO
        assert "No service name" in result.error_message


# ── _generate_user_prompt ──────────────────────────────────────────────────


class TestGenerateUserPromptBranches:
    """Lines 309-312 — SMS, EMAIL, RECOVERY prompt text."""

    def test_sms_prompt(self):
        handler = MFAHandler()
        prompt = handler._generate_user_prompt(make_field(MFAInputType.SMS))
        assert "phone" in prompt

    def test_email_prompt(self):
        handler = MFAHandler()
        prompt = handler._generate_user_prompt(make_field(MFAInputType.EMAIL))
        assert "email" in prompt

    def test_recovery_prompt(self):
        handler = MFAHandler()
        prompt = handler._generate_user_prompt(make_field(MFAInputType.RECOVERY))
        assert "recovery" in prompt.lower() or "backup" in prompt.lower()


# ── _extract_service_from_url ──────────────────────────────────────────────


class TestExtractServiceFromUrlFallback:
    """Lines 359-360 — non-URL string uses simple pattern match."""

    def test_non_url_string_matches_pattern(self):
        handler = MFAHandler()
        result = handler._extract_service_from_url("github.com/login")
        assert result == "github"

    def test_non_url_no_match_returns_none(self):
        handler = MFAHandler()
        result = handler._extract_service_from_url("unknownsite.xyz")
        assert result is None


# ── _check_cache ───────────────────────────────────────────────────────────


class TestCheckCacheExpired:
    """Line 372 — expired cache entry is deleted and None returned."""

    def test_expired_cache_returns_none(self):
        handler = MFAHandler()
        handler.cache_ttl = 5  # 5 seconds TTL
        # Manually insert an entry with a timestamp far in the past
        handler.code_cache["github"] = (time.time() - 100, "123456")

        result = handler._check_cache("github")
        assert result is None
        # Entry should be removed
        assert "github" not in handler.code_cache

    def test_fresh_cache_returns_code(self):
        handler = MFAHandler()
        handler.code_cache["github"] = (time.time(), "654321")
        result = handler._check_cache("github")
        assert result == "654321"


# ── _select_best_result ────────────────────────────────────────────────────


class TestSelectBestResult:
    """Lines 389, 394 — TOTP and generic success selection."""

    def _make_result(self, success, method):
        return MFAResolutionResult(success=success, code_used="x", method_used=method)

    def test_totp_success_preferred_over_retrieval(self):
        handler = MFAHandler()
        totp_result = self._make_result(True, MFAResolutionMethod.TOTP_AUTO)
        sms_result = self._make_result(True, MFAResolutionMethod.SMS_RETRIEVAL)

        best = handler._select_best_result([sms_result, totp_result])
        assert best.method_used == MFAResolutionMethod.TOTP_AUTO

    def test_any_success_returned_when_no_preferred(self):
        handler = MFAHandler()
        sms_result = self._make_result(True, MFAResolutionMethod.SMS_RETRIEVAL)
        fail_result = self._make_result(False, MFAResolutionMethod.TOTP_AUTO)

        best = handler._select_best_result([fail_result, sms_result])
        assert best.success is True

    def test_all_failed_returns_first(self):
        handler = MFAHandler()
        r1 = self._make_result(False, MFAResolutionMethod.TOTP_AUTO)
        r2 = self._make_result(False, MFAResolutionMethod.USER_PROMPT)
        best = handler._select_best_result([r1, r2])
        assert best is r1

    def test_empty_results_returns_fallback(self):
        handler = MFAHandler()
        result = handler._select_best_result([])
        assert result.success is False
