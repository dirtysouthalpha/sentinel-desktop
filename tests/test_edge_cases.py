"""Edge case and integration tests to harden the engine."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.engine import CommandEngine, CommandResult


class TestEdgeCases:
    """Test edge cases that could crash the engine."""

    def setup_method(self):
        self.engine = CommandEngine()

    def test_empty_string(self):
        result = self.engine.parse_command("")
        assert result is None

    def test_whitespace_only(self):
        result = self.engine.parse_command("   ")
        assert result is None

    def test_very_long_input(self):
        long_text = "cpu " + "x" * 5000
        result = self.engine.parse_command(long_text)
        assert result is not None
        assert result[0] == "system"

    def test_special_chars(self):
        result = self.engine.parse_command("cpu !!! @@@ ###")
        assert result is not None
        assert result[0] == "system"

    def test_newlines_in_input(self):
        result = self.engine.parse_command("cpu\nsystem info")
        assert result is not None

    def test_numbers_only(self):
        result = self.engine.parse_command("12345")
        assert result is None

    def test_unicode_input(self):
        result = self.engine.parse_command("cafe n e u")
        assert result is None

    def test_mixed_case(self):
        result = self.engine.parse_command("CPU")
        assert result is not None
        assert result[0] == "system"

    def test_mixed_case_lower(self):
        result = self.engine.parse_command("CpU")
        assert result is not None
        assert result[0] == "system"

    def test_tab_separated(self):
        result = self.engine.parse_command("cpu\tsystem")
        assert result is not None

    def test_execute_empty_string(self):
        result = self.engine.execute("")
        assert result.success is True  # Now returns friendly fallback

    def test_execute_unknown_garbage(self):
        result = self.engine.execute("xyzzy abc123")
        assert result.success is True  # Now returns friendly suggestion
        assert "help" in result.message.lower()

    def test_command_result_str(self):
        cr = CommandResult(True, "test message")
        assert str(cr) == "test message"

    def test_command_result_data(self):
        cr = CommandResult(True, "msg", {"key": "value"})
        assert cr.data == {"key": "value"}

    def test_command_result_empty_data(self):
        cr = CommandResult(True, "msg")
        assert cr.data == {}


class TestEngineIntegration:
    """Integration tests that exercise multiple modules through the engine."""

    def setup_method(self):
        self.engine = CommandEngine()

    def test_full_system_flow(self):
        with patch.object(self.engine.sys, "cpu_usage") as mock_cpu:
            mock_cpu.return_value = CommandResult(True, "CPU: 50%")
            result = self.engine.execute("cpu")
            assert result.success is True

    @patch("src.commands.clipboard.subprocess")
    def test_full_clipboard_flow(self, mock_subproc):
        mock_subproc.run.return_value = MagicMock(returncode=0, stdout=b"hello")
        result = self.engine.execute("copy hello world")
        assert result.success is True

    def test_full_help_flow(self):
        result = self.engine.execute("help")
        assert result.success is True

    def test_full_media_flow(self):
        with patch.object(self.engine.media, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("volume up")
            assert result.success is True

    def test_full_macros_flow(self):
        with patch.object(self.engine.macros, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("start recording")
            assert result.success is True

    def test_full_plugins_flow(self):
        with patch.object(self.engine.plugins, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("list plugins")
            assert result.success is True

    def test_full_power_flow(self):
        with patch.object(self.engine.power, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("lock screen")
            assert result.success is True

    def test_full_notify_flow(self):
        with patch.object(self.engine.notify, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("notify hello")
            assert result.success is True

    def test_full_scheduler_flow(self):
        with patch.object(self.engine.scheduler, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("timer 5")
            assert result.success is True

    def test_full_voice_flow(self):
        with patch.object(self.engine.voice, "execute") as mock_exec:
            mock_exec.return_value = CommandResult(True, "ok")
            result = self.engine.execute("speak hello")
            assert result.success is True
