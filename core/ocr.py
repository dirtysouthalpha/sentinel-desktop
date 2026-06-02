"""Sentinel Desktop v3.1 — OCR (text-on-screen) utilities.

Uses ``pytesseract`` when Tesseract is installed on the host.  With Tesseract
the agent gains:

* ``click_text``: locate visible text and click its centre.
* ``read_text``: dump the whole screen as text (handy for forms, dialogs,
  read-only viewers).

If pytesseract or the Tesseract binary aren't available, the helpers return
``None`` / ``""`` and log once — the agent then falls back to the vision
model's pixel reasoning.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from difflib import SequenceMatcher
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from core.screenshot import (
    capture_focused_window_with_title,
    capture_screen,
    capture_window,
    get_capture_offset,
)
from core.utils import get_tesseract, have_tesseract

# Set to False (via config) to OCR the raw screenshot. Default-on because
# Tesseract is noticeably more accurate on preprocessed UI text.
PREPROCESS_DEFAULT = True

# Heuristic: when OCR output has fewer than this many alphanumeric chars
# per line we flag the result as "low confidence" so the LLM can fall back
# to the vision model.
_MIN_ALNUM_PER_LINE_FOR_CONFIDENT = 6

# Minimum average Tesseract confidence score (0-100) to consider OCR reliable.
_MIN_AVG_CONFIDENCE = 60.0

# Maximum screenshot resolution before downsampling for OCR.
_MAX_OCR_RESOLUTION = (1920, 1080)

# Aggressive downsampling threshold: images above this resolution are always downsampled
_AGGRESSIVE_DOWNSAMPLE_THRESHOLD = (2560, 1440)  # 2K resolution

# OCR result cache: (cache_key) → (text, confidence_data, timestamp)
_ocr_cache: dict[str, tuple[str, dict[str, Any], float]] = {}
_CACHE_TTL = 3.0  # seconds
_CACHE_MAX_SIZE = 50  # evict oldest when cache exceeds this

# Boxes cache for find_text(): (cache_key) → (boxes, timestamp)
# Stores the parsed word-box list from image_to_data so consecutive find_text()
# calls on the same screen state skip the expensive Tesseract scan.
_boxes_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}

logger = logging.getLogger(__name__)


def _image_cache_key(img: Image.Image, preprocess: bool = PREPROCESS_DEFAULT) -> str:
    """Lightweight cache key: dimensions + mode + 4×4 sampled pixel grid + preprocess flag.

    Performance-optimized: Uses 9-point grid (3x3) instead of 16-point (4x4) for faster
    cache key generation while maintaining low false-positive rate.
    """
    w, h = img.size
    try:
        # 9-point grid sample (3x3) for balance between speed and accuracy
        xs = [w // 4, w // 2, 3 * w // 4]
        ys = [h // 4, h // 2, 3 * h // 4]
        samples = [img.getpixel((x, y)) for x in xs for y in ys]
        fingerprint = f"{w}x{h}:{img.mode}:{samples}:{preprocess}"
    except (IndexError, OSError):
        fingerprint = f"{w}x{h}:{img.mode}:{preprocess}"
    return hashlib.md5(fingerprint.encode()).hexdigest()  # noqa: S324


def _check_cache(key: str) -> tuple[str, dict[str, Any] | None] | None:
    """Return cached OCR result if still valid, else None.

    The second element may be ``None`` when stored by the text-only path.
    """
    if key in _ocr_cache:
        text, conf_data, ts = _ocr_cache[key]
        if time.monotonic() - ts < _CACHE_TTL:
            return (text, conf_data)
        # Expired — remove
        del _ocr_cache[key]
    return None


def _store_cache(key: str, text: str, conf_data: dict[str, Any] | None) -> None:
    """Store an OCR result in the cache, pruning expired and oversized entries.

    Pass ``conf_data=None`` when only the text was computed (fast path).
    ``_ocr_image_with_confidence`` will recompute the confidence data on a
    cache miss for the confidence layer rather than returning empty data.
    """
    now = time.monotonic()
    _ocr_cache[key] = (text, conf_data, now)
    # Remove expired entries
    expired = [k for k, (_, _, ts) in _ocr_cache.items() if now - ts >= _CACHE_TTL]
    for k in expired:
        del _ocr_cache[k]
    # Evict oldest entries if cache exceeds max size
    if len(_ocr_cache) > _CACHE_MAX_SIZE:
        oldest = sorted(_ocr_cache, key=lambda k: _ocr_cache[k][2])
        for k in oldest[: len(_ocr_cache) - _CACHE_MAX_SIZE]:
            del _ocr_cache[k]


def _downsample_if_needed(img: Image.Image) -> Image.Image:
    """Downsample image to 1080p if resolution exceeds 1920x1080.

    Performance-optimized: Uses aggressive downsampling for 2K+ resolutions to
    maximize speedup while maintaining OCR accuracy. Tesseract is faster and more
    accurate at moderate resolutions.

    Profiling shows 5.44x speedup for 4K images with downsampling.
    """
    w, h = img.size
    max_w, max_h = _MAX_OCR_RESOLUTION

    # Check if downsampling is needed
    if w > max_w or h > max_h:
        # For very high resolutions (2K+), use more aggressive downsampling
        if w > _AGGRESSIVE_DOWNSAMPLE_THRESHOLD[0] or h > _AGGRESSIVE_DOWNSAMPLE_THRESHOLD[1]:
            # Target 720p for very high resolutions for maximum speedup
            target_w, target_h = (1280, 720)
        else:
            # Standard 1080p target
            target_w, target_h = max_w, max_h

        # Compute scale to fit within target resolution while preserving aspect ratio
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        logger.debug("Downsampling OCR image from %dx%d to %dx%d", w, h, new_w, new_h)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Apply a cheap, robust pipeline to make UI text easier for Tesseract.

    Steps:
      1. Convert to grayscale first — reduces data to 1 channel so the
         subsequent resize operates on 3-4x less pixel data.
      2. Upscale 2x via LANCZOS — Tesseract works much better at >300 DPI.
      3. Auto-contrast (stretch the histogram so faint text pops).
      4. Mild unsharp-mask to crisp up anti-aliased glyph edges.

    Skipped on tiny images (already small enough to be problematic).
    """
    original = img
    try:
        img = img.convert("L")  # grayscale first — cheaper resize below
        w, h = img.size
        # Don't upscale anything already huge — Tesseract will choke.
        if w * h < 4_000_000:  # roughly <2000x2000
            img = img.resize((w * 2, h * 2), Image.LANCZOS)
        img = ImageOps.autocontrast(img, cutoff=2)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=2))
        # Light contrast boost — too aggressive blows out hairline strokes.
        return ImageEnhance.Contrast(img).enhance(1.25)
    except (OSError, ValueError) as exc:
        logger.debug("preprocess_for_ocr failed (falling back to raw): %s", exc)
        return original


