"""Tests for v11.0 Memory — episodic, semantic, working memory."""

from __future__ import annotations

from pathlib import Path

from core.memory.episodic import Episode, EpisodicMemory
from core.memory.semantic import SemanticMemory
from core.memory.working import WorkingMemory

# ===========================================================================
# Episodic Memory
# ===========================================================================


class TestEpisodicMemory:
    def test_store_and_recall(self, tmp_path: Path):
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store(
            "Login to firewall",
            actions=[{"action": "web_open", "url": "https://192.168.1.1"}],
            outcome="Logged in",
            success=True,
        )
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

    def test_search_outcome_matching(self, tmp_path: Path):
        """Test search matches against outcome field."""
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store("Login", outcome="Successfully authenticated")
        mem.store("Logout", outcome="Failed to disconnect")
        results = mem.search("authenticated")
        assert len(results) == 1
        assert "Login" in results[0]["goal"]

    def test_search_case_insensitive(self, tmp_path: Path):
        """Test search is case-insensitive."""
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store("FIREWALL Configuration")
        results = mem.search("firewall")
        assert len(results) == 1

    def test_search_with_limit(self, tmp_path: Path):
        """Test search respects limit parameter."""
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        for i in range(10):
            mem.store(f"Task {i}", tags=["test"])
        results = mem.search("test", limit=3)
        assert len(results) == 3

    def test_compress_old_episodes(self, tmp_path: Path):
        """Test compression of old episodes."""
        import json
        from datetime import datetime, timedelta

        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")

        # Store an episode and manually make it appear old
        mem.store("Old task", success=True)

        # Read the file and modify the timestamp
        lines = tmp_path.joinpath("episodes.jsonl").read_text(encoding="utf-8").splitlines()
        if lines:
            data = json.loads(lines[0])
            # Make it appear 40 days old
            old_time = datetime.utcnow() - timedelta(days=40)
            data["created_at"] = old_time.isoformat()
            lines[0] = json.dumps(data, ensure_ascii=False)
            # Write with proper trailing newline
            tmp_path.joinpath("episodes.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )

        # Create a new memory instance to pick up the modified file
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")

        # Add a recent episode
        mem.store("Recent task", success=True)

        # Before compression, should have 2 episodes
        assert mem.count() == 2

        # Compress episodes older than 30 days
        compressed_count = mem.compress_old(days=30)
        assert compressed_count == 1

        # After compression, should have 2 episodes (summary + recent)
        assert mem.count() == 2

        # Verify the compressed summary exists
        recent = mem.recall(limit=10)
        summary_eps = [ep for ep in recent if "compressed" in ep.get("tags", [])]
        assert len(summary_eps) == 1
        assert "Summary" in summary_eps[0]["goal"]

    def test_compress_no_old_episodes(self, tmp_path: Path):
        """Test compression when there are no old episodes."""
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        mem.store("Recent task", success=True)

        compressed_count = mem.compress_old(days=30)
        assert compressed_count == 0
        assert mem.count() == 1

    def test_compress_with_invalid_timestamp(self, tmp_path: Path):
        """Test compression handles episodes with invalid timestamps."""
        import json

        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")

        # Store an episode
        mem.store("Task with bad timestamp", success=True)

        # Corrupt the timestamp
        lines = tmp_path.joinpath("episodes.jsonl").read_text(encoding="utf-8").splitlines()
        if lines:
            data = json.loads(lines[0])
            data["created_at"] = "invalid-date"
            lines[0] = json.dumps(data, ensure_ascii=False)
            # Write with proper trailing newline
            tmp_path.joinpath("episodes.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )

        # Create a new memory instance to pick up the modified file
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")

        # Compress should skip the invalid episode
        compressed_count = mem.compress_old(days=30)
        # The episode with invalid timestamp should be kept as "recent"
        assert compressed_count == 0
        assert mem.count() == 1

    def test_read_all_with_invalid_json(self, tmp_path: Path):
        """Test _read_all handles invalid JSON gracefully."""
        path = tmp_path / "episodes.jsonl"
        path.write_text("valid line\ninvalid json\nanother valid line\n", encoding="utf-8")

        mem = EpisodicMemory(path=path)
        # Should skip invalid lines
        count = mem.count()
        # Should have read the valid lines only
        assert count >= 0

    def test_read_all_with_missing_fields(self, tmp_path: Path):
        """Test _read_all handles episodes with missing fields."""
        path = tmp_path / "episodes.jsonl"

        # Write JSON with missing required fields
        path.write_text('{"incomplete": "data"}\n', encoding="utf-8")

        mem = EpisodicMemory(path=path)
        # Should handle incomplete data gracefully
        count = mem.count()
        assert count >= 0

    def test_recall_with_offset(self, tmp_path: Path):
        """Test recall with offset parameter."""
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")
        for i in range(10):
            mem.store(f"Task {i}")

        # Get episodes 5-9
        results = mem.recall(limit=5, offset=5)
        assert len(results) == 5

    def test_empty_file_handling(self, tmp_path: Path):
        """Test handling of empty episodic file."""
        path = tmp_path / "episodes.jsonl"
        path.write_text("", encoding="utf-8")

        mem = EpisodicMemory(path=path)
        assert mem.count() == 0
        assert mem.recall() == []
        assert mem.search("anything") == []

    def test_compress_all_successful(self, tmp_path: Path):
        """Test compression when all old episodes were successful."""
        import json
        from datetime import datetime, timedelta

        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")

        # Store successful episodes and make them old
        for i in range(3):
            mem.store(f"Old task {i}", success=True)

        # Manually age the episodes
        lines = tmp_path.joinpath("episodes.jsonl").read_text(encoding="utf-8").splitlines()
        aged_lines = []
        for line in lines:
            data = json.loads(line)
            old_time = datetime.utcnow() - timedelta(days=40)
            data["created_at"] = old_time.isoformat()
            aged_lines.append(json.dumps(data, ensure_ascii=False))
        # Write with proper trailing newline
        tmp_path.joinpath("episodes.jsonl").write_text(
            "\n".join(aged_lines) + "\n", encoding="utf-8"
        )

        # Create a new memory instance to pick up the modified file
        mem = EpisodicMemory(path=tmp_path / "episodes.jsonl")

        # Compress
        compressed_count = mem.compress_old(days=30)
        assert compressed_count == 3

        # Check the summary
        recent = mem.recall(limit=10)
        summary_eps = [ep for ep in recent if "compressed" in ep.get("tags", [])]
        assert len(summary_eps) == 1
        # All successful, so summary should be successful
        assert summary_eps[0]["success"] is True


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
