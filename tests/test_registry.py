"""Tests for core.registry — Windows registry read/write/delete."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import core.registry


def _make_winreg():
    """Return a fake winreg module with the constants tests need."""
    m = MagicMock()
    m.HKEY_LOCAL_MACHINE = 0x80000002
    m.HKEY_CURRENT_USER = 0x80000001
    m.HKEY_CLASSES_ROOT = 0x80000000
    m.HKEY_USERS = 0x80000003
    m.HKEY_CURRENT_CONFIG = 0x80000005
    m.REG_SZ = 1
    m.REG_DWORD = 4
    m.REG_EXPAND_SZ = 2
    m.REG_MULTI_SZ = 7
    m.REG_BINARY = 3
    m.REG_QWORD = 11
    m.KEY_READ = 0x20019
    m.KEY_WRITE = 0x20006
    m.KEY_SET_VALUE = 0x0002
    return m


_FAKE_HIVE_MAP = {
    "HKLM": 0x80000002,
    "HKCU": 0x80000001,
    "HKCR": 0x80000000,
    "HKU": 0x80000003,
    "HKCC": 0x80000005,
    "HKEY_LOCAL_MACHINE": 0x80000002,
    "HKEY_CURRENT_USER": 0x80000001,
    "HKEY_CLASSES_ROOT": 0x80000000,
    "HKEY_USERS": 0x80000003,
    "HKEY_CURRENT_CONFIG": 0x80000005,
}


def _win32_patches(mock_winreg=None):
    """Context manager stack: fake winreg + win32 platform + hive map."""
    if mock_winreg is None:
        mock_winreg = _make_winreg()
    return (
        patch("core.registry.winreg", mock_winreg, create=True),
        patch("core.registry.sys") ,
        mock_winreg,
    )


# ── _parse_key_path ────────────────────────────────────────────────────────────

class TestParseKeyPath:
    def test_raises_on_non_windows(self):
        from core.registry import _parse_key_path
        # On Linux, sys.platform != "win32" → raises OSError
        with pytest.raises(OSError, match="only available on Windows"):
            _parse_key_path("HKLM\\Software\\Test")

    def test_raises_for_unknown_hive_on_windows(self):
        from core.registry import _parse_key_path
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    with pytest.raises(ValueError, match="Unknown registry hive"):
                        _parse_key_path("INVALID\\Software\\Test")

    def test_returns_hive_and_subpath(self):
        from core.registry import _parse_key_path
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    hive, subpath = _parse_key_path("HKLM\\Software\\Test")
        assert hive == 0x80000002
        assert subpath == "Software\\Test"

    def test_handles_forward_slashes(self):
        from core.registry import _parse_key_path
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    hive, subpath = _parse_key_path("HKLM/Software/Test")
        assert subpath == "Software\\Test"

    def test_no_subpath(self):
        from core.registry import _parse_key_path
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    hive, subpath = _parse_key_path("HKLM")
        assert subpath == ""


# ── registry_read ──────────────────────────────────────────────────────────────

class TestRegistryRead:
    def test_returns_none_on_linux(self):
        # On the test machine (Linux), _parse_key_path raises OSError → None
        result = core.registry.registry_read("HKLM\\Software\\Test", "TestValue")
        assert result is None

    def test_returns_none_for_invalid_path_on_windows(self):
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_read("INVALID\\foo", "val")
        assert result is None

    def test_reads_reg_sz_value(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mwr.QueryValueEx.return_value = ("hello", mwr.REG_SZ)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_read("HKLM\\Software\\Test", "TestValue")

        assert result is not None
        assert result["data"] == "hello"
        assert result["type"] == "REG_SZ"
        assert result["value_name"] == "TestValue"
        assert result["path"] == "HKLM\\Software\\Test"

    def test_reads_default_value(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mwr.QueryValueEx.return_value = ("default_val", mwr.REG_SZ)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_read("HKLM\\Software\\Test")

        assert result is not None
        assert result["value_name"] == "(Default)"

    def test_returns_none_on_oserror(self):
        mwr = _make_winreg()
        mwr.OpenKey.side_effect = OSError("access denied")

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_read("HKLM\\Software\\Test", "Val")

        assert result is None

    def test_reads_dword_type(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mwr.QueryValueEx.return_value = (42, mwr.REG_DWORD)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_read("HKLM\\Software\\Test", "NumVal")

        assert result["data"] == 42
        assert result["type"] == "REG_DWORD"


# ── registry_write ─────────────────────────────────────────────────────────────

class TestRegistryWrite:
    def test_returns_false_on_linux(self):
        # On Linux, type_map uses winreg.REG_SZ etc which aren't available,
        # but _parse_key_path raises OSError before that matters on Linux.
        # Actually on Linux winreg isn't imported so type_map dict would fail
        # unless winreg is injected. Just verify the function returns False.
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            # sys.platform is still "linux", so _parse_key_path raises OSError
            result = core.registry.registry_write("HKLM\\Software\\Test", "val", "data")
        assert result is False

    def test_writes_reg_sz(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.CreateKeyEx.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.CreateKeyEx.return_value.__exit__ = MagicMock(return_value=False)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_write(
                        "HKLM\\Software\\Test", "TestVal", "hello", "REG_SZ"
                    )

        assert result is True
        mwr.SetValueEx.assert_called_once()

    def test_writes_reg_dword(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.CreateKeyEx.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.CreateKeyEx.return_value.__exit__ = MagicMock(return_value=False)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_write(
                        "HKLM\\Software\\Test", "NumVal", 42, "REG_DWORD"
                    )

        assert result is True

    def test_returns_false_on_invalid_hive(self):
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_write(
                        "INVALID\\Software\\Test", "val", "data"
                    )
        assert result is False

    def test_returns_false_on_oserror(self):
        mwr = _make_winreg()
        mwr.CreateKeyEx.side_effect = OSError("permission denied")

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_write(
                        "HKLM\\Software\\Test", "val", "data"
                    )
        assert result is False

    def test_defaults_to_reg_sz_for_unknown_type(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.CreateKeyEx.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.CreateKeyEx.return_value.__exit__ = MagicMock(return_value=False)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_write(
                        "HKLM\\Software\\Test", "val", "data", "REG_UNKNOWN"
                    )
        assert result is True


# ── registry_delete ────────────────────────────────────────────────────────────

class TestRegistryDelete:
    def test_returns_false_on_linux(self):
        result = core.registry.registry_delete("HKLM\\Software\\Test")
        assert result is False

    def test_returns_false_on_invalid_hive(self):
        mwr = _make_winreg()
        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_delete("INVALID\\foo")
        assert result is False

    def test_deletes_value(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.OpenKey.return_value.__exit__ = MagicMock(return_value=False)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_delete(
                        "HKLM\\Software\\Test", "TestValue"
                    )

        assert result is True
        mwr.DeleteValue.assert_called_once_with(mock_key, "TestValue")

    def test_deletes_key(self):
        mwr = _make_winreg()
        mock_key = MagicMock()
        mwr.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mwr.OpenKey.return_value.__exit__ = MagicMock(return_value=False)

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_delete(
                        "HKLM\\Software\\Test\\SubKey"
                    )

        assert result is True
        mwr.DeleteKey.assert_called_once_with(mock_key, "SubKey")

    def test_returns_false_on_oserror(self):
        mwr = _make_winreg()
        mwr.OpenKey.side_effect = OSError("access denied")

        with patch("core.registry.winreg", mwr, create=True):
            with patch("core.registry.sys") as ms:
                ms.platform = "win32"
                with patch.object(core.registry, "_HIVE_MAP", _FAKE_HIVE_MAP):
                    result = core.registry.registry_delete(
                        "HKLM\\Software\\Test", "val"
                    )
        assert result is False
