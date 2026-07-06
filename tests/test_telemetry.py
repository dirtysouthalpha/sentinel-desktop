"""
Tests for the v26.0.0 Telemetry module.
"""
import tempfile
from pathlib import Path

from core.telemetry import TelemetryCollector


class TestTelemetryCollector:
    def test_init_creates_db(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=True)
        assert (tmp_path / "tel.db").exists()

    def test_disabled_does_not_record(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=False)
        rid = tc.start_run("test goal")
        assert rid == 0

    def test_start_and_finish_run(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=True)
        rid = tc.start_run("open notepad", tenant="acme", model="gpt-4o")
        assert rid > 0
        tc.finish_run(rid, steps=5, status="completed")
        runs = tc.get_recent_runs(limit=10)
        assert len(runs) >= 1
        assert runs[0]["goal"] == "open notepad"
        assert runs[0]["status"] == "completed"
        assert runs[0]["steps"] == 5

    def test_record_action(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=True)
        rid = tc.start_run("test")
        tc.record_action(rid, step=1, action_type="click", success=True, latency_ms=50.0)
        tc.record_action(rid, step=2, action_type="type", success=False, latency_ms=120.0)
        summary = tc.get_summary()
        assert summary["actions"]["total"] >= 2
        assert summary["actions"]["successful"] >= 1

    def test_record_llm_call(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=True)
        rid = tc.start_run("test")
        tc.record_llm_call(rid, provider="openai", model="gpt-4o", input_tokens=500, output_tokens=200, latency_ms=800.0)
        summary = tc.get_summary()
        assert summary["llm_tokens"]["input"] >= 500
        assert summary["llm_tokens"]["output"] >= 200

    def test_summary_empty_db(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=True)
        s = tc.get_summary()
        assert s["runs"]["total"] == 0
        assert s["actions"]["total"] == 0

    def test_get_recent_runs_limit(self, tmp_path):
        tc = TelemetryCollector(db_path=tmp_path / "tel.db", enabled=True)
        for i in range(5):
            tc.start_run(f"goal {i}")
        runs = tc.get_recent_runs(limit=3)
        assert len(runs) == 3
