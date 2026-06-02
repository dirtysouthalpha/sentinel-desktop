"""Gap tests for agent_pool.py — cover cancel running, dispatcher, _agent_worker, shutdown join."""

import threading
import time
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

# ---------------------------------------------------------------------------
# cancel() for a RUNNING session  (lines 247-249)
# ---------------------------------------------------------------------------


class TestCancelRunningSession:
    """cancel() on a running session sets _cancel_requested and returns True."""

    def test_cancel_running_session(self):
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            session = pool._sessions[sid]
            # Force the session into RUNNING state
            session.status = STATUS_RUNNING
            result = pool.cancel(sid)
            assert result is True
            assert session._cancel_requested.is_set()
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# get_result() KeyError for unknown session  (line 276)
# ---------------------------------------------------------------------------


class TestGetResultKeyError:
    """get_result raises KeyError when session_id is unknown."""

    def test_get_result_unknown_session_raises_keyerror(self):
        pool = AgentPool(max_agents=2)
        try:
            with pytest.raises(KeyError, match="No such session"):
                pool.get_result("nonexistent_id")
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# shutdown(wait=True) joins threads, warns on timeout  (lines 310, 317-328)
# ---------------------------------------------------------------------------


class TestShutdownWaitJoinsThreads:
    """shutdown(wait=True) joins dispatcher and agent threads."""

    def test_shutdown_sets_cancel_on_running_sessions(self):
        """Running sessions have their cancel event set during shutdown."""
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            session = pool._sessions[sid]
            session.status = STATUS_RUNNING
            cancel_event = session._cancel_requested
            assert not cancel_event.is_set()
            pool.shutdown(wait=False)
            assert cancel_event.is_set()
        except Exception:
            pool.shutdown(wait=False)
            raise

    def test_shutdown_wait_true_joins_dispatcher(self):
        """shutdown(wait=True) joins the dispatcher thread."""
        pool = AgentPool(max_agents=2)
        pool.shutdown(wait=True, timeout=5.0)
        assert not pool._dispatcher_thread.is_alive()

    def test_shutdown_wait_logs_thread_timeout(self):
        """If a running agent thread doesn't exit in time, a warning is logged."""
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            session = pool._sessions[sid]
            session.status = STATUS_RUNNING

            # Create a fake thread that stays alive
            block_event = threading.Event()

            def slow_thread_target():
                block_event.wait(timeout=10)

            fake_thread = threading.Thread(target=slow_thread_target, daemon=True)
            fake_thread.start()
            session.thread = fake_thread

            with patch("core.agent_pool.logger") as mock_logger:
                pool.shutdown(wait=True, timeout=0.1)
                # Verify the warning about thread not exiting was logged
                mock_logger.warning.assert_any_call(
                    "Thread for session %s did not exit within timeout",
                    sid,
                )

            block_event.set()
            fake_thread.join(timeout=2)
        except Exception:
            pool.shutdown(wait=False)
            raise


# ---------------------------------------------------------------------------
# _dispatcher_loop edge cases  (lines 357, 361, 369)
# ---------------------------------------------------------------------------


