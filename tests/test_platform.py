"""Tests for the v4.0 Platform Abstraction Layer (core/platform/).

Covers:
- Platform detection
- Backend factory
- Abstract base classes and no-op fallback
- Windows backend structure
- Linux backend structure
- macOS backend structure
"""

from __future__ import annotations

import platform
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


class TestPlatformDetection:
    """Test platform detection utilities."""

    def test_current_platform_returns_string(self):
        from core.platform import current_platform
        result = current_platform()
        assert isinstance(result, str)
        assert result in ("windows", "linux", "macos", "unknown")

    def test_current_platform_matches_system(self):
        from core.platform import current_platform
        system = platform.system()
        expected = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(system, "unknown")
        assert current_platform() == expected

    def test_is_windows_on_windows(self):
        from core.platform import is_windows
        if platform.system() == "Windows":
            assert is_windows() is True
        else:
            assert is_windows() is False

    def test_is_linux_on_linux(self):
        from core.platform import is_linux
        if platform.system() == "Linux":
            assert is_linux() is True
        else:
            assert is_linux() is False

    def test_is_macos_on_macos(self):
        from core.platform import is_macos
        if platform.system() == "Darwin":
            assert is_macos() is True
        else:
            assert is_macos() is False


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------


class TestBackendFactory:
    """Test get_backend() returns correct backend for platform."""

    def test_get_backend_returns_backend_object(self):
        from core.platform import get_backend, reset_backend
        reset_backend()
        backend = get_backend()
        assert backend is not None
        # Should have all subsystem properties
        assert hasattr(backend, "accessibility")
        assert hasattr(backend, "stealth")
        assert hasattr(backend, "credentials")
        assert hasattr(backend, "shell")
        assert hasattr(backend, "window")
        assert hasattr(backend, "overlay")
        reset_backend()

    def test_get_backend_caches_result(self):
        from core.platform import get_backend, reset_backend
        reset_backend()
        b1 = get_backend()
        b2 = get_backend()
        assert b1 is b2
        reset_backend()

    def test_reset_backend_clears_cache(self):
        from core.platform import get_backend, reset_backend
        reset_backend()
        b1 = get_backend()
        reset_backend()
        b2 = get_backend()
        assert b1 is not b2
        reset_backend()

    @patch("core.platform._SYSTEM", "Windows")
    def test_windows_creates_windows_backend(self):
        from core.platform import _create_backend, reset_backend
        reset_backend()
        # Import after patch so the module picks up the mock
        from core.platform.windows_backend import WindowsBackend
        backend = _create_backend()
        assert isinstance(backend, WindowsBackend)
        reset_backend()

    @patch("core.platform._SYSTEM", "Linux")
    def test_linux_creates_linux_backend(self):
        from core.platform import _create_backend, reset_backend
        reset_backend()
        from core.platform.linux_backend import LinuxBackend
        backend = _create_backend()
        assert isinstance(backend, LinuxBackend)
        reset_backend()

    @patch("core.platform._SYSTEM", "Darwin")
    def test_macos_creates_macos_backend(self):
        from core.platform import _create_backend, reset_backend
        reset_backend()
        from core.platform.macos_backend import MacOSBackend
        backend = _create_backend()
        assert isinstance(backend, MacOSBackend)
        reset_backend()

    @patch("core.platform._SYSTEM", "FreeBSD")
    def test_unknown_creates_noop_backend(self):
        from core.platform import _create_backend, reset_backend
        from core.platform.base import NoOpBackend
        reset_backend()
        backend = _create_backend()
        assert isinstance(backend, NoOpBackend)
        reset_backend()


# ---------------------------------------------------------------------------
# Base types
# ---------------------------------------------------------------------------


class TestUIElement:
    """Test the UIElement data class."""

    def test_default_construction(self):
        from core.platform.base import UIElement
        elem = UIElement()
        assert elem.name == ""
        assert elem.control_type == "unknown"
        assert elem.bounding_box is None
        assert elem.enabled is True
        assert elem.value is None
        assert elem.automation_id is None
        assert elem.actions == []
        assert elem.children == []
        assert elem.raw == {}

    def test_full_construction(self):
        from core.platform.base import UIElement
        elem = UIElement(
            name="Save",
            control_type="button",
            bounding_box=(100, 200, 80, 30),
            enabled=True,
            value=None,
            automation_id="btnSave",
            actions=["invoke"],
        )
        assert elem.name == "Save"
        assert elem.control_type == "button"
        assert elem.bounding_box == (100, 200, 80, 30)
        assert elem.automation_id == "btnSave"

    def test_to_dict(self):
        from core.platform.base import UIElement
        elem = UIElement(name="OK", control_type="button", bounding_box=(10, 20, 50, 30))
        d = elem.to_dict()
        assert d["name"] == "OK"
        assert d["type"] == "button"
        assert "bounds" in d
        assert d["bounds"]["x"] == 10

    def test_to_dict_minimal(self):
        from core.platform.base import UIElement
        elem = UIElement()
        d = elem.to_dict()
        assert "name" in d
        assert "type" in d
        assert "bounds" not in d
        assert "value" not in d


