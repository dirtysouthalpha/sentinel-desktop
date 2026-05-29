"""Tests for process management: list, start, kill processes."""

from unittest.mock import MagicMock, patch

from core import process_manager


def test_list_processes_returns_list():
    """list_processes should return a list of dicts sorted by cpu."""
    fake_info = {
        "pid": 1,
        "name": "test.exe",
        "cpu_percent": 5.0,
        "memory_info": MagicMock(rss=100 * 1024 * 1024),
    }
    mock_proc = MagicMock(info=fake_info)

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.list_processes(sort_by="cpu", limit=10)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["pid"] == 1
    assert result[0]["name"] == "test.exe"
    assert "memory_info" not in result[0]
    assert "memory_mb" in result[0]
    assert result[0]["memory_mb"] == 100.0


def test_list_processes_sorts_by_memory():
    """When sort_by='memory', results should be sorted by memory_mb."""
    procs = []
    for pid, mem in [(1, 200), (2, 50), (3, 150)]:
        info = {
            "pid": pid,
            "name": f"p{pid}",
            "cpu_percent": 0,
            "memory_info": MagicMock(rss=mem * 1024 * 1024),
        }
        procs.append(MagicMock(info=info))

    with patch("core.process_manager.psutil.process_iter", return_value=procs):
        result = process_manager.list_processes(sort_by="memory", limit=10)

    assert result[0]["pid"] == 1  # 200 MB is highest
    assert result[1]["pid"] == 3  # 150 MB
    assert result[2]["pid"] == 2  # 50 MB


def test_list_processes_handles_null_memory():
    """process_iter entries with None memory_info should get 0 memory_mb."""
    info = {"pid": 1, "name": "test", "cpu_percent": 0, "memory_info": None}
    mock_proc = MagicMock(info=info)

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.list_processes()

    assert result[0]["memory_mb"] == 0


def test_list_processes_skips_dead_processes():
    """NoSuchProcess and AccessDenied should be silently skipped."""
    import psutil

    mock_proc = MagicMock(info={"pid": 1, "name": "x", "cpu_percent": 0, "memory_info": None})
    mock_proc.info = None  # simulate access after process died
    mock_proc.info = MagicMock(get=MagicMock(side_effect=psutil.NoSuchProcess(1)))

    # The real code accesses p.info keys, so let's set up a proper side effect
    info = MagicMock()
    info.__getitem__ = MagicMock(side_effect=psutil.NoSuchProcess(1))
    mock_proc = MagicMock()
    mock_proc.info = info

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.list_processes()

    assert result == []


