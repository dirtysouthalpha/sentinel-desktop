"""Tests for Phase 6: Local Grounding Model — feature-flagged, optional, air-gapped."""

from unittest.mock import MagicMock, patch

from PIL import Image

from core.local_grounding import (
    FEATURE_FLAG,
    LocalGroundingModel,
    LocalGroundingResult,
    get_grounding_backend,
    is_local_grounding_enabled,
)

# ---------------------------------------------------------------------------
# LocalGroundingResult
# ---------------------------------------------------------------------------


class TestLocalGroundingResult:
    """Test the grounding result dataclass."""

    def test_default_result_is_invalid(self):
        result = LocalGroundingResult()
        assert result.is_valid is False
        assert result.model == "none"

    def test_valid_result(self):
        result = LocalGroundingResult(bbox=(100, 200, 80, 30), confidence=0.9)
        assert result.is_valid is True
        assert result.confidence == 0.9

    def test_center_property(self):
        result = LocalGroundingResult(bbox=(100, 200, 100, 40))
        assert result.center == (150, 220)

    def test_zero_area_is_invalid(self):
        result = LocalGroundingResult(bbox=(100, 200, 0, 0))
        assert result.is_valid is False

    def test_latency_tracking(self):
        result = LocalGroundingResult(latency_ms=42.5)
        assert result.latency_ms == 42.5


# ---------------------------------------------------------------------------
# LocalGroundingModel
# ---------------------------------------------------------------------------


class TestLocalGroundingModel:
    """Test the local grounding model interface."""

    def test_auto_backend_no_model_available(self):
        """Without any backends installed, returns invalid result."""
        model = LocalGroundingModel(backend="auto")
        with patch.dict("core.local_grounding._BACKEND_LOADERS", {}, clear=True):
            result = model.predict(Image.new("RGB", (800, 600)), "Save button")
            assert result.is_valid is False
            assert result.model == "none"

    def test_is_available_false_without_backends(self):
        model = LocalGroundingModel(backend="auto")
        with patch.dict("core.local_grounding._BACKEND_LOADERS", {}, clear=True):
            assert model.is_available is False

    def test_predict_with_mock_backend(self):
        """When a backend is available, predict returns its result."""
        model = LocalGroundingModel(backend="test")

        mock_backend = MagicMock()
        mock_backend.predict.return_value = LocalGroundingResult(
            bbox=(100, 200, 80, 30),
            confidence=0.85,
            label="Save button",
        )

        def mock_loader():
            return mock_backend

        with patch.dict("core.local_grounding._BACKEND_LOADERS", {"test": mock_loader}):
            result = model.predict(Image.new("RGB", (800, 600)), "Save button")
            assert result.is_valid is True
            assert result.bbox == (100, 200, 80, 30)
            assert result.confidence == 0.85
            assert result.latency_ms >= 0  # mocked backend may complete in 0.0ms

    def test_predict_with_raw_bbox_tuple(self):
        """Backend returning raw tuple gets wrapped in LocalGroundingResult."""
        model = LocalGroundingModel(backend="test")

        mock_backend = MagicMock()
        mock_backend.predict.return_value = (150, 250, 100, 40)

        def mock_loader():
            return mock_backend

        with patch.dict("core.local_grounding._BACKEND_LOADERS", {"test": mock_loader}):
            result = model.predict(Image.new("RGB", (800, 600)), "OK button")
            assert result.is_valid is True
            assert result.bbox == (150, 250, 100, 40)

    def test_predict_error_returns_invalid(self):
        """Backend errors are caught and return invalid result."""
        model = LocalGroundingModel(backend="test")

        mock_backend = MagicMock()
        mock_backend.predict.side_effect = RuntimeError("model crashed")

        def mock_loader():
            return mock_backend

        with patch.dict("core.local_grounding._BACKEND_LOADERS", {"test": mock_loader}):
            result = model.predict(Image.new("RGB", (800, 600)), "test")
            assert result.is_valid is False

    def test_specific_backend_import_error(self):
        """When specific backend can't load, is_available is False."""
        model = LocalGroundingModel(backend="omniparser")

        def failing_loader():
            raise ImportError("not installed")

        with patch.dict("core.local_grounding._BACKEND_LOADERS", {"omniparser": failing_loader}):
            assert model.is_available is False


