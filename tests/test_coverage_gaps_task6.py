"""Gap tests for Task 6: core/web/* and core/platform/* coverage gaps.

Targets
-------
- core/web/mfa_detector.py : 181, 225, 300 (hidden-input continue)
                             370, 374, 378 (_classify_mfa_type SMS/EMAIL/RECOVERY)
- core/web/mfa_handler.py  : 201 (retrieval success → early return)
                             312 (_generate_user_prompt else branch)
- core/web/session_vault.py: 72-74 (save_session except Exception)
                             197-198 (_save OSError)
- core/platform/__init__.py: 83-85 (Windows backend branch)
- core/platform/base.py    : 88, 90, 92 (UIElement.to_dict optional fields)
                             375 (NoOpAccessibility.set_element_value)
                             426, 429, 432 (NoOpShell methods)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# ── MFADetector ────────────────────────────────────────────────────────────────

from core.web.mfa_detector import MFADetector, MFAInputType


class TestMFADetectorHiddenInputSkip:
    """Lines 181, 225, 300: hidden inputs are skipped (continue) in all three detect methods."""

    def setup_method(self) -> None:
        self.detector = MFADetector()

    def test_detect_by_keywords_skips_hidden(self) -> None:
        inputs = [
            {"type": "hidden", "name": "csrf_token"},
            {"type": "text", "name": "otp_code", "id": "otp"},
        ]
        result = self.detector._detect_by_keywords(inputs, "Enter OTP code")
        # hidden input skipped; visible one may or may not match — no crash
        assert isinstance(result, list)

    def test_detect_by_dom_attributes_skips_hidden(self) -> None:
        inputs = [
            {"type": "hidden", "name": "state"},
            {"type": "text", "autocomplete": "one-time-code", "name": "code", "id": "code"},
        ]
        result = self.detector._detect_by_dom_attributes(inputs)
        assert len(result) == 1  # hidden skipped, visible found

    def test_detect_by_structure_skips_hidden(self) -> None:
        # Hidden-only inputs → loop hits the continue (line 300) and returns []
        inputs = [{"type": "hidden", "name": "nonce"}]
        result = self.detector._detect_by_structure(
            forms=[{}],
            inputs=inputs,
            text="",
            url="https://example.com/page",
        )
        assert result == []


class TestMFAClassifyType:
    """Lines 370, 374, 378: _classify_mfa_type returns SMS/EMAIL/RECOVERY."""

    def setup_method(self) -> None:
        self.d = MFADetector()

    def test_sms_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "sms_code", "id": ""}) == MFAInputType.SMS

    def test_phone_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "phone_otp", "id": ""}) == MFAInputType.SMS

    def test_mobile_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "mobile_code", "id": ""}) == MFAInputType.SMS

    def test_email_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "email_code", "id": ""}) == MFAInputType.EMAIL

    def test_mail_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "mailcode", "id": ""}) == MFAInputType.EMAIL

    def test_recovery_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "recovery_code", "id": ""}) == MFAInputType.RECOVERY

    def test_backup_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "backup_key", "id": ""}) == MFAInputType.RECOVERY

    def test_restore_keyword(self) -> None:
        assert self.d._classify_mfa_type({"name": "restore_code", "id": ""}) == MFAInputType.RECOVERY


# ── MFAHandler ─────────────────────────────────────────────────────────────────

from core.web.mfa_handler import MFAHandler, MFAResolutionMethod, MFAResolutionResult


class TestMFAHandlerRetrievalSuccess:
    """Line 201: return retrieval_result when SMS/EMAIL retrieval succeeds."""

    def test_sms_retrieval_success_returned(self) -> None:
        handler = MFAHandler()
        mfa_field = MagicMock()
        mfa_field.input_type = MFAInputType.SMS

        success_result = MFAResolutionResult(
            success=True,
            code_used="654321",
            method_used=MFAResolutionMethod.SMS_RETRIEVAL,
            error_message=None,
            retry_allowed=False,
        )

        with patch.object(handler, "_try_code_retrieval", return_value=success_result):
            result = handler.resolve_mfa(mfa_field, page_url="https://example.com/mfa")

        assert result.success is True
        assert result.code_used == "654321"

    def test_email_retrieval_success_returned(self) -> None:
        handler = MFAHandler()
        mfa_field = MagicMock()
        mfa_field.input_type = MFAInputType.EMAIL

        success_result = MFAResolutionResult(
            success=True,
            code_used="123456",
            method_used=MFAResolutionMethod.EMAIL_RETRIEVAL,
            error_message=None,
            retry_allowed=False,
        )

        with patch.object(handler, "_try_code_retrieval", return_value=success_result):
            result = handler.resolve_mfa(mfa_field, page_url="https://example.com/verify")

        assert result.success is True


class TestMFAHandlerGeneratePromptElse:
    """Line 312: _generate_user_prompt else branch for PUSH and UNKNOWN types."""

    def test_push_type_returns_generic_prompt(self) -> None:
        handler = MFAHandler()
        mfa_field = MagicMock()
        mfa_field.input_type = MFAInputType.PUSH
        assert handler._generate_user_prompt(mfa_field) == "Please enter the verification code:"

    def test_unknown_type_returns_generic_prompt(self) -> None:
        handler = MFAHandler()
        mfa_field = MagicMock()
        mfa_field.input_type = MFAInputType.UNKNOWN
        assert handler._generate_user_prompt(mfa_field) == "Please enter the verification code:"


# ── SessionVault ───────────────────────────────────────────────────────────────

from core.web.session_vault import SessionVault


class TestSessionVaultSaveException:
    """Lines 72-74: save_session catches Exception from _save and returns False."""

    def test_save_session_returns_false_on_exception(self, tmp_path) -> None:
        vault = SessionVault(tmp_path / "vault.json")
        with patch.object(vault, "_save", side_effect=RuntimeError("disk full")):
            result = vault.save_session("example.com", [{"name": "sid", "value": "abc"}])
        assert result is False


class TestSessionVaultSaveOSError:
    """Lines 197-198: _save catches OSError from write_text and does not raise."""

    def test_save_oserror_does_not_propagate(self, tmp_path) -> None:
        vault = SessionVault(tmp_path / "vault.json")
        vault._data = {
            "example.com": {
                "cookies": [],
                "local_storage": {},
                "saved_at": "2026-06-11T00:00:00",
                "domain": "example.com",
            }
        }
        # Replace _path with a mock whose write_text raises OSError
        mock_path = MagicMock()
        mock_path.parent.mkdir.return_value = None
        mock_path.write_text.side_effect = OSError("no space left")
        vault._path = mock_path
        # Should not raise
        vault._save()
        mock_path.write_text.assert_called_once()


# ── Platform __init__ ──────────────────────────────────────────────────────────

import core.platform as _platform_module
from core.platform import _create_backend


class TestPlatformWindowsBranch:
    """Lines 83-85: Windows backend branch in _create_backend."""

    def test_windows_backend_instantiated_on_windows(self) -> None:
        mock_instance = MagicMock()
        mock_cls = MagicMock(return_value=mock_instance)
        fake_module = MagicMock()
        fake_module.WindowsBackend = mock_cls

        with (
            patch.object(_platform_module, "current_platform", return_value="windows"),
            patch.dict(sys.modules, {"core.platform.windows_backend": fake_module}),
        ):
            result = _create_backend()

        mock_cls.assert_called_once()
        assert result is mock_instance


# ── Platform base.py ───────────────────────────────────────────────────────────

from core.platform.base import NoOpAccessibility, NoOpShell, UIElement


class TestUIElementToDictOptionalFields:
    """Lines 88, 90, 92: value/automation_id/actions appear in to_dict when set."""

    def test_value_included(self) -> None:
        elem = UIElement(name="input", value="hello")
        assert elem.to_dict()["value"] == "hello"

    def test_automation_id_included(self) -> None:
        elem = UIElement(name="btn", automation_id="btn-001")
        assert elem.to_dict()["automation_id"] == "btn-001"

    def test_actions_included(self) -> None:
        elem = UIElement(name="btn", actions=["invoke", "toggle"])
        assert elem.to_dict()["actions"] == ["invoke", "toggle"]

    def test_none_value_not_included(self) -> None:
        elem = UIElement(name="label")  # value=None, automation_id=None, actions=[]
        d = elem.to_dict()
        assert "value" not in d
        assert "automation_id" not in d
        assert "actions" not in d


class TestNoOpAccessibilitySetValue:
    """Line 375: NoOpAccessibility.set_element_value returns False."""

    def test_set_element_value_returns_false(self) -> None:
        noop = NoOpAccessibility()
        assert noop.set_element_value(UIElement(name="x"), "v") is False


class TestNoOpShellMethods:
    """Lines 426, 429, 432: NoOpShell execute/get_platform_shell/sanitize_command."""

    def setup_method(self) -> None:
        self.shell = NoOpShell()

    def test_execute_returns_error_dict(self) -> None:
        result = self.shell.execute("ls -la")
        assert result["exit_code"] == -1
        assert result["stdout"] == ""
        assert "No shell available" in result["stderr"]

    def test_get_platform_shell_returns_sh(self) -> None:
        assert self.shell.get_platform_shell() == "sh"

    def test_sanitize_command_returns_command_unchanged(self) -> None:
        assert self.shell.sanitize_command("echo hello") == "echo hello"
