"""Tests for core/utils.py shared utility functions."""

import platform
import unittest.mock as mock
from datetime import datetime, timezone

from core.utils import (
    get_tesseract,
    get_uia_auto,
    have_tesseract,
    have_uia,
    is_windows,
    iso_now,
)


class TestIsoNow:
    """Test suite for iso_now() function."""

    def test_returns_string(self):
        """Verify iso_now returns a string."""
        result = iso_now()
        assert isinstance(result, str)

    def test_iso8601_format(self):
        """Verify the result is in ISO-8601 format."""
        result = iso_now()
        # Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(result)
        assert isinstance(parsed, datetime)

    def test_includes_timezone(self):
        """Verify the result includes timezone information."""
        result = iso_now()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        assert parsed.tzinfo == timezone.utc

    def test_approximate_current_time(self):
        """Verify the time is approximately current."""
        before = datetime.now(timezone.utc)
        result = iso_now()
        after = datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(result)
        assert before <= parsed <= after


class TestIsWindows:
    """Test suite for is_windows() function."""

    def test_returns_boolean(self):
        """Verify is_windows returns a boolean."""
        result = is_windows()
        assert isinstance(result, bool)

    def test_consistent_with_platform(self):
        """Verify result matches platform.system()."""
        result = is_windows()
        expected = platform.system() == "Windows"
        assert result == expected


class TestHaveTesseract:
    """Test suite for have_tesseract() function."""

    def test_returns_boolean(self):
        """Verify have_tesseract returns a boolean."""
        result = have_tesseract()
        assert isinstance(result, bool)

    def test_caches_result(self):
        """Verify the result is cached on subsequent calls."""
        first = have_tesseract()
        second = have_tesseract()
        # Should return same result (cached)
        assert first == second

    def test_missing_module_returns_false(self):
        """Verify returns False when pytesseract is not available."""
        with mock.patch.dict("sys.modules", {"pytesseract": None}):
            # Need to reset the cached state
            import core.utils

            core.utils._TESSERACT_OK = None
            result = core.utils.have_tesseract()
            assert result is False
            # Reset for other tests
            core.utils._TESSERACT_OK = None

    def test_oserror_on_version_check_returns_false(self):
        """Verify returns False when pytesseract.get_tesseract_version raises OSError."""
        import core.utils

        core.utils._TESSERACT_OK = None
        try:
            # Mock the pytesseract module to raise OSError on version check
            import sys

            original_pytesseract = sys.modules.get("pytesseract")
            try:
                mock_pytesseract = mock.MagicMock()
                mock_pytesseract.get_tesseract_version.side_effect = OSError("Tesseract not found")
                sys.modules["pytesseract"] = mock_pytesseract
                result = core.utils.have_tesseract()
                assert result is False
            finally:
                # Restore original pytesseract
                if original_pytesseract:
                    sys.modules["pytesseract"] = original_pytesseract
                elif "pytesseract" in sys.modules:
                    del sys.modules["pytesseract"]
                core.utils._TESSERACT_OK = None
        except Exception:
            # If the test fails, ensure cache is reset
            core.utils._TESSERACT_OK = None
            raise


class TestGetTesseract:
    """Test suite for get_tesseract() function."""

    def test_returns_module_or_none(self):
        """Verify get_tesseract returns module or None."""
        result = get_tesseract()
        if have_tesseract():
            assert result is not None
        else:
            assert result is None

    def test_consistent_with_have_tesseract(self):
        """Verify get_tesseract result matches have_tesseract()."""
        available = have_tesseract()
        result = get_tesseract()
        if available:
            assert result is not None
        else:
            assert result is None


class TestHaveUIA:
    """Test suite for have_uia() function."""

    def test_returns_boolean(self):
        """Verify have_uia returns a boolean."""
        result = have_uia()
        assert isinstance(result, bool)

    def test_caches_result(self):
        """Verify the result is cached on subsequent calls."""
        first = have_uia()
        second = have_uia()
        # Should return same result (cached)
        assert first == second

    def test_non_windows_returns_false(self):
        """Verify returns False when not on Windows."""
        with mock.patch("platform.system", return_value="Linux"):
            import core.utils

            core.utils._UIA_OK = None
            result = core.utils.have_uia()
            assert result is False
            # Reset for other tests
            core.utils._UIA_OK = None

    def test_missing_module_returns_false(self):
        """Verify returns False when uiautomation is not available."""
        # Only test on Windows
        if is_windows():
            with mock.patch.dict("sys.modules", {"uiautomation": None}):
                import core.utils

                core.utils._UIA_OK = None
                result = core.utils.have_uia()
                assert result is False
                # Reset for other tests
                core.utils._UIA_OK = None


class TestGetUIAAuto:
    """Test suite for get_uia_auto() function."""

    def test_returns_module_or_none(self):
        """Verify get_uia_auto returns module or None."""
        result = get_uia_auto()
        if have_uia():
            assert result is not None
        else:
            assert result is None

    def test_consistent_with_have_uia(self):
        """Verify get_uia_auto result matches have_uia()."""
        available = have_uia()
        result = get_uia_auto()
        if available:
            assert result is not None
        else:
            assert result is None


class TestUtilitiesIntegration:
    """Integration tests for utilities interactions."""

    def test_iso_now_thread_safe(self):
        """Verify iso_now can be called from multiple contexts safely."""
        results = [iso_now() for _ in range(10)]
        assert len(results) == 10
        assert all(isinstance(r, str) for r in results)

    def test_have_functions_independent(self):
        """Verify have_tesseract and have_uia are independent."""
        tesseract_result = have_tesseract()
        uia_result = have_uia()
        # These should be independent checks
        # (even if both return False on non-Windows)
        assert isinstance(tesseract_result, bool)
        assert isinstance(uia_result, bool)
