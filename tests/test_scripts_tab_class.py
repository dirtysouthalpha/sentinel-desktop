"""Tests for gui/tabs/scripts_tab.py — ScriptsTab class internals.

Constructs the tab against the headless customtkinter stub (conftest) with a
fake ``app`` exposing a ``_t`` theme accessor and a ``cfg`` dict, and patches
the script engine / threads so disk + execution paths are deterministic.

Complements ``test_scripts_tab.py`` (helper-level tests) by exercising the
detail panel, parameter-field builder, run worker, progress callback, recorder
hook, and output helper.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import customtkinter as ctk

import gui.tabs.scripts_tab as st
from gui.tabs.scripts_tab import ScriptsTab


def _theme(key=None, default=None):
    return default


def _make_app(tmp_path=None):
    app = MagicMock()
    app._t = _theme
    app.cfg = {"script_base": str(tmp_path) if tmp_path is not None else "."}
    return app


def _make_tab(tmp_path=None):
    """Build a ScriptsTab against an empty script base (no JSON found)."""
    app = _make_app(tmp_path)
    tab = ScriptsTab(ctk.CTkFrame(), app)
    return tab, app


class _SyncThread:
    """threading.Thread stand-in that runs the target synchronously on start()."""

    def __init__(self, target=None, daemon=None, **kw):
        self._target = target

    def start(self):
        if self._target:
            self._target()


def _sync_after(app):
    """Make app.root.after(delay, cb) execute cb immediately."""
    app.root.after = lambda delay, cb=None: (cb() if cb else None)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
class TestConstruction:
    def test_builds_with_empty_base(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        assert tab._scripts == []
        assert tab._selected_script is None
        assert tab._active_category == "All"


# ---------------------------------------------------------------------------
# _populate_list (cleanup + card creation)
# ---------------------------------------------------------------------------
class TestPopulateList:
    def test_destroys_existing_children_then_builds_cards(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        child = MagicMock()
        tab._list_frame = MagicMock()
        tab._list_frame.winfo_children.return_value = [child]
        scripts = [
            {
                "name": "Alpha",
                "description": "x" * 80,  # >60 chars -> truncation branch
                "steps": [{"a": 1}, {"a": 2}],
                "icon": "🔧",
                "_path": "/a.json",
            },
            {"_path": "/b.json"},  # all defaults: Untitled, 1 step path
        ]
        tab._populate_list(scripts)
        child.destroy.assert_called_once()

    def test_card_click_binding_invokes_select(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab.select_script = MagicMock()
        bound = []

        class _Widget:
            """Plain widget stub (avoids MagicMock spec-of-a-mock errors)."""

            def __init__(self, *a, **kw):
                pass

            def pack(self, *a, **kw):
                pass

            def pack_propagate(self, *a, **kw):
                pass

            def grid(self, *a, **kw):
                pass

            def grid_columnconfigure(self, *a, **kw):
                pass

            def winfo_children(self):
                return []

            def bind(self, _evt, cb):
                bound.append(cb)

        with (
            patch.object(st.ctk, "CTkFrame", _Widget),
            patch.object(st.ctk, "CTkLabel", _Widget),
        ):
            tab._list_frame = _Widget()
            tab._populate_list([{"name": "One", "_path": "/one.json"}])
        # Fire one of the bound click handlers; it should route to select_script.
        assert bound
        bound[0](None)
        tab.select_script.assert_called_with("/one.json")


# ---------------------------------------------------------------------------
# select_script + date parsing
# ---------------------------------------------------------------------------
class TestSelectScript:
    def test_select_parses_iso_date(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._scripts = [
            {
                "_path": "/x.json",
                "name": "Dated",
                "description": "d",
                "steps": [{"a": 1}],
                "author": "bob",
                "created": "2024-01-02T03:04:05",
                "parameters": [],
            }
        ]
        tab._meta_label = MagicMock()
        tab.select_script("/x.json")
        assert tab._selected_path == "/x.json"
        meta = tab._meta_label.configure.call_args.kwargs["text"]
        assert "2024-01-02" in meta
        assert "bob" in meta

    def test_select_bad_date_kept_as_is(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._scripts = [
            {"_path": "/y.json", "name": "BadDate", "created": "not-a-date"}
        ]
        tab._meta_label = MagicMock()
        tab.select_script("/y.json")
        meta = tab._meta_label.configure.call_args.kwargs["text"]
        assert "not-a-date" in meta

    def test_select_not_found_is_noop(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._scripts = []
        tab.select_script("/missing.json")
        assert tab._selected_script is None


# ---------------------------------------------------------------------------
# _build_param_fields
# ---------------------------------------------------------------------------
class TestBuildParamFields:
    def test_no_params_sets_none_label_and_clears(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._params_label = MagicMock()
        tab._params_frame = MagicMock()
        tab._params_frame.winfo_children.return_value = []
        tab._param_entries = {"old": MagicMock()}
        tab._build_param_fields({"parameters": []})
        tab._params_label.configure.assert_called_with(text="Parameters  (none)")
        assert tab._param_entries == {}

    def test_builds_entries_with_defaults_and_required(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._params_label = MagicMock()
        child = MagicMock()
        tab._params_frame = MagicMock()
        tab._params_frame.winfo_children.return_value = [child]

        captured_entries = []

        class _Entry(MagicMock):
            def __init__(self, *a, **kw):
                super().__init__()
                captured_entries.append(self)

        with patch.object(st.ctk, "CTkEntry", _Entry), patch.object(st.ctk, "CTkLabel", MagicMock()):
            tab._build_param_fields(
                {
                    "parameters": [
                        {"name": "user", "label": "User", "required": True, "default": "admin"},
                        {"name": "host", "description": "hostname"},  # no default, no label
                        {"required": True},  # no name -> param_2 fallback
                    ]
                }
            )
        child.destroy.assert_called_once()
        tab._params_label.configure.assert_called_with(text="Parameters  (3)")
        assert set(tab._param_entries) == {"user", "host", "param_2"}
        # The first entry had a default -> insert called.
        assert captured_entries[0].insert.called


# ---------------------------------------------------------------------------
# run_selected_script
# ---------------------------------------------------------------------------
class TestRunSelectedScript:
    def test_no_selection_warns(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._selected_script = None
        tab._selected_path = None
        tab._append_output = MagicMock()
        tab.run_selected_script()
        tab._append_output.assert_called_once()
        assert "No script selected" in tab._append_output.call_args[0][0]

    def _setup_running(self, tab, app):
        tab._selected_script = {"name": "Demo"}
        tab._selected_path = "/demo.json"
        tab._append_output = MagicMock()
        tab._run_btn = MagicMock()
        e = MagicMock()
        e.get.return_value = "  val  "
        tab._param_entries = {"p": e}
        _sync_after(app)

    def test_success_path_reports_steps(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        self._setup_running(tab, app)
        result = SimpleNamespace(
            success=True,
            steps_completed=2,
            steps_total=2,
            duration_ms=42,
            error="",
            results=[{"success": True, "output": "ok"}, {"success": False, "error": "bad"}],
        )
        engine = MagicMock()
        engine.run_script.return_value = result
        fake_ae = SimpleNamespace(ActionExecutor=MagicMock())
        fake_se = SimpleNamespace(ScriptEngine=MagicMock(return_value=engine))
        with (
            patch.object(st, "threading", SimpleNamespace(Thread=_SyncThread)),
            patch.dict(
                "sys.modules",
                {"core.action_executor": fake_ae, "core.script_engine": fake_se},
            ),
        ):
            tab.run_selected_script()
        # Stripped param value was passed through.
        assert engine.run_script.call_args[0][1] == {"p": "val"}
        engine.set_progress_callback.assert_called_once_with(tab._on_script_progress)
        joined = "".join(c.args[0] for c in tab._append_output.call_args_list)
        assert "Completed" in joined
        assert "Step 1" in joined and "Step 2" in joined
        # Button re-enabled via after().
        tab._run_btn.configure.assert_any_call(state="normal", text="▶ Run Script")

    def test_failure_path_reports_error(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        self._setup_running(tab, app)
        result = SimpleNamespace(
            success=False,
            steps_completed=0,
            steps_total=1,
            duration_ms=5,
            error="kaboom",
            results=[],
        )
        engine = MagicMock()
        engine.run_script.return_value = result
        fake_ae = SimpleNamespace(ActionExecutor=MagicMock())
        fake_se = SimpleNamespace(ScriptEngine=MagicMock(return_value=engine))
        with (
            patch.object(st, "threading", SimpleNamespace(Thread=_SyncThread)),
            patch.dict(
                "sys.modules",
                {"core.action_executor": fake_ae, "core.script_engine": fake_se},
            ),
        ):
            tab.run_selected_script()
        joined = "".join(c.args[0] for c in tab._append_output.call_args_list)
        assert "Failed" in joined
        assert "kaboom" in joined

    def test_exception_in_worker_is_caught(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        self._setup_running(tab, app)
        # ScriptEngine raises a ValueError when run.
        engine = MagicMock()
        engine.run_script.side_effect = ValueError("explode")
        fake_ae = SimpleNamespace(ActionExecutor=MagicMock())
        fake_se = SimpleNamespace(ScriptEngine=MagicMock(return_value=engine))
        with (
            patch.object(st, "threading", SimpleNamespace(Thread=_SyncThread)),
            patch.dict(
                "sys.modules",
                {"core.action_executor": fake_ae, "core.script_engine": fake_se},
            ),
        ):
            tab.run_selected_script()
        joined = "".join(c.args[0] for c in tab._append_output.call_args_list)
        assert "Exception" in joined
        assert "explode" in joined
        # finally-block still re-enabled the button.
        tab._run_btn.configure.assert_any_call(state="normal", text="▶ Run Script")


# ---------------------------------------------------------------------------
# _on_script_progress
# ---------------------------------------------------------------------------
class TestProgressCallback:
    def test_progress_success(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._append_output = MagicMock()
        _sync_after(app)
        tab._on_script_progress(1, 3, "click", {"success": True, "output": "done"})
        out = tab._append_output.call_args[0][0]
        assert "Step 1/3" in out
        assert "✓" in out
        assert "done" in out

    def test_progress_failure_uses_error(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._append_output = MagicMock()
        _sync_after(app)
        tab._on_script_progress(2, 2, "type", {"success": False, "error": "nope"})
        out = tab._append_output.call_args[0][0]
        assert "✗" in out
        assert "nope" in out


# ---------------------------------------------------------------------------
# _open_recorder
# ---------------------------------------------------------------------------
class TestOpenRecorder:
    def test_uses_recorder_panel_when_present(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._append_output = MagicMock()
        app.recorder_panel = MagicMock()
        tab._open_recorder()
        app.recorder_panel.start_recording.assert_called_once()

    def test_no_recorder_panel_appends_message(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._append_output = MagicMock()
        app.recorder_panel = None
        tab._open_recorder()
        assert "Recording started" in tab._append_output.call_args[0][0]

    def test_recorder_error_is_caught(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._append_output = MagicMock()
        app.recorder_panel = MagicMock()
        app.recorder_panel.start_recording.side_effect = RuntimeError("boom")
        tab._open_recorder()
        assert "Could not start recorder" in tab._append_output.call_args[0][0]


# ---------------------------------------------------------------------------
# _append_output
# ---------------------------------------------------------------------------
class TestAppendOutput:
    def test_writes_to_output_box(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._output_box = MagicMock()
        _sync_after(app)
        tab._append_output("hello")
        tab._output_box.insert.assert_called_once_with("end", "hello\n")
        tab._output_box.see.assert_called_once_with("end")
        # state toggled normal -> disabled around the write.
        assert tab._output_box.configure.call_args_list[0].kwargs == {"state": "normal"}
        assert tab._output_box.configure.call_args_list[-1].kwargs == {"state": "disabled"}

    def test_runtime_error_from_after_is_swallowed(self, tmp_path):
        tab, app = _make_tab(tmp_path)
        tab._output_box = MagicMock()
        app.root.after = MagicMock(side_effect=RuntimeError("no loop"))
        # Must not raise.
        tab._append_output("x")


# ---------------------------------------------------------------------------
# refresh_scripts (disk scanning) + filter interplay
# ---------------------------------------------------------------------------
class TestRefreshScripts:
    def test_scans_and_skips_bad_json(self, tmp_path):
        sdir = tmp_path / "scripts" / "it_support"
        sdir.mkdir(parents=True)
        (sdir / "good.json").write_text(
            json.dumps({"name": "Good", "description": "ok", "steps": []})
        )
        (sdir / "bad.json").write_text("{{{nope")
        tab, _ = _make_tab(tmp_path)  # construction calls refresh_scripts
        names = [s["name"] for s in tab._scripts]
        assert names == ["Good"]
        assert tab._scripts[0]["_folder"] == "scripts/it_support"

    def test_category_filter_then_search(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._scripts = [
            {"name": "Install Office", "description": "MS", "_folder": "scripts/it_support"},
            {"name": "Custom Thing", "description": "x", "_folder": "scripts/custom"},
        ]
        tab._populate_list = MagicMock()
        tab._count_label = MagicMock()
        tab._set_category("IT Support")
        filtered = tab._populate_list.call_args[0][0]
        assert [s["name"] for s in filtered] == ["Install Office"]
        # count label uses singular form for 1.
        assert tab._count_label.configure.call_args.kwargs["text"] == "1 script"

    def test_search_query_excludes_non_matching(self, tmp_path):
        tab, _ = _make_tab(tmp_path)
        tab._scripts = [
            {"name": "Install Office", "description": "MS Office"},
            {"name": "Reset Password", "description": "AD reset"},
        ]
        tab._search_var = MagicMock()
        tab._search_var.get.return_value = "password"
        tab._active_category = "All"
        tab._populate_list = MagicMock()
        tab._count_label = MagicMock()
        tab._apply_filter()
        filtered = tab._populate_list.call_args[0][0]
        # "Install Office" is excluded by the search query (hits the continue).
        assert [s["name"] for s in filtered] == ["Reset Password"]
