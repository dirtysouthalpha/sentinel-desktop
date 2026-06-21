"""Sentinel Desktop v4.0 — macOS Platform Backend.

Provides accessibility (NSAccessibility/AX), stealth input (AppleScript/
osascript), credentials (Keychain), shell (zsh), and window management
(AppleScript/System Events) for macOS.
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import threading
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

logger = logging.getLogger(__name__)

# ── Availability probes ─────────────────────────────────────────────────


def _probe_osascript() -> bool:
    """Check if osascript is available."""
    try:
        result = subprocess.run(
            ["osascript", "-e", 'return "ok"'],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _probe_applescript_accessibility() -> bool:
    """Check if System Events UI scripting is available."""
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return name of every process'],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _probe_security() -> bool:
    """Check if macOS security command (Keychain access) is available."""
    try:
        result = subprocess.run(
            ["security", "list-keychains"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _probe_pyobjc() -> bool:
    """Check if PyObjC (ApplicationServices/Quartz) is available."""
    try:
        import ApplicationServices  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# macOS Accessibility Backend (AppleScript / System Events)
# ---------------------------------------------------------------------------


class MacOSAccessibility(AccessibilityBackend):
    """AppleScript/System Events-based accessibility for macOS.

    Uses osascript to query the accessibility tree via System Events.
    Less powerful than a native AX API but doesn't require PyObjC.
    """

    def __init__(self) -> None:
        self._available = _probe_applescript_accessibility()

    def is_available(self) -> bool:
        return self._available

    def get_tree(self, window_title: str | None = None) -> list[UIElement]:
        """Query UI elements via System Events AppleScript."""
        if not self._available:
            return []
        try:
            if window_title:
                script = (
                    'tell application "System Events"\n'
                    f'    set targetWin to window 1 of process "{window_title}"\n'
                    '    set output to ""\n'
                    "    repeat with elem in (every UI element of targetWin)\n"
                    "        try\n"
                    '            set elemDesc to (description of elem) & "|" '
                    '                & (role of elem) & "|" '
                    '                & (name of elem) & "|" '
                    '                & (value of elem) & "|" '
                    '                & (position of elem) & "|" '
                    "                & (size of elem)\n"
                    "            set output to output & elemDesc & linefeed\n"
                    "        end try\n"
                    "    end repeat\n"
                    "    return output\n"
                    "end tell"
                )
            else:
                # Get frontmost app's front window
                script = (
                    'tell application "System Events"\n'
                    "    set frontApp to name of first process whose frontmost is true\n"
                    "    set targetWin to window 1 of process frontApp\n"
                    '    set output to ""\n'
                    "    repeat with elem in (every UI element of targetWin)\n"
                    "        try\n"
                    '            set elemDesc to (description of elem) & "|" '
                    '                & (role of elem) & "|" '
                    '                & (name of elem) & "|" '
                    '                & (value of elem) & "|" '
                    '                & (position of elem) & "|" '
                    "                & (size of elem)\n"
                    "            set output to output & elemDesc & linefeed\n"
                    "        end try\n"
                    "    end repeat\n"
                    "    return output\n"
                    "end tell"
                )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            return self._parse_applescript_elements(result.stdout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS accessibility get_tree failed: %s", exc)
            return []

    def find_element(
        self,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> UIElement | None:
        """Find an element by searching the tree."""
        elements = self.get_tree(window_title)
        for elem in elements:
            if name and name.lower() not in (elem.name or "").lower():
                continue
            if control_type and control_type.lower() not in elem.control_type.lower():
                continue
            if automation_id and elem.automation_id != automation_id:
                continue
            return elem
        return None

    def invoke_element(self, element: UIElement) -> bool:
        """Click a UI element via AppleScript."""
        if not self._available or not element.name:
            return False
        try:
            script = (
                'tell application "System Events"\n'
                "    click UI element whose name is "
                f'"{element.name}" of window 1 of frontmost process\n'
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS invoke failed: %s", exc)
        return False

    def set_element_value(self, element: UIElement, value: str) -> bool:
        """Set text value via AppleScript."""
        if not self._available or not element.name:
            return False
        try:
            script = (
                'tell application "System Events"\n'
                "    set value of text field whose name is "
                f'"{element.name}" of window 1 of frontmost process '
                f'to "{value}"\n'
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS set_value failed: %s", exc)
        return False

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_applescript_elements(output: str) -> list[UIElement]:
        """Parse AppleScript output into UIElement list."""
        elements: list[UIElement] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue
            desc, role, name, value, pos, size = parts[:6]
            box = None
            try:
                # Parse position {x, y} and size {w, h}
                pos_clean = pos.strip().strip("{}")
                size_clean = size.strip().strip("{}")
                px, py = [int(x.strip()) for x in pos_clean.split(",")]
                sw, sh = [int(x.strip()) for x in size_clean.split(",")]
                box = (px, py, sw, sh)
            except (ValueError, IndexError):
                pass

            # Normalize role
            role_clean = role.strip().lower()
            if "button" in role_clean:
                ct = "button"
            elif "text" in role_clean or "field" in role_clean:
                ct = "edit"
            elif "menu" in role_clean:
                ct = "menu"
            elif "check" in role_clean:
                ct = "checkbox"
            elif "radio" in role_clean:
                ct = "radio"
            elif "tab" in role_clean:
                ct = "tab"
            else:
                ct = role_clean

            actions: list[str] = []
            if ct in ("button", "checkbox", "radio"):
                actions.append("invoke")
            if ct == "edit":
                actions.append("set_value")

            elements.append(
                UIElement(
                    name=name.strip(),
                    control_type=ct,
                    bounding_box=box,
                    enabled=True,
                    value=value.strip() if value.strip() else None,
                    automation_id=desc.strip() or None,
                    actions=actions,
                )
            )
        return elements


# ---------------------------------------------------------------------------
# macOS Stealth Input Backend (AppleScript / cliclick)
# ---------------------------------------------------------------------------


class MacOSStealthInput(StealthInputBackend):
    """AppleScript/osascript-based stealth input for macOS.

    Uses AppleScript System Events for mouse/keyboard when possible.
    Falls back to ``cliclick`` if installed for more reliable input.
    """

    def __init__(self) -> None:
        self._has_osascript = _probe_osascript()

    def is_available(self) -> bool:
        return self._has_osascript

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
        """Click via AppleScript System Events."""
        if not self._has_osascript:
            return False
        try:
            btn = "" if button == "left" else " using {button button}"
            click_str = "click" if clicks == 1 else "double click"
            script = (
                f'tell application "System Events"\n    {click_str} at {{{x}, {y}}}{btn}\nend tell'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS stealth click failed: %s", exc)
            return False

    def type_text(self, text: str) -> bool:
        """Type text via AppleScript."""
        if not self._has_osascript or not text:
            return False
        try:
            # Escape quotes for AppleScript
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            script = f'tell application "System Events"\n    keystroke "{escaped}"\nend tell'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=15,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS stealth type failed: %s", exc)
            return False

    def press_key(self, key: str) -> bool:
        """Press a key via AppleScript."""
        if not self._has_osascript:
            return False
        try:
            key_code = self._to_applescript_key(key)
            script = f'tell application "System Events"\n    key code {key_code}\nend tell'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS stealth key failed: %s", exc)
            return False

    def hotkey(self, *keys: str) -> bool:
        """Send chorded hotkey via AppleScript."""
        if not self._has_osascript or not keys:
            return False
        try:
            modifiers = []
            main_key = ""
            for k in keys:
                k_lower = k.lower()
                if k_lower in ("ctrl", "control"):
                    modifiers.append("control down")
                elif k_lower == "shift":
                    modifiers.append("shift down")
                elif k_lower in ("alt", "option"):
                    modifiers.append("option down")
                elif k_lower in ("cmd", "command"):
                    modifiers.append("command down")
                else:
                    main_key = k

            using = ", ".join(modifiers)
            if main_key:
                using = f" using {{{using}}}" if using else ""
                script = (
                    f'tell application "System Events"\n    keystroke "{main_key}"{using}\nend tell'
                )
            else:
                return False

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS stealth hotkey failed: %s", exc)
            return False

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> bool:
        """Scroll via AppleScript."""
        if not self._has_osascript:
            return False
        try:
            direction = "down" if amount < 0 else "up"
            count = min(abs(amount), 20)
            lines = []
            for _ in range(count):
                lines.append(f'    scroll 1 in direction "{direction}"')
            script = 'tell application "System Events"\n' + "\n".join(lines) + "\n" + "end tell"
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    # ── Phase A v23 extensions: satisfy BackendProtocol ──────────────────
    # These delegate to pyautogui (the macOS native input lib via Quartz).
    # They exist so MacOSStealthInput satisfies core.platform.backend.
    # BackendProtocol — DesktopController may route through them on macOS.

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> bool:
        """Move the cursor to (x, y) via pyautogui."""
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return True
        except Exception as exc:  # noqa: BLE001 — never crash input
            logger.debug("MacOSStealthInput.moveTo failed: %s", exc)
            return False

    def position(self) -> tuple[int, int]:
        """Return current cursor (x, y) via pyautogui."""
        try:
            import pyautogui
            pos = pyautogui.position()
            return (int(pos.x), int(pos.y))
        except Exception as exc:  # noqa: BLE001
            logger.debug("MacOSStealthInput.position failed: %s", exc)
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
        """Drag from (x1, y1) to (x2, y2) via pyautogui."""
        try:
            import pyautogui
            pyautogui.moveTo(x1, y1)
            pyautogui.dragTo(x2, y2, duration=duration, button=button)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("MacOSStealthInput.drag failed: %s", exc)
            return False

    def screenshot(self):
        """Capture the full screen via pyautogui (PIL.Image)."""
        try:
            import pyautogui
            return pyautogui.screenshot()
        except Exception as exc:  # noqa: BLE001
            logger.debug("MacOSStealthInput.screenshot failed: %s", exc)
            from PIL import Image
            return Image.new("RGB", (1920, 1080))

    def rightClick(self, x: int, y: int, clicks: int = 1) -> bool:
        """Right-click at (x, y) via pyautogui."""
        try:
            import pyautogui
            for _ in range(max(1, clicks)):
                pyautogui.rightClick(x, y)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("MacOSStealthInput.rightClick failed: %s", exc)
            return False

    def doubleClick(self, x: int, y: int) -> bool:
        """Double-click at (x, y) via pyautogui."""
        try:
            import pyautogui
            pyautogui.doubleClick(x, y)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("MacOSStealthInput.doubleClick failed: %s", exc)
            return False

    @staticmethod
    def _to_applescript_key(key: str) -> int:
        """Map key names to macOS key codes."""
        key_codes = {
            "enter": 36,
            "return": 36,
            "tab": 48,
            "escape": 53,
            "esc": 53,
            "space": 49,
            "backspace": 51,
            "delete": 51,
            "up": 126,
            "down": 125,
            "left": 123,
            "right": 124,
            "home": 115,
            "end": 119,
            "pageup": 116,
            "pagedown": 121,
            "f1": 122,
            "f2": 120,
            "f3": 99,
            "f4": 118,
            "f5": 96,
            "f6": 97,
            "f7": 98,
            "f8": 100,
            "f9": 101,
            "f10": 109,
            "f11": 103,
            "f12": 111,
        }
        k = (key or "").lower()
        if k in key_codes:
            return key_codes[k]
        if len(key) == 1:
            return ord(key.upper()) - 32  # rough ASCII→key code
        return 0


# ---------------------------------------------------------------------------
# macOS Credential Backend (Keychain)
# ---------------------------------------------------------------------------


class MacOSCredentialBackend(CredentialBackend):
    """macOS Keychain-backed credential storage.

    Uses the ``security`` command-line tool to store/retrieve passwords
    in the macOS Keychain. Falls back to file-based storage if Keychain
    is unavailable.
    """

    _SERVICE = "sentinel-desktop"

    def __init__(self) -> None:
        self._has_security = _probe_security()
        self._file_path = Path("config/vault.json")
        self._lock = threading.RLock()
        self._file_data: dict[str, Any] = self._load_file()

    def store(self, key: str, value: str) -> bool:
        if self._has_security:
            return self._store_keychain(key, value)
        return self._store_file(key, value)

    def retrieve(self, key: str) -> str | None:
        if self._has_security:
            return self._retrieve_keychain(key)
        return self._retrieve_file(key)

    def delete(self, key: str) -> bool:
        if self._has_security:
            return self._delete_keychain(key)
        return self._delete_file(key)

    def list_keys(self) -> list[str]:
        if self._has_security:
            return self._list_keychain()
        return self._list_file()

    # ── Keychain ────────────────────────────────────────────────────────

    def _store_keychain(self, key: str, value: str) -> bool:
        try:
            # Delete existing first (security add-generic-password fails on duplicate)
            self._delete_keychain(key)
            result = subprocess.run(
                ["security", "add-generic-password", "-a", key, "-s", self._SERVICE, "-w", value],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("Keychain store failed: %s", exc)
            return self._store_file(key, value)

    def _retrieve_keychain(self, key: str) -> str | None:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-a", key, "-s", self._SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return self._retrieve_file(key)

    def _delete_keychain(self, key: str) -> bool:
        try:
            result = subprocess.run(
                ["security", "delete-generic-password", "-a", key, "-s", self._SERVICE],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _list_keychain(self) -> list[str]:
        try:
            result = subprocess.run(
                ["security", "dump-keychain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            keys = []
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if self._SERVICE in line and "acct" in line:
                        # Parse "acct"<blob>="key_name"
                        import re

                        match = re.search(r'"acct"<blob>="([^"]+)"', line)
                        if match:
                            keys.append(match.group(1))
            return sorted(keys)
        except (OSError, subprocess.TimeoutExpired):
            return self._list_file()

    # ── File fallback ───────────────────────────────────────────────────

    def _load_file(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return {"version": 1, "keys": {}}
        try:
            text = self._file_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict) and "keys" in data:
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": 1, "keys": {}}

    def _save_file(self) -> bool:
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(
                json.dumps(self._file_data, indent=2) + "\n",
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def _store_file(self, key: str, value: str) -> bool:
        with self._lock:
            self._file_data.setdefault("keys", {})[key] = {
                "encrypted": base64.b64encode(value.encode()).decode(),
                "created": self._iso_now(),
            }
            return self._save_file()

    def _retrieve_file(self, key: str) -> str | None:
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
# macOS Shell Backend (zsh)
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS = (
    "rm -rf /",
    "rm -rf /*",
    ":(){ :|:& };:",
    "mkfs.",
    "dd if=/dev/zero",
)


class MacOSShellBackend(ShellBackend):
    """zsh-based shell backend for macOS."""

    def execute(
        self,
        command: str,
        timeout: float = 60.0,
        capture: bool = True,
    ) -> dict[str, Any]:
        """Execute a command in zsh."""
        sanitized = self.sanitize_command(command)
        try:
            result = subprocess.run(
                ["zsh", "-c", sanitized],
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
        return "zsh"

    def sanitize_command(self, command: str) -> str:
        lower = command.lower().strip()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in lower:
                raise ValueError(f"Command contains dangerous pattern: '{pattern}'")
        return command


# ---------------------------------------------------------------------------
# macOS Window Backend (AppleScript)
# ---------------------------------------------------------------------------


class MacOSWindowBackend(WindowBackend):
    """AppleScript-based window management for macOS."""

    def __init__(self) -> None:
        self._has_osascript = _probe_osascript()

    def list_windows(self) -> list[WindowInfo]:
        """List windows via AppleScript."""
        if not self._has_osascript:
            return []
        try:
            script = (
                'tell application "System Events"\n'
                '    set output to ""\n'
                "    repeat with p in (every process whose background only is false)\n"
                "        try\n"
                "            repeat with w in (every window of p)\n"
                "                set winName to name of w\n"
                "                set winPos to position of w\n"
                "                set winSize to size of w\n"
                '                set output to output & winName & "|" '
                '                    & (item 1 of winPos) & "," '
                '                    & (item 2 of winPos) & "|" '
                '                    & (item 1 of winSize) & "," '
                "                    & (item 2 of winSize) & linefeed\n"
                "            end repeat\n"
                "        end try\n"
                "    end repeat\n"
                "    return output\n"
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            return self._parse_window_list(result.stdout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("macOS list_windows failed: %s", exc)
            return []

    def focus_window(self, title: str) -> bool:
        """Focus a window by title via AppleScript."""
        if not self._has_osascript:
            return False
        try:
            escaped = title.replace('"', '\\"')
            script = (
                'tell application "System Events"\n'
                "    set frontmost of (every process whose windows contains "
                f'        (every window whose name contains "{escaped}")) to true\n'
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def close_window(self, title: str) -> bool:
        """Close a window via AppleScript."""
        if not self._has_osascript:
            return False
        try:
            escaped = title.replace('"', '\\"')
            script = (
                'tell application "System Events"\n'
                f"    click (first button of (every window whose name contains "
                f'        "{escaped}") whose subrole is "AXCloseButton")\n'
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def get_focused_window_rect(self) -> tuple[int, int, int, int] | None:
        """Get focused window geometry."""
        if not self._has_osascript:
            return None
        try:
            script = (
                'tell application "System Events"\n'
                "    set frontApp to name of first process whose frontmost is true\n"
                "    tell process frontApp\n"
                "        set winPos to position of window 1\n"
                "        set winSize to size of window 1\n"
                '        return (item 1 of winPos) & "," & (item 2 of winPos) '
                '            & "," & (item 1 of winSize) & "," & (item 2 of winSize)\n'
                "    end tell\n"
                "end tell"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) == 4:
                    return tuple(int(p.strip()) for p in parts)  # type: ignore[return-value]
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        return None

    def get_window_rect(self, title: str) -> tuple[int, int, int, int] | None:
        """Get a window's geometry by title."""
        for w in self.list_windows():
            if title.lower() in (w.title or "").lower():
                return (w.x, w.y, w.width, w.height)
        return None

    @staticmethod
    def _parse_window_list(output: str) -> list[WindowInfo]:
        """Parse AppleScript window list output."""
        windows: list[WindowInfo] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            if len(parts) < 3:
                continue
            try:
                title = parts[0].strip()
                x, y = [int(v.strip()) for v in parts[1].split(",")]
                w, h = [int(v.strip()) for v in parts[2].split(",")]
                windows.append(WindowInfo(title=title, x=x, y=y, width=w, height=h))
            except (ValueError, IndexError):
                continue
        return windows


