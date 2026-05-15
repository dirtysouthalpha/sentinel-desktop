"""Tests for core/ocr.py — OCR text reading and analysis."""

from core.ocr import (
    _boxes_from_data,
    _centroid,
    _exact_substring_hit,
    _fuzzy_line_hit,
    _words_covering_substring,
    looks_low_confidence,
    preprocess_for_ocr,
)


class TestLooksLowConfidence:
    def test_empty_string(self):
        assert looks_low_confidence("") is True

    def test_whitespace_only(self):
        assert looks_low_confidence("   \n  \t  ") is True

    def test_short_garbage(self):
        assert looks_low_confidence("@#$%^") is True

    def test_good_text(self):
        text = "Hello World\nThis is a test\nWith enough alphanumeric chars"
        assert looks_low_confidence(text) is False

    def test_few_alnum_chars(self):
        assert looks_low_confidence("!@# $%^ &*()") is True

    def test_many_lines_tiny_alnum(self):
        text = "\n".join(["!!"] * 20)
        assert looks_low_confidence(text) is True


class TestPreprocessForOcr:
    def test_returns_image(self):
        from PIL import Image

        img = Image.new("RGB", (100, 100), "white")
        result = preprocess_for_ocr(img)
        assert isinstance(result, Image.Image)

    def test_output_is_grayscale(self):
        from PIL import Image

        img = Image.new("RGB", (100, 100), "white")
        result = preprocess_for_ocr(img)
        assert result.mode == "L"

    def test_upscales_small_image(self):
        from PIL import Image

        img = Image.new("RGB", (200, 200), "white")
        result = preprocess_for_ocr(img)
        w, h = result.size
        assert w == 400
        assert h == 400

    def test_does_not_upscale_huge_image(self):
        from PIL import Image

        img = Image.new("RGB", (2500, 2500), "white")
        result = preprocess_for_ocr(img)
        w, h = result.size
        assert w == 2500
        assert h == 2500


class TestBoxesFromData:
    def test_filters_empty_text(self):
        data = {
            "text": ["", "hello", "  "],
            "left": [0, 10, 20],
            "top": [0, 5, 10],
            "width": [50, 60, 70],
            "height": [20, 25, 30],
            "conf": [90, 95, 80],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        }
        boxes = _boxes_from_data(data)
        assert len(boxes) == 1
        assert boxes[0]["text"] == "hello"

    def test_filters_low_confidence(self):
        data = {
            "text": ["good", "bad"],
            "left": [0, 50],
            "top": [0, 0],
            "width": [40, 40],
            "height": [20, 20],
            "conf": [90, 10],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }
        boxes = _boxes_from_data(data)
        assert len(boxes) == 1
        assert boxes[0]["text"] == "good"

    def test_handles_invalid_confidence(self):
        data = {
            "text": ["word"],
            "left": [0],
            "top": [0],
            "width": [50],
            "height": [20],
            "conf": [None],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        boxes = _boxes_from_data(data)
        assert len(boxes) == 0  # None → 0.0 conf → filtered

    def test_empty_data(self):
        data = {"text": [], "left": [], "top": [], "width": [], "height": [], "conf": []}
        assert _boxes_from_data(data) == []


class TestCentroid:
    def test_single_box(self):
        boxes = [{"x": 10, "y": 20, "w": 30, "h": 40}]
        assert _centroid(boxes) == (25, 40)

    def test_multiple_boxes(self):
        boxes = [
            {"x": 0, "y": 0, "w": 10, "h": 10},
            {"x": 20, "y": 20, "w": 10, "h": 10},
        ]
        cx, cy = _centroid(boxes)
        assert cx == 15  # (0+20+10) // 2
        assert cy == 15

    def test_empty_returns_none(self):
        assert _centroid([]) is None


class TestWordsCoveringSubstring:
    def test_exact_word(self):
        words = [
            {"text": "Hello", "x": 0, "y": 0, "w": 50, "h": 20},
            {"text": "World", "x": 60, "y": 0, "w": 50, "h": 20},
        ]
        result = _words_covering_substring(words, "hello")
        assert len(result) == 1
        assert result[0]["text"] == "Hello"

    def test_spanning_words(self):
        words = [
            {"text": "Hello", "x": 0, "y": 0, "w": 50, "h": 20},
            {"text": "World", "x": 60, "y": 0, "w": 50, "h": 20},
        ]
        result = _words_covering_substring(words, "hello world")
        assert len(result) == 2

    def test_not_found_returns_all(self):
        words = [
            {"text": "Hello", "x": 0, "y": 0, "w": 50, "h": 20},
        ]
        result = _words_covering_substring(words, "xyz")
        assert len(result) == 1  # fallback to whole line


class TestExactSubstringHit:
    def test_finds_match(self):
        boxes = [
            {"text": "Click", "x": 0, "y": 0, "w": 40, "h": 20, "line_id": (1, 1, 1)},
            {"text": "Here", "x": 50, "y": 0, "w": 40, "h": 20, "line_id": (1, 1, 1)},
        ]
        result = _exact_substring_hit(boxes, "click here")
        assert result is not None
        assert len(result) == 2

    def test_no_match(self):
        boxes = [
            {"text": "Hello", "x": 0, "y": 0, "w": 50, "h": 20, "line_id": (1, 1, 1)},
        ]
        result = _exact_substring_hit(boxes, "goodbye")
        assert result is None

    def test_empty_boxes(self):
        assert _exact_substring_hit([], "test") is None


class TestFuzzyLineHit:
    def test_close_match(self):
        boxes = [
            {"text": "Settings", "x": 0, "y": 0, "w": 60, "h": 20, "line_id": (1, 1, 1)},
        ]
        result = _fuzzy_line_hit(boxes, "setting", min_score=0.5)
        assert result is not None

    def test_no_match(self):
        boxes = [
            {"text": "Hello", "x": 0, "y": 0, "w": 50, "h": 20, "line_id": (1, 1, 1)},
        ]
        result = _fuzzy_line_hit(boxes, "zzzzzzzzz", min_score=0.7)
        assert result is None

    def test_empty_boxes(self):
        assert _fuzzy_line_hit([], "test", 0.5) is None
