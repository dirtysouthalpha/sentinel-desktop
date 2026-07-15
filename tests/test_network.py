import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.commands.network import NetworkCommands


class TestNetworkCommands:
    def setup_method(self):
        self.cmds = NetworkCommands()

    @patch("core.commands.network.subprocess.run")
    def test_ping(self, mock_run):
        mock_run.return_value = MagicMock(stdout="PING google.com: 56 data bytes", returncode=0)
        result = self.cmds.ping("google.com")
        assert result.success is True
        assert "google.com" in result.message

    @patch("core.commands.network.subprocess.run")
    def test_ping_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ping", timeout=15)
        result = self.cmds.ping("slowhost.com")
        assert result.success is False
        assert "timed out" in result.message.lower()

    @patch("core.commands.network.subprocess.run")
    def test_ipconfig(self, mock_run):
        mock_run.return_value = MagicMock(stdout="eth0: flags=4099", returncode=0)
        result = self.cmds.ipconfig()
        assert result.success is True

    @patch("core.commands.network.subprocess.run")
    def test_diagnostics(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ttl=64 time=1.2ms", returncode=0)
        result = self.cmds.diagnostics()
        assert result.success is True
        assert "Connectivity" in result.message
