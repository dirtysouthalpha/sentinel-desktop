"""Pytest fixture to automatically clear screenshot cache between tests.

This ensures tests that expect object identity from screenshot functions
continue to work without modification.
"""

import pytest

from core.screenshot import clear_screenshot_cache


@pytest.fixture(autouse=True)
def clear_screenshot_cache_before_each_test():
    """Automatically clear the screenshot cache before each test."""
    clear_screenshot_cache()
    yield
    # Optional: also clear after each test
    clear_screenshot_cache()
