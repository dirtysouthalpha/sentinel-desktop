"""Edge-case hardening tests for core/scheduler.py.

Covers the run-loop and lifecycle branches the other suites miss: stopping
with no live thread, executing a task that's no longer registered, loading a
file with malformed entries, an unrecognised on_complete directive, and the
``_tick`` paths where a cron isn't due, a task is removed mid-run, or
recomputing ``next_run`` fails.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from core.scheduler import TaskScheduler


def _scheduler(tmp_path) -> TaskScheduler:
    return TaskScheduler(engine=None, tasks_path=str(tmp_path / "tasks.json"))


class TestStopWithoutThread:
    def test_stop_with_no_thread_still_saves(self, tmp_path):
        """Branch 184->187: stop() while marked running but with no live thread
        skips the join and still persists."""
        ts = _scheduler(tmp_path)
        ts._running = True
        ts._thread = None
        with patch.object(ts, "save") as mock_save:
            ts.stop()
        assert ts._running is False
        mock_save.assert_called_once()


class TestRunTaskNowRemovedMidRun:
    def test_run_task_now_task_removed_during_execution(self, tmp_path):
        """Branch 322->327: run_task_now() where the task is removed mid-run
        skips the last_run/next_run update but still saves and returns."""
        ts = _scheduler(tmp_path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        tid = task["id"]

        def fake_exec(_task):
            # The task is deleted (e.g. via the API) while it executes.
            ts._tasks.pop(tid, None)
            return {"success": True, "output": "", "error": None}

        with patch.object(ts, "_execute_task", side_effect=fake_exec), \
             patch.object(ts, "save") as mock_save:
            result = ts.run_task_now(tid)
        assert tid not in ts._tasks
        assert result == {"success": True, "output": "", "error": None}
        mock_save.assert_called_once()


class TestLoadMalformedItems:
    def test_load_skips_non_dict_and_idless_items(self, tmp_path):
        """Branch 376->375: list entries that aren't dicts or lack an 'id' are
        skipped during load()."""
        path = tmp_path / "tasks.json"
        path.write_text(
            json.dumps(
                [
                    "not a dict",
                    {"no_id": True},
                    {"id": "good", "name": "G", "type": "script", "cron_expr": "* * * * *"},
                ]
            ),
            encoding="utf-8",
        )
        ts = TaskScheduler(engine=None, tasks_path=str(path))
        ts.load()
        assert list(ts._tasks.keys()) == ["good"]


class TestHandleOnCompleteUnknownDirective:
    def test_unknown_directive_is_noop(self, tmp_path):
        """Branch 515->exit: an on_complete directive that's neither 'disable'
        nor 'remove' leaves the task untouched."""
        ts = _scheduler(tmp_path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        ts._handle_on_complete({"id": task["id"], "on_complete": "notify"}, {})
        assert task["id"] in ts._tasks
        assert ts._tasks[task["id"]].get("enabled", True) is True


class TestTickEdgeCases:
    def test_cron_not_due_skips_task(self, tmp_path):
        """Branch 547->540: a valid cron that isn't due is skipped."""
        ts = _scheduler(tmp_path)
        ts.add_task("T", "script", "* * * * *", path="x.py")
        ran = []
        ts.set_on_task_complete(lambda r: ran.append(r))
        with patch("core.scheduler.cron_matches", return_value=False):
            ts._tick()
        assert ran == []

    def test_task_removed_during_execution(self, tmp_path):
        """Branch 559->568: a task deleted while it runs skips the post-run
        bookkeeping but still reaches on_complete handling."""
        ts = _scheduler(tmp_path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        tid = task["id"]

        def fake_exec(_task):
            # Simulate the task being removed (e.g. via the API) mid-run.
            ts._tasks.pop(tid, None)
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()
        assert tid not in ts._tasks

    def test_next_run_recomputation_failure_sets_none(self, tmp_path):
        """Lines 564-566: if recomputing next_run raises, it's logged and the
        field is reset to None."""
        ts = _scheduler(tmp_path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        tid = task["id"]
        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", return_value={"status": "success"}), \
             patch("core.scheduler._next_run_after", side_effect=ValueError("bad cron")):
            ts._tick()
        assert ts._tasks[tid]["next_run"] is None
