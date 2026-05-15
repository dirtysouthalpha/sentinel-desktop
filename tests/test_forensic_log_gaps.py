"""Gap tests for forensic_log.py — export error paths, auto-save, log_event details."""

import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.forensic_log import ForensicLog, _default_log_dir, _iso_now, _preview, _redact_params


class TestForensicLogExportErrors:
    """Export methods handle I/O errors gracefully."""

    def test_export_json_write_failure_returns_false(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            assert fl.export_json("/fake/path.json") is False

    def test_export_csv_write_failure_returns_false(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            assert fl.export_csv("/fake/path.csv") is False


class TestForensicLogAutoSave:
    """Auto-save triggers on lifecycle methods."""

    def test_start_run_creates_json_file(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        run_id = fl.start_run("Goal", "openai", "gpt-4o")
        expected = Path(tmpdir) / f"{run_id}.json"
        assert expected.exists()
        data = json.loads(expected.read_text())
        assert data["run"]["goal"] == "Goal"

    def test_end_run_updates_json_file(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        run_id = fl.start_run("Goal", "openai", "gpt-4o")
        fl.end_run("success", "Done", 1)
        expected = Path(tmpdir) / f"{run_id}.json"
        data = json.loads(expected.read_text())
        assert data["run"]["status"] == "success"

    def test_log_step_updates_json_file(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        run_id = fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        expected = Path(tmpdir) / f"{run_id}.json"
        data = json.loads(expected.read_text())
        assert len(data["steps"]) == 1

    def test_auto_save_no_run_does_nothing(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl._auto_save()  # Should not create any file
        assert list(Path(tmpdir).iterdir()) == []

    def test_auto_save_oserror_handled(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        with patch("pathlib.Path.open", side_effect=OSError("no space")):
            fl._auto_save()  # Should not raise


class TestForensicLogEventDuration:
    """log_event computes duration correctly."""

    def test_log_event_without_prior_step(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl._last_step_time = None
        fl.log_event("pause", {"reason": "test"})
        steps = fl.get_steps()
        assert steps[0]["duration_ms"] == 0

    def test_log_event_with_invalid_last_step_time(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl._last_step_time = "not-a-datetime"
        fl.log_event("pause", {"reason": "test"})
        steps = fl.get_steps()
        assert steps[0]["duration_ms"] == 0


class TestForensicLogLogStepDuration:
    """log_step handles duration edge cases."""

    def test_log_step_no_last_step_time(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl._last_step_time = None
        step_id = fl.log_step(1, "click", "Btn", {}, "success")
        assert len(step_id) == 36
        steps = fl.get_steps()
        assert steps[0]["duration_ms"] == 0

    def test_log_step_invalid_last_step_time(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl._last_step_time = "bad-time"
        fl.log_step(1, "click", "Btn", {}, "success")
        steps = fl.get_steps()
        assert steps[0]["duration_ms"] == 0


class TestForensicLogSummary:
    """Additional summary display cases."""

    def test_summary_with_completed_run_and_events(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Open Chrome", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        fl.log_event("override", {"action": "cancel"})
        fl.end_run("success", "Done", 2)
        summary = fl.get_summary()
        assert "actions=1" in summary
        assert "overrides=1" in summary
        assert "Done" in summary

    def test_summary_empty_run(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl._run = {"run_id": "abc"}
        summary = fl.get_summary()
        assert "abc" in summary


class TestExportCsvContent:
    """CSV export produces correct content."""

    def test_csv_success_column(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        path = str(Path(tmpdir) / "test.csv")
        assert fl.export_csv(path) is True
        with Path(path).open(newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["success"] == "true"
        assert rows[0]["action_type"] == "click"

    def test_export_csv_creates_parent_dirs(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        path = str(Path(tmpdir) / "sub" / "dir" / "out.csv")
        assert fl.export_csv(path) is True
        assert Path(path).is_file()


class TestDefaultLogDir:
    """_default_log_dir returns a valid path."""

    def test_returns_string(self):
        result = _default_log_dir()
        assert isinstance(result, str)
        assert "sentinel-desktop" in result


class TestIsoNow:
    """_iso_now returns valid ISO format."""

    def test_returns_iso_string(self):
        result = _iso_now()
        assert "T" in result
        assert "+" in result or "Z" in result or "-" in result


class TestRedactParamsEdgeCases:
    """Additional redaction edge cases."""

    def test_credit_card_redacted(self):
        result = _redact_params({"credit_card": "4111111111111111"})
        assert result["credit_card"] == "***REDACTED***"

    def test_ssn_redacted(self):
        result = _redact_params({"ssn": "123-45-6789"})
        assert result["ssn"] == "***REDACTED***"

    def test_credential_redacted(self):
        result = _redact_params({"aws_credential": "AKIA..."})
        assert result["aws_credential"] == "***REDACTED***"

    def test_pin_redacted(self):
        result = _redact_params({"user_pin": "1234"})
        assert result["user_pin"] == "***REDACTED***"


class TestPreviewEdgeCases:
    """Additional _preview edge cases."""

    def test_exact_max_len(self):
        text = "x" * 50
        assert _preview(text, max_len=50) == text

    def test_list_serialized(self):
        result = _preview([1, 2, 3])
        assert "1" in result

    def test_bool_serialized(self):
        result = _preview(True)
        assert "true" in result.lower()
