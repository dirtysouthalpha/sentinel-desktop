"""Additional gap tests for forensic_log.py — infer_event_type, CSV ok-match, auto-save TypeError."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.forensic_log import ForensicLog


class TestInferEventType:
    """_infer_event_type maps result strings to event categories."""

    def test_timeout_returns_error(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "wait", "Btn", {}, "timeout after 10s")
        steps = fl.get_steps()
        assert steps[0]["event_type"] == "error"

    def test_error_returns_error(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "error: element not found")
        steps = fl.get_steps()
        assert steps[0]["event_type"] == "error"

    def test_fail_returns_error(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "failed to locate")
        steps = fl.get_steps()
        assert steps[0]["event_type"] == "error"

    def test_exception_returns_error(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "exception in click handler")
        steps = fl.get_steps()
        assert steps[0]["event_type"] == "error"

    def test_success_returns_action(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        steps = fl.get_steps()
        assert steps[0]["event_type"] == "action"

    def test_neutral_returns_action(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "read", "Text", {}, "read 500 chars")
        steps = fl.get_steps()
        assert steps[0]["event_type"] == "action"


class TestCsvOkMatch:
    """CSV export marks 'ok' results as success."""

    def test_ok_in_result_marks_success(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "ok — clicked")
        path = str(Path(tmpdir) / "ok.csv")
        assert fl.export_csv(path) is True
        with Path(path).open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["success"] == "true"

    def test_failure_result_marks_false(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "element not found")
        path = str(Path(tmpdir) / "fail.csv")
        assert fl.export_csv(path) is True
        with Path(path).open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["success"] == "false"


class TestLogEventNonDictDetails:
    """log_event handles non-dict details gracefully."""

    def test_string_details_get_empty_params(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_event("pause", "a string instead of dict")
        steps = fl.get_steps()
        assert steps[0]["params"] == {}

    def test_none_details_get_empty_params(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_event("resume", None)
        steps = fl.get_steps()
        assert steps[0]["params"] == {}


class TestLogStepScreenshotPath:
    """log_step stores screenshot_path when provided."""

    def test_screenshot_path_stored(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success", screenshot_path="shot.png")
        steps = fl.get_steps()
        assert steps[0]["screenshot_path"] == "shot.png"

    def test_default_screenshot_path_is_none(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        steps = fl.get_steps()
        assert steps[0]["screenshot_path"] is None


class TestAutoSaveTypeError:
    """_auto_save handles TypeError from json.dump."""

    def test_typeerror_handled(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        with patch("json.dump", side_effect=TypeError("not serializable")):
            fl._auto_save()  # Should not raise


class TestExportCsvEmptySteps:
    """CSV export with no steps creates header-only file."""

    def test_empty_steps_produces_header_only_csv(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        path = str(Path(tmpdir) / "empty.csv")
        assert fl.export_csv(path) is True
        with Path(path).open(newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert rows == []


class TestEndRunPopulatesFields:
    """end_run sets status, summary, total_steps, end_time."""

    def test_end_run_sets_fields(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.end_run("success", "Done", 1)
        assert fl._run["status"] == "success"
        assert fl._run["summary"] == "Done"
        assert fl._run["total_steps"] == 1
        assert "end_time" in fl._run
