"""Tests for core/checkpoint.py — crash-resume checkpoint save/restore."""

import json
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from core.checkpoint import CheckpointManager


@pytest.fixture
def cm(tmp_path):
    return CheckpointManager(checkpoint_dir=str(tmp_path / "cp"))


def _save_checkpoint(cm, goal="Test goal", step=1, status="running"):
    return cm.save(
        goal=goal,
        step_num=step,
        agent_memory=[{"role": "user", "content": goal}],
        last_screenshot_path=None,
        config={"provider": "openai", "model": "gpt-4o"},
        status=status,
        messages=[],
    )


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


class TestSave:
    def test_returns_uuid(self, cm):
        cp_id = _save_checkpoint(cm)
        assert len(cp_id) == 36

    def test_file_created(self, cm):
        cp_id = _save_checkpoint(cm)
        files = [p.name for p in Path(cm._dir).iterdir()]
        assert f"{cp_id}.json" in files

    def test_file_content(self, cm):
        cp_id = _save_checkpoint(cm, goal="Open Chrome", step=5)
        path = Path(cm._dir) / f"{cp_id}.json"
        with path.open() as fh:
            data = json.load(fh)
        assert data["goal"] == "Open Chrome"
        assert data["step_num"] == 5
        assert data["provider"] == "openai"

    def test_invalid_status_defaults_to_running(self, cm):
        cp_id = _save_checkpoint(cm, status="bogus")
        path = Path(cm._dir) / f"{cp_id}.json"
        with path.open() as fh:
            data = json.load(fh)
        assert data["status"] == "running"

    def test_messages_saved(self, cm):
        msgs = [{"role": "user", "content": "hello"}]
        cp_id = cm.save(
            goal="Goal",
            step_num=1,
            agent_memory=[],
            last_screenshot_path=None,
            config={"provider": "openai"},
            messages=msgs,
        )
        path = Path(cm._dir) / f"{cp_id}.json"
        with path.open() as fh:
            data = json.load(fh)
        assert len(data["messages"]) == 1

    def test_should_auto_save(self):
        assert CheckpointManager.should_auto_save(5) is True
        assert CheckpointManager.should_auto_save(10) is True
        assert CheckpointManager.should_auto_save(0) is False
        assert CheckpointManager.should_auto_save(3) is False


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_existing(self, cm):
        cp_id = _save_checkpoint(cm, goal="My Goal")
        record = cm.load(cp_id)
        assert record is not None
        assert record["goal"] == "My Goal"

    def test_load_nonexistent_returns_none(self, cm):
        assert cm.load("does-not-exist") is None

    def test_load_latest(self, cm):
        import time

        _save_checkpoint(cm, goal="First")
        time.sleep(0.05)
        _save_checkpoint(cm, goal="Second")
        latest = cm.load_latest()
        assert latest is not None
        assert latest["goal"] == "Second"

    def test_load_latest_empty_dir(self, cm):
        assert cm.load_latest() is None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestList:
    def test_list_empty(self, cm):
        assert cm.list_checkpoints() == []

    def test_list_returns_summaries(self, cm):
        _save_checkpoint(cm, goal="Goal A", step=1)
        _save_checkpoint(cm, goal="Goal B", step=2)
        cps = cm.list_checkpoints()
        assert len(cps) == 2
        assert all("id" in c for c in cps)
        assert all("goal_preview" in c for c in cps)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_existing(self, cm):
        cp_id = _save_checkpoint(cm)
        assert cm.delete(cp_id) is True
        assert cm.load(cp_id) is None

    def test_delete_nonexistent(self, cm):
        assert cm.delete("no-such-id") is True

    def test_clear_all(self, cm):
        _save_checkpoint(cm)
        _save_checkpoint(cm)
        _save_checkpoint(cm)
        removed = cm.clear_all()
        assert removed == 3
        assert cm.list_checkpoints() == []


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_directory_traversal_sanitized(self, cm):
        result = cm.load("../../etc/passwd")
        assert result is None


# ---------------------------------------------------------------------------
# Edge cases: stale, corrupt, malformed
# ---------------------------------------------------------------------------


