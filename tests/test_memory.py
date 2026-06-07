"""Tests for v11.0 Memory — episodic, semantic, working memory."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.episodic import EpisodicMemory, Episode
from core.memory.semantic import SemanticMemory
from core.memory.working import WorkingMemory


# ===========================================================================
# Episodic Memory
# ===========================================================================


class TestEpisodicMemory:
    def test_store_and_recall(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        ep_id = mem.store("Login to firewall", actions=[{"action": "web_open", "url": "https://192.168.1.1"}], outcome="Logged in", success=True)
        recent = mem.recall(limit=1)
        assert len(recent) == 1
        assert recent[0]["goal"] == "Login to firewall"
        assert recent[0]["success"] is True

    def test_recall_multiple(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store("Task 1")
        mem.store("Task 2")
        mem.store("Task 3")
        recent = mem.recall(limit=2)
        assert len(recent) == 2
        # Most recent first
        assert recent[0]["goal"] == "Task 3"

    def test_search(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store("Login to SonicWall firewall")
        mem.store("Check ARP table on Cisco switch")
        mem.store("Configure FortiGate VPN")
        results = mem.search("firewall")
        assert len(results) == 1
        assert "SonicWall" in results[0]["goal"]

    def test_search_by_tag(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store("Task A", tags=["networking", "firewall"])
        mem.store("Task B", tags=["desktop", "excel"])
        results = mem.search("firewall")
        assert len(results) == 1

    def test_count(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        assert mem.count() == 0
        mem.store("Task 1")
        mem.store("Task 2")
        assert mem.count() == 2

    def test_get_by_id(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        ep_id = mem.store("Find this episode")
        result = mem.get_by_id(ep_id)
        assert result is not None
        assert result["goal"] == "Find this episode"

    def test_get_missing_id(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        assert mem.get_by_id("nonexistent") is None

    def test_delete(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        ep_id = mem.store("Delete me")
        assert mem.count() == 1
        assert mem.delete(ep_id) is True
        assert mem.count() == 0

    def test_delete_missing(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        assert mem.delete("nope") is False

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "episodes.jsonl"
        mem1 = EpisodicMemory(path=path)
        mem1.store("Persistent task", outcome="Done", success=True)

        mem2 = EpisodicMemory(path=path)
        assert mem2.count() == 1
        recent = mem2.recall(limit=1)
        assert recent[0]["goal"] == "Persistent task"

    def test_search_empty(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        assert mem.search("anything") == []


class TestEpisode:
    def test_to_dict_roundtrip(self):
        ep = Episode(goal="Test", actions=[{"a": 1}], outcome="ok", success=True, tags=["test"])
        d = ep.to_dict()
        restored = Episode.from_dict(d)
        assert restored.goal == "Test"
        assert restored.actions == [{"a": 1}]
        assert restored.success is True
        assert restored.tags == ["test"]


# ===========================================================================
# Semantic Memory
# ===========================================================================


class TestSemanticMemory:
    def test_store_and_recall(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("firewall_ip", "192.168.1.1", category="network")
        result = mem.recall("firewall_ip")
        assert result is not None
        assert result["value"] == "192.168.1.1"
        assert result["category"] == "network"

    def test_update_existing(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("fw_ip", "192.168.1.1")
        mem.store("fw_ip", "10.0.0.1")
        result = mem.recall("fw_ip")
        assert result["value"] == "10.0.0.1"

    def test_query(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("sonicwall_ip", "192.168.1.1", category="network")
        mem.store("fortigate_ip", "10.0.0.1", category="network")
        mem.store("default_browser", "firefox", category="preferences")
        results = mem.query("ip")
        assert len(results) == 2

    def test_recall_category(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("key1", "val1", category="network")
        mem.store("key2", "val2", category="network")
        mem.store("key3", "val3", category="preferences")
        results = mem.recall_category("network")
        assert len(results) == 2

    def test_delete(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("temp", "value")
        assert mem.delete("temp") is True
        assert mem.recall("temp") is None

    def test_delete_missing(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        assert mem.delete("nope") is False

    def test_list_keys(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("alpha", "1")
        mem.store("beta", "2")
        keys = mem.list_keys()
        assert "alpha" in keys
        assert "beta" in keys

    def test_list_keys_by_category(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("net_1", "x", category="network")
        mem.store("pref_1", "y", category="prefs")
        keys = mem.list_keys(category="network")
        assert keys == ["net_1"]

    def test_count(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        assert mem.count() == 0
        mem.store("a", "1")
        mem.store("b", "2")
        assert mem.count() == 2

    def test_access_count_increments(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("popular", "value")
        mem.recall("popular")
        mem.recall("popular")
        mem.recall("popular")
        result = mem.recall("popular")
        assert result["access_count"] >= 3

    def test_tags_stored(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        mem.store("fw", "192.168.1.1", tags=["firewall", "sonicwall"])
        result = mem.recall("fw")
        assert "firewall" in result["tags"]
        assert "sonicwall" in result["tags"]

    def test_recall_missing(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "semantic.db")
        assert mem.recall("nonexistent") is None


# ===========================================================================
# Working Memory
# ===========================================================================


class TestWorkingMemory:
    def test_set_and_get(self):
        wm = WorkingMemory()
        wm.set("task", "Login to firewall")
        assert wm.get("task") == "Login to firewall"

    def test_get_default(self):
        wm = WorkingMemory()
        assert wm.get("missing", "default") == "default"

    def test_has(self):
        wm = WorkingMemory()
        wm.set("key", "value")
        assert wm.has("key") is True
        assert wm.has("missing") is False

    def test_delete(self):
        wm = WorkingMemory()
        wm.set("temp", "value")
        assert wm.delete("temp") is True
        assert wm.has("temp") is False

    def test_delete_missing(self):
        wm = WorkingMemory()
        assert wm.delete("nope") is False

    def test_push_and_get_bucket(self):
        wm = WorkingMemory()
        wm.push("urls", "https://192.168.1.1")
        wm.push("urls", "https://10.0.0.1")
        urls = wm.get_bucket("urls")
        assert len(urls) == 2
        assert urls[0] == "https://192.168.1.1"

    def test_bucket_limit(self):
        wm = WorkingMemory()
        for i in range(150):
            wm.push("items", i)
        items = wm.get_bucket("items", limit=200)
        assert len(items) == 100  # trimmed to MAX_BUCKET_SIZE

    def test_get_bucket_with_limit(self):
        wm = WorkingMemory()
        for i in range(30):
            wm.push("data", i)
        recent = wm.get_bucket("data", limit=5)
        assert len(recent) == 5
        assert recent[-1] == 29

    def test_clear_bucket(self):
        wm = WorkingMemory()
        wm.push("temp", "a")
        wm.push("temp", "b")
        wm.clear_bucket("temp")
        assert wm.get_bucket("temp") == []

    def test_snapshot(self):
        wm = WorkingMemory()
        wm.set("key1", "val1")
        wm.push("bucket1", "item1")
        snap = wm.snapshot()
        assert snap["store"]["key1"] == "val1"
        assert snap["buckets"]["bucket1"] == ["item1"]

    def test_clear(self):
        wm = WorkingMemory()
        wm.set("a", 1)
        wm.push("b", 2)
        wm.clear()
        assert wm.count() == 0

    def test_count(self):
        wm = WorkingMemory()
        wm.set("a", 1)
        wm.set("b", 2)
        wm.push("c", 3)
        assert wm.count() == 3

    def test_keys(self):
        wm = WorkingMemory()
        wm.set("alpha", 1)
        wm.set("beta", 2)
        assert set(wm.keys()) == {"alpha", "beta"}

    def test_bucket_names(self):
        wm = WorkingMemory()
        wm.push("urls", "x")
        wm.push("actions", "y")
        assert set(wm.bucket_names()) == {"urls", "actions"}