# ---------------------------------------------------------------------------
# Feature flag (LCL-02)
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    """Test feature flag configuration."""

    def test_disabled_by_default(self):
        assert is_local_grounding_enabled(None) is False
        assert is_local_grounding_enabled({}) is False

    def test_enabled_with_bool(self):
        assert is_local_grounding_enabled({"local_grounding": True}) is True
        assert is_local_grounding_enabled({"local_grounding": False}) is False

    def test_enabled_with_dict(self):
        config = {"local_grounding": {"enabled": True, "model": "auto"}}
        assert is_local_grounding_enabled(config) is True

    def test_disabled_with_dict(self):
        config = {"local_grounding": {"enabled": False}}
        assert is_local_grounding_enabled(config) is False

    def test_feature_flag_constant(self):
        assert FEATURE_FLAG == "local_grounding"


class TestBackendConfig:
    """Test backend configuration."""

    def test_default_auto(self):
        assert get_grounding_backend(None) == "auto"
        assert get_grounding_backend({}) == "auto"

    def test_configured_backend(self):
        config = {"local_grounding": {"model": "florence2"}}
        assert get_grounding_backend(config) == "florence2"

    def test_bool_config_returns_auto(self):
        assert get_grounding_backend({"local_grounding": True}) == "auto"


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


