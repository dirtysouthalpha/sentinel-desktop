"""Tests for core.http_client — http_get, http_post, http_download."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.http_client import http_delete, http_download, http_get, http_post, http_put


# ── URL validation ────────────────────────────────────────────────────────────

class TestUrlValidation:
    def test_rejects_file_urls(self):
        result = http_get("file:///etc/passwd")
        assert result["success"] is False
        assert "invalid_url" in result.get("error", "")

    def test_rejects_custom_scheme(self):
        result = http_get("ftp://example.com/file")
        assert result["success"] is False

    def test_rejects_empty_url(self):
        result = http_get("")
        assert result["success"] is False


# ── http_get ──────────────────────────────────────────────────────────────────

class TestHttpGet:
    def _mock_response(self, status=200, text='{"ok":true}', content_type="application/json"):
        resp = MagicMock()
        resp.status_code = status
        resp.is_success = (200 <= status < 300)
        resp.text = text
        resp.json.return_value = {"ok": True}
        resp.headers = {"content-type": content_type}
        return resp

    def test_get_success(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            result = http_get("https://example.com/api")
        assert result["success"] is True
        assert result["status_code"] == 200
        mock_req.assert_called_once()

    def test_get_passes_headers(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_get("https://example.com", headers={"X-Token": "abc"})
        _, kwargs = mock_req.call_args
        assert kwargs["headers"]["X-Token"] == "abc"

    def test_get_passes_params(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_get("https://example.com", params={"page": "1"})
        _, kwargs = mock_req.call_args
        assert kwargs["params"] == {"page": "1"}

    def test_get_404_returns_failure(self):
        with patch("httpx.request", return_value=self._mock_response(status=404, text="not found", content_type="text/plain")):
            result = http_get("https://example.com/missing")
        assert result["success"] is False
        assert result["status_code"] == 404

    def test_get_returns_parsed_json(self):
        with patch("httpx.request", return_value=self._mock_response()):
            result = http_get("https://example.com/json")
        assert result["body"] == {"ok": True}

    def test_get_returns_text_for_non_json(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.text = "plain text body"
        resp.headers = {"content-type": "text/plain"}
        with patch("httpx.request", return_value=resp):
            result = http_get("https://example.com/text")
        assert result["body"] == "plain text body"

    def test_get_network_error_returns_failure(self):
        with patch("httpx.request", side_effect=Exception("connection refused")):
            result = http_get("https://example.com")
        assert result["success"] is False
        assert "connection refused" in result["output"]

    def test_get_ssl_verify_false_passes_to_httpx(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_get("https://example.com", verify_ssl=False)
        _, kwargs = mock_req.call_args
        assert kwargs["verify"] is False


# ── http_post ─────────────────────────────────────────────────────────────────

class TestHttpPost:
    def _mock_response(self, status=200):
        resp = MagicMock()
        resp.status_code = status
        resp.is_success = True
        resp.text = '{"created":true}'
        resp.json.return_value = {"created": True}
        resp.headers = {"content-type": "application/json"}
        return resp

    def test_post_with_json_body(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            result = http_post("https://example.com/api", json={"key": "value"})
        assert result["success"] is True
        _, kwargs = mock_req.call_args
        assert kwargs["json"] == {"key": "value"}

    def test_post_with_raw_body(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_post("https://example.com/api", body="raw content")
        _, kwargs = mock_req.call_args
        assert kwargs["content"] == b"raw content"

    def test_post_empty_body(self):
        with patch("httpx.request", return_value=self._mock_response()):
            result = http_post("https://example.com/api")
        assert result["success"] is True


# ── http_download ─────────────────────────────────────────────────────────────

class TestHttpDownload:
    def test_download_writes_file(self, tmp_path):
        dest = tmp_path / "downloaded.txt"
        content = b"file content"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = [content]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response):
            result = http_download("https://example.com/file.txt", str(dest))

        assert result["success"] is True
        assert dest.exists()
        assert dest.read_bytes() == content

    def test_download_rejects_invalid_url(self, tmp_path):
        result = http_download("file:///etc/passwd", str(tmp_path / "out.txt"))
        assert result["success"] is False

    def test_download_creates_parent_dirs(self, tmp_path):
        dest = tmp_path / "nested" / "dir" / "file.bin"
        content = b"data"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = [content]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response):
            result = http_download("https://example.com/data", str(dest))

        assert result["success"] is True
        assert dest.parent.exists()


# ── Executor integration ──────────────────────────────────────────────────────

class TestHttpActionsInExecutor:
    def test_http_get_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "http_get" in ActionExecutor._dispatch_table

    def test_http_post_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "http_post" in ActionExecutor._dispatch_table

    def test_http_download_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "http_download" in ActionExecutor._dispatch_table

    def test_http_get_executor_action(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.text = "ok"
        resp.json.side_effect = Exception("not json")
        resp.headers = {"content-type": "text/plain"}
        with patch("httpx.request", return_value=resp):
            from core.action_executor import ActionExecutor
            executor = ActionExecutor()
            result = executor.execute_sync({"action": "http_get", "url": "https://example.com"})
        assert result["success"] is True
        assert result["status_code"] == 200
