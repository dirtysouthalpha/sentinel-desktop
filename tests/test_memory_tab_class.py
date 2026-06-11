"""Tests for gui/tabs/memory_tab.py — MemoryTab class via real construction.

Builds the tab through its real ``__init__`` against the headless customtkinter
stub (conftest) so all widget-construction paths, data-refresh branches, and
conductor methods are exercised.  SemanticMemory and EpisodicMemory are patched
to avoid touching disk.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


def _theme(key=None, default="#ffffff"):
    return default


def _make_app():
    app = MagicMock()
    app._t = _theme
    return app


def _make_tab(semantic=None, episodic=None):
    """Construct a MemoryTab through its real __init__ (covers build paths)."""
    from gui.tabs.memory_tab import MemoryTab

    fake_semantic = semantic if semantic is not None else MagicMock()
    fake_episodic = episodic if episodic is not None else MagicMock()
    fake_semantic.list_keys.return_value = []
    fake_episodic.recall.return_value = []

    with (
        patch("gui.tabs.memory_tab.SemanticMemory", return_value=fake_semantic),
        patch("gui.tabs.memory_tab.EpisodicMemory", return_value=fake_episodic),
    ):
        tab = MemoryTab(MagicMock(), _make_app())

    # Attach mocks for later test-method calls
    tab._semantic = fake_semantic
    tab._episodic = fake_episodic
    return tab, fake_semantic, fake_episodic


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_builds_without_error(self):
        tab, _, _ = _make_tab()
        assert tab is not None

    def test_selected_key_starts_none(self):
        tab, _, _ = _make_tab()
        assert tab._selected_key is None

    def test_running_conductor_starts_false(self):
        tab, _, _ = _make_tab()
        assert tab._running_conductor is False


# ---------------------------------------------------------------------------
# _switch_sub — conductor branch (lines 113-124)
# ---------------------------------------------------------------------------


class TestSwitchSub:
    def test_switch_to_conductor(self):
        tab, _, _ = _make_tab()
        # Calling _switch_sub("conductor") should not raise
        tab._switch_sub("conductor")

    def test_switch_to_memory(self):
        tab, _, _ = _make_tab()
        tab._switch_sub("memory")


# ---------------------------------------------------------------------------
# _refresh_facts — all branches (lines 340-395)
# ---------------------------------------------------------------------------


class TestRefreshFacts:
    def test_no_query_empty_keys_shows_placeholder(self):
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: "  "  # whitespace → no query
        tab._refresh_facts()  # should not raise

    def test_no_query_with_keys(self):
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = ["host.firewall", "user.admin"]
        tab._search_var.get = lambda: ""
        tab._refresh_facts()

    def test_with_query_returns_results(self):
        """Lines 345, 349-350: query path with matching results."""
        tab, sem, _ = _make_tab()
        sem.query.return_value = [{"key": "host.firewall"}, {"key": "user.admin"}]
        tab._search_var.get = lambda: "firewall"
        tab._refresh_facts()
        sem.query.assert_called_once_with("firewall", limit=50)

    def test_with_query_no_results_shows_placeholder(self):
        """Lines 358-365: empty results after search → placeholder label."""
        tab, sem, _ = _make_tab()
        sem.query.return_value = []
        tab._search_var.get = lambda: "notfound"
        tab._refresh_facts()

    def test_exception_in_refresh_swallowed(self):
        """Lines 353-355: exception is caught and keys defaults to []."""
        tab, sem, _ = _make_tab()
        sem.list_keys.side_effect = RuntimeError("db error")
        tab._search_var.get = lambda: ""
        tab._refresh_facts()  # should not raise

    def test_selected_key_highlights_card(self):
        """Lines 394-395: selected key triggers card highlight."""
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = ["selected.key", "other.key"]
        tab._selected_key = "selected.key"
        tab._search_var.get = lambda: ""
        tab._refresh_facts()  # exercises the highlight branch


# ---------------------------------------------------------------------------
# _select_fact (lines 400-458)
# ---------------------------------------------------------------------------


class TestSelectFact:
    def test_select_existing_fact(self):
        """Lines 400-431: select a fact that exists in semantic store."""
        tab, sem, _ = _make_tab()
        sem.recall.return_value = {
            "key": "host.fw",
            "value": "192.168.1.1",
            "category": "network",
            "tags": ["firewall"],
            "source": "gui",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "access_count": 3,
        }
        sem.list_keys.return_value = ["host.fw"]
        tab._search_var.get = lambda: ""
        tab._select_fact("host.fw")
        assert tab._selected_key == "host.fw"

    def test_select_missing_fact(self):
        """Lines 436-444: recall returns None → shows '(not found)' message."""
        tab, sem, _ = _make_tab()
        sem.recall.return_value = None
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: ""
        tab._select_fact("ghost.key")
        assert tab._selected_key == "ghost.key"

    def test_select_recall_raises(self):
        """Exception in recall is caught."""
        tab, sem, _ = _make_tab()
        sem.recall.side_effect = RuntimeError("no such key")
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: ""
        tab._select_fact("bad.key")
        assert tab._selected_key == "bad.key"


# ---------------------------------------------------------------------------
# _refresh_episodes (lines 440-458)
# ---------------------------------------------------------------------------


class TestRefreshEpisodes:
    def test_no_episodes_shows_placeholder(self):
        tab, _, epi = _make_tab()
        epi.recall.return_value = []
        tab._refresh_episodes()

    def test_with_episodes_renders_lines(self):
        tab, _, epi = _make_tab()
        epi.recall.return_value = [
            {
                "goal": "Check routing table",
                "started_at": "2026-06-01T10:30:00",
                "actions": [{"action": "ssh_connect"}, {"action": "ssh_show"}],
                "status": "completed",
            },
            {
                "goal": "Restart service",
                "started_at": "2026-06-01T11:00:00",
                "actions": [],
                "status": "error",
            },
        ]
        tab._refresh_episodes()

    def test_episodes_exception_handled(self):
        tab, _, epi = _make_tab()
        epi.recall.side_effect = RuntimeError("io error")
        tab._refresh_episodes()


# ---------------------------------------------------------------------------
# _set_conductor_output (lines 670-673)
# ---------------------------------------------------------------------------


class TestSetConductorOutput:
    def test_set_output_text(self):
        tab, _, _ = _make_tab()
        tab._set_conductor_output("hello world\n")


# ---------------------------------------------------------------------------
# _render_subtask_cards (lines 626-659)
# ---------------------------------------------------------------------------


class TestRenderSubtaskCards:
    def test_empty_results(self):
        tab, _, _ = _make_tab()
        tab._render_subtask_cards([])

    def test_results_with_various_statuses(self):
        tab, _, _ = _make_tab()
        results = [
            {"status": "success", "description": "SSH connect", "task_type": "ssh"},
            {"status": "error", "description": "Ping failed", "task_type": "net", "error": "timeout"},
            {"status": "timeout", "description": "OCR read", "task_type": "ocr"},
            {"status": "pending", "subtask_id": "t-4", "task_type": "click"},
        ]
        tab._render_subtask_cards(results)


# ---------------------------------------------------------------------------
# _finish_conductor (lines 620-621)
# ---------------------------------------------------------------------------


class TestFinishConductor:
    def test_resets_running_flag(self):
        tab, _, _ = _make_tab()
        tab._running_conductor = True
        tab._finish_conductor()
        assert tab._running_conductor is False


# ---------------------------------------------------------------------------
# _run_conductor (lines 556-617)
# ---------------------------------------------------------------------------


class TestRunConductor:
    def test_no_op_when_empty_goal(self):
        tab, _, _ = _make_tab()
        tab._goal_var.get = lambda: "  "
        tab._run_conductor()
        assert tab._running_conductor is False

    def test_no_op_when_already_running(self):
        tab, _, _ = _make_tab()
        tab._running_conductor = True
        tab._goal_var.get = lambda: "do something"
        tab._run_conductor()

    def test_runs_conductor_success(self):
        """Lines 557-617: full run path with successful result."""
        tab, _, _ = _make_tab()
        tab._goal_var.get = lambda: "check ARP table"
        tab._timeout_slider.get = lambda: 30

        mock_result = {
            "success": True,
            "total_subtasks": 2,
            "elapsed_ms": 1500,
            "results": [
                {"status": "success", "description": "SSH connect", "task_type": "ssh"},
                {"status": "success", "description": "Run command", "task_type": "cmd"},
            ],
        }

        async def _fake_run(goal, timeout=120.0):
            return mock_result

        mock_conductor = MagicMock()
        mock_conductor.run = _fake_run

        import threading

        done_event = threading.Event()
        original_after = tab.after

        def _capture_after(delay, fn=None, *args):
            if fn is not None:
                fn(*args)
            if tab._running_conductor is False:
                done_event.set()

        tab.after = _capture_after

        with patch("core.conductor.coordinator.Conductor", return_value=mock_conductor):
            tab._run_conductor()
            done_event.wait(timeout=5)

    def test_runs_conductor_with_error_key(self):
        """Result dict contains 'error' key — renders error line."""
        tab, _, _ = _make_tab()
        tab._goal_var.get = lambda: "do something"
        tab._timeout_slider.get = lambda: 30

        mock_result = {
            "success": False,
            "total_subtasks": 1,
            "elapsed_ms": 500,
            "results": [{"status": "error", "description": "ssh", "task_type": "ssh", "error": "refused"}],
            "error": "Plan failed",
        }

        async def _fake_run(goal, timeout=120.0):
            return mock_result

        mock_conductor = MagicMock()
        mock_conductor.run = _fake_run

        import threading

        done_event = threading.Event()

        def _capture_after(delay, fn=None, *args):
            if fn is not None:
                fn(*args)
            if not tab._running_conductor:
                done_event.set()

        tab.after = _capture_after

        with patch("core.conductor.coordinator.Conductor", return_value=mock_conductor):
            tab._run_conductor()
            done_event.wait(timeout=5)

    def test_runs_conductor_exception_path(self):
        """Lines 608-613: exception in thread sets error output."""
        tab, _, _ = _make_tab()
        tab._goal_var.get = lambda: "do something"
        tab._timeout_slider.get = lambda: 30

        import threading

        done_event = threading.Event()

        def _capture_after(delay, fn=None, *args):
            if fn is not None:
                fn(*args)
            if not tab._running_conductor:
                done_event.set()

        tab.after = _capture_after

        with patch("core.conductor.coordinator.Conductor", side_effect=RuntimeError("fail")):
            tab._run_conductor()
            done_event.wait(timeout=5)


# ---------------------------------------------------------------------------
# _show_store_dialog (lines 463-552) — logic branches without GUI interaction
# ---------------------------------------------------------------------------


class TestShowStoreDialog:
    def test_show_store_dialog_does_not_raise(self):
        """Lines 463-552: dialog construction runs without error."""
        tab, _, _ = _make_tab()
        tab._show_store_dialog()

    def _capture_save(self, tab, sem):
        """Helper: builds dialog, captures _save closure and its entries dict."""
        import customtkinter as ctk

        captured: dict = {}
        _orig_cls = ctk.CTkButton

        class _CapturingButton(_orig_cls):
            def __init__(self_btn, *a, **kw):
                super().__init__(*a, **kw)
                if kw.get("text") == "Save":
                    captured["save"] = kw.get("command")

        with patch("gui.tabs.memory_tab.ctk.CTkButton", _CapturingButton):
            tab._show_store_dialog()

        save_fn = captured.get("save")
        assert save_fn is not None, "Save button command was not captured"

        # Extract entries dict from closure so we can set .get() return values
        entries = None
        for cell in save_fn.__closure__ or []:
            try:
                val = cell.cell_contents
                if isinstance(val, dict) and "key_entry" in val:
                    entries = val
                    break
            except ValueError:
                pass
        assert entries is not None, "Could not find entries in _save closure"
        return save_fn, entries

    def test_save_with_valid_key_and_value(self):
        """Lines 515-523: _save() with real key+value calls semantic.store."""
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: ""

        save_fn, entries = self._capture_save(tab, sem)

        entries["key_entry"].get = lambda: "host.fw"
        entries["value_entry"].get = lambda: "10.0.0.1"
        entries["cat_entry"].get = lambda: "network"
        entries["tags_entry"].get = lambda: "firewall, prod"

        save_fn()
        sem.store.assert_called_once_with(
            "host.fw", "10.0.0.1", "network", ["firewall", "prod"], source="gui"
        )

    def test_save_exception_path(self):
        """Lines 519-520: store raises → warning logged, dialog still destroyed."""
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: ""
        sem.store.side_effect = RuntimeError("db locked")

        save_fn, entries = self._capture_save(tab, sem)

        entries["key_entry"].get = lambda: "host.fw"
        entries["value_entry"].get = lambda: "10.0.0.1"
        entries["cat_entry"].get = lambda: ""
        entries["tags_entry"].get = lambda: ""

        save_fn()  # should not raise

    def test_save_empty_key_early_returns(self):
        """Empty key/value → early return, semantic.store not called."""
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: ""

        save_fn, _ = self._capture_save(tab, sem)
        save_fn()  # entry stubs return "" → early return
        sem.store.assert_not_called()


class TestWinfoChildrenLoopBodies:
    """Covers the w.destroy() lines inside for-loop over winfo_children()."""

    def test_refresh_facts_destroys_existing_children(self):
        """Line 345: destroy() called when _facts_list has children."""
        tab, sem, _ = _make_tab()
        sem.list_keys.return_value = []
        tab._search_var.get = lambda: ""

        child = MagicMock()
        tab._facts_list.winfo_children = lambda: [child]
        tab._refresh_facts()
        child.destroy.assert_called_once()

    def test_render_subtask_cards_destroys_existing_children(self):
        """Line 628: destroy() called when _subtasks_frame has existing cards."""
        tab, _, _ = _make_tab()

        child = MagicMock()
        tab._subtasks_frame.winfo_children = lambda: [child]
        tab._render_subtask_cards([])
        child.destroy.assert_called_once()
