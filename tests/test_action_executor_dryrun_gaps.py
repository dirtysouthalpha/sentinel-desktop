"""Dry-run guard coverage for state-changing actions added after v17.

The ``STATE_CHANGING_ACTIONS`` set gates which actions are short-circuited (logged
instead of executed) in dry-run mode. FS/registry/credential/memory/system/skill/
trigger/voice actions were wired into the dispatch table over v16-v22 but never
added to the set, so dry-run mode — which promises "logged, not executed" — was
silently performing real ``delete_file``/``registry_write``/``service_control`` etc.
These tests pin the guard for every state-changing action so the set can't drift
again without a failing test.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Every action that mutates local FS / registry / credential / memory / system /
# trigger / voice state. Read-only actions (read_file, list_*, screenshot, ping,
# dns_lookup, *_recall/search, web_*, ssh_run) are deliberately excluded.
STATE_CHANGING_ACTIONS_TO_GUARD = [
    "delete_file",
    "move_file",
    "copy_file",
    "mkdir",
    "archive_create",
    "archive_extract",
    "registry_write",
    "registry_delete",
    "cred_store",
    "memory_store",
    "memory_forget",
    "set_env",
    "set_priority",
    "service_control",
    "cost_reset",
    "skill_install",
    "skill_uninstall",
    "trigger_add",
    "trigger_remove",
    "trigger_enable",
    "trigger_disable",
    "trigger_fire_custom",
    "voice_start_ambient",
    "voice_stop_ambient",
]


@pytest.mark.parametrize("action", STATE_CHANGING_ACTIONS_TO_GUARD)
def test_dry_run_short_circuits_state_changing_action(action):
    """In dry-run, a state-changing action must return a dry_run result and
    never reach its handler."""
    from core.action_executor import ActionExecutor, ExecutorConfig

    ex = ActionExecutor(config=ExecutorConfig(dry_run=True))
    # Shadow the class dispatch table with an instance copy so the sentinel
    # never mutates shared state. If the guard fails to fire, the sentinel runs
    # and returns a non-dry_run dict.
    sentinel = MagicMock(return_value={"success": True, "output": "handler-ran"})
    ex._dispatch_table = {**ex._dispatch_table, action: sentinel}

    result = ex.execute_sync({"action": action})

    assert result.get("dry_run") is True, (
        f"{action!r} must be short-circuited in dry-run mode "
        f"(got {result!r})"
    )
    sentinel.assert_not_called()


def test_dry_run_does_not_actually_delete_file(tmp_path):
    """The headline safety property: dry-run mode must not delete a real file.

    Uses the real ``delete_file`` handler (no mock) — before the set was fixed
    the handler ran and the file was destroyed.
    """
    from core.action_executor import ActionExecutor, ExecutorConfig

    target = tmp_path / "important.txt"
    target.write_text("keep-me")

    ex = ActionExecutor(config=ExecutorConfig(dry_run=True))
    result = ex.execute_sync({"action": "delete_file", "path": str(target)})

    assert result.get("dry_run") is True
    assert target.exists(), "dry-run mode must not actually delete the file"
    assert target.read_text() == "keep-me"


def test_dry_run_still_runs_read_only_action():
    """Read-only actions must still execute for real in dry-run mode so the
    agent can observe — guards the regression where a read-only action gets
    accidentally added to the set."""
    from core.action_executor import ActionExecutor, ExecutorConfig

    ex = ActionExecutor(config=ExecutorConfig(dry_run=True))
    sentinel = MagicMock(return_value={"success": True, "output": "ran"})
    ex._dispatch_table = {**ex._dispatch_table, "read_file": sentinel}

    result = ex.execute_sync({"action": "read_file", "path": "/tmp/whatever"})

    assert result.get("dry_run") is None, "read_file must NOT be dry-run-guarded"
    sentinel.assert_called_once()
