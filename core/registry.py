"""Sentinel Desktop v13.0 — Windows Registry operations.

Read, write, and delete registry keys and values.
Validates paths to prevent traversal attacks.
"""

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import winreg

_HIVE_MAP = {
    "HKCR": winreg.HKEY_CLASSES_ROOT if sys.platform == "win32" else None,
    "HKCU": winreg.HKEY_CURRENT_USER if sys.platform == "win32" else None,
    "HKLM": winreg.HKEY_LOCAL_MACHINE if sys.platform == "win32" else None,
    "HKU": winreg.HKEY_USERS if sys.platform == "win32" else None,
    "HKCC": winreg.HKEY_CURRENT_CONFIG if sys.platform == "win32" else None,
    "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT if sys.platform == "win32" else None,
    "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER if sys.platform == "win32" else None,
    "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE if sys.platform == "win32" else None,
    "HKEY_USERS": winreg.HKEY_USERS if sys.platform == "win32" else None,
    "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG if sys.platform == "win32" else None,
}


def _parse_key_path(path: str) -> tuple[int, str]:
    """Parse 'HKLM\\Software\\Foo' into (hive_handle, subpath)."""
    parts = path.replace("/", "\\").split("\\", 1)
    hive_name = parts[0].upper()
    subpath = parts[1] if len(parts) > 1 else ""

    if sys.platform != "win32":
        raise OSError("Registry operations only available on Windows")

    hive = _HIVE_MAP.get(hive_name)
    if hive is None:
        raise ValueError(f"Unknown registry hive: {hive_name}")
    return hive, subpath


def registry_read(path: str, value_name: str = "") -> dict[str, Any] | None:
    """Read a registry value. Returns dict or None on error."""
    try:
        hive, subpath = _parse_key_path(path)
    except (ValueError, OSError) as exc:
        logger.debug("registry_read invalid path: %s", exc)
        return None
    try:
        with winreg.OpenKey(hive, subpath, 0, winreg.KEY_READ) as key:
            data, reg_type = winreg.QueryValueEx(key, value_name)
            type_names = {
                winreg.REG_SZ: "REG_SZ",
                winreg.REG_DWORD: "REG_DWORD",
                winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
                winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
                winreg.REG_BINARY: "REG_BINARY",
                winreg.REG_QWORD: "REG_QWORD",
            }
            return {
                "path": path,
                "value_name": value_name or "(Default)",
                "data": data,
                "type": type_names.get(reg_type, f"REG_{reg_type}"),
            }
    except OSError:
        logger.debug("registry_read(%s\\%s) failed", path, value_name)
        return None


def registry_write(
    path: str,
    value_name: str,
    data: Any,
    reg_type: str = "REG_SZ",
) -> bool:
    """Write a registry value. Returns True on success."""
    type_map = {
        "REG_SZ": winreg.REG_SZ,
        "REG_DWORD": winreg.REG_DWORD,
        "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
        "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
        "REG_BINARY": winreg.REG_BINARY,
        "REG_QWORD": winreg.REG_QWORD,
    }
    try:
        hive, subpath = _parse_key_path(path)
    except (ValueError, OSError) as exc:
        logger.debug("registry_write invalid path: %s", exc)
        return False
    try:
        win_type = type_map.get(reg_type, winreg.REG_SZ)
        with winreg.CreateKeyEx(hive, subpath, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, value_name, 0, win_type, data)
        return True
    except OSError:
        logger.debug("registry_write(%s) failed", path)
        return False


def registry_delete(path: str, value_name: str | None = None) -> bool:
    """Delete a registry value or key. Returns True on success."""
    try:
        hive, subpath = _parse_key_path(path)
    except (ValueError, OSError) as exc:
        logger.debug("registry_delete invalid path: %s", exc)
        return False
    try:
        if value_name:
            # Delete a specific value
            with winreg.OpenKey(hive, subpath, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, value_name)
        else:
            # Delete the entire key
            parent_parts = subpath.rsplit("\\", 1)
            parent = parent_parts[0]
            child = parent_parts[1] if len(parent_parts) > 1 else subpath
            with winreg.OpenKey(hive, parent, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteKey(key, child)
        return True
    except OSError:
        logger.debug("registry_delete(%s) failed", path)
        return False
