"""Tests for gui/tabs/history_tab.py — logic methods with mocked CTk."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def mock_app():
    app = MagicMock()
    app._t = lambda k, f="#fff": f
    app.engine = MagicMock()
    app.engine.forensic_log = []
    app.engine.notes = []
    return app


@pytest.fixture()
def history_tab(mock_app):
    import gui.tabs.history_tab as history_tab_mod
    from gui.tabs.history_tab import HistoryTab

    with patch.object(history_tab_mod, "ctk"):
        tab = HistoryTab.__new__(HistoryTab)
        tab.app = mock_app
        tab.sessions = []
        tab.selected_index = -1
        tab.filter_var = MagicMock()
        tab.session_list = MagicMock()
        tab.session_list.winfo_children.return_value = []
        tab.search_entry = MagicMock()
        tab.search_entry.get.return_value = ""
        tab.goal_label = MagicMock()
        tab.status_badge = MagicMock()
        tab.timeline = MagicMock()
        tab.timeline.winfo_children.return_value = []
        tab.output_text = MagicMock()
    return tab


class TestHistoryTabRefresh:
    def test_refresh_empty_engine(self, history_tab):
        history_tab.app.engine = None
        history_tab.refresh_history()
        assert len(history_tab.sessions) >= 1
        assert history_tab.sessions[0]["status"] == "empty"

    def test_refresh_with_forensic_log(self, history_tab):
        history_tab.app.engine.forensic_log = [
            {"step": {"action": "click"}, "ok": True, "timestamp": datetime.now().isoformat()},
            {"step": {"action": "finish"}, "ok": True, "timestamp": datetime.now().isoformat()},
        ]
        history_tab.refresh_history()
        assert len(history_tab.sessions) >= 1

    def test_refresh_with_notes_only(self, history_tab):
        history_tab.app.engine.forensic_log = []
        history_tab.app.engine.notes = ["note1", "note2"]
        history_tab.refresh_history()
        assert any("notes" in s for s in history_tab.sessions)

    def test_refresh_marks_completed_on_finish_action(self, history_tab):
        now = datetime.now().isoformat()
        history_tab.app.engine.forensic_log = [
            {"step": {"action": "click", "x": 1}, "ok": True, "timestamp": now, "goal": "Test"},
            {"step": {"action": "finish", "summary": "done"}, "ok": True, "timestamp": now},
        ]
        history_tab.refresh_history()
        assert history_tab.sessions[0]["status"] == "completed"

    def test_refresh_marks_failed_on_last_not_ok(self, history_tab):
        now = datetime.now().isoformat()
        history_tab.app.engine.forensic_log = [
            {"step": {"action": "click"}, "ok": True, "timestamp": now, "goal": "Fail test"},
            {"step": {"action": "click"}, "ok": False, "timestamp": now},
        ]
        history_tab.refresh_history()
        assert history_tab.sessions[0]["status"] == "failed"


class TestHistoryTabFilter:
    def test_filter_all(self, history_tab):
        history_tab.sessions = [
            {"goal": "a", "status": "completed", "start": datetime.now().isoformat()},
            {"goal": "b", "status": "failed", "start": datetime.now().isoformat()},
        ]
        history_tab.filter_var = MagicMock()
        history_tab.filter_var.get.return_value = "All"
        history_tab._apply_filter()
        assert len(history_tab.sessions) == 2

    def test_filter_failed(self, history_tab):
        history_tab.sessions = [
            {"goal": "a", "status": "completed", "start": ""},
            {"goal": "b", "status": "failed", "start": ""},
        ]
        history_tab.filter_var = MagicMock()
        history_tab.filter_var.get.return_value = "Failed"
        history_tab._apply_filter()
        assert len(history_tab.sessions) == 1
        assert history_tab.sessions[0]["status"] == "failed"

    def test_filter_today(self, history_tab):
        today = datetime.now().isoformat()
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        history_tab.sessions = [
            {"goal": "today", "status": "completed", "start": today},
            {"goal": "yesterday", "status": "completed", "start": yesterday},
        ]
        history_tab.filter_var = MagicMock()
        history_tab.filter_var.get.return_value = "Today"
        history_tab._apply_filter()
        assert len(history_tab.sessions) == 1
        assert history_tab.sessions[0]["goal"] == "today"

    def test_filter_this_week(self, history_tab):
        recent = (datetime.now() - timedelta(days=2)).isoformat()
        old = (datetime.now() - timedelta(days=10)).isoformat()
        history_tab.sessions = [
            {"goal": "recent", "status": "completed", "start": recent},
            {"goal": "old", "status": "completed", "start": old},
        ]
        history_tab.filter_var = MagicMock()
        history_tab.filter_var.get.return_value = "This Week"
        history_tab._apply_filter()
        assert len(history_tab.sessions) == 1
        assert history_tab.sessions[0]["goal"] == "recent"


class TestHistoryTabSelect:
    def test_select_out_of_bounds(self, history_tab):
        history_tab.sessions = [{"goal": "a"}]
        history_tab.selected_index = -1
        history_tab.select_session(-1)
        assert history_tab.selected_index == -1

    def test_select_valid_index(self, history_tab):
        history_tab.sessions = [
            {"goal": "test", "status": "completed", "steps": [], "start": "", "notes": []},
        ]
        history_tab.select_session(0)
        assert history_tab.selected_index == 0


class TestHistoryTabExportLog:
    def test_export_no_selection(self, history_tab):
        history_tab.selected_index = -1
        result = history_tab._export_log()
        assert result is None

    def test_export_with_session(self, history_tab, tmp_path):
        history_tab.selected_index = 0
        history_tab.sessions = [
            {
                "goal": "test goal",
                "status": "completed",
                "start": "2025-01-01T00:00:00",
                "steps": [{"step": {"action": "click"}, "ok": True}],
            }
        ]
        with patch.object(Path, "home", return_value=tmp_path):
            history_tab._export_log()
            export_files = list((tmp_path / "Desktop").glob("sentinel_log_*.txt"))
            assert len(export_files) == 1
            content = export_files[0].read_text()
            assert "test goal" in content
            assert "completed" in content


class TestHistoryTabReplay:
    def test_replay_no_selection(self, history_tab):
        history_tab.selected_index = -1
        history_tab._replay_session()
        history_tab.app._on_run.assert_not_called()

    def test_replay_valid_session(self, history_tab):
        history_tab.selected_index = 0
        history_tab.sessions = [{"goal": "replay me"}]
        history_tab.app.goal_entry = MagicMock()
        history_tab._replay_session()
        history_tab.app._on_run.assert_called_once()
