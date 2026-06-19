"""Sentinel Desktop v19 — Secrets Vault Broker.

Wraps the existing ``CredentialVault`` (DPAPI / XOR encryption) and
adds two enterprise-grade layers:

1. **Policy enforcement** — ``PolicyEngine`` checks whether the caller's
   role is permitted to read or write the requested secret key.  If no
   policy file is loaded all operations pass through unchanged.

2. **Audit logging** — every mutating operation (put / delete / rotate)
   and every read (get) is recorded in an ``AuditChain`` so that vault
   access can be forensically verified later.

Secrets are namespaced as ``<category>/<name>`` in the underlying
``CredentialVault`` (forward-slash is the separator).  The ``category``
defaults to ``"default"``.  Callers that don't care about namespacing can
just pass a plain name and leave the category at its default.

Thread safety
-------------
``SecretsVault`` is thread-safe.  The underlying ``CredentialVault`` is
itself guarded by an ``RLock``; policy and audit calls are also
thread-safe.

Usage::

    vault = SecretsVault()
    vault.put("openai_key", "sk-...", category="api")
    key = vault.get("openai_key", category="api", role="admin")
    vault.rotate("openai_key", "sk-new-...", category="api", role="admin")
    vault.delete("openai_key", category="api", role="admin")
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from core.audit_chain import AuditChain
from core.encryption import CredentialVault
from core.policy import PolicyEngine, get_default_engine

logger = logging.getLogger(__name__)

_DEFAULT_VAULT_PATH = "config/vault.json"
_DEFAULT_AUDIT_PATH = "logs/secrets_audit.jsonl"
_DEFAULT_CATEGORY = "default"
_SEP = "/"


def _make_key(name: str, category: str) -> str:
    """Compose the storage key from *category* and *name*."""
    cat = (category or _DEFAULT_CATEGORY).strip(_SEP)
    return f"{cat}{_SEP}{name}"


class SecretNotFound(KeyError):
    """Raised when a requested secret does not exist in the vault."""


class SecretsVault:
    """Enterprise secrets broker with policy enforcement and audit logging.

    Args:
        vault_path: Path to the ``CredentialVault`` JSON file.
        policy_engine: ``PolicyEngine`` instance used for access checks.
            Pass ``None`` to skip policy enforcement (allow-all).
        audit_chain: ``AuditChain`` instance for immutable event logging.
            Pass ``None`` to disable audit logging.
    """

    def __init__(
        self,
        vault_path: str = _DEFAULT_VAULT_PATH,
        policy_engine: PolicyEngine | None = None,
        audit_chain: AuditChain | None = None,
    ) -> None:
        self._vault = CredentialVault(vault_path)
        self._policy = policy_engine
        self._audit = audit_chain
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_policy(self, action: str, key: str, role: str | None) -> None:
        """Run a file_path policy check for *key* if a policy engine is set.

        Secrets use the ``file_path`` rule type so operators can write
        patterns like ``/secret/api/**`` or ``/secret/ssh/**`` in
        ``config/policy.json``.  The virtual path is
        ``/secret/<category>/<name>``.

        Raises:
            PolicyViolation: If the policy engine denies the operation.
        """
        if self._policy is None:
            return
        virtual_path = f"/secret/{key}"
        self._policy.assert_file_path(virtual_path, role=role)

    def _log(self, event_type: str, actor: str, data: dict[str, Any]) -> None:
        """Append an audit entry if an audit chain is configured."""
        if self._audit is None:
            return
        try:
            self._audit.append(event_type, actor=actor, data=data)
        except Exception as exc:  # never let audit failure crash the caller
            logger.error("Audit write failed: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(
        self,
        name: str,
        value: str,
        category: str = _DEFAULT_CATEGORY,
        role: str | None = None,
        actor: str = "system",
    ) -> None:
        """Store or overwrite a secret.

        Args:
            name: Secret identifier within *category*.
            value: Plaintext secret value to encrypt and store.
            category: Namespace / grouping (e.g. ``"api"``, ``"ssh"``).
            role: Caller's role for policy enforcement.
            actor: Human-readable identity for the audit log.

        Raises:
            PolicyViolation: If policy denies the write.
            RuntimeError: If the underlying vault fails to write.
        """
        key = _make_key(name, category)
        self._check_policy("put", key, role)
        with self._lock:
            ok = self._vault.store(key, value)
        if not ok:
            raise RuntimeError(f"Vault store failed for '{key}'")
        self._log("secret_put", actor, {"key": key, "category": category})

    def get(
        self,
        name: str,
        category: str = _DEFAULT_CATEGORY,
        role: str | None = None,
        actor: str = "system",
    ) -> str:
        """Retrieve a secret value.

        Args:
            name: Secret identifier.
            category: Secret namespace.
            role: Caller's role for policy enforcement.
            actor: Identity for the audit log.

        Returns:
            Decrypted secret value.

        Raises:
            PolicyViolation: If policy denies the read.
            SecretNotFound: If no such secret exists.
        """
        key = _make_key(name, category)
        self._check_policy("get", key, role)
        with self._lock:
            value = self._vault.retrieve(key)
        if value is None:
            raise SecretNotFound(f"Secret '{key}' not found in vault")
        self._log("secret_get", actor, {"key": key, "category": category})
        return value

    def delete(
        self,
        name: str,
        category: str = _DEFAULT_CATEGORY,
        role: str | None = None,
        actor: str = "system",
    ) -> bool:
        """Delete a secret from the vault.

        Args:
            name: Secret identifier.
            category: Secret namespace.
            role: Caller's role for policy enforcement.
            actor: Identity for the audit log.

        Returns:
            True if the secret existed and was deleted; False if not found.

        Raises:
            PolicyViolation: If policy denies the deletion.
        """
        key = _make_key(name, category)
        self._check_policy("delete", key, role)
        with self._lock:
            deleted = self._vault.delete(key)
        if deleted:
            self._log("secret_delete", actor, {"key": key, "category": category})
        return deleted

    def rotate(
        self,
        name: str,
        new_value: str,
        category: str = _DEFAULT_CATEGORY,
        role: str | None = None,
        actor: str = "system",
    ) -> None:
        """Replace the value of an existing secret.

        Semantically equivalent to ``put()``, but the audit event is
        ``"secret_rotate"`` so rotation is distinguishable from initial
        storage.

        Args:
            name: Secret identifier.
            new_value: New plaintext secret value.
            category: Secret namespace.
            role: Caller's role for policy enforcement.
            actor: Identity for the audit log.

        Raises:
            PolicyViolation: If policy denies the write.
            SecretNotFound: If the secret does not already exist.
            RuntimeError: If the vault store fails.
        """
        key = _make_key(name, category)
        self._check_policy("rotate", key, role)
        with self._lock:
            if not self._vault.has_key(key):
                raise SecretNotFound(f"Secret '{key}' not found — use put() for new secrets")
            ok = self._vault.store(key, new_value)
        if not ok:
            raise RuntimeError(f"Vault store failed during rotation of '{key}'")
        self._log("secret_rotate", actor, {"key": key, "category": category})

    def exists(
        self,
        name: str,
        category: str = _DEFAULT_CATEGORY,
    ) -> bool:
        """Return True if *name* exists in *category*.

        Does not apply policy checks or emit audit events (existence
        checks are non-sensitive by convention).

        Args:
            name: Secret identifier.
            category: Secret namespace.

        Returns:
            bool: Whether the secret is stored.
        """
        key = _make_key(name, category)
        with self._lock:
            return self._vault.has_key(key)

    def list_secrets(self, category: str = "") -> list[str]:
        """List stored secret names, optionally filtered by *category*.

        Args:
            category: If provided, only return secrets in this namespace.
                Pass an empty string (default) to list all secrets.

        Returns:
            List of ``"<category>/<name>"`` strings.
        """
        with self._lock:
            all_keys: list[str] = self._vault.list_keys()
        if category:
            prefix = (category.strip(_SEP)) + _SEP
            return [k for k in all_keys if k.startswith(prefix)]
        return list(all_keys)

    def summary(self) -> str:
        """Return a brief human-readable description of vault state."""
        secrets = self.list_secrets()
        policy_status = "policy=none" if self._policy is None else "policy=active"
        audit_status = "audit=none" if self._audit is None else "audit=active"
        return (
            f"SecretsVault({len(secrets)} secret(s), {policy_status}, {audit_status})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_vault: SecretsVault | None = None
_vault_lock = threading.Lock()


def get_default_vault(
    vault_path: str = _DEFAULT_VAULT_PATH,
    audit_path: str = _DEFAULT_AUDIT_PATH,
) -> SecretsVault:
    """Return the process-wide ``SecretsVault`` singleton.

    On first call, creates a ``SecretsVault`` wired to the default
    ``PolicyEngine`` singleton and a dedicated ``AuditChain`` at
    *audit_path*.

    Args:
        vault_path: Vault JSON path (used only on first call).
        audit_path: Audit log path (used only on first call).

    Returns:
        SecretsVault: The shared vault instance.
    """
    global _default_vault  # noqa: PLW0603
    with _vault_lock:
        if _default_vault is None:
            _default_vault = SecretsVault(
                vault_path=vault_path,
                policy_engine=get_default_engine(),
                audit_chain=AuditChain(audit_path),
            )
        return _default_vault
