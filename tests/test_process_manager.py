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
        stderr=subprocess.DEVNULL,
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


# ── set_priority ──────────────────────────────────────────────────────────────

def test_set_priority_success():
    mock_proc = MagicMock()
    with patch("core.process_manager.psutil.Process", return_value=mock_proc):
        result = process_manager.set_priority(1234, "normal")
    assert result is True
    mock_proc.nice.assert_called_once()


def test_set_priority_high():
    mock_proc = MagicMock()
    with patch("core.process_manager.psutil.Process", return_value=mock_proc):
        result = process_manager.set_priority(1234, "high")
    assert result is True


def test_set_priority_unknown_returns_false():
    mock_proc = MagicMock()
    with patch("core.process_manager.psutil.Process", return_value=mock_proc):
        result = process_manager.set_priority(1234, "turbo_boost")
    assert result is False
    mock_proc.nice.assert_not_called()


def test_set_priority_no_such_process():
    import psutil
    with patch("core.process_manager.psutil.Process", side_effect=psutil.NoSuchProcess(1234)):
        result = process_manager.set_priority(1234, "normal")
    assert result is False


def test_set_priority_access_denied():
    import psutil
    mock_proc = MagicMock()
    mock_proc.nice.side_effect = psutil.AccessDenied(1234)
    with patch("core.process_manager.psutil.Process", return_value=mock_proc):
        result = process_manager.set_priority(1234, "high")
    assert result is False


def test_set_priority_oserror():
    mock_proc = MagicMock()
    mock_proc.nice.side_effect = OSError("permission denied")
    with patch("core.process_manager.psutil.Process", return_value=mock_proc):
        result = process_manager.set_priority(1234, "idle")
    assert result is False


# ── set_env ───────────────────────────────────────────────────────────────────

def test_set_env_basic():
    result = process_manager.set_env("_SENTINEL_TEST_VAR", "hello")
    assert result is True
    import os
    assert os.environ.get("_SENTINEL_TEST_VAR") == "hello"
    del os.environ["_SENTINEL_TEST_VAR"]


def test_set_env_permanent_non_windows():
    """On Linux, permanent=True just sets the env var (no winreg branch)."""
    result = process_manager.set_env("_SENTINEL_TEST_PERM", "world", permanent=True)
    assert result is True
    import os
    assert os.environ.get("_SENTINEL_TEST_PERM") == "world"
    del os.environ["_SENTINEL_TEST_PERM"]


def test_set_env_permanent_windows_oserror():
    """Windows permanent path: winreg.OpenKey raises OSError → returns False."""
    mock_winreg = MagicMock()
    mock_winreg.OpenKey.side_effect = OSError("Access denied")
    with patch("sys.platform", "win32"):
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = process_manager.set_env("_SENTINEL_WINTEST", "val", permanent=True)
    assert result is False
    # Clean up env var that was set before the OSError was raised
    import os
    os.environ.pop("_SENTINEL_WINTEST", None)


# ── service_control ───────────────────────────────────────────────────────────

def test_service_control_non_windows():
    result = process_manager.service_control("Spooler", "start")
    assert result["success"] is False
    assert "Windows" in result["error"]


# ── _sanitize_command ────────────────────────────────────────────────────────

def test_sanitize_command_dangerous_pattern():
    """_sanitize_command raises ValueError for dangerous patterns."""
    import pytest
    with pytest.raises(ValueError, match="dangerous"):
        process_manager._sanitize_command("rm -rf /tmp")


def test_sanitize_command_shell_metachar_in_path():
    """_sanitize_command raises ValueError for shell metacharacters in path."""
    import pytest
    with pytest.raises(ValueError, match="metacharacter"):
        process_manager._sanitize_command("/usr/bin/app|evil")


def test_start_process_dangerous_command_returns_none():
    """start_process with a dangerous command returns None (ValueError caught)."""
    result = process_manager.start_process("rm -rf /important")
    assert result is None


# ── get_env ──────────────────────────────────────────────────────────────────

def test_get_env_existing():
    """get_env returns value for a set environment variable."""
    import os
    os.environ["_SENTINEL_GETENV_TEST"] = "sentinel_value"
    try:
        assert process_manager.get_env("_SENTINEL_GETENV_TEST") == "sentinel_value"
    finally:
        del os.environ["_SENTINEL_GETENV_TEST"]


def test_get_env_missing():
    """get_env returns None for a missing environment variable."""
    import os
    os.environ.pop("_SENTINEL_MISSING_VAR", None)
    assert process_manager.get_env("_SENTINEL_MISSING_VAR") is None


# ── set_env Windows success path ──────────────────────────────────────────────

