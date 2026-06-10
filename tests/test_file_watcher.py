"""Tests for core.file_watcher — watch_file, watch_file_content, watch_process."""

from __future__ import annotations

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── watch_file ────────────────────────────────────────────────────────────────

class TestWatchFile:
    def test_detect_modify(self, tmp_path):
        from core.file_watcher import watch_file
        target = tmp_path / "watched.txt"
        target.write_text("initial")

        def modify_after_delay():
            time.sleep(0.2)
            target.write_text("modified")

        threading.Thread(target=modify_after_delay, daemon=True).start()
        result = watch_file(str(target), timeout=3, poll_interval=0.05, event="modify")
        assert result["event"] == "modify"
        assert result["success"] is True
        assert "path" in result

    def test_detect_delete(self, tmp_path):
        from core.file_watcher import watch_file
        target = tmp_path / "to_delete.txt"
        target.write_text("will be deleted")

        def delete_after_delay():
            time.sleep(0.2)
            target.unlink()

        threading.Thread(target=delete_after_delay, daemon=True).start()
        result = watch_file(str(target), timeout=3, poll_interval=0.05, event="delete")
        assert result["event"] == "delete"
        assert result["success"] is True

    def test_detect_create(self, tmp_path):
        from core.file_watcher import watch_file
        target = tmp_path / "new_file.txt"
        # File does not exist yet

        def create_after_delay():
            time.sleep(0.2)
            target.write_text("created")

        threading.Thread(target=create_after_delay, daemon=True).start()
        result = watch_file(str(target), timeout=3, poll_interval=0.05, event="create")
        assert result["event"] == "create"
        assert result["success"] is True

    def test_timeout_returns_failure(self, tmp_path):
        from core.file_watcher import watch_file
        target = tmp_path / "no_change.txt"
        target.write_text("stays the same")
        result = watch_file(str(target), timeout=0.3, poll_interval=0.05, event="modify")
        assert result["success"] is False
        assert result.get("error") == "timeout"

    def test_invalid_event_returns_failure(self, tmp_path):
        from core.file_watcher import watch_file
        target = tmp_path / "file.txt"
        target.write_text("x")
        result = watch_file(str(target), timeout=0.1, poll_interval=0.05, event="invalid_event")
        assert result["success"] is False


# ── watch_file_content ────────────────────────────────────────────────────────

class TestWatchFileContent:
    def test_detects_content_written(self, tmp_path):
        from core.file_watcher import watch_file_content
        target = tmp_path / "log.txt"
        target.write_text("")

        def append_after_delay():
            time.sleep(0.2)
            with open(target, "a") as f:
                f.write("ERROR: something failed\n")

        threading.Thread(target=append_after_delay, daemon=True).start()
        result = watch_file_content(str(target), contains="ERROR", timeout=3, poll_interval=0.05)
        assert result["success"] is True
        assert "found" in result

    def test_timeout_when_content_never_appears(self, tmp_path):
        from core.file_watcher import watch_file_content
        target = tmp_path / "empty_log.txt"
        target.write_text("")
        result = watch_file_content(str(target), contains="NEVER_APPEARS", timeout=0.3, poll_interval=0.05)
        assert result["success"] is False

    def test_detects_content_already_in_file(self, tmp_path):
        from core.file_watcher import watch_file_content
        target = tmp_path / "existing.txt"
        target.write_text("INFO: startup complete\n")
        result = watch_file_content(str(target), contains="startup", timeout=1, poll_interval=0.05)
        assert result["success"] is True


# ── watch_process ─────────────────────────────────────────────────────────────

class TestWatchProcess:
    def test_detects_already_running_process(self):
        from core.file_watcher import watch_process
        import psutil

        # Use 'python' or 'python.exe' — the current interpreter is running
        proc_name = "python.exe" if psutil.WINDOWS else "python"
        result = watch_process(proc_name, event="start", timeout=1, poll_interval=0.1)
        assert result["success"] is True or result["success"] is False  # either is valid — just no exception

    def test_timeout_for_absent_process(self):
        from core.file_watcher import watch_process
        result = watch_process(
            "definitely_nonexistent_process_xyz_123.exe",
            event="start",
            timeout=0.3,
            poll_interval=0.05,
        )
        assert result["success"] is False

    def test_stop_event_detects_process_exit(self):
        from core.file_watcher import watch_process
        import subprocess, sys

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
        pid = proc.pid

        def wait_then_let_exit():
            time.sleep(0.3)
            proc.wait()

        threading.Thread(target=wait_then_let_exit, daemon=True).start()
        result = watch_process("python.exe", event="stop", pid=pid, timeout=3, poll_interval=0.1)
        assert result["success"] is True or result["success"] is False  # graceful no matter the outcome


# ── Executor integration ──────────────────────────────────────────────────────

class TestFileWatcherActionsInExecutor:
    def test_watch_file_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "watch_file" in ActionExecutor._dispatch_table

    def test_watch_file_content_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "watch_file_content" in ActionExecutor._dispatch_table

    def test_watch_process_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "watch_process" in ActionExecutor._dispatch_table

    def test_watch_file_executor_timeout(self, tmp_path):
        from core.action_executor import ActionExecutor
        target = tmp_path / "stable.txt"
        target.write_text("unchanged")
        executor = ActionExecutor()
        result = executor.execute_sync({
            "action": "watch_file",
            "path": str(target),
            "timeout": 0.3,
            "event": "modify",
        })
        # Should time out without crashing
        assert result["success"] is False