class TestDispatcherEdgeCases:
    """Cover dispatcher inner-loop edge cases."""

    def test_dispatcher_exits_on_shutdown_inside_inner_loop(self):
        """The dispatcher checks _shutdown inside the inner while and returns."""
        pool = AgentPool(max_agents=1)
        try:
            # Submit a task so the dispatcher has something to process
            sid = pool.submit("Goal", priority="background")
            session = pool._sessions[sid]

            # Force into RUNNING to occupy the slot, so the next queued item
            # won't be dispatched immediately
            session.status = STATUS_RUNNING

            # Submit another to fill the queue
            pool.submit("Goal2", priority="background")

            # Trigger shutdown — dispatcher should notice _shutdown in inner loop
            pool._shutdown = True
            pool._dispatcher_event.set()

            # Wait briefly for dispatcher to exit
            pool._dispatcher_thread.join(timeout=3)
            assert not pool._dispatcher_thread.is_alive()
        except Exception:
            pool.shutdown(wait=False)
            raise

    def test_dispatcher_skips_when_at_capacity(self):
        """Dispatcher breaks from inner loop when _running_count >= max_agents."""
        pool = AgentPool(max_agents=1)
        try:
            # Manually put a session into RUNNING
            sid = pool.submit("Goal", priority="background")
            pool._sessions[sid].status = STATUS_RUNNING

            # Submit another — it should stay queued because we're at capacity
            sid2 = pool.submit("Goal2", priority="background")
            time.sleep(0.3)
            assert pool._sessions[sid2].status == STATUS_QUEUED
        finally:
            pool.shutdown(wait=False)

    def test_dispatcher_skips_stale_queue_entry(self):
        """Dispatcher skips a queue entry whose session was cancelled."""
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal", priority="background")
            session = pool._sessions[sid]

            # Cancel it while still queued, but leave a stale entry in queue
            # to simulate a race. We cancel which removes from queue.
            pool.cancel(sid)
            assert session.status == STATUS_CANCELLED

            # Now manually inject a stale entry back into the queue
            with pool._lock:
                pool._queue.append((1, 999, sid))

            # Wake dispatcher — it should skip the stale entry gracefully
            pool._dispatcher_event.set()
            time.sleep(0.3)
            # Session should still be cancelled, not running
            assert pool._sessions[sid].status == STATUS_CANCELLED
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# _agent_worker full flow  (lines 407-495)
# ---------------------------------------------------------------------------


