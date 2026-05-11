"""
Sentinel Desktop v2 — LLM Client.

Unified chat client supporting 16+ providers via the OpenAI-compatible
API pattern.  Supports:

* Text chat with arbitrary message histories
* Vision / screenshot analysis (base64 image payloads)
* Tool / function calling (OpenAI-style, auto-converted for Anthropic)
* Streaming-friendly response normalisation

Typical usage::

    from core.llm_client import LLMClient

    client = LLMClient()
    reply = client.chat(
        provider="openai",
        api_key="sk-...",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(reply)
"""

from __future__ import annotations

import json
import logging
import base64
from typing import Any, Dict, List, Optional

import requests

from .provider_registry import PROVIDERS, fetch_models, get_base_url

logger = logging.getLogger(__name__)

# Default network timeout (seconds) — generous for large generations.
DEFAULT_TIMEOUT = 120


class LLMClient:
    """Synchronous LLM client that speaks to 16+ provider endpoints.

    The constructor is cheap — no connections are opened until a request is
    made.  A single instance can be reused across providers and models.
    """

    def __init__(self) -> None:
        self.providers = PROVIDERS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        custom_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> str:
        """Send a chat completion request and return the assistant's text.

        For providers that return *tool calls* the result is a JSON-encoded
        string ``{"tool_calls": [...]}`` so the caller can distinguish tool
        invocations from plain text.

        Args:
            provider:   Provider key (e.g. ``"openai"``, ``"anthropic"``).
            api_key:    API key (ignored when ``no_auth`` is set on the provider).
            model:      Model identifier (e.g. ``"gpt-4o"``).
            messages:   OpenAI-style message list.
            tools:      Optional list of OpenAI-style tool definitions.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.
            custom_url: Override base URL (for ``"custom"`` provider).
            timeout:    HTTP timeout in seconds.

        Returns:
            Assistant message content (plain text), or a JSON-encoded
            ``{"tool_calls": [...]}`` payload when the model requests a
            tool invocation.

        Raises:
            ValueError: If *provider* is not in the catalog.
            requests.RequestException: On network / HTTP errors.
        """
        provider_config = PROVIDERS.get(provider)
        if not provider_config:
            raise ValueError(f"Unknown provider: {provider}")

        # Anthropic has its own wire format.
        if provider_config.get("anthropic_native"):
            return self._chat_anthropic(
                api_key=api_key,
                model=model,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )

        # --- OpenAI-compatible path ------------------------------------
        base_url = get_base_url(provider, custom_url)
        chat_url = f"{base_url}{provider_config['chat_endpoint']}"

        headers = self._build_headers(provider_config, api_key)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.info(
            "chat → %s/%s (%d msgs, %d tools)",
            provider, model, len(messages), len(tools or []),
        )

        resp = requests.post(
            chat_url, headers=headers, json=payload, timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        # Check for tool calls first — return as JSON payload.
        if msg.get("tool_calls"):
            return json.dumps({"tool_calls": msg["tool_calls"]})

        return msg.get("content", "")

    def chat_with_vision(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, Any]],
        image_base64: str,
        prompt: str = "Describe this screenshot.",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        custom_url: Optional[str] = None,
    ) -> str:
        """Send a chat request with a screenshot image.

        The *image_base64* string is embedded as a ``data:`` URI in a vision
        message appended to *messages*.

        For Anthropic the image is sent in the native ``source.type =
        "base64"`` format.

        Args:
            provider:     Provider key.
            api_key:      API key.
            model:        Model identifier.
            messages:     Existing conversation history.
            image_base64: Base64-encoded PNG/JPEG image data.
            prompt:       Text instruction to accompany the image.
            max_tokens:   Max response tokens.
            temperature:  Sampling temperature.
            custom_url:   Override base URL for the ``"custom"`` provider.

        Returns:
            Assistant message content (plain text).
        """
        provider_config = PROVIDERS.get(provider, {})

        if provider_config.get("anthropic_native"):
            vision_message = self._make_anthropic_vision_message(
                image_base64, prompt,
            )
        else:
            vision_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }

        all_messages = messages + [vision_message]
        return self.chat(
            provider=provider,
            api_key=api_key,
            model=model,
            messages=all_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            custom_url=custom_url,
        )

    def list_models(
        self,
        provider: str,
        api_key: str = "",
        custom_url: Optional[str] = None,
    ) -> List[str]:
        """Convenience wrapper around :func:`fetch_models`.

        Returns a sorted list of model ID strings for the given provider.
        """
        return fetch_models(provider, api_key, custom_url)

    # ------------------------------------------------------------------
    # Anthropic native API
    # ------------------------------------------------------------------

    def _chat_anthropic(
        self,
        api_key: str,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> str:
        """Send a chat request using Anthropic's native ``/messages`` API."""
        provider_config = PROVIDERS["anthropic"]
        base_url = get_base_url("anthropic")
        chat_url = f"{base_url}{provider_config['chat_endpoint']}"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        # Convert messages: extract system prompt, build Anthropic-style list.
        system_msg = ""
        converted_messages: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                system_msg += (content if isinstance(content, str) else str(content)) + "\n"
            elif role in ("user", "assistant"):
                converted_messages.append({"role": role, "content": content})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg.strip():
            payload["system"] = system_msg.strip()
        if tools:
            payload["tools"] = self._convert_tools_to_anthropic(tools)

        logger.info("chat → anthropic/%s", model)

        resp = requests.post(
            chat_url, headers=headers, json=payload, timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text / tool-use from the response.
        content_blocks = data.get("content", [])
        text_parts: List[str] = []
        tool_use_blocks: List[Dict[str, Any]] = []

        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_use_blocks.append(block)

        if tool_use_blocks:
            # Normalise to OpenAI-style tool_calls payload.
            openai_tool_calls = []
            for tb in tool_use_blocks:
                openai_tool_calls.append({
                    "id": tb.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tb.get("name", ""),
                        "arguments": json.dumps(tb.get("input", {})),
                    },
                })
            return json.dumps({"tool_calls": openai_tool_calls})

        return "\n".join(text_parts).strip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_headers(
        provider_config: Dict[str, Any],
        api_key: str,
    ) -> Dict[str, str]:
        """Construct HTTP headers from the provider config and API key."""
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if not provider_config.get("no_auth") and api_key:
            auth_header = provider_config.get("auth_header", "Authorization")
            auth_prefix = provider_config.get("auth_prefix", "Bearer ")
            headers[auth_header] = f"{auth_prefix}{api_key}"
        return headers

    @staticmethod
    def _convert_tools_to_anthropic(
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI-style tool definitions to Anthropic format.

        OpenAI::

            {"type": "function", "function": {"name": ..., "description": ...,
             "parameters": {...}}}

        Anthropic::

            {"name": ..., "description": ..., "input_schema": {...}}
        """
        anthropic_tools: List[Dict[str, Any]] = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {
                    "type": "object",
                    "properties": {},
                }),
            })
        return anthropic_tools

    @staticmethod
    def _make_anthropic_vision_message(
        image_base64: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """Build a user message with a base64 image for Anthropic vision."""
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64,
                    },
                },
            ],
        }
