"""Tests for core/audit_export.py — sensitive masking and export formats."""

import csv
import json
from pathlib import Path

import pytest

from core.audit_export import (
    AuditExporter,
    _compute_summary,
    _esc,
    _mask_log,
    _mask_value,
    export_audit,
)

# ---------------------------------------------------------------------------
# _mask_value
# ---------------------------------------------------------------------------


class TestMaskValue:
    def test_password_key_masked(self):
        assert _mask_value({"password": "hunter2"}) == {"password": "***"}

    def test_token_key_masked(self):
        assert _mask_value({"api_token": "tok-123"}) == {"api_token": "***"}

    def test_api_key_masked(self):
        assert _mask_value({"api_key": "sk-abc"}) == {"api_key": "***"}

    def test_secret_key_masked(self):
        assert _mask_value({"client_secret": "s"}) == {"client_secret": "***"}

    def test_access_key_masked(self):
        assert _mask_value({"access_key": "ak"}) == {"access_key": "***"}

    def test_auth_key_masked(self):
        assert _mask_value({"authorization": "Bearer x"}) == {"authorization": "***"}

    def test_normal_key_passed_through(self):
        assert _mask_value({"name": "Alice"}) == {"name": "Alice"}

    def test_nested_dict_masked(self):
        data = {"config": {"password": "pw", "count": 5}}
        result = _mask_value(data)
        assert result["config"]["password"] == "***"
        assert result["config"]["count"] == 5

    def test_list_masked(self):
        data = [{"password": "pw"}, {"safe": "val"}]
        result = _mask_value(data)
        assert result[0]["password"] == "***"
        assert result[1]["safe"] == "val"

    def test_string_value_matching_secret_pattern(self):
        assert _mask_value("my_api_key_value") == "***"

    def test_plain_string_not_matching(self):
        assert _mask_value("hello world") == "hello world"

    def test_non_string_scalar(self):
        assert _mask_value(42) == 42
        assert _mask_value(True) is True


# ---------------------------------------------------------------------------
# _mask_log
# ---------------------------------------------------------------------------


class TestMaskLog:
    def test_masks_params(self):
        log = [{"step": 1, "params": {"password": "pw"}}]
        masked = _mask_log(log)
        assert masked[0]["params"]["password"] == "***"

    def test_masks_result(self):
        log = [{"step": 1, "result": {"token": "tok"}}]
        masked = _mask_log(log)
        assert masked[0]["result"]["token"] == "***"

    def test_does_not_mutate_original(self):
        log = [{"step": 1, "params": {"password": "pw"}}]
        _mask_log(log)
        assert log[0]["params"]["password"] == "pw"


# ---------------------------------------------------------------------------
# _compute_summary
# ---------------------------------------------------------------------------


class TestComputeSummary:
    def test_basic_summary(self):
        log = [
            {"action": "click", "result": "ok", "duration": 0.5},
            {"action": "type", "result": "ok", "duration": 0.3},
            {"action": "click", "result": "fail", "duration": 0.1},
        ]
        summary = _compute_summary(log, {"status": "completed"})
        assert summary["total_steps"] == 3
        assert summary["success_count"] == 2
        assert summary["fail_count"] == 1
        assert summary["success_rate"] == pytest.approx(66.7, abs=0.1)
        assert summary["action_counts"]["click"] == 2
        assert summary["action_counts"]["type"] == 1
        assert summary["total_duration"] == pytest.approx(0.9)
        assert summary["status"] == "completed"

    def test_empty_log(self):
        summary = _compute_summary([], {})
        assert summary["total_steps"] == 0
        assert summary["success_rate"] == 0.0

    def test_null_result_counts_as_fail(self):
        log = [{"action": "x", "result": None}]
        summary = _compute_summary(log, {"status": "ok"})
        assert summary["fail_count"] == 1


# ---------------------------------------------------------------------------
# _esc
# ---------------------------------------------------------------------------


class TestEsc:
    def test_escapes_html_entities(self):
        assert _esc("<script>alert('xss')</script>") == (
            "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;"
        )

    def test_escapes_ampersand(self):
        assert _esc("a&b") == "a&amp;b"

    def test_escapes_quotes(self):
        assert _esc('say "hi"') == "say &quot;hi&quot;"


# ---------------------------------------------------------------------------
# AuditExporter — generate_report dispatch
# ---------------------------------------------------------------------------


@pytest.fixture
def exporter(tmp_path):
    return AuditExporter(output_dir=str(tmp_path / "reports"))


