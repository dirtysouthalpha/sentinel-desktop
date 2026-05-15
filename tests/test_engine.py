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
        payload = json.dumps({
            "tool_calls": [
                {
                    "function": {
                        "name": "click",
                        "arguments": '{"x": 50, "y": 60}',
                    }
                }
            ]
        })
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
        tool_calls = [
            {"function": {"name": "click", "arguments": '{"x": 10, "y": 20}'}}
        ]
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
        tool_calls = [
            {"function": {"name": "click", "arguments": '{"action":"click","x":1}'}}
        ]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result == {"action": "click", "x": 1}

    def test_invalid_json_arguments(self):
        tool_calls = [
            {"function": {"name": "click", "arguments": "not json{{{"}}
        ]
        result = AgentEngine._action_from_tool_call(tool_calls)
        assert result is not None
        assert result["action"] == "click"
