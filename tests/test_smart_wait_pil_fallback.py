"""
Tests for core/smart_wait.py — pure-PIL fallback and edge cases.

Exercises the _compute_change_score function when numpy is unavailable,
the zero-dimension image edge case, and _downsample with tiny images.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# _compute_change_score — pure-PIL fallback (numpy unavailable)
# ---------------------------------------------------------------------------


class TestNumpyImportGuard:
    """The module-level ``try: import numpy / except ImportError`` guard."""

    def test_import_falls_back_when_numpy_missing(self):
        """A missing numpy at import time sets ``_HAS_NUMPY`` False (lines 50-52).

        Setting ``sys.modules['numpy'] = None`` forces ``import numpy`` to raise
        ImportError, so reloading the module re-runs the top-level guard down the
        fallback path. The module is reloaded again afterwards to restore the real
        numpy-backed state for the rest of the session.
        """
        import importlib

        import core.smart_wait as sw

        try:
            with patch.dict(sys.modules, {"numpy": None}):
                reloaded = importlib.reload(sw)
                assert reloaded._HAS_NUMPY is False
                assert reloaded.np is None
        finally:
            importlib.reload(sw)
        assert sw._HAS_NUMPY is True


class TestComputeChangeScorePILFallback:
    """Test _compute_change_score when _HAS_NUMPY is False."""

    def _import_with_no_numpy(self):
        """Import smart_wait with _HAS_NUMPY forced to False."""
        import core.smart_wait as sw

        return sw

    def test_identical_images_score_zero(self):
        """Two identical images should produce a change score of 0.0."""
        sw = self._import_with_no_numpy()
        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img, img.copy())
        assert score == 0.0

    def test_completely_different_images_score_high(self):
        """Two completely different images should produce a score near 1.0."""
        sw = self._import_with_no_numpy()
        img_a = Image.new("RGB", (10, 10), color=(0, 0, 0))
        img_b = Image.new("RGB", (10, 10), color=(255, 255, 255))
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        assert score == 1.0

    def test_grayscale_images(self):
        """Grayscale images should be converted to RGB internally."""
        sw = self._import_with_no_numpy()
        img_a = Image.new("L", (5, 5), color=100)
        img_b = Image.new("L", (5, 5), color=200)
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        # Both grayscale converted to RGB — channels differ by 100
        assert score == 1.0

    def test_zero_dimension_image_returns_zero(self):
        """An image with zero width or height should return 0.0."""
        sw = self._import_with_no_numpy()
        # Create a 0x0 image
        img_a = Image.new("RGB", (0, 0))
        img_b = Image.new("RGB", (0, 0))
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        assert score == 0.0

    def test_partial_change(self):
        """Only some pixels changed — score should be proportional."""
        sw = self._import_with_no_numpy()
        # 4x1 image — change 2 of 4 pixels
        img_a = Image.new("RGB", (4, 1), color=(100, 100, 100))
        img_b = Image.new("RGB", (4, 1), color=(100, 100, 100))
        pixels = img_b.load()
        pixels[0, 0] = (200, 200, 200)  # changed
        pixels[1, 0] = (200, 200, 200)  # changed
        # pixels[2,0] and [3,0] unchanged
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        assert 0.0 < score <= 1.0
        assert score == 0.5  # 2 of 4 changed

    def test_threshold_respected(self):
        """Changes below the per-channel threshold should not count."""
        sw = self._import_with_no_numpy()
        img_a = Image.new("RGB", (2, 2), color=(100, 100, 100))
        img_b = Image.new("RGB", (2, 2), color=(100, 100, 100))
        pixels = img_b.load()
        # Change of 1 per channel — below default threshold (usually 10)
        pixels[0, 0] = (101, 101, 101)
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        assert score == 0.0  # below threshold

    def test_rgba_images_handled(self):
        """RGBA images should be converted to RGB for comparison."""
        sw = self._import_with_no_numpy()
        img_a = Image.new("RGBA", (5, 5), color=(100, 100, 100, 255))
        img_b = Image.new("RGBA", (5, 5), color=(200, 200, 200, 255))
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        assert score == 1.0

    def test_single_pixel_images(self):
        """Single-pixel images should work correctly."""
        sw = self._import_with_no_numpy()
        img_a = Image.new("RGB", (1, 1), color=(0, 0, 0))
        img_b = Image.new("RGB", (1, 1), color=(255, 255, 255))
        with patch.object(sw, "_HAS_NUMPY", False):
            score = sw._compute_change_score(img_a, img_b)
        assert score == 1.0


# ---------------------------------------------------------------------------
# _downsample edge cases
# ---------------------------------------------------------------------------


class TestDownsample:
    """Test _downsample with various image sizes."""

    def test_downsample_tiny_image(self):
        """Downsampling a 1x1 image should return it unchanged or small."""
        import core.smart_wait as sw

        img = Image.new("RGB", (1, 1), color=(128, 128, 128))
        result = sw._downsample(img)
        assert result.size[0] <= 1
        assert result.size[1] <= 1

    def test_downsample_normal_image(self):
        """Downsampling should reduce image size."""
        import core.smart_wait as sw

        img = Image.new("RGB", (200, 200), color=(128, 128, 128))
        result = sw._downsample(img)
        assert result.size[0] < 200
        assert result.size[1] < 200

    def test_downsample_preserves_or_converts_mode(self):
        """Output should be a valid PIL image mode."""
        import core.smart_wait as sw

        img = Image.new("RGBA", (100, 100), color=(128, 128, 128, 255))
        result = sw._downsample(img)
        assert result.mode in ("RGB", "RGBA", "L")

    def test_downsample_exact_divisor(self):
        """Image size exactly divisible by factor should work cleanly."""
        import core.smart_wait as sw

        # Default factor is 4; 80 / 4 = 20
        img = Image.new("RGB", (80, 80), color=(64, 128, 192))
        result = sw._downsample(img)
        assert result.size == (20, 20)

    def test_downsample_non_divisor(self):
        """Image size not divisible by factor should still work."""
        import core.smart_wait as sw

        img = Image.new("RGB", (81, 81), color=(64, 128, 192))
        result = sw._downsample(img)
        # Floor division: 81 // 4 = 20
        assert result.size[0] <= 21
        assert result.size[1] <= 21


# ---------------------------------------------------------------------------
# _save_snapshot edge cases
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    """Test _save_snapshot helper."""

    def test_save_snapshot_returns_path(self, tmp_path):
        """Should save an image and return the path."""
        import core.smart_wait as sw

        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        with patch("tempfile.gettempdir", return_value=str(tmp_path)):
            result = sw._save_snapshot(img, prefix="test")
        assert result is not None
        assert "test" in result

    def test_save_snapshot_none_raises(self):
        """Should raise AttributeError when image is None (img.save fails)."""
        import core.smart_wait as sw

        with pytest.raises(AttributeError):
            sw._save_snapshot(None, prefix="test")

    def test_save_snapshot_returns_string(self, tmp_path):
        """Should return a string path."""
        import core.smart_wait as sw

        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        with patch("tempfile.gettempdir", return_value=str(tmp_path)):
            result = sw._save_snapshot(img, prefix="path_test")
        assert isinstance(result, str)
        assert result.endswith(".png")


# ---------------------------------------------------------------------------
# SmartWait initialization and basic properties
# ---------------------------------------------------------------------------


class TestSmartWaitInit:
    """Test SmartWait initialization."""

    def test_init_default(self):
        """SmartWait should initialize with defaults."""
        import core.smart_wait as sw

        waiter = sw.SmartWait()
        assert waiter is not None

    def test_repr(self):
        """SmartWait should have a useful repr."""
        import core.smart_wait as sw

        waiter = sw.SmartWait()
        r = repr(waiter)
        assert "SmartWait" in r
