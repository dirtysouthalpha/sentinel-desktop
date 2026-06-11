"""Gap tests for core.dashboard — covers lines 133-134, 267-287.

  133-134: _get_gpu_info() exception path (SubprocessError)
  267-287: sentinel_chat() all paths (success, timeout, http error, exception)
"""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dashboard import _get_gpu_info, router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestGetGpuInfoException:
    """Lines 133-134 — subprocess errors are caught and return empty list."""

    def test_subprocess_error_returns_empty(self):
        with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
             patch("subprocess.run", side_effect=subprocess.SubprocessError("gpu busy")):
            result = _get_gpu_info()
        assert result == []

    def test_oserror_returns_empty(self):
        with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
             patch("subprocess.run", side_effect=OSError("no device")):
            result = _get_gpu_info()
        assert result == []

    def test_value_error_from_bad_output_returns_empty(self):
        bad_proc = MagicMock()
        bad_proc.returncode = 0
        bad_proc.stdout = "GeForce RTX, NOT_A_FLOAT, 8192, 70, 80, 120\n"
        with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
             patch("subprocess.run", return_value=bad_proc):
            result = _get_gpu_info()
        assert result == []


class TestSentinelChat:
    """Lines 267-287 — sentinel_chat endpoint exception branches."""

    def test_empty_message_returns_error(self, client):
        resp = client.post("/dashboard/chat/sentinel-ai", json={"message": ""})
        assert resp.status_code == 200
        assert resp.json()["error"] == "message is required"

    def test_missing_message_key_returns_error(self, client):
        resp = client.post("/dashboard/chat/sentinel-ai", json={})
        assert resp.status_code == 200
        assert "message is required" in resp.json()["error"]

    def test_success_path(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": "Hello from AI"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/dashboard/chat/sentinel-ai", json={"message": "hello"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["response"] == "Hello from AI"

    def test_timeout_exception_returns_timeout(self, client):
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/dashboard/chat/sentinel-ai", json={"message": "ping"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "timeout"
        assert "timeout" in body["error"].lower()

    def test_http_error_returns_error_status(self, client):
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPError("500 server error")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/dashboard/chat/sentinel-ai", json={"message": "ping"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "Model error" in body["error"]

    def test_generic_exception_returns_internal_error(self, client):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected crash"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/dashboard/chat/sentinel-ai", json={"message": "ping"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "Internal error" in body["error"]
