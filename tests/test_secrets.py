"""Tests for core/secrets.py — Secrets Vault Broker (v19)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from core.audit_chain import AuditChain
from core.policy import PolicyEngine, PolicyViolation
from core.secrets import (
    SecretNotFound,
    SecretsVault,
    _make_key,
    get_default_vault,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(
    tmp_path: Path, *, with_policy: bool = False, deny_pattern: str = ""
) -> tuple[SecretsVault, AuditChain]:
    """Create a SecretsVault backed by tmp_path files."""
    vault_file = tmp_path / "vault.json"
    audit_file = tmp_path / "audit.jsonl"
    audit = AuditChain(audit_file)

    if with_policy and deny_pattern:
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_effect": "allow",
                    "rules": [
                        {
                            "type": "file_path",
                            "pattern": deny_pattern,
                            "effect": "deny",
                            "reason": "test policy deny",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        policy = PolicyEngine(str(policy_file))
    else:
        policy = None

    vault = SecretsVault(str(vault_file), policy_engine=policy, audit_chain=audit)
    return vault, audit


# ---------------------------------------------------------------------------
# _make_key helper
# ---------------------------------------------------------------------------


class TestMakeKey:
    def test_default_category(self):
        assert _make_key("mykey", "default") == "default/mykey"

    def test_custom_category(self):
        assert _make_key("token", "api") == "api/token"

    def test_strips_leading_slash(self):
        key = _make_key("name", "/api/")
        assert not key.startswith("/")


# ---------------------------------------------------------------------------
# SecretsVault — core CRUD
# ---------------------------------------------------------------------------


class TestSecretsVaultPut:
    def test_put_stores_secret(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("mykey", "secret123")
        assert vault.exists("mykey")

    def test_put_custom_category(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("token", "abc", category="api")
        assert vault.exists("token", category="api")
        assert not vault.exists("token", category="ssh")

    def test_put_overwrites_existing(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("key", "v1")
        vault.put("key", "v2")
        assert vault.get("key") == "v2"

    def test_put_emits_audit_event(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.put("key", "val", actor="alice")
        entries = audit.entries()
        assert len(entries) == 1
        assert entries[0]["event_type"] == "secret_put"
        assert entries[0]["actor"] == "alice"
        assert "key" in entries[0]["data"]["key"]


class TestSecretsVaultGet:
    def test_get_returns_value(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("apikey", "sk-abc")
        assert vault.get("apikey") == "sk-abc"

    def test_get_not_found_raises(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        with pytest.raises(SecretNotFound):
            vault.get("missing")

    def test_get_category_isolation(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("key", "val", category="a")
        with pytest.raises(SecretNotFound):
            vault.get("key", category="b")

    def test_get_emits_audit_event(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.put("k", "v", actor="system")
        vault.get("k", actor="bob")
        events = [e["event_type"] for e in audit.entries()]
        assert "secret_put" in events
        assert "secret_get" in events


class TestSecretsVaultDelete:
    def test_delete_removes_secret(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("key", "val")
        result = vault.delete("key")
        assert result is True
        assert not vault.exists("key")

    def test_delete_nonexistent_returns_false(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        result = vault.delete("nonexistent")
        assert result is False

    def test_delete_emits_audit_event(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.put("k", "v")
        vault.delete("k", actor="admin")
        events = [e["event_type"] for e in audit.entries()]
        assert "secret_delete" in events

    def test_delete_nonexistent_no_audit(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.delete("missing")
        # put wasn't called so audit starts empty; delete non-existent = no event
        assert len(audit.entries()) == 0


class TestSecretsVaultRotate:
    def test_rotate_updates_value(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("k", "old")
        vault.rotate("k", "new")
        assert vault.get("k") == "new"

    def test_rotate_nonexistent_raises(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        with pytest.raises(SecretNotFound):
            vault.rotate("missing", "new_val")

    def test_rotate_emits_audit_event(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.put("k", "v1")
        vault.rotate("k", "v2", actor="ops")
        events = [e["event_type"] for e in audit.entries()]
        assert "secret_rotate" in events
        rotate_entry = next(e for e in audit.entries() if e["event_type"] == "secret_rotate")
        assert rotate_entry["actor"] == "ops"


class TestSecretsVaultList:
    def test_list_all(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("a", "1", category="x")
        vault.put("b", "2", category="y")
        keys = vault.list_secrets()
        assert "x/a" in keys
        assert "y/b" in keys

    def test_list_by_category(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("a", "1", category="api")
        vault.put("b", "2", category="ssh")
        api_keys = vault.list_secrets(category="api")
        assert "api/a" in api_keys
        assert "ssh/b" not in api_keys

    def test_list_empty_vault(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        assert vault.list_secrets() == []


class TestSecretsVaultExists:
    def test_exists_true(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("k", "v")
        assert vault.exists("k") is True

    def test_exists_false(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        assert vault.exists("missing") is False

    def test_exists_category_scoped(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("k", "v", category="api")
        assert vault.exists("k", category="api") is True
        assert vault.exists("k", category="ssh") is False


# ---------------------------------------------------------------------------
# Policy integration
# ---------------------------------------------------------------------------


class TestSecretsVaultPolicy:
    def test_policy_denies_put(self, tmp_path):
        vault, _ = _make_vault(tmp_path, with_policy=True, deny_pattern="/secret/**")
        with pytest.raises(PolicyViolation):
            vault.put("key", "val")

    def test_policy_denies_get(self, tmp_path):
        # Put directly via the vault bypass to pre-load; then check get denied
        vault_file = tmp_path / "vault.json"
        policy_file = tmp_path / "policy.json"
        audit_file = tmp_path / "audit.jsonl"

        # First, store without policy
        from core.secrets import SecretsVault as SV

        bare = SV(str(vault_file))
        bare.put("secret_key", "value")

        # Now enforce policy
        policy_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_effect": "allow",
                    "rules": [{"type": "file_path", "pattern": "/secret/**", "effect": "deny"}],
                }
            ),
            encoding="utf-8",
        )
        policy = PolicyEngine(str(policy_file))
        audit = AuditChain(audit_file)
        protected = SV(str(vault_file), policy_engine=policy, audit_chain=audit)
        with pytest.raises(PolicyViolation):
            protected.get("secret_key")

    def test_policy_role_scoped(self, tmp_path):
        """Admin can access secrets, viewer cannot."""
        vault_file = tmp_path / "vault.json"
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_effect": "allow",
                    "rules": [
                        {
                            "type": "file_path",
                            "pattern": "/secret/**",
                            "roles": ["viewer"],
                            "effect": "deny",
                            "reason": "viewers cannot access secrets",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        policy = PolicyEngine(str(policy_file))
        vault = SecretsVault(str(vault_file), policy_engine=policy)
        vault.put("key", "val", role="admin")  # admin can put

        with pytest.raises(PolicyViolation):
            vault.get("key", role="viewer")  # viewer blocked

        assert vault.get("key", role="admin") == "val"  # admin can read

    def test_no_policy_engine_allows_all(self, tmp_path):
        vault_file = tmp_path / "vault.json"
        vault = SecretsVault(str(vault_file), policy_engine=None)
        vault.put("k", "v")
        assert vault.get("k") == "v"


# ---------------------------------------------------------------------------
# Audit chain integrity
# ---------------------------------------------------------------------------


class TestSecretsAuditIntegrity:
    def test_audit_chain_verifies_after_operations(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.put("k1", "v1", actor="alice")
        vault.put("k2", "v2", actor="bob")
        vault.get("k1", actor="carol")
        vault.rotate("k1", "new_v1", actor="alice")
        vault.delete("k2", actor="admin")
        ok, bad = audit.verify()
        assert ok is True, f"Audit chain corrupted: bad seqs={bad}"

    def test_audit_entries_ordered(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        vault.put("a", "1", actor="user1")
        vault.put("b", "2", actor="user2")
        vault.get("a", actor="user3")
        entries = audit.entries()
        assert entries[0]["event_type"] == "secret_put"
        assert entries[0]["actor"] == "user1"
        assert entries[2]["event_type"] == "secret_get"


# ---------------------------------------------------------------------------
# Summary and inspection
# ---------------------------------------------------------------------------


class TestSecretsVaultSummary:
    def test_summary_empty(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        s = vault.summary()
        assert "0 secret(s)" in s
        assert "audit=active" in s

    def test_summary_with_secrets(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        vault.put("a", "1")
        vault.put("b", "2")
        s = vault.summary()
        assert "2 secret(s)" in s

    def test_summary_no_policy(self, tmp_path):
        vault_file = tmp_path / "vault.json"
        vault = SecretsVault(str(vault_file), policy_engine=None, audit_chain=None)
        s = vault.summary()
        assert "policy=none" in s
        assert "audit=none" in s


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestSecretsVaultThreadSafety:
    def test_concurrent_puts_and_gets(self, tmp_path):
        vault, audit = _make_vault(tmp_path)
        errors = []

        def worker(i: int):
            try:
                key = f"key_{i}"
                vault.put(key, f"val_{i}")
                result = vault.get(key)
                assert result == f"val_{i}"
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        ok, bad = audit.verify()
        assert ok is True, f"Audit chain corrupt: {bad}"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestGetDefaultVault:
    def test_returns_same_instance(self, tmp_path):
        import core.secrets as secrets_mod

        secrets_mod._default_vault = None
        vault_path = str(tmp_path / "vault.json")
        audit_path = str(tmp_path / "audit.jsonl")
        v1 = get_default_vault(vault_path, audit_path)
        v2 = get_default_vault(vault_path, audit_path)
        assert v1 is v2
        secrets_mod._default_vault = None  # cleanup

    def test_singleton_is_secrets_vault(self, tmp_path):
        import core.secrets as secrets_mod

        secrets_mod._default_vault = None
        v = get_default_vault(str(tmp_path / "v.json"), str(tmp_path / "a.jsonl"))
        assert isinstance(v, SecretsVault)
        secrets_mod._default_vault = None
