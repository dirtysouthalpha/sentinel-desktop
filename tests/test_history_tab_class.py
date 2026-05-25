"""Tests for gui/tabs/history_tab.py — HistoryTab class via real construction.

Builds the tab through its real ``__init__`` against the headless customtkinter
stub (conftest) so the ``_build_left`` / ``_build_right`` widget-construction
paths and the data-rendering branches are exercised.  The fake ``app`` exposes a
``_t`` theme accessor returning the supplied fallback, mirroring the live HUD.

history_tab.py uses only ``customtkinter`` (no ``tkinter``/``TclError``), so the
cross-module ``sys.modules['tkinter']`` pollution pitfall does not apply here;
construction order is therefore irrelevant for these tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import gui.tabs.history_tab as ht
from gui.tabs.history_tab import HistoryTab


def _theme(key=None, default="#ffffff"):
    return default


def _make_app(forensic_log=None, notes=None, with_engine=True):
    app = MagicMock()
    app._t = _theme
    if with_engine:
        app.engine = MagicMock()
        app.engine.forensic_log = forensic_log if forensic_log is not None else []
        app.engine.notes = notes if notes is not None else []
    else:
        app.engine = None
    return app


def _make_tab(forensic_log=None, notes=None, with_engine=True):
    """Construct a HistoryTab through its real __init__ (covers build paths)."""
    app = _make_app(forensic_log=forensic_log, notes=notes, with_engine=with_engine)
    tab = HistoryTab(MagicMock(), app)
    return tab, app


class _FakeChildren:
    """Frame stand-in whose winfo_children() returns destroyable children."""

    def __init__(self, children):
        self._children = children

    def winfo_children(self):
        return self._children

    def __getattr__(self, _name):
        # any other widget call (grid/pack/etc.) is a no-op
        return lambda *a, **kw: None


# ---------------------------------------------------------------------------
# Construction (covers __init__, _build_left, _build_right, initial refresh)
# ---------------------------------------------------------------------------
class TestConstruction:
    def test_builds_with_empty_engine(self):
        tab, _ = _make_tab(with_engine=False)
        # refresh_history ran during construction -> at least the placeholder.
        assert tab.sessions
        assert tab.sessions[0]["status"] == "empty"
        assert tab.selected_index == -1

    def test_builds_with_engine_and_log(self):
        now = datetime.now().isoformat()
        log = [
            {"step": {"action": "start"}, "ok": True, "timestamp": now, "goal": "Do thing"},
            {"step": {"action": "click"}, "ok": True, "timestamp": now, "goal": "Do thing"},
            {"step": {"action": "finish", "summary": "ok"}, "ok": True, "timestamp": now},
        ]
        tab, _ = _make_tab(forensic_log=log)
        assert tab.sessions
        assert tab.sessions[0]["status"] == "completed"

    def test_t_falls_back_when_app_lacks_accessor(self):
        tab, _ = _make_tab(with_engine=False)
        plain = object()  # no _t attribute
        tab.app = plain
        assert tab._t("anything", "DEFAULT") == "DEFAULT"


# ---------------------------------------------------------------------------
# refresh_history grouping branches
# ---------------------------------------------------------------------------
class TestRefreshHistory:
    def test_goal_change_flushes_previous_session(self):
        now = datetime.now().isoformat()
        log = [
            {"step": {"action": "click"}, "ok": True, "timestamp": now, "goal": "Goal A"},
            {"step": {"action": "click"}, "ok": True, "timestamp": now, "goal": "Goal A"},
            # goal change -> flush previous (covers line 176)
            {"step": {"action": "click"}, "ok": False, "timestamp": now, "goal": "Goal B"},
        ]
        tab, _ = _make_tab(forensic_log=log)
        tab.refresh_history()
        goals = [s["goal"] for s in tab.sessions]
        assert "Goal A" in goals
        assert "Goal B" in goals

    def test_session_with_no_goal_uses_first_step_goal(self):
        # No goal on entries, no "start"/"finish" -> finalize derives fields.
        now = datetime.now().isoformat()
        log = [
            {"step": {"action": "click"}, "ok": True, "timestamp": now},
        ]
        tab, _ = _make_tab(forensic_log=log)
        tab.refresh_history()
        assert tab.sessions[0]["status"] == "completed"

    def test_notes_only_branch(self):
        tab, _ = _make_tab(forensic_log=[], notes=["alpha", "beta"])
        tab.refresh_history()
        assert any("notes" in s for s in tab.sessions)


# ---------------------------------------------------------------------------
# _apply_filter
# ---------------------------------------------------------------------------
class TestApplyFilter:
    def test_filter_today(self):
        tab, _ = _make_tab(with_engine=False)
        today = datetime.now().isoformat()
        old = (datetime.now() - timedelta(days=3)).isoformat()
        tab.sessions = [
            {"goal": "t", "status": "completed", "start": today},
            {"goal": "o", "status": "completed", "start": old},
        ]
        tab.filter_var = MagicMock()
        tab.filter_var.get.return_value = "Today"
        tab._apply_filter()
        assert [s["goal"] for s in tab.sessions] == ["t"]

    def test_filter_this_week(self):
        tab, _ = _make_tab(with_engine=False)
        recent = (datetime.now() - timedelta(days=1)).isoformat()
        old = (datetime.now() - timedelta(days=30)).isoformat()
        tab.sessions = [
            {"goal": "r", "status": "completed", "start": recent},
            {"goal": "o", "status": "completed", "start": old},
        ]
        tab.filter_var = MagicMock()
        tab.filter_var.get.return_value = "This Week"
        tab._apply_filter()
        assert [s["goal"] for s in tab.sessions] == ["r"]

    def test_filter_failed(self):
        tab, _ = _make_tab(with_engine=False)
        tab.sessions = [
            {"goal": "a", "status": "completed", "start": ""},
            {"goal": "b", "status": "failed", "start": ""},
        ]
        tab.filter_var = MagicMock()
        tab.filter_var.get.return_value = "Failed"
        tab._apply_filter()
        assert [s["goal"] for s in tab.sessions] == ["b"]


# ---------------------------------------------------------------------------
# _render_sessions branches (destroy children, search skip, selection color)
# ---------------------------------------------------------------------------
class TestRenderSessions:
    def test_destroys_existing_children(self):
        tab, _ = _make_tab(with_engine=False)
        child = MagicMock()
        tab.session_list = _FakeChildren([child])
        tab.sessions = [{"goal": "x", "status": "completed", "steps": [], "start": ""}]
        tab._render_sessions()
        child.destroy.assert_called_once()

    def test_search_query_filters_out_nonmatching(self):
        tab, _ = _make_tab(with_engine=False)
        tab.sessions = [
            {"goal": "Alpha task", "status": "completed", "steps": [], "start": ""},
            {"goal": "Beta task", "status": "failed", "steps": [], "start": ""},
        ]
        tab.search_entry = MagicMock()
        tab.search_entry.get.return_value = "beta"  # only Beta matches -> Alpha skipped
        # must not raise; exercises the `continue` skip on line 252
        tab._render_sessions()

    def test_highlights_selected_index(self):
        tab, _ = _make_tab(with_engine=False)
        tab.selected_index = 0
        tab.sessions = [
            {"goal": "sel", "status": "running", "steps": [{}], "start": "2025-01-01T00:00:00"},
        ]
        tab._render_sessions()  # selected branch (accent color) — must not raise

    def test_unknown_status_icon(self):
        tab, _ = _make_tab(with_engine=False)
        tab.sessions = [
            {"goal": "mystery", "status": "weird", "steps": [], "start": ""},
        ]
        tab._render_sessions()  # status not in icon map -> "❓"


# ---------------------------------------------------------------------------
# select_session (timeline rendering, output summary/notes)
# ---------------------------------------------------------------------------
class TestSelectSession:
    def test_out_of_bounds_returns_early(self):
        tab, _ = _make_tab(with_engine=False)
        tab.sessions = [{"goal": "a"}]
        tab.select_session(5)
        assert tab.selected_index == 5  # set before the bounds check returns

    def test_negative_index_returns_early(self):
        tab, _ = _make_tab(with_engine=False)
        tab.sessions = [{"goal": "a"}]
        tab.select_session(-1)
        assert tab.selected_index == -1

    def test_renders_timeline_with_ok_and_failed_steps(self):
        tab, _ = _make_tab(with_engine=False)
        ts = "2025-01-01T12:30:45"
        tab.sessions = [
            {
                "goal": "Run",
                "status": "completed",
                "start": ts,
                "steps": [
                    {"step": {"action": "click"}, "ok": True, "timestamp": ts},
                    {"step": {"action": "type"}, "ok": False, "timestamp": ts},
                    # step_data with no nested "step" -> falls back to step_data itself
                    {"action": "scroll", "ok": True, "timestamp": ts},
                ],
                "summary": "all done",
                "notes": ["n1", "n2"],
            }
        ]
        tab.timeline = _FakeChildren([MagicMock()])
        tab.select_session(0)
        assert tab.selected_index == 0

    def test_renders_summary_and_notes_into_output(self):
        tab, _ = _make_tab(with_engine=False)
        tab.output_text = MagicMock()
        tab.sessions = [
            {
                "goal": "Run",
                "status": "completed",
                "start": "",
                "steps": [],
                "summary": "the summary",
                "notes": ["one", "two"],
            }
        ]
        tab.select_session(0)
        joined = "".join(c.args[1] for c in tab.output_text.insert.call_args_list)
        assert "the summary" in joined
        assert "one" in joined and "two" in joined

    def test_no_summary_no_notes(self):
        tab, _ = _make_tab(with_engine=False)
        tab.output_text = MagicMock()
        tab.sessions = [
            {"goal": "Run", "status": "empty", "start": "", "steps": []},
        ]
        tab.select_session(0)
        # No summary / notes -> insert never called for those branches.
        assert tab.selected_index == 0


# ---------------------------------------------------------------------------
# _replay_session
# ---------------------------------------------------------------------------
class TestReplaySession:
    def test_no_selection(self):
        tab, app = _make_tab(with_engine=False)
        tab.selected_index = -1
        tab._replay_session()
        app._on_run.assert_not_called()

    def test_valid_replay_invokes_on_run(self):
        tab, app = _make_tab(with_engine=False)
        tab.selected_index = 0
        tab.sessions = [{"goal": "replay this"}]
        app.goal_entry = MagicMock()
        tab._replay_session()
        app.goal_entry.delete.assert_called_once_with("1.0", "end")
        app.goal_entry.insert.assert_called_once_with("1.0", "replay this")
        app._on_run.assert_called_once()

    def test_replay_without_on_run_attr(self):
        tab, _ = _make_tab(with_engine=False)
        tab.selected_index = 0
        tab.sessions = [{"goal": "g"}]
        # app lacking _on_run -> hasattr False, no crash. Use a plain object.
        tab.app = type("A", (), {})()
        tab._replay_session()

    def test_replay_empty_goal(self):
        tab, app = _make_tab(with_engine=False)
        tab.selected_index = 0
        tab.sessions = [{"goal": ""}]
        app.goal_entry = MagicMock()
        tab._replay_session()
        app._on_run.assert_not_called()


# ---------------------------------------------------------------------------
# _export_log
# ---------------------------------------------------------------------------
class TestExportLog:
    def test_no_selection_returns_none(self):
        tab, _ = _make_tab(with_engine=False)
        tab.selected_index = -1
        assert tab._export_log() is None

    def test_writes_log_file(self, tmp_path):
        tab, _ = _make_tab(with_engine=False)
        tab.output_text = MagicMock()
        tab.selected_index = 0
        tab.sessions = [
            {
                "goal": "export goal",
                "status": "completed",
                "start": "2025-01-01T00:00:00",
                "steps": [{"step": {"action": "click"}, "ok": True}],
            }
        ]
        with patch.object(Path, "home", return_value=tmp_path):
            tab._export_log()
        files = list((tmp_path / "Desktop").glob("sentinel_log_*.txt"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "export goal" in content
        assert "completed" in content
        # Output area got the confirmation line.
        joined = "".join(c.args[1] for c in tab.output_text.insert.call_args_list)
        assert "Log exported to" in joined

    def test_oserror_branch_logs_and_returns(self):
        tab, _ = _make_tab(with_engine=False)
        tab.output_text = MagicMock()
        tab.selected_index = 0
        tab.sessions = [{"goal": "g", "status": "completed", "start": "", "steps": []}]
        fake_path = MagicMock()
        fake_path.parent.mkdir.side_effect = OSError("disk full")
        with (
            patch.object(Path, "home", return_value=Path("/x")),
            patch.object(ht, "logger") as log,
        ):
            # Force the constructed export_path to be our failing mock.
            with patch("gui.tabs.history_tab.Path") as PathCls:
                PathCls.home.return_value = MagicMock()
                # Path.home() / "Desktop" / filename -> chain returns fake_path
                PathCls.home.return_value.__truediv__.return_value.__truediv__.return_value = (
                    fake_path
                )
                result = tab._export_log()
        assert result is None
        log.error.assert_called_once()
        # Nothing written to output area since we returned early.
        tab.output_text.insert.assert_not_called()
