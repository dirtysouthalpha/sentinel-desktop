"""Gap tests for core.netops.ssh_client — covers lines 30-31, 105, 122, 137-138, 185-188."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_paramiko():
    """Patch paramiko at both the module-global and sys.modules level.

    The module-global patch (core.netops.ssh_client.paramiko) is sufficient on
    Python 3.11+, but on 3.10 the mock can leak and reach the real paramiko
    SSHClient.connect(), which then hangs for 30s on a real network connection
    to 10.0.0.1. Patching sys.modules['paramiko'] too ensures the real client
    is never reachable, making the fixture version-independent.
    """
    fake_paramiko = MagicMock()
    mock_client = MagicMock()
    fake_paramiko.SSHClient.return_value = mock_client
    fake_paramiko.AutoAddPolicy.return_value = "auto_add_policy"

    original_paramiko = sys.modules.get("paramiko")
    sys.modules["paramiko"] = fake_paramiko
    try:
        with patch("core.netops.ssh_client._HAS_PARAMIKO", True):
            with patch("core.netops.ssh_client.paramiko", fake_paramiko):
                yield fake_paramiko, mock_client
    finally:
        if original_paramiko is None:
            sys.modules.pop("paramiko", None)
        else:
            sys.modules["paramiko"] = original_paramiko


class TestParamikoImportLines:
    """Lines 30-31 — paramiko = _paramiko; _HAS_PARAMIKO = True in module-level import."""

    def test_paramiko_import_lines_covered(self):
        """Reload ssh_client with a fake paramiko in sys.modules to cover lines 30-31."""
        fake_paramiko = MagicMock()
        fake_paramiko.__version__ = "3.0.0"
        fake_paramiko.SSHClient = MagicMock
        fake_paramiko.AutoAddPolicy = MagicMock

        original = sys.modules.get("paramiko")
        original_ssh = sys.modules.get("core.netops.ssh_client")
        try:
            sys.modules["paramiko"] = fake_paramiko
            if "core.netops.ssh_client" in sys.modules:
                del sys.modules["core.netops.ssh_client"]
            import core.netops.ssh_client as ssh_mod

            assert ssh_mod._HAS_PARAMIKO is True
            assert ssh_mod.paramiko is fake_paramiko
        finally:
            # Restore original state
            if original is None:
                sys.modules.pop("paramiko", None)
            else:
                sys.modules["paramiko"] = original
            if original_ssh is not None:
                sys.modules["core.netops.ssh_client"] = original_ssh
            elif "core.netops.ssh_client" in sys.modules:
                del sys.modules["core.netops.ssh_client"]
            # Force reimport with real state
            import core.netops.ssh_client  # noqa: F401


class TestSSHClientAlreadyConnected:
    """Line 105 — connect() is a no-op when already connected."""

    def test_connect_noop_when_already_connected(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        client = SSHClient(hostname="10.0.0.1", username="admin")
        client.connect()
        assert client.is_connected is True

        # Second connect should return early — mock_client.connect should still be called only once
        client.connect()
        mock_client.connect.assert_called_once()


class TestSSHClientKeyFilename:
    """Line 122 — key_filename is passed to connect() kwargs."""

    def test_connect_with_key_filename(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        client = SSHClient(
            hostname="10.0.0.1",
            username="admin",
            key_filename="/home/user/.ssh/id_rsa",
        )
        client.connect()

        _, kwargs = mock_client.connect.call_args
        assert kwargs.get("key_filename") == "/home/user/.ssh/id_rsa"


class TestSSHClientCloseException:
    """Lines 137-138 — _client.close() raises, caught silently."""

    def test_close_with_exception_still_disconnects(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        mock_client.close.side_effect = Exception("transport already closed")

        client = SSHClient(hostname="10.0.0.1")
        client.connect()
        assert client.is_connected is True

        # Should not raise despite _client.close() throwing
        client.close()
        assert client.is_connected is False
        assert client._client is None


class TestSSHClientRunCommandException:
    """Lines 185-188 — exec_command raises, returns SSHResult(success=False)."""

    def test_run_command_exception_returns_failure_result(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient, SSHResult

        mock_client.exec_command.side_effect = Exception("channel closed unexpectedly")

        client = SSHClient(hostname="10.0.0.1", username="admin")
        client.connect()
        result = client.run_command("show version")

        assert isinstance(result, SSHResult)
        assert result.success is False
        assert "channel closed" in result.stderr
        assert result.exit_code is None
        assert result.command == "show version"
        assert result.duration_ms >= 0

    def test_run_command_timeout_exception(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        mock_client.exec_command.side_effect = TimeoutError("timed out")

        client = SSHClient(hostname="10.0.0.1")
        client.connect()
        result = client.run_command("ping 8.8.8.8")

        assert result.success is False
        assert "timed out" in result.stderr
