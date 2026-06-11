"""Sentinel Desktop v2 — LLM provider catalog with auto-detection of available models.

Defines 24 providers (cloud & local) with their base URLs, authentication
headers, and model-discovery endpoints.  Most providers follow the
OpenAI-compatible ``/chat/completions`` pattern; Anthropic uses its native
``/messages`` endpoint and is flagged with ``anthropic_native``.

Usage::

    from core.provider_registry import PROVIDERS, fetch_models

    # List all provider keys
    list(PROVIDERS.keys())

    # Fetch live model list from a provider
    models = fetch_models("openai", "sk-...")
"""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider catalog — every entry describes how to reach the provider's API.
# ---------------------------------------------------------------------------
PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "computer_use": "openai",
        "manual_models": [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o3-mini",
            "o4-mini",
            "gpt-4o",
            "gpt-4o-mini",
        ],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "base_url": "https://api.anthropic.com/v1",
        "models_endpoint": None,  # manual model entry
        "auth_header": "x-api-key",
        "auth_prefix": "",
        "chat_endpoint": "/messages",
        "anthropic_native": True,
        "computer_use": "anthropic",
        "manual_models": [
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ],
    },
    "google": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
    },
    "xai": {
        "name": "xAI Grok",
        "base_url": "https://api.x.ai/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "grok-4.3",
            "grok-4.20",
            "grok-4.20-reasoning",
            "grok-4-1-fast-reasoning",
            "grok-4-1-fast-non-reasoning",
        ],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "nexn2": {
        "name": "Nex-N2-Pro (free, OpenRouter)",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "nex-agi/nex-n2-pro:free",
            "nex-agi/nex-n2-pro",
            "nex-agi/nex-n2-mini",
        ],
    },
    "gemma4": {
        "name": "Gemma 4 31B (free, OpenRouter)",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "google/gemma-4-31b-it:free",
            "google/gemma-4-31b-it",
        ],
    },
    "nemotron": {
        "name": "Nemotron 3 Super (free, OpenRouter)",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-super-120b-a12b",
        ],
    },
    "poolside": {
        "name": "Poolside Laguna M.1 (free, OpenRouter)",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "poolside/laguna-m.1:free",
            "poolside/laguna-m.1",
        ],
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
        ],
    },
    "mistral": {
        "name": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "mistral-large-3",
            "mistral-medium-3",
            "mistral-small-3.2",
            "codestral",
            "pixtral-large-2",
        ],
    },
    "together": {
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "fireworks": {
        "name": "Fireworks AI",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "cerebras": {
        "name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "llama3.1-8b",
            "gpt-oss-120b",
            "qwen-3-235b-a22b-instruct-2507",
        ],
    },
    "perplexity": {
        "name": "Perplexity",
        "base_url": "https://api.perplexity.ai",
        "models_endpoint": None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "sonar-pro",
            "sonar",
            "sonar-reasoning",
            "sonar-reasoning-pro",
            "sonar-deep-research",
        ],
    },
    "zai": {
        "name": "Z.ai Coding Plan (GLM)",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "models_endpoint": None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "glm-5",
            "glm-5-pro",
            "glm-5-flash",
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-air",
            "glm-4-plus",
            "glm-4-air",
            "glm-4-flash",
            "glm-z1-air",
            "glm-z1-flash",
        ],
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.io/v1",
        "models_endpoint": None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "MiniMax-M1",
            "MiniMax-Text-01",
            "abab6.5-chat",
            "abab6.5s-chat",
            "abab6.5t-chat",
        ],
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "base_url": "https://api.moonshot.ai/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "kimi-latest",
            "kimi-k2-0905-preview",
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
        ],
    },
    "qwen": {
        "name": "Qwen (Alibaba DashScope)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "qwen3-max",
            "qwen3.5-plus",
            "qwen3.5-flash",
            "qwen3-coder-plus",
            "qwen3-coder-flash",
            "qwen-plus",
            "qwen-turbo",
            "qwq-plus",
        ],
    },
    "cohere": {
        "name": "Cohere",
        "base_url": "https://api.cohere.ai/compatibility/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "manual_models": [
            "command-a-03-2025",
            "command-r-plus",
            "command-r",
            "command-r7b",
        ],
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "huggingface": {
        "name": "HuggingFace Router",
        "base_url": "https://router.huggingface.co/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "github": {
        "name": "GitHub Models",
        "base_url": "https://models.github.ai/inference",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "deepinfra": {
        "name": "DeepInfra",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
    "azure_openai": {
        "name": "Azure OpenAI (use Custom for deployment URL)",
        "base_url": "",
        "models_endpoint": "/models",
        "auth_header": "api-key",
        "auth_prefix": "",
        "chat_endpoint": "/chat/completions",
    },
    "ollama": {
        "name": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "no_auth": True,
    },
    "lmstudio": {
        "name": "LM Studio (local)",
        "base_url": "http://localhost:1234/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
        "no_auth": True,
    },
    "custom": {
        "name": "Custom Endpoint",
        "base_url": "",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "chat_endpoint": "/chat/completions",
    },
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_provider(name: str) -> dict[str, Any] | None:
    """Return the config dict for *name*, or ``None`` if unknown."""
    return PROVIDERS.get(name)


def get_provider_names() -> list[str]:
    """Sorted list of every provider key in the catalog."""
    return sorted(PROVIDERS.keys())


def get_provider_display_name(name: str) -> str:
    """Human-readable provider name."""
    return PROVIDERS.get(name, {}).get("name", name)


def get_base_url(provider_key: str, custom_url: str | None = None) -> str:
    """Resolve the effective base URL for *provider_key*.

    If *custom_url* is truthy, it overrides the catalog URL for **any**
    provider (not just the ``"custom"`` placeholder). This is how the GUI's
    "Base URL" field redirects e.g. Z.ai to its coding-plan endpoint.

    Falls back to the catalog ``base_url`` when no override is provided.
    """
    if custom_url:
        return custom_url.rstrip("/")
    provider = PROVIDERS.get(provider_key, {})
    return provider.get("base_url", "").rstrip("/")


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------


def _fetch_models_raw(url: str, headers: dict[str, str], provider_key: str) -> object | None:
    """GET *url* and return the parsed JSON body, or None on any error."""
    try:
        resp = requests.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.warning("fetch_models(%s): request timed out", provider_key)
    except requests.exceptions.ConnectionError:
        logger.warning("fetch_models(%s): connection error", provider_key)
    except requests.exceptions.HTTPError as exc:
        logger.warning(
            "fetch_models(%s): HTTP %s — %s",
            provider_key,
            exc.response.status_code,
            exc,
        )
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("fetch_models(%s): unexpected %s: %s", provider_key, type(exc).__name__, exc)
    return None


def _extract_model_ids(data: object, provider_key: str) -> list[str] | None:
    """Return sorted model ID strings parsed from *data*, or None if unparseable."""
    models_list = (
        data
        if isinstance(data, list)
        else (
            data.get("data", data.get("models", [])) if isinstance(data, dict) else None  # type: ignore[union-attr]
        )
    )
    if not isinstance(models_list, list):
        logger.warning("fetch_models(%s): unexpected response shape", provider_key)
        return None

    ids: list[str] = []
    for entry in models_list:
        if isinstance(entry, dict):
            mid = entry.get("id") or entry.get("name") or entry.get("model", "")
        else:
            mid = str(entry)
        if mid:
            ids.append(mid)
    return sorted(ids)


def _build_models_request(
    provider: dict[str, Any],
    provider_key: str,
    api_key: str,
    custom_url: str | None,
) -> tuple[str | None, dict[str, str]]:
    """Build the URL and headers for a models endpoint request.

    Args:
        provider: Provider configuration dict.
        provider_key: Provider key for logging.
        api_key: API key for authentication.
        custom_url: Optional custom URL override.

    Returns:
        (url, headers) tuple, or (None, {}) if URL cannot be built.

    """
    base_url = get_base_url(provider_key, custom_url)
    if not base_url:
        logger.warning("fetch_models: no base_url for %r", provider_key)
        return None, {}

    models_endpoint = provider.get("models_endpoint")
    url = f"{base_url}{models_endpoint}"

    headers: dict[str, str] = {}
    if not provider.get("no_auth") and api_key:
        headers[provider["auth_header"]] = f"{provider['auth_prefix']}{api_key}"

    return url, headers


def fetch_models(
    provider_key: str,
    api_key: str = "",
    custom_url: str | None = None,
) -> list[str]:
    """Fetch available model IDs from a provider.

    * For providers whose ``models_endpoint`` is ``None`` the function
      returns either the provider's ``manual_models`` list or an empty list.
    * For providers with a valid ``models_endpoint`` a synchronous ``GET``
      is issued; the JSON response is expected to follow the OpenAI
      ``{ "data": [ { "id": "..." }, ... ] }`` convention.
    * Network / parse errors are caught and logged — the function always
      returns a list (possibly empty).

    Args:
        provider_key: One of the keys in :data:`PROVIDERS`.
        api_key: API key for authentication (may be empty for local providers).
        custom_url: Override base URL for the ``"custom"`` provider.

    Returns:
        Sorted list of model ID strings.

    """
    provider = PROVIDERS.get(provider_key)
    if not provider:
        logger.warning("fetch_models: unknown provider %r", provider_key)
        return []

    # Providers that don't expose a /models endpoint → manual list or empty.
    models_endpoint = provider.get("models_endpoint")
    if models_endpoint is None:
        return sorted(provider.get("manual_models", []))

    url, headers = _build_models_request(provider, provider_key, api_key, custom_url)
    if not url:
        return []

    data = _fetch_models_raw(url, headers, provider_key)
    if data is None:
        return []

    ids = _extract_model_ids(data, provider_key)
    return ids if ids is not None else []
