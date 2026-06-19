"""Gap tests for core/browser.py — covers uncovered lines:
40-46 (import success block), 146 (webkit launch), 167-168/174-175/181-182
(close() exception handlers), 274 (middle button), 328 (get_by_label),
557-558 (download except), 657 (_ensure_launched → launch), 736-737/749-750
(detect_mfa exception handlers), 824/833 (handle_mfa early returns),
870-877 (MFA resolution fill path), 887-888 (handle_mfa outer except).
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

PLAYWRIGHT_PATH = "core.browser"


# ── shared fixture helpers ────────────────────────────────────────────────────


def _make_page(url: str = "https://example.com") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.title.return_value = "Test"
    page.inner_text.return_value = ""
    return page


def _launched_manager(**kw) -> MagicMock:
    """Return a BrowserManager with injected mock Playwright internals."""
    from core.browser import BrowserManager

    kwargs = {"headless": True, "browser_type": "chromium"}
    kwargs.update(kw)

    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = _make_page()
    mock_context.new_page.return_value = mock_page
    mock_pw.chromium.launch.return_value = mock_browser
    mock_pw.webkit.launch.return_value = mock_browser
    mock_pw.firefox.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context

    with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True):
        mgr = BrowserManager(**kwargs)

    mgr._playwright = mock_pw
    mgr._browser = mock_browser
    mgr._context = mock_context
    mgr._pages = [mock_page]
    mgr._active_page_index = 0
    return mgr


# ── Lines 40-46 — Playwright import success block ───────────────────────────


class TestPlaywrightImportSuccessBlock:
    """Lines 40-46 — cover the successful-import path in the try block."""

    def test_reload_with_fake_playwright_sets_has_playwright_true(self):
        """Reload core.browser with fake playwright installed → _HAS_PLAYWRIGHT True."""
        import core.browser as browser_mod

        orig_has_pw = browser_mod._HAS_PLAYWRIGHT

        # Build a minimal fake playwright.sync_api module
        fake_sync_api = MagicMock()
        fake_sync_api.Browser = MagicMock
        fake_sync_api.BrowserContext = MagicMock
        fake_sync_api.Page = MagicMock
        fake_sync_api.Playwright = MagicMock
        fake_sync_playwright = MagicMock()
        fake_sync_api.sync_playwright = fake_sync_playwright

        try:
            with patch.dict(
                sys.modules,
                {
                    "playwright": MagicMock(),
                    "playwright.sync_api": fake_sync_api,
                },
            ):
                importlib.reload(browser_mod)
                assert browser_mod._HAS_PLAYWRIGHT is True
                assert browser_mod.sync_playwright is fake_sync_playwright
        finally:
            # Restore to original state
            importlib.reload(browser_mod)
            assert browser_mod._HAS_PLAYWRIGHT is orig_has_pw


# ── Line 146 — chromium branch in launch() ────────────────────────────────────


class TestChromiumLaunch:
    """Line 146 — BrowserManager.launch() chromium else-branch."""

    def test_chromium_launch_called_when_browser_type_is_chromium(self):
        """Line 146 — browser_type defaults to chromium → else branch executes."""
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = _make_page()
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_browser.is_connected.return_value = True
        mock_pw.chromium.launch.return_value = mock_browser

        mock_sync_pw = MagicMock()
        mock_sync_pw.return_value.start.return_value = mock_pw

        with (
            patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True),
            patch(f"{PLAYWRIGHT_PATH}.sync_playwright", mock_sync_pw),
        ):
            from core.browser import BrowserManager

            mgr = BrowserManager(headless=True, browser_type="chromium")
            mgr.launch()

        assert mock_pw.chromium.launch.call_count == 1


# ── Lines 167-168, 174-175, 181-182 — close() exception handlers ─────────────


class TestCloseExceptionHandlers:
    """Lines 167-168, 174-175, 181-182 — close() swallows exceptions."""

    def _make_mgr(self):
        from core.browser import BrowserManager

        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True):
            mgr = BrowserManager(headless=True)
        return mgr

    def test_context_close_exception_is_swallowed(self):
        """Line 167-168 — _context.close() raises; close() continues."""
        mgr = self._make_mgr()
        mgr._context = MagicMock()
        mgr._context.close.side_effect = Exception("context error")
        mgr._browser = MagicMock()
        mgr._playwright = MagicMock()

        # Should not raise
        mgr.close()

        assert mgr._context is None
        assert mgr._browser is None

    def test_browser_close_exception_is_swallowed(self):
        """Lines 174-175 — _browser.close() raises; close() continues."""
        mgr = self._make_mgr()
        mgr._context = None  # already cleaned up
        mgr._browser = MagicMock()
        mgr._browser.close.side_effect = Exception("browser crash")
        mgr._playwright = MagicMock()

        mgr.close()

        assert mgr._browser is None

    def test_playwright_stop_exception_is_swallowed(self):
        """Lines 181-182 — _playwright.stop() raises; close() completes."""
        mgr = self._make_mgr()
        mgr._context = None
        mgr._browser = None
        mgr._playwright = MagicMock()
        mgr._playwright.stop.side_effect = Exception("pw stop error")

        mgr.close()

        assert mgr._playwright is None


# ── Line 274 — middle button click ───────────────────────────────────────────


class TestMiddleButtonClick:
    """Line 274 — click() with button='middle' sets kwargs['button']='middle'."""

    def test_middle_button_click_passes_button_kwarg(self):
        mgr = _launched_manager()
        page = mgr.active_page
        mock_locator = MagicMock()
        page.locator.return_value = mock_locator

        result = mgr.click(selector="#link", button="middle")

        click_kwargs = mock_locator.click.call_args[1]
        assert click_kwargs.get("button") == "middle"
        assert result["success"] is True


# ── Line 328 — type_text with label (get_by_label path) ─────────────────────


class TestTypeTextGetByLabel:
    """Line 328 — type_text(label=...) uses page.get_by_label()."""

    def test_label_path_calls_get_by_label(self):
        mgr = _launched_manager()
        page = mgr.active_page
        mock_locator = MagicMock()
        page.get_by_label.return_value = mock_locator

        result = mgr.type_text("hello", label="Username")

        page.get_by_label.assert_called_once_with("Username")
        assert result["success"] is True


# ── Line 328 — type_text with role/name (_resolve_locator path) ──────────────


class TestTypeTextRoleNamePath:
    """Line 328 — type_text(role=...) uses _resolve_locator()."""

    def test_role_name_calls_resolve_locator(self):
        mgr = _launched_manager()
        mock_locator = MagicMock()
        with patch.object(mgr, "_resolve_locator", return_value=mock_locator) as mock_resolve:
            result = mgr.type_text("hello", role="textbox", name="Username")
        mock_resolve.assert_called_once()
        assert result["success"] is True


# ── Lines 557-558 — download except block ─────────────────────────────────────


class TestDownloadExceptBlock:
    """Lines 557-558 — download handler outer except returns error dict."""

    def test_download_exception_returns_error(self):
        mgr = _launched_manager()
        page = mgr.active_page

        # Make goto raise to trigger the outer except
        page.goto.side_effect = Exception("network failure during download")

        result = mgr.download(url="https://example.com/file.zip")

        assert result["success"] is False
        assert "network failure" in result["error"]


# ── Line 657 — _ensure_launched calls launch() when not running ───────────────


class TestEnsureLaunched:
    """Line 657 — _ensure_launched() calls launch() when is_running is False."""

    def test_ensure_launched_calls_launch_when_not_running(self):
        from core.browser import BrowserManager

        with patch(f"{PLAYWRIGHT_PATH}._HAS_PLAYWRIGHT", True):
            mgr = BrowserManager(headless=True)

        # is_running is False when no browser
        assert mgr.is_running is False

        with patch.object(mgr, "launch") as mock_launch:
            mgr._ensure_launched()
            mock_launch.assert_called_once()


# ── Lines 736-737, 749-750 — detect_mfa exception handlers in loops ──────────


class TestDetectMfaExceptionHandlers:
    """Lines 736-737, 749-750 — bad input/form elements are skipped via continue."""

    def test_bad_input_element_is_skipped(self):
        """Line 736-737 — inp.get_attribute raises → continue; other inputs still processed."""
        mgr = _launched_manager()
        page = mgr.active_page

        bad_inp = MagicMock()
        bad_inp.get_attribute.side_effect = Exception("stale element")

        good_inp = MagicMock()
        good_inp.get_attribute.side_effect = lambda attr: {
            "type": "text",
            "name": "user",
            "id": "u",
            "placeholder": "",
            "maxlength": None,
            "inputmode": "",
            "autocomplete": "",
            "aria-label": "",
            "title": "",
        }.get(attr, "")

        def _query_selector_all(selector):
            if selector == "input":
                return [bad_inp, good_inp]
            return []

        page.query_selector_all.side_effect = _query_selector_all
        page.inner_text.return_value = "Login"

        result = mgr.detect_mfa()

        # Should succeed even though the first input element raised
        assert result["success"] is True

    def test_bad_form_element_is_skipped(self):
        """Lines 749-750 — form.get_attribute raises → continue."""
        mgr = _launched_manager()
        page = mgr.active_page

        bad_form = MagicMock()
        bad_form.get_attribute.side_effect = Exception("detached form element")

        def _query_selector_all(selector):
            if selector == "form":
                return [bad_form]
            return []

        page.query_selector_all.side_effect = _query_selector_all
        page.inner_text.return_value = ""

        result = mgr.detect_mfa()

        # Form error is swallowed; detection still runs
        assert result["success"] is True


# ── Lines 824, 833 — handle_mfa early returns ────────────────────────────────


class TestHandleMfaEarlyReturns:
    """Lines 824, 833 — no fields / no selector → early return error dicts."""

    def test_no_mfa_fields_returns_error(self):
        """Line 824 — empty mfa_fields list → early return."""
        mgr = _launched_manager()

        with patch.object(
            mgr,
            "detect_mfa",
            return_value={
                "success": True,
                "has_mfa": True,
                "mfa_fields": [],
            },
        ):
            result = mgr.handle_mfa()

        assert result["success"] is False
        assert "No MFA fields found" in result["error"]
        assert result["has_mfa"] is True

    def test_no_mfa_field_selector_returns_error(self):
        """Line 833 — field element_id is empty/None → early return."""
        mgr = _launched_manager()

        with patch.object(
            mgr,
            "detect_mfa",
            return_value={
                "success": True,
                "has_mfa": True,
                "mfa_fields": [
                    {"element_id": "", "input_type": "totp", "label": None, "confidence": 0.9}
                ],
            },
        ):
            result = mgr.handle_mfa(selector=None)

        assert result["success"] is False
        assert "No MFA field selector available" in result["error"]
        assert result["has_mfa"] is True


# ── Lines 870-877 — MFA resolution fill path ─────────────────────────────────


class TestHandleMfaResolutionFillPath:
    """Lines 870-877 — handler.resolve_mfa() succeeds → _fill_mfa_code called."""

    def test_resolution_success_fills_and_returns(self):
        mgr = _launched_manager()

        fields_data = [
            {
                "element_id": "#otp",
                "input_type": "TOTP",
                "label": "Code",
                "confidence": 0.95,
            }
        ]

        with patch.object(
            mgr,
            "detect_mfa",
            return_value={
                "success": True,
                "has_mfa": True,
                "mfa_fields": fields_data,
            },
        ):
            mock_fill_result = {"success": True, "output": "filled"}

            with patch.object(mgr, "_fill_mfa_code", return_value=mock_fill_result) as mock_fill:
                mock_resolution = MagicMock()
                mock_resolution.success = True
                mock_resolution.code_used = "123456"
                mock_resolution.method_used.value = "totp"

                mock_handler = MagicMock()
                mock_handler.resolve_mfa.return_value = mock_resolution

                with patch("core.web.mfa_handler.MFAHandler", return_value=mock_handler):
                    result = mgr.handle_mfa()

        mock_fill.assert_called_once_with("#otp", "123456")
        assert result["success"] is True
        assert result["code_used"] == "123456"


# ── Lines 887-888 — handle_mfa outer except ──────────────────────────────────


class TestHandleMfaOuterExcept:
    """Lines 887-888 — unexpected exception in handle_mfa returns error dict."""

    def test_outer_exception_returns_error_dict(self):
        mgr = _launched_manager()

        # detect_mfa raises an unexpected error inside handle_mfa's try block
        with patch.object(mgr, "detect_mfa", side_effect=RuntimeError("unexpected boom")):
            result = mgr.handle_mfa()

        assert result["success"] is False
        assert "MFA handling failed" in result["error"]
        assert result["has_mfa"] is True
