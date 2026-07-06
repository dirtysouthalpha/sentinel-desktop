"""Scheduled task and timer commands."""
import threading
import time
from core.legacy_engine import CommandResult


class SchedulerCommands:
    """Manage timers, reminders, and scheduled commands."""

    def __init__(self):
        self.timers = {}
        self._counter = 0

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    def timer(self, seconds: int, label: str = "") -> CommandResult:
        """Start a countdown timer."""
        try:
            secs = max(1, int(seconds))
            timer_id = self._next_id()
            name = label or f"Timer #{timer_id}"
            self.timers[timer_id] = {"label": name, "seconds": secs, "active": True}

            def _fire():
                time.sleep(secs)
                if self.timers.get(timer_id, {}).get("active"):
                    self.timers[timer_id]["active"] = False

            t = threading.Thread(target=_fire, daemon=True)
            t.start()
            return CommandResult(True, f"Timer #{timer_id} '{name}' set for {secs}s")
        except ValueError:
            return CommandResult(False, "Invalid timer duration")
        except Exception as e:
            return CommandResult(False, f"Timer failed: {e}")

    def list_timers(self) -> CommandResult:
        """List all active timers."""
        active = {k: v for k, v in self.timers.items() if v.get("active")}
        if not active:
            return CommandResult(True, "No active timers")
        lines = []
        for tid, info in active.items():
            lines.append(f"  #{tid}: {info['label']} ({info['seconds']}s)")
        return CommandResult(True, "Active timers:\n" + "\n".join(lines))

    def cancel_timer(self, timer_id: int) -> CommandResult:
        """Cancel a timer by ID."""
        tid = int(timer_id)
        if tid in self.timers:
            self.timers[tid]["active"] = False
            return CommandResult(True, f"Timer #{tid} cancelled")
        return CommandResult(False, f"Timer #{tid} not found")

    def execute(self, text: str) -> CommandResult:
        """Parse and execute scheduler commands."""
        t = text.lower().strip()
        if t.startswith("timer ") or t.startswith("set timer"):
            import re
            nums = re.findall(r"\d+", text)
            if nums:
                secs = int(nums[0])
                label_match = re.search(r"for (.+)", text, re.IGNORECASE)
                label = label_match.group(1) if label_match else ""
                return self.timer(secs, label)
            return CommandResult(False, "Usage: timer <seconds> [for <label>]")
        if "list timer" in t or "timers" in t:
            return self.list_timers()
        if t.startswith("cancel timer"):
            import re
            nums = re.findall(r"\d+", text)
            if nums:
                return self.cancel_timer(int(nums[0]))
            return CommandResult(False, "Usage: cancel timer <id>")
        return CommandResult(False, f"Unknown scheduler command: {text}")
