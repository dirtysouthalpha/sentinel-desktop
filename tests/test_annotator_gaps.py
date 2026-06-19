"""Gap tests for core/perception/annotator.py — covers lines 153-155, 199, 216-223."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from core.perception.annotator import _draw_label_tag, _load_font

# ── Lines 153-155 — _draw_label_tag textbbox AttributeError fallback ─────────


class TestDrawLabelTagTextbboxFallback:
    """Lines 153-155 — fallback text sizing when draw.textbbox raises."""

    def _make_draw(self):
        img = Image.new("RGB", (200, 100), "white")
        return ImageDraw.Draw(img)

    def test_attribute_error_on_textbbox_uses_char_count(self):
        draw = self._make_draw()
        # Make textbbox raise AttributeError (old Pillow without textbbox)
        with patch.object(draw, "textbbox", side_effect=AttributeError("no textbbox")):
            # Should not raise — falls back to len(text)*8
            _draw_label_tag(draw, "OK", x=50, y=50, color="#00F0FF", font=None, small_font=None)

    def test_type_error_on_textbbox_uses_char_count(self):
        draw = self._make_draw()
        with patch.object(draw, "textbbox", side_effect=TypeError("bad args")):
            _draw_label_tag(draw, "Submit", x=50, y=50, color="#FFFFFF", font=None, small_font=None)


# ── Line 199 — _load_font Windows font_dirs branch ───────────────────────────


class TestLoadFontWindowsBranch:
    """Line 199 — _load_font appends Windows Fonts dir when os.name == 'nt'."""

    def test_windows_font_dir_appended(self):
        # os is imported locally inside _load_font, patch it at the os module level
        with (
            patch("os.name", "nt"),
            patch.dict(os.environ, {"WINDIR": r"C:\Windows"}),
            patch("PIL.ImageFont.truetype", side_effect=OSError("not found")),
            patch("PIL.ImageFont.load_default", return_value=MagicMock()),
        ):
            font = _load_font(12)
            assert font is not None  # Got fallback font


# ── Lines 215-223 — _load_font OSError fallback and load_default TypeError ───


class TestLoadFontFallbacks:
    """Lines 215-223 — _load_font fallbacks when truetype fails."""

    def test_truetype_oserror_falls_through_to_load_default(self):
        """Line 216 — OSError on truetype → continue; eventually use load_default."""
        # Patch isfile to return True so the loop tries to load, but truetype fails
        with (
            patch("os.path.isfile", return_value=True),
            patch("PIL.ImageFont.truetype", side_effect=OSError("font load failed")),
            patch("PIL.ImageFont.load_default", return_value=MagicMock()) as mock_ld,
        ):
            _load_font(12)
            mock_ld.assert_called()

    def test_load_default_with_size_raises_type_error_falls_back(self):
        """Lines 220-223 — load_default(size=) raises TypeError → bare load_default()."""
        bare_font = MagicMock()

        def _load_default_side_effect(**kwargs):
            if "size" in kwargs:
                raise TypeError("size not supported")
            return bare_font

        with (
            patch("os.path.isfile", return_value=False),
            patch("PIL.ImageFont.load_default", side_effect=_load_default_side_effect),
        ):
            font = _load_font(12)
            assert font is bare_font
