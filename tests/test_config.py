"""Tests for configuration module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import VERSION, COLORS, load_config, save_config, DEFAULT_CONFIG


def test_version():
    assert VERSION == "6.1.0"


def test_colors():
    assert "bg_primary" in COLORS
    assert "accent" in COLORS
    assert "success" in COLORS


def test_load_config():
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "brain_url" in cfg
    assert "appearance" in cfg


def test_default_config():
    assert DEFAULT_CONFIG["brain_enabled"] is True
    assert "neuralis" in DEFAULT_CONFIG["api_provider"]
