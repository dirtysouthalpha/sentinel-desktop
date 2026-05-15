"""Tests for checkpoint.py — covering error paths, stale, corrupt, and edge cases."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from core.checkpoint import (
    CheckpointManager,
    _checkpoint_path,
    _discover_checkpoint_files,
    _parse_timestamp,
)


class TestHelpers:
    """Module-level helper functions."""

    def test_checkpoint_path_returns_str(self) -> None:
        result = _checkpoint_path("abc-123")
        assert result.endswith("abc-123.json")

    def test_discover_nonexistent_dir(self, tmp_path: Path) -> None:
        result = _discover_checkpoint_files(str(tmp_path / "nope"))
        assert result == []

    def test_parse_timestamp_valid(self) -> None:
        ts = "2026-01-15T12:00:00+00:00"
        result = _parse_timestamp(ts)
        assert result is not None
        assert result.year == 2026

    def test_parse_timestamp_invalid(self) -> None:
        assert _parse_timestamp("garbage") is None

    def test_parse_timestamp_none(self) -> None:
        assert _parse_timestamp(None) is None  # type: ignore[arg-type]

    def test_parse_timestamp_empty(self) -> None:
        assert _parse_timestamp("") is None


class TestSaveErrors:
    """save() failure paths."""

    def test_save_oserror_returns_none(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            result = cm.save("goal", 1, [], None, {}, "running")
        assert result is None

    def test_save_value_error_returns_none(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        with patch("json.dump", side_effect=ValueError("bad value")):
            result = cm.save("goal", 1, [], None, {}, "running")
        assert result is None


class TestLoadLatestCorrupt:
    """load_latest() handles corrupt and malformed files."""

    def test_corrupt_json_skipped(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid", encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.load_latest() is None

    def test_malformed_record_skipped(self, tmp_path: Path) -> None:
        bad = tmp_path / "arr.json"
        bad.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.load_latest() is None

    def test_record_missing_id_skipped(self, tmp_path: Path) -> None:
        bad = tmp_path / "no_id.json"
        bad.write_text(
            json.dumps({"timestamp": datetime.now(timezone.utc).isoformat()}), encoding="utf-8"
        )
        cm = CheckpointManager(str(tmp_path))
        assert cm.load_latest() is None

    def test_stale_checkpoint_skipped(self, tmp_path: Path) -> None:
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        record = {"id": "stale-1", "timestamp": old_ts, "step_num": 1, "status": "running"}
        stale = tmp_path / "stale.json"
        stale.write_text(json.dumps(record), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.load_latest() is None

    def test_no_files_returns_none(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        cm = CheckpointManager(str(empty))
        assert cm.load_latest() is None

    def test_valid_checkpoint_returned(self, tmp_path: Path) -> None:
        record = {
            "id": "valid-1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goal": "test",
            "step_num": 1,
        }
        good = tmp_path / "valid.json"
        good.write_text(json.dumps(record), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        result = cm.load_latest()
        assert result is not None
        assert result["id"] == "valid-1"


class TestListCheckpointsCorrupt:
    """list_checkpoints() handles corrupt/malformed files."""

    def test_corrupt_file_skipped(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{bad", encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.list_checkpoints() == []

    def test_non_dict_record_skipped(self, tmp_path: Path) -> None:
        arr = tmp_path / "arr.json"
        arr.write_text(json.dumps([1, 2]), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.list_checkpoints() == []

    def test_valid_records_listed(self, tmp_path: Path) -> None:
        rec = {"id": "r1", "goal_preview": "g", "step_num": 1, "timestamp": "", "status": "running"}
        good = tmp_path / "r1.json"
        good.write_text(json.dumps(rec), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        result = cm.list_checkpoints()
        assert len(result) == 1
        assert result[0]["id"] == "r1"


class TestLoadErrors:
    """load() handles corrupt and missing files."""

    def test_load_corrupt_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "corrupt.json"
        bad.write_text("{bad", encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.load("corrupt") is None

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        assert cm.load("nonexistent") is None

    def test_load_valid(self, tmp_path: Path) -> None:
        rec = {"id": "good", "goal": "test", "step_num": 5}
        f = tmp_path / "good.json"
        f.write_text(json.dumps(rec), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        result = cm.load("good")
        assert result is not None
        assert result["step_num"] == 5


class TestDeleteErrors:
    """delete() handles OSError."""

    def test_delete_oserror_returns_false(self, tmp_path: Path) -> None:
        rec = {"id": "del-me", "goal": "t", "step_num": 1}
        f = tmp_path / "del-me.json"
        f.write_text(json.dumps(rec), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        with patch.object(Path, "unlink", side_effect=OSError("locked")):
            assert cm.delete("del-me") is False

    def test_delete_nonexistent_returns_true(self, tmp_path: Path) -> None:
        cm = CheckpointManager(str(tmp_path))
        assert cm.delete("ghost") is True

    def test_delete_existing_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "rm.json"
        f.write_text(json.dumps({"id": "rm"}), encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.delete("rm") is True
        assert not f.exists()


class TestClearAllErrors:
    """clear_all() handles individual unlink failures."""

    def test_partial_failure_still_counts(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text("{}", encoding="utf-8")
        f2.write_text("{}", encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))

        call_count = 0
        orig_unlink = Path.unlink

        def selective_unlink(self_path: Path, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("busy")
            orig_unlink(self_path, *args, **kwargs)

        with patch.object(Path, "unlink", selective_unlink):
            removed = cm.clear_all()
        assert removed == 1


class TestAutoSaveGate:
    """should_auto_save() boundary conditions."""

    def test_step_0(self) -> None:
        assert CheckpointManager.should_auto_save(0) is False

    def test_step_5(self) -> None:
        assert CheckpointManager.should_auto_save(5) is True

    def test_step_7(self) -> None:
        assert CheckpointManager.should_auto_save(7) is False
