import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.notify import NotifyCommands


class TestNotifyCommands:
    def setup_method(self):
        self.cmds = NotifyCommands()

    @patch("src.commands.notify.subprocess.Popen")
    def test_send(self, mock_popen):
        result = self.cmds.send("Test", "Hello")
        assert result.success is True
        assert "Test" in result.message

    @patch("src.commands.notify.subprocess.Popen")
    def test_alert(self, mock_popen):
        result = self.cmds.alert("Warning!")
        assert result.success is True
        assert "Alert" in result.message or "Warning" in result.message

    def test_execute_notify(self):
        with patch.object(self.cmds, "send") as mock_send:
            mock_send.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("notify test message")
            mock_send.assert_called_once()

    def test_execute_alert(self):
        with patch.object(self.cmds, "alert") as mock_alert:
            mock_alert.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("alert danger")
            mock_alert.assert_called_once()

    def test_execute_unknown(self):
        result = self.cmds.execute("fly away")
        assert result.success is False
