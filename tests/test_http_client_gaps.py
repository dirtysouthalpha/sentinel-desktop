"""Gap tests for core.http_client — covers lines 86, 97, 141, 190-191, 195, 205."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.http_client import http_delete, http_download, http_get, http_put


class TestHttpPutAndDelete:
    """http_put and http_delete return values (lines 86, 97)."""

    def _mock_response(self, status=200, text="ok"):
        resp = MagicMock()
        resp.status_code = status
        resp.is_success = 200 <= status < 300
        resp.text = text
        resp.headers = {"content-type": "text/plain"}
        return resp

    def test_http_put_returns_success(self):
        with patch("httpx.request", return_value=self._mock_response(200)):
            result = http_put("https://example.com/resource", json={"key": "val"})
        assert result["success"] is True
        assert result["status_code"] == 200

    def test_http_put_passes_method(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_put("https://example.com/r")
        args, _ = mock_req.call_args
        assert args[0] == "PUT"

    def test_http_delete_returns_success(self):
        with patch("httpx.request", return_value=self._mock_response(204)):
            result = http_delete("https://example.com/resource")
        assert result["success"] is True

    def test_http_delete_passes_method(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_delete("https://example.com/r")
        args, _ = mock_req.call_args
        assert args[0] == "DELETE"

    def test_http_put_body_string(self):
        with patch("httpx.request", return_value=self._mock_response()) as mock_req:
            http_put("https://example.com/r", body="raw data")
        _, kwargs = mock_req.call_args
        assert kwargs["content"] == b"raw data"

    def test_http_delete_invalid_url(self):
        result = http_delete("ftp://not-http.example.com")
        assert result["success"] is False
        assert result["error"] == "invalid_url"


class TestHttpDownloadImportError:
    """ImportError path in http_download (line 141)."""

    def test_download_no_httpx(self, tmp_path):
        dest = str(tmp_path / "out.bin")
        with patch.dict("sys.modules", {"httpx": None}):
            result = http_download("https://example.com/file", dest)
        assert result["success"] is False
        assert result["error"] == "missing_dep"


class TestRequestJsonParseError:
    """response.json() raises inside _request (lines 190-191)."""

    def test_json_parse_error_falls_back_to_text(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.text = "not-valid-json-but-content-type-says-json"
        resp.headers = {"content-type": "application/json; charset=utf-8"}
        resp.json.side_effect = ValueError("not valid json")

        with patch("httpx.request", return_value=resp):
            result = http_get("https://example.com/api")

        assert result["success"] is True
        assert result["body"] == "not-valid-json-but-content-type-says-json"


class TestRequestBodyTruncation:
    """Large response body gets truncated (line 195)."""

    def test_large_body_is_truncated(self):
        big_text = "x" * 60_000
        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.text = big_text
        resp.headers = {"content-type": "text/plain"}

        with patch("httpx.request", return_value=resp):
            result = http_get("https://example.com/big")

        assert "[... truncated" in result["body"]
        assert len(result["body"]) < len(big_text)


class TestRequestImportError:
    """ImportError path in _request (line 205)."""

    def test_request_no_httpx(self):
        with patch.dict("sys.modules", {"httpx": None}):
            result = http_get("https://example.com/api")
        assert result["success"] is False
        assert result["error"] == "missing_dep"
        assert "httpx not installed" in result["output"]
