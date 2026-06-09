"""Sentinel Desktop v8.0 — Browser Manager.

Embedded controlled browser via Playwright with CDP support. Launches a
managed browser instance the agent drives directly for DOM-aware web
automation. Handles headless/headed mode, page lifecycle, screenshots,
and JavaScript execution.

Playwright is an optional dependency — this module gracefully degrades
when not installed. Install with: pip install sentinel-desktop[web]

Usage::

    from core.browser import BrowserManager

    mgr = BrowserManager()
    page = mgr.open("https://192.168.1.1")
    page.click("#login-button")
    text = page.text_content("#status")
    mgr.close()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Check if Playwright is available
_HAS_PLAYWRIGHT = False
sync_playwright = None  # Define as None for test patching

try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
    )
    from playwright.sync_api import (
        sync_playwright as _sync_playwright,
    )

    # Override the None placeholder with the real import
    sync_playwright = _sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    pass


class BrowserError(Exception):
    """Raised when browser operations fail."""


class BrowserManager:
    """Manages a Playwright browser instance for web automation.

    Handles browser lifecycle (launch, close), page management (tabs),
    and provides high-level web action methods that map to action executor
    actions.

    The manager lazily initializes Playwright on first use. Call close()
    when done to release resources.
    """

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
        slow_mo: float = 0.0,
        viewport: dict[str, int] | None = None,
        ignore_https_errors: bool = False,
    ) -> None:
        """Initialize the browser manager.

        Args:
            headless: Run browser without visible window.
            browser_type: "chromium", "firefox", or "webkit".
            slow_mo: Slow down operations by N milliseconds (for debugging).
            viewport: Override viewport size, e.g. {"width": 1920, "height": 1080}.
            ignore_https_errors: Ignore HTTPS certificate errors (for self-signed certs).
        """
        if not _HAS_PLAYWRIGHT:
            raise BrowserError(
                "Playwright not installed. Install with: pip install playwright && playwright install"
            )

        self.headless = headless
        self.browser_type = browser_type
        self.slow_mo = slow_mo
        self.viewport = viewport or {"width": 1920, "height": 1080}
        self.ignore_https_errors = ignore_https_errors

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages: list[Page] = []
        self._active_page_index: int = 0

    @property
    def is_available(self) -> bool:
        """Whether Playwright is installed and browser is ready."""
        return _HAS_PLAYWRIGHT

    @property
    def is_running(self) -> bool:
        """Whether the browser is currently running."""
        return self._browser is not None and self._browser.is_connected()

    @property
    def active_page(self) -> Page:
        """Get the currently active page/tab.

        Returns:
            The active Playwright Page.

        Raises:
            BrowserError: If no browser or pages are open.
        """
        if not self._pages:
            raise BrowserError("No pages open — call open() first")
        return self._pages[self._active_page_index]

    def launch(self) -> None:
        """Launch the browser instance.

        Creates a persistent context with the configured settings.
        Idempotent — no-op if already running.
        """
        if self.is_running:
            return

        self._playwright = sync_playwright().start()

        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "slow_mo": self.slow_mo,
        }

        if self.browser_type == "firefox":
            self._browser = self._playwright.firefox.launch(**launch_kwargs)
        elif self.browser_type == "webkit":
            self._browser = self._playwright.webkit.launch(**launch_kwargs)
        else:
            self._browser = self._playwright.chromium.launch(**launch_kwargs)

        # Create a context with viewport and HTTPS settings
        context_kwargs: dict[str, Any] = {
            "viewport": self.viewport,
            "ignore_https_errors": self.ignore_https_errors,
        }
        self._context = self._browser.new_context(**context_kwargs)

        logger.info(
            "Browser launched: %s (headless=%s, viewport=%s)",
            self.browser_type,
            self.headless,
            self.viewport,
        )

    def close(self) -> None:
        """Close the browser and release all resources."""
        if self._context:
            try:
                self._context.close()
            except Exception as exc:
                logger.debug("Context close error: %s", exc)
            self._context = None

        if self._browser:
            try:
                self._browser.close()
            except Exception as exc:
                logger.debug("Browser close error: %s", exc)
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as exc:
                logger.debug("Playwright stop error: %s", exc)
            self._playwright = None

        self._pages.clear()
        self._active_page_index = 0
        logger.info("Browser closed")

    def open(self, url: str, wait_until: str = "load") -> dict[str, Any]:
        """Navigate to a URL (web_open action).

        Creates a new page/tab if none exists, or navigates the active page.

        Args:
            url: URL to navigate to.
            wait_until: When to consider navigation complete.
                "load" (default), "domcontentloaded", "networkidle", "commit"

        Returns:
            Dict with success, url, title, and status.
        """
        self._ensure_launched()

        if not self._pages:
            page = self._context.new_page()  # type: ignore
            self._pages.append(page)
            self._active_page_index = 0
        else:
            page = self.active_page

        try:
            response = page.goto(url, wait_until=wait_until, timeout=30000)
            title = page.title()
            status = response.status if response else None

            logger.info("Navigated to %s (status=%s, title=%s)", url, status, title)

            return {
                "success": True,
                "url": page.url,
                "title": title,
                "status": status,
            }
        except Exception as exc:
            logger.warning("Navigation to %s failed: %s", url, exc)
            return {
                "success": False,
                "url": url,
                "error": str(exc),
            }

    def click(
        self,
        selector: str | None = None,
        text: str | None = None,
        role: str | None = None,
        name: str | None = None,
        button: str = "left",
        click_count: int = 1,
        timeout: float = 10000,
    ) -> dict[str, Any]:
        """Click an element (web_click action).

        Finds element by CSS selector, text content, or ARIA role + name.
        Auto-scrolls element into view before clicking.

        Args:
            selector: CSS selector to find element.
            text: Text content to match (exact or contains).
            role: ARIA role (e.g., "button", "link", "textbox").
            name: Accessible name (used with role).
            button: "left", "right", or "middle".
            click_count: Number of clicks (1 for single, 2 for double).
            timeout: Maximum time to wait for element in ms.

        Returns:
            Dict with success and description of what was clicked.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            locator = self._resolve_locator(page, selector, text, role, name)

            # Wait for element and scroll into view
            locator.wait_for(state="visible", timeout=timeout)
            locator.scroll_into_view_if_needed()

            # Perform the click
            kwargs: dict[str, Any] = {}
            if button == "right":
                kwargs["button"] = "right"
            elif button == "middle":
                kwargs["button"] = "middle"
            if click_count > 1:
                kwargs["click_count"] = click_count

            locator.click(**kwargs)

            desc = self._describe_target(selector, text, role, name)
            logger.info("Clicked: %s", desc)

            return {"success": True, "target": desc, "button": button}

        except Exception as exc:
            desc = self._describe_target(selector, text, role, name)
            logger.warning("Click failed on %s: %s", desc, exc)
            return {"success": False, "target": desc, "error": str(exc)}

    def type_text(
        self,
        text: str,
        selector: str | None = None,
        label: str | None = None,
        role: str | None = None,
        name: str | None = None,
        clear: bool = True,
        timeout: float = 10000,
    ) -> dict[str, Any]:
        """Type text into a form field (web_type action).

        Finds the input by selector, label text, or ARIA role. Optionally
        clears existing content before typing.

        Args:
            text: Text to type.
            selector: CSS selector for the input.
            label: Label text associated with the input.
            role: ARIA role (e.g., "textbox", "searchbox").
            name: Accessible name for the input.
            clear: Whether to clear existing content first.
            timeout: Maximum time to wait for element in ms.

        Returns:
            Dict with success and target description.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            # Try to find by label if no selector provided
            if selector:
                locator = page.locator(selector)
            elif label:
                # Find input associated with a label
                locator = page.get_by_label(label)
            elif role or name:
                locator = self._resolve_locator(page, None, None, role, name)
            else:
                return {"success": False, "error": "No selector, label, role, or name provided"}

            locator.wait_for(state="visible", timeout=timeout)

            if clear:
                locator.fill("")
            locator.type(text, delay=10)

            desc = selector or label or f"role={role}, name={name}"
            logger.info("Typed %d chars into %s", len(text), desc)

            return {"success": True, "target": desc, "text_length": len(text)}

        except Exception as exc:
            desc = selector or label or f"role={role}, name={name}"
            logger.warning("Type failed on %s: %s", desc, exc)
            return {"success": False, "target": desc, "error": str(exc)}

    def read(
        self,
        selector: str | None = None,
        full_page: bool = False,
    ) -> dict[str, Any]:
        """Read text content from the page (web_read action).

        Args:
            selector: CSS selector to read from. If None, reads full page.
            full_page: Whether to read the entire page body.

        Returns:
            Dict with success, text content, and character count.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            if selector:
                locator = page.locator(selector)
                text = locator.inner_text()
            else:
                text = page.inner_text("body")

            logger.info("Read %d chars from %s", len(text), selector or "page")

            return {
                "success": True,
                "text": text,
                "char_count": len(text),
                "source": selector or "full_page",
            }

        except Exception as exc:
            logger.warning("Read failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def wait_for(
        self,
        selector: str | None = None,
        text: str | None = None,
        state: str = "visible",
        timeout: float = 30000,
    ) -> dict[str, Any]:
        """Wait for an element or condition (web_wait_for action).

        Args:
            selector: CSS selector to wait for.
            text: Text content to wait for on the page.
            state: "visible", "hidden", "attached", "detached".
            timeout: Maximum wait time in ms.

        Returns:
            Dict with success and what was waited for.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            if selector:
                page.wait_for_selector(selector, state=state, timeout=timeout)
                desc = f"selector={selector}"
            elif text:
                page.wait_for_function(
                    f"document.body.innerText.includes({repr(text)})",
                    timeout=timeout,
                )
                desc = f"text={text!r}"
            else:
                page.wait_for_load_state("networkidle", timeout=timeout)
                desc = "networkidle"

            return {"success": True, "waited_for": desc}

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def screenshot(self, selector: str | None = None, full_page: bool = False) -> dict[str, Any]:
        """Capture a screenshot of the browser viewport (web_screenshot action).

        Args:
            selector: CSS selector to screenshot a specific element.
            full_page: Capture the entire scrollable page.

        Returns:
            Dict with success and base64 image data.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            import base64
            import io

            from PIL import Image

            if selector:
                locator = page.locator(selector)
                buf = locator.screenshot()
            else:
                buf = page.screenshot(full_page=full_page)

            img = Image.open(io.BytesIO(buf))
            # Convert to base64 for compatibility with rest of engine
            img_io = io.BytesIO()
            img.save(img_io, format="PNG")
            b64 = base64.b64encode(img_io.getvalue()).decode("utf-8")

            return {"success": True, "image_size": img.size, "image_base64": b64}

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def eval_js(self, expression: str) -> dict[str, Any]:
        """Execute JavaScript in browser context (web_eval_js action).

        Args:
            expression: JavaScript expression to evaluate.

        Returns:
            Dict with success and the return value.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            result = page.evaluate(expression)
            return {"success": True, "result": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def extract(self, selector: str = "table", format: str = "json") -> dict[str, Any]:
        """Extract structured data from the page (web_extract action).

        Args:
            selector: CSS selector for the data container (default: "table").
            format: Output format ("json" or "text").

        Returns:
            Dict with success and extracted data.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            if selector == "table" or selector.startswith("table"):
                # Extract table data as list of dicts
                data = page.evaluate("""(sel) => {
                    const tables = document.querySelectorAll(sel);
                    const results = [];
                    tables.forEach(table => {
                        const headers = Array.from(table.querySelectorAll('th')).map(th => th.innerText.trim());
                        const rows = table.querySelectorAll('tbody tr');
                        rows.forEach(row => {
                            const cells = Array.from(row.querySelectorAll('td')).map(td => td.innerText.trim());
                            if (headers.length && cells.length) {
                                const obj = {};
                                headers.forEach((h, i) => obj[h] = cells[i] || '');
                                results.push(obj);
                            } else if (cells.length) {
                                results.push(cells);
                            }
                        });
                    });
                    return results;
                }""", selector)
            else:
                # Generic element text extraction
                data = page.inner_text(selector)

            return {"success": True, "data": data, "format": format}

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def download(self, url: str | None = None, save_path: str | None = None) -> dict[str, Any]:
        """Download a file from the browser (web_download action).

        Args:
            url: URL to download. If None, triggers download from current page.
            save_path: Local path to save the file.

        Returns:
            Dict with success and file path.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            if url:
                # Navigate to download URL
                with page.expect_download(timeout=60000) as download_info:
                    page.goto(url)
                download = download_info.value
            else:
                return {"success": False, "error": "No URL provided and no download triggered"}

            if save_path:
                download.save_as(save_path)
                return {"success": True, "path": save_path, "filename": download.suggested_filename}
            else:
                # Save to temp
                path = download.path()
                return {"success": True, "path": str(path), "filename": download.suggested_filename}

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def upload(self, selector: str, file_paths: list[str]) -> dict[str, Any]:
        """Upload files to a web form (web_upload action).

        Args:
            selector: CSS selector for the file input element.
            file_paths: List of file paths to upload.

        Returns:
            Dict with success and file count.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            page.set_input_files(selector, file_paths)
            return {"success": True, "files_uploaded": len(file_paths)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def tabs(self, action: str = "list", index: int | None = None, url: str | None = None) -> dict[str, Any]:
        """Manage browser tabs (web_tabs action).

        Args:
            action: "list", "switch", "new", "close".
            index: Tab index for switch/close.
            url: URL for new tab.

        Returns:
            Dict with success and tab information.
        """
        self._ensure_launched()

        if action == "list":
            tabs_info = []
            for i, page in enumerate(self._pages):
                tabs_info.append({
                    "index": i,
                    "url": page.url,
                    "title": page.title(),
                    "active": i == self._active_page_index,
                })
            return {"success": True, "tabs": tabs_info, "count": len(tabs_info)}

        elif action == "switch":
            if index is None or index >= len(self._pages):
                return {"success": False, "error": f"Invalid tab index: {index}"}
            self._active_page_index = index
            self._pages[index].bring_to_front()
            return {"success": True, "active_index": index}

        elif action == "new":
            page = self._context.new_page()  # type: ignore
            self._pages.append(page)
            self._active_page_index = len(self._pages) - 1
            if url:
                page.goto(url, wait_until="load", timeout=30000)
            return {"success": True, "index": self._active_page_index, "url": url}

        elif action == "close":
            if index is None:
                return {"success": False, "error": "No tab index provided"}
            if len(self._pages) <= 1:
                return {"success": False, "error": "Cannot close the last tab"}
            self._pages[index].close()
            self._pages.pop(index)
            self._active_page_index = min(self._active_page_index, len(self._pages) - 1)
            return {"success": True, "remaining": len(self._pages)}

        else:
            return {"success": False, "error": f"Unknown tab action: {action}"}

    def get_cookies(self) -> list[dict[str, Any]]:
        """Get all cookies from the browser context.

        Returns:
            List of cookie dicts.
        """
        self._ensure_launched()
        return self._context.cookies()  # type: ignore

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Set cookies in the browser context.

        Args:
            cookies: List of cookie dicts (from get_cookies format).
        """
        self._ensure_launched()
        self._context.add_cookies(cookies)  # type: ignore

    def _ensure_launched(self) -> None:
        """Ensure the browser is launched, launching if needed."""
        if not self.is_running:
            self.launch()

    def _resolve_locator(
        self,
        page: Page,
        selector: str | None,
        text: str | None,
        role: str | None,
        name: str | None,
    ):
        """Resolve a Playwright locator from various targeting methods."""
        if selector:
            return page.locator(selector)
        if text:
            return page.get_by_text(text)
        if role:
            if name:
                return page.get_by_role(role, name=name)
            return page.get_by_role(role)
        raise BrowserError("No targeting method provided (selector, text, role, or name)")

    @staticmethod
    def _describe_target(
        selector: str | None,
        text: str | None,
        role: str | None,
        name: str | None,
    ) -> str:
        """Describe what was targeted for logging."""
        if selector:
            return f"selector={selector}"
        if text:
            return f"text={text!r}"
        if role:
            return f"role={role}, name={name}"
        return "unknown"

    # -------------------------------------------------------------------
    # MFA Support (v13.0)
    # -------------------------------------------------------------------

    def detect_mfa(self) -> dict[str, Any]:
        """Detect MFA on the current page.

        Returns:
            Dict with detection results including has_mfa, mfa_fields,
            confidence, and detection_methods.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            from core.web.mfa_detector import MFADetector

            # Gather page data for MFA detection
            page_data = {
                "url": page.url,
                "title": page.title(),
                "text": page.inner_text("body"),
                "inputs": [],
                "forms": [],
            }

            # Extract input fields
            inputs = page.query_selector_all("input")
            for inp in inputs:
                try:
                    input_data = {
                        "type": inp.get_attribute("type") or "text",
                        "name": inp.get_attribute("name") or "",
                        "id": inp.get_attribute("id") or "",
                        "placeholder": inp.get_attribute("placeholder") or "",
                        "maxlength": inp.get_attribute("maxlength"),
                        "inputmode": inp.get_attribute("inputmode") or "",
                        "autocomplete": inp.get_attribute("autocomplete") or "",
                        "aria-label": inp.get_attribute("aria-label") or "",
                        "title": inp.get_attribute("title") or "",
                    }
                    page_data["inputs"].append(input_data)
                except Exception:
                    continue

            # Extract forms
            forms = page.query_selector_all("form")
            for form in forms:
                try:
                    form_data = {
                        "action": form.get_attribute("action") or "",
                        "method": form.get_attribute("method") or "",
                        "id": form.get_attribute("id") or "",
                    }
                    page_data["forms"].append(form_data)
                except Exception:
                    continue

            # Run MFA detection
            detector = MFADetector()
            result = detector.detect_mfa(page_data)

            return {
                "success": True,
                "has_mfa": result.has_mfa,
                "mfa_fields": [
                    {
                        "element_id": f.element_id,
                        "input_type": f.input_type.value,
                        "label": f.label,
                        "confidence": f.confidence,
                    }
                    for f in result.mfa_fields
                ],
                "detection_methods": result.detection_methods,
                "confidence": result.confidence,
                "page_type": result.page_type,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": f"MFA detection failed: {exc}",
                "has_mfa": False,
            }

    def handle_mfa(
        self,
        *,
        code: str | None = None,
        user_callback: callable | None = None,
        service_name: str | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
        """Handle MFA on the current page.

        Args:
            code: Optional MFA code to use directly.
            user_callback: Optional async callback to prompt user for code.
            service_name: Optional service name for TOTP lookup.
            selector: Optional selector for MFA input field.

        Returns:
            Dict with success, method_used, and code_used.
        """
        self._ensure_launched()
        page = self.active_page

        try:
            from core.web.mfa_handler import MFAHandler, MFAResolutionMethod

            # Detect MFA fields
            detection_result = self.detect_mfa()
            if not detection_result.get("success"):
                return {
                    "success": False,
                    "error": "MFA detection failed",
                    "has_mfa": False,
                }

            if not detection_result.get("has_mfa"):
                return {
                    "success": False,
                    "error": "No MFA detected on page",
                    "has_mfa": False,
                }

            # Get MFA fields
            mfa_fields_data = detection_result.get("mfa_fields", [])
            if not mfa_fields_data:
                return {
                    "success": False,
                    "error": "No MFA fields found",
                    "has_mfa": True,
                }

            # Use provided selector or detected field
            target_selector = selector or mfa_fields_data[0].get("element_id")
            if not target_selector:
                return {
                    "success": False,
                    "error": "No MFA field selector available",
                    "has_mfa": True,
                }

            # If code provided directly, use it
            if code:
                result = self._fill_mfa_code(target_selector, code)
                if result.get("success"):
                    result["method_used"] = MFAResolutionMethod.USER_PROMPT.value
                    result["code_used"] = code
                return result

            # Try to resolve MFA using handler
            handler = MFAHandler()

            # Try each resolution strategy
            for field_data in mfa_fields_data:
                from core.web.mfa_detector import MFAField, MFAInputType

                field = MFAField(
                    element_id=field_data.get("element_id", ""),
                    input_type=MFAInputType[field_data.get("input_type", "TOTP").upper()],
                    label=field_data.get("label"),
                    confidence=field_data.get("confidence", 0.0),
                )

                resolution_result = handler.resolve_mfa(
                    field,
                    page.url,
                    user_callback,
                    service_name,
                )

                if resolution_result.success and resolution_result.code_used:
                    # Fill the code
                    fill_result = self._fill_mfa_code(
                        target_selector,
                        resolution_result.code_used,
                    )
                    if fill_result.get("success"):
                        fill_result["method_used"] = resolution_result.method_used.value
                        fill_result["code_used"] = resolution_result.code_used
                        return fill_result

            # All strategies failed
            return {
                "success": False,
                "error": "Unable to resolve MFA automatically",
                "has_mfa": True,
                "hint": "Provide code directly or set up user_callback",
            }

        except Exception as exc:
            return {
                "success": False,
                "error": f"MFA handling failed: {exc}",
                "has_mfa": True,
            }

    def _fill_mfa_code(self, selector: str, code: str) -> dict[str, Any]:
        """Fill an MFA code into an input field and submit."""
        self._ensure_launched()
        page = self.active_page

        try:
            # Find and fill the input
            locator = page.locator(selector)
            locator.wait_for(state="visible", timeout=5000)
            locator.fill(code)

            # Try to submit (look for submit button)
            submit_buttons = page.query_selector_all('button[type="submit"], input[type="submit"]')
            if submit_buttons:
                submit_buttons[0].click()

            return {
                "success": True,
                "output": f"MFA code filled ({len(code)} digits)",
            }

        except Exception as exc:
            return {
                "success": False,
                "error": f"Failed to fill MFA code: {exc}",
            }
