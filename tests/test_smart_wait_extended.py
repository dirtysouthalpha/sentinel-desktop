"""Extended tests for core/smart_wait.py — SmartWait class methods and edge cases."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.smart_wait import (
    _CHANNEL_THRESHOLD,
    _DOWNSCALE,
    SmartWait,
    WaitResult,
    _compute_change_score,
    _crop_to_region,
    _downsample,
    _save_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sw():
    """Fresh SmartWait instance."""
    return SmartWait()


def _solid_image(color=(100, 100, 100), size=(50, 50)):
    return Image.new("RGB", size, color)


def _different_image(color=(200, 200, 200), size=(50, 50)):
    return Image.new("RGB", size, color)


# ---------------------------------------------------------------------------
# _crop_to_region
# ---------------------------------------------------------------------------

class TestCropToRegion:
    """Tests for the _crop_to_region helper."""

    @patch("core.smart_wait.capture_screen")
    def test_no_region_calls_capture_screen(self, mock_capture):
        mock_capture.return_value = _solid_image()
        result = _crop_to_region(None)
        mock_capture.assert_called_once()
        assert result is not None

    @patch("core.smart_wait.capture_region")
    def test_with_region_calls_capture_region(self, mock_region):
        mock_region.return_value = _solid_image()
        result = _crop_to_region((10, 20, 100, 200))
        mock_region.assert_called_once_with(10, 20, 100, 200)
        assert result is not None

    @patch("core.smart_wait.capture_screen", side_effect=OSError("no display"))
    def test_returns_none_on_capture_error(self, mock_capture):
        result = _crop_to_region(None)
        assert result is None

    @patch("core.smart_wait.capture_region", side_effect=RuntimeError("fail"))
    def test_returns_none_on_runtime_error(self, mock_region):
        result = _crop_to_region((0, 0, 10, 10))
        assert result is None


# ---------------------------------------------------------------------------
# WaitResult dataclass
# ---------------------------------------------------------------------------

class TestWaitResultExtended:
    """Extended WaitResult tests."""

    def test_equality(self):
        a = WaitResult(success=True, elapsed=1.0, frames_checked=3, change_score=0.5)
        b = WaitResult(success=True, elapsed=1.0, frames_checked=3, change_score=0.5)
        assert a == b

    def test_inequality(self):
        a = WaitResult(success=True, elapsed=1.0, frames_checked=3, change_score=0.5)
        b = WaitResult(success=False, elapsed=1.0, frames_checked=3, change_score=0.5)
        assert a != b

    def test_repr(self):
        r = WaitResult(success=True, elapsed=0.5, frames_checked=1, change_score=0.0)
        rep = repr(r)
        assert "success=True" in rep

    def test_default_snapshot_path_is_none(self):
        r = WaitResult(success=False, elapsed=0.0, frames_checked=0, change_score=0.0)
        assert r.snapshot_path is None

    def test_snapshot_path_stored(self):
        r = WaitResult(
            success=True, elapsed=1.0, frames_checked=2,
            change_score=1.0, snapshot_path="/tmp/test.png",
        )
        assert r.snapshot_path == "/tmp/test.png"


# ---------------------------------------------------------------------------
# _downsample edge cases
# ---------------------------------------------------------------------------

class TestDownsampleExtended:
    def test_factor_1_returns_same_size(self):
        img = _solid_image(size=(64, 64))
        result = _downsample(img, factor=1)
        assert result.size == (64, 64)

    def test_large_factor_gives_1x1(self):
        img = _solid_image(size=(100, 100))
        result = _downsample(img, factor=1000)
        assert result.size == (1, 1)

    def test_non_square_image(self):
        img = _solid_image(size=(200, 100))
        result = _downsample(img, factor=4)
        assert result.size == (50, 25)

    def test_output_is_rgb(self):
        img = _solid_image(size=(100, 100))
        result = _downsample(img, factor=4)
        assert result.mode == "RGB"

    def test_default_factor_is_downscale_constant(self):
        img = _solid_image(size=(100, 100))
        result = _downsample(img)
        expected_size = (100 // _DOWNSCALE, 100 // _DOWNSCALE)
        assert result.size == expected_size


# ---------------------------------------------------------------------------
# _compute_change_score extended
# ---------------------------------------------------------------------------

class TestComputeChangeScoreExtended:
    def test_threshold_boundary_exact(self):
        """Pixels differing by exactly the threshold should NOT count as changed."""
        val = 100
        border = val + _CHANNEL_THRESHOLD  # exactly at threshold
        a = Image.new("RGB", (10, 10), (val, val, val))
        b = Image.new("RGB", (10, 10), (border, val, val))
        score = _compute_change_score(a, b)
        assert score == 0.0  # threshold is strictly > not >=

    def test_threshold_boundary_one_above(self):
        """Pixels differing by threshold+1 should count as changed."""
        val = 100
        over = val + _CHANNEL_THRESHOLD + 1
        a = Image.new("RGB", (10, 10), (val, val, val))
        b = Image.new("RGB", (10, 10), (over, val, val))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_single_channel_difference(self):
        """Only one channel differing should still trigger change."""
        a = Image.new("RGB", (10, 10), (100, 100, 100))
        b = Image.new("RGB", (10, 10), (200, 100, 100))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_grayscale_images(self):
        a = Image.new("L", (10, 10), 100)
        b = Image.new("L", (10, 10), 200)
        score = _compute_change_score(a, b)
        # L mode gets converted to RGB internally
        assert isinstance(score, float)

    def test_very_small_images(self):
        a = Image.new("RGB", (1, 1), (100, 100, 100))
        b = Image.new("RGB", (1, 1), (200, 200, 200))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_identical_complex_images(self):
        """Even complex noise should score 0.0 when identical."""
        img = Image.new("RGB", (20, 20))
        pixels = [(i % 256, (i * 3) % 256, (i * 7) % 256) for i in range(400)]
        img.putdata(pixels)
        score = _compute_change_score(img, img.copy())
        assert score == 0.0


# ---------------------------------------------------------------------------
# _save_snapshot edge cases
# ---------------------------------------------------------------------------

class TestSaveSnapshotExtended:
    def test_creates_png_file(self, tmp_path):
        import core.smart_wait as sw
        orig = sw.tempfile.gettempdir
        sw.tempfile.gettempdir = lambda: str(tmp_path)
        try:
            img = _solid_image()
            path = _save_snapshot(img, prefix="test_ext")
            assert path != ""
            assert path.endswith(".png")
            from pathlib import Path
            assert Path(path).exists()
        finally:
            sw.tempfile.gettempdir = orig

    def test_custom_prefix(self, tmp_path):
        import core.smart_wait as sw
        orig = sw.tempfile.gettempdir
        sw.tempfile.gettempdir = lambda: str(tmp_path)
        try:
            img = _solid_image()
            path = _save_snapshot(img, prefix="myprefix")
            assert "myprefix" in path
        finally:
            sw.tempfile.gettempdir = orig

    @patch("core.smart_wait.Path.mkdir", side_effect=OSError("no space"))
    def test_returns_empty_string_on_failure(self, mock_mkdir):
        img = _solid_image()
        path = _save_snapshot(img, prefix="fail")
        assert path == ""


# ---------------------------------------------------------------------------
# SmartWait — cancel mechanism
# ---------------------------------------------------------------------------

class TestSmartWaitCancel:
    def test_cancel_sets_event(self, sw):
        assert not sw._cancelled()
        sw.cancel()
        assert sw._cancelled()

    def test_reset_cancel_clears_event(self, sw):
        sw.cancel()
        assert sw._cancelled()
        sw._reset_cancel()
        assert not sw._cancelled()

    def test_cancel_from_thread(self, sw):
        """Cancel should be thread-safe."""
        results = []

        def cancel_after_delay():
            time.sleep(0.1)
            sw.cancel()
            results.append("cancelled")

        t = threading.Thread(target=cancel_after_delay)
        t.start()
        time.sleep(0.2)
        t.join()
        assert sw._cancelled()
        assert results == ["cancelled"]


# ---------------------------------------------------------------------------
# SmartWait.wait_for_change — mocked capture
# ---------------------------------------------------------------------------

class TestWaitForChange:
    @patch.object(SmartWait, "_capture")
    def test_returns_success_on_change(self, mock_capture, sw):
        # First call = baseline, second = changed
        mock_capture.side_effect = [
            _solid_image((100, 100, 100)),
            _different_image((200, 200, 200)),
        ]
        result = sw.wait_for_change(timeout=2, interval=0.05)
        assert result.success is True
        assert result.change_score > 0.0
        assert result.frames_checked >= 2

    @patch.object(SmartWait, "_capture", return_value=None)
    def test_returns_failure_when_no_initial_capture(self, mock_capture, sw):
        result = sw.wait_for_change(timeout=1, interval=0.05)
        assert result.success is False
        assert result.frames_checked == 0

    @patch.object(SmartWait, "_capture")
    def test_timeout_returns_failure(self, mock_capture, sw):
        # Always return same image = no change = timeout
        img = _solid_image()
        mock_capture.return_value = img
        result = sw.wait_for_change(timeout=0.2, interval=0.05)
        assert result.success is False

    @patch.object(SmartWait, "_capture")
    def test_cancel_during_wait(self, mock_capture, sw):
        img = _solid_image()
        mock_capture.return_value = img
        # Cancel shortly after starting
        threading.Timer(0.05, sw.cancel).start()
        result = sw.wait_for_change(timeout=2, interval=0.05)
        assert result.success is False

    @patch.object(SmartWait, "_capture")
    def test_elapsed_is_positive(self, mock_capture, sw):
        mock_capture.side_effect = [
            _solid_image((100, 100, 100)),
            _different_image((200, 200, 200)),
        ]
        result = sw.wait_for_change(timeout=5, interval=0.05)
        assert result.elapsed > 0

    @patch.object(SmartWait, "_capture")
    def test_frames_checked_increases(self, mock_capture, sw):
        mock_capture.side_effect = [
            _solid_image((100, 100, 100)),
            _solid_image((100, 100, 100)),
            _different_image((200, 200, 200)),
        ]
        result = sw.wait_for_change(timeout=5, interval=0.05)
        assert result.frames_checked >= 2


# ---------------------------------------------------------------------------
# SmartWait.wait_for_stable — mocked capture
# ---------------------------------------------------------------------------

class TestWaitForStable:
    @patch.object(SmartWait, "_capture")
    def test_returns_success_when_stable(self, mock_capture, sw):
        # First: baseline, then same images = stable
        img = _solid_image()
        mock_capture.side_effect = [img, img.copy(), img.copy()]
        result = sw.wait_for_stable(timeout=2, stable_time=0.1, interval=0.05)
        assert result.success is True

    @patch.object(SmartWait, "_capture", return_value=None)
    def test_returns_failure_when_no_initial_capture(self, mock_capture, sw):
        result = sw.wait_for_stable(timeout=1, interval=0.05)
        assert result.success is False

    @patch.object(SmartWait, "_capture")
    def test_timeout_when_never_stable(self, mock_capture, sw):
        # Alternate between two images = never stable
        a = _solid_image((100, 100, 100))
        b = _different_image((200, 200, 200))
        mock_capture.side_effect = [a, b, a, b, a, b, a, b]
        result = sw.wait_for_stable(timeout=0.3, stable_time=0.2, interval=0.05)
        assert result.success is False

    @patch.object(SmartWait, "_capture")
    def test_cancel_during_wait(self, mock_capture, sw):
        img = _solid_image()
        mock_capture.return_value = img
        # Use a generous stable_time so the cancel timer reliably fires
        # before the stability threshold is met (avoids race condition).
        threading.Timer(0.05, sw.cancel).start()
        result = sw.wait_for_stable(timeout=2, stable_time=1.0, interval=0.05)
        assert result.success is False

    @patch.object(SmartWait, "_capture")
    def test_change_score_on_success(self, mock_capture, sw):
        img = _solid_image()
        mock_capture.side_effect = [img, img.copy(), img.copy()]
        result = sw.wait_for_stable(timeout=2, stable_time=0.1, interval=0.05)
        assert isinstance(result.change_score, float)


# ---------------------------------------------------------------------------
# SmartWait.wait_for_text — mocked OCR
# ---------------------------------------------------------------------------

class TestWaitForText:
    def test_empty_text_returns_immediately(self, sw):
        result = sw.wait_for_text(text="   ", timeout=2)
        assert result.success is False
        assert result.frames_checked == 0

    @patch("core.smart_wait.capture_screen", return_value=_solid_image())
    @patch("core.smart_wait._save_snapshot", return_value="/tmp/snap.png")
    @patch("core.ocr.read_screen_text", return_value="Hello World")
    def test_text_found_immediately(self, mock_ocr, mock_snap, mock_cap, sw):
        # Test OCR text detection with mocked OCR response
        result = sw.wait_for_text(text="Hello World", timeout=2)
        assert result.success is True
        assert result.frames_checked == 1

    def test_whitespace_only_returns_failure(self, sw):
        result = sw.wait_for_text(text="\t\n ", timeout=2)
        assert result.success is False


# ---------------------------------------------------------------------------
# SmartWait.wait_for_color — mocked capture
# ---------------------------------------------------------------------------

class TestWaitForColor:
    @patch("core.smart_wait.capture_region")
    def test_color_match_immediately(self, mock_region, sw):
        # Return a 2x2 image with the target color
        img = Image.new("RGB", (2, 2), (128, 128, 128))
        mock_region.return_value = img
        result = sw.wait_for_color(
            x=10, y=10, target_rgb=(128, 128, 128), tolerance=10, timeout=1,
        )
        assert result.success is True
        assert result.change_score == 1.0

    @patch("core.smart_wait.capture_region", side_effect=OSError("no display"))
    def test_capture_failure_timeout(self, mock_region, sw):
        result = sw.wait_for_color(
            x=10, y=10, target_rgb=(128, 128, 128), timeout=0.2,
        )
        assert result.success is False

    @patch("core.smart_wait.capture_region")
    def test_cancel_during_wait(self, mock_region, sw):
        img = Image.new("RGB", (2, 2), (0, 0, 0))
        mock_region.return_value = img
        threading.Timer(0.05, sw.cancel).start()
        result = sw.wait_for_color(
            x=10, y=10, target_rgb=(255, 255, 255), timeout=2,
        )
        assert result.success is False

    @patch("core.smart_wait.capture_region")
    def test_tolerance_accepts_close_color(self, mock_region, sw):
        img = Image.new("RGB", (2, 2), (125, 125, 125))
        mock_region.return_value = img
        result = sw.wait_for_color(
            x=10, y=10, target_rgb=(128, 128, 128), tolerance=5, timeout=1,
        )
        assert result.success is True

    @patch("core.smart_wait.capture_region")
    def test_tolerance_rejects_far_color(self, mock_region, sw):
        img = Image.new("RGB", (2, 2), (0, 0, 0))
        mock_region.return_value = img
        result = sw.wait_for_color(
            x=10, y=10, target_rgb=(200, 200, 200), tolerance=5, timeout=0.2,
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# SmartWait.wait_for_match — mocked find_template
# ---------------------------------------------------------------------------

class TestWaitForMatch:
    @patch("core.smart_wait.capture_screen", return_value=_solid_image())
    @patch("core.smart_wait._save_snapshot", return_value="/tmp/match.png")
    @patch("core.screenshot.find_template", return_value=(100, 200))
    def test_template_found(self, mock_find, mock_snap, mock_cap, sw):
        result = sw.wait_for_match(
            template_path="/tmp/tpl.png", timeout=2, interval=0.05,
        )
        assert result.success is True

    @patch("core.screenshot.find_template", return_value=None)
    def test_template_not_found_timeout(self, mock_find, sw):
        result = sw.wait_for_match(
            template_path="/tmp/tpl.png", timeout=0.2, interval=0.05,
        )
        assert result.success is False

    @patch("core.screenshot.find_template", side_effect=OSError("fail"))
    def test_find_template_error_continues(self, mock_find, sw):
        """Errors in find_template should be caught, not crash."""
        result = sw.wait_for_match(
            template_path="/tmp/tpl.png", timeout=0.2, interval=0.05,
        )
        assert result.success is False

    @patch("core.screenshot.find_template", return_value=None)
    def test_cancel_during_wait_for_match(self, mock_find, sw):
        threading.Timer(0.05, sw.cancel).start()
        result = sw.wait_for_match(
            template_path="/tmp/tpl.png", timeout=2, interval=0.05,
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_channel_threshold_is_positive(self):
        assert 0 < _CHANNEL_THRESHOLD <= 255

    def test_downscale_is_positive(self):
        assert _DOWNSCALE >= 1

    def test_channel_threshold_reasonable(self):
        # Should be in a reasonable range (10-100)
        assert 10 <= _CHANNEL_THRESHOLD <= 100

    def test_downscale_reasonable(self):
        # Should be 2-8
        assert 2 <= _DOWNSCALE <= 8
