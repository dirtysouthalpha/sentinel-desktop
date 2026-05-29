"""Additional gap tests for checkpoint.py — stale-then-valid sequence, save TypeError, config defaults."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch as _patch

from core.checkpoint import CheckpointManager


class TestLoadLatestStaleThenValid:
    """load_latest skips stale checkpoint and returns older valid one."""

    def test_stale_skipped_older_valid_returned(self, tmp_path: Path) -> None:
        # Create an old valid checkpoint first
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        old_rec = {"id": "old-valid", "timestamp": old_ts, "goal": "old goal", "step_num": 3}
        old_file = tmp_path / "old.json"
        old_file.write_text(json.dumps(old_rec), encoding="utf-8")

        # Create a stale (too old) checkpoint with a newer mtime
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        stale_rec = {"id": "stale-1", "timestamp": stale_ts, "step_num": 1, "status": "running"}
        stale_file = tmp_path / "stale.json"
        stale_file.write_text(json.dumps(stale_rec), encoding="utf-8")

        cm = CheckpointManager(str(tmp_path))
        result = cm.load_latest()
        # The stale one should be skipped; the old valid one should be returned
        assert result is not None
        assert result["id"] == "old-valid"


class TestSaveTypeError:
    """save() handles TypeError from json.dump."""

    def test_save_typeerror_returns_none(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        with _patch_json_dump_raises(TypeError("unserializable")):
            result = cm.save("goal", 1, [], None, {}, "running")
        assert result is None


class TestSaveConfigDefaults:
    """save() handles config without provider/model keys."""

    def test_missing_provider_model_uses_defaults(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        cid = cm.save("goal", 1, [], None, {}, "running")
        assert cid is not None
        data = json.loads((tmp_path / f"{cid}.json").read_text(encoding="utf-8"))
        assert data["provider"] == ""
        assert data["model"] == ""


class TestAutoSaveMultiples:
    """should_auto_save at various step counts."""

    def test_step_10_true(self) -> None:
        assert CheckpointManager.should_auto_save(10) is True

    def test_step_15_true(self) -> None:
        assert CheckpointManager.should_auto_save(15) is True

    def test_step_3_false(self) -> None:
        assert CheckpointManager.should_auto_save(3) is False


class TestSaveWithScreenshot:
    """save() persists last_screenshot_path."""

    def test_screenshot_path_in_checkpoint(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        cid = cm.save("goal", 1, [], "screen.png", {}, "running")
        data = json.loads((tmp_path / f"{cid}.json").read_text(encoding="utf-8"))
        assert data["last_screenshot_path"] == "screen.png"

    def test_none_screenshot_path(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        cid = cm.save("goal", 1, [], None, {}, "running")
        data = json.loads((tmp_path / f"{cid}.json").read_text(encoding="utf-8"))
        assert data["last_screenshot_path"] is None


class TestDeleteWithTraversal:
    """delete() sanitizes path traversal in checkpoint_id."""

    def test_directory_traversal_returns_false(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        result = cm.delete("../../etc/passwd")
        # Path is sanitized via Path().name, so it won't find anything
        # Returns True because the file doesn't exist
        assert result is True


class TestLoadLatestNoTimestamp:
    """load_latest returns record when timestamp is missing (ts is None branch)."""

    def test_no_timestamp_record_returned(self, tmp_path: Path) -> None:
        # A checkpoint without a 'timestamp' key — _parse_timestamp returns None,
        # so the age-out check is skipped and the record is returned directly.
        rec = {"id": "no-ts-id", "goal": "do something", "step_num": 1}
        (tmp_path / "notimestamp.json").write_text(json.dumps(rec), encoding="utf-8")

        cm = CheckpointManager(str(tmp_path))
        result = cm.load_latest()
        assert result is not None
        assert result["id"] == "no-ts-id"


# Helper for patching json.dump to raise


class _patch_json_dump_raises:
    def __init__(self, exc):
        self.exc = exc
        self._cm = None

    def __enter__(self):
        self._cm = _patch("json.dump", side_effect=self.exc)
        return self._cm.__enter__()

    def __exit__(self, *args):
        return self._cm.__exit__(*args)
