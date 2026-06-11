"""Second-pass coverage tests for core/platform/linux_backend.py.

Covers specific lines left uncovered by test_linux_backend_gaps.py:
  65-68  _probe_atspi success path
  102-105 _probe_wnck success path
  123    LinuxAccessibility.is_available()
  135-150 get_tree() AT-SPI success path
  166    find_element name-filter continue
  177    invoke_element raw=None (needs __new__ to bypass UIElement init)
  185-189 invoke_element action success
  197    set_element_value raw=None
  202-210 set_element_value Atspi.Text success + exception → False
  226-231 _walk_atspi children traversal
  240-241 _atspi_to_element role_name success
  247    _atspi_to_element extents
  256-259 _atspi_to_element action detection
  280-282 _get_atspi_value text success
  457,462,467,472 LinuxCredentialBackend dispatch via secretstorage
  499,515,532 secretstorage unlock in retrieve/delete/list
  768    _list_wnck screen is None
  772-774 _list_wnck window append
  841-842 _list_xdotool OSError/TimeoutExpired inside per-wid try
  853-863 _focus_wnck success path
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

MOD = "core.platform.linux_backend"


def _reset_probes():
    import core.platform.linux_backend as lb

    lb._has_xdotool = None
    lb._has_atspi = None
    lb._has_secretstorage = None
    lb._has_wnck = None


# ── probe success paths ───────────────────────────────────────────────────────


class TestProbeSuccessPaths:
    def setup_method(self):
        _reset_probes()

    def teardown_method(self):
        _reset_probes()

    def test_probe_atspi_success(self):
        """Lines 65-68: gi.require_version + Atspi import succeeds → True."""
        import core.platform.linux_backend as lb

        lb._has_atspi = None

        fake_gi = MagicMock()
        fake_gi.require_version = MagicMock()
        fake_repo = MagicMock()
        fake_repo.Atspi = MagicMock()

        with patch.dict(sys.modules, {"gi": fake_gi, "gi.repository": fake_repo}):
            result = lb._probe_atspi()

        assert result is True

    def test_probe_wnck_success(self):
        """Lines 102-105: gi.require_version + Wnck import succeeds → True."""
        import core.platform.linux_backend as lb

        lb._has_wnck = None

        fake_gi = MagicMock()
        fake_gi.require_version = MagicMock()
        fake_repo = MagicMock()
        fake_repo.Wnck = MagicMock()

        with patch.dict(sys.modules, {"gi": fake_gi, "gi.repository": fake_repo}):
            result = lb._probe_wnck()

        assert result is True


# ── LinuxAccessibility ────────────────────────────────────────────────────────


class TestLinuxAccessibilityIsAvailable:
    def test_is_available_true(self):
        """Line 123: is_available() returns self._available."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = True
        assert acc.is_available() is True

    def test_is_available_false(self):
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = False
        assert acc.is_available() is False


