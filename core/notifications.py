"""
Sentinel Desktop v3.0 — Multi-Channel Notification System.

Provides desktop and remote notifications for task completion, errors,
and status updates across five channels:

* **toast**   — Windows 10 toast popup (win10toast with ctypes fallback)
* **webhook** — Generic HTTP POST webhook (JSON payload)
* **discord** — Discord webhook with colour-coded embeds
* **email**   — SMTP email with plain-text body
* **log**     — Always-on Python ``logging`` output (cannot be disabled)

All HTTP is performed via ``urllib.request`` so there are **zero external
dependencies** beyond the optional ``win10toast`` package for native
toast notifications on Windows.

Every channel degrades gracefully — a failure in one channel never
prevents other channels from firing.

Quick start::

    from core.notifications import NotificationManager

    nm = NotificationManager({
        "enabled_channels": ["toast", "discord", "log"],
        "discord_webhook": "https://discord.com/api/webhooks/...",
    })

    # Send to all enabled channels
    nm.notify("Task complete", "Password reset succeeded.", level="success")

    # Send to a specific channel only
    nm.notify("Alert", "Disk space critical!", level="error",
              channels=["discord"])

    # Test a single channel
    ok, detail = nm.test_channel("discord")

    # Reconfigure at runtime
    nm.configure("discord", {"discord_webhook": "https://discord.com/..."})

    # Batch notifications
    nm.notify_batch([
        {"title": "Step 1 done", "message": "...", "level": "info"},
        {"title": "Step 2 done", "message": "...", "level": "success"},
    ])

    # View statistics
    stats = nm.get_stats()
"""

import json
import logging
import platform
import smtplib
import threading
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

__all__ = ["NotificationManager", "CHANNELS", "LEVEL_COLORS", "VALID_LEVELS"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Mapping of notification level names to Discord embed colour integers.
LEVEL_COLORS: Dict[str, int] = {
    "info":     0x3498DB,   # blue
    "success":  0x2ECC71,   # green
    "warning":  0xF39C12,   # orange
    "error":    0xE74C3C,   # red
    "critical": 0x8E44AD,   # purple
}

#: Set of valid notification levels.
VALID_LEVELS = set(LEVEL_COLORS)

#: Canonical channel identifiers.
CHANNELS = ("toast", "webhook", "discord", "email", "log")

#: Default HTTP timeout in seconds.
HTTP_TIMEOUT = 10

#: Maximum number of automatic retries per HTTP call.
MAX_RETRIES = 2

#: Minimum seconds between notifications on the same channel (rate limit).
RATE_LIMIT_SECONDS = 5.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_windows() -> bool:
    """Return ``True`` when running on Microsoft Windows."""
    return platform.system() == "Windows"


def _send_http(
    url: str,
    payload: dict,
    timeout: int = HTTP_TIMEOUT,
    retries: int = MAX_RETRIES,
) -> Tuple[bool, str]:
    """POST *payload* as JSON to *url* with linear back-off retries.

    Returns a ``(ok, detail)`` tuple where *ok* is ``True`` when the
    server responded with a 2xx status code.
    """
    data = json.dumps(payload).encode("utf-8")
    last_error = ""

    for attempt in range(1, retries + 1):
        try:
            req = Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 0)
                body = resp.read().decode("utf-8", errors="replace")[:512]
                if 200 <= status < 300:
                    return True, f"HTTP {status}: {body}"
                last_error = f"HTTP {status}: {body}"
        except (URLError, OSError) as exc:
            last_error = str(exc)

        # Simple linear back-off before retrying.
        if attempt < retries:
            time.sleep(0.5 * attempt)

    return False, last_error


# ---------------------------------------------------------------------------
# NotificationManager
# ---------------------------------------------------------------------------


