"""Gap tests for ocr.py — _have_tesseract, _ocr_image, read_*, find_text paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PIL import Image

from core import ocr
from core.utils import have_tesseract


class TestHaveTesseract:
    """have_tesseract lazy probe."""

    def setup_method(self):
        # Reset the cached state in core.utils
        import core.utils
        core.utils._TESSERACT_OK = None
        core.utils._pytesseract = None

    def test_cached_true_returns_immediately(self):
        import core.utils
        core.utils._TESSERACT_OK = True
        assert have_tesseract() is True

    def test_import_failure_returns_false(self):
        with patch("builtins.__import__", side_effect=ImportError("no tesseract")):
            assert have_tesseract() is False

    def test_cached_false_returns_immediately(self):
        import core.utils
        core.utils._TESSERACT_OK = False
        assert have_tesseract() is False


class TestPreprocessException:
    """preprocess_for_ocr exception handler returns raw image."""

    def test_exception_returns_original(self):
        img = Image.new("RGB", (10, 10))
        with patch.object(Image, "LANCZOS", side_effect=RuntimeError("fail")):
            # Force exception in resize
            result = ocr.preprocess_for_ocr(img)
        assert result is img


class TestOcrImage:
    """_ocr_image without tesseract returns empty."""

    def setup_method(self) -> None:
        ocr._ocr_cache.clear()

    def test_no_tesseract_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            img = Image.new("RGB", (10, 10))
            assert ocr._ocr_image(img) == ""

    def test_tesseract_exception_returns_empty(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.side_effect = RuntimeError("ocr fail")
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            assert ocr._ocr_image(img) == ""

    def test_tesseract_success(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "Hello World"
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            assert ocr._ocr_image(img) == "Hello World"


class TestLooksLowConfidenceEmptyLines:
    """looks_low_confidence with empty lines list."""

    def test_only_newlines(self):
        assert ocr.looks_low_confidence("\n\n\n") is True


class TestReadScreenText:
    """read_screen_text paths."""

    def test_no_tesseract_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            assert ocr.read_screen_text() == ""

    def test_capture_exception_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_screen", side_effect=OSError("fail")):
            assert ocr.read_screen_text() == ""


class TestReadFocusedWindowText:
    """read_focused_window_text delegates to _with_title."""

    def test_delegates_to_with_title(self):
        with patch("core.ocr.read_focused_window_text_with_title", return_value=("text", "Title")):
            assert ocr.read_focused_window_text() == "text"


class TestReadFocusedWindowTextWithTitle:
    """read_focused_window_text_with_title paths."""

    def test_no_tesseract_returns_empty_tuple(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            assert ocr.read_focused_window_text_with_title() == ("", "")

    def test_capture_returns_none_falls_back(self):
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_focused_window_with_title", return_value=None), \
             patch("core.ocr.read_screen_text", return_value="fallback text"):
            text, title = ocr.read_focused_window_text_with_title()
            assert text == "fallback text"
            assert title == "<full screen fallback>"

    def test_capture_returns_image_and_title(self):
        img = Image.new("RGB", (10, 10))
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_focused_window_with_title", return_value=(img, "My Window")), \
             patch("core.ocr._ocr_image", return_value="window text"):
            text, title = ocr.read_focused_window_text_with_title()
            assert text == "window text"
            assert title == "My Window"

    def test_exception_returns_empty_tuple(self):
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_focused_window_with_title", side_effect=RuntimeError("fail")):
            assert ocr.read_focused_window_text_with_title() == ("", "")


class TestReadWindowText:
    """read_window_text paths."""

    def test_empty_title_returns_empty(self):
        assert ocr.read_window_text("") == ""

    def test_no_tesseract_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            assert ocr.read_window_text("Chrome") == ""

    def test_capture_returns_none(self):
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_window", return_value=None):
            assert ocr.read_window_text("Chrome") == ""

    def test_capture_returns_image(self):
        img = Image.new("RGB", (10, 10))
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_window", return_value=img), \
             patch("core.ocr._ocr_image", return_value="text"):
            assert ocr.read_window_text("Chrome") == "text"

    def test_exception_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_window", side_effect=OSError("fail")):
            assert ocr.read_window_text("Chrome") == ""


class TestFindText:
    """find_text paths."""

    def setup_method(self):
        ocr._ocr_cache.clear()
        ocr._boxes_cache.clear()

    def test_empty_query_returns_none(self):
        assert ocr.find_text("") is None

    def test_no_tesseract_returns_none(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            assert ocr.find_text("test") is None

    def test_ocr_exception_returns_none(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_data.side_effect = RuntimeError("fail")
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract), \
             patch("core.ocr.capture_screen", return_value=Image.new("RGB", (10, 10))):
            assert ocr.find_text("test") is None

    def test_exact_hit_returns_position(self):
        mock_tesseract = MagicMock()
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["Submit"],
            "left": [100],
            "top": [200],
            "width": [50],
            "height": [20],
            "conf": [95],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract), \
             patch("core.ocr.capture_screen", return_value=Image.new("RGB", (100, 100))), \
             patch("core.ocr.get_capture_offset", return_value=(0, 0)):
            result = ocr.find_text("Submit")
        assert result is not None
        assert isinstance(result[0], int)

    def test_fuzzy_hit_returns_position(self):
        mock_tesseract = MagicMock()
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["Setting"],
            "left": [50],
            "top": [60],
            "width": [40],
            "height": [15],
            "conf": [90],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract), \
             patch("core.ocr.capture_screen", return_value=Image.new("RGB", (100, 100))), \
             patch("core.ocr.get_capture_offset", return_value=(0, 0)):
            result = ocr.find_text("Settings", fuzzy=True, min_score=0.5)
        assert result is not None

    def test_no_match_returns_none(self):
        mock_tesseract = MagicMock()
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["Completely"],
            "left": [50],
            "top": [60],
            "width": [40],
            "height": [15],
            "conf": [90],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract), \
             patch("core.ocr.capture_screen", return_value=Image.new("RGB", (100, 100))), \
             patch("core.ocr.get_capture_offset", return_value=(0, 0)):
            result = ocr.find_text("xyz", fuzzy=True, min_score=0.9)
        assert result is None

    def test_whitespace_only_needle_returns_none(self):
        with patch("core.ocr.have_tesseract", return_value=True):
            assert ocr.find_text("   ") is None
