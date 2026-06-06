"""Tests for api.server WebSocket/PTY helper methods.

Covers the terminal WebSocket handler methods that were previously untested:
_handle_dashboard_index, _configure_master_fd_nonblocking, _read_pty,
_handle_ws_timeout, _handle_input_message, _handle_resize_message,
_handle_ping_message, _process_ws_message, _read_ws, _cleanup_pty.

_setup_pty_child and _handle_terminal_ws require actual process forking
and are marked pragma: no cover in those specific call sites.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import signal
import struct
import termios
from unittest.mock import AsyncMock, patch

import pytest

from api.server import SentinelServer
from config import Config


def _make_server() -> SentinelServer:
    return SentinelServer(Config())


# ── AsyncMock WebSocket ───────────────────────────────────────────────────────


def _make_ws() -> AsyncMock:
    """Minimal fake WebSocket."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


# ── _handle_dashboard_index ───────────────────────────────────────────────────


class TestHandleDashboardIndex:
    @pytest.mark.asyncio
    async def test_returns_file_response_for_index_html(self):
        srv = _make_server()

        with patch("api.server.FileResponse", return_value="response_obj") as mock_fr:
            result = await srv._handle_dashboard_index()

        assert result == "response_obj"
        called_path = mock_fr.call_args[0][0]
        assert str(called_path).endswith("index.html")


# ── _configure_master_fd_nonblocking ─────────────────────────────────────────


class TestConfigureMasterFdNonblocking:
    def test_sets_nonblocking_flag(self):
        srv = _make_server()
        master_fd = 99

        with patch("fcntl.fcntl") as mock_fcntl:
            mock_fcntl.return_value = 0  # F_GETFL returns 0
            srv._configure_master_fd_nonblocking(master_fd)

        assert mock_fcntl.call_count == 2
        # First call: F_GETFL
        assert mock_fcntl.call_args_list[0][0][1] == fcntl.F_GETFL
        # Second call: F_SETFL with O_NONBLOCK added
        set_flags = mock_fcntl.call_args_list[1][0][2]
        assert set_flags & os.O_NONBLOCK


# ── _read_pty ─────────────────────────────────────────────────────────────────


class TestReadPty:
    @pytest.mark.asyncio
    async def test_sends_data_to_websocket(self):
        srv = _make_server()
        ws = _make_ws()
        call_count = 0

        def fake_read(fd, n):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"hello"
            return b""  # triggers break

        with patch("os.read", side_effect=fake_read):
            await srv._read_pty(99, ws)

        ws.send_json.assert_called_once()
        call_kwargs = ws.send_json.call_args[0][0]
        assert call_kwargs["type"] == "data"
        assert call_kwargs["data"] == "hello"

    @pytest.mark.asyncio
    async def test_breaks_on_empty_read(self):
        srv = _make_server()
        ws = _make_ws()

        with patch("os.read", return_value=b""):
            await srv._read_pty(99, ws)

        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_sleeps_on_blocking_io_error(self):
        srv = _make_server()
        ws = _make_ws()
        call_count = 0

        def fake_read(fd, n):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise BlockingIOError
            return b""  # then break

        with patch("os.read", side_effect=fake_read), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await srv._read_pty(99, ws)

        mock_sleep.assert_called_once_with(0.01)

    @pytest.mark.asyncio
    async def test_breaks_on_os_error(self):
        srv = _make_server()
        ws = _make_ws()

        with patch("os.read", side_effect=OSError("broken pipe")):
            await srv._read_pty(99, ws)

        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_breaks_on_timeout_sending(self):
        srv = _make_server()
        ws = _make_ws()
        # Raise ConnectionError from send_json so it propagates through wait_for
        ws.send_json.side_effect = ConnectionError("pipe closed")

        with patch("os.read", return_value=b"data"):
            await srv._read_pty(99, ws)

    @pytest.mark.asyncio
    async def test_breaks_on_runtime_error_sending(self):
        srv = _make_server()
        ws = _make_ws()
        ws.send_json.side_effect = RuntimeError("ws closed")

        with patch("os.read", return_value=b"data"):
            await srv._read_pty(99, ws)


# ── _handle_ws_timeout ────────────────────────────────────────────────────────


