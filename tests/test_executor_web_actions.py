"""Tests for web action dispatch through ActionExecutor.

Verifies that web_open, web_click, web_type, web_read, etc. route correctly
through the executor's dispatch table to BrowserManager.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Patch Playwright availability before importing action_executor
BROWSER_PATH = "core.browser"


@pytest.fixture
def executor_with_mock_browser():
    """ActionExecutor with a mocked BrowserManager."""
    mock_browser = MagicMock()
    mock_browser.open.return_value = {
        "success": True,
        "url": "https://example.com",
        "title": "Test",
    }
    mock_browser.click.return_value = {"success": True, "target": "selector=#btn"}
    mock_browser.type_text.return_value = {"success": True, "text_length": 5}
    mock_browser.read.return_value = {"success": True, "text": "Hello", "char_count": 5}
    mock_browser.extract.return_value = {"success": True, "data": []}
    mock_browser.wait_for.return_value = {"success": True, "waited_for": "networkidle"}
    mock_browser.screenshot.return_value = {"success": True, "image_size": (100, 100)}
    mock_browser.eval_js.return_value = {"success": True, "result": 42}
    mock_browser.download.return_value = {"success": True, "path": "/tmp/f.pdf"}
    mock_browser.upload.return_value = {"success": True, "files_uploaded": 1}
    mock_browser.tabs.return_value = {"success": True, "tabs": [], "count": 0}

    with patch(f"{BROWSER_PATH}._HAS_PLAYWRIGHT", True):
        from core.action_executor import ActionExecutor

        executor = ActionExecutor()
        executor._browser_manager = mock_browser

        yield executor, mock_browser


class TestWebOpenDispatch:
    def test_dispatches_to_browser_open(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_open", "url": "https://example.com"})
        assert result["success"] is True
        mock_browser.open.assert_called_once_with("https://example.com", wait_until="load")

    def test_passes_wait_until(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        executor.execute_sync(
            {"action": "web_open", "url": "https://x.com", "wait_until": "networkidle"}
        )
        mock_browser.open.assert_called_once_with("https://x.com", wait_until="networkidle")


class TestWebClickDispatch:
    def test_dispatches_to_browser_click(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_click", "selector": "#btn"})
        assert result["success"] is True
        mock_browser.click.assert_called_once()
        call_kwargs = mock_browser.click.call_args[1]
        assert call_kwargs["selector"] == "#btn"

    def test_passes_all_params(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        executor.execute_sync(
            {
                "action": "web_click",
                "selector": "#btn",
                "button": "right",
                "click_count": 2,
            }
        )
        call_kwargs = mock_browser.click.call_args[1]
        assert call_kwargs["button"] == "right"
        assert call_kwargs["click_count"] == 2


class TestWebTypeDispatch:
    def test_dispatches_to_browser_type_text(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_type", "text": "hello", "selector": "#q"})
        assert result["success"] is True
        mock_browser.type_text.assert_called_once()
        call_kwargs = mock_browser.type_text.call_args[1]
        assert call_kwargs["text"] == "hello"
        assert call_kwargs["selector"] == "#q"


class TestWebReadDispatch:
    def test_dispatches_to_browser_read(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_read"})
        assert result["success"] is True
        mock_browser.read.assert_called_once_with(selector=None, full_page=False)

    def test_with_selector(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        executor.execute_sync({"action": "web_read", "selector": "#content"})
        mock_browser.read.assert_called_once_with(selector="#content", full_page=False)


class TestWebExtractDispatch:
    def test_dispatches_to_browser_extract(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_extract"})
        assert result["success"] is True
        mock_browser.extract.assert_called_once_with(selector="table", format="json")


class TestWebWaitForDispatch:
    def test_dispatches_to_browser_wait_for(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_wait_for", "timeout": 5.0})
        assert result["success"] is True
        mock_browser.wait_for.assert_called_once()
        call_kwargs = mock_browser.wait_for.call_args[1]
        assert call_kwargs["timeout"] == 5000.0  # seconds → ms


class TestWebScreenshotDispatch:
    def test_dispatches_to_browser_screenshot(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_screenshot", "full_page": True})
        assert result["success"] is True
        mock_browser.screenshot.assert_called_once_with(selector=None, full_page=True)


class TestWebEvalJsDispatch:
    def test_dispatches_to_browser_eval_js(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_eval_js", "expression": "1+1"})
        assert result["success"] is True
        mock_browser.eval_js.assert_called_once_with(expression="1+1")


class TestWebDownloadDispatch:
    def test_dispatches_to_browser_download(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync(
            {
                "action": "web_download",
                "url": "https://x.com/f.pdf",
                "save_path": "/tmp/f.pdf",
            }
        )
        assert result["success"] is True
        mock_browser.download.assert_called_once_with(
            url="https://x.com/f.pdf", save_path="/tmp/f.pdf"
        )


class TestWebUploadDispatch:
    def test_dispatches_to_browser_upload(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync(
            {
                "action": "web_upload",
                "selector": "#file",
                "file_paths": ["/tmp/a.pdf"],
            }
        )
        assert result["success"] is True
        mock_browser.upload.assert_called_once_with(selector="#file", file_paths=["/tmp/a.pdf"])


class TestWebTabsDispatch:
    def test_dispatches_to_browser_tabs(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_tabs", "tab_action": "list"})
        assert result["success"] is True
        mock_browser.tabs.assert_called_once_with(action="list", index=None, url=None)


class TestWebActionsNotDryRunBlocked:
    """Web actions should execute even in dry-run mode (they're read-like)."""

    def test_web_open_not_blocked_in_dry_run(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        executor.dry_run = True
        result = executor.execute_sync({"action": "web_open", "url": "https://example.com"})
        # web_open is NOT in STATE_CHANGING_ACTIONS, so it should still execute
        assert result["success"] is True
        mock_browser.open.assert_called_once()

    def test_web_read_not_blocked_in_dry_run(self, executor_with_mock_browser):
        executor, mock_browser = executor_with_mock_browser
        executor.dry_run = True
        result = executor.execute_sync({"action": "web_read"})
        assert result["success"] is True
        mock_browser.read.assert_called_once()


class TestUnknownWebAction:
    def test_unknown_action_returns_error(self, executor_with_mock_browser):
        executor, _ = executor_with_mock_browser
        result = executor.execute_sync({"action": "web_teleport"})
        assert result["success"] is False
        assert "Unknown action" in result["output"]


class TestBrowserLazyInit:
    """Browser manager is lazily initialized on first web action."""

    def test_browser_property_creates_instance(self):
        with patch(f"{BROWSER_PATH}._HAS_PLAYWRIGHT", True):
            from core.action_executor import ActionExecutor

            executor = ActionExecutor()
            assert executor._browser_manager is None

            # Access the property
            bm = executor.browser
            assert bm is not None
            assert executor._browser_manager is bm

    def test_browser_reuses_existing(self):
        with patch(f"{BROWSER_PATH}._HAS_PLAYWRIGHT", True):
            from core.action_executor import ActionExecutor

            executor = ActionExecutor()
            bm1 = executor.browser
            bm2 = executor.browser
            assert bm1 is bm2