class NotificationManager:
    """Route notifications to multiple channels with graceful degradation.

    Parameters
    ----------
    config : dict, optional
        Initial configuration.  Accepted keys:

        =================== ============= ===================================
        Key                 Type          Description
        =================== ============= ===================================
        ``enabled_channels`` list[str]    Active channels (default ``["log"]``)
        ``webhook_url``      str | None   Generic HTTP POST endpoint
        ``email_to``         str | list   Recipient address(es)
        ``email_from``       str | None   Sender address
        ``smtp_server``      str | None   ``host:port`` string
        ``smtp_use_tls``     bool         Use STARTTLS (default ``True``)
        ``discord_webhook``  str | None   Discord webhook URL
        ``toast_enabled``    bool         Enable Windows toast (default auto)
        =================== ============= ===================================
    """

    def __init__(self, config: Optional[dict] = None):
        self._config: Dict[str, Any] = {
            "enabled_channels": ["log"],
            "webhook_url": None,
            "email_to": None,
            "email_from": None,
            "smtp_server": None,
            "smtp_use_tls": True,
            "discord_webhook": None,
            "toast_enabled": _is_windows(),
        }
        if config:
            self._config.update({k: v for k, v in config.items() if v is not None})

        # Per-channel last-fire timestamp (monotonic) for rate limiting.
        self._last_sent: Dict[str, float] = {}

        # Per-channel last result cache.
        self._last_results: Dict[str, Tuple[bool, str]] = {}

        # Cumulative counters.
        self._stats: Dict[str, Dict[str, int]] = {
            ch: {"sent": 0, "succeeded": 0, "failed": 0} for ch in CHANNELS
        }
        self._total_notifications = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify(
        self,
        title: str,
        message: str,
        level: str = "info",
        channels: Optional[List[str]] = None,
    ) -> bool:
        """Send a notification to the requested channels.

        Parameters
        ----------
        title : str
            Short heading shown in toast / email subject / Discord title.
        message : str
            Body text describing the notification.
        level : str
            Severity — one of ``info``, ``success``, ``warning``,
            ``error``, or ``critical``.  Unknown levels fall back to
            ``info``.
        channels : list[str], optional
            Override the enabled-channels list for this call only.
            ``"log"`` is always appended regardless.

        Returns
        -------
        bool
            ``True`` if **every** requested channel succeeded.  ``False``
            means at least one channel failed (log always succeeds).
        """
        if level not in VALID_LEVELS:
            logger.warning(
                "Unknown notification level %r — falling back to 'info'", level,
            )
            level = "info"

        target_channels = self._resolve_channels(channels)
        all_ok = True
        self._total_notifications += 1

        for ch in target_channels:
            handler = self._dispatch_map().get(ch)
            if handler is None:
                logger.warning("Unknown channel %r — skipping", ch)
                continue

            # Per-channel rate limiting.
            now = time.monotonic()
            if now - self._last_sent.get(ch, 0) < RATE_LIMIT_SECONDS:
                logger.debug("Channel %r rate-limited — skipping", ch)
                continue

            try:
                ok, detail = handler(title, message, level)
                self._last_results[ch] = (ok, detail)
                self._last_sent[ch] = now
                self._stats[ch]["sent"] += 1
                if ok:
                    self._stats[ch]["succeeded"] += 1
                else:
                    self._stats[ch]["failed"] += 1
                    logger.error("Channel %r failed: %s", ch, detail)
                    all_ok = False
            except Exception as exc:
                # Graceful degradation — never let one channel kill others.
                self._last_results[ch] = (False, str(exc))
                self._stats[ch]["sent"] += 1
                self._stats[ch]["failed"] += 1
                logger.exception("Channel %r raised an unexpected exception", ch)
                all_ok = False

        return all_ok

    def notify_batch(
        self,
        notifications: List[Dict[str, Any]],
    ) -> Dict[str, bool]:
        """Send multiple notifications in sequence.

        Each element is a dict with keys accepted by :meth:`notify`
        (``title``, ``message``, ``level``, ``channels``).

        Returns a mapping of ``{title: success_bool}``.
        """
        results: Dict[str, bool] = {}
        for n in notifications:
            title = n.get("title", "Untitled")
            results[title] = self.notify(
                title=title,
                message=n.get("message", ""),
                level=n.get("level", "info"),
                channels=n.get("channels"),
            )
        return results

    def test_channel(self, channel: str) -> Tuple[bool, str]:
        """Send a test notification to a single channel.

        Returns ``(ok, detail)``.

        Raises
        ------
        ValueError
            If *channel* is not a recognised channel name.
        """
        handler = self._dispatch_map().get(channel)
        if handler is None:
            raise ValueError(f"Unknown channel: {channel!r}")

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ok, detail = handler(
                "Sentinel Test",
                f"Test notification at {ts}",
                "info",
            )
        except Exception as exc:
            ok, detail = False, str(exc)

        self._last_results[channel] = (ok, detail)
        return ok, detail

    def configure(self, channel: str, settings: dict) -> None:
        """Update configuration relevant to *channel*.

        *settings* maps directly onto internal config keys for that
        channel.  Example::

            nm.configure("discord", {"discord_webhook": "https://..."})
            nm.configure("email", {
                "smtp_server": "smtp.example.com:587",
                "email_from": "bot@example.com",
                "email_to": "admin@example.com",
            })
        """
        for key, value in settings.items():
            self._config[key] = value
        logger.info("Channel %r reconfigured: %s", channel, list(settings.keys()))

    def get_channels(self) -> Dict[str, Any]:
        """Return current channel configuration and last-send status.

        Returns a dict with keys:

        * ``enabled``       — list of currently enabled channel names
        * ``available``     — all recognised channel names
        * ``last_results``  — per-channel ``{ok, detail}`` of last send
        """
        return {
            "enabled": list(self._config["enabled_channels"]),
            "available": list(CHANNELS),
            "last_results": {
                ch: {"ok": ok, "detail": detail}
                for ch, (ok, detail) in self._last_results.items()
            },
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return cumulative notification statistics.

        Example return value::

            {
                "total_notifications": 42,
                "channels": {
                    "discord": {"sent": 10, "succeeded": 9, "failed": 1},
                    ...
                }
            }
        """
        return {
            "total_notifications": self._total_notifications,
            "channels": dict(self._stats),
        }

    def reset_stats(self) -> None:
        """Zero-out all cumulative counters."""
        self._stats = {
            ch: {"sent": 0, "succeeded": 0, "failed": 0} for ch in CHANNELS
        }
        self._total_notifications = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_channels(self, override: Optional[List[str]]) -> List[str]:
        """Determine the final channel list, always including ``"log"``."""
        channels = list(override) if override else list(
            self._config["enabled_channels"],
        )
        if "log" not in channels:
            channels.append("log")
        return channels

    def _dispatch_map(self) -> Dict[str, Any]:
        """Return ``{channel_name: handler_callable}``."""
        return {
            "toast":   self._send_toast,
            "webhook": self._send_webhook,
            "discord": self._send_discord,
            "email":   self._send_email,
            "log":     self._send_log,
        }

    # ------------------------------------------------------------------
    # Channel implementations
    # ------------------------------------------------------------------

    # -- Log (always succeeds) -----------------------------------------

    def _send_log(self, title: str, message: str, level: str) -> Tuple[bool, str]:
        """Write to the standard Python logger.  Always succeeds."""
        log_fn = {
            "info":     logger.info,
            "success":  logger.info,
            "warning":  logger.warning,
            "error":    logger.error,
            "critical": logger.critical,
        }.get(level, logger.info)
        log_fn("[NOTIFICATION] %s — %s", title, message)
        return True, "logged"

    # -- Windows Toast -------------------------------------------------

    def _send_toast(self, title: str, message: str, level: str) -> Tuple[bool, str]:
        """Show a Windows toast notification.

        Tries ``win10toast`` first; falls back to a non-blocking
        ``MessageBoxW`` via ctypes.  Returns ``(False, reason)`` on
        non-Windows platforms or when toast is disabled.
        """
        if not self._config.get("toast_enabled"):
            return False, "Toast notifications disabled in config"

        if not _is_windows():
            return False, "Toast is only available on Windows"

        # Strategy 1: win10toast (optional third-party package).
        try:
            from win10toast import ToastNotifier  # type: ignore

            ToastNotifier().show_toast(
                title,
                message,
                icon_path=None,
                duration=5,
                threaded=True,
            )
            return True, "toast sent via win10toast"
        except ImportError:
            logger.debug("win10toast not installed — trying ctypes fallback")
        except Exception as exc:
            logger.debug("win10toast failed (%s) — trying ctypes fallback", exc)

        # Strategy 2: ctypes MessageBox in a daemon thread.
        try:
            import ctypes  # type: ignore

            def _show_box() -> None:
                # MB_ICONINFORMATION = 0x40
                ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                    0, message, f"Sentinel — {title}", 0x40,
                )

            threading.Thread(target=_show_box, daemon=True).start()
            return True, "toast sent via ctypes MessageBox"
        except Exception as exc:
            return False, f"Toast unavailable: {exc}"

    # -- Generic Webhook (HTTP POST) -----------------------------------

    def _send_webhook(self, title: str, message: str, level: str) -> Tuple[bool, str]:
        """POST a JSON payload to the configured ``webhook_url``."""
        url = self._config.get("webhook_url")
        if not url:
            return False, "No webhook_url configured"

        payload = {
            "title": title,
            "message": message,
            "level": level,
            "source": "sentinel-desktop",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        return _send_http(url, payload)

    # -- Discord Webhook -----------------------------------------------

    def _send_discord(self, title: str, message: str, level: str) -> Tuple[bool, str]:
        """Send a colour-coded rich embed to a Discord webhook URL."""
        url = self._config.get("discord_webhook")
        if not url:
            return False, "No discord_webhook configured"

        colour = LEVEL_COLORS.get(level, LEVEL_COLORS["info"])
        embed = {
            "title": title,
            "description": message,
            "color": colour,
            "footer": {"text": "Sentinel Desktop v3.0"},
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        payload = {"embeds": [embed]}
        return _send_http(url, payload)

    # -- Email (SMTP) --------------------------------------------------

    def _send_email(self, title: str, message: str, level: str) -> Tuple[bool, str]:
        """Send a plain-text email via SMTP with optional STARTTLS."""
        smtp_server = self._config.get("smtp_server")
        email_from = self._config.get("email_from")
        email_to = self._config.get("email_to")

        if not all([smtp_server, email_from, email_to]):
            return False, "email requires smtp_server, email_from, and email_to"

        # Normalise recipients to a flat list.
        if isinstance(email_to, str):
            recipients = [addr.strip() for addr in email_to.split(",")]
        else:
            recipients = list(email_to)

        subject = f"[Sentinel][{level.upper()}] {title}"
        body = (
            f"Sentinel Desktop Notification\n"
            f"{'=' * 40}\n"
            f"Level: {level.upper()}\n"
            f"Time:  {datetime.utcnow().isoformat()}Z\n\n"
            f"{message}\n"
        )

        # Build MIME message.
        msg = MIMEMultipart()
        msg["From"] = email_from
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Parse host and optional port.
        parts = smtp_server.rsplit(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 587
        use_tls = self._config.get("smtp_use_tls", True)

        try:
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=HTTP_TIMEOUT)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP(host, port, timeout=HTTP_TIMEOUT)

            server.sendmail(email_from, recipients, msg.as_string())
            server.quit()
            return True, f"email sent to {len(recipients)} recipient(s)"
        except Exception as exc:
            return False, f"SMTP error: {exc}"
