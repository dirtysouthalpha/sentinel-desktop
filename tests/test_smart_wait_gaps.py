"""Gap-filling tests for core/smart_wait.py.

Covers SmartWait class methods (wait_for_change, wait_for_stable, wait_for_match,
wait_for_text, wait_for_color), cancellation, _crop_to_region, and edge cases
that the base test file doesn't exercise.
"""

import threading
import time
from unittest.mock import MagicMock, patch

from PIL import Image

from core.smart_wait import (
    SmartWait,
    WaitResult,
    _crop_to_region,
    _downsample,
    _save_snapshot,
)

# ---------------------------------------------------------------------------
# _crop_to_region
# ---------------------------------------------------------------------------


class TestCropToRegion:
    def test_no_region_calls_capture_screen(self):
        mock_img = Image.new("RGB", (10, 10), "red")
        with patch("core.smart_wait.capture_screen", return_value=mock_img):
            result = _crop_to_region(None)
            assert result is mock_img

    def test_with_region_calls_capture_region(self):
        mock_img = Image.new("RGB", (10, 10), "blue")
        with patch("core.smart_wait.capture_region", return_value=mock_img) as mock_cr:
            result = _crop_to_region((100, 200, 300, 400))
            assert result is mock_img
            mock_cr.assert_called_once_with(100, 200, 300, 400)

    def test_oserror_returns_none(self):
        with patch("core.smart_wait.capture_screen", side_effect=OSError("no screen")):
            result = _crop_to_region(None)
            assert result is None

    def test_runtime_error_returns_none(self):
        with patch("core.smart_wait.capture_screen", side_effect=RuntimeError("fail")):
            result = _crop_to_region(None)
            assert result is None


# ---------------------------------------------------------------------------
# SmartWait cancellation
# ---------------------------------------------------------------------------


class TestSmartWaitCancellation:
    def test_cancel_sets_event(self):
        sw = SmartWait()
        assert not sw._cancelled()
        sw.cancel()
        assert sw._cancelled()

    def test_reset_cancel_clears_event(self):
        sw = SmartWait()
        sw.cancel()
        assert sw._cancelled()
        sw._reset_cancel()
        assert not sw._cancelled()


# ---------------------------------------------------------------------------
# wait_for_change
# ---------------------------------------------------------------------------


class TestWaitForChange:
    def test_baseline_capture_fails(self):
        """If initial capture fails, should return failure immediately."""
        sw = SmartWait()
        with patch.object(sw, "_capture", return_value=None):
            result = sw.wait_for_change(timeout=1, interval=0.05)
            assert result.success is False
            assert result.frames_checked == 0

    def test_detects_change_immediately(self):
        """First poll shows change → success."""
        sw = SmartWait()
        baseline = Image.new("RGB", (100, 100), (100, 100, 100))
        changed = Image.new("RGB", (100, 100), (200, 200, 200))
        # First call: baseline, second call: changed
        with patch.object(sw, "_capture", side_effect=[baseline, changed]):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/test.png"):
                result = sw.wait_for_change(timeout=2, interval=0.05)
                assert result.success is True
                assert result.frames_checked == 2
                assert result.change_score > 0

    def test_timeout_returns_failure(self):
        """No change within timeout → failure."""
        sw = SmartWait()
        same_img = Image.new("RGB", (50, 50), (50, 50, 50))
        with patch.object(sw, "_capture", return_value=same_img):
            result = sw.wait_for_change(timeout=0.3, interval=0.1)
            assert result.success is False

    def test_cancellation_mid_wait(self):
        """Cancel from another thread → failure result."""
        sw = SmartWait()
        same_img = Image.new("RGB", (50, 50), (100, 100, 100))
        with patch.object(sw, "_capture", return_value=same_img):
            # Cancel after a short delay
            def cancel_later():
                time.sleep(0.1)
                sw.cancel()

            t = threading.Thread(target=cancel_later)
            t.start()
            result = sw.wait_for_change(timeout=5, interval=0.05)
            t.join()
            assert result.success is False

    def test_none_capture_skipped(self):
        """If a poll returns None (capture failure), it should be skipped."""
        sw = SmartWait()
        baseline = Image.new("RGB", (50, 50), (100, 100, 100))
        changed = Image.new("RGB", (50, 50), (200, 200, 200))
        # baseline, None, changed
        with patch.object(sw, "_capture", side_effect=[baseline, None, changed]):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/test.png"):
                result = sw.wait_for_change(timeout=2, interval=0.05)
                assert result.success is True


# ---------------------------------------------------------------------------
# wait_for_stable
# ---------------------------------------------------------------------------


