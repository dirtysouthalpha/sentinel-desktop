"""Tests for core/llm_client.py -- LLM API calls, retry, and response parsing."""

import json

# Mock Windows-only modules before import
import sys
from unittest.mock import MagicMock

import pytest

for mod in [
    "pyautogui",
    "uiautomation",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "pytesseract",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from core.llm_client import RETRY_STATUSES, LLMClient


class TestLLMClientInit:
    """Test LLMClient initialization."""

    def test_init_no_args(self):
        client = LLMClient()
        assert client.providers is not None

    def test_providers_catalog_accessible(self):
        client = LLMClient()
        # Should have at least the major providers
        for p in ["openai", "anthropic", "google", "deepseek", "groq"]:
            assert p in client.providers, f"Provider '{p}' missing from catalog"


class TestBuildMessages:
    """Test message structure handling."""

    def test_basic_messages_structure(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["content"] == "Hello"

    def test_vision_message_format(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What do you see?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC123"}},
                ],
            },
        ]
        assert messages[0]["content"][1]["type"] == "image_url"
        assert "base64" in messages[0]["content"][1]["image_url"]["url"]

    def test_tool_result_message(self):
        messages = [
            {"role": "tool", "tool_call_id": "tc_123", "content": json.dumps({"success": True})},
        ]
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "tc_123"


class TestResponseParsing:
    """Test parsing of LLM responses in different formats."""

    def test_parse_openai_tool_call(self):
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "click",
                                    "arguments": json.dumps({"x": 100, "y": 200}),
                                }
                            }
                        ]
                    }
                }
            ]
        }
        tc = response["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "click"
        args = json.loads(tc["function"]["arguments"])
        assert args["x"] == 100

    def test_parse_anthropic_tool_use(self):
        response = {
            "content": [
                {"type": "text", "text": "I'll click that button."},
                {"type": "tool_use", "name": "click", "input": {"x": 150, "y": 250}},
            ],
            "stop_reason": "tool_use",
        }
        tool_block = [b for b in response["content"] if b["type"] == "tool_use"][0]
        assert tool_block["name"] == "click"
        assert tool_block["input"]["x"] == 150

    def test_parse_plain_json_response(self):
        text = '{"action": "click", "x": 300, "y": 400}'
        parsed = json.loads(text)
        assert parsed["action"] == "click"

    def test_parse_json_in_markdown_fence(self):
        text = '```json\n{"action": "type_text", "text": "hello"}\n```'
        stripped = text.strip().removeprefix("```json\n").removesuffix("\n```").strip()
        parsed = json.loads(stripped)
        assert parsed["action"] == "type_text"

    def test_parse_nested_json(self):
        text = '{"action": "note", "text": "Found user: {\\"name\\": \\"John\\"}"}'
        parsed = json.loads(text)
        assert "John" in parsed["text"]


class TestRetryStatusCodes:
    """Test retry eligibility for HTTP status codes."""

    def test_retry_on_429(self):
        assert 429 in RETRY_STATUSES

    def test_retry_on_500(self):
        assert 500 in RETRY_STATUSES

    def test_retry_on_502(self):
        assert 502 in RETRY_STATUSES

    def test_retry_on_503(self):
        assert 503 in RETRY_STATUSES

    def test_no_retry_on_401(self):
        assert 401 not in RETRY_STATUSES

    def test_no_retry_on_403(self):
        assert 403 not in RETRY_STATUSES

    def test_no_retry_on_404(self):
        assert 404 not in RETRY_STATUSES

    def test_no_retry_on_200(self):
        assert 200 not in RETRY_STATUSES


class TestChatValidation:
    """Test chat() input validation."""

    def test_unknown_provider_raises(self):
        client = LLMClient()
        with pytest.raises(ValueError, match="Unknown provider"):
            client.chat(
                provider="nonexistent_provider",
                api_key="key",
                model="model",
                messages=[{"role": "user", "content": "hi"}],
            )


class TestFriendlyErrors:
    """Test error message formatting."""

    def test_401_message(self):
        from core.llm_client import _friendly_http_error

        msg = _friendly_http_error(401, "")
        assert "API key" in msg

    def test_404_message(self):
        from core.llm_client import _friendly_http_error

        msg = _friendly_http_error(404, "")
        assert "not found" in msg.lower() or "model" in msg.lower()

    def test_429_message(self):
        from core.llm_client import _friendly_http_error

        msg = _friendly_http_error(429, "slow down")
        assert "rate" in msg.lower() or "limit" in msg.lower()

    def test_500_message(self):
        from core.llm_client import _friendly_http_error

        msg = _friendly_http_error(500, "internal error")
        assert "500" in msg or "Provider error" in msg


# ---------------------------------------------------------------------------
# Edge cases — response parsing
# ---------------------------------------------------------------------------


class TestParseOpenAIResponseEdgeCases:
    """Edge cases for _parse_openai_response."""

    def test_non_dict_response_raises(self):
        from core.llm_client import LLMClient, LLMError

        with pytest.raises(LLMError, match="unexpected response type"):
            LLMClient._parse_openai_response(["not", "a", "dict"], "testprovider")

    def test_error_envelope_without_choices_raises(self):
        from core.llm_client import LLMClient, LLMError

        data = {"error": {"message": "quota exceeded", "code": "quota_exceeded"}}
        with pytest.raises(LLMError, match="quota exceeded"):
            LLMClient._parse_openai_response(data, "testprovider")

    def test_empty_choices_raises(self):
        from core.llm_client import LLMClient, LLMError

        with pytest.raises(LLMError, match="no 'choices'"):
            LLMClient._parse_openai_response({"choices": []}, "testprovider")

    def test_multiple_tool_calls_in_response(self):
        """All tool calls in the response must be preserved in the returned JSON."""
        from core.llm_client import LLMClient

        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "click", "arguments": "{}"}},
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "type_text", "arguments": '{"text": "hi"}'},
            },
        ]
        data = {"choices": [{"message": {"tool_calls": tool_calls}}]}
        result = LLMClient._parse_openai_response(data, "testprovider")
        parsed = json.loads(result)
        assert len(parsed["tool_calls"]) == 2
        assert parsed["tool_calls"][0]["id"] == "call_1"
        assert parsed["tool_calls"][1]["id"] == "call_2"

    def test_content_as_list_of_blocks_joined(self):
        """Content returned as a list of text blocks should be space-joined."""
        from core.llm_client import LLMClient

        data = {"choices": [{"message": {"content": [{"text": "hello"}, {"text": "world"}]}}]}
        result = LLMClient._parse_openai_response(data, "testprovider")
        assert "hello" in result and "world" in result

    def test_null_message_returns_empty_string(self):
        """A choice with null/missing message should return empty string, not raise."""
        from core.llm_client import LLMClient

        data = {"choices": [{"message": None}]}
        result = LLMClient._parse_openai_response(data, "testprovider")
        assert result == ""


