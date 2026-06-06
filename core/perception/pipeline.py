"""Sentinel Desktop v5.0 — Perception Pipeline.

Orchestrates the full perception flow: capture screenshot, query accessibility
tree, run OCR, fuse results, and produce an annotated screenshot + element
list for the LLM.

This is the main entry point for v5.0 perception.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time

from PIL import Image

from core.perception.annotator import annotate_screenshot
from core.perception.fusion import FusionEngine
from core.perception.types import (
    ElementSource,
    ElementType,
    PerceptionElement,
    PerceptionResult,
)

logger = logging.getLogger(__name__)

# Cache for perception results — avoids reprocessing same screenshot
_result_cache: dict[str, tuple[PerceptionResult, float]] = {}
_result_cache_lock = threading.Lock()
_RESULT_CACHE_TTL = 2.0  # seconds — short because screen changes frequently
_RESULT_CACHE_MAX = 10


class PerceptionPipeline:
    """Full perception pipeline: accessibility → OCR → vision → fusion → annotation.

    Usage::

        pipeline = PerceptionPipeline()
        result = pipeline.analyze(screenshot_image)
        # Send result.annotated_image + result.to_llm_context() to LLM
    """

    def __init__(self) -> None:
        self.fusion = FusionEngine()

    def analyze(
        self,
        screenshot: Image.Image,
        window_title: str | None = None,
        include_accessibility: bool = True,
        include_ocr: bool = True,
        include_vision: bool = False,
    ) -> PerceptionResult:
        """Run the full perception pipeline on a screenshot.

        Args:
            screenshot: PIL Image of the screen.
            window_title: Optional window title to filter accessibility tree.
            include_accessibility: Query OS accessibility tree.
            include_ocr: Run OCR text detection.
            include_vision: Run vision model analysis (expensive).

        Returns:
            PerceptionResult with annotated image and element list.
        """
        start = time.monotonic()

        # Check cache
        cache_key = self._cache_key(screenshot)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Phase 1: Accessibility tree
        acc_elements: list[PerceptionElement] = []
        if include_accessibility:
            acc_elements = self._query_accessibility(window_title)

        # Phase 2: OCR text detection
        ocr_elements: list[PerceptionElement] = []
        if include_ocr:
            ocr_elements = self._query_ocr(screenshot)

        # Phase 3: Vision model (future — placeholder)
        vision_elements: list[PerceptionElement] = []
        if include_vision:
            vision_elements = self._query_vision(screenshot)

        # Phase 4: Fusion — merge and deduplicate
        elements = self.fusion.fuse(
            accessibility_elements=acc_elements,
            ocr_elements=ocr_elements,
            vision_elements=vision_elements,
        )

        # Phase 5: Annotation — draw bounding boxes
        annotated = annotate_screenshot(screenshot, elements)

        # Build result
        elapsed_ms = (time.monotonic() - start) * 1000

        result = PerceptionResult(
            annotated_image=annotated,
            elements=elements,
            text_description=self._build_text_description(elements),
            accessibility_count=len(acc_elements),
            ocr_count=len(ocr_elements),
            vision_count=len(vision_elements),
            processing_time_ms=elapsed_ms,
            screenshot_hash=cache_key,
        )

        # Cache result
        self._store_cached(cache_key, result)

        logger.debug(
            "Perception: %d elements (%d acc, %d ocr, %d vis) in %.1fms",
            len(elements),
            len(acc_elements),
            len(ocr_elements),
            len(vision_elements),
            elapsed_ms,
        )

        return result

    def _query_accessibility(self, window_title: str | None = None) -> list[PerceptionElement]:
        """Query the OS accessibility tree via the platform backend.

        Returns a list of PerceptionElements from the accessibility tree.
        """
        try:
            from core.platform import get_backend

            backend = get_backend()
            if not backend.accessibility.is_available():
                return []

            tree = backend.accessibility.get_tree(window_title)
            elements = []
            for node in tree:
                # Determine element type
                elem_type = self._classify_element_type(node.control_type)

                # Determine if interactable
                is_interactable = bool(node.actions)

                elements.append(
                    PerceptionElement(
                        label=node.name,
                        element_type=elem_type,
                        bounding_box=node.bounding_box or (0, 0, 0, 0),
                        confidence=0.95,  # Accessibility data is very reliable
                        source=ElementSource.ACCESSIBILITY,
                        actions=node.actions,
                        is_interactable=is_interactable,
                        raw=node.raw,
                    )
                )
            return elements
        except Exception as exc:
            logger.debug("Accessibility query failed: %s", exc)
            return []

    def _query_ocr(self, screenshot: Image.Image) -> list[PerceptionElement]:
        """Run OCR text detection on the screenshot.

        Returns a list of PerceptionElements from detected text.
        """
        try:
            from core.ocr import find_text_boxes

            boxes = find_text_boxes(screenshot)
            if not boxes:
                return []

            elements = []
            for box in boxes:
                text = box.get("text", "").strip()
                bbox = box.get("bbox")
                confidence = box.get("confidence", 0.5)

                if not text or not bbox:
                    continue

                # OCR boxes are typically (x, y, w, h)
                x, y, w, h = bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]
                if w <= 0 or h <= 0:
                    continue

                # Classify based on text content
                elem_type = self._classify_text_element(text)

                elements.append(
                    PerceptionElement(
                        label=text,
                        element_type=elem_type,
                        bounding_box=(x, y, w, h),
                        confidence=min(confidence / 100.0, 1.0) if confidence > 1 else confidence,
                        source=ElementSource.OCR,
                        actions=["click"]
                        if elem_type
                        in (ElementType.BUTTON, ElementType.LINK, ElementType.MENU_ITEM)
                        else [],
                        is_interactable=elem_type
                        in (
                            ElementType.BUTTON,
                            ElementType.LINK,
                            ElementType.INPUT,
                            ElementType.MENU_ITEM,
                            ElementType.DROPDOWN,
                        ),
                    )
                )
            return elements
        except Exception as exc:
            logger.debug("OCR query failed: %s", exc)
            return []

    def _query_vision(self, screenshot: Image.Image) -> list[PerceptionElement]:
        """Analyze screenshot with a vision model (placeholder for v5.1).

        In the future, this will use a local YOLO/Florence-2 model for
        element detection and icon captioning. For now, returns empty.
        """
        # Placeholder — will be implemented with local model inference
        return []

    @staticmethod
    def _classify_element_type(control_type: str) -> ElementType:
        """Map a platform control type string to ElementType."""
        ct = (control_type or "").lower()
        mapping = {
            "button": ElementType.BUTTON,
            "edit": ElementType.INPUT,
            "text": ElementType.TEXT,
            "input": ElementType.INPUT,
            "link": ElementType.LINK,
            "checkbox": ElementType.CHECKBOX,
            "radio": ElementType.RADIO,
            "combobox": ElementType.DROPDOWN,
            "dropdown": ElementType.DROPDOWN,
            "select": ElementType.DROPDOWN,
            "menu": ElementType.MENU,
            "menuitem": ElementType.MENU_ITEM,
            "tab": ElementType.TAB,
            "image": ElementType.IMAGE,
            "icon": ElementType.ICON,
            "dialog": ElementType.DIALOG,
            "tooltip": ElementType.TOOLTIP,
            "slider": ElementType.SLIDER,
            "scrollbar": ElementType.SCROLLBAR,
        }
        return mapping.get(ct, ElementType.UNKNOWN)

    @staticmethod
    def _classify_text_element(text: str) -> ElementType:
        """Heuristic classification of OCR text into element types."""
        text_lower = text.lower().strip()

        # Common button labels
        button_words = {
            "ok",
            "cancel",
            "save",
            "apply",
            "close",
            "yes",
            "no",
            "submit",
            "send",
            "delete",
            "remove",
            "add",
            "create",
            "edit",
            "update",
            "install",
            "download",
            "upload",
            "open",
            "next",
            "back",
            "done",
            "accept",
            "decline",
            "retry",
            "browse",
            "choose",
            "select",
            "search",
            "find",
            "go",
            "login",
            "sign in",
            "sign up",
            "register",
            "reset",
            "enable",
            "disable",
            "connect",
            "disconnect",
        }
        if text_lower in button_words or (len(text_lower) < 20 and text_lower.isupper()):
            return ElementType.BUTTON

        # URL-like text
        if text_lower.startswith(("http://", "https://", "www.")):
            return ElementType.LINK

        # Menu indicators
        if text_lower in {
            "file",
            "edit",
            "view",
            "tools",
            "help",
            "window",
            "settings",
            "preferences",
            "options",
        }:
            return ElementType.MENU_ITEM

        # Input placeholder text
        if any(
            p in text_lower
            for p in ("enter ", "type ", "search ", "password", "email", "username", "placeholder")
        ):
            return ElementType.INPUT

        return ElementType.TEXT

    @staticmethod
    def _build_text_description(elements: list[PerceptionElement]) -> str:
        """Build a compact text description of all elements for LLM context."""
        if not elements:
            return "No interactive elements detected."

        lines = ["Detected screen elements:"]
        for elem in elements:
            actions_str = ", ".join(elem.actions) if elem.actions else ""
            interact = " [interactable]" if elem.is_interactable else ""
            x, y = elem.center
            label_display = elem.label if elem.label else "(unlabeled)"
            line = f"  [{elem.id}] {elem.element_type.value} '{label_display}' at ({x},{y})"
            if actions_str:
                line += f" actions: {actions_str}"
            line += interact
            lines.append(line)

        return "\n".join(lines)

    # ── Cache helpers ────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(image: Image.Image) -> str:
        """Generate a cache key from image content."""
        w, h = image.size
        # Sample 9 pixels for a fast fingerprint
        xs = [w // 4, w // 2, 3 * w // 4]
        ys = [h // 4, h // 2, 3 * h // 4]
        try:
            samples = [str(image.getpixel((x, y))) for x in xs for y in ys]
            fingerprint = f"{w}x{h}:{','.join(samples)}"
        except (IndexError, OSError):
            fingerprint = f"{w}x{h}"
        return hashlib.md5(fingerprint.encode(), usedforsecurity=False).hexdigest()

    @staticmethod
    def _get_cached(key: str) -> PerceptionResult | None:
        """Return cached result if still valid."""
        with _result_cache_lock:
            if key in _result_cache:
                result, ts = _result_cache[key]
                if time.monotonic() - ts < _RESULT_CACHE_TTL:
                    return result
                del _result_cache[key]
        return None

    @staticmethod
    def _store_cached(key: str, result: PerceptionResult) -> None:
        """Store result in cache with eviction."""
        with _result_cache_lock:
            # Evict expired
            now = time.monotonic()
            expired = [k for k, (_, ts) in _result_cache.items() if now - ts >= _RESULT_CACHE_TTL]
            for k in expired:
                del _result_cache[k]

            # Evict oldest if at capacity
            if len(_result_cache) >= _RESULT_CACHE_MAX:
                oldest = min(_result_cache.keys(), key=lambda k: _result_cache[k][1])
                del _result_cache[oldest]

            _result_cache[key] = (result, now)
