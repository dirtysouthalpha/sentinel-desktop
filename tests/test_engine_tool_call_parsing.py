"""Tests for AgentEngine._action_from_tool_call edge cases."""

from core.engine import AgentEngine


def _from_tool_call(tool_calls):
    return AgentEngine._action_from_tool_call(tool_calls)


class TestActionFromToolCallEdgeCases:
    def test_none_input(self):
        assert _from_tool_call(None) is None

    def test_empty_list(self):
        assert _from_tool_call([]) is None

    def test_string_instead_of_list(self):
        assert _from_tool_call("not a list") is None

    def test_first_element_not_dict(self):
        assert _from_tool_call(["string_element"]) is None

    def test_no_function_key(self):
        assert _from_tool_call([{}]) is None

    def test_function_not_dict(self):
        assert _from_tool_call([{"function": "not_a_dict"}]) is None

    def test_name_from_call_level(self):
        result = _from_tool_call([{"name": "click", "input": {"x": 100}}])
        assert result == {"action": "click", "x": 100}

    def test_arguments_as_dict(self):
        result = _from_tool_call(
            [{"function": {"name": "type_text", "arguments": {"text": "hello"}}}]
        )
        assert result == {"action": "type_text", "text": "hello"}

    def test_arguments_as_json_string(self):
        import json

        result = _from_tool_call(
            [
                {
                    "function": {
                        "name": "hotkey",
                        "arguments": json.dumps({"keys": ["ctrl", "c"]}),
                    }
                }
            ]
        )
        assert result == {"action": "hotkey", "keys": ["ctrl", "c"]}

    def test_arguments_as_empty_string(self):
        result = _from_tool_call([{"function": {"name": "screenshot", "arguments": ""}}])
        assert result == {"action": "screenshot"}

    def test_arguments_as_invalid_json_string(self):
        result = _from_tool_call([{"function": {"name": "screenshot", "arguments": "{broken"}}])
        assert result == {"action": "screenshot"}

    def test_input_key_fallback(self):
        result = _from_tool_call([{"name": "click", "input": {"x": 50, "y": 75}}])
        assert result == {"action": "click", "x": 50, "y": 75}

    def test_input_not_dict_returns_action_only(self):
        result = _from_tool_call([{"name": "click", "input": "bad"}])
        assert result == {"action": "click"}

    def test_action_key_in_args_is_stripped(self):
        result = _from_tool_call(
            [{"function": {"name": "click", "arguments": {"action": "click", "x": 1}}}]
        )
        assert result == {"action": "click", "x": 1}

    def test_no_name_returns_none(self):
        assert _from_tool_call([{"function": {"arguments": {"x": 1}}}]) is None