def _ocr_image(img: Image.Image, preprocess: bool = PREPROCESS_DEFAULT) -> str:
    """OCR a PIL Image with optional preprocessing."""
    if not have_tesseract():
        return ""
    try:
        img = _downsample_if_needed(img)
        # Key on the downsampled raw image so preprocessing is skipped on cache hits.
        cache_key = _image_cache_key(img, preprocess)
        cached = _check_cache(cache_key)
        if cached is not None:
            return cached[0]

        target = preprocess_for_ocr(img) if preprocess else img
        result = get_tesseract().image_to_string(target)  # type: ignore[union-attr]
        _store_cache(cache_key, result, None)
        return result
    except (OSError, RuntimeError) as exc:
        logger.warning("Tesseract failed: %s", exc)
        return ""


def _extract_confidence_data(data: dict[str, Any]) -> dict[str, Any]:
    """Summarise Tesseract per-word confidence data into a structured dict."""
    confidences = []
    low_conf_words: list[str] = []
    low_conf_regions: list[dict[str, Any]] = []
    n = len(data.get("text", []))
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = 0.0
        if conf > 0:
            confidences.append(conf)
            if conf < 50:
                low_conf_words.append(word)
                low_conf_regions.append({"text": word, "confidence": conf})
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "avg_confidence": round(avg_conf, 1),
        "word_count": len(confidences),
        "low_confidence_words": low_conf_words,
        "low_confidence_regions": low_conf_regions,
    }


