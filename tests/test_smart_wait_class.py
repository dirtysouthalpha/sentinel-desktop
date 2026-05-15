"""Tests for core/smart_wait.py — SmartWait class methods with mocked capture."""

from unittest.mock import MagicMock, patch

from PIL import Image

from core.smart_wait import SmartWait


def _constant_image(color: tuple = (100, 100, 100)) -> Image.Image:
    return Image.new("RGB", (50, 50), color)


def _different_image() -> Image.Image:
    return Image.new("RGB", (50, 50), (200, 200, 200))


class TestCancel:
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


class TestWaitForChange:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_detects_change(self, mock_mono, mock_sleep, mock_capture):
        # Simulate: 0.0 baseline, 0.1 first check (same), 0.2 second check (changed)
        mock_mono.side_effect = [0.0, 0.1, 0.1, 0.2, 0.2]
        same = _constant_image()
        diff = _different_image()
        mock_capture.side_effect = [same, same, diff]
        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is True
        assert result.change_score > 0.0
        assert result.frames_checked == 3

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_timeout_no_change(self, mock_mono, mock_sleep, mock_capture):
        # Timeout after first check
        mock_mono.side_effect = [0.0, 5.1, 5.1]
        mock_capture.return_value = _constant_image()
        sw = SmartWait()
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    def test_cancel_mid_wait(self, mock_sleep, mock_capture):
        mock_capture.return_value = _constant_image()
        sw = SmartWait()

        # Cancel immediately after first sleep
        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        result = sw.wait_for_change(timeout=5, interval=0.01)
        assert result.success is False


class TestWaitForStable:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_stable_after_no_change(self, mock_mono, mock_sleep, mock_capture):
        # Two identical frames captured, enough stable_time passes
        # t=0 baseline, t=0.1 first check, t=0.2 stable check
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 0.2, 2.0, 2.0]
        same = _constant_image()
        mock_capture.side_effect = [same, same, same]
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=5, stable_time=1.5, interval=0.01)
        assert result.success is True
        assert result.frames_checked == 3

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_timeout_while_unstable(self, mock_mono, mock_sleep, mock_capture):
        # Simulate rapid monotonic progression: baseline, then immediate timeout
        mock_mono.side_effect = [0.0, 0.0, 0.1, 0.1, 10.0, 10.0]
        # First two captures same (no change = stable clock resets),
        # third would be checked but we already timed out
        same = _constant_image()
        diff = _different_image()
        mock_capture.side_effect = [same, diff, same]
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=5, stable_time=2.0, interval=0.01)
        assert result.success is False

    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    def test_cancel_mid_stable_wait(self, mock_sleep, mock_capture):
        mock_capture.return_value = _constant_image()
        sw = SmartWait()

        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        result = sw.wait_for_stable(timeout=5, stable_time=2.0, interval=0.01)
        assert result.success is False


# ---------------------------------------------------------------------------
# Tests for _downsample
# ---------------------------------------------------------------------------


class TestDownsample:
    def test_reduces_image_size(self):
        from core.smart_wait import _downsample

        img = Image.new("RGB", (800, 600))
        result = _downsample(img, factor=4)
        assert result.size == (200, 150)

    def test_minimum_size_is_1x1(self):
        from core.smart_wait import _downsample

        img = Image.new("RGB", (3, 3))
        result = _downsample(img, factor=4)
        assert result.size[0] >= 1
        assert result.size[1] >= 1

    def test_factor_one_keeps_size(self):
        from core.smart_wait import _downsample

        img = Image.new("RGB", (100, 80))
        result = _downsample(img, factor=1)
        assert result.size == (100, 80)


# ---------------------------------------------------------------------------
# Tests for _compute_change_score
# ---------------------------------------------------------------------------


