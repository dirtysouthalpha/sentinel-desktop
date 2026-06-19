"""Tests for core/policy.py — Declarative Policy Guardrails (v19)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from core.policy import (
    PolicyEngine,
    PolicyViolation,
    _fnmatch_path,
    _role_matches,
    get_default_engine,
)


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestFnmatchPath:
    def test_exact_match(self):
        assert _fnmatch_path("/etc/passwd", "/etc/passwd")

    def test_star_does_not_cross_slash(self):
        assert not _fnmatch_path("/etc/*", "/etc/sub/file")

    def test_double_star_crosses_slash(self):
        assert _fnmatch_path("/etc/**", "/etc/sub/file")

    def test_no_match(self):
        assert not _fnmatch_path("/tmp/**", "/etc/passwd")

    def test_action_glob(self):
        assert _fnmatch_path("write_*", "write_file")
        assert not _fnmatch_path("write_*", "read_file")


class TestRoleMatches:
    def test_no_roles_means_all(self):
        assert _role_matches(None, "admin")
        assert _role_matches([], "viewer")
        assert _role_matches(None, None)

    def test_specific_role(self):
        assert _role_matches(["admin"], "admin")
        assert not _role_matches(["admin"], "viewer")

    def test_case_insensitive(self):
        assert _role_matches(["Admin", "Viewer"], "admin")

    def test_none_role_not_in_list(self):
        assert not _role_matches(["admin"], None)


# ---------------------------------------------------------------------------
# PolicyEngine unit tests
# ---------------------------------------------------------------------------


@pytest.fixture
def policy_file(tmp_path: Path):
    """Write a policy JSON and return its path."""
    def _make(rules, default_effect="allow"):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps({"version": 1, "default_effect": default_effect, "rules": rules}),
            encoding="utf-8",
        )
        return str(path)

    return _make


class TestPolicyEngineLoad:
    def test_missing_file_passes_all(self, tmp_path):
        engine = PolicyEngine(str(tmp_path / "nonexistent.json"))
        assert engine.loaded is False
        allowed, reason = engine.check_action("write_file")
        assert allowed is True
        assert reason == "no policy loaded"

    def test_loads_valid_file(self, policy_file):
        path = policy_file([{"type": "action", "name": "write_file", "effect": "deny"}])
        engine = PolicyEngine(path)
        assert engine.loaded is True
        assert engine.rule_count == 1

    def test_reload_updates_rules(self, policy_file, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps({"version": 1, "rules": [
                {"type": "action", "name": "write_file", "effect": "deny"}
            ]}),
            encoding="utf-8",
        )
        engine = PolicyEngine(str(path))
        assert engine.rule_count == 1

        # Update file and reload
        path.write_text(
            json.dumps({"version": 1, "rules": []}),
            encoding="utf-8",
        )
        engine.load()
        assert engine.rule_count == 0

    def test_invalid_json_retains_old_rules(self, policy_file, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps({"version": 1, "rules": [
                {"type": "action", "name": "write_file", "effect": "deny"}
            ]}),
            encoding="utf-8",
        )
        engine = PolicyEngine(str(path))
        assert engine.rule_count == 1

        path.write_text("{bad json", encoding="utf-8")
        result = engine.load()
        assert result is False
        assert engine.rule_count == 1  # unchanged

    def test_unknown_default_effect_falls_back_to_allow(self, policy_file):
        path = policy_file([], default_effect="unknown_value")
        engine = PolicyEngine(path)
        allowed, _ = engine.check_action("anything")
        assert allowed is True


class TestCheckAction:
    def test_deny_specific_action(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "write_file", "effect": "deny", "reason": "no writes"}
        ])
        engine = PolicyEngine(path)
        allowed, reason = engine.check_action("write_file")
        assert allowed is False
        assert reason == "no writes"

    def test_allow_action_passes(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "read_file", "effect": "allow"}
        ])
        engine = PolicyEngine(path)
        allowed, _ = engine.check_action("read_file")
        assert allowed is True

    def test_case_insensitive_action_name(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "WRITE_FILE", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        allowed, _ = engine.check_action("write_file")
        assert allowed is False

    def test_glob_action_name(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "write_*", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_action("write_file")[0] is False
        assert engine.check_action("write_clipboard")[0] is False
        assert engine.check_action("read_file")[0] is True

    def test_role_scoped_deny(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "write_file", "roles": ["viewer"], "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_action("write_file", role="viewer")[0] is False
        assert engine.check_action("write_file", role="admin")[0] is True

    def test_first_match_wins(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "write_file", "roles": ["admin"], "effect": "allow"},
            {"type": "action", "name": "write_file", "effect": "deny"},
        ])
        engine = PolicyEngine(path)
        assert engine.check_action("write_file", role="admin")[0] is True
        assert engine.check_action("write_file", role="viewer")[0] is False

    def test_no_matching_rule_uses_default_allow(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "other_action", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        allowed, _ = engine.check_action("write_file")
        assert allowed is True

    def test_default_deny_blocks_unmatched(self, policy_file):
        path = policy_file([], default_effect="deny")
        engine = PolicyEngine(path)
        allowed, reason = engine.check_action("anything")
        assert allowed is False
        assert "default" in reason

    def test_unmatched_action_type_not_matched(self, policy_file):
        path = policy_file([
            {"type": "endpoint", "method": "DELETE", "path": "/api/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        # action-type check should not match endpoint-type rules
        allowed, _ = engine.check_action("delete_endpoint")
        assert allowed is True


class TestCheckEndpoint:
    def test_deny_delete(self, policy_file):
        path = policy_file([
            {"type": "endpoint", "method": "DELETE", "path": "/api/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_endpoint("DELETE", "/api/users/1")[0] is False
        assert engine.check_endpoint("GET", "/api/users/1")[0] is True

    def test_wildcard_method(self, policy_file):
        path = policy_file([
            {"type": "endpoint", "method": "*", "path": "/admin/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_endpoint("GET", "/admin/settings")[0] is False
        assert engine.check_endpoint("POST", "/admin/users")[0] is False

    def test_role_scoped_endpoint(self, policy_file):
        path = policy_file([
            {
                "type": "endpoint", "method": "DELETE", "path": "/api/**",
                "roles": ["viewer"], "effect": "deny"
            }
        ])
        engine = PolicyEngine(path)
        assert engine.check_endpoint("DELETE", "/api/x", role="viewer")[0] is False
        assert engine.check_endpoint("DELETE", "/api/x", role="admin")[0] is True

    def test_method_case_insensitive(self, policy_file):
        path = policy_file([
            {"type": "endpoint", "method": "delete", "path": "/api/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_endpoint("DELETE", "/api/x")[0] is False


class TestCheckFilePath:
    def test_deny_etc(self, policy_file):
        path = policy_file([
            {"type": "file_path", "pattern": "/etc/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_file_path("/etc/passwd")[0] is False
        assert engine.check_file_path("/tmp/file.txt")[0] is True

    def test_exact_path_match(self, policy_file):
        path = policy_file([
            {"type": "file_path", "pattern": "/tmp/secret.txt", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_file_path("/tmp/secret.txt")[0] is False
        assert engine.check_file_path("/tmp/other.txt")[0] is True

    def test_role_scoped_file_path(self, policy_file):
        path = policy_file([
            {"type": "file_path", "pattern": "/var/**", "roles": ["viewer"], "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        assert engine.check_file_path("/var/log/syslog", role="viewer")[0] is False
        assert engine.check_file_path("/var/log/syslog", role="admin")[0] is True


class TestAssertHelpers:
    def test_assert_action_passes_silently(self, policy_file):
        path = policy_file([])
        engine = PolicyEngine(path)
        engine.assert_action("anything")  # should not raise

    def test_assert_action_raises_on_deny(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "write_file", "effect": "deny", "reason": "blocked"}
        ])
        engine = PolicyEngine(path)
        with pytest.raises(PolicyViolation) as exc_info:
            engine.assert_action("write_file")
        assert "write_file" in str(exc_info.value)
        assert exc_info.value.reason == "blocked"

    def test_assert_endpoint_raises(self, policy_file):
        path = policy_file([
            {"type": "endpoint", "method": "DELETE", "path": "/api/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        with pytest.raises(PolicyViolation):
            engine.assert_endpoint("DELETE", "/api/x")

    def test_assert_file_path_raises(self, policy_file):
        path = policy_file([
            {"type": "file_path", "pattern": "/etc/**", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        with pytest.raises(PolicyViolation):
            engine.assert_file_path("/etc/hosts")

    def test_policy_violation_attributes(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "rm_rf", "effect": "deny", "reason": "too dangerous"}
        ])
        engine = PolicyEngine(path)
        with pytest.raises(PolicyViolation) as exc_info:
            engine.assert_action("rm_rf")
        err = exc_info.value
        assert err.action == "rm_rf"
        assert err.reason == "too dangerous"


class TestInspection:
    def test_summary_no_policy(self, tmp_path):
        engine = PolicyEngine(str(tmp_path / "missing.json"))
        s = engine.summary()
        assert "no policy loaded" in s

    def test_summary_with_rules(self, policy_file):
        path = policy_file([{"type": "action", "name": "x", "effect": "deny"}])
        engine = PolicyEngine(path)
        s = engine.summary()
        assert "1 rule" in s
        assert "default=allow" in s

    def test_get_rules_is_copy(self, policy_file):
        path = policy_file([{"type": "action", "name": "x", "effect": "deny"}])
        engine = PolicyEngine(path)
        rules = engine.get_rules()
        rules.clear()
        assert engine.rule_count == 1


class TestThreadSafety:
    def test_concurrent_checks(self, policy_file):
        path = policy_file([
            {"type": "action", "name": "write_file", "effect": "deny"}
        ])
        engine = PolicyEngine(path)
        results = []
        errors = []

        def check():
            try:
                allowed, _ = engine.check_action("write_file")
                results.append(allowed)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=check) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert all(r is False for r in results)
        assert len(results) == 50


class TestGetDefaultEngine:
    def test_returns_singleton(self, tmp_path):
        import core.policy as policy_mod

        # Reset singleton so test isolation works
        policy_mod._default_engine = None
        path = str(tmp_path / "policy.json")
        e1 = get_default_engine(path)
        e2 = get_default_engine(path)
        assert e1 is e2
        policy_mod._default_engine = None  # cleanup


class TestRealPolicyFile:
    """Smoke test that ships with config/policy.json parses cleanly."""

    def test_example_policy_loads(self):
        engine = PolicyEngine("config/policy.json")
        # The example policy has write_file deny for viewer/operator
        allowed, reason = engine.check_action("write_file", role="viewer")
        assert allowed is False
        assert reason  # has a reason string

        # Admins are not in the deny list so fall through to default (allow)
        allowed, _ = engine.check_action("write_file", role="admin")
        assert allowed is True

        # /etc/ is blocked for everyone
        allowed, _ = engine.check_file_path("/etc/passwd")
        assert allowed is False

        # DELETE blocked for viewers
        allowed, _ = engine.check_endpoint("DELETE", "/api/users/1", role="viewer")
        assert allowed is False

        # DELETE allowed for admins (no rule matches)
        allowed, _ = engine.check_endpoint("DELETE", "/api/users/1", role="admin")
        assert allowed is True
