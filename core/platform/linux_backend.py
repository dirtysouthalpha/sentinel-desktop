"""Linux platform backend (X11/Wayland).

Uses xdotool, wmctrl, xdotool, scrot/import, and pyautogui where available.
Falls back gracefully when running headless.
"""

from __future__ import annotations

import logging
import os
import shutil
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


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run a command and return stdout; returns '' on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _which(name: str) -> str | None:
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Window system
# ---------------------------------------------------------------------------

class _LinuxWindowSystem:
    def __init__(self) -> None:
        self._has_xlib = False
        try:
            import Xlib.display  # noqa: F401
            self._has_xlib = True
        except ImportError:
            pass
        self._has_wmctrl = bool(_which("wmctrl"))
        self._has_xdotool = bool(_which("xdotool"))

    def get_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        if self._has_xlib:
            return self._get_windows_xlib(visible_only)
        if self._has_wmctrl:
            return self._get_windows_wmctrl(visible_only)
        return []

    def _get_windows_xlib(self, visible_only: bool) -> list[WindowInfo]:
        try:
            from Xlib import X, display, Xatom
            d = display.Display()
            root = d.screen().root
            windows = []

            def _walk(window):
                try:
                    attrs = window.get_attributes()
                    if visible_only and attrs.map_state != X.IsViewable:
                        return
                    title = ""
                    try:
                        wmname = window.get_full_property(Xatom.WM_NAME, 0)
                        if wmname:
                            title = wmname.value.decode("utf-8", errors="replace") if isinstance(wmname.value, bytes) else str(wmname.value)
                    except Exception:
                        pass
                    if title:
                        geom = window.get_geometry()
                        # translate to root coordinates
                        coords = window.translate_coords(root, 0, 0)
                        windows.append(WindowInfo(
                            title=title,
                            x=-coords.x,
                            y=-coords.y,
                            width=geom.width,
                            height=geom.height,
                        ))
                    for child in window.query_tree().children:
                        _walk(child)
                except Exception:
                    pass

            _walk(root)
            d.close()
            return windows
        except Exception as exc:
            logger.debug("Xlib get_windows failed: %s", exc)
            return []

    def _get_windows_wmctrl(self, visible_only: bool) -> list[WindowInfo]:
        out = _run(["wmctrl", "-l", "-G"])
        if not out:
            return []
        result = []
        for line in out.strip().splitlines():
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            # <id> <desktop> <x> <y> <w> <h> <host> <title...>
            try:
                x, y, w, h = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
            except (ValueError, IndexError):
                continue
            result.append(WindowInfo(title=parts[8], x=x, y=y, width=w, height=h, handle=parts[0]))
        return result

    def get_focused_window(self) -> WindowInfo | None:
        if self._has_xdotool:
            out = _run(["xdotool", "getactivewindow", "getwindowname"])
            if out.strip():
                title = out.strip()
                for w in self.get_windows():
                    if w.title == title:
                        return w
                return WindowInfo(title=title, x=0, y=0, width=0, height=0, is_focused=True)
        return None

    def find_window(self, title: str) -> WindowInfo | None:
        for w in self.get_windows():
            if title.lower() in w.title.lower():
                return w
        return None

    def focus_window(self, handle: Any) -> bool:
        if self._has_xdotool:
            out = _run(["xdotool", "search", "--name", str(handle), "windowactivate", "--sync"])
            return bool(out)
        return False

    def close_window(self, handle: Any) -> bool:
        if self._has_xdotool:
            _run(["xdotool", "search", "--name", str(handle), "windowclose"])
            return True
        return False

    def move_window(self, handle: Any, x: int, y: int) -> bool:
        if self._has_xdotool:
            _run(["xdotool", "search", "--name", str(handle), "windowmove", str(x), str(y)])
            return True
        return False

    def resize_window(self, handle: Any, w: int, h: int) -> bool:
        if self._has_xdotool:
            _run(["xdotool", "search", "--name", str(handle), "windowsize", str(w), str(h)])
            return True
        return False

    def minimize_window(self, handle: Any) -> bool:
        if self._has_xdotool:
            _run(["xdotool", "search", "--name", str(handle), "windowminimize"])
            return True
        return False

    def maximize_window(self, handle: Any) -> bool:
        if self._has_xdotool:
            _run(["xdotool", "search", "--name", str(handle), "windowactivate", "--sync", "windowsize", "100%", "100%"])
            return True
        return False


