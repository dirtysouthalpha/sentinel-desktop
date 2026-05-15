"""Tests for the provider registry catalog."""

from unittest.mock import MagicMock, patch

from core.provider_registry import (
    PROVIDERS,
    fetch_models,
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


# ---------------------------------------------------------------------------
# fetch_models
# ---------------------------------------------------------------------------


def test_fetch_models_unknown_provider():
    assert fetch_models("nonexistent_provider") == []


def test_fetch_models_manual_only_provider():
    models = fetch_models("anthropic")
    assert "claude-opus-4-7" in models
    assert models == sorted(models)


def test_fetch_models_manual_provider_no_key():
    models = fetch_models("perplexity")
    assert "sonar-pro" in models


def test_fetch_models_no_base_url():
    """Provider with empty base_url and no custom_url returns []."""
    assert fetch_models("custom") == []


def test_fetch_models_custom_url_with_no_endpoint(monkeypatch):
    """anthropic has models_endpoint=None, so custom_url is ignored."""
    models = fetch_models("anthropic", custom_url="https://example.com")
    assert "claude-opus-4-7" in models


def test_fetch_models_http_success():
    with patch("core.provider_registry.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = fetch_models("openai", api_key="sk-test")

    assert models == ["gpt-4o", "gpt-4o-mini"]
    mock_get.assert_called_once()
    # Verify auth header was set
    headers = mock_get.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer sk-test"


def test_fetch_models_http_timeout():
    import requests

    with patch(
        "core.provider_registry.requests.get",
        side_effect=requests.exceptions.Timeout("timed out"),
    ):
        assert fetch_models("openai", "sk-test") == []


def test_fetch_models_connection_error():
    import requests

    with patch(
        "core.provider_registry.requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        assert fetch_models("openai", "sk-test") == []


def test_fetch_models_http_error():
    import requests

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)

    with patch("core.provider_registry.requests.get", return_value=mock_resp):
        assert fetch_models("openai", "sk-test") == []


def test_fetch_models_nonstandard_response_list():
    """Provider returning a bare list should still be parsed."""
    with patch("core.provider_registry.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "model-a"}, {"id": "model-b"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = fetch_models("deepinfra", "key")
    assert models == ["model-a", "model-b"]


def test_fetch_models_no_auth_provider():
    """Ollama has no_auth=True — no auth header should be sent."""
    with patch("core.provider_registry.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"id": "llama3"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = fetch_models("ollama")

    assert "llama3" in models
    headers = mock_get.call_args[1]["headers"]
    assert headers == {}


def test_get_base_url_falls_back_to_catalog():
    assert get_base_url("openai") == "https://api.openai.com/v1"


def test_get_base_url_empty_custom_falls_back():
    assert get_base_url("openai", "") == "https://api.openai.com/v1"


def test_get_base_url_none_custom_falls_back():
    assert get_base_url("openai", None) == "https://api.openai.com/v1"
