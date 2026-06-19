"""Tests for core/llm_client.py — gap coverage for lines 200, 443-444, 472-476.

Line 200:   msg reset to {} when choice message is not a dict.
Lines 443-444: LLMError raised when successful response body is not valid JSON.
Lines 472-476: LLMError raised after exhausting retries on connection/timeout errors.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from core.llm_client import LLMClient, LLMError

# ---------------------------------------------------------------------------
# Line 200: msg = {} when choice["message"] is not a dict
# ---------------------------------------------------------------------------


class TestChatNonDictMessage:
    """When a choice's "message" field is not a dict, it must be reset to {}."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_choice_message_is_string_returns_empty(
        self, _url: MagicMock, mock_post: MagicMock
    ) -> None:
        """If the message in the first choice is a plain string, chat returns empty string."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": "not-a-dict"}]}),
        )

        client = LLMClient()
        # openai provider so we hit the OpenAI-compatible path
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert result == ""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_choice_message_is_none_returns_empty(
        self, _url: MagicMock, mock_post: MagicMock
    ) -> None:
        """If the message in the first choice is None, chat returns empty string."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"choices": [{"message": None}]}),
        )

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])
        assert result == ""


# ---------------------------------------------------------------------------
# Lines 443-444: provider returns non-JSON body on success (2xx)
# ---------------------------------------------------------------------------


