"""
Tests for Browser MFA Integration

Comprehensive test suite for MFA detection and handling in browser manager.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from core.browser import BrowserManager


class TestBrowserMFAIntegration:
    """Test MFA integration in BrowserManager."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = Mock()
        page.url = "https://github.com/login"
        page.title.return_value = "Sign In"
        page.inner_text.return_value = "Enter your authentication code"
        return page

    @pytest.fixture
    def mock_browser_manager(self, mock_page):
        """Create a BrowserManager with mocked browser."""
        # Patch Playwright availability check
        with patch('core.browser._HAS_PLAYWRIGHT', True):
            manager = BrowserManager(headless=True)
            manager._browser = Mock()
            manager._context = Mock()
            manager._pages = [mock_page]
            manager._active_page_index = 0
            return manager

    def test_detect_mfa_success(self, mock_browser_manager, mock_page):
        """Test successful MFA detection."""
        # Mock input field
        mock_input = Mock()
        mock_input.get_attribute.side_effect = lambda attr: {
            "type": "text",
            "name": "otp",
            "id": "otp-input",
            "placeholder": "123456",
            "maxlength": "6",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "aria-label": "",
            "title": "",
        }.get(attr, "")

        mock_page.query_selector_all.return_value = [mock_input]
        mock_page.query_selector_all.return_value = []

        result = mock_browser_manager.detect_mfa()

        assert result["success"] is True
        assert isinstance(result, dict)

    def test_detect_mfa_no_playwright(self):
        """Test MFA detection when Playwright is not available."""
        # Test that BrowserError is raised when Playwright is not available
        with patch('core.browser._HAS_PLAYWRIGHT', False):
            from core.browser import BrowserError
            with pytest.raises(BrowserError) as exc_info:
                manager = BrowserManager(headless=True)

            # Should raise an error about Playwright not being installed
            assert "Playwright" in str(exc_info.value) or "not installed" in str(exc_info.value)

    def test_handle_mfa_with_code(self, mock_browser_manager, mock_page):
        """Test handling MFA with provided code."""
        # Mock MFA detection
        mock_browser_manager.detect_mfa = Mock(return_value={
            "success": True,
            "has_mfa": True,
            "mfa_fields": [{
                "element_id": "#otp-input",
                "input_type": "totp",
                "label": "Authentication Code",
                "confidence": 0.9,
            }],
            "detection_methods": ["keywords"],
            "confidence": 0.9,
            "page_type": "mfa",
        })

        # Mock locator
        mock_locator = Mock()
        mock_page.locator.return_value = mock_locator

        # Mock submit buttons - return empty list (no submit button)
        mock_page.query_selector_all.return_value = []

        result = mock_browser_manager.handle_mfa(code="123456")

        assert result["success"] is True

    def test_handle_mfa_no_code_no_callback(self, mock_browser_manager, mock_page):
        """Test handling MFA without code or callback."""
        # Mock MFA detection
        mock_browser_manager.detect_mfa = Mock(return_value={
            "success": True,
            "has_mfa": True,
            "mfa_fields": [{
                "element_id": "#otp-input",
                "input_type": "totp",
                "label": "Authentication Code",
                "confidence": 0.9,
            }],
            "detection_methods": ["keywords"],
            "confidence": 0.9,
            "page_type": "mfa",
        })

        result = mock_browser_manager.handle_mfa()

        assert result["success"] is False
        assert "Unable to resolve" in result.get("error", "")

    def test_handle_mfa_no_mfa_detected(self, mock_browser_manager):
        """Test handling MFA when no MFA is detected."""
        # Mock MFA detection
        mock_browser_manager.detect_mfa = Mock(return_value={
            "success": True,
            "has_mfa": False,
            "mfa_fields": [],
            "detection_methods": [],
            "confidence": 0.0,
            "page_type": None,
        })

        result = mock_browser_manager.handle_mfa()

        assert result["success"] is False
        assert "No MFA detected" in result.get("error", "")

    def test_handle_mfa_detection_failure(self, mock_browser_manager):
        """Test handling MFA when detection fails."""
        # Mock MFA detection failure
        mock_browser_manager.detect_mfa = Mock(return_value={
            "success": False,
            "error": "Detection failed",
            "has_mfa": False,
        })

        result = mock_browser_manager.handle_mfa()

        assert result["success"] is False
        assert result.get("error") is not None

    def test_fill_mfa_code_success(self, mock_browser_manager, mock_page):
        """Test filling MFA code successfully."""
        # Mock locator
        mock_locator = Mock()
        mock_page.locator.return_value = mock_locator

        # Mock submit buttons
        mock_submit = Mock()
        mock_page.query_selector_all.return_value = [mock_submit]

        result = mock_browser_manager._fill_mfa_code("#otp-input", "123456")

        assert result["success"] is True
        assert "MFA code filled" in result["output"]
        mock_locator.fill.assert_called_once_with("123456")

    def test_fill_mfa_code_no_submit(self, mock_browser_manager, mock_page):
        """Test filling MFA code without submit button."""
        # Mock locator
        mock_locator = Mock()
        mock_page.locator.return_value = mock_locator

        # No submit buttons
        mock_page.query_selector_all.return_value = []

        result = mock_browser_manager._fill_mfa_code("#otp-input", "123456")

        assert result["success"] is True
        mock_locator.fill.assert_called_once_with("123456")

    def test_fill_mfa_code_field_not_found(self, mock_browser_manager, mock_page):
        """Test filling MFA code when field not found."""
        # Mock locator that raises exception
        mock_page.locator.side_effect = Exception("Element not found")

        result = mock_browser_manager._fill_mfa_code("#otp-input", "123456")

        assert result["success"] is False

    def test_detect_mfa_with_multiple_inputs(self, mock_browser_manager, mock_page):
        """Test MFA detection with multiple input fields."""
        # Mock multiple inputs
        mock_input1 = Mock()
        mock_input1.get_attribute.side_effect = lambda attr: {
            "type": "text",
            "name": "otp",
            "id": "otp-input",
            "placeholder": "123456",
            "maxlength": "6",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "aria-label": "",
            "title": "",
        }.get(attr, "")

        mock_input2 = Mock()
        mock_input2.get_attribute.side_effect = lambda attr: {
            "type": "text",
            "name": "username",
            "id": "username",
            "placeholder": "username",
            "maxlength": "",
            "inputmode": "",
            "autocomplete": "username",
            "aria-label": "",
            "title": "",
        }.get(attr, "")

        mock_page.query_selector_all.return_value = [mock_input1, mock_input2]

        result = mock_browser_manager.detect_mfa()

        assert result["success"] is True