class TestHandleWsTimeout:
    @pytest.mark.asyncio
    async def test_returns_true_on_successful_ping(self):
        srv = _make_server()
        ws = _make_ws()

        result = await srv._handle_ws_timeout(ws)

        assert result is True
        ws.send_json.assert_called_once_with({"type": "ping"})

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        srv = _make_server()
        ws = _make_ws()
        ws.send_json.side_effect = ConnectionError("closed")

        result = await srv._handle_ws_timeout(ws)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_runtime_error(self):
        srv = _make_server()
        ws = _make_ws()
        ws.send_json.side_effect = RuntimeError("disconnected")

        result = await srv._handle_ws_timeout(ws)

        assert result is False


# ── _handle_input_message ─────────────────────────────────────────────────────


class TestHandleInputMessage:
    @pytest.mark.asyncio
    async def test_writes_input_to_pty(self):
        srv = _make_server()

        with patch("os.write") as mock_write:
            result = await srv._handle_input_message(99, {"data": "ls\n"})

        assert result is True
        mock_write.assert_called_once_with(99, b"ls\n")

    @pytest.mark.asyncio
    async def test_returns_false_on_os_error(self):
        srv = _make_server()

        with patch("os.write", side_effect=OSError("bad fd")):
            result = await srv._handle_input_message(99, {"data": "ls\n"})

        assert result is False

    @pytest.mark.asyncio
    async def test_empty_data_writes_empty_bytes(self):
        srv = _make_server()

        with patch("os.write") as mock_write:
            result = await srv._handle_input_message(99, {})

        assert result is True
        mock_write.assert_called_once_with(99, b"")


# ── _handle_resize_message ────────────────────────────────────────────────────


class TestHandleResizeMessage:
    @pytest.mark.asyncio
    async def test_sends_resize_ioctl(self):
        srv = _make_server()

        with patch("fcntl.ioctl") as mock_ioctl:
            result = await srv._handle_resize_message(99, {"rows": 40, "cols": 120})

        assert result is True
        mock_ioctl.assert_called_once()
        args = mock_ioctl.call_args[0]
        assert args[0] == 99
        assert args[1] == termios.TIOCSWINSZ
        # Verify rows/cols are packed correctly
        rows, cols = struct.unpack("HH", args[2][:4])
        assert rows == 40
        assert cols == 120

    @pytest.mark.asyncio
    async def test_returns_true_on_os_error(self):
        srv = _make_server()

        with patch("fcntl.ioctl", side_effect=OSError("unsupported")):
            result = await srv._handle_resize_message(99, {"rows": 24, "cols": 80})

        assert result is True  # resize failure is non-critical

    @pytest.mark.asyncio
    async def test_defaults_to_24x80(self):
        srv = _make_server()

        with patch("fcntl.ioctl") as mock_ioctl:
            await srv._handle_resize_message(99, {})

        args = mock_ioctl.call_args[0]
        rows, cols = struct.unpack("HH", args[2][:4])
        assert rows == 24
        assert cols == 80


# ── _handle_ping_message ──────────────────────────────────────────────────────


class TestHandlePingMessage:
    @pytest.mark.asyncio
    async def test_sends_pong(self):
        srv = _make_server()
        ws = _make_ws()

        result = await srv._handle_ping_message(ws)

        assert result is True
        ws.send_json.assert_called_once_with({"type": "pong"})

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        srv = _make_server()
        ws = _make_ws()
        ws.send_json.side_effect = ConnectionError("gone")

        result = await srv._handle_ping_message(ws)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_os_error(self):
        srv = _make_server()
        ws = _make_ws()
        ws.send_json.side_effect = OSError("closed")

        result = await srv._handle_ping_message(ws)

        assert result is False


# ── _process_ws_message ───────────────────────────────────────────────────────


class TestProcessWsMessage:
    @pytest.mark.asyncio
    async def test_dispatches_input(self):
        srv = _make_server()
        ws = _make_ws()

        with patch.object(srv, "_handle_input_message", new_callable=AsyncMock, return_value=True) as mock:
            result = await srv._process_ws_message(99, ws, {"type": "input", "data": "x"})

        assert result is True
        mock.assert_called_once_with(99, {"type": "input", "data": "x"})

    @pytest.mark.asyncio
    async def test_dispatches_resize(self):
        srv = _make_server()
        ws = _make_ws()

        with patch.object(srv, "_handle_resize_message", new_callable=AsyncMock, return_value=True) as mock:
            result = await srv._process_ws_message(99, ws, {"type": "resize", "rows": 30, "cols": 90})

        assert result is True
        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_ping(self):
        srv = _make_server()
        ws = _make_ws()
        called_with = []

        async def fake_ping(w):
            called_with.append(w)
            return True

        srv._handle_ping_message = fake_ping
        result = await srv._process_ws_message(99, ws, {"type": "ping"})

        assert result is True
        assert called_with == [ws]

    @pytest.mark.asyncio
    async def test_unknown_type_continues(self):
        srv = _make_server()
        ws = _make_ws()

        result = await srv._process_ws_message(99, ws, {"type": "unknown"})

        assert result is True