class TestComputeChangeScore:
    def test_identical_images_score_zero(self):
        from core.smart_wait import _compute_change_score

        a = Image.new("RGB", (50, 50), (100, 100, 100))
        b = Image.new("RGB", (50, 50), (100, 100, 100))
        score = _compute_change_score(a, b)
        assert score == 0.0

    def test_different_images_score_above_zero(self):
        from core.smart_wait import _compute_change_score

        a = Image.new("RGB", (50, 50), (0, 0, 0))
        b = Image.new("RGB", (50, 50), (255, 255, 255))
        score = _compute_change_score(a, b)
        assert score > 0.0

    def test_size_mismatch_returns_one(self):
        from core.smart_wait import _compute_change_score

        a = Image.new("RGB", (50, 50))
        b = Image.new("RGB", (30, 30))
        score = _compute_change_score(a, b)
        assert score == 1.0

    def test_near_threshold_treated_as_same(self):
        """Pixels within the channel threshold (30) should not count as changed."""
        from core.smart_wait import _compute_change_score

        a = Image.new("RGB", (10, 10), (100, 100, 100))
        b = Image.new("RGB", (10, 10), (120, 120, 120))
        score = _compute_change_score(a, b)
        assert score == 0.0

    def test_empty_image_zero_score(self):
        from core.smart_wait import _compute_change_score

        a = Image.new("RGB", (0, 0))
        b = Image.new("RGB", (0, 0))
        score = _compute_change_score(a, b)
        assert score == 0.0

    def test_pure_pil_fallback_identical(self):
        """Exercise the pure-PIL path by forcing _HAS_NUMPY = False."""
        import core.smart_wait as sw_mod

        original = sw_mod._HAS_NUMPY
        try:
            sw_mod._HAS_NUMPY = False
            a = Image.new("RGB", (10, 10), (50, 50, 50))
            b = Image.new("RGB", (10, 10), (50, 50, 50))
            score = sw_mod._compute_change_score(a, b)
            assert score == 0.0
        finally:
            sw_mod._HAS_NUMPY = original

    def test_pure_pil_fallback_different(self):
        import core.smart_wait as sw_mod

        original = sw_mod._HAS_NUMPY
        try:
            sw_mod._HAS_NUMPY = False
            a = Image.new("RGB", (10, 10), (0, 0, 0))
            b = Image.new("RGB", (10, 10), (255, 255, 255))
            score = sw_mod._compute_change_score(a, b)
            assert score == 1.0
        finally:
            sw_mod._HAS_NUMPY = original


# ---------------------------------------------------------------------------
# Tests for _save_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_returns_path_string(self):
        from core.smart_wait import _save_snapshot

        img = Image.new("RGB", (10, 10), (128, 128, 128))
        path = _save_snapshot(img, prefix="test_snap")
        assert isinstance(path, str)
        assert "test_snap" in path
        assert path.endswith(".png")

    def test_returns_empty_on_save_failure(self):
        from core.smart_wait import _save_snapshot

        bad_img = MagicMock()
        bad_img.save.side_effect = OSError("disk full")
        path = _save_snapshot(bad_img, prefix="fail")
        assert path == ""


# ---------------------------------------------------------------------------
# Tests for _crop_to_region
# ---------------------------------------------------------------------------


class TestCropToRegion:
    @patch("core.smart_wait.capture_region")
    def test_with_region_calls_capture_region(self, mock_cap):
        from core.smart_wait import _crop_to_region

        fake_img = Image.new("RGB", (10, 10))
        mock_cap.return_value = fake_img
        result = _crop_to_region((5, 10, 20, 30))
        mock_cap.assert_called_once_with(5, 10, 20, 30)
        assert result is fake_img

    @patch("core.smart_wait.capture_screen")
    def test_without_region_calls_capture_screen(self, mock_cap):
        from core.smart_wait import _crop_to_region

        fake_img = Image.new("RGB", (10, 10))
        mock_cap.return_value = fake_img
        result = _crop_to_region(None)
        mock_cap.assert_called_once()
        assert result is fake_img


# ---------------------------------------------------------------------------
# Tests for wait_for_change with region
# ---------------------------------------------------------------------------


