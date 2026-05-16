"""Tests for gui/tabs/scripts_tab.py — logic methods with mocked CTk."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import pytest


@pytest.fixture()
def mock_app(tmp_path):
    app = MagicMock()
    app._t = lambda k, f="#fff": f
    app.cfg = {"script_base": str(tmp_path)}
    return app


@pytest.fixture()
def scripts_tab(mock_app):
    from gui.tabs.scripts_tab import ScriptsTab

    parent = ctk.CTkFrame()
    tab = ScriptsTab(parent, mock_app)
    return tab


class TestScriptsTabRefresh:
    def test_refresh_empty_dir(self, scripts_tab, mock_app, tmp_path):
        scripts_tab._scripts.clear()
        scripts_tab.refresh_scripts()
        assert scripts_tab._scripts == []

    def test_refresh_scans_script_dirs(self, scripts_tab, mock_app, tmp_path):
        script_dir = tmp_path / "scripts" / "it_support"
        script_dir.mkdir(parents=True)
        (script_dir / "test_script.json").write_text(
            json.dumps({"name": "Test Script", "description": "A test", "steps": [{"action": "click"}]})
        )
        scripts_tab.refresh_scripts()
        assert len(scripts_tab._scripts) == 1
        assert scripts_tab._scripts[0]["name"] == "Test Script"

    def test_refresh_skips_invalid_json(self, scripts_tab, mock_app, tmp_path):
        script_dir = tmp_path / "scripts" / "it_support"
        script_dir.mkdir(parents=True)
        (script_dir / "bad.json").write_text("not valid json{{{")
        (script_dir / "good.json").write_text(json.dumps({"name": "Good"}))
        scripts_tab.refresh_scripts()
        assert len(scripts_tab._scripts) == 1
        assert scripts_tab._scripts[0]["name"] == "Good"

    def test_refresh_skips_nonexistent_dirs(self, scripts_tab, mock_app, tmp_path):
        scripts_tab._scripts.clear()
        scripts_tab.refresh_scripts()
        assert scripts_tab._scripts == []


class TestScriptsTabCategory:
    def test_set_category_updates_active(self, scripts_tab):
        scripts_tab._chip_btns = [MagicMock()]
        scripts_tab._t = lambda k, f="#fff": f
        scripts_tab._set_category("All")
        assert scripts_tab._active_category == "All"

    def test_set_category_unknown_defaults_all(self, scripts_tab):
        scripts_tab._chip_btns = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        scripts_tab._t = lambda k, f="#fff": f
        scripts_tab._set_category("NonExistent")
        assert scripts_tab._active_category == "NonExistent"


class TestScriptsTabFilter:
    def test_apply_filter_by_category(self, scripts_tab):
        scripts_tab._scripts = [
            {"name": "A", "_folder": "scripts/it_support"},
            {"name": "B", "_folder": "scripts/custom"},
        ]
        scripts_tab._search_var = MagicMock()
        scripts_tab._search_var.get.return_value = ""
        scripts_tab._active_category = "IT Support"
        scripts_tab._populate_list = MagicMock()
        scripts_tab._count_label = MagicMock()
        scripts_tab._apply_filter()
        filtered_list = scripts_tab._populate_list.call_args[0][0]
        assert len(filtered_list) == 1
        assert filtered_list[0]["name"] == "A"

    def test_apply_filter_by_search_query(self, scripts_tab):
        scripts_tab._scripts = [
            {"name": "Install Office", "description": "Install MS Office"},
            {"name": "Reset Password", "description": "Reset AD password"},
        ]
        scripts_tab._search_var = MagicMock()
        scripts_tab._search_var.get.return_value = "password"
        scripts_tab._active_category = "All"
        scripts_tab._populate_list = MagicMock()
        scripts_tab._count_label = MagicMock()
        scripts_tab._apply_filter()
        filtered_list = scripts_tab._populate_list.call_args[0][0]
        assert len(filtered_list) == 1
        assert filtered_list[0]["name"] == "Reset Password"


class TestScriptsTabSelect:
    def test_select_script_found(self, scripts_tab):
        scripts_tab._scripts = [
            {"_path": "/a/b.json", "name": "Test", "description": "Desc", "steps": [{"action": "x"}]},
        ]
        scripts_tab._name_label = MagicMock()
        scripts_tab._desc_label = MagicMock()
        scripts_tab._meta_label = MagicMock()
        scripts_tab._build_param_fields = MagicMock()
        scripts_tab.select_script("/a/b.json")
        assert scripts_tab._selected_path == "/a/b.json"

    def test_select_script_not_found(self, scripts_tab):
        scripts_tab.select_script("/nonexistent.json")
        assert scripts_tab._selected_script is None


class TestScriptsTabRunSelected:
    def test_run_no_selection(self, scripts_tab):
        scripts_tab._selected_script = None
        scripts_tab._selected_path = None
        scripts_tab._append_output = MagicMock()
        scripts_tab.run_selected_script()
        scripts_tab._append_output.assert_called_once()
        assert "No script selected" in scripts_tab._append_output.call_args[0][0]
