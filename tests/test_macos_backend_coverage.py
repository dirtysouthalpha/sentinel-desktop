"""Coverage tests for core/platform/macos_backend.py.

All macOS-specific subprocess calls (osascript, security) are mocked so
these tests run on Linux without any macOS tooling installed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MOD = "core.platform.macos_backend"


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


# ── Probe functions ────────────────────────────────────────────────────────────


class TestProbes:
    def test_probe_osascript_success(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", return_value=_make_proc(0)):
            assert mb._probe_osascript() is True

    def test_probe_osascript_failure(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", side_effect=OSError("no osascript")):
            assert mb._probe_osascript() is False

    def test_probe_osascript_timeout(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 3)):
            assert mb._probe_osascript() is False

    def test_probe_applescript_accessibility_success(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", return_value=_make_proc(0)):
            assert mb._probe_applescript_accessibility() is True

    def test_probe_applescript_accessibility_failure(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", side_effect=OSError("fail")):
            assert mb._probe_applescript_accessibility() is False

    def test_probe_security_success(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", return_value=_make_proc(0)):
            assert mb._probe_security() is True

    def test_probe_security_failure(self):
        import core.platform.macos_backend as mb

        with patch("subprocess.run", side_effect=FileNotFoundError("no security")):
            assert mb._probe_security() is False

    def test_probe_pyobjc_success(self):
        import core.platform.macos_backend as mb

        fake_as = MagicMock()
        with patch.dict(sys.modules, {"ApplicationServices": fake_as}):
            assert mb._probe_pyobjc() is True

    def test_probe_pyobjc_failure(self):
        import core.platform.macos_backend as mb

        with patch.dict(sys.modules, {"ApplicationServices": None}):
            # None in sys.modules causes ImportError on 'import ApplicationServices'
            assert mb._probe_pyobjc() is False


# ── MacOSAccessibility ─────────────────────────────────────────────────────────


class TestMacOSAccessibility:
    def _make(self, available: bool = True):
        from core.platform.macos_backend import MacOSAccessibility

        acc = MacOSAccessibility.__new__(MacOSAccessibility)
        acc._available = available
        return acc

    def test_is_available_true(self):
        acc = self._make(True)
        assert acc.is_available() is True

    def test_is_available_false(self):
        acc = self._make(False)
        assert acc.is_available() is False

    def test_get_tree_not_available(self):
        acc = self._make(False)
        assert acc.get_tree() == []

    def test_get_tree_with_window_title_success(self):
        acc = self._make(True)
        output = "desc|AXButton|OK|val|{10, 20}|{80, 30}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            elements = acc.get_tree("MyApp")
        assert len(elements) == 1
        assert elements[0].name == "OK"

    def test_get_tree_no_window_title_success(self):
        acc = self._make(True)
        output = "desc|AXTextField|username|hello|{5, 5}|{200, 24}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            elements = acc.get_tree()
        assert len(elements) == 1
        assert elements[0].name == "username"

    def test_get_tree_subprocess_fails(self):
        acc = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(1)):
            assert acc.get_tree() == []

    def test_get_tree_oserror(self):
        acc = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert acc.get_tree() == []

    def test_find_element_found(self):
        acc = self._make(True)
        output = "d|AXButton|Submit||{0, 0}|{80, 30}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            elem = acc.find_element(name="Submit")
        assert elem is not None
        assert elem.name == "Submit"

    def test_find_element_not_found(self):
        acc = self._make(True)
        output = "d|AXButton|Cancel||{0, 0}|{80, 30}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            elem = acc.find_element(name="Submit")
        assert elem is None

    def test_find_element_control_type_filter(self):
        acc = self._make(True)
        output = "d|AXButton|OK||{0, 0}|{80, 30}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            # control_type doesn't match → None
            elem = acc.find_element(name="OK", control_type="edit")
        assert elem is None

    def test_find_element_automation_id_filter(self):
        acc = self._make(True)
        output = "myid|AXButton|OK||{0, 0}|{80, 30}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            elem = acc.find_element(automation_id="myid")
        assert elem is not None

    def test_find_element_automation_id_no_match(self):
        acc = self._make(True)
        output = "otherid|AXButton|OK||{0, 0}|{80, 30}\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            elem = acc.find_element(automation_id="myid")
        assert elem is None

    def test_invoke_element_not_available(self):
        from core.platform.base import UIElement

        acc = self._make(False)
        elem = UIElement(name="btn", control_type="button")
        assert acc.invoke_element(elem) is False

    def test_invoke_element_no_name(self):
        from core.platform.base import UIElement

        acc = self._make(True)
        elem = UIElement(name=None, control_type="button")
        assert acc.invoke_element(elem) is False

    def test_invoke_element_success(self):
        from core.platform.base import UIElement

        acc = self._make(True)
        elem = UIElement(name="OK", control_type="button")
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert acc.invoke_element(elem) is True

    def test_invoke_element_failure(self):
        from core.platform.base import UIElement

        acc = self._make(True)
        elem = UIElement(name="OK", control_type="button")
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert acc.invoke_element(elem) is False

    def test_set_element_value_not_available(self):
        from core.platform.base import UIElement

        acc = self._make(False)
        elem = UIElement(name="field", control_type="edit")
        assert acc.set_element_value(elem, "text") is False

    def test_set_element_value_success(self):
        from core.platform.base import UIElement

        acc = self._make(True)
        elem = UIElement(name="username", control_type="edit")
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert acc.set_element_value(elem, "admin") is True

    def test_set_element_value_timeout(self):
        from core.platform.base import UIElement

        acc = self._make(True)
        elem = UIElement(name="username", control_type="edit")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osa", 5)):
            assert acc.set_element_value(elem, "admin") is False


class TestParseApplescriptElements:
    def _parse(self, text: str):
        from core.platform.macos_backend import MacOSAccessibility

        return MacOSAccessibility._parse_applescript_elements(text)

    def test_parse_button(self):
        output = "desc|AXButton|OK||{10, 20}|{80, 30}\n"
        elems = self._parse(output)
        assert len(elems) == 1
        assert elems[0].control_type == "button"
        assert "invoke" in elems[0].actions

    def test_parse_textfield(self):
        output = "desc|AXTextField|user||{0, 0}|{200, 24}\n"
        elems = self._parse(output)
        assert elems[0].control_type == "edit"
        assert "set_value" in elems[0].actions

    def test_parse_menu(self):
        output = "desc|AXMenu|File||{0, 0}|{50, 20}\n"
        elems = self._parse(output)
        assert elems[0].control_type == "menu"

    def test_parse_checkbox(self):
        output = "desc|AXCheckBox|Enable||{0, 0}|{20, 20}\n"
        elems = self._parse(output)
        assert elems[0].control_type == "checkbox"

    def test_parse_radio(self):
        # Use AXRadio (no "button" substring) to exercise the "radio" branch
        output = "desc|AXRadio|Option1||{0, 0}|{100, 20}\n"
        elems = self._parse(output)
        assert elems[0].control_type == "radio"

    def test_parse_tab(self):
        output = "desc|AXTab|Tab1||{0, 0}|{100, 30}\n"
        elems = self._parse(output)
        assert elems[0].control_type == "tab"

    def test_parse_unknown_role(self):
        output = "desc|AXSplitter|split||{0, 0}|{10, 300}\n"
        elems = self._parse(output)
        assert elems[0].control_type == "axsplitter"

    def test_parse_with_value(self):
        output = "d|AXTextField|email|user@example.com|{0, 0}|{200, 24}\n"
        elems = self._parse(output)
        assert elems[0].value == "user@example.com"

    def test_parse_bad_position(self):
        output = "desc|AXButton|OK||bad_pos|bad_size\n"
        elems = self._parse(output)
        assert len(elems) == 1
        assert elems[0].bounding_box is None

    def test_parse_too_few_parts(self):
        output = "desc|AXButton\n"
        elems = self._parse(output)
        assert elems == []

    def test_parse_empty(self):
        assert self._parse("") == []

    def test_parse_empty_lines_skipped(self):
        output = "\n\ndesc|AXButton|OK||{0,0}|{10,10}\n\n"
        elems = self._parse(output)
        assert len(elems) == 1


# ── MacOSStealthInput ──────────────────────────────────────────────────────────


class TestMacOSStealthInput:
    def _make(self, has_osascript: bool = True):
        from core.platform.macos_backend import MacOSStealthInput

        inp = MacOSStealthInput.__new__(MacOSStealthInput)
        inp._has_osascript = has_osascript
        return inp

    def test_is_available(self):
        assert self._make(True).is_available() is True
        assert self._make(False).is_available() is False

    def test_click_not_available(self):
        assert self._make(False).click(100, 200) is False

    def test_click_success(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert inp.click(100, 200) is True

    def test_click_double(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.click(10, 20, clicks=2)
        call_args = mock_run.call_args[0][0]
        assert "double click" in call_args[2]

    def test_click_right_button(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.click(10, 20, button="right")
        call_args = mock_run.call_args[0][0]
        assert "button" in call_args[2]

    def test_click_oserror(self):
        inp = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert inp.click(0, 0) is False

    def test_type_text_not_available(self):
        assert self._make(False).type_text("hello") is False

    def test_type_text_empty(self):
        assert self._make(True).type_text("") is False

    def test_type_text_success(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert inp.type_text("hello world") is True

    def test_type_text_with_quotes(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.type_text('say "hi"')
        call_args = mock_run.call_args[0][0]
        assert '\\"' in call_args[2]

    def test_type_text_timeout(self):
        inp = self._make(True)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osa", 15)):
            assert inp.type_text("hello") is False

    def test_press_key_not_available(self):
        assert self._make(False).press_key("enter") is False

    def test_press_key_success(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert inp.press_key("enter") is True

    def test_press_key_oserror(self):
        inp = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert inp.press_key("escape") is False

    def test_hotkey_not_available(self):
        assert self._make(False).hotkey("ctrl", "c") is False

    def test_hotkey_no_keys(self):
        assert self._make(True).hotkey() is False

    def test_hotkey_no_main_key(self):
        # Only modifiers, no main character → returns False
        inp = self._make(True)
        assert inp.hotkey("ctrl", "shift") is False

    def test_hotkey_with_ctrl(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.hotkey("ctrl", "c")
        call_args = mock_run.call_args[0][0]
        assert "control down" in call_args[2]

    def test_hotkey_with_cmd(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.hotkey("cmd", "v")
        call_args = mock_run.call_args[0][0]
        assert "command down" in call_args[2]

    def test_hotkey_with_alt(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.hotkey("alt", "f4")
        call_args = mock_run.call_args[0][0]
        assert "option down" in call_args[2]

    def test_hotkey_with_shift(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.hotkey("shift", "a")
        call_args = mock_run.call_args[0][0]
        assert "shift down" in call_args[2]

    def test_hotkey_no_modifiers(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.hotkey("a")
        call_args = mock_run.call_args[0][0]
        assert "keystroke" in call_args[2]

    def test_hotkey_oserror(self):
        inp = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert inp.hotkey("ctrl", "c") is False

    def test_scroll_not_available(self):
        assert self._make(False).scroll(3) is False

    def test_scroll_up(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            result = inp.scroll(2)
        call_args = mock_run.call_args[0][0]
        assert '"up"' in call_args[2]
        assert result is True

    def test_scroll_down(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.scroll(-3)
        call_args = mock_run.call_args[0][0]
        assert '"down"' in call_args[2]

    def test_scroll_capped_at_20(self):
        inp = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            inp.scroll(100)
        call_args = mock_run.call_args[0][0]
        # 20 scroll lines max
        assert call_args[2].count("scroll") == 20

    def test_scroll_oserror(self):
        inp = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert inp.scroll(1) is False

    def test_to_applescript_key_known(self):
        from core.platform.macos_backend import MacOSStealthInput

        assert MacOSStealthInput._to_applescript_key("enter") == 36
        assert MacOSStealthInput._to_applescript_key("escape") == 53
        assert MacOSStealthInput._to_applescript_key("tab") == 48
        assert MacOSStealthInput._to_applescript_key("f1") == 122
        assert MacOSStealthInput._to_applescript_key("pageup") == 116

    def test_to_applescript_key_single_char(self):
        from core.platform.macos_backend import MacOSStealthInput

        # Single char → ASCII-based key code
        result = MacOSStealthInput._to_applescript_key("a")
        assert result == ord("A") - 32

    def test_to_applescript_key_unknown(self):
        from core.platform.macos_backend import MacOSStealthInput

        assert MacOSStealthInput._to_applescript_key("unknown_key") == 0

    def test_to_applescript_key_empty(self):
        from core.platform.macos_backend import MacOSStealthInput

        assert MacOSStealthInput._to_applescript_key("") == 0


# ── MacOSCredentialBackend ─────────────────────────────────────────────────────


class TestMacOSCredentialBackend:
    def _make_with_security(self, tmp_path: Path):
        from core.platform.macos_backend import MacOSCredentialBackend

        cred = MacOSCredentialBackend.__new__(MacOSCredentialBackend)
        cred._has_security = True
        cred._file_path = tmp_path / "vault.json"
        import threading

        cred._lock = threading.RLock()
        cred._file_data = {"version": 1, "keys": {}}
        return cred

    def _make_file_only(self, tmp_path: Path):
        from core.platform.macos_backend import MacOSCredentialBackend

        cred = MacOSCredentialBackend.__new__(MacOSCredentialBackend)
        cred._has_security = False
        cred._file_path = tmp_path / "vault.json"
        import threading

        cred._lock = threading.RLock()
        cred._file_data = {"version": 1, "keys": {}}
        return cred

    def test_store_keychain_success(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert cred.store("mykey", "myval") is True

    def test_store_keychain_oserror_fallback(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", side_effect=OSError("fail")):
            # Falls back to file store
            result = cred.store("mykey", "myval")
        # File store should succeed
        assert result is True

    def test_retrieve_keychain_success(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0, stdout="secretval\n")):
            val = cred.retrieve("mykey")
        assert val == "secretval"

    def test_retrieve_keychain_not_found(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1)):
            val = cred.retrieve("missingkey")
        assert val is None

    def test_retrieve_keychain_oserror_fallback(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", side_effect=OSError("fail")):
            val = cred.retrieve("mykey")
        assert val is None

    def test_delete_keychain_success(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert cred.delete("mykey") is True

    def test_delete_keychain_failure(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1)):
            assert cred.delete("mykey") is False

    def test_delete_keychain_oserror(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("security", 5)):
            assert cred.delete("mykey") is False

    def test_list_keychain_with_matches(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        # Parser requires service name AND "acct" on the SAME line
        stdout = (
            'keychain: "/Users/test/Library/Keychains/login.keychain-db"\n'
            '    "acct"<blob>="mykey" "svce"<blob>="sentinel-desktop"\n'
            '    "acct"<blob>="other" "svce"<blob>="other-service"\n'
        )
        with patch("subprocess.run", return_value=_make_proc(0, stdout=stdout)):
            keys = cred.list_keys()
        assert "mykey" in keys

    def test_list_keychain_failure_fallback(self, tmp_path):
        cred = self._make_with_security(tmp_path)
        with patch("subprocess.run", side_effect=OSError("fail")):
            keys = cred.list_keys()
        assert keys == []

    def test_store_file(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        result = cred.store("k1", "v1")
        assert result is True
        val = cred.retrieve("k1")
        assert val == "v1"

    def test_retrieve_file_missing_key(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        assert cred.retrieve("nonexistent") is None

    def test_retrieve_file_bad_encrypted(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        cred._file_data["keys"]["bad"] = {"encrypted": "!!!bad_b64!!!"}
        # Should handle ValueError gracefully
        val = cred.retrieve("bad")
        assert val is None

    def test_delete_file_success(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        cred.store("k2", "v2")
        assert cred.delete("k2") is True
        assert cred.retrieve("k2") is None

    def test_delete_file_not_found(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        assert cred.delete("ghost") is False

    def test_list_file(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        cred.store("alpha", "1")
        cred.store("beta", "2")
        keys = cred.list_keys()
        assert "alpha" in keys
        assert "beta" in keys

    def test_load_file_not_exists(self, tmp_path):
        from core.platform.macos_backend import MacOSCredentialBackend

        cred = MacOSCredentialBackend.__new__(MacOSCredentialBackend)
        cred._file_path = tmp_path / "nonexistent.json"
        data = cred._load_file()
        assert data == {"version": 1, "keys": {}}

    def test_load_file_valid(self, tmp_path):
        import json

        from core.platform.macos_backend import MacOSCredentialBackend

        vault = tmp_path / "vault.json"
        vault.write_text(json.dumps({"version": 1, "keys": {"k": {"encrypted": "dg=="}}}))
        cred = MacOSCredentialBackend.__new__(MacOSCredentialBackend)
        cred._file_path = vault
        data = cred._load_file()
        assert "keys" in data

    def test_load_file_invalid_json(self, tmp_path):
        from core.platform.macos_backend import MacOSCredentialBackend

        vault = tmp_path / "vault.json"
        vault.write_text("not json{{{")
        cred = MacOSCredentialBackend.__new__(MacOSCredentialBackend)
        cred._file_path = vault
        data = cred._load_file()
        assert data == {"version": 1, "keys": {}}

    def test_load_file_missing_keys(self, tmp_path):
        import json

        from core.platform.macos_backend import MacOSCredentialBackend

        vault = tmp_path / "vault.json"
        vault.write_text(json.dumps({"version": 1}))
        cred = MacOSCredentialBackend.__new__(MacOSCredentialBackend)
        cred._file_path = vault
        data = cred._load_file()
        assert data == {"version": 1, "keys": {}}

    def test_save_file_oserror(self, tmp_path):
        cred = self._make_file_only(tmp_path)
        # _save_file now writes atomically (temp + fsync + os.replace); inject
        # the OSError at the fsync step since the write_text path is gone.
        with patch("os.fsync", side_effect=OSError("no space")):
            assert cred._save_file() is False

    def test_iso_now(self, tmp_path):
        from core.platform.macos_backend import MacOSCredentialBackend

        result = MacOSCredentialBackend._iso_now()
        assert "T" in result  # ISO 8601 format


# ── MacOSShellBackend ──────────────────────────────────────────────────────────


class TestMacOSShellBackend:
    def _make(self):
        from core.platform.macos_backend import MacOSShellBackend

        return MacOSShellBackend()

    def test_execute_success(self):
        sh = self._make()
        with patch("subprocess.run", return_value=_make_proc(0, stdout="hello\n")):
            result = sh.execute("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    def test_execute_timeout(self):
        sh = self._make()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("zsh", 60)):
            result = sh.execute("sleep 999")
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"]

    def test_execute_oserror(self):
        sh = self._make()
        with patch("subprocess.run", side_effect=OSError("no zsh")):
            result = sh.execute("echo hi")
        assert result["exit_code"] == -1

    def test_get_platform_shell(self):
        sh = self._make()
        assert sh.get_platform_shell() == "zsh"

    def test_sanitize_command_safe(self):
        sh = self._make()
        assert sh.sanitize_command("ls -la") == "ls -la"

    def test_sanitize_command_dangerous(self):
        sh = self._make()
        with pytest.raises(ValueError, match="dangerous"):
            sh.sanitize_command("rm -rf /")

    def test_sanitize_command_fork_bomb(self):
        sh = self._make()
        with pytest.raises(ValueError):
            sh.sanitize_command(":(){ :|:& };:")


# ── MacOSWindowBackend ─────────────────────────────────────────────────────────


class TestMacOSWindowBackend:
    def _make(self, has_osascript: bool = True):
        from core.platform.macos_backend import MacOSWindowBackend

        win = MacOSWindowBackend.__new__(MacOSWindowBackend)
        win._has_osascript = has_osascript
        return win

    def test_list_windows_not_available(self):
        win = self._make(False)
        assert win.list_windows() == []

    def test_list_windows_success(self):
        win = self._make(True)
        output = "Finder|100,200|800,600\nSafari|50,100|1200,800\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            windows = win.list_windows()
        assert len(windows) == 2
        assert windows[0].title == "Finder"

    def test_list_windows_subprocess_fails(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(1)):
            assert win.list_windows() == []

    def test_list_windows_oserror(self):
        win = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert win.list_windows() == []

    def test_focus_window_not_available(self):
        win = self._make(False)
        assert win.focus_window("Finder") is False

    def test_focus_window_success(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert win.focus_window("Finder") is True

    def test_focus_window_with_quotes_in_title(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            win.focus_window('My "App"')
        call_args = mock_run.call_args[0][0]
        assert '\\"' in call_args[2]

    def test_focus_window_failure(self):
        win = self._make(True)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osa", 5)):
            assert win.focus_window("Finder") is False

    def test_close_window_not_available(self):
        win = self._make(False)
        assert win.close_window("Finder") is False

    def test_close_window_success(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert win.close_window("Finder") is True

    def test_close_window_oserror(self):
        win = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert win.close_window("Finder") is False

    def test_get_focused_window_rect_not_available(self):
        win = self._make(False)
        assert win.get_focused_window_rect() is None

    def test_get_focused_window_rect_success(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0, stdout="100, 200, 800, 600")):
            rect = win.get_focused_window_rect()
        assert rect == (100, 200, 800, 600)

    def test_get_focused_window_rect_bad_output(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0, stdout="bad")):
            assert win.get_focused_window_rect() is None

    def test_get_focused_window_rect_oserror(self):
        win = self._make(True)
        with patch("subprocess.run", side_effect=OSError("fail")):
            assert win.get_focused_window_rect() is None

    def test_get_window_rect_found(self):
        win = self._make(True)
        output = "Finder|100,200|800,600\n"
        with patch("subprocess.run", return_value=_make_proc(0, stdout=output)):
            rect = win.get_window_rect("finder")
        assert rect == (100, 200, 800, 600)

    def test_get_window_rect_not_found(self):
        win = self._make(True)
        with patch("subprocess.run", return_value=_make_proc(0, stdout="")):
            assert win.get_window_rect("NoSuchApp") is None

    def test_parse_window_list_valid(self):
        from core.platform.macos_backend import MacOSWindowBackend

        output = "Finder|100,200|800,600\nSafari|0,0|1440,900\n"
        windows = MacOSWindowBackend._parse_window_list(output)
        assert len(windows) == 2
        assert windows[0].title == "Finder"
        assert windows[0].x == 100
        assert windows[1].width == 1440

    def test_parse_window_list_bad_line(self):
        # Single-part line skipped by the len < 3 guard
        from core.platform.macos_backend import MacOSWindowBackend

        output = "bad_line\nFinder|100,200|800,600\n"
        windows = MacOSWindowBackend._parse_window_list(output)
        assert len(windows) == 1

    def test_parse_window_list_invalid_coords(self):
        # 3 parts but non-integer coords → ValueError → line 817-818 covered
        from core.platform.macos_backend import MacOSWindowBackend

        output = "Finder|bad,pos|wrong,size\nSafari|0,0|1440,900\n"
        windows = MacOSWindowBackend._parse_window_list(output)
        assert len(windows) == 1
        assert windows[0].title == "Safari"

    def test_parse_window_list_empty(self):
        from core.platform.macos_backend import MacOSWindowBackend

        assert MacOSWindowBackend._parse_window_list("") == []


# ── MacOSOverlayBackend ────────────────────────────────────────────────────────


class TestMacOSOverlayBackend:
    def _make(self):
        from core.platform.macos_backend import MacOSOverlayBackend

        return MacOSOverlayBackend()

    def test_is_available(self):
        ov = self._make()
        with patch("subprocess.run", return_value=_make_proc(0)):
            assert ov.is_available() is True

    def test_show_ring_exception_swallowed(self):
        ov = self._make()
        # tkinter.Tk() will fail in headless environment — exception should be swallowed
        with patch("tkinter.Tk", side_effect=RuntimeError("no display")):
            ov.show_ring(100, 200)  # should not raise

    def test_show_ring_tkinter_success(self):
        # Mock tkinter so the happy path (lines 839-846) executes without a display
        import tkinter as tk

        ov = self._make()
        mock_root = MagicMock()
        mock_canvas = MagicMock()
        with patch.object(tk, "Tk", return_value=mock_root):
            with patch.object(tk, "Canvas", return_value=mock_canvas):
                ov.show_ring(200, 300, duration_ms=100, color="red")
        mock_root.mainloop.assert_called_once()

    def test_show_cursor_move_success(self):
        ov = self._make()
        with patch("subprocess.run", return_value=_make_proc(0)):
            ov.show_cursor_move(0, 0, 100, 200)  # no return value

    def test_show_cursor_move_oserror(self):
        ov = self._make()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osa", 3)):
            ov.show_cursor_move(0, 0, 100, 200)  # should not raise


# ── MacOSBackend (aggregated) ──────────────────────────────────────────────────


class TestMacOSBackendAggregated:
    def test_all_subsystems_present(self):
        from core.platform.macos_backend import (
            MacOSAccessibility,
            MacOSBackend,
            MacOSCredentialBackend,
            MacOSOverlayBackend,
            MacOSShellBackend,
            MacOSStealthInput,
            MacOSWindowBackend,
        )

        with patch("subprocess.run", return_value=_make_proc(1)):
            backend = MacOSBackend()

        assert isinstance(backend.accessibility, MacOSAccessibility)
        assert isinstance(backend.stealth, MacOSStealthInput)
        assert isinstance(backend.credentials, MacOSCredentialBackend)
        assert isinstance(backend.shell, MacOSShellBackend)
        assert isinstance(backend.window, MacOSWindowBackend)
        assert isinstance(backend.overlay, MacOSOverlayBackend)
        assert backend.default_shell == "zsh"
