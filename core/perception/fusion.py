"""Sentinel Desktop v5.0 — Fusion Engine.

Merges elements from multiple perception sources (accessibility tree, OCR,
vision model) into a single deduplicated element map. Handles overlapping
bounding boxes from different sources, preferring higher-confidence and
more structured sources.

Deduplication strategy:
    1. Start with accessibility elements (highest confidence, structured data).
    2. Add OCR elements that don't overlap with existing ones.
    3. Add vision elements that don't overlap with existing ones.
    4. Merge overlapping elements, keeping the best label and bounding box.
"""

from __future__ import annotations

import logging

from core.perception.types import ElementSource, ElementType, PerceptionElement

logger = logging.getLogger(__name__)

# Overlap threshold: if IoU > this, consider two boxes the same element
_OVERLAP_THRESHOLD = 0.3

# Minimum element area in pixels (filter out tiny noise)
_MIN_ELEMENT_AREA = 50


def compute_iou(
    box_a: tuple[int, int, int, int],
    box_b: tuple[int, int, int, int],
) -> float:
    """Compute Intersection over Union (IoU) of two bounding boxes.

    Args:
        box_a: (x, y, w, h) of first box.
        box_b: (x, y, w, h) of second box.

    Returns:
        IoU value 0.0–1.0.
    """
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    # Convert to (x1, y1, x2, y2)
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    # Intersection
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    intersection = (ix2 - ix1) * (iy2 - iy1)
    union = aw * ah + bw * bh - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def boxes_overlap(
    box_a: tuple[int, int, int, int],
    box_b: tuple[int, int, int, int],
    threshold: float = _OVERLAP_THRESHOLD,
) -> bool:
    """Check if two boxes overlap above the threshold."""
    return compute_iou(box_a, box_b) > threshold


def merge_elements(
    existing: PerceptionElement,
    new_elem: PerceptionElement,
) -> PerceptionElement:
    """Merge two overlapping elements, keeping the best data from each.

    Preference order: accessibility > OCR > vision (by confidence).
    """
    # Source priority
    source_priority = {
        ElementSource.ACCESSIBILITY: 3,
        ElementSource.OCR: 2,
        ElementSource.VISION: 1,
        ElementSource.TEMPLATE: 0,
    }

    existing_priority = source_priority.get(existing.source, 0)
    new_priority = source_priority.get(new_elem.source, 0)

    # Use the label from the higher-priority source
    label = existing.label if existing_priority >= new_priority else new_elem.label
    if not label:
        label = existing.label or new_elem.label

    # Use the element type from the higher-priority source
    elem_type = (
        existing.element_type if existing_priority >= new_priority else new_elem.element_type
    )
    if elem_type == ElementType.UNKNOWN:
        elem_type = (
            new_elem.element_type
            if new_elem.element_type != ElementType.UNKNOWN
            else existing.element_type
        )

    # Use the tighter bounding box (smaller area)
    box = existing.bounding_box if existing.area <= new_elem.area else new_elem.bounding_box

    # Merge actions
    actions = list(set(existing.actions + new_elem.actions))

    # Higher confidence wins
    confidence = max(existing.confidence, new_elem.confidence)

    # Interactable if either says so
    is_interactable = existing.is_interactable or new_elem.is_interactable

    # Keep higher-priority source
    source = existing.source if existing_priority >= new_priority else new_elem.source

    return PerceptionElement(
        id=existing.id,  # Keep the existing ID
        label=label,
        element_type=elem_type,
        bounding_box=box,
        confidence=confidence,
        source=source,
        actions=actions,
        is_interactable=is_interactable,
        raw=existing.raw or new_elem.raw,
    )


class FusionEngine:
    """Merges elements from multiple perception sources into a unified map.

    Usage::

        fusion = FusionEngine()
        elements = fusion.fuse(
            accessibility_elements=[...],
            ocr_elements=[...],
            vision_elements=[...],
        )
    """

    def fuse(
        self,
        accessibility_elements: list[PerceptionElement] | None = None,
        ocr_elements: list[PerceptionElement] | None = None,
        vision_elements: list[PerceptionElement] | None = None,
    ) -> list[PerceptionElement]:
        """Merge all element sources into a deduplicated list.

        Args:
            accessibility_elements: Elements from the OS accessibility tree.
            ocr_elements: Elements from OCR text detection.
            vision_elements: Elements from vision model analysis.

        Returns:
            Deduplicated, sorted list of PerceptionElements.
        """
        acc_elems = accessibility_elements or []
        ocr_elems = ocr_elements or []
        vis_elems = vision_elements or []

        merged: list[PerceptionElement] = []
        next_id = 1

        # Phase 1: Add accessibility elements (highest priority)
        for elem in acc_elems:
            if elem.area < _MIN_ELEMENT_AREA:
                continue
            elem.id = next_id
            next_id += 1
            merged.append(elem)

        # Phase 2: Add OCR elements, merging overlaps
        for elem in ocr_elems:
            if elem.area < _MIN_ELEMENT_AREA:
                continue
            overlap_idx = self._find_overlap(elem, merged)
            if overlap_idx is not None:
                merged[overlap_idx] = merge_elements(merged[overlap_idx], elem)
            else:
                elem.id = next_id
                next_id += 1
                merged.append(elem)

        # Phase 3: Add vision elements, merging overlaps
        for elem in vis_elems:
            if elem.area < _MIN_ELEMENT_AREA:
                continue
            overlap_idx = self._find_overlap(elem, merged)
            if overlap_idx is not None:
                merged[overlap_idx] = merge_elements(merged[overlap_idx], elem)
            else:
                elem.id = next_id
                next_id += 1
                merged.append(elem)

        # Sort by position: top-to-bottom, left-to-right
        merged.sort(key=lambda e: (e.bounding_box[1], e.bounding_box[0]))

        return merged

    @staticmethod
    def _find_overlap(
        elem: PerceptionElement,
        existing: list[PerceptionElement],
    ) -> int | None:
        """Find the index of an existing element that overlaps with *elem*.

        Returns the index or ``None`` if no overlap found.
        """
        for i, ex in enumerate(existing):
            if boxes_overlap(elem.bounding_box, ex.bounding_box):
                return i
        return None
