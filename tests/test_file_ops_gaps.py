"""Gap tests for file_ops.py — _get_lockdown_root import/error paths."""

from unittest.mock import patch

from core.file_ops import _get_lockdown_root


class TestGetLockdownRootErrors:
    """_get_lockdown_root handles config import and load failures."""

    def test_import_error_returns_none(self) -> None:
        with patch.dict("sys.modules", {"config": None}):
            result = _get_lockdown_root()
        assert result is None

    def test_os_error_returns_none(self) -> None:
        mock_config = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_config.Config.return_value.load.side_effect = OSError("config missing")
        with patch.dict("sys.modules", {"config": mock_config}):
            result = _get_lockdown_root()
        assert result is None