def test_start_process_success():
    """start_process should return PID on success."""
    with patch("core.process_manager.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock(pid=9999)
        pid = process_manager.start_process("notepad.exe")

    assert pid == 9999


def test_start_process_with_args():
    """start_process should forward args to Popen."""
    import subprocess

    with patch("core.process_manager.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock(pid=1234)
        pid = process_manager.start_process("cmd.exe", args=["/c", "dir"])

    assert pid == 1234
    mock_popen.assert_called_once_with(
        ["cmd.exe", "/c", "dir"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def test_start_process_failure_returns_none():
    """start_process should return None on failure."""
    with patch("core.process_manager.subprocess.Popen", side_effect=OSError("nope")):
        pid = process_manager.start_process("/nonexistent")

    assert pid is None


def test_kill_process_by_pid():
    """kill_process with an int should kill that PID."""
    with patch("core.process_manager.psutil.Process") as mock_proc:
        process_manager.kill_process(1234)

    mock_proc.assert_called_once_with(1234)
    mock_proc.return_value.kill.assert_called_once()


def test_kill_process_by_name():
    """kill_process with a string should kill matching processes."""
    info = {"name": "Notepad.exe", "pid": 999}
    mock_proc = MagicMock(info=info)

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.kill_process("notepad")

    assert result is True
    mock_proc.kill.assert_called_once()


def test_kill_process_empty_target():
    """kill_process with empty/None target should return False."""
    assert process_manager.kill_process("") is False
    assert process_manager.kill_process(None) is False


def test_kill_process_by_name_no_match():
    """kill_process with a name that matches nothing should return False."""
    with patch("core.process_manager.psutil.process_iter", return_value=[]):
        result = process_manager.kill_process("nonexistent_app")

    assert result is False


def test_kill_process_no_such_pid():
    """kill_process with a dead PID should return False."""
    import psutil

    with patch("core.process_manager.psutil.Process", side_effect=psutil.NoSuchProcess(9999)):
        result = process_manager.kill_process(9999)

    assert result is False


def test_kill_process_access_denied():
    """kill_process with AccessDenied should return False."""
    import psutil

    with patch("core.process_manager.psutil.Process", side_effect=psutil.AccessDenied(1234)):
        result = process_manager.kill_process(1234)

    assert result is False


def test_kill_process_by_name_access_denied():
    """kill by name: AccessDenied on individual process should continue."""
    import psutil

    info = {"name": "Locked.exe", "pid": 100}
    mock_proc = MagicMock(info=info)
    mock_proc.kill.side_effect = psutil.AccessDenied(100)

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.kill_process("locked")

    assert result is False


def test_list_processes_skips_access_denided():
    """AccessDenied during iteration should be silently skipped."""
    import psutil

    info = MagicMock()
    info.__getitem__ = MagicMock(side_effect=psutil.AccessDenied(1))
    mock_proc = MagicMock()
    mock_proc.info = info

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.list_processes()

    assert result == []


def test_start_process_file_not_found():
    """start_process with FileNotFoundError should return None."""
    with patch("core.process_manager.subprocess.Popen", side_effect=FileNotFoundError("not found")):
        pid = process_manager.start_process("/missing/binary")

    assert pid is None


def test_start_process_subprocess_error():
    """start_process with SubprocessError should return None."""
    import subprocess

    with patch(
        "core.process_manager.subprocess.Popen",
        side_effect=subprocess.SubprocessError("broken pipe"),
    ):
        pid = process_manager.start_process("cmd.exe")

    assert pid is None


def test_kill_process_by_name_empty_after_lower():
    """kill_process with whitespace-only string returns False."""
    assert process_manager.kill_process("   ") is False


def test_kill_process_by_pid_oserror():
    """kill_process with OSError from psutil.Process should return False."""
    with patch("core.process_manager.psutil.Process", side_effect=OSError("kernel error")):
        result = process_manager.kill_process(42)

    assert result is False


def test_kill_process_by_name_no_such_process_during_kill():
    """kill by name: NoSuchProcess during kill should be skipped gracefully."""
    import psutil

    info = {"name": "Zombie.exe", "pid": 555}
    mock_proc = MagicMock(info=info)
    mock_proc.kill.side_effect = psutil.NoSuchProcess(555)

    with patch("core.process_manager.psutil.process_iter", return_value=[mock_proc]):
        result = process_manager.kill_process("zombie")

    assert result is False


def test_list_processes_cpu_percent_none():
    """cpu_percent=None should sort as 0 (via 'or 0' fallback)."""
    info_low = {
        "pid": 1,
        "name": "low",
        "cpu_percent": None,
        "memory_info": MagicMock(rss=10 * 1024 * 1024),
    }
    info_high = {
        "pid": 2,
        "name": "high",
        "cpu_percent": 50.0,
        "memory_info": MagicMock(rss=10 * 1024 * 1024),
    }
    procs = [MagicMock(info=info_low), MagicMock(info=info_high)]

    with patch("core.process_manager.psutil.process_iter", return_value=procs):
        result = process_manager.list_processes(sort_by="cpu", limit=10)

    assert result[0]["pid"] == 2  # 50.0 sorts before None-as-0


def test_list_processes_limit_cuts():
    """list_processes should enforce the limit parameter."""
    procs = []
    for i in range(20):
        info = {
            "pid": i,
            "name": f"p{i}",
            "cpu_percent": float(i),
            "memory_info": MagicMock(rss=50 * 1024 * 1024),
        }
        procs.append(MagicMock(info=info))

    with patch("core.process_manager.psutil.process_iter", return_value=procs):
        result = process_manager.list_processes(limit=5)

    assert len(result) == 5


def test_start_process_running_process_no_warning():
    """start_process with a still-running process (poll()=None) should not log a warning."""
    import subprocess

    mock_proc = MagicMock()
    mock_proc.pid = 42
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read.return_value = b""
    mock_proc.poll.return_value = None  # process still running — False branch at line 37

    with patch("core.process_manager.subprocess.Popen", return_value=mock_proc):
        with patch("core.process_manager.logger") as mock_log:
            pid = process_manager.start_process("long_running.sh")

    assert pid == 42
    mock_log.warning.assert_not_called()
