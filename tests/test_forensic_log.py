"""Tests for core/forensic_log.py — structured audit trail."""

import json
import tempfile
from pathlib import Path

from core.forensic_log import ForensicLog, _preview, _redact_params

# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------


class TestRedactParams:
    def test_empty_dict(self):
        assert _redact_params({}) == {}

    def test_none_returns_empty(self):
        assert _redact_params(None) == {}

    def test_normal_keys_pass_through(self):
        params = {"x": 100, "y": 200}
        assert _redact_params(params) == {"x": 100, "y": 200}

    def test_password_redacted(self):
        result = _redact_params({"username": "admin", "password": "secret123"})
        assert result["username"] == "admin"
        assert result["password"] == "***REDACTED***"

    def test_api_key_redacted(self):
        result = _redact_params({"api_key": "sk-abc", "model": "gpt-4"})
        assert result["api_key"] == "***REDACTED***"
        assert result["model"] == "gpt-4"

    def test_token_redacted(self):
        result = _redact_params({"bearer_token": "xyz", "url": "https://example.com"})
        assert result["bearer_token"] == "***REDACTED***"

    def test_case_insensitive_redaction(self):
        result = _redact_params({"SECRET_value": "top"})
        assert result["SECRET_value"] == "***REDACTED***"


class TestPreview:
    def test_short_string(self):
        assert _preview("hello") == "hello"

    def test_long_string_truncated(self):
        long_str = "x" * 200
        result = _preview(long_str, max_len=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_dict_serialized(self):
        result = _preview({"a": 1})
        assert '"a"' in result

    def test_int_serialized(self):
        result = _preview(42)
        assert "42" in result


# ---------------------------------------------------------------------------
# ForensicLog lifecycle
# ---------------------------------------------------------------------------


class TestForensicLogLifecycle:
    def test_start_run_returns_uuid(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        run_id = fl.start_run("Open Chrome", "openai", "gpt-4o")
        assert len(run_id) == 36
        assert "-" in run_id

    def test_get_run_returns_metadata(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Test goal", "anthropic", "claude-3")
        run = fl.get_run()
        assert run["goal"] == "Test goal"
        assert run["provider"] == "anthropic"
        assert run["model"] == "claude-3"
        assert run["status"] == "running"

    def test_end_run(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.end_run("success", "Done", 3)
        run = fl.get_run()
        assert run["status"] == "success"
        assert run["summary"] == "Done"
        assert run["total_steps"] == 3
        assert run["end_time"] is not None


# ---------------------------------------------------------------------------
# Step logging
# ---------------------------------------------------------------------------


class TestForensicLogSteps:
    def test_log_step_returns_step_id(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        step_id = fl.log_step(1, "click", "Button", {"x": 100}, "success")
        assert len(step_id) == 36

    def test_logged_steps_retrievable(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Button A", {}, "success")
        fl.log_step(2, "type", "Input field", {"text": "hello"}, "success")
        steps = fl.get_steps()
        assert len(steps) == 2
        assert steps[0]["action_type"] == "click"
        assert steps[1]["action_type"] == "type"

    def test_sensitive_params_redacted_in_steps(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Login", "openai", "gpt-4o")
        fl.log_step(1, "type", "Password", {"password": "secret"}, "success")
        steps = fl.get_steps()
        assert steps[0]["params"]["password"] == "***REDACTED***"

    def test_log_event(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_event("pause", {"reason": "MFA detected"})
        steps = fl.get_steps()
        assert len(steps) == 1
        assert steps[0]["action_type"] == "event"
        assert steps[0]["result"] == "pause"
        assert steps[0]["params"]["reason"] == "MFA detected"


# ---------------------------------------------------------------------------
# Event type inference
# ---------------------------------------------------------------------------


class TestInferEventType:
    def test_success_is_action(self):
        assert ForensicLog._infer_event_type("success") == "action"

    def test_error_is_error(self):
        assert ForensicLog._infer_event_type("error: timeout") == "error"

    def test_fail_is_error(self):
        assert ForensicLog._infer_event_type("failed to click") == "error"

    def test_exception_is_error(self):
        assert ForensicLog._infer_event_type("exception raised") == "error"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    def test_no_run(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        assert "No forensic run" in fl.get_summary()

    def test_running_summary(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Open Excel", "openai", "gpt-4o")
        summary = fl.get_summary()
        assert "Open Excel" in summary
        assert "running" in summary


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_json(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        path = str(Path(tmpdir) / "test_export.json")
        assert fl.export_json(path) is True
        with Path(path).open() as fh:
            data = json.load(fh)
        assert data["run"]["goal"] == "Goal"
        assert len(data["steps"]) == 1

    def test_export_csv(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        path = str(Path(tmpdir) / "test_export.csv")
        assert fl.export_csv(path) is True
        with Path(path).open() as fh:
            lines = fh.readlines()
        assert len(lines) == 2  # header + 1 row

    def test_export_json_creates_parent_dirs(self):
        tmpdir = tempfile.mkdtemp()
        fl = ForensicLog(log_dir=tmpdir)
        fl.start_run("Goal", "openai", "gpt-4o")
        path = str(Path(tmpdir) / "sub" / "dir" / "out.json")
        assert fl.export_json(path) is True
        assert Path(path).is_file()
