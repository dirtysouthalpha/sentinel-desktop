"""Gap tests for core/smart_wait.py.

Targets uncovered lines: 50-52, 102-104, 270, 303, 360, 392,
472-474, 478-480, 583-585, 668-670.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

from PIL import Image

from core.smart_wait import SmartWait, _crop_to_region

# ---------------------------------------------------------------------------
# Lines 50-52: numpy import fallback
# ---------------------------------------------------------------------------


class TestNumpyImportFallback:
    """When numpy is unavailable, the module must still load and set
    ``_HAS_NUMPY = False`` and ``np = None`` (lines 50-52)."""

    def test_fallback_when_numpy_missing(self):
        orig_np = sys.modules.get("numpy")
        orig_sw = sys.modules.pop("core.smart_wait", None)

        # Block numpy import.
        sys.modules["numpy"] = None  # type: ignore[assignment]

        try:
            mod = importlib.import_module("core.smart_wait")
            assert mod._HAS_NUMPY is False
            assert mod.np is None
        finally:
            # Restore original state.
            if orig_np is not None:
                sys.modules["numpy"] = orig_np
            else:
                sys.modules.pop("numpy", None)
            if orig_sw is not None:
                sys.modules["core.smart_wait"] = orig_sw
            else:
                sys.modules.pop("core.smart_wait", None)
            importlib.reload(sys.modules["core.smart_wait"])


# ---------------------------------------------------------------------------
# Lines 102-104: _crop_to_region exception handler
# ---------------------------------------------------------------------------


class TestCropToRegionException:
    """Cover the (OSError, RuntimeError) except clause in _crop_to_region."""

    @patch("core.smart_wait.capture_screen", side_effect=OSError("screen fail"))
    def test_oserror_on_full_screen_returns_none(self, mock_cap):
        assert _crop_to_region(None) is None
        mock_cap.assert_called_once()

    @patch("core.smart_wait.capture_region", side_effect=RuntimeError("region fail"))
    def test_runtime_error_on_region_returns_none(self, mock_cap):
        assert _crop_to_region((0, 0, 100, 100)) is None
        mock_cap.assert_called_once_with(0, 0, 100, 100)


# ---------------------------------------------------------------------------
# Line 270: wait_for_change baseline capture is None
# ---------------------------------------------------------------------------


class TestWaitForChangeBaselineNone:
    """When the initial capture in wait_for_change returns None, it should
    immediately return a failure result (line 270)."""

    @patch("core.smart_wait._crop_to_region", return_value=None)
    def test_returns_failure_when_baseline_none(self, mock_crop):
        sw = SmartWait()
        result = sw.wait_for_change(timeout=1)
        assert result.success is False
        assert result.frames_checked == 0


# ---------------------------------------------------------------------------
# Line 303: wait_for_change loop current capture is None
# ---------------------------------------------------------------------------


class TestWaitForChangeCurrentNone:
    """When a mid-loop capture returns None, the method should ``continue``
    (line 303) and keep looping until timeout."""

    def test_continues_when_current_is_none(self):
        real_img = Image.new("RGB", (10, 10), "red")
        call_count = 0

        def _fake_crop(_region):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return real_img
            return None

        with patch("core.smart_wait._crop_to_region", side_effect=_fake_crop):
            sw = SmartWait()
            result = sw.wait_for_change(timeout=0.15, interval=0.05)
        assert result.success is False


# ---------------------------------------------------------------------------
# Line 360: wait_for_stable initial capture is None
# ---------------------------------------------------------------------------


class TestWaitForStableBaselineNone:
    """When the initial capture in wait_for_stable returns None, it should
    immediately return a failure result (line 360)."""

    @patch("core.smart_wait._crop_to_region", return_value=None)
    def test_returns_failure_when_baseline_none(self, mock_crop):
        sw = SmartWait()
        result = sw.wait_for_stable(timeout=1)
        assert result.success is False
        assert result.frames_checked == 0


# ---------------------------------------------------------------------------
# Line 392: wait_for_stable loop current capture is None
# ---------------------------------------------------------------------------


class TestWaitForStableCurrentNone:
    """When a mid-loop capture returns None in wait_for_stable, the method
    should ``continue`` (line 392)."""

    def test_continues_when_current_is_none(self):
        real_img = Image.new("RGB", (10, 10), "blue")
        call_count = 0

        def _fake_crop(_region):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return real_img
            return None

        with patch("core.smart_wait._crop_to_region", side_effect=_fake_crop):
            sw = SmartWait()
            result = sw.wait_for_stable(timeout=0.15, interval=0.05)
        assert result.success is False


# ---------------------------------------------------------------------------
# Lines 472-474: wait_for_match find_template exception
# ---------------------------------------------------------------------------


class TestWaitForMatchTemplateException:
    """When ``find_template`` raises (OSError, RuntimeError, ValueError),
    the exception is caught (line 472-474) and ``pos`` is set to None."""

    def test_template_oserror_is_caught(self):
        """find_template raises OSError -> pos=None -> timeout -> failure."""
        mock_ft = MagicMock(side_effect=OSError("template read error"))
        with patch.dict("sys.modules", {"core.screenshot": MagicMock(find_template=mock_ft)}):
            sw = SmartWait()
            result = sw.wait_for_match(template_path="/fake.png", timeout=0.1, interval=0.05)
        assert result.success is False

    def test_template_runtime_error_is_caught(self):
        mock_ft = MagicMock(side_effect=RuntimeError("corrupt template"))
        with patch.dict("sys.modules", {"core.screenshot": MagicMock(find_template=mock_ft)}):
            sw = SmartWait()
            result = sw.wait_for_match(template_path="/fake.png", timeout=0.1, interval=0.05)
        assert result.success is False

    def test_template_value_error_is_caught(self):
        mock_ft = MagicMock(side_effect=ValueError("bad params"))
        with patch.dict("sys.modules", {"core.screenshot": MagicMock(find_template=mock_ft)}):
            sw = SmartWait()
            result = sw.wait_for_match(template_path="/fake.png", timeout=0.1, interval=0.05)
        assert result.success is False


# ---------------------------------------------------------------------------
# Lines 478-480: wait_for_match capture_screen exception after match
# ---------------------------------------------------------------------------


class TestWaitForMatchSnapshotException:
    """After find_template returns a match, capture_screen may raise.
    The exception is caught (lines 478-480) and current is set to None."""

    def test_capture_exception_after_match(self):
        """find_template succeeds, but capture_screen raises OSError."""
        mock_ft = MagicMock(return_value=(10, 20))
        mock_screen = MagicMock(side_effect=OSError("screen capture failed"))
        with patch.dict("sys.modules", {"core.screenshot": MagicMock(find_template=mock_ft)}):
            with patch("core.smart_wait.capture_screen", mock_screen):
                sw = SmartWait()
                result = sw.wait_for_match(template_path="/fake.png", timeout=5, interval=0.1)
        assert result.success is True
        assert result.snapshot_path is None


# ---------------------------------------------------------------------------
# Lines 583-585: wait_for_text post-match snapshot exception
# ---------------------------------------------------------------------------


class TestWaitForTextSnapshotException:
    """After OCR finds text, the post-match snapshot capture may raise.
    The exception is caught (lines 583-585) and snap is set to None."""

    def test_snapshot_capture_exception_after_text_match(self):
        mock_ocr = MagicMock()
        mock_ocr.read_screen_text.return_value = "Hello World"
        with patch.dict("sys.modules", {"core.ocr": mock_ocr}):
            with patch(
                "core.smart_wait._crop_to_region",
                side_effect=OSError("snapshot capture failed"),
            ):
                sw = SmartWait()
                result = sw.wait_for_text(text="Hello", timeout=5, interval=0.1)
        assert result.success is True
        assert result.snapshot_path is None


# ---------------------------------------------------------------------------
# Lines 668-670: wait_for_color snapshot exception
# ---------------------------------------------------------------------------


class TestWaitForColorSnapshotException:
    """After color matches, the context snapshot capture_region may raise.
    The exception is caught (lines 668-670) and snap is set to None."""

    def test_snapshot_exception_after_color_match(self):
        pixel_img = Image.new("RGB", (2, 2), (100, 100, 100))
        call_count = 0

        def _fake_capture_region(x, y, w, h):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return pixel_img
            raise OSError("snapshot region fail")

        with patch("core.smart_wait.capture_region", side_effect=_fake_capture_region):
            sw = SmartWait()
            result = sw.wait_for_color(
                x=50, y=50, target_rgb=(100, 100, 100), tolerance=10, timeout=1
            )
        assert result.success is True
        assert result.snapshot_path is None


# ---------------------------------------------------------------------------
# Pure-PIL 0x0 image edge case (preserved from original file)
# ---------------------------------------------------------------------------


class TestPurePilEmptyImage:
    """0x0 image in pure-PIL path returns 0.0 (line 149)."""

    def test_pure_pil_zero_size_returns_zero(self) -> None:
        import core.smart_wait as sw_mod

        original = sw_mod._HAS_NUMPY
        try:
            sw_mod._HAS_NUMPY = False
            a = Image.new("RGB", (0, 0))
            b = Image.new("RGB", (0, 0))
            score = sw_mod._compute_change_score(a, b)
            assert score == 0.0
        finally:
            sw_mod._HAS_NUMPY = original
