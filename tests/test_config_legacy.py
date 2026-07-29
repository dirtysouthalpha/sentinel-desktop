"""Tests for core/config_legacy.py — configuration, paths, and config load/save."""

import json
from pathlib import Path

import pytest

import core.config_legacy as cfg


class TestPaths:
    def test_app_dir_is_project_root(self):
        assert cfg.APP_DIR.name == "sentinel-desktop"

    def test_data_dir_is_hidden_home_subdir(self):
        assert cfg.DATA_DIR == Path.home() / ".sentinel-desktop"

    def test_log_dir_under_data_dir(self):
        assert cfg.LOG_DIR == cfg.DATA_DIR / "logs"

    def test_screenshot_dir_under_data_dir(self):
        assert cfg.SCREENSHOT_DIR == cfg.DATA_DIR / "screenshots"

    def test_config_file_under_data_dir(self):
        assert cfg.CONFIG_FILE == cfg.DATA_DIR / "config.json"


class TestConstants:
    def test_version_matches(self):
        assert cfg.VERSION == "31.0.0"

    def test_app_title(self):
        assert cfg.APP_TITLE == "Sentinel Desktop v31.0.0"

    def test_brain_timeout_positive(self):
        assert cfg.BRAIN_TIMEOUT > 0

    def test_window_dimensions_valid(self):
        assert cfg.WINDOW_WIDTH > 0
        assert cfg.WINDOW_HEIGHT > 0
        assert cfg.WINDOW_MIN_WIDTH > 0
        assert cfg.WINDOW_MIN_HEIGHT > 0


class TestColors:
    def test_required_keys_present(self):
        required = {"bg_primary", "bg_secondary", "accent", "text_primary", "success", "error"}
        assert required <= set(cfg.COLORS.keys())

    def test_hex_format(self):
        for key, val in cfg.COLORS.items():
            assert val.startswith("#"), f"{key} not hex: {val}"
            assert len(val) == 7, f"{key} bad length: {val}"


class TestDefaultConfig:
    def test_default_keys(self):
        assert "brain_url" in cfg.DEFAULT_CONFIG
        assert "brain_enabled" in cfg.DEFAULT_CONFIG
        assert "appearance" in cfg.DEFAULT_CONFIG
        assert cfg.DEFAULT_CONFIG["appearance"] == "dark"

    def test_default_brain_enabled(self):
        assert cfg.DEFAULT_CONFIG["brain_enabled"] is True


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "nonexistent.json")
        result = cfg.load_config()
        assert result == cfg.DEFAULT_CONFIG

    def test_loads_existing_config(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        user_cfg = {"appearance": "light", "mouse_speed": 0.5}
        cfg_file.write_text(json.dumps(user_cfg))
        monkeypatch.setattr(cfg, "CONFIG_FILE", cfg_file)
        result = cfg.load_config()
        assert result["appearance"] == "light"
        assert result["mouse_speed"] == 0.5
        # Defaults fill in missing keys
        assert "brain_url" in result

    def test_corrupted_file_returns_defaults(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("{not valid json")
        monkeypatch.setattr(cfg, "CONFIG_FILE", cfg_file)
        result = cfg.load_config()
        assert result == cfg.DEFAULT_CONFIG


class TestSaveConfig:
    def test_save_writes_file(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        monkeypatch.setattr(cfg, "CONFIG_FILE", cfg_file)
        cfg.save_config({"appearance": "light"})
        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text())
        assert data["appearance"] == "light"

    def test_save_is_atomic(self, tmp_path, monkeypatch):
        """save_config uses atomic_write_text, so a crash mid-write can't corrupt."""
        cfg_file = tmp_path / "config.json"
        monkeypatch.setattr(cfg, "CONFIG_FILE", cfg_file)
        cfg.save_config({"key": "value"})
        # File should be valid JSON after save
        data = json.loads(cfg_file.read_text())
        assert data["key"] == "value"


class TestCommandCategories:
    def test_categories_dict(self):
        assert "system" in cfg.COMMAND_CATEGORIES
        assert "automation" in cfg.COMMAND_CATEGORIES
        assert "network" in cfg.COMMAND_CATEGORIES
