"""Tests for AgentPool.clear_completed — terminal session cleanup."""

from __future__ import annotations

from core.agent_pool import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    AgentPool,
    AgentSession,
)


class TestClearCompleted:
    """Test AgentPool.clear_completed behaviour."""

    def test_removes_completed_sessions(self) -> None:
        pool = AgentPool(max_agents=5)
        try:
            s1 = AgentSession(id="s1", goal="done")
            s1.status = STATUS_COMPLETED
            s2 = AgentSession(id="s2", goal="running")
            s2.status = STATUS_RUNNING
            pool._sessions["s1"] = s1
            pool._sessions["s2"] = s2

            removed = pool.clear_completed()
            assert removed == 1
            assert "s1" not in pool._sessions
            assert "s2" in pool._sessions
        finally:
            pool.shutdown(wait=False)

    def test_removes_failed_sessions(self) -> None:
        pool = AgentPool(max_agents=5)
        try:
            s = AgentSession(id="f1", goal="fail")
            s.status = STATUS_FAILED
            pool._sessions["f1"] = s

            removed = pool.clear_completed()
            assert removed == 1
            assert "f1" not in pool._sessions
        finally:
            pool.shutdown(wait=False)

    def test_removes_cancelled_sessions(self) -> None:
        pool = AgentPool(max_agents=5)
        try:
            s = AgentSession(id="c1", goal="cancel")
            s.status = STATUS_CANCELLED
            pool._sessions["c1"] = s

            removed = pool.clear_completed()
            assert removed == 1
            assert "c1" not in pool._sessions
        finally:
            pool.shutdown(wait=False)

    def test_does_not_remove_running_or_queued(self) -> None:
        pool = AgentPool(max_agents=5)
        try:
            s_run = AgentSession(id="r1", goal="running")
            s_run.status = STATUS_RUNNING
            s_q = AgentSession(id="q1", goal="queued")
            s_q.status = STATUS_QUEUED
            pool._sessions["r1"] = s_run
            pool._sessions["q1"] = s_q

            removed = pool.clear_completed()
            assert removed == 0
            assert "r1" in pool._sessions
            assert "q1" in pool._sessions
        finally:
            pool.shutdown(wait=False)

    def test_keep_last_preserves_newest_completed(self) -> None:
        pool = AgentPool(max_agents=10)
        try:
            for i in range(5):
                s = AgentSession(id=f"s{i:03d}", goal=f"done-{i}")
                s.status = STATUS_COMPLETED
                pool._sessions[f"s{i:03d}"] = s

            removed = pool.clear_completed(keep_last=2)
            assert removed == 3
            # The newest 2 (s003, s004) should survive
            assert "s003" in pool._sessions
            assert "s004" in pool._sessions
            assert "s000" not in pool._sessions
            assert "s001" not in pool._sessions
            assert "s002" not in pool._sessions
        finally:
            pool.shutdown(wait=False)

    def test_keep_last_larger_than_count_removes_none(self) -> None:
        pool = AgentPool(max_agents=5)
        try:
            s = AgentSession(id="s1", goal="done")
            s.status = STATUS_COMPLETED
            pool._sessions["s1"] = s

            removed = pool.clear_completed(keep_last=10)
            assert removed == 0
            assert "s1" in pool._sessions
        finally:
            pool.shutdown(wait=False)

    def test_keep_last_zero_removes_all(self) -> None:
        pool = AgentPool(max_agents=10)
        try:
            for i in range(3):
                s = AgentSession(id=f"s{i}", goal=f"done-{i}")
                s.status = STATUS_FAILED
                pool._sessions[f"s{i}"] = s

            removed = pool.clear_completed(keep_last=0)
            assert removed == 3
            assert len(pool._sessions) == 0
        finally:
            pool.shutdown(wait=False)

    def test_mixed_statuses_with_keep_last(self) -> None:
        pool = AgentPool(max_agents=10)
        try:
            # 3 completed, 2 running, 1 failed
            for i in range(3):
                s = AgentSession(id=f"done{i}", goal=f"d{i}")
                s.status = STATUS_COMPLETED
                pool._sessions[f"done{i}"] = s
            for i in range(2):
                s = AgentSession(id=f"run{i}", goal=f"r{i}")
                s.status = STATUS_RUNNING
                pool._sessions[f"run{i}"] = s
            s_fail = AgentSession(id="fail0", goal="f0")
            s_fail.status = STATUS_FAILED
            pool._sessions["fail0"] = s_fail

            # 4 terminal sessions (3 completed + 1 failed), keep last 1
            removed = pool.clear_completed(keep_last=1)
            assert removed == 3
            # Running sessions untouched
            assert "run0" in pool._sessions
            assert "run1" in pool._sessions
            # Only 1 terminal session should remain
            terminal_remaining = [
                sid for sid, sess in pool._sessions.items()
                if sess.status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)
            ]
            assert len(terminal_remaining) == 1
        finally:
            pool.shutdown(wait=False)

    def test_empty_pool_returns_zero(self) -> None:
        pool = AgentPool(max_agents=5)
        try:
            removed = pool.clear_completed()
            assert removed == 0
        finally:
            pool.shutdown(wait=False)
