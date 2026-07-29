"""Edge-case tests for core/llm_client.py — malformed responses, retries, timeouts."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.llm_client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    LLMClient,
    LLMError,
    _friendly_http_error,
    omits_sampling_params,
)


class TestFriendlyHttpError:
    def test_401_invalid_key(self):
        result = _friendly_http_error(401, "bad key")
        assert "Invalid API key" in result

    def test_403_forbidden(self):
        result = _friendly_http_error(403, "")
        assert "lacks access" in result

    def test_404_not_found(self):
        result = _friendly_http_error(404, "")
        assert "not found" in result

    def test_429_rate_limited(self):
        result = _friendly_http_error(429, "slow down")
        assert "Rate limited" in result

    def test_500_provider_error(self):
        result = _friendly_http_error(500, "internal error")
        assert "Provider error" in result

    def test_unknown_status(self):
        result = _friendly_http_error(418, "I'm a teapot")
        assert "418" in result

    def test_long_body_truncated(self):
        """Bodies longer than 240 chars should be truncated."""
        long_body = "x" * 500
        result = _friendly_http_error(500, long_body)
        assert "…" in result or len(result) < 300


class TestOmitsSamplingParams:
    def test_claude_5_prefixes(self):
        assert omits_sampling_params("claude-sonnet-5-123") is True
        assert omits_sampling_params("claude-opus-5") is True
        assert omits_sampling_params("claude-fable-5") is True
        assert omits_sampling_params("claude-mythos-5") is True

    def test_claude_4_7_8(self):
        assert omits_sampling_params("claude-opus-4-7") is True
        assert omits_sampling_params("claude-opus-4-8") is True

    def test_regular_model_does_not_omit(self):
        assert omits_sampling_params("gpt-4o") is False
        assert omits_sampling_params("claude-sonnet-4-20250514") is False
        assert omits_sampling_params("") is False


class TestLLMClientInit:
    def test_default_init(self):
        client = LLMClient()
        assert client.providers is not None
        assert len(client.providers) > 0


class TestPostWithRetry:
    def setup_method(self):
        self.client = LLMClient()

    def test_successful_post(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}

        with patch("core.llm_client.requests.post", return_value=mock_resp):
            result = self.client._post_with_retry(
                "http://test/v1/chat", {}, {}, 30,
                max_retries=0, base_delay=0, provider_label="test",
            )
        assert result["choices"][0]["message"]["content"] == "Hello"

    def test_timeout_retries(self):
        """Timeout should be retried up to max_retries."""
        with patch(
            "core.llm_client.requests.post",
            side_effect=requests.exceptions.Timeout,
        ):
            with pytest.raises(LLMError, match="Timeout"):
                self.client._post_with_retry(
                    "http://test", {}, {}, 30,
                    max_retries=2, base_delay=0, provider_label="test",
                )

    def test_connection_error_retries(self):
        """ConnectionError should be retried."""
        with patch(
            "core.llm_client.requests.post",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            with pytest.raises(LLMError, match="ConnectionError"):
                self.client._post_with_retry(
                    "http://test", {}, {}, 30,
                    max_retries=1, base_delay=0, provider_label="test",
                )

    def test_non_retriable_http_error(self):
        """HTTP 401 should NOT be retried — it fails immediately."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid key"

        with patch("core.llm_client.requests.post", return_value=mock_resp):
            with pytest.raises(LLMError, match="Invalid API key"):
                self.client._post_with_retry(
                    "http://test", {}, {}, 30,
                    max_retries=3, base_delay=0, provider_label="test",
                )

    def test_retry_status_429(self):
        """HTTP 429 should be retried, then fail with friendly message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "rate limited"

        with patch("core.llm_client.requests.post", return_value=mock_resp):
            with pytest.raises(LLMError, match="Rate limited"):
                self.client._post_with_retry(
                    "http://test", {}, {}, 30,
                    max_retries=2, base_delay=0, provider_label="test",
                )

    def test_retry_status_500(self):
        """HTTP 500 should be retried."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal error"

        with patch("core.llm_client.requests.post", return_value=mock_resp):
            with pytest.raises(LLMError, match="Provider error"):
                self.client._post_with_retry(
                    "http://test", {}, {}, 30,
                    max_retries=1, base_delay=0, provider_label="test",
                )

    def test_non_json_response_raises(self):
        """A 200 with non-JSON body should raise LLMError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not json")

        with patch("core.llm_client.requests.post", return_value=mock_resp):
            with pytest.raises(LLMError, match="non-JSON"):
                self.client._post_with_retry(
                    "http://test", {}, {}, 30,
                    max_retries=0, base_delay=0, provider_label="test",
                )


class TestParseOpenaiResponse:
    def setup_method(self):
        self.client = LLMClient()

    def test_plain_text_content(self):
        data = {"choices": [{"message": {"content": "Hello world"}}]}
        assert self.client._parse_openai_response(data, "test") == "Hello world"

    def test_empty_content_returns_empty(self):
        data = {"choices": [{"message": {"content": ""}}]}
        assert self.client._parse_openai_response(data, "test") == ""

    def test_tool_calls_return_json(self):
        data = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "click", "arguments": "{}"}}],
                },
            }],
        }
        result = self.client._parse_openai_response(data, "test")
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        assert parsed["tool_calls"][0]["function"]["name"] == "click"

    def test_content_as_list_of_blocks(self):
        data = {
            "choices": [{
                "message": {
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ],
                },
            }],
        }
        assert self.client._parse_openai_response(data, "test") == "Part 1 Part 2"

    def test_non_dict_response_raises(self):
        with pytest.raises(LLMError, match="unexpected response type"):
            self.client._parse_openai_response("not a dict", "test")

    def test_error_envelope_without_choices(self):
        data = {"error": {"message": "something went wrong", "code": 500}}
        with pytest.raises(LLMError, match="something went wrong"):
            self.client._parse_openai_response(data, "test")

    def test_error_envelope_with_string_error(self):
        data = {"error": "plain string error"}
        with pytest.raises(LLMError, match="plain string error"):
            self.client._parse_openai_response(data, "test")

    def test_no_choices_raises(self):
        data = {"choices": []}
        with pytest.raises(LLMError, match="no 'choices'"):
            self.client._parse_openai_response(data, "test")

    def test_missing_choices_key_raises(self):
        data = {"id": "resp_123"}
        with pytest.raises(LLMError, match="no 'choices'"):
            self.client._parse_openai_response(data, "test")

    def test_delta_message_format(self):
        """Some providers return 'delta' instead of 'message'."""
        data = {"choices": [{"delta": {"content": "streamed content"}}]}
        assert self.client._parse_openai_response(data, "test") == "streamed content"


class TestBuildHeaders:
    def test_standard_auth_header(self):
        config = {"auth_header": "Authorization", "auth_prefix": "Bearer "}
        headers = LLMClient._build_headers(config, "sk-test123")
        assert headers["Authorization"] == "Bearer sk-test123"
        assert headers["Content-Type"] == "application/json"

    def test_no_auth_provider(self):
        config = {"no_auth": True}
        headers = LLMClient._build_headers(config, "sk-test123")
        assert "Authorization" not in headers

    def test_empty_api_key(self):
        config = {"auth_header": "Authorization", "auth_prefix": "Bearer "}
        headers = LLMClient._build_headers(config, "")
        assert "Authorization" not in headers


class TestConvertToolsToAnthropic:
    def test_single_tool(self):
        tools = [{"type": "function", "function": {"name": "click", "description": "Click", "parameters": {"type": "object"}}}]
        result = LLMClient._convert_tools_to_anthropic(tools)
        assert result[0]["name"] == "click"
        assert result[0]["input_schema"] == {"type": "object"}
        assert "function" not in result[0]

    def test_empty_tools(self):
        assert LLMClient._convert_tools_to_anthropic([]) == []

    def test_tool_missing_parameters(self):
        tools = [{"type": "function", "function": {"name": "noop", "description": "No-op"}}]
        result = LLMClient._convert_tools_to_anthropic(tools)
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}


class TestChatUnknownProvider:
    def test_unknown_provider_raises(self):
        client = LLMClient()
        with pytest.raises(ValueError, match="Unknown provider"):
            client.chat(provider="nonexistent_provider_xyz", api_key="k", model="m", messages=[])
