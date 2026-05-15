"""Tests for core/llm_client.py — list_models, chat_with_vision Anthropic path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.llm_client import LLMClient


class TestListModels:
    @patch("core.llm_client.fetch_models")
    def test_delegates_to_fetch_models(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = ["gpt-4", "gpt-3.5-turbo"]
        client = LLMClient()
        result = client.list_models("openai", api_key="sk-test")
        assert result == ["gpt-4", "gpt-3.5-turbo"]
        mock_fetch.assert_called_once_with("openai", "sk-test", None)

    @patch("core.llm_client.fetch_models")
    def test_passes_custom_url(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = []
        client = LLMClient()
        client.list_models("openai", api_key="sk-test", custom_url="http://localhost:1234")
        mock_fetch.assert_called_once_with("openai", "sk-test", "http://localhost:1234")

    @patch("core.llm_client.fetch_models")
    def test_returns_sorted_models(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = ["model-b", "model-a"]
        client = LLMClient()
        result = client.list_models("openai", api_key="k")
        assert result == ["model-b", "model-a"]


class TestChatWithVisionAnthropic:
    @patch.object(LLMClient, "chat")
    def test_anthropic_path_sends_vision_message(self, mock_chat: MagicMock) -> None:
        mock_chat.return_value = {"role": "assistant", "content": "I see a desktop"}
        client = LLMClient()
        messages = [{"role": "user", "content": "What is on screen?"}]

        client.chat_with_vision(
            provider="anthropic",
            api_key="sk-ant-test",
            model="claude-sonnet-4-20250514",
            messages=messages,
            image_base64="dGVzdA==",
            prompt="Describe this image",
        )

        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args
        sent_messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        vision_msg = sent_messages[-1]
        assert vision_msg["role"] == "user"
        content = vision_msg["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image"
        assert content[1]["source"]["type"] == "base64"
        assert content[1]["source"]["data"] == "dGVzdA=="

    @patch.object(LLMClient, "chat")
    def test_openai_path_sends_vision_message(self, mock_chat: MagicMock) -> None:
        mock_chat.return_value = {"role": "assistant", "content": "I see a desktop"}
        client = LLMClient()
        messages = [{"role": "user", "content": "Describe"}]

        client.chat_with_vision(
            provider="openai",
            api_key="sk-test",
            model="gpt-4o",
            messages=messages,
            image_base64="dGVzdA==",
            prompt="What do you see?",
        )

        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args
        sent_messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        vision_msg = sent_messages[-1]
        assert vision_msg["role"] == "user"
        content = vision_msg["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
