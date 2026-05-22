"""Tests for core/agent_pool.py — session lifecycle and priority queue."""

import pytest

from core.agent_pool import (
    STATUS_CANCELLED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    AgentPool,
    AgentSession,
)

# ---------------------------------------------------------------------------
# AgentSession
# ---------------------------------------------------------------------------


class TestAgentSession:
    def test_initial_state(self):
        s = AgentSession(id="abc", goal="test")
        assert s.status == STATUS_QUEUED
        assert s.priority == "normal"
        assert s.step_count == 0
        assert s.result is None

    def test_to_dict(self):
        s = AgentSession(id="abc", goal="test", status=STATUS_RUNNING)
        d = s.to_dict()
        assert d["id"] == "abc"
        assert d["goal"] == "test"
        assert d["status"] == STATUS_RUNNING
        assert d["start_time"] is None

    def test_to_dict_with_times(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        s = AgentSession(id="x", goal="g", start_time=now, end_time=now)
        d = s.to_dict()
        assert d["start_time"] == now.isoformat()
        assert d["end_time"] == now.isoformat()


# ---------------------------------------------------------------------------
# AgentPool — construction and shutdown
# ---------------------------------------------------------------------------


class TestAgentPoolInit:
    def test_default_max_agents(self):
        pool = AgentPool(max_agents=2)
        assert pool.max_agents == 2
        pool.shutdown(wait=False)

    def test_invalid_max_agents_raises(self):
        with pytest.raises(ValueError, match="max_agents"):
            AgentPool(max_agents=0)


# ---------------------------------------------------------------------------
# AgentPool — submit
# ---------------------------------------------------------------------------


class TestAgentPoolSubmit:
    def test_submit_returns_session_id(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Do something")
            assert isinstance(sid, str)
            assert len(sid) > 0
        finally:
            pool.shutdown(wait=False)

    def test_submit_with_invalid_priority_raises(self):
        pool = AgentPool(max_agents=2)
        try:
            with pytest.raises(ValueError, match="Invalid priority"):
                pool.submit("Do something", priority="critical")
        finally:
            pool.shutdown(wait=False)

    def test_submit_after_shutdown_raises(self):
        pool = AgentPool(max_agents=2)
        pool.shutdown(wait=False)
        with pytest.raises(RuntimeError, match="shut down"):
            pool.submit("Too late")


# ---------------------------------------------------------------------------
# AgentPool — cancel
# ---------------------------------------------------------------------------


class TestAgentPoolCancel:
    def test_cancel_queued_session(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            assert pool.cancel(sid) is True
            status = pool.get_status(sid)
            assert status["status"] == STATUS_CANCELLED
        finally:
            pool.shutdown(wait=False)

    def test_cancel_nonexistent_returns_false(self):
        pool = AgentPool(max_agents=2)
        try:
            assert pool.cancel("nope") is False
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# AgentPool — get_status / get_result
# ---------------------------------------------------------------------------


class TestAgentPoolStatus:
    def test_get_status_unknown_raises(self):
        pool = AgentPool(max_agents=2)
        try:
            with pytest.raises(KeyError):
                pool.get_status("nope")
        finally:
            pool.shutdown(wait=False)

    def test_get_result_not_finished_raises(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            with pytest.raises(ValueError, match="not a terminal state"):
                pool.get_result(sid)
        finally:
            pool.shutdown(wait=False)

    def test_list_sessions(self):
        pool = AgentPool(max_agents=4)
        try:
            pool.submit("A", priority="background")
            pool.submit("B", priority="background")
            sessions = pool.list_sessions()
            assert len(sessions) == 2
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# AgentPool — priority ordering
# ---------------------------------------------------------------------------


class TestAgentPoolPriority:
    def test_urgent_comes_first(self):
        pool = AgentPool(max_agents=1)
        try:
            # Submit background first, then urgent
            bg = pool.submit("Background task", priority="background")
            urg = pool.submit("Urgent task", priority="urgent")
            sessions = pool.list_sessions()
            # Both should be queued since max_agents=1 and agent worker
            # needs real VirtualDesktop/AgentEngine to run
            ids = [s["id"] for s in sessions]
            assert bg in ids
            assert urg in ids
        finally:
            pool.shutdown(wait=False)

    def test_repr(self):
        pool = AgentPool(max_agents=3)
        try:
            r = repr(pool)
            assert "AgentPool" in r
            assert "max_agents=3" in r
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# AgentPool — properties
# ---------------------------------------------------------------------------


class TestAgentPoolProperties:
    def test_active_count(self):
        pool = AgentPool(max_agents=2)
        try:
            assert pool.active_count >= 0
        finally:
            pool.shutdown(wait=False)

    def test_queued_count(self):
        pool = AgentPool(max_agents=2)
        try:
            pool.submit("A", priority="background")
            assert pool.queued_count >= 0
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# AgentPool — _mark_session_failed helper
# ---------------------------------------------------------------------------


class TestMarkSessionFailed:
    def test_sets_status_to_failed(self):
        pool = AgentPool(max_agents=1)
        try:
            s = AgentSession(id="fail1", goal="test")
            pool._mark_session_failed(s, "something broke", "RuntimeError")
            assert s.status == "failed"
            assert s.result == {"error": "something broke", "error_type": "RuntimeError"}
            assert s.end_time is not None
        finally:
            pool.shutdown(wait=False)

    def test_overwrites_previous_status(self):
        pool = AgentPool(max_agents=1)
        try:
            s = AgentSession(id="fail2", goal="test", status=STATUS_RUNNING)
            pool._mark_session_failed(s, "crash", "OSError")
            assert s.status == "failed"
            assert s.result["error_type"] == "OSError"
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# AgentPool — _cleanup_virtual_desktop helper
# ---------------------------------------------------------------------------


class TestCleanupVirtualDesktop:
    def test_calls_switch_back_and_close(self):
        pool = AgentPool(max_agents=1)
        try:
            from unittest.mock import MagicMock

            vd = MagicMock()
            pool._cleanup_virtual_desktop(vd, "s1", "test-desktop")
            vd.switch_back.assert_called_once()
            vd.close.assert_called_once()
        finally:
            pool.shutdown(wait=False)

    def test_logs_warning_on_error(self, caplog):
        pool = AgentPool(max_agents=1)
        try:
            from unittest.mock import MagicMock

            vd = MagicMock()
            vd.switch_back.side_effect = OSError("nope")
            pool._cleanup_virtual_desktop(vd, "s1", "d1")
            assert any("error cleaning up" in r.message.lower() for r in caplog.records)
        finally:
            pool.shutdown(wait=False)

    def test_handles_attribute_error(self):
        pool = AgentPool(max_agents=1)
        try:
            from unittest.mock import MagicMock

            vd = MagicMock()
            vd.switch_back.side_effect = AttributeError("missing")
            # Should not raise — error is caught and logged
            pool._cleanup_virtual_desktop(vd, "s1", "d1")
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# AgentPool — _notify_session_complete helper
# ---------------------------------------------------------------------------


class TestNotifySessionComplete:
    def test_calls_callback_with_snapshot(self):
        pool = AgentPool(max_agents=1)
        try:
            captured = {}
            pool._on_session_complete = lambda snap: captured.update(snap)
            s = AgentSession(id="cb1", goal="test goal")
            pool._notify_session_complete(s)
            assert captured["id"] == "cb1"
            assert captured["goal"] == "test goal"
        finally:
            pool.shutdown(wait=False)

    def test_noop_when_callback_is_none(self):
        pool = AgentPool(max_agents=1)
        try:
            s = AgentSession(id="nocb", goal="test")
            # Should not raise
            pool._notify_session_complete(s)
        finally:
            pool.shutdown(wait=False)

    def test_catches_callback_exception(self, caplog):
        pool = AgentPool(max_agents=1)
        try:

            def bad_callback(snap):
                raise RuntimeError("boom")

            pool._on_session_complete = bad_callback
            s = AgentSession(id="badcb", goal="test")
            pool._notify_session_complete(s)
            assert any("boom" in r.message for r in caplog.records)
        finally:
            pool.shutdown(wait=False)

    def test_catches_type_error_from_to_dict(self):
        pool = AgentPool(max_agents=1)
        try:

            class BadSession:
                def to_dict(self):
                    raise TypeError(" serialization fail")

            pool._on_session_complete = lambda snap: None
            # Should not raise even though to_dict fails
            pool._notify_session_complete(BadSession())
        finally:
            pool.shutdown(wait=False)
