"""Tests for core/audit_export.py — OSError write paths and utility helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from core.audit_export import AuditExporter, _now_iso

# ---------------------------------------------------------------------------
# _now_iso
# ---------------------------------------------------------------------------


class TestNowIso:
    def test_returns_iso_format(self) -> None:
        result = _now_iso()
        assert "T" in result
        datetime.fromisoformat(result)

    def test_is_utc(self) -> None:
        result = _now_iso()
        assert "+" in result or result.endswith("Z")


# ---------------------------------------------------------------------------
# _filename helper
# ---------------------------------------------------------------------------


class TestFilename:
    def test_contains_base_and_ext(self, tmp_path: Path) -> None:
        exporter = AuditExporter(output_dir=str(tmp_path / "reports"))
        result = exporter._filename("audit_report", "html")
        assert "audit_report" in result
        assert result.endswith(".html")

    def test_contains_timestamp(self, tmp_path: Path) -> None:
        exporter = AuditExporter(output_dir=str(tmp_path / "reports"))
        result = exporter._filename("report", "json")
        assert "_" in Path(result).stem


# ---------------------------------------------------------------------------
# export_text — OSError path
# ---------------------------------------------------------------------------


class TestExportTextOSError:
    def test_text_write_failure_propagates(self, tmp_path: Path) -> None:
        exporter = AuditExporter(output_dir=str(tmp_path / "reports"))
        log = [{"step": 1, "action": "click", "params": {}, "result": "ok", "duration": 0.1}]
        metadata = {"goal": "test", "status": "done", "total_steps": 1}

        target = tmp_path / "reports" / "blocked.txt"
        target.mkdir(parents=True)
        exporter._filename = lambda base, ext: str(target)

        with pytest.raises(OSError):
            exporter.export_text(log, metadata)


# ---------------------------------------------------------------------------
# export_html — OSError path
# ---------------------------------------------------------------------------


class TestExportHTMLOSError:
    def test_html_write_failure_propagates(self, tmp_path: Path) -> None:
        exporter = AuditExporter(output_dir=str(tmp_path / "reports"))
        log = [{"step": 1, "action": "click", "params": {}, "result": "ok", "duration": 0.1}]
        metadata = {"goal": "test", "status": "done", "total_steps": 1}

        target = tmp_path / "reports" / "blocked.html"
        target.mkdir(parents=True)
        exporter._filename = lambda base, ext: str(target)

        with pytest.raises(OSError):
            exporter.export_html(log, metadata)


# ---------------------------------------------------------------------------
# HTML helper methods
# ---------------------------------------------------------------------------


class TestHTMLHelpers:
    def test_html_preamble_contains_doctype(self) -> None:
        result = AuditExporter._html_preamble()
        assert "<!DOCTYPE html>" in result
        assert "<style>" in result

    def test_html_postamble_closes_tags(self) -> None:
        result = AuditExporter._html_postamble()
        assert "</body>" in result
        assert "</html>" in result
        assert "End of Report" in result

    def test_html_metadata_section(self) -> None:
        metadata = {
            "goal": "Open notepad",
            "start_time": "2025-01-01T00:00:00",
            "end_time": "2025-01-01T00:00:05",
            "total_steps": 3,
            "status": "completed",
        }
        result = AuditExporter._html_metadata_section(metadata)
        assert "Open notepad" in result
        assert "completed" in result
        assert "meta-grid" in result

    def test_html_timeline(self) -> None:
        log = [
            {
                "step": 1,
                "timestamp": "t1",
                "action": "click",
                "params": {"x": 1},
                "result": "ok",
                "duration": 0.5,
            }
        ]
        result = AuditExporter._html_timeline(log)
        assert "<table>" in result
        assert "click" in result
        assert "badge-success" in result

    def test_html_timeline_failure_badge(self) -> None:
        log = [
            {
                "step": 1,
                "timestamp": "t1",
                "action": "click",
                "params": {},
                "result": "fail",
                "duration": 0.1,
            }
        ]
        result = AuditExporter._html_timeline(log)
        assert "badge-fail" in result

    def test_html_summary(self) -> None:
        summary = {
            "total_steps": 5,
            "success_count": 4,
            "fail_count": 1,
            "success_rate": 80.0,
            "total_duration": 2.5,
            "status": "completed",
            "action_counts": {"click": 3, "type": 2},
        }
        result = AuditExporter._html_summary(summary)
        assert "5" in result
        assert "80.0%" in result
        assert "click: 3" in result
        assert "summary-grid" in result