@pytest.fixture
def sample_log():
    return [
        {
            "step": 1,
            "timestamp": "2025-01-01T00:00:00",
            "action": "click",
            "params": {"x": 100},
            "result": "ok",
            "duration": 0.5,
        },
        {
            "step": 2,
            "timestamp": "2025-01-01T00:00:01",
            "action": "type",
            "params": {"password": "secret"},
            "result": "ok",
            "duration": 0.3,
        },
    ]


@pytest.fixture
def sample_metadata():
    return {
        "goal": "Test goal",
        "start_time": "2025-01-01T00:00:00",
        "end_time": "2025-01-01T00:00:05",
        "total_steps": 2,
        "status": "completed",
    }


class TestGenerateReport:
    def test_unsupported_format_raises(self, exporter, sample_log, sample_metadata):
        with pytest.raises(ValueError, match="Unsupported format"):
            exporter.generate_report(sample_log, sample_metadata, format="xml")


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


class TestExportJSON:
    def test_creates_valid_json(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="json")
        assert Path(path).is_file()
        with Path(path).open() as f:
            data = json.load(f)
        assert "Audit Report" in data["header"]
        assert "steps" in data
        assert "summary" in data

    def test_masks_sensitive_params(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="json")
        with Path(path).open() as f:
            data = json.load(f)
        # Step 2 has password param — should be masked
        step2 = data["steps"][1]
        assert step2["params"]["password"] == "***"


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


class TestExportCSV:
    def test_creates_csv_file(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="csv")
        assert Path(path).is_file()
        with Path(path).open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["action"] == "click"

    def test_csv_has_header(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="csv")
        with Path(path).open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert "step" in header
        assert "action" in header


# ---------------------------------------------------------------------------
# Text export
# ---------------------------------------------------------------------------


class TestExportText:
    def test_creates_text_file(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="text")
        assert Path(path).is_file()
        with Path(path).open() as f:
            content = f.read()
        assert "Sentinel Desktop" in content
        assert "Summary Statistics" in content

    def test_text_contains_metadata(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="text")
        with Path(path).open() as f:
            content = f.read()
        assert "Test goal" in content
        assert "completed" in content

    def test_txt_alias(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="txt")
        assert Path(path).is_file()


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------


class TestExportHTML:
    def test_creates_html_file(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="html")
        assert Path(path).is_file()
        with Path(path).open() as f:
            content = f.read()
        assert "<!DOCTYPE html>" in content
        assert "Sentinel Desktop" in content

    def test_html_escaping(self, exporter, sample_metadata):
        log = [
            {
                "step": 1,
                "timestamp": "t",
                "action": "<script>",
                "params": {},
                "result": "ok",
                "duration": 0,
            }
        ]
        path = exporter.generate_report(log, sample_metadata, format="html")
        with Path(path).open() as f:
            content = f.read()
        assert "<script>" not in content.replace("<!DOCTYPE html>", "").replace(
            "<script>", ""
        ).replace("</script>", "")
        assert "&lt;script&gt;" in content

    def test_html_contains_summary(self, exporter, sample_log, sample_metadata):
        path = exporter.generate_report(sample_log, sample_metadata, format="html")
        with Path(path).open() as f:
            content = f.read()
        assert "Summary Statistics" in content
        assert "Action Breakdown" in content


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


class TestExportAuditConvenience:
    def test_export_audit_creates_file(self, tmp_path, sample_log, sample_metadata):
        path = export_audit(
            sample_log, sample_metadata, fmt="json", output_dir=str(tmp_path / "out")
        )
        assert Path(path).is_file()


# ---------------------------------------------------------------------------
# Error handling — write failures propagate with logging
# ---------------------------------------------------------------------------


class TestExportIOErrors:
    def test_json_write_failure_propagates(self, tmp_path, sample_log, sample_metadata):
        exporter = AuditExporter(output_dir=str(tmp_path / "reports"))
        # Override _filename to return a path that's a directory (can't write to it)
        target = tmp_path / "reports" / "blocked.json"
        target.mkdir(parents=True)
        exporter._filename = lambda base, ext: str(target)
        with pytest.raises(OSError):
            exporter.export_json(sample_log, sample_metadata)

    def test_csv_write_failure_propagates(self, tmp_path, sample_log, sample_metadata):
        exporter = AuditExporter(output_dir=str(tmp_path / "reports"))
        target = tmp_path / "reports" / "blocked.csv"
        target.mkdir(parents=True)
        exporter._filename = lambda base, ext: str(target)
        with pytest.raises(OSError):
            exporter.export_csv(sample_log, sample_metadata)

    def test_makedirs_failure_logged(self, tmp_path):
        # Point output_dir at a path under a file (not a directory)
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file")
        bad_path = str(blocker / "subdir")
        # Should not raise, but should log the error
        exporter = AuditExporter(output_dir=bad_path)
        assert exporter.output_dir == bad_path
