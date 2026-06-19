"""Tests for core/llm_client.py — chat paths, retry logic, Anthropic path."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.llm_client import LLMClient, LLMError


def _make_response(status_code: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text or (json.dumps(json_body) if json_body else "")
    resp.json.return_value = json_body or {}
    return resp


class TestChatOpenAIPath:
    @patch("core.llm_client.requests.post")
    def test_basic_text_response(self, mock_post):
        mock_post.return_value = _make_response(
            200, {"choices": [{"message": {"content": "Hello from GPT!"}}]}
        )
        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])
        assert result == "Hello from GPT!"
        mock_post.assert_called_once()

    @patch("core.llm_client.requests.post")
    def test_tool_calls_returned_as_json(self, mock_post):
        tool_calls = [
            {
                "id": "tc1",
                "type": "function",
                "function": {"name": "click", "arguments": '{"x": 100}'},
            }
        ]
        mock_post.return_value = _make_response(
            200, {"choices": [{"message": {"tool_calls": tool_calls}}]}
        )
        client = LLMClient()
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "Click"}],
            tools=[{"type": "function", "function": {"name": "click"}}],
        )
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        assert parsed["tool_calls"][0]["function"]["name"] == "click"

    @patch("core.llm_client.requests.post")
    def test_empty_choices_raises_llmerror(self, mock_post):
        mock_post.return_value = _make_response(200, {"choices": []})
        client = LLMClient()
        with pytest.raises(LLMError, match="no 'choices'"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])

    @patch("core.llm_client.requests.post")
    def test_error_envelope_raises_llmerror(self, mock_post):
        mock_post.return_value = _make_response(200, {"error": {"message": "model overloaded"}})
        client = LLMClient()
        with pytest.raises(LLMError, match="model overloaded"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])

    @patch("core.llm_client.requests.post")
    def test_content_as_list_of_blocks(self, mock_post):
        mock_post.return_value = _make_response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "Part 1"},
                                {"type": "text", "text": "Part 2"},
                            ]
                        }
                    }
                ]
            },
        )
        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])
        assert "Part 1" in result
        assert "Part 2" in result

    @patch("core.llm_client.requests.post")
    def test_non_dict_response_raises_llmerror(self, mock_post):
        mock_post.return_value = _make_response(200)
        mock_post.return_value.json.return_value = "not a dict"
        client = LLMClient()
        with pytest.raises(LLMError, match="unexpected response type"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])


class TestChatRetryLogic:
    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    def test_retries_on_429_then_succeeds(self, mock_post, mock_sleep):
        # First call: 429, second call: 200
        mock_post.side_effect = [
            _make_response(429, text="rate limited"),
            _make_response(200, {"choices": [{"message": {"content": "OK"}}]}),
        ]
        client = LLMClient()
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
            retry_base_delay=0.01,
        )
        assert result == "OK"
        assert mock_post.call_count == 2

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    def test_retries_exhausted_raises_llmerror(self, mock_post, mock_sleep):
        mock_post.return_value = _make_response(429, text="rate limited")
        client = LLMClient()
        with pytest.raises(LLMError, match="Rate limited"):
            client.chat(
                "openai",
                "sk-test",
                "gpt-4o",
                [{"role": "user", "content": "Hi"}],
                max_retries=1,
                retry_base_delay=0.01,
            )
        assert mock_post.call_count == 2  # initial + 1 retry

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    def test_retries_on_connection_error(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("conn refused"),
            _make_response(200, {"choices": [{"message": {"content": "recovered"}}]}),
        ]
        client = LLMClient()
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
            retry_base_delay=0.01,
        )
        assert result == "recovered"

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    def test_retries_on_timeout(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.exceptions.Timeout("timed out"),
            _make_response(200, {"choices": [{"message": {"content": "back"}}]}),
        ]
        client = LLMClient()
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
            retry_base_delay=0.01,
        )
        assert result == "back"

    @patch("core.llm_client.requests.post")
    def test_non_retriable_401_raises_immediately(self, mock_post):
        mock_post.return_value = _make_response(401, text="bad key")
        client = LLMClient()
        with pytest.raises(LLMError, match="API key"):
            client.chat(
                "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}], max_retries=3
            )
        assert mock_post.call_count == 1


class TestChatAnthropicPath:
    @patch("core.llm_client.requests.post")
    def test_anthropic_text_response(self, mock_post):
        mock_post.return_value = _make_response(
            200, {"content": [{"type": "text", "text": "Hello from Claude!"}]}
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-sonnet-4-6",
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
            ],
        )
        assert result == "Hello from Claude!"

    @patch("core.llm_client.requests.post")
    def test_anthropic_tool_use(self, mock_post):
        mock_post.return_value = _make_response(
            200,
            {
                "content": [
                    {"type": "text", "text": "I'll click for you."},
                    {
                        "type": "tool_use",
                        "id": "tu1",
                        "name": "computer",
                        "input": {"action": "click", "coordinate": [100, 200]},
                    },
                ]
            },
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-sonnet-4-6",
            [{"role": "user", "content": "Click"}],
            tools=[{"type": "function", "function": {"name": "click"}}],
        )
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        assert parsed["tool_calls"][0]["function"]["name"] == "click"

    @patch("core.llm_client.requests.post")
    def test_anthropic_system_prompt_extraction(self, mock_post):
        mock_post.return_value = _make_response(200, {"content": [{"type": "text", "text": "ok"}]})
        client = LLMClient()
        client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-sonnet-4-6",
            [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Hi"},
            ],
        )
        # Verify system prompt was extracted into the payload
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["system"] == "Be concise."


class TestVisionMessageConstruction:
    """Vision-message construction (v18: chat_with_vision removed; the engine
    builds vision messages via _make_vision_message + chat)."""

    @patch("core.llm_client.requests.post")
    def test_vision_message_appends_image(self, mock_post):
        mock_post.return_value = _make_response(
            200, {"choices": [{"message": {"content": "I see a screenshot"}}]}
        )
        client = LLMClient()
        vision_msg = client._make_vision_message(
            "openai", "iVBORabcd1234", "Describe this screenshot."
        )
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "What do you see?"}, vision_msg],
        )
        assert result == "I see a screenshot"
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        # The last message should be the vision message with image_url
        last_msg = payload["messages"][-1]
        assert last_msg["role"] == "user"
        assert any("image_url" in str(b) for b in last_msg["content"])
