"""Gap tests for api/server.py — covers lines 60-63, 610-652, 772-807.

60-63:   ImportError except block (PTY modules unavailable → set to None)
610-652: _setup_pty_child() — os.setsid, fcntl.ioctl, dup2, execvpe, _exit
772-807: _handle_terminal_ws() — no-PTY error path + parent process path
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.server as server_mod
from api.server import SentinelServer
from config import Config


def _make_server() -> SentinelServer:
    return SentinelServer(Config())


# ── lines 60-63 — ImportError → fcntl/pty/termios = None ─────────────────


class TestPtyImportErrorBranch:
    """Lines 60-63 — module-level ImportError sets PTY names to None."""

    def test_pty_import_error_sets_has_pty_false(self):
        """Reload api.server with pty blocked → _HAS_PTY becomes False."""
        import importlib

        orig_has_pty = server_mod._HAS_PTY
        orig_fcntl = sys.modules.get("fcntl")
        orig_pty = sys.modules.get("pty")
        orig_termios = sys.modules.get("termios")

        try:
            # Setting a sys.modules entry to None makes `import X` raise ImportError
            with patch.dict(sys.modules, {"pty": None}):
                importlib.reload(server_mod)
                assert server_mod._HAS_PTY is False
                assert server_mod.pty is None
        finally:
            # Restore originals in sys.modules
            for name, orig in [("fcntl", orig_fcntl), ("pty", orig_pty), ("termios", orig_termios)]:
                if orig is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = orig
            # Reload to return the module to its normal state
            importlib.reload(server_mod)
            assert server_mod._HAS_PTY is orig_has_pty


# ── lines 610-652 — _setup_pty_child ──────────────────────────────────────


class TestSetupPtyChild:
    """Lines 610-652 — _setup_pty_child() all paths."""

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    def test_setup_pty_child_exec_oserror_calls_exit(self):
        """Lines 645-652 — all shells fail with OSError → os._exit(1) called."""
        server = _make_server()
        mock_exit = MagicMock()

        with (
            patch("api.server.os.close"),
            patch("api.server.os.setsid"),
            patch("api.server.os.dup2"),
            patch("api.server.fcntl"),
            patch("api.server.termios"),
            patch("api.server.os.path.isfile", return_value=True),
            patch("api.server.os.execvpe", side_effect=OSError("exec failed")),
            patch("api.server.os._exit", mock_exit),
        ):
            server._setup_pty_child(slave_fd=5)

        mock_exit.assert_called_once_with(1)

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    def test_setup_pty_child_no_shells_found_falls_through_to_exit(self):
        """Lines 646-650 — no shells found → last-resort execvpe raises → _exit."""
        server = _make_server()
        mock_exit = MagicMock()

        with (
            patch("api.server.os.close"),
            patch("api.server.os.setsid"),
            patch("api.server.os.dup2"),
            patch("api.server.fcntl"),
            patch("api.server.termios"),
            patch("api.server.os.path.isfile", return_value=False),
            patch("api.server.os.execvpe", side_effect=OSError("no shell")),
            patch("api.server.os._exit", mock_exit),
        ):
            server._setup_pty_child(slave_fd=3)

        mock_exit.assert_called_once_with(1)

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    def test_setup_pty_child_slave_fd_le_2_skips_second_close(self):
        """slave_fd <= 2 → the guarded close (after dup2, `if slave_fd > 2`)
        is skipped, AND there is no top-level close anymore (the premature
        os.close(slave_fd) that caused the Bad-fd crash was removed). So with
        slave_fd=1, os.close is never called at all."""
        server = _make_server()
        close_calls = []

        def track_close(fd):
            close_calls.append(fd)

        mock_exit = MagicMock()

        with (
            patch("api.server.os.close", side_effect=track_close),
            patch("api.server.os.setsid"),
            patch("api.server.os.dup2"),
            patch("api.server.fcntl"),
            patch("api.server.termios"),
            patch("api.server.os.path.isfile", return_value=False),
            patch("api.server.os.execvpe", side_effect=OSError("no shell")),
            patch("api.server.os._exit", mock_exit),
        ):
            server._setup_pty_child(slave_fd=1)

        # No close at all: no premature top-level close (removed), and the
        # post-dup2 close is guarded by `slave_fd > 2` which 1 fails.
        assert close_calls == []
        mock_exit.assert_called_once_with(1)


# ── lines 772-807 — _handle_terminal_ws ───────────────────────────────────


class TestHandleTerminalWs:
    """Lines 772-807 — _handle_terminal_ws() no-PTY and parent-process paths."""

    @pytest.mark.asyncio
    async def test_no_pty_sends_error_and_closes(self):
        """Lines 774-782 — _HAS_PTY is False → send error, close."""
        server = _make_server()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        orig = server_mod._HAS_PTY
        try:
            server_mod._HAS_PTY = False
            await server._handle_terminal_ws(ws)
        finally:
            server_mod._HAS_PTY = orig

        ws.accept.assert_called_once()
        ws.send_json.assert_called_once()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "error"
        assert "Windows" in sent["data"] or "PTY" in sent["data"]
        ws.close.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    async def test_parent_process_path_runs_and_cleans_up(self):
        """Lines 790-807 — parent process path: tasks run, cleanup called."""
        server = _make_server()
        ws = MagicMock()
        ws.accept = AsyncMock()

        cleanup_called = []

        async def _fake_cleanup(child_pid, master_fd):
            cleanup_called.append((child_pid, master_fd))

        async def _fake_read_pty(master_fd, ws):
            return

        async def _fake_read_ws(master_fd, ws):
            return

        mock_pty = MagicMock()
        mock_pty.openpty.return_value = (10, 11)

        with (
            patch("api.server.pty", mock_pty),
            patch("os.fork", return_value=42),
            patch("os.close"),
            patch.object(server, "_configure_master_fd_nonblocking"),
            patch.object(server, "_cleanup_pty", side_effect=_fake_cleanup),
            patch.object(server, "_read_pty", _fake_read_pty),
            patch.object(server, "_read_ws", _fake_read_ws),
        ):
            await server._handle_terminal_ws(ws)

        ws.accept.assert_called_once()
        assert len(cleanup_called) == 1
        assert cleanup_called[0] == (42, 10)

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    async def test_parent_process_handles_websocket_disconnect(self):
        """Lines 804-805 — WebSocketDisconnect in task wait is caught."""
        from fastapi import WebSocketDisconnect

        server = _make_server()
        ws = MagicMock()
        ws.accept = AsyncMock()

        async def _fake_cleanup(child_pid, master_fd):
            pass

        async def _raises_disconnect(master_fd, ws_arg):
            raise WebSocketDisconnect(code=1001)

        async def _fake_read_ws(master_fd, ws_arg):
            return

        mock_pty = MagicMock()
        mock_pty.openpty.return_value = (10, 11)

        with (
            patch("api.server.pty", mock_pty),
            patch("os.fork", return_value=42),
            patch("os.close"),
            patch.object(server, "_configure_master_fd_nonblocking"),
            patch.object(server, "_cleanup_pty", side_effect=_fake_cleanup),
            patch.object(server, "_read_pty", _raises_disconnect),
            patch.object(server, "_read_ws", _fake_read_ws),
        ):
            # Should not raise — exception is caught
            await server._handle_terminal_ws(ws)

        ws.accept.assert_called_once()


# ── line 627 — HOME missing from environment ─────────────────────────────────


class TestSetupPtyChildHomeEnv:
    """Line 627 — env["HOME"] assigned when HOME absent from os.environ."""

    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    def test_home_not_in_env_sets_home(self):
        server = _make_server()
        mock_exit = MagicMock()

        # Strip HOME from the environment copy that _setup_pty_child sees
        env_without_home = {k: v for k, v in __import__("os").environ.items() if k != "HOME"}

        with (
            patch("api.server.os.close"),
            patch("api.server.os.setsid"),
            patch("api.server.os.dup2"),
            patch("api.server.fcntl"),
            patch("api.server.termios"),
            patch("api.server.os.environ", env_without_home),
            patch("api.server.os.path.isfile", return_value=False),
            patch("api.server.os.execvpe", side_effect=OSError("no shell")),
            patch("api.server.os._exit", mock_exit),
        ):
            server._setup_pty_child(slave_fd=5)

        mock_exit.assert_called_once_with(1)


# ── line 789 — child process branch calls _setup_pty_child ───────────────────


class TestHandleTerminalWsChildBranch:
    """Line 789 — os.fork() == 0 path: _setup_pty_child is called."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    async def test_child_branch_calls_setup_pty_child(self):
        server = _make_server()
        ws = MagicMock()
        ws.accept = AsyncMock()

        mock_setup = MagicMock()
        mock_pty = MagicMock()
        mock_pty.openpty.return_value = (10, 11)

        with (
            patch("api.server.pty", mock_pty),
            patch("api.server.os.fork", return_value=0),
            patch("api.server.os.close"),
            patch.object(server, "_setup_pty_child", mock_setup),
        ):
            await server._handle_terminal_ws(ws)

        mock_setup.assert_called_once_with(11)


