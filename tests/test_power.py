import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.commands.power import PowerCommands


class TestPowerCommands:
    def setup_method(self):
        self.cmds = PowerCommands()

    @patch("core.commands.power.subprocess.Popen")
    def test_shutdown(self, mock_popen):
        result = self.cmds.shutdown(0)
        assert result.success is True
        assert "Shut" in result.message

    @patch("core.commands.power.subprocess.Popen")
    def test_shutdown_delay(self, mock_popen):
        result = self.cmds.shutdown(30)
        assert result.success is True

    @patch("core.commands.power.subprocess.Popen")
    def test_restart(self, mock_popen):
        result = self.cmds.restart(0)
        assert result.success is True
        assert "Restart" in result.message

    @patch("core.commands.power.subprocess.Popen")
    def test_sleep(self, mock_popen):
        result = self.cmds.sleep()
        assert result.success is True
        assert "sleep" in result.message.lower()

    @patch("core.commands.power.subprocess.Popen")
    def test_lock(self, mock_popen):
        result = self.cmds.lock()
        assert result.success is True
        assert "lock" in result.message.lower()

    @patch("core.commands.power.subprocess.Popen")
    def test_cancel(self, mock_popen):
        result = self.cmds.cancel()
        assert result.success is True
        assert "cancel" in result.message.lower()

    def test_execute_shutdown(self):
        with patch.object(self.cmds, "shutdown") as mock_sd:
            mock_sd.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("shutdown")
            mock_sd.assert_called_once()

    def test_execute_restart(self):
        with patch.object(self.cmds, "restart") as mock_rs:
            mock_rs.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("restart")
            mock_rs.assert_called_once()

    def test_execute_lock(self):
        with patch.object(self.cmds, "lock") as mock_lk:
            mock_lk.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("lock screen")
            mock_lk.assert_called_once()

    def test_execute_sleep(self):
        with patch.object(self.cmds, "sleep") as mock_sl:
            mock_sl.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("sleep")
            mock_sl.assert_called_once()

    def test_execute_cancel(self):
        with patch.object(self.cmds, "cancel") as mock_cn:
            mock_cn.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("cancel shutdown")
            mock_cn.assert_called_once()

    def test_execute_unknown(self):
        result = self.cmds.execute("fly to moon")
        assert result.success is False
