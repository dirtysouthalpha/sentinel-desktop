"""
Sentinel Desktop — Virtual Desktop isolation layer.

Creates a separate Windows desktop object via the Win32 API so the agent can
operate applications on its own desktop without interfering with the user's
active ("Default") desktop.  The user keeps working normally while the agent
controls windows on ``SentinelDesktop``.

Uses only ``ctypes`` — no ``pywin32`` dependency — so the import is cheap and
portable.  On non-Windows platforms (or if desktop creation fails at runtime)
the class falls back to the current desktop and logs a warning.

Thread safety
-------------
The agent loop typically runs on one thread while screenshot capture happens
on another.  Every public method is guarded by an internal ``threading.Lock``
so that ``switch_to()`` / ``switch_back()`` calls never race with each other
or with ``launch_app()``.

Usage
-----
>>> from core.virtual_desktop import VirtualDesktop
>>> with VirtualDesktop("SentinelDesktop") as vd:
...     vd.launch_app(r"C:\\Windows\\notepad.exe")
...     img = vd.screenshot()
...     windows = vd.list_windows()
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
from types import TracebackType
from typing import Any, NoReturn

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform gate — everything below only exists on real Windows.
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

# Win32 desktop access rights (from winuser.h)
DESKTOP_READOBJECTS = 0x0001
DESKTOP_CREATEWINDOW = 0x0002
DESKTOP_CREATEMENU = 0x0004
DESKTOP_HOOKCONTROL = 0x0008
DESKTOP_JOURNALRECORD = 0x0010
DESKTOP_JOURNALPLAYBACK = 0x0020
DESKTOP_ENUMERATE = 0x0040
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_SWITCHDESKTOP = 0x0100

# Standard all-access mask for a desktop we own
_DESKTOP_FULL_ACCESS = (
    DESKTOP_READOBJECTS
    | DESKTOP_CREATEWINDOW
    | DESKTOP_CREATEMENU
    | DESKTOP_HOOKCONTROL
    | DESKTOP_JOURNALRECORD
    | DESKTOP_JOURNALPLAYBACK
    | DESKTOP_ENUMERATE
    | DESKTOP_WRITEOBJECTS
    | DESKTOP_SWITCHDESKTOP
)

# STARTUPINFO dwFlags
STARTF_USESHOWWINDOW = 0x00000001

# ShowWindow constants
SW_SHOWNORMAL = 1

# GetUserObjectInformation index
UOI_NAME = 2

# Lazy ctypes handles — populated once on first use.
_user32: Any | None = None
_kernel32: Any | None = None


def _get_user32() -> Any:
    global _user32
    if _user32 is None:
        import ctypes

        _user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    return _user32


def _get_kernel32() -> Any:
    global _kernel32
    if _kernel32 is None:
        import ctypes

        _kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    return _kernel32


# ---------------------------------------------------------------------------
# Helper: discover the name of the current (default) desktop
# ---------------------------------------------------------------------------


def _get_current_desktop_name() -> str:
    """Retrieve the name of the desktop assigned to the calling thread.

    Uses ``GetThreadDesktop`` → ``GetUserObjectInformationW(UOI_NAME)``.
    Falls back to ``"Default"`` on any failure.
    """
    if not _IS_WINDOWS:
        return "Default"
    try:
        import ctypes
        from ctypes import wintypes

        user32 = _get_user32()

        hdesk = user32.GetThreadDesktop(
            ctypes.windll.kernel32.GetCurrentThreadId()  # type: ignore[attr-defined]
        )
        if not hdesk:
            return "Default"

        # GetUserObjectInformationW needs a buffer for the name string.
        buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        if not user32.GetUserObjectInformationW(
            hdesk, UOI_NAME, buf, ctypes.sizeof(buf), ctypes.byref(needed)
        ):
            return "Default"

        name = buf.value
        return name if name else "Default"
    except Exception as exc:
        logger.debug("_get_current_desktop_name failed: %s", exc)
        return "Default"


# ---------------------------------------------------------------------------
# Windows implementation
# ---------------------------------------------------------------------------


class _Win32VirtualDesktop:
    """Internal implementation backed by real Win32 desktop objects."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._handle: int | None = None
        self._default_desktop_name: str = _get_current_desktop_name()
        self._default_handle: int | None = None
        self._lock = threading.Lock()
        self._is_active = False
        self._launched_pids: list[int] = []

        # Snapshot the handle of the default desktop so we can restore it.
        try:
            user32 = _get_user32()
            self._default_handle = user32.GetThreadDesktop(_get_kernel32().GetCurrentThreadId())
        except Exception as exc:
            logger.debug("Could not snapshot default desktop handle: %s", exc)

    # -- creation / cleanup --------------------------------------------------

    def create(self) -> bool:
        """Create the virtual desktop.  Returns ``True`` on success."""
        if not _IS_WINDOWS:
            return False
        try:
            user32 = _get_user32()

            # If the desktop already exists, try to open it instead.
            existing = user32.OpenDesktopW(
                self._name,
                0,  # dwFlags
                False,  # fInherit
                _DESKTOP_FULL_ACCESS,
            )
            if existing:
                logger.info("Opened existing desktop %r", self._name)
                self._handle = existing
                return True

            # Create a brand-new desktop object.
            handle = user32.CreateDesktopW(
                self._name,  # lpszDesktop
                None,  # lpszDevice (no device)
                None,  # pDevmode (no devmode)
                0,  # dwFlags (reserved, 0)
                _DESKTOP_FULL_ACCESS,  # dwDesiredAccess
                None,  # lpsa (NULL → default security)
            )
            if not handle:
                _raise_last_error("CreateDesktopW")

            self._handle = handle
            logger.info("Created virtual desktop %r (handle=%s)", self._name, handle)
            return True

        except Exception as exc:
            logger.warning(
                "Virtual desktop creation failed (%s); falling back to current desktop",
                exc,
            )
            self._handle = None
            return False

    def close(self) -> None:
        """Close the desktop handle and clean up launched processes."""
        with self._lock:
            self._is_active = False
            # Terminate processes we launched on this desktop.
            self._cleanup_launched_processes()
            if self._handle:
                try:
                    _get_user32().CloseDesktop(self._handle)
                except Exception as exc:
                    logger.debug("CloseDesktop failed: %s", exc)
                self._handle = None
            logger.info("Virtual desktop %r closed", self._name)

    # -- desktop switching ---------------------------------------------------

    def switch_to(self) -> bool:
        """Switch the calling thread to this virtual desktop.

        After calling this, ``pyautogui.screenshot()`` / ``mss`` will capture
        pixels from *this* desktop, not the user's desktop.

        Returns ``True`` on success.
        """
        with self._lock:
            if not self._handle:
                logger.debug("switch_to: no handle — already in fallback mode")
                return False
            try:
                user32 = _get_user32()
                if not user32.SetThreadDesktop(self._handle):
                    _raise_last_error("SetThreadDesktop")
                # Also switch the visible desktop so windows render.
                if not user32.SwitchDesktop(self._handle):
                    # Not fatal — SetThreadDesktop may succeed even if
                    # SwitchDesktop doesn't (e.g. service session).
                    logger.debug("SwitchDesktop returned False (non-fatal)")
                self._is_active = True
                return True
            except Exception as exc:
                logger.warning("switch_to failed: %s", exc)
                return False

    def switch_back(self) -> bool:
        """Return to the default desktop.

        Returns ``True`` on success.
        """
        with self._lock:
            if not self._default_handle and not self._default_desktop_name:
                logger.debug("switch_back: no default info available")
                return False
            try:
                user32 = _get_user32()

                # Re-open the default desktop by name — the cached handle
                # belongs to a different thread and may not be valid here.
                default_handle = user32.OpenDesktopW(
                    self._default_desktop_name,
                    0,
                    False,
                    _DESKTOP_FULL_ACCESS,
                )
                if not default_handle:
                    _raise_last_error("OpenDesktopW(default)")

                if not user32.SetThreadDesktop(default_handle):
                    _raise_last_error("SetThreadDesktop(default)")

                if not user32.SwitchDesktop(default_handle):
                    logger.debug("SwitchDesktop(default) returned False (non-fatal)")

                user32.CloseDesktop(default_handle)
                self._is_active = False
                return True
            except Exception as exc:
                logger.warning("switch_back failed: %s", exc)
                return False

    # -- process launching ---------------------------------------------------

    def launch_app(self, path: str, args: str | None = None) -> dict[str, Any]:
        """Start a process on this virtual desktop via ``STARTUPINFO.lpDesktop``.

        Returns ``{"success": bool, "pid": int|None, "output": str}``.
        """
        with self._lock:
            return self._launch_app_locked(path, args)

    def _launch_app_locked(self, path: str, args: str | None = None) -> dict[str, Any]:
        """Must be called while ``self._lock`` is held."""
        import ctypes
        from ctypes import wintypes

        # Build the command line.
        cmd = f'"{path}"'
        if args:
            cmd = f"{cmd} {args}"

        # STARTUPINFOW structure (68 bytes on 64-bit, 48 on 32-bit — we use
        # the explicit cb field so it's correct on both).
        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.dwFlags = STARTF_USESHOWWINDOW
        si.wShowWindow = SW_SHOWNORMAL

        # Point the process at our virtual desktop.
        desktop_target = self._name if self._handle else None
        si.lpDesktop = desktop_target

        pi = PROCESS_INFORMATION()

        kernel32 = _get_kernel32()

        # CreateProcessW signature:
        #   lpApplicationName, lpCommandLine, lpProcessAttributes,
        #   lpThreadAttributes, bInheritHandles, dwCreationFlags,
        #   lpEnvironment, lpCurrentDirectory, lpStartupInfo,
        #   lpProcessInformation
        CREATE_NEW_CONSOLE = 0x00000010

        cmd_line = ctypes.create_unicode_buffer(cmd)

        ok = kernel32.CreateProcessW(
            None,  # lpApplicationName
            cmd_line,  # lpCommandLine
            None,  # lpProcessAttributes
            None,  # lpThreadAttributes
            False,  # bInheritHandles
            CREATE_NEW_CONSOLE,  # dwCreationFlags
            None,  # lpEnvironment
            None,  # lpCurrentDirectory
            ctypes.byref(si),  # lpStartupInfo
            ctypes.byref(pi),  # lpProcessInformation
        )

        if not ok:
            error = kernel32.GetLastError()
            msg = f"CreateProcessW failed for {path!r} ( GetLastError={error} )"
            logger.error(msg)
            return {"success": False, "pid": None, "output": msg}

        pid = pi.dwProcessId
        self._launched_pids.append(pid)

        # Close the handles we don't need.
        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)

        logger.info(
            "Launched %r on desktop %r (pid=%d)",
            path,
            desktop_target or "(current)",
            pid,
        )
        return {
            "success": True,
            "pid": pid,
            "output": f"Launched {path!r} on {desktop_target or 'current'} desktop (pid={pid})",
        }

    def _cleanup_launched_processes(self) -> None:
        """Best-effort termination of processes spawned on this desktop."""
        for pid in self._launched_pids:
            try:
                import signal

                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        self._launched_pids.clear()

    # -- screenshot ----------------------------------------------------------

    def screenshot(self) -> Image.Image | None:
        """Capture a screenshot of this virtual desktop.

        Temporarily switches the calling thread to this desktop (if not
        already active), captures via ``pyautogui``, then restores the
        previous desktop.

        Returns ``PIL.Image`` on success, ``None`` on failure.
        """
        # The lock serialises switch/capture/restore so another thread
        # can't switch away between our switch_to and the capture.
        acquired = self._lock.acquire(timeout=5)
        if not acquired:
            logger.warning("screenshot: could not acquire lock within timeout")
            return None
        try:
            was_on_vd = self._is_active
            switched = False

            if self._handle and not was_on_vd:
                switched = self._switch_to_locked()

            try:
                import pyautogui

                img = pyautogui.screenshot()
                return img
            except Exception as exc:
                logger.warning("screenshot capture failed: %s", exc)
                return None
            finally:
                if switched:
                    self._switch_back_locked()
        finally:
            self._lock.release()

    # -- window enumeration --------------------------------------------------

    def list_windows(self) -> list[dict[str, Any]]:
        """Enumerate visible windows belonging to this virtual desktop.

        Returns a list of dicts with ``title``, ``x``, ``y``, ``width``,
        ``height``, ``hwnd`` keys.
        """
        windows: list[dict[str, Any]] = []

        if not _IS_WINDOWS or not self._handle:
            # Fallback: use the standard window_manager enumeration.
            try:
                from core import window_manager as wm

                return wm.list_windows()
            except Exception as exc:
                logger.debug("window_manager fallback failed: %s", exc)
                return windows

        try:
            import ctypes
            from ctypes import wintypes

            user32 = _get_user32()

            # We need to be on the virtual desktop to enumerate its windows.
            acquired = self._lock.acquire(timeout=5)
            if not acquired:
                return windows
            try:
                switched = False
                if not self._is_active:
                    switched = self._switch_to_locked()

                # Callback for EnumWindows — only collects windows whose
                # desktop matches ours.
                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

                def _enum_cb(hwnd: int, lparam: int) -> bool:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    # Retrieve the window's desktop.
                    # GetWindowDesktopHandle is not a standard API, so we
                    # check by process/thread instead: query the thread that
                    # owns the window and see if it's on our desktop.
                    tid = user32.GetWindowThreadProcessId(hwnd, None)
                    if not tid:
                        return True
                    hdesk = user32.GetThreadDesktop(tid)
                    # Compare handles (our handle is the virtual desktop).
                    if hdesk != self._handle:
                        return True  # not ours, skip

                    # Get title.
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length == 0:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    if not title:
                        return True

                    # Get rect.
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    windows.append(
                        {
                            "title": title,
                            "x": rect.left,
                            "y": rect.top,
                            "width": rect.right - rect.left,
                            "height": rect.bottom - rect.top,
                            "hwnd": hwnd,
                            "is_focused": hwnd == user32.GetForegroundWindow(),
                        }
                    )
                    return True

                callback = WNDENUMPROC(_enum_cb)
                user32.EnumWindows(callback, 0)

                if switched:
                    self._switch_back_locked()
            finally:
                self._lock.release()

        except Exception as exc:
            logger.warning("list_windows on virtual desktop failed: %s", exc)

        return windows

    # -- internal locked helpers ---------------------------------------------

    def _switch_to_locked(self) -> bool:
        """Switch to virtual desktop.  Caller must hold ``self._lock``."""
        try:
            user32 = _get_user32()
            if not user32.SetThreadDesktop(self._handle):
                return False
            user32.SwitchDesktop(self._handle)
            self._is_active = True
            return True
        except Exception as exc:
            logger.debug("_switch_to_locked failed: %s", exc)
            return False

    def _switch_back_locked(self) -> bool:
        """Switch back to default desktop.  Caller must hold ``self._lock``."""
        try:
            user32 = _get_user32()
            default_handle = user32.OpenDesktopW(
                self._default_desktop_name,
                0,
                False,
                _DESKTOP_FULL_ACCESS,
            )
            if not default_handle:
                return False
            user32.SetThreadDesktop(default_handle)
            user32.SwitchDesktop(default_handle)
            user32.CloseDesktop(default_handle)
            self._is_active = False
            return True
        except Exception as exc:
            logger.debug("_switch_back_locked failed: %s", exc)
            return False

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> _Win32VirtualDesktop:
        self.create()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Best-effort: switch back before closing.
        self.switch_back()
        self.close()


