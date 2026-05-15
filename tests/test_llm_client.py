"""Tests for core/llm_client.py — error messages, headers, tool conversion."""

from core.llm_client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    LLMClient,
    LLMError,
    RETRY_STATUSES,
    _friendly_http_error,
)


class TestConstants:
    def test_defaults(self):
        assert DEFAULT_TIMEOUT == 120
        assert DEFAULT_MAX_RETRIES == 3

    def test_retry_statuses(self):
        assert 429 in RETRY_STATUSES
        assert 500 in RETRY_STATUSES
        assert 502 in RETRY_STATUSES
        assert 200 not in RETRY_STATUSES
        assert 404 not in RETRY_STATUSES


class TestFriendlyHttpError:
    def test_401(self):
        msg = _friendly_http_error(401, "bad key")
        assert "API key" in msg

    def test_403(self):
        msg = _friendly_http_error(403, "forbidden")
        assert "access" in msg.lower() or "billing" in msg.lower()

    def test_404(self):
        msg = _friendly_http_error(404, "not here")
        assert "not found" in msg.lower()

    def test_429(self):
        msg = _friendly_http_error(429, "slow down")
        assert "Rate limited" in msg

    def test_500(self):
        msg = _friendly_http_error(500, "internal error")
        assert "Provider error" in msg
        assert "500" in msg

    def test_unknown_status(self):
        msg = _friendly_http_error(418, "I'm a teapot")
        assert "418" in msg

    def test_long_body_truncated(self):
        long_body = "x" * 500
        msg = _friendly_http_error(500, long_body)
        assert "…" in msg


class TestBuildHeaders:
    def test_bearer_auth(self):
        config = {"auth_header": "Authorization", "auth_prefix": "Bearer "}
        headers = LLMClient._build_headers(config, "sk-123")
        assert headers["Authorization"] == "Bearer sk-123"
        assert headers["Content-Type"] == "application/json"

    def test_no_auth_provider(self):
        config = {"no_auth": True}
        headers = LLMClient._build_headers(config, "ignored")
        assert "Authorization" not in headers

    def test_custom_auth_header(self):
        config = {"auth_header": "X-API-Key", "auth_prefix": ""}
        headers = LLMClient._build_headers(config, "mykey")
        assert headers["X-API-Key"] == "mykey"

    def test_empty_api_key_skips_auth(self):
        config = {}
        headers = LLMClient._build_headers(config, "")
        assert "Authorization" not in headers


class TestConvertToolsToAnthropic:
    def test_converts_openai_tools(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click at coordinates",
                    "parameters": {"type": "object", "properties": {"x": {"type": "int"}}},
                },
            }
        ]
        result = LLMClient._convert_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == "click"
        assert result[0]["description"] == "Click at coordinates"
        assert "input_schema" in result[0]
        assert result[0]["input_schema"]["properties"]["x"]["type"] == "int"

    def test_empty_tools(self):
        assert LLMClient._convert_tools_to_anthropic([]) == []

    def test_missing_function_key(self):
        tools = [{"type": "function"}]
        result = LLMClient._convert_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == ""
        assert "input_schema" in result[0]


class TestMakeAnthropicVisionMessage:
    def test_structure(self):
        msg = LLMClient._make_anthropic_vision_message("base64data", "Describe this")
        assert msg["role"] == "user"
        content = msg["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Describe this"
        assert content[1]["type"] == "image"
        assert content[1]["source"]["type"] == "base64"
        assert content[1]["source"]["data"] == "base64data"


class TestLLMClientChat:
    def test_unknown_provider_raises(self):
        client = LLMClient()
        try:
            client.chat("nonexistent_provider", "key", "model", [])
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "nonexistent_provider" in str(exc)
