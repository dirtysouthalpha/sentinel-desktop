"""Gap tests for core/control/verifier.py — covers lines 106, 189, 219-221."""

from __future__ import annotations

from unittest.mock import patch

from PIL import Image

from core.control.verifier import (
    ActionVerifier,
    VerifyResult,
    _compute_pixel_diff,
)


class TestComputePixelDiffMismatchedSize:
    """Line 106: different pixel counts → return 100.0."""

    def test_mismatched_pixel_counts_returns_100(self):
        # Force different pixel counts by patching getdata to return different lengths
        before = Image.new("RGB", (200, 200), "white")
        after = Image.new("RGB", (200, 200), "black")

        with patch.object(
            type(before.resize((200, 200), Image.Resampling.BILINEAR).convert("RGB")),
            "getdata",
            side_effect=[list(range(100)), list(range(200))],
        ):
            # Directly test with mocked images that return different pixel counts
            class _FakeImage:
                def resize(self, size, resample=None):
                    return self

                def convert(self, mode):
                    return self

                _data: list

                def getdata(self):
                    return self._data

            img_a = _FakeImage()
            img_a._data = [(255, 255, 255)] * 100

            img_b = _FakeImage()
            img_b._data = [(0, 0, 0)] * 200

            result = _compute_pixel_diff(img_a, img_b)  # type: ignore[arg-type]
            assert result == 100.0


class TestVerifyMinimalChange:
    """Line 189: diff_pct < _MIN_CHANGE_THRESHOLD (0.5%) → NO_CHANGE."""

    def test_tiny_pixel_change_returns_no_change(self):
        # Patch _image_hash so the two images get different hashes (bypasses the
        # early-return equal-hash branch), and patch _compute_pixel_diff to return
        # a value well below the 0.5% threshold.
        before = Image.new("RGB", (200, 200), (128, 128, 128))
        after = before.copy()

        verifier = ActionVerifier()

        with (
            patch("core.control.verifier._image_hash", side_effect=["aaaa", "bbbb"]),
            patch("core.control.verifier._compute_pixel_diff", return_value=0.1),
        ):
            report = verifier.verify(before, after)

        assert report.result == VerifyResult.NO_CHANGE
        assert report.pixel_diff_percent < 0.5


class TestVerifyExceptionHandling:
    """Lines 219-221: exception in verify() → VerifyResult.ERROR."""

    def test_exception_returns_error_report(self):
        before = Image.new("RGB", (200, 200), "white")
        after = Image.new("RGB", (200, 200), "black")

        verifier = ActionVerifier()

        with patch(
            "core.control.verifier._image_hash",
            side_effect=RuntimeError("hash error"),
        ):
            report = verifier.verify(before, after)

        assert report.result == VerifyResult.ERROR
        assert "hash error" in report.details