class TestParseAnthropicResponseEdgeCases:
    """Edge cases for _parse_anthropic_response."""

    def test_multiple_tool_use_blocks_preserved(self):
        """Multiple tool_use blocks must all appear in the normalised output."""
        from core.llm_client import LLMClient

        data = {
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "click", "input": {"x": 10, "y": 20}},
                {"type": "tool_use", "id": "tu_2", "name": "type_text", "input": {"text": "hi"}},
            ]
        }
        result = LLMClient._parse_anthropic_response(data)
        parsed = json.loads(result)
        assert len(parsed["tool_calls"]) == 2
        names = {tc["function"]["name"] for tc in parsed["tool_calls"]}
        assert names == {"click", "type_text"}

    def test_mixed_text_and_tool_blocks_returns_tool_calls(self):
        """When tool_use blocks are present, tool calls win over text blocks."""
        from core.llm_client import LLMClient

        data = {
            "content": [
                {"type": "text", "text": "I will click now."},
                {"type": "tool_use", "id": "tu_1", "name": "click", "input": {}},
            ]
        }
        result = LLMClient._parse_anthropic_response(data)
        parsed = json.loads(result)
        assert "tool_calls" in parsed

    def test_empty_content_returns_empty_string(self):
        from core.llm_client import LLMClient

        result = LLMClient._parse_anthropic_response({"content": []})
        assert result == ""