# ---------------------------------------------------------------------------
# macOS Overlay Backend
# ---------------------------------------------------------------------------


class MacOSOverlayBackend(OverlayBackend):
    """Transparent overlay for macOS via NSWindow / Tkinter."""

    def is_available(self) -> bool:
        return _probe_osascript()

    def show_ring(self, x: int, y: int, color: str = "#00F0FF", duration_ms: int = 420) -> None:
        """Show ring via a Tkinter overlay."""
        try:
            import tkinter as tk

            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.geometry(f"80x80+{x - 40}+{y - 40}")
            canvas = tk.Canvas(root, width=80, height=80, highlightthickness=0)
            canvas.create_oval(5, 5, 75, 75, outline=color, width=3)
            canvas.pack()
            root.after(duration_ms, root.destroy)
            root.mainloop()
        except Exception as exc:
            logger.debug("macOS overlay ring failed: %s", exc)

    def show_cursor_move(
        self, from_x: int, from_y: int, to_x: int, to_y: int, duration_ms: int = 300
    ) -> None:
        """Move cursor via AppleScript."""
        try:
            script = (
                f'tell application "System Events"\n    set cursor to {{{to_x}, {to_y}}}\nend tell'
            )
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


# ---------------------------------------------------------------------------
# Aggregated macOS Backend
# ---------------------------------------------------------------------------


class MacOSBackend(PlatformBackend):
    """Aggregated backend for macOS."""

    def __init__(self) -> None:
        self._accessibility = MacOSAccessibility()
        self._stealth = MacOSStealthInput()
        self._credentials = MacOSCredentialBackend()
        self._shell = MacOSShellBackend()
        self._window = MacOSWindowBackend()
        self._overlay = MacOSOverlayBackend()

    @property
    def accessibility(self) -> MacOSAccessibility:
        return self._accessibility

    @property
    def stealth(self) -> MacOSStealthInput:
        return self._stealth

    @property
    def input(self) -> MacOSStealthInput:
        """Alias for ``.stealth`` — the physical/stealth input surface.

        Callers (core.stealth_input, core.desktop) use ``backend.input.*`` so
        the code reads naturally; the underlying object is the same stealth
        input subsystem.
        """
        return self._stealth

    @property
    def credentials(self) -> MacOSCredentialBackend:
        return self._credentials

    @property
    def shell(self) -> MacOSShellBackend:
        return self._shell

    @property
    def window(self) -> MacOSWindowBackend:
        return self._window

    @property
    def overlay(self) -> MacOSOverlayBackend:
        return self._overlay

    @property
    def default_shell(self) -> str:
        return "zsh"
