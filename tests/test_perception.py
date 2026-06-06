"""Tests for Sentinel Desktop v5.0 Perception Pipeline.

Covers: types, fusion engine, annotator, pipeline, element classification.
"""

from __future__ import annotations

from unittest.mock import patch

from PIL import Image

from core.perception.annotator import annotate_screenshot, get_color
from core.perception.fusion import FusionEngine, compute_iou
from core.perception.types import (
    ElementSource,
    ElementType,
    PerceptionElement,
    PerceptionResult,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class TestPerceptionElement:
    """Test PerceptionElement data class."""

    def test_default_values(self):
        elem = PerceptionElement()
        assert elem.id == 0
        assert elem.label == ""
        assert elem.element_type == ElementType.UNKNOWN
        assert elem.confidence == 0.0
        assert elem.source == ElementSource.VISION

    def test_center_calculation(self):
        elem = PerceptionElement(bounding_box=(100, 200, 80, 60))
        assert elem.center == (140, 230)

    def test_area(self):
        elem = PerceptionElement(bounding_box=(0, 0, 100, 50))
        assert elem.area == 5000

    def test_to_dict(self):
        elem = PerceptionElement(
            id=1, label="Save", element_type=ElementType.BUTTON,
            bounding_box=(100, 200, 80, 30), confidence=0.95,
            source=ElementSource.ACCESSIBILITY, actions=["click"],
            is_interactable=True,
        )
        d = elem.to_dict()
        assert d["id"] == 1
        assert d["label"] == "Save"
        assert d["type"] == "button"
        assert d["interactable"] is True
        assert "center" in d
        assert d["center"] == [140, 215]


class TestPerceptionResult:
    """Test PerceptionResult data class."""

    def test_empty_result(self):
        result = PerceptionResult()
        assert result.elements == []
        assert "No interactive elements" in result.to_llm_context()

    def test_find_by_label(self):
        elem = PerceptionElement(id=1, label="Save Button")
        result = PerceptionResult(elements=[elem])
        assert result.find_by_label("save") is elem
        assert result.find_by_label("cancel") is None

    def test_find_by_id(self):
        elem = PerceptionElement(id=5, label="Test")
        result = PerceptionResult(elements=[elem])
        assert result.find_by_id(5) is elem
        assert result.find_by_id(99) is None

    def test_interactable_elements(self):
        elems = [
            PerceptionElement(id=1, is_interactable=True),
            PerceptionElement(id=2, is_interactable=False),
            PerceptionElement(id=3, is_interactable=True),
        ]
        result = PerceptionResult(elements=elems)
        assert len(result.interactable_elements()) == 2

    def test_to_llm_context(self):
        elems = [
            PerceptionElement(
                id=1, label="Save", element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30), is_interactable=True,
                actions=["click"],
            ),
        ]
        result = PerceptionResult(elements=elems)
        ctx = result.to_llm_context()
        assert "[1]" in ctx
        assert "Save" in ctx
        assert "button" in ctx.lower()


# ---------------------------------------------------------------------------
# Fusion Engine
# ---------------------------------------------------------------------------


class TestComputeIoU:
    """Test IoU computation."""

    def test_no_overlap(self):
        iou = compute_iou((0, 0, 10, 10), (20, 20, 10, 10))
        assert iou == 0.0

    def test_full_overlap(self):
        iou = compute_iou((0, 0, 10, 10), (0, 0, 10, 10))
        assert iou == 1.0

    def test_partial_overlap(self):
        iou = compute_iou((0, 0, 10, 10), (5, 5, 10, 10))
        assert 0 < iou < 1

    def test_zero_area(self):
        iou = compute_iou((0, 0, 0, 0), (0, 0, 10, 10))
        assert iou == 0.0


