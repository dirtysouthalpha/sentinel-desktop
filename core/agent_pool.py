"""Sentinel Desktop — Multi-Agent Parallel Execution Pool.

Manages multiple concurrent agent sessions, each running in its own thread
with a dedicated AgentEngine and isolated VirtualDesktop.  A dispatcher
thread pulls sessions from a priority queue and starts them as slots become
available.

Priority ordering:
  1. ``urgent``   — dispatched before everything else
  2. ``normal``   — default priority
  3. ``background``— runs only when no higher-priority work is waiting

Thread safety
-------------
All shared state is guarded by a single ``threading.Lock``.  Public methods
are safe to call from any thread (GUI, API, scheduler, …).

Usage
-----
>>> from core.agent_pool import AgentPool
>>> pool = AgentPool(max_agents=4)
>>> sid = pool.submit("Open Outlook and draft an email to Bob", priority="normal")
>>> pool.get_status(sid)
{'id': '...', 'status': 'running', ...}
>>> pool.shutdown()
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.virtual_desktop import VirtualDesktop

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priority definition
# ---------------------------------------------------------------------------


class _Priority(IntEnum):
    """Numeric priority so that sorting is trivial (lower = higher urgency)."""

    URGENT = 0
    NORMAL = 1
    BACKGROUND = 2


_PRIORITY_MAP: dict[str, _Priority] = {
    "urgent": _Priority.URGENT,
    "normal": _Priority.NORMAL,
    "background": _Priority.BACKGROUND,
}

_VALID_PRIORITIES = set(_PRIORITY_MAP.keys())

# Session status constants (also used by callers / API)
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

# ---------------------------------------------------------------------------
# AgentSession dataclass
# ---------------------------------------------------------------------------


@dataclass
class AgentSession:
    """Tracks one agent session through its full lifecycle."""

    id: str
    goal: str
    status: str = STATUS_QUEUED
    priority: str = "normal"
    desktop_name: str = ""
    config: dict[str, Any] | None = None

    # Populated at runtime
    thread: threading.Thread | None = field(default=None, repr=False)
    result: dict[str, Any] | None = field(default=None, repr=False)
    start_time: datetime | None = None
    end_time: datetime | None = None
    step_count: int = 0

    # Internal cancellation flag
    _cancel_requested: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the session to a plain dict suitable for JSON / API."""
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "priority": self.priority,
            "desktop_name": self.desktop_name,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "step_count": self.step_count,
            "result": self.result,
        }


# ---------------------------------------------------------------------------
# AgentPool
# ---------------------------------------------------------------------------


