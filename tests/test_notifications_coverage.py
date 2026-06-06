"""Additional coverage tests for notifications.py — gap paths."""

from unittest.mock import MagicMock, patch

import pytest

from core.notifications import (
    CHANNELS,
    LEVEL_COLORS,
    VALID_LEVELS,
    NotificationManager,
    _send_http,
)

# ---------------------------------------------------------------------------
# _send_http — retry and error paths
# ---------------------------------------------------------------------------


class TestSendHttpRetries:
    """_send_http retry logic — URLError recovery and exhaustion."""

    def test_url_error_then_success(self) -> None:
        """First attempt fails with URLError, second succeeds."""
        call_count = 0

        def fake_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                from urllib.error import URLError

                raise URLError("connection refused")
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"ok"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("core.notifications.urlopen", side_effect=fake_urlopen):
            with patch("core.notifications.time.sleep"):
                ok, detail = _send_http("https://example.com/hook", {"x": 1}, retries=3)

        assert ok is True
        assert "200" in detail
        assert call_count == 2

    def test_all_retries_exhausted(self) -> None:
        """All retry attempts fail — returns last error."""
        from urllib.error import URLError

        with patch(
            "core.notifications.urlopen",
            side_effect=URLError("host unreachable"),
        ):
            with patch("core.notifications.time.sleep"):
                ok, detail = _send_http("https://example.com/hook", {"x": 1}, retries=2)

        assert ok is False
        assert "host unreachable" in detail

    def test_oserror_handled(self) -> None:
        """OSError during HTTP call is caught and retried."""
        call_count = 0

        def fake_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("network down")
            mock_resp = MagicMock()
            mock_resp.status = 201
            mock_resp.read.return_value = b"created"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("core.notifications.urlopen", side_effect=fake_urlopen):
            with patch("core.notifications.time.sleep"):
                ok, detail = _send_http("https://example.com/hook", {"x": 1}, retries=3)

        assert ok is True
        assert "201" in detail

    def test_large_response_body_truncated(self) -> None:
        """Response body longer than 512 chars is truncated in detail."""
        long_body = "x" * 1000

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = long_body.encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("core.notifications.urlopen", return_value=mock_resp):
            ok, detail = _send_http("https://example.com/hook", {"x": 1})

        assert ok is True
        assert len(detail) < 600  # should be truncated


# ---------------------------------------------------------------------------
# _resolve_channels edge cases
# ---------------------------------------------------------------------------


class TestResolveChannels:
    """Channel resolution logic — dedup and ordering."""

    def test_log_deduplicated_when_already_present(self) -> None:
        """If 'log' is already in override, it shouldn't be added again."""
        nm = NotificationManager()
        channels = nm._resolve_channels(["discord", "log"])
        assert channels.count("log") == 1

    def test_log_appended_when_missing(self) -> None:
        """If override doesn't include 'log', it's appended."""
        nm = NotificationManager()
        channels = nm._resolve_channels(["discord"])
        assert "log" in channels

    def test_override_preserves_order(self) -> None:
        """Override channels should maintain their order."""
        nm = NotificationManager()
        channels = nm._resolve_channels(["webhook", "discord"])
        assert channels[0] == "webhook"
        assert channels[1] == "discord"

    def test_no_override_uses_enabled_channels(self) -> None:
        """When no override, enabled_channels from config are used."""
        nm = NotificationManager({"enabled_channels": ["discord", "email"]})
        channels = nm._resolve_channels(None)
        assert "discord" in channels
        assert "email" in channels


# ---------------------------------------------------------------------------
# notify edge cases
# ---------------------------------------------------------------------------


class TestNotifyEdgeCases:
    """Edge cases in the notify() method."""

    def test_unknown_channel_skipped(self) -> None:
        """Unknown channel name is skipped with a warning."""
        nm = NotificationManager({"enabled_channels": ["log"]})
        # Override with a bogus channel that's not in the dispatch map
        result = nm.notify("T", "M", channels=["totally_fake_channel"])
        # log gets auto-appended, so it still succeeds via log
        assert result is True
        # The fake channel shouldn't appear in stats
        assert "totally_fake_channel" not in nm._stats

    def test_notify_with_none_config(self) -> None:
        """NotificationManager with no config uses defaults."""
        nm = NotificationManager(None)
        assert nm.notify("T", "M", level="info") is True

    def test_config_none_values_filtered(self) -> None:
        """Config values that are None should not override defaults."""
        nm = NotificationManager({"discord_webhook": None})
        assert nm._config["discord_webhook"] is None

    def test_notify_batch_empty_list(self) -> None:
        """notify_batch with empty list returns empty dict."""
        nm = NotificationManager()
        result = nm.notify_batch([])
        assert result == {}

    def test_notify_batch_missing_keys(self) -> None:
        """notify_batch items with missing keys use defaults."""
        nm = NotificationManager({"enabled_channels": ["log"]})
        result = nm.notify_batch([{}])
        assert "Untitled" in result
        assert result["Untitled"] is True

    def test_notify_increments_total_notifications(self) -> None:
        """Each call to notify increments _total_notifications."""
        nm = NotificationManager({"enabled_channels": ["log"]})
        assert nm._total_notifications == 0
        nm._last_sent.clear()
        nm.notify("T1", "M1")
        nm._last_sent.clear()
        nm.notify("T2", "M2")
        assert nm._total_notifications == 2


# ---------------------------------------------------------------------------
# test_channel
# ---------------------------------------------------------------------------


