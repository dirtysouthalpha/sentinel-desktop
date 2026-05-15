"""Tests for core/checkpoint.py — crash-resume checkpoint save/restore."""

import json
import os
import tempfile

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
        files = os.listdir(cm._dir)
        assert f"{cp_id}.json" in files

    def test_file_content(self, cm):
        cp_id = _save_checkpoint(cm, goal="Open Chrome", step=5)
        path = os.path.join(cm._dir, f"{cp_id}.json")
        with open(path) as fh:
            data = json.load(fh)
        assert data["goal"] == "Open Chrome"
        assert data["step_num"] == 5
        assert data["provider"] == "openai"

    def test_invalid_status_defaults_to_running(self, cm):
        cp_id = _save_checkpoint(cm, status="bogus")
        path = os.path.join(cm._dir, f"{cp_id}.json")
        with open(path) as fh:
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
        path = os.path.join(cm._dir, f"{cp_id}.json")
        with open(path) as fh:
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
        _save_checkpoint(cm, goal="First")
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
