"""Tests for BrainTab GUI panel (gui/tabs/brain_tab.py).

Strategy: stub out tkinter and customtkinter with lightweight fakes so the
tests run headless without a display. Same pattern used by memory_tab tests.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Fake CTk widgets ─────────────────────────────────────────────────────────


class FakeWidget:
    """A thin tkinter/CTk widget stand-in that records configure calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cfg: dict[str, Any] = dict(kwargs)
        self._children: list[FakeWidget] = []
        self._grid_kwargs: dict[str, Any] = {}
        self._grid_forgotten = False
        self._text = kwargs.get("text", "")
        self._state = kwargs.get("state", "normal")

    # Grid API
    def grid(self, **kwargs: Any) -> None:
        self._grid_kwargs = kwargs
        self._grid_forgotten = False

    def grid_forget(self) -> None:
        self._grid_forgotten = True

    def grid_columnconfigure(self, *_: Any, **__: Any) -> None:
        pass

    def grid_rowconfigure(self, *_: Any, **__: Any) -> None:
        pass

    # Widget API
    def configure(self, **kwargs: Any) -> None:
        self._cfg.update(kwargs)
        if "text" in kwargs:
            self._text = kwargs["text"]
        if "state" in kwargs:
            self._state = kwargs["state"]

    def cget(self, key: str) -> Any:
        return self._cfg.get(key, "")

    def winfo_children(self) -> list:
        return []

    def winfo_exists(self) -> bool:
        return True

    def after(self, ms: int, fn: Any = None, *args: Any) -> None:
        pass

    def destroy(self) -> None:
        pass

    # Textbox API
    def get(self, *args: Any) -> str:
        return self._cfg.get("text", "")

    def delete(self, *_: Any) -> None:
        pass

    def insert(self, *_: Any) -> None:
        pass

    def bind(self, *_: Any, **__: Any) -> None:
        pass


class FakeScrollableFrame(FakeWidget):
    pass


