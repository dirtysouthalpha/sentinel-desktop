"""Tests for core/profile.py — Sentinel Profile loading, adoption, and detection."""

import json
import sys
from pathlib import Path

import pytest

from core.profile import (
    Profile,
    ProfileError,
    adopt_profile,
    detect_profile,
    load_profile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(tmp_path: Path, **overrides) -> Path:
    """Write a minimal valid profile.json and return the profile directory."""
    manifest = {
        "name": "test-profile",
        "label": "Test Profile",
        "version": "1.0.0",
        "sentinel_compat": ">=1.0",
        "description": "A test profile.",
        **overrides,
    }
    (tmp_path / "profile.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------


class TestLoadProfile:
    def test_load_valid_profile_from_dir(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path)
        assert profile.name == "test-profile"
        assert profile.label == "Test Profile"
        assert profile.version == "1.0.0"
        assert profile.path == tmp_path

    def test_load_valid_profile_from_manifest_file(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path / "profile.json")
        assert profile.name == "test-profile"

    def test_load_missing_manifest_raises(self, tmp_path):
        with pytest.raises(ProfileError, match="not found"):
            load_profile(tmp_path)

    def test_load_malformed_json_raises(self, tmp_path):
        (tmp_path / "profile.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ProfileError, match="Malformed"):
            load_profile(tmp_path)

    def test_load_missing_required_field_raises(self, tmp_path):
        manifest = {"name": "x", "label": "x"}  # missing version, compat, description
        (tmp_path / "profile.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(ProfileError, match="missing fields"):
            load_profile(tmp_path)

    def test_compat_mismatch_warns_but_loads(self, tmp_path, caplog):
        import logging

        _make_manifest(tmp_path, sentinel_compat=">=999.0")
        with caplog.at_level(logging.WARNING, logger="core.profile"):
            profile = load_profile(tmp_path)
        assert profile.name == "test-profile"
        assert "sentinel_compat" in caplog.text or "requires" in caplog.text

    def test_includes_populated_from_manifest(self, tmp_path):
        _make_manifest(
            tmp_path,
            includes={"config": "my-config.json", "scripts_dir": "it-scripts"},
        )
        profile = load_profile(tmp_path)
        assert profile.includes.config == "my-config.json"
        assert profile.includes.scripts_dir == "it-scripts"

    def test_includes_defaults_when_absent(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path)
        assert profile.includes.config == "config.json"
        assert profile.includes.scripts_dir == "scripts"

    def test_flags_populated_from_manifest(self, tmp_path):
        _make_manifest(tmp_path, flags={"auto_adopt": False, "secrets_redacted": False})
        profile = load_profile(tmp_path)
        assert profile.flags.auto_adopt is False
        assert profile.flags.secrets_redacted is False

    def test_path_property_set(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path)
        assert profile.path == tmp_path

    def test_config_path_property_returns_none_when_missing(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path)
        assert profile.config_path is None  # no config.json in dir

    def test_config_path_property_returns_path_when_present(self, tmp_path):
        _make_manifest(tmp_path)
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        profile = load_profile(tmp_path)
        assert profile.config_path == tmp_path / "config.json"

    def test_scripts_dir_property_returns_none_when_missing(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path)
        assert profile.scripts_dir is None

    def test_scripts_dir_property_returns_path_when_present(self, tmp_path):
        _make_manifest(tmp_path)
        (tmp_path / "scripts").mkdir()
        profile = load_profile(tmp_path)
        assert profile.scripts_dir == tmp_path / "scripts"

    def test_brain_snapshot_property_returns_none_when_missing(self, tmp_path):
        _make_manifest(tmp_path)
        profile = load_profile(tmp_path)
        assert profile.brain_snapshot_path is None

    def test_brain_snapshot_property_returns_path_when_present(self, tmp_path):
        _make_manifest(tmp_path)
        (tmp_path / "brain-snapshot.jsonl").write_text("", encoding="utf-8")
        profile = load_profile(tmp_path)
        assert profile.brain_snapshot_path == tmp_path / "brain-snapshot.jsonl"


# ---------------------------------------------------------------------------
# adopt_profile
# ---------------------------------------------------------------------------


class TestAdoptProfile:
    def _make_profile(self, tmp_path: Path) -> tuple[Profile, Path]:
        """Create a full profile with config, scripts, and workflows."""
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        _make_manifest(profile_dir)
        (profile_dir / "config.json").write_text(json.dumps({"theme": "midnight"}))
        scripts = profile_dir / "scripts"
        scripts.mkdir()
        (scripts / "test.json").write_text("{}", encoding="utf-8")
        workflows = profile_dir / "workflows"
        workflows.mkdir()
        (workflows / "wf.json").write_text("{}", encoding="utf-8")
        profile = load_profile(profile_dir)
        target = tmp_path / "data"
        return profile, target

    def test_adopt_copies_config(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        adopt_profile(profile, target_dir=target)
        assert (target / "config.json").exists()

    def test_adopt_copies_scripts(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        adopt_profile(profile, target_dir=target)
        assert (target / "scripts" / "test.json").exists()

    def test_adopt_copies_workflows(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        adopt_profile(profile, target_dir=target)
        assert (target / "workflows" / "wf.json").exists()

    def test_adopt_no_clobber_existing_config(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        target.mkdir(parents=True, exist_ok=True)
        existing = target / "config.json"
        existing.write_text(json.dumps({"theme": "user-choice"}), encoding="utf-8")
        adopt_profile(profile, target_dir=target)
        # Should not overwrite
        assert json.loads(existing.read_text())["theme"] == "user-choice"

    def test_adopt_force_overwrites_config(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.json").write_text(json.dumps({"theme": "old"}), encoding="utf-8")
        adopt_profile(profile, target_dir=target, force=True)
        assert json.loads((target / "config.json").read_text())["theme"] == "midnight"

    def test_adopt_creates_target_dir(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        assert not target.exists()
        adopt_profile(profile, target_dir=target)
        assert target.exists()

    def test_adopt_no_clobber_existing_script(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "scripts").mkdir()
        existing = target / "scripts" / "test.json"
        existing.write_text('{"custom": true}', encoding="utf-8")
        adopt_profile(profile, target_dir=target)
        # Existing script kept
        assert json.loads(existing.read_text()).get("custom") is True

    def test_adopt_force_overwrites_script(self, tmp_path):
        profile, target = self._make_profile(tmp_path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "scripts").mkdir()
        (target / "scripts" / "test.json").write_text('{"custom": true}', encoding="utf-8")
        adopt_profile(profile, target_dir=target, force=True)
        data = json.loads((target / "scripts" / "test.json").read_text())
        assert "custom" not in data


# ---------------------------------------------------------------------------
# detect_profile
# ---------------------------------------------------------------------------


class TestDetectProfile:
    def test_detect_none_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        monkeypatch.delenv("SENTINEL_PROFILE", raising=False)
        assert detect_profile() is None

    def test_detect_embedded_profile(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        monkeypatch.delenv("SENTINEL_PROFILE", raising=False)
        profiles_dir = tmp_path / "profiles" / "my-profile"
        profiles_dir.mkdir(parents=True)
        _make_manifest(profiles_dir, name="my-profile")
        result = detect_profile()
        assert result is not None
        assert result.name == "my-profile"

    def test_detect_dropped_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        monkeypatch.delenv("SENTINEL_PROFILE", raising=False)
        dropped = tmp_path / "sentinel-profile"
        dropped.mkdir()
        _make_manifest(dropped, name="dropped")
        result = detect_profile()
        assert result is not None
        assert result.name == "dropped"

    def test_detect_cli_arg_wins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        monkeypatch.delenv("SENTINEL_PROFILE", raising=False)
        # Also create an embedded profile — CLI arg should win
        embedded_dir = tmp_path / "profiles" / "embedded"
        embedded_dir.mkdir(parents=True)
        _make_manifest(embedded_dir, name="embedded")
        cli_dir = tmp_path / "cli-profile"
        cli_dir.mkdir()
        _make_manifest(cli_dir, name="cli-profile")
        result = detect_profile(cli_arg=str(cli_dir))
        assert result is not None
        assert result.name == "cli-profile"

    def test_detect_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        env_dir = tmp_path / "env-profile"
        env_dir.mkdir()
        _make_manifest(env_dir, name="env-profile")
        monkeypatch.setenv("SENTINEL_PROFILE", str(env_dir))
        result = detect_profile()
        assert result is not None
        assert result.name == "env-profile"

    def test_detect_bad_cli_arg_falls_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        monkeypatch.delenv("SENTINEL_PROFILE", raising=False)
        result = detect_profile(cli_arg=str(tmp_path / "nonexistent"))
        assert result is None  # no other profiles present


# ---------------------------------------------------------------------------
# Bundled field-it-tech profile
# ---------------------------------------------------------------------------


class TestBundledProfile:
    """Verify the profiles/field-it-tech/ directory in the repo is valid."""

    def test_field_it_tech_loads(self):
        profile_dir = Path(__file__).parent.parent / "profiles" / "field-it-tech"
        assert profile_dir.exists(), "profiles/field-it-tech/ must exist"
        profile = load_profile(profile_dir)
        assert profile.name == "field-it-tech"

    def test_field_it_tech_has_scripts(self):
        profile_dir = Path(__file__).parent.parent / "profiles" / "field-it-tech"
        profile = load_profile(profile_dir)
        assert profile.scripts_dir is not None
        scripts = list(profile.scripts_dir.iterdir())
        assert len(scripts) >= 19, "Should have at least 19 IT scripts"

    def test_field_it_tech_config_has_no_api_key(self):
        profile_dir = Path(__file__).parent.parent / "profiles" / "field-it-tech"
        profile = load_profile(profile_dir)
        if profile.config_path:
            cfg = json.loads(profile.config_path.read_text(encoding="utf-8"))
            assert cfg.get("api_key", "") == "", "API key must be empty in bundled profile"
