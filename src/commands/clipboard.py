"""Clipboard operation commands."""
import subprocess
import platform
from src.core.engine import CommandResult


class ClipboardCommands:
    """Read from and write to the system clipboard."""

    def read(self) -> CommandResult:
        """Read current clipboard content."""
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5
                )
                text = result.stdout.strip()
            else:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, timeout=5
                )
                text = result.stdout.strip()
            if text:
                preview = text[:500]
                if len(text) > 500:
                    preview += f"... ({len(text)} chars total)"
                return CommandResult(True, "Clipboard:\n" + preview)
            return CommandResult(True, "Clipboard is empty")
        except FileNotFoundError:
            return CommandResult(False, "Clipboard tool not available")
        except Exception as e:
            return CommandResult(False, f"Clipboard read failed: {e}")

    def write(self, text: str) -> CommandResult:
        """Write text to the clipboard."""
        if not text:
            return CommandResult(False, "No text provided to copy")
        try:
            is_win = platform.system() == "Windows"
            if is_win:
                subprocess.run(
                    ["powershell", "-command", "Set-Clipboard -Value " + text],
                    capture_output=True, timeout=5
                )
            else:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text, text=True, timeout=5
                )
            return CommandResult(True, f"Copied to clipboard: {text[:50]}")
        except FileNotFoundError:
            return CommandResult(False, "Clipboard tool not available")
        except Exception as e:
            return CommandResult(False, f"Clipboard write failed: {e}")

    def execute(self, text: str) -> CommandResult:
        text_lower = text.lower().strip()
        if text_lower.startswith("copy "):
            return self.write(text[5:].strip())
        if text_lower in ["paste", "clipboard"]:
            return self.read()
        return CommandResult(False, f"Unknown clipboard command: {text}")
