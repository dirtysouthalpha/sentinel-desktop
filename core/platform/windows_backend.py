"""Sentinel Desktop v4.0 — Windows Platform Backend.

Wraps the existing Windows-specific code (UIA, PostMessage, DPAPI, PowerShell,
win32gui) behind the platform abstraction interfaces. This is the reference
implementation — the one that has the most features.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
from typing import Any

from core.platform import PlatformBackend
from core.platform.base import (
    AccessibilityBackend,
    CredentialBackend,
    OverlayBackend,
    ShellBackend,
    StealthInputBackend,
    UIElement,
    WindowBackend,
    WindowInfo,
)

logger = logging.getLogger(__name__)

# ── Availability probes (run once) ──────────────────────────────────────

_HAS_UIA: bool | None = None
_uia_auto = None


def _probe_uia() -> bool:
    """Check if uiautomation package is available."""
    global _HAS_UIA, _uia_auto
    if _HAS_UIA is not None:
        return _HAS_UIA
    try:
        import uiautomation as auto  # type: ignore

        _uia_auto = auto
        _HAS_UIA = True
    except (ImportError, ModuleNotFoundError, OSError):
        _HAS_UIA = False
    return _HAS_UIA


_HAS_WIN32: bool | None = None
_win32gui: Any = None
_win32api: Any = None
_win32con: Any = None


def _probe_win32() -> bool:
    """Check if win32gui/win32api/win32con are available."""
    global _HAS_WIN32, _win32gui, _win32api, _win32con
    if _HAS_WIN32 is not None:
        return _HAS_WIN32
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore

        _win32gui = win32gui
        _win32api = win32api
        _win32con = win32con
        _HAS_WIN32 = True
    except ImportError:
        _HAS_WIN32 = False
    return _HAS_WIN32


def _probe_powershell() -> bool:
    """Check if PowerShell is available on this system."""
    try:
        result = subprocess.run(
            ["powershell", "-Command", "echo ok"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ── DPAPI ctypes (lazy) ─────────────────────────────────────────────────

_dpapi_ready = False
_CryptProtectData: Any = None
_CryptUnprotectData: Any = None
_DPAPI_OK = False


def _init_dpapi() -> None:
    """Initialize DPAPI ctypes bindings (called once, lazily)."""
    global _dpapi_ready, _CryptProtectData, _CryptUnprotectData, _DPAPI_OK
    if _dpapi_ready:
        return
    _dpapi_ready = True
    try:
        from ctypes import POINTER, Structure, c_byte, c_uint, c_void_p, c_wchar_p

        class _DATA_BLOB(Structure):
            _fields_ = [("cbData", c_uint), ("pbData", POINTER(c_byte))]

        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]

        _CryptProtectData = crypt32.CryptProtectData
        _CryptProtectData.argtypes = [
            POINTER(_DATA_BLOB),
            c_wchar_p,
            POINTER(_DATA_BLOB),
            c_void_p,
            c_void_p,
            c_uint,
            POINTER(_DATA_BLOB),
        ]
        _CryptProtectData.restype = c_uint

        _CryptUnprotectData = crypt32.CryptUnprotectData
        _CryptUnprotectData.argtypes = [
            POINTER(_DATA_BLOB),
            POINTER(c_wchar_p),
            POINTER(_DATA_BLOB),
            c_void_p,
            c_void_p,
            c_uint,
            POINTER(_DATA_BLOB),
        ]
        _CryptUnprotectData.restype = c_uint
        _DPAPI_OK = True
    except (OSError, AttributeError):
        logger.debug("DPAPI initialization failed")


# ---------------------------------------------------------------------------
# Windows Accessibility Backend
# ---------------------------------------------------------------------------


class WindowsAccessibility(AccessibilityBackend):
    """UIAutomation-based accessibility tree for Windows."""

    def __init__(self) -> None:
        self._available = _probe_uia()

    def is_available(self) -> bool:
        return self._available

    def get_tree(self, window_title: str | None = None) -> list[UIElement]:
        """Walk the UIAutomation tree and return flattened elements."""
        if not self._available or _uia_auto is None:
            return []
        try:
            root = self._get_root(window_title)
            if root is None:
                return []
            elements: list[UIElement] = []
            self._walk_tree(root, elements, depth=0, max_depth=10)
            return elements
        except (OSError, RuntimeError) as exc:
            logger.debug("get_tree failed: %s", exc)
            return []

    def find_element(
        self,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> UIElement | None:
        """Find a single UI element by attributes."""
        if not self._available or _uia_auto is None:
            return None
        try:
            root = self._get_root(window_title)
            if root is None:
                return None
            # Build search parameters
            kwargs: dict[str, Any] = {}
            if name:
                kwargs["Name"] = name
            if automation_id:
                kwargs["AutomationId"] = automation_id

            # Map our control_type string to UIA control type
            if control_type and _uia_auto is not None:
                uia_type = getattr(_uia_auto, f"{control_type}Control", None)
                if uia_type is not None:
                    kwargs["ControlType"] = uia_type

            found = root.FindControl(**kwargs, searchDepth=15) if kwargs else None
            if found:
                return self._uia_to_element(found)
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.debug("find_element failed: %s", exc)
        return None

    def invoke_element(self, element: UIElement) -> bool:
        """Invoke a UI element via its InvokePattern."""
        if not self._available or element.raw is None:
            return False
        try:
            raw = element.raw.get("_uia_ref")
            if raw is None:
                return False
            pattern = raw.GetInvokePattern()
            if pattern:
                pattern.Invoke()
                return True
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.debug("invoke_element failed: %s", exc)
        return False

    def set_element_value(self, element: UIElement, value: str) -> bool:
        """Set text via ValuePattern."""
        if not self._available or element.raw is None:
            return False
        try:
            raw = element.raw.get("_uia_ref")
            if raw is None:
                return False
            pattern = raw.GetValuePattern()
            if pattern:
                pattern.SetValue(value)
                return True
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.debug("set_element_value failed: %s", exc)
        return False

    # ── Internal helpers ────────────────────────────────────────────────

    def _get_root(self, window_title: str | None = None) -> Any:
        """Get the root element for searching."""
        if _uia_auto is None:
            return None
        if window_title:
            return _uia_auto.WindowControl(searchDepth=1, Name=window_title)
        return _uia_auto.GetForegroundWindow()

    def _walk_tree(
        self,
        control: Any,
        elements: list[UIElement],
        depth: int,
        max_depth: int,
    ) -> None:
        """Recursively walk the UIA tree and collect elements."""
        if depth > max_depth:
            return
        try:
            elem = self._uia_to_element(control)
            if elem.name or elem.control_type != "unknown":
                elements.append(elem)
            for child in control.GetChildren():
                self._walk_tree(child, elements, depth + 1, max_depth)
        except (OSError, RuntimeError):
            pass

    def _uia_to_element(self, control: Any) -> UIElement:
        """Convert a UIA control to our normalized UIElement."""
        try:
            rect = control.BoundingRectangle
            box = (int(rect.left), int(rect.top), int(rect.width), int(rect.height))
        except (OSError, RuntimeError, AttributeError):
            box = None

        # Get control type name
        try:
            ct = type(control).__name__.replace("Control", "").lower()
        except (AttributeError, TypeError):
            ct = "unknown"

        # Get available actions
        actions: list[str] = []
        try:
            if control.GetInvokePattern():
                actions.append("invoke")
            if control.GetValuePattern():
                actions.append("set_value")
            if control.GetTogglePattern():
                actions.append("toggle")
            if control.GetExpandCollapsePattern():
                actions.append("expand")
            if control.GetScrollPattern():
                actions.append("scroll")
            if control.GetSelectionItemPattern():
                actions.append("select")
        except (OSError, RuntimeError, AttributeError):
            pass

        return UIElement(
            name=control.Name or "",
            control_type=ct,
            bounding_box=box,
            enabled=control.IsEnabled if control.IsEnabled is not None else True,
            value=self._get_value(control),
            automation_id=control.AutomationId or None,
            actions=actions,
            raw={"_uia_ref": control},
        )

    @staticmethod
    def _get_value(control: Any) -> str | None:
        """Try to get the value of a control."""
        try:
            pattern = control.GetValuePattern()
            if pattern:
                return pattern.Value or None
        except (OSError, RuntimeError, AttributeError):
            pass
        return None


# ---------------------------------------------------------------------------
# Windows Stealth Input Backend
# ---------------------------------------------------------------------------


class WindowsStealthInput(StealthInputBackend):
    """PostMessage-based stealth input for Windows."""

    def __init__(self) -> None:
        self._available = _probe_win32()

    def is_available(self) -> bool:
        return self._available

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
        """Send a click via PostMessage without moving the cursor."""
        if not self._available:
            return False
        try:
            hwnd = _win32gui.WindowFromPoint((int(x), int(y)))
            if not hwnd:
                return False
            cx, cy = _win32gui.ScreenToClient(hwnd, (int(x), int(y)))
            lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
            if button == "right":
                down, up = _win32con.WM_RBUTTONDOWN, _win32con.WM_RBUTTONUP
                wparam = _win32con.MK_RBUTTON
            elif button == "middle":
                down, up = _win32con.WM_MBUTTONDOWN, _win32con.WM_MBUTTONUP
                wparam = _win32con.MK_MBUTTON
            else:
                down, up = _win32con.WM_LBUTTONDOWN, _win32con.WM_LBUTTONUP
                wparam = _win32con.MK_LBUTTON
            import time

            for _ in range(max(1, clicks)):
                _win32api.PostMessage(hwnd, down, wparam, lparam)
                time.sleep(0.02)
                _win32api.PostMessage(hwnd, up, 0, lparam)
                time.sleep(0.02)
            return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("stealth click failed at (%s,%s): %s", x, y, exc)
            return False

    def type_text(self, text: str) -> bool:
        """Type text via WM_CHAR messages."""
        if not self._available or not text:
            return False
        try:
            hwnd = _win32gui.GetForegroundWindow()
            if not hwnd:
                return False
            focus_hwnd = self._get_focus_hwnd(hwnd) or hwnd
            import time

            for ch in text:
                _win32api.PostMessage(focus_hwnd, _win32con.WM_CHAR, ord(ch), 0)
                time.sleep(0.005)
            return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("stealth type_text failed: %s", exc)
            return False

    def press_key(self, key: str) -> bool:
        """Press a key via WM_KEYDOWN/WM_KEYUP."""
        if not self._available:
            return False
        from core.stealth_input import VK_NAMES, post_key

        vk = VK_NAMES.get((key or "").lower())
        if vk is not None:
            return post_key(vk)
        return False

    def hotkey(self, *keys: str) -> bool:
        """Send chorded hotkey via PostMessage."""
        if not self._available:
            return False
        from core.stealth_input import post_hotkey

        return post_hotkey(list(keys))

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> bool:
        """Scroll via WM_MOUSEWHEEL."""
        if not self._available:
            return False
        try:
            if x is not None and y is not None:
                hwnd = _win32gui.WindowFromPoint((int(x), int(y)))
            else:
                hwnd = _win32gui.GetForegroundWindow()
            if not hwnd:
                return False
            # WM_MOUSEWHEEL: wParam = (delta << 16) | keys
            delta = amount * 120  # WHEEL_DELTA = 120
            lparam = 0
            if x is not None and y is not None:
                lparam = ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)
            _win32api.PostMessage(hwnd, _win32con.WM_MOUSEWHEEL, delta << 16, lparam)
            return True
        except (OSError, AttributeError, RuntimeError) as exc:
            logger.debug("stealth scroll failed: %s", exc)
            return False

    @staticmethod
    def _get_focus_hwnd(parent: int) -> int | None:
        """Get the focused control HWND inside parent's thread."""
        try:
            import ctypes
            from ctypes import wintypes

            thread_id = _win32api.GetWindowThreadProcessId(parent)[0]

            class _RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class _GUI_THREAD_INFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("hwndActive", wintypes.HWND),
                    ("hwndFocus", wintypes.HWND),
                    ("hwndCapture", wintypes.HWND),
                    ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND),
                    ("hwndCaret", wintypes.HWND),
                    ("rcCaret", _RECT),
                ]

            info = _GUI_THREAD_INFO()
            info.cbSize = ctypes.sizeof(info)
            if ctypes.windll.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
                return int(info.hwndFocus) or None
        except (OSError, AttributeError, RuntimeError):
            pass
        return None