# ---------------------------------------------------------------------------
# Input controller
# ---------------------------------------------------------------------------

class _LinuxInput:
    def __init__(self) -> None:
        self._has_xdotool = bool(_which("xdotool"))
        self._has_pyautogui = False
        try:
            import pyautogui  # noqa: F401
            self._has_pyautogui = True
        except ImportError:
            pass

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        if self._has_xdotool:
            btn_map = {"left": 1, "middle": 2, "right": 3}
            btn = btn_map.get(button, 1)
            _run(["xdotool", "mousemove", str(x), str(y), "click", "--repeat", str(clicks), str(btn)])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.click(x, y, button=button, clicks=clicks)

    def double_click(self, x: int, y: int, button: str = "left") -> None:
        self.click(x, y, button=button, clicks=2)

    def move_to(self, x: int, y: int) -> None:
        if self._has_xdotool:
            _run(["xdotool", "mousemove", str(x), str(y)])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.moveTo(x, y)

    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
        if self._has_xdotool:
            btn_map = {"left": 1, "middle": 2, "right": 3}
            btn = btn_map.get(button, 1)
            _run(["xdotool", "mousemove", str(x1), str(y1), "mousedown", str(btn), "mousemove", str(x2), str(y2), "mouseup", str(btn)])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.moveTo(x1, y1)
            pyautogui.drag(x2 - x1, y2 - y1, button=button, duration=0.3)

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None:
        if self._has_xdotool:
            btn = 4 if clicks > 0 else 5
            for _ in range(abs(clicks)):
                _run(["xdotool", "click", str(btn)])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.scroll(clicks, x=x, y=y)

    def key_press(self, key: str) -> None:
        if self._has_xdotool:
            _run(["xdotool", "key", key])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.press(key)

    def key_down(self, key: str) -> None:
        if self._has_xdotool:
            _run(["xdotool", "keydown", key])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.keyDown(key)

    def key_up(self, key: str) -> None:
        if self._has_xdotool:
            _run(["xdotool", "keyup", key])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.keyUp(key)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        if self._has_xdotool:
            _run(["xdotool", "type", "--delay", str(int(interval * 1000)), text])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.typewrite(text, interval=interval)

    def hotkey(self, *keys: str) -> None:
        if self._has_xdotool:
            _run(["xdotool", "key", "+".join(keys)])
        elif self._has_pyautogui:
            import pyautogui
            pyautogui.hotkey(*keys)


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

