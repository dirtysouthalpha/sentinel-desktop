"""Additional coverage tests for audit_export.py — edge cases and gap paths."""

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
# _mask_value edge cases
# ---------------------------------------------------------------------------


class TestMaskValueEdgeCases:
    """_mask_value with unusual inputs."""

    def test_nested_list_with_dicts(self) -> None:
        """List containing dicts with sensitive keys should be masked."""
        data = [{"password": "secret123", "name": "alice"}, {"token": "abc"}]
        result = _mask_value(data)
        assert result[0]["password"] == "***"
        assert result[0]["name"] == "alice"
        assert result[1]["token"] == "***"

    def test_integer_value(self) -> None:
        """Integer values should pass through unchanged."""
        assert _mask_value(42) == 42

    def test_float_value(self) -> None:
        """Float values should pass through unchanged."""
        assert _mask_value(3.14) == 3.14

    def test_boolean_value(self) -> None:
        """Boolean values should pass through unchanged."""
        assert _mask_value(True) is True
        assert _mask_value(False) is False

    def test_none_value(self) -> None:
        """None should pass through unchanged."""
        assert _mask_value(None) is None

    def test_deeply_nested(self) -> None:
        """Three levels of nesting with sensitive keys."""
        data = {"outer": {"middle": {"api_key": "sk-12345"}}}
        result = _mask_value(data)
        assert result["outer"]["middle"]["api_key"] == "***"

    def test_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        assert _mask_value({}) == {}

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        assert _mask_value([]) == []


# ---------------------------------------------------------------------------
# _mask_log edge cases
# ---------------------------------------------------------------------------


class TestMaskLogEdgeCases:
    """_mask_log with entries missing optional keys."""

    def test_entry_missing_params_and_result(self) -> None:
        """Entries without params/result keys are returned as-is."""
        log = [{"step": 1, "action": "click", "timestamp": "2024-01-01"}]
        result = _mask_log(log)
        assert len(result) == 1
        assert result[0]["step"] == 1
        assert "params" not in result[0]
        assert "result" not in result[0]

    def test_entry_with_params_only(self) -> None:
        """Entry with params but no result."""
        log = [{"params": {"username": "admin", "password": "s3cret"}}]
        result = _mask_log(log)
        assert result[0]["params"]["password"] == "***"
        assert result[0]["params"]["username"] == "admin"

    def test_empty_log(self) -> None:
        """Empty log returns empty list."""
        assert _mask_log([]) == []


# ---------------------------------------------------------------------------
# _compute_summary edge cases
# ---------------------------------------------------------------------------


