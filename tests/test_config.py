"""Tests for config save/load round-trip and defaults."""

from config import DEFAULTS, Config


def test_defaults_have_expected_keys():
    for key in (
        "provider",
        "model",
        "max_steps",
        "approval_mode",
        "dry_run",
        "use_tools",
        "image_history",
        "monitor",
        "autonomous",
        "llm_max_retries",
        "llm_retry_base_delay",
    ):
        assert key in DEFAULTS, f"missing default: {key}"


def test_monitor_default_is_auto():
    # "auto" picks the monitor with the focused window; falls back to
    # the virtual desktop union (0) on multi-monitor setups.
    assert DEFAULTS["monitor"] == "auto"


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


# ---------------------------------------------------------------------------
# Dict-like access
# ---------------------------------------------------------------------------


def test_contains():
    c = Config()
    assert "provider" in c
    assert "nonexistent_key_xyz" not in c


def test_as_dict_returns_copy():
    c = Config()
    d = c.as_dict()
    assert isinstance(d, dict)
    assert d is not c._data
    assert d == c._data


def test_get_with_default():
    c = Config()
    assert c.get("nonexistent_key_xyz", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_load_returns_defaults_when_no_file(tmp_path):
    c = Config()
    c._path = str(tmp_path / "nonexistent.json")
    data = c.load()
    assert data["provider"] == DEFAULTS["provider"]


def test_save_with_data_arg(tmp_path):
    path = tmp_path / "config.json"
    c = Config()
    c._path = str(path)
    c.save(data={"provider": "ollama", "model": "llama3"})
    assert path.exists()
    c2 = Config()
    c2._path = str(path)
    data = c2.load()
    assert data["provider"] == "ollama"
    assert data["model"] == "llama3"


def test_save_handles_oserror(tmp_path, monkeypatch):
    c = Config()
    c._path = str(tmp_path / "subdir" / "config.json")

    monkeypatch.setattr(
        "builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full"))
    )
    # Should not raise — logs the error and returns.
    c.save()


# ---------------------------------------------------------------------------
# Convenience properties
# ---------------------------------------------------------------------------


def test_provider_property():
    c = Config()
    assert c.provider == DEFAULTS["provider"]
    c["provider"] = "anthropic"
    assert c.provider == "anthropic"


def test_api_key_property():
    c = Config()
    c.set("api_key", "sk-test")
    assert c.api_key == "sk-test"


def test_model_property():
    c = Config()
    c.set("model", "gpt-4o")
    assert c.model == "gpt-4o"


def test_max_steps_property():
    c = Config()
    assert isinstance(c.max_steps, int)
    assert c.max_steps > 0


def test_approval_mode_property():
    c = Config()
    default_val = DEFAULTS.get("approval_mode", True)
    assert c.approval_mode == default_val
    c.approval_mode = False
    assert c.approval_mode is False
    assert c["approval_mode"] is False
