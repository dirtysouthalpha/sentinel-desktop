"""Windows platform backend.

Adapts the existing win32/PIL/pyautogui code into the platform abstraction.
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


# ---------------------------------------------------------------------------
# Window system (wraps core/window_manager.py)
# ---------------------------------------------------------------------------


class _WindowsWindowSystem:
    def __init__(self) -> None:
        self._has_win32 = False
        self._has_pgw = False
        try:
            import win32con  # noqa: F401
            import win32gui  # noqa: F401

            self._has_win32 = True
        except ImportError:
            pass
        try:
            import pygetwindow as pgw  # noqa: F401

            self._has_pgw = True
        except ImportError:
            pass

    def get_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        from core.window_manager import list_windows

        raw = list_windows()
        result = []
        for w in raw:
            if visible_only and not w.get("is_visible", True):
                continue
            result.append(
                WindowInfo(
                    title=w.get("title", ""),
                    x=w.get("x", 0),
                    y=w.get("y", 0),
                    width=w.get("width", 0),
                    height=w.get("height", 0),
                    is_focused=w.get("is_focused", False),
                    handle=w.get("hwnd"),
                )
            )
        return result

    def get_focused_window(self) -> WindowInfo | None:
        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                return self._hwnd_to_info(hwnd)
        except Exception as exc:
            logger.debug("get_focused_window failed: %s", exc)
        # Fallback: find among listed windows
        for w in self.get_windows():
            if w.is_focused:
                return w
        return None

    def find_window(self, title: str) -> WindowInfo | None:
        for w in self.get_windows():
            if title.lower() in w.title.lower():
                return w
        return None

    def focus_window(self, handle: Any) -> bool:
        try:
            import win32gui

            if isinstance(handle, int) and handle > 0:
                win32gui.SetForegroundWindow(handle)
                return True
        except Exception as exc:
            logger.debug("focus_window failed: %s", exc)
        return False

    def close_window(self, handle: Any) -> bool:
        try:
            import win32con
            import win32gui

            if isinstance(handle, int) and handle > 0:
                win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
                return True
        except Exception as exc:
            logger.debug("close_window failed: %s", exc)
        return False

    def move_window(self, handle: Any, x: int, y: int) -> bool:
        try:
            if self._has_pgw:
                import pygetwindow as pgw

                for w in pgw.getAllWindows():
                    if str(handle) in str(w._hWnd) or w.title == str(handle):
                        w.moveTo(x, y)
                        return True
        except Exception as exc:
            logger.debug("move_window failed: %s", exc)
        return False

    def resize_window(self, handle: Any, w: int, h: int) -> bool:
        try:
            if self._has_pgw:
                import pygetwindow as pgw

                for win in pgw.getAllWindows():
                    if str(handle) in str(win._hWnd) or win.title == str(handle):
                        win.resizeTo(w, h)
                        return True
        except Exception as exc:
            logger.debug("resize_window failed: %s", exc)
        return False

    def minimize_window(self, handle: Any) -> bool:
        try:
            if self._has_pgw:
                import pygetwindow as pgw

                for w in pgw.getAllWindows():
                    if str(handle) in str(w._hWnd) or w.title == str(handle):
                        w.minimize()
                        return True
        except Exception as exc:
            logger.debug("minimize_window failed: %s", exc)
        return False

    def maximize_window(self, handle: Any) -> bool:
        try:
            if self._has_pgw:
                import pygetwindow as pgw

                for w in pgw.getAllWindows():
                    if str(handle) in str(w._hWnd) or w.title == str(handle):
                        w.maximize()
                        return True
        except Exception as exc:
            logger.debug("maximize_window failed: %s", exc)
        return False

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _hwnd_to_info(hwnd: int) -> WindowInfo:
        import win32gui

        title = win32gui.GetWindowText(hwnd) or ""
        rect = win32gui.GetWindowRect(hwnd)
        focused = hwnd == win32gui.GetForegroundWindow()
        return WindowInfo(
            title=title,
            x=rect[0],
            y=rect[1],
            width=rect[2] - rect[0],
            height=rect[3] - rect[1],
            is_focused=focused,
            handle=hwnd,
        )


# ---------------------------------------------------------------------------
# Input controller (wraps pyautogui)
# ---------------------------------------------------------------------------


class _WindowsInput:
    def __init__(self) -> None:
        try:
            import pyautogui

            pyautogui.PAUSE = 0.05
            pyautogui.FAILSAFE = True
            self._ok = True
        except ImportError:
            self._ok = False

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        import pyautogui

        pyautogui.click(x, y, button=button, clicks=clicks)

    def double_click(self, x: int, y: int, button: str = "left") -> None:
        import pyautogui

        pyautogui.doubleClick(x, y, button=button)

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
# Screen capture (wraps core/screenshot.py)
# ---------------------------------------------------------------------------


class _WindowsScreen:
    def __init__(self) -> None:
        self._has_mss = False
        try:
            import mss  # noqa: F401

            self._has_mss = True
        except ImportError:
            pass

    def capture(self, region: tuple[int, int, int, int] | None = None) -> Any:
        if self._has_mss:
            import mss
            import mss.tool

            with mss.mss() as sct:
                if region:
                    monitor = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
                else:
                    monitor = sct.monitors[1]  # primary
                raw = sct.grab(monitor)
                from PIL import Image

                return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        # fallback to pyautogui
        import pyautogui

        if region:
            return pyautogui.screenshot(region=region)
        return pyautogui.screenshot()

    def capture_monitor(self, index: int) -> Any:
        if self._has_mss:
            import mss

            with mss.mss() as sct:
                monitor = sct.monitors[index] if index < len(sct.monitors) else sct.monitors[1]
                raw = sct.grab(monitor)
                from PIL import Image

                return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        import pyautogui

        return pyautogui.screenshot()

    def get_monitors(self) -> list[MonitorInfo]:
        result = []
        if self._has_mss:
            import mss

            with mss.mss() as sct:
                for i, m in enumerate(sct.monitors[1:], start=1):  # skip "all"
                    result.append(
                        MonitorInfo(
                            index=i,
                            x=m["left"],
                            y=m["top"],
                            width=m["width"],
                            height=m["height"],
                            is_primary=(i == 1),
                        )
                    )
        if not result:
            import ctypes

            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            result = [MonitorInfo(index=1, x=0, y=0, width=w, height=h, is_primary=True)]
        return result

    def get_primary_size(self) -> tuple[int, int]:
        import ctypes

        try:
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            return w, h
        except Exception:
            return 1920, 1080

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


class _WindowsApplicationManager:
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
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
            return True
        except Exception as exc:
            logger.debug("terminate %d failed: %s", pid, exc)
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


class _WindowsPower:
    def shutdown(self, force: bool = False, delay: int = 0) -> None:
        cmd = ["shutdown", "/s", "/t", str(delay)]
        if force:
            cmd.append("/f")
        subprocess.run(cmd, capture_output=True)

    def restart(self, force: bool = False, delay: int = 0) -> None:
        cmd = ["shutdown", "/r", "/t", str(delay)]
        if force:
            cmd.append("/f")
        subprocess.run(cmd, capture_output=True)

    def lock(self) -> None:
        import ctypes

        ctypes.windll.user32.LockWorkStation()

    def sleep(self) -> None:
        import ctypes

        # SetSuspendState: sleep=False, force=False, disable_wake=False
        try:
            ctypes.windll.PowrProf.SetSuspendState(0, 0, 0)
        except AttributeError:
            # Fallback: Python's SystemStandbyRequirement
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    def hibernate(self) -> None:
        import ctypes

        try:
            ctypes.windll.PowrProf.SetSuspendState(1, 0, 0)
        except AttributeError:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 1,1,0")


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class WindowsBackend(Backend):
    name = "windows"

    def create_window_system(self) -> WindowSystem:
        return _WindowsWindowSystem()

    def create_input(self) -> InputController:
        return _WindowsInput()

    def create_screen(self) -> ScreenCapture:
        return _WindowsScreen()

    def create_application(self) -> ApplicationManager:
        return _WindowsApplicationManager()

    def create_power(self) -> PowerManager:
        return _WindowsPower()
