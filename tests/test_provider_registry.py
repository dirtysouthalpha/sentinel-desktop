"""Tests for the provider registry catalog."""

from core.provider_registry import (
    PROVIDERS,
    get_base_url,
    get_provider,
    get_provider_display_name,
    get_provider_names,
)


def test_catalog_has_expected_providers():
    expected = {
        "openai",
        "anthropic",
        "google",
        "xai",
        "deepseek",
        "openrouter",
        "groq",
        "mistral",
        "together",
        "fireworks",
        "cerebras",
        "perplexity",
        "zai",
        "minimax",
        "moonshot",
        "qwen",
        "cohere",
        "nvidia",
        "huggingface",
        "github",
        "deepinfra",
        "azure_openai",
        "ollama",
        "lmstudio",
        "custom",
    }
    assert expected.issubset(set(PROVIDERS.keys()))


def test_catalog_meets_provider_count_promise():
    # README advertises "20+ LLM providers".
    assert len(PROVIDERS) >= 20


def test_every_provider_has_required_keys():
    for name, p in PROVIDERS.items():
        assert "name" in p, f"{name} missing 'name'"
        assert "chat_endpoint" in p, f"{name} missing 'chat_endpoint'"
        # models_endpoint may be None for manual-only providers; that's fine.


def test_anthropic_is_flagged_native():
    assert PROVIDERS["anthropic"].get("anthropic_native") is True


def test_get_base_url_strips_trailing_slash():
    assert not get_base_url("openai").endswith("/")


def test_custom_provider_uses_custom_url():
    assert get_base_url("custom", "https://example.com/v1/") == "https://example.com/v1"


def test_provider_names_returns_sorted():
    names = get_provider_names()
    assert names == sorted(names)
    assert "openai" in names


def test_get_provider_returns_none_for_unknown():
    assert get_provider("nonexistent_provider") is None


def test_display_name_falls_back_to_key():
    assert get_provider_display_name("nonexistent") == "nonexistent"
    assert "OpenAI" in get_provider_display_name("openai")
