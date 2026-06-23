"""Tests for core/triggers.py (v22.0 — TriggerRegistry + TriggerEngine)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.triggers import EventType, Trigger, TriggerEngine, TriggerRegistry

# ---------------------------------------------------------------------------
# Trigger dataclass
# ---------------------------------------------------------------------------


def test_trigger_defaults():
    t = Trigger(
        name="test",
        event_type=EventType.CUSTOM,
        condition={"event_name": "foo"},
        action={"action": "speak", "text": "hi"},
    )
    assert t.enabled is True
    assert t.description == ""
    assert len(t.id) == 8


def test_trigger_to_dict_roundtrip():
    t = Trigger(
        name="roundtrip",
        event_type=EventType.SPOKEN_KEYWORD,
        condition={"keyword": "sentinel"},
        action={"action": "screenshot"},
        description="keyword watcher",
        enabled=False,
    )
    d = t.to_dict()
    assert d["event_type"] == "spoken_keyword"
    assert d["enabled"] is False

    t2 = Trigger.from_dict(d)
    assert t2.name == t.name
    assert t2.event_type == EventType.SPOKEN_KEYWORD
    assert t2.enabled is False
    assert t2.description == "keyword watcher"


def test_trigger_from_dict_missing_id_generates_one():
    d = {
        "name": "x",
        "event_type": "custom",
        "condition": {},
        "action": {},
    }
    t = Trigger.from_dict(d)
    assert t.id  # non-empty


# ---------------------------------------------------------------------------
# TriggerRegistry
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry(tmp_path: Path) -> TriggerRegistry:
    return TriggerRegistry(storage_dir=tmp_path / "triggers")


def test_registry_add_and_get(registry: TriggerRegistry):
    t = Trigger("t1", EventType.CUSTOM, {}, {})
    registry.add(t)
    assert registry.get(t.id) is t


def test_registry_list_all(registry: TriggerRegistry):
    registry.add(Trigger("a", EventType.CUSTOM, {}, {}))
    registry.add(Trigger("b", EventType.FILE_CHANGE, {}, {}))
    assert len(registry.list_all()) == 2


def test_registry_remove(registry: TriggerRegistry):
    t = Trigger("del_me", EventType.CUSTOM, {}, {})
    registry.add(t)
    assert registry.remove(t.id) is True
    assert registry.get(t.id) is None


def test_registry_remove_nonexistent(registry: TriggerRegistry):
    assert registry.remove("doesnotexist") is False


def test_registry_enable_disable(registry: TriggerRegistry):
    t = Trigger("tog", EventType.CUSTOM, {}, {}, enabled=False)
    registry.add(t)
    assert registry.enable(t.id) is True
    assert registry.get(t.id).enabled is True
    assert registry.disable(t.id) is True
    assert registry.get(t.id).enabled is False


def test_registry_enable_nonexistent(registry: TriggerRegistry):
    assert registry.enable("ghost") is False


def test_registry_find_by_event(registry: TriggerRegistry):
    t_custom = Trigger("c", EventType.CUSTOM, {}, {})
    t_file = Trigger("f", EventType.FILE_CHANGE, {}, {})
    t_disabled = Trigger("d", EventType.CUSTOM, {}, {}, enabled=False)
    registry.add(t_custom)
    registry.add(t_file)
    registry.add(t_disabled)

    results = registry.find_by_event(EventType.CUSTOM)
    assert len(results) == 1
    assert results[0].name == "c"


def test_registry_persists_to_disk(tmp_path: Path):
    r1 = TriggerRegistry(storage_dir=tmp_path / "trig")
    t = Trigger("persist", EventType.SCHEDULE, {"cron": "0 9 * * *"}, {})
    r1.add(t)

    r2 = TriggerRegistry(storage_dir=tmp_path / "trig")
    loaded = r2.get(t.id)
    assert loaded is not None
    assert loaded.name == "persist"
    assert loaded.event_type == EventType.SCHEDULE


def test_registry_save_leaves_no_tmp_leftover(registry: TriggerRegistry):
    registry.add(Trigger("t", EventType.CUSTOM, {}, {}))
    assert (registry._dir / "triggers.json").exists()
    assert not (registry._dir / "triggers.tmp").exists()


def test_registry_save_uses_unique_tmp_per_write(registry: TriggerRegistry, monkeypatch):
    # Atomic rename only protects against readers; two processes saving
    # concurrently (GUI + API share ~/.sentinel/triggers/) must not share one
    # temp inode or the loser's payload is clobbered on rename. Each save must
    # therefore write to a uniquely-named temp file.
    import core.triggers as trig

    seen = []
    orig_replace = trig.Path.replace

    def spy(self, target):  # noqa: ANN001
        seen.append(self.name)
        return orig_replace(self, target)

    monkeypatch.setattr(trig.Path, "replace", spy)
    registry.add(Trigger("a", EventType.CUSTOM, {}, {}))
    registry.add(Trigger("b", EventType.CUSTOM, {}, {}))
    assert len(seen) == 2
    assert len(set(seen)) == 2, f"two saves shared one temp inode: {seen}"


def test_registry_corrupt_file_is_quarantined(tmp_path: Path):
    storage = tmp_path / "trig"
    storage.mkdir(parents=True)
    triggers_file = storage / "triggers.json"
    # A crash mid-save can leave a truncated/garbled file.
    triggers_file.write_text("{this is not valid json", encoding="utf-8")

    reg = TriggerRegistry(storage_dir=storage)
    # Registry starts empty …
    assert reg.list_all() == []
    # … but the corrupt data is preserved for recovery, not destroyed.
    assert not triggers_file.exists()
    backup = storage / "triggers.json.corrupt"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "{this is not valid json"


def test_registry_save_after_corrupt_load_preserves_quarantine(tmp_path: Path):
    # The destructive half of the bug: after a corrupt load the next mutation
    # must not overwrite the recoverable data (it's quarantined, not lost).
    storage = tmp_path / "trig"
    storage.mkdir(parents=True)
    triggers_file = storage / "triggers.json"
    triggers_file.write_text("{garbage", encoding="utf-8")

    reg = TriggerRegistry(storage_dir=storage)
    reg.add(Trigger("new", EventType.CUSTOM, {}, {}))

    backup = storage / "triggers.json.corrupt"
    assert backup.read_text(encoding="utf-8") == "{garbage"
    # Fresh registry loads only the newly-added trigger from the rewritten file.
    reloaded = TriggerRegistry(storage_dir=storage)
    assert [t.name for t in reloaded.list_all()] == ["new"]


def test_registry_skips_single_bad_record_keeps_good_ones(tmp_path: Path):
    # Valid JSON array, but ONE record is malformed (missing required "name").
    # The good records must survive — a single bad entry must not quarantine
    # the whole file and destroy every other saved trigger.
    storage = tmp_path / "trig"
    storage.mkdir(parents=True)
    triggers_file = storage / "triggers.json"
    good = Trigger("good_one", EventType.CUSTOM, {"event_name": "x"}, {})
    also_good = Trigger("good_two", EventType.CUSTOM, {"event_name": "y"}, {})
    bad_record = {"event_type": "custom", "condition": {}, "action": {}}  # no "name"
    import json as _json
    triggers_file.write_text(
        _json.dumps([good.to_dict(), bad_record, also_good.to_dict()]),
        encoding="utf-8",
    )

    reg = TriggerRegistry(storage_dir=storage)
    names = sorted(t.name for t in reg.list_all())
    assert names == ["good_one", "good_two"]
    # The file is NOT quarantined — only a truly unparseable file is.
    assert triggers_file.exists()
    assert not (storage / "triggers.json.corrupt").exists()


# ---------------------------------------------------------------------------
# TriggerEngine
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine_with_registry(tmp_path: Path):
    reg = TriggerRegistry(storage_dir=tmp_path / "trig")
    mock_exec = MagicMock()
    eng = TriggerEngine(reg, executor_fn=mock_exec)
    yield eng, reg, mock_exec
    eng.stop()


def test_engine_start_stop(engine_with_registry):
    eng, _, _ = engine_with_registry
    eng.start()
    assert eng.running is True
    eng.stop()
    assert eng.running is False


def test_engine_start_idempotent(engine_with_registry):
    eng, _, _ = engine_with_registry
    eng.start()
    eng.start()  # second call must not raise or spawn extra thread
    assert eng.running is True


def test_engine_fire_custom_calls_executor(engine_with_registry):
    eng, reg, mock_exec = engine_with_registry
    action = {"action": "speak", "text": "hello"}
    t = Trigger("on_deploy", EventType.CUSTOM, {"event_name": "deploy"}, action)
    reg.add(t)

    eng.start()
    eng.fire_custom("deploy")
    # Give the engine thread time to process
    time.sleep(0.2)
    eng.stop()

    mock_exec.assert_called_once_with(action)


def test_engine_fire_custom_no_match(engine_with_registry):
    eng, reg, mock_exec = engine_with_registry
    t = Trigger("on_deploy", EventType.CUSTOM, {"event_name": "deploy"}, {"action": "speak"})
    reg.add(t)

    eng.start()
    eng.fire_custom("not_deploy")
    time.sleep(0.2)
    eng.stop()

    mock_exec.assert_not_called()


def test_engine_disabled_trigger_not_fired(engine_with_registry):
    eng, reg, mock_exec = engine_with_registry
    t = Trigger("dis", EventType.CUSTOM, {"event_name": "go"}, {"action": "speak"}, enabled=False)
    reg.add(t)

    eng.start()
    eng.fire_custom("go")
    time.sleep(0.2)
    eng.stop()

    mock_exec.assert_not_called()


def test_engine_executor_exception_does_not_crash(engine_with_registry):
    eng, reg, mock_exec = engine_with_registry
    mock_exec.side_effect = RuntimeError("boom")
    t = Trigger("boom", EventType.CUSTOM, {"event_name": "x"}, {"action": "speak"})
    reg.add(t)

    eng.start()
    eng.fire_custom("x")
    time.sleep(0.2)
    eng.stop()  # should not raise

    assert not eng.running
