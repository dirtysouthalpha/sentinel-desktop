"""Tests for the command engine and routing."""
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.engine import CommandEngine, CommandResult


class TestCommandResult:
    def test_success_result(self):
        r = CommandResult(True, "OK")
        assert r.success is True
        assert r.message == "OK"

    def test_failure_result(self):
        r = CommandResult(False, "Failed")
        assert r.success is False
        assert r.message == "Failed"

    def test_str(self):
        r = CommandResult(True, "Hello")
        assert str(r) == "Hello"


class TestCommandParsing:
    def setup_method(self):
        self.engine = CommandEngine()

    def test_parse_cpu(self):
        result = self.engine.parse_command("check cpu")
        assert result is not None
        assert result[0] == "system"
        assert result[1] == "cpu"

    def test_parse_memory(self):
        result = self.engine.parse_command("memory usage")
        assert result is not None
        assert result[0] == "system"

    def test_parse_click(self):
        result = self.engine.parse_command("click 500,300")
        assert result is not None
        assert result[0] == "automation"

    def test_parse_type(self):
        result = self.engine.parse_command("type hello world")
        assert result is not None
        assert result[0] == "automation"

    def test_parse_ping(self):
        result = self.engine.parse_command("ping google.com")
        assert result is not None
        assert result[0] == "network"

    def test_parse_unknown(self):
        result = self.engine.parse_command("xyzzy random text")
        assert result is None

    def test_parse_screenshot(self):
        result = self.engine.parse_command("take a screenshot")
        assert result is not None
        assert result[0] == "automation"

    def test_parse_disk(self):
        result = self.engine.parse_command("disk usage")
        assert result is not None
        assert result[0] == "system"
        assert result[1] == "disk"

    def test_parse_battery(self):
        result = self.engine.parse_command("battery status")
        assert result is not None
        assert result[0] == "system"

    def test_parse_kill(self):
        result = self.engine.parse_command("kill chrome")
        assert result is not None
        assert result[0] == "process"
