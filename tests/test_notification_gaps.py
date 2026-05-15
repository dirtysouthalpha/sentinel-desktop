"""Tests for notifications.py — covering uncovered paths and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from core.notifications import NotificationManager


class TestUnknownChannel:
    """notify() skips unknown channels gracefully."""

    def test_unknown_channel_skipped(self) -> None:
        nm = NotificationManager({"enabled_channels": ["log"]})
        with patch.object(
            nm,
            "_dispatch_map",
            return_value={},
        ):
            result = nm.notify("T", "M", channels=["bogus"])
        # bogus channel skipped, but "log" was force-appended and also missing
        # from dispatch_map, so all channels are skipped => returns True (vacuously)
        assert result is True


class TestHandlerFailureStats:
    """Handler that fails updates failed counter."""

    def test_handler_failure_increments_failed(self) -> None:
        nm = NotificationManager({"enabled_channels": ["log"]})

        def bad_handler(title: str, message: str, level: str) -> tuple[bool, str]:
            raise RuntimeError("channel broke")

        with patch.object(nm, "_dispatch_map", return_value={"log": bad_handler}):
            result = nm.notify("T", "M")
        assert result is False
        assert nm._stats["log"]["failed"] == 1


class TestKeyboardInterruptReRaise:
    """KeyboardInterrupt and SystemExit propagate through notify()."""

    def test_keyboard_interrupt_propagates(self) -> None:
        nm = NotificationManager({"enabled_channels": ["log"]})

        def raise_ki(title: str, message: str, level: str) -> tuple[bool, str]:
            raise KeyboardInterrupt

        with patch.object(nm, "_dispatch_map", return_value={"log": raise_ki}):
            with pytest.raises(KeyboardInterrupt):
                nm.notify("T", "M")

    def test_system_exit_propagates(self) -> None:
        nm = NotificationManager({"enabled_channels": ["log"]})

        def raise_se(title: str, message: str, level: str) -> tuple[bool, str]:
            raise SystemExit(1)

        with patch.object(nm, "_dispatch_map", return_value={"log": raise_se}):
            with pytest.raises(SystemExit):
                nm.notify("T", "M")


class TestTestChannel:
    """test_channel() success and error paths."""

    def test_test_channel_log_succeeds(self) -> None:
        nm = NotificationManager()
        ok, detail = nm.test_channel("log")
        assert ok is True
        assert detail == "logged"

    def test_test_channel_captures_exception(self) -> None:
        nm = NotificationManager()

        def bad(title: str, message: str, level: str) -> tuple[bool, str]:
            raise RuntimeError("boom")

        with patch.object(nm, "_dispatch_map", return_value={"webhook": bad}):
            ok, detail = nm.test_channel("webhook")
        assert ok is False
        assert "boom" in detail


class TestResolveChannelsAppendsLog:
    """_resolve_channels always adds 'log' when not present."""

    def test_override_without_log_gets_log_appended(self) -> None:
        nm = NotificationManager()
        channels = nm._resolve_channels(["webhook"])
        assert "log" in channels
        assert "webhook" in channels

    def test_config_without_log_gets_log_appended(self) -> None:
        nm = NotificationManager({"enabled_channels": ["webhook"]})
        channels = nm._resolve_channels(None)
        assert "log" in channels


class TestSendToast:
    """_send_toast behavior on Windows."""

    def test_toast_disabled_returns_false(self) -> None:
        nm = NotificationManager({"toast_enabled": False})
        ok, detail = nm._send_toast("T", "M", "info")
        assert ok is False
        assert "disabled" in detail

    @patch("core.notifications._is_windows", return_value=False)
    def test_toast_non_windows_returns_false(self, mock_win: MagicMock) -> None:
        nm = NotificationManager({"toast_enabled": True})
        ok, detail = nm._send_toast("T", "M", "info")
        assert ok is False

    @patch("core.notifications._is_windows", return_value=True)
    @patch("core.notifications.threading.Thread")
    def test_toast_ctypes_fallback(self, mock_thread: MagicMock, mock_win: MagicMock) -> None:
        nm = NotificationManager({"toast_enabled": True})
        # win10toast import will fail, ctypes fallback used
        with patch.dict("sys.modules", {"win10toast": None}):
            import ctypes as real_ctypes

            mock_windll = MagicMock()
            with patch.object(real_ctypes, "windll", mock_windll):
                ok, detail = nm._send_toast("T", "M", "info")
        assert ok is True
        assert "ctypes" in detail
        mock_thread.assert_called_once()

    @patch("core.notifications._is_windows", return_value=True)
    def test_toast_all_fail(self, mock_win: MagicMock) -> None:
        nm = NotificationManager({"toast_enabled": True})
        with patch.dict("sys.modules", {"win10toast": None}):
            with patch("builtins.__import__", side_effect=ImportError("nope")):
                ok, detail = nm._send_toast("T", "M", "info")
        assert ok is False


class TestSendWebhook:
    """_send_webhook sends payload to configured URL."""

    @patch("core.notifications._send_http", return_value=(True, "HTTP 200: ok"))
    def test_webhook_sends_payload(self, mock_http: MagicMock) -> None:
        nm = NotificationManager({"webhook_url": "https://example.com/hook"})
        ok, detail = nm._send_webhook("Title", "Body", "success")
        assert ok is True
        mock_http.assert_called_once()
        payload = mock_http.call_args[0][1]
        assert payload["title"] == "Title"
        assert payload["level"] == "success"

    def test_webhook_no_url(self) -> None:
        nm = NotificationManager({"webhook_url": None})
        ok, detail = nm._send_webhook("T", "M", "info")
        assert ok is False


class TestSendDiscord:
    """_send_discord sends embed to Discord webhook."""

    @patch("core.notifications._send_http", return_value=(True, "HTTP 204: "))
    def test_discord_sends_embed(self, mock_http: MagicMock) -> None:
        nm = NotificationManager({"discord_webhook": "https://discord.com/api/webhooks/test"})
        ok, detail = nm._send_discord("Alert", "Disk full", "error")
        assert ok is True
        payload = mock_http.call_args[0][1]
        assert "embeds" in payload
        assert payload["embeds"][0]["color"] == 0xE74C3C  # error red

    def test_discord_no_url(self) -> None:
        nm = NotificationManager()
        ok, detail = nm._send_discord("T", "M", "info")
        assert ok is False


class TestEmailRecipients:
    """_send_email handles string and list recipients."""

    def test_email_string_recipients(self) -> None:
        nm = NotificationManager(
            {
                "smtp_server": "smtp.test.com:587",
                "email_from": "bot@test.com",
                "email_to": "a@test.com, b@test.com",
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value
            ok, detail = nm._send_email("Subject", "Body", "info")
        assert ok is True
        # sendmail called with list of recipients
        call_args = instance.sendmail.call_args[0]
        assert call_args[1] == ["a@test.com", "b@test.com"]

    def test_email_starttls_path(self) -> None:
        nm = NotificationManager(
            {
                "smtp_server": "smtp.test.com:587",
                "email_from": "bot@test.com",
                "email_to": "user@test.com",
                "smtp_use_tls": True,
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value
            ok, detail = nm._send_email("T", "M", "info")
        assert ok is True
        instance.starttls.assert_called_once()
        instance.ehlo.assert_called()

    def test_email_list_recipients(self) -> None:
        nm = NotificationManager(
            {
                "smtp_server": "smtp.test.com:587",
                "email_from": "bot@test.com",
                "email_to": ["a@test.com", "b@test.com"],
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value
            ok, detail = nm._send_email("T", "M", "info")
        assert ok is True
        call_args = instance.sendmail.call_args[0]
        assert call_args[1] == ["a@test.com", "b@test.com"]

    def test_email_no_tls_path(self) -> None:
        nm = NotificationManager(
            {
                "smtp_server": "smtp.test.com:25",
                "email_from": "bot@test.com",
                "email_to": "user@test.com",
                "smtp_use_tls": False,
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value
            ok, detail = nm._send_email("T", "M", "info")
        assert ok is True
        instance.starttls.assert_not_called()