class TestFusionEngine:
    """Test the fusion engine's merging behavior."""

    def test_empty_inputs(self):
        fusion = FusionEngine()
        result = fusion.fuse()
        assert result == []

    def test_accessibility_only(self):
        fusion = FusionEngine()
        elems = [
            PerceptionElement(
                label="Save", element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30), confidence=0.95,
                source=ElementSource.ACCESSIBILITY, is_interactable=True,
            ),
        ]
        result = fusion.fuse(accessibility_elements=elems)
        assert len(result) == 1
        assert result[0].id == 1

    def test_deduplication_merges_overlapping(self):
        fusion = FusionEngine()
        acc = [
            PerceptionElement(
                label="Save", bounding_box=(100, 200, 80, 30),
                confidence=0.95, source=ElementSource.ACCESSIBILITY,
                is_interactable=True,
            ),
        ]
        ocr = [
            PerceptionElement(
                label="Save", bounding_box=(102, 201, 78, 28),
                confidence=0.8, source=ElementSource.OCR,
            ),
        ]
        result = fusion.fuse(accessibility_elements=acc, ocr_elements=ocr)
        # Should merge into 1 element (high IoU)
        assert len(result) == 1
        # Should prefer accessibility source
        assert result[0].source == ElementSource.ACCESSIBILITY

    def test_non_overlapping_preserved(self):
        fusion = FusionEngine()
        acc = [
            PerceptionElement(
                label="Save", bounding_box=(100, 200, 80, 30),
                confidence=0.95, source=ElementSource.ACCESSIBILITY,
            ),
        ]
        ocr = [
            PerceptionElement(
                label="Cancel", bounding_box=(400, 200, 80, 30),
                confidence=0.8, source=ElementSource.OCR,
            ),
        ]
        result = fusion.fuse(accessibility_elements=acc, ocr_elements=ocr)
        assert len(result) == 2

    def test_tiny_elements_filtered(self):
        fusion = FusionEngine()
        elems = [
            PerceptionElement(label="tiny", bounding_box=(0, 0, 2, 2)),
        ]
        result = fusion.fuse(accessibility_elements=elems)
        assert len(result) == 0

    def test_sorted_by_position(self):
        fusion = FusionEngine()
        elems = [
            PerceptionElement(label="Bottom", bounding_box=(100, 500, 80, 30)),
            PerceptionElement(label="Top", bounding_box=(100, 100, 80, 30)),
            PerceptionElement(label="Mid", bounding_box=(100, 300, 80, 30)),
        ]
        result = fusion.fuse(accessibility_elements=elems)
        assert result[0].label == "Top"
        assert result[1].label == "Mid"
        assert result[2].label == "Bottom"

    def test_id_assignment(self):
        fusion = FusionEngine()
        elems = [
            PerceptionElement(label=f"E{i}", bounding_box=(i * 100, 0, 50, 50))
            for i in range(5)
        ]
        result = fusion.fuse(accessibility_elements=elems)
        ids = [e.id for e in result]
        assert ids == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Annotator
# ---------------------------------------------------------------------------


