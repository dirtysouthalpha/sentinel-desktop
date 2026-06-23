"""Tests for clipboard commands."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.clipboard import ClipboardCommands


class TestClipboardCommands:
    def setup_method(self):
        self.cmds = ClipboardCommands()

    @patch("src.commands.clipboard.subprocess.run")
    def test_read_clipboard(self, mock_run):
        mock_run.return_value = MagicMock(stdout="hello world", returncode=0)
        result = self.cmds.read()
        assert result.success is True
        assert "hello world" in result.message

    @patch("src.commands.clipboard.subprocess.run")
    def test_read_empty_clipboard(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = self.cmds.read()
        assert result.success is True
        assert "empty" in result.message.lower()

    def test_write_empty(self):
        result = self.cmds.write("")
        assert result.success is False

    @patch("src.commands.clipboard.subprocess.run")
    def test_write_text(self, mock_run):
        result = self.cmds.write("test text")
        assert result.success is True
        assert "test text" in result.message

    @patch("src.commands.clipboard.subprocess.run")
    def test_read_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("not found")
        result = self.cmds.read()
        assert result.success is False
        assert "not available" in result.message.lower()

    def test_execute_copy(self):
        with patch.object(self.cmds, "write") as mock_write:
            mock_write.return_value = MagicMock(success=True, message="ok")
            result = self.cmds.execute("copy hello")
            mock_write.assert_called_once_with("hello")

    def test_execute_paste(self):
        with patch.object(self.cmds, "read") as mock_read:
            mock_read.return_value = MagicMock(success=True, message="ok")
            result = self.cmds.execute("paste")
            mock_read.assert_called_once()
