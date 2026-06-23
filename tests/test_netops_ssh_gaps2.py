"""Gap tests for core.netops.ssh_client transport-liveness recovery.

A cached _connected flag cannot detect a server-side session drop (idle
timeout, firewall reap, network blip). is_connected must verify the
underlying paramiko transport is actually active, or run_command's
reconnect guard never fires and the client stays wedged for the rest of
the session after one transient failure.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_paramiko():
    """Patch paramiko at module-global and sys.modules level (version-safe)."""
    fake_paramiko = MagicMock()
    fake_paramiko.AutoAddPolicy.return_value = "auto_add_policy"

    original_paramiko = sys.modules.get("paramiko")
    sys.modules["paramiko"] = fake_paramiko
    try:
        with patch("core.netops.ssh_client._HAS_PARAMIKO", True):
            with patch("core.netops.ssh_client.paramiko", fake_paramiko):
                yield fake_paramiko
    finally:
        if original_paramiko is None:
            sys.modules.pop("paramiko", None)
        else:
            sys.modules["paramiko"] = original_paramiko


def _live_client(stdout: bytes = b"ok", exit_code: int = 0):
    """A fake paramiko client whose transport reports active and exec succeeds."""
    client = MagicMock(name="live_client")
    transport = MagicMock(name="live_transport")
    transport.is_active.return_value = True
    client.get_transport.return_value = transport

    stdin = MagicMock()
    out = MagicMock()
    out.read.return_value = stdout
    out.channel.recv_exit_status.return_value = exit_code
    err = MagicMock()
    err.read.return_value = b""
    client.exec_command.return_value = (stdin, out, err)
    return client


def _dead_client():
    """A fake paramiko client whose transport reports inactive and exec fails."""
    client = MagicMock(name="dead_client")
    transport = MagicMock(name="dead_transport")
    transport.is_active.return_value = False
    client.get_transport.return_value = transport
    client.exec_command.side_effect = Exception("SSH session is not active")
    return client


class TestIsConnectedTransportLiveness:
    """is_connected must reflect actual transport liveness, not a cached flag."""

    def test_is_connected_false_when_transport_dropped(self, mock_paramiko):
        from core.netops.ssh_client import SSHClient

        live = _live_client()
        mock_paramiko.SSHClient.return_value = live

        client = SSHClient(hostname="10.0.0.1", username="admin")
        client.connect()
        assert client.is_connected is True

        # Server reaps the idle session; the cached flag can't see this.
        live.get_transport.return_value.is_active.return_value = False

        assert client.is_connected is False

    def test_is_connected_false_when_transport_none(self, mock_paramiko):
        from core.netops.ssh_client import SSHClient

        live = _live_client()
        live.get_transport.return_value = None
        mock_paramiko.SSHClient.return_value = live

        client = SSHClient(hostname="10.0.0.1", username="admin")
        client.connect()

        assert client.is_connected is False


class TestRunCommandReconnectsAfterDrop:
    """run_command must reconnect after a mid-session transport drop instead
    of failing every subsequent command against the dead client."""

    def test_run_command_reconnects_and_succeeds(self, mock_paramiko):
        from core.netops.ssh_client import SSHClient

        dead = _dead_client()
        live = _live_client(stdout=b"Software Version 12.2", exit_code=0)
        mock_paramiko.SSHClient.side_effect = [dead, live]

        client = SSHClient(hostname="10.0.0.1", username="admin")
        client.connect()
        assert client._client is dead

        # Transport dropped between commands. Without a live-transport check
        # the reconnect guard never fires and this returns failure.
        result = client.run_command("show version")

        assert result.success is True
        assert "Software Version 12.2" in result.stdout
        assert client._client is live
        live.exec_command.assert_called_once()
        dead.exec_command.assert_not_called()
