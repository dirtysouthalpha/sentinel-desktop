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
            id=1,
            label="Save",
            element_type=ElementType.BUTTON,
            bounding_box=(100, 200, 80, 30),
            confidence=0.95,
            source=ElementSource.ACCESSIBILITY,
            actions=["click"],
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
                id=1,
                label="Save",
                element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30),
                is_interactable=True,
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
                label="Save",
                element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30),
                confidence=0.95,
                source=ElementSource.ACCESSIBILITY,
                is_interactable=True,
            ),
        ]
        result = fusion.fuse(accessibility_elements=elems)
        assert len(result) == 1
        assert result[0].id == 1

    def test_deduplication_merges_overlapping(self):
        fusion = FusionEngine()
        acc = [
            PerceptionElement(
                label="Save",
                bounding_box=(100, 200, 80, 30),
                confidence=0.95,
                source=ElementSource.ACCESSIBILITY,
                is_interactable=True,
            ),
        ]
        ocr = [
            PerceptionElement(
                label="Save",
                bounding_box=(102, 201, 78, 28),
                confidence=0.8,
                source=ElementSource.OCR,
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
                label="Save",
                bounding_box=(100, 200, 80, 30),
                confidence=0.95,
                source=ElementSource.ACCESSIBILITY,
            ),
        ]
        ocr = [
            PerceptionElement(
                label="Cancel",
                bounding_box=(400, 200, 80, 30),
                confidence=0.8,
                source=ElementSource.OCR,
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
            PerceptionElement(label=f"E{i}", bounding_box=(i * 100, 0, 50, 50)) for i in range(5)
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
                id=1,
                label="Save",
                element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30),
                is_interactable=True,
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
                label="File",
                element_type=ElementType.MENU_ITEM,
                bounding_box=(10, 5, 40, 20),
                confidence=0.95,
                source=ElementSource.ACCESSIBILITY,
                is_interactable=True,
                actions=["click"],
            ),
        ]
        ocr_elems = [
            PerceptionElement(
                label="Edit",
                element_type=ElementType.MENU_ITEM,
                bounding_box=(60, 5, 35, 20),
                confidence=0.7,
                source=ElementSource.OCR,
            ),
        ]

        # Test full pipeline with mocked query methods
        with (
            patch.object(pipeline, "_query_accessibility", return_value=acc_elems),
            patch.object(pipeline, "_query_ocr", return_value=ocr_elems),
        ):
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

    def test_query_accessibility_with_backend(self):
        """Test _query_accessibility with actual backend calls."""
        from core.perception.pipeline import _result_cache, _result_cache_lock

        with _result_cache_lock:
            _result_cache.clear()
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()

        # Mock backend to return sample tree
        mock_node = type("Node", (), {
            "name": "Button",
            "control_type": "Button",
            "bounding_box": (10, 10, 100, 30),
            "actions": ["click"],
            "raw": {"role": "button"}
        })()

        with patch("core.platform.get_backend") as mock_get_backend:
            mock_backend = type("Backend", (), {
                "accessibility": type("Acc", (), {
                    "is_available": lambda: True,
                    "get_tree": lambda x: [mock_node]
                })()
            })()
            mock_get_backend.return_value = mock_backend

            result = pipeline._query_accessibility()
            # Should return results from the mocked backend
            assert isinstance(result, list)

    def test_query_accessibility_unavailable(self):
        """Test _query_accessibility when backend is unavailable."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()

        with patch("core.platform.get_backend") as mock_get_backend:
            mock_backend = type("Backend", (), {
                "accessibility": type("Acc", (), {
                    "is_available": lambda: False
                })()
            })()
            mock_get_backend.return_value = mock_backend

            result = pipeline._query_accessibility()
            assert result == []

    def test_query_accessibility_exception_handling(self):
        """Test _query_accessibility handles exceptions gracefully."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()

        with patch("core.platform.get_backend", side_effect=ImportError("No module")):
            result = pipeline._query_accessibility()
            assert result == []

    def test_query_ocr_handles_exceptions(self):
        """Test _query_ocr handles exceptions gracefully."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), color="white")

        # Test with missing OCR module (ImportError)
        result = pipeline._query_ocr(img)
        assert isinstance(result, list)  # Should return empty list on failure

    def test_query_vision_placeholder(self):
        """Test _query_vision returns empty list (placeholder for future)."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), color="white")

        result = pipeline._query_vision(img)
        assert result == []

    def test_classify_element_type_button(self):
        """Test element type classification for Button."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()

        # Test common button control types
        assert pipeline._classify_element_type("Button") == ElementType.BUTTON
        assert pipeline._classify_element_type("button") == ElementType.BUTTON

    def test_classify_element_type_text(self):
        """Test element type classification for Text."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()

        # Test text control types
        assert pipeline._classify_element_type("Text") == ElementType.TEXT
        assert pipeline._classify_element_type("Edit") == ElementType.INPUT  # Edit maps to INPUT, not TEXT

    def test_classify_element_type_unknown(self):
        """Test element type classification for unknown types."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()

        # Test unknown control type defaults to UNKNOWN
        assert pipeline._classify_element_type("UnknownWidget") == ElementType.UNKNOWN
        assert pipeline._classify_element_type("") == ElementType.UNKNOWN

    def test_cache_key_generation(self):
        """Test _cache_key generates consistent hash."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (100, 100), color="blue")

        key1 = pipeline._cache_key(img)
        key2 = pipeline._cache_key(img)

        assert key1 == key2
        assert isinstance(key1, str)
        assert len(key1) > 0

    def test_cache_operations(self):
        """Test cache store and get operations."""
        from core.perception.pipeline import _result_cache, _result_cache_lock, PerceptionPipeline
        from core.perception.types import PerceptionResult

        with _result_cache_lock:
            _result_cache.clear()

        pipeline = PerceptionPipeline()
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        mock_result = PerceptionResult(
            annotated_image=img,
            elements=[],
            text_description="test",
            accessibility_count=0,
            ocr_count=0,
            vision_count=0,
            processing_time_ms=10.0,
            screenshot_hash="test123"
        )

        # Test store
        cache_key = "test-key"
        pipeline._store_cached(cache_key, mock_result)

        # Test get
        retrieved = pipeline._get_cached(cache_key)
        assert retrieved is not None
        assert retrieved.text_description == "test"

    def test_cache_ttl_expires_old_entries(self):
        """Test cache entries expire after TTL."""
        from core.perception.pipeline import _result_cache, _result_cache_lock, PerceptionPipeline
        from core.perception.types import PerceptionResult
        import time

        with _result_cache_lock:
            _result_cache.clear()

        pipeline = PerceptionPipeline()
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="green")
        mock_result = PerceptionResult(
            annotated_image=img,
            elements=[],
            text_description="expired",
            accessibility_count=0,
            ocr_count=0,
            vision_count=0,
            processing_time_ms=10.0,
            screenshot_hash="expire-test"
        )

        # Store with timestamp in the past (beyond TTL)
        cache_key = "expire-key"
        with _result_cache_lock:
            _result_cache[cache_key] = (mock_result, time.monotonic() - 10.0)  # 10 seconds ago

        # Should return None since entry is expired
        retrieved = pipeline._get_cached(cache_key)
        assert retrieved is None

    def test_build_text_description(self):
        """Test _build_text_description generates element descriptions."""
        from core.perception.pipeline import PerceptionPipeline
        from core.perception.types import PerceptionElement, ElementType

        pipeline = PerceptionPipeline()

        elements = [
            PerceptionElement(
                id=1,
                label="Save",
                element_type=ElementType.BUTTON,
                bounding_box=(10, 10, 50, 20),
            ),
            PerceptionElement(
                id=2,
                label="Username",
                element_type=ElementType.TEXT,
                bounding_box=(10, 40, 100, 20),
            ),
        ]

        description = pipeline._build_text_description(elements)
        assert "Save" in description
        assert "Username" in description
        assert isinstance(description, str)

    def test_analyze_includes_vision(self):
        """Test analyze with vision enabled."""
        from core.perception.pipeline import _result_cache, _result_cache_lock, PerceptionPipeline

        with _result_cache_lock:
            _result_cache.clear()

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), color="white")

        # Test with vision enabled (should call _query_vision)
        result = pipeline.analyze(
            img,
            include_accessibility=False,
            include_ocr=False,
            include_vision=True,
        )

        assert result.vision_count == 0  # Returns empty list (placeholder)
        assert result.processing_time_ms >= 0


