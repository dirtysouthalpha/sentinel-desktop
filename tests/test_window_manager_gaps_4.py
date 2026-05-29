"""Gap tests for window_manager.py -- module-level import branches (lines 15-16, 21-22, 27-32).

These lines execute at import time inside conditional/try-except blocks:
  - Lines 15-16: HAS_WIN32 = False when win32gui/win32con import fails on Windows
  - Lines 21-22: HAS_PGW = False when pygetwindow import fails on Windows
  - Lines 27-28: _Win32Error = OSError when pywintypes import fails on Windows
  - Lines 29-32: else branch -- non-Windows platform sets all three to False/OSError
"""

import importlib
import platform
import sys
from unittest.mock import MagicMock, patch

import pytest

import core.window_manager as wm_original


class TestWin32ImportFailsOnWindows:
    """Cover lines 15-16: HAS_WIN32 = False when win32gui import fails."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Test simulates Windows-specific import failures")
    def test_has_win32_false_when_win32_import_fails(self):
        """On Windows, if win32con/win32gui raise ImportError, HAS_WIN32 = False."""
        # Capture the real module before we manipulate sys.modules
        real_win32gui = sys.modules.get("win32gui")
        real_win32con = sys.modules.get("win32con")
        real_pgw = sys.modules.get("pygetwindow")
        real_pywintypes = sys.modules.get("pywintypes")

        try:
            # Remove win32 modules so the import fails
            sys.modules["win32gui"] = None  # type: ignore[assignment]
            sys.modules["win32con"] = None  # type: ignore[assignment]
            # Provide pygetwindow so it succeeds (to avoid line 21-22)
            sys.modules["pygetwindow"] = MagicMock()
            # Provide pywintypes so it succeeds (to avoid line 27-28)
            sys.modules["pywintypes"] = MagicMock()

            with patch("platform.system", return_value="Windows"):
                # Force a re-import of the module
                importlib.reload(wm_original)

            # Lines 15-16 should have executed: HAS_WIN32 = False
            assert wm_original.HAS_WIN32 is False
            # pygetwindow succeeded, so HAS_PGW = True (lines 20)
            assert wm_original.HAS_PGW is True
        finally:
            # Restore original state
            if real_win32gui is not None:
                sys.modules["win32gui"] = real_win32gui
            else:
                sys.modules.pop("win32gui", None)
            if real_win32con is not None:
                sys.modules["win32con"] = real_win32con
            else:
                sys.modules.pop("win32con", None)
            if real_pgw is not None:
                sys.modules["pygetwindow"] = real_pgw
            else:
                sys.modules.pop("pygetwindow", None)
            if real_pywintypes is not None:
                sys.modules["pywintypes"] = real_pywintypes
            else:
                sys.modules.pop("pywintypes", None)
            # On Linux, pygetwindow raises NotImplementedError on import, so mock it
            # to avoid ImportError when reloading with platform.system == "Windows"
            if platform.system() != "Windows":
                real_pgw_final = sys.modules.get("pygetwindow")
                try:
                    sys.modules["pygetwindow"] = MagicMock()
                    with patch("platform.system", return_value="Windows"):
                        importlib.reload(wm_original)
                finally:
                    if real_pgw_final is not None:
                        sys.modules["pygetwindow"] = real_pgw_final
                    else:
                        sys.modules.pop("pygetwindow", None)
            else:
                # Restore the module to its original state
                with patch("platform.system", return_value="Windows"):
                    importlib.reload(wm_original)


class TestPgwImportFailsOnWindows:
    """Cover lines 21-22: HAS_PGW = False when pygetwindow import fails."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Test simulates Windows-specific import failures")
    def test_has_pgw_false_when_pgw_import_fails(self):
        """On Windows, if pygetwindow raises ImportError, HAS_PGW = False."""
        real_win32gui = sys.modules.get("win32gui")
        real_win32con = sys.modules.get("win32con")
        real_pgw = sys.modules.get("pygetwindow")
        real_pywintypes = sys.modules.get("pywintypes")

        try:
            # Provide win32 modules so they succeed (avoid lines 15-16)
            sys.modules["win32gui"] = MagicMock()
            sys.modules["win32con"] = MagicMock()
            # Remove pygetwindow so it fails
            sys.modules["pygetwindow"] = None  # type: ignore[assignment]
            # Provide pywintypes so it succeeds (avoid lines 27-28)
            sys.modules["pywintypes"] = MagicMock()

            with patch("platform.system", return_value="Windows"):
                importlib.reload(wm_original)

            # Lines 21-22 should have executed: HAS_PGW = False
            assert wm_original.HAS_PGW is False
            # win32 succeeded, so HAS_WIN32 = True
            assert wm_original.HAS_WIN32 is True
        finally:
            if real_win32gui is not None:
                sys.modules["win32gui"] = real_win32gui
            else:
                sys.modules.pop("win32gui", None)
            if real_win32con is not None:
                sys.modules["win32con"] = real_win32con
            else:
                sys.modules.pop("win32con", None)
            if real_pgw is not None:
                sys.modules["pygetwindow"] = real_pgw
            else:
                sys.modules.pop("pygetwindow", None)
            if real_pywintypes is not None:
                sys.modules["pywintypes"] = real_pywintypes
            else:
                sys.modules.pop("pywintypes", None)
            with patch("platform.system", return_value="Windows"):
                importlib.reload(wm_original)


