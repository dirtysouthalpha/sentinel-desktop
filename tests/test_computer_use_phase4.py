"""Tests for Phase 4: Native Computer-Use Adapters — Anthropic + OpenAI tool formats."""

import json

from core.computer_use import (
    _parse_anthropic_key,
    _parse_scroll_direction,
    build_anthropic_tools,
    build_openai_tools,
    get_computer_use_type,
    translate_anthropic_action,
    translate_openai_action,
)

# ---------------------------------------------------------------------------
# Provider capability detection (NCU-01, NCU-02)
# ---------------------------------------------------------------------------


class TestProviderCapability:
    """Test provider computer-use capability detection."""

    def test_anthropic_supports_computer_use(self):
        assert get_computer_use_type("anthropic") == "anthropic"

    def test_openai_supports_computer_use(self):
        assert get_computer_use_type("openai") == "openai"

    def test_other_providers_no_computer_use(self):
        assert get_computer_use_type("google") is None
        assert get_computer_use_type("deepseek") is None
        assert get_computer_use_type("xai") is None

    def test_unknown_provider(self):
        assert get_computer_use_type("nonexistent_provider") is None


# ---------------------------------------------------------------------------
# Anthropic tool building (NCU-01)
# ---------------------------------------------------------------------------


class TestAnthropicTools:
    """Test Anthropic native computer tool building."""

    def test_builds_computer_tool(self):
        tools = build_anthropic_tools()
        assert len(tools) >= 1
        assert tools[0]["type"] == "computer_20250124"
        assert tools[0]["name"] == "computer"

    def test_display_dimensions(self):
        tools = build_anthropic_tools(display_width=2560, display_height=1440)
        assert tools[0]["display_width_px"] == 2560
        assert tools[0]["display_height_px"] == 1440

    def test_includes_text_editor_with_standard_tools(self):
        standard = [{"type": "function", "function": {"name": "type_text"}}]
        tools = build_anthropic_tools(standard_tools=standard)
        # Should have computer tool + text editor
        types = [t["type"] for t in tools]
        assert "computer_20250124" in types


# ---------------------------------------------------------------------------
# OpenAI tool building (NCU-02)
# ---------------------------------------------------------------------------


class TestOpenAITools:
    """Test OpenAI native computer tool building."""

    def test_builds_computer_tool(self):
        tools = build_openai_tools()
        assert len(tools) >= 1
        assert tools[0]["type"] == "computer_use_preview"

    def test_display_dimensions(self):
        tools = build_openai_tools(display_width=2560, display_height=1440)
        assert tools[0]["display_width"] == 2560
        assert tools[0]["display_height"] == 1440

    def test_includes_standard_tools_as_fallback(self):
        standard = [
            {"type": "function", "function": {"name": "type_text"}},
            {"type": "function", "function": {"name": "press_key"}},
        ]
        tools = build_openai_tools(standard_tools=standard)
        # Should have computer tool + standard tools
        assert len(tools) >= 3
        assert tools[0]["type"] == "computer_use_preview"


# ---------------------------------------------------------------------------
# Anthropic action translation (NCU-01)
# ---------------------------------------------------------------------------


class TestAnthropicActionTranslation:
    """Test Anthropic computer tool action → our action format."""

    def _computer_block(self, action: str, **kwargs) -> dict:
        """Create a mock Anthropic computer tool_use block."""
        return {
            "type": "tool_use",
            "id": "cu_123",
            "name": "computer",
            "input": {"action": action, **kwargs},
        }

    def test_click(self):
        block = self._computer_block("click", coordinate=[500, 300])
        action = translate_anthropic_action(block)
        assert action is not None
        assert action["action"] == "click"
        assert action["x"] == 500
        assert action["y"] == 300

    def test_right_click(self):
        block = self._computer_block("right_click", coordinate=[500, 300])
        action = translate_anthropic_action(block)
        assert action["action"] == "right_click"

    def test_double_click(self):
        block = self._computer_block("double_click", coordinate=[500, 300])
        action = translate_anthropic_action(block)
        assert action["action"] == "double_click"

    def test_type(self):
        block = self._computer_block("type", text="Hello World")
        action = translate_anthropic_action(block)
        assert action["action"] == "type_text"
        assert action["text"] == "Hello World"

    def test_key(self):
        block = self._computer_block("key", text="ctrl+c")
        action = translate_anthropic_action(block)
        assert action["action"] == "hotkey"
        assert action["keys"] == ["ctrl", "c"]

    def test_screenshot(self):
        block = self._computer_block("screenshot")
        action = translate_anthropic_action(block)
        assert action["action"] == "screenshot"

    def test_mouse_move(self):
        block = self._computer_block("mouse_move", coordinate=[100, 200])
        action = translate_anthropic_action(block)
        assert action["action"] == "mouse_move"
        assert action["x"] == 100
        assert action["y"] == 200

    def test_scroll(self):
        block = self._computer_block("scroll", direction="down", amount=3)
        action = translate_anthropic_action(block)
        assert action["action"] == "scroll"
        assert action["amount"] == 3

    def test_scroll_up(self):
        block = self._computer_block("scroll", direction="up", amount=5)
        action = translate_anthropic_action(block)
        assert action["amount"] == -5

    def test_drag(self):
        block = self._computer_block(
            "left_click_drag",
            start_coordinate=[100, 200],
            coordinate=[300, 400],
        )
        action = translate_anthropic_action(block)
        assert action["action"] == "drag"
        assert action["from_x"] == 100
        assert action["from_y"] == 200
        assert action["to_x"] == 300
        assert action["to_y"] == 400

    def test_non_computer_tool_returns_none(self):
        block = {"type": "tool_use", "id": "tu_123", "name": "some_other_tool", "input": {}}
        assert translate_anthropic_action(block) is None

    def test_non_tool_use_returns_none(self):
        block = {"type": "text", "text": "I see the screen"}
        assert translate_anthropic_action(block) is None

    def test_unknown_action_passthrough(self):
        block = self._computer_block("custom_action", foo="bar")
        action = translate_anthropic_action(block)
        assert action is not None
        assert action["action"] == "custom_action"


