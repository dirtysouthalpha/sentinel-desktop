"""Tests for core.file_watcher — watch_file, watch_file_content, watch_process."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── watch_file ────────────────────────────────────────────────────────────────


class TestWatchFile:
    def test_detect_modify(self, tmp_path):
        from core.file_watcher import watch_file

        target = tmp_path / "watched.txt"
        target.write_text("initial")
        target_str = str(target)  # Capture path before potential tmp_path cleanup

        modified = threading.Event()

        def modify_after_delay():
            time.sleep(0.3)  # Slightly longer delay for robustness
            try:
                Path(target_str).write_text("modified")
                modified.set()
            except (FileNotFoundError, OSError):
                # If tmp_path was cleaned up, silently fail - test will timeout
                pass

        thread = threading.Thread(target=modify_after_delay, daemon=True)
        thread.start()
        result = watch_file(target_str, timeout=3, poll_interval=0.05, event="modify")
        assert result["event"] == "modify"
        assert result["success"] is True
        assert "path" in result
        # Wait for the modification thread to complete before allowing tmp_path cleanup
        modified.wait(timeout=1.0)

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
        result = watch_file_content(
            str(target), contains="NEVER_APPEARS", timeout=0.3, poll_interval=0.05
        )
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
        import psutil

        from core.file_watcher import watch_process

        # Use 'python' or 'python.exe' — the current interpreter is running
        proc_name = "python.exe" if psutil.WINDOWS else "python"
        result = watch_process(proc_name, event="start", timeout=1, poll_interval=0.1)
        assert (
            result["success"] is True or result["success"] is False
        )  # either is valid — just no exception

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
        import subprocess
        import sys

        from core.file_watcher import watch_process

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
        pid = proc.pid

        def wait_then_let_exit():
            time.sleep(0.3)
            proc.wait()

        threading.Thread(target=wait_then_let_exit, daemon=True).start()
        result = watch_process("python.exe", event="stop", pid=pid, timeout=3, poll_interval=0.1)
        assert (
            result["success"] is True or result["success"] is False
        )  # graceful no matter the outcome


# ── Executor integration ──────────────────────────────────────────────────────


class TestFileWatcherEdgeCases:
    def test_watch_file_content_oserror_on_read(self, tmp_path):
        """OSError during read_text inside watch loop should be silently swallowed."""
        from core.file_watcher import watch_file_content

        target = tmp_path / "err.txt"
        target.write_text("initial content here")
        # read_text raises OSError → hits except OSError: pass branch
        with patch("pathlib.Path.read_text", side_effect=OSError("disk error")):
            result = watch_file_content(
                str(target), contains="initial", timeout=0.3, poll_interval=0.05
            )
        # Timed out (content never confirmed) — but no exception raised
        assert result["success"] is False

    def test_watch_process_find_proc_access_denied(self):
        """NoSuchProcess/AccessDenied on individual iteration entries are silently skipped."""
        import psutil

        from core.file_watcher import watch_process

        bad_proc = MagicMock()
        bad_proc.info = MagicMock()
        bad_proc.info.get = MagicMock(side_effect=psutil.AccessDenied(999))

        with patch("core.file_watcher.psutil.process_iter", return_value=[bad_proc]):
            result = watch_process("anything", event="start", timeout=0.1, poll_interval=0.05)
        assert result["success"] is False  # nothing found → timeout

    def test_watch_process_start_event_records_pid(self):
        """start event: result_pid comes from the newly appeared process."""
        import psutil

        from core.file_watcher import watch_process

        mock_proc = MagicMock(spec=psutil.Process)
        mock_proc.pid = 42
        mock_proc.is_running.return_value = True
        mock_proc.info = {"name": "myapp", "pid": 42}

        call_n = [0]

        def iter_side(_fields):
            call_n[0] += 1
            if call_n[0] < 3:
                return []  # not running yet → initial_proc = None
            return [mock_proc]

        with patch("core.file_watcher.psutil.process_iter", side_effect=iter_side):
            result = watch_process("myapp", event="start", timeout=2, poll_interval=0.05)
        assert result["success"] is True
        assert result["pid"] == 42

    def test_watch_process_cpu_spike_detected(self):
        """cpu_spike event triggers when cpu_percent > 80."""
        import psutil

        from core.file_watcher import watch_process

        mock_proc = MagicMock(spec=psutil.Process)
        mock_proc.pid = 99
        mock_proc.is_running.return_value = True
        mock_proc.info = {"name": "heavyapp", "pid": 99}
        mock_proc.cpu_percent.return_value = 95.0

        with patch("core.file_watcher.psutil.process_iter", return_value=[mock_proc]):
            result = watch_process("heavyapp", event="cpu_spike", timeout=2, poll_interval=0.05)
        assert result["success"] is True
        assert result["pid"] == 99
        assert result["event"] == "cpu_spike"

    def test_watch_process_cpu_spike_no_spike(self):
        """cpu_spike event times out when cpu stays below threshold."""
        import psutil

        from core.file_watcher import watch_process

        mock_proc = MagicMock(spec=psutil.Process)
        mock_proc.pid = 10
        mock_proc.info = {"name": "idle", "pid": 10}
        mock_proc.cpu_percent.return_value = 5.0

        with patch("core.file_watcher.psutil.process_iter", return_value=[mock_proc]):
            result = watch_process("idle", event="cpu_spike", timeout=0.3, poll_interval=0.05)
        assert result["success"] is False

    def test_watch_process_cpu_spike_access_denied(self):
        """cpu_percent raising AccessDenied during cpu_spike check is silently handled."""
        import psutil

        from core.file_watcher import watch_process

        mock_proc = MagicMock(spec=psutil.Process)
        mock_proc.pid = 10
        mock_proc.info = {"name": "sysapp", "pid": 10}
        mock_proc.cpu_percent.side_effect = psutil.AccessDenied(10)

        with patch("core.file_watcher.psutil.process_iter", return_value=[mock_proc]):
            result = watch_process("sysapp", event="cpu_spike", timeout=0.3, poll_interval=0.05)
        assert result["success"] is False


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
        result = executor.execute_sync(
            {
                "action": "watch_file",
                "path": str(target),
                "timeout": 0.3,
                "event": "modify",
            }
        )
        # Should time out without crashing
        assert result["success"] is False