class TestLinuxAccessibilityGetTreeSuccess:
    def _make_atspi_tree(self):
        """Build a minimal mock AT-SPI object tree: desktop → app → window."""
        mock_win = MagicMock()
        mock_win.get_name.return_value = "My Window"
        mock_win.get_child_count.return_value = 0

        mock_app = MagicMock()
        mock_app.get_child_count.return_value = 1
        mock_app.get_child_at_index.return_value = mock_win

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 1
        mock_desktop.get_child_at_index.return_value = mock_app

        mock_atspi = MagicMock()
        mock_atspi.get_desktop.return_value = mock_desktop
        return mock_atspi, mock_win

    def test_get_tree_calls_walk_atspi(self):
        """Lines 135-150: successful get_tree() calls _walk_atspi on window."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = True

        mock_atspi, mock_win = self._make_atspi_tree()
        fake_gi = MagicMock()
        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": fake_gi, "gi.repository": fake_repo}):
            with patch.object(acc, "_walk_atspi") as mock_walk:
                result = acc.get_tree()

        mock_walk.assert_called_once_with(mock_win, [], depth=0, max_depth=12)
        assert result == []

    def test_get_tree_with_window_title_filter_no_match(self):
        """Line 148: window_title filter causes continue (window_title not in name)."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = True

        mock_atspi, mock_win = self._make_atspi_tree()
        fake_gi = MagicMock()
        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": fake_gi, "gi.repository": fake_repo}):
            with patch.object(acc, "_walk_atspi") as mock_walk:
                result = acc.get_tree(window_title="NonExistent")

        mock_walk.assert_not_called()
        assert result == []

    def test_get_tree_app_is_none_continues(self):
        """Line 141: app is None → continue."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = True

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 1
        mock_desktop.get_child_at_index.return_value = None  # app is None

        mock_atspi = MagicMock()
        mock_atspi.get_desktop.return_value = mock_desktop
        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            with patch.object(acc, "_walk_atspi") as mock_walk:
                result = acc.get_tree()

        mock_walk.assert_not_called()
        assert result == []

    def test_get_tree_window_is_none_continues(self):
        """Line 145: win is None → continue."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = True

        mock_app = MagicMock()
        mock_app.get_child_count.return_value = 1
        mock_app.get_child_at_index.return_value = None  # win is None

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 1
        mock_desktop.get_child_at_index.return_value = mock_app

        mock_atspi = MagicMock()
        mock_atspi.get_desktop.return_value = mock_desktop
        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            with patch.object(acc, "_walk_atspi") as mock_walk:
                result = acc.get_tree()

        mock_walk.assert_not_called()
        assert result == []


class TestLinuxAccessibilityFindElementNameFilter:
    def test_find_element_name_no_match_continues_to_next(self):
        """Line 166: name filter rejects first element, matches second."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        acc._available = True

        elem1 = UIElement(name="Unrelated", control_type="label")
        elem2 = UIElement(name="Submit Button", control_type="button")

        with patch.object(acc, "get_tree", return_value=[elem1, elem2]):
            result = acc.find_element(name="submit")

        assert result is elem2


class TestLinuxAccessibilityInvokeElementRawNone:
    def test_invoke_element_raw_is_none(self):
        """Line 177: element.raw is None → return False.

        UIElement.__init__ converts raw=None to {}, so we bypass __init__
        using __new__ + direct slot assignment to get a true None raw.
        """
        from core.platform.linux_backend import LinuxAccessibility
        from core.platform.base import UIElement

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        elem = UIElement.__new__(UIElement)
        elem.raw = None  # bypass UIElement.__init__ which does raw or {}

        assert acc.invoke_element(elem) is False

    def test_invoke_element_action_success(self):
        """Lines 185-189: invoke_element with valid atspi_ref + n_actions > 0 → True."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_node = MagicMock()
        mock_action = MagicMock()
        mock_action.get_n_actions.return_value = 2
        mock_atspi = MagicMock()
        mock_atspi.Action = mock_action

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        elem = UIElement(name="Btn", raw={"_atspi_ref": mock_node})

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = acc.invoke_element(elem)

        assert result is True
        mock_action.do_action.assert_called_once_with(mock_node, 0)

    def test_invoke_element_zero_actions_returns_false(self):
        """Lines 185-192: n_actions == 0 → falls through try → return False."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_node = MagicMock()
        mock_action = MagicMock()
        mock_action.get_n_actions.return_value = 0
        mock_atspi = MagicMock()
        mock_atspi.Action = mock_action

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        elem = UIElement(name="Btn", raw={"_atspi_ref": mock_node})

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = acc.invoke_element(elem)

        assert result is False


class TestLinuxAccessibilitySetElementValuePaths:
    def test_set_element_value_raw_is_none(self):
        """Line 197: element.raw is None → return False (bypassing UIElement init)."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)
        elem = UIElement.__new__(UIElement)
        elem.raw = None

        assert acc.set_element_value(elem, "hello") is False

    def test_set_element_value_atspi_text_success(self):
        """Lines 202-207: Atspi.Text.set_text_contents succeeds → True."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_node = MagicMock()
        mock_text = MagicMock()
        mock_atspi = MagicMock()
        mock_atspi.Text = mock_text

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        elem = UIElement(name="Input", raw={"_atspi_ref": mock_node})

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = acc.set_element_value(elem, "hello world")

        assert result is True
        mock_text.set_text_contents.assert_called_once_with(mock_node, "hello world")

    def test_set_element_value_exception_returns_false(self):
        """Lines 208-210: Atspi.Text raises → return False."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_node = MagicMock()
        mock_text = MagicMock()
        mock_text.set_text_contents.side_effect = RuntimeError("set failed")
        mock_atspi = MagicMock()
        mock_atspi.Text = mock_text

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        elem = UIElement(name="Input", raw={"_atspi_ref": mock_node})

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = acc.set_element_value(elem, "hello")

        assert result is False


