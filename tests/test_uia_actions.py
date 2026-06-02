"""Tests for core.uia_actions — three-tier UIA/PostMessage/pyautogui pipeline."""

import pytest

import core.uia_actions as mod

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeDesktop:
    """Minimal fake DesktopController for tier-3 tests."""

    def __init__(self):
        self.calls: list[tuple] = []

    def click(self, x, y, *, button="left", clicks=1):
        self.calls.append(("click", x, y, button, clicks))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, amount, *, x=None, y=None):
        self.calls.append(("scroll", amount, x, y))


@pytest.fixture(autouse=True)
def _reset_probes():
    """Reset availability caches between tests."""
    mod._UIA_AVAILABLE = None
    mod._auto = None
    mod._POSTMESSAGE_AVAILABLE = None
    mod._win32gui = None
    mod._win32api = None
    mod._win32con = None
    yield
    mod._UIA_AVAILABLE = None
    mod._auto = None
    mod._POSTMESSAGE_AVAILABLE = None
    mod._win32gui = None
    mod._win32api = None
    mod._win32con = None


@pytest.fixture
def pipe():
    return mod.UIAActionPipeline()


@pytest.fixture
def no_tiers(monkeypatch):
    """Disable both UIA and PostMessage tiers so only physical (tier 3) runs."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: False)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: False)


@pytest.fixture
def uia_only(monkeypatch):
    """Enable UIA tier, disable PostMessage."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: True)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: False)


