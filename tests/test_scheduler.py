import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.scheduler import SchedulerCommands


class TestSchedulerCommands:
    def setup_method(self):
        self.cmds = SchedulerCommands()

    def test_timer(self):
        result = self.cmds.timer(5, "Test")
        assert result.success is True
        assert "5s" in result.message

    def test_timer_no_label(self):
        result = self.cmds.timer(3)
        assert result.success is True
        assert "Timer" in result.message

    def test_timer_invalid(self):
        result = self.cmds.timer(-5)
        assert result.success is True
        assert "1s" in result.message

    def test_list_timers_empty(self):
        result = self.cmds.list_timers()
        assert result.success is True
        assert "No active" in result.message

    def test_list_timers_active(self):
        self.cmds.timer(60, "Active")
        result = self.cmds.list_timers()
        assert result.success is True
        assert "Active" in result.message

    def test_cancel_timer(self):
        r = self.cmds.timer(60, "ToCancel")
        timer_id = 1
        result = self.cmds.cancel_timer(timer_id)
        assert result.success is True
        assert "cancelled" in result.message.lower()

    def test_cancel_not_found(self):
        result = self.cmds.cancel_timer(999)
        assert result.success is False

    def test_execute_timer(self):
        result = self.cmds.execute("timer 10 for coffee")
        assert result.success is True
        assert "10s" in result.message

    def test_execute_list(self):
        result = self.cmds.execute("list timers")
        assert result.success is True

    def test_execute_cancel(self):
        self.cmds.timer(60)
        result = self.cmds.execute("cancel timer 1")
        assert result.success is True

    def test_execute_unknown(self):
        result = self.cmds.execute("fly away")
        assert result.success is False