class TestWaitForStable:
    def test_initial_capture_fails(self):
        sw = SmartWait()
        with patch.object(sw, "_capture", return_value=None):
            result = sw.wait_for_stable(timeout=1, interval=0.05)
            assert result.success is False
            assert result.frames_checked == 0

    def test_already_stable(self):
        """If screen never changes, should become stable after stable_time."""
        sw = SmartWait()
        same_img = Image.new("RGB", (50, 50), (100, 100, 100))
        with patch.object(sw, "_capture", return_value=same_img):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/test.png"):
                result = sw.wait_for_stable(
                    timeout=5, stable_time=0.2, interval=0.05
                )
                assert result.success is True

    def test_timeout_while_changing(self):
        """Screen keeps changing → timeout."""
        sw = SmartWait()
        images = []
        for i in range(30):
            images.append(Image.new("RGB", (50, 50), (i * 8, i * 8, i * 8)))
        with patch.object(sw, "_capture", side_effect=images):
            result = sw.wait_for_stable(timeout=0.5, stable_time=1.0, interval=0.05)
            assert result.success is False

    def test_cancellation(self):
        sw = SmartWait()
        same_img = Image.new("RGB", (50, 50), (100, 100, 100))
        with patch.object(sw, "_capture", return_value=same_img):

            def cancel_later():
                time.sleep(0.1)
                sw.cancel()

            t = threading.Thread(target=cancel_later)
            t.start()
            result = sw.wait_for_stable(timeout=5, stable_time=5.0, interval=0.05)
            t.join()
            assert result.success is False


# ---------------------------------------------------------------------------
# wait_for_match
# ---------------------------------------------------------------------------


