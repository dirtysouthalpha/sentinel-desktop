"""
Sentinel Desktop v2 — OCR (text-on-screen) utilities.

Uses ``pytesseract`` when Tesseract is installed on the host. With Tesseract
the agent gains:

* ``click_text``: locate visible text and click its centre.
* ``read_text``: dump the whole screen as text (handy for forms, dialogs,
  read-only viewers).

If pytesseract or the Tesseract binary aren't available, the helpers return
``None`` / ``""`` and log once — the agent then falls back to the vision
model's pixel reasoning.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from core.screenshot import (
    capture_focused_window_with_title,
    capture_screen,
    capture_window,
    get_capture_offset,
)

# Set to False (via config) to OCR the raw screenshot. Default-on because
# Tesseract is noticeably more accurate on preprocessed UI text.
PREPROCESS_DEFAULT = True

# Heuristic: when OCR output has fewer than this many alphanumeric chars
# per line we flag the result as "low confidence" so the LLM can fall back
# to the vision model.
_MIN_ALNUM_PER_LINE_FOR_CONFIDENT = 6

logger = logging.getLogger(__name__)

_TESSERACT_OK: bool | None = None  # None = not yet probed
_pytesseract = None


def _have_tesseract() -> bool:
    """Lazily probe for pytesseract + the Tesseract binary."""
    global _TESSERACT_OK, _pytesseract
    if _TESSERACT_OK is not None:
        return _TESSERACT_OK
    try:
        import pytesseract  # type: ignore

        # Touch the binary to confirm it's reachable.
        pytesseract.get_tesseract_version()
        _pytesseract = pytesseract
        _TESSERACT_OK = True
    except Exception as exc:
        logger.info(
            "OCR disabled — install Tesseract + pytesseract to enable click_text / read_text (%s)",
            exc,
        )
        _TESSERACT_OK = False
    return _TESSERACT_OK


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Apply a cheap, robust pipeline to make UI text easier for Tesseract.

    Steps:
      1. Upscale 2x via LANCZOS — Tesseract works much better at >300 DPI.
      2. Convert to grayscale.
      3. Auto-contrast (stretch the histogram so faint text pops).
      4. Mild unsharp-mask to crisp up anti-aliased glyph edges.

    Skipped on tiny images (already small enough to be problematic).
    """
    try:
        w, h = img.size
        # Don't upscale anything already huge — Tesseract will choke.
        if w * h < 4_000_000:  # roughly <2000x2000
            img = img.resize((w * 2, h * 2), Image.LANCZOS)
        img = img.convert("L")  # grayscale
        img = ImageOps.autocontrast(img, cutoff=2)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=2))
        # Light contrast boost — too aggressive blows out hairline strokes.
        img = ImageEnhance.Contrast(img).enhance(1.25)
        return img
    except Exception as exc:
        logger.debug("preprocess_for_ocr failed (falling back to raw): %s", exc)
        return img


def _ocr_image(img: Image.Image, preprocess: bool = PREPROCESS_DEFAULT) -> str:
    """OCR a PIL Image with optional preprocessing."""
    if not _have_tesseract():
        return ""
    try:
        target = preprocess_for_ocr(img) if preprocess else img
        return _pytesseract.image_to_string(target)  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("Tesseract failed: %s", exc)
        return ""


def looks_low_confidence(text: str) -> bool:
    """Heuristic: does this OCR output look like garbled junk?

    Returns True for strings that are mostly punctuation, special symbols,
    or have very few alphanumeric characters per line. The agent uses this
    to decide whether to fall back to the vision model.
    """
    if not text or not text.strip():
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    total_alnum = sum(c.isalnum() for c in text)
    if total_alnum < 20:
        return True
    avg_alnum_per_line = total_alnum / len(lines)
    return avg_alnum_per_line < _MIN_ALNUM_PER_LINE_FOR_CONFIDENT


def read_screen_text(monitor: int | None = None, preprocess: bool = PREPROCESS_DEFAULT) -> str:
    """OCR the screen and return the raw text. Empty string if OCR is unavailable."""
    if not _have_tesseract():
        return ""
    try:
        img = capture_screen(monitor=monitor)
        return _ocr_image(img, preprocess=preprocess)
    except Exception as exc:
        logger.warning("read_screen_text failed: %s", exc)
        return ""


def read_focused_window_text() -> str:
    """OCR the agent's target window (foreground, but skipping the Sentinel GUI)."""
    text, _title = read_focused_window_text_with_title()
    return text


def read_focused_window_text_with_title() -> tuple[str, str]:
    """Return (text, title) of the OCR'd window so callers can surface what
    window was actually read. Useful for debugging multi-monitor confusion."""
    if not _have_tesseract():
        return ("", "")
    try:
        pair = capture_focused_window_with_title()
        if pair is None:
            return (read_screen_text(), "<full screen fallback>")
        img, title = pair
        return (_ocr_image(img), title)
    except Exception as exc:
        logger.debug("read_focused_window_text_with_title failed: %s", exc)
        return ("", "")