# ── _read_ws ──────────────────────────────────────────────────────────────────


class TestReadWs:
    @pytest.mark.asyncio
    async def test_processes_input_message_then_breaks_on_false(self):
        srv = _make_server()
        ws = _make_ws()

        msg = json.dumps({"type": "input", "data": "q"})
        ws.receive_text.side_effect = [msg, ConnectionError("done")]

        with patch.object(srv, "_process_ws_message", new_callable=AsyncMock, return_value=False):
            await srv._read_ws(99, ws)

    @pytest.mark.asyncio
    async def test_sends_keepalive_on_timeout_and_breaks_if_failed(self):
        srv = _make_server()
        ws = _make_ws()

        async def always_timeout(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError

        with patch("asyncio.wait_for", new=always_timeout), \
             patch.object(srv, "_handle_ws_timeout", new_callable=AsyncMock, return_value=False):
            await srv._read_ws(99, ws)

    @pytest.mark.asyncio
    async def test_continues_on_timeout_when_ping_succeeds(self):
        srv = _make_server()
        ws = _make_ws()
        call_count = 0

        async def fake_wait_for(coro, timeout):
            nonlocal call_count
            call_count += 1
            coro.close()
            if call_count <= 2:
                raise asyncio.TimeoutError
            raise ConnectionError("done")

        with patch("asyncio.wait_for", new=fake_wait_for), \
             patch.object(srv, "_handle_ws_timeout", new_callable=AsyncMock, return_value=True):
            await srv._read_ws(99, ws)

    @pytest.mark.asyncio
    async def test_continues_on_json_decode_error(self):
        srv = _make_server()
        ws = _make_ws()
        call_count = 0

        async def fake_wait_for(coro, timeout):
            nonlocal call_count
            call_count += 1
            coro.close()
            if call_count == 1:
                return "not json {"
            raise ConnectionError("done")

        with patch("asyncio.wait_for", new=fake_wait_for):
            await srv._read_ws(99, ws)

    @pytest.mark.asyncio
    async def test_breaks_on_connection_error(self):
        srv = _make_server()
        ws = _make_ws()

        async def conn_error(coro, timeout):
            coro.close()
            raise ConnectionError("closed")

        with patch("asyncio.wait_for", new=conn_error):
            await srv._read_ws(99, ws)


# ── _cleanup_pty ──────────────────────────────────────────────────────────────


class TestCleanupPty:
    @pytest.mark.asyncio
    async def test_kills_child_and_closes_fd(self):
        srv = _make_server()

        with patch("os.kill") as mock_kill, \
             patch("os.close") as mock_close, \
             patch("os.waitpid") as mock_waitpid:
            await srv._cleanup_pty(1234, 5)

        mock_kill.assert_called_once_with(1234, signal.SIGTERM)
        mock_close.assert_called_once_with(5)
        mock_waitpid.assert_called_once_with(1234, os.WNOHANG)

    @pytest.mark.asyncio
    async def test_ignores_process_lookup_error(self):
        srv = _make_server()

        with patch("os.kill", side_effect=ProcessLookupError), \
             patch("os.close"), \
             patch("os.waitpid"):
            await srv._cleanup_pty(9999, 5)  # should not raise

    @pytest.mark.asyncio
    async def test_ignores_close_os_error(self):
        srv = _make_server()

        with patch("os.kill"), \
             patch("os.close", side_effect=OSError("bad fd")), \
             patch("os.waitpid"):
            await srv._cleanup_pty(1234, 99)  # should not raise

    @pytest.mark.asyncio
    async def test_ignores_waitpid_child_error(self):
        srv = _make_server()

        with patch("os.kill"), \
             patch("os.close"), \
             patch("os.waitpid", side_effect=ChildProcessError):
            await srv._cleanup_pty(1234, 5)  # should not raise
