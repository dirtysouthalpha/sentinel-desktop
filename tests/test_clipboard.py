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

    def test_returns_none_when_no_clipboard(self):
        import core.clipboard as mod

        mod._clipboard = None
        with patch.object(mod, "pyperclip", None):
            assert clipboard_read() is None

    def test_returns_none_on_exception(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.paste.side_effect = mod._PyperclipException("boom")
        assert clipboard_read() is None


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
        with patch.object(mod, "pyperclip", None):
            assert clipboard_write("test") is False

    def test_returns_false_on_exception(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.copy.side_effect = mod._PyperclipException("boom")
        assert clipboard_write("test") is False

    def test_write_empty_string(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        assert clipboard_write("") is True
        mod._clipboard.copy.assert_called_once_with("")

    def test_write_special_characters(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        special = "!@#$%^&*()_+-=[]{}|;':\",./<>?\n\t\r"
        assert clipboard_write(special) is True
        mod._clipboard.copy.assert_called_once_with(special)

    def test_write_unicode_content(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        unicode_text = "éèê 日本語 \U0001f600"
        assert clipboard_write(unicode_text) is True
        mod._clipboard.copy.assert_called_once_with(unicode_text)

    def test_write_whitespace_only(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        assert clipboard_write("   \t\n  ") is True
        mod._clipboard.copy.assert_called_once_with("   \t\n  ")


# ---------------------------------------------------------------------------
# _get_clipboard lazy initialization
# ---------------------------------------------------------------------------


class TestGetClipboard:
    def test_returns_module_clipboard_when_set(self):
        import core.clipboard as mod

        mock_cb = MagicMock()
        mod._clipboard = mock_cb
        from core.clipboard import _get_clipboard

        assert _get_clipboard() is mock_cb

    def test_lazy_init_from_pyperclip(self):
        import core.clipboard as mod

        mod._clipboard = None
        mock_pyperclip = MagicMock()
        with patch.object(mod, "pyperclip", mock_pyperclip):
            from core.clipboard import _get_clipboard

            result = _get_clipboard()
            assert result is mock_pyperclip
            # Second call should return the same cached value
            result2 = _get_clipboard()
            assert result2 is mock_pyperclip

    def test_returns_none_when_pyperclip_missing(self):
        import core.clipboard as mod

        mod._clipboard = None
        with patch.object(mod, "pyperclip", None):
            from core.clipboard import _get_clipboard

            assert _get_clipboard() is None


# ---------------------------------------------------------------------------
# clipboard_read edge cases
# ---------------------------------------------------------------------------


class TestClipboardReadEdgeCases:
    def test_read_returns_empty_string(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.paste.return_value = ""
        assert clipboard_read() == ""

    def test_read_returns_unicode(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.paste.return_value = "éèê 日本語"
        assert clipboard_read() == "éèê 日本語"

    def test_read_returns_multiline(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        multiline = "line1\nline2\nline3"
        mod._clipboard.paste.return_value = multiline
        assert clipboard_read() == multiline

    def test_read_catches_pyperclip_exception(self):
        import core.clipboard as mod

        mod._clipboard = MagicMock()
        mod._clipboard.paste.side_effect = mod._PyperclipException("clipboard locked")
        assert clipboard_read() is None