def read_window_text(title: str) -> str:
    """OCR a window whose title contains *title*. Returns '' if not found."""
    if not title or not _have_tesseract():
        return ""
    try:
        img = capture_window(title)
        if img is None:
            return ""
        return _ocr_image(img)
    except Exception as exc:
        logger.debug("read_window_text(%s) failed: %s", title, exc)
        return ""


def find_text(
    query: str,
    *,
    fuzzy: bool = True,
    min_score: float = 0.7,
    monitor: int | None = None,
) -> tuple[int, int] | None:
    """Locate *query* on screen via OCR. Returns the centre (x, y) or ``None``.

    Matching strategy:
      1. Case-insensitive exact substring match across word-level OCR boxes.
      2. If no exact hit, fuzzy-match each line (SequenceMatcher >= min_score).

    Args:
        query: The text to find. Whitespace-collapsed and lowercased.
        fuzzy: Whether to attempt fuzzy matching after exact search fails.
        min_score: Minimum SequenceMatcher ratio for fuzzy matches (0.0–1.0).
        monitor: Pass-through to ``capture_screen``.
    """
    if not query or not _have_tesseract():
        return None
    needle = re.sub(r"\s+", " ", query).strip().lower()
    if not needle:
        return None

    try:
        img = capture_screen(monitor=monitor)
        data: dict[str, list[Any]] = _pytesseract.image_to_data(  # type: ignore[union-attr]
            img,
            output_type=_pytesseract.Output.DICT,  # type: ignore[union-attr]
        )
    except Exception as exc:
        logger.warning("OCR find_text failed: %s", exc)
        return None

    boxes = _boxes_from_data(data)
    offset_x, offset_y = get_capture_offset(monitor)

    # 1) Exact substring on the joined line text.
    hit = _exact_substring_hit(boxes, needle)
    if hit is not None:
        return (hit[0] + offset_x, hit[1] + offset_y)

    # 2) Fuzzy on each line.
    if fuzzy:
        hit = _fuzzy_line_hit(boxes, needle, min_score)
        if hit is not None:
            return (hit[0] + offset_x, hit[1] + offset_y)
    return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _boxes_from_data(data: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Normalise pytesseract's ``image_to_data`` output to per-word boxes."""
    n = len(data.get("text", []))
    boxes: list[dict[str, Any]] = []
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            logger.debug("Invalid confidence value at index %d: %r", i, data["conf"][i])
            conf = 0.0
        if conf < 30:  # Drop low-confidence cells.
            continue
        boxes.append(
            {
                "text": text,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
                "line_id": (
                    int(data.get("block_num", [0])[i]),
                    int(data.get("par_num", [0])[i]),
                    int(data.get("line_num", [0])[i]),
                ),
            }
        )
    return boxes


def _exact_substring_hit(
    boxes: list[dict[str, Any]],
    needle: str,
) -> tuple[int, int] | None:
    # Group word boxes into lines, then test the joined lower-cased line text.
    by_line: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for b in boxes:
        by_line.setdefault(b["line_id"], []).append(b)

    for _line_id, words in by_line.items():
        words.sort(key=lambda w: w["x"])
        joined = " ".join(w["text"] for w in words).lower()
        if needle in joined:
            # Find which word(s) cover the needle and return their centroid.
            covering = _words_covering_substring(words, needle)
            result = _centroid(covering)
            if result is not None:
                return result
    return None


def _words_covering_substring(
    words: list[dict[str, Any]],
    needle: str,
) -> list[dict[str, Any]]:
    """Return the subset of word boxes whose joined text covers the needle."""
    joined = ""
    spans = []  # (char_start, char_end_exclusive, word_index)
    for idx, w in enumerate(words):
        token = w["text"].lower()
        if joined:
            joined += " "
        start = len(joined)
        joined += token
        spans.append((start, len(joined), idx))

    pos = joined.find(needle)
    if pos < 0:
        return words  # fall back: whole line
    end = pos + len(needle)
    covering_idx = [idx for (s, e, idx) in spans if not (e <= pos or s >= end)]
    return [words[i] for i in covering_idx] or words


def _fuzzy_line_hit(
    boxes: list[dict[str, Any]],
    needle: str,
    min_score: float,
) -> tuple[int, int] | None:
    by_line: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for b in boxes:
        by_line.setdefault(b["line_id"], []).append(b)

    best_score = 0.0
    best_words: list[dict[str, Any]] | None = None
    for words in by_line.values():
        words.sort(key=lambda w: w["x"])
        joined = " ".join(w["text"] for w in words).lower()
        score = SequenceMatcher(None, needle, joined).ratio()
        if score > best_score:
            best_score = score
            best_words = words

    if best_words is not None and best_score >= min_score:
        result = _centroid(best_words)
        if result is not None:
            return result
    return None


def _centroid(boxes: list[dict[str, Any]]) -> tuple[int, int] | None:
    if not boxes:
        return None
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return ((x0 + x1) // 2, (y0 + y1) // 2)
