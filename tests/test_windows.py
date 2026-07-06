"""Tests for window management commands."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.commands.windows import WindowCommands


class TestWindowCommands:
    def setup_method(self):
        self.cmds = WindowCommands()

    @patch("src.commands.windows.subprocess.run")
    def test_list_windows(self, mock_run):
        mock_run.return_value = MagicMock(stdout="0x01 Notepad\n0x02 Chrome", returncode=0)
        result = self.cmds.list_windows()
        assert result.success is True

    @patch("src.commands.windows.subprocess.run")
    def test_list_no_windows(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = self.cmds.list_windows()
        assert result.success is True
        assert "no open" in result.message.lower()

    @patch("src.commands.windows.subprocess.run")
    def test_list_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("wmctrl not found")
        result = self.cmds.list_windows()
        assert result.success is False
        assert "not available" in result.message.lower()

    def test_execute_list(self):
        with patch.object(self.cmds, "list_windows") as mock_list:
            mock_list.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("list windows")
            mock_list.assert_called_once()