# ---------------------------------------------------------------------------
# Non-Windows stub — logs a warning and provides safe no-op methods.
# ---------------------------------------------------------------------------


class _StubVirtualDesktop:
    """Fallback used when the platform is not Windows or Win32 APIs fail."""

    def __init__(self, name: str) -> None:
        self._name = name
        logger.warning(
            "VirtualDesktop(%r): not running on Windows — operating on "
            "the current desktop. Agent actions will be visible to the user.",
            name,
        )

    def create(self) -> bool:
        return False

    def switch_to(self) -> bool:
        return False

    def switch_back(self) -> bool:
        return False

    def launch_app(self, path: str, args: str | None = None) -> dict[str, Any]:
        """Launch on the *current* desktop as a graceful fallback."""
        try:
            cmd = [path]
            if args:
                cmd.append(args)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "pid": proc.pid,
                "output": f"Launched {path!r} on current desktop (pid={proc.pid}) [fallback]",
            }
        except (OSError, subprocess.SubprocessError, FileNotFoundError) as exc:
            return {
                "success": False,
                "pid": None,
                "output": f"Failed to launch {path!r}: {exc}",
            }

    def screenshot(self) -> Image.Image | None:
        """Capture the current (only) desktop."""
        try:
            import pyautogui

            return pyautogui.screenshot()
        except Exception as exc:
            logger.warning("screenshot (fallback) failed: %s", exc)
            return None

    def list_windows(self) -> list[dict[str, Any]]:
        """Delegate to the standard window_manager."""
        try:
            from core import window_manager as wm

            return wm.list_windows()
        except Exception as exc:
            logger.debug("list_windows fallback failed: %s", exc)
            return []

    def close(self) -> None:
        pass

    def __enter__(self) -> _StubVirtualDesktop:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------


