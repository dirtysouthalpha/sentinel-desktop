"""Regression tests for the v31 fleet-bus concurrency fixes.

* ``InMemoryBus.publish`` invoked subscriber callbacks while holding a
  non-reentrant ``threading.Lock``, so any callback that published in response
  deadlocked the publishing thread against itself.
* ``FleetManager.deploy_agent`` did ``node.agents_running += 1`` outside the
  lock — a read-modify-write that loses counts under concurrency.
"""

from __future__ import annotations

import threading
import time

from core.fleet.redis_bus import FleetManager, InMemoryBus

# A generous bound: the buggy version blocked forever, the fixed one is instant.
DEADLOCK_TIMEOUT = 10.0


def _run_with_timeout(fn, timeout=DEADLOCK_TIMEOUT):
    """Run *fn* in a thread; return True if it finished within *timeout*."""
    done = threading.Event()
    error: list = []

    def _target():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - surfaced to the test
            error.append(exc)
        finally:
            done.set()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    finished = done.wait(timeout)
    if error:
        raise error[0]
    return finished


# ---------------------------------------------------------------------------
# Re-entrant publish must not deadlock
# ---------------------------------------------------------------------------


def test_callback_that_publishes_does_not_deadlock():
    """Pre-v31 this blocked forever on a non-reentrant lock."""
    bus = InMemoryBus()
    seen: list = []

    def _on_ping(message):
        seen.append(message)
        if message.get("hop", 0) < 1:
            bus.publish("pong", {"hop": message.get("hop", 0) + 1})

    def _on_pong(message):
        seen.append(message)

    bus.subscribe("ping", _on_ping)
    bus.subscribe("pong", _on_pong)

    assert _run_with_timeout(lambda: bus.publish("ping", {"hop": 0})), (
        "publish() deadlocked when a subscriber published"
    )
    assert len(seen) == 2


def test_callback_that_republishes_same_channel_does_not_deadlock():
    bus = InMemoryBus()
    hops: list = []

    def _echo(message):
        hop = message.get("hop", 0)
        hops.append(hop)
        if hop < 5:
            bus.publish("loop", {"hop": hop + 1})

    bus.subscribe("loop", _echo)
    assert _run_with_timeout(lambda: bus.publish("loop", {"hop": 0}))
    assert hops == [0, 1, 2, 3, 4, 5]


def test_callback_that_subscribes_does_not_deadlock():
    bus = InMemoryBus()

    def _adder(message):
        bus.subscribe("later", lambda m: None)

    bus.subscribe("go", _adder)
    assert _run_with_timeout(lambda: bus.publish("go", {}))


def test_raising_callback_does_not_break_other_subscribers():
    bus = InMemoryBus()
    delivered: list = []
    bus.subscribe("c", lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("c", lambda m: delivered.append(m))
    bus.publish("c", {"v": 1})
    assert delivered == [{"v": 1}]


def test_messages_are_still_recorded():
    bus = InMemoryBus()
    bus.publish("a", {"n": 1})
    bus.publish("b", {"n": 2})
    assert [m["data"]["n"] for m in bus.get_messages()] == [1, 2]
    assert [m["data"]["n"] for m in bus.get_messages("a")] == [1]


def test_register_node_publishes_outside_the_manager_lock():
    """A fleet subscriber must be able to call back into the manager."""
    manager = FleetManager()
    results: list = []

    def _on_fleet(message):
        # Re-entering the manager would deadlock if publish held its lock.
        results.append(len(manager.list_nodes()))

    manager._bus.subscribe("fleet", _on_fleet)
    assert _run_with_timeout(lambda: manager.register_node("n1", hostname="h1"))
    assert results and results[0] >= 1


# ---------------------------------------------------------------------------
# agents_running must not lose updates
# ---------------------------------------------------------------------------


def test_concurrent_deploys_do_not_lose_agent_counts():
    """Pre-v31 `node.agents_running += 1` ran outside the lock."""
    manager = FleetManager()
    node_id = "worker-1"
    manager.register_node(node_id, hostname="worker", ip="10.0.0.5")

    deploys = 200
    threads_count = 8
    start = threading.Barrier(threads_count)
    per_thread = deploys // threads_count

    def _worker():
        start.wait()
        for _ in range(per_thread):
            manager.deploy_agent(node_id, "goal")

    threads = [threading.Thread(target=_worker) for _ in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    node = next(n for n in manager.list_nodes() if n["id"] == node_id)
    assert node["agents_running"] == per_thread * threads_count


def test_deploy_agent_rejects_unknown_node():
    manager = FleetManager()
    result = manager.deploy_agent("nope", "goal")
    assert result["success"] is False
    assert "not found" in result["message"]


def test_deploy_agent_rejects_offline_node():
    manager = FleetManager()
    manager.register_node("stale", hostname="s")
    # Force the heartbeat far into the past.
    manager._nodes["stale"].last_heartbeat = time.time() - 3600
    result = manager.deploy_agent("stale", "goal")
    assert result["success"] is False
    assert "offline" in result["message"]


def test_deploy_agent_increments_and_publishes():
    manager = FleetManager()
    manager.register_node("n", hostname="h")
    result = manager.deploy_agent("n", "do the thing")
    assert result["success"] is True
    events = manager.get_events("deploy")
    assert events and events[-1]["data"]["goal"] == "do the thing"
    node = next(n for n in manager.list_nodes() if n["id"] == "n")
    assert node["agents_running"] == 1


def test_os_is_importable_at_module_top():
    """`import os` used to sit at the bottom of the file though __init__ used it."""
    import core.fleet.redis_bus as bus_mod

    source = open(bus_mod.__file__, encoding="utf-8").read()
    head = source.split("logger = logging.getLogger")[0]
    assert "import os" in head, "os must be imported before it is used"
    assert source.rstrip().count("\nimport os") == 1
