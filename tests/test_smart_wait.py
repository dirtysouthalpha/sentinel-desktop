"""Tests for core/smart_wait.py — visual-diff-based waiting."""

from PIL import Image

from core.smart_wait import (
    WaitResult,
    _compute_change_score,
    _downsample,
    _save_snapshot,
)


class TestWaitResult:
    def test_default_values(self):
        r = WaitResult(success=True, elapsed=1.0, frames_checked=5, change_score=0.3)
        assert r.success is True
        assert r.elapsed == 1.0
        assert r.frames_checked == 5
        assert r.change_score == 0.3
        assert r.snapshot_path is None

    def test_with_snapshot_path(self):
        r = WaitResult(
            success=True,
            elapsed=0.5,
            frames_checked=1,
            change_score=1.0,
            snapshot_path="/tmp/test.png",  # noqa: S108
        )
        assert r.snapshot_path == "/tmp/test.png"  # noqa: S108


class TestDownsample:
    def test_reduces_size(self):
        img = Image.new("RGB", (100, 100), "red")
        result = _downsample(img, factor=4)
        assert result.size == (25, 25)

    def test_custom_factor(self):
        img = Image.new("RGB", (200, 200), "blue")
        result = _downsample(img, factor=2)
        assert result.size == (100, 100)

    def test_minimum_size_1x1(self):
        img = Image.new("RGB", (3, 3), "green")
        result = _downsample(img, factor=10)
        assert result.size == (1, 1)


class TestComputeChangeScore:
    def test_identical_images(self):
        img = Image.new("RGB", (50, 50), (100, 100, 100))
        score = _compute_change_score(img, img)
        assert score == 0.0

    def test_completely_different(self):
        a = Image.new("RGB", (50, 50), (0, 0, 0))
        b = Image.new("RGB", (50, 50), (255, 255, 255))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_slight_difference_below_threshold(self):
        a = Image.new("RGB", (10, 10), (100, 100, 100))
        # Difference of 5 per channel — well below default threshold of 30
        b = Image.new("RGB", (10, 10), (105, 105, 105))
        score = _compute_change_score(a, b)
        assert score == 0.0

    def test_above_threshold_difference(self):
        a = Image.new("RGB", (10, 10), (100, 100, 100))
        b = Image.new("RGB", (10, 10), (200, 200, 200))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_different_sizes_returns_1(self):
        a = Image.new("RGB", (50, 50), "red")
        b = Image.new("RGB", (100, 100), "red")
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_partial_change(self):
        a = Image.new("RGB", (100, 100), (100, 100, 100))
        # Make half the image different
        pixels = list(a.getdata())
        for i in range(len(pixels) // 2):
            pixels[i] = (200, 200, 200)
        b = Image.new("RGB", (100, 100))
        b.putdata(pixels)
        score = _compute_change_score(a, b)
        assert 0.4 < score < 0.6

    def test_empty_image(self):
        a = Image.new("RGB", (0, 0))
        b = Image.new("RGB", (0, 0))
        score = _compute_change_score(a, b)
        assert score == 0.0


class TestSaveSnapshot:
    def test_saves_file(self, tmp_path):
        import core.smart_wait as sw

        orig_tmpdir = sw.tempfile.gettempdir
        sw.tempfile.gettempdir = lambda: str(tmp_path)
        try:
            img = Image.new("RGB", (10, 10), "red")
            path = _save_snapshot(img, prefix="test")
            assert path != ""
            assert path.endswith(".png")
        finally:
            sw.tempfile.gettempdir = orig_tmpdir