class TestWaitForMatch:
    def test_match_found_immediately(self):
        sw = SmartWait()
        mock_img = Image.new("RGB", (10, 10))
        with patch("core.screenshot.find_template", return_value=(50, 50)):
            with patch("core.smart_wait.capture_screen", return_value=mock_img):
                with patch("core.smart_wait._save_snapshot", return_value="/tmp/match.png"):
                    result = sw.wait_for_match("/tmp/tmpl.png", timeout=1, interval=0.05)
                    assert result.success is True
                    assert result.change_score == 0.8  # default confidence

    def test_timeout_no_match(self):
        sw = SmartWait()
        with patch("core.screenshot.find_template", return_value=None):
            result = sw.wait_for_match("/tmp/tmpl.png", timeout=0.3, interval=0.1)
            assert result.success is False

    def test_template_error_handled(self):
        """Template matching that raises should be treated as no match."""
        sw = SmartWait()
        call_count = 0

        def mock_find(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("template read error")
            return None

        with patch("core.screenshot.find_template", side_effect=mock_find):
            result = sw.wait_for_match("/tmp/tmpl.png", timeout=0.5, interval=0.1)
            assert result.success is False
            assert call_count >= 1

    def test_cancellation(self):
        sw = SmartWait()
        with patch("core.screenshot.find_template", return_value=None):

            def cancel_later():
                time.sleep(0.1)
                sw.cancel()

            t = threading.Thread(target=cancel_later)
            t.start()
            result = sw.wait_for_match("/tmp/tmpl.png", timeout=5, interval=0.05)
            t.join()
            assert result.success is False

    def test_custom_confidence(self):
        sw = SmartWait()
        mock_img = Image.new("RGB", (10, 10))
        with patch("core.screenshot.find_template", return_value=(10, 20)):
            with patch("core.smart_wait.capture_screen", return_value=mock_img):
                with patch("core.smart_wait._save_snapshot", return_value="/tmp/match.png"):
                    result = sw.wait_for_match(
                        "/tmp/tmpl.png", timeout=1, confidence=0.95, interval=0.05
                    )
                    assert result.success is True
                    assert result.change_score == 0.95


# ---------------------------------------------------------------------------
# wait_for_text
# ---------------------------------------------------------------------------


class TestWaitForText:
    def test_empty_text_returns_failure(self):
        sw = SmartWait()
        result = sw.wait_for_text("  ", timeout=1)
        assert result.success is False
        assert result.frames_checked == 0

    def test_ocr_unavailable(self):
        sw = SmartWait()
        with patch.dict("sys.modules", {"core.ocr": None}):
            # Force import to fail
            with patch("builtins.__import__", side_effect=ImportError("no ocr")):
                result = sw.wait_for_text("hello", timeout=1)
                assert result.success is False

    def test_text_found(self):
        sw = SmartWait()
        mock_img = Image.new("RGB", (10, 10))
        with patch("core.ocr.read_screen_text", return_value="Hello World"):
            with patch.object(sw, "_capture", return_value=mock_img):
                with patch("core.smart_wait._save_snapshot", return_value="/tmp/text.png"):
                    result = sw.wait_for_text("hello", timeout=1, interval=0.05)
                    assert result.success is True
                    assert result.change_score == 1.0

    def test_text_case_insensitive(self):
        sw = SmartWait()
        mock_img = Image.new("RGB", (10, 10))
        with patch("core.ocr.read_screen_text", return_value="WELCOME HOME"):
            with patch.object(sw, "_capture", return_value=mock_img):
                with patch("core.smart_wait._save_snapshot", return_value="/tmp/text.png"):
                    result = sw.wait_for_text("welcome", timeout=1, interval=0.05)
                    assert result.success is True

    def test_text_not_found_timeout(self):
        sw = SmartWait()
        with patch("core.ocr.read_screen_text", return_value="no match here"):
            result = sw.wait_for_text("target", timeout=0.3, interval=0.1)
            assert result.success is False

    def test_cancellation(self):
        sw = SmartWait()
        with patch("core.ocr.read_screen_text", return_value="no match"):

            def cancel_later():
                time.sleep(0.1)
                sw.cancel()

            t = threading.Thread(target=cancel_later)
            t.start()
            result = sw.wait_for_text("target", timeout=5, interval=0.05)
            t.join()
            assert result.success is False


# ---------------------------------------------------------------------------
# wait_for_color
# ---------------------------------------------------------------------------


class TestWaitForColor:
    def test_color_match_immediately(self):
        sw = SmartWait()
        # Pixel (0,0) = (100, 150, 200), target = (100, 150, 200)
        img = Image.new("RGB", (2, 2), (100, 150, 200))
        snap_img = Image.new("RGB", (100, 100), (100, 150, 200))
        with patch("core.smart_wait.capture_region", side_effect=[img, snap_img]):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/color.png"):
                result = sw.wait_for_color(10, 20, (100, 150, 200), timeout=1)
                assert result.success is True
                assert result.change_score == 1.0

    def test_color_within_tolerance(self):
        sw = SmartWait()
        img = Image.new("RGB", (2, 2), (105, 155, 205))
        snap_img = Image.new("RGB", (100, 100), (105, 155, 205))
        with patch("core.smart_wait.capture_region", side_effect=[img, snap_img]):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/color.png"):
                result = sw.wait_for_color(
                    10, 20, (100, 150, 200), tolerance=10, timeout=1
                )
                assert result.success is True

    def test_color_outside_tolerance(self):
        sw = SmartWait()
        # Target (100,100,100) but pixel is (200,200,200), tolerance=10
        img = Image.new("RGB", (2, 2), (200, 200, 200))
        with patch("core.smart_wait.capture_region", return_value=img):
            result = sw.wait_for_color(10, 20, (100, 100, 100), tolerance=10, timeout=0.3)
            assert result.success is False

    def test_pixel_capture_failure_continues(self):
        """If pixel capture fails, it should retry, not crash."""
        sw = SmartWait()
        fail_img = Image.new("RGB", (2, 2), (100, 100, 100))
        snap_img = Image.new("RGB", (100, 100), (100, 100, 100))
        # First two capture_region calls fail, third succeeds
        with patch(
            "core.smart_wait.capture_region",
            side_effect=[
                OSError("fail"),
                fail_img,
                snap_img,
            ],
        ):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/color.png"):
                result = sw.wait_for_color(10, 20, (100, 100, 100), timeout=2)
                assert result.success is True

    def test_cancellation(self):
        sw = SmartWait()
        img = Image.new("RGB", (2, 2), (0, 0, 0))
        with patch("core.smart_wait.capture_region", return_value=img):

            def cancel_later():
                time.sleep(0.1)
                sw.cancel()

            t = threading.Thread(target=cancel_later)
            t.start()
            result = sw.wait_for_color(10, 20, (255, 255, 255), timeout=5)
            t.join()
            assert result.success is False


# ---------------------------------------------------------------------------
# Edge cases for helpers
# ---------------------------------------------------------------------------


class TestDownsampleEdgeCases:
    def test_factor_1_no_change(self):
        img = Image.new("RGB", (50, 50), "red")
        result = _downsample(img, factor=1)
        assert result.size == (50, 50)

    def test_grayscale_image(self):
        img = Image.new("L", (100, 100), 128)
        result = _downsample(img, factor=4)
        assert result.size == (25, 25)


class TestSaveSnapshotEdgeCases:
    def test_save_failure_returns_empty(self, tmp_path):
        """If image.save fails, should return empty string."""
        import core.smart_wait as sw

        orig_tmpdir = sw.tempfile.gettempdir
        sw.tempfile.gettempdir = lambda: str(tmp_path)
        try:
            mock_img = MagicMock()
            mock_img.save.side_effect = OSError("disk full")
            path = _save_snapshot(mock_img, prefix="fail")
            assert path == ""
        finally:
            sw.tempfile.gettempdir = orig_tmpdir


class TestWaitResultDefaults:
    def test_equality(self):
        a = WaitResult(success=True, elapsed=1.0, frames_checked=5, change_score=0.5)
        b = WaitResult(success=True, elapsed=1.0, frames_checked=5, change_score=0.5)
        assert a == b

    def test_inequality(self):
        a = WaitResult(success=True, elapsed=1.0, frames_checked=5, change_score=0.5)
        b = WaitResult(success=False, elapsed=1.0, frames_checked=5, change_score=0.5)
        assert a != b