class FakeEntry(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._value = ""

    def get(self, *_: Any) -> str:
        return self._value

    def delete(self, *_: Any) -> None:
        self._value = ""


class FakeTextbox(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._value = ""

    def get(self, *_: Any) -> str:
        return self._value

    def delete(self, *_: Any) -> None:
        self._value = ""

    def insert(self, pos: Any, text: str) -> None:
        self._value += text


class FakeStringVar:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, v: str) -> None:
        self._value = v


class FakeOptionMenu(FakeWidget):
    pass


class FakeButton(FakeWidget):
    def __init__(self, *args: Any, command: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._command = command

    def invoke(self) -> Any:
        if self._command:
            return self._command()
        return None


class FakeLabel(FakeWidget):
    pass


class FakeCTk(types.ModuleType):
    """Fake customtkinter module."""

    CTkFrame = FakeWidget
    CTkScrollableFrame = FakeScrollableFrame
    CTkLabel = FakeLabel
    CTkButton = FakeButton
    CTkEntry = FakeEntry
    CTkTextbox = FakeTextbox
    CTkOptionMenu = FakeOptionMenu
    StringVar = FakeStringVar

    @staticmethod
    def CTkFrame(*args: Any, **kwargs: Any) -> FakeWidget:  # type: ignore[override]
        return FakeWidget(*args, **kwargs)


# ── Fake tkinter (for TclError) ───────────────────────────────────────────────


class FakeTkinter(types.ModuleType):
    class TclError(Exception):
        pass

    class Frame:
        pass


# ── Install stubs before any import of the module under test ─────────────────


def _install_stubs() -> None:
    # customtkinter — must be a superset of what conftest installs so that
    # tests running after this file don't see a broken stub.
    ctk_mod = types.ModuleType("customtkinter")
    ctk_mod.CTkFrame = FakeWidget  # type: ignore[attr-defined]
    ctk_mod.CTkScrollableFrame = FakeScrollableFrame  # type: ignore[attr-defined]
    ctk_mod.CTkLabel = FakeLabel  # type: ignore[attr-defined]
    ctk_mod.CTkButton = FakeButton  # type: ignore[attr-defined]
    ctk_mod.CTkEntry = FakeEntry  # type: ignore[attr-defined]
    ctk_mod.CTkTextbox = FakeTextbox  # type: ignore[attr-defined]
    ctk_mod.CTkOptionMenu = FakeOptionMenu  # type: ignore[attr-defined]
    ctk_mod.StringVar = FakeStringVar  # type: ignore[attr-defined]
    # Remaining CTk widget classes used by other GUI modules
    for _cls_name in (
        "CTk",
        "CTkCheckBox",
        "CTkComboBox",
        "CTkProgressBar",
        "CTkRadioButton",
        "CTkSlider",
        "CTkSwitch",
        "CTkTabview",
        "CTkImage",
        "CTkCanvas",
        "CTkSegmentedButton",
        "CTkToplevel",
    ):
        setattr(ctk_mod, _cls_name, type(_cls_name, (FakeWidget,), {}))
    ctk_mod.CTkFont = lambda *a, **kw: None  # type: ignore[attr-defined]
    # Typed variable stubs
    for _var_name in ("IntVar", "DoubleVar", "BooleanVar"):
        setattr(
            ctk_mod,
            _var_name,
            type(
                _var_name,
                (),
                {
                    "__init__": lambda s, *a, **kw: None,
                    "get": lambda s: 0,
                    "set": lambda s, v: None,
                    "trace_add": lambda s, *a, **kw: None,
                },
            ),
        )
    # Module-level functions and constants used by themes.py / app.py
    ctk_mod.set_appearance_mode = lambda *a, **kw: None  # type: ignore[attr-defined]
    ctk_mod.set_default_color_theme = lambda *a, **kw: None  # type: ignore[attr-defined]
    ctk_mod.set_widget_scaling = lambda *a, **kw: None  # type: ignore[attr-defined]
    ctk_mod.DARK = "Dark"  # type: ignore[attr-defined]
    ctk_mod.LIGHT = "Light"  # type: ignore[attr-defined]
    ctk_mod.SYSTEM = "System"  # type: ignore[attr-defined]
    sys.modules["customtkinter"] = ctk_mod

    # tkinter
    tk_mod = FakeTkinter("tkinter")
    sys.modules.setdefault("tkinter", tk_mod)


@pytest.fixture(autouse=True)
def _restore_ctk_after_test():
    """Restore the customtkinter stub to its pre-test state after each test.

    Saving and restoring (rather than deleting) keeps all module-level
    ``import customtkinter as ctk`` bindings in other test files pointing to
    the same object, preventing cross-test assertion failures when those tests
    call ``patch.object(ctk, ...)``.
    """
    original = sys.modules.get("customtkinter")
    yield
    if original is not None:
        sys.modules["customtkinter"] = original
    else:
        sys.modules.pop("customtkinter", None)


# ── Load the module under test ────────────────────────────────────────────────


def _make_app() -> MagicMock:
    """Return a fake app with the minimal interface BrainTab needs."""
    app = MagicMock()

    def _t(key: str, default: str = "") -> str:
        return default

    app._t = _t
    return app


def _load_brain_tab():
    """Import (or reload) BrainTab with the fakes in place."""
    _install_stubs()  # reinstall brain-tab fakes — conftest may have replaced them
    if "gui.tabs.brain_tab" in sys.modules:
        del sys.modules["gui.tabs.brain_tab"]
    if "gui.tabs" in sys.modules:
        del sys.modules["gui.tabs"]
    mod = importlib.import_module("gui.tabs.brain_tab")
    return mod


def _make_tab():
    """Return a BrainTab instance ready for assertions."""
    mod = _load_brain_tab()
    app = _make_app()
    # Disable after() so the tick doesn't fire in tests
    with patch.object(FakeWidget, "after", lambda *_a, **_kw: None):
        tab = mod.BrainTab(FakeWidget(), app)
    return tab


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestBrainTabInit:
    def test_import_succeeds(self) -> None:
        mod = _load_brain_tab()
        assert hasattr(mod, "BrainTab")

    def test_instantiation_does_not_raise(self) -> None:
        tab = _make_tab()
        assert tab is not None

    def test_available_starts_false(self) -> None:
        tab = _make_tab()
        assert tab._available is False

    def test_pulse_state_starts_false(self) -> None:
        tab = _make_tab()
        assert tab._pulse_state is False

    def test_advanced_visible_starts_false(self) -> None:
        tab = _make_tab()
        assert tab._advanced_visible is False

    def test_busy_flags_start_false(self) -> None:
        tab = _make_tab()
        assert tab._busy_recall is False
        assert tab._busy_think is False
        assert tab._busy_search is False


class TestSearchRecallIndependence:
    """Search and Recall must use independent busy flags.

    Regression: _do_search previously guarded on _busy_recall, so an in-flight
    recall silently swallowed every search (and vice-versa).
    """

    def test_pending_recall_does_not_block_search(self) -> None:
        tab = _make_tab()
        # Patch Thread inert so no background brain call runs during the test.
        with patch("gui.tabs.brain_tab.threading.Thread"):
            tab._busy_recall = True  # a recall is in flight
            tab._do_search()
            # Search must still launch under its own flag.
            assert tab._busy_search is True

    def test_search_in_flight_blocks_repeat_search(self) -> None:
        tab = _make_tab()
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            tab._busy_search = True  # a search is already running
            tab._do_search()
            # Must not launch a second concurrent search.
            mock_thread.return_value.start.assert_not_called()


class TestStatsRendering:
    def test_offline_status_text(self) -> None:
        tab = _make_tab()
        tab._render_stats(False, {})
        assert "offline" in tab._status_line._text.lower()

    def test_online_status_text(self) -> None:
        tab = _make_tab()
        brain_stats = {
            "totals": {"neurons": 1234, "synapses": 567},
            "neurons_per_region": [{"region": "knowledge", "count": 800}],
            "recent_neurons_24h": [],
        }
        tab._render_stats(True, brain_stats)
        assert "online" in tab._status_line._text.lower()
        assert "1,234" in tab._status_line._text

    def test_region_line_shows_regions(self) -> None:
        tab = _make_tab()
        brain_stats = {
            "totals": {"neurons": 10, "synapses": 5},
            "neurons_per_region": [
                {"region": "knowledge", "count": 8},
                {"region": "context", "count": 2},
            ],
            "recent_neurons_24h": [],
        }
        tab._render_stats(True, brain_stats)
        assert "knowledge" in tab._region_line._text

    def test_offline_clears_region_line(self) -> None:
        tab = _make_tab()
        tab._region_line._text = "was set"
        tab._render_stats(False, {})
        assert tab._region_line._text == ""


class TestFeedRendering:
    def test_offline_shows_placeholder(self) -> None:
        tab = _make_tab()
        # Patch winfo_children so we can detect the label creation
        created: list[str] = []

        class CapturingLabel(FakeLabel):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(kwargs.get("text", ""))

        with patch.dict(sys.modules, {}):
            with patch("gui.tabs.brain_tab.ctk.CTkLabel", CapturingLabel):
                tab._render_feed(False, {})
        # At least one label should mention offline
        assert any("offline" in t.lower() for t in created)

    def test_empty_neurons_shows_no_recent(self) -> None:
        tab = _make_tab()
        created: list[str] = []

        class CapturingLabel(FakeLabel):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(kwargs.get("text", ""))

        with patch("gui.tabs.brain_tab.ctk.CTkLabel", CapturingLabel):
            tab._render_feed(True, {"neurons": []})
        assert any("no recent" in t.lower() for t in created)


class TestRecallResults:
    def test_error_shows_in_results(self) -> None:
        tab = _make_tab()
        tab._render_recall_results({"error": "connection refused"})
        assert "Error" in tab._results_text._value
        assert "connection refused" in tab._results_text._value

    def test_empty_shows_nothing_found(self) -> None:
        tab = _make_tab()
        tab._render_recall_results({"neurons": []})
        assert "Nothing found" in tab._results_text._value

    def test_neurons_show_content_snippet(self) -> None:
        tab = _make_tab()
        neurons = [
            {"content": "A fact about the fleet.", "score": 0.95},
            {"content": "Another thought.", "score": 0.80},
        ]
        tab._render_recall_results({"neurons": neurons})
        assert "A fact about the fleet" in tab._results_text._value

    def test_score_displayed(self) -> None:
        tab = _make_tab()
        neurons = [{"content": "something", "score": 0.75}]
        tab._render_recall_results({"neurons": neurons})
        assert "0.75" in tab._results_text._value


class TestSearchResults:
    def test_error_shows(self) -> None:
        tab = _make_tab()
        tab._render_search_results({"error": "timeout"})
        assert "Error" in tab._results_text._value

    def test_no_results_shows(self) -> None:
        tab = _make_tab()
        tab._render_search_results({"neurons": []})
        assert "No results" in tab._results_text._value

    def test_content_rendered(self) -> None:
        tab = _make_tab()
        tab._render_search_results({"neurons": [{"content": "Fleet memory fact."}]})
        assert "Fleet memory fact" in tab._results_text._value


class TestSetResults:
    def test_set_results_updates_textbox(self) -> None:
        tab = _make_tab()
        tab._set_results("hello world")
        assert "hello world" in tab._results_text._value


class TestThink:
    def test_finish_think_ok_clears_fields(self) -> None:
        tab = _make_tab()
        tab._busy_think = True
        # Mock the refresh so it doesn't fire background work
        with patch.object(tab, "_refresh_now"):
            tab._finish_think(True, None)
        assert not tab._busy_think
        assert "✓" in tab._think_status._text

    def test_finish_think_error_shows_message(self) -> None:
        tab = _make_tab()
        tab._busy_think = True
        tab._finish_think(False, "timeout")
        assert "timeout" in tab._think_status._text
        assert not tab._busy_think


class TestDoThinkGuard:
    def test_busy_guard_prevents_double_call(self) -> None:
        tab = _make_tab()
        tab._busy_think = True
        # Should return early without starting a thread
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            tab._do_think()
        mock_thread.assert_not_called()

    def test_unavailable_guard_prevents_call(self) -> None:
        tab = _make_tab()
        tab._available = False
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            tab._do_think()
        mock_thread.assert_not_called()


class TestFireGuard:
    def test_invalid_id_shows_error(self) -> None:
        tab = _make_tab()
        tab._fire_entry._value = "notanumber"
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            tab._do_fire()
        mock_thread.assert_not_called()
        assert "invalid" in tab._fire_status._text

    def test_empty_id_does_nothing(self) -> None:
        tab = _make_tab()
        tab._fire_entry._value = ""
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            tab._do_fire()
        mock_thread.assert_not_called()


class TestFireFinish:
    def test_fire_ok_sets_status(self) -> None:
        tab = _make_tab()
        # Simulate the after() callback directly
        tab._fire_status.configure(text="✓ Fired")
        assert "Fired" in tab._fire_status._text

    def test_fire_fail_sets_status(self) -> None:
        tab = _make_tab()
        tab._fire_status.configure(text="✗ failed")
        assert "failed" in tab._fire_status._text


class TestDoRecallGuard:
    def test_empty_query_does_nothing(self) -> None:
        tab = _make_tab()
        tab._recall_entry._value = ""
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            tab._do_recall()
        mock_thread.assert_not_called()

    def test_busy_guard(self) -> None:
        tab = _make_tab()
        tab._recall_entry._value = "something"
        tab._busy_recall = True
        with patch("gui.tabs.brain_tab.threading.Thread") as mock_thread:
            tab._do_recall()
        mock_thread.assert_not_called()


class TestToggleAdvanced:
    def test_toggle_advanced_flips_state(self) -> None:
        tab = _make_tab()
        assert not tab._advanced_visible
        tab._toggle_advanced()
        assert tab._advanced_visible
        tab._toggle_advanced()
        assert not tab._advanced_visible


class TestApplyOnlineState:
    def test_online_enables_remember_button(self) -> None:
        tab = _make_tab()
        tab._apply_online_state(True)
        assert tab._remember_btn._state == "normal"

    def test_offline_disables_remember_button(self) -> None:
        tab = _make_tab()
        tab._apply_online_state(False)
        assert tab._remember_btn._state == "disabled"


class TestPulseTick:
    def test_pulse_state_flips(self) -> None:
        tab = _make_tab()
        initial = tab._pulse_state
        # Manually call; after() is stubbed so it won't recurse
        with patch.object(tab, "after", lambda *_a, **_kw: None):
            tab._pulse_tick()
        assert tab._pulse_state != initial


class TestTabRegistration:
    def test_brain_tab_in_tab_defs(self) -> None:
        """Verify BrainTab is registered in gui/app.py _TAB_DEFS."""
        # Parse the file — no need to import/delete the module
        from pathlib import Path

        content = Path("gui/app.py").read_text()
        assert '"brain"' in content
        assert "BrainTab" in content
        assert "brain_tab" in content


class TestSourceColors:
    def test_sentinel_desktop_color_present(self) -> None:
        mod = _load_brain_tab()
        assert "sentinel-desktop" in mod._SOURCE_COLORS

    def test_claude_code_color_present(self) -> None:
        mod = _load_brain_tab()
        assert "claude-code" in mod._SOURCE_COLORS


class TestRegions:
    def test_all_four_regions_present(self) -> None:
        mod = _load_brain_tab()
        for r in ("knowledge", "context", "preference", "decision"):
            assert r in mod._REGIONS


class TestRefreshMs:
    def test_refresh_interval(self) -> None:
        mod = _load_brain_tab()
        assert mod._REFRESH_MS == 5000