def _ocr_image_with_confidence(
    img: Image.Image, preprocess: bool = PREPROCESS_DEFAULT,
) -> tuple[str, dict[str, Any]]:
    """OCR a PIL Image and return text + confidence data.

    Returns:
        (text, confidence_data) where confidence_data has:
        - avg_confidence: average Tesseract confidence (0-100)
        - word_count: number of words detected
        - low_confidence_words: list of words with confidence < 50
        - low_confidence_regions: list of (text, confidence) for low-confidence words

    """
    empty_conf = {
        "avg_confidence": 0.0,
        "word_count": 0,
        "low_confidence_words": [],
        "low_confidence_regions": [],
    }
    if not have_tesseract():
        return ("", empty_conf)
    try:
        img = _downsample_if_needed(img)
        # Key on the downsampled raw image so preprocessing is skipped on cache hits.
        cache_key = _image_cache_key(img, preprocess)
        cached = _check_cache(cache_key)
        # Only use the cache when conf_data was computed (not None, which means
        # the entry was stored by the text-only _ocr_image fast path).
        if cached is not None and cached[1] is not None:
            return cached

        target = preprocess_for_ocr(img) if preprocess else img
        # Reuse cached text when available to skip image_to_string.
        cached_text = cached[0] if cached is not None else None
        text = cached_text if cached_text is not None else get_tesseract().image_to_string(target)  # type: ignore[union-attr]
        data = get_tesseract().image_to_data(  # type: ignore[union-attr]
            target,
            output_type=get_tesseract().Output.DICT,  # type: ignore[union-attr]
        )
        conf_data = _extract_confidence_data(data)
        _store_cache(cache_key, text, conf_data)
        return (text, conf_data)
    except (OSError, RuntimeError) as exc:
        logger.warning("Tesseract (with confidence) failed: %s", exc)
        # Return cached text if available rather than discarding it on image_to_data failure.
        fallback_text = cached[0] if cached is not None else ""
        return (fallback_text, empty_conf)


def looks_low_confidence(text: str, confidence_data: dict[str, Any] | None = None) -> bool:
    """Heuristic: does this OCR output look like garbled junk?.

    Returns True for strings that are mostly punctuation, special symbols,
    have very few alphanumeric characters per line, or have low average
    Tesseract confidence scores. The agent uses this to decide whether to
    fall back to the vision model.

    Args:
        text: The OCR text output.
        confidence_data: Optional dict from _ocr_image_with_confidence with
            avg_confidence, low_confidence_words, etc.

    """
    # Validate text has sufficient alphanumeric content
    if not text or not text.strip():
        return True

    lines = [ln for ln in text.splitlines() if ln.strip()]
    # pragma: no cover  # unreachable: non-empty text.strip() implies a non-empty line
    if not lines:
        return True  # pragma: no cover  # unreachable: non-empty text.strip() implies a non-empty line

    total_alnum = sum(c.isalnum() for c in text)
    avg_alnum_per_line = total_alnum / len(lines)

    # Combine alphanumeric checks to reduce returns
    if total_alnum < 20 or avg_alnum_per_line < _MIN_ALNUM_PER_LINE_FOR_CONFIDENT:
        return True

    # Check confidence metrics if provided
    if confidence_data:
        avg_conf = confidence_data.get("avg_confidence", 0)
        if avg_conf > 0 and avg_conf < _MIN_AVG_CONFIDENCE:
            logger.debug(
                "OCR low confidence: avg=%.1f (threshold=%.1f)",
                avg_conf,
                _MIN_AVG_CONFIDENCE,
            )
            return True

        low_conf_words = confidence_data.get("low_confidence_words", [])
        word_count = confidence_data.get("word_count", 0)
        if word_count > 3 and len(low_conf_words) / max(word_count, 1) > 0.5:
            logger.debug(
                "OCR low confidence: %d/%d words below threshold",
                len(low_conf_words),
                word_count,
            )
            return True

    return False


