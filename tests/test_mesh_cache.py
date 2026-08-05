"""Tests for the local SQLite state cache."""
import os
import sqlite3
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

    def test_every_operation_closes_its_connection(self):
        """No operation may leave a SQLite handle open once it returns.

        The other tests in this file only catch a leak by accident, and only on
        some interpreters: they fail at TemporaryDirectory teardown, which needs
        Windows' refuse-to-unlink-open-files semantics AND a CPython whose GC has
        not yet reaped the connection. On POSIX, or on CPython 3.10 where
        refcounting frees connections promptly, a leak sails straight through.

        This asserts the invariant directly and portably instead. SQLite deletes
        the -wal/-shm sidecars when the LAST connection to a database closes, so
        their presence after a completed call is proof a handle is still open.
        No gc.collect() here on purpose — correctness must not depend on the GC.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "cache.db")
            cache = StateCache(db_path=db)
            cache.put("plan", "p1", {"goal": "test"})
            cache.get("plan", "p1")
            cache.list_bucket("plan")
            cache.delete("plan", "p1")
            cache.prune(max_age_seconds=0)

            leftover = [f for f in sorted(os.listdir(tmp)) if f != "cache.db"]
            assert leftover == [], (
                f"StateCache leaked an open connection; WAL sidecars remain: {leftover}"
            )

    def test_connection_is_closed_even_when_the_query_raises(self):
        """A failing operation must not leak the handle either.

        Without the try/finally in StateCache._connect, an exception mid-statement
        would skip the close entirely, so this covers the path the happy-path test
        above cannot reach.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "cache.db")
            cache = StateCache(db_path=db)
            cache.put("plan", "p1", {"goal": "test"})

            with pytest.raises(sqlite3.Error):
                with cache._connect() as conn:
                    conn.execute("SELECT * FROM table_that_does_not_exist")

            leftover = [f for f in sorted(os.listdir(tmp)) if f != "cache.db"]
            assert leftover == [], (
                f"StateCache leaked a connection on the error path: {leftover}"
            )