def test_set_env_permanent_windows_success():
    """set_env on Windows with permanent=True calls SetValueEx and CloseKey."""
    mock_winreg = MagicMock()
    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value = mock_key
    mock_winreg.HKEY_CURRENT_USER = 0x80000001
    mock_winreg.KEY_SET_VALUE = 0x0002
    mock_winreg.REG_SZ = 1
    with patch("sys.platform", "win32"):
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            result = process_manager.set_env("_SENTINEL_WIN_SUCC", "val", permanent=True)
    assert result is True
    mock_winreg.SetValueEx.assert_called_once()
    mock_winreg.CloseKey.assert_called_once_with(mock_key)
    import os
    os.environ.pop("_SENTINEL_WIN_SUCC", None)


# ── service_control Windows paths ─────────────────────────────────────────────

def _make_mock_ctypes(sc_val=1, svc_val=1, status_val=4):
    """Build a minimal ctypes mock for service_control tests."""
    mock_ctypes = MagicMock()
    mock_advapi = MagicMock()
    mock_ctypes.windll.advapi32 = mock_advapi
    mock_advapi.OpenSCManagerW.return_value = sc_val
    mock_advapi.OpenServiceW.return_value = svc_val

    def fake_query_status(svc, byref_obj):
        byref_obj._obj.value = status_val

    mock_status = MagicMock()
    mock_status.value = status_val
    mock_ctypes.c_void_p = MagicMock(return_value=MagicMock())
    mock_ctypes.c_uint32.return_value = mock_status
    mock_ctypes.c_int = MagicMock(return_value=MagicMock())
    mock_ctypes.c_wchar_p = MagicMock(return_value=MagicMock())

    def fake_byref(obj):
        return obj

    mock_ctypes.byref = fake_byref
    mock_advapi.QueryServiceStatus = MagicMock(return_value=1)
    return mock_ctypes, mock_advapi, mock_status


def test_service_control_windows_query_success():
    """service_control query returns running state on Windows."""
    mock_ctypes, mock_advapi, mock_status = _make_mock_ctypes(status_val=4)
    mock_status.value = 4
    with patch("sys.platform", "win32"):
        with patch("core.process_manager.ctypes", mock_ctypes, create=True):
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                result = process_manager.service_control("Spooler", "query")
    assert result["success"] is True
    assert result["service"] == "Spooler"
    assert result["state"] == "running"


def test_service_control_windows_query_sc_fail():
    """service_control query returns error when OpenSCManager fails."""
    mock_ctypes, mock_advapi, _ = _make_mock_ctypes(sc_val=0)
    with patch("sys.platform", "win32"):
        with patch("core.process_manager.ctypes", mock_ctypes, create=True):
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                result = process_manager.service_control("Spooler", "query")
    assert result["success"] is False
    assert "SCManager" in result["error"]


def test_service_control_windows_query_svc_fail():
    """service_control query returns error when OpenService fails."""
    mock_ctypes, mock_advapi, _ = _make_mock_ctypes(sc_val=1, svc_val=0)
    with patch("sys.platform", "win32"):
        with patch("core.process_manager.ctypes", mock_ctypes, create=True):
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                result = process_manager.service_control("Spooler", "query")
    assert result["success"] is False
    assert "not found" in result["error"]


def test_service_control_windows_query_oserror():
    """service_control query catches OSError from ctypes."""
    mock_ctypes = MagicMock()
    mock_ctypes.windll.advapi32.OpenSCManagerW.side_effect = OSError("access denied")
    with patch("sys.platform", "win32"):
        with patch("core.process_manager.ctypes", mock_ctypes, create=True):
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                result = process_manager.service_control("Spooler", "query")
    assert result["success"] is False


def test_service_control_windows_start_action():
    """service_control start action runs net start on Windows."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Service started.\n"
    mock_result.stderr = ""
    mock_ctypes = MagicMock()
    with patch("sys.platform", "win32"):
        with patch("core.process_manager.ctypes", mock_ctypes, create=True):
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                with patch("core.process_manager.subprocess.run", return_value=mock_result):
                    result = process_manager.service_control("Spooler", "start")
    assert result["success"] is True
    assert result["service"] == "Spooler"
    assert result["action"] == "start"


def test_service_control_windows_action_subprocess_error():
    """service_control handles subprocess errors for start/stop actions."""
    import subprocess
    mock_ctypes = MagicMock()
    with patch("sys.platform", "win32"):
        with patch("core.process_manager.ctypes", mock_ctypes, create=True):
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                with patch(
                    "core.process_manager.subprocess.run",
                    side_effect=subprocess.SubprocessError("timed out"),
                ):
                    result = process_manager.service_control("Spooler", "stop")
    assert result["success"] is False
    assert "error" in result