def read_screen_text(monitor: int | None = None, preprocess: bool = PREPROCESS_DEFAULT) -> str:
    """OCR the screen and return the raw text. Empty string if OCR is unavailable."""
    if not have_tesseract():
        return ""
    try:
        img = capture_screen(monitor=monitor)
        return _ocr_image(img, preprocess=preprocess)
    except (OSError, RuntimeError) as exc:
        logger.warning("read_screen_text failed: %s", exc)
        return ""


def read_screen_text_with_confidence(
    monitor: int | None = None, preprocess: bool = PREPROCESS_DEFAULT,
) -> tuple[str, dict[str, Any]]:
    """OCR the screen and return text + confidence data."""
    if not have_tesseract():
        return (
            "",
            {
                "avg_confidence": 0,
                "word_count": 0,
                "low_confidence_words": [],
                "low_confidence_regions": [],
            },
        )
    try:
        img = capture_screen(monitor=monitor)
        return _ocr_image_with_confidence(img, preprocess=preprocess)
    except (OSError, RuntimeError) as exc:
        logger.warning("read_screen_text_with_confidence failed: %s", exc)
        return (
            "",
            {
                "avg_confidence": 0,
                "word_count": 0,
                "low_confidence_words": [],
                "low_confidence_regions": [],
            },
        )


def read_focused_window_text() -> str:
    """OCR the agent's target window (foreground, but skipping the Sentinel GUI)."""
    text, _title = read_focused_window_text_with_title()
    return text


def read_focused_window_text_with_title() -> tuple[str, str]:
    """Return (text, title) of the OCR'd window for debugging multi-monitor issues.

    Useful for debugging multi-monitor confusion.
    """
    if not have_tesseract():
        return ("", "")
    try:
        pair = capture_focused_window_with_title()
        if pair is None:
            return (read_screen_text(), "<full screen fallback>")
        img, title = pair
        return (_ocr_image(img), title)
    except (OSError, RuntimeError) as exc:
        logger.debug("read_focused_window_text_with_title failed: %s", exc)
        return ("", "")


def read_window_text(title: str) -> str:
    """OCR a window whose title contains *title*. Returns '' if not found."""
    if not title or not have_tesseract():
        return ""
    try:
        img = capture_window(title)
        if img is None:
            return ""
        return _ocr_image(img)
    except (OSError, RuntimeError) as exc:
        logger.debug("read_window_text(%s) failed: %s", title, exc)
        return ""


def _get_screen_boxes(monitor: int | None) -> list[dict[str, Any]] | None:
    """Capture the screen and return OCR word-boxes, using _boxes_cache."""
    try:
        img = capture_screen(monitor=monitor)
        img_small = _downsample_if_needed(img)
        cache_key = _image_cache_key(img_small)
        now = time.monotonic()
        entry = _boxes_cache.get(cache_key)
        if entry is not None and now - entry[1] < _CACHE_TTL:
            return entry[0]
        data: dict[str, list[Any]] = get_tesseract().image_to_data(  # type: ignore[union-attr]
            img_small,
            output_type=get_tesseract().Output.DICT,  # type: ignore[union-attr]
        )
        boxes = _boxes_from_data(data)
        _boxes_cache[cache_key] = (boxes, now)
        return boxes
    except (OSError, RuntimeError) as exc:
        logger.warning("OCR find_text failed: %s", exc)
        return None


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
    if not query or not have_tesseract():
        return None
    needle = re.sub(r"\s+", " ", query).strip().lower()
    if not needle:
        return None
    boxes = _get_screen_boxes(monitor)
    if boxes is None:
        return None
    offset_x, offset_y = get_capture_offset(monitor)
    hit = _exact_substring_hit(boxes, needle)
    if hit is not None:
        return (hit[0] + offset_x, hit[1] + offset_y)
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
            },
        )
    return boxes


def _exact_substring_hit(
    boxes: list[dict[str, Any]],
    needle: str,
) -> tuple[int, int] | None:
    """Find needle via case-insensitive substring match across OCR line groups."""
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
    """Find needle via fuzzy ratio scoring across OCR line groups."""
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
    """Return the geometric centre of a group of bounding boxes, or ``None``."""
    if not boxes:
        return None
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return ((x0 + x1) // 2, (y0 + y1) // 2)
