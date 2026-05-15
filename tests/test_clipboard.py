"""Tests for core/clipboard.py — clipboard read/write."""

from unittest.mock import MagicMock, patch

import pytest

from core.clipboard import clipboard_read, clipboard_write


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level clipboard singleton between tests."""
    import core.clipboard as mod

    original = mod._clipboard
    mod._clipboard = None
    yield
    mod._clipboard = original


# ---------------------------------------------------------------------------
# clipboard_read
# ---------------------------------------------------------------------------


class TestClipboardRead:
    def test_returns_string_on_success(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.paste.return_value = "hello world"
        assert clipboard_read() == "hello world"

    def test_returns_empty_when_no_clipboard(self):
        import core.clipboard as mod

        mod._clipboard = None
        with patch.dict("sys.modules", {"pyperclip": None}):
            # _get_clipboard will fail to import pyperclip
            assert clipboard_read() == ""

    def test_returns_empty_on_exception(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.paste.side_effect = RuntimeError("boom")
        assert clipboard_read() == ""


# ---------------------------------------------------------------------------
# clipboard_write
# ---------------------------------------------------------------------------


class TestClipboardWrite:
    def test_returns_true_on_success(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        assert clipboard_write("test") is True
        mod._clipboard.copy.assert_called_once_with("test")

    def test_returns_false_when_no_clipboard(self):
        import core.clipboard as mod

        mod._clipboard = None
        with patch.dict("sys.modules", {"pyperclip": None}):
            assert clipboard_write("test") is False

    def test_returns_false_on_exception(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.copy.side_effect = RuntimeError("boom")
        assert clipboard_write("test") is False