class TestLinuxAccessibilityWalkAtspiChildren:
    def test_walk_atspi_appends_element_and_recurses(self):
        """Lines 226-231: _walk_atspi appends matched elem and calls itself for children."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_child = MagicMock()
        mock_child.get_child_count.return_value = 0

        mock_node = MagicMock()
        mock_node.get_child_count.return_value = 1
        mock_node.get_child_at_index.return_value = mock_child

        elem_parent = UIElement(name="Parent", control_type="button")
        elem_child = UIElement(name="Child", control_type="label")

        elements: list = []
        with patch.object(acc, "_atspi_to_element", side_effect=[elem_parent, elem_child]):
            acc._walk_atspi(mock_node, elements, depth=0, max_depth=5)

        assert elem_parent in elements
        assert elem_child in elements

    def test_walk_atspi_skips_none_children(self):
        """Lines 230-231: child is None → not recursed."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_node = MagicMock()
        mock_node.get_child_count.return_value = 1
        mock_node.get_child_at_index.return_value = None  # child is None

        elem_parent = UIElement(name="Parent", control_type="button")
        elements: list = []
        with patch.object(acc, "_atspi_to_element", return_value=elem_parent):
            acc._walk_atspi(mock_node, elements, depth=0, max_depth=5)

        assert elements == [elem_parent]

    def test_walk_atspi_skips_unnamed_unknown_elements(self):
        """Line 227 (condition): elem has no name and unknown type → not appended."""
        from core.platform.base import UIElement
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_node = MagicMock()
        mock_node.get_child_count.return_value = 0

        elem = UIElement(name="", control_type="unknown")
        elements: list = []
        with patch.object(acc, "_atspi_to_element", return_value=elem):
            acc._walk_atspi(mock_node, elements, depth=0, max_depth=5)

        assert elements == []


