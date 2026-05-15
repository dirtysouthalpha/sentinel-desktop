"""Tests for recorder.py internal helpers — _describe_step, _generate_name,
_finalise_steps, _compute_screenshot_hash, _summarise_result, _detect_parameters."""

from __future__ import annotations

import base64
import hashlib

from core.recorder import ActionRecorder

# ---------------------------------------------------------------------------
# _describe_step
# ---------------------------------------------------------------------------


class TestDescribeStep:
    def test_click_with_text(self) -> None:
        result = ActionRecorder._describe_step("click", {"text": "OK"}, "")
        assert result == "Click 'OK'"

    def test_click_with_label(self) -> None:
        result = ActionRecorder._describe_step("click", {"label": "Submit"}, "")
        assert result == "Click 'Submit'"

    def test_click_with_selector(self) -> None:
        result = ActionRecorder._describe_step("click", {"selector": "#btn"}, "")
        assert result == "Click '#btn'"

    def test_click_with_coordinates(self) -> None:
        result = ActionRecorder._describe_step("click", {"x": 100, "y": 200}, "")
        assert result == "Click at (100, 200)"

    def test_click_no_target(self) -> None:
        result = ActionRecorder._describe_step("click", {}, "")
        assert result == "Click"

    def test_double_click(self) -> None:
        result = ActionRecorder._describe_step("double_click", {"text": "File"}, "")
        assert result == "Double-click 'File'"

    def test_right_click(self) -> None:
        result = ActionRecorder._describe_step("right_click", {"x": 50, "y": 75}, "")
        assert result == "Right-click at (50, 75)"

    def test_type_text(self) -> None:
        result = ActionRecorder._describe_step("type", {"text": "hello world"}, "")
        assert result == "Type 'hello world'"

    def test_key_press(self) -> None:
        result = ActionRecorder._describe_step("key_press", {"key": "Enter"}, "")
        assert result == "Press 'Enter'"

    def test_scroll(self) -> None:
        result = ActionRecorder._describe_step("scroll", {"x": 10, "y": 20}, "")
        assert result == "Scroll at (10, 20)"

    def test_hover(self) -> None:
        result = ActionRecorder._describe_step("hover", {"text": "Menu"}, "")
        assert result == "Hover over 'Menu'"

    def test_drag(self) -> None:
        result = ActionRecorder._describe_step("drag", {"text": "Item"}, "")
        assert result == "Drag to 'Item'"

    def test_screenshot(self) -> None:
        result = ActionRecorder._describe_step("screenshot", {}, "")
        assert result == "Take screenshot"

    def test_wait(self) -> None:
        result = ActionRecorder._describe_step("wait", {}, "")
        assert result == "Wait"

    def test_navigate_with_url(self) -> None:
        result = ActionRecorder._describe_step("navigate", {"url": "https://example.com"}, "")
        assert result == "Navigate to 'https://example.com'"

    def test_select(self) -> None:
        result = ActionRecorder._describe_step("select", {"text": "Option A"}, "")
        assert result == "Select 'Option A'"

    def test_copy(self) -> None:
        result = ActionRecorder._describe_step("copy", {}, "")
        assert result == "Copy"

    def test_paste(self) -> None:
        result = ActionRecorder._describe_step("paste", {}, "")
        assert result == "Paste"

    def test_focus(self) -> None:
        result = ActionRecorder._describe_step("focus", {"text": "Input"}, "")
        assert result == "Focus on 'Input'"

    def test_unknown_action_uses_capitalized_name(self) -> None:
        result = ActionRecorder._describe_step("custom_action", {}, "")
        assert result == "Custom action"


# ---------------------------------------------------------------------------
# _describe_step_static
# ---------------------------------------------------------------------------


class TestDescribeStepStatic:
    def test_delegates_to_describe_step(self) -> None:
        result = ActionRecorder._describe_step_static("click", {"text": "Button"})
        assert result == "Click 'Button'"


# ---------------------------------------------------------------------------
# _generate_name
# ---------------------------------------------------------------------------


class TestGenerateName:
    def test_with_goal(self) -> None:
        result = ActionRecorder._generate_name("Open notepad and type hello")
        assert "open" in result
        assert "notepad" in result

    def test_with_empty_goal(self) -> None:
        result = ActionRecorder._generate_name("")
        assert result.startswith("script_")

    def test_with_none_like_goal(self) -> None:
        result = ActionRecorder._generate_name("")
        # Should produce a timestamped name
        assert len(result) > len("script_")

    def test_slugifies_special_chars(self) -> None:
        result = ActionRecorder._generate_name("Hello, World! Test: #1")
        assert " " not in result
        assert "," not in result
        assert "!" not in result

    def test_truncates_long_goal(self) -> None:
        long_goal = " ".join(f"word{i}" for i in range(20))
        result = ActionRecorder._generate_name(long_goal)
        parts = result.split("_")
        assert len(parts) <= 6


