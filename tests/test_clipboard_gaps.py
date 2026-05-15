"""Tests for clipboard.py — covering pyperclip ImportError fallback."""

import importlib
import sys

import core.clipboard as clipboard_mod


class TestPyperclipImportFallback:
    """pyperclip = None fallback at import time."""

    def test_import_error_sets_pyperclip_none(self) -> None:
        saved_mod = sys.modules.get("core.clipboard")
        saved_pyperclip = sys.modules.get("pyperclip")
        try:
            # Block pyperclip import
            sys.modules["pyperclip"] = None
            # Reload to trigger the except ImportError path
            mod = importlib.reload(clipboard_mod)
            assert mod.pyperclip is None
        finally:
            # Restore original state
            if saved_pyperclip is not None:
                sys.modules["pyperclip"] = saved_pyperclip
            else:
                sys.modules.pop("pyperclip", None)
            sys.modules["core.clipboard"] = saved_mod
            importlib.reload(saved_mod)

    def test_import_fallback_read_returns_empty(self) -> None:
        saved_mod = sys.modules.get("core.clipboard")
        saved_pyperclip = sys.modules.get("pyperclip")
        try:
            sys.modules["pyperclip"] = None
            mod = importlib.reload(clipboard_mod)
            mod._clipboard = None
            assert mod.clipboard_read() == ""
        finally:
            if saved_pyperclip is not None:
                sys.modules["pyperclip"] = saved_pyperclip
            else:
                sys.modules.pop("pyperclip", None)
            sys.modules["core.clipboard"] = saved_mod
            importlib.reload(saved_mod)

    def test_import_fallback_write_returns_false(self) -> None:
        saved_mod = sys.modules.get("core.clipboard")
        saved_pyperclip = sys.modules.get("pyperclip")
        try:
            sys.modules["pyperclip"] = None
            mod = importlib.reload(clipboard_mod)
            mod._clipboard = None
            assert mod.clipboard_write("test") is False
        finally:
            if saved_pyperclip is not None:
                sys.modules["pyperclip"] = saved_pyperclip
            else:
                sys.modules.pop("pyperclip", None)
            sys.modules["core.clipboard"] = saved_mod
            importlib.reload(saved_mod)