# ---------------------------------------------------------------------------
# Pipeline coverage: _query_accessibility body, _query_ocr body, cv/grounding,
# cache eviction paths, cache_key error path
# ---------------------------------------------------------------------------


class TestPipelineCoverage:
    """Tests targeting previously uncovered branches in PerceptionPipeline."""

    def _clear_cache(self):
        from core.perception.pipeline import _result_cache, _result_cache_lock
        with _result_cache_lock:
            _result_cache.clear()

    # ── _query_accessibility body (lines 143-164) ─────────────────────────

    def test_query_accessibility_returns_elements(self):
        """_query_accessibility converts tree nodes to PerceptionElements."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline
        from core.perception.types import ElementSource

        node = MagicMock()
        node.name = "Save"
        node.control_type = "Button"
        node.bounding_box = (10, 10, 80, 30)
        node.actions = ["click"]
        node.raw = {}

        mock_backend = MagicMock()
        mock_backend.accessibility.is_available.return_value = True
        mock_backend.accessibility.get_tree.return_value = [node]

        pipeline = PerceptionPipeline()
        with patch("core.platform.get_backend", return_value=mock_backend):
            elements = pipeline._query_accessibility("TestWindow")

        assert len(elements) == 1
        assert elements[0].label == "Save"
        assert elements[0].source == ElementSource.ACCESSIBILITY
        assert elements[0].is_interactable is True

    def test_query_accessibility_unavailable_backend(self):
        """_query_accessibility returns [] when backend is unavailable."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_backend = MagicMock()
        mock_backend.accessibility.is_available.return_value = False

        pipeline = PerceptionPipeline()
        with patch("core.platform.get_backend", return_value=mock_backend):
            elements = pipeline._query_accessibility(None)

        assert elements == []

    def test_query_accessibility_empty_tree(self):
        """_query_accessibility with an empty tree returns []."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_backend = MagicMock()
        mock_backend.accessibility.is_available.return_value = True
        mock_backend.accessibility.get_tree.return_value = []

        pipeline = PerceptionPipeline()
        with patch("core.platform.get_backend", return_value=mock_backend):
            elements = pipeline._query_accessibility("Main")

        assert elements == []

    def test_query_accessibility_node_no_bbox(self):
        """_query_accessibility uses (0,0,0,0) when node.bounding_box is None."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        node = MagicMock()
        node.name = "Label"
        node.control_type = "Text"
        node.bounding_box = None
        node.actions = []
        node.raw = {}

        mock_backend = MagicMock()
        mock_backend.accessibility.is_available.return_value = True
        mock_backend.accessibility.get_tree.return_value = [node]

        pipeline = PerceptionPipeline()
        with patch("core.platform.get_backend", return_value=mock_backend):
            elements = pipeline._query_accessibility(None)

        assert elements[0].bounding_box == (0, 0, 0, 0)

    # ── _query_ocr body (lines 181-222) ──────────────────────────────────

    def test_query_ocr_with_boxes(self):
        """_query_ocr produces PerceptionElements from OCR boxes."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline
        from core.perception.types import ElementSource

        boxes = [
            {"text": "Save", "bbox": (10, 10, 90, 40), "confidence": 90},
            {"text": "cancel", "bbox": (100, 10, 180, 40), "confidence": 0.85},
        ]
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch("core.ocr.find_text_boxes", return_value=boxes):
            elements = pipeline._query_ocr(img)

        assert len(elements) >= 1
        sources = {e.source for e in elements}
        assert ElementSource.OCR in sources

    def test_query_ocr_skips_empty_text(self):
        """_query_ocr skips boxes with empty text."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline

        boxes = [
            {"text": "", "bbox": (10, 10, 90, 40), "confidence": 0.9},
            {"text": "  ", "bbox": (10, 50, 90, 80), "confidence": 0.9},
            {"text": "OK", "bbox": (10, 90, 90, 120), "confidence": 0.9},
        ]
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch("core.ocr.find_text_boxes", return_value=boxes):
            elements = pipeline._query_ocr(img)

        assert all(e.label.strip() for e in elements)

    def test_query_ocr_skips_missing_bbox(self):
        """_query_ocr skips boxes missing bbox."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline

        boxes = [
            {"text": "Save", "bbox": None, "confidence": 0.9},
            {"text": "OK", "bbox": (10, 10, 90, 40), "confidence": 0.9},
        ]
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch("core.ocr.find_text_boxes", return_value=boxes):
            elements = pipeline._query_ocr(img)

        labels = [e.label for e in elements]
        assert "Save" not in labels

    def test_query_ocr_confidence_normalization(self):
        """_query_ocr normalizes confidence > 1 to 0-1 range."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline

        boxes = [
            {"text": "OK", "bbox": (10, 10, 90, 40), "confidence": 95},
        ]
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch("core.ocr.find_text_boxes", return_value=boxes):
            elements = pipeline._query_ocr(img)

        if elements:
            assert elements[0].confidence <= 1.0

    def test_query_ocr_zero_dimension_box_skipped(self):
        """_query_ocr skips boxes with zero width or height."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline

        boxes = [
            {"text": "Ghost", "bbox": (10, 10, 10, 40), "confidence": 0.9},  # w=0
            {"text": "Real", "bbox": (10, 10, 90, 40), "confidence": 0.9},
        ]
        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch("core.ocr.find_text_boxes", return_value=boxes):
            elements = pipeline._query_ocr(img)

        labels = [e.label for e in elements]
        assert "Ghost" not in labels
        assert "Real" in labels

    # ── _cv_contour_detection (lines 250-290) ────────────────────────────

    def test_cv_contour_detection_no_cv2(self):
        """_cv_contour_detection returns [] when cv2 is not available."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline
        import sys

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (200, 200))

        saved_cv2 = sys.modules.get("cv2")
        sys.modules["cv2"] = None  # type: ignore[assignment]
        try:
            elements = pipeline._cv_contour_detection(img)
        finally:
            if saved_cv2 is None:
                sys.modules.pop("cv2", None)
            else:
                sys.modules["cv2"] = saved_cv2

        assert elements == []

    def test_cv_contour_detection_with_mock_cv2(self):
        """_cv_contour_detection processes contours when cv2 is available."""
        from unittest.mock import MagicMock, patch
        import numpy as np
        from core.perception.pipeline import PerceptionPipeline

        mock_cv2 = MagicMock()
        # Make a contour that passes all filters: area=300*100=30000, aspect=3, w>15, h>15
        contour = np.array([[[0, 0]], [[300, 0]], [[300, 100]], [[0, 100]]])
        mock_cv2.boundingRect.return_value = (10, 20, 300, 100)
        mock_cv2.findContours.return_value = ([contour], None)
        mock_cv2.cvtColor.return_value = MagicMock()
        mock_cv2.Canny.return_value = MagicMock()
        mock_cv2.getStructuringElement.return_value = MagicMock()
        mock_cv2.dilate.return_value = MagicMock()
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.MORPH_RECT = 0
        mock_cv2.RETR_EXTERNAL = 0
        mock_cv2.CHAIN_APPROX_SIMPLE = 2

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": np}):
            elements = pipeline._cv_contour_detection(img)

        assert len(elements) >= 1
        assert elements[0].confidence == 0.3

    def test_cv_contour_detection_filters_tiny_contours(self):
        """_cv_contour_detection skips contours that are too small."""
        from unittest.mock import MagicMock, patch
        import numpy as np
        from core.perception.pipeline import PerceptionPipeline

        mock_cv2 = MagicMock()
        # Area = 10*10 = 100 < 200 → filtered
        mock_cv2.boundingRect.return_value = (0, 0, 10, 10)
        mock_cv2.findContours.return_value = ([MagicMock()], None)
        mock_cv2.cvtColor.return_value = MagicMock()
        mock_cv2.Canny.return_value = MagicMock()
        mock_cv2.getStructuringElement.return_value = MagicMock()
        mock_cv2.dilate.return_value = MagicMock()
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.MORPH_RECT = 0
        mock_cv2.RETR_EXTERNAL = 0
        mock_cv2.CHAIN_APPROX_SIMPLE = 2

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": np}):
            elements = pipeline._cv_contour_detection(img)

        assert elements == []

    def test_cv_contour_detection_exception_returns_empty(self):
        """_cv_contour_detection handles exceptions gracefully."""
        from unittest.mock import MagicMock, patch
        import numpy as np
        from core.perception.pipeline import PerceptionPipeline

        mock_cv2 = MagicMock()
        mock_cv2.cvtColor.side_effect = RuntimeError("GPU error")
        mock_cv2.COLOR_RGB2GRAY = 7

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": np}):
            elements = pipeline._cv_contour_detection(img)

        assert elements == []

    # ── _local_grounding_detection (lines 306-337) ────────────────────────

    def test_local_grounding_model_available_returns_elements(self):
        """_local_grounding_detection returns elements when model is available."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline
        from core.perception.types import ElementSource

        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.confidence = 0.9
        mock_result.bbox = (10, 20, 50, 30)

        mock_model = MagicMock()
        mock_model.is_available = True
        mock_model.predict.return_value = mock_result

        mock_model_class = MagicMock(return_value=mock_model)

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"core.local_grounding": MagicMock(LocalGroundingModel=mock_model_class)}):
            elements = pipeline._local_grounding_detection(img)

        assert len(elements) >= 1
        assert elements[0].source == ElementSource.VISION
        assert elements[0].confidence == 0.9

    def test_local_grounding_model_unavailable(self):
        """_local_grounding_detection returns [] when model is not available."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_model = MagicMock()
        mock_model.is_available = False
        mock_model_class = MagicMock(return_value=mock_model)

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"core.local_grounding": MagicMock(LocalGroundingModel=mock_model_class)}):
            elements = pipeline._local_grounding_detection(img)

        assert elements == []

    def test_local_grounding_low_confidence_filtered(self):
        """_local_grounding_detection filters results below 0.5 confidence."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.confidence = 0.3  # below threshold

        mock_model = MagicMock()
        mock_model.is_available = True
        mock_model.predict.return_value = mock_result

        mock_model_class = MagicMock(return_value=mock_model)

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"core.local_grounding": MagicMock(LocalGroundingModel=mock_model_class)}):
            elements = pipeline._local_grounding_detection(img)

        assert elements == []

    def test_local_grounding_exception_returns_empty(self):
        """_local_grounding_detection handles exceptions gracefully."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_model = MagicMock()
        mock_model.is_available = True
        mock_model.predict.side_effect = RuntimeError("CUDA OOM")
        mock_model_class = MagicMock(return_value=mock_model)

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        with patch.dict("sys.modules", {"core.local_grounding": MagicMock(LocalGroundingModel=mock_model_class)}):
            elements = pipeline._local_grounding_detection(img)

        assert elements == []

    # ── cache_key error path (lines 476-477) ─────────────────────────────

    def test_cache_key_getpixel_error_falls_back(self):
        """_cache_key uses size-only fingerprint when getpixel raises."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        img = MagicMock()
        img.size = (100, 100)
        img.getpixel.side_effect = OSError("display error")

        key = PerceptionPipeline._cache_key(img)
        assert isinstance(key, str)
        assert len(key) == 32  # md5 hex digest

    # ── cache eviction paths (lines 499, 503-504) ─────────────────────────

    def test_store_cached_evicts_expired_entries(self):
        """_store_cached removes expired entries before storing new result."""
        import time
        from core.perception.pipeline import (
            PerceptionPipeline,
            _result_cache,
            _result_cache_lock,
        )
        from core.perception.types import PerceptionResult

        self._clear_cache()
        pipeline = PerceptionPipeline()
        old_result = PerceptionResult(elements=[])
        new_result = PerceptionResult(elements=[])

        # Plant an expired entry
        with _result_cache_lock:
            _result_cache["stale-key"] = (old_result, time.monotonic() - 100.0)

        pipeline._store_cached("fresh-key", new_result)

        with _result_cache_lock:
            assert "stale-key" not in _result_cache
            assert "fresh-key" in _result_cache

    def test_query_ocr_exception_returns_empty(self):
        """_query_ocr returns [] when find_text_boxes raises."""
        from unittest.mock import patch
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch("core.ocr.find_text_boxes", side_effect=RuntimeError("OCR crash")):
            elements = pipeline._query_ocr(img)

        assert elements == []

    def test_cv_contour_aspect_filter(self):
        """_cv_contour_detection skips contours with aspect ratio > 10."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_cv2 = MagicMock()
        # w=200, h=10 → area=2000 > 200, aspect=20 > 10 → filtered out
        mock_cv2.boundingRect.return_value = (0, 0, 200, 10)
        mock_cv2.findContours.return_value = ([MagicMock()], None)
        mock_cv2.cvtColor.return_value = MagicMock()
        mock_cv2.Canny.return_value = MagicMock()
        mock_cv2.getStructuringElement.return_value = MagicMock()
        mock_cv2.dilate.return_value = MagicMock()
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.MORPH_RECT = 0
        mock_cv2.RETR_EXTERNAL = 0
        mock_cv2.CHAIN_APPROX_SIMPLE = 2

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            elements = pipeline._cv_contour_detection(img)

        assert elements == []

    def test_cv_contour_small_dimension_filter(self):
        """_cv_contour_detection skips contours with w or h < 15."""
        from unittest.mock import MagicMock, patch
        from core.perception.pipeline import PerceptionPipeline

        mock_cv2 = MagicMock()
        # w=10 < 15 → filtered; area=10*30=300 > 200, aspect=30/10=3 <= 10
        mock_cv2.boundingRect.return_value = (0, 0, 10, 30)
        mock_cv2.findContours.return_value = ([MagicMock()], None)
        mock_cv2.cvtColor.return_value = MagicMock()
        mock_cv2.Canny.return_value = MagicMock()
        mock_cv2.getStructuringElement.return_value = MagicMock()
        mock_cv2.dilate.return_value = MagicMock()
        mock_cv2.COLOR_RGB2GRAY = 7
        mock_cv2.MORPH_RECT = 0
        mock_cv2.RETR_EXTERNAL = 0
        mock_cv2.CHAIN_APPROX_SIMPLE = 2

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            elements = pipeline._cv_contour_detection(img)

        assert elements == []

    def test_local_grounding_import_error_returns_empty(self):
        """_local_grounding_detection returns [] when core.local_grounding is missing."""
        from core.perception.pipeline import PerceptionPipeline
        import sys

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600))

        saved = sys.modules.get("core.local_grounding")
        sys.modules["core.local_grounding"] = None  # type: ignore[assignment]
        try:
            elements = pipeline._local_grounding_detection(img)
        finally:
            if saved is None:
                sys.modules.pop("core.local_grounding", None)
            else:
                sys.modules["core.local_grounding"] = saved

        assert elements == []

    def test_store_cached_evicts_oldest_when_at_capacity(self):
        """_store_cached evicts the oldest entry when cache is at max capacity."""
        import time
        from core.perception.pipeline import (
            PerceptionPipeline,
            _RESULT_CACHE_MAX,
            _result_cache,
            _result_cache_lock,
        )
        from core.perception.types import PerceptionResult

        self._clear_cache()
        pipeline = PerceptionPipeline()
        now = time.monotonic()
        dummy = PerceptionResult(elements=[])

        # Fill cache to max capacity — all entries fresh (age < TTL of 2s)
        # key-0 gets the smallest (oldest) timestamp, key-9 gets the largest (newest)
        with _result_cache_lock:
            for i in range(_RESULT_CACHE_MAX):
                _result_cache[f"key-{i}"] = (dummy, now - (_RESULT_CACHE_MAX - 1 - i) * 0.001)

        # Oldest is key-0 (largest age). Storing one more should evict it.
        pipeline._store_cached("new-key", dummy)

        with _result_cache_lock:
            assert "key-0" not in _result_cache
            assert "new-key" in _result_cache
