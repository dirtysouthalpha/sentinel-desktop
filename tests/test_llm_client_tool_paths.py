"""Gap tests for core/llm_client.py — lines 259-260, 470-471, 487.

Lines 259-260: elif tools: branch in _chat_openai_compatible — triggers when
  using a provider without computer_use support (e.g. groq/mistral).
Lines 470-471: elif tools: branch in _chat_anthropic — triggers when calling
  the method directly with computer_use_type=None and tools provided.
Line 487: return _parse_anthropic_response path in _chat_anthropic — triggers
  when computer_use_type is None (standard Anthropic call, no computer-use).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.llm_client import LLMClient


def _ok_response(body: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = body
    return r


class TestOpenAICompatibleElseTools:
    """Lines 259-260: elif tools: branch in _chat_openai_compatible.

    Use a provider without a computer_use flag so computer_use_type is None.
    """

    @patch("core.llm_client.requests.post")
    def test_groq_provider_with_tools_hits_elif_branch(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _ok_response({"choices": [{"message": {"content": "ok"}}]})
        client = LLMClient()
        tools = [{"type": "function", "function": {"name": "click", "description": ""}}]
        result = client.chat(
            "groq",
            "gsk-test",
            "llama3-70b-8192",
            [{"role": "user", "content": "hi"}],
            tools=tools,
        )
        assert isinstance(result, str)
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert payload.get("tools") == tools
        assert payload.get("tool_choice") == "auto"


class TestChatAnthropicElseTools:
    """Lines 470-471: elif tools: branch in _chat_anthropic.

    Call _chat_anthropic directly with computer_use_type=None and tools.
    Line 487 (return _parse_anthropic_response) is also covered here.
    """

    @patch("core.llm_client.requests.post")
    def test_anthropic_direct_with_tools_no_computer_use(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _ok_response({"content": [{"type": "text", "text": "hello"}]})
        client = LLMClient()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "click",
                    "description": "Click a target",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = client._chat_anthropic(
            api_key="sk-ant-test",
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            max_tokens=1024,
            temperature=0.0,
            timeout=30,
            computer_use_type=None,
        )
        assert result == "hello"

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        # Tools should have been converted to Anthropic format
        assert "tools" in payload
        assert payload["tools"][0]["name"] == "click"
        assert "input_schema" in payload["tools"][0]

    @patch("core.llm_client.requests.post")
    def test_anthropic_direct_no_tools_no_computer_use_returns_text(
        self, mock_post: MagicMock
    ) -> None:
        """Line 487: _parse_anthropic_response called when computer_use_type is None."""
        mock_post.return_value = _ok_response({"content": [{"type": "text", "text": "world"}]})
        client = LLMClient()
        result = client._chat_anthropic(
            api_key="sk-ant-test",
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
            max_tokens=1024,
            temperature=0.0,
            timeout=30,
            computer_use_type=None,
        )
        assert result == "world"