# ---------------------------------------------------------------------------
# Windows Credential Backend (DPAPI)
# ---------------------------------------------------------------------------


class WindowsCredentialBackend(CredentialBackend):
    """DPAPI-backed credential storage for Windows.

    Delegates entirely to the existing ``core.encryption.CredentialVault``
    which already handles DPAPI on Windows and has proper file persistence.
    """

    def __init__(self) -> None:
        # No need to re-initialize DPAPI — CredentialVault handles it.
        pass

    def store(self, key: str, value: str) -> bool:
        """Encrypt and store a credential using DPAPI."""
        from core.encryption import CredentialVault

        vault = CredentialVault()
        return vault.store(key, value)

    def retrieve(self, key: str) -> str | None:
        """Decrypt and return a stored credential."""
        from core.encryption import CredentialVault

        vault = CredentialVault()
        return vault.retrieve(key)

    def delete(self, key: str) -> bool:
        """Delete a stored credential."""
        from core.encryption import CredentialVault

        vault = CredentialVault()
        return vault.delete(key)

    def list_keys(self) -> list[str]:
        """List all stored credential names."""
        from core.encryption import CredentialVault

        vault = CredentialVault()
        return vault.list_keys()


# ---------------------------------------------------------------------------
# Windows Shell Backend (PowerShell)
# ---------------------------------------------------------------------------