class TestPywintypesImportFailsOnWindows:
    """Cover lines 27-28: _Win32Error = OSError when pywintypes import fails."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Test simulates Windows-specific import failures")
    def test_win32_error_is_oserror_when_pywintypes_fails(self):
        """On Windows, if pywintypes raises ImportError, _Win32Error = OSError."""
        real_win32gui = sys.modules.get("win32gui")
        real_win32con = sys.modules.get("win32con")
        real_pgw = sys.modules.get("pygetwindow")
        real_pywintypes = sys.modules.get("pywintypes")

        try:
            # Provide win32 and pgw so they succeed
            sys.modules["win32gui"] = MagicMock()
            sys.modules["win32con"] = MagicMock()
            sys.modules["pygetwindow"] = MagicMock()
            # Remove pywintypes so it fails -- triggers line 28
            sys.modules["pywintypes"] = None  # type: ignore[assignment]

            with patch("platform.system", return_value="Windows"):
                importlib.reload(wm_original)

            # Lines 27-28: _Win32Error should be OSError
            assert wm_original._Win32Error is OSError
        finally:
            if real_win32gui is not None:
                sys.modules["win32gui"] = real_win32gui
            else:
                sys.modules.pop("win32gui", None)
            if real_win32con is not None:
                sys.modules["win32con"] = real_win32con
            else:
                sys.modules.pop("win32con", None)
            if real_pgw is not None:
                sys.modules["pygetwindow"] = real_pgw
            else:
                sys.modules.pop("pygetwindow", None)
            if real_pywintypes is not None:
                sys.modules["pywintypes"] = real_pywintypes
            else:
                sys.modules.pop("pywintypes", None)
            with patch("platform.system", return_value="Windows"):
                importlib.reload(wm_original)


class TestNonWindowsPlatform:
    """Cover lines 29-32: else branch for non-Windows platforms."""

    def test_non_windows_sets_all_false(self):
        """On non-Windows, HAS_WIN32=False, HAS_PGW=False, _Win32Error=OSError."""
        real_win32gui = sys.modules.get("win32gui")
        real_win32con = sys.modules.get("win32con")
        real_pgw = sys.modules.get("pygetwindow")
        real_pywintypes = sys.modules.get("pywintypes")

        try:
            # Even if win32 modules exist, non-Windows branch skips all imports
            sys.modules["win32gui"] = MagicMock()
            sys.modules["win32con"] = MagicMock()
            sys.modules["pygetwindow"] = MagicMock()
            sys.modules["pywintypes"] = MagicMock()

            with patch("platform.system", return_value="Linux"):
                importlib.reload(wm_original)

            # Lines 30-32: all set to False / OSError
            assert wm_original.HAS_WIN32 is False
            assert wm_original.HAS_PGW is False
            assert wm_original._Win32Error is OSError
        finally:
            if real_win32gui is not None:
                sys.modules["win32gui"] = real_win32gui
            else:
                sys.modules.pop("win32gui", None)
            if real_win32con is not None:
                sys.modules["win32con"] = real_win32con
            else:
                sys.modules.pop("win32con", None)
            if real_pgw is not None:
                sys.modules["pygetwindow"] = real_pgw
            else:
                sys.modules.pop("pygetwindow", None)
            if real_pywintypes is not None:
                sys.modules["pywintypes"] = real_pywintypes
            else:
                sys.modules.pop("pywintypes", None)
            # On Linux, pygetwindow raises NotImplementedError on import, so mock it
            # to avoid ImportError when reloading with platform.system == "Windows"
            if platform.system() != "Windows":
                real_pgw_final = sys.modules.get("pygetwindow")
                try:
                    sys.modules["pygetwindow"] = MagicMock()
                    with patch("platform.system", return_value="Windows"):
                        importlib.reload(wm_original)
                finally:
                    if real_pgw_final is not None:
                        sys.modules["pygetwindow"] = real_pgw_final
                    else:
                        sys.modules.pop("pygetwindow", None)
            else:
                with patch("platform.system", return_value="Windows"):
                    importlib.reload(wm_original)
