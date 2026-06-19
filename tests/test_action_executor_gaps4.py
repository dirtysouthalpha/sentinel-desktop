"""Gap tests for action_executor.py — 4th batch.

Covers lines:
  650-651   _click_element success path
  868-874   _mouse_move success + OSError
  1302-1333 file ops failure paths (delete/move/copy/mkdir/stat/find)
  1357      _find_files failure
  1372-1399 _archive_create + _archive_extract success
  1410-1412 _set_priority
  1444-1445 _service_control
  1485      _registry_read success
  1502-1504 _registry_write
  1513-1515 _registry_delete
  1765-1766 _ssh_connect exception
  1777-1778 _ssh_disconnect with active client
  1796-1797 _ssh_run success
  1829-1855 _ssh_show body
  1878-1881 _ssh_ping body
  1903-1906 _ssh_traceroute body
  1957-1958 _memory_search exception
  1982-1983 _memory_forget key-not-found
  2035-2041 _retry_last success path
  2045-2047 _get_circuit_breakers
  2124-2150 window control dispatch (resize/move/min/max/restore/state)
  2190-2191 _http_post
  2205-2206 _http_download
  2235-2236 _watch_file_content
  2248-2249 _watch_process
  2277-2281 _listen success + 2289 failure
  2293-2295 _volume_set
  2299-2301 _mute_toggle
  2305-2307 _list_voices
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import core.desktop as desktop_mod
import core.file_ops as file_ops_mod
from core.action_executor import ActionExecutor
from core.perception.types import PerceptionElement, PerceptionResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor() -> ActionExecutor:
    """Create an ActionExecutor with a MagicMock desktop backend."""
    original = desktop_mod.DesktopEngine
    desktop_mod.DesktopEngine = MagicMock
    try:
        return ActionExecutor()
    finally:
        desktop_mod.DesktopEngine = original


def _make_perception_result(
    element_id: int = 1, bbox: tuple = (100, 100, 50, 50)
) -> PerceptionResult:
    elem = PerceptionElement(id=element_id, label="btn", bounding_box=bbox)
    pr = PerceptionResult()
    pr.elements = [elem]
    return pr


# ---------------------------------------------------------------------------
# _click_element success path (lines 650-651)
# ---------------------------------------------------------------------------


class TestClickElementSuccess:
    """Line 650-651 — elem found → call _click with center coords."""

    def test_click_element_found_delegates_to_click(self):
        ex = _make_executor()
        ex.perception_result = _make_perception_result(element_id=1, bbox=(100, 100, 40, 20))
        # center = (100 + 20, 100 + 10) = (120, 110)
        ex._desktop.click = MagicMock()

        result = ex._click_element(element_id=1)

        assert result["success"] is True


# ---------------------------------------------------------------------------
# _mouse_move (lines 868-874)
# ---------------------------------------------------------------------------


class TestMouseMove:
    """Lines 868-874 — success and OSError paths."""

    def test_mouse_move_success(self):
        ex = _make_executor()
        ex._desktop.move_to = MagicMock()

        result = ex._mouse_move(x=200, y=300)

        assert result["success"] is True
        assert "200" in result["output"] or "300" in result["output"]

    def test_mouse_move_oserror(self):
        ex = _make_executor()
        ex._desktop.move_to = MagicMock(side_effect=OSError("display gone"))

        result = ex._mouse_move(x=10, y=10)

        assert result["success"] is False
        assert result["error"] == "mouse_move_failed"


# ---------------------------------------------------------------------------
# File ops failure paths (lines 1302-1357)
# ---------------------------------------------------------------------------


class TestFileOpsFailure:
    """File operation failure branches (return False / None from file_ops)."""

    def test_delete_file_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "delete_file", return_value=False):
            result = ex._delete_file(path="/tmp/nope.txt")
        assert result["success"] is False

    def test_move_file_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "move_file", return_value=False):
            result = ex._move_file(src="/a", dst="/b")
        assert result["success"] is False

    def test_copy_file_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "copy_file", return_value=False):
            result = ex._copy_file(src="/a", dst="/b")
        assert result["success"] is False

    def test_mkdir_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "mkdir", return_value=False):
            result = ex._mkdir(path="/no/such/dir")
        assert result["success"] is False

    def test_stat_file_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "stat_file", return_value=None):
            result = ex._stat_file(path="/missing.txt")
        assert result["success"] is False
        assert result["error"] == "stat_failed"

    def test_find_files_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "find_files", return_value=None):
            result = ex._find_files(pattern="*.log")
        assert result["success"] is False
        assert result["error"] == "find_failed"


# ---------------------------------------------------------------------------
# Archive success paths (lines 1372-1399)
# ---------------------------------------------------------------------------


class TestArchiveOps:
    """Lines 1372-1399 — archive create and extract success."""

    def test_archive_create_success(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "archive_create", return_value=True):
            result = ex._archive_create(archive_path="/tmp/out.zip", files=["a.txt", "b.txt"])
        assert result["success"] is True
        assert "out.zip" in result["output"]

    def test_archive_extract_success(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "archive_extract", return_value=True):
            result = ex._archive_extract(archive_path="/tmp/out.zip", dest_dir="/tmp/out")
        assert result["success"] is True
        assert "out.zip" in result["output"]


# ---------------------------------------------------------------------------
# _set_priority and _service_control (lines 1410-1412, 1444-1445)
# ---------------------------------------------------------------------------


class TestProcessControl:
    """Lines 1410-1412, 1444-1445 — set_priority and service_control dispatch."""

    def test_set_priority_success(self):
        ex = _make_executor()
        with patch("core.process_manager.set_priority", return_value=True):
            result = ex._set_priority(pid=1234, priority="normal")
        assert result["success"] is True
        assert "1234" in result["output"]

    def test_service_control_dispatch(self):
        ex = _make_executor()
        fake_result = {"success": True, "output": "Service started"}
        with patch("core.process_manager.service_control", return_value=fake_result):
            result = ex._service_control(name="Spooler", control_action="start")
        assert result == fake_result


# ---------------------------------------------------------------------------
# Registry actions (lines 1485, 1502-1504, 1513-1515)
# ---------------------------------------------------------------------------


class TestRegistryActions:
    """Lines 1485, 1502-1504, 1513-1515 — registry read/write/delete."""

    def test_registry_read_success(self):
        ex = _make_executor()
        with patch("core.registry.registry_read", return_value="some_value"):
            result = ex._registry_read(path=r"HKLM\Software\Test", value_name="Key")
        assert result["success"] is True
        assert result["output"] == "some_value"

    def test_registry_write_dispatches(self):
        ex = _make_executor()
        with patch("core.registry.registry_write", return_value=True):
            result = ex._registry_write(
                path=r"HKLM\Software\Test",
                value_name="Key",
                data="val",
            )
        assert result["success"] is True
        assert "Wrote" in result["output"]

    def test_registry_delete_dispatches(self):
        ex = _make_executor()
        with patch("core.registry.registry_delete", return_value=True):
            result = ex._registry_delete(path=r"HKLM\Software\Test")
        assert result["success"] is True
        assert "Deleted" in result["output"]


# ---------------------------------------------------------------------------
# SSH operations (lines 1765-1906)
# ---------------------------------------------------------------------------


class TestSshConnect:
    """Line 1765-1766 — _ssh_connect exception path."""

    def test_connect_exception_returns_failure(self):
        ex = _make_executor()
        with patch("core.netops.ssh_client.SSHClient", side_effect=OSError("refused")):
            result = ex._ssh_connect(hostname="10.0.0.1", username="admin")
        assert result["success"] is False
        assert result["error"] == "ssh_connect_failed"
        assert "refused" in result["output"]


class TestSshDisconnect:
    """Lines 1777-1778 — _ssh_disconnect with an active client."""

    def test_disconnect_with_client_closes(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["10.0.0.1"] = fake_client

        result = ex._ssh_disconnect(hostname="10.0.0.1")

        fake_client.close.assert_called_once()
        assert result["success"] is True
        assert "10.0.0.1" not in ex._ssh_clients


class TestSshRun:
    """Lines 1796-1797 — _ssh_run returns command result."""

    def test_ssh_run_success(self):
        ex = _make_executor()
        fake_client = MagicMock()
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.stdout = "output"
        fake_result.stderr = ""
        fake_result.exit_code = 0
        fake_client.run_command.return_value = fake_result
        ex._ssh_clients["router"] = fake_client

        result = ex._ssh_run(hostname="router", command="show version")

        assert result["success"] is True
        assert result["output"] == "output"
        fake_client.run_command.assert_called_once_with("show version", timeout=None)


class TestSshShow:
    """Lines 1829-1855 — _ssh_show body: parsers dispatched."""

    def _setup_ssh_show(self, what: str, success: bool = True):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        fake_cmd_result = MagicMock()
        fake_cmd_result.success = success
        fake_cmd_result.stdout = "raw output"
        fake_cmd_result.stderr = "err" if not success else ""

        fake_runner = MagicMock()
        fake_runner.show_version.return_value = fake_cmd_result
        fake_runner.show_interfaces.return_value = fake_cmd_result
        fake_runner.show_routing.return_value = fake_cmd_result
        fake_runner.show_arp.return_value = fake_cmd_result
        fake_runner.show_cpu.return_value = fake_cmd_result
        fake_runner.show_logging.return_value = fake_cmd_result
        fake_runner.show_running_config.return_value = fake_cmd_result

        return ex, fake_runner, fake_cmd_result

    def test_ssh_show_unknown_command(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        with patch("core.netops.command_runner.CommandRunner"):
            result = ex._ssh_show(hostname="router", what="unknown_cmd")

        assert result["success"] is False
        assert "Unknown show command" in result["output"]

    def test_ssh_show_version_with_parser(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        fake_run_result = MagicMock()
        fake_run_result.success = True
        fake_run_result.stdout = "Cisco IOS 15.2"

        mock_runner = MagicMock()
        mock_runner.show_version.return_value = fake_run_result

        with (
            patch("core.netops.command_runner.CommandRunner", return_value=mock_runner),
            patch("core.netops.output_parser.parse_version", return_value={"version": "15.2"}),
        ):
            result = ex._ssh_show(hostname="router", what="version")

        assert result["success"] is True
        assert result["output"] == {"version": "15.2"}

    def test_ssh_show_cpu_no_parser(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        fake_run_result = MagicMock()
        fake_run_result.success = True
        fake_run_result.stdout = "CPU: 5%"

        mock_runner = MagicMock()
        mock_runner.show_cpu.return_value = fake_run_result

        with patch("core.netops.command_runner.CommandRunner", return_value=mock_runner):
            result = ex._ssh_show(hostname="router", what="cpu")

        assert result["success"] is True
        assert "CPU" in result["output"]

    def test_ssh_show_failed_command_result(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        fake_run_result = MagicMock()
        fake_run_result.success = False
        fake_run_result.stdout = ""
        fake_run_result.stderr = "timeout"

        mock_runner = MagicMock()
        mock_runner.show_version.return_value = fake_run_result

        with (
            patch("core.netops.command_runner.CommandRunner", return_value=mock_runner),
            patch("core.netops.output_parser.parse_version", return_value={}),
        ):
            result = ex._ssh_show(hostname="router", what="version")

        assert result["success"] is False


class TestSshPing:
    """Lines 1878-1881 — _ssh_ping body."""

    def test_ssh_ping_success(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        fake_run_result = MagicMock()
        fake_run_result.stdout = "5 packets transmitted, 5 received"

        mock_runner = MagicMock()
        mock_runner.ping.return_value = fake_run_result

        parsed = {"success": True, "packets_sent": 5, "packets_received": 5}

        with (
            patch("core.netops.command_runner.CommandRunner", return_value=mock_runner),
            patch("core.netops.output_parser.parse_ping", return_value=parsed),
        ):
            result = ex._ssh_ping(hostname="router", target="8.8.8.8")

        assert result["success"] is True
        assert result["output"] == parsed


class TestSshTraceroute:
    """Lines 1903-1906 — _ssh_traceroute body."""

    def test_ssh_traceroute_dispatches(self):
        ex = _make_executor()
        fake_client = MagicMock()
        ex._ssh_clients["router"] = fake_client

        fake_run_result = MagicMock()
        fake_run_result.stdout = "1 192.168.1.1  1ms"

        mock_runner = MagicMock()
        mock_runner.traceroute.return_value = fake_run_result

        parsed = {"success": True, "hops": [{"hop": 1, "ip": "192.168.1.1"}]}

        with (
            patch("core.netops.command_runner.CommandRunner", return_value=mock_runner),
            patch("core.netops.output_parser.parse_traceroute", return_value=parsed),
        ):
            result = ex._ssh_traceroute(hostname="router", target="1.1.1.1")

        assert result["success"] is True
        assert result["output"] == parsed


# ---------------------------------------------------------------------------
# Memory actions (lines 1957-1983)
# ---------------------------------------------------------------------------


class TestMemorySearchException:
    """Lines 1957-1958 — _memory_search exception."""

    def test_search_exception_returns_failure(self):
        ex = _make_executor()
        fake_mem = MagicMock()
        fake_mem.query.side_effect = RuntimeError("db locked")
        ex._semantic_memory = fake_mem

        result = ex._memory_search(query="anything")

        assert result["success"] is False
        assert result["error"] == "memory_search_failed"


class TestMemoryForgetNotFound:
    """Lines 1982-1983 — _memory_forget when key is absent."""

    def test_forget_key_not_found_returns_false(self):
        ex = _make_executor()
        fake_mem = MagicMock()
        fake_mem.delete.return_value = False
        ex._semantic_memory = fake_mem

        result = ex._memory_forget(key="missing_key")

        assert result["success"] is False
        assert "not found" in result["output"].lower()


# ---------------------------------------------------------------------------
# _retry_last (lines 2035-2041)
# ---------------------------------------------------------------------------


class TestRetryLast:
    """Lines 2035-2041 — _retry_last finds failed action and re-runs it."""

    def test_retry_last_reruns_failed_action(self):
        ex = _make_executor()
        # Plant a failure in the log
        ex._log = [
            {"action": "screenshot", "params": {}, "success": True},
            {"action": "wait", "params": {"seconds": 1}, "success": False},
        ]

        with patch.object(
            ex, "execute_sync", return_value={"success": True, "output": "ok"}
        ) as mock_exec:
            result = ex._retry_last()

        mock_exec.assert_called_once_with({"action": "wait", "seconds": 1})
        assert result["success"] is True

    def test_retry_last_no_failures_returns_not_found(self):
        ex = _make_executor()
        ex._log = [{"action": "click", "params": {}, "success": True}]

        result = ex._retry_last()

        assert result["success"] is False
        assert "No failed action" in result["output"]


# ---------------------------------------------------------------------------
# _get_circuit_breakers (lines 2045-2047)
# ---------------------------------------------------------------------------


class TestGetCircuitBreakers:
    """Lines 2045-2047 — _get_circuit_breakers calls get_all_breaker_stats."""

    def test_returns_breaker_stats(self):
        ex = _make_executor()
        fake_stats = {"ssh": {"state": "CLOSED"}, "llm": {"state": "OPEN"}}
        with patch("core.resilience.get_all_breaker_stats", return_value=fake_stats):
            result = ex._get_circuit_breakers()
        assert result["success"] is True
        assert result["breakers"] == fake_stats


# ---------------------------------------------------------------------------
# Window control dispatch (lines 2124-2150)
# ---------------------------------------------------------------------------


class TestWindowControlDispatch:
    """Lines 2124-2150 — all window control methods delegate to core.window_control."""

    def test_resize_window(self):
        ex = _make_executor()
        with patch("core.window_control.resize_window", return_value={"success": True}) as m:
            ex._resize_window(title="Notepad", width=800, height=600)
        m.assert_called_once_with("Notepad", 800, 600)

    def test_move_window(self):
        ex = _make_executor()
        with patch("core.window_control.move_window", return_value={"success": True}) as m:
            ex._move_window(title="Notepad", x=100, y=200)
        m.assert_called_once_with("Notepad", 100, 200)

    def test_minimize_window(self):
        ex = _make_executor()
        with patch("core.window_control.minimize_window", return_value={"success": True}) as m:
            ex._minimize_window(title="Notepad")
        m.assert_called_once_with("Notepad")

    def test_maximize_window(self):
        ex = _make_executor()
        with patch("core.window_control.maximize_window", return_value={"success": True}) as m:
            ex._maximize_window(title="Notepad")
        m.assert_called_once_with("Notepad")

    def test_restore_window(self):
        ex = _make_executor()
        with patch("core.window_control.restore_window", return_value={"success": True}) as m:
            ex._restore_window(title="Notepad")
        m.assert_called_once_with("Notepad")

    def test_get_window_state(self):
        ex = _make_executor()
        fake_state = {"success": True, "state": "maximized"}
        with patch("core.window_control.get_window_state", return_value=fake_state) as m:
            result = ex._get_window_state(title="Notepad")
        m.assert_called_once_with("Notepad")
        assert result == fake_state


# ---------------------------------------------------------------------------
# HTTP client dispatch (lines 2190-2206)
# ---------------------------------------------------------------------------


class TestHttpClientDispatch:
    """Lines 2190-2191, 2205-2206 — http_post and http_download dispatch."""

    def test_http_post_dispatches(self):
        ex = _make_executor()
        fake_resp = {"success": True, "status_code": 200, "body": "created"}
        with patch("core.http_client.http_post", return_value=fake_resp) as m:
            result = ex._http_post(
                url="https://api.example.com/resource",
                json={"key": "val"},
            )
        m.assert_called_once()
        assert result == fake_resp

    def test_http_download_dispatches(self):
        ex = _make_executor()
        fake_resp = {"success": True, "bytes": 1024}
        with patch("core.http_client.http_download", return_value=fake_resp) as m:
            result = ex._http_download(
                url="https://example.com/file.zip",
                save_path="/tmp/file.zip",
            )
        m.assert_called_once()
        assert result == fake_resp


# ---------------------------------------------------------------------------
# File / process watcher dispatch (lines 2235-2249)
# ---------------------------------------------------------------------------


class TestFileWatcherDispatch:
    """Lines 2235-2236, 2248-2249 — watch_file_content and watch_process."""

    def test_watch_file_content_dispatches(self):
        ex = _make_executor()
        fake_resp = {"success": True, "found": True}
        with patch("core.file_watcher.watch_file_content", return_value=fake_resp) as m:
            result = ex._watch_file_content(path="/var/log/app.log", contains="ERROR")
        m.assert_called_once_with("/var/log/app.log", "ERROR", timeout=60.0)
        assert result == fake_resp

    def test_watch_process_dispatches(self):
        ex = _make_executor()
        fake_resp = {"success": True, "event": "start"}
        with patch("core.file_watcher.watch_process", return_value=fake_resp) as m:
            result = ex._watch_process(name="notepad.exe", event="start")
        m.assert_called_once_with("notepad.exe", event="start", pid=None, timeout=60.0)
        assert result == fake_resp


# ---------------------------------------------------------------------------
# Audio actions (lines 2277-2307)
# ---------------------------------------------------------------------------


class TestAudioDispatch:
    """Lines 2277-2307 — _listen, _volume_set, _mute_toggle, _list_voices."""

    def test_listen_success(self):
        ex = _make_executor()
        with patch("core.audio.listen", return_value="hello world"):
            result = ex._listen()
        assert result["success"] is True
        assert result["text"] == "hello world"

    def test_listen_no_speech(self):
        ex = _make_executor()
        with patch("core.audio.listen", return_value=None):
            result = ex._listen()
        assert result["success"] is False
        assert result["text"] == ""
        assert "No speech" in result["output"]

    def test_volume_set_success(self):
        ex = _make_executor()
        with patch("core.audio.volume_set", return_value=True):
            result = ex._volume_set(level=75)
        assert result["success"] is True
        assert result["level"] == 75

    def test_volume_set_failure(self):
        ex = _make_executor()
        with patch("core.audio.volume_set", return_value=False):
            result = ex._volume_set(level=75)
        assert result["success"] is False

    def test_mute_toggle_muted(self):
        ex = _make_executor()
        with patch("core.audio.mute_toggle", return_value=True):
            result = ex._mute_toggle()
        assert result["success"] is True
        assert result["muted"] is True
        assert "Muted" in result["output"]

    def test_mute_toggle_unmuted(self):
        ex = _make_executor()
        with patch("core.audio.mute_toggle", return_value=False):
            result = ex._mute_toggle()
        assert result["success"] is True
        assert result["muted"] is False
        assert "Unmuted" in result["output"]

    def test_list_voices_dispatches(self):
        ex = _make_executor()
        fake_voices = [{"name": "David", "id": "0"}, {"name": "Zira", "id": "1"}]
        with patch("core.audio.list_voices", return_value=fake_voices):
            result = ex._list_voices()
        assert result["success"] is True
        assert result["count"] == 2
        assert result["voices"] == fake_voices
