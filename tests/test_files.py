"""Tests for file operation commands."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.files import FileCommands


class TestFileCommands:
    def setup_method(self):
        self.cmds = FileCommands()

    def test_list_files(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()
        result = self.cmds.list_files(str(tmp_path))
        assert result.success is True
        assert "test.txt" in result.message

    def test_read_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")
        result = self.cmds.read_file(str(test_file))
        assert result.success is True
        assert "Hello World" in result.message

    def test_read_nonexistent(self):
        result = self.cmds.read_file("/nonexistent/path/file.txt")
        assert result.success is False
