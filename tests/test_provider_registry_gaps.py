"""Gap tests for provider_registry.py — unexpected response shape."""

from unittest.mock import MagicMock, patch

from core.provider_registry import fetch_models


class TestFetchModelsUnexpectedShape:
    """fetch_models handles non-list response data gracefully."""

    def test_dict_with_non_list_data_field(self) -> None:
        """Dict with string 'data' field triggers unexpected shape warning."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "not a list"}
        mock_response.raise_for_status = MagicMock()
        with patch("core.provider_registry.httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_client.return_value)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = mock_response
            models = fetch_models("openai", api_key="sk-test")
        assert models == []

    def test_dict_with_no_data_or_models_key(self) -> None:
        """Dict without data/models keys and non-list .get result."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"other": 42}
        mock_response.raise_for_status = MagicMock()
        with patch("core.provider_registry.httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_client.return_value)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = mock_response
            models = fetch_models("openai", api_key="sk-test")
        # {"other": 42} -> data.get("data", data.get("models", [])) -> []
        # [] is a list, so it passes isinstance check and returns []
        assert models == []
