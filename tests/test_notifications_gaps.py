"""Gap tests for notifications.py — lines 269-271, 453-460, 463-464, 471."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.notifications import NotificationManager


class TestNotifyHandlerReturnsFalse:
    """Lines 269-271: handler returns (False, detail) — failed counter and all_ok."""

    def test_handler_returning_false_increments_failed_counter(self) -> None:
        """When a handler returns (False, reason), failed stat increments."""
        nm = NotificationManager({"enabled_channels": ["log"]})

        def failing_handler(title: str, message: str, level: str) -> tuple[bool, str]:
            return False, "something went wrong"

        with patch.object(nm, "_dispatch_map", return_value={"log": failing_handler}):
            result = nm.notify("T", "M")

        assert result is False
        assert nm._stats["log"]["failed"] == 1
        assert nm._stats["log"]["succeeded"] == 0

    def test_handler_returning_false_records_last_result(self) -> None:
        """When handler returns (False, detail), last_results is stored."""
        nm = NotificationManager({"enabled_channels": ["log"]})

        def failing_handler(title: str, message: str, level: str) -> tuple[bool, str]:
            return False, "network timeout"

        with patch.object(nm, "_dispatch_map", return_value={"log": failing_handler}):
            nm.notify("T", "M")

        ok, detail = nm._last_results["log"]
        assert ok is False
        assert "network timeout" in detail


class TestToastWin10toastSuccess:
    """Lines 453-460: win10toast show_toast succeeds."""

    @patch("core.notifications._is_windows", return_value=True)
    def test_win10toast_success_path(self, mock_win: MagicMock) -> None:
        """win10toast installed and succeeds — returns True with detail."""
        nm = NotificationManager({"toast_enabled": True})

        mock_toaster_cls = MagicMock()
        mock_toaster_instance = MagicMock()
        mock_toaster_cls.return_value = mock_toaster_instance

        mock_module = MagicMock()
        mock_module.ToastNotifier = mock_toaster_cls

        with patch.dict("sys.modules", {"win10toast": mock_module}):
            ok, detail = nm._send_toast("Title", "Body", "info")

        assert ok is True
        assert "win10toast" in detail
        mock_toaster_instance.show_toast.assert_called_once_with(
            "Title",
            "Body",
            icon_path=None,
            duration=5,
            threaded=True,
        )


class TestToastWin10toastExceptionFallback:
    """Lines 463-464: win10toast raises non-ImportError — falls through."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ctypes.windll test")
    @patch("core.notifications._is_windows", return_value=True)
    @patch("core.notifications.threading.Thread")
    def test_win10toast_exception_falls_to_ctypes(
        self, mock_thread: MagicMock, mock_win: MagicMock
    ) -> None:
        """win10toast raises RuntimeError — ctypes fallback is attempted."""
        nm = NotificationManager({"toast_enabled": True})

        mock_toaster_cls = MagicMock()
        mock_toaster_instance = MagicMock()
        mock_toaster_instance.show_toast.side_effect = RuntimeError("toast crashed")
        mock_toaster_cls.return_value = mock_toaster_instance

        mock_module = MagicMock()
        mock_module.ToastNotifier = mock_toaster_cls

        import ctypes as real_ctypes

        mock_windll = MagicMock()

        with patch.dict("sys.modules", {"win10toast": mock_module}):
            with patch.object(real_ctypes, "windll", mock_windll):
                ok, detail = nm._send_toast("T", "M", "info")

        # ctypes fallback should succeed
        assert ok is True
        assert "ctypes" in detail
        mock_thread.assert_called_once()


class TestToastCtypesMessageBoxW:
    """Line 471: ctypes.windll.user32.MessageBoxW called inside thread."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ctypes.windll test")
    @patch("core.notifications._is_windows", return_value=True)
    @patch("core.notifications.threading.Thread")
    def test_messageboxw_called_with_correct_args(
        self, mock_thread: MagicMock, mock_win: MagicMock
    ) -> None:
        """MessageBoxW is invoked with message, title, and icon flag."""
        nm = NotificationManager({"toast_enabled": True})

        mock_message_box = MagicMock()
        mock_user32 = MagicMock()
        mock_user32.MessageBoxW = mock_message_box
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32

        # ctypes is imported locally in _send_toast, so patch the stdlib module directly
        import ctypes as real_ctypes

        with patch.dict("sys.modules", {"win10toast": None}):
            with patch.object(real_ctypes, "windll", mock_windll):
                ok, detail = nm._send_toast("MyTitle", "MyMessage", "warning")

                # Thread was created — extract the target function and call it
                # while windll is still patched
                mock_thread.assert_called_once()
                target_fn = mock_thread.call_args[1]["target"]
                target_fn()

        assert ok is True
        assert "ctypes" in detail

        # Verify MessageBoxW was called with expected args
        mock_message_box.assert_called_once_with(0, "MyMessage", "Sentinel — MyTitle", 0x40)
