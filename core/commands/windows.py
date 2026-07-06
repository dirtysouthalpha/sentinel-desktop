"""Window management commands."""
import subprocess
import platform
from core.legacy_engine import CommandResult


class WindowCommands:
    """List, focus, minimize, and maximize windows."""

    def list_windows(self) -> CommandResult:
        """List all open windows."""
        try:
            is_win = platform.system() == "Windows"
            windows = []

            if is_win:
                result = subprocess.run(
                    ["tasklist", "/v", "/fo", "csv"],
                    capture_output=True, text=True, timeout=5
                )
                raw = result.stdout.strip()
                DQ = chr(34)  # double quote character
                for line in raw.split(chr(10))[1:]:
                    parts = line.split(DQ + "," + DQ)
                    if len(parts) >= 9:
                        title = parts[8].strip().strip(DQ)
                        if title and title != "N/A":
                            windows.append(title)
            else:
                result = subprocess.run(
                    ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.strip().split(chr(10)):
                    if line.strip():
                        parts = line.split(None, 3)
                        if len(parts) >= 4:
                            windows.append(parts[3])

            if windows:
                shown = windows[:20]
                lines_list = []
                for i, w in enumerate(shown):
                    lines_list.append(f"  {i+1}. {w[:60]}")
                msg = f"Open Windows ({len(windows)}):" + chr(10) + chr(10).join(lines_list)
                if len(windows) > 20:
                    msg += f"{chr(10)}... and {len(windows) - 20} more"
                return CommandResult(True, msg, {"count": len(windows)})
            return CommandResult(True, "No open windows detected")
        except FileNotFoundError:
            return CommandResult(False, "Window management tool not available")
        except Exception as e:
            return CommandResult(False, f"Window list failed: {e}")

    def execute(self, text: str) -> CommandResult:
        text_lower = text.lower().strip()
        if "list" in text_lower or text_lower == "windows":
            return self.list_windows()
        return CommandResult(False, f"Unknown window command: {text}")