def _raise_last_error(api_name: str) -> NoReturn:
    """Raise an ``OSError`` with the Win32 last-error text."""
    import ctypes

    error_code = ctypes.GetLastError()
    # FormatMessageW is the proper way but a simple code is fine for logging.
    raise OSError(f"{api_name} failed (Win32 error {error_code})")


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


class VirtualDesktop:
    """Create and manage an isolated Windows desktop for agent operations.

    On Windows this creates a real desktop object via ``CreateDesktopW``.
    On every other platform (or if creation fails) it falls back to operating
    on the current desktop with a warning.

    Supports the context-manager protocol for automatic cleanup::

        with VirtualDesktop("SentinelDesktop") as vd:
            vd.launch_app(r"C:\\Windows\\notepad.exe")
            img = vd.screenshot()

    Or use it manually::

        vd = VirtualDesktop()
        vd.create()
        try:
            vd.switch_to()
            vd.launch_app(...)
            img = vd.screenshot()
        finally:
            vd.switch_back()
            vd.close()
    """

    def __init__(self, name: str = "SentinelDesktop") -> None:
        self._name = name
        self._impl: Any | None = None

        if _IS_WINDOWS:
            try:
                self._impl = _Win32VirtualDesktop(name)
            except Exception as exc:
                logger.warning(
                    "Failed to initialise Win32 virtual desktop: %s — falling back to stub",
                    exc,
                )
                self._impl = _StubVirtualDesktop(name)
        else:
            self._impl = _StubVirtualDesktop(name)

    # -- delegate all public methods to the implementation -------------------

    def create(self) -> bool:
        """Create (or open) the virtual desktop.

        Returns ``True`` if the desktop was created / opened successfully.
        On non-Windows platforms always returns ``False``.
        """
        return self._impl.create()

    def switch_to(self) -> bool:
        """Switch the calling thread to this desktop.

        After this call, screenshot capture will see this desktop's windows.
        Returns ``True`` on success.
        """
        return self._impl.switch_to()

    def switch_back(self) -> bool:
        """Return to the original (default) desktop.

        Returns ``True`` on success.
        """
        return self._impl.switch_back()

    def launch_app(self, path: str, args: str | None = None) -> dict[str, Any]:
        """Launch an application on this desktop.

        On Windows, the process is started with
        ``STARTUPINFO.lpDesktop`` pointing to the virtual desktop so it
        renders there instead of the user's desktop.

        Args:
            path: Absolute path to the executable.
            args: Optional command-line arguments string.

        Returns:
            Dict with ``success``, ``pid``, ``output`` keys.
        """
        return self._impl.launch_app(path, args)

    def screenshot(self) -> Image.Image | None:
        """Capture a screenshot of the virtual desktop.

        Temporarily switches to this desktop if necessary, captures, then
        switches back.  Thread-safe.

        Returns a ``PIL.Image.Image`` on success or ``None`` on failure.
        """
        return self._impl.screenshot()

    def list_windows(self) -> list[dict[str, Any]]:
        """List visible windows on this desktop.

        Returns a list of dicts with ``title``, ``x``, ``y``, ``width``,
        ``height``, ``hwnd`` keys (same shape as
        ``core.window_manager.list_windows``).
        """
        return self._impl.list_windows()

    def close(self) -> None:
        """Close the desktop handle and clean up any launched processes."""
        self._impl.close()

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> VirtualDesktop:
        self.create()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.switch_back()
        self.close()

    # -- repr ----------------------------------------------------------------

    def __repr__(self) -> str:
        impl_type = type(self._impl).__name__
        return f"<VirtualDesktop name={self._name!r} impl={impl_type}>"
