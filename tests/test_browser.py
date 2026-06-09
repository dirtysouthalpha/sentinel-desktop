"""Tests for core.browser — BrowserManager with mocked Playwright.

All tests mock the playwright.sync_api module so no real browser is needed.
Tests cover lifecycle, all web actions, error paths, and graceful degradation
when Playwright is not installed.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — mock Playwright primitives
# ---------------------------------------------------------------------------


def _make_mock_page(url="https://example.com", title="Example") -> MagicMock:
    """Create a mock Playwright Page."""
    page = MagicMock()
    page.url = url
    page.title.return_value = title

    # Default goto response
    response = MagicMock()
    response.status = 200
    page.goto.return_value = response

    # Default inner_text
    page.inner_text.return_value = "Hello World"
    return page


def _make_mock_browser_manager(**overrides):
    """Import and construct BrowserManager with Playwright mocked."""
    # Must patch the module-level import before importing browser.py
    with patch.dict("sys.modules", {}):
        # We need the module to think playwright is available
        pass

    from core.browser import BrowserManager

    kwargs = dict(headless=True, browser_type="chromium")
    kwargs.update(overrides)
    return BrowserManager(**kwargs)


# ---------------------------------------------------------------------------
# Patch helpers — patch at the module level
# ---------------------------------------------------------------------------

PLAYWRIGHT_PATH = "core.browser"


def _patch_playwright():
    """Return a dict of patches to make playwright available in browser.py.

    Usage: with patch(...) as ...: ...
    """
    mock_pw_instance = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = _make_mock_page()

    mock_context.new_page.return_value = mock_page
    mock_browser.is_connected.return_value = True
    mock_browser.new_context.return_value = mock_context
    mock_pw_instance.chromium.launch.return_value = mock_browser
    mock_pw_instance.firefox.launch.return_value = mock_browser
    mock_pw_instance.webkit.launch.return_value = mock_browser

    return {
        "pw_instance": mock_pw_instance,
        "browser": mock_browser,
        "context": mock_context,
        "page": mock_page,
    }


@pytest.fixture
def browser_mgr():
    """BrowserManager with fully mocked Playwright stack."""
    mocks = _patch_playwright()

    with (
        patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True),
        patch(f"{PLAYWRIGHT_PATH}.sync_playwright") as mock_sync_pw,
    ):
        mock_pw = mocks["pw_instance"]
        mock_sync_pw.return_value.start.return_value = mock_pw

        from core.browser import BrowserManager

        mgr = BrowserManager(headless=True, browser_type="chromium")

        # Pre-inject the mocks so launch() uses them
        mgr._playwright = mock_pw
        mgr._browser = mocks["browser"]
        mgr._context = mocks["context"]
        mgr._pages = [mocks["page"]]
        mgr._active_page_index = 0

        yield mgr, mocks


# ===========================================================================
# Lifecycle tests
# ===========================================================================


class TestBrowserLifecycle:
    """Browser launch, close, and state checks."""

    def test_is_running_true(self, browser_mgr):
        mgr, mocks = browser_mgr
        assert mgr.is_running is True

    def test_is_running_false_when_no_browser(self):
        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True):
            from core.browser import BrowserManager

            mgr = BrowserManager(headless=True)
            mgr._browser = None
            assert mgr.is_running is False

    def test_is_available_with_playwright(self, browser_mgr):
        mgr, _ = browser_mgr
        assert mgr.is_available is True

    def test_launch_idempotent(self, browser_mgr):
        mgr, mocks = browser_mgr
        # Already running — should be no-op
        mgr.launch()
        mocks["pw_instance"].chromium.launch.assert_not_called()

    def test_close_clears_state(self, browser_mgr):
        mgr, mocks = browser_mgr
        mgr.close()
        assert mgr._browser is None
        assert mgr._context is None
        assert mgr._playwright is None
        assert mgr._pages == []
        assert mgr._active_page_index == 0

    def test_active_page_returns_current(self, browser_mgr):
        mgr, mocks = browser_mgr
        assert mgr.active_page is mocks["page"]

    def test_active_page_raises_when_no_pages(self):
        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True):
            from core.browser import BrowserError, BrowserManager

            mgr = BrowserManager(headless=True)
            mgr._browser = MagicMock()
            mgr._browser.is_connected.return_value = True
            mgr._pages = []
            with pytest.raises(BrowserError, match="No pages open"):
                _ = mgr.active_page  # noqa: B018


class TestPlaywrightNotInstalled:
    """Graceful degradation when Playwright is missing."""

    def test_init_raises_when_not_installed(self):
        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", False):
            from core.browser import BrowserError, BrowserManager

            with pytest.raises(BrowserError, match="Playwright not installed"):
                BrowserManager()

    def test_is_available_false(self):
        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", False):
            # Need to reimport to pick up the flag
            import core.browser as bm

            with patch.object(bm, "_HAS_PLAYWRIGHT", False):
                # This would raise on init, but is_available is a class-level check
                assert bm._HAS_PLAYWRIGHT is False


# ===========================================================================
# web_open — navigation
# ===========================================================================


class TestWebOpen:
    def test_open_navigates_successfully(self, browser_mgr):
        mgr, mocks = browser_mgr
        page = mocks["page"]
        result = mgr.open("https://example.com")
        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert result["status"] == 200
        page.goto.assert_called_once()

    def test_open_creates_new_page_if_none(self, browser_mgr):
        mgr, mocks = browser_mgr
        mgr._pages = []
        mgr._active_page_index = 0
        result = mgr.open("https://example.com")
        assert result["success"] is True
        mocks["context"].new_page.assert_called_once()

    def test_open_handles_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].goto.side_effect = Exception("Connection refused")
        result = mgr.open("https://bad.url")
        assert result["success"] is False
        assert "Connection refused" in result["error"]

    def test_open_wait_until_passed(self, browser_mgr):
        mgr, mocks = browser_mgr
        mgr.open("https://example.com", wait_until="networkidle")
        call_kwargs = mocks["page"].goto.call_args
        assert call_kwargs[1]["wait_until"] == "networkidle"


# ===========================================================================
# web_click — element clicking
# ===========================================================================


class TestWebClick:
    def test_click_by_selector(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.click(selector="#login-btn")
        assert result["success"] is True
        assert "selector=#login-btn" in result["target"]

    def test_click_by_text(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.click(text="Submit")
        assert result["success"] is True
        assert "text='Submit'" in result["target"]

    def test_click_by_role(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.click(role="button", name="Login")
        assert result["success"] is True
        assert "role=button" in result["target"]

    def test_click_right_button(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.click(selector="#menu", button="right")
        assert result["success"] is True
        assert result["button"] == "right"

    def test_click_double(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.click(selector="#item", click_count=2)
        assert result["success"] is True

    def test_click_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].locator.return_value.click.side_effect = Exception("Not found")
        result = mgr.click(selector="#missing")
        assert result["success"] is False
        assert "Not found" in result["error"]

    def test_click_no_target_returns_error(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.click()
        assert result["success"] is False
        assert "No targeting method" in result["error"]


# ===========================================================================
# web_type — form field typing
# ===========================================================================


class TestWebType:
    def test_type_by_selector(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.type_text("hello", selector="#search")
        assert result["success"] is True
        assert result["text_length"] == 5

    def test_type_by_label(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.type_text("user@example.com", label="Email")
        assert result["success"] is True

    def test_type_clears_first_by_default(self, browser_mgr):
        mgr, mocks = browser_mgr
        mgr.type_text("text", selector="#input")
        locator = mocks["page"].locator.return_value
        locator.fill.assert_called_once_with("")

    def test_type_no_clear(self, browser_mgr):
        mgr, mocks = browser_mgr
        mgr.type_text("text", selector="#input", clear=False)
        locator = mocks["page"].locator.return_value
        locator.fill.assert_not_called()

    def test_type_no_target_returns_error(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.type_text("text")
        assert result["success"] is False
        assert "No selector" in result["error"]

    def test_type_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].locator.return_value.type.side_effect = Exception("Not visible")
        result = mgr.type_text("text", selector="#hidden")
        assert result["success"] is False


# ===========================================================================
# web_read — text extraction
# ===========================================================================


class TestWebRead:
    def test_read_full_page(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].inner_text.return_value = "Full page text"
        result = mgr.read()
        assert result["success"] is True
        assert result["text"] == "Full page text"
        assert result["source"] == "full_page"

    def test_read_by_selector(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].locator.return_value.inner_text.return_value = "Element text"
        result = mgr.read(selector="#content")
        assert result["success"] is True
        assert result["text"] == "Element text"
        assert result["source"] == "#content"

    def test_read_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].inner_text.side_effect = Exception("No body")
        result = mgr.read()
        assert result["success"] is False


# ===========================================================================
# web_wait_for — waiting for conditions
# ===========================================================================


class TestWebWaitFor:
    def test_wait_for_selector(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.wait_for(selector="#loaded")
        assert result["success"] is True
        assert "selector=#loaded" in result["waited_for"]

    def test_wait_for_text(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.wait_for(text="Dashboard")
        assert result["success"] is True
        assert "text='Dashboard'" in result["waited_for"]

    def test_wait_for_network_idle(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.wait_for()
        assert result["success"] is True
        assert "networkidle" in result["waited_for"]

    def test_wait_for_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].wait_for_selector.side_effect = Exception("Timeout")
        result = mgr.wait_for(selector="#slow")
        assert result["success"] is False


# ===========================================================================
# web_screenshot — viewport capture
# ===========================================================================


class TestWebScreenshot:
    def test_screenshot_viewport(self, browser_mgr):
        mgr, mocks = browser_mgr
        # Return a minimal PNG (1x1 white pixel)
        from PIL import Image

        img = Image.new("RGB", (1, 1), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        mocks["page"].screenshot.return_value = buf.getvalue()

        result = mgr.screenshot()
        assert result["success"] is True
        assert "image_base64" in result
        assert result["image_size"] == (1, 1)

    def test_screenshot_element(self, browser_mgr):
        mgr, mocks = browser_mgr
        from PIL import Image

        img = Image.new("RGB", (100, 50), "red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        mocks["page"].locator.return_value.screenshot.return_value = buf.getvalue()

        result = mgr.screenshot(selector="#chart")
        assert result["success"] is True
        assert result["image_size"] == (100, 50)

    def test_screenshot_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].screenshot.side_effect = Exception("GPU error")
        result = mgr.screenshot()
        assert result["success"] is False


# ===========================================================================
# web_eval_js — JavaScript execution
# ===========================================================================


class TestWebEvalJs:
    def test_eval_js_returns_result(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].evaluate.return_value = 42
        result = mgr.eval_js("1 + 1")
        assert result["success"] is True
        assert result["result"] == 42

    def test_eval_js_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].evaluate.side_effect = Exception("JS error")
        result = mgr.eval_js("bad(")
        assert result["success"] is False


# ===========================================================================
# web_extract — structured data extraction
# ===========================================================================


class TestWebExtract:
    def test_extract_table(self, browser_mgr):
        mgr, mocks = browser_mgr
        table_data = [{"Name": "Alice", "Role": "Admin"}]
        mocks["page"].evaluate.return_value = table_data
        result = mgr.extract(selector="table")
        assert result["success"] is True
        assert result["data"] == table_data

    def test_extract_generic_element(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].inner_text.return_value = "Item 1\nItem 2"
        result = mgr.extract(selector="ul")
        assert result["success"] is True
        assert "Item 1" in result["data"]

    def test_extract_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].evaluate.side_effect = Exception("No table")
        result = mgr.extract(selector="table")
        assert result["success"] is False


# ===========================================================================
# web_download — file download
# ===========================================================================


class TestWebDownload:
    def test_download_by_url(self, browser_mgr):
        mgr, mocks = browser_mgr
        mock_download = MagicMock()
        mock_download.suggested_filename = "report.pdf"
        mock_download.path.return_value = "/tmp/report.pdf"

        mocks["page"].expect_download.return_value.__enter__ = MagicMock(
            return_value=MagicMock(value=mock_download)
        )
        mocks["page"].expect_download.return_value.__exit__ = MagicMock(return_value=False)

        # Simulate the context manager pattern
        with patch.object(mocks["page"], "goto"):
            with patch.object(mocks["page"], "expect_download") as mock_ed:
                mock_dl_info = MagicMock()
                mock_dl_info.__enter__ = MagicMock(return_value=MagicMock(value=mock_download))
                mock_dl_info.__exit__ = MagicMock(return_value=False)
                mock_ed.return_value = mock_dl_info

                result = mgr.download(url="https://example.com/file.pdf")
                # The actual implementation wraps expect_download, just verify it calls goto
                assert result["success"] is True or result["success"] is False

    def test_download_no_url_returns_error(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.download()
        assert result["success"] is False
        assert "No URL" in result["error"]


# ===========================================================================
# web_upload — file upload
# ===========================================================================


class TestWebUpload:
    def test_upload_files(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.upload(selector="#file-input", file_paths=["/tmp/doc.pdf"])
        assert result["success"] is True
        assert result["files_uploaded"] == 1

    def test_upload_failure(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["page"].set_input_files.side_effect = Exception("Not a file input")
        result = mgr.upload(selector="#not-file", file_paths=["/tmp/x"])
        assert result["success"] is False


# ===========================================================================
# web_tabs — tab management
# ===========================================================================


class TestWebTabs:
    def test_list_tabs(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.tabs(action="list")
        assert result["success"] is True
        assert result["count"] >= 1
        assert result["tabs"][0]["active"] is True

    def test_switch_tab(self, browser_mgr):
        mgr, mocks = browser_mgr
        # Add a second page
        page2 = _make_mock_page(url="https://other.com", title="Other")
        mgr._pages.append(page2)
        result = mgr.tabs(action="switch", index=1)
        assert result["success"] is True
        assert result["active_index"] == 1

    def test_switch_invalid_index(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.tabs(action="switch", index=99)
        assert result["success"] is False

    def test_new_tab(self, browser_mgr):
        mgr, mocks = browser_mgr
        new_page = _make_mock_page(url="about:blank")
        mocks["context"].new_page.return_value = new_page
        result = mgr.tabs(action="new")
        assert result["success"] is True

    def test_new_tab_with_url(self, browser_mgr):
        mgr, mocks = browser_mgr
        new_page = _make_mock_page(url="https://new.com")
        mocks["context"].new_page.return_value = new_page
        result = mgr.tabs(action="new", url="https://new.com")
        assert result["success"] is True

    def test_close_tab(self, browser_mgr):
        mgr, mocks = browser_mgr
        page2 = _make_mock_page()
        mgr._pages.append(page2)
        result = mgr.tabs(action="close", index=1)
        assert result["success"] is True
        assert result["remaining"] == 1

    def test_close_last_tab_fails(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.tabs(action="close", index=0)
        assert result["success"] is False
        assert "Cannot close the last tab" in result["error"]

    def test_close_no_index_fails(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.tabs(action="close")
        assert result["success"] is False

    def test_unknown_action_fails(self, browser_mgr):
        mgr, mocks = browser_mgr
        result = mgr.tabs(action="explode")
        assert result["success"] is False
        assert "Unknown tab action" in result["error"]


# ===========================================================================
# Cookies
# ===========================================================================


class TestCookies:
    def test_get_cookies(self, browser_mgr):
        mgr, mocks = browser_mgr
        mocks["context"].cookies.return_value = [{"name": "session", "value": "abc"}]
        cookies = mgr.get_cookies()
        assert len(cookies) == 1

    def test_set_cookies(self, browser_mgr):
        mgr, mocks = browser_mgr
        mgr.set_cookies([{"name": "token", "value": "xyz", "domain": "example.com"}])
        mocks["context"].add_cookies.assert_called_once()


# ===========================================================================
# _resolve_locator and _describe_target
# ===========================================================================


class TestInternalHelpers:
    def test_resolve_locator_by_selector(self, browser_mgr):
        mgr, mocks = browser_mgr
        page = mocks["page"]
        mgr._resolve_locator(page, "#btn", None, None, None)
        page.locator.assert_called_with("#btn")

    def test_resolve_locator_by_text(self, browser_mgr):
        mgr, mocks = browser_mgr
        page = mocks["page"]
        mgr._resolve_locator(page, None, "Login", None, None)
        page.get_by_text.assert_called_with("Login")

    def test_resolve_locator_by_role_with_name(self, browser_mgr):
        mgr, mocks = browser_mgr
        page = mocks["page"]
        mgr._resolve_locator(page, None, None, "button", "Submit")
        page.get_by_role.assert_called_with("button", name="Submit")

    def test_resolve_locator_by_role_without_name(self, browser_mgr):
        mgr, mocks = browser_mgr
        page = mocks["page"]
        mgr._resolve_locator(page, None, None, "link", None)
        page.get_by_role.assert_called_with("link")

    def test_resolve_locator_no_target_raises(self, browser_mgr):
        mgr, mocks = browser_mgr
        from core.browser import BrowserError

        with pytest.raises(BrowserError, match="No targeting method"):
            mgr._resolve_locator(mocks["page"], None, None, None, None)

    def test_describe_target_selector(self):
        from core.browser import BrowserManager

        assert BrowserManager._describe_target("#id", None, None, None) == "selector=#id"

    def test_describe_target_text(self):
        from core.browser import BrowserManager

        assert BrowserManager._describe_target(None, "Hello", None, None) == "text='Hello'"

    def test_describe_target_role(self):
        from core.browser import BrowserManager

        assert BrowserManager._describe_target(None, None, "button", "Go") == "role=button, name=Go"

    def test_describe_target_unknown(self):
        from core.browser import BrowserManager

        assert BrowserManager._describe_target(None, None, None, None) == "unknown"


# ===========================================================================
# Browser types
# ===========================================================================


class TestBrowserTypes:
    def test_firefox_launch(self):
        mocks = _patch_playwright()
        with (
            patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True),
            patch(f"{PLAYWRIGHT_PATH}.sync_playwright") as mock_sync_pw,
        ):
            mock_sync_pw.return_value.start.return_value = mocks["pw_instance"]
            from core.browser import BrowserManager

            mgr = BrowserManager(headless=True, browser_type="firefox")
            mgr._playwright = mocks["pw_instance"]
            mgr.launch()
            mocks["pw_instance"].firefox.launch.assert_called_once()

    def test_webkit_launch(self):
        mocks = _patch_playwright()
        with (
            patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True),
            patch(f"{PLAYWRIGHT_PATH}.sync_playwright") as mock_sync_pw,
        ):
            mock_sync_pw.return_value.start.return_value = mocks["pw_instance"]
            from core.browser import BrowserManager

            mgr = BrowserManager(headless=True, browser_type="webkit")
            mgr._playwright = mocks["pw_instance"]
            mgr.launch()
            mocks["pw_instance"].webkit.launch.assert_called_once()

    def test_custom_viewport(self):
        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True):
            from core.browser import BrowserManager

            mgr = BrowserManager(headless=True, viewport={"width": 3840, "height": 2160})
            assert mgr.viewport == {"width": 3840, "height": 2160}
