"""Tests for core/engine.py — stop, context building, report generation, logging."""

import json
from unittest.mock import patch

from core.engine import AgentEngine


class TestStop:
    def test_stop_sets_running_false(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.running = True
        eng.stop()
        assert eng.running is False

    def test_stop_idempotent(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.running = False
        eng.stop()
        assert eng.running is False


class TestBuildEnvContext:
    def test_returns_string(self):
        eng = AgentEngine({})
        result = eng._build_env_context()
        assert isinstance(result, str)

    @patch("core.engine.sysinfo")
    @patch("core.engine.wm")
    def test_includes_tenant_when_configured(self, mock_wm, mock_sysinfo):
        mock_sysinfo.brief_system_info.return_value = "Win11"
        mock_wm.list_windows.return_value = []
        eng = AgentEngine({"tenant_name": "AcmeCorp"})
        result = eng._build_env_context()
        assert "AcmeCorp" in result

    @patch("core.engine.sysinfo")
    @patch("core.engine.wm")
    def test_includes_lockdown_mode(self, mock_wm, mock_sysinfo):
        mock_sysinfo.brief_system_info.return_value = ""
        mock_wm.list_windows.return_value = []
        eng = AgentEngine({"tenant_name": "Acme", "tenant_lockdown": True})
        result = eng._build_env_context()
        assert "LOCKDOWN" in result

    @patch("core.engine.sysinfo")
    def test_handles_sysinfo_failure(self, mock_sysinfo):
        mock_sysinfo.brief_system_info.side_effect = RuntimeError("boom")
        eng = AgentEngine({})
        result = eng._build_env_context()
        assert isinstance(result, str)  # doesn't crash


class TestBuildAppContext:
    @patch("core.engine.wm")
    def test_returns_empty_when_no_focused_window(self, mock_wm):
        mock_wm.list_windows.return_value = [{"title": "Chrome", "is_focused": False}]
        eng = AgentEngine({})
        result = eng._build_app_context()
        assert result == ""

    @patch("core.engine.wm")
    def test_returns_profile_context_for_known_app(self, mock_wm):
        mock_wm.list_windows.return_value = [{"title": "Calculator", "is_focused": True}]
        eng = AgentEngine({})
        result = eng._build_app_context()
        # Should return a string (may be empty if Calculator isn't profiled)
        assert isinstance(result, str)

    @patch("core.engine.wm")
    def test_handles_list_windows_failure(self, mock_wm):
        mock_wm.list_windows.side_effect = RuntimeError("no windows")
        eng = AgentEngine({})
        result = eng._build_app_context()
        assert result == ""


class TestGenerateReport:
    def test_basic_report_structure(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 3
        eng.notes = ["Did a thing"]
        eng.forensic_log = []
        eng.finish_summary = "All done"
        eng.config = {"provider": "openai", "model": "gpt-4o"}
        report = eng._generate_report("open chrome", 5.2)
        assert report["status"] == "success"
        assert report["steps_total"] == 3
        assert report["goal"] == "open chrome"
        assert report["summary"] == "All done"
        assert "text" in report
        assert "SENTINEL DESKTOP" in report["text"]

    def test_failed_report_when_no_summary(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 1
        eng.notes = []
        eng.forensic_log = []
        eng.finish_summary = ""
        eng.config = {"provider": "openai", "model": "gpt-4o"}
        report = eng._generate_report("test", 1.0)
        assert report["status"] == "failed"

    def test_report_includes_errors(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 2
        eng.notes = []
        eng.forensic_log = [
            {"step": 1, "action": "click", "result": {"ok": False, "msg": "missed"}},
        ]
        eng.finish_summary = ""
        eng.config = {"provider": "openai", "model": "gpt-4o"}
        report = eng._generate_report("goal", 2.0)
        assert len(report["error_list"]) == 1
        assert report["steps_failed"] == 1

    def test_report_includes_notes(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 1
        eng.notes = ["observed X", "tried Y"]
        eng.forensic_log = []
        eng.finish_summary = "done"
        eng.config = {"provider": "test", "model": "test"}
        report = eng._generate_report("goal", 1.0)
        assert report["notes"] == ["observed X", "tried Y"]
        assert "observed X" in report["text"]


class TestLogStep:
    def test_appends_to_forensic_log(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 1
        eng.forensic_log = []
        eng._log_step({"action": "click", "x": 100}, {"ok": True, "msg": "clicked"})
        assert len(eng.forensic_log) == 1
        entry = eng.forensic_log[0]
        assert entry["step"] == 1
        assert entry["action"] == "click"
        assert entry["params"] == {"x": 100}
        assert entry["result"]["ok"] is True
        assert "timestamp" in entry


class TestLogStepResult:
    def test_updates_existing_entry(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.forensic_log = [
            {"step": 1, "action": "click", "result": {"pending": True}},
            {"step": 2, "action": "type", "result": {"pending": True}},
        ]
        eng._log_step_result(2, {"ok": True, "msg": "typed"})
        assert eng.forensic_log[1]["result"]["ok"] is True
        # Step 1 unchanged
        assert eng.forensic_log[0]["result"]["pending"] is True

    def test_no_crash_on_missing_step(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.forensic_log = []
        eng._log_step_result(99, {"ok": True})  # should not raise


class TestExportLog:
    def test_exports_valid_json(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.forensic_log = [{"step": 1, "action": "click"}]
        result = eng.export_log()
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["action"] == "click"

    def test_empty_log(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.forensic_log = []
        result = eng.export_log()
        assert json.loads(result) == []


class TestAddVisionMessage:
    def test_anthropic_format(self):
        eng = AgentEngine({"provider": "anthropic"})
        eng.step = 1
        messages: list = []
        eng._add_vision_message(messages, "base64data", "Goal: test")
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "user"
        content = msg["content"]
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image"
        assert content[1]["source"]["type"] == "base64"
        assert msg["_sentinel_has_image"] is True

    def test_openai_format(self):
        eng = AgentEngine({"provider": "openai"})
        eng.step = 2
        messages: list = []
        eng._add_vision_message(messages, "base64data", "Step 2 result:")
        assert len(messages) == 1
        msg = messages[0]
        content = msg["content"]
        assert content[1]["type"] == "image_url"
        assert "base64data" in content[1]["image_url"]["url"]


class TestRunResetsState:
    def test_run_resets_notes_and_log_on_start(self):
        """Calling run() a second time must clear stale state."""
        eng = AgentEngine({"provider": "openai", "api_key": "", "model": "gpt-4o"})
        # First run — will bail on missing key
        result1 = eng.run("first goal")
        assert result1["error"] == "api_key_missing"
        # Simulate leftover state
        eng.forensic_log = [{"old": True}]
        eng.notes = ["stale"]
        eng.finish_summary = "old summary"
        # Second run
        result2 = eng.run("second goal")
        assert result2["error"] == "api_key_missing"
        assert result2["notes"] != ["stale"]  # stale notes replaced
        assert eng.forensic_log == []
