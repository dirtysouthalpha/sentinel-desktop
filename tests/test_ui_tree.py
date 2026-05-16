"""Tests for core.ui_tree — UIAutomation wrapper.

Since uiautomation is a Windows-only package, most tests work by
mocking the _have_uia guard and the internal _auto module reference.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core import ui_tree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    *,
    name: str = "",
    control_type: str = "TextControl",
    automation_id: str = "",
    class_name: str = "",
    left: int = 0,
    top: int = 0,
    right: int = 100,
    bottom: int = 50,
    is_enabled: bool = True,
    is_offscreen: bool = False,
    children: list | None = None,
) -> MagicMock:
    """Build a mock UIA node with realistic attributes."""
    node = MagicMock()
    node.Name = name
    node.ControlTypeName = control_type
    node.AutomationId = automation_id
    node.ClassName = class_name
    node.IsEnabled = is_enabled
    node.IsOffscreen = is_offscreen
    rect = MagicMock()
    rect.left = left
    rect.top = top
    rect.right = right
    rect.bottom = bottom
    node.BoundingRectangle = rect
    node.GetChildren.return_value = children or []
    return node


# ---------------------------------------------------------------------------
# list_controls
# ---------------------------------------------------------------------------


class TestListControls:
    def test_returns_empty_when_uia_unavailable(self):
        with patch.object(ui_tree, "_have_uia", return_value=False):
            assert ui_tree.list_controls() == []

    def test_returns_empty_when_no_root_window(self):
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=None),
        ):
            assert ui_tree.list_controls() == []

    def test_walks_single_node(self):
        node = _make_node(name="Button1", control_type="ButtonControl")
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=node),
        ):
            result = ui_tree.list_controls()
        assert len(result) == 1
        assert result[0]["name"] == "Button1"
        assert result[0]["control_type"] == "ButtonControl"
        assert result[0]["x"] == 0
        assert result[0]["y"] == 0
        assert result[0]["width"] == 100
        assert result[0]["height"] == 50

    def test_walks_nested_children(self):
        child1 = _make_node(name="Child1")
        child2 = _make_node(name="Child2")
        root = _make_node(name="Root", children=[child1, child2])
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=root),
        ):
            result = ui_tree.list_controls()
        assert len(result) == 3
        names = [r["name"] for r in result]
        assert names == ["Root", "Child1", "Child2"]

    def test_respects_max_results(self):
        root = _make_node(name="Root")
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=root),
        ):
            result = ui_tree.list_controls(max_results=1)
        assert len(result) == 1

    def test_respects_max_depth(self):
        grandchild = _make_node(name="Grandchild")
        child = _make_node(name="Child", children=[grandchild])
        root = _make_node(name="Root", children=[child])
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=root),
        ):
            result = ui_tree.list_controls(max_depth=1)
        names = [r["name"] for r in result]
        assert "Root" in names
        assert "Child" in names
        assert "Grandchild" not in names

    def test_handles_walk_exception_gracefully(self):
        node = MagicMock()
        node.BoundingRectangle = property(lambda s: (_ for _ in ()).throw(RuntimeError("fail")))
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=node),
        ):
            result = ui_tree.list_controls()
        assert result == []


# ---------------------------------------------------------------------------
# click_control
# ---------------------------------------------------------------------------


class TestClickControl:
    def test_returns_none_when_uia_unavailable(self):
        with patch.object(ui_tree, "_have_uia", return_value=False):
            assert ui_tree.click_control(name="btn") is None

    def test_returns_none_when_control_not_found(self):
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=None),
        ):
            assert ui_tree.click_control(name="missing") is None

    def test_clicks_via_invoke_pattern(self):
        ctrl = _make_node()
        ctrl.GetInvokePattern.return_value.Invoke.return_value = None
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.click_control(name="btn")
        assert result == (50, 25)

    def test_falls_back_to_selection_pattern(self):
        ctrl = _make_node()
        ctrl.GetInvokePattern.return_value = None
        sel = MagicMock()
        ctrl.GetSelectionItemPattern.return_value = sel
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.click_control(name="item")
        assert result == (50, 25)
        sel.Select.assert_called_once()

    def test_falls_back_to_physical_click(self):
        ctrl = _make_node()
        ctrl.GetInvokePattern.side_effect = AttributeError("no pattern")
        ctrl.GetSelectionItemPattern.side_effect = AttributeError("no pattern")
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.click_control(name="btn")
        assert result == (50, 25)
        ctrl.Click.assert_called_once_with(simulateMove=False)

    def test_right_click(self):
        ctrl = _make_node()
        ctrl.GetInvokePattern.return_value = None
        ctrl.GetSelectionItemPattern.return_value = None
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.click_control(name="btn", button="right")
        assert result == (50, 25)
        ctrl.RightClick.assert_called_once_with(simulateMove=False)

    def test_returns_none_on_click_failure(self):
        ctrl = _make_node()
        ctrl.BoundingRectangle = property(lambda s: (_ for _ in ()).throw(RuntimeError("fail")))
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.click_control(name="btn")
        assert result is None


# ---------------------------------------------------------------------------
# set_text
# ---------------------------------------------------------------------------


class TestSetText:
    def test_returns_false_when_uia_unavailable(self):
        with patch.object(ui_tree, "_have_uia", return_value=False):
            assert ui_tree.set_text("hello", name="field") is False

    def test_returns_false_when_control_not_found(self):
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=None),
        ):
            assert ui_tree.set_text("hello", name="missing") is False

    def test_sets_via_value_pattern(self):
        ctrl = _make_node()
        pattern = MagicMock()
        ctrl.GetValuePattern.return_value = pattern
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.set_text("hello", name="field")
        assert result is True
        pattern.SetValue.assert_called_once_with("hello")

    def test_falls_back_to_sendkeys(self):
        ctrl = _make_node()
        ctrl.GetValuePattern.side_effect = AttributeError("no pattern")
        mock_auto = MagicMock()
        with (
            patch.object(ui_tree, "_have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
            patch.object(ui_tree, "_auto", mock_auto),
        ):
            result = ui_tree.set_text("hello", name="field")
        assert result is True
        ctrl.SetFocus.assert_called_once()
        mock_auto.SendKeys.assert_called_once()


# ---------------------------------------------------------------------------
# _find_control internal
# ---------------------------------------------------------------------------


class TestFindControl:
    def test_returns_none_when_no_root(self):
        with patch.object(ui_tree, "_find_window", return_value=None):
            from core.ui_tree import _find_control

            assert _find_control(name="test") is None

    def test_finds_exact_name_match(self):
        child = _make_node(name="TargetButton")
        root = _make_node(name="Root", children=[child])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(name="TargetButton")
        assert result is child

    def test_finds_partial_name_match(self):
        child = _make_node(name="Submit Button")
        root = _make_node(name="Root", children=[child])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(name="submit")
        assert result is child

    def test_finds_by_automation_id(self):
        child = _make_node(automation_id="mainInput")
        root = _make_node(name="Root", children=[child])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(automation_id="mainInput")
        assert result is child

    def test_returns_none_when_no_match(self):
        child = _make_node(name="Other")
        root = _make_node(name="Root", children=[child])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            assert _find_control(name="NonExistent") is None

    def test_combines_name_and_type_filters(self):
        btn = _make_node(name="OK", control_type="ButtonControl")
        txt = _make_node(name="OK", control_type="TextControl")
        root = _make_node(name="Root", children=[btn, txt])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(name="OK", control_type="ButtonControl")
        assert result is btn


# ---------------------------------------------------------------------------
# _find_window internal
# ---------------------------------------------------------------------------


class TestFindWindow:
    def test_returns_none_when_auto_is_none(self):
        ui_tree._auto = None
        from core.ui_tree import _find_window

        assert _find_window("test") is None

    def test_returns_foreground_when_no_title(self):
        mock_auto = MagicMock()
        fg = MagicMock()
        mock_auto.GetForegroundControl.return_value = fg
        original = ui_tree._auto
        ui_tree._auto = mock_auto
        try:
            from core.ui_tree import _find_window

            result = _find_window(None)
            assert result is fg
        finally:
            ui_tree._auto = original

    def test_finds_window_by_partial_title(self):
        win = MagicMock()
        win.Name = "My App - Document"
        mock_auto = MagicMock()
        mock_auto.GetRootControl.return_value.GetChildren.return_value = [win]
        original = ui_tree._auto
        ui_tree._auto = mock_auto
        try:
            from core.ui_tree import _find_window

            result = _find_window("My App")
            assert result is win
        finally:
            ui_tree._auto = original

    def test_returns_none_when_title_not_matched(self):
        win = MagicMock()
        win.Name = "Other Window"
        mock_auto = MagicMock()
        mock_auto.GetRootControl.return_value.GetChildren.return_value = [win]
        original = ui_tree._auto
        ui_tree._auto = mock_auto
        try:
            from core.ui_tree import _find_window

            assert _find_window("Not Found") is None
        finally:
            ui_tree._auto = original
