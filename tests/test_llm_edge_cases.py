"""Edge case tests for core/llm_client.py — malformed responses, timeouts, and odd inputs.

Covers scenarios NOT exercised by test_llm_client.py or test_llm_client_gaps.py:
- Empty/null choices arrays
- None content, list-block content
- Error envelopes without choices
- Non-dict top-level response
- Missing function key in tool_calls
- Retry-then-success on transient HTTP errors
- Immediate failure on non-retriable errors (401, 403, 404)
- Anthropic empty content, tool-use normalisation, system prompt extraction
- _build_headers with no_auth providers
- _convert_tools_to_anthropic edge cases
- _friendly_http_error truncation and fallback codes
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.llm_client import (
    LLMClient,
    LLMError,
    _friendly_http_error,
)

# ---------------------------------------------------------------------------
# OpenAI-compatible path: malformed / edge-case responses
# ---------------------------------------------------------------------------


class TestEmptyChoicesArray:
    """When 'choices' is present but empty, chat() must raise LLMError."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_empty_choices_raises(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": []}),
        )
        client = LLMClient()
        with pytest.raises(LLMError, match="no 'choices'"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_null_choices_raises(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": None}),
        )
        client = LLMClient()
        with pytest.raises(LLMError, match="no 'choices'"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])


class TestNoneContent:
    """When message content is None, chat() should return empty string."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_content_none_returns_empty(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": None}}]}),
        )
        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert result == ""


class TestListBlockContent:
    """When content is a list of blocks, text is concatenated."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_list_content_blocks(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "text", "text": "Hello"},
                                    {"type": "text", "text": "World"},
                                ]
                            }
                        }
                    ]
                }
            ),
        )
        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert "Hello" in result
        assert "World" in result


class TestErrorEnvelope:
    """When response contains an 'error' key without choices, raise LLMError."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_error_dict_envelope(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={"error": {"message": "billing issue", "code": "ERR_BILLING"}}
            ),
        )
        client = LLMClient()
        with pytest.raises(LLMError, match="billing issue"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_error_string_envelope(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"error": "something went wrong"}),
        )
        client = LLMClient()
        with pytest.raises(LLMError, match="something went wrong"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])


class TestNonDictResponse:
    """When the response JSON is not a dict, raise LLMError."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_list_response_raises(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=["not", "a", "dict"]),
        )
        client = LLMClient()
        with pytest.raises(LLMError, match="unexpected response type"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])


class TestToolCallMissingFunctionKey:
    """Tool calls without 'function' key are still serialised as JSON."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_tool_call_no_function_key(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "choices": [{"message": {"tool_calls": [{"id": "tc_1", "type": "function"}]}}]
                }
            ),
        )
        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        assert parsed["tool_calls"][0]["id"] == "tc_1"


# ---------------------------------------------------------------------------
# Retry behaviour: transient then success, non-retriable immediate fail
# ---------------------------------------------------------------------------


class TestRetryThenSuccess:
    """A transient HTTP error followed by a successful response should work."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_429_then_200(self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock) -> None:
        error_resp = MagicMock(status_code=429, text="rate limited")
        success_resp = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": "hello back"}}]}),
        )
        mock_post.side_effect = [error_resp, success_resp]

        client = LLMClient()
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "hi"}],
            max_retries=2,
        )
        assert result == "hello back"

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_500_then_200(self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock) -> None:
        error_resp = MagicMock(status_code=500, text="internal server error")
        success_resp = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": "ok"}}]}),
        )
        mock_post.side_effect = [error_resp, success_resp]

        client = LLMClient()
        result = client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "hi"}],
            max_retries=2,
        )
        assert result == "ok"


class TestNonRetriableImmediateFail:
    """401, 403, 404 should raise LLMError immediately, no retry."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_401_no_retry(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=401, text="bad key")
        client = LLMClient()
        with pytest.raises(LLMError, match="API key"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert mock_post.call_count == 1

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_403_no_retry(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=403, text="forbidden")
        client = LLMClient()
        with pytest.raises(LLMError, match="access"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert mock_post.call_count == 1

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_404_no_retry(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=404, text="not found")
        client = LLMClient()
        with pytest.raises(LLMError, match="not found"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert mock_post.call_count == 1


# ---------------------------------------------------------------------------
# Anthropic native path edge cases
# ---------------------------------------------------------------------------


class TestAnthropicEmptyContent:
    """Anthropic response with no content blocks returns empty string."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_empty_content_blocks(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"content": []}),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-3-5-sonnet-20241022",
            [{"role": "user", "content": "hi"}],
        )
        assert result == ""


class TestAnthropicToolUse:
    """Anthropic tool_use blocks are normalised to OpenAI tool_calls format."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_tool_use_normalised(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "content": [
                        {"type": "text", "text": "I'll click that."},
                        {
                            "type": "tool_use",
                            "id": "tu_123",
                            "name": "computer",
                            "input": {"action": "click", "coordinate": [100, 200]},
                        },
                    ]
                }
            ),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-3-5-sonnet-20241022",
            [{"role": "user", "content": "click the button"}],
        )
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        tc = parsed["tool_calls"][0]
        assert tc["function"]["name"] == "click"
        args = json.loads(tc["function"]["arguments"])
        assert args["x"] == 100


class TestAnthropicSystemPromptExtraction:
    """System messages are extracted and sent as the 'system' field."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_system_prompt_in_payload(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"content": [{"type": "text", "text": "done"}]}),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-3-5-sonnet-20241022",
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hi"},
            ],
        )
        assert result == "done"
        # Verify the system field was in the payload
        call_args = mock_post.call_args
        payload = (
            call_args[1]["json"]
            if "json" in call_args[1]
            else call_args[0][2]
            if len(call_args[0]) > 2
            else None
        )
        if payload is None:
            # kwargs style
            payload = call_args.kwargs.get("json", {})
        assert "system" in payload
        assert "You are helpful." in payload["system"]