class TestTestChannel:
    """test_channel() method coverage."""

    def test_test_channel_log_succeeds(self) -> None:
        """Testing the log channel should always succeed."""
        nm = NotificationManager()
        ok, detail = nm.test_channel("log")
        assert ok is True
        assert "logged" in detail

    def test_test_channel_handler_exception_returns_false(self) -> None:
        """If handler raises during test, returns (False, error message)."""
        nm = NotificationManager()

        def boom(title, message, level):
            raise RuntimeError("boom")

        with patch.object(nm, "_dispatch_map", return_value={"log": boom}):
            ok, detail = nm.test_channel("log")

        assert ok is False
        assert "boom" in detail

    def test_test_channel_webhook_no_url(self) -> None:
        """Testing webhook with no URL returns failure."""
        nm = NotificationManager()
        ok, detail = nm.test_channel("webhook")
        assert ok is False
        assert "no webhook_url" in detail.lower()


# ---------------------------------------------------------------------------
# _send_log with various levels
# ---------------------------------------------------------------------------


class TestSendLogLevels:
    """_send_log routes to the correct logging level."""

    @pytest.mark.parametrize("level", ["info", "success", "warning", "error", "critical"])
    def test_log_level_succeeds(self, level: str) -> None:
        """All valid levels should succeed in _send_log."""
        nm = NotificationManager()
        ok, detail = nm._send_log("Title", "Message", level)
        assert ok is True
        assert detail == "logged"


# ---------------------------------------------------------------------------
# Channel sends with mocked HTTP
# ---------------------------------------------------------------------------


class TestWebhookSend:
    """_send_webhook with mocked HTTP."""

    def test_webhook_success(self) -> None:
        """Webhook sends to configured URL with correct payload."""
        nm = NotificationManager({"webhook_url": "https://example.com/hook"})

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("core.notifications.urlopen", return_value=mock_resp):
            ok, detail = nm._send_webhook("Title", "Body", "info")

        assert ok is True
        assert "200" in detail


class TestDiscordSend:
    """_send_discord with mocked HTTP."""

    def test_discord_success(self) -> None:
        """Discord webhook sends colour-coded embed."""
        nm = NotificationManager({"discord_webhook": "https://discord.com/api/webhooks/test"})

        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("core.notifications.urlopen", return_value=mock_resp) as mock_open:
            ok, detail = nm._send_discord("Alert", "Something happened", "error")

        assert ok is True
        assert "204" in detail
        # Verify the payload includes an embed with the correct colour
        call_args = mock_open.call_args
        req = call_args[0][0]
        import json

        payload = json.loads(req.data)
        assert payload["embeds"][0]["color"] == LEVEL_COLORS["error"]

    def test_discord_uses_info_color_for_unknown_level(self) -> None:
        """Discord falls back to info colour for unknown levels."""
        nm = NotificationManager({"discord_webhook": "https://discord.com/api/webhooks/test"})

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("core.notifications.urlopen", return_value=mock_resp) as mock_open:
            nm._send_discord("T", "M", "nonexistent")

        call_args = mock_open.call_args
        req = call_args[0][0]
        import json

        payload = json.loads(req.data)
        assert payload["embeds"][0]["color"] == LEVEL_COLORS["info"]


# ---------------------------------------------------------------------------
# Email — TLS and list recipients
# ---------------------------------------------------------------------------


class TestEmailEdgeCases:
    """Additional email channel tests."""

    def test_email_with_tls_enabled(self) -> None:
        """Email with TLS calls starttls and ehlo."""
        nm = NotificationManager(
            {
                "smtp_server": "smtp.example.com:587",
                "email_from": "bot@example.com",
                "email_to": "user@example.com",
                "smtp_use_tls": True,
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value = instance
            ok, detail = nm._send_email("T", "M", "info")

        assert ok is True
        instance.starttls.assert_called_once()
        assert instance.ehlo.call_count == 2

    def test_email_list_recipients(self) -> None:
        """Email with list of recipients (not comma-separated string)."""
        nm = NotificationManager(
            {
                "smtp_server": "smtp.example.com:587",
                "email_from": "bot@example.com",
                "email_to": ["a@b.com", "c@d.com"],
                "smtp_use_tls": False,
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value = instance
            ok, detail = nm._send_email("T", "M", "info")

        assert ok is True
        call_args = instance.sendmail.call_args
        recipients = call_args[0][1]
        assert len(recipients) == 2

    def test_email_smtp_default_port(self) -> None:
        """SMTP server without port defaults to 587."""
        nm = NotificationManager(
            {
                "smtp_server": "smtp.example.com",
                "email_from": "bot@example.com",
                "email_to": "user@example.com",
                "smtp_use_tls": False,
            }
        )
        with patch("core.notifications.smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value = instance
            nm._send_email("T", "M", "info")

        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants are consistent."""

    def test_valid_levels_matches_level_colors(self) -> None:
        """VALID_LEVELS should contain exactly the keys in LEVEL_COLORS."""
        assert VALID_LEVELS == set(LEVEL_COLORS)

    def test_channels_tuple(self) -> None:
        """CHANNELS should be a tuple with expected values."""
        assert isinstance(CHANNELS, tuple)
        assert set(CHANNELS) == {"toast", "webhook", "discord", "email", "log"}

    def test_stats_initialized_for_all_channels(self) -> None:
        """Stats should have entries for every channel."""
        nm = NotificationManager()
        for ch in CHANNELS:
            assert ch in nm._stats
            assert nm._stats[ch] == {"sent": 0, "succeeded": 0, "failed": 0}


# ---------------------------------------------------------------------------
# get_channels with no activity
# ---------------------------------------------------------------------------


class TestGetChannelsClean:
    """get_channels() when no notifications have been sent."""

    def test_last_results_empty_initially(self) -> None:
        """Before any notifications, last_results should be empty."""
        nm = NotificationManager()
        info = nm.get_channels()
        assert info["last_results"] == {}
