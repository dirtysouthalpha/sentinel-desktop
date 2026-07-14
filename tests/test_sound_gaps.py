"""Gap tests for sound.py — Windows-specific import guard (line 42).

The module has an import guard at line 42 that only executes on Windows:
    if _IS_WINDOWS:
        import winsound

These lines never run on Linux at import time, so we use importlib.reload()
with mocked conditions to execute them during testing, then reload again
to restore the normal state.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

import core.sound as sound_mod


class TestWindowsImportGuard:
    """Line 42: the module-level Windows winsound import guard.

    This line only executes at import time on Windows when _IS_WINDOWS is True.
    We reimport the module with platform.system() faked to "Windows" and
    winsound mocked to ensure the guard executes and the import succeeds.

    The module is reloaded again afterwards to restore the Linux state.
    """

    def test_windows_import_guard_executes_on_import(self):
        """On Windows, the winsound import guard executes and imports winsound."""
        # Mock winsound before reload so it can be imported
        mock_winsound = MagicMock()
        mock_winsound.Beep = MagicMock()
        mock_winsound.PlaySound = MagicMock()
        mock_winsound.SND_FILENAME = 0x00020000
        mock_winsound.SND_NODEFAULT = 0x0002
        mock_winsound.SND_ASYNC = 0x0001

        with patch("platform.system", return_value="Windows"):
            try:
                # Make winsound available for import
                with patch.dict("sys.modules", {"winsound": mock_winsound}):
                    reloaded = importlib.reload(sound_mod)
                    # After reload on Windows, _IS_WINDOWS should be True
                    assert reloaded._IS_WINDOWS is True
                    # The import guard executed successfully
                    # (If it failed, the module would not load properly)
                    assert callable(reloaded._play)
            finally:
                # Restore the normal platform state
                importlib.reload(sound_mod)

        # After exiting the patch context, verify we're back to real platform state
        import platform as _plat
        # Need one more reload to clear the mocked platform.system
        importlib.reload(sound_mod)
        assert sound_mod._IS_WINDOWS is (_plat.system() == "Windows")

    def test_non_windows_skips_winsound_import(self):
        """On non-Windows platforms, the winsound import is skipped."""
        with patch("platform.system", return_value="Linux"):
            try:
                reloaded = importlib.reload(sound_mod)
                # After reload on Linux, _IS_WINDOWS should be False
                assert reloaded._IS_WINDOWS is False
                # winsound should not be in sys.modules from this import
                # (it may be there from other tests, but this module didn't import it)
            finally:
                # Restore the normal platform state
                importlib.reload(sound_mod)

        # Verify we're back to the real platform state
        import platform as _plat
        assert sound_mod._IS_WINDOWS is (_plat.system() == "Windows")

    def test_winsound_import_failure_is_caught(self):
        """If winsound import fails on Windows, the module still loads."""
        with patch("platform.system", return_value="Windows"):
            try:
                # Make winsound import fail
                with patch.dict("sys.modules", {"winsound": None}):
                    # This should not raise an exception during reload
                    # The module should handle the import failure gracefully
                    reloaded = importlib.reload(sound_mod)
                    assert reloaded._IS_WINDOWS is True
                    # The _play function should still exist even if winsound failed to import
                    assert callable(reloaded._play)
            finally:
                # Restore the normal platform state
                importlib.reload(sound_mod)