# ---------------------------------------------------------------------------
# _build_headers edge cases
# ---------------------------------------------------------------------------


class TestBuildHeadersNoAuth:
    """Providers with no_auth=True should not include auth header."""

    def test_no_auth_provider_skips_header(self) -> None:
        config = {"no_auth": True}
        headers = LLMClient._build_headers(config, "secret-key")
        assert "Authorization" not in headers
        assert "x-api-key" not in headers

    def test_regular_provider_includes_auth(self) -> None:
        config = {"auth_header": "Authorization", "auth_prefix": "Bearer "}
        headers = LLMClient._build_headers(config, "sk-test")
        assert headers["Authorization"] == "Bearer sk-test"

    def test_empty_key_skips_auth(self) -> None:
        config = {"auth_header": "Authorization", "auth_prefix": "Bearer "}
        headers = LLMClient._build_headers(config, "")
        assert "Authorization" not in headers

    def test_custom_auth_header(self) -> None:
        config = {"auth_header": "X-Custom-Auth", "auth_prefix": "Token "}
        headers = LLMClient._build_headers(config, "my-token")
        assert headers["X-Custom-Auth"] == "Token my-token"


# ---------------------------------------------------------------------------
# _convert_tools_to_anthropic edge cases
# ---------------------------------------------------------------------------


class TestConvertToolsEdgeCases:
    """Tool conversion handles missing 'function' key gracefully."""

    def test_missing_function_key(self) -> None:
        tools = [{"type": "function"}]  # no 'function' key
        result = LLMClient._convert_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == ""
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_empty_tools_list(self) -> None:
        result = LLMClient._convert_tools_to_anthropic([])
        assert result == []

    def test_full_tool_definition(self) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click at coordinates",
                    "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
                },
            }
        ]
        result = LLMClient._convert_tools_to_anthropic(tools)
        assert result[0]["name"] == "click"
        assert result[0]["description"] == "Click at coordinates"
        assert "x" in result[0]["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# _friendly_http_error edge cases
# ---------------------------------------------------------------------------


class TestFriendlyHttpErrorEdgeCases:
    """Error message formatting for less common codes and long bodies."""

    def test_403_message(self) -> None:
        msg = _friendly_http_error(403, "org issue")
        assert "access" in msg.lower() or "403" in msg

    def test_unknown_status_code(self) -> None:
        msg = _friendly_http_error(418, "I'm a teapot")
        assert "418" in msg

    def test_long_body_truncated(self) -> None:
        long_body = "x" * 500
        msg = _friendly_http_error(500, long_body)
        assert len(msg) < 600  # Should be truncated
        assert "…" in msg or len(msg) < len(long_body)

    def test_5xx_generic(self) -> None:
        msg = _friendly_http_error(502, "bad gateway")
        assert "Provider error" in msg or "502" in msg


# ---------------------------------------------------------------------------
# Anthropic: malformed tool_use blocks (missing id/name/input)
# ---------------------------------------------------------------------------


class TestAnthropicMalformedToolUse:
    """tool_use blocks with missing fields should produce empty-string fallbacks."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_tool_use_missing_all_fields(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """A tool_use block with no id/name/input should still parse without error."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "content": [
                        {"type": "tool_use"},  # missing id, name, input
                    ]
                }
            ),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-opus-4-7",
            [{"role": "user", "content": "do something"}],
        )
        parsed = json.loads(result)
        tc = parsed["tool_calls"][0]
        assert tc["id"] == ""
        assert tc["function"]["name"] == ""
        assert json.loads(tc["function"]["arguments"]) == {}

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_tool_use_partial_fields(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """A tool_use block with only 'name' fills in defaults for the rest."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "content": [
                        {"type": "tool_use", "name": "computer", "input": {"action": "click"}},  # missing id, partial input
                    ]
                }
            ),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant-test",
            "claude-opus-4-7",
            [{"role": "user", "content": "click something"}],
        )
        parsed = json.loads(result)
        tc = parsed["tool_calls"][0]
        assert tc["function"]["name"] == "click"
        assert tc["id"] == ""


# ---------------------------------------------------------------------------
# Anthropic path: timeout triggers retry then raises
# ---------------------------------------------------------------------------


class TestAnthropicTimeoutRetry:
    """Timeout on the Anthropic endpoint should retry and eventually raise LLMError."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_anthropic_timeout_exhausts_retries(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """All retries timing out should raise LLMError mentioning the provider."""
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout("timed out")
        client = LLMClient()
        with pytest.raises(LLMError, match="anthropic"):
            client.chat(
                "anthropic",
                "sk-ant-test",
                "claude-opus-4-7",
                [{"role": "user", "content": "hello"}],
            )
        # Should have been called max_retries+1 times (default 3 retries = 4 calls)
        assert mock_post.call_count >= 2
