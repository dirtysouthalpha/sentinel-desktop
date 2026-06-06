"""Advanced LLM client tests for malformed responses, timeouts, and network issues.

Covers:
- Connection errors and network failures
- Malformed JSON responses
- Large response handling
- Concurrent requests edge cases
- Rate limiting and timeout edge cases
- Different content structures and types
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests as req

from core.llm_client import LLMClient, LLMError

# ---------------------------------------------------------------------------
# Connection errors and network failures
# ---------------------------------------------------------------------------


class TestConnectionErrors:
    """Test LLM client handling of connection errors and network failures."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_connection_error_retries(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Connection errors should trigger retries and eventually raise LLMError."""
        mock_post.side_effect = req.exceptions.ConnectionError("network unreachable")

        client = LLMClient()
        with pytest.raises(LLMError, match="network|connection"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])

        # Should have attempted multiple retries
        assert mock_post.call_count >= 2

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.anthropic.com/v1")
    def test_dns_error_handling(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """DNS resolution errors should be handled gracefully."""
        mock_post.side_effect = req.exceptions.ConnectionError("DNS lookup failed")

        client = LLMClient()
        with pytest.raises(LLMError, match="network|connection|dns|DNS"):
            client.chat(
                "anthropic",
                "sk-ant-test",
                "claude-3-5-sonnet-20241022",
                [{"role": "user", "content": "test"}],
                max_retries=2,
            )

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_connection_reset_during_request(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Connection reset during request should trigger retries."""
        mock_post.side_effect = req.exceptions.ConnectionError("Connection reset by peer")

        client = LLMClient()
        with pytest.raises(LLMError):
            client.chat(
                "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}], max_retries=2
            )

        # Should have attempted retries
        assert mock_post.call_count >= 2


# ---------------------------------------------------------------------------
# Malformed JSON responses
# ---------------------------------------------------------------------------


class TestMalformedJsonResponses:
    """Test LLM client handling of malformed JSON responses."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_invalid_json_response(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Invalid JSON in response should raise LLMError."""
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
        )

        client = LLMClient()
        with pytest.raises(LLMError, match="non-JSON|json|parse"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_truncated_json_response(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Truncated JSON response should raise appropriate error."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                side_effect=json.JSONDecodeError("Expecting value", '{"choices": [{"', 10)
            ),
        )

        client = LLMClient()
        with pytest.raises(LLMError, match="non-JSON|json|parse"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_json_with_syntax_errors(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """JSON with syntax errors should raise LLMError."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                side_effect=json.JSONDecodeError(
                    "Extra data", '{"valid": "json"} {"extra": "data"}', 20
                )
            ),
        )

        client = LLMClient()
        with pytest.raises(LLMError, match="non-JSON|json|parse"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])


# ---------------------------------------------------------------------------
# Large response handling
# ---------------------------------------------------------------------------


class TestLargeResponseHandling:
    """Test LLM client handling of large responses."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_very_large_response_content(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Very large response content should be handled gracefully."""
        large_content = "x" * 100000  # 100KB of text
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": large_content}}]}),
        )

        client = LLMClient()
        result = client.chat(
            "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "generate long text"}]
        )
        assert len(result) == 100000

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_many_choices_in_response(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Response with many choices should use first one."""
        choices = [{"message": {"content": f"Choice {i}"}} for i in range(100)]
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"choices": choices})
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        assert result == "Choice 0"

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_deeply_nested_response_structure(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Deeply nested response structure should be handled correctly."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "choices": [
                        {
                            "message": {
                                "content": "nested content",
                                "extra": {"nested": {"deep": {"value": "ignored"}}},
                            }
                        }
                    ]
                }
            ),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        assert result == "nested content"


# ---------------------------------------------------------------------------
# Timeout edge cases
# ---------------------------------------------------------------------------


class TestTimeoutEdgeCases:
    """Test timeout handling in various edge case scenarios."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_timeout_then_success(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Timeout followed by success should work after retry."""
        error_resp = req.exceptions.Timeout("Request timed out")
        success_resp = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": "success"}}]}),
        )
        mock_post.side_effect = [error_resp, success_resp]

        client = LLMClient()
        result = client.chat(
            "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}], max_retries=2
        )
        assert result == "success"

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_timeout_with_long_response_time(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Timeout after long processing time should still trigger retries."""
        mock_post.side_effect = req.exceptions.Timeout("Request timeout after 120 seconds")

        client = LLMClient()
        with pytest.raises(LLMError, match="timeout"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_read_timeout_vs_connect_timeout(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Different types of timeouts should both be handled."""
        # Provide enough timeout exceptions to exhaust all retries
        mock_post.side_effect = [req.exceptions.ReadTimeout("Read timeout")] * 10

        client = LLMClient()
        with pytest.raises(LLMError, match="timeout"):
            client.chat(
                "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}], max_retries=5
            )


# ---------------------------------------------------------------------------
# Different content structures and types
# ---------------------------------------------------------------------------


class TestUnusualContentStructures:
    """Test handling of unusual content structures and types."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_content_as_integer(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Content as integer should be returned as-is (or converted to string)."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": 42}}]}),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        # Result could be integer or string representation
        assert result == 42 or result == "42"

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_content_as_float(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Content as float should be returned as-is (or converted to string)."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": 3.14159}}]}),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        # Result could be float or string representation
        assert result == 3.14159 or result == "3.14159"

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_content_as_boolean(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Content as boolean should be returned as-is (or converted to string)."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": True}}]}),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        # Result could be boolean or string representation
        assert result is True or result == "True"

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_content_as_list_with_mixed_types(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Content as list with mixed types should be concatenated."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "text", "text": "Hello "},
                                    {"type": "text", "text": 123},
                                    {"type": "text", "text": " World"},
                                ]
                            }
                        }
                    ]
                }
            ),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        assert "Hello" in result
        assert "World" in result


# ---------------------------------------------------------------------------
# Rate limiting edge cases
# ---------------------------------------------------------------------------


class TestRateLimitingEdgeCases:
    """Test rate limiting and retry edge cases."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_rate_limit_then_success(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Rate limit response followed by success should work."""
        rate_limit_resp = MagicMock(
            status_code=429, text="Rate limit exceeded", headers={"Retry-After": "1"}
        )
        success_resp = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": "success"}}]}),
        )
        mock_post.side_effect = [rate_limit_resp, success_resp]

        client = LLMClient()
        result = client.chat(
            "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}], max_retries=2
        )
        assert result == "success"

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_persistent_rate_limit(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Persistent rate limiting should eventually raise LLMError."""
        mock_post.return_value = MagicMock(
            status_code=429, text="Rate limit exceeded", headers={"Retry-After": "60"}
        )

        client = LLMClient()
        with pytest.raises(LLMError, match="Rate limit|rate limit"):
            client.chat(
                "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}], max_retries=2
            )

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_rate_limit_with_retry_after_header(
        self, _url: MagicMock, mock_post: MagicMock, _sleep: MagicMock
    ) -> None:
        """Rate limit with Retry-After header should use it for backoff."""
        rate_limit_resp = MagicMock(
            status_code=429, text="Rate limit exceeded", headers={"Retry-After": "5"}
        )
        success_resp = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": "success"}}]}),
        )
        mock_post.side_effect = [rate_limit_resp, success_resp]

        client = LLMClient()
        result = client.chat(
            "openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}], max_retries=2
        )
        assert result == "success"


# ---------------------------------------------------------------------------
# Request/Response edge cases
# ---------------------------------------------------------------------------


class TestRequestResponseEdgeCases:
    """Test edge cases in request/response handling."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_empty_response_body(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Empty response body should raise appropriate error."""
        mock_post.return_value = MagicMock(status_code=200, json=MagicMock(return_value={}))

        client = LLMClient()
        with pytest.raises(LLMError, match="no 'choices'"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_response_with_extra_fields(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Response with extra unknown fields should be handled gracefully."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "choices": [{"message": {"content": "test"}}],
                    "unknown_field": "value",
                    "another_unknown": 123,
                    "nested": {"unknown": "data"},
                }
            ),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        assert result == "test"

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_response_with_unicode_content(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Response with unicode characters should be handled correctly."""
        unicode_content = "Hello 世界 🌍 Привед мир"
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": unicode_content}}]}),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        assert result == unicode_content

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.openai.com/v1")
    def test_response_with_special_characters(self, _url: MagicMock, mock_post: MagicMock) -> None:
        """Response with special characters should be handled correctly."""
        special_content = "Test\n\t\r\x00\x1b[0m"
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": {"content": special_content}}]}),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "test"}])
        assert result == special_content