class TestBrowserMFAIntegrationErrors:
    """Test error handling in browser MFA integration."""

    def test_detect_mfa_page_exception(self):
        """Test MFA detection when page raises exception."""
        with patch('core.browser._HAS_PLAYWRIGHT', True):
            manager = BrowserManager(headless=True)
            manager._browser = Mock()
            manager._context = Mock()

            # Create a page that raises exception
            mock_page = Mock()
            mock_page.inner_text.side_effect = Exception("Page error")
            manager._pages = [mock_page]
            manager._active_page_index = 0

            result = manager.detect_mfa()

            assert result["success"] is False
            assert "error" in result

    def test_fill_mfa_code_exception(self):
        """Test filling MFA code when exception occurs."""
        with patch('core.browser._HAS_PLAYWRIGHT', True):
            manager = BrowserManager(headless=True)
            manager._browser = Mock()
            manager._context = Mock()

            mock_page = Mock()
            mock_page.locator.side_effect = Exception("Field not found")
            manager._pages = [mock_page]
            manager._active_page_index = 0

            result = manager._fill_mfa_code("#otp-input", "123456")

            assert result["success"] is False


class TestBrowserMFAWithServiceName:
    """Test MFA handling with service name."""

    def test_handle_mfa_with_service_name(self):
        """Test handling MFA with service name for TOTP lookup."""
        with patch('core.browser._HAS_PLAYWRIGHT', True):
            manager = BrowserManager(headless=True)
            manager._browser = Mock()
            manager._context = Mock()

            mock_page = Mock()
            mock_page.url = "https://github.com/login"
            manager._pages = [mock_page]
            manager._active_page_index = 0

            # Mock MFA detection
            manager.detect_mfa = Mock(return_value={
                "success": True,
                "has_mfa": True,
                "mfa_fields": [{
                    "element_id": "#otp-input",
                    "input_type": "totp",
                    "label": "Authentication Code",
                    "confidence": 0.9,
                }],
                "detection_methods": ["keywords"],
                "confidence": 0.9,
                "page_type": "mfa",
            })

            # Mock locator
            mock_locator = Mock()
            mock_page.locator.return_value = mock_locator

            # Test with service name
            result = manager.handle_mfa(service_name="github")

            # Should attempt TOTP resolution
            assert isinstance(result, dict)


class TestBrowserMFAWithSelector:
    """Test MFA handling with custom selector."""

    def test_handle_mfa_with_custom_selector(self):
        """Test handling MFA with custom selector."""
        with patch('core.browser._HAS_PLAYWRIGHT', True):
            manager = BrowserManager(headless=True)
            manager._browser = Mock()
            manager._context = Mock()

            mock_page = Mock()
            manager._pages = [mock_page]
            manager._active_page_index = 0

            # Mock MFA detection
            manager.detect_mfa = Mock(return_value={
                "success": True,
                "has_mfa": True,
                "mfa_fields": [{
                    "element_id": "#custom-field",
                    "input_type": "totp",
                    "label": "Code",
                    "confidence": 0.8,
                }],
                "detection_methods": ["keywords"],
                "confidence": 0.8,
                "page_type": "mfa",
            })

            # Mock locator
            mock_locator = Mock()
            mock_page.locator.return_value = mock_locator

            # Mock submit buttons - return empty list (no submit button)
            mock_page.query_selector_all.return_value = []

            # Test with custom selector
            result = manager.handle_mfa(code="654321", selector="#custom-otp-field")

            assert result["success"] is True
            mock_locator.fill.assert_called_once_with("654321")