class AgentPool:
    """Manage simultaneous agent sessions with a capped concurrency limit.

    Parameters
    ----------
    max_agents:
        Maximum number of agents that may run concurrently.  Each agent
        consumes one slot and gets its own ``VirtualDesktop`` named
        ``SentinelAgent-{N}`` where *N* is a monotonically increasing counter.

    on_session_complete:
        Optional callback ``f(session_dict)`` invoked (from the agent thread)
        when a session finishes — either successfully or with an error.

    """

    def __init__(
        self,
        max_agents: int = 3,
        on_session_complete: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize the pool and start the background dispatcher thread.

        Args:
            max_agents: Maximum number of agent sessions that may run concurrently.
            on_session_complete: Optional callback invoked (from the agent thread)
                when a session finishes — either successfully or with an error.

        """
        if max_agents < 1:
            raise ValueError("max_agents must be >= 1")
        self._max_agents = max_agents
        self._on_session_complete = on_session_complete

        # Session storage: id -> AgentSession
        self._sessions: dict[str, AgentSession] = {}
        # Priority queue: list of (priority_value, creation_order, session_id)
        self._queue: list[tuple] = []
        # Monotonic counter for ordering equal-priority entries (FIFO)
        self._seq = 0
        # Monotonic counter for naming virtual desktops
        self._desktop_counter = 0

        self._lock = threading.Lock()
        self._dispatcher_event = threading.Event()  # signals dispatcher to wake
        self._shutdown = False

        # Start the background dispatcher thread
        self._dispatcher_thread = threading.Thread(
            target=self._dispatcher_loop,
            name="AgentPool-Dispatcher",
            daemon=True,
        )
        self._dispatcher_thread.start()
        logger.info(
            "AgentPool started (max_agents=%d, dispatcher alive)",
            self._max_agents,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        goal: str,
        config: dict[str, Any] | None = None,
        priority: str = "normal",
    ) -> str:
        """Submit a new agent goal.  Returns the session ID.

        Parameters
        ----------
        goal:
            Natural-language goal for the agent to accomplish.
        config:
            Optional dict forwarded to ``AgentEngine``.  Keys like
            ``provider``, ``api_key``, ``model``, ``max_steps``, etc.
        priority:
            One of ``"urgent"``, ``"normal"``, ``"background"``.

        """
        if priority not in _VALID_PRIORITIES:
            raise ValueError(f"Invalid priority {priority!r}; choose from {_VALID_PRIORITIES}")
        if self._shutdown:
            raise RuntimeError("AgentPool is shut down; cannot submit new goals")

        session_id = uuid.uuid4().hex[:12]
        session = AgentSession(
            id=session_id,
            goal=goal,
            config=config or {},
            priority=priority,
        )

        with self._lock:
            self._sessions[session_id] = session
            self._queue.append((_PRIORITY_MAP[priority], self._seq, session_id))
            self._seq += 1
            # Keep the queue sorted so the dispatcher can pop from the front
            self._queue.sort()

        logger.info(
            "Session %s submitted (goal=%r, priority=%s)",
            session_id,
            goal[:80],
            priority,
        )
        self._dispatcher_event.set()
        return session_id

    def cancel(self, session_id: str) -> bool:
        """Request cancellation of a session.

        Returns ``True`` if the session was found and cancellation was
        requested.  Sessions that are already completed or failed return
        ``False``.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning("cancel: unknown session %s", session_id)
                return False

            if session.status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
                logger.info(
                    "cancel: session %s already in terminal state '%s'",
                    session_id,
                    session.status,
                )
                return False

            if session.status == STATUS_QUEUED:
                # Remove from queue and mark cancelled immediately
                self._queue = [entry for entry in self._queue if entry[2] != session_id]
                session.status = STATUS_CANCELLED
                session.end_time = datetime.now(timezone.utc)
                logger.info("cancel: session %s removed from queue", session_id)
                return True

            # Session is running — set the cancel event so the worker notices
            session._cancel_requested.set()
            logger.info("cancel: cancellation requested for running session %s", session_id)
            return True

    def get_status(self, session_id: str) -> dict[str, Any]:
        """Return a status dict for a session, or raise ``KeyError``."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"No such session: {session_id}")
            return session.to_dict()

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return status dicts for all sessions, newest first."""
        with self._lock:
            sessions = list(self._sessions.values())
        # Sort by creation order (reverse so newest is first)
        sessions.sort(key=lambda s: s.id, reverse=True)
        return [s.to_dict() for s in sessions]

    def get_result(self, session_id: str) -> dict[str, Any]:
        """Return the full result dict for a completed/failed session.

        Raises ``KeyError`` if the session does not exist, and
        ``ValueError`` if the session has not finished yet.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"No such session: {session_id}")
            if session.status not in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
                raise ValueError(
                    f"Session {session_id} has status '{session.status}', not a terminal state",
                )
            return session.to_dict()

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Shut down the pool.

        Parameters
        ----------
        wait:
            If ``True``, block until all running agent threads finish (up to
            *timeout* seconds).  If ``False``, request shutdown and return
            immediately.
        timeout:
            Maximum seconds to wait for each running thread when *wait* is
            ``True``.

        """
        logger.info("AgentPool shutdown requested")
        with self._lock:
            self._shutdown = True
            for _pri, _seq, sid in self._queue:
                session = self._sessions.get(sid)
                if session and session.status == STATUS_QUEUED:
                    session.status = STATUS_CANCELLED
                    session.end_time = datetime.now(timezone.utc)
            self._queue.clear()
            for session in self._sessions.values():
                if session.status == STATUS_RUNNING:
                    session._cancel_requested.set()

        self._dispatcher_event.set()
        if wait:
            self._join_running_threads(timeout)
        logger.info("AgentPool shutdown complete")

    def _join_running_threads(self, timeout: float) -> None:
        """Join the dispatcher thread and all live agent threads, warning on stragglers."""
        self._dispatcher_thread.join(timeout=timeout)
        with self._lock:
            running = [
                s for s in self._sessions.values() if s.thread is not None and s.thread.is_alive()
            ]
        for s in running:
            s.thread.join(timeout=timeout)
            if s.thread.is_alive():
                logger.warning(
                    "Thread for session %s did not exit within timeout",
                    s.id,
                )

    # Internal: dispatcher

    def _running_count(self) -> int:
        """Must be called with ``self._lock`` held."""
        return sum(1 for s in self._sessions.values() if s.status == STATUS_RUNNING)

    def _dispatcher_loop(self) -> None:
        """Background thread: pulls queued sessions and starts agents."""
        logger.debug("Dispatcher thread started")
        while True:
            # Wait for a signal (new submission or shutdown)
            self._dispatcher_event.wait(timeout=1.0)
            self._dispatcher_event.clear()

            if self._shutdown:
                logger.debug("Dispatcher exiting (shutdown)")
                return

            # Try to schedule as many sessions as possible
            while True:
                with self._lock:
                    if self._shutdown:
                        return
                    if not self._queue:
                        break
                    if self._running_count() >= self._max_agents:
                        break

                    # Pop the highest-priority entry (smallest int value)
                    entry = self._queue.pop(0)
                    _pri, _seq, session_id = entry
                    session = self._sessions.get(session_id)
                    if session is None or session.status != STATUS_QUEUED:
                        # Stale entry (e.g. cancelled in the meantime)
                        continue

                    # Allocate a virtual desktop name
                    self._desktop_counter += 1
                    desktop_name = f"SentinelAgent-{self._desktop_counter}"

                    session.status = STATUS_RUNNING
                    session.start_time = datetime.now(timezone.utc)
                    session.desktop_name = desktop_name

                # Start the agent thread *outside* the lock to avoid
                # deadlock if the thread tries to call back into the pool
                # immediately.
                self._start_agent_thread(session, desktop_name)

    # ------------------------------------------------------------------
    # Internal: agent thread
    # ------------------------------------------------------------------

    def _start_agent_thread(self, session: AgentSession, desktop_name: str) -> None:
        """Spawn a new daemon thread to run one agent session."""
        thread = threading.Thread(
            target=self._agent_worker,
            args=(session.id, desktop_name),
            name=f"AgentPool-{session.id}",
            daemon=True,
        )
        with self._lock:
            session.thread = thread
        thread.start()
        logger.info(
            "Agent thread started for session %s (desktop=%s)",
            session.id,
            desktop_name,
        )

    def _mark_session_failed(
        self,
        session: AgentSession,
        error: str,
        error_type: str,
    ) -> None:
        """Thread-safe helper to mark a session as failed with error metadata."""
        with self._lock:
            session.status = STATUS_FAILED
            session.result = {"error": error, "error_type": error_type}
            session.end_time = datetime.now(timezone.utc)

    def _setup_virtual_desktop(
        self,
        session_id: str,
        desktop_name: str,
    ) -> VirtualDesktop | None:
        """Create and switch to an isolated virtual desktop for a session.

        Returns the VirtualDesktop instance on success, or None if the
        desktop couldn't be created (the session continues on the
        current desktop).
        """
        from core.virtual_desktop import VirtualDesktop

        vd = VirtualDesktop(name=desktop_name)
        vd_created = vd.create()
        if vd_created:
            vd.switch_to()
            logger.info(
                "Session %s: switched to virtual desktop '%s'",
                session_id,
                desktop_name,
            )
        else:
            logger.warning(
                "Session %s: virtual desktop '%s' unavailable, running on current desktop",
                session_id,
                desktop_name,
            )
        return vd

    def _cleanup_virtual_desktop(
        self,
        vd: VirtualDesktop,
        session_id: str,
        desktop_name: str,
    ) -> None:
        """Switch back from and close a session's virtual desktop.

        Non-fatal — errors are logged but don't propagate.
        """
        try:
            vd.switch_back()
            vd.close()
            logger.debug(
                "Session %s: virtual desktop '%s' cleaned up",
                session_id,
                desktop_name,
            )
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.warning(
                "Session %s: error cleaning up desktop '%s': %s",
                session_id,
                desktop_name,
                exc,
            )

    def _notify_session_complete(self, session: AgentSession) -> None:
        """Fire the on_session_complete callback with a session snapshot."""
        if self._on_session_complete is None:
            return
        try:
            with self._lock:
                snapshot = session.to_dict()
            self._on_session_complete(snapshot)
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            logger.error(
                "on_session_complete callback raised %s: %s",
                type(exc).__name__,
                exc,
            )

    def _agent_worker(self, session_id: str, desktop_name: str) -> None:
        """Worker function executed inside the agent thread."""
        try:
            from core.engine import AgentEngine
        except ImportError as exc:
            logger.exception(
                "Worker: failed to import engine/virtual_desktop for session %s",
                session_id,
            )
            with self._lock:
                session = self._sessions.get(session_id)
            if session is not None:
                self._mark_session_failed(session, str(exc), "ImportError")
            self._dispatcher_event.set()
            return

        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            logger.error("Worker: session %s not found", session_id)
            return

        self._run_engine_for_session(session, session_id, desktop_name, AgentEngine)

    def _run_engine_for_session(
        self,
        session: AgentSession,
        session_id: str,
        desktop_name: str,
        agent_engine: type,
    ) -> None:
        """Run an AgentEngine inside a virtual desktop and record the result."""
        vd: VirtualDesktop | None = None
        try:
            vd = self._setup_virtual_desktop(session_id, desktop_name)
            merged_config = dict(session.config or {})
            merged_config["virtual_desktop"] = False  # we handle it ourselves
            engine = agent_engine(config=merged_config)
            result = engine.run(goal=session.goal)
            with self._lock:
                session.status = STATUS_COMPLETED
                session.result = result
                session.end_time = datetime.now(timezone.utc)
                session.step_count = result.get("steps", 0) if isinstance(result, dict) else 0
            logger.info("Session %s completed (%d steps)", session_id, session.step_count)
        except (RuntimeError, OSError, ValueError, ImportError) as exc:
            logger.exception("Session %s failed with exception", session_id)
            self._mark_session_failed(session, str(exc), type(exc).__name__)
        except (TypeError, AttributeError) as exc:
            logger.exception("Session %s failed with unexpected error (possible bug)", session_id)
            self._mark_session_failed(session, str(exc), type(exc).__name__)
        finally:
            if vd is not None:
                self._cleanup_virtual_desktop(vd, session_id, desktop_name)
            self._notify_session_complete(session)
            self._dispatcher_event.set()

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def max_agents(self) -> int:
        """Maximum number of concurrent agents."""
        return self._max_agents

    @property
    def active_count(self) -> int:
        """Number of currently running agent sessions."""
        with self._lock:
            return self._running_count()

    @property
    def queued_count(self) -> int:
        """Number of sessions waiting in the queue."""
        with self._lock:
            return len(self._queue)

    def clear_completed(self, keep_last: int = 0) -> int:
        """Remove terminal-state sessions from memory.

        Parameters
        ----------
        keep_last:
            Keep at least this many of the most recent completed/failed/
            cancelled sessions.  Default ``0`` removes all of them.

        Returns
        -------
        int
            Number of sessions removed.

        """
        removed = 0
        with self._lock:
            terminal_ids = [
                sid
                for sid, s in self._sessions.items()
                if s.status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)
            ]
            if keep_last > 0:
                # Keep the newest *keep_last* by ID sort (creation order).
                terminal_ids.sort()
                terminal_ids = terminal_ids[:-keep_last] if len(terminal_ids) > keep_last else []
            for sid in terminal_ids:
                del self._sessions[sid]
                removed += 1
        if removed:
            logger.info("AgentPool: cleared %d completed session(s)", removed)
        return removed

    def __repr__(self) -> str:
        """Return string representation of AgentPool state."""
        return (
            f"AgentPool(max_agents={self._max_agents}, "
            f"active={self.active_count}, queued={self.queued_count}, "
            f"shutdown={self._shutdown})"
        )
