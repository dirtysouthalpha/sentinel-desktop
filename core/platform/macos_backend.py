"""macOS platform backend.

Uses pyautogui for input, screencapture/AppKit for screen, osascript
for window management and app lifecycle.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from .base import (
    ApplicationManager,
    Backend,
    InputController,
    MonitorInfo,
    PowerManager,
    ProcessInfo,
    ScreenCapture,
    WindowInfo,
    WindowSystem,
)

logger = logging.getLogger(__name__)


def _osascript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


# ---------------------------------------------------------------------------
# Window system
# ---------------------------------------------------------------------------


class _MacOSWindowSystem:
    def get_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        out = _osascript(
            'tell application "System Events" to get {name, position, size, value of attribute "AXMinimized"} of every window of every process'
        )
        # AppleScript returns: {{name1, {x,y}, {w,h}, false}, {name2, ...}, ...}
        result = []
        if not out:
            return result
        # Parse the AppleScript list output (simplified)
        import re

        window_data = re.findall(
            r"\{([^,]+),\s*\{(\d+),\s*(\d+)\},\s*\{(\d+),\s*(\d+)\},\s*(true|false)\}",
            out,
        )
        for title, x, y, w, h, minimized in window_data:
            title = title.strip(", ")
            is_visible = minimized.strip() == "false"
            if visible_only and not is_visible:
                continue
            result.append(
                WindowInfo(
                    title=title,
                    x=int(x),
                    y=int(y),
                    width=int(w),
                    height=int(h),
                    is_visible=is_visible,
                )
            )
        return result

    def get_focused_window(self) -> WindowInfo | None:
        out = _osascript(
            'tell application "System Events" to get name of first window of (first process whose frontmost is true)'
        )
        if out:
            for w in self.get_windows():
                if w.title == out:
                    return w
            return WindowInfo(title=out, x=0, y=0, width=0, height=0, is_focused=True)
        return None

    def find_window(self, title: str) -> WindowInfo | None:
        for w in self.get_windows():
            if title.lower() in w.title.lower():
                return w
        return None

    def focus_window(self, handle: Any) -> bool:
        if isinstance(handle, str):
            _osascript(f'tell application "{handle}" to activate')
            return True
        return False

    def close_window(self, handle: Any) -> bool:
        title = str(handle)
        _osascript(
            f'tell application "System Events" to tell (first process whose name contains "{title}") to click button 1 of window 1'
        )
        return True

    def move_window(self, handle: Any, x: int, y: int) -> bool:
        title = str(handle)
        _osascript(
            f'tell application "System Events" to tell (first process whose name contains "{title}") to set position of window 1 to {{{x}, {y}}}'
        )
        return True

    def resize_window(self, handle: Any, w: int, h: int) -> bool:
        title = str(handle)
        _osascript(
            f'tell application "System Events" to tell (first process whose name contains "{title}") to set size of window 1 to {{{w}, {h}}}'
        )
        return True

    def minimize_window(self, handle: Any) -> bool:
        title = str(handle)
        _osascript(
            f'tell application "System Events" to tell (first process whose name contains "{title}") to set value of attribute "AXMinimized" of window 1 to true'
        )
        return True

    def maximize_window(self, handle: Any) -> bool:
        title = str(handle)
        _osascript(
            f'tell application "System Events" to tell (first process whose name contains "{title}") to set value of attribute "AXMinimized" of window 1 to false'
        )
        return True


# ---------------------------------------------------------------------------
# Input controller
# ---------------------------------------------------------------------------


class _MacOSInput:
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        import pyautogui

        pyautogui.click(x, y, button=button, clicks=clicks)

    def double_click(self, x: int, y: int, button: str = "left") -> None:
        self.click(x, y, button=button, clicks=2)

    def move_to(self, x: int, y: int) -> None:
        import pyautogui

        pyautogui.moveTo(x, y)

    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
        import pyautogui

        pyautogui.moveTo(x1, y1)
        pyautogui.drag(x2 - x1, y2 - y1, button=button, duration=0.3)

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None:
        import pyautogui

        pyautogui.scroll(clicks, x=x, y=y)

    def key_press(self, key: str) -> None:
        import pyautogui

        pyautogui.press(key)

    def key_down(self, key: str) -> None:
        import pyautogui

        pyautogui.keyDown(key)

    def key_up(self, key: str) -> None:
        import pyautogui

        pyautogui.keyUp(key)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        import pyautogui

        pyautogui.typewrite(text, interval=interval)

    def hotkey(self, *keys: str) -> None:
        import pyautogui

        pyautogui.hotkey(*keys)


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------


class _MacOSScreen:
    def capture(self, region: tuple[int, int, int, int] | None = None) -> Any:
        import tempfile

        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        if region:
            subprocess.run(
                ["screencapture", "-R", f"{region[0]},{region[1]},{region[2]},{region[3]}", path], capture_output=True
            )
        else:
            subprocess.run(["screencapture", path], capture_output=True)
        try:
            img = Image.open(path)
            os.unlink(path)
            return img
        except Exception:
            return Image.new("RGB", (1920, 1080), (0, 0, 0))

    def capture_monitor(self, index: int) -> Any:
        return self.capture()

    def get_monitors(self) -> list[MonitorInfo]:
        try:
            import subprocess

            out = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True).stdout
            result = []
            idx = 0
            for line in out.splitlines():
                if "Resolution" in line:
                    import re

                    match = re.search(r"(\d+)\s*x\s*(\d+)", line)
                    if match:
                        idx += 1
                        result.append(
                            MonitorInfo(
                                index=idx,
                                x=0,
                                y=0,
                                width=int(match.group(1)),
                                height=int(match.group(2)),
                                is_primary=(idx == 1),
                            )
                        )
            return result or [MonitorInfo(index=1, x=0, y=0, width=2560, height=1440, is_primary=True)]
        except Exception:
            return [MonitorInfo(index=1, x=0, y=0, width=2560, height=1440, is_primary=True)]

    def get_primary_size(self) -> tuple[int, int]:
        m = self.get_monitors()
        primary = next((x for x in m if x.is_primary), m[0] if m else None)
        if primary:
            return primary.width, primary.height
        return 2560, 1440

    def capture_base64(self, region: tuple[int, int, int, int] | None = None, fmt: str = "PNG") -> str:
        import base64
        import io

        img = self.capture(region)
        if img is None:
            return ""
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Application manager
# ---------------------------------------------------------------------------


class _MacOSApplicationManager:
    def launch(self, command: str | list[str], **kwargs: Any) -> int | None:
        if isinstance(command, str):
            script = f'do shell script "{command} > /dev/null 2>&1 &"'
            _osascript(script)
        else:
            cmd_str = " ".join(command)
            _osascript(f'do shell script "{cmd_str} > /dev/null 2>&1 &"')
        # macOS doesn't give us PID easily; return 0 as sentinel
        return 0

    def terminate(self, pid: int) -> bool:
        try:
            os.kill(pid, 9)
            return True
        except OSError:
            return False

    def find_processes(self, name: str) -> list[ProcessInfo]:
        return [p for p in self.list_processes() if name.lower() in p.name.lower()]

    def list_processes(self) -> list[ProcessInfo]:
        result = []
        try:
            import psutil

            for p in psutil.process_iter(["pid", "name", "exe", "cpu_percent", "memory_info"]):
                try:
                    info = p.info
                    result.append(
                        ProcessInfo(
                            pid=info["pid"] or 0,
                            name=info.get("name", ""),
                            executable=info.get("exe", "") or "",
                            cpu_percent=info.get("cpu_percent", 0.0) or 0.0,
                            memory_mb=(info.get("memory_info").rss / 1024 / 1024) if info.get("memory_info") else 0.0,
                        )
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            pass
        return result

    def is_running(self, name: str) -> bool:
        return any(name.lower() in p.name.lower() for p in self.list_processes())


# ---------------------------------------------------------------------------
# Power management
# ---------------------------------------------------------------------------


class _MacOSPower:
    def shutdown(self, force: bool = False, delay: int = 0) -> None:
        import subprocess

        if delay:
            subprocess.run(["sudo", "shutdown", "-h", f"+{delay}"], capture_output=True)
        else:
            _osascript('tell application "System Events" to shut down')

    def restart(self, force: bool = False, delay: int = 0) -> None:
        import subprocess

        if delay:
            subprocess.run(["sudo", "shutdown", "-r", f"+{delay}"], capture_output=True)
        else:
            _osascript('tell application "System Events" to restart')

    def lock(self) -> None:
        import subprocess

        subprocess.run(
            ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
            capture_output=True,
        )

    def sleep(self) -> None:
        import subprocess

        subprocess.run(["pmset", "sleepnow"], capture_output=True)

    def hibernate(self) -> None:
        # macOS hibernate is configured via pmset
        import subprocess

        subprocess.run(["pmset", "hibernatemode", "25"], capture_output=True)
        subprocess.run(["pmset", "sleepnow"], capture_output=True)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class MacOSBackend(Backend):
    name = "macos"

    def create_window_system(self) -> WindowSystem:
        return _MacOSWindowSystem()

    def create_input(self) -> InputController:
        return _MacOSInput()

    def create_screen(self) -> ScreenCapture:
        return _MacOSScreen()

    def create_application(self) -> ApplicationManager:
        return _MacOSApplicationManager()

    def create_power(self) -> PowerManager:
        return _MacOSPower()
