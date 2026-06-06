"""Sentinel Desktop v5.0 — Perception data types.

Shared data structures used across the perception pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from PIL import Image


class ElementSource(str, Enum):
    """Where a perception element was detected."""

    ACCESSIBILITY = "accessibility"  # From OS accessibility tree (UIA/AT-SPI/AX)
    OCR = "ocr"  # From Tesseract/PaddleOCR text detection
    VISION = "vision"  # From vision model analysis
    TEMPLATE = "template"  # From template matching


class ElementType(str, Enum):
    """What kind of UI element this is."""

    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    TEXT = "text"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    MENU = "menu"
    MENU_ITEM = "menu_item"
    TAB = "tab"
    ICON = "icon"
    IMAGE = "image"
    DIALOG = "dialog"
    TOOLTIP = "tooltip"
    SLIDER = "slider"
    SCROLLBAR = "scrollbar"
    UNKNOWN = "unknown"


@dataclass
class PerceptionElement:
    """A single detected UI element in the perception pipeline.

    Attributes:
        id: Unique integer ID for this element (used in annotations).
        label: Human-readable text label (button text, icon description, etc.).
        element_type: What kind of UI element this is.
        bounding_box: ``(x, y, width, height)`` in screenshot coordinates.
        confidence: Detection confidence 0.0–1.0.
        source: How this element was detected.
        actions: Available actions (click, type, select, etc.).
        is_interactable: Whether the user/agent can interact with this.
        raw: Platform-specific original data (e.g. UIA element ref).
    """

    id: int = 0
    label: str = ""
    element_type: ElementType = ElementType.UNKNOWN
    bounding_box: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    source: ElementSource = ElementSource.VISION
    actions: list[str] = field(default_factory=list)
    is_interactable: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> tuple[int, int]:
        """Return the center ``(x, y)`` of this element's bounding box."""
        x, y, w, h = self.bounding_box
        return (x + w // 2, y + h // 2)

    @property
    def area(self) -> int:
        """Return the pixel area of this element."""
        return self.bounding_box[2] * self.bounding_box[3]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for LLM context."""
        d: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "type": self.element_type.value,
            "confidence": round(self.confidence, 2),
            "source": self.source.value,
            "interactable": self.is_interactable,
        }
        if self.bounding_box != (0, 0, 0, 0):
            d["center"] = list(self.center)
            d["bounds"] = {
                "x": self.bounding_box[0],
                "y": self.bounding_box[1],
                "width": self.bounding_box[2],
                "height": self.bounding_box[3],
            }
        if self.actions:
            d["actions"] = self.actions
        return d


@dataclass
class PerceptionResult:
    """Complete result from the perception pipeline.

    Attributes:
        annotated_image: Screenshot with numbered bounding boxes drawn on it.
        elements: All detected elements, sorted by position (top-left to bottom-right).
        text_description: Formatted text listing all elements for LLM context.
        accessibility_count: Elements sourced from accessibility tree.
        ocr_count: Elements sourced from OCR.
        vision_count: Elements sourced from vision analysis.
        processing_time_ms: Total pipeline processing time.
        screenshot_hash: Hash of the original screenshot (for cache invalidation).
    """

    annotated_image: Image.Image | None = None
    elements: list[PerceptionElement] = field(default_factory=list)
    text_description: str = ""
    accessibility_count: int = 0
    ocr_count: int = 0
    vision_count: int = 0
    processing_time_ms: float = 0.0
    screenshot_hash: str = ""

    def to_llm_context(self) -> str:
        """Generate a formatted text block for the LLM system prompt.

        Returns a numbered element list like:
            [1] Button 'Save' at (450,320) [interactable]
            [2] Edit 'Filename' at (200,280) [interactable, type]
            [3] Text 'Documents' at (100,50)
        """
        if not self.elements:
            return "No interactive elements detected on screen."
        lines = []
        for elem in self.elements:
            actions_str = ", ".join(elem.actions) if elem.actions else ""
            interact_str = "interactable" if elem.is_interactable else ""
            tags = " | ".join(
                filter(None, [interactable_str for interactable_str in [actions_str, interact_str]])
            )
            tag_str = f" [{tags}]" if tags else ""
            x, y = elem.center
            lines.append(
                f"[{elem.id}] {elem.element_type.value.title()} '{elem.label}' at ({x},{y}){tag_str}"
            )
        return "\n".join(lines)

    def find_by_label(self, label: str) -> PerceptionElement | None:
        """Find an element by partial label match."""
        needle = label.lower()
        for elem in self.elements:
            if needle in elem.label.lower():
                return elem
        return None

    def find_by_id(self, elem_id: int) -> PerceptionElement | None:
        """Find an element by its numeric ID."""
        for elem in self.elements:
            if elem.id == elem_id:
                return elem
        return None

    def interactable_elements(self) -> list[PerceptionElement]:
        """Return only interactable elements."""
        return [e for e in self.elements if e.is_interactable]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full result."""
        return {
            "element_count": len(self.elements),
            "interactable_count": len(self.interactable_elements()),
            "accessibility_count": self.accessibility_count,
            "ocr_count": self.ocr_count,
            "vision_count": self.vision_count,
            "processing_time_ms": round(self.processing_time_ms, 1),
            "elements": [e.to_dict() for e in self.elements],
        }