class TestComputeSummaryEdgeCases:
    """Summary calculation with various result patterns."""

    def test_all_failures(self) -> None:
        """All entries with 'fail' result."""
        log = [
            {"result": "fail", "action": "click"},
            {"result": "error", "action": "type"},
        ]
        summary = _compute_summary(log, {"status": "failed"})
        assert summary["success_count"] == 0
        assert summary["fail_count"] == 2
        assert summary["success_rate"] == 0.0

    def test_mixed_case_results(self) -> None:
        """'FAIL' and 'Fail' should also count as failures."""
        log = [
            {"result": "FAIL", "action": "click"},
            {"result": "Fail", "action": "type"},
            {"result": "ok", "action": "wait"},
        ]
        summary = _compute_summary(log, {"status": "mixed"})
        assert summary["fail_count"] == 2
        assert summary["success_count"] == 1

    def test_empty_log(self) -> None:
        """Empty log returns zero stats."""
        summary = _compute_summary([], {"status": "empty"})
        assert summary["total_steps"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["action_counts"] == {}

    def test_duration_summed(self) -> None:
        """Durations are summed and rounded."""
        log = [
            {"result": "ok", "action": "a", "duration": 1.5},
            {"result": "ok", "action": "b", "duration": 2.3},
        ]
        summary = _compute_summary(log, {"status": "ok"})
        assert summary["total_duration"] == 3.8

    def test_metadata_status_default(self) -> None:
        """Missing status key defaults to 'unknown'."""
        summary = _compute_summary([], {})
        assert summary["status"] == "unknown"


# ---------------------------------------------------------------------------
# generate_report edge cases
# ---------------------------------------------------------------------------


class TestGenerateReportEdgeCases:
    """generate_report dispatch and backwards compat."""

    @pytest.fixture
    def exporter(self, tmp_path: Path) -> AuditExporter:
        return AuditExporter(output_dir=str(tmp_path / "reports"))

    @pytest.fixture
    def sample_log(self) -> list[dict]:
        return [{"step": 1, "action": "click", "params": {"x": 100}, "result": "ok", "duration": 0.5}]

    @pytest.fixture
    def sample_metadata(self) -> dict:
        return {"goal": "test", "start_time": "2024-01-01", "status": "ok"}

    def test_format_kwarg_backwards_compat(
        self, exporter: AuditExporter, sample_log: list, sample_metadata: dict
    ) -> None:
        """The `format` keyword arg should override `fmt`."""
        path = exporter.generate_report(
            sample_log, sample_metadata, fmt="html", format="json"
        )
        assert path.endswith(".json")

    def test_dir_not_ready_raises_oserror(self) -> None:
        """If _dir_ready is False, generate_report raises OSError."""
        exporter = AuditExporter(output_dir="/tmp/reports_test_exist")
        exporter._dir_ready = False
        with pytest.raises(OSError, match="not available"):
            exporter.generate_report([], {}, fmt="json")

    def test_case_insensitive_format(
        self, exporter: AuditExporter, sample_log: list, sample_metadata: dict
    ) -> None:
        """Format string is case-insensitive."""
        path = exporter.generate_report(sample_log, sample_metadata, fmt="HTML")
        assert path.endswith(".html")


# ---------------------------------------------------------------------------
# _esc edge cases
# ---------------------------------------------------------------------------


class TestEscEdgeCases:
    """HTML entity escaping."""

    def test_all_special_chars(self) -> None:
        """All five HTML entities are escaped."""
        result = _esc('<>&"\'')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result
        assert "&#39;" in result

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert _esc("") == ""

    def test_no_special_chars(self) -> None:
        """Plain text passes through unchanged."""
        assert _esc("hello world") == "hello world"


# ---------------------------------------------------------------------------
# export_text edge cases
# ---------------------------------------------------------------------------


class TestExportTextEdgeCases:
    """Text export with unusual inputs."""

    @pytest.fixture
    def exporter(self, tmp_path: Path) -> AuditExporter:
        return AuditExporter(output_dir=str(tmp_path / "reports"))

    def test_long_result_truncated(self, exporter: AuditExporter) -> None:
        """Results longer than column width are truncated with '...'."""
        long_result = "x" * 50
        log = [{"step": 1, "action": "click", "result": long_result, "duration": 1.0}]
        metadata = {"goal": "test", "status": "ok"}
        path = exporter.export_text(log, metadata)
        content = Path(path).read_text()
        assert "..." in content

    def test_empty_log(self, exporter: AuditExporter) -> None:
        """Empty log still produces valid text report."""
        metadata = {"goal": "test", "status": "ok"}
        path = exporter.export_text([], metadata)
        content = Path(path).read_text()
        assert "Audit Report" in content
        assert "Total Steps   : 0" in content

    def test_metadata_missing_keys(self, exporter: AuditExporter) -> None:
        """Missing metadata keys default to N/A."""
        log = [{"step": 1, "action": "click", "result": "ok", "duration": 0}]
        path = exporter.export_text(log, {})
        content = Path(path).read_text()
        assert "N/A" in content


# ---------------------------------------------------------------------------
# CSV edge cases
# ---------------------------------------------------------------------------


class TestCsvEdgeCases:
    """CSV export with complex data."""

    @pytest.fixture
    def exporter(self, tmp_path: Path) -> AuditExporter:
        return AuditExporter(output_dir=str(tmp_path / "reports"))

    def test_csv_with_complex_params(self, exporter: AuditExporter) -> None:
        """Nested JSON in params is serialized."""
        log = [
            {
                "step": 1,
                "action": "type",
                "params": {"nested": {"key": "value"}},
                "result": "ok",
                "duration": 0.5,
            }
        ]
        metadata = {"goal": "test", "status": "ok"}
        path = exporter.export_csv(log, metadata)
        content = Path(path).read_text()
        assert "nested" in content

    def test_csv_with_sensitive_params_masked(self, exporter: AuditExporter) -> None:
        """Password in params is masked in CSV output."""
        log = [
            {
                "step": 1,
                "action": "login",
                "params": {"password": "super_secret"},
                "result": "ok",
                "duration": 0.3,
            }
        ]
        metadata = {"goal": "test", "status": "ok"}
        path = exporter.export_csv(log, metadata)
        content = Path(path).read_text()
        assert "super_secret" not in content
        assert "***" in content


# ---------------------------------------------------------------------------
# HTML edge cases
# ---------------------------------------------------------------------------


class TestHtmlEdgeCases:
    """HTML export edge cases."""

    @pytest.fixture
    def exporter(self, tmp_path: Path) -> AuditExporter:
        return AuditExporter(output_dir=str(tmp_path / "reports"))

    def test_html_timeline_empty_log(self, exporter: AuditExporter) -> None:
        """Empty log produces valid HTML with no rows."""
        metadata = {"goal": "test", "status": "ok"}
        path = exporter.export_html([], metadata)
        content = Path(path).read_text()
        assert "<tbody>" in content
        assert "</tbody>" in content

    def test_html_summary_empty_action_counts(self, exporter: AuditExporter) -> None:
        """Empty log has no action breakdown items."""
        metadata = {"goal": "test", "status": "ok"}
        path = exporter.export_html([], metadata)
        content = Path(path).read_text()
        assert "Action Breakdown" in content
        # Empty <li> items — just the list tags
        assert '<ul class="action-list">' in content


# ---------------------------------------------------------------------------
# export_audit convenience function
# ---------------------------------------------------------------------------


class TestExportAuditConvenience:
    """export_audit one-shot wrapper."""

    def test_json_format(self, tmp_path: Path) -> None:
        """export_audit with fmt='json' creates JSON file."""
        log = [{"step": 1, "action": "test", "result": "ok", "duration": 0.1}]
        metadata = {"goal": "test", "status": "ok"}
        path = export_audit(log, metadata, fmt="json", output_dir=str(tmp_path))
        assert path.endswith(".json")
        data = json.loads(Path(path).read_text())
        assert data["steps"][0]["action"] == "test"

    def test_csv_format(self, tmp_path: Path) -> None:
        """export_audit with fmt='csv' creates CSV file."""
        log = [{"step": 1, "action": "test", "result": "ok", "duration": 0.1}]
        metadata = {"goal": "test", "status": "ok"}
        path = export_audit(log, metadata, fmt="csv", output_dir=str(tmp_path))
        assert path.endswith(".csv")

    def test_text_format(self, tmp_path: Path) -> None:
        """export_audit with fmt='text' creates text file."""
        log = [{"step": 1, "action": "test", "result": "ok", "duration": 0.1}]
        metadata = {"goal": "test", "status": "ok"}
        path = export_audit(log, metadata, fmt="text", output_dir=str(tmp_path))
        assert path.endswith(".txt")
