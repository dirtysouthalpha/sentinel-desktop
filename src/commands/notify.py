"""System notification commands."""
import subprocess
import platform
from src.core.engine import CommandResult


class NotifyCommands:
    """Send system notifications and alerts."""

    def send(self, title: str, message: str = "") -> CommandResult:
        """Send a system notification."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                ps_cmd = f"[System.Reflection.Assembly]::LoadWithPartialName(\"System.Windows.Forms\"); $n=New-Object System.Windows.Forms.NotifyIcon; $n.BalloonTipTitle=\"" + title + "\"; $n.BalloonTipText=\"" + message + "\"; $n.Visible=$true; $n.ShowBalloonTip(5000)"
                subprocess.Popen(["powershell", "-command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return CommandResult(True, f"Notification sent: {title}")
        except FileNotFoundError:
            return CommandResult(False, "Notification tool not available")
        except Exception as e:
            return CommandResult(False, f"Notification failed: {e}")

    def alert(self, message: str) -> CommandResult:
        """Send an alert notification."""
        return self.send("Sentinel Alert", message)

    def execute(self, text: str) -> CommandResult:
        """Parse and execute notification commands."""
        t = text.lower().strip()
        if t.startswith("notify "):
            parts = text[7:].strip().split(None, 1)
            title = parts[0] if parts else "Notification"
            msg = parts[1] if len(parts) > 1 else ""
            return self.send(title, msg)
        if t.startswith("alert "):
            return self.alert(text[6:].strip())
        if t.startswith("remind "):
            msg = text[7:].strip()
            return self.send("Reminder", msg)
        return CommandResult(False, f"Unknown notification command: {text}")
