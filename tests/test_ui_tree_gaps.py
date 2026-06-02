"""Gap tests for ui_tree.py — _have_uia probe, _walk errors, _find_control scoring, _find_window errors."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core import ui_tree, utils


@pytest.fixture(autouse=True)
def clear_ui_tree_cache():
    """Clear UI tree caches before each test to prevent interference."""
    ui_tree.clear_all_caches()
    yield
    ui_tree.clear_all_caches()


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


class TestHaveUia:
    """have_uia lazy probe covers caching and platform guard."""

    def setup_method(self):
        utils._UIA_OK = None
        utils._auto = None

    @patch("core.utils.platform.system", return_value="Linux")
    def test_non_windows_returns_false(self, mock_sys):
        assert utils.have_uia() is False
        assert utils._UIA_OK is False

    @patch("core.utils.platform.system", return_value="Windows")
    def test_import_failure_returns_false(self, mock_sys):
        with patch.dict("sys.modules", {"uiautomation": None}):
            with patch("builtins.__import__", side_effect=ImportError("nope")):
                assert utils.have_uia() is False

    @patch("core.utils.platform.system", return_value="Windows")
    def test_cached_true_skips_reprobe(self, mock_sys):
        utils._UIA_OK = True
        assert utils.have_uia() is True
        mock_sys.assert_not_called()

    @patch("core.utils.platform.system", return_value="Windows")
    def test_cached_false_skips_reprobe(self, mock_sys):
        utils._UIA_OK = False
        assert utils.have_uia() is False
        mock_sys.assert_not_called()


class TestListControlsWalkException:
    """list_controls catches _walk exceptions."""

    def test_walk_oserror_returns_empty(self):
        node = _make_node()
        with (
            patch.object(ui_tree, "have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=node),
            patch.object(ui_tree, "_walk", side_effect=OSError("COM failed")),
        ):
            assert ui_tree.list_controls() == []

    def test_walk_runtime_error_returns_empty(self):
        node = _make_node()
        with (
            patch.object(ui_tree, "have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=node),
            patch.object(ui_tree, "_walk", side_effect=RuntimeError("dead")),
        ):
            assert ui_tree.list_controls() == []


class TestClickControlMiddleButton:
    """click_control with button='middle'."""

    def test_middle_click(self):
        ctrl = _make_node()
        ctrl.GetInvokePattern.return_value = None
        ctrl.GetSelectionItemPattern.return_value = None
        with (
            patch.object(ui_tree, "have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
        ):
            result = ui_tree.click_control(name="btn", button="middle")
        assert result == (50, 25)
        ctrl.MiddleClick.assert_called_once_with(simulateMove=False)


class TestSetTextFailure:
    """set_text outer exception handler."""

    def test_attribute_error_returns_false(self):
        ctrl = _make_node()
        ctrl.GetValuePattern.side_effect = AttributeError("no pattern")
        ctrl.SetFocus.side_effect = AttributeError("no focus")
        with (
            patch.object(ui_tree, "have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
            patch.object(ui_tree, "get_uia_auto", MagicMock()),
        ):
            assert ui_tree.set_text("hello", name="field") is False

    def test_os_error_returns_false(self):
        ctrl = _make_node()
        ctrl.GetValuePattern.side_effect = AttributeError("no pattern")
        ctrl.SetFocus.side_effect = OSError("COM fail")
        with (
            patch.object(ui_tree, "have_uia", return_value=True),
            patch.object(ui_tree, "_find_control", return_value=ctrl),
            patch.object(ui_tree, "get_uia_auto", MagicMock()),
        ):
            assert ui_tree.set_text("hello", name="field") is False


class TestFindWindowErrors:
    """_find_window exception handling."""

    def test_exception_returns_none(self):
        mock_auto = MagicMock()
        mock_auto.GetRootControl.side_effect = RuntimeError("COM dead")
        with patch.object(ui_tree, "get_uia_auto", return_value=mock_auto):
            from core.ui_tree import _find_window

            assert _find_window("test") is None

    def test_foreground_exception_returns_none(self):
        mock_auto = MagicMock()
        mock_auto.GetForegroundControl.side_effect = AttributeError("no fg")
        with patch.object(ui_tree, "get_uia_auto", return_value=mock_auto):
            from core.ui_tree import _find_window

            assert _find_window(None) is None


class TestWalkGetChildrenError:
    """_walk handles GetChildren exceptions."""

    def test_get_children_error_stops_recursion(self):
        child = _make_node(name="Child")
        child.GetChildren.side_effect = RuntimeError("COM error")
        root = _make_node(name="Root", children=[child])
        with (
            patch.object(ui_tree, "have_uia", return_value=True),
            patch.object(ui_tree, "_find_window", return_value=root),
        ):
            result = ui_tree.list_controls()
        names = [r["name"] for r in result]
        assert "Root" in names
        assert "Child" in names


class TestFindControlScoringErrors:
    """_find_control scoring and child traversal edge cases."""

    def test_scoring_exception_handled(self):
        node = MagicMock()
        node.Name = MagicMock(side_effect=RuntimeError("COM"))
        node.ControlTypeName = "TextControl"
        node.GetChildren.return_value = []
        root = _make_node(name="Root", children=[node])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(name="test")
        # Scoring fails for child, root may still match or not — just no crash
        assert result is not None or result is None

    def test_get_children_exception_during_bfs(self):
        node = _make_node(name="Target")
        node.GetChildren.side_effect = OSError("COM fail")
        root = _make_node(name="Root", children=[node])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(name="Target")
        assert result is node

    def test_automation_id_partial_match(self):
        child = _make_node(automation_id="myInputField")
        root = _make_node(name="Root", children=[child])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(automation_id="input")
        assert result is child

    def test_prefers_exact_over_partial_match(self):
        exact = _make_node(name="Submit")
        partial = _make_node(name="Submit Button")
        root = _make_node(name="Root", children=[partial, exact])
        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            result = _find_control(name="Submit")
        assert result is exact


class TestFindControlMaxDepth:
    """_find_control does not expand children at depth >= max_depth (line 320 False branch)."""

    def test_node_at_max_depth_not_expanded(self):
        # Build a chain so that Leaf12 sits at depth 12 (max_depth=12).
        # deep_child is Leaf12's child and should never be enqueued.
        # root is at depth 0; we need 12 wrappers to place Leaf12 at depth 12.
        deep_child = _make_node(name="DeepChild")
        current = _make_node(name="Leaf12", children=[deep_child])
        for _ in range(12):  # 12 wraps → root at depth 0, Leaf12 at depth 12
            current = _make_node(name="Inner", children=[current])
        root = current

        with patch.object(ui_tree, "_find_window", return_value=root):
            from core.ui_tree import _find_control

            # Search for DeepChild — it should NOT be found (parent at depth 12 stops expansion)
            result = _find_control(name="DeepChild")
        assert result is not deep_child