class _LinuxScreen:
    def __init__(self) -> None:
        self._has_scrot = _which("scrot") is not None
        self._has_import = _which("import") is not None  # ImageMagick
        self._has_mss = False
        try:
            import mss  # noqa: F401
            self._has_mss = True
        except ImportError:
            pass

    def capture(self, region: tuple[int, int, int, int] | None = None) -> Any:
        from PIL import Image
        if self._has_mss:
            import mss
            with mss.mss() as sct:
                if region:
                    monitor = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
                else:
                    monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        # Fallback: scrot or import
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            if self._has_scrot:
                if region:
                    _run(["scrot", "-a", f"{region[0]},{region[1]},{region[2]},{region[3]}", path])
                else:
                    _run(["scrot", path])
            elif self._has_import:
                if region:
                    _run(["import", "-window", "root", "-crop", f"{region[2]}x{region[3]}+{region[0]}+{region[1]}", path])
                else:
                    _run(["import", "-window", "root", path])
            return Image.open(path)
        except Exception:
            return Image.new("RGB", (1920, 1080), (0, 0, 0))

    def capture_monitor(self, index: int) -> Any:
        return self.capture()  # linux typically has one logical display via X11

    def get_monitors(self) -> list[MonitorInfo]:
        out = _run(["xrandr", "--listmonitors"])
        if not out:
            return [MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, is_primary=True)]
        result = []
        for line in out.strip().splitlines()[1:]:  # skip "Monitors: N"
            parts = line.split()
            if len(parts) >= 4:
                try:
                    res = parts[-1] if "+" in parts[-1] else ""
                    if not res and len(parts) >= 3:
                        res = parts[2]
                    if "+" in res:
                        size, pos = res.split("+", 1)
                        w_h = size.split("/")[0].split("x")
                        w, h = int(w_h[0]), int(w_h[1])
                        x, y = int(pos.split("+")[0]), int(pos.split("+")[1])
                        is_primary = "*" in line
                        result.append(MonitorInfo(index=len(result)+1, x=x, y=y, width=w, height=h, is_primary=is_primary))
                except (ValueError, IndexError):
                    pass
        return result or [MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, is_primary=True)]

    def get_primary_size(self) -> tuple[int, int]:
        out = _run(["xrandr", "--current"])
        for line in out.splitlines():
            if "*" in line or "primary" in line:
                parts = line.split()
                for p in parts:
                    if "x" in p and p[0].isdigit():
                        try:
                            w, h = p.split("x")
                            return int(w), int(h.split("+")[0].split("/")[0])
                        except ValueError:
                            pass
        return 1920, 1080

    def capture_base64(self, region: tuple[int, int, int, int] | None = None, fmt: str = "PNG") -> str:
        import base64
        import io
        from PIL import Image
        img = self.capture(region)
        if img is None:
            return ""
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Application manager
# ---------------------------------------------------------------------------

class _LinuxApplicationManager:
    def launch(self, command: str | list[str], **kwargs: Any) -> int | None:
        try:
            if isinstance(command, list):
                proc = subprocess.Popen(command, **kwargs)
            else:
                proc = subprocess.Popen(command, shell=True, **kwargs)
            return proc.pid
        except Exception as exc:
            logger.warning("launch %r failed: %s", command, exc)
            return None

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
                    result.append(ProcessInfo(
                        pid=info["pid"] or 0,
                        name=info.get("name", ""),
                        executable=info.get("exe", "") or "",
                        cpu_percent=info.get("cpu_percent", 0.0) or 0.0,
                        memory_mb=(info.get("memory_info").rss / 1024 / 1024) if info.get("memory_info") else 0.0,
                    ))
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

class _LinuxPower:
    def shutdown(self, force: bool = False, delay: int = 0) -> None:
        cmd = ["shutdown", "-h", f"+{delay}" if delay else "now"]
        if force:
            cmd.insert(1, "-f")
        subprocess.run(cmd, capture_output=True)

    def restart(self, force: bool = False, delay: int = 0) -> None:
        cmd = ["shutdown", "-r", f"+{delay}" if delay else "now"]
        if force:
            cmd.insert(1, "-f")
        subprocess.run(cmd, capture_output=True)

    def lock(self) -> None:
        # Try common Linux screen lockers
        for locker in ("gnome-screensaver-command -l", "xscreensaver-command -lock", "loginctl lock-session", "dm-tool lock"):
            if _run(locker.split()).strip() is not None:
                return

    def sleep(self) -> None:
        subprocess.run(["systemctl", "suspend"], capture_output=True)

    def hibernate(self) -> None:
        subprocess.run(["systemctl", "hibernate"], capture_output=True)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class LinuxBackend(Backend):
    name = "linux"

    def create_window_system(self) -> WindowSystem:
        return _LinuxWindowSystem()

    def create_input(self) -> InputController:
        return _LinuxInput()

    def create_screen(self) -> ScreenCapture:
        return _LinuxScreen()

    def create_application(self) -> ApplicationManager:
        return _LinuxApplicationManager()

    def create_power(self) -> PowerManager:
        return _LinuxPower()
