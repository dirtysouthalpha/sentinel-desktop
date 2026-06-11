"""Gap tests for core/ocr.py — find_text_boxes (lines 461, 472-477, 485-487) and
_get_screen_boxes cache-hit path (line 439)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from PIL import Image

import core.ocr as ocr_module
from core.ocr import _get_screen_boxes, find_text_boxes


def _small_img() -> Image.Image:
    return Image.new("RGB", (100, 50), "white")


class TestFindTextBoxesNoTesseract:
    """Line 461: have_tesseract() is False → return []."""

    def test_returns_empty_when_no_tesseract(self) -> None:
        with patch.object(ocr_module, "have_tesseract", return_value=False):
            result = find_text_boxes(_small_img())
        assert result == []


class TestFindTextBoxesSuccess:
    """Lines 472-477: successful tesseract call returns box dicts."""

    def _make_tesseract_mock(self) -> MagicMock:
        tess = MagicMock()
        tess.Output.DICT = "dict"
        tess.image_to_data.return_value = {
            "text": ["Hello", "World", ""],
            "conf": [85.0, 90.0, -1.0],
            "left": [10, 100, 0],
            "top": [10, 10, 0],
            "width": [50, 60, 0],
            "height": [20, 20, 0],
            "block_num": [1, 1, 0],
            "par_num": [1, 1, 0],
            "line_num": [1, 1, 0],
        }
        return tess

    def test_returns_boxes_for_valid_image(self) -> None:
        tess = self._make_tesseract_mock()
        with (
            patch.object(ocr_module, "have_tesseract", return_value=True),
            patch.object(ocr_module, "get_tesseract", return_value=tess),
        ):
            result = find_text_boxes(_small_img())

        assert len(result) == 2
        assert result[0]["text"] == "Hello"
        assert result[0]["bbox"] == (10, 10, 60, 30)
        assert result[0]["confidence"] == 70.0
        assert result[1]["text"] == "World"

    def test_skips_zero_dimension_boxes(self) -> None:
        tess = MagicMock()
        tess.Output.DICT = "dict"
        tess.image_to_data.return_value = {
            "text": ["ok", "zero"],
            "conf": [90.0, 90.0],
            "left": [5, 5],
            "top": [5, 5],
            "width": [20, 0],   # second box has zero width → should be skipped
            "height": [10, 10],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }
        with (
            patch.object(ocr_module, "have_tesseract", return_value=True),
            patch.object(ocr_module, "get_tesseract", return_value=tess),
        ):
            result = find_text_boxes(_small_img())

        assert len(result) == 1
        assert result[0]["text"] == "ok"


class TestGetScreenBoxesCacheHit:
    """Line 439: cache-hit branch returns cached boxes directly."""

    def test_cache_hit_returns_without_calling_tesseract(self) -> None:
        cached_boxes = [{"text": "cached", "bbox": (0, 0, 10, 10), "confidence": 70.0}]

        fake_img = _small_img()
        with (
            patch.object(ocr_module, "capture_screen", return_value=fake_img),
            patch.object(ocr_module, "_downsample_if_needed", return_value=fake_img),
        ):
            cache_key = ocr_module._image_cache_key(fake_img)
            ocr_module._boxes_cache[cache_key] = (cached_boxes, time.monotonic())

            result = _get_screen_boxes(None)

        assert result is cached_boxes


class TestFindTextBoxesException:
    """Lines 485-487: OSError/RuntimeError → return []."""

    def test_oserror_returns_empty(self) -> None:
        with (
            patch.object(ocr_module, "have_tesseract", return_value=True),
            patch.object(ocr_module, "get_tesseract", side_effect=OSError("tess unavailable")),
        ):
            result = find_text_boxes(_small_img())
        assert result == []

    def test_runtimeerror_returns_empty(self) -> None:
        with (
            patch.object(ocr_module, "have_tesseract", return_value=True),
            patch.object(ocr_module, "get_tesseract", side_effect=RuntimeError("tess crashed")),
        ):
            result = find_text_boxes(_small_img())
        assert result == []