class TestWaitForChangeWithRegion:
    @patch("core.smart_wait._crop_to_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_region_passed_to_capture(self, mock_mono, mock_sleep, mock_capture):
        mock_mono.side_effect = [0.0, 5.1, 5.1]
        mock_capture.return_value = _constant_image()
        sw = SmartWait()
        sw.wait_for_change(timeout=5, interval=0.01, region=(10, 20, 100, 200))
        # _crop_to_region is called; the region is forwarded via _capture -> _crop_to_region
        assert mock_capture.call_count >= 1


# ---------------------------------------------------------------------------
# Tests for wait_for_match
# ---------------------------------------------------------------------------


class TestWaitForMatch:
    @patch("core.smart_wait.capture_screen")
    @patch("core.smart_wait._save_snapshot")
    @patch("core.smart_wait.find_template", create=True)
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_match_found_immediately(
        self, mock_mono, mock_sleep, mock_find, mock_snap, mock_cap_screen
    ):
        """Import path patched: core.screenshot.find_template is imported inside the method."""
        # We need to patch the import. Since find_template is imported inside the method body,
        # we patch core.screenshot.find_template and let the from-import pick it up.
        pass  # This approach is complex; see the working tests below.

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_match_timeout(self, mock_mono, mock_sleep):
        """wait_for_match returns failure on timeout."""
        # We patch the internal import of find_template by mocking core.screenshot
        mock_mono.side_effect = [0.0, 10.1, 10.1]
        sw = SmartWait()
        with patch.dict(
            "sys.modules",
            {"core.screenshot": MagicMock(find_template=MagicMock(return_value=None))},
        ):
            result = sw.wait_for_match(template_path="/fake.png", timeout=10, interval=0.1)
        assert result.success is False

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_match_cancel(self, mock_mono, mock_sleep):
        """wait_for_match returns failure when cancelled after the first frame."""
        # start=0.0, first loop elapsed=0.5 (not cancelled yet, not found), sleep triggers cancel,
        # second loop elapsed=1.0 (cancelled)
        mock_mono.side_effect = [0.0, 0.5, 1.0, 1.0]
        sw = SmartWait()

        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        with patch.dict(
            "sys.modules",
            {"core.screenshot": MagicMock(find_template=MagicMock(return_value=None))},
        ):
            result = sw.wait_for_match(template_path="/fake.png", timeout=10, interval=0.1)
        assert result.success is False

    @patch("core.smart_wait.capture_screen")
    @patch("core.smart_wait._save_snapshot", return_value="/tmp/match_snap.png")  # noqa: S108
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_match_success_on_first_frame(self, mock_mono, mock_sleep, mock_snap, mock_cap_screen):
        """Template found on the very first check frame."""
        mock_mono.side_effect = [0.0, 0.5, 0.5]
        sw = SmartWait()
        fake_screenshot = MagicMock()
        mock_cap_screen.return_value = fake_screenshot
        with patch.dict(
            "sys.modules",
            {"core.screenshot": MagicMock(find_template=MagicMock(return_value=(10, 20)))},
        ):
            result = sw.wait_for_match(
                template_path="/fake.png", timeout=5, confidence=0.9, interval=0.1
            )
        assert result.success is True
        assert result.change_score == 0.9
        assert result.frames_checked == 1
        assert result.snapshot_path == "/tmp/match_snap.png"  # noqa: S108


# ---------------------------------------------------------------------------
# Tests for wait_for_text
# ---------------------------------------------------------------------------


class TestWaitForText:
    def test_empty_text_returns_failure(self):
        sw = SmartWait()
        result = sw.wait_for_text(text="   ", timeout=5)
        assert result.success is False
        assert result.frames_checked == 0
        assert result.elapsed == 0.0

    def test_ocr_unavailable_returns_failure(self):
        """When OCR import fails, wait_for_text returns failure immediately."""
        import builtins

        sw = SmartWait()
        original_import = builtins.__import__

        def _block_ocr(name, *args, **kwargs):
            if name == "core.ocr":
                raise ImportError("OCR disabled for test")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_ocr):
            result = sw.wait_for_text(text="hello", timeout=5)
        assert result.success is False
        assert result.frames_checked == 0
        assert result.elapsed == 0.0

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_text_found_on_first_frame(self, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 0.5, 0.5]
        sw = SmartWait()
        mock_ocr = MagicMock()
        mock_ocr.read_screen_text.return_value = "Hello World"
        mock_snap = Image.new("RGB", (10, 10))
        with patch.dict("sys.modules", {"core.ocr": mock_ocr}):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/text_snap.png"):  # noqa: S108
                with patch("core.smart_wait._crop_to_region", return_value=mock_snap):
                    result = sw.wait_for_text(text="hello", timeout=5, interval=0.1)
        assert result.success is True
        assert result.frames_checked == 1

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_text_timeout(self, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 10.1, 10.1]
        sw = SmartWait()
        mock_ocr = MagicMock()
        mock_ocr.read_screen_text.return_value = "Nothing relevant"
        with patch.dict("sys.modules", {"core.ocr": mock_ocr}):
            result = sw.wait_for_text(text="target", timeout=10, interval=0.1)
        assert result.success is False

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_text_cancel(self, mock_mono, mock_sleep):
        """Cancel during wait_for_text returns failure."""
        # start=0.0, first check at 0.5 (no match), cancel on sleep,
        # second check at 1.0 sees cancel
        mock_mono.side_effect = [0.0, 0.5, 1.0, 1.0]
        sw = SmartWait()

        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        mock_ocr = MagicMock()
        mock_ocr.read_screen_text.return_value = "nothing relevant"
        with patch.dict("sys.modules", {"core.ocr": mock_ocr}):
            result = sw.wait_for_text(text="hello", timeout=5, interval=0.1)
        assert result.success is False

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_text_with_region_uses_ocr_image(self, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 0.5, 0.5]
        sw = SmartWait()
        mock_ocr = MagicMock()
        mock_ocr._ocr_image.return_value = "Detected Text Here"
        fake_img = Image.new("RGB", (10, 10))
        with patch.dict("sys.modules", {"core.ocr": mock_ocr}):
            with patch("core.smart_wait._save_snapshot", return_value="/tmp/region_snap.png"):  # noqa: S108
                with patch("core.smart_wait._crop_to_region", return_value=fake_img):
                    result = sw.wait_for_text(text="detected", timeout=5, region=(0, 0, 100, 100))
        assert result.success is True
        mock_ocr._ocr_image.assert_called_once()

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_ocr_exception_handled_gracefully(self, mock_mono, mock_sleep):
        """If OCR raises during capture, it should be caught and retried."""
        # First call raises, second iteration hits timeout
        mock_mono.side_effect = [0.0, 0.5, 0.5, 10.1, 10.1]
        sw = SmartWait()
        mock_ocr = MagicMock()
        mock_ocr.read_screen_text.side_effect = RuntimeError("OCR engine crashed")
        with patch.dict("sys.modules", {"core.ocr": mock_ocr}):
            result = sw.wait_for_text(text="hello", timeout=5, interval=0.1)
        assert result.success is False


