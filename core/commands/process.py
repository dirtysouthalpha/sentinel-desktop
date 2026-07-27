"""
Process Management Commands
Open/close applications, manage running processes.
"""
import os
import platform
import subprocess

from core.legacy_engine import CommandResult

try:
    import psutil
except Exception:
    psutil = None


class ProcessCommands:
    """Application and process management."""

    def open_application(self, name: str) -> CommandResult:
        if not name:
            return CommandResult(False, "Usage: open <application_name>")

        is_win = platform.system() == "Windows"
        try:
            if is_win:
                os.startfile(name)  # pylint: disable=no-member
            else:
                subprocess.Popen([name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return CommandResult(True, f"Opening: {name}")
        except Exception:
            # Fallback: try subprocess.
            # On Windows, shell=True with a list flattens the list into a
            # single cmd.exe command line, so `name` reached the shell as code
            # (`open "foo & calc"` ran calc). Pass the name as an argument to
            # cmd.exe's own `start` instead, and reject shell metacharacters.
            try:
                if is_win:
                    if any(c in name for c in '&|<>^"\r\n\x00'):
                        return CommandResult(False, f"Unsafe application name: {name!r}")
                    subprocess.Popen(
                        ["cmd.exe", "/c", "start", "", name],
                        shell=False,
                    )
                else:
                    subprocess.Popen([name])
                return CommandResult(True, f"Opening: {name}")
            except Exception as e2:
                return CommandResult(False, f"Could not open '{name}': {e2}")

    def kill_process(self, name: str) -> CommandResult:
        if not name:
            return CommandResult(False, "Usage: close <process_name>")
        if not psutil:
            return CommandResult(False, "psutil not available")

        killed = []
        name_lower = name.lower()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if name_lower in proc.info["name"].lower():
                    proc.kill()
                    killed.append(f"{proc.info['pid']}: {proc.info['name']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed:
            return CommandResult(True, f"Terminated {len(killed)} process(es):\n" + "\n".join(killed))
        return CommandResult(False, f"No process matching '{name}' found")
