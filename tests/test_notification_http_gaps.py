"""Gap tests for _send_http retry loop and network error paths."""

from unittest.mock import MagicMock, patch
from urllib.error import URLError

from core.notifications import _send_http


class TestSendHttpRetryLoop:
    """_send_http retries on network errors and returns last error."""

    @patch("core.notifications.time.sleep")
    @patch("core.notifications.urlopen")
    def test_urlerror_retries_and_returns_error(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = URLError("connection refused")
        ok, detail = _send_http("https://example.com/hook", {"msg": "hi"}, retries=2)
        assert ok is False
        assert "connection refused" in detail
        assert mock_urlopen.call_count == 2
        assert mock_sleep.call_count == 1  # one sleep between attempts

    @patch("core.notifications.time.sleep")
    @patch("core.notifications.urlopen")
    def test_oserror_retries_and_returns_error(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = OSError("network down")
        ok, detail = _send_http("https://example.com/hook", {"msg": "hi"}, retries=3)
        assert ok is False
        assert "network down" in detail
        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("core.notifications.time.sleep")
    @patch("core.notifications.urlopen")
    def test_succeeds_on_second_attempt(self, mock_urlopen, mock_sleep):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"ok"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [URLError("timeout"), resp]
        ok, detail = _send_http("https://example.com/hook", {"msg": "hi"}, retries=2)
        assert ok is True
        assert "200" in detail
        assert mock_sleep.call_count == 1

    @patch("core.notifications.time.sleep")
    @patch("core.notifications.urlopen")
    def test_single_retry_no_sleep(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = URLError("fail")
        _send_http("https://example.com/hook", {"msg": "hi"}, retries=1)
        assert mock_sleep.call_count == 0


class TestSendHttpNonHttpUrl:
    """_send_http refuses non-http(s) URLs."""

    def test_file_url_refused(self):
        ok, detail = _send_http("file:///etc/passwd", {"msg": "hi"})
        assert ok is False
        assert "non-http" in detail

    def test_ftp_url_refused(self):
        ok, detail = _send_http("ftp://example.com/file", {"msg": "hi"})
        assert ok is False
        assert "non-http" in detail
