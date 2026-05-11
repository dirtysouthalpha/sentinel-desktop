"""Tests for config save/load round-trip and defaults."""
import json
import os
from unittest import mock

import pytest

from config import Config, DEFAULTS


def test_defaults_have_expected_keys():
    for key in ("provider", "model", "max_steps", "approval_mode",
                "dry_run", "use_tools", "image_history", "monitor",
                "autonomous", "llm_max_retries", "llm_retry_base_delay"):
        assert key in DEFAULTS, f"missing default: {key}"


def test_monitor_defaults_to_virtual_desktop():
    # Default is 0 so the agent sees every screen out of the box.
    assert DEFAULTS["monitor"] == 0


def test_autonomous_defaults_to_off():
    # Safety: never default to autonomous; user must opt in.
    assert DEFAULTS["autonomous"] is False


def test_max_steps_default_is_int_and_positive():
    assert isinstance(DEFAULTS["max_steps"], int)
    assert DEFAULTS["max_steps"] > 0


def test_get_set_roundtrip():
    c = Config()
    c.set("provider", "openai")
    assert c.get("provider") == "openai"
    assert c["provider"] == "openai"
    c["model"] = "gpt-4o"
    assert c["model"] == "gpt-4o"


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    c = Config()
    c._path = str(path)
    c.set("provider", "anthropic")
    c.set("model", "claude-3-5-sonnet-20241022")
    c.set("api_key", "test-key")
    c.save()
    assert path.exists()

    c2 = Config()
    c2._path = str(path)
    data = c2.load()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-3-5-sonnet-20241022"
    assert data["api_key"] == "test-key"
    # Defaults still merged in:
    assert "max_steps" in data


def test_load_falls_back_to_defaults_when_corrupt(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json", encoding="utf-8")
    c = Config()
    c._path = str(path)
    data = c.load()
    assert data["provider"] == DEFAULTS["provider"]


def test_reset_restores_defaults():
    c = Config()
    c.set("provider", "anthropic")
    c.reset()
    assert c.get("provider") == DEFAULTS["provider"]