class TestWindowInfo:
    """Test the WindowInfo data class."""

    def test_default_construction(self):
        from core.platform.base import WindowInfo
        w = WindowInfo()
        assert w.title == ""
        assert w.x == 0
        assert w.width == 0
        assert w.handle is None

    def test_to_dict(self):
        from core.platform.base import WindowInfo
        w = WindowInfo(title="Chrome", x=100, y=50, width=800, height=600, is_focused=True, handle=12345)
        d = w.to_dict()
        assert d["title"] == "Chrome"
        assert d["x"] == 100
        assert d["width"] == 800
        assert d["is_focused"] is True
        assert d["handle"] == 12345


# ---------------------------------------------------------------------------
# No-op backend (used for unknown platforms)
# ---------------------------------------------------------------------------


class TestNoOpBackend:
    """Test that the no-op backend gracefully handles everything."""

    def test_accessibility_noop(self):
        from core.platform.base import NoOpAccessibility
        acc = NoOpAccessibility()
        assert acc.is_available() is False
        assert acc.get_tree() == []
        assert acc.find_element(name="test") is None
        assert acc.invoke_element(None) is False

    def test_stealth_noop(self):
        from core.platform.base import NoOpStealthInput
        stealth = NoOpStealthInput()
        assert stealth.is_available() is False
        assert stealth.click(0, 0) is False
        assert stealth.type_text("test") is False
        assert stealth.press_key("enter") is False
        assert stealth.hotkey("ctrl", "c") is False
        assert stealth.scroll(1) is False

    def test_credential_noop(self):
        from core.platform.base import NoOpCredential
        cred = NoOpCredential()
        assert cred.store("key", "val") is False
        assert cred.retrieve("key") is None
        assert cred.delete("key") is False
        assert cred.list_keys() == []

    def test_window_noop(self):
        from core.platform.base import NoOpWindow
        win = NoOpWindow()
        assert win.list_windows() == []
        assert win.focus_window("test") is False
        assert win.close_window("test") is False
        assert win.get_focused_window_rect() is None
        assert win.get_window_rect("test") is None

    def test_overlay_noop(self):
        from core.platform.base import NoOpOverlay
        overlay = NoOpOverlay()
        assert overlay.is_available() is False
        # These should not raise
        overlay.show_ring(0, 0)
        overlay.show_cursor_move(0, 0, 100, 100)

    def test_aggregated_noop_backend(self):
        from core.platform.base import NoOpBackend
        backend = NoOpBackend()
        assert backend.default_shell == "sh"
        assert backend.accessibility.is_available() is False
        assert backend.stealth.is_available() is False


# ---------------------------------------------------------------------------
# Windows backend structure
# ---------------------------------------------------------------------------


class TestWindowsBackendStructure:
    """Test Windows backend has correct subsystems."""

    def test_has_all_subsystems(self):
        from core.platform.windows_backend import WindowsBackend
        backend = WindowsBackend()
        assert backend.accessibility is not None
        assert backend.stealth is not None
        assert backend.credentials is not None
        assert backend.shell is not None
        assert backend.window is not None
        assert backend.overlay is not None

    def test_default_shell(self):
        from core.platform.windows_backend import WindowsBackend
        backend = WindowsBackend()
        # On Windows with PowerShell, should return 'powershell'
        shell = backend.default_shell
        assert shell in ("powershell", "cmd")

    def test_shell_sanitization_blocks_dangerous(self):
        from core.platform.windows_backend import WindowsShellBackend
        shell = WindowsShellBackend()
        with pytest.raises(ValueError, match="dangerous"):
            shell.sanitize_command("del /f /s /q c:\\")

    def test_shell_sanitization_allows_safe(self):
        from core.platform.windows_backend import WindowsShellBackend
        shell = WindowsShellBackend()
        result = shell.sanitize_command("Get-Process | Select-Object -First 5")
        assert result == "Get-Process | Select-Object -First 5"


# ---------------------------------------------------------------------------
# Linux backend structure
# ---------------------------------------------------------------------------


class TestLinuxBackendStructure:
    """Test Linux backend has correct subsystems."""

    def test_has_all_subsystems(self):
        from core.platform.linux_backend import LinuxBackend
        backend = LinuxBackend()
        assert backend.accessibility is not None
        assert backend.stealth is not None
        assert backend.credentials is not None
        assert backend.shell is not None
        assert backend.window is not None
        assert backend.overlay is not None

    def test_default_shell(self):
        from core.platform.linux_backend import LinuxBackend
        backend = LinuxBackend()
        assert backend.default_shell == "bash"

    def test_shell_sanitization_blocks_dangerous(self):
        from core.platform.linux_backend import LinuxShellBackend
        shell = LinuxShellBackend()
        with pytest.raises(ValueError, match="dangerous"):
            shell.sanitize_command("rm -rf /")

    def test_shell_sanitization_allows_safe(self):
        from core.platform.linux_backend import LinuxShellBackend
        shell = LinuxShellBackend()
        result = shell.sanitize_command("ls -la /home")
        assert result == "ls -la /home"

    def test_xdotool_key_mapping(self):
        from core.platform.linux_backend import LinuxStealthInput
        assert LinuxStealthInput._to_xdotool_key("enter") == "Return"
        assert LinuxStealthInput._to_xdotool_key("tab") == "Tab"
        assert LinuxStealthInput._to_xdotool_key("escape") == "Escape"
        assert LinuxStealthInput._to_xdotool_key("ctrl") == "ctrl"
        assert LinuxStealthInput._to_xdotool_key("f1") == "F1"
        assert LinuxStealthInput._to_xdotool_key("unknown_key") == "unknown_key"