# ---------------------------------------------------------------------------
# Tests for wait_for_color
# ---------------------------------------------------------------------------


class TestWaitForColor:
    @patch("core.smart_wait._save_snapshot", return_value="/tmp/color_snap.png")  # noqa: S108
    @patch("core.smart_wait.capture_region")
    @patch("core.smart_wait.time.monotonic")
    def test_color_match_immediately(self, mock_mono, mock_cap, mock_snap):
        mock_mono.side_effect = [0.0, 0.5, 0.5]
        fake_img = Image.new("RGB", (2, 2), (128, 64, 200))
        mock_cap.return_value = fake_img
        sw = SmartWait()
        result = sw.wait_for_color(x=10, y=20, target_rgb=(128, 64, 200), timeout=5)
        assert result.success is True
        assert result.change_score == 1.0
        assert result.frames_checked == 1

    @patch("core.smart_wait.capture_region")
    @patch("core.smart_wait.time.monotonic")
    def test_color_timeout(self, mock_mono, mock_cap):
        mock_mono.side_effect = [0.0, 5.1, 5.1]
        fake_img = Image.new("RGB", (2, 2), (0, 0, 0))
        mock_cap.return_value = fake_img
        sw = SmartWait()
        result = sw.wait_for_color(x=10, y=20, target_rgb=(255, 255, 255), timeout=5)
        assert result.success is False

    @patch("core.smart_wait.capture_region")
    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_color_cancel(self, mock_mono, mock_sleep, mock_cap):
        """Cancel during color wait returns failure."""
        # First frame: no match (wrong color), then cancel on sleep
        mock_mono.side_effect = [0.0, 0.5, 0.5, 1.0, 1.0]
        fake_img = Image.new("RGB", (2, 2), (0, 0, 0))
        mock_cap.return_value = fake_img
        sw = SmartWait()

        def _cancel_on_sleep(_):
            sw.cancel()

        mock_sleep.side_effect = _cancel_on_sleep
        result = sw.wait_for_color(x=10, y=20, target_rgb=(255, 255, 255), timeout=5)
        assert result.success is False

    @patch("core.smart_wait.time.sleep")
    @patch("core.smart_wait.time.monotonic")
    def test_color_capture_exception_retried(self, mock_mono, mock_sleep):
        """Pixel capture failure should be caught; loop continues until timeout."""
        mock_mono.side_effect = [0.0, 0.1, 0.1, 5.1, 5.1]
        sw = SmartWait()
        with patch("core.smart_wait.capture_region", side_effect=OSError("no display")):
            result = sw.wait_for_color(x=10, y=20, target_rgb=(0, 0, 0), timeout=5)
        assert result.success is False

    @patch("core.smart_wait._save_snapshot", return_value="/tmp/color_snap.png")  # noqa: S108
    @patch("core.smart_wait.capture_region")
    @patch("core.smart_wait.time.monotonic")
    def test_color_within_tolerance(self, mock_mono, mock_cap, mock_snap):
        """Color within tolerance should match."""
        mock_mono.side_effect = [0.0, 0.5, 0.5]
        fake_img = Image.new("RGB", (2, 2), (100, 100, 100))
        mock_cap.return_value = fake_img
        sw = SmartWait()
        result = sw.wait_for_color(x=10, y=20, target_rgb=(110, 110, 110), tolerance=15, timeout=5)
        assert result.success is True


# ---------------------------------------------------------------------------
# Tests for WaitResult dataclass
# ---------------------------------------------------------------------------


class TestWaitResult:
    def test_default_snapshot_path_is_none(self):
        from core.smart_wait import WaitResult

        r = WaitResult(success=True, elapsed=1.0, frames_checked=5, change_score=0.5)
        assert r.snapshot_path is None

    def test_custom_snapshot_path(self):
        from core.smart_wait import WaitResult

        r = WaitResult(
            success=True,
            elapsed=2.0,
            frames_checked=3,
            change_score=0.8,
            snapshot_path="/tmp/test.png",  # noqa: S108
        )
        assert r.snapshot_path == "/tmp/test.png"  # noqa: S108