class TestStaleCheckpoints:
    """load_latest skips checkpoints older than 1 hour."""

    def test_stale_checkpoint_skipped_by_load_latest(self, cm):
        from datetime import datetime, timedelta, timezone

        cp_id = _save_checkpoint(cm, goal="Old checkpoint")
        # Backdate the timestamp to 2 hours ago
        path = Path(cm._dir) / f"{cp_id}.json"
        data = json.loads(path.read_text())
        data["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        path.write_text(json.dumps(data))
        # load_latest should skip stale, return None
        assert cm.load_latest() is None

    def test_stale_checkpoint_still_loadable_by_id(self, cm):
        from datetime import datetime, timedelta, timezone

        cp_id = _save_checkpoint(cm, goal="Old but explicit")
        path = Path(cm._dir) / f"{cp_id}.json"
        data = json.loads(path.read_text())
        data["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        path.write_text(json.dumps(data))
        # Direct load should still work
        record = cm.load(cp_id)
        assert record is not None
        assert record["goal"] == "Old but explicit"

    def test_nonstale_checkpoint_preferred_over_stale(self, cm):
        from datetime import datetime, timedelta, timezone

        import time

        # Create stale
        stale_id = _save_checkpoint(cm, goal="Stale")
        path = Path(cm._dir) / f"{stale_id}.json"
        data = json.loads(path.read_text())
        data["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        path.write_text(json.dumps(data))
        # Create fresh
        time.sleep(0.05)
        _save_checkpoint(cm, goal="Fresh")
        latest = cm.load_latest()
        assert latest is not None
        assert latest["goal"] == "Fresh"


class TestCorruptFiles:
    """Corrupt or malformed JSON files are gracefully skipped."""

    def test_corrupt_json_skipped_by_load_latest(self, cm):
        # Write garbage to a .json file
        bad = Path(cm._dir) / "corrupt-checkpoint.json"
        bad.write_text("NOT VALID JSON {{{")
        assert cm.load_latest() is None

    def test_corrupt_json_skipped_by_list_checkpoints(self, cm):
        bad = Path(cm._dir) / "corrupt-list.json"
        bad.write_text("{broken")
        assert cm.list_checkpoints() == []

    def test_corrupt_json_skipped_by_load(self, cm):
        bad = Path(cm._dir) / "corrupt-load.json"
        bad.write_text("}{not json")
        result = cm.load("corrupt-load")
        assert result is None

    def test_malformed_list_instead_of_dict(self, cm):
        bad = Path(cm._dir) / "malformed-list.json"
        bad.write_text(json.dumps([]))
        assert cm.load_latest() is None
        assert cm.list_checkpoints() == []

    def test_malformed_missing_id(self, cm):
        bad = Path(cm._dir) / "malformed-no-id.json"
        bad.write_text(json.dumps({"goal": "no id field"}))
        assert cm.load_latest() is None
        assert cm.list_checkpoints() == []


class TestSaveEdgeCases:
    """Edge cases in save behavior."""

    def test_goal_preview_truncated_to_200(self, cm):
        long_goal = "A" * 300
        cp_id = _save_checkpoint(cm, goal=long_goal)
        path = Path(cm._dir) / f"{cp_id}.json"
        data = json.loads(path.read_text())
        assert len(data["goal_preview"]) == 200
        assert data["goal"] == long_goal

    def test_save_returns_none_on_write_failure(self, tmp_path):
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        cm = CheckpointManager(checkpoint_dir=str(ro_dir))
        # Mock Path.open to raise OSError (simulating write failure)
        with patch.object(Path, "open", side_effect=OSError("Simulated write failure")):
            result = _save_checkpoint(cm)
            assert result is None

    def test_empty_goal_handled(self, cm):
        cp_id = cm.save(
            goal="",
            step_num=1,
            agent_memory=[],
            last_screenshot_path=None,
            config={"provider": "test"},
            status="running",
            messages=[],
        )
        path = Path(cm._dir) / f"{cp_id}.json"
        data = json.loads(path.read_text())
        assert data["goal"] == ""
        assert data["goal_preview"] == ""

    def test_should_auto_save_edge_cases(self):
        assert CheckpointManager.should_auto_save(-1) is False
        assert CheckpointManager.should_auto_save(-5) is False
        assert CheckpointManager.should_auto_save(1) is False
        assert CheckpointManager.should_auto_save(4) is False
        assert CheckpointManager.should_auto_save(5) is True
        assert CheckpointManager.should_auto_save(6) is False
        assert CheckpointManager.should_auto_save(10) is True
        assert CheckpointManager.should_auto_save(15) is True
        assert CheckpointManager.should_auto_save(100) is True


class TestThreadSafety:
    """Concurrent operations don't corrupt data."""

    def test_concurrent_saves(self, cm):
        import threading

        errors = []
        ids = []

        def worker(idx):
            try:
                cp_id = _save_checkpoint(cm, goal=f"Thread {idx}")
                if cp_id is None:
                    errors.append(f"thread {idx} got None")
                else:
                    ids.append(cp_id)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent saves: {errors}"
        assert len(ids) == 10
        # Verify all files are valid JSON
        for cp_id in ids:
            path = Path(cm._dir) / f"{cp_id}.json"
            assert path.is_file()
            data = json.loads(path.read_text())
            assert "id" in data