# Dangerous command patterns to block
_DANGEROUS_PATTERNS = (
    "rm -rf /",
    "del /f /s /q c:\\",
    "format ",
    "diskpart",
    "reg delete",
    "reg add",
    "net user",
    "net localgroup",
)


class WindowsShellBackend(ShellBackend):
    """PowerShell-based shell for Windows."""

    def __init__(self) -> None:
        self._has_ps = _probe_powershell()

    def execute(
        self,
        command: str,
        timeout: float = 60.0,
        capture: bool = True,
    ) -> dict[str, Any]:
        """Execute a command via PowerShell."""
        sanitized = self.sanitize_command(command)
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", sanitized],
                capture_output=capture,
                text=True,
                timeout=timeout,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "Command timed out"}
        except (OSError, RuntimeError) as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc)}

    def get_platform_shell(self) -> str:
        """Return 'powershell'."""
        return "powershell" if self._has_ps else "cmd"

    def sanitize_command(self, command: str) -> str:
        """Block obviously dangerous commands."""
        lower = command.lower().strip()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in lower:
                raise ValueError(f"Command contains potentially dangerous pattern: '{pattern}'")
        return command


# ---------------------------------------------------------------------------
# Windows Window Backend (win32gui)
# ---------------------------------------------------------------------------


class WindowsWindowBackend(WindowBackend):
    """Win32-based window management for Windows."""

    def __init__(self) -> None:
        self._has_win32 = _probe_win32()
        self._has_pgw = False
        try:
            import pygetwindow as pgw  # type: ignore

            self._has_pgw = True
            self._pgw = pgw
        except ImportError:
            self._pgw = None

    def list_windows(self) -> list[WindowInfo]:
        """List all visible windows."""
        windows: list[WindowInfo] = []
        if self._has_win32:

            def _enum(hwnd: int, _: Any) -> None:
                if _win32gui.IsWindowVisible(hwnd):
                    title = _win32gui.GetWindowText(hwnd)
                    if title:
                        rect = _win32gui.GetWindowRect(hwnd)
                        windows.append(
                            WindowInfo(
                                title=title,
                                x=rect[0],
                                y=rect[1],
                                width=rect[2] - rect[0],
                                height=rect[3] - rect[1],
                                is_focused=hwnd == _win32gui.GetForegroundWindow(),
                                handle=hwnd,
                            )
                        )

            try:
                _win32gui.EnumWindows(_enum, None)
            except OSError as exc:
                logger.error("EnumWindows failed: %s", exc)
        elif self._has_pgw and self._pgw:
            try:
                for w in self._pgw.getAllWindows():
                    if w.title:
                        windows.append(
                            WindowInfo(
                                title=w.title,
                                x=w.left,
                                y=w.top,
                                width=w.width,
                                height=w.height,
                                is_focused=w.isActive,
                            )
                        )
            except (OSError, RuntimeError) as exc:
                logger.error("pygetwindow list failed: %s", exc)
        return windows

    def focus_window(self, title: str) -> bool:
        """Bring a window to the foreground."""
        if self._has_win32:
            return self._focus_win32(title)
        if self._has_pgw and self._pgw:
            return self._focus_pgw(title)
        return False

    def close_window(self, title: str) -> bool:
        """Close a window by title."""
        if self._has_win32:
            return self._close_win32(title)
        if self._has_pgw and self._pgw:
            return self._close_pgw(title)
        return False

    def get_focused_window_rect(self) -> tuple[int, int, int, int] | None:
        """Get the focused window's rectangle."""
        if self._has_win32:
            try:
                hwnd = _win32gui.GetForegroundWindow()
                if not hwnd:
                    return None
                rect = _win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w <= 0 or h <= 0:
                    return None
                return (x, y, w, h)
            except OSError as exc:
                logger.debug("get_focused_window_rect failed: %s", exc)
        return None

    def get_window_rect(self, title: str) -> tuple[int, int, int, int] | None:
        """Get a window's rectangle by title."""
        needle = title.lower()
        for w in self.list_windows():
            if needle in (w.title or "").lower():
                return (w.x, w.y, w.width, w.height)
        return None

    # ── Internal helpers ────────────────────────────────────────────────

    def _focus_win32(self, title: str) -> bool:
        """Focus a window using Win32 API."""
        needle = title.lower()
        for w in self.list_windows():
            if needle in (w.title or "").lower():
                hwnd = w.handle
                if hwnd:
                    try:
                        _win32gui.ShowWindow(hwnd, _win32con.SW_RESTORE)
                        # Alt-tap trick to bypass SetForegroundWindow restrictions
                        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                        ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)
                        _win32gui.SetForegroundWindow(hwnd)
                        return True
                    except OSError as exc:
                        logger.warning("focus_window(%s) failed: %s", title, exc)
        return False

    def _focus_pgw(self, title: str) -> bool:
        """Focus a window using PyGetWindow."""
        try:
            wins = self._pgw.getWindowsWithTitle(title)
            if wins:
                wins[0].activate()
                return True
        except (OSError, RuntimeError):
            pass
        return False

    def _close_win32(self, title: str) -> bool:
        """Close a window via WM_CLOSE."""
        needle = title.lower()
        found = False

        def _find(hwnd: int, _: Any) -> None:
            nonlocal found
            if found:
                return
            if _win32gui.IsWindowVisible(hwnd) and needle in _win32gui.GetWindowText(hwnd).lower():
                _win32gui.PostMessage(hwnd, _win32con.WM_CLOSE, 0, 0)
                found = True

        try:
            _win32gui.EnumWindows(_find, None)
            return found
        except OSError:
            return False

    def _close_pgw(self, title: str) -> bool:
        """Close a window using PyGetWindow."""
        try:
            wins = self._pgw.getWindowsWithTitle(title)
            if wins:
                wins[0].close()
                return True
        except (OSError, RuntimeError):
            pass
        return False


