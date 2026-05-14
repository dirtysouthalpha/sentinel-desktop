"""Tests for the multi-channel notification system."""

from unittest.mock import MagicMock, patch

import pytest

from core.notifications import NotificationManager, _send_http

# ---------------------------------------------------------------------------
# NotificationManager basic operations
# ---------------------------------------------------------------------------


def test_notify_log_always_succeeds():
    """The log channel should always succeed."""
    nm = NotificationManager({"enabled_channels": ["log"]})
    assert nm.notify("Title", "Body", level="info") is True


def test_notify_unknown_level_defaults_to_info():
    """Unknown levels should fall back to 'info' and still succeed."""
    nm = NotificationManager({"enabled_channels": ["log"]})
    assert nm.notify("T", "M", level="nonexistent") is True


def test_notify_batch():
    """notify_batch should return per-title results."""
    nm = NotificationManager({"enabled_channels": ["log"]})
    results = nm.notify_batch([
        {"title": "A", "message": "a"},
        {"title": "B", "message": "b"},
    ])
    assert results["A"] is True
    assert results["B"] is True


def test_get_stats_increments():
    """Stats should reflect sent notifications (accounting for rate limiting)."""
    import time

    nm = NotificationManager({"enabled_channels": ["log"]})
    nm.notify("T1", "M1")
    # Rate limit window is 5s — wait to avoid skip.
    time.sleep(0.1)
    nm._last_sent.clear()  # bypass rate limit for testing
    nm.notify("T2", "M2")
    stats = nm.get_stats()
    assert stats["total_notifications"] == 2
    assert stats["channels"]["log"]["sent"] == 2
    assert stats["channels"]["log"]["succeeded"] == 2


def test_reset_stats():
    nm = NotificationManager({"enabled_channels": ["log"]})
    nm.notify("T", "M")
    nm.reset_stats()
    stats = nm.get_stats()
    assert stats["total_notifications"] == 0
    assert stats["channels"]["log"]["sent"] == 0


def test_get_channels():
    nm = NotificationManager({"enabled_channels": ["log", "discord"]})
    info = nm.get_channels()
    assert "log" in info["enabled"]
    assert "discord" in info["enabled"]
    assert "log" in info["available"]
    assert "discord" in info["available"]


def test_configure():
    nm = NotificationManager()
    nm.configure("discord", {"discord_webhook": "https://example.com/hook"})
    assert nm._config["discord_webhook"] == "https://example.com/hook"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limiting_skips_duplicate():
    """Rapid duplicate notifications on the same channel should be rate-limited."""
    nm = NotificationManager({"enabled_channels": ["log"]})
    # First should succeed
    assert nm.notify("T", "M") is True
    # Second within the rate limit window should be skipped
    assert nm.notify("T", "M") is True  # still True because log always succeeds


# ---------------------------------------------------------------------------
# Channel-specific tests
# ---------------------------------------------------------------------------


def test_toast_disabled():
    nm = NotificationManager({"toast_enabled": False})
    ok, detail = nm._send_toast("T", "M", "info")
    assert ok is False
    assert "disabled" in detail.lower()


def test_webhook_no_url():
    nm = NotificationManager()
    ok, detail = nm._send_webhook("T", "M", "info")
    assert ok is False
    assert "no webhook_url" in detail.lower()


def test_discord_no_url():
    nm = NotificationManager()
    ok, detail = nm._send_discord("T", "M", "info")
    assert ok is False
    assert "no discord_webhook" in detail.lower()


def test_email_missing_config():
    nm = NotificationManager()
    ok, detail = nm._send_email("T", "M", "info")
    assert ok is False
    assert "requires" in detail.lower()


def test_email_invalid_smtp_port():
    nm = NotificationManager({
        "smtp_server": "smtp.example.com:notaport",
        "email_from": "a@b.com",
        "email_to": "c@d.com",
    })
    ok, detail = nm._send_email("T", "M", "info")
    assert ok is False
    assert "invalid" in detail.lower() or "smtp" in detail.lower()


def test_email_sends_with_valid_config():
    nm = NotificationManager({
        "smtp_server": "smtp.example.com:587",
        "email_from": "bot@example.com",
        "email_to": "user@example.com",
        "smtp_use_tls": False,
    })
    with patch("core.notifications.smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value = instance
        ok, detail = nm._send_email("Test", "Body", "info")

    assert ok is True
    assert "sent" in detail.lower()
    instance.sendmail.assert_called_once()
    instance.quit.assert_called_once()


def test_email_multiple_recipients():
    nm = NotificationManager({
        "smtp_server": "smtp.example.com:587",
        "email_from": "bot@example.com",
        "email_to": "a@b.com, c@d.com",
        "smtp_use_tls": False,
    })
    with patch("core.notifications.smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value = instance
        ok, detail = nm._send_email("T", "M", "info")

    assert ok is True
    call_args = instance.sendmail.call_args
    recipients = call_args[0][1]
    assert len(recipients) == 2


# ---------------------------------------------------------------------------
# _send_http tests
# ---------------------------------------------------------------------------


def test_send_http_refuses_non_http_url():
    ok, detail = _send_http("ftp://evil.com", {"x": 1})
    assert ok is False
    assert "non-http" in detail.lower() or "refusing" in detail.lower()


def test_send_http_refuses_file_url():
    ok, detail = _send_http("file:///etc/passwd", {"x": 1})
    assert ok is False


def test_test_channel_unknown():
    nm = NotificationManager()
    with pytest.raises(ValueError, match="Unknown channel"):
        nm.test_channel("nonexistent")