# ── line 803 — pending task cancel ───────────────────────────────────────────


class TestHandleTerminalWsPendingCancel:
    """Line 803 — pending tasks cancelled after asyncio.wait(FIRST_COMPLETED)."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    async def test_pending_task_is_cancelled(self):
        import asyncio as _asyncio

        server = _make_server()
        ws = MagicMock()
        ws.accept = AsyncMock()

        completed_event = _asyncio.Event()

        async def _returns_instantly(master_fd, ws_arg):
            completed_event.set()

        async def _blocks_until_cancelled(master_fd, ws_arg):
            await _asyncio.sleep(9999)

        async def _cleanup(child_pid, master_fd):
            pass

        mock_pty = MagicMock()
        mock_pty.openpty.return_value = (10, 11)

        with (
            patch("api.server.pty", mock_pty),
            patch("api.server.os.fork", return_value=42),
            patch("api.server.os.close"),
            patch.object(server, "_configure_master_fd_nonblocking"),
            patch.object(server, "_cleanup_pty", side_effect=_cleanup),
            patch.object(server, "_read_pty", _returns_instantly),
            patch.object(server, "_read_ws", _blocks_until_cancelled),
        ):
            await server._handle_terminal_ws(ws)

        # If we reach here without hanging, the pending task was cancelled correctly


# ── lines 804-805 — except (WebSocketDisconnect, ...) block ──────────────────


class TestHandleTerminalWsExceptBlock:
    """Lines 804-805 — RuntimeError raised by asyncio.wait caught by except clause."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="PTY only on Unix")
    async def test_runtime_error_in_wait_is_caught(self):
        server = _make_server()
        ws = MagicMock()
        ws.accept = AsyncMock()

        cleanup_called = []

        async def _cleanup(child_pid, master_fd):
            cleanup_called.append(True)

        mock_pty = MagicMock()
        mock_pty.openpty.return_value = (10, 11)

        # Patch asyncio.wait itself to raise RuntimeError so the except clause fires
        async def _wait_raises(*args, **kwargs):
            raise RuntimeError("event loop closed")

        with (
            patch("api.server.pty", mock_pty),
            patch("api.server.os.fork", return_value=42),
            patch("api.server.os.close"),
            patch.object(server, "_configure_master_fd_nonblocking"),
            patch.object(server, "_cleanup_pty", side_effect=_cleanup),
            patch("api.server.asyncio.wait", side_effect=_wait_raises),
        ):
            # Should not propagate — caught by except (lines 804-805)
            await server._handle_terminal_ws(ws)

        # finally block still runs
        assert cleanup_called
