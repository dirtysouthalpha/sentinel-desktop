"""Tests for system diagnostic commands."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.system import SystemCommands


class TestSystemCommands:
    def setup_method(self):
        self.cmds = SystemCommands()

    def test_cpu_usage(self):
        result = self.cmds.cpu_usage()
        assert result.success is True
        assert "CPU" in result.message

    def test_memory_usage(self):
        result = self.cmds.memory_usage()
        assert result.success is True
        assert "Memory" in result.message

    def test_disk_usage(self):
        result = self.cmds.disk_usage()
        assert result.success is True
        assert "Disk" in result.message

    def test_list_processes(self):
        result = self.cmds.list_processes(limit=5)
        assert result.success is True
        assert "Process" in result.message

    def test_system_info(self):
        result = self.cmds.system_info()
        assert result.success is True
        assert "OS" in result.message

    def test_uptime(self):
        result = self.cmds.uptime()
        assert result.success is True
        assert "Uptime" in result.message
