"""
Sentinel Desktop v2 — LLM provider catalog with auto-detection of available models.

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
        manual = provider.get("manual_models", [])
        return sorted(manual)

    # Resolve base URL.
    base_url = get_base_url(provider_key, custom_url)
    if not base_url:
        logger.warning("fetch_models: no base_url for %r", provider_key)
        return []

    url = f"{base_url}{models_endpoint}"

    # Build headers (same logic as LLMClient.chat).
    headers: dict[str, str] = {}
    if not provider.get("no_auth") and api_key:
        headers[provider["auth_header"]] = f"{provider['auth_prefix']}{api_key}"

    try:
        resp = requests.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        logger.warning("fetch_models(%s): request timed out", provider_key)
        return []
    except requests.exceptions.ConnectionError:
        logger.warning("fetch_models(%s): connection error", provider_key)
        return []
    except requests.exceptions.HTTPError as exc:
        logger.warning(
            "fetch_models(%s): HTTP %s — %s",
            provider_key,
            exc.response.status_code,
            exc,
        )
        return []
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning("fetch_models(%s): %s", provider_key, exc)
        return []

    # Parse response — tolerate a few shapes.
    if isinstance(data, list):
        models_list = data
    else:
        models_list = data.get("data", data.get("models", []))
    if not isinstance(models_list, list):
        # Some providers wrap the list differently.
        if isinstance(data, list):
            models_list = data
        else:
            logger.warning(
                "fetch_models(%s): unexpected response shape",
                provider_key,
            )
            return []

    ids: list[str] = []
    for entry in models_list:
        if isinstance(entry, dict):
            mid = entry.get("id") or entry.get("name") or entry.get("model", "")
        else:
            mid = str(entry)
        if mid:
            ids.append(mid)

    return sorted(ids)
