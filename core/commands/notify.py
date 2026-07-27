"""System notification commands."""
import platform
import subprocess

from core.legacy_engine import CommandResult
from core.powershell import _ps_escape_single_quoted


class NotifyCommands:
    """Send system notifications and alerts."""

    def send(self, title: str, message: str = "") -> CommandResult:
        """Send a system notification."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                # title/message are user/agent supplied. Pre-v31 they were
                # concatenated into a double-quoted PowerShell string, where
                # `"`, `$(...)` and `;` all execute — so a notification title
                # was arbitrary code. Quote them as verbatim single-quoted
                # literals instead.
                try:
                    ps_title = _ps_escape_single_quoted(title)
                    ps_message = _ps_escape_single_quoted(message)
                except (TypeError, ValueError) as exc:
                    return CommandResult(False, f"Unsafe notification text: {exc}")
                ps_cmd = (
                    '[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms"); '
                    "$n=New-Object System.Windows.Forms.NotifyIcon; "
                    f"$n.BalloonTipTitle={ps_title}; "
                    f"$n.BalloonTipText={ps_message}; "
                    "$n.Visible=$true; $n.ShowBalloonTip(5000)"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
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
