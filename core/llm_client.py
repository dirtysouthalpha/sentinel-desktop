"""Sentinel Desktop v3 — LLM Client.

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
import random
import time
from typing import Any, NoReturn

import requests

from .provider_registry import PROVIDERS, fetch_models, get_base_url

logger = logging.getLogger(__name__)

# Default network timeout (seconds) — generous for large generations.
DEFAULT_TIMEOUT = 120

# Default retry policy. The engine overrides these from config when calling
# .chat(); keep these conservative as a fallback for direct LLMClient users.
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 1.0  # seconds — multiplied by 2^attempt with jitter

# HTTP status codes we consider transient and worth retrying.
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504, 522, 524}

# Anthropic model families that removed the sampling parameters
# (temperature / top_p / top_k). Sending "temperature" to one of these is a
# hard 400, so _chat_anthropic omits it rather than letting the request fail.
NO_SAMPLING_PARAM_PREFIXES = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-opus-4-7",
    "claude-opus-4-8",
)


def omits_sampling_params(model: str) -> bool:
    """True when ``model`` rejects ``temperature``/``top_p``/``top_k``."""
    return model.startswith(NO_SAMPLING_PARAM_PREFIXES)

# Common HTTP status codes
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_TIMEOUT = 408
HTTP_SERVER_ERROR_MAX = 600

# Error message truncation length
MAX_ERROR_SNIPPET_LENGTH = 240

# Anthropic computer-use models lose click accuracy on screenshots larger than
# roughly this many pixels on the longest edge (the API downscales big images
# internally). We downscale to this size ourselves and scale coordinates back.
MAX_SCREENSHOT_EDGE = 1536


class LLMError(Exception):
    """Raised for unrecoverable LLM errors with a human-friendly message."""


def _friendly_http_error(status: int, body: str) -> str:
    """Map an HTTP status code to an actionable message for the GUI."""
    snippet = body.strip()
    if len(snippet) > MAX_ERROR_SNIPPET_LENGTH:
        snippet = snippet[:MAX_ERROR_SNIPPET_LENGTH] + "…"
    if status == HTTP_UNAUTHORIZED:
        return "Invalid API key — check Settings."
    if status == HTTP_FORBIDDEN:
        return "API key lacks access to this model (or org/billing issue)."
    if status == HTTP_NOT_FOUND:
        return "Model or endpoint not found — verify the model name."
    if status == HTTP_TOO_MANY_REQUESTS:
        return f"Rate limited by provider. {snippet}"
    if HTTP_INTERNAL_SERVER_ERROR <= status < HTTP_SERVER_ERROR_MAX:
        return f"Provider error (HTTP {status}). {snippet}"
    return f"HTTP {status}: {snippet}"


class LLMClient:
    """Synchronous LLM client that speaks to 16+ provider endpoints.

    The constructor is cheap — no connections are opened until a request is
    made.  A single instance can be reused across providers and models.
    """

    def __init__(self) -> None:
        """Initialize the client and expose the built-in provider catalog."""
        self.providers = PROVIDERS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        custom_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        computer_use_enabled: bool = True,
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
            max_retries: Maximum number of retry attempts for transient failures.
            retry_base_delay: Base delay in seconds for exponential backoff.

        Returns:
            Assistant message content (plain text), or a JSON-encoded
            ``{"tool_calls": [...]}`` payload when the model requests a
            tool invocation.

        Raises:
            ValueError: If *provider* is not in the catalog.
            requests.RequestException: On network / HTTP errors.

        """
        return self._route_chat_request(
            provider=provider,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            custom_url=custom_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            computer_use_enabled=computer_use_enabled,
        )

    def _route_chat_request(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        custom_url: str | None,
        timeout: int,
        max_retries: int,
        retry_base_delay: float,
        computer_use_enabled: bool = True,
    ) -> str:
        """Route chat request to appropriate provider implementation.

        When the provider supports native computer-use (Anthropic computer_20250124,
        OpenAI computer-use-preview), the tools list is replaced with the native
        computer tool and the response is translated back to our JSON action format.
        """
        provider_config = PROVIDERS.get(provider)
        if not provider_config:
            raise ValueError(f"Unknown provider: {provider}")

        # Check for native computer-use support — respect the enabled flag
        computer_use_type = provider_config.get("computer_use") if computer_use_enabled else None

        if provider_config.get("anthropic_native"):
            return self._chat_anthropic(
                api_key=api_key,
                model=model,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                max_retries=max_retries,
                retry_base_delay=retry_base_delay,
                custom_url=custom_url,
                computer_use_type=computer_use_type,
            )

        return self._chat_openai_compatible(
            provider_config=provider_config,
            provider=provider,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            custom_url=custom_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            computer_use_type=computer_use_type,
        )

    def _chat_openai_compatible(
        self,
        *,
        provider_config: dict[str, Any],
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        custom_url: str | None,
        timeout: int,
        max_retries: int,
        retry_base_delay: float,
        computer_use_type: str | None = None,
    ) -> str:
        """Send a chat request via the OpenAI-compatible endpoint.

        When computer_use_type is "openai", replaces tools with the native
        computer-use-preview tool for screen control.
        """
        base_url = get_base_url(provider, custom_url)
        chat_url = f"{base_url}{provider_config['chat_endpoint']}"
        headers = self._build_headers(provider_config, api_key)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Use native computer-use tools when available
        if computer_use_type == "openai":
            from core.computer_use import build_openai_tools

            payload["tools"] = build_openai_tools(tools)
            payload["tool_choice"] = "auto"
        elif tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.info(
            "chat → %s/%s (%d msgs, %d tools)%s",
            provider,
            model,
            len(messages),
            len(payload.get("tools") or []),
            " [computer-use]" if computer_use_type else "",
        )
        data = self._post_with_retry(
            chat_url,
            headers,
            payload,
            timeout,
            max_retries=max_retries,
            base_delay=retry_base_delay,
            provider_label=provider,
        )
        return self._parse_openai_response(data, provider)

    @staticmethod
    def _parse_openai_response(data: Any, provider: str) -> str:
        """Parse an OpenAI-shaped chat completion response into text or tool calls.

        Handles error envelopes, missing ``choices``, tool-call payloads,
        and content blocks (plain text or list-of-blocks).

        Args:
            data:       Raw JSON-decoded response body.
            provider:   Provider label for error messages.

        Returns:
            Assistant text content, or a JSON-encoded
            ``{"tool_calls": [...]}`` payload.

        Raises:
            LLMError: On malformed or error responses.

        """
        # Defensively unwrap the OpenAI-shaped response. Some providers (e.g.
        # Z.ai's coding plan) occasionally return error envelopes without a
        # "choices" key — we surface a clear LLMError instead of letting a
        # KeyError bubble up to the GUI.
        if not isinstance(data, dict):
            raise LLMError(f"{provider}: unexpected response type {type(data).__name__}")
        if "error" in data and not data.get("choices"):
            err = data["error"]
            if isinstance(err, dict):
                err = err.get("message") or err.get("code") or str(err)
            raise LLMError(f"{provider}: {err}")

        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"{provider}: response had no 'choices'. Body: {json.dumps(data)[:300]}")

        choice = choices[0] if isinstance(choices[0], dict) else {}
        msg = choice.get("message") or choice.get("delta") or {}
        if not isinstance(msg, dict):
            msg = {}

        # Check for tool calls first — return as JSON payload.
        if msg.get("tool_calls"):
            return json.dumps({"tool_calls": msg["tool_calls"]})

        # Some providers nest the text under "content" as a list of blocks.
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
        return content or ""

    def chat_with_vision(
        self,
        provider: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        image_base64: str,
        prompt: str = "Describe this screenshot.",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        custom_url: str | None = None,
    ) -> str:
        """Send a chat request with a screenshot image.

        .. deprecated:: 3.1.0
            This method is no longer called by the engine loop. Vision
            messages are now constructed directly by
            ``AgentEngine._add_vision_message`` and sent via ``chat()``.
            Kept for backward compatibility with external callers.

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
        vision_message = self._make_vision_message(provider, image_base64, prompt)
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

    def _make_vision_message(self, provider: str, image_base64: str, prompt: str) -> dict[str, Any]:
        """Construct a vision message for the given provider."""
        provider_config = PROVIDERS.get(provider, {})

        if provider_config.get("anthropic_native"):
            return self._make_anthropic_vision_message(image_base64, prompt)

        return self._make_openai_vision_message(image_base64, prompt)

    def _make_openai_vision_message(self, image_base64: str, prompt: str) -> dict[str, Any]:
        """Construct a vision message in OpenAI format."""
        return {
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

    def list_models(
        self,
        provider: str,
        api_key: str = "",
        custom_url: str | None = None,
    ) -> list[str]:
        """Wrap :func:`fetch_models` for convenience.

        Returns a sorted list of model ID strings for the given provider.
        """
        return fetch_models(provider, api_key, custom_url)

    # ------------------------------------------------------------------
    # Anthropic native API
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_display_size(
        messages: list[dict[str, Any]],
        default: tuple[int, int] = (1920, 1080),
    ) -> tuple[int, int]:
        """Infer the display resolution from the most recent screenshot.

        The Anthropic computer tool must be told the exact pixel dimensions of
        the screenshots it receives, otherwise returned click coordinates are
        scaled wrong. We read the dimensions straight from the latest image in
        the message list so this works at any resolution without hardcoding.

        Handles both Anthropic-native image blocks
        (``{"type": "image", "source": {"data": <b64>}}``) and OpenAI-style
        data URLs (``{"type": "image_url", "image_url": {"url": "data:...;base64,..."}}``).
        Falls back to *default* when no decodable image is present.
        """
        import base64
        from io import BytesIO

        b64: str | None = None
        for message in reversed(messages):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in reversed(content):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "image":
                    source = block.get("source", {})
                    if isinstance(source, dict) and source.get("data"):
                        b64 = source["data"]
                        break
                elif block.get("type") == "image_url":
                    url = block.get("image_url", {}).get("url", "")
                    if "base64," in url:
                        b64 = url.split("base64,", 1)[1]
                        break
            if b64:
                break

        if not b64:
            return default
        try:
            from PIL import Image

            with Image.open(BytesIO(base64.b64decode(b64))) as img:
                width, height = img.size
            if width > 0 and height > 0:
                return width, height
        except Exception as exc:  # noqa: BLE001 — bad image must never break a call
            logger.debug("Could not infer display size from screenshot: %s", exc)
        return default

    @staticmethod
    def _downscale_message_images(
        messages: list[dict[str, Any]],
        scale: float,
    ) -> tuple[list[dict[str, Any]], int]:
        """Resize every embedded screenshot by *scale* (0 < scale < 1).

        Returns ``(new_messages, count)`` where *count* is how many images were
        actually resized. The original list is left untouched. Any image that
        fails to decode is passed through unchanged so a bad frame never breaks
        the call. The count lets the caller scale returned coordinates only when
        a real screenshot was downscaled (never on the no-image fallback).
        """
        if scale >= 1.0:
            return messages, 0
        import base64
        from io import BytesIO

        from PIL import Image

        downscaled = 0
        out: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                out.append(message)
                continue
            new_content: list[Any] = []
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "image"
                    and isinstance(block.get("source"), dict)
                    and block["source"].get("type") == "base64"
                    and block["source"].get("data")
                ):
                    try:
                        raw = base64.b64decode(block["source"]["data"])
                        with Image.open(BytesIO(raw)) as im:
                            new_w = max(1, round(im.width * scale))
                            new_h = max(1, round(im.height * scale))
                            resized = im.resize((new_w, new_h))
                            buf = BytesIO()
                            resized.save(buf, format="PNG")
                        new_data = base64.b64encode(buf.getvalue()).decode()
                        new_content.append({
                            **block,
                            "source": {
                                **block["source"],
                                "media_type": "image/png",
                                "data": new_data,
                            },
                        })
                        downscaled += 1
                        continue
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Image downscale failed, sending as-is: %s", exc)
                new_content.append(block)
            out.append({**message, "content": new_content})
        return out, downscaled

    def _chat_anthropic(
        self,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        timeout: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        custom_url: str | None = None,
        computer_use_type: str | None = None,
    ) -> str:
        """Send a chat request using Anthropic's native ``/messages`` API.

        When computer_use_type is "anthropic", replaces the standard tools with
        the native computer_20250124 tool for screen control.
        """
        provider_config = PROVIDERS["anthropic"]
        base_url = get_base_url("anthropic", custom_url)
        chat_url = f"{base_url}{provider_config['chat_endpoint']}"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Accept-Encoding": "identity",  # prevent gzip mis-encoding from proxy layers
        }

        system_msg, converted_messages = self._convert_messages_for_anthropic(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
            "max_tokens": max_tokens,
        }
        if not omits_sampling_params(model):
            payload["temperature"] = temperature
        if system_msg.strip():
            payload["system"] = system_msg.strip()

        # Use native computer-use tools when available
        coord_scale = 1.0
        if computer_use_type == "anthropic":
            from core.computer_use import build_anthropic_tools

            # 1. Infer the true screenshot resolution (no 1920x1080 assumption).
            src_w, src_h = self._infer_display_size(messages)

            # 2. Anthropic's computer-use models lose click accuracy on images
            #    larger than ~1568px on the long edge (they get internally
            #    downscaled). Downscale the screenshots OURSELVES to a known
            #    size, declare that exact size to the model, and remember the
            #    factor so returned coordinates can be scaled back up to real
            #    screen pixels. This keeps clicks accurate on big displays
            #    (3440x1440 ultrawide, 4K) at any resolution.
            scale = 1.0
            longest = max(src_w, src_h)
            if longest > MAX_SCREENSHOT_EDGE:
                scale = MAX_SCREENSHOT_EDGE / longest

            # Downscale the screenshots in the payload first. Only if at least
            # one real image was actually resized do we declare the reduced size
            # and scale coordinates back — otherwise (e.g. a text-only call with
            # no screenshot) we keep native size and pass coordinates through
            # unchanged.
            downscaled = 0
            if scale < 1.0:
                payload["messages"], downscaled = self._downscale_message_images(
                    payload["messages"], scale,
                )
            if downscaled:
                disp_w = max(1, round(src_w * scale))
                disp_h = max(1, round(src_h * scale))
                coord_scale = src_w / disp_w if disp_w else 1.0
            else:
                disp_w, disp_h = src_w, src_h
                coord_scale = 1.0

            payload["tools"] = build_anthropic_tools(
                display_width=disp_w, display_height=disp_h,
            )
            # Attach Sentinel's own action tools (finish, note, click_text, …)
            # as native Anthropic tools so the agent loop keeps working. The
            # response parser handles these tool_use blocks alongside the
            # computer tool.
            if tools:
                payload["tools"] += self._convert_tools_to_anthropic(tools)
            # The computer_20250124 tool type is gated behind a beta flag.
            # Without this header Anthropic rejects the request with HTTP 400
            # ("Input tag 'computer_20250124' does not match any expected
            # tags"). The version string must match the tool version above.
            headers["anthropic-beta"] = "computer-use-2025-01-24"
        elif tools:
            payload["tools"] = self._convert_tools_to_anthropic(tools)

        logger.info("chat → anthropic/%s%s", model, " [computer-use]" if computer_use_type else "")
        data = self._post_with_retry(
            chat_url,
            headers,
            payload,
            timeout,
            max_retries=max_retries,
            base_delay=retry_base_delay,
            provider_label="anthropic",
        )

        # Parse response — translate computer tool actions to our format,
        # scaling coordinates from the (downscaled) model space back to real
        # screen pixels.
        if computer_use_type == "anthropic":
            return self._parse_anthropic_computer_response(data, coord_scale=coord_scale)
        return self._parse_anthropic_response(data)

    @staticmethod
    def _convert_messages_for_anthropic(
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Split OpenAI-style messages into Anthropic system prompt + message list."""
        system_msg = ""
        converted: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                system_msg += (content if isinstance(content, str) else str(content)) + "\n"
            elif role in ("user", "assistant"):
                converted.append({"role": role, "content": content})
        return system_msg, converted

    @staticmethod
    def _parse_anthropic_response(data: dict[str, Any]) -> str:
        """Extract text or normalised tool-calls from an Anthropic /messages response."""
        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        tool_use_blocks: list[dict[str, Any]] = []

        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_use_blocks.append(block)

        if tool_use_blocks:
            openai_tool_calls = [
                {
                    "id": tb.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tb.get("name", ""),
                        "arguments": json.dumps(tb.get("input", {})),
                    },
                }
                for tb in tool_use_blocks
            ]
            return json.dumps({"tool_calls": openai_tool_calls})

        return "\n".join(text_parts).strip()

    @staticmethod
    def _parse_anthropic_computer_response(
        data: dict[str, Any],
        coord_scale: float = 1.0,
    ) -> str:
        """Parse Anthropic response with native computer tool actions.

        Translates computer_20250124 tool responses to our JSON action format
        so the executor can handle them uniformly. *coord_scale* multiplies the
        returned coordinates to convert from the (possibly downscaled) image
        space the model saw back to real screen pixels.
        """
        from core.computer_use import translate_anthropic_action

        coord_keys = ("x", "y", "from_x", "from_y", "to_x", "to_y")
        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        actions: list[dict[str, Any]] = []

        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                action = translate_anthropic_action(block)
                if action:
                    if coord_scale != 1.0:
                        for key in coord_keys:
                            value = action.get(key)
                            if isinstance(value, (int, float)):
                                action[key] = int(round(value * coord_scale))
                    # Store the original id from the tool_use block
                    action["_original_id"] = block.get("id", "")
                    actions.append(action)
                else:
                    # Handle malformed tool_use blocks by creating a default tool_call
                    # This ensures graceful degradation when responses are incomplete
                    actions.append({
                        "action": block.get("name", ""),
                        "_original_id": block.get("id", ""),
                        "_input": block.get("input", {}),
                    })

        if actions:
            # Return as tool_calls format so the engine picks it up
            tool_calls = []
            for action in actions:
                # Check if this is a malformed action (has _id and _input keys)
                if "_id" in action or "_input" in action:
                    # Handle malformed tool_use block
                    tool_calls.append({
                        "id": action.get("_id", ""),
                        "type": "function",
                        "function": {
                            "name": action.get("action", ""),
                            "arguments": json.dumps(action.get("_input", {})),
                        },
                    })
                else:
                    # Handle normal computer use action
                    # Use the original tool_use block's id if available, otherwise use empty string
                    tool_calls.append({
                        "id": action.get("_original_id", ""),
                        "type": "function",
                        "function": {
                            "name": action["action"],
                            "arguments": json.dumps({
                                k: v for k, v in action.items()
                                if k not in ("action", "_original_id")
                            }),
                        },
                    })
            return json.dumps({"tool_calls": tool_calls})

        return "\n".join(text_parts).strip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Networking with retry/backoff
    # ------------------------------------------------------------------

    def _post_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
        *,
        max_retries: int,
        base_delay: float,
        provider_label: str,
    ) -> dict[str, Any]:
        """POST a JSON payload with exponential backoff for transient errors.

        Raises:
            LLMError: With a human-readable message after retries are exhausted
                or on a non-retriable error.

        """
        attempt = 0
        last_exc: Exception | None = None
        last_status: int | None = None
        last_body: str = ""

        while attempt <= max_retries:
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.RequestException,
            ) as exc:
                last_exc = exc
                self._log_request_exc(provider_label, exc, attempt, max_retries)
            else:
                if resp.status_code < HTTP_BAD_REQUEST:
                    return self._parse_response_json(resp, provider_label)
                last_status, last_body = self._classify_error_response(
                    resp,
                    provider_label,
                    attempt,
                    max_retries,
                )

            if attempt >= max_retries:
                break
            delay = min(30.0, base_delay * (2**attempt))
            delay += random.uniform(0, base_delay)  # noqa: S311
            time.sleep(delay)
            attempt += 1

        self._raise_retry_exhausted(last_status, last_body, last_exc, provider_label, max_retries)
        # Unreachable - _raise_retry_exhausted always raises
        return {}  # pragma: no cover

    @staticmethod
    def _log_request_exc(
        provider_label: str,
        exc: Exception,
        attempt: int,
        max_retries: int,
    ) -> None:
        """Log a network-level request failure with attempt context."""
        logger.warning(
            "%s: %s (attempt %d/%d): %s",
            provider_label,
            type(exc).__name__,
            attempt + 1,
            max_retries + 1,
            exc,
        )

    @staticmethod
    def _raise_retry_exhausted(
        last_status: int | None,
        last_body: str,
        last_exc: Exception | None,
        provider_label: str,
        max_retries: int,
    ) -> NoReturn:
        """Raise an LLMError summarising why all retry attempts failed."""
        if last_status is not None:
            raise LLMError(_friendly_http_error(last_status, last_body))
        if last_exc is not None:
            raise LLMError(
                f"{provider_label}: {last_exc.__class__.__name__}: {last_exc}",
            ) from last_exc
        raise LLMError(
            f"{provider_label}: request failed for unknown reasons ({max_retries + 1} attempts)",
        )

    @staticmethod
    def _parse_response_json(resp: Any, provider_label: str) -> dict[str, Any]:
        """Parse a successful HTTP response as JSON, raising LLMError on decode failure."""
        try:
            return resp.json()  # type: ignore[no-any-return]
        except ValueError as exc:
            raise LLMError(f"{provider_label}: provider returned non-JSON body") from exc

    @staticmethod
    def _classify_error_response(
        resp: Any,
        provider_label: str,
        attempt: int,
        max_retries: int,
    ) -> tuple[int, str]:
        """Handle ≥400 HTTP response.

        Raises for non-retriable errors; returns (status, body) for retriable.
        """
        body = (resp.text or "")[:500]
        if resp.status_code not in RETRY_STATUSES:
            raise LLMError(_friendly_http_error(resp.status_code, body))
        logger.warning(  # noqa: E501
            "%s: HTTP %d (attempt %d/%d) — %s",
            provider_label,
            resp.status_code,
            attempt + 1,
            max_retries + 1,
            body[:120],
        )
        return resp.status_code, body

    @staticmethod
    def _build_headers(
        provider_config: dict[str, Any],
        api_key: str,
    ) -> dict[str, str]:
        """Construct HTTP headers from the provider config and API key."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if not provider_config.get("no_auth") and api_key:
            auth_header = provider_config.get("auth_header", "Authorization")
            auth_prefix = provider_config.get("auth_prefix", "Bearer ")
            headers[auth_header] = f"{auth_prefix}{api_key}"
        return headers

    @staticmethod
    def _convert_tools_to_anthropic(
        tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert OpenAI-style tool definitions to Anthropic format.

        OpenAI::

            {"type": "function", "function": {"name": ..., "description": ...,
             "parameters": {...}}}

        Anthropic::

            {"name": ..., "description": ..., "input_schema": {...}}
        """
        anthropic_tools: list[dict[str, Any]] = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append(
                {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get(
                        "parameters",
                        {
                            "type": "object",
                            "properties": {},
                        },
                    ),
                },
            )
        return anthropic_tools

    @staticmethod
    def _make_anthropic_vision_message(
        image_base64: str,
        prompt: str,
    ) -> dict[str, Any]:
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
