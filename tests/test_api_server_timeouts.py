"""Timeout tests for api.server REST handlers — targets 8 uncovered timeout exception lines.

This module adds coverage for timeout error paths in:
- _handle_windows (line 468)
- _handle_processes (line 483)
- _handle_system (line 498)
- _handle_schedule_run (line 749)
- _handle_notify (line 770)
- _handle_plugins_reload (line 803)
- _handle_auth_login (line 892)
- _handle_audit_export (line 951)

Each test simulates asyncio.TimeoutError from asyncio.wait_for() to verify
the proper 504 HTTPException is raised with the correct timeout message.
"""

import asyncio
from unittest.mock import Mock
from typing import Any

import pytest
from fastapi import HTTPException, Request

import api.server as mod
from api.server import SentinelServer
from config import Config


def _run(coro):
    return asyncio.run(coro)


def _make_server():
    return SentinelServer(Config())


def _fake_request():
    """Create a fake FastAPI Request object."""
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "query_string": b"",
        "path": "/test",
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# _handle_windows timeout (line 468)
# ---------------------------------------------------------------------------


class TestHandleWindowsTimeout:
    def test_windows_timeout(self, monkeypatch):
        """Test _handle_windows raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_windows(authorization=None))
        assert exc_info.value.status_code == 504
        assert "List windows timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_processes timeout (line 483)
# ---------------------------------------------------------------------------


class TestHandleProcessesTimeout:
    def test_processes_timeout(self, monkeypatch):
        """Test _handle_processes raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_processes(authorization=None))
        assert exc_info.value.status_code == 504
        assert "List processes timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_system timeout (line 498)
# ---------------------------------------------------------------------------


class TestHandleSystemTimeout:
    def test_system_timeout(self, monkeypatch):
        """Test _handle_system raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_system(authorization=None))
        assert exc_info.value.status_code == 504
        assert "System info timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_schedule_run timeout (line 749)
# ---------------------------------------------------------------------------


class TestHandleScheduleRunTimeout:
    def test_schedule_run_timeout(self, monkeypatch):
        """Test _handle_schedule_run raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))

        fake_engine = type("E", (), {"scheduler": type("S", (), {"run_task_now": lambda s, tid: None})()})()
        server = _make_server()
        server.engine = fake_engine
        req = mod.ScheduleRunRequest(task_id="test_task")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_schedule_run(req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "Task execution timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_notify timeout (line 770)
# ---------------------------------------------------------------------------


class TestHandleNotifyTimeout:
    def test_notify_timeout(self, monkeypatch):
        """Test _handle_notify raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))

        fake_notifications = type("NM", (), {"notify": lambda s, title, message, level: False})()
        fake_engine = type("E", (), {"notifications": fake_notifications})()
        server = _make_server()
        server.engine = fake_engine
        req = mod.NotifyRequest(title="Test", message="Test message", level="info")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_notify(req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "Notification timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_plugins_reload timeout (line 803)
# ---------------------------------------------------------------------------


class TestHandlePluginsReloadTimeout:
    def test_plugins_reload_timeout(self, monkeypatch):
        """Test _handle_plugins_reload raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))

        fake_plugin_loader = type("PL", (), {"reload_plugin": lambda s, name: True})()
        fake_engine = type("E", (), {"plugin_loader": fake_plugin_loader})()
        server = _make_server()
        server.engine = fake_engine
        req = mod.PluginReloadRequest(name="test_plugin")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_plugins_reload(req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "Plugin reload timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_auth_login timeout (line 892)
# ---------------------------------------------------------------------------


class TestHandleAuthLoginTimeout:
    def test_auth_login_timeout(self, monkeypatch):
        """Test _handle_auth_login raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))

        fake_auth = type("AM", (), {"authenticate": lambda s, u, p: None, "create_session": lambda s, u: "token"})()
        fake_engine = type("E", (), {"auth_manager": fake_auth})()
        server = _make_server()
        _ = server.create_app()  # Initialize _login_attempts
        server.engine = fake_engine
        req = mod.AuthLoginRequest(username="test", password="test")
        fake_req = _fake_request()
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_auth_login(req, fake_req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "Authentication timed out after" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# _handle_audit_export timeout (line 951)
# ---------------------------------------------------------------------------


class TestHandleAuditExportTimeout:
    def test_audit_export_timeout(self, monkeypatch):
        """Test _handle_audit_export raises 504 on timeout."""
        from fastapi import HTTPException

        def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(asyncio, "to_thread", lambda f, *args: f(*args))

        fake_audit_exporter = type("AE", (), {"generate_report": lambda s, log, goal, fmt: None})()
        fake_engine = type("E", (), {"audit_exporter": fake_audit_exporter, "forensic_log": []})()
        server = _make_server()
        server.engine = fake_engine
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_audit_export(authorization=None, format="json"))
        assert exc_info.value.status_code == 504
        assert "Audit export timed out after" in str(exc_info.value.detail)
