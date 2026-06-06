"""Tests for core/engine.py — JSON parsing, message cleaning, action parsing."""

import json

from core.engine import (
    AgentEngine,
    _clean_messages_for_api,
    _find_balanced_json_with_key,
)


class TestFindBalancedJsonWithKey:
    def test_simple_object(self):
        text = 'here is {"action":"click","x":100} ok'
        result = _find_balanced_json_with_key(text, "action")
        assert result == {"action": "click", "x": 100}

    def test_nested_braces(self):
        text = 'prefix {"outer": {"inner": 1}, "action": "go"} suffix'
        result = _find_balanced_json_with_key(text, "action")
        assert result is not None
        assert result["action"] == "go"

    def test_string_with_braces(self):
        text = 'text {"key": "a{b}c", "action": "test"} end'
        result = _find_balanced_json_with_key(text, "action")
        assert result is not None
        assert result["action"] == "test"

    def test_no_key_match(self):
        text = '{"foo": "bar"}'
        assert _find_balanced_json_with_key(text, "action") is None

    def test_no_json(self):
        assert _find_balanced_json_with_key("plain text", "action") is None

    def test_invalid_json_with_key(self):
        text = '{"action": broken}'
        assert _find_balanced_json_with_key(text, "action") is None

    def test_escaped_quotes(self):
        text = '{"action":"click","text":"say \\"hello\\""}'
        result = _find_balanced_json_with_key(text, "action")
        assert result is not None
        assert result["action"] == "click"
        assert result["text"] == 'say "hello"'

    def test_multiple_objects_returns_first_with_key(self):
        text = '{"foo":1} and {"action":"go","x":1}'
        result = _find_balanced_json_with_key(text, "action")
        assert result is not None
        assert result["action"] == "go"


class TestCleanMessagesForApi:
    def test_strips_sentinel_keys(self):
        messages = [
            {"role": "user", "content": "hi", "_sentinel_has_image": True, "_sentinel_step": 5},
        ]
        cleaned = _clean_messages_for_api(messages)
        assert "_sentinel_has_image" not in cleaned[0]
        assert "_sentinel_step" not in cleaned[0]
        assert cleaned[0]["role"] == "user"

    def test_preserves_normal_keys(self):
        messages = [{"role": "user", "content": "hi"}]
        cleaned = _clean_messages_for_api(messages)
        assert cleaned == messages

    def test_handles_non_dict(self):
        messages = ["plain string", {"role": "user", "content": "hi"}]
        cleaned = _clean_messages_for_api(messages)
        assert cleaned[0] == "plain string"

    def test_does_not_mutate_original(self):
        messages = [{"role": "user", "content": "hi", "_sentinel_step": 1}]
        _clean_messages_for_api(messages)
        assert "_sentinel_step" in messages[0]


class TestParseAction:
    def test_plain_action_json(self):
        engine = AgentEngine.__new__(AgentEngine)
        result = engine._parse_action('{"action":"click","x":100,"y":200}')
        assert result == {"action": "click", "x": 100, "y": 200}

    def test_tool_call_envelope(self):
        engine = AgentEngine.__new__(AgentEngine)
        payload = json.dumps(
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "click",
                            "arguments": '{"x": 50, "y": 60}',
                        }
                    }
                ]
            }
        )
        result = engine._parse_action(payload)
        assert result is not None
        assert result["action"] == "click"
        assert result["x"] == 50

    def test_markdown_fenced_json(self):
        engine = AgentEngine.__new__(AgentEngine)
        text = '```json\n{"action": "type_text", "text": "hello"}\n```'
        result = engine._parse_action(text)
        assert result == {"action": "type_text", "text": "hello"}

    def test_returns_none_for_no_json(self):
        engine = AgentEngine.__new__(AgentEngine)
        assert engine._parse_action("just plain text") is None


class TestActionFromToolCall:
    def test_openai_shape(self):
        tool_calls = [{"function": {"name": "click", "arguments": '{"x": 10, "y": 20}'}}]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result == {"action": "click", "x": 10, "y": 20}

    def test_anthropic_shape(self):
        tool_calls = [{"name": "click", "input": {"x": 5, "y": 10}}]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result == {"action": "click", "x": 5, "y": 10}

    def test_dict_arguments(self):
        tool_calls = [{"function": {"name": "click", "arguments": {"x": 1}}}]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result == {"action": "click", "x": 1}

    def test_empty_tool_calls(self):
        assert AgentEngine._action_from_tool_call([]) is None
        assert AgentEngine._action_from_tool_call(None) is None

    def test_non_dict_call(self):
        assert AgentEngine._action_from_tool_call(["string"]) is None

    def test_no_name_returns_none(self):
        assert AgentEngine._action_from_tool_call([{"function": {}}]) is None

    def test_drops_action_from_args(self):
        tool_calls = [{"function": {"name": "click", "arguments": '{"action":"click","x":1}'}}]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result == {"action": "click", "x": 1}

    def test_invalid_json_arguments(self):
        tool_calls = [{"function": {"name": "click", "arguments": "not json{{{"}}]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result is not None
        assert result["action"] == "click"


