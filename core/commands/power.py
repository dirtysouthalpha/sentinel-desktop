"""Power management commands."""
import subprocess
import platform
import time
from core.legacy_engine import CommandResult


class PowerCommands:
    """Shutdown, restart, sleep, lock, hibernate."""

    def shutdown(self, delay: int = 0) -> CommandResult:
        """Shutdown the system."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                secs = max(0, delay)
                subprocess.Popen(["shutdown", "/s", "/t", str(secs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = f"Shutting down in {secs}s..." if secs > 0 else "Shutting down..."
            else:
                subprocess.Popen(["shutdown", "-h", "now"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = "Shutting down..."
            return CommandResult(True, msg)
        except Exception as e:
            return CommandResult(False, f"Shutdown failed: {e}")

    def restart(self, delay: int = 0) -> CommandResult:
        """Restart the system."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                secs = max(0, delay)
                subprocess.Popen(["shutdown", "/r", "/t", str(secs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = f"Restarting in {secs}s..." if secs > 0 else "Restarting..."
            else:
                subprocess.Popen(["reboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = "Restarting..."
            return CommandResult(True, msg)
        except Exception as e:
            return CommandResult(False, f"Restart failed: {e}")

    def sleep(self) -> CommandResult:
        """Put the system to sleep."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["systemctl", "suspend"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return CommandResult(True, "System going to sleep...")
        except Exception as e:
            return CommandResult(False, f"Sleep failed: {e}")

    def lock(self) -> CommandResult:
        """Lock the screen."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["loginctl", "lock-session"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return CommandResult(True, "Screen locked")
        except Exception as e:
            return CommandResult(False, f"Lock failed: {e}")

    def cancel(self) -> CommandResult:
        """Cancel a pending shutdown/restart."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                subprocess.Popen(["shutdown", "/a"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["shutdown", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return CommandResult(True, "Pending shutdown cancelled")
        except Exception as e:
            return CommandResult(False, f"Cancel failed: {e}")

    def execute(self, text: str) -> CommandResult:
        """Parse and execute power commands."""
        t = text.lower().strip()
        if "cancel" in t:
            return self.cancel()
        if "lock" in t:
            return self.lock()
        if "sleep" in t or "suspend" in t:
            return self.sleep()
        if "restart" in t or "reboot" in t:
            import re
            m = re.search(r"(\d+)", t)
            delay = int(m.group(1)) if m else 0
            return self.restart(delay)
        if "shutdown" in t or "power off" in t or "turn off" in t:
            import re
            m = re.search(r"(\d+)", t)
            delay = int(m.group(1)) if m else 0
            return self.shutdown(delay)
        return CommandResult(False, f"Unknown power command: {text}")
