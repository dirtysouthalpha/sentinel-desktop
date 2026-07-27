"""Regression tests for v31 event-bus watcher tracking.

``watch_file`` / ``watch_dir`` started their poll threads as bare locals and
never assigned ``self._poll_thread``, so watchers leaked: there was no way to
enumerate them, join them, or shut them down individually.
"""

from __future__ import annotations

import time

from core.server.event_bus import EVENT_FILE_CREATED, EVENT_FILE_MODIFIED, EventBus


def test_watch_file_thread_is_tracked(tmp_path):
    target = tmp_path / "watched.txt"
    target.write_text("v1")
    bus = EventBus()
    try:
        bus.watch_file(str(target), poll_interval=0.05)
        threads = bus.watcher_threads
        assert len(threads) == 1
        assert threads[0].is_alive()
        assert str(target) in threads[0].name
    finally:
        bus.stop_watchers(timeout=5)


def test_watch_dir_thread_is_tracked(tmp_path):
    bus = EventBus()
    try:
        bus.watch_dir(str(tmp_path), poll_interval=0.05)
        threads = bus.watcher_threads
        assert len(threads) == 1
        assert threads[0].is_alive()
        assert str(tmp_path) in threads[0].name
    finally:
        bus.stop_watchers(timeout=5)


def test_multiple_watchers_are_all_tracked(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    sub = tmp_path / "sub"
    sub.mkdir()

    bus = EventBus()
    try:
        bus.watch_file(str(a), poll_interval=0.05)
        bus.watch_file(str(b), poll_interval=0.05)
        bus.watch_dir(str(sub), poll_interval=0.05)
        assert len(bus.watcher_threads) == 3
        assert all(t.is_alive() for t in bus.watcher_threads)
    finally:
        bus.stop_watchers(timeout=5)


def test_stop_watchers_joins_every_thread(tmp_path):
    target = tmp_path / "w.txt"
    target.write_text("x")
    sub = tmp_path / "d"
    sub.mkdir()

    bus = EventBus()
    bus.watch_file(str(target), poll_interval=0.05)
    bus.watch_dir(str(sub), poll_interval=0.05)
    started = bus.watcher_threads
    assert len(started) == 2

    bus.stop_watchers(timeout=10)

    assert bus._running is False
    for thread in started:
        assert not thread.is_alive(), f"{thread.name} outlived stop_watchers()"
    assert bus.watcher_threads == []


def test_watchers_are_daemon_threads(tmp_path):
    target = tmp_path / "w.txt"
    target.write_text("x")
    bus = EventBus()
    try:
        bus.watch_file(str(target), poll_interval=0.05)
        assert all(t.daemon for t in bus.watcher_threads)
    finally:
        bus.stop_watchers(timeout=5)


def test_watcher_threads_returns_a_snapshot(tmp_path):
    target = tmp_path / "w.txt"
    target.write_text("x")
    bus = EventBus()
    try:
        bus.watch_file(str(target), poll_interval=0.05)
        snapshot = bus.watcher_threads
        snapshot.clear()
        assert len(bus.watcher_threads) == 1
    finally:
        bus.stop_watchers(timeout=5)


def test_file_watcher_still_emits_modification_events(tmp_path):
    target = tmp_path / "watched.txt"
    target.write_text("v1")
    seen: list = []

    bus = EventBus()
    bus.on(EVENT_FILE_MODIFIED, lambda e: seen.append(e))
    try:
        bus.watch_file(str(target), poll_interval=0.05)
        time.sleep(0.2)
        target.write_text("v2 changed")
        deadline = time.time() + 5
        while time.time() < deadline and not seen:
            time.sleep(0.05)
    finally:
        bus.stop_watchers(timeout=5)

    assert seen, "file watcher never reported the modification"
    assert seen[0].data["path"] == str(target)


def test_dir_watcher_still_emits_creation_events(tmp_path):
    seen: list = []
    bus = EventBus()
    bus.on(EVENT_FILE_CREATED, lambda e: seen.append(e))
    try:
        bus.watch_dir(str(tmp_path), poll_interval=0.05)
        time.sleep(0.2)
        (tmp_path / "fresh.txt").write_text("new")
        deadline = time.time() + 5
        while time.time() < deadline and not seen:
            time.sleep(0.05)
    finally:
        bus.stop_watchers(timeout=5)

    assert seen, "dir watcher never reported the new file"
    assert seen[0].data["filename"] == "fresh.txt"
