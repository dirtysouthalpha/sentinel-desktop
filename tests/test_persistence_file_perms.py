"""Owner-only (0600) permission tests for ~/.sentinel/ persistence writers.

These files hold sensitive material — audit action arguments, trigger
payloads, the user's verbatim episodic goals, and cost/token logs — and must
not be readable by other local users on a shared IT host. POSIX-only: on
Windows the file ACL governs access and the mode bits are a no-op.
"""

from __future__ import annotations

import os
import stat
import sys

import pytest

from core.audit_chain import AuditChain
from core.auth import AuthManager, Role
from core.cost_tracker import CostTracker
from core.memory.episodic import EpisodicMemory
from core.memory.semantic import SemanticMemory
from core.triggers import EventType, Trigger, TriggerRegistry

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits"
)


def _group_other_bits(path) -> int:
    return stat.S_IMODE(path.stat().st_mode) & 0o077


class TestAuditChainPerms:
    def test_append_creates_owner_only(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        chain = AuditChain(path)
        chain.append("action", actor="admin", data={"path": "/secret"})
        assert _group_other_bits(path) == 0

    def test_legacy_world_readable_healed_on_load(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        path.write_text(
            '{"seq":1,"entry_hash":"x"}\n', encoding="utf-8"
        )
        os.chmod(path, 0o644)
        assert _group_other_bits(path) != 0
        AuditChain(path)  # opening heals perms
        assert _group_other_bits(path) == 0


class TestTriggerRegistryPerms:
    def test_save_creates_owner_only(self, tmp_path):
        reg = TriggerRegistry(storage_dir=tmp_path / "trig")
        reg.add(
            Trigger(
                name="x",
                event_type=EventType.CUSTOM,
                condition={"event_name": "foo"},
                action={"action": "speak", "text": "hi"},
            )
        )
        assert _group_other_bits(reg._file) == 0

    def test_legacy_world_readable_healed_on_load(self, tmp_path):
        reg = TriggerRegistry(storage_dir=tmp_path / "trig")
        reg._file.parent.mkdir(parents=True, exist_ok=True)
        reg._file.write_text("[]", encoding="utf-8")
        os.chmod(reg._file, 0o644)
        assert _group_other_bits(reg._file) != 0
        TriggerRegistry(storage_dir=tmp_path / "trig")  # opening heals
        assert _group_other_bits(reg._file) == 0


class TestEpisodicMemoryPerms:
    def test_store_creates_owner_only(self, tmp_path):
        path = tmp_path / "episodes.jsonl"
        mem = EpisodicMemory(path=path)
        mem.store(
            "Login to firewall with admin creds",
            actions=[{"action": "ssh_run"}],
            outcome="ok",
        )
        assert _group_other_bits(path) == 0


class TestSemanticMemoryPerms:
    def test_store_creates_owner_only(self, tmp_path):
        path = tmp_path / "semantic.db"
        mem = SemanticMemory(path=path)
        mem.store(
            "firewall_default_creds",
            "SonicWall default: admin/password",
            category="credentials",
        )
        assert _group_other_bits(path) == 0

    def test_legacy_world_readable_healed_on_open(self, tmp_path):
        path = tmp_path / "semantic.db"
        SemanticMemory(path=path)  # creates a valid SQLite db at 0600
        os.chmod(path, 0o644)
        assert _group_other_bits(path) != 0
        SemanticMemory(path=path)  # reopening heals perms
        assert _group_other_bits(path) == 0


class TestCostTrackerPerms:
    def test_record_creates_owner_only(self, tmp_path):
        path = tmp_path / "cost_history.jsonl"
        tracker = CostTracker(history_path=path)
        tracker.record("openai", "gpt-4o", {"prompt_tokens": 10, "completion_tokens": 5})
        assert _group_other_bits(path) == 0


class TestAuthUsersPerms:
    def test_save_creates_owner_only(self, tmp_path):
        # users.json stores bcrypt password hashes + API keys — must be 0600.
        path = tmp_path / "users.json"
        manager = AuthManager(config_path=str(path))
        manager.create_user("ops", "s3cret", role=Role.OPERATOR)
        assert _group_other_bits(path) == 0

    def test_legacy_world_readable_healed_on_load(self, tmp_path):
        path = tmp_path / "users.json"
        manager = AuthManager(config_path=str(path))  # bootstraps default admin
        manager._save()
        os.chmod(path, 0o644)
        assert _group_other_bits(path) != 0
        AuthManager(config_path=str(path))  # reopening heals perms
        assert _group_other_bits(path) == 0