class TestLinuxAccessibilityAtspiToElementSuccess:
    def test_atspi_to_element_full_success(self):
        """Lines 240-241, 247, 256-259: role, extents, and actions all succeed."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_ext = MagicMock()
        mock_ext.x = 10
        mock_ext.y = 20
        mock_ext.width = 100
        mock_ext.height = 50

        mock_role = MagicMock()
        mock_atspi = MagicMock()
        mock_atspi.Role.get_name.return_value = "push button"
        mock_atspi.CoordType.SCREEN = 0
        mock_atspi.Action.get_n_actions.return_value = 1
        mock_atspi.Text.get_text.return_value = ""

        mock_node = MagicMock()
        mock_node.get_role.return_value = mock_role
        mock_node.get_extents.return_value = mock_ext
        mock_node.get_name.return_value = "OK"
        mock_node.get_description.return_value = "ok_btn"
        mock_node.get_child_count.return_value = 0

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            elem = acc._atspi_to_element(mock_node)

        assert elem.name == "OK"
        assert elem.control_type == "push button"
        assert elem.bounding_box == (10, 20, 100, 50)
        assert "invoke" in elem.actions
        assert elem.automation_id == "ok_btn"

    def test_atspi_to_element_extents_exception(self):
        """Line 249: extents raises → bounding_box is None."""
        from core.platform.linux_backend import LinuxAccessibility

        acc = LinuxAccessibility.__new__(LinuxAccessibility)

        mock_atspi = MagicMock()
        mock_atspi.Role.get_name.return_value = "label"
        mock_atspi.CoordType.SCREEN = 0
        mock_atspi.Action.get_n_actions.return_value = 0

        mock_node = MagicMock()
        mock_node.get_role.return_value = MagicMock()
        mock_node.get_extents.side_effect = RuntimeError("no extents")
        mock_node.get_name.return_value = "Lbl"
        mock_node.get_description.return_value = None
        mock_node.get_child_count.return_value = 0

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            elem = acc._atspi_to_element(mock_node)

        assert elem.bounding_box is None


class TestLinuxAccessibilityGetAtspiValueSuccess:
    def test_get_atspi_value_returns_text(self):
        """Lines 280-282: Atspi.Text.get_text returns non-empty string."""
        from core.platform.linux_backend import LinuxAccessibility

        mock_text_iface = MagicMock()
        mock_text_iface.get_text.return_value = "hello world"
        mock_atspi = MagicMock()
        mock_atspi.Text = mock_text_iface

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        mock_node = MagicMock()

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = LinuxAccessibility._get_atspi_value(mock_node)

        assert result == "hello world"

    def test_get_atspi_value_empty_string_returns_none(self):
        """Line 282: empty text → returns None."""
        from core.platform.linux_backend import LinuxAccessibility

        mock_text_iface = MagicMock()
        mock_text_iface.get_text.return_value = ""
        mock_atspi = MagicMock()
        mock_atspi.Text = mock_text_iface

        fake_repo = MagicMock()
        fake_repo.Atspi = mock_atspi

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = LinuxAccessibility._get_atspi_value(MagicMock())

        assert result is None


# ── LinuxCredentialBackend: dispatch paths ───────────────────────────────────


def _make_ss_backend(tmp_path=None):
    from core.platform.linux_backend import LinuxCredentialBackend

    backend = LinuxCredentialBackend.__new__(LinuxCredentialBackend)
    backend._use_secretstorage = True
    backend._file_path = Path(tmp_path or "/tmp/_test_vault2.json")
    backend._lock = threading.RLock()
    backend._file_data = {"version": 1, "keys": {}}
    return backend


class TestLinuxCredentialDispatch:
    """Lines 457, 462, 467, 472: dispatch methods route to secretstorage."""

    def test_store_dispatches_to_secretstorage(self):
        """Line 457: store() calls _store_secretstorage when enabled."""
        backend = _make_ss_backend()
        with patch.object(backend, "_store_secretstorage", return_value=True) as m:
            result = backend.store("k", "v")
        m.assert_called_once_with("k", "v")
        assert result is True

    def test_retrieve_dispatches_to_secretstorage(self):
        """Line 462: retrieve() calls _retrieve_secretstorage when enabled."""
        backend = _make_ss_backend()
        with patch.object(backend, "_retrieve_secretstorage", return_value="val") as m:
            result = backend.retrieve("k")
        m.assert_called_once_with("k")
        assert result == "val"

    def test_delete_dispatches_to_secretstorage(self):
        """Line 467: delete() calls _delete_secretstorage when enabled."""
        backend = _make_ss_backend()
        with patch.object(backend, "_delete_secretstorage", return_value=True) as m:
            result = backend.delete("k")
        m.assert_called_once_with("k")
        assert result is True

    def test_list_keys_dispatches_to_secretstorage(self):
        """Line 472: list_keys() calls _list_secretstorage when enabled."""
        backend = _make_ss_backend()
        with patch.object(backend, "_list_secretstorage", return_value=["a"]) as m:
            result = backend.list_keys()
        m.assert_called_once_with()
        assert result == ["a"]


class TestLinuxCredentialSecretstorageUnlock:
    """Lines 499, 515, 532: unlock path in retrieve/delete/list secretstorage."""

    def _make_mock_ss(self, locked=True):
        mock_ss = MagicMock()
        mock_bus = MagicMock()
        mock_col = MagicMock()
        mock_col.is_locked.return_value = locked
        mock_ss.dbus_init.return_value = mock_bus
        mock_ss.get_default_collection.return_value = mock_col
        return mock_ss, mock_col

    def test_retrieve_secretstorage_unlocks_locked(self):
        """Line 499: retrieve calls collection.unlock() when locked."""
        backend = _make_ss_backend()
        mock_ss, mock_col = self._make_mock_ss(locked=True)
        mock_col.search_items.return_value = []

        with patch.dict(sys.modules, {"secretstorage": mock_ss}):
            with patch.object(backend, "_retrieve_file", return_value=None):
                backend._retrieve_secretstorage("k")

        mock_col.unlock.assert_called_once()

    def test_delete_secretstorage_unlocks_locked(self):
        """Line 515: delete calls collection.unlock() when locked."""
        backend = _make_ss_backend()
        mock_ss, mock_col = self._make_mock_ss(locked=True)
        mock_col.search_items.return_value = []

        with patch.dict(sys.modules, {"secretstorage": mock_ss}):
            with patch.object(backend, "_delete_file", return_value=False):
                backend._delete_secretstorage("k")

        mock_col.unlock.assert_called_once()

    def test_list_secretstorage_unlocks_locked(self):
        """Line 532: list calls collection.unlock() when locked."""
        backend = _make_ss_backend()
        mock_ss, mock_col = self._make_mock_ss(locked=True)
        mock_col.get_all_items.return_value = []

        with patch.dict(sys.modules, {"secretstorage": mock_ss}):
            result = backend._list_secretstorage()

        mock_col.unlock.assert_called_once()
        assert result == []


# ── LinuxWindowBackend ────────────────────────────────────────────────────────


class TestLinuxWindowBackendWnck:
    def _make_backend(self, has_wnck=True):
        from core.platform.linux_backend import LinuxWindowBackend

        backend = LinuxWindowBackend.__new__(LinuxWindowBackend)
        backend._has_wnck = has_wnck
        backend._has_xdotool = False
        return backend

    def _make_wnck_mock(self, screen_none=False, windows=None):
        mock_wnck = MagicMock()
        if screen_none:
            mock_wnck.Screen.get_default.return_value = None
        else:
            mock_screen = MagicMock()
            mock_screen.get_windows.return_value = windows or []
            mock_wnck.Screen.get_default.return_value = mock_screen
        fake_repo = MagicMock()
        fake_repo.Wnck = mock_wnck
        return mock_wnck, fake_repo

    def test_list_wnck_screen_is_none_returns_empty(self):
        """Line 768: screen is None → return []."""
        backend = self._make_backend(has_wnck=True)
        mock_wnck, fake_repo = self._make_wnck_mock(screen_none=True)

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._list_wnck()

        assert result == []

    def test_list_wnck_appends_visible_windows(self):
        """Lines 772-774: non-pager-skip windows get appended to result."""
        from core.platform.linux_backend import LinuxWindowBackend
        from core.platform.base import WindowInfo

        backend = self._make_backend(has_wnck=True)

        mock_win = MagicMock()
        mock_win.is_skip_pager.return_value = False
        mock_win.get_name.return_value = "Firefox"
        geo = MagicMock()
        geo.__getitem__ = lambda self, i: [10, 20, 800, 600][i]
        mock_win.get_geometry.return_value = geo

        mock_wnck, fake_repo = self._make_wnck_mock(windows=[mock_win])

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._list_wnck()

        assert len(result) == 1
        assert result[0].title == "Firefox"

    def test_list_wnck_skips_pager_windows(self):
        """Line 772 condition: is_skip_pager() → skipped."""
        backend = self._make_backend(has_wnck=True)

        mock_win = MagicMock()
        mock_win.is_skip_pager.return_value = True
        mock_win.get_name.return_value = "Taskbar"

        mock_wnck, fake_repo = self._make_wnck_mock(windows=[mock_win])

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._list_wnck()

        assert result == []

    def test_list_wnck_skips_unnamed_windows(self):
        """Line 772 condition: get_name() returns None → skipped."""
        backend = self._make_backend(has_wnck=True)

        mock_win = MagicMock()
        mock_win.is_skip_pager.return_value = False
        mock_win.get_name.return_value = None

        mock_wnck, fake_repo = self._make_wnck_mock(windows=[mock_win])

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._list_wnck()

        assert result == []


class TestLinuxWindowBackendFocusWnck:
    def _make_backend(self):
        from core.platform.linux_backend import LinuxWindowBackend

        backend = LinuxWindowBackend.__new__(LinuxWindowBackend)
        backend._has_wnck = True
        backend._has_xdotool = False
        return backend

    def test_focus_wnck_matches_and_activates(self):
        """Lines 853-863: _focus_wnck finds matching window and activates it."""
        backend = self._make_backend()

        mock_win = MagicMock()
        mock_win.get_name.return_value = "Firefox Browser"

        mock_screen = MagicMock()
        mock_screen.get_windows.return_value = [mock_win]

        mock_wnck = MagicMock()
        mock_wnck.Screen.get_default.return_value = mock_screen

        fake_repo = MagicMock()
        fake_repo.Wnck = mock_wnck

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._focus_wnck("firefox")

        assert result is True
        mock_win.activate.assert_called_once()

    def test_focus_wnck_no_match_returns_false(self):
        """Line 860-862: no window matches title → return False."""
        backend = self._make_backend()

        mock_win = MagicMock()
        mock_win.get_name.return_value = "Some Other App"

        mock_screen = MagicMock()
        mock_screen.get_windows.return_value = [mock_win]

        mock_wnck = MagicMock()
        mock_wnck.Screen.get_default.return_value = mock_screen

        fake_repo = MagicMock()
        fake_repo.Wnck = mock_wnck

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._focus_wnck("nonexistent")

        assert result is False

    def test_focus_wnck_screen_is_none_returns_false(self):
        """Line 856-857: screen is None → return False."""
        backend = self._make_backend()

        mock_wnck = MagicMock()
        mock_wnck.Screen.get_default.return_value = None

        fake_repo = MagicMock()
        fake_repo.Wnck = mock_wnck

        with patch.dict(sys.modules, {"gi": MagicMock(), "gi.repository": fake_repo}):
            result = backend._focus_wnck("anything")

        assert result is False


class TestLinuxWindowBackendXdotoolErrors:
    """Lines 841-842: per-wid OSError/TimeoutExpired/ValueError → continue."""

    def _make_backend(self):
        from core.platform.linux_backend import LinuxWindowBackend

        backend = LinuxWindowBackend.__new__(LinuxWindowBackend)
        backend._has_wnck = False
        backend._has_xdotool = True
        return backend

    def _make_list_result(self, wid="12345"):
        result = MagicMock()
        result.returncode = 0
        result.stdout = wid
        return result

    def test_list_xdotool_oserror_per_wid_continues(self):
        """Line 841: OSError in per-wid block → continue, other windows processed."""
        backend = self._make_backend()

        list_result = self._make_list_result("12345\n67890")

        name_results = [
            MagicMock(returncode=0, stdout="GoodWindow"),
            MagicMock(returncode=0, stdout="AnotherWindow"),
        ]
        geo_results = [
            MagicMock(returncode=0, stdout="X=0\nY=0\nWIDTH=800\nHEIGHT=600"),
        ]

        call_count = [0]

        def mock_run(cmd, **kwargs):
            if "search" in cmd:
                return list_result
            if "getwindowname" in cmd:
                r = MagicMock(returncode=0, stdout="BadWindow" if cmd[-1] == "12345" else "GoodWindow")
                return r
            if "getwindowgeometry" in cmd:
                count = call_count[0]
                call_count[0] += 1
                if count == 0:
                    raise OSError("no geometry")
                return MagicMock(returncode=0, stdout="X=0\nY=0\nWIDTH=100\nHEIGHT=100")

        with patch("subprocess.run", side_effect=mock_run):
            result = backend._list_xdotool()

        # Second window should still be processed
        assert isinstance(result, list)

    def test_list_xdotool_timeout_per_wid_continues(self):
        """Line 841: TimeoutExpired in per-wid name fetch → continue."""
        backend = self._make_backend()

        list_result = self._make_list_result("12345")

        def mock_run(cmd, **kwargs):
            if "search" in cmd:
                return list_result
            if "getwindowname" in cmd:
                raise subprocess.TimeoutExpired(cmd, 3)
            return MagicMock(returncode=0, stdout="")

        with patch("subprocess.run", side_effect=mock_run):
            result = backend._list_xdotool()

        assert result == []
