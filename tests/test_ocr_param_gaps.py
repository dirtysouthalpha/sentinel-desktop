"""Gap tests for ocr.py — preprocess=False, fuzzy=False, monitor offset."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PIL import Image

from core import ocr


class TestOcrImageNoPreprocess:
    """_ocr_image with preprocess=False skips preprocessing."""

    def test_preprocess_false_skips_preprocess_for_ocr(self):
        ocr._TESSERACT_OK = True
        ocr._pytesseract = MagicMock()
        ocr._pytesseract.image_to_string.return_value = "raw text"
        ocr._ocr_cache.clear()
        img = Image.new("RGB", (10, 10))
        with patch("core.ocr.preprocess_for_ocr") as mock_pp:
            result = ocr._ocr_image(img, preprocess=False)
        mock_pp.assert_not_called()
        assert result == "raw text"

    def test_preprocess_true_calls_preprocess_for_ocr(self):
        ocr._TESSERACT_OK = True
        ocr._pytesseract = MagicMock()
        ocr._pytesseract.image_to_string.return_value = "preprocessed text"
        ocr._ocr_cache.clear()
        img = Image.new("RGB", (10, 10))
        with patch("core.ocr.preprocess_for_ocr", return_value=img) as mock_pp:
            result = ocr._ocr_image(img, preprocess=True)
        mock_pp.assert_called_once_with(img)
        assert result == "preprocessed text"


class TestFindTextFuzzyFalse:
    """find_text with fuzzy=False skips fuzzy matching."""

    def test_fuzzy_false_skips_fuzzy_matching(self):
        ocr._TESSERACT_OK = True
        ocr._pytesseract = MagicMock()
        ocr._pytesseract.Output.DICT = "dict"
        # Text is "Setting" — not an exact match for "Settings"
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
        ocr._pytesseract.image_to_data.return_value = data
        with (
            patch("core.ocr.capture_screen", return_value=Image.new("RGB", (100, 100))),
            patch("core.ocr.get_capture_offset", return_value=(0, 0)),
        ):
            # fuzzy=False should skip fuzzy matching and return None
            result = ocr.find_text("Settings", fuzzy=False)
        assert result is None

    def test_fuzzy_false_still_finds_exact_match(self):
        ocr._TESSERACT_OK = True
        ocr._pytesseract = MagicMock()
        ocr._pytesseract.Output.DICT = "dict"
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
        ocr._pytesseract.image_to_data.return_value = data
        with (
            patch("core.ocr.capture_screen", return_value=Image.new("RGB", (100, 100))),
            patch("core.ocr.get_capture_offset", return_value=(10, 20)),
        ):
            result = ocr.find_text("Submit", fuzzy=False)
        assert result is not None
        # Offset should be applied
        # Centroid: ((x + x+w)//2, (y + y+h)//2) + offset
        assert result == ((100 + 150) // 2 + 10, (200 + 220) // 2 + 20)


class TestFindTextMonitorOffset:
    """find_text passes monitor parameter to capture_screen."""

    def test_monitor_param_passed_to_capture(self):
        ocr._TESSERACT_OK = True
        ocr._pytesseract = MagicMock()
        ocr._pytesseract.Output.DICT = "dict"
        data = {
            "text": ["Hello"],
            "left": [10],
            "top": [20],
            "width": [30],
            "height": [10],
            "conf": [95],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        ocr._pytesseract.image_to_data.return_value = data
        with (
            patch("core.ocr.capture_screen", return_value=Image.new("RGB", (100, 100))) as mock_cap,
            patch("core.ocr.get_capture_offset", return_value=(0, 0)),
        ):
            ocr.find_text("Hello", monitor=1)
        mock_cap.assert_called_once_with(monitor=1)
