"""Tests for api/server.py v10/v11/v12 handlers and PTY helpers.

Covers:
- _handle_daemon_status/start/stop
- _handle_fleet_nodes/register/unregister
- _handle_jobs_list/submit/status/cancel
- _handle_memory_list/get/store/delete/search
- _handle_episodes_list/search
- _handle_conductor_run
- _handle_dashboard_index
- PTY helpers: _handle_ws_timeout, _handle_input_message, _handle_resize_message,
               _handle_ping_message, _process_ws_message, _cleanup_pty,
               _configure_master_fd_nonblocking, _read_pty
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.server import SentinelServer
from config import Config


def _run(coro):
    return asyncio.run(coro)


def _make_server():
    return SentinelServer(Config())


# ---------------------------------------------------------------------------
# _handle_dashboard_index
# ---------------------------------------------------------------------------


class TestHandleDashboardIndex:
    def test_returns_file_response(self):
        server = _make_server()
        with patch("api.server.os.path.join", return_value="/fake/index.html"):
            with patch("api.server.FileResponse") as mock_fr:
                mock_fr.return_value = "response"
                result = _run(server._handle_dashboard_index())
        assert result == "response"


# ---------------------------------------------------------------------------
# v10 Daemon handlers
# ---------------------------------------------------------------------------


class TestDaemonHandlers:
    def test_daemon_status_success(self):
        server = _make_server()
        mock_daemon = MagicMock()
        mock_daemon.get_status.return_value = {"running": False}
        with patch.dict(
            "sys.modules",
            {"core.server.daemon": MagicMock(SentinelDaemon=MagicMock(return_value=mock_daemon))},
        ):
            result = _run(server._handle_daemon_status())
        assert result["success"] is True
        assert "data" in result

    def test_daemon_status_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.daemon": MagicMock(
                    SentinelDaemon=MagicMock(side_effect=RuntimeError("fail"))
                )
            },
        ):
            result = _run(server._handle_daemon_status())
        assert result["success"] is False
        assert "fail" in result["error"]

    def test_daemon_start_success(self):
        server = _make_server()
        mock_daemon = MagicMock()
        mock_daemon.start.return_value = {"started": True}
        with patch.dict(
            "sys.modules",
            {"core.server.daemon": MagicMock(SentinelDaemon=MagicMock(return_value=mock_daemon))},
        ):
            result = _run(server._handle_daemon_start())
        assert result["success"] is True

    def test_daemon_start_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.daemon": MagicMock(
                    SentinelDaemon=MagicMock(side_effect=OSError("no daemon"))
                )
            },
        ):
            result = _run(server._handle_daemon_start())
        assert result["success"] is False
        assert "no daemon" in result["error"]

    def test_daemon_stop_success(self):
        server = _make_server()
        mock_daemon = MagicMock()
        mock_daemon.stop.return_value = {"stopped": True}
        with patch.dict(
            "sys.modules",
            {"core.server.daemon": MagicMock(SentinelDaemon=MagicMock(return_value=mock_daemon))},
        ):
            result = _run(server._handle_daemon_stop())
        assert result["success"] is True

    def test_daemon_stop_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.daemon": MagicMock(
                    SentinelDaemon=MagicMock(side_effect=ValueError("err"))
                )
            },
        ):
            result = _run(server._handle_daemon_stop())
        assert result["success"] is False


# ---------------------------------------------------------------------------
# v10 Fleet handlers
# ---------------------------------------------------------------------------


class TestFleetHandlers:
    def test_fleet_nodes_success(self):
        server = _make_server()
        mock_fleet = MagicMock()
        mock_fleet.list_nodes.return_value = [{"id": "n1"}]
        with patch.dict(
            "sys.modules",
            {"core.server.fleet": MagicMock(FleetManager=MagicMock(return_value=mock_fleet))},
        ):
            result = _run(server._handle_fleet_nodes())
        assert result["success"] is True
        assert result["data"] == [{"id": "n1"}]

    def test_fleet_nodes_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {"core.server.fleet": MagicMock(FleetManager=MagicMock(side_effect=RuntimeError("x")))},
        ):
            result = _run(server._handle_fleet_nodes())
        assert result["success"] is False

    def test_fleet_register_success(self):
        server = _make_server()
        mock_fleet = MagicMock()
        mock_fleet.register_node.return_value = {"success": True, "node_id": "n1"}
        with patch.dict(
            "sys.modules",
            {"core.server.fleet": MagicMock(FleetManager=MagicMock(return_value=mock_fleet))},
        ):
            result = _run(
                server._handle_fleet_register(
                    {
                        "node_id": "n1",
                        "hostname": "host",
                        "ip_address": "1.2.3.4",
                        "role": "agent",
                        "tags": ["tag1"],
                    }
                )
            )
        assert result["success"] is True

    def test_fleet_register_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {"core.server.fleet": MagicMock(FleetManager=MagicMock(side_effect=ValueError("bad")))},
        ):
            result = _run(server._handle_fleet_register({}))
        assert result["success"] is False

    def test_fleet_unregister_success(self):
        server = _make_server()
        mock_fleet = MagicMock()
        mock_fleet.unregister_node.return_value = {"success": True}
        with patch.dict(
            "sys.modules",
            {"core.server.fleet": MagicMock(FleetManager=MagicMock(return_value=mock_fleet))},
        ):
            result = _run(server._handle_fleet_unregister({"node_id": "n1"}))
        assert result["success"] is True

    def test_fleet_unregister_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.fleet": MagicMock(
                    FleetManager=MagicMock(side_effect=RuntimeError("err"))
                )
            },
        ):
            result = _run(server._handle_fleet_unregister({"node_id": "n1"}))
        assert result["success"] is False


# ---------------------------------------------------------------------------
# v10 Job handlers
# ---------------------------------------------------------------------------


class TestJobHandlers:
    def test_jobs_list_success(self):
        server = _make_server()
        mock_queue = MagicMock()
        mock_queue.list_jobs.return_value = [{"id": "j1"}]
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(return_value=mock_queue))},
        ):
            result = _run(server._handle_jobs_list())
        assert result["success"] is True
        assert result["data"] == [{"id": "j1"}]

    def test_jobs_list_with_status_filter(self):
        server = _make_server()
        mock_queue = MagicMock()
        mock_queue.list_jobs.return_value = []
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(return_value=mock_queue))},
        ):
            result = _run(server._handle_jobs_list(status="pending"))
        mock_queue.list_jobs.assert_called_once_with(status="pending")
        assert result["success"] is True

    def test_jobs_list_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.job_queue": MagicMock(
                    JobQueue=MagicMock(side_effect=RuntimeError("fail"))
                )
            },
        ):
            result = _run(server._handle_jobs_list())
        assert result["success"] is False

    def test_jobs_submit_success(self):
        server = _make_server()
        mock_queue = MagicMock()
        mock_queue.submit.return_value = "job-123"
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(return_value=mock_queue))},
        ):
            result = _run(server._handle_jobs_submit({"goal": "do thing", "priority": 1}))
        assert result["success"] is True
        assert result["job_id"] == "job-123"

    def test_jobs_submit_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(side_effect=ValueError("x")))},
        ):
            result = _run(server._handle_jobs_submit({}))
        assert result["success"] is False

    def test_job_status_found(self):
        server = _make_server()
        mock_queue = MagicMock()
        mock_queue.get_job.return_value = {"id": "j1", "status": "running"}
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(return_value=mock_queue))},
        ):
            result = _run(server._handle_job_status("j1"))
        assert result["success"] is True
        assert result["data"]["id"] == "j1"

    def test_job_status_not_found(self):
        server = _make_server()
        mock_queue = MagicMock()
        mock_queue.get_job.return_value = None
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(return_value=mock_queue))},
        ):
            result = _run(server._handle_job_status("missing"))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_job_status_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.job_queue": MagicMock(
                    JobQueue=MagicMock(side_effect=RuntimeError("err"))
                )
            },
        ):
            result = _run(server._handle_job_status("j1"))
        assert result["success"] is False

    def test_job_cancel_success(self):
        server = _make_server()
        mock_queue = MagicMock()
        mock_queue.cancel.return_value = True
        with patch.dict(
            "sys.modules",
            {"core.server.job_queue": MagicMock(JobQueue=MagicMock(return_value=mock_queue))},
        ):
            result = _run(server._handle_job_cancel("j1"))
        assert result["success"] is True

    def test_job_cancel_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.server.job_queue": MagicMock(
                    JobQueue=MagicMock(side_effect=RuntimeError("boom"))
                )
            },
        ):
            result = _run(server._handle_job_cancel("j1"))
        assert result["success"] is False


# ---------------------------------------------------------------------------
# v11 Memory handlers
# ---------------------------------------------------------------------------


class TestMemoryHandlers:
    def test_memory_list_success(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.list_keys.return_value = ["k1", "k2"]
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_list())
        assert result["success"] is True
        assert result["count"] == 2

    def test_memory_list_with_category(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.list_keys.return_value = ["k1"]
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_list(category="network"))
        mock_mem.list_keys.assert_called_once_with(category="network")
        assert result["success"] is True

    def test_memory_list_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.semantic": MagicMock(
                    SemanticMemory=MagicMock(side_effect=RuntimeError("fail"))
                )
            },
        ):
            result = _run(server._handle_memory_list())
        assert result["success"] is False

    def test_memory_get_found(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.recall.return_value = {"value": "192.168.1.1"}
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_get("gateway_ip"))
        assert result["success"] is True
        assert result["data"]["value"] == "192.168.1.1"

    def test_memory_get_not_found(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.recall.return_value = None
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_get("missing_key"))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_memory_get_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.semantic": MagicMock(
                    SemanticMemory=MagicMock(side_effect=RuntimeError("x"))
                )
            },
        ):
            result = _run(server._handle_memory_get("k"))
        assert result["success"] is False

    def test_memory_store_success(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.store.return_value = "fact-42"
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(
                server._handle_memory_store({"key": "k", "value": "v", "category": "net"})
            )
        assert result["success"] is True
        assert result["fact_id"] == "fact-42"

    def test_memory_store_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.semantic": MagicMock(
                    SemanticMemory=MagicMock(side_effect=RuntimeError("x"))
                )
            },
        ):
            result = _run(server._handle_memory_store({}))
        assert result["success"] is False

    def test_memory_delete_success(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.delete.return_value = True
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_delete("old_key"))
        assert result["success"] is True

    def test_memory_delete_not_found(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.delete.return_value = False
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_delete("ghost"))
        assert result["success"] is False

    def test_memory_delete_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.semantic": MagicMock(
                    SemanticMemory=MagicMock(side_effect=RuntimeError("x"))
                )
            },
        ):
            result = _run(server._handle_memory_delete("k"))
        assert result["success"] is False

    def test_memory_search_success(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.query.return_value = [{"key": "k1", "value": "v1"}]
        with patch.dict(
            "sys.modules",
            {"core.memory.semantic": MagicMock(SemanticMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_memory_search(query="net", limit=10))
        assert result["success"] is True
        assert result["count"] == 1

    def test_memory_search_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.semantic": MagicMock(
                    SemanticMemory=MagicMock(side_effect=RuntimeError("x"))
                )
            },
        ):
            result = _run(server._handle_memory_search())
        assert result["success"] is False

    def test_episodes_list_success(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.recall.return_value = [{"ts": "2026-01-01", "text": "did stuff"}]
        with patch.dict(
            "sys.modules",
            {"core.memory.episodic": MagicMock(EpisodicMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_episodes_list(limit=5))
        assert result["success"] is True
        assert result["count"] == 1

    def test_episodes_list_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.episodic": MagicMock(
                    EpisodicMemory=MagicMock(side_effect=RuntimeError("x"))
                )
            },
        ):
            result = _run(server._handle_episodes_list())
        assert result["success"] is False

    def test_episodes_search_success(self):
        server = _make_server()
        mock_mem = MagicMock()
        mock_mem.search.return_value = [{"text": "clicked button"}]
        with patch.dict(
            "sys.modules",
            {"core.memory.episodic": MagicMock(EpisodicMemory=MagicMock(return_value=mock_mem))},
        ):
            result = _run(server._handle_episodes_search(query="click", limit=5))
        assert result["success"] is True
        assert result["count"] == 1

    def test_episodes_search_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.memory.episodic": MagicMock(
                    EpisodicMemory=MagicMock(side_effect=RuntimeError("x"))
                )
            },
        ):
            result = _run(server._handle_episodes_search())
        assert result["success"] is False


# ---------------------------------------------------------------------------
# v12 Conductor handler
# ---------------------------------------------------------------------------


class TestConductorHandler:
    def test_conductor_run_success(self):
        server = _make_server()
        mock_conductor = MagicMock()
        mock_conductor.run = AsyncMock(return_value={"status": "done", "steps": 3})
        with patch.dict(
            "sys.modules",
            {
                "core.conductor.coordinator": MagicMock(
                    Conductor=MagicMock(return_value=mock_conductor)
                )
            },
        ):
            result = _run(server._handle_conductor_run({"goal": "restart service", "timeout": 30}))
        assert result["success"] is True
        assert result["data"]["status"] == "done"

    def test_conductor_run_exception(self):
        server = _make_server()
        with patch.dict(
            "sys.modules",
            {
                "core.conductor.coordinator": MagicMock(
                    Conductor=MagicMock(side_effect=RuntimeError("timeout"))
                )
            },
        ):
            result = _run(server._handle_conductor_run({"goal": "do thing"}))
        assert result["success"] is False
        assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# PTY helper methods
# ---------------------------------------------------------------------------


class TestPtyHelpers:
    """Tests for PTY WebSocket helper methods (Unix only)."""

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY not available on Windows")
    def test_configure_master_fd_nonblocking(self):
        server = _make_server()
        r, w = os.pipe()
        try:
            import api.server as mod

            if mod._HAS_PTY:
                server._configure_master_fd_nonblocking(r)
                import fcntl

                flags = fcntl.fcntl(r, fcntl.F_GETFL)
                assert flags & os.O_NONBLOCK
        finally:
            os.close(r)
            os.close(w)

    def test_configure_master_fd_nonblocking_no_pty(self):
        server = _make_server()
        import api.server as mod

        original = mod._HAS_PTY
        mod._HAS_PTY = False
        try:
            # Should return immediately without error
            server._configure_master_fd_nonblocking(999)
        finally:
            mod._HAS_PTY = original

    @pytest.mark.asyncio
    async def test_handle_ws_timeout_success(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        result = await server._handle_ws_timeout(ws)
        assert result is True
        ws.send_json.assert_called_once_with({"type": "ping"})

    @pytest.mark.asyncio
    async def test_handle_ws_timeout_connection_error(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=ConnectionError("dead"))
        result = await server._handle_ws_timeout(ws)
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_ws_timeout_runtime_error(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=RuntimeError("closed"))
        result = await server._handle_ws_timeout(ws)
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_ws_timeout_os_error(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=OSError("broken pipe"))
        result = await server._handle_ws_timeout(ws)
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_input_message_success(self):
        server = _make_server()
        r, w = os.pipe()
        try:
            result = await server._handle_input_message(w, {"data": "hello"})
            assert result is True
            data = os.read(r, 100)
            assert data == b"hello"
        finally:
            os.close(r)
            os.close(w)

    @pytest.mark.asyncio
    async def test_handle_input_message_os_error(self):
        server = _make_server()
        result = await server._handle_input_message(-1, {"data": "hi"})
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="fcntl/termios not on Windows")
    async def test_handle_resize_message_success(self):
        server = _make_server()
        import api.server as mod

        if not mod._HAS_PTY:
            pytest.skip("PTY not available")
        r, w = os.pipe()
        try:
            result = await server._handle_resize_message(r, {"rows": 30, "cols": 100})
            assert result is True
        except OSError:
            pass  # pipe doesn't support ioctl — that's fine, still covers the call
        finally:
            os.close(r)
            os.close(w)

    @pytest.mark.asyncio
    async def test_handle_resize_message_os_error(self):
        server = _make_server()
        import api.server as mod

        if not mod._HAS_PTY:
            pytest.skip("PTY not available")
        with patch("fcntl.ioctl", side_effect=OSError("bad fd")):
            result = await server._handle_resize_message(5, {"rows": 24, "cols": 80})
        assert result is True  # resize failure is non-critical

    @pytest.mark.asyncio
    async def test_handle_ping_message_success(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        result = await server._handle_ping_message(ws)
        assert result is True
        ws.send_json.assert_called_once_with({"type": "pong"})

    @pytest.mark.asyncio
    async def test_handle_ping_message_error(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=ConnectionError("dead"))
        result = await server._handle_ping_message(ws)
        assert result is False

    @pytest.mark.asyncio
    async def test_process_ws_message_input(self):
        server = _make_server()
        r, w = os.pipe()
        try:
            result = await server._process_ws_message(w, None, {"type": "input", "data": "ls\n"})
            assert result is True
        finally:
            os.close(r)
            os.close(w)

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="fcntl not on Windows")
    async def test_process_ws_message_resize(self):
        server = _make_server()
        import api.server as mod

        if not mod._HAS_PTY:
            pytest.skip("PTY not available")
        ws = MagicMock()
        with patch("fcntl.ioctl", side_effect=OSError("ioctl fail")):
            result = await server._process_ws_message(
                5, ws, {"type": "resize", "rows": 24, "cols": 80}
            )
        assert result is True  # resize failure is non-critical

    @pytest.mark.asyncio
    async def test_process_ws_message_ping(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        result = await server._process_ws_message(0, ws, {"type": "ping"})
        assert result is True

    @pytest.mark.asyncio
    async def test_process_ws_message_unknown_type(self):
        server = _make_server()
        ws = MagicMock()
        result = await server._process_ws_message(0, ws, {"type": "unknown"})
        assert result is True

    @pytest.mark.asyncio
    async def test_cleanup_pty(self):
        server = _make_server()
        # Test with invalid pid/fd — all exceptions should be swallowed
        await server._cleanup_pty(child_pid=99999999, master_fd=-1)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is Unix-only")
    async def test_cleanup_pty_real_process(self):
        server = _make_server()
        # Fork a real process to clean up
        r, w = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(r)
            os.close(w)
            os._exit(0)
        os.close(r)
        await server._cleanup_pty(child_pid=child_pid, master_fd=w)

    @pytest.mark.asyncio
    async def test_read_pty_empty_data_breaks(self):
        server = _make_server()
        r, w = os.pipe()
        os.close(w)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        # Empty read (EOF) should break the loop
        await server._read_pty(r, ws)
        os.close(r)

    @pytest.mark.asyncio
    async def test_read_pty_os_error_breaks(self):
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        # Invalid fd raises OSError → loop breaks
        await server._read_pty(-1, ws)


# ---------------------------------------------------------------------------
# Additional _read_pty coverage
# ---------------------------------------------------------------------------


class TestReadPtyAdditional:
    @pytest.mark.asyncio
    async def test_read_pty_sends_data(self):
        """Hit the ws.send_json line by writing real data to a pipe."""
        server = _make_server()
        r, w = os.pipe()
        os.write(w, b"hello from pty")
        os.close(w)

        sent = []
        ws = MagicMock()

        async def fake_send_json(msg):
            sent.append(msg)

        ws.send_json = fake_send_json

        await server._read_pty(r, ws)
        os.close(r)
        assert any(m.get("type") == "data" for m in sent)

    @pytest.mark.asyncio
    async def test_read_pty_blocking_io_error(self):
        """BlockingIOError → asyncio.sleep path (line 673)."""
        server = _make_server()
        ws = MagicMock()
        ws.send_json = AsyncMock()

        call_count = 0

        def fake_read(fd, n):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise BlockingIOError
            return b""  # EOF on second call → break

        with patch("os.read", side_effect=fake_read):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await server._read_pty(0, ws)
        mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_read_pty_interrupted_error(self):
        """InterruptedError → asyncio.sleep path (same line 673)."""
        server = _make_server()
        ws = MagicMock()
        call_count = 0

        def fake_read(fd, n):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise InterruptedError
            return b""

        with patch("os.read", side_effect=fake_read):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await server._read_pty(0, ws)
        mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_read_pty_connection_error_breaks(self):
        """ws.send_json raises ConnectionError → loop breaks (line 676)."""
        server = _make_server()
        r, w = os.pipe()
        os.write(w, b"data")
        os.close(w)

        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=ConnectionError("dead"))

        await server._read_pty(r, ws)
        os.close(r)

    @pytest.mark.asyncio
    async def test_read_pty_runtime_error_breaks(self):
        """ws.send_json raises RuntimeError → loop breaks (line 677)."""
        server = _make_server()
        r, w = os.pipe()
        os.write(w, b"data")
        os.close(w)

        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=RuntimeError("closed"))

        await server._read_pty(r, ws)
        os.close(r)

    @pytest.mark.asyncio
    async def test_read_pty_timeout_error_breaks(self):
        """asyncio.wait_for raises TimeoutError → loop breaks (line 676)."""
        server = _make_server()
        r, w = os.pipe()
        os.write(w, b"data")
        os.close(w)

        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=asyncio.TimeoutError())

        await server._read_pty(r, ws)
        os.close(r)

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY not on Windows")
    @pytest.mark.asyncio
    async def test_handle_resize_message_pty_success(self):
        """Hit the return True after successful ioctl (line 706)."""
        import api.server as mod

        if not mod._HAS_PTY:
            pytest.skip("PTY not available")
        import pty as _pty

        server = _make_server()
        master_fd, slave_fd = _pty.openpty()
        try:
            result = await server._handle_resize_message(master_fd, {"rows": 30, "cols": 120})
            assert result is True
        finally:
            os.close(master_fd)
            os.close(slave_fd)


# ---------------------------------------------------------------------------
# _read_ws coverage
# ---------------------------------------------------------------------------


class TestReadWs:
    @pytest.mark.asyncio
    async def test_read_ws_input_message(self):
        """Happy path: receive an input message and process it."""
        server = _make_server()
        r, w = os.pipe()

        ws = MagicMock()
        call_count = 0

        async def fake_receive_text():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"type": "input", "data": "hi"}'
            raise ConnectionError("done")

        ws.receive_text = fake_receive_text

        await server._read_ws(w, ws)
        data = os.read(r, 100)
        assert data == b"hi"
        os.close(r)
        os.close(w)

    @pytest.mark.asyncio
    async def test_read_ws_timeout_then_ping_fails(self):
        """TimeoutError → _handle_ws_timeout fails → break."""
        server = _make_server()
        ws = MagicMock()

        async def fake_receive():
            raise asyncio.TimeoutError()

        ws.receive_text = fake_receive
        ws.send_json = AsyncMock(side_effect=OSError("dead"))  # ping fails

        await server._read_ws(0, ws)

    @pytest.mark.asyncio
    async def test_read_ws_timeout_then_ping_ok_then_connection_error(self):
        """TimeoutError → ping OK → continue → ConnectionError → break."""
        server = _make_server()
        ws = MagicMock()
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise asyncio.TimeoutError()
            raise ConnectionError("gone")

        ws.receive_text = fake_receive
        ws.send_json = AsyncMock()  # ping succeeds

        await server._read_ws(0, ws)

    @pytest.mark.asyncio
    async def test_read_ws_json_decode_error_continues(self):
        """JSONDecodeError → continue, then connection break."""
        server = _make_server()
        ws = MagicMock()
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not-valid-json"
            raise ConnectionError("done")

        ws.receive_text = fake_receive

        await server._read_ws(0, ws)

    @pytest.mark.asyncio
    async def test_read_ws_connection_error_breaks(self):
        """ConnectionError from receive_text → break."""
        server = _make_server()
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=ConnectionError("closed"))

        await server._read_ws(0, ws)

    @pytest.mark.asyncio
    async def test_read_ws_runtime_error_breaks(self):
        """RuntimeError from receive_text → break."""
        server = _make_server()
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=RuntimeError("starlette closed"))

        await server._read_ws(0, ws)

    @pytest.mark.asyncio
    async def test_read_ws_process_returns_false_breaks(self):
        """_process_ws_message returns False → break loop."""
        server = _make_server()
        ws = MagicMock()
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"type": "input", "data": ""}'
            raise ConnectionError("done")

        ws.receive_text = fake_receive

        # Patch _process_ws_message to return False
        with patch.object(
            server, "_process_ws_message", new_callable=AsyncMock, return_value=False
        ):
            await server._read_ws(0, ws)
