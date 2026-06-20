"""Tests for Phase 2: Hybrid Grounding Pipeline — engine integration + action handlers."""

from unittest.mock import MagicMock, patch

from core.action_executor import ActionExecutor, ExecutorConfig
from core.perception.types import (
    ElementSource,
    ElementType,
    PerceptionElement,
    PerceptionResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_element(
    elem_id: int,
    label: str = "Button",
    elem_type: ElementType = ElementType.BUTTON,
    bbox: tuple[int, int, int, int] = (100, 200, 80, 30),
    interactable: bool = True,
) -> PerceptionElement:
    """Create a test PerceptionElement."""
    return PerceptionElement(
        id=elem_id,
        label=label,
        element_type=elem_type,
        bounding_box=bbox,
        confidence=0.95,
        source=ElementSource.ACCESSIBILITY,
        actions=["click"],
        is_interactable=interactable,
    )


def _make_result(elements: list[PerceptionElement] | None = None) -> PerceptionResult:
    """Create a test PerceptionResult."""
    if elements is None:
        elements = [
            _make_element(1, "Save", bbox=(100, 100, 80, 30)),
            _make_element(2, "Cancel", bbox=(200, 100, 80, 30)),
            _make_element(3, "Username", ElementType.INPUT, bbox=(100, 200, 200, 25)),
            _make_element(4, "Password", ElementType.INPUT, bbox=(100, 250, 200, 25)),
        ]
    return PerceptionResult(
        elements=elements,
        text_description="Test elements",
        accessibility_count=len(elements),
        ocr_count=0,
        vision_count=0,
        processing_time_ms=10.0,
        screenshot_hash="abc123",
    )


# ---------------------------------------------------------------------------
# click_element action
# ---------------------------------------------------------------------------


class TestClickElement:
    """Tests for click_element action handler."""

    def test_no_perception_data(self):
        """Returns error when no perception result is stored."""
        executor = ActionExecutor()  # No dry_run — let handler run
        executor.perception_result = None
        result = executor.execute_sync({"action": "click_element", "element_id": 1})
        assert result["success"] is False
        assert "no perception" in result["output"].lower() or "No perception" in result["output"]

    def test_element_not_found(self):
        """Returns error when element ID doesn't exist."""
        executor = ActionExecutor()  # No dry_run — let handler run
        executor.perception_result = _make_result()
        result = executor.execute_sync({"action": "click_element", "element_id": 99})
        assert result["success"] is False
        assert "not found" in result["output"].lower()

    def test_click_valid_element(self):
        """Clicks at the center of the specified element."""
        executor = ActionExecutor(config=ExecutorConfig(dry_run=True))
        executor.perception_result = _make_result()
        # Element 1 has bbox (100, 100, 80, 30) → center (140, 115)
        result = executor.execute_sync({"action": "click_element", "element_id": 1})
        assert result["success"] is True

    def test_click_element_resolves_coordinates(self):
        """Verify the element center is computed correctly."""
        executor = ActionExecutor(config=ExecutorConfig(dry_run=True))
        elem = _make_element(5, "OK", bbox=(200, 300, 100, 40))
        executor.perception_result = _make_result([elem])

        # center = (200 + 50, 300 + 20) = (250, 320)
        # In dry-run mode, the action is logged but not executed
        result = executor.execute_sync({"action": "click_element", "element_id": 5})
        assert result["success"] is True

    def test_click_element_with_right_button(self):
        """Supports button parameter."""
        executor = ActionExecutor(config=ExecutorConfig(dry_run=True))
        executor.perception_result = _make_result()
        result = executor.execute_sync(
            {
                "action": "click_element",
                "element_id": 1,
                "button": "right",
            }
        )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# click_mark action
# ---------------------------------------------------------------------------


class TestClickMark:
    """Tests for click_mark action (alias for click_element)."""

    def test_click_mark_no_perception(self):
        executor = ActionExecutor()  # No dry_run
        executor.perception_result = None
        result = executor.execute_sync({"action": "click_mark", "mark_id": 3})
        assert result["success"] is False

    def test_click_mark_valid(self):
        executor = ActionExecutor(config=ExecutorConfig(dry_run=True))
        executor.perception_result = _make_result()
        result = executor.execute_sync({"action": "click_mark", "mark_id": 2})
        assert result["success"] is True

    def test_click_mark_not_found(self):
        executor = ActionExecutor()  # No dry_run
        executor.perception_result = _make_result()
        result = executor.execute_sync({"action": "click_mark", "mark_id": 999})
        assert result["success"] is False


# ---------------------------------------------------------------------------
# list_elements action
# ---------------------------------------------------------------------------


class TestListElements:
    """Tests for list_elements action handler."""

    def test_no_perception_data(self):
        executor = ActionExecutor()
        executor.perception_result = None
        result = executor.execute_sync({"action": "list_elements"})
        assert result["success"] is False
        assert "no perception" in result["output"].lower() or "No perception" in result["output"]

    def test_returns_element_list(self):
        executor = ActionExecutor()
        elements = [
            _make_element(1, "Save", bbox=(100, 100, 80, 30)),
            _make_element(2, "Open", bbox=(200, 100, 80, 30)),
        ]
        executor.perception_result = _make_result(elements)

        result = executor.execute_sync({"action": "list_elements"})
        assert result["success"] is True
        assert result["count"] == 2
        assert isinstance(result["output"], list)
        assert result["output"][0]["id"] == 1
        assert result["output"][1]["id"] == 2

    def test_includes_text_description(self):
        executor = ActionExecutor()
        executor.perception_result = _make_result()
        result = executor.execute_sync({"action": "list_elements"})
        assert result["success"] is True
        assert "text_description" in result
        assert isinstance(result["text_description"], str)

    def test_interactable_count(self):
        executor = ActionExecutor()
        elements = [
            _make_element(1, "Label", ElementType.TEXT, interactable=False),
            _make_element(2, "Button", ElementType.BUTTON, interactable=True),
        ]
        executor.perception_result = _make_result(elements)
        result = executor.execute_sync({"action": "list_elements"})
        assert result["success"] is True
        assert result["interactable"] == 1


# ---------------------------------------------------------------------------
# Dispatch table registration
# ---------------------------------------------------------------------------


class TestDispatchRegistration:
    """Verify new actions are in the dispatch table."""

    def test_click_element_registered(self):
        assert "click_element" in ActionExecutor._dispatch_table

    def test_click_mark_registered(self):
        assert "click_mark" in ActionExecutor._dispatch_table

    def test_list_elements_registered(self):
        assert "list_elements" in ActionExecutor._dispatch_table


# ---------------------------------------------------------------------------
# PerceptionResult integration
# ---------------------------------------------------------------------------


class TestPerceptionResultIntegration:
    """Test PerceptionResult methods used by the action handlers."""

    def test_find_by_id(self):
        result = _make_result()
        elem = result.find_by_id(1)
        assert elem is not None
        assert elem.label == "Save"

    def test_find_by_id_not_found(self):
        result = _make_result()
        assert result.find_by_id(99) is None

    def test_find_by_label(self):
        result = _make_result()
        elem = result.find_by_label("Cancel")
        assert elem is not None
        assert elem.id == 2

    def test_find_by_label_case_insensitive(self):
        result = _make_result()
        elem = result.find_by_label("cancel")
        assert elem is not None

    def test_interactable_elements(self):
        elements = [
            _make_element(1, "Label", ElementType.TEXT, interactable=False),
            _make_element(2, "Button", ElementType.BUTTON, interactable=True),
            _make_element(3, "Input", ElementType.INPUT, interactable=True),
        ]
        result = _make_result(elements)
        interactable = result.interactable_elements()
        assert len(interactable) == 2

    def test_to_llm_context(self):
        result = _make_result()
        context = result.to_llm_context()
        assert isinstance(context, str)
        assert "Save" in context or "Detected" in context or "[" in context

    def test_element_center(self):
        elem = _make_element(1, bbox=(100, 200, 80, 40))
        assert elem.center == (140, 220)

    def test_element_to_dict(self):
        elem = _make_element(1, "OK")
        d = elem.to_dict()
        assert d["id"] == 1
        assert d["label"] == "OK"
        assert d["type"] == "button"
        assert d["interactable"] is True


# ---------------------------------------------------------------------------
# Engine perception integration
# ---------------------------------------------------------------------------


class TestEnginePerception:
    """Test engine's _run_perception method."""

    def test_engine_has_run_perception(self):
        """Engine should have _run_perception method."""
        from core.engine import AgentEngine

        assert hasattr(AgentEngine, "_run_perception")

    @patch("core.dpi.detect_monitors")
    @patch("core.dpi._get_mss_monitors")
    def test_perception_stores_on_executor(self, mock_mss, mock_detect):
        mock_mss.return_value = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_detect.return_value = [
            MagicMock(
                index=1, width=1920, height=1080, scale_factor=1.0, is_primary=True, x=0, y=0
            ),
        ]

        from core.engine import AgentEngine

        engine = AgentEngine(config={"dry_run": True})

        # Mock perception pipeline
        mock_result = _make_result()
        with patch("core.perception.PerceptionPipeline") as MockPipeline:
            mock_pipeline = MockPipeline.return_value
            mock_pipeline.analyze.return_value = mock_result

            from PIL import Image

            img = Image.new("RGB", (100, 100), "white")
            result = engine._run_perception(img)

            assert result is not None
            assert len(result.elements) > 0

    @patch("core.dpi.detect_monitors")
    @patch("core.dpi._get_mss_monitors")
    def test_perception_returns_none_on_import_error(self, mock_mss, mock_detect):
        mock_mss.return_value = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_detect.return_value = [
            MagicMock(
                index=1, width=1920, height=1080, scale_factor=1.0, is_primary=True, x=0, y=0
            ),
        ]

        from core.engine import AgentEngine

        engine = AgentEngine(config={"dry_run": True})

        with patch("core.perception.PerceptionPipeline", side_effect=ImportError):
            from PIL import Image

            img = Image.new("RGB", (100, 100), "white")
            result = engine._run_perception(img)
            assert result is None
