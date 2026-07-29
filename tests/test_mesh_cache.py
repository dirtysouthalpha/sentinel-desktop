"""Tests for the local SQLite state cache."""
import os
import tempfile
import time
import pytest
from core.mesh.cache import StateCache

class TestStateCache:
    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"goal": "test", "status": "active"})
            result = cache.get("plan", "p1")
            assert result is not None
            assert result["goal"] == "test"

    def test_read_missing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            assert cache.get("plan", "nonexistent") is None

    def test_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"status": "active"})
            cache.put("plan", "p1", {"status": "completed"})
            assert cache.get("plan", "p1")["status"] == "completed"

    def test_list_by_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"goal": "a"})
            cache.put("plan", "p2", {"goal": "b"})
            cache.put("memory", "m1", {"content": "x"})
            plans = cache.list_bucket("plan")
            assert len(plans) == 2

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"goal": "test"})
            cache.delete("plan", "p1")
            assert cache.get("plan", "p1") is None

    def test_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "old", {"goal": "old"})
            cache.put("plan", "new", {"goal": "new"})
            time.sleep(0.01)
            cache.prune(max_age_seconds=0)
            assert cache.get("plan", "old") is None
            assert cache.get("plan", "new") is None
