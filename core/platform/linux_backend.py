"""Sentinel Desktop v4.0 — Linux Platform Backend.

Provides accessibility (AT-SPI), stealth input (xdotool/XTest), credentials
(libsecret/secretstorage), shell (bash), and window management (wnck/xdotool)
for Linux desktop environments (GNOME, KDE, XFCE, etc.).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import uuid
from pathlib import Path
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
from core.utils import restrict_file_perms

logger = logging.getLogger(__name__)

# ── Availability probes ─────────────────────────────────────────────────

_has_xdotool: bool | None = None


def _probe_xdotool() -> bool:
    """Check if xdotool is available."""
    global _has_xdotool
    if _has_xdotool is not None:
        return _has_xdotool
    try:
        result = subprocess.run(
            ["xdotool", "version"],
            capture_output=True,
            timeout=3,
        )
        _has_xdotool = result.returncode == 0
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        _has_xdotool = False
    return _has_xdotool


_has_atspi: bool | None = None


def _probe_atspi() -> bool:
    """Check if python-atspi / pyatspi is available."""
    global _has_atspi
    if _has_atspi is not None:
        return _has_atspi
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi  # noqa: F401

        _has_atspi = True
    except (ImportError, ValueError, OSError):
        _has_atspi = False
    return _has_atspi


_has_secretstorage: bool | None = None


def _probe_secretstorage() -> bool:
    """Check if secretstorage (libsecret Python bindings) is available."""
    global _has_secretstorage
    if _has_secretstorage is not None:
        return _has_secretstorage
    try:
        import secretstorage  # type: ignore  # noqa: F401

        _has_secretstorage = True
    except ImportError:
        _has_secretstorage = False
    return _has_secretstorage


_has_wnck: bool | None = None


def _probe_wnck() -> bool:
    """Check if libwnck is available for window management."""
    global _has_wnck
    if _has_wnck is not None:
        return _has_wnck
    try:
        import gi

        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck  # noqa: F401

        _has_wnck = True
    except (ImportError, ValueError, OSError):
        _has_wnck = False
    return _has_wnck


# ---------------------------------------------------------------------------
# Linux Accessibility Backend (AT-SPI)
# ---------------------------------------------------------------------------


class LinuxAccessibility(AccessibilityBackend):
    """AT-SPI based accessibility tree for Linux (GNOME, KDE, XFCE)."""

    def __init__(self) -> None:
        self._available = _probe_atspi()

    def is_available(self) -> bool:
        return self._available

    def get_tree(self, window_title: str | None = None) -> list[UIElement]:
        """Walk the AT-SPI tree for the focused or named window."""
        if not self._available:
            return []
        try:
            import gi

            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi

            desktop = Atspi.get_desktop(0)
            elements: list[UIElement] = []

            for app_idx in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(app_idx)
                if app is None:
                    continue
                for win_idx in range(app.get_child_count()):
                    win = app.get_child_at_index(win_idx)
                    if win is None:
                        continue
                    win_name = win.get_name() or ""
                    if window_title and window_title.lower() not in win_name.lower():
                        continue
                    self._walk_atspi(win, elements, depth=0, max_depth=12)
            return elements
        except Exception as exc:
            logger.debug("AT-SPI get_tree failed: %s", exc)
            return []

    def find_element(
        self,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> UIElement | None:
        """Find a single element by attributes."""
        elements = self.get_tree(window_title)
        for elem in elements:
            if name and name.lower() not in (elem.name or "").lower():
                continue
            if automation_id and elem.automation_id != automation_id:
                continue
            if control_type and elem.control_type != control_type.lower():
                continue
            return elem
        return None

    def invoke_element(self, element: UIElement) -> bool:
        """Invoke an AT-SPI action."""
        if element.raw is None:
            return False
        try:
            atspi_ref = element.raw.get("_atspi_ref")
            if atspi_ref is None:
                return False
            # Try Action interface
            from gi.repository import Atspi

            action = Atspi.Action
            n_actions = action.get_n_actions(atspi_ref)
            if n_actions > 0:
                action.do_action(atspi_ref, 0)
                return True
        except Exception as exc:
            logger.debug("AT-SPI invoke failed: %s", exc)
        return False

    def set_element_value(self, element: UIElement, value: str) -> bool:
        """Set text via AT-SPI Value or Text interface."""
        if element.raw is None:
            return False
        try:
            atspi_ref = element.raw.get("_atspi_ref")
            if atspi_ref is None:
                return False
            from gi.repository import Atspi

            # Try Text interface
            text_iface = Atspi.Text
            text_iface.set_text_contents(atspi_ref, value)
            return True
        except Exception as exc:
            logger.debug("AT-SPI set_value failed: %s", exc)
        return False

    # ── Internal helpers ────────────────────────────────────────────────

    def _walk_atspi(
        self,
        node: Any,
        elements: list[UIElement],
        depth: int,
        max_depth: int,
    ) -> None:
        """Walk the AT-SPI tree recursively."""
        if depth > max_depth:
            return
        try:
            elem = self._atspi_to_element(node)
            if elem.name or elem.control_type != "unknown":
                elements.append(elem)
            for i in range(node.get_child_count()):
                child = node.get_child_at_index(i)
                if child is not None:
                    self._walk_atspi(child, elements, depth + 1, max_depth)
        except Exception:
            logger.debug("AT-SPI tree walk raised exception", exc_info=True)

    def _atspi_to_element(self, node: Any) -> UIElement:
        """Convert an AT-SPI node to UIElement."""
        try:
            from gi.repository import Atspi

            role = node.get_role()
            role_name = Atspi.Role.get_name(role).lower() if role else "unknown"
        except Exception:
            role_name = "unknown"

        try:
            ext = node.get_extents(Atspi.CoordType.SCREEN)
            box = (ext.x, ext.y, ext.width, ext.height)
        except Exception:
            box = None

        # Determine available actions
        actions: list[str] = []
        try:
            from gi.repository import Atspi

            action = Atspi.Action
            n = action.get_n_actions(node)
            if n > 0:
                actions.append("invoke")
        except Exception:
            logger.debug("AT-SPI action detection raised exception", exc_info=True)

        return UIElement(
            name=node.get_name() or "",
            control_type=role_name,
            bounding_box=box,
            enabled=True,  # AT-SPI doesn't have a simple enabled check
            value=self._get_atspi_value(node),
            automation_id=node.get_description() or None,
            actions=actions,
            raw={"_atspi_ref": node},
        )

    @staticmethod
    def _get_atspi_value(node: Any) -> str | None:
        """Try to get the text content of an AT-SPI node."""
        try:
            from gi.repository import Atspi

            text_iface = Atspi.Text
            text = text_iface.get_text(node, 0, -1)
            return text if text else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Linux Stealth Input Backend (xdotool / XTest)
# ---------------------------------------------------------------------------


class LinuxStealthInput(StealthInputBackend):
    """xdotool-based stealth input for Linux X11.

    Uses ``xdotool`` to send mouse/keyboard events to specific windows
    without necessarily moving the visible cursor (where possible).
    On Wayland, falls back to ``ydotool`` or physical input.
    """

    def __init__(self) -> None:
        self._available = _probe_xdotool()
        self._is_wayland = os.environ.get("XDG_SESSION_TYPE", "") == "wayland"

    def is_available(self) -> bool:
        return self._available and not self._is_wayland

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
        """Click via xdotool window activate + click."""
        if not self._available:
            return False
        try:
            btn_map = {"left": "1", "middle": "2", "right": "3"}
            btn = btn_map.get(button, "1")
            for _ in range(max(1, clicks)):
                subprocess.run(
                    ["xdotool", "mousemove", "--sync", str(x), str(y), "click", btn],
                    capture_output=True,
                    timeout=5,
                )
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool click failed: %s", exc)
            return False

    def type_text(self, text: str) -> bool:
        """Type text via xdotool."""
        if not self._available or not text:
            return False
        try:
            subprocess.run(
                ["xdotool", "type", "--delay", "5", text],
                capture_output=True,
                timeout=30,
            )
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool type failed: %s", exc)
            return False

    def press_key(self, key: str) -> bool:
        """Press a key via xdotool."""
        if not self._available:
            return False
        try:
            xdo_key = self._to_xdotool_key(key)
            subprocess.run(
                ["xdotool", "key", xdo_key],
                capture_output=True,
                timeout=5,
            )
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool key failed: %s", exc)
            return False

    def hotkey(self, *keys: str) -> bool:
        """Send chorded hotkey via xdotool."""
        if not self._available or not keys:
            return False
        try:
            combo = "+".join(self._to_xdotool_key(k) for k in keys)
            subprocess.run(
                ["xdotool", "key", combo],
                capture_output=True,
                timeout=5,
            )
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool hotkey failed: %s", exc)
            return False

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> bool:
        """Scroll via xdotool."""
        if not self._available:
            return False
        try:
            if x is not None and y is not None:
                subprocess.run(
                    ["xdotool", "mousemove", str(x), str(y)],
                    capture_output=True,
                    timeout=5,
                )
            # xdotool click 4 = scroll up, 5 = scroll down
            btn = "4" if amount > 0 else "5"
            count = min(abs(amount), 20)  # Cap scroll amount
            for _ in range(count):
                subprocess.run(
                    ["xdotool", "click", btn],
                    capture_output=True,
                    timeout=3,
                )
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool scroll failed: %s", exc)
            return False

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> bool:
        """Move the cursor to (x, y) via xdotool.

        duration > 0 requests an animated move (xdotool --delay between steps);
        duration == 0 is an instant teleport.
        """
        if not self._available:
            return False
        try:
            args = ["xdotool", "mousemove", "--sync", str(x), str(y)]
            if duration > 0:
                # ~step ms; xdotool doesn't take a total-duration, so approximate.
                args = [
                    "xdotool", "mousemove", "--sync",
                    "--delay", str(max(1, int(duration * 1000 / 20))),
                    str(x), str(y),
                ]
            subprocess.run(args, capture_output=True, timeout=10)
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool moveTo failed: %s", exc)
            return False

    def position(self) -> tuple[int, int]:
        """Return current cursor (x, y) via xdotool getmouselocation."""
        if not self._available:
            return (0, 0)
        try:
            r = subprocess.run(
                ["xdotool", "getmouselocation"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0 or not r.stdout.strip():
                return (0, 0)
            # Output: "x:123 y:456 screen:0 window:42"
            parts = {}
            for tok in r.stdout.split():
                if ":" in tok:
                    k, _, v = tok.partition(":")
                    parts[k] = v
            return (int(parts.get("x", 0)), int(parts.get("y", 0)))
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            logger.debug("xdotool position failed: %s", exc)
            return (0, 0)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> bool:
        """Drag from (x1, y1) to (x2, y2) via xdotool mousedown+mousemove+mouseup."""
        if not self._available:
            return False
        btn_map = {"left": "1", "middle": "2", "right": "3"}
        btn = btn_map.get(button, "1")
        try:
            # Move to start, press, move to end, release.
            subprocess.run(
                ["xdotool", "mousemove", "--sync", str(x1), str(y1)],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["xdotool", "mousedown", btn],
                capture_output=True, timeout=5,
            )
            if duration > 0:
                subprocess.run(
                    ["xdotool", "mousemove", "--sync",
                     "--delay", str(max(1, int(duration * 1000 / 20))),
                     str(x2), str(y2)],
                    capture_output=True, timeout=10,
                )
            else:
                subprocess.run(
                    ["xdotool", "mousemove", "--sync", str(x2), str(y2)],
                    capture_output=True, timeout=5,
                )
            subprocess.run(
                ["xdotool", "mouseup", btn],
                capture_output=True, timeout=5,
            )
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("xdotool drag failed: %s", exc)
            return False

    def screenshot(self):
        """Capture the full screen via mss; fall back to a blank PIL image."""
        try:
            import mss
            from PIL import Image
        except ImportError:
            from PIL import Image
            return Image.new("RGB", (1920, 1080))
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.debug("mss screenshot failed: %s", exc)
            from PIL import Image
            return Image.new("RGB", (1920, 1080))

    def rightClick(self, x: int, y: int, clicks: int = 1) -> bool:
        """Right-click at (x, y) via xdotool."""
        return self.click(x, y, button="right", clicks=clicks)

    def doubleClick(self, x: int, y: int) -> bool:
        """Double-click at (x, y) via xdotool."""
        return self.click(x, y, button="left", clicks=2)

    @staticmethod
    def _to_xdotool_key(key: str) -> str:
        """Map common key names to xdotool key names."""
        mapping = {
            "enter": "Return",
            "return": "Return",
            "tab": "Tab",
            "escape": "Escape",
            "esc": "Escape",
            "space": "space",
            "backspace": "BackSpace",
            "delete": "Delete",
            "insert": "Insert",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            "home": "Home",
            "end": "End",
            "pageup": "Page_Up",
            "pagedown": "Page_Down",
            "ctrl": "ctrl",
            "control": "ctrl",
            "shift": "shift",
            "alt": "alt",
            "super": "super",
            "win": "super",
            "meta": "super",
        }
        k = (key or "").lower()
        if k in mapping:
            return mapping[k]
        if k.startswith("f") and k[1:].isdigit():
            return k.upper()  # f1 → F1
        return key


# ---------------------------------------------------------------------------
# Linux Credential Backend (libsecret/secretstorage)
# ---------------------------------------------------------------------------


class LinuxCredentialBackend(CredentialBackend):
    """libsecret-backed credential storage for Linux.

    Uses the ``secretstorage`` Python package to store credentials in the
    system keyring (GNOME Keyring / KDE Wallet). Falls back to an
    encrypted file if secretstorage is unavailable.
    """

    _COLLECTION = "sentinel_desktop"

    def __init__(self) -> None:
        self._use_secretstorage = _probe_secretstorage()
        self._file_path = Path("config/vault.json")
        self._lock = threading.RLock()
        self._file_data: dict[str, Any] = self._load_file()

    def store(self, key: str, value: str) -> bool:
        if self._use_secretstorage:
            return self._store_secretstorage(key, value)
        return self._store_file(key, value)

    def retrieve(self, key: str) -> str | None:
        if self._use_secretstorage:
            return self._retrieve_secretstorage(key)
        return self._retrieve_file(key)

    def delete(self, key: str) -> bool:
        if self._use_secretstorage:
            return self._delete_secretstorage(key)
        return self._delete_file(key)

    def list_keys(self) -> list[str]:
        if self._use_secretstorage:
            return self._list_secretstorage()
        return self._list_file()

    # ── secretstorage implementation ────────────────────────────────────

    def _store_secretstorage(self, key: str, value: str) -> bool:
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            if collection.is_locked():
                collection.unlock()
            attrs = {"application": "sentinel-desktop", "key": key}
            collection.create_item(key, attrs, value.encode(), replace=True)
            return True
        except Exception as exc:
            logger.debug("secretstorage store failed: %s", exc)
            return self._store_file(key, value)

    def _retrieve_secretstorage(self, key: str) -> str | None:
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            if collection.is_locked():
                collection.unlock()
            attrs = {"application": "sentinel-desktop", "key": key}
            items = collection.search_items(attrs)
            for item in items:
                return item.get_secret().decode("utf-8")
        except Exception as exc:
            logger.debug("secretstorage retrieve failed: %s", exc)
        return self._retrieve_file(key)

    def _delete_secretstorage(self, key: str) -> bool:
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            if collection.is_locked():
                collection.unlock()
            attrs = {"application": "sentinel-desktop", "key": key}
            items = collection.search_items(attrs)
            for item in items:
                item.delete()
                return True
        except Exception as exc:
            logger.debug("secretstorage delete failed: %s", exc)
        return self._delete_file(key)

    def _list_secretstorage(self) -> list[str]:
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            if collection.is_locked():
                collection.unlock()
            keys = []
            for item in collection.get_all_items():
                attrs = item.get_attributes()
                if attrs.get("application") == "sentinel-desktop":
                    k = attrs.get("key", "")
                    if k:
                        keys.append(k)
            return sorted(keys)
        except Exception as exc:
            logger.debug("secretstorage list failed: %s", exc)
        return self._list_file()

    # ── File-based fallback ─────────────────────────────────────────────

    def _load_file(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return {"version": 1, "keys": {}}
        try:
            text = self._file_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict) and "keys" in data:
                return data
        except (OSError, json.JSONDecodeError):
            logger.debug("Failed to load credential file")
        return {"version": 1, "keys": {}}

    def _save_file(self) -> bool:
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic + owner-only write: the fallback vault stores credential
            # values, so a crash mid-save must not truncate it (lose every
            # stored cred) and it must not be world-readable (base64 values are
            # trivially decoded). The old code honored the umask (0644/0664).
            tmp = self._file_path.parent / f".vault-{uuid.uuid4().hex}.tmp"
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(self._file_data, indent=2) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            restrict_file_perms(tmp)
            tmp.replace(self._file_path)
            return True
        except OSError:
            return False

    def _store_file(self, key: str, value: str) -> bool:
        import base64

        with self._lock:
            self._file_data.setdefault("keys", {})[key] = {
                "encrypted": base64.b64encode(value.encode()).decode(),
                "created": self._iso_now(),
            }
            return self._save_file()

    def _retrieve_file(self, key: str) -> str | None:
        import base64

        with self._lock:
            entry = self._file_data.get("keys", {}).get(key)
            if entry is None:
                return None
            try:
                return base64.b64decode(entry["encrypted"]).decode("utf-8")
            except (ValueError, KeyError):
                return None

    def _delete_file(self, key: str) -> bool:
        with self._lock:
            keys = self._file_data.get("keys", {})
            if key not in keys:
                return False
            del keys[key]
            return self._save_file()

    def _list_file(self) -> list[str]:
        with self._lock:
            return sorted(self._file_data.get("keys", {}).keys())

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Linux Shell Backend (bash)
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS = (
    "rm -rf /",
    "rm -rf /*",
    ":(){ :|:& };:",
    "mkfs.",
    "dd if=/dev/zero",
    "> /dev/sda",
)


class LinuxShellBackend(ShellBackend):
    """Bash-based shell backend for Linux."""

    def execute(
        self,
        command: str,
        timeout: float = 60.0,
        capture: bool = True,
    ) -> dict[str, Any]:
        """Execute a command in bash."""
        sanitized = self.sanitize_command(command)
        try:
            result = subprocess.run(
                ["bash", "-c", sanitized],
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
        return "bash"

    def sanitize_command(self, command: str) -> str:
        lower = command.lower().strip()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in lower:
                raise ValueError(f"Command contains dangerous pattern: '{pattern}'")
        return command


# ---------------------------------------------------------------------------
# Linux Window Backend (wnck / xdotool)
# ---------------------------------------------------------------------------


class LinuxWindowBackend(WindowBackend):
    """Window management for Linux via libwnck or xdotool."""

    def __init__(self) -> None:
        self._has_wnck = _probe_wnck()
        self._has_xdotool = _probe_xdotool()

    def list_windows(self) -> list[WindowInfo]:
        """List all visible windows."""
        if self._has_wnck:
            return self._list_wnck()
        if self._has_xdotool:
            return self._list_xdotool()
        return []

    def focus_window(self, title: str) -> bool:
        """Focus a window by title."""
        if self._has_xdotool:
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--name", title, "windowactivate", "--sync"],
                    capture_output=True,
                    timeout=5,
                )
                return result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        if self._has_wnck:
            return self._focus_wnck(title)
        return False

    def close_window(self, title: str) -> bool:
        """Close a window by title."""
        if self._has_xdotool:
            try:
                # Find window ID, then close it
                result = subprocess.run(
                    ["xdotool", "search", "--name", title],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    wid = result.stdout.strip().split("\n")[0]
                    subprocess.run(
                        ["xdotool", "windowclose", wid],
                        capture_output=True,
                        timeout=5,
                    )
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
        return False

    def get_focused_window_rect(self) -> tuple[int, int, int, int] | None:
        """Get the focused window's geometry."""
        if self._has_xdotool:
            try:
                result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowgeometry", "--shell"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    geo = {}
                    for line in result.stdout.strip().split("\n"):
                        if "=" in line:
                            k, v = line.split("=", 1)
                            geo[k.strip()] = int(v.strip())
                    return (
                        geo.get("X", 0),
                        geo.get("Y", 0),
                        geo.get("WIDTH", 0),
                        geo.get("HEIGHT", 0),
                    )
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass
        return None

    def get_window_rect(self, title: str) -> tuple[int, int, int, int] | None:
        """Get a window's geometry by title."""
        for w in self.list_windows():
            if title.lower() in (w.title or "").lower():
                return (w.x, w.y, w.width, w.height)
        return None

    # ── Internal ────────────────────────────────────────────────────────

    def _list_wnck(self) -> list[WindowInfo]:
        """List windows via libwnck."""
        try:
            import gi

            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck

            screen = Wnck.Screen.get_default()
            if screen is None:
                return []
            screen.force_update()
            windows = []
            for win in screen.get_windows():
                if not win.is_skip_pager() and win.get_name():
                    geo = win.get_geometry()
                    windows.append(
                        WindowInfo(
                            title=win.get_name() or "",
                            x=geo[0],
                            y=geo[1],
                            width=geo[2],
                            height=geo[3],
                            is_focused=win.is_active(),
                            handle=win.get_xid(),
                        )
                    )
            return windows
        except Exception as exc:
            logger.debug("wnck list_windows failed: %s", exc)
            return []

    def _list_xdotool(self) -> list[WindowInfo]:
        """List windows via xdotool (fallback)."""
        windows: list[WindowInfo] = []
        try:
            # Get list of active window IDs
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
            for wid in result.stdout.strip().split("\n"):
                wid = wid.strip()
                if not wid:
                    continue
                try:
                    # Get window name
                    name_result = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    name = name_result.stdout.strip() if name_result.returncode == 0 else ""
                    if not name:
                        continue
                    # Get geometry
                    geo_result = subprocess.run(
                        ["xdotool", "getwindowgeometry", "--shell", wid],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    geo = {}
                    if geo_result.returncode == 0:
                        for line in geo_result.stdout.strip().split("\n"):
                            if "=" in line:
                                k, v = line.split("=", 1)
                                geo[k.strip()] = int(v.strip())
                    windows.append(
                        WindowInfo(
                            title=name,
                            x=geo.get("X", 0),
                            y=geo.get("Y", 0),
                            width=geo.get("WIDTH", 0),
                            height=geo.get("HEIGHT", 0),
                            handle=int(wid),
                        )
                    )
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    continue
        except (OSError, subprocess.TimeoutExpired):
            pass
        return windows

    def _focus_wnck(self, title: str) -> bool:
        """Focus window via wnck."""
        try:
            import gi

            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck

            screen = Wnck.Screen.get_default()
            if screen is None:
                return False
            screen.force_update()
            needle = title.lower()
            for win in screen.get_windows():
                if needle in (win.get_name() or "").lower():
                    win.activate(int.from_bytes(os.urandom(4), "big"))
                    return True
        except Exception as exc:
            logger.debug("wnck focus failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Linux Overlay Backend (X11 transparent windows or no-op)
# ---------------------------------------------------------------------------


class LinuxOverlayBackend(OverlayBackend):
    """Overlay for Linux — limited to X11 compositing, no-op on Wayland."""

    def is_available(self) -> bool:
        return os.environ.get("XDG_SESSION_TYPE", "") != "wayland"

    def show_ring(self, x: int, y: int, color: str = "#00F0FF", duration_ms: int = 420) -> None:
        """Show ring via a Python/Tkinter overlay window (X11)."""
        if not self.is_available():
            return
        try:
            import tkinter as tk

            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-transparentcolor", "black")
            root.geometry(f"80x80+{x - 40}+{y - 40}")
            canvas = tk.Canvas(root, width=80, height=80, bg="black", highlightthickness=0)
            canvas.create_oval(5, 5, 75, 75, outline=color, width=3)
            canvas.pack()
            root.after(duration_ms, root.destroy)
            root.mainloop()
        except Exception as exc:
            logger.debug("Linux overlay ring failed: %s", exc)

    def show_cursor_move(
        self, from_x: int, from_y: int, to_x: int, to_y: int, duration_ms: int = 300
    ) -> None:
        """Animate cursor via xdotool (basic: just moves, no animation)."""
        if self._has_xdotool():
            try:
                subprocess.run(
                    ["xdotool", "mousemove", "--sync", str(to_x), str(to_y)],
                    capture_output=True,
                    timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass

    @staticmethod
    def _has_xdotool() -> bool:
        return _probe_xdotool()


# ---------------------------------------------------------------------------
# Aggregated Linux Backend
# ---------------------------------------------------------------------------


class LinuxBackend(PlatformBackend):
    """Aggregated backend for Linux."""

    def __init__(self) -> None:
        self._accessibility = LinuxAccessibility()
        self._stealth = LinuxStealthInput()
        self._credentials = LinuxCredentialBackend()
        self._shell = LinuxShellBackend()
        self._window = LinuxWindowBackend()
        self._overlay = LinuxOverlayBackend()

    @property
    def accessibility(self) -> LinuxAccessibility:
        return self._accessibility

    @property
    def stealth(self) -> LinuxStealthInput:
        return self._stealth

    @property
    def input(self) -> LinuxStealthInput:
        """Alias for ``.stealth`` — the physical/stealth input surface.

        Callers (core.stealth_input, core.desktop) use ``backend.input.*`` so
        the code reads naturally; the underlying object is the same stealth
        input subsystem.
        """
        return self._stealth

    @property
    def credentials(self) -> LinuxCredentialBackend:
        return self._credentials

    @property
    def shell(self) -> LinuxShellBackend:
        return self._shell

    @property
    def window(self) -> LinuxWindowBackend:
        return self._window

    @property
    def overlay(self) -> LinuxOverlayBackend:
        return self._overlay

    @property
    def default_shell(self) -> str:
        return "bash"