class TestAnnotator:
    """Test screen annotation."""

    def test_empty_elements_returns_copy(self):
        img = Image.new("RGB", (800, 600))
        result = annotate_screenshot(img, [])
        assert result.size == img.size
        assert result is not img

    def test_with_elements(self):
        img = Image.new("RGB", (800, 600))
        elems = [
            PerceptionElement(
                id=1, label="Save", element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30), is_interactable=True,
            ),
        ]
        result = annotate_screenshot(img, elems)
        assert result.size == img.size
        # Should not raise

    def test_get_color(self):
        assert get_color(ElementType.BUTTON) == "#00F0FF"
        assert get_color(ElementType.INPUT) == "#FBBC00"
        assert get_color(ElementType.LINK) == "#95E400"
        assert get_color(ElementType.UNKNOWN) == "#888888"

    def test_zero_box_skipped(self):
        img = Image.new("RGB", (800, 600))
        elems = [
            PerceptionElement(id=1, label="Ghost", bounding_box=(0, 0, 0, 0)),
        ]
        # Should not raise
        annotate_screenshot(img, elems)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestPipelineElementClassification:
    """Test the pipeline's element type classification heuristics."""

    def test_classify_button_words(self):
        from core.perception.pipeline import PerceptionPipeline
        cls = PerceptionPipeline._classify_text_element
        assert cls("Save") == ElementType.BUTTON
        assert cls("OK") == ElementType.BUTTON
        assert cls("Cancel") == ElementType.BUTTON
        assert cls("submit") == ElementType.BUTTON

    def test_classify_url(self):
        from core.perception.pipeline import PerceptionPipeline
        cls = PerceptionPipeline._classify_text_element
        assert cls("https://example.com") == ElementType.LINK
        assert cls("www.google.com") == ElementType.LINK

    def test_classify_menu(self):
        from core.perception.pipeline import PerceptionPipeline
        cls = PerceptionPipeline._classify_text_element
        assert cls("File") == ElementType.MENU_ITEM
        assert cls("Settings") == ElementType.MENU_ITEM

    def test_classify_input(self):
        from core.perception.pipeline import PerceptionPipeline
        cls = PerceptionPipeline._classify_text_element
        assert cls("Enter your email") == ElementType.INPUT
        assert cls("Search for...") == ElementType.INPUT

    def test_classify_plain_text(self):
        from core.perception.pipeline import PerceptionPipeline
        cls = PerceptionPipeline._classify_text_element
        assert cls("Hello World") == ElementType.TEXT
        assert cls("Welcome to the application") == ElementType.TEXT

    def test_classify_control_type_mapping(self):
        from core.perception.pipeline import PerceptionPipeline
        cls = PerceptionPipeline._classify_element_type
        assert cls("button") == ElementType.BUTTON
        assert cls("edit") == ElementType.INPUT
        assert cls("checkbox") == ElementType.CHECKBOX
        assert cls("tab") == ElementType.TAB
        assert cls("unknown_weird_thing") == ElementType.UNKNOWN


class TestPipelineIntegration:
    """Test the full pipeline with mocked subsystems."""

    def test_analyze_with_no_sources(self):
        from core.perception.pipeline import _result_cache, _result_cache_lock
        with _result_cache_lock:
            _result_cache.clear()
        from core.perception.pipeline import PerceptionPipeline
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), color="white")
        result = pipeline.analyze(
            img,
            include_accessibility=False,
            include_ocr=False,
            include_vision=False,
        )
        assert result.elements == []
        assert result.accessibility_count == 0
        assert result.ocr_count == 0
        assert result.processing_time_ms >= 0

    def test_analyze_fuses_sources(self):
        from core.perception.pipeline import _result_cache, _result_cache_lock
        with _result_cache_lock:
            _result_cache.clear()
        from core.perception.pipeline import PerceptionPipeline
        pipeline = PerceptionPipeline()

        acc_elems = [
            PerceptionElement(
                label="File", element_type=ElementType.MENU_ITEM,
                bounding_box=(10, 5, 40, 20), confidence=0.95,
                source=ElementSource.ACCESSIBILITY, is_interactable=True,
                actions=["click"],
            ),
        ]
        ocr_elems = [
            PerceptionElement(
                label="Edit", element_type=ElementType.MENU_ITEM,
                bounding_box=(60, 5, 35, 20), confidence=0.7,
                source=ElementSource.OCR,
            ),
        ]

        # Test full pipeline with mocked query methods
        with patch.object(pipeline, '_query_accessibility', return_value=acc_elems), \
             patch.object(pipeline, '_query_ocr', return_value=ocr_elems):
            img = Image.new("RGB", (800, 600), color="white")
            result = pipeline.analyze(img, include_vision=False)
            assert len(result.elements) == 2
            assert result.accessibility_count == 1
            assert result.ocr_count == 1

    def test_caching_returns_same_result(self):
        from core.perception.pipeline import _result_cache, _result_cache_lock
        with _result_cache_lock:
            _result_cache.clear()
        from core.perception.pipeline import PerceptionPipeline
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (100, 100), color="blue")
        r1 = pipeline.analyze(
            img,
            include_accessibility=False,
            include_ocr=False,
            include_vision=False,
        )
        r2 = pipeline.analyze(
            img,
            include_accessibility=False,
            include_ocr=False,
            include_vision=False,
        )
        assert r1.screenshot_hash == r2.screenshot_hash
