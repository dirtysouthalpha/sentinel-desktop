"""Gap tests for core/perception/fusion.py — lines 63, 99, 187, 199, 202."""

from __future__ import annotations

from core.perception.fusion import FusionEngine, compute_iou, merge_elements
from core.perception.types import ElementSource, ElementType, PerceptionElement


def _elem(
    x: int,
    y: int,
    w: int,
    h: int,
    label: str = "btn",
    source: ElementSource = ElementSource.ACCESSIBILITY,
    elem_type: ElementType = ElementType.BUTTON,
    confidence: float = 0.9,
    is_interactable: bool = True,
) -> PerceptionElement:
    return PerceptionElement(
        id=0,
        label=label,
        element_type=elem_type,
        bounding_box=(x, y, w, h),
        source=source,
        confidence=confidence,
        is_interactable=is_interactable,
    )


class TestComputeIouZeroUnion:
    """Line 63: union <= 0 → return 0.0 (zero-area boxes)."""

    def test_zero_area_box_returns_zero(self) -> None:
        # Both boxes have zero width/height → union == 0
        result = compute_iou((10, 10, 0, 0), (10, 10, 0, 0))
        assert result == 0.0

    def test_one_zero_area_box_returns_zero(self) -> None:
        result = compute_iou((10, 10, 0, 5), (10, 10, 50, 50))
        assert result == 0.0


class TestMergeElementsEmptyLabel:
    """Line 99: label is falsy after priority comparison → fall back to or-chain."""

    def test_empty_label_falls_back_to_or_chain(self) -> None:
        # existing has higher priority (ACCESSIBILITY) but empty label
        existing = _elem(0, 0, 100, 100, label="", source=ElementSource.ACCESSIBILITY)
        new_elem = _elem(0, 0, 100, 100, label="Submit", source=ElementSource.OCR)

        result = merge_elements(existing, new_elem)
        # existing_priority (3) >= new_priority (2) → label = existing.label ("") → falsy
        # → falls back to existing.label or new_elem.label → "Submit"
        assert result.label == "Submit"

    def test_both_empty_labels_produce_empty(self) -> None:
        existing = _elem(0, 0, 100, 100, label="", source=ElementSource.ACCESSIBILITY)
        new_elem = _elem(0, 0, 100, 100, label="", source=ElementSource.OCR)

        result = merge_elements(existing, new_elem)
        assert result.label == ""


class TestFuseSmallOcrElementSkipped:
    """Line 187: OCR element with area < 50 is skipped (continue)."""

    def test_tiny_ocr_element_not_in_result(self) -> None:
        fusion = FusionEngine()
        tiny = _elem(10, 10, 5, 5, label="x", source=ElementSource.OCR)  # area = 25 < 50
        big = _elem(0, 0, 100, 100, label="panel", source=ElementSource.OCR)

        result = fusion.fuse(ocr_elements=[tiny, big])
        labels = [e.label for e in result]
        assert "x" not in labels
        assert "panel" in labels


class TestFuseSmallVisionElementSkipped:
    """Line 199: vision element with area < 50 is skipped (continue)."""

    def test_tiny_vision_element_not_in_result(self) -> None:
        fusion = FusionEngine()
        tiny = _elem(10, 10, 4, 4, label="noise", source=ElementSource.VISION)  # area = 16 < 50
        big = _elem(0, 0, 80, 80, label="icon", source=ElementSource.VISION)

        result = fusion.fuse(vision_elements=[tiny, big])
        labels = [e.label for e in result]
        assert "noise" not in labels
        assert "icon" in labels


class TestFuseVisionOverlapMerge:
    """Line 202: vision element overlaps an existing element → merged in-place."""

    def test_vision_element_merged_with_existing(self) -> None:
        fusion = FusionEngine()
        # An accessibility element already in merged list
        acc = _elem(0, 0, 100, 100, label="btn_acc", source=ElementSource.ACCESSIBILITY)
        # A vision element that heavily overlaps the same area
        vis = _elem(5, 5, 90, 90, label="btn_vis", source=ElementSource.VISION)

        result = fusion.fuse(accessibility_elements=[acc], vision_elements=[vis])

        # Should be 1 merged element, not 2
        assert len(result) == 1
        # Accessibility wins on label (higher priority)
        assert result[0].label == "btn_acc"
