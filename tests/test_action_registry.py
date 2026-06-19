"""Tests for core.action_registry and the v18 dispatch-table migration.

The hard invariant: the registry-derived action-name set must equal the v17
``_dispatch_table`` key set exactly (110 names, no drift). Zero behavior change.
"""

from __future__ import annotations

import pytest

from core import action_executor as ae
from core import action_registry as ar

# The exact baseline captured from the _dispatch_table.
# Locking this down prevents silent action additions/removals across the
# registry migration and any future refactor.
_V17_BASELINE_NAMES = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "click_text",
        "click_image",
        "click_control",
        "click_element",
        "click_mark",
        "list_controls",
        "list_elements",
        "web_open",
        "web_click",
        "web_type",
        "web_read",
        "web_extract",
        "web_wait_for",
        "web_screenshot",
        "web_eval_js",
        "web_download",
        "web_upload",
        "web_tabs",
        "ssh_connect",
        "ssh_disconnect",
        "ssh_run",
        "ssh_show",
        "ssh_ping",
        "ssh_traceroute",
        "memory_store",
        "memory_recall",
        "memory_search",
        "memory_forget",
        "conductor_run",
        "set_text",
        "read_text",
        "read_window",
        "type_text",
        "press_key",
        "hotkey",
        "scroll",
        "mouse_move",
        "drag",
        "screenshot",
        "find_image",
        "wait",
        "wait_for_image",
        "smart_wait",
        "wait_for_stable",
        "wait_for_text",
        "open_app",
        "smart_open",
        "close_app",
        "focus_window",
        "close_window",
        "list_windows",
        "read_file",
        "write_file",
        "list_directory",
        "delete_file",
        "move_file",
        "copy_file",
        "mkdir",
        "stat_file",
        "find_files",
        "archive_create",
        "archive_extract",
        "set_priority",
        "get_env",
        "set_env",
        "service_control",
        "cred_store",
        "cred_read",
        "registry_read",
        "registry_write",
        "registry_delete",
        "clipboard_read",
        "clipboard_write",
        "system_info",
        "list_processes",
        "start_process",
        "kill_process",
        "note",
        "finish",
        "powershell",
        "run_script",
        "retry_last",
        "get_circuit_breakers",
        "config_get",
        "config_set",
        "dns_lookup",
        "ping",
        "port_scan",
        "resize_window",
        "move_window",
        "minimize_window",
        "maximize_window",
        "restore_window",
        "get_window_state",
        "get_monitors",
        "http_get",
        "http_post",
        "http_download",
        "watch_file",
        "watch_file_content",
        "watch_process",
        "speak",
        "listen",
        "volume_get",
        "volume_set",
        "mute_toggle",
        "list_voices",
        # Neuralis Brain (fleet-wide shared memory)
        "brain_think",
        "brain_recall",
        "brain_search",
        "brain_stats",
        "brain_fire",
        # v21 — Cost tracker
        "cost_summary",
        "cost_history",
        "cost_reset",
        # v21 — Eval harness
        "eval_list",
        "eval_run",
        "eval_results",
        # v21 — Skill marketplace
        "skill_list",
        "skill_search",
        "skill_install",
        "skill_get",
        "skill_export",
        "skill_uninstall",
        "skill_run",
        # v22 — Event triggers
        "trigger_add",
        "trigger_remove",
        "trigger_list",
        "trigger_enable",
        "trigger_disable",
        "trigger_fire_custom",
        # v22 — Voice engine
        "voice_start_ambient",
        "voice_stop_ambient",
        "voice_status",
    }
)


# ---------------------------------------------------------------------------
# Parity: registry == dispatch table == v17 baseline
# ---------------------------------------------------------------------------
class TestDispatchParity:
    def test_dispatch_table_has_128_entries(self):
        assert len(ae.ActionExecutor._dispatch_table) == 137

    def test_dispatch_table_keys_equal_registry(self):
        """The dispatch table and the registry must expose the same names."""
        assert set(ae.ActionExecutor._dispatch_table) == set(ar.registered_names())

    def test_registry_keys_equal_v17_baseline(self):
        """No action may be silently added or removed vs the v17 set."""
        registry = set(ar.registered_names())
        assert registry == _V17_BASELINE_NAMES, (
            f"drift: added={registry - _V17_BASELINE_NAMES} "
            f"removed={_V17_BASELINE_NAMES - registry}"
        )

    def test_dispatch_table_values_match_registry(self):
        """Each name must resolve to the same handler in both places."""
        table = ae.ActionExecutor._dispatch_table
        for name, handler in table.items():
            assert ar.resolve(name) is handler, f"{name} handler mismatch"

    def test_alias_click_double_click_right_click_share_handler(self):
        """The one multi-name alias group must still resolve to one function."""
        table = ae.ActionExecutor._dispatch_table
        assert table["click"] is table["double_click"] is table["right_click"]


# ---------------------------------------------------------------------------
# Registry primitives
# ---------------------------------------------------------------------------
class TestRegisterAction:
    def test_duplicate_name_raises(self):
        """Registering the same name twice (different functions) must fail loud.

        Uses a throwaway name so the global registry is restored cleanly — no
        ``clear()``/reload (which would break other tests' parity checks).
        """
        from core.action_registry import _REGISTRY, ActionAlreadyRegistered

        sentinel_name = "__test_dup_unique_v18__"

        @ar.register_action(sentinel_name)
        def _a(self):
            return {}

        try:
            with pytest.raises(ActionAlreadyRegistered):

                @ar.register_action(sentinel_name)
                def _b(self):
                    return {}

            # The original registration survived the duplicate attempt.
            assert _REGISTRY[sentinel_name] is _a
        finally:
            _REGISTRY.pop(sentinel_name, None)

    def test_unknown_action_resolves_none(self):
        assert ar.resolve("definitely_not_a_real_action") is None

    def test_snapshot_returns_copy(self):
        snap = ar.snapshot()
        snap["__injected__"] = lambda self: {}  # type: ignore[assignment]
        assert "__injected__" not in ar.snapshot()

    def test_registered_names_is_sorted(self):
        names = ar.registered_names()
        assert names == sorted(names)
