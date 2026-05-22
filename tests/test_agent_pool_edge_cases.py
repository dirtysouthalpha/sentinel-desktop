"""
Tests for core/agent_pool.py — uncovered edge cases.

Targets lines 234-239 (cancel terminal state), 284 (get_result success),
487-496 (ImportError in worker), and 531-534 (TypeError/AttributeError worker).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.agent_pool import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    AgentPool,
    AgentSession,
)


class TestCancelTerminalState:
    """Test cancelling sessions that are already in a terminal state."""

    def test_cancel_completed_session_returns_false(self):
        """Cancelling an already-completed session should return False."""
        pool = AgentPool(max_agents=2)
        try:
            session_id = pool.submit("test goal")
            # Manually set session to completed
            with pool._lock:
                session = pool._sessions[session_id]
                session.status = STATUS_COMPLETED
            result = pool.cancel(session_id)
            assert result is False
        finally:
            pool.shutdown(wait=False)

    def test_cancel_failed_session_returns_false(self):
        """Cancelling an already-failed session should return False."""
        pool = AgentPool(max_agents=2)
        try:
            session_id = pool.submit("test goal")
            with pool._lock:
                session = pool._sessions[session_id]
                session.status = STATUS_FAILED
            result = pool.cancel(session_id)
            assert result is False
        finally:
            pool.shutdown(wait=False)

    def test_cancel_cancelled_session_returns_false(self):
        """Cancelling an already-cancelled session should return False."""
        pool = AgentPool(max_agents=2)
        try:
            session_id = pool.submit("test goal")
            with pool._lock:
                session = pool._sessions[session_id]
                session.status = STATUS_CANCELLED
            result = pool.cancel(session_id)
            assert result is False
        finally:
            pool.shutdown(wait=False)


class TestGetResultSuccess:
    """Test get_result success path."""

    def test_get_result_completed_session(self):
        """get_result should return session dict for completed session."""
        pool = AgentPool(max_agents=2)
        try:
            session_id = pool.submit("test goal")
            with pool._lock:
                session = pool._sessions[session_id]
                session.status = STATUS_COMPLETED
                session.end_time = datetime.now(timezone.utc)
                session.result = {"steps": 5, "success": True}
                session.step_count = 5
            result = pool.get_result(session_id)
            assert result["status"] == STATUS_COMPLETED
            assert result["step_count"] == 5
        finally:
            pool.shutdown(wait=False)

    def test_get_result_failed_session(self):
        """get_result should return session dict for failed session."""
        pool = AgentPool(max_agents=2)
        try:
            session_id = pool.submit("test goal")
            with pool._lock:
                session = pool._sessions[session_id]
                session.status = STATUS_FAILED
                session.end_time = datetime.now(timezone.utc)
                session.result = {"error": "Something went wrong", "error_type": "RuntimeError"}
            result = pool.get_result(session_id)
            assert result["status"] == STATUS_FAILED
            assert result["result"]["error"] == "Something went wrong"
        finally:
            pool.shutdown(wait=False)

    def test_get_result_cancelled_session(self):
        """get_result should return session dict for cancelled session."""
        pool = AgentPool(max_agents=2)
        try:
            session_id = pool.submit("test goal")
            with pool._lock:
                session = pool._sessions[session_id]
                session.status = STATUS_CANCELLED
                session.end_time = datetime.now(timezone.utc)
            result = pool.get_result(session_id)
            assert result["status"] == STATUS_CANCELLED
        finally:
            pool.shutdown(wait=False)


class TestWorkerImportError:
    """Test worker handling when engine import fails."""

    def test_worker_import_error_marks_session_failed(self):
        """Worker should mark session as failed when AgentEngine can't be imported."""
        pool = AgentPool(max_agents=1)
        session_id = pool.submit("test goal")
        session = pool._sessions[session_id]

        # Patch the import to raise ImportError
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "core.engine":
                raise ImportError("No module named 'core.engine'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            pool._agent_worker(session_id, "TestDesktop")

        assert session.status == STATUS_FAILED
        assert session.result is not None
        assert "ImportError" in session.result.get("error_type", "")
        pool.shutdown(wait=False)

    def test_worker_import_error_wakes_dispatcher(self):
        """Worker should set dispatcher_event when import fails."""
        pool = AgentPool(max_agents=1)
        session_id = pool.submit("test goal")
        pool._dispatcher_event.clear()

        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "core.engine":
                raise ImportError("engine missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            pool._agent_worker(session_id, "TestDesktop")

        assert pool._dispatcher_event.is_set()
        pool.shutdown(wait=False)


class TestWorkerTypeError:
    """Test worker handling of TypeError/AttributeError."""

    def test_worker_type_error_marks_session_failed(self):
        """Worker should handle TypeError and mark session as failed."""
        pool = AgentPool(max_agents=1)
        session_id = pool.submit("test goal")
        session = pool._sessions[session_id]

        with patch("core.agent_pool.AgentEngine", create=True) as mock_engine_cls:
            # Make the constructor raise TypeError
            mock_engine_cls.side_effect = TypeError("bad type")

            # Import normally but have the engine constructor fail
            with patch("core.engine.AgentEngine", side_effect=TypeError("bad type"), create=True):
                # Actually, we need to patch the import inside the worker
                pass

        # Use a more direct approach: patch the module-level import
        with patch.dict("sys.modules", {"core.engine": MagicMock(
            AgentEngine=MagicMock(side_effect=TypeError("config has wrong type"))
        )}):
            pool._agent_worker(session_id, "TestDesktop")

        assert session.status == STATUS_FAILED
        assert session.result is not None
        assert session.result.get("error_type") == "TypeError"
        pool.shutdown(wait=False)

    def test_worker_attribute_error_marks_session_failed(self):
        """Worker should handle AttributeError and mark session as failed."""
        pool = AgentPool(max_agents=1)
        session_id = pool.submit("test goal")
        session = pool._sessions[session_id]

        with patch.dict("sys.modules", {"core.engine": MagicMock(
            AgentEngine=MagicMock(side_effect=AttributeError("no attribute 'run'"))
        )}):
            pool._agent_worker(session_id, "TestDesktop")

        assert session.status == STATUS_FAILED
        assert session.result is not None
        assert session.result.get("error_type") == "AttributeError"
        pool.shutdown(wait=False)
