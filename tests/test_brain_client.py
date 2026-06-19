"""Unit tests for core/brain/client.py — mocked httpx, no live API calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

import core.brain.client as _mod
from core.brain.client import (
    BrainClient,
    BrainError,
    BrainUnavailableError,
    fire,
    get_default_client,
    recall,
    search,
    stats,
    think,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client(json_data: object = None, status_code: int = 200) -> MagicMock:
    """Build a fake httpx response and wire it into a fake httpx.Client."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data if json_data is not None else {"ok": True}
    resp.text = str(json_data)

    client = MagicMock()
    client.request.return_value = resp
    return client


def _make_brain(base_url: str = "http://testhost:8000") -> BrainClient:
    """Create a BrainClient with a pre-wired mock httpx.Client."""
    bc = BrainClient(base_url=base_url)
    bc._client = _mock_client()
    return bc


# ---------------------------------------------------------------------------
# Construction / env var
# ---------------------------------------------------------------------------


class TestBrainClientInit:
    def test_default_url_fallback(self, monkeypatch):
        monkeypatch.delenv("NEURALIS_BRAIN_URL", raising=False)
        bc = BrainClient()
        assert bc.base_url == "http://100.70.240.55:8000"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("NEURALIS_BRAIN_URL", "http://custom:9999")
        bc = BrainClient()
        assert bc.base_url == "http://custom:9999"

    def test_explicit_url_takes_priority(self, monkeypatch):
        monkeypatch.setenv("NEURALIS_BRAIN_URL", "http://env:1111")
        bc = BrainClient(base_url="http://explicit:2222")
        assert bc.base_url == "http://explicit:2222"

    def test_trailing_slash_stripped(self):
        bc = BrainClient(base_url="http://host:8000/")
        assert not bc.base_url.endswith("/")


# ---------------------------------------------------------------------------
# _get_client lazy init
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_lazy_creates_httpx_client(self):
        bc = BrainClient(base_url="http://test:8000")
        assert bc._client is None
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            bc._get_client()
        mock_cls.assert_called_once_with(base_url="http://test:8000", timeout=5.0)
        assert bc._client is not None

    def test_reuses_existing_client(self):
        bc = BrainClient(base_url="http://test:8000")
        fake = MagicMock()
        bc._client = fake
        with patch("httpx.Client") as mock_cls:
            result = bc._get_client()
        mock_cls.assert_not_called()
        assert result is fake


# ---------------------------------------------------------------------------
# _request — network errors → BrainUnavailableError
# ---------------------------------------------------------------------------


class TestRequest:
    def test_connect_error_raises_unavailable(self):
        bc = BrainClient(base_url="http://dead:8000")
        fake_client = MagicMock()
        fake_client.request.side_effect = httpx.ConnectError("refused")
        bc._client = fake_client
        with pytest.raises(BrainUnavailableError):
            bc._request("GET", "/health")

    def test_timeout_raises_unavailable(self):
        bc = BrainClient(base_url="http://dead:8000")
        fake_client = MagicMock()
        fake_client.request.side_effect = httpx.TimeoutException("timeout")
        bc._client = fake_client
        with pytest.raises(BrainUnavailableError):
            bc._request("GET", "/health")

    def test_non_2xx_raises_brain_error(self):
        bc = BrainClient(base_url="http://test:8000")
        bc._client = _mock_client(json_data={"error": "not found"}, status_code=404)
        with pytest.raises(BrainError):
            bc._request("GET", "/missing")

    def test_success_returns_json(self):
        bc = BrainClient(base_url="http://test:8000")
        bc._client = _mock_client(json_data={"result": 42})
        data = bc._request("GET", "/something")
        assert data == {"result": 42}

    def test_non_json_response_raises_brain_error(self):
        bc = BrainClient(base_url="http://test:8000")
        resp = MagicMock()
        resp.is_success = True
        resp.json.side_effect = ValueError("not json")
        fake_client = MagicMock()
        fake_client.request.return_value = resp
        bc._client = fake_client
        with pytest.raises(BrainError):
            bc._request("GET", "/broken")


# ---------------------------------------------------------------------------
# think
# ---------------------------------------------------------------------------


class TestThink:
    def test_posts_to_neurons_think(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"neuron": {"id": 7, "content": "test"}})
        bc._client = fake_client
        result = bc.think(content="test knowledge", region="knowledge", source="sentinel-desktop")
        fake_client.request.assert_called_once_with(
            "POST",
            "/neurons/think",
            json={"content": "test knowledge", "region": "knowledge", "source": "sentinel-desktop"},
        )
        assert result["neuron"]["id"] == 7

    def test_default_region_and_source(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"neuron": {"id": 1}})
        bc._client = fake_client
        bc.think(content="hello")
        _, kwargs = fake_client.request.call_args
        kwargs.get("json") or fake_client.request.call_args[1].get("json")
        # access positional args too
        call = fake_client.request.call_args
        sent_json = call.kwargs.get("json") or call.args[2] if len(call.args) > 2 else None
        if sent_json is None:
            sent_json = call[1].get("json")
        assert sent_json["region"] == "knowledge"
        assert sent_json["source"] == "sentinel-desktop"


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------