class TestStripScreenshotParams:
    """Tests for AgentEngine._strip_screenshot_params static method."""

    def test_strips_screenshot_key(self):
        params = {"x": 100, "screenshot": "base64data", "y": 200}
        result = AgentEngine._strip_screenshot_params(params)
        assert "screenshot" not in result
        assert result["x"] == 100
        assert result["y"] == 200

    def test_returns_empty_dict_for_none(self):
        assert AgentEngine._strip_screenshot_params(None) == {}

    def test_returns_empty_dict_for_empty(self):
        assert AgentEngine._strip_screenshot_params({}) == {}

    def test_preserves_non_screenshot_keys(self):
        params = {"action": "click", "x": 1, "text": "hello"}
        assert AgentEngine._strip_screenshot_params(params) == params

    def test_strips_only_screenshot_not_other_keys(self):
        params = {"screenshot": "data", "screen": "value"}
        result = AgentEngine._strip_screenshot_params(params)
        assert "screenshot" not in result
        assert result.get("screen") == "value"


class TestComputeActionCounts:
    """Tests for AgentEngine._compute_action_counts."""

    def test_counts_single_action_type(self):
        engine = AgentEngine.__new__(AgentEngine)
        engine.forensic_log = [
            {"action": "click"},
            {"action": "click"},
            {"action": "click"},
        ]
        assert engine._compute_action_counts() == {"click": 3}

    def test_counts_multiple_action_types(self):
        engine = AgentEngine.__new__(AgentEngine)
        engine.forensic_log = [
            {"action": "click"},
            {"action": "type_text"},
            {"action": "click"},
        ]
        result = engine._compute_action_counts()
        assert result == {"click": 2, "type_text": 1}

    def test_empty_log_returns_empty_dict(self):
        engine = AgentEngine.__new__(AgentEngine)
        engine.forensic_log = []
        assert engine._compute_action_counts() == {}

    def test_missing_action_key_counts_as_unknown(self):
        engine = AgentEngine.__new__(AgentEngine)
        engine.forensic_log = [{"other": "data"}, {"action": "click"}]
        result = engine._compute_action_counts()
        assert result == {"unknown": 1, "click": 1}


class TestBuildStepTrace:
    """Tests for AgentEngine._build_step_trace."""

    def test_builds_trace_from_entries(self):
        engine = AgentEngine.__new__(AgentEngine)
        entries = [
            {
                "step": 1,
                "action": "click",
                "params": {"x": 100, "y": 200},
                "result": {"ok": True, "msg": "clicked"},
                "timestamp": "2025-01-01T00:00:00",
            }
        ]
        trace = engine._build_step_trace(entries)
        assert len(trace) == 1
        assert trace[0]["step"] == 1
        assert trace[0]["action"] == "click"
        assert trace[0]["ok"] is True

    def test_strips_screenshots_from_params(self):
        engine = AgentEngine.__new__(AgentEngine)
        entries = [
            {
                "step": 1,
                "action": "click",
                "params": {"x": 10, "screenshot": "huge_base64_string"},
                "result": {"ok": True, "msg": "ok"},
                "timestamp": "t1",
            }
        ]
        trace = engine._build_step_trace(entries)
        assert "screenshot" not in trace[0]["params"]
        assert trace[0]["params"]["x"] == 10

    def test_handles_none_params(self):
        engine = AgentEngine.__new__(AgentEngine)
        entries = [
            {"step": 1, "action": "note", "params": None, "result": {"ok": True}, "timestamp": "t1"}
        ]
        trace = engine._build_step_trace(entries)
        assert trace[0]["params"] == {}

    def test_truncates_output_preview(self):
        engine = AgentEngine.__new__(AgentEngine)
        entries = [
            {
                "step": 1,
                "action": "click",
                "params": {},
                "result": {"ok": True, "msg": "x" * 500},
                "timestamp": "t1",
            }
        ]
        trace = engine._build_step_trace(entries)
        assert len(trace[0]["output_preview"]) <= 200

    def test_empty_entries_returns_empty_list(self):
        engine = AgentEngine.__new__(AgentEngine)
        assert engine._build_step_trace([]) == []


