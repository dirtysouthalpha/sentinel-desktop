"""Tests for core.netops.ssh_client and command_runner — mocked paramiko."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
            success=True,
            stdout="output",
            stderr="",
            exit_code=0,
            command="show version",
            duration_ms=150.0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "output"
        assert d["exit_code"] == 0
        assert d["duration_ms"] == 150.0


class TestCommandRunner:
    def test_show_version_cisco(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.command_runner import CommandRunner
        from core.netops.ssh_client import SSHClient

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
        from core.netops.command_runner import CommandRunner
        from core.netops.ssh_client import SSHClient

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
        from core.netops.command_runner import CommandRunner
        from core.netops.ssh_client import SSHClient

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"4 packets transmitted, 4 received\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="10.0.0.1")
        client.connect()
        runner = CommandRunner(client, device_type="linux")
        runner.ping("192.168.1.1")
        mock_client.exec_command.assert_called_with("ping -c 4 192.168.1.1", timeout=30.0)

    def test_run_raw(self, mock_paramiko):
        mock_pw, mock_client = mock_paramiko
        from core.netops.command_runner import CommandRunner
        from core.netops.ssh_client import SSHClient

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
        from core.netops.command_runner import CommandRunner
        from core.netops.ssh_client import SSHClient

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

    def _make_runner(self, mock_paramiko, device_type="cisco_ios"):
        mock_pw, mock_client = mock_paramiko
        from core.netops.command_runner import CommandRunner
        from core.netops.ssh_client import SSHClient

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"output\n"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        client = SSHClient(hostname="192.168.1.1")
        client.connect()
        return CommandRunner(client, device_type=device_type), mock_client

    def test_show_routing_cisco(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.show_routing()
        cmd = mock_client.exec_command.call_args[0][0]
        assert "route" in cmd.lower()

    def test_show_arp_cisco(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.show_arp()
        cmd = mock_client.exec_command.call_args[0][0]
        assert "arp" in cmd.lower()

    def test_show_running_config_cisco(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.show_running_config()
        mock_client.exec_command.assert_called_with("show running-config", timeout=30.0)

    def test_traceroute_cisco(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.traceroute("8.8.8.8")
        mock_client.exec_command.assert_called_with("traceroute 8.8.8.8", timeout=30.0)

    def test_traceroute_fortigate(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "fortigate")
        runner.traceroute("8.8.8.8")
        mock_client.exec_command.assert_called_with("execute traceroute 8.8.8.8", timeout=30.0)

    def test_traceroute_mikrotik(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "mikrotik")
        runner.traceroute("8.8.8.8")
        mock_client.exec_command.assert_called_with("/tool traceroute 8.8.8.8", timeout=30.0)

    @pytest.mark.parametrize(
        "bad_target",
        [
            "8.8.8.8 ; write erase",  # shell metacharacters
            "-c",                      # leading dash = flag injection
            "$(reboot)",               # command substitution
            "8.8.8.8\nreboot",         # newline escape
            "",                        # empty
            "../../etc",               # traversal-ish
        ],
    )
    def test_ping_rejects_injection(self, mock_paramiko, bad_target):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        result = runner.ping(bad_target, count=4)
        assert result.success is False
        assert "invalid host" in result.stderr
        # No command must reach the device when the target is rejected.
        mock_client.exec_command.assert_not_called()

    @pytest.mark.parametrize(
        "bad_target",
        ["8.8.8.8;reboot", "-n", "$(id)", "", "8.8.8.8|cat /etc/passwd"],
    )
    def test_traceroute_rejects_injection(self, mock_paramiko, bad_target):
        runner, mock_client = self._make_runner(mock_paramiko, "linux")
        result = runner.traceroute(bad_target)
        assert result.success is False
        assert "invalid host" in result.stderr
        mock_client.exec_command.assert_not_called()

    def test_ping_count_is_bounded(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.ping("8.8.8.8", count=999)
        # count clamped to 10, not passed through as 999
        mock_client.exec_command.assert_called_with("ping 8.8.8.8 repeat 10", timeout=30.0)

    def test_show_logging_cisco(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.show_logging(lines=20)
        mock_client.exec_command.assert_called_with("show logging | last 20", timeout=30.0)

    def test_show_logging_linux(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "linux")
        runner.show_logging()
        mock_client.exec_command.assert_called_with("tail -n 50 /var/log/syslog", timeout=30.0)

    def test_show_cpu_cisco(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "cisco_ios")
        runner.show_cpu()
        mock_client.exec_command.assert_called_with("show processes cpu", timeout=30.0)

    def test_show_cpu_fortigate(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "fortigate")
        runner.show_cpu()
        mock_client.exec_command.assert_called_with("get system performance status", timeout=30.0)

    def test_show_cpu_mikrotik(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "mikrotik")
        runner.show_cpu()
        mock_client.exec_command.assert_called_with("/system resource print", timeout=30.0)

    def test_show_cpu_linux(self, mock_paramiko):
        runner, mock_client = self._make_runner(mock_paramiko, "linux")
        runner.show_cpu()
        mock_client.exec_command.assert_called_with("top -bn1 | head -5", timeout=30.0)