class TestNonJsonSuccessResponse:
    """A 2xx response whose body is not valid JSON must raise LLMError."""

    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_non_json_body_raises_llm_error(self, _url: MagicMock, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(side_effect=ValueError("No JSON")),
        )

        client = LLMClient()
        with pytest.raises(LLMError, match="non-JSON body"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Lines 472-476: exhausted retries on connection/timeout errors
# ---------------------------------------------------------------------------


class TestRetriesExhaustedConnectionError:
    """When all retries fail with ConnectionError, LLMError wraps last exception."""

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_connection_error_exhausted_retries(
        self, _url: MagicMock, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        client = LLMClient()
        with pytest.raises(LLMError, match="ConnectionError"):
            client.chat(
                "openai",
                "sk-test",
                "gpt-4o",
                [{"role": "user", "content": "hi"}],
                max_retries=0,
            )

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_timeout_exhausted_retries(
        self, _url: MagicMock, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        client = LLMClient()
        with pytest.raises(LLMError, match="Timeout"):
            client.chat(
                "openai",
                "sk-test",
                "gpt-4o",
                [{"role": "user", "content": "hi"}],
                max_retries=0,
            )

    @patch("core.llm_client.time.sleep")
    @patch("core.llm_client.requests.post")
    @patch("core.llm_client.get_base_url", return_value="https://api.example.com/v1")
    def test_unknown_reason_exhausted_retries(
        self, _url: MagicMock, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """If somehow last_exc and last_status are both None, raise the fallback message."""
        # This is a defensive path. To trigger it we call _post_with_retry
        # directly in a way that the loop exits without setting last_exc or last_status.
        # The loop: attempt=0, max_retries=0 -> while 0 <= 0 (true)
        # We need the try block to succeed (no exception) but with status >= 400
        # and status IN RETRY_STATUSES, so last_status gets set and the code
        # goes to retry. After retry, attempt becomes 1 > max_retries=0, loop exits.
        # Then last_status is set, so we get the _friendly_http_error path.
        # To hit line 476 we need last_status=None AND last_exc=None.
        # This is only reachable if the loop body somehow skips all branches.
        # We'll test the _post_with_retry method directly with a mock that
        # raises a generic RequestException that isn't Timeout or ConnectionError.
        mock_post.side_effect = requests.exceptions.RequestException("generic")

        client = LLMClient()
        with pytest.raises(LLMError, match="RequestException: generic"):
            client._post_with_retry(
                "https://api.example.com/v1/chat/completions",
                {"Content-Type": "application/json"},
                {"model": "gpt-4o", "messages": []},
                timeout=10,
                max_retries=0,
                base_delay=0.01,
                provider_label="test",
            )


class TestPostWithRetryLoopNeverRuns:
    """The defensive 'unknown reasons' fallback (loop body never executes)."""

    @patch("core.llm_client.requests.post")
    def test_negative_max_retries_raises_unknown_reason(self, mock_post: MagicMock) -> None:
        """With max_retries < 0 the retry loop never enters, so neither
        last_status nor last_exc is set and the final fallback raises."""
        client = LLMClient()
        with pytest.raises(LLMError, match="failed for unknown reasons"):
            client._post_with_retry(
                "https://api.example.com/v1/chat/completions",
                {"Content-Type": "application/json"},
                {"model": "gpt-4o", "messages": []},
                timeout=10,
                max_retries=-1,
                base_delay=0.01,
                provider_label="test",
            )
        # The loop body never ran, so requests.post was never called.
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# list_models convenience wrapper
# ---------------------------------------------------------------------------


class TestListModelsWrapper:
    """list_models() delegates to the module-level fetch_models()."""

    @patch("core.llm_client.fetch_models", return_value=["m-a", "m-b"])
    def test_delegates_to_fetch_models(self, mock_fetch: MagicMock) -> None:
        client = LLMClient()
        result = client.list_models("openai", "sk-test", "https://custom")
        assert result == ["m-a", "m-b"]
        mock_fetch.assert_called_once_with("openai", "sk-test", "https://custom")


# ---------------------------------------------------------------------------
# Anthropic-native paths: vision message + message/block conversion edges
# ---------------------------------------------------------------------------


class TestAnthropicVisionAndConversion:
    """Cover the anthropic_native vision branch and the conversion loops."""

    @patch("core.llm_client.requests.post")
    def test_vision_uses_native_anthropic_image_block(self, mock_post: MagicMock) -> None:
        """An anthropic vision message carries a native image block via
        _make_anthropic_vision_message and routes to _chat_anthropic.

        (v18) The deprecated chat_with_vision() wrapper was removed; this test
        now builds the vision message via the private helper and sends it with
        chat() — the same path the engine loop uses.
        """
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"content": [{"type": "text", "text": "a cat"}]}),
        )
        client = LLMClient()
        vision_msg = client._make_vision_message("anthropic", "aGVsbG8=", "What is this?")
        result = client.chat(
            "anthropic",
            "sk-ant",
            "claude-opus-4-7",
            [{"role": "user", "content": "earlier"}, vision_msg],
        )
        assert result == "a cat"
        # The outgoing payload's final message must carry a native image block.
        sent_payload = mock_post.call_args.kwargs["json"]
        last_msg = sent_payload["messages"][-1]
        block_types = [b["type"] for b in last_msg["content"]]
        assert "image" in block_types

    @patch("core.llm_client.requests.post")
    def test_anthropic_skips_unrecognised_role(self, mock_post: MagicMock) -> None:
        """A message whose role is neither system nor user/assistant is dropped."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"content": [{"type": "text", "text": "ok"}]}),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant",
            "claude-opus-4-7",
            [
                {"role": "tool", "content": "ignored tool output"},
                {"role": "user", "content": "hi"},
            ],
        )
        assert result == "ok"
        sent_payload = mock_post.call_args.kwargs["json"]
        roles = [m["role"] for m in sent_payload["messages"]]
        assert roles == ["user"]  # the 'tool' message was skipped

    @patch("core.llm_client.requests.post")
    def test_anthropic_skips_unknown_content_block(self, mock_post: MagicMock) -> None:
        """A response content block of an unknown type is ignored; text is kept."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "content": [
                        {"type": "thinking", "text": "scratchpad"},
                        {"type": "text", "text": "final answer"},
                    ]
                }
            ),
        )
        client = LLMClient()
        result = client.chat(
            "anthropic",
            "sk-ant",
            "claude-opus-4-7",
            [{"role": "user", "content": "hi"}],
        )
        assert result == "final answer"