class TestBuildErrorList:
    """Tests for AgentEngine._build_error_list."""

    def test_builds_error_list_from_failures(self):
        engine = AgentEngine.__new__(AgentEngine)
        errors = [
            {
                "step": 3,
                "action": "click",
                "params": {"x": 10},
                "result": {"ok": False, "msg": "element not found"},
                "timestamp": "t1",
            }
        ]
        result = engine._build_error_list(errors)
        assert len(result) == 1
        assert result[0]["step"] == 3
        assert result[0]["error"] == "element not found"

    def test_caps_at_20_entries(self):
        engine = AgentEngine.__new__(AgentEngine)
        errors = [
            {
                "step": i,
                "action": "click",
                "params": {},
                "result": {"ok": False, "msg": "err"},
                "timestamp": f"t{i}",
            }
            for i in range(50)
        ]
        result = engine._build_error_list(errors)
        assert len(result) == 20

    def test_truncates_error_message_at_300(self):
        engine = AgentEngine.__new__(AgentEngine)
        errors = [
            {
                "step": 1,
                "action": "click",
                "params": {},
                "result": {"ok": False, "msg": "e" * 500},
                "timestamp": "t1",
            }
        ]
        result = engine._build_error_list(errors)
        assert len(result[0]["error"]) <= 300

    def test_strips_screenshots_from_params(self):
        engine = AgentEngine.__new__(AgentEngine)
        errors = [
            {
                "step": 1,
                "action": "click",
                "params": {"screenshot": "data"},
                "result": {"msg": "fail"},
                "timestamp": "t1",
            }
        ]
        result = engine._build_error_list(errors)
        assert "screenshot" not in result[0]["params"]

    def test_empty_errors_returns_empty(self):
        engine = AgentEngine.__new__(AgentEngine)
        assert engine._build_error_list([]) == []


class TestBuildReportText:
    """Tests for AgentEngine._build_report_text."""

    def _make_engine(self):
        engine = AgentEngine.__new__(AgentEngine)
        engine.step = 5
        engine.notes = ["test note 1", "test note 2"]
        engine.forensic_log = []
        return engine

    def test_basic_report_text(self):
        engine = self._make_engine()
        report = {
            "session_id": "20250101-000000",
            "started_at": "2025-01-01T00:00:00",
            "finished_at": "2025-01-01T00:00:05",
            "summary": "done",
        }
        text = engine._build_report_text(
            report,
            "test goal",
            5.0,
            True,
            [],
            "openai",
            "gpt-4",
        )
        assert "SENTINEL DESKTOP" in text
        assert "COMPLETED" in text
        assert "test goal" in text
        assert "openai / gpt-4" in text

    def test_failed_report_shows_failed_status(self):
        engine = self._make_engine()
        report = {
            "session_id": "20250101-000000",
            "started_at": "t0",
            "finished_at": "t1",
            "summary": "Run ended without completion",
        }
        text = engine._build_report_text(report, "goal", 10.0, False, [], "test", "m1")
        assert "FAILED" in text

    def test_includes_notes_section(self):
        engine = self._make_engine()
        report = {
            "session_id": "s1",
            "started_at": "t0",
            "finished_at": "t1",
            "summary": "ok",
        }
        text = engine._build_report_text(report, "g", 1.0, True, [], "p", "m")
        assert "Notes:" in text
        assert "test note 1" in text

    def test_includes_errors_section(self):
        engine = self._make_engine()
        engine.notes = []
        report = {
            "session_id": "s1",
            "started_at": "t0",
            "finished_at": "t1",
            "summary": "ok",
        }
        errors = [
            {"step": 2, "action": "click", "result": {"msg": "not found"}},
            {"step": 4, "action": "type", "result": {"msg": "timeout"}},
        ]
        text = engine._build_report_text(report, "g", 3.0, False, errors, "p", "m")
        assert "Errors:" in text
        assert "click" in text
        assert "timeout" in text

    def test_limits_notes_to_10(self):
        engine = self._make_engine()
        engine.notes = [f"note {i}" for i in range(20)]
        report = {"session_id": "s1", "started_at": "t0", "finished_at": "t1", "summary": "ok"}
        text = engine._build_report_text(report, "g", 1.0, True, [], "p", "m")
        assert "note 0" in text
        assert "note 9" in text
        assert "note 19" not in text

    def test_limits_errors_to_5(self):
        engine = self._make_engine()
        engine.notes = []
        report = {"session_id": "s1", "started_at": "t0", "finished_at": "t1", "summary": "ok"}
        errors = [{"step": i, "action": "click", "result": {"msg": f"err{i}"}} for i in range(10)]
        text = engine._build_report_text(report, "g", 1.0, False, errors, "p", "m")
        # Count how many error lines appear
        error_lines = [l for l in text.split("\n") if l.startswith("  Step ")]
        assert len(error_lines) <= 5
