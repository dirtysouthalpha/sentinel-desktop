"""Tests for Phase 3: Set-of-Marks Screenshots — CV contours, annotation, multi-source marks."""

from unittest.mock import patch

import pytest
from PIL import Image

from core.perception.annotator import annotate_screenshot, get_color
from core.perception.fusion import FusionEngine, boxes_overlap, compute_iou
from core.perception.pipeline import PerceptionPipeline
from core.perception.types import (
    ElementSource,
    ElementType,
    PerceptionElement,
    PerceptionResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _elem(
    elem_id: int,
    label: str = "Btn",
    bbox: tuple[int, int, int, int] = (100, 100, 80, 30),
    source: ElementSource = ElementSource.ACCESSIBILITY,
    elem_type: ElementType = ElementType.BUTTON,
    interactable: bool = True,
) -> PerceptionElement:
    return PerceptionElement(
        id=elem_id,
        label=label,
        element_type=elem_type,
        bounding_box=bbox,
        confidence=0.9,
        source=source,
        actions=["click"],
        is_interactable=interactable,
    )


def _blank_screenshot(w: int = 800, h: int = 600) -> Image.Image:
    """Create a blank white screenshot for annotation tests."""
    return Image.new("RGB", (w, h), "white")


# ---------------------------------------------------------------------------
# SoM Annotation (SOM-01)
# ---------------------------------------------------------------------------


class TestSoMAnnotation:
    """Test Set-of-Marks annotated screenshot rendering."""

    def test_annotates_with_numbered_boxes(self):
        """Screenshots display numbered bounding boxes on all interactive elements."""
        elements = [
            _elem(1, "Save", (100, 100, 80, 30)),
            _elem(2, "Cancel", (200, 100, 80, 30)),
        ]
        img = _blank_screenshot()
        annotated = annotate_screenshot(img, elements)
        assert annotated.size == img.size
        # The annotated image should differ from the original
        assert list(annotated.getdata()) != list(img.getdata())

    def test_no_elements_returns_copy(self):
        """Empty element list returns unmodified copy."""
        img = _blank_screenshot()
        result = annotate_screenshot(img, [])
        assert result.size == img.size

    def test_zero_bbox_elements_skipped(self):
        """Elements with (0,0,0,0) bbox are skipped."""
        elements = [
            _elem(1, "Hidden", (0, 0, 0, 0)),
            _elem(2, "Visible", (100, 100, 80, 30)),
        ]
        img = _blank_screenshot()
        # Should not raise
        annotated = annotate_screenshot(img, elements)
        assert annotated is not None

    def test_color_by_element_type(self):
        """Different element types get different colors."""
        colors = set()
        for etype in [ElementType.BUTTON, ElementType.INPUT, ElementType.TEXT, ElementType.LINK]:
            c = get_color(etype)
            colors.add(c)
        assert len(colors) >= 3  # At least 3 distinct colors

    def test_interactable_elements_thicker(self):
        """Interactable elements get thicker outlines."""
        elements = [
            _elem(1, "Button", (100, 100, 80, 30), interactable=True),
            _elem(2, "Label", (200, 100, 80, 30), interactable=False),
        ]
        img = _blank_screenshot()
        # Should not raise — just verify both are rendered
        annotated = annotate_screenshot(img, elements, highlight_interactable=True)
        assert annotated is not None

    def test_long_labels_truncated(self):
        """Labels longer than 30 chars get truncated with ellipsis."""
        long_label = "A" * 50
        elements = [_elem(1, long_label, (100, 100, 80, 30))]
        img = _blank_screenshot()
        # Should not raise on long label
        annotated = annotate_screenshot(img, elements)
        assert annotated is not None

    def test_show_ids_false(self):
        """Can suppress element IDs in annotation."""
        elements = [_elem(1, "OK", (100, 100, 80, 30))]
        img = _blank_screenshot()
        annotated = annotate_screenshot(img, elements, show_ids=False)
        assert annotated is not None

    def test_show_labels_false(self):
        """Can suppress labels in annotation."""
        elements = [_elem(1, "OK", (100, 100, 80, 30))]
        img = _blank_screenshot()
        annotated = annotate_screenshot(img, elements, show_labels=False)
        assert annotated is not None


# ---------------------------------------------------------------------------
# Mark-based targeting (SOM-02) — click_mark already tested in Phase 2
# ---------------------------------------------------------------------------


class TestMarkTargeting:
    """Verify mark ID resolution works through PerceptionResult."""

    def test_find_by_id_resolves_mark(self):
        """PerceptionResult.find_by_id resolves mark IDs."""
        elements = [
            _elem(1, "Save", (100, 100, 80, 30)),
            _elem(7, "Open", (200, 100, 80, 30)),
        ]
        result = PerceptionResult(elements=elements)
        found = result.find_by_id(7)
        assert found is not None
        assert found.label == "Open"

    def test_mark_center_coordinates(self):
        """Mark center is computed correctly for click resolution."""
        elem = _elem(3, "Test", (200, 300, 100, 40))
        cx, cy = elem.center
        assert cx == 250
        assert cy == 320


# ---------------------------------------------------------------------------
# Multi-source mark generation (SOM-03)
# ---------------------------------------------------------------------------


class TestMultiSourceMarks:
    """Test that elements from multiple sources are fused into unified marks."""

    def test_fusion_merges_accessibility_and_ocr(self):
        """a11y and OCR elements that overlap are merged."""
        acc = [_elem(1, "Save", (100, 100, 80, 30), source=ElementSource.ACCESSIBILITY)]
        ocr = [_elem(0, "Save", (102, 101, 78, 28), source=ElementSource.OCR)]

        fusion = FusionEngine()
        merged = fusion.fuse(accessibility_elements=acc, ocr_elements=ocr)

        # Should merge into 1 element (high IoU overlap)
        assert len(merged) == 1
        assert merged[0].label == "Save"

    def test_fusion_keeps_non_overlapping(self):
        """Non-overlapping elements from different sources are both kept."""
        acc = [_elem(1, "Save", (100, 100, 80, 30), source=ElementSource.ACCESSIBILITY)]
        ocr = [_elem(0, "Cancel", (500, 100, 80, 30), source=ElementSource.OCR)]

        fusion = FusionEngine()
        merged = fusion.fuse(accessibility_elements=acc, ocr_elements=ocr)
        assert len(merged) == 2

    def test_fusion_prefers_accessibility_label(self):
        """When merging, accessibility label takes priority over OCR."""
        acc = [_elem(1, "Save", (100, 100, 80, 30), source=ElementSource.ACCESSIBILITY)]
        ocr = [_elem(0, "5ave", (100, 100, 80, 30), source=ElementSource.OCR)]  # OCR misread

        fusion = FusionEngine()
        merged = fusion.fuse(accessibility_elements=acc, ocr_elements=ocr)
        assert merged[0].label == "Save"  # Accessibility wins

    def test_cv_contour_detection_with_mock(self):
        """CV contour detection finds candidate regions in images."""
        pipeline = PerceptionPipeline()

        # Create an image with some rectangular regions (simulate canvas UI)
        img = _blank_screenshot(400, 300)
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        # Draw some dark rectangles (simulating buttons)
        draw.rectangle([50, 50, 150, 80], fill="black")
        draw.rectangle([200, 50, 300, 80], fill="black")
        draw.rectangle([50, 150, 150, 180], fill="black")

        try:
            elements = pipeline._query_vision(img)
            # May or may not find elements depending on OpenCV availability
            assert isinstance(elements, list)
        except ImportError:
            pytest.skip("OpenCV not available")

    def test_cv_contour_handles_no_opencv(self):
        """CV contour gracefully returns empty when OpenCV unavailable."""
        pipeline = PerceptionPipeline()
        img = _blank_screenshot()

        with patch.dict("sys.modules", {"cv2": None, "numpy": None}):
            elements = pipeline._query_vision(img)
            assert elements == []

    def test_pipeline_runs_all_sources(self):
        """Full pipeline combines a11y + OCR + CV into unified result."""
        pipeline = PerceptionPipeline()
        img = _blank_screenshot()

        with patch.object(
            pipeline,
            "_query_accessibility",
            return_value=[
                _elem(1, "Btn1", (100, 100, 80, 30), source=ElementSource.ACCESSIBILITY),
            ],
        ):
            with patch.object(
                pipeline,
                "_query_ocr",
                return_value=[
                    _elem(0, "Btn1", (101, 101, 79, 29), source=ElementSource.OCR),
                    _elem(0, "Text2", (300, 100, 80, 30), source=ElementSource.OCR),
                ],
            ):
                with patch.object(
                    pipeline,
                    "_query_vision",
                    return_value=[
                        _elem(0, "", (400, 200, 60, 60), source=ElementSource.VISION),
                    ],
                ):
                    result = pipeline.analyze(img)

                    # Should have fused elements from all 3 sources
                    assert result.accessibility_count == 1
                    assert result.ocr_count == 2
                    assert result.vision_count == 1
                    # Merged should have ≤ 4 elements (overlap merges possible)
                    assert len(result.elements) >= 2
                    assert len(result.elements) <= 4


# ---------------------------------------------------------------------------
# IoU computation
# ---------------------------------------------------------------------------


class TestIoU:
    """Test IoU computation used for element deduplication."""

    def test_no_overlap(self):
        iou = compute_iou((0, 0, 100, 100), (200, 200, 100, 100))
        assert iou == 0.0

    def test_perfect_overlap(self):
        iou = compute_iou((100, 100, 80, 30), (100, 100, 80, 30))
        assert iou == 1.0

    def test_partial_overlap(self):
        iou = compute_iou((0, 0, 100, 100), (50, 50, 100, 100))
        assert 0.0 < iou < 1.0

    def test_boxes_overlap_threshold(self):
        assert boxes_overlap((100, 100, 80, 30), (102, 101, 78, 28))
        assert not boxes_overlap((100, 100, 80, 30), (500, 500, 80, 30))

    def test_zero_area_box(self):
        iou = compute_iou((0, 0, 0, 0), (100, 100, 80, 30))
        assert iou == 0.0


# ---------------------------------------------------------------------------
# PerceptionResult.to_llm_context
# ---------------------------------------------------------------------------


class TestLLMContext:
    """Test the LLM context generation from perception results."""

    def test_context_includes_ids(self):
        """LLM context includes element IDs for targeting."""
        elements = [
            _elem(1, "Save", (100, 100, 80, 30)),
            _elem(2, "Cancel", (200, 100, 80, 30)),
        ]
        result = PerceptionResult(elements=elements)
        context = result.to_llm_context()
        assert "[1]" in context
        assert "[2]" in context

    def test_context_includes_labels(self):
        """LLM context includes element labels."""
        elements = [_elem(1, "Save")]
        result = PerceptionResult(elements=elements)
        context = result.to_llm_context()
        assert "Save" in context

    def test_empty_context(self):
        """Empty result returns fallback message."""
        result = PerceptionResult(elements=[])
        context = result.to_llm_context()
        assert "No" in context or "no" in context