# ---------------------------------------------------------------------------
# Windows Overlay Backend
# ---------------------------------------------------------------------------


class WindowsOverlayBackend(OverlayBackend):
    """Transparent overlay via Win32 layered windows."""

    def is_available(self) -> bool:
        return _probe_win32()

    def show_ring(self, x: int, y: int, color: str = "#00F0FF", duration_ms: int = 420) -> None:
        """Show ring highlight via the existing GUI overlay system."""
        # Delegate to existing gui overlay module if available
        try:
            from gui import overlay as overlay_mod

            if hasattr(overlay_mod, "show_action_ring"):
                overlay_mod.show_action_ring(x, y, color, duration_ms)
        except (ImportError, AttributeError):
            logger.debug("Overlay ring not available")

    def show_cursor_move(
        self, from_x: int, from_y: int, to_x: int, to_y: int, duration_ms: int = 300
    ) -> None:
        """Animate cursor via the existing GUI cursor overlay."""
        try:
            from gui import cursor_overlay as cursor_mod

            if hasattr(cursor_mod, "animate_cursor"):
                cursor_mod.animate_cursor(from_x, from_y, to_x, to_y, duration_ms)
        except (ImportError, AttributeError):
            logger.debug("Cursor overlay not available")


# ---------------------------------------------------------------------------
# Aggregated Windows Backend
# ---------------------------------------------------------------------------


class WindowsBackend(PlatformBackend):
    """Aggregated backend for Windows."""

    def __init__(self) -> None:
        self._accessibility = WindowsAccessibility()
        self._stealth = WindowsStealthInput()
        self._credentials = WindowsCredentialBackend()
        self._shell = WindowsShellBackend()
        self._window = WindowsWindowBackend()
        self._overlay = WindowsOverlayBackend()

    @property
    def accessibility(self) -> WindowsAccessibility:
        return self._accessibility

    @property
    def stealth(self) -> WindowsStealthInput:
        return self._stealth

    @property
    def credentials(self) -> WindowsCredentialBackend:
        return self._credentials

    @property
    def shell(self) -> WindowsShellBackend:
        return self._shell

    @property
    def window(self) -> WindowsWindowBackend:
        return self._window

    @property
    def overlay(self) -> WindowsOverlayBackend:
        return self._overlay

    @property
    def default_shell(self) -> str:
        return self._shell.get_platform_shell()