class TestAgentWorkerFullFlow:
    """Cover _agent_worker: success, failure, cleanup, callback."""

    def test_worker_session_not_found_returns_early(self):
        """Worker logs error and returns if session_id is missing."""
        pool = AgentPool(max_agents=2)
        try:
            with patch("core.agent_pool.logger") as mock_logger:
                pool._agent_worker("nonexistent_session", "Desktop-X")
                mock_logger.error.assert_called_once_with(
                    "Worker: session %s not found", "nonexistent_session"
                )
        finally:
            pool.shutdown(wait=False)

    def test_worker_success_path(self):
        """Worker runs engine, sets status to COMPLETED, calls callback."""
        callback = MagicMock()
        pool = AgentPool(max_agents=1, on_session_complete=callback)
        try:
            sid = pool.submit("Do stuff", config={"model": "test"})
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 7, "result": "done"}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert session.status == STATUS_COMPLETED
            assert session.result == {"steps": 7, "result": "done"}
            assert session.step_count == 7
            assert session.end_time is not None
            callback.assert_called_once()
            call_arg = callback.call_args[0][0]
            assert call_arg["status"] == STATUS_COMPLETED
        finally:
            pool.shutdown(wait=False)

    def test_worker_vd_create_fails_continues(self):
        """Worker continues when VirtualDesktop.create() returns False."""
        callback = MagicMock()
        pool = AgentPool(max_agents=1, on_session_complete=callback)
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = False
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 1}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert session.status == STATUS_COMPLETED
            # switch_to should NOT have been called since create returned False
            mock_vd.switch_to.assert_not_called()
            callback.assert_called_once()
        finally:
            pool.shutdown(wait=False)

    def test_worker_engine_exception_sets_failed(self):
        """Worker catches engine exceptions and sets status to FAILED."""
        callback = MagicMock()
        pool = AgentPool(max_agents=1, on_session_complete=callback)
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.side_effect = RuntimeError("engine blew up")

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert session.status == STATUS_FAILED
            assert session.result["error"] == "engine blew up"
            assert session.result["error_type"] == "RuntimeError"
            assert session.end_time is not None
            callback.assert_called_once()
        finally:
            pool.shutdown(wait=False)

    def test_worker_import_error_sets_failed(self):
        """Worker catches ImportError and sets FAILED status."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = True

            with (
                patch(
                    "core.virtual_desktop.VirtualDesktop",
                    return_value=mock_vd,
                ),
                patch(
                    "core.engine.AgentEngine",
                    side_effect=ImportError("missing module"),
                ),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert session.status == STATUS_FAILED
            assert session.result["error_type"] == "ImportError"
        finally:
            pool.shutdown(wait=False)

    def test_worker_value_error_sets_failed(self):
        """Worker catches ValueError and sets FAILED status."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = True

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch(
                    "core.engine.AgentEngine",
                    side_effect=ValueError("bad value"),
                ),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert session.status == STATUS_FAILED
            assert session.result["error_type"] == "ValueError"
        finally:
            pool.shutdown(wait=False)

    def test_worker_os_error_sets_failed(self):
        """Worker catches OSError and sets FAILED status."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = True

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch(
                    "core.engine.AgentEngine",
                    side_effect=OSError("os error"),
                ),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert session.status == STATUS_FAILED
            assert session.result["error_type"] == "OSError"
        finally:
            pool.shutdown(wait=False)

    def test_worker_cleanup_virtual_desktop(self):
        """Worker cleans up VirtualDesktop in finally block."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 0}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            mock_vd.switch_back.assert_called_once()
            mock_vd.close.assert_called_once()
        finally:
            pool.shutdown(wait=False)

    def test_worker_cleanup_error_handled_gracefully(self):
        """If VirtualDesktop cleanup raises, worker logs warning but continues."""
        callback = MagicMock()
        pool = AgentPool(max_agents=1, on_session_complete=callback)
        try:
            # Create session manually without submit to avoid dispatcher picking it up
            session = AgentSession(id="test_cleanup_id", goal="Goal", config={})
            pool._sessions["test_cleanup_id"] = session
            sid = "test_cleanup_id"

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_vd.switch_back.side_effect = RuntimeError("cleanup fail")
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 1}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
                patch("core.agent_pool.logger") as mock_logger,
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            # Session still completed
            assert session.status == STATUS_COMPLETED
            # Warning was logged for cleanup failure
            mock_logger.warning.assert_any_call(
                "Session %s: error cleaning up desktop '%s': %s",
                sid,
                "SentinelAgent-1",
                mock_vd.switch_back.side_effect,
            )
            # Callback still called
            callback.assert_called_once()
            # Verify the callback received the expected result
            call_arg = callback.call_args[0][0]
            assert call_arg["status"] == STATUS_COMPLETED
            assert call_arg["step_count"] == 1
        finally:
            pool.shutdown(wait=False)

    def test_worker_callback_exception_handled(self):
        """If on_session_complete callback raises, worker logs warning."""
        bad_callback = MagicMock(side_effect=RuntimeError("callback boom"))
        pool = AgentPool(max_agents=1, on_session_complete=bad_callback)
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 2}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
                patch("core.agent_pool.logger") as mock_logger,
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            # Session still completed
            assert session.status == STATUS_COMPLETED
            # Callback was attempted
            bad_callback.assert_called_once()
            # Warning about callback exception was logged
            mock_logger.error.assert_any_call(
                "on_session_complete callback raised %s: %s",
                "RuntimeError",
                bad_callback.side_effect,
            )
        finally:
            pool.shutdown(wait=False)

    def test_worker_wakes_dispatcher_on_finish(self):
        """Worker sets _dispatcher_event when finished, freeing a slot."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 1}

            # Clear the event first so we can observe it being set
            pool._dispatcher_event.clear()

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine),
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            assert pool._dispatcher_event.is_set()
        finally:
            pool.shutdown(wait=False)

    def test_worker_with_no_config(self):
        """Worker handles session with None config by defaulting to empty dict."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            # Create session with config=None explicitly
            session = AgentSession(id="manual_id", goal="g", config=None)
            pool._sessions["manual_id"] = session

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 0}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine) as mock_engine_cls,
            ):
                pool._agent_worker("manual_id", "SentinelAgent-1")

            # Verify config passed to engine was {} with virtual_desktop=False
            engine_config = mock_engine_cls.call_args[1]["config"]
            assert engine_config["virtual_desktop"] is False
            assert session.status == STATUS_COMPLETED
        finally:
            pool.shutdown(wait=False)

    def test_worker_merges_session_config(self):
        """Worker merges per-session config with virtual_desktop override."""
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal", config={"provider": "openai", "model": "gpt-4"})

            mock_vd = MagicMock()
            mock_vd.create.return_value = True
            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 0}

            with (
                patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd),
                patch("core.engine.AgentEngine", return_value=mock_engine) as mock_engine_cls,
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            engine_config = mock_engine_cls.call_args[1]["config"]
            assert engine_config["provider"] == "openai"
            assert engine_config["model"] == "gpt-4"
            assert engine_config["virtual_desktop"] is False
        finally:
            pool.shutdown(wait=False)

    def test_worker_vd_is_none_skips_cleanup(self):
        """Cover the False branch of 'if vd is not None' (line 537->539).

        When _setup_virtual_desktop raises before assigning vd, the finally
        block finds vd=None and skips _cleanup_virtual_desktop.
        """
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]

            mock_engine = MagicMock()
            mock_engine.run.return_value = {"steps": 1}

            # Patch _setup_virtual_desktop to raise immediately so vd stays None.
            with (
                patch.object(pool, "_setup_virtual_desktop", side_effect=OSError("vd init fail")),
                patch("core.engine.AgentEngine", return_value=mock_engine),
                patch.object(pool, "_cleanup_virtual_desktop") as mock_cleanup,
            ):
                pool._agent_worker(sid, "SentinelAgent-1")

            # vd was None, so cleanup should NOT have been called.
            mock_cleanup.assert_not_called()
            # Session should be in FAILED state (OSError caught by except clause).
            assert session.status == STATUS_FAILED
        finally:
            pool.shutdown(wait=False)

    def test_worker_import_error_session_already_removed(self):
        """Cover the False branch of 'if session is not None' after ImportError (line 493->495).

        Setting core.engine to None in sys.modules makes 'from core.engine import AgentEngine'
        raise ImportError. The _SessionsProxy returns None for sid, simulating a race where
        the session was removed before the cleanup runs.
        """
        pool = AgentPool(max_agents=1, on_session_complete=MagicMock())
        try:
            sid = pool.submit("Goal")

            class _SessionsProxy(dict):
                def get(self, key, default=None):
                    if key == sid:
                        return None
                    return super().get(key, default)

            pool._sessions = _SessionsProxy(pool._sessions)

            import sys
            original = sys.modules.get("core.engine", ...)
            sys.modules["core.engine"] = None  # makes 'from core.engine import AgentEngine' fail
            try:
                with patch("core.agent_pool.logger"):
                    pool._agent_worker(sid, "SentinelAgent-1")
            finally:
                if original is ...:
                    del sys.modules["core.engine"]
                else:
                    sys.modules["core.engine"] = original

            # Should complete without crashing — _mark_session_failed not called.
        finally:
            pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# shutdown(wait=True) — thread exits within timeout (line 330 False branch)
# ---------------------------------------------------------------------------


class TestShutdownWaitThreadExitsQuickly:
    """Cover the False branch of 'if s.thread.is_alive()' (line 330->328).

    We need a running session whose thread exits within the join timeout so
    is_alive() returns False and no warning is logged.
    """

    def test_shutdown_wait_thread_exits_in_time_no_warning(self):
        """A thread that appears alive then exits during join → is_alive() False → no warning.

        Uses a mock thread whose is_alive() returns True on the first call
        (list comprehension inclusion) and False on the second call (line 330 check).
        """
        pool = AgentPool(max_agents=2)
        try:
            sid = pool.submit("Goal")
            session = pool._sessions[sid]
            session.status = STATUS_RUNNING

            # Mock thread: alive → included in 'running'; then dead → no warning.
            mock_thread = MagicMock()
            mock_thread.is_alive.side_effect = [True, False]
            session.thread = mock_thread

            with patch("core.agent_pool.logger") as mock_logger:
                pool.shutdown(wait=True, timeout=2.0)
                assert not any(
                    "did not exit within timeout" in str(c)
                    for c in mock_logger.warning.call_args_list
                )
        finally:
            pool.shutdown(wait=False)