# ---------------------------------------------------------------------------
# macOS backend structure
# ---------------------------------------------------------------------------


class TestMacOSBackendStructure:
    """Test macOS backend has correct subsystems."""

    def test_has_all_subsystems(self):
        from core.platform.macos_backend import MacOSBackend
        backend = MacOSBackend()
        assert backend.accessibility is not None
        assert backend.stealth is not None
        assert backend.credentials is not None
        assert backend.shell is not None
        assert backend.window is not None
        assert backend.overlay is not None

    def test_default_shell(self):
        from core.platform.macos_backend import MacOSBackend
        backend = MacOSBackend()
        assert backend.default_shell == "zsh"

    def test_shell_sanitization_blocks_dangerous(self):
        from core.platform.macos_backend import MacOSShellBackend
        shell = MacOSShellBackend()
        with pytest.raises(ValueError, match="dangerous"):
            shell.sanitize_command("rm -rf /")

    def test_key_code_mapping(self):
        from core.platform.macos_backend import MacOSStealthInput
        assert MacOSStealthInput._to_applescript_key("enter") == 36
        assert MacOSStealthInput._to_applescript_key("tab") == 48
        assert MacOSStealthInput._to_applescript_key("escape") == 53
        assert MacOSStealthInput._to_applescript_key("f1") == 122


# ---------------------------------------------------------------------------
# Cross-platform: XOR encryption fallback
# ---------------------------------------------------------------------------


class TestXOREncryptionFallback:
    """Test the XOR encryption used as DPAPI fallback on non-Windows."""

    def test_xor_encrypt_produces_different_output(self):
        from core.encryption import _xor_encrypt
        data = b"hello world"
        result = _xor_encrypt(data)
        assert result is not None
        assert result != data

    def test_xor_decrypt_reverses_encrypt(self):
        from core.encryption import _xor_decrypt, _xor_encrypt
        data = b"test credential value 12345"
        encrypted = _xor_encrypt(data)
        decrypted = _xor_decrypt(encrypted)
        assert decrypted == data

    def test_xor_roundtrip_empty(self):
        from core.encryption import _xor_decrypt, _xor_encrypt
        data = b""
        encrypted = _xor_encrypt(data)
        decrypted = _xor_decrypt(encrypted)
        assert decrypted == data

    def test_xor_roundtrip_binary(self):
        from core.encryption import _xor_decrypt, _xor_encrypt
        data = bytes(range(256))
        encrypted = _xor_encrypt(data)
        decrypted = _xor_decrypt(encrypted)
        assert decrypted == data

    def test_xor_decrypt_invalid_base64_returns_none(self):
        from core.encryption import _xor_decrypt
        result = _xor_decrypt(b"not-valid-base64!!!")
        assert result is None


# ---------------------------------------------------------------------------
# Process manager sanitization
# ---------------------------------------------------------------------------


class TestProcessManagerSanitization:
    """Test command sanitization in process_manager."""

    def test_blocks_rm_rf(self):
        from core.process_manager import _sanitize_command
        with pytest.raises(ValueError, match="dangerous"):
            _sanitize_command("/usr/bin/rm", ["-rf", "/"])

    def test_blocks_del_format(self):
        from core.process_manager import _sanitize_command
        with pytest.raises(ValueError, match="dangerous"):
            _sanitize_command("del /f /q c:\\important")

    def test_blocks_shell_metacharacters_in_path(self):
        from core.process_manager import _sanitize_command
        with pytest.raises(ValueError, match="metacharacter"):
            _sanitize_command("notepad && del important.txt")

    def test_allows_safe_commands(self):
        from core.process_manager import _sanitize_command
        # Should not raise
        _sanitize_command("notepad.exe")
        _sanitize_command("C:\\Program Files\\App\\app.exe", ["--flag"])
        _sanitize_command("/usr/bin/python3", ["script.py"])

    def test_blocks_pipe_in_path(self):
        from core.process_manager import _sanitize_command
        with pytest.raises(ValueError, match="metacharacter"):
            _sanitize_command("cmd | evil")

    def test_blocks_semicolon_in_path(self):
        from core.process_manager import _sanitize_command
        with pytest.raises(ValueError, match="metacharacter"):
            _sanitize_command("cmd ; evil")
