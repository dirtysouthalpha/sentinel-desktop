"""Tests for gui/tabs/workflows_tab.py — WorkflowsTab class.

Constructs the tab against the headless customtkinter stub (conftest) with a
fake ``app`` exposing a ``_t`` theme accessor, and patches WorkflowEngine /
threads so disk + execution paths are deterministic.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gui.tabs.workflows_tab as wt
from gui.tabs.workflows_tab import WorkflowsTab


def _theme(key=None, default=None):
    return default


def _make_app():
    app = MagicMock()
    app._t = _theme
    return app


def _make_tab(workflows=None):
    app = _make_app()
    with patch.object(wt.WorkflowEngine, "list_workflows", return_value=workflows or []):
        tab = WorkflowsTab(MagicMock(), app)
    return tab, app


class _SyncThread:
    """threading.Thread stand-in that runs the target synchronously on start()."""

    def __init__(self, target=None, daemon=None, **kw):
        self._target = target

    def start(self):
        if self._target:
            self._target()


# ---------------------------------------------------------------------------
# Construction + refresh
# ---------------------------------------------------------------------------
class TestConstruction:
    def test_builds_with_no_workflows(self):
        tab, _ = _make_tab([])
        assert tab._workflows == []
        assert tab._selected_path is None

    def test_refresh_builds_cards_and_highlights_selection(self):
        workflows = [
            {"name": "Alpha", "description": "first", "steps": 1, "path": "/wf/a.json"},
            {"name": "Beta", "description": "second", "steps": 3, "path": "/wf/b.json"},
        ]
        tab, _ = _make_tab(workflows)
        tab._selected_path = "/wf/a.json"
        with patch.object(wt.WorkflowEngine, "list_workflows", return_value=workflows):
            tab.refresh_workflows()
        assert len(tab._workflows) == 2

    def test_refresh_filters_by_search_query(self):
        workflows = [
            {"name": "Alpha", "description": "x", "steps": 0, "path": "/wf/a.json"},
            {"name": "Beta", "description": "y", "steps": 1, "path": "/wf/b.json"},
        ]
        tab, _ = _make_tab(workflows)
        tab._search_var = MagicMock()
        tab._search_var.get.return_value = "alpha"
        with patch.object(wt.WorkflowEngine, "list_workflows", return_value=workflows):
            tab.refresh_workflows()  # only Alpha passes the filter — must not raise


# ---------------------------------------------------------------------------
# select_workflow
# ---------------------------------------------------------------------------
class TestSelectWorkflow:
    def test_loads_and_renders(self, tmp_path):
        wf_file = tmp_path / "wf.json"
        wf_file.write_text(
            json.dumps(
                {
                    "name": "Demo",
                    "description": "demo flow",
                    "steps": [
                        {
                            "id": "s1",
                            "type": "condition",
                            "check": "ok",
                            "true_next": "s2",
                            "false_next": "s3",
                        },
                        {"id": "s2", "type": "action", "action": {"action": "click"}},
                        {"id": "s3", "type": "delay", "delay_seconds": 2},
                    ],
                    "variables": {"user": "admin", "count": 3},
                }
            )
        )
        tab, _ = _make_tab([])
        with patch.object(wt.WorkflowEngine, "list_workflows", return_value=[]):
            tab.select_workflow(str(wf_file))
        assert tab._selected_path == str(wf_file)
        assert tab._workflow_data["name"] == "Demo"
        # Variables were rendered into entry widgets.
        assert set(tab._var_entries) == {"user", "count"}

    def test_renders_no_variables(self, tmp_path):
        wf_file = tmp_path / "wf.json"
        wf_file.write_text(json.dumps({"name": "Empty", "steps": [], "variables": {}}))
        tab, _ = _make_tab([])
        with patch.object(wt.WorkflowEngine, "list_workflows", return_value=[]):
            tab.select_workflow(str(wf_file))
        assert tab._workflow_data["name"] == "Empty"

    def test_bad_json_shows_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        tab, _ = _make_tab([])
        tab._name_label = MagicMock()
        tab._desc_label = MagicMock()
        tab.select_workflow(str(bad))
        tab._name_label.configure.assert_called_with(text="Error loading workflow")

    def test_missing_file_shows_error(self):
        tab, _ = _make_tab([])
        tab._name_label = MagicMock()
        tab._desc_label = MagicMock()
        tab.select_workflow("/no/such/workflow.json")
        tab._name_label.configure.assert_called_with(text="Error loading workflow")


# ---------------------------------------------------------------------------
# Variable collection
# ---------------------------------------------------------------------------
class TestVariables:
    def test_collect_variables_reads_entries(self):
        tab, _ = _make_tab([])
        e1, e2 = MagicMock(), MagicMock()
        e1.get.return_value = "v1"
        e2.get.return_value = "v2"
        tab._var_entries = {"a": e1, "b": e2}
        assert tab._collect_variables() == {"a": "v1", "b": "v2"}

    def test_collect_variables_without_entries(self):
        tab, _ = _make_tab([])
        # No _var_entries attribute set yet -> getattr default {}.
        if hasattr(tab, "_var_entries"):
            del tab._var_entries
        assert tab._collect_variables() == {}


# ---------------------------------------------------------------------------
# run_selected_workflow / _finish_run
# ---------------------------------------------------------------------------
class TestRun:
    def test_noop_when_already_running(self):
        tab, _ = _make_tab([])
        tab._running = True
        tab._append_output = MagicMock()
        tab.run_selected_workflow()
        tab._append_output.assert_not_called()

    def test_warns_when_nothing_selected(self):
        tab, _ = _make_tab([])
        tab._selected_path = None
        tab._workflow_data = None
        tab._append_output = MagicMock()
        tab.run_selected_workflow()
        tab._append_output.assert_called_once()

    def test_runs_workflow_and_reports(self):
        tab, _ = _make_tab([])
        tab._selected_path = "/wf/a.json"
        tab._workflow_data = {"name": "A"}
        tab._append_output = MagicMock()
        # after() runs callbacks immediately for deterministic output.
        tab.after = lambda delay, cb: cb()

        result = SimpleNamespace(
            success=True,
            steps_completed=2,
            steps_total=2,
            elapsed_seconds=1.5,
            error="",
            step_results=[{"success": True}, {"success": False}],
        )
        fake_engine = MagicMock()
        fake_engine.run_workflow.return_value = result
        with (
            patch.object(wt, "threading", SimpleNamespace(Thread=_SyncThread)),
            patch.object(wt, "WorkflowEngine", return_value=fake_engine),
        ):
            tab.run_selected_workflow()

        fake_engine.run_workflow.assert_called_once()
        assert tab._running is False  # _finish_run ran via after()
        assert tab._append_output.call_count >= 2

    def test_run_reports_error_field(self):
        tab, _ = _make_tab([])
        tab._selected_path = "/wf/a.json"
        tab._workflow_data = {"name": "A"}
        tab._append_output = MagicMock()
        tab.after = lambda delay, cb: cb()
        result = SimpleNamespace(
            success=False,
            steps_completed=0,
            steps_total=1,
            elapsed_seconds=0.2,
            error="kaboom",
            step_results=[],
        )
        fake_engine = MagicMock()
        fake_engine.run_workflow.return_value = result
        with (
            patch.object(wt, "threading", SimpleNamespace(Thread=_SyncThread)),
            patch.object(wt, "WorkflowEngine", return_value=fake_engine),
        ):
            tab.run_selected_workflow()
        # The error line is included in the joined output.
        joined = "".join(c.args[0] for c in tab._append_output.call_args_list)
        assert "kaboom" in joined

    def test_finish_run_resets_state(self):
        tab, _ = _make_tab([])
        tab._running = True
        tab._run_btn = MagicMock()
        tab._finish_run()
        assert tab._running is False
        tab._run_btn.configure.assert_called_once()


# ---------------------------------------------------------------------------
# _new_workflow + _append_output
# ---------------------------------------------------------------------------
class TestNewWorkflowAndOutput:
    def test_new_workflow_saves_and_selects(self, tmp_path):
        tab, _ = _make_tab([])
        tab.select_workflow = MagicMock()
        with (
            patch.object(wt, "WORKFLOWS_DIR", str(tmp_path)),
            patch.object(wt.WorkflowEngine, "save_workflow") as save,
            patch.object(wt.WorkflowEngine, "list_workflows", return_value=[]),
        ):
            tab._new_workflow()
        save.assert_called_once()
        tab.select_workflow.assert_called_once()

    def test_append_output_writes_text(self):
        tab, _ = _make_tab([])
        tab._output_text = MagicMock()
        tab._append_output("hello\n")
        tab._output_text.insert.assert_called_once_with("end", "hello\n")
        tab._output_text.see.assert_called_once_with("end")


# ---------------------------------------------------------------------------
# Existing-children cleanup branches
# ---------------------------------------------------------------------------
class TestChildCleanup:
    def test_refresh_destroys_existing_cards(self):
        tab, _ = _make_tab([])
        child = MagicMock()
        tab._list_container = MagicMock()
        tab._list_container.winfo_children.return_value = [child]
        with patch.object(wt.WorkflowEngine, "list_workflows", return_value=[]):
            tab.refresh_workflows()
        child.destroy.assert_called_once()

    def test_render_steps_destroys_existing(self):
        tab, _ = _make_tab([])
        child = MagicMock()
        tab._steps_frame = MagicMock()
        tab._steps_frame.winfo_children.return_value = [child]
        tab._render_steps([])
        child.destroy.assert_called_once()

    def test_render_variables_destroys_existing(self):
        tab, _ = _make_tab([])
        child = MagicMock()
        tab._vars_frame = MagicMock()
        tab._vars_frame.winfo_children.return_value = [child]
        tab._render_variables({})
        child.destroy.assert_called_once()
