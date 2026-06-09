"""Tests for MemoryTab — import, construction, data methods."""

from __future__ import annotations


class TestMemoryTabImport:
    """Verify MemoryTab can be imported."""

    def test_import(self):
        from gui.tabs.memory_tab import MemoryTab

        assert MemoryTab is not None

    def test_has_expected_methods(self):
        from gui.tabs.memory_tab import MemoryTab

        methods = [
            "_refresh_facts",
            "_select_fact",
            "_refresh_episodes",
            "_show_store_dialog",
            "_run_conductor",
            "_render_subtask_cards",
            "_set_conductor_output",
        ]
        for m in methods:
            assert hasattr(MemoryTab, m), f"Missing method: {m}"


class TestMemoryTabRegistration:
    """Verify MemoryTab is registered in app.py."""

    def test_tab_importable(self):
        import importlib

        mod = importlib.import_module("gui.tabs.memory_tab")
        assert hasattr(mod, "MemoryTab")

    def test_app_registers_memory_tab(self):
        with open("gui/app.py", encoding="utf-8") as f:
            content = f.read()
        assert "gui.tabs.memory_tab" in content
        assert "MemoryTab" in content
        assert "memory_tab" in content


class TestMemoryTabStyling:
    """Verify tab uses theme system."""

    def test_theme_helper_used(self):
        with open("gui/tabs/memory_tab.py", encoding="utf-8") as f:
            content = f.read()
        # Should assign self._t from app._t
        assert "self._t = app._t" in content
        # Should use theme keys like accent, bg_input
        assert "accent" in content
        assert "bg_input" in content
