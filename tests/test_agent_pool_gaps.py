"""Gap tests for agent_pool.py — cancel terminal states, session_complete callback."""

import time
from unittest.mock import MagicMock

from core.agent_pool import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    AgentPool,
    AgentSession,
)


class TestAgentPoolCancelTerminalStates:
    """cancel() returns False for sessions already completed or failed."""

    def test_cancel_completed_returns_false(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            # Manually set status to completed
            pool._sessions[sid].status = STATUS_COMPLETED
            assert pool.cancel(sid) is False
        finally:
            pool.shutdown(wait=False)

    def test_cancel_failed_returns_false(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            pool._sessions[sid].status = STATUS_FAILED
            assert pool.cancel(sid) is False
        finally:
            pool.shutdown(wait=False)

    def test_cancel_already_cancelled_returns_false(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            pool.cancel(sid)
            assert pool.cancel(sid) is False
        finally:
            pool.shutdown(wait=False)


class TestAgentPoolGetResultCompleted:
    """get_result works for cancelled sessions."""

    def test_get_result_cancelled(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            pool.cancel(sid)
            result = pool.get_result(sid)
            assert result["status"] == STATUS_CANCELLED
        finally:
            pool.shutdown(wait=False)


class TestAgentPoolSessionCompleteCallback:
    """on_session_complete callback is invoked when a session finishes."""

    def test_callback_invoked_on_success(self):
        callback = MagicMock()
        pool = AgentPool(max_agents=1, on_session_complete=callback)
        try:
            # Patch _agent_worker to simulate a successful run
            def fake_worker(session_id, desktop_name):
                session = pool._sessions[session_id]
                with pool._lock:
                    session.status = STATUS_COMPLETED
                    session.result = {"steps": 5}
                # Simulate the finally block callback
                if pool._on_session_complete is not None:
                    with pool._lock:
                        snapshot = session.to_dict()
                    pool._on_session_complete(snapshot)
                pool._dispatcher_event.set()

            pool._agent_worker = fake_worker
            pool.submit("Do something")
            time.sleep(0.5)
            callback.assert_called_once()
            call_args = callback.call_args[0][0]
            assert call_args["status"] == STATUS_COMPLETED
        finally:
            pool.shutdown(wait=False)


class TestAgentSessionToDict:
    """Additional to_dict edge cases."""

    def test_to_dict_with_result(self):
        s = AgentSession(id="x", goal="g", result={"steps": 3})
        d = s.to_dict()
        assert d["result"] == {"steps": 3}

    def test_to_dict_preserves_priority(self):
        s = AgentSession(id="x", goal="g", priority="urgent")
        d = s.to_dict()
        assert d["priority"] == "urgent"


class TestAgentPoolShutdownCancelsQueued:
    """Shutdown cancels all queued sessions."""

    def test_shutdown_cancels_queued(self):
        pool = AgentPool(max_agents=1)
        try:
            pool.submit("A", priority="background")
            pool.submit("B", priority="background")
            pool.shutdown(wait=False)
            time.sleep(0.1)
            sessions = pool.list_sessions()
            for s in sessions:
                assert s["status"] == STATUS_CANCELLED
        except Exception:
            pool.shutdown(wait=False)
            raise


class TestAgentPoolSubmitAllPriorities:
    """All valid priority levels work."""

    def test_submit_urgent(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Urgent", priority="urgent")
            assert pool.get_status(sid)["priority"] == "urgent"
        finally:
            pool.shutdown(wait=False)

    def test_submit_normal(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Normal", priority="normal")
            assert pool.get_status(sid)["priority"] == "normal"
        finally:
            pool.shutdown(wait=False)

    def test_submit_background(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Background", priority="background")
            assert pool.get_status(sid)["priority"] == "background"
        finally:
            pool.shutdown(wait=False)