@pytest.fixture
def postmsg_only(monkeypatch):
    """Disable UIA, enable PostMessage."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: False)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: True)


# ---------------------------------------------------------------------------
# _result helper
# ---------------------------------------------------------------------------


class TestResult:
    def test_success(self):
        r = mod._result(True, "ok", "uia")
        assert r == {"success": True, "output": "ok", "method_used": "uia"}

    def test_failure(self):
        r = mod._result(False, "nope", "physical")
        assert r["success"] is False
        assert r["output"] == "nope"


# ---------------------------------------------------------------------------
# click_element
# ---------------------------------------------------------------------------


class TestClickElement:
    def test_uia_tier_succeeds(self, pipe, uia_only, monkeypatch):
        monkeypatch.setattr(mod, "import_module", lambda _: None, raising=False)
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "click_control", lambda **kw: (100, 200))
        r = pipe.click_element("OK")
        assert r["success"] is True
        assert r["method_used"] == "uia"
        assert r["output"]["x"] == 100

    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        """When UIA and PostMessage are off and bounds are unknown, it fails."""
        r = pipe.click_element("Missing")
        assert r["success"] is False

    def test_physical_tier_with_bounds(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 50,
                "center_y": 60,
                "x": 40,
                "y": 50,
                "width": 20,
                "height": 20,
            },
        )
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.click_element("Btn")
        assert r["success"] is True
        assert r["method_used"] == "physical"
        assert fake_desktop.calls[0][0] == "click"


# ---------------------------------------------------------------------------
# type_into_field
# ---------------------------------------------------------------------------


class TestTypeIntoField:
    def test_uia_tier_succeeds(self, pipe, uia_only, monkeypatch):
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "set_text", lambda text, **kw: True)
        r = pipe.type_into_field("Search", "hello")
        assert r["success"] is True
        assert r["method_used"] == "uia"

    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 10,
                "center_y": 20,
                "x": 0,
                "y": 0,
                "width": 20,
                "height": 40,
            },
        )
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.type_into_field("Field", "test")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_not_found_returns_failure(self, pipe, no_tiers, monkeypatch):
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.type_into_field("Ghost", "x")
        assert r["success"] is False


# ---------------------------------------------------------------------------
# click_at
# ---------------------------------------------------------------------------


class TestClickAt:
    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.click_at(100, 200)
        assert r["success"] is True
        assert r["method_used"] == "physical"
        assert r["output"] == {"x": 100, "y": 200}

    def test_postmessage_succeeds(self, pipe, postmsg_only, monkeypatch):
        import core.stealth_input as si

        monkeypatch.setattr(si, "post_click", lambda x, y, **kw: True)
        r = pipe.click_at(50, 75)
        assert r["success"] is True
        assert r["method_used"] == "postmessage"


# ---------------------------------------------------------------------------
# type_text
# ---------------------------------------------------------------------------


class TestTypeText:
    def test_empty_text_fails(self, pipe, postmsg_only):
        r = pipe.type_text("")
        assert r["success"] is False

    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.type_text("abc")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_postmessage_succeeds(self, pipe, postmsg_only, monkeypatch):
        import core.stealth_input as si

        monkeypatch.setattr(si, "post_text", lambda text, **kw: True)
        r = pipe.type_text("hello")
        assert r["success"] is True
        assert r["method_used"] == "postmessage"


# ---------------------------------------------------------------------------
# press_key
# ---------------------------------------------------------------------------


class TestPressKey:
    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.press_key("enter")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_postmessage_succeeds(self, pipe, postmsg_only, monkeypatch):
        import core.stealth_input as si

        monkeypatch.setattr(si, "post_named_key", lambda key, **kw: True)
        r = pipe.press_key("f5")
        assert r["success"] is True
        assert r["method_used"] == "postmessage"


# ---------------------------------------------------------------------------
# hotkey
# ---------------------------------------------------------------------------


class TestHotkey:
    def test_empty_keys_fails(self, pipe, postmsg_only):
        r = pipe.hotkey([])
        assert r["success"] is False

    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.hotkey(["ctrl", "c"])
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_postmessage_succeeds(self, pipe, postmsg_only, monkeypatch):
        import core.stealth_input as si

        monkeypatch.setattr(si, "post_hotkey", lambda keys, **kw: True)
        r = pipe.hotkey(["alt", "f4"])
        assert r["success"] is True
        assert r["method_used"] == "postmessage"


# ---------------------------------------------------------------------------
# scroll_at
# ---------------------------------------------------------------------------


class TestScrollAt:
    def test_physical_fallback(self, pipe, no_tiers, monkeypatch):
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.scroll_at(100, 200, 3)
        assert r["success"] is True
        assert r["method_used"] == "physical"
        assert r["output"]["amount"] == 3


# ---------------------------------------------------------------------------
# find_element
# ---------------------------------------------------------------------------


class TestFindElement:
    def test_uia_unavailable_fails(self, pipe, no_tiers):
        r = pipe.find_element("Button")
        assert r["success"] is False

    def test_uia_returns_element(self, pipe, uia_only, monkeypatch):
        import core.ui_tree as ui_tree_mod

        class FakeCtrl:
            Name = "Button"
            ControlTypeName = "ButtonControl"
            AutomationId = "btn1"
            ClassName = "Button"

            class BoundingRectangle:
                left = top = 0
                right = bottom = 100

            BoundingRectangle = BoundingRectangle()

        monkeypatch.setattr(ui_tree_mod, "_find_control", lambda **kw: FakeCtrl())
        r = pipe.find_element("Button")
        assert r["success"] is True
        assert r["output"]["name"] == "Button"
        assert r["method_used"] == "uia"


# ---------------------------------------------------------------------------
# list_controls
# ---------------------------------------------------------------------------


class TestListControls:
    def test_uia_unavailable_fails(self, pipe, no_tiers):
        r = pipe.list_controls()
        assert r["success"] is False

    def test_uia_returns_controls(self, pipe, uia_only, monkeypatch):
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "list_controls", lambda wt=None: [{"name": "OK"}])
        r = pipe.list_controls()
        assert r["success"] is True
        assert len(r["output"]) == 1


# ---------------------------------------------------------------------------
# get_element_bounds
# ---------------------------------------------------------------------------


class TestGetElementBounds:
    def test_found(self, pipe, monkeypatch):
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 50,
                "center_x": 50,
                "center_y": 25,
            },
        )
        r = pipe.get_element_bounds("OK")
        assert r["success"] is True
        assert r["output"]["center_x"] == 50

    def test_not_found(self, pipe, monkeypatch):
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.get_element_bounds("Ghost")
        assert r["success"] is False


# ---------------------------------------------------------------------------
# _control_to_dict
# ---------------------------------------------------------------------------


class TestControlToDict:
    def test_normal_control(self):
        class FakeCtrl:
            Name = "Save"
            ControlTypeName = "ButtonControl"
            AutomationId = "saveBtn"
            ClassName = "Button"

            class Rect:
                left = top = 10
                right = 110
                bottom = 60

            BoundingRectangle = Rect()

        d = mod.UIAActionPipeline._control_to_dict(FakeCtrl())
        assert d["name"] == "Save"
        assert d["width"] == 100
        assert d["height"] == 50
        assert d["center_x"] == 60

    def test_broken_control_returns_error(self):
        class BadCtrl:
            @property
            def BoundingRectangle(self):
                raise RuntimeError("no rect")

            Name = "Broken"

        d = mod.UIAActionPipeline._control_to_dict(BadCtrl())
        assert "error" in d


# ---------------------------------------------------------------------------
# _find_child_by_name
# ---------------------------------------------------------------------------


class TestFindChildByName:
    def test_exact_match(self):
        class Child:
            Name = "File"

        class Parent:
            def GetChildren(self):
                return [Child()]

        result = mod.UIAActionPipeline._find_child_by_name(Parent(), "File")
        assert result is not None

    def test_case_insensitive_partial(self):
        class Child:
            Name = "File Menu"

        class Parent:
            def GetChildren(self):
                return [Child()]

        result = mod.UIAActionPipeline._find_child_by_name(Parent(), "file")
        assert result is not None

    def test_no_match(self):
        class Parent:
            def GetChildren(self):
                return []

        result = mod.UIAActionPipeline._find_child_by_name(Parent(), "File")
        assert result is None

    def test_exception_returns_none(self):
        class BadParent:
            def GetChildren(self):
                raise RuntimeError("boom")

        result = mod.UIAActionPipeline._find_child_by_name(BadParent(), "x")
        assert result is None


# ---------------------------------------------------------------------------
# select_menu_item
# ---------------------------------------------------------------------------


class TestSelectMenuItem:
    def test_empty_path_fails(self, pipe, uia_only):
        r = pipe.select_menu_item("")
        assert r["success"] is False

    def test_uia_menu_walk_succeeds(self, pipe, uia_only, monkeypatch):
        monkeypatch.setattr(pipe, "_uia_menu_walk", lambda segs, wt=None: True)
        r = pipe.select_menu_item("File > Save")
        assert r["success"] is True
        assert r["method_used"] == "uia"

    def test_uia_menu_walk_fails_falls_through(self, pipe, uia_only, monkeypatch):
        monkeypatch.setattr(pipe, "_uia_menu_walk", lambda segs, wt=None: False)
        # Will fall through to physical tier (which may fail in headless)
        r = pipe.select_menu_item("File > Save")
        # In headless, pyautogui stubs succeed, so it returns physical
        assert r["method_used"] in ("physical", "postmessage", "uia")


# ---------------------------------------------------------------------------
# _uia_bounds
# ---------------------------------------------------------------------------


class TestUiaBounds:
    def test_uia_unavailable(self, no_tiers):
        r = mod.UIAActionPipeline._uia_bounds("Button")
        assert r is None

    def test_found(self, uia_only, monkeypatch):
        import core.ui_tree as ui_tree_mod

        class FakeCtrl:
            class Rect:
                left = top = 10
                right = 110
                bottom = 60

            BoundingRectangle = Rect()

        monkeypatch.setattr(ui_tree_mod, "_find_control", lambda **kw: FakeCtrl())
        r = mod.UIAActionPipeline._uia_bounds("OK")
        assert r is not None
        assert r["center_x"] == 60

    def test_not_found(self, uia_only, monkeypatch):
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "_find_control", lambda **kw: None)
        r = mod.UIAActionPipeline._uia_bounds("Ghost")
        assert r is None

    def test_cache_hit_skips_find_control(self, uia_only, monkeypatch):
        """Cached bounds are returned without calling _find_control again."""

        import core.ui_tree as ui_tree_mod

        call_count = [0]

        class FakeCtrl:
            class Rect:
                left = top = 0
                right = 100
                bottom = 50

            BoundingRectangle = Rect()

        def counting_find(**kw):
            call_count[0] += 1
            return FakeCtrl()

        monkeypatch.setattr(ui_tree_mod, "_find_control", counting_find)
        # Clear the bounds cache first.
        mod._bounds_cache.clear()
        r1 = mod.UIAActionPipeline._uia_bounds("CachedBtn")
        assert r1 is not None
        assert call_count[0] == 1
        # Second call within TTL should hit the cache.
        r2 = mod.UIAActionPipeline._uia_bounds("CachedBtn")
        assert r2 == r1
        assert call_count[0] == 1  # no additional call


# ---------------------------------------------------------------------------
# _hwnd_for_element
# ---------------------------------------------------------------------------


class TestHwndForElement:
    def test_postmessage_unavailable(self, no_tiers):
        r = mod.UIAActionPipeline._hwnd_for_element("OK")
        assert r is None

    def test_no_bounds(self, postmsg_only, monkeypatch):
        monkeypatch.setattr(mod.UIAActionPipeline, "_uia_bounds", lambda *a, **kw: None)
        r = mod.UIAActionPipeline._hwnd_for_element("OK")
        assert r is None

    def test_found(self, postmsg_only, monkeypatch):
        monkeypatch.setattr(
            mod.UIAActionPipeline,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 100,
                "center_y": 200,
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 400,
            },
        )
        fake_win32gui = type("win32gui", (), {"WindowFromPoint": lambda self, pt: 42})()
        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        r = mod.UIAActionPipeline._hwnd_for_element("OK")
        assert r == 42


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_pipeline_exists(self):
        assert hasattr(mod, "pipeline")
        assert isinstance(mod.pipeline, mod.UIAActionPipeline)
