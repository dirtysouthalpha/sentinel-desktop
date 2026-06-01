"""Gap tests for ocr.py — round 2: covers lines 68-70, 95-96, 103-107, 118,
130-134, 161, 177, 202-261, 281, 287, 291-308, 319."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from PIL import Image

from core import ocr

# ---------------------------------------------------------------------------
# Lines 68-70: _have_tesseract success path (tesseract import + version probe)
# ---------------------------------------------------------------------------


class TestHaveTesseractSuccessPath:
    """Cover lines 68-70: successful pytesseract import and version check."""

    def setup_method(self):
        # Reset the cached state in core.utils
        import core.utils
        core.utils._TESSERACT_OK = None
        core.utils._pytesseract = None

    def test_tesseract_available_sets_flag_true(self):
        import core.utils
        mock_pytesseract = MagicMock()
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"
        with patch("builtins.__import__", return_value=mock_pytesseract):
            result = core.utils.have_tesseract()
        assert result is True
        assert core.utils._TESSERACT_OK is True
        assert core.utils._pytesseract is mock_pytesseract


# ---------------------------------------------------------------------------
# Lines 95-96: _image_cache_key exception fallback
# ---------------------------------------------------------------------------


class TestImageCacheKeyException:
    """Cover lines 95-96: exception in pixel sampling falls back to size-only key."""

    def test_pixel_access_failure_falls_back(self):
        img = Image.new("RGB", (10, 10))
        # getpixel works on a real image, so force failure via side_effect
        with patch.object(img, "getpixel", side_effect=OSError("pixel fail")):
            key = ocr._image_cache_key(img)
        assert isinstance(key, str)
        assert len(key) == 32  # md5 hex digest

    def test_index_error_falls_back(self):
        img = Image.new("RGB", (10, 10))
        with patch.object(img, "getpixel", side_effect=IndexError("out of range")):
            key = ocr._image_cache_key(img)
        assert isinstance(key, str)
        assert len(key) == 32


# ---------------------------------------------------------------------------
# Lines 103-107: _check_cache hit and expiry
# ---------------------------------------------------------------------------


class TestCheckCache:
    """Cover lines 103-107: cache hit returns data; expired entries are removed."""

    def setup_method(self):
        ocr._ocr_cache.clear()

    def test_cache_hit_returns_data(self):
        text = "cached text"
        conf_data = {"avg_confidence": 90.0}
        ocr._ocr_cache["test_key"] = (text, conf_data, time.monotonic())
        result = ocr._check_cache("test_key")
        assert result == (text, conf_data)

    def test_cache_expired_entry_removed(self):
        old_ts = time.monotonic() - ocr._CACHE_TTL - 10  # definitely expired
        ocr._ocr_cache["expired_key"] = ("old", {}, old_ts)
        result = ocr._check_cache("expired_key")
        assert result is None
        assert "expired_key" not in ocr._ocr_cache

    def test_cache_miss_returns_none(self):
        result = ocr._check_cache("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Line 118: _store_cache pruning of expired entries
# ---------------------------------------------------------------------------


class TestStoreCachePruning:
    """Cover line 118: _store_cache prunes expired entries."""

    def setup_method(self):
        ocr._ocr_cache.clear()

    def test_prunes_expired_entries_on_store(self):
        old_ts = time.monotonic() - ocr._CACHE_TTL - 10
        ocr._ocr_cache["old1"] = ("data", {}, old_ts)
        ocr._ocr_cache["old2"] = ("data", {}, old_ts)
        # Storing a new entry should prune the expired ones
        ocr._store_cache("new_key", "new text", {"avg": 80})
        assert "old1" not in ocr._ocr_cache
        assert "old2" not in ocr._ocr_cache
        assert "new_key" in ocr._ocr_cache

    def test_keeps_fresh_entries_on_store(self):
        fresh_ts = time.monotonic()
        ocr._ocr_cache["fresh"] = ("data", {}, fresh_ts)
        ocr._store_cache("new_key", "new text", {})
        assert "fresh" in ocr._ocr_cache
        assert "new_key" in ocr._ocr_cache

    def test_evicts_oldest_when_cache_overflows(self):
        """Cover lines 116-118: oldest entries are evicted when cache exceeds _CACHE_MAX_SIZE."""
        ocr._ocr_cache.clear()
        # Fill cache just beyond the limit with fresh entries
        now = time.monotonic()
        for i in range(ocr._CACHE_MAX_SIZE):
            ocr._ocr_cache[f"key{i}"] = (f"text{i}", {}, now + i)
        # The oldest entry is key0 (smallest timestamp).
        assert "key0" in ocr._ocr_cache
        # Storing one more should evict key0.
        ocr._store_cache("overflow_key", "overflow text", {})
        assert len(ocr._ocr_cache) <= ocr._CACHE_MAX_SIZE
        assert "key0" not in ocr._ocr_cache
        assert "overflow_key" in ocr._ocr_cache


# ---------------------------------------------------------------------------
# Lines 130-134: _downsample_if_needed actual resize path
# ---------------------------------------------------------------------------


class TestDownsampleIfNeeded:
    """Cover lines 130-134: image actually gets downsampled when oversized."""

    def test_downsamples_oversized_image(self):
        # Create a 4K image (exceeds 1920x1080)
        big = Image.new("RGB", (3840, 2160), "white")
        result = ocr._downsample_if_needed(big)
        w, h = result.size
        # 4K images are aggressively downsampled to 720p for performance
        assert w <= 1280
        assert h <= 720
        # Should maintain aspect ratio (16:9)
        assert abs(w / h - 16 / 9) < 0.01

    def test_no_downsample_for_small_image(self):
        small = Image.new("RGB", (800, 600), "white")
        result = ocr._downsample_if_needed(small)
        assert result.size == (800, 600)

    def test_downsamples_height_only_exceeds(self):
        # Width OK but height exceeds
        tall = Image.new("RGB", (1000, 2000), "white")
        result = ocr._downsample_if_needed(tall)
        w, h = result.size
        assert h <= 1080
        assert w <= 1920

    def test_downsamples_medium_resolution_image(self):
        # Image between 1080p and 2K (e.g., 2000x1200)
        # Should use standard 1080p target, not aggressive 720p
        medium = Image.new("RGB", (2000, 1200), "white")
        result = ocr._downsample_if_needed(medium)
        w, h = result.size
        # Should be downsampled to 1080p target
        assert w <= 1920
        assert h <= 1080
        # Should maintain aspect ratio
        assert abs(w / h - 2000 / 1200) < 0.01


# ---------------------------------------------------------------------------
# Line 177: _ocr_image cache hit returns cached text
# ---------------------------------------------------------------------------


class TestOcrImageCacheHit:
    """Cover line 177: _ocr_image returns from cache on hit."""

    def setup_method(self):
        ocr._ocr_cache.clear()

    def test_cache_hit_returns_cached_text(self):
        mock_tesseract = MagicMock()
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            # Pre-populate using the raw-image key (cache key is now computed before preprocessing)
            cache_key = ocr._image_cache_key(img, preprocess=True)
            ocr._ocr_cache[cache_key] = ("cached result", {}, time.monotonic())
            # _ocr_image should return the cached text without calling tesseract
            result = ocr._ocr_image(img, preprocess=True)
            assert result == "cached result"
            mock_tesseract.image_to_string.assert_not_called()


# ---------------------------------------------------------------------------
# Lines 202-261: _ocr_image_with_confidence (entire function)
# ---------------------------------------------------------------------------


class TestOcrImageWithConfidence:
    """Cover lines 202-261: _ocr_image_with_confidence full function."""

    def setup_method(self):
        ocr._ocr_cache.clear()

    def test_no_tesseract_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            img = Image.new("RGB", (10, 10))
            text, conf = ocr._ocr_image_with_confidence(img)
            assert text == ""
            assert conf["avg_confidence"] == 0.0
            assert conf["word_count"] == 0

    def test_success_with_confidence_data(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "Hello World"
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["Hello", "World"],
            "conf": [95, 88],
            "left": [0, 50],
            "top": [0, 0],
            "width": [40, 40],
            "height": [20, 20],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (100, 100))
            text, conf = ocr._ocr_image_with_confidence(img)
            assert text == "Hello World"
            assert conf["avg_confidence"] > 0
            assert conf["word_count"] == 2
            assert conf["low_confidence_words"] == []

    def test_low_confidence_words_detected(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "garbled text"
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["garbled", "text"],
            "conf": [30, 45],
            "left": [0, 50],
            "top": [0, 0],
            "width": [40, 40],
            "height": [20, 20],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (100, 100))
            _text, conf = ocr._ocr_image_with_confidence(img)
            assert len(conf["low_confidence_words"]) == 2
            assert len(conf["low_confidence_regions"]) == 2
            assert conf["low_confidence_regions"][0]["confidence"] == 30.0

    def test_empty_text_words_skipped(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = ""
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["", " ", "valid"],
            "conf": [0, -1, 90],
            "left": [0, 0, 50],
            "top": [0, 0, 0],
            "width": [0, 0, 40],
            "height": [0, 0, 20],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (100, 100))
            _text, conf = ocr._ocr_image_with_confidence(img)
            # Only "valid" with conf 90 is counted (conf > 0 filter)
            assert conf["word_count"] == 1

    def test_invalid_confidence_value_treated_as_zero(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "word"
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["word"],
            "conf": [None],
            "left": [0],
            "top": [0],
            "width": [50],
            "height": [20],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (100, 100))
            _text, conf = ocr._ocr_image_with_confidence(img)
            # None conf -> 0.0, which is not > 0, so not counted
            assert conf["word_count"] == 0

    def test_tesseract_exception_returns_empty(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.side_effect = RuntimeError("tess fail")
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            text, conf = ocr._ocr_image_with_confidence(img)
            assert text == ""
            assert conf["avg_confidence"] == 0.0

    def test_cache_hit_returns_cached_data(self):
        mock_tesseract = MagicMock()
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            # Pre-populate using the raw-image key (cache key is now computed before preprocessing)
            cache_key = ocr._image_cache_key(img, preprocess=True)
            cached_conf = {
                "avg_confidence": 85.0,
                "word_count": 3,
                "low_confidence_words": [],
                "low_confidence_regions": [],
            }
            ocr._ocr_cache[cache_key] = ("cached", cached_conf, time.monotonic())
            text, conf = ocr._ocr_image_with_confidence(img, preprocess=True)
            assert text == "cached"
            assert conf["avg_confidence"] == 85.0
            mock_tesseract.image_to_string.assert_not_called()

    def test_preprocess_false_skips_preprocessing(self):
        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = "raw"
        mock_tesseract.Output.DICT = "dict"
        data = {
            "text": ["raw"],
            "conf": [90],
            "left": [0],
            "top": [0],
            "width": [30],
            "height": [10],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        mock_tesseract.image_to_data.return_value = data
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            with patch("core.ocr.preprocess_for_ocr") as mock_pp:
                ocr._ocr_image_with_confidence(img, preprocess=False)
            mock_pp.assert_not_called()


# ---------------------------------------------------------------------------
# Lines 281, 287: looks_low_confidence edge cases
# ---------------------------------------------------------------------------


class TestLooksLowConfidenceEdgeCases:
    """Cover lines 281 and 287: empty lines and low alnum/line."""

    def test_stripped_lines_all_empty_returns_true(self):
        # Text with only whitespace lines => lines list is empty after strip
        assert ocr.looks_low_confidence("\n   \n  \n") is True

    def test_low_alnum_per_line_returns_true(self):
        # Each line has very few alphanumeric chars relative to total
        # Need total_alnum >= 20 but avg < 6 per line
        text = "a b c d e f g h i j k l m n o p q r s t"
        # That's 20 alnum chars spread over 1 line => avg = 20, not < 6
        # Need more lines: 20 alnum across many lines
        text = "a!!\nb!!\nc!!\nd!!\ne!!\nf!!\ng!!\nh!!\ni!!\nj!!"
        # 10 alnum across 10 lines => avg = 1 < 6
        assert ocr.looks_low_confidence(text) is True


# ---------------------------------------------------------------------------
# Lines 291-308: looks_low_confidence with confidence_data
# ---------------------------------------------------------------------------


class TestLooksLowConfidenceWithData:
    """Cover lines 291-308: confidence_data branches."""

    def _good_text(self):
        # Enough text to pass the basic checks (>= 20 alnum, avg >= 6/line)
        return "Hello World Application\nAnother line of text data here"

    def test_low_avg_confidence_returns_true(self):
        text = self._good_text()
        conf_data = {"avg_confidence": 40.0, "word_count": 5, "low_confidence_words": []}
        assert ocr.looks_low_confidence(text, conf_data) is True

    def test_high_avg_confidence_returns_false(self):
        text = self._good_text()
        conf_data = {"avg_confidence": 85.0, "word_count": 5, "low_confidence_words": []}
        assert ocr.looks_low_confidence(text, conf_data) is False

    def test_avg_confidence_zero_is_not_low(self):
        # avg_conf == 0 means "no data", so the avg_conf > 0 check skips
        text = self._good_text()
        conf_data = {"avg_confidence": 0, "word_count": 5, "low_confidence_words": []}
        assert ocr.looks_low_confidence(text, conf_data) is False

    def test_many_low_confidence_words_returns_true(self):
        text = self._good_text()
        # 6 low-conf words out of 10 total => 60% > 50% threshold
        conf_data = {
            "avg_confidence": 80.0,
            "word_count": 10,
            "low_confidence_words": ["w1", "w2", "w3", "w4", "w5", "w6"],
        }
        assert ocr.looks_low_confidence(text, conf_data) is True

    def test_few_low_confidence_words_returns_false(self):
        text = self._good_text()
        # 2 low-conf words out of 10 => 20% < 50%
        conf_data = {
            "avg_confidence": 80.0,
            "word_count": 10,
            "low_confidence_words": ["w1", "w2"],
        }
        assert ocr.looks_low_confidence(text, conf_data) is False

    def test_word_count_leq_three_skips_ratio_check(self):
        text = self._good_text()
        # word_count <= 3 means ratio check skipped (guard: word_count > 3)
        conf_data = {
            "avg_confidence": 80.0,
            "word_count": 3,
            "low_confidence_words": ["w1", "w2"],
        }
        assert ocr.looks_low_confidence(text, conf_data) is False

    def test_empty_confidence_data_dict_skips_checks(self):
        text = self._good_text()
        assert ocr.looks_low_confidence(text, {}) is False

    def test_none_confidence_data_skips_checks(self):
        text = self._good_text()
        assert ocr.looks_low_confidence(text, None) is False


# ---------------------------------------------------------------------------
# Line 319: read_screen_text success path (capture + _ocr_image)
# ---------------------------------------------------------------------------


class TestReadScreenTextSuccess:
    """Cover line 319: read_screen_text captures and OCRs successfully."""

    def test_success_path_calls_ocr_image(self):
        with patch("core.ocr.have_tesseract", return_value=True):
            ocr._ocr_cache.clear()
            img = Image.new("RGB", (100, 100))
            with (
                patch("core.ocr.capture_screen", return_value=img),
                patch("core.ocr._ocr_image", return_value="screen text") as mock_ocr,
            ):
                result = ocr.read_screen_text()
            assert result == "screen text"
            mock_ocr.assert_called_once()

    def test_with_monitor_and_preprocess_params(self):
        with patch("core.ocr.have_tesseract", return_value=True):
            ocr._ocr_cache.clear()
            img = Image.new("RGB", (100, 100))
            with (
                patch("core.ocr.capture_screen", return_value=img) as mock_cap,
                patch("core.ocr._ocr_image", return_value="text"),
            ):
                ocr.read_screen_text(monitor=1, preprocess=False)
            mock_cap.assert_called_once_with(monitor=1)


# ---------------------------------------------------------------------------
# read_screen_text_with_confidence paths
# ---------------------------------------------------------------------------


class TestReadScreenTextWithConfidence:
    """Cover read_screen_text_with_confidence function."""

    def test_success_path(self):
        with patch("core.ocr.have_tesseract", return_value=True):
            ocr._ocr_cache.clear()
            img = Image.new("RGB", (100, 100))
            conf_data = {
                "avg_confidence": 90.0,
                "word_count": 2,
                "low_confidence_words": [],
                "low_confidence_regions": [],
            }
            with (
                patch("core.ocr.capture_screen", return_value=img),
                patch("core.ocr._ocr_image_with_confidence", return_value=("text", conf_data)),
            ):
                text, conf = ocr.read_screen_text_with_confidence()
            assert text == "text"
            assert conf["avg_confidence"] == 90.0

    def test_no_tesseract_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=False):
            text, conf = ocr.read_screen_text_with_confidence()
            assert text == ""
            assert conf["word_count"] == 0

    def test_exception_returns_empty(self):
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.capture_screen", side_effect=OSError("fail")):
            text, conf = ocr.read_screen_text_with_confidence()
            assert text == ""
            assert conf["avg_confidence"] == 0


# ---------------------------------------------------------------------------
# ocr.py:499->492 — _exact_substring_hit when _centroid returns None
# ---------------------------------------------------------------------------


class TestExactSubstringHitCentroidNone:
    """Cover line 499 False branch: _centroid returns None so the loop continues."""

    def test_centroid_none_skips_result(self):
        # Build a box set where needle is found but _centroid is patched to return None.
        boxes = [
            {"text": "hello", "x": 0, "y": 0, "w": 40, "h": 20, "line_id": (1, 1, 1)},
            {"text": "world", "x": 50, "y": 0, "w": 40, "h": 20, "line_id": (1, 1, 1)},
        ]
        with patch("core.ocr._centroid", return_value=None):
            result = ocr._exact_substring_hit(boxes, "hello")
        # Both lines had needle but centroid returned None → function returns None
        assert result is None


# ---------------------------------------------------------------------------
# ocr.py:549->551 — _fuzzy_line_hit when _centroid returns None
# ---------------------------------------------------------------------------


class TestFuzzyLineHitCentroidNone:
    """Cover line 549 False branch: best_words found but _centroid returns None."""

    def test_centroid_none_returns_none(self):
        boxes = [
            {"text": "hello", "x": 0, "y": 0, "w": 40, "h": 20, "line_id": (1, 1, 1)},
        ]
        with patch("core.ocr._centroid", return_value=None):
            result = ocr._fuzzy_line_hit(boxes, "hello", min_score=0.0)
        assert result is None


# ---------------------------------------------------------------------------
# Cross-function cache interaction: _ocr_image stores None conf_data, so
# _ocr_image_with_confidence must recompute confidence on such cache hits.
# ---------------------------------------------------------------------------


class TestOcrCacheCrossFunction:
    """_ocr_image stores None for conf_data; _ocr_image_with_confidence must
    not return that cache entry as its confidence layer — it recomputes."""

    def setup_method(self) -> None:
        ocr._ocr_cache.clear()

    def teardown_method(self) -> None:
        ocr._ocr_cache.clear()

    def _make_data(self, word: str = "hello", conf_val: int = 90) -> dict:
        return {
            "text": [word],
            "conf": [conf_val],
            "left": [0],
            "top": [0],
            "width": [40],
            "height": [20],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }

    def test_text_only_cache_not_used_for_confidence(self):
        """_ocr_image_with_confidence recomputes conf when cache has conf_data=None."""
        mock_tesseract = MagicMock()
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            cache_key = ocr._image_cache_key(img, preprocess=True)
            # Simulate a cache entry left by the text-only _ocr_image path.
            ocr._ocr_cache[cache_key] = ("hello from text-only", None, time.monotonic())
            mock_tesseract.Output.DICT = "dict"
            mock_tesseract.image_to_data.return_value = self._make_data("hello", 90)

            text, conf = ocr._ocr_image_with_confidence(img, preprocess=True)

            # image_to_string should NOT be called (text reused from cache).
            mock_tesseract.image_to_string.assert_not_called()
            # image_to_data MUST be called to compute confidence.
            mock_tesseract.image_to_data.assert_called_once()
            # Text comes from the cache entry.
            assert text == "hello from text-only"
            # Confidence data is freshly computed.
            assert conf["avg_confidence"] > 0

    def test_full_cache_hit_skips_both_calls(self):
        """When cache has real conf_data, neither image_to_string nor image_to_data fires."""
        mock_tesseract = MagicMock()
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            cache_key = ocr._image_cache_key(img, preprocess=True)
            full_conf = {
                "avg_confidence": 75.0,
                "word_count": 2,
                "low_confidence_words": [],
                "low_confidence_regions": [],
            }
            ocr._ocr_cache[cache_key] = ("cached text", full_conf, time.monotonic())

            text, conf = ocr._ocr_image_with_confidence(img, preprocess=True)

            mock_tesseract.image_to_string.assert_not_called()
            mock_tesseract.image_to_data.assert_not_called()
            assert text == "cached text"
            assert conf["avg_confidence"] == 75.0

    def test_image_to_data_failure_returns_cached_text(self):
        """If image_to_data raises after reusing cached text, cached text is preserved."""
        mock_tesseract = MagicMock()
        with patch("core.ocr.have_tesseract", return_value=True), \
             patch("core.ocr.get_tesseract", return_value=mock_tesseract):
            img = Image.new("RGB", (10, 10))
            cache_key = ocr._image_cache_key(img, preprocess=True)
            # Text-only cache entry (from _ocr_image fast path).
            ocr._ocr_cache[cache_key] = ("preserved text", None, time.monotonic())
            mock_tesseract.image_to_data.side_effect = OSError("tesseract crashed")

            text, conf = ocr._ocr_image_with_confidence(img, preprocess=True)

        # The cached text must survive even though image_to_data failed.
        assert text == "preserved text"
        assert conf["avg_confidence"] == 0.0