class TestRecall:
    def test_gets_recall_with_context_param(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"memories": [{"content": "remembered"}]})
        bc._client = fake_client
        result = bc.recall("fortigate ha")
        fake_client.request.assert_called_once_with(
            "GET", "/recall", params={"context": "fortigate ha"}
        )
        assert "memories" in result


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_gets_neurons_search_with_q(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"neurons": [{"id": 1, "content": "found"}]})
        bc._client = fake_client
        result = bc.search("sonicwall vpn")
        fake_client.request.assert_called_once_with(
            "GET", "/neurons/search", params={"q": "sonicwall vpn"}
        )
        assert "neurons" in result


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_gets_brain_stats(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"neurons": 100, "connections": 500})
        bc._client = fake_client
        result = bc.stats()
        fake_client.request.assert_called_once_with("GET", "/brain/stats")
        assert result["neurons"] == 100


# ---------------------------------------------------------------------------
# fire
# ---------------------------------------------------------------------------


class TestFire:
    def test_posts_to_neuron_fire_path(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"fired": True, "neuron_id": 42})
        bc._client = fake_client
        result = bc.fire(neuron_id=42)
        fake_client.request.assert_called_once_with("POST", "/neurons/42/fire")
        assert result["neuron_id"] == 42

    def test_fire_uses_neuron_id_in_path(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = _mock_client({"fired": True, "neuron_id": 99})
        bc._client = fake_client
        bc.fire(neuron_id=99)
        call_path = fake_client.request.call_args.args[1]
        assert "99" in call_path


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_true_when_health_succeeds(self):
        bc = BrainClient(base_url="http://test:8000")
        bc._client = _mock_client({"status": "ok"})
        assert bc.is_available() is True

    def test_returns_false_on_connect_error(self):
        bc = BrainClient(base_url="http://dead:8000")
        fake_client = MagicMock()
        fake_client.request.side_effect = httpx.ConnectError("refused")
        bc._client = fake_client
        assert bc.is_available() is False

    def test_returns_false_on_non_2xx(self):
        bc = BrainClient(base_url="http://test:8000")
        bc._client = _mock_client(status_code=503)
        assert bc.is_available() is False

    def test_never_raises(self):
        bc = BrainClient(base_url="http://dead:8000")
        fake_client = MagicMock()
        fake_client.request.side_effect = RuntimeError("unexpected")
        bc._client = fake_client
        # should not raise even on unexpected exception
        result = bc.is_available()
        assert result is False


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_clears_client(self):
        bc = BrainClient(base_url="http://test:8000")
        fake_client = MagicMock()
        bc._client = fake_client
        bc.close()
        fake_client.close.assert_called_once()
        assert bc._client is None

    def test_close_noop_when_no_client(self):
        bc = BrainClient(base_url="http://test:8000")
        bc.close()  # should not raise


# ---------------------------------------------------------------------------
# get_default_client singleton
# ---------------------------------------------------------------------------


class TestGetDefaultClient:
    def test_returns_brain_client(self):
        # reset singleton
        _mod._default_client = None
        c = get_default_client()
        assert isinstance(c, BrainClient)

    def test_singleton_same_instance(self):
        _mod._default_client = None
        c1 = get_default_client()
        c2 = get_default_client()
        assert c1 is c2
        _mod._default_client = None  # cleanup


# ---------------------------------------------------------------------------
# Module-level convenience wrappers delegate to get_default_client()
# ---------------------------------------------------------------------------


class TestConvenienceWrappers:
    def setup_method(self):
        self._fake_client = _mock_client()
        self._bc = BrainClient(base_url="http://test:8000")
        self._bc._client = self._fake_client
        _mod._default_client = self._bc

    def teardown_method(self):
        _mod._default_client = None

    def test_think_wrapper(self):
        self._fake_client.request.return_value = MagicMock(
            is_success=True, json=lambda: {"neuron": {"id": 1}}, text=""
        )
        result = think(content="hello", region="knowledge")
        assert "neuron" in result

    def test_recall_wrapper(self):
        self._fake_client.request.return_value = MagicMock(
            is_success=True, json=lambda: {"memories": []}, text=""
        )
        result = recall("context string")
        assert "memories" in result

    def test_search_wrapper(self):
        self._fake_client.request.return_value = MagicMock(
            is_success=True, json=lambda: {"neurons": []}, text=""
        )
        result = search("query")
        assert "neurons" in result

    def test_stats_wrapper(self):
        self._fake_client.request.return_value = MagicMock(
            is_success=True, json=lambda: {"neurons": 5}, text=""
        )
        result = stats()
        assert "neurons" in result

    def test_fire_wrapper(self):
        self._fake_client.request.return_value = MagicMock(
            is_success=True, json=lambda: {"fired": True, "neuron_id": 3}, text=""
        )
        result = fire(neuron_id=3)
        assert result["neuron_id"] == 3
