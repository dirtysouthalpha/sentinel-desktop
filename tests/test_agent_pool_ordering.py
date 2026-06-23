"""Tests for AgentPool session ordering — newest-first must be by start time.

Regression: ``list_sessions`` and ``clear_completed`` historically sorted by
``session.id``, but the id is ``uuid4().hex`` (random), so "newest first" /
"keep the newest N" were determined by a random hex string, not by when the
session ran. These tests pin the correct behaviour: ordering by ``start_time``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.agent_pool import (
    STATUS_COMPLETED,
    AgentPool,
    AgentSession,
)

# Ids chosen so lexical id-order DISAGREES with start_time order:
#   id-sort ascending  -> newest, mid, old   (wrong for "creation order")
#   start_time order   -> old, mid, newest   (correct)
_OLD_ID = "zzzzzzzzzzzz"
_MID_ID = "aaaaaaaaaaaa"
_NEW_ID = "000000000000"

_T_OLD = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_T_MID = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
_T_NEW = datetime(2026, 1, 1, 12, 0, 2, tzinfo=timezone.utc)


def _completed(id_: str, start_time: datetime) -> AgentSession:
    s = AgentSession(id=id_, goal=f"goal-{id_}")
    s.status = STATUS_COMPLETED
    s.start_time = start_time
    return s


class TestClearCompletedOrdering:
    """keep_last must retain the most-recently-started terminal sessions."""

    def test_keep_last_retains_newest_by_start_time(self) -> None:
        pool = AgentPool(max_agents=10)
        try:
            pool._sessions[_OLD_ID] = _completed(_OLD_ID, _T_OLD)
            pool._sessions[_MID_ID] = _completed(_MID_ID, _T_MID)
            pool._sessions[_NEW_ID] = _completed(_NEW_ID, _T_NEW)

            removed = pool.clear_completed(keep_last=1)

            assert removed == 2
            # The newest session survives; the older two are cleared.
            assert _NEW_ID in pool._sessions
            assert _OLD_ID not in pool._sessions
            assert _MID_ID not in pool._sessions
        finally:
            pool.shutdown(wait=False)


class TestListSessionsOrdering:
    """list_sessions must return sessions newest-first by start time."""

    def test_list_sessions_newest_first_by_start_time(self) -> None:
        pool = AgentPool(max_agents=10)
        try:
            pool._sessions[_OLD_ID] = _completed(_OLD_ID, _T_OLD)
            pool._sessions[_MID_ID] = _completed(_MID_ID, _T_MID)
            pool._sessions[_NEW_ID] = _completed(_NEW_ID, _T_NEW)

            sessions = pool.list_sessions()
            ids = [s["id"] for s in sessions]

            assert ids == [_NEW_ID, _MID_ID, _OLD_ID]
        finally:
            pool.shutdown(wait=False)
