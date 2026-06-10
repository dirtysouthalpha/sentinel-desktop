"""Tests for core.config_store — JSON configuration persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.config_store import ConfigStore


# ── Core CRUD ─────────────────────────────────────────────────────────────────

class TestConfigStore:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        Path(self.tmp.name).unlink()  # remove so ConfigStore starts empty
        self.cfg = ConfigStore(path=self.tmp.name)

    def teardown_method(self):
        try:
            Path(self.tmp.name).unlink(missing_ok=True)
        except Exception:
            pass

    def test_get_returns_default_for_missing_key(self):
        assert self.cfg.get("missing.key") is None
        assert self.cfg.get("missing.key", "default") == "default"

    def test_set_and_get_simple_key(self):
        self.cfg.set("foo", "bar", auto_save=False)
        assert self.cfg.get("foo") == "bar"

    def test_set_and_get_nested_key(self):
        self.cfg.set("llm.provider", "openai", auto_save=False)
        assert self.cfg.get("llm.provider") == "openai"

    def test_deep_nesting(self):
        self.cfg.set("a.b.c.d", 42, auto_save=False)
        assert self.cfg.get("a.b.c.d") == 42

    def test_overwrite_existing_key(self):
        self.cfg.set("key", "first", auto_save=False)
        self.cfg.set("key", "second", auto_save=False)
        assert self.cfg.get("key") == "second"

    def test_delete_existing_key(self):
        self.cfg.set("key", "val", auto_save=False)
        deleted = self.cfg.delete("key", auto_save=False)
        assert deleted is True
        assert self.cfg.get("key") is None

    def test_delete_missing_key_returns_false(self):
        assert self.cfg.delete("nonexistent.key", auto_save=False) is False

    def test_keys_returns_all_flat_keys(self):
        self.cfg.set("a.b", 1, auto_save=False)
        self.cfg.set("c", 2, auto_save=False)
        keys = self.cfg.keys()
        assert "a.b" in keys
        assert "c" in keys

    def test_keys_with_prefix_filter(self):
        self.cfg.set("llm.provider", "openai", auto_save=False)
        self.cfg.set("llm.model", "gpt-4", auto_save=False)
        self.cfg.set("other.key", "val", auto_save=False)
        keys = self.cfg.keys(prefix="llm")
        assert "llm.provider" in keys
        assert "llm.model" in keys
        assert "other.key" not in keys

    def test_save_and_reload(self):
        self.cfg.set("persist.this", "value", auto_save=True)
        reloaded = ConfigStore(path=self.tmp.name)
        assert reloaded.get("persist.this") == "value"

    def test_reset_clears_all_keys(self):
        self.cfg.set("a", 1, auto_save=False)
        self.cfg.set("b", 2, auto_save=False)
        self.cfg.reset(auto_save=False)
        assert self.cfg.keys() == []

    def test_save_creates_parent_dirs(self, tmp_path):
        nested_path = tmp_path / "a" / "b" / "config.json"
        cfg = ConfigStore(path=nested_path)
        cfg.set("x", 1, auto_save=True)
        assert nested_path.exists()

    def test_corrupted_file_starts_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{{not valid json}}")
        cfg = ConfigStore(path=bad)
        assert cfg.get("anything") is None

    def test_all_returns_dict_copy(self):
        self.cfg.set("k", "v", auto_save=False)
        d = self.cfg.all()
        assert isinstance(d, dict)
        d["k"] = "modified"  # mutation should not affect store
        assert self.cfg.get("k") == "v"

    def test_set_various_types(self):
        self.cfg.set("int_val", 42, auto_save=False)
        self.cfg.set("list_val", [1, 2, 3], auto_save=False)
        self.cfg.set("dict_val", {"x": 1}, auto_save=False)
        self.cfg.set("bool_val", False, auto_save=False)
        assert self.cfg.get("int_val") == 42
        assert self.cfg.get("list_val") == [1, 2, 3]
        assert self.cfg.get("bool_val") is False


# ── Executor integration ──────────────────────────────────────────────────────

class TestConfigActionsInExecutor:
    def test_config_get_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "config_get" in ActionExecutor._dispatch_table

    def test_config_set_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "config_set" in ActionExecutor._dispatch_table

    def test_config_set_get_round_trip(self, tmp_path, monkeypatch):
        # Patch the default store to use a temp path
        from core import config_store
        store = ConfigStore(path=tmp_path / "test_config.json")
        monkeypatch.setattr(config_store, "_SINGLETON", store)

        from core.action_executor import ActionExecutor
        executor = ActionExecutor()

        set_result = executor.execute_sync({
            "action": "config_set",
            "key": "test.key",
            "value": "test_value",
        })
        assert set_result["success"] is True

        get_result = executor.execute_sync({
            "action": "config_get",
            "key": "test.key",
        })
        assert get_result["success"] is True
        assert get_result["value"] == "test_value"
