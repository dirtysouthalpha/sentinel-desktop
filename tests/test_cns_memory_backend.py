"""Tests for the CNS 2.0 Memory Backend."""
import json
from unittest.mock import patch, MagicMock

import pytest

from core.cns.memory_backend import (
    InMemoryBackend,
    MemoryBackend,
    NeuralisBackend,
)


class TestInMemoryBackend:
    def test_remember_and_recall(self):
        be = InMemoryBackend()
        be.remember("key1", "value1")
        assert be.recall("key1") == "value1"

    def test_recall_missing_returns_none(self):
        be = InMemoryBackend()
        assert be.recall("nope") is None

    def test_remember_overwrites(self):
        be = InMemoryBackend()
        be.remember("k", "v1")
        be.remember("k", "v2")
        assert be.recall("k") == "v2"

    def test_search_by_key(self):
        be = InMemoryBackend()
        be.remember("alpha", "first")
        be.remember("beta", "second")
        results = be.search("alpha")
        assert len(results) == 1
        assert results[0]["key"] == "alpha"

    def test_search_by_value(self):
        be = InMemoryBackend()
        be.remember("k1", "hello world")
        be.remember("k2", "goodbye")
        results = be.search("hello")
        assert len(results) == 1
        assert results[0]["key"] == "k1"

    def test_search_limit(self):
        be = InMemoryBackend()
        for i in range(10):
            be.remember(f"key_{i}", f"val_{i}")
        results = be.search("key", limit=3)
        assert len(results) == 3

    def test_search_no_match(self):
        be = InMemoryBackend()
        be.remember("a", "x")
        assert be.search("zzz") == []

    def test_clear(self):
        be = InMemoryBackend()
        be.remember("k", "v")
        be.clear()
        assert be.recall("k") is None
        assert len(be) == 0

    def test_len(self):
        be = InMemoryBackend()
        assert len(be) == 0
        be.remember("a", 1)
        be.remember("b", 2)
        assert len(be) == 2

    def test_remember_returns_true(self):
        be = InMemoryBackend()
        assert be.remember("k", "v") is True

    def test_is_abstract(self):
        """MemoryBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MemoryBackend()  # type: ignore[abstract]


class TestNeuralisBackend:
    def test_default_url(self):
        be = NeuralisBackend()
        assert be.base_url == "http://localhost:8001"

    def test_custom_url(self):
        be = NeuralisBackend(base_url="http://brain.local:9000")
        assert be.base_url == "http://brain.local:9000"

    def test_url_trailing_slash_stripped(self):
        be = NeuralisBackend(base_url="http://example.com/")
        assert be.base_url == "http://example.com"

    def test_remember_falls_back_on_failure(self, monkeypatch):
        be = NeuralisBackend()
        monkeypatch.setattr(be, "_request", lambda *a, **kw: None)
        result = be.remember("k", "v")
        assert result is True  # fallback succeeds
        assert be._fallback.recall("k") == "v"

    def test_recall_falls_back_on_failure(self, monkeypatch):
        be = NeuralisBackend()
        be._fallback.remember("existing", "data")
        monkeypatch.setattr(be, "_request", lambda *a, **kw: None)
        assert be.recall("existing") == "data"

    def test_search_falls_back_on_failure(self, monkeypatch):
        be = NeuralisBackend()
        be._fallback.remember("hello", "world")
        monkeypatch.setattr(be, "_request", lambda *a, **kw: None)
        results = be.search("hello")
        assert len(results) == 1
        assert results[0]["key"] == "hello"

    def test_remember_online_success(self, monkeypatch):
        be = NeuralisBackend()
        monkeypatch.setattr(be, "_request", lambda *a, **kw: {"status": "ok"})
        result = be.remember("k", "v")
        assert result is True
        assert be.is_online is True

    def test_recall_online_success(self, monkeypatch):
        be = NeuralisBackend()
        monkeypatch.setattr(
            be, "_request", lambda *a, **kw: {"value": "brain_data"}
        )
        assert be.recall("k") == "brain_data"

    def test_search_online_success(self, monkeypatch):
        be = NeuralisBackend()
        search_response = {"results": [{"id": 1, "content": "neuron"}]}
        monkeypatch.setattr(be, "_request", lambda *a, **kw: search_response)
        results = be.search("query")
        assert len(results) == 1
        assert results[0]["key"] == 1

    def test_search_online_list_response(self, monkeypatch):
        be = NeuralisBackend()
        monkeypatch.setattr(
            be, "_request", lambda *a, **kw: [{"id": 42, "content": "x"}]
        )
        results = be.search("q")
        assert len(results) == 1
        assert results[0]["key"] == 42

    def test_is_online_false_when_unreachable(self, monkeypatch):
        be = NeuralisBackend()
        monkeypatch.setattr(be, "_request", lambda *a, **kw: None)
        assert be.is_online is False

    def test_is_online_true_when_reachable(self, monkeypatch):
        be = NeuralisBackend()
        monkeypatch.setattr(be, "_request", lambda *a, **kw: {"ok": True})
        assert be.is_online is True

    def test_api_key_stored(self):
        be = NeuralisBackend(api_key="secret123")
        assert be.api_key == "secret123"

    def test_api_key_default_none(self):
        be = NeuralisBackend()
        assert be.api_key is None
