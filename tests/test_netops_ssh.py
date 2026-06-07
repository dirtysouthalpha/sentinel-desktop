"""Tests for core.netops.ssh_client and command_runner — mocked paramiko."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


@pytest.fixture
def mock_paramiko():
    """Mock paramiko module for SSH tests."""
    with patch("core.netops.ssh_client._HAS_PARAMIKO", True):
        with patch("core.netops.ssh_client.paramiko") as mock_pw:
            mock_client = MagicMock()
            mock_pw.SSHClient.return_value = mock_client
            mock_pw.AutoAddPolicy.return_value = "auto_add_policy"
            yield mock_pw, mock_client


class TestSSHClient:
    def test_connect(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        client = SSHClient(hostname="192.168.1.1", username="admin", password="secret")
        client.connect()
        mock_client.connect.assert_called_once()
        assert client.is_connected is True

    def test_close(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        client.close()
        assert client.is_connected is False
        mock_client.close.assert_called_once()

    def test_run_command(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        # Setup mock stdout/stderr
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"Cisco IOS Version 15.0\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1", username="admin", password="secret")
        client.connect()
        result = client.run_command("show version")

        assert result.success is True
        assert "Cisco IOS" in result.stdout
        assert result.exit_code == 0
        assert result.command == "show version"

    def test_run_command_failure(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b""
        mock_stdout.channel.recv_exit_status.return_value = 1
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"% Invalid command\n"
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        result = client.run_command("bad command")

        assert result.success is False
        assert result.exit_code == 1

    def test_run_commands_sequential(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"output\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        results = client.run_commands(["show version", "show ip interface brief"])

        assert len(results) == 2
        assert all(r.success for r in results)
        assert mock_client.exec_command.call_count == 2

    def test_context_manager(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        with SSHClient(hostname="192.168.1.1") as client:
            assert client.is_connected is True
        assert client.is_connected is False

    def test_connect_error(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient, SSHError

        mock_client.connect.side_effect = Exception("Connection refused")
        client = SSHClient(hostname="10.0.0.99")

        with pytest.raises(SSHError, match="Connection refused"):
            client.connect()

    def test_run_command_when_not_connected_auto_connects(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"ok\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1", username="admin", password="secret")
        result = client.run_command("echo hello")
        assert result.success is True

    def test_no_paramiko_raises(self):
        with patch("core.netops.ssh_client._HAS_PARAMIKO", False):
            from core.netops.ssh_client import SSHClient, SSHError

            with pytest.raises(SSHError, match="paramiko not installed"):
                SSHClient(hostname="x")


class TestSSHResult:
    def test_to_dict(self):
        from core.netops.ssh_client import SSHResult

        result = SSHResult(
            success=True, stdout="output", stderr="",
            exit_code=0, command="show version", duration_ms=150.0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "output"
        assert d["exit_code"] == 0
        assert d["duration_ms"] == 150.0


class TestCommandRunner:
    def test_show_version_cisco(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient
        from core.netops.command_runner import CommandRunner

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"Cisco IOS Version 15.0\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        runner = CommandRunner(client, device_type="cisco_ios")
        result = runner.show_version()
        assert result.success is True
        mock_client.exec_command.assert_called_with("show version", timeout=30.0)

    def test_ping_cisco(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient
        from core.netops.command_runner import CommandRunner

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"Success rate is 100 percent (4/4)\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        runner = CommandRunner(client, device_type="cisco_ios")
        result = runner.ping("8.8.8.8", count=4)
        assert result.success is True
        mock_client.exec_command.assert_called_with("ping 8.8.8.8 repeat 4", timeout=30.0)

    def test_ping_linux(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient
        from core.netops.command_runner import CommandRunner

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"4 packets transmitted, 4 received\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="10.0.0.1")
        client.connect()
        runner = CommandRunner(client, device_type="linux")
        result = runner.ping("192.168.1.1")
        mock_client.exec_command.assert_called_with("ping -c 4 192.168.1.1", timeout=30.0)

    def test_run_raw(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient
        from core.netops.command_runner import CommandRunner

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"raw output\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        runner = CommandRunner(client)
        result = runner.run_raw("custom command here")
        assert result.success is True

    def test_show_interfaces(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.ssh_client import SSHClient
        from core.netops.command_runner import CommandRunner

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"interface output\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        runner = CommandRunner(client, device_type="cisco_ios")
        runner.show_interfaces()
        mock_client.exec_command.assert_called_with("show ip interface brief", timeout=30.0)
