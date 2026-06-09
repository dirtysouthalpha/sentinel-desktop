"""Sentinel Desktop v5.0 — Screen Annotator.

Draws numbered bounding boxes on screenshots with color-coded labels
based on element type. This is what gets sent to the LLM — instead of
a raw screenshot, the LLM sees numbered boxes and picks IDs.

Color scheme:
    - Buttons/Controls:  Cyan (#00F0FF)
    - Text/Labels:       White (#FFFFFF)
    - Input fields:      Amber (#FBBC00)
    - Links/Menus:       Lime (#95E400)
    - Icons/Images:      Orange (#FF8C00)
    - Unknown:           Gray (#888888)
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from core.perception.types import ElementType, PerceptionElement

logger = logging.getLogger(__name__)

# Color map by element type
_COLORS: dict[ElementType, str] = {
    ElementType.BUTTON: "#00F0FF",
    ElementType.INPUT: "#FBBC00",
    ElementType.LINK: "#95E400",
    ElementType.TEXT: "#FFFFFF",
    ElementType.CHECKBOX: "#00F0FF",
    ElementType.RADIO: "#00F0FF",
    ElementType.DROPDOWN: "#00F0FF",
    ElementType.MENU: "#95E400",
    ElementType.MENU_ITEM: "#95E400",
    ElementType.TAB: "#95E400",
    ElementType.ICON: "#FF8C00",
    ElementType.IMAGE: "#FF8C00",
    ElementType.DIALOG: "#FF4444",
    ElementType.TOOLTIP: "#CC88FF",
    ElementType.SLIDER: "#00F0FF",
    ElementType.SCROLLBAR: "#888888",
    ElementType.UNKNOWN: "#888888",
}

# Box drawing parameters
_BOX_PADDING = 2
_BOX_WIDTH = 2
_FONT_SIZE = 14
_LABEL_PADDING = 4
_MAX_LABEL_WIDTH = 200


def get_color(element_type: ElementType) -> str:
    """Return the annotation color for an element type."""
    return _COLORS.get(element_type, "#888888")


def annotate_screenshot(
    image: Image.Image,
    elements: list[PerceptionElement],
    show_labels: bool = True,
    show_ids: bool = True,
    highlight_interactable: bool = True,
) -> Image.Image:
    """Draw numbered bounding boxes on a screenshot (Set-of-Marks annotation).

    Produces an annotated image where every detected element has a numbered
    bounding box. The LLM uses these numbers (mark IDs) to target elements
    instead of raw pixel coordinates.

    Args:
        image: The original screenshot.
        elements: Detected elements with bounding boxes.
        show_labels: Whether to show element labels.
        show_ids: Whether to show element IDs.
        highlight_interactable: Whether to use thicker outlines for interactable elements.

    Returns:
        A new PIL Image with annotations drawn on it.
    """
    if not elements:
        return image.copy()

    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)

    # Try to load a reasonable font
    font = _load_font(_FONT_SIZE)
    small_font = _load_font(_FONT_SIZE - 2)

    for elem in elements:
        if elem.bounding_box == (0, 0, 0, 0):
            continue

        x, y, w, h = elem.bounding_box
        color = get_color(elem.element_type)

        # Thicker outline for interactable elements
        thicker = highlight_interactable and elem.is_interactable
        box_width = _BOX_WIDTH + 1 if thicker else _BOX_WIDTH

        # Draw bounding box
        draw.rectangle(
            [x - _BOX_PADDING, y - _BOX_PADDING, x + w + _BOX_PADDING, y + h + _BOX_PADDING],
            outline=color,
            width=box_width,
        )

        # Draw label tag
        tag_parts = []
        if show_ids:
            tag_parts.append(f"[{elem.id}]")
        if show_labels and elem.label:
            # Truncate long labels
            label = elem.label[:30] + "…" if len(elem.label) > 30 else elem.label
            tag_parts.append(label)

        if tag_parts:
            tag_text = " ".join(tag_parts)
            _draw_label_tag(draw, tag_text, x, y, color, font, small_font)

    return annotated


def _draw_label_tag(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    color: str,
    font: Any,
    small_font: Any,
) -> None:
    """Draw a label tag above or below the bounding box.

    Args:
        draw: PIL ImageDraw instance.
        text: Label text to draw.
        x: X coordinate of the box.
        y: Y coordinate of the box top.
        color: Box color.
        font: Font for drawing.
        small_font: Smaller font for long text.
    """
    # Measure text
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except (AttributeError, TypeError):
        text_w = len(text) * 8
        text_h = _FONT_SIZE

    # Position: above the box if space allows, otherwise inside top
    label_x = max(0, x - _BOX_PADDING)
    label_y = max(0, y - text_h - _LABEL_PADDING * 2 - 2)

    # Draw background rectangle
    draw.rectangle(
        [
            label_x,
            label_y,
            label_x + text_w + _LABEL_PADDING * 2,
            label_y + text_h + _LABEL_PADDING * 2,
        ],
        fill="#000000CC",  # Semi-transparent black
        outline=color,
        width=1,
    )

    # Draw text
    draw.text(
        (label_x + _LABEL_PADDING, label_y + _LABEL_PADDING),
        text,
        fill=color,
        font=font,
    )


def _load_font(size: int) -> Any:
    """Try to load a TrueType font, falling back to default."""
    # Try common fonts in order of preference
    font_names = [
        "consola.ttf",  # Windows Consolas
        "arial.ttf",  # Windows Arial
        "DejaVuSans.ttf",  # Linux
        "Menlo.ttc",  # macOS
        "Helvetica.ttc",  # macOS
    ]

    import os

    # Common font directories
    font_dirs = []
    if os.name == "nt":
        font_dirs.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    elif os.name == "posix":
        font_dirs.extend(
            [
                "/usr/share/fonts/truetype/dejavu/",
                "/usr/share/fonts/TTF/",
                "/System/Library/Fonts/",
                "/Library/Fonts/",
            ]
        )

    for font_dir in font_dirs:
        for font_name in font_names:
            path = os.path.join(font_dir, font_name)
            if os.path.isfile(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue

    # Fallback to default PIL font
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
