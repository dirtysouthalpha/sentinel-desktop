import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.web import WebCommands


class TestWebCommands:
    def setup_method(self):
        self.cmds = WebCommands()

    @patch("src.commands.web.webbrowser.open")
    def test_open_url(self, mock_open):
        result = self.cmds.open_url("https://example.com")
        assert result.success is True
        assert "example.com" in result.message

    @patch("src.commands.web.webbrowser.open")
    def test_open_url_adds_https(self, mock_open):
        result = self.cmds.open_url("example.com")
        assert result.success is True

    @patch("src.commands.web.requests.get")
    def test_fetch(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, text="<html><title>Test</title><body>Hello world this is a test page</body></html>",
            raise_for_status=lambda: None
        )
        result = self.cmds.fetch("https://example.com")
        assert result.success is True
        assert "Test" in result.message

    @patch("src.commands.web.requests.get")
    def test_brief(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text="<html><title>News</title><body><p>This is a long paragraph about important news that exceeds fifty characters easily.</p></body></html>",
            raise_for_status=lambda: None
        )
        result = self.cmds.brief("https://news.com")
        assert result.success is True
        assert "BRIEF" in result.message

    @patch("src.commands.web.webbrowser.open")
    def test_search(self, mock_open):
        result = self.cmds.search("python tutorials")
        assert result.success is True
        assert "google" in result.message.lower()

    def test_execute_brief_with_url(self):
        with patch.object(self.cmds, "brief") as mock_brief:
            mock_brief.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("brief me on https://example.com")
            mock_brief.assert_called_once()

    def test_execute_open_url(self):
        with patch.object(self.cmds, "open_url") as mock_open:
            mock_open.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("go to example.com")
            mock_open.assert_called_once()

    def test_execute_search(self):
        with patch.object(self.cmds, "search") as mock_search:
            mock_search.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("search for python tutorials")
            mock_search.assert_called_once()

    def test_execute_unknown(self):
        result = self.cmds.execute("fly away")
        assert result.success is False