# ---------------------------------------------------------------------------
# OpenAI action translation (NCU-02)
# ---------------------------------------------------------------------------


class TestOpenAIActionTranslation:
    """Test OpenAI computer tool action → our action format."""

    def _computer_call(self, action: str, **kwargs) -> dict:
        """Create a mock OpenAI computer_use_preview tool call."""
        return {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "computer_use_preview",
                "arguments": json.dumps({"action": action, **kwargs}),
            },
        }

    def test_click(self):
        call = self._computer_call("click", coordinate=[500, 300])
        action = translate_openai_action(call)
        assert action is not None
        assert action["action"] == "click"
        assert action["x"] == 500
        assert action["y"] == 300

    def test_right_click(self):
        call = self._computer_call("right_click", coordinate=[500, 300])
        action = translate_openai_action(call)
        assert action["action"] == "right_click"

    def test_type(self):
        call = self._computer_call("type", text="Hello")
        action = translate_openai_action(call)
        assert action["action"] == "type_text"
        assert action["text"] == "Hello"

    def test_screenshot(self):
        call = self._computer_call("screenshot")
        action = translate_openai_action(call)
        assert action["action"] == "screenshot"

    def test_standard_function_call_passthrough(self):
        """Standard function calls (not computer_use_preview) pass through."""
        call = {
            "id": "call_456",
            "type": "function",
            "function": {
                "name": "click",
                "arguments": json.dumps({"x": 500, "y": 300}),
            },
        }
        action = translate_openai_action(call)
        assert action is not None
        assert action["action"] == "click"
        assert action["x"] == 500

    def test_invalid_arguments_returns_none(self):
        call = {
            "id": "call_789",
            "type": "function",
            "function": {
                "name": "computer_use_preview",
                "arguments": "not json{{{",
            },
        }
        assert translate_openai_action(call) is None


# ---------------------------------------------------------------------------
# Key parsing helpers
# ---------------------------------------------------------------------------


class TestKeyParsing:
    """Test key string parsing for hotkey translation."""

    def test_single_key(self):
        assert _parse_anthropic_key("enter") == ["enter"]

    def test_combo(self):
        assert _parse_anthropic_key("ctrl+c") == ["ctrl", "c"]

    def test_triple_combo(self):
        assert _parse_anthropic_key("ctrl+shift+s") == ["ctrl", "shift", "s"]

    def test_empty_defaults_to_enter(self):
        assert _parse_anthropic_key("") == ["enter"]

    def test_return_mapped_to_enter(self):
        assert _parse_anthropic_key("return") == ["enter"]

    def test_case_insensitive(self):
        result = _parse_anthropic_key("Ctrl+C")
        assert result == ["ctrl", "c"]


class TestScrollDirection:
    """Test scroll direction parsing."""

    def test_down(self):
        assert _parse_scroll_direction("down", 3) == 3

    def test_up(self):
        assert _parse_scroll_direction("up", 3) == -3

    def test_default_amount(self):
        assert _parse_scroll_direction("down") == 1


# ---------------------------------------------------------------------------
# LLM client integration (NCU-03 — JSON fallback)
# ---------------------------------------------------------------------------


class TestLLMClientComputerUse:
    """Test LLM client routes correctly for computer-use providers."""

    def test_client_routes_anthropic_with_computer_use(self):
        """Anthropic provider gets computer-use tools when available."""
        from core.llm_client import LLMClient

        client = LLMClient()
        # Verify Anthropic is flagged with computer_use
        config = client.providers.get("anthropic", {})
        assert config.get("computer_use") == "anthropic"

    def test_client_routes_openai_with_computer_use(self):
        """OpenAI provider gets computer-use tools when available."""
        from core.llm_client import LLMClient

        client = LLMClient()
        config = client.providers.get("openai", {})
        assert config.get("computer_use") == "openai"

    def test_other_providers_no_computer_use(self):
        """Non-computer-use providers don't have the flag."""
        from core.llm_client import LLMClient

        client = LLMClient()
        for provider in ["google", "deepseek", "xai", "ollama"]:
            config = client.providers.get(provider, {})
            assert config.get("computer_use") is None

    def test_anthropic_computer_response_parsing(self):
        """Anthropic computer-use response gets translated to our action format."""
        from core.llm_client import LLMClient

        client = LLMClient()
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "cu_abc",
                    "name": "computer",
                    "input": {"action": "click", "coordinate": [500, 300]},
                },
            ]
        }
        result = client._parse_anthropic_computer_response(response)
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        assert len(parsed["tool_calls"]) == 1
        assert parsed["tool_calls"][0]["function"]["name"] == "click"

    def test_anthropic_standard_response_unchanged(self):
        """Non-computer-use Anthropic responses parse normally."""
        from core.llm_client import LLMClient

        client = LLMClient()
        response = {
            "content": [
                {"type": "text", "text": "I see a Save button."},
            ]
        }
        result = client._parse_anthropic_response(response)
        assert result == "I see a Save button."


# ---------------------------------------------------------------------------
# mouse_move action registration
# ---------------------------------------------------------------------------


class TestMouseMoveAction:
    """Test mouse_move action in executor."""

    def test_mouse_move_registered(self):
        from core.action_executor import ActionExecutor

        assert "mouse_move" in ActionExecutor._dispatch_table