# ---------------------------------------------------------------------------
# _compute_screenshot_hash
# ---------------------------------------------------------------------------


class TestComputeScreenshotHash:
    def test_none_returns_empty(self) -> None:
        assert ActionRecorder._compute_screenshot_hash(None) == ""

    def test_bytes_input(self) -> None:
        data = b"test screenshot data"
        result = ActionRecorder._compute_screenshot_hash(data)
        expected_digest = hashlib.md5(data, usedforsecurity=False).digest()
        expected = base64.b64encode(expected_digest).decode("ascii")[:8]
        assert result == expected

    def test_string_input(self) -> None:
        data = "test screenshot"
        result = ActionRecorder._compute_screenshot_hash(data)
        raw = data.encode("utf-8")
        expected_digest = hashlib.md5(raw, usedforsecurity=False).digest()
        expected = base64.b64encode(expected_digest).decode("ascii")[:8]
        assert result == expected

    def test_returns_8_chars(self) -> None:
        result = ActionRecorder._compute_screenshot_hash(b"data")
        assert len(result) == 8


# ---------------------------------------------------------------------------
# _summarise_result
# ---------------------------------------------------------------------------


class TestSummariseResult:
    def test_with_text_param(self) -> None:
        result = ActionRecorder._summarise_result("click", {"text": "Button"}, {"status": "ok"})
        assert "click" in result
        assert "Button" in result
        assert "ok" in result

    def test_with_label_param(self) -> None:
        result = ActionRecorder._summarise_result("click", {"label": "Submit"}, {"success": True})
        assert "Submit" in result

    def test_with_selector_param(self) -> None:
        result = ActionRecorder._summarise_result("click", {"selector": "#btn"}, {"status": "done"})
        assert "#btn" in result

    def test_without_element(self) -> None:
        result = ActionRecorder._summarise_result("scroll", {}, {"status": "done"})
        assert "scroll" in result
        assert "done" in result

    def test_default_status(self) -> None:
        result = ActionRecorder._summarise_result("click", {}, {})
        assert "done" in result


# ---------------------------------------------------------------------------
# _finalise_steps
# ---------------------------------------------------------------------------


class TestFinaliseSteps:
    def test_strips_internal_fields(self) -> None:
        steps = [
            {
                "action": "click",
                "params": {"x": 10},
                "description": "Click",
                "wait_after_ms": 300,
                "screenshot_hash": "abc12345",
                "internal_field": "should be removed",
                "debug_info": "also removed",
            }
        ]
        result = ActionRecorder._finalise_steps(steps)
        assert len(result) == 1
        assert set(result[0].keys()) == {
            "action",
            "params",
            "description",
            "wait_after_ms",
            "screenshot_hash",
        }

    def test_defaults_for_missing_fields(self) -> None:
        steps = [{"action": "type"}]
        result = ActionRecorder._finalise_steps(steps)
        assert result[0]["params"] == {}
        assert result[0]["description"] == ""
        assert result[0]["wait_after_ms"] == 500
        assert result[0]["screenshot_hash"] == ""

    def test_empty_list(self) -> None:
        assert ActionRecorder._finalise_steps([]) == []

    def test_does_not_mutate_original(self) -> None:
        steps = [
            {
                "action": "click",
                "params": {"x": 1},
                "extra": "data",
            }
        ]
        ActionRecorder._finalise_steps(steps)
        assert "extra" in steps[0]


# ---------------------------------------------------------------------------
# _detect_parameters
# ---------------------------------------------------------------------------


class TestDetectParameters:
    def test_detects_repeated_value(self) -> None:
        steps = [
            {"params": {"text": "repeated_val"}},
            {"params": {"text": "repeated_val"}},
            {"params": {"text": "repeated_val"}},
        ]
        params = ActionRecorder._detect_parameters(steps)
        assert len(params) >= 1
        assert params[0]["type"] == "string"
        assert params[0]["default"] == "repeated_val"

    def test_ignores_single_occurrence(self) -> None:
        steps = [
            {"params": {"text": "unique"}},
            {"params": {"text": "different"}},
        ]
        params = ActionRecorder._detect_parameters(steps)
        assert len(params) == 0

    def test_ignores_short_strings(self) -> None:
        steps = [
            {"params": {"text": "a"}},
            {"params": {"text": "a"}},
        ]
        params = ActionRecorder._detect_parameters(steps)
        assert len(params) == 0

    def test_ignores_non_string_values(self) -> None:
        steps = [
            {"params": {"x": 100}},
            {"params": {"x": 100}},
        ]
        params = ActionRecorder._detect_parameters(steps)
        assert len(params) == 0

    def test_empty_steps(self) -> None:
        assert ActionRecorder._detect_parameters([]) == []

    def test_steps_without_params(self) -> None:
        steps = [{"action": "click"}, {"action": "type"}]
        params = ActionRecorder._detect_parameters(steps)
        assert len(params) == 0