class TestPipelineLocalGrounding:
    """Test perception pipeline's local grounding integration."""

    def test_pipeline_vision_splits_into_cv_and_local(self):
        """Pipeline vision query uses both CV and local model."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        # Verify methods exist
        assert hasattr(pipeline, "_cv_contour_detection")
        assert hasattr(pipeline, "_local_grounding_detection")

    def test_local_grounding_returns_empty_without_model(self):
        """Local grounding path returns empty when no model available."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), "white")

        with patch.dict("core.local_grounding._BACKEND_LOADERS", {}, clear=True):
            elements = pipeline._local_grounding_detection(img)
            assert elements == []

    def test_cv_contour_returns_empty_without_opencv(self):
        """CV contour returns empty when OpenCV not available."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), "white")

        with patch.dict("sys.modules", {"cv2": None, "numpy": None}):
            elements = pipeline._cv_contour_detection(img)
            assert elements == []

    def test_full_vision_combines_both_sources(self):
        """Full _query_vision combines CV contours and local grounding."""
        from core.perception.pipeline import PerceptionPipeline

        pipeline = PerceptionPipeline()
        img = Image.new("RGB", (800, 600), "white")

        with patch.object(
            pipeline,
            "_cv_contour_detection",
            return_value=[
                MagicMock(source="cv"),
            ],
        ):
            with patch.object(
                pipeline,
                "_local_grounding_detection",
                return_value=[
                    MagicMock(source="local"),
                ],
            ):
                elements = pipeline._query_vision(img)
                assert len(elements) == 2


# ---------------------------------------------------------------------------
# Coverage gap tests — targets all 24 missed lines
# ---------------------------------------------------------------------------


class TestLocalGroundingCoverage:
    """Targets uncovered lines: 96, 164, 196, 207-224, 234, 245-267, 293."""

    # Line 96 -------------------------------------------------------------------

    def test_try_load_early_return_model_is_none(self):
        """Line 96: _try_load returns False when already initialized but _model is None."""
        model = LocalGroundingModel(backend="test")
        model._initialized = True
        model._model = None
        assert model._try_load() is False

    def test_try_load_early_return_model_set(self):
        """Line 96: _try_load returns True when already initialized and _model exists."""
        model = LocalGroundingModel(backend="test")
        model._initialized = True
        model._model = MagicMock()
        assert model._try_load() is True

    # Line 164 ------------------------------------------------------------------

    def test_predict_unexpected_return_type(self):
        """Line 164: model returns an unexpected type (not LocalGroundingResult or 4-tuple)."""
        model = LocalGroundingModel(backend="test")
        mock_backend = MagicMock()
        mock_backend.predict.return_value = "unexpected string"

        def mock_loader():
            return mock_backend

        with patch.dict("core.local_grounding._BACKEND_LOADERS", {"test": mock_loader}):
            result = model.predict(Image.new("RGB", (100, 100)), "test")

        assert result.model == "test"
        assert result.is_valid is False
        assert result.latency_ms >= 0

    # Line 196 ------------------------------------------------------------------

    def test_load_omniparser_success(self):
        """Line 196: _load_omniparser returns OmniParser() when module is importable."""
        from core.local_grounding import _load_omniparser

        mock_omni_cls = MagicMock()
        mock_omni_module = MagicMock()
        mock_omni_module.OmniParser = mock_omni_cls

        with patch.dict("sys.modules", {"omniparser": mock_omni_module}):
            result = _load_omniparser()

        mock_omni_cls.assert_called_once()
        assert result is mock_omni_cls.return_value

    # Lines 207-224 -------------------------------------------------------------

    def test_load_florence2_success_and_predict_not_implemented(self):
        """Lines 207-224: _load_florence2 creates wrapper; predict raises NotImplementedError."""
        import pytest

        from core.local_grounding import _load_florence2

        mock_transformers = MagicMock()
        mock_transformers.AutoModelForCausalLM.from_pretrained.return_value = MagicMock()
        mock_transformers.AutoProcessor.from_pretrained.return_value = MagicMock()

        with patch.dict("sys.modules", {"transformers": mock_transformers}):
            wrapper = _load_florence2()

        assert wrapper is not None
        assert hasattr(wrapper, "predict")
        with pytest.raises(NotImplementedError):
            wrapper.predict(Image.new("RGB", (100, 100)), "test")

    # Line 234 ------------------------------------------------------------------

    def test_load_uground_success(self):
        """Line 234: _load_uground returns uground.Model() when module is importable."""
        from core.local_grounding import _load_uground

        mock_uground = MagicMock()

        with patch.dict("sys.modules", {"uground": mock_uground}):
            result = _load_uground()

        mock_uground.Model.assert_called_once()
        assert result is mock_uground.Model.return_value

    # Lines 245-267 -------------------------------------------------------------

    def test_load_yolo_success_no_detections(self):
        """Lines 245-252, 265, 267: _load_yolo creates wrapper; predict with empty boxes."""
        from core.local_grounding import LocalGroundingResult, _load_yolo

        mock_yolo_instance = MagicMock()
        mock_ultralytics = MagicMock()
        mock_ultralytics.YOLO.return_value = mock_yolo_instance

        with patch.dict("sys.modules", {"ultralytics": mock_ultralytics}):
            wrapper = _load_yolo()

        mock_ultralytics.YOLO.assert_called_once_with("yolov8n.pt")
        assert wrapper is not None

        # No detections: len(boxes) == 0 → return LocalGroundingResult() (line 265)
        mock_result = MagicMock()
        mock_result.boxes.__len__.return_value = 0
        mock_yolo_instance.return_value = [mock_result]

        result = wrapper.predict(Image.new("RGB", (200, 200)), "test button")
        assert isinstance(result, LocalGroundingResult)
        assert result.is_valid is False

    def test_load_yolo_predict_with_detections(self):
        """Lines 255-264: _YOLOWrapper.predict returns bbox when detections are present."""
        import numpy as np

        from core.local_grounding import LocalGroundingResult, _load_yolo

        mock_yolo_instance = MagicMock()
        mock_ultralytics = MagicMock()
        mock_ultralytics.YOLO.return_value = mock_yolo_instance

        with patch.dict("sys.modules", {"ultralytics": mock_ultralytics}):
            wrapper = _load_yolo()

        # Build mock detection: boxes[0].xyxy[0].cpu().numpy() = [10, 20, 110, 70]
        box_coords = np.array([10.0, 20.0, 110.0, 70.0])
        mock_xyxy_entry = MagicMock()
        mock_xyxy_entry.cpu.return_value.numpy.return_value = box_coords

        mock_box = MagicMock()
        mock_box.xyxy = [mock_xyxy_entry]  # plain list so [0] works normally
        mock_box.conf = [0.9]  # plain list so float(conf[0]) works

        mock_boxes = MagicMock()
        mock_boxes.__len__.return_value = 1
        mock_boxes.__getitem__.return_value = mock_box

        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_yolo_instance.return_value = [mock_result]

        result = wrapper.predict(Image.new("RGB", (200, 200)), "test button")
        assert isinstance(result, LocalGroundingResult)
        assert result.bbox == (10, 20, 100, 50)  # x2-x1=100, y2-y1=50
        assert result.confidence == 0.9

    # Line 293 ------------------------------------------------------------------

    def test_is_local_grounding_enabled_non_bool_non_dict(self):
        """Line 293: is_local_grounding_enabled returns False when setting is not bool or dict."""
        assert is_local_grounding_enabled({"local_grounding": 42}) is False
        assert is_local_grounding_enabled({"local_grounding": "yes"}) is False
        assert is_local_grounding_enabled({"local_grounding": [True]}) is False
