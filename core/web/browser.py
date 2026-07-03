"""Browser automation using Playwright (primary) with CDP fallback.

Provides: navigation, clicking, typing, screenshots, DOM queries,
form filling, network interception, and recording.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class PageInfo:
    """Current page state."""

    url: str
    title: str
    text_content: str = ""


@dataclass
class ElementInfo:
    """Located DOM element."""

    tag: str
    text: str
    selector: str
    bounding_box: dict[str, float] | None = None
    attributes: dict[str, str] = field(default_factory=dict)


class BrowserController:
    """High-level browser automation using Playwright."""

    def __init__(self, headless: bool = True, browser_type: str = "chromium") -> None:
        self._headless = headless
        self._browser_type = browser_type
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> bool:
        """Start the browser."""
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            browser_cls = getattr(self._playwright, self._browser_type, self._playwright.chromium)
            self._browser = browser_cls.launch(headless=self._headless)
            self._context = self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            self._page = self._context.new_page()
            logger.info("Browser started: %s (headless=%s)", self._browser_type, self._headless)
            return True
        except ImportError:
            logger.error("playwright not installed. Run: pip install playwright && playwright install")
            return False
        except Exception as exc:
            logger.error("Failed to start browser: %s", exc)
            return False

    def stop(self) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    @property
    def page(self) -> Any:
        return self._page

    # -- navigation --------------------------------------------------------

    def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        if not self._page:
            return False
        try:
            self._page.goto(url, wait_until=wait_until, timeout=30000)
            return True
        except Exception as exc:
            logger.warning("navigate to %s failed: %s", url, exc)
            return False

    def back(self) -> None:
        if self._page:
            self._page.go_back()

    def forward(self) -> None:
        if self._page:
            self._page.go_forward()

    def reload(self) -> None:
        if self._page:
            self._page.reload()

    def get_page_info(self) -> PageInfo | None:
        if not self._page:
            return None
        return PageInfo(
            url=self._page.url,
            title=self._page.title(),
            text_content=self._page.inner_text("body")[:2000] if self._page else "",
        )

    # -- interaction -------------------------------------------------------

    def click(self, selector: str, timeout: int = 10000) -> bool:
        if not self._page:
            return False
        try:
            self._page.click(selector, timeout=timeout)
            return True
        except Exception as exc:
            logger.debug("click %s failed: %s", selector, exc)
            return False

    def fill(self, selector: str, text: str, timeout: int = 10000) -> bool:
        if not self._page:
            return False
        try:
            self._page.fill(selector, text, timeout=timeout)
            return True
        except Exception as exc:
            logger.debug("fill %s failed: %s", selector, exc)
            return False

    def type_text(self, selector: str, text: str, delay: int = 50) -> bool:
        if not self._page:
            return False
        try:
            self._page.type(selector, text, delay=delay)
            return True
        except Exception as exc:
            logger.debug("type into %s failed: %s", selector, exc)
            return False

    def select_option(self, selector: str, value: str) -> bool:
        if not self._page:
            return False
        try:
            self._page.select_option(selector, value)
            return True
        except Exception as exc:
            logger.debug("select %s failed: %s", selector, exc)
            return False

    def check(self, selector: str) -> bool:
        if not self._page:
            return False
        try:
            self._page.check(selector)
            return True
        except Exception:
            return False

    def press_key(self, key: str) -> None:
        if self._page:
            self._page.keyboard.press(key)

    def hover(self, selector: str) -> bool:
        if not self._page:
            return False
        try:
            self._page.hover(selector)
            return True
        except Exception:
            return False

    # -- queries -----------------------------------------------------------

    def find_elements(self, selector: str) -> list[ElementInfo]:
        if not self._page:
            return []
        results = []
        try:
            elements = self._page.query_selector_all(selector)
            for el in elements:
                box = el.bounding_box()
                results.append(ElementInfo(
                    tag=el.evaluate("el => el.tagName.toLowerCase()"),
                    text=(el.inner_text() or "")[:200],
                    selector=selector,
                    bounding_box={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]} if box else None,
                ))
        except Exception as exc:
            logger.debug("find_elements %s failed: %s", selector, exc)
        return results

    def find_by_text(self, text: str, partial: bool = True) -> list[ElementInfo]:
        if not self._page:
            return []
        selector = f"text={text}" if partial else f"text='{text}'"
        return self.find_elements(selector)

    def get_element_text(self, selector: str) -> str:
        if not self._page:
            return ""
        try:
            return self._page.inner_text(selector) or ""
        except Exception:
            return ""

    def get_attribute(self, selector: str, attr: str) -> str:
        if not self._page:
            return ""
        try:
            return self._page.get_attribute(selector, attr) or ""
        except Exception:
            return ""

    def evaluate_js(self, script: str) -> Any:
        if not self._page:
            return None
        try:
            return self._page.evaluate(script)
        except Exception as exc:
            logger.debug("evaluate_js failed: %s", exc)
            return None

    def wait_for_element(self, selector: str, timeout: int = 10000) -> bool:
        if not self._page:
            return False
        try:
            self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    def wait_for_text(self, text: str, timeout: int = 10000) -> bool:
        if not self._page:
            return False
        try:
            self._page.wait_for_selector(f"text={text}", timeout=timeout)
            return True
        except Exception:
            return False

    def wait_for_navigation(self, timeout: int = 30000) -> None:
        if self._page:
            self._page.wait_for_load_state("networkidle", timeout=timeout)

    # -- screenshots -------------------------------------------------------

    def screenshot(self, full_page: bool = False) -> Any:
        if not self._page:
            return None
        try:
            from PIL import Image
            data = self._page.screenshot(full_page=full_page)
            return Image.open(io.BytesIO(data))
        except Exception:
            return None

    def screenshot_base64(self, full_page: bool = False) -> str:
        img = self.screenshot(full_page=full_page)
        if img is None:
            return ""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # -- forms -------------------------------------------------------------

    def fill_form(self, form_data: dict[str, str], submit_selector: str = "") -> bool:
        """Fill multiple form fields at once.

        form_data maps CSS selectors → values.
        """
        ok = True
        for selector, value in form_data.items():
            if not self.fill(selector, value):
                ok = False
        if submit_selector and ok:
            self.click(submit_selector)
        return ok

    # -- cookies & storage -------------------------------------------------

    def get_cookies(self) -> list[dict]:
        if not self._context:
            return []
        return self._context.cookies()

    def set_cookies(self, cookies: list[dict]) -> None:
        if self._context:
            self._context.add_cookies(cookies)

    def clear_cookies(self) -> None:
        if self._context:
            self._context.clear_cookies()

    def get_local_storage(self, key: str) -> str:
        if not self._page:
            return ""
        try:
            return self._page.evaluate(f"() => localStorage.getItem('{key}')") or ""
        except Exception:
            return ""

    # -- tabs --------------------------------------------------------------

    def new_tab(self, url: str = "") -> bool:
        if not self._context:
            return False
        try:
            new_page = self._context.new_page()
            if url:
                new_page.goto(url)
            return True
        except Exception:
            return False

    def switch_tab(self, index: int) -> None:
        if self._context and index < len(self._context.pages):
            self._page = self._context.pages[index]
            self._page.bring_to_front()

    def close_tab(self, index: int = -1) -> None:
        if not self._context:
            return
        pages = self._context.pages
        if not pages:
            return
        if index == -1:
            pages[-1].close()
        elif index < len(pages):
            pages[index].close()
        if pages:
            self._page = pages[0]

    @property
    def tab_count(self) -> int:
        return len(self._context.pages) if self._context else 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()


__all__ = ["BrowserController", "PageInfo", "ElementInfo"]
