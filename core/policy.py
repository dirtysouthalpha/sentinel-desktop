"""Sentinel Desktop v19 — Declarative Policy Guardrails.

Operator-editable allow/deny rules over actions, API endpoints, and file
paths. Rules are evaluated top-to-bottom; first match wins. When no rule
matches the configured *default_effect* applies (``"allow"`` by default for
backwards compatibility).

Policy file format (``config/policy.json``)::

    {
        "version": 1,
        "default_effect": "allow",
        "rules": [
            {
                "type": "action",
                "name": "write_file",
                "effect": "deny",
                "reason": "File writes disabled by operator policy"
            },
            {
                "type": "action",
                "name": "write_file",
                "roles": ["admin"],
                "effect": "allow"
            },
            {
                "type": "file_path",
                "pattern": "/etc/**",
                "effect": "deny",
                "reason": "System config directories are off-limits"
            },
            {
                "type": "endpoint",
                "method": "DELETE",
                "path": "/api/**",
                "roles": ["viewer", "operator"],
                "effect": "deny",
                "reason": "Only admins may use DELETE"
            }
        ]
    }

Rule fields
-----------
``type``
    ``"action"`` | ``"endpoint"`` | ``"file_path"``
``effect``
    ``"allow"`` | ``"deny"``
``roles``
    Optional list of role names this rule applies to. If omitted the rule
    applies to *all* roles.
``reason``
    Optional human-readable explanation included in violation messages.

Pattern matching
----------------
* **action** rules match on the literal action name (case-insensitive).
* **file_path** rules use ``fnmatch`` glob patterns (``*`` = any chars except
  ``/``, ``**`` = any path segment sequence).
* **endpoint** rules match on HTTP method (case-insensitive) and path using
  the same glob patterns.

Thread safety
-------------
``PolicyEngine`` is read-heavy and write-rarely. ``load()`` replaces the rule
list atomically under a lock so concurrent ``check_*`` calls are safe.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_POLICY_PATH: str = "config/policy.json"
_ALLOW = "allow"
_DENY = "deny"


class PolicyViolationError(Exception):
    """Raised by assert_* helpers when a policy check fails.

    Attributes:
        action: The action/endpoint/path that was denied.
        reason: Human-readable explanation from the matching rule.
    """

    def __init__(self, message: str, action: str = "", reason: str = "") -> None:
        super().__init__(message)
        self.action = action
        self.reason = reason


def _match_segments(pat_parts: list[str], val_parts: list[str]) -> bool:
    """Recursive segment-by-segment glob matcher.

    ``*`` in a segment matches any chars within that segment only.
    ``**`` as a whole segment matches zero or more path segments.
    """
    if not pat_parts and not val_parts:
        return True
    if not pat_parts:
        return False
    head = pat_parts[0]
    rest_pat = pat_parts[1:]
    if head == "**":
        for i in range(len(val_parts) + 1):
            if _match_segments(rest_pat, val_parts[i:]):
                return True
        return False
    if not val_parts:
        return False
    if fnmatch.fnmatch(val_parts[0], head):
        return _match_segments(rest_pat, val_parts[1:])
    return False


def _fnmatch_path(pattern: str, value: str) -> bool:
    """Match *value* against *pattern* with shell-like path glob semantics.

    * ``*`` matches any chars within a single path segment (does **not** cross
      ``/``).
    * ``**`` as a whole path segment matches zero or more path segments
      (including ``/``).

    For patterns that contain no ``/``, falls back to plain ``fnmatch`` so
    that action-name patterns like ``write_*`` work as expected.
    """
    if "/" not in pattern:
        return fnmatch.fnmatch(value, pattern)
    return _match_segments(pattern.split("/"), value.split("/"))


def _role_matches(rule_roles: list[str] | None, role: str | None) -> bool:
    """Return True if *role* is covered by *rule_roles*.

    If *rule_roles* is None or empty the rule applies to all roles.
    If *role* is None it is treated as an anonymous / no-role caller.
    """
    if not rule_roles:
        return True
    if role is None:
        return False
    return role.lower() in {r.lower() for r in rule_roles}


class PolicyEngine:
    """Evaluate requests against operator-defined allow/deny rules.

    Typical usage::

        engine = PolicyEngine("config/policy.json")
        allowed, reason = engine.check_action("write_file", role="operator")
        if not allowed:
            raise PolicyViolationError(...)

        # Or use the assert helper (raises on deny):
        engine.assert_action("delete_file", role="viewer")

    The engine is a no-op when the policy file does not exist: all checks
    return ``(True, "no policy loaded")`` so existing deployments are
    unaffected by default.
    """

    def __init__(self, policy_path: str = DEFAULT_POLICY_PATH) -> None:
        """Initialise and load policy rules from *policy_path*.

        Args:
            policy_path: Path to the JSON policy file. Missing file is
                silently ignored (all checks pass).
        """
        self._lock = threading.RLock()
        self.policy_path = Path(policy_path)
        self._rules: list[dict[str, Any]] = []
        self._default_effect: str = _ALLOW
        self._loaded: bool = False
        self.load()

    # ------------------------------------------------------------------
    # Load / reload
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load (or reload) rules from the policy file.

        Returns:
            bool: True if the file was found and parsed, False if missing or
            invalid.  On failure the previous rule set is retained.
        """
        if not self.policy_path.exists():
            logger.debug("Policy file not found: %s — all checks will pass", self.policy_path)
            with self._lock:
                self._loaded = False
            return False

        try:
            with open(self.policy_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read policy file %s: %s", self.policy_path, exc)
            return False

        rules = data.get("rules", [])
        default = data.get("default_effect", _ALLOW).lower()
        if default not in (_ALLOW, _DENY):
            logger.warning("Unknown default_effect %r — falling back to 'allow'", default)
            default = _ALLOW

        with self._lock:
            self._rules = rules
            self._default_effect = default
            self._loaded = True

        logger.info(
            "Policy loaded from %s: %d rule(s), default=%s",
            self.policy_path,
            len(rules),
            default,
        )
        return True

    @property
    def loaded(self) -> bool:
        """True if a policy file has been successfully loaded."""
        with self._lock:
            return self._loaded

    @property
    def rule_count(self) -> int:
        """Number of rules currently loaded."""
        with self._lock:
            return len(self._rules)

    # ------------------------------------------------------------------
    # Internal evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        rule_type: str,
        match_fn: Any,
        role: str | None,
    ) -> tuple[bool, str]:
        """Walk the rule list and return the first match result.

        Args:
            rule_type: ``"action"`` | ``"endpoint"`` | ``"file_path"``
            match_fn: Callable(rule) → bool — returns True if this rule is
                structurally applicable to the current request.
            role: The caller's role string (``None`` for anonymous).

        Returns:
            (allowed: bool, reason: str) — reason is empty on allow.
        """
        with self._lock:
            if not self._loaded:
                return True, "no policy loaded"
            rules = list(self._rules)
            default = self._default_effect

        for rule in rules:
            if rule.get("type") != rule_type:
                continue
            if not match_fn(rule):
                continue
            if not _role_matches(rule.get("roles"), role):
                continue

            effect = rule.get("effect", _ALLOW).lower()
            reason = rule.get("reason", "")
            if effect == _DENY:
                return False, reason
            return True, ""

        # No rule matched — apply default
        if default == _DENY:
            return False, "denied by default policy"
        return True, ""

    # ------------------------------------------------------------------
    # Public check API
    # ------------------------------------------------------------------

    def check_action(
        self,
        action_name: str,
        role: str | None = None,
    ) -> tuple[bool, str]:
        """Check whether *action_name* is permitted for *role*.

        Args:
            action_name: The action key (e.g. ``"write_file"``).
            role: The caller's role, or ``None`` for anonymous callers.

        Returns:
            (allowed: bool, reason: str)
        """
        name_lower = action_name.lower()

        def match(rule: dict[str, Any]) -> bool:
            pattern = rule.get("name", "")
            return _fnmatch_path(pattern.lower(), name_lower)

        return self._evaluate("action", match, role)

    def check_endpoint(
        self,
        method: str,
        path: str,
        role: str | None = None,
    ) -> tuple[bool, str]:
        """Check whether an HTTP *method* + *path* combination is permitted.

        Args:
            method: HTTP method (``"GET"``, ``"POST"``, etc.).
            path: Request path (e.g. ``"/api/goal"``).
            role: The caller's role.

        Returns:
            (allowed: bool, reason: str)
        """
        method_lower = method.lower()

        def match(rule: dict[str, Any]) -> bool:
            rule_method = rule.get("method", "*").lower()
            rule_path = rule.get("path", "**")
            method_ok = rule_method in ("*", method_lower)
            path_ok = _fnmatch_path(rule_path, path)
            return method_ok and path_ok

        return self._evaluate("endpoint", match, role)

    def check_file_path(
        self,
        path: str,
        role: str | None = None,
    ) -> tuple[bool, str]:
        """Check whether access to file *path* is permitted.

        Args:
            path: File system path being accessed.
            role: The caller's role.

        Returns:
            (allowed: bool, reason: str)
        """

        def match(rule: dict[str, Any]) -> bool:
            pattern = rule.get("pattern", "**")
            return _fnmatch_path(pattern, path)

        return self._evaluate("file_path", match, role)

    # ------------------------------------------------------------------
    # Assert helpers (raise on deny)
    # ------------------------------------------------------------------

    def assert_action(self, action_name: str, role: str | None = None) -> None:
        """Like ``check_action`` but raises ``PolicyViolationError`` on deny.

        Args:
            action_name: The action key to check.
            role: The caller's role.

        Raises:
            PolicyViolationError: If the action is denied by policy.
        """
        allowed, reason = self.check_action(action_name, role)
        if not allowed:
            msg = f"Action '{action_name}' denied by policy"
            if reason:
                msg = f"{msg}: {reason}"
            raise PolicyViolationError(msg, action=action_name, reason=reason)

    def assert_endpoint(self, method: str, path: str, role: str | None = None) -> None:
        """Like ``check_endpoint`` but raises ``PolicyViolationError`` on deny.

        Args:
            method: HTTP method.
            path: Request path.
            role: The caller's role.

        Raises:
            PolicyViolationError: If the endpoint call is denied by policy.
        """
        allowed, reason = self.check_endpoint(method, path, role)
        if not allowed:
            msg = f"Endpoint '{method} {path}' denied by policy"
            if reason:
                msg = f"{msg}: {reason}"
            raise PolicyViolationError(msg, action=f"{method} {path}", reason=reason)

    def assert_file_path(self, path: str, role: str | None = None) -> None:
        """Like ``check_file_path`` but raises ``PolicyViolationError`` on deny.

        Args:
            path: File path to check.
            role: The caller's role.

        Raises:
            PolicyViolationError: If file path access is denied by policy.
        """
        allowed, reason = self.check_file_path(path, role)
        if not allowed:
            msg = f"File path '{path}' denied by policy"
            if reason:
                msg = f"{msg}: {reason}"
            raise PolicyViolationError(msg, action=path, reason=reason)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get_rules(self) -> list[dict[str, Any]]:
        """Return a copy of the loaded rules list."""
        with self._lock:
            return list(self._rules)

    def summary(self) -> str:
        """Return a brief human-readable summary of the loaded policy."""
        with self._lock:
            loaded = self._loaded
            count = len(self._rules)
            default = self._default_effect
            path = str(self.policy_path)

        if not loaded:
            return f"PolicyEngine: no policy loaded (file: {path})"
        return f"PolicyEngine: {count} rule(s) from {path}, default={default}"


# ---------------------------------------------------------------------------
# Module-level singleton helper
# ---------------------------------------------------------------------------

_default_engine: PolicyEngine | None = None
_engine_lock = threading.Lock()


def get_default_engine(policy_path: str = DEFAULT_POLICY_PATH) -> PolicyEngine:
    """Return the process-wide ``PolicyEngine`` singleton.

    The engine is created lazily on first call and reused thereafter.
    Call ``get_default_engine().load()`` to reload after editing the policy
    file.

    Args:
        policy_path: Path used only on first call (ignored on subsequent calls).

    Returns:
        PolicyEngine: The shared engine instance.
    """
    global _default_engine  # noqa: PLW0603
    with _engine_lock:
        if _default_engine is None:
            _default_engine = PolicyEngine(policy_path)
        return _default_engine
