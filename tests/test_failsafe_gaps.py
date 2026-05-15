"""Tests for failsafe.py — covering keyboard import failure and unhook exception."""

import sys
from unittest.mock import MagicMock, patch

from core.failsafe import FailsafeListener


class TestKeyboardImportFailure:
    """import keyboard raising Exception logs and returns False."""

    def test_import_failure_returns_false(self) -> None:
        fl = FailsafeListener(on_panic=lambda: None)
        # Setting sys.modules["keyboard"] = None makes Python raise ImportError
        with patch.dict(sys.modules, {"keyboard": None}):
            result = fl.start()
        assert result is False
        assert fl._started is False

    def test_import_failure_logs_info(self) -> None:
        fl = FailsafeListener(on_panic=lambda: None)
        with patch.dict(sys.modules, {"keyboard": None}):
            with patch("core.failsafe.logger") as mock_log:
                fl.start()
        mock_log.info.assert_called_once()
        msg = mock_log.info.call_args[0][0]
        assert "failsafe disabled" in msg


class TestUnhookException:
    """stop() handles unhook exception gracefully."""

    def test_unhook_exception_sets_stopped_anyway(self) -> None:
        fl = FailsafeListener(on_panic=lambda: None)
        fl._started = True
        fl._stopped = False
        fl._kb = MagicMock()
        fl._hotkey_handle = MagicMock()
        fl._kb.unhook.side_effect = OSError("hook not found")
        fl.stop()
        assert fl._stopped is True

    def test_unhook_exception_logs_debug(self) -> None:
        fl = FailsafeListener(on_panic=lambda: None)
        fl._started = True
        fl._stopped = False
        fl._kb = MagicMock()
        fl._hotkey_handle = MagicMock()
        fl._kb.unhook.side_effect = RuntimeError("unhook broke")
        with patch("core.failsafe.logger") as mock_log:
            fl.stop()
        mock_log.debug.assert_called_once()
        assert "unhook failed" in mock_log.debug.call_args[0][0]
