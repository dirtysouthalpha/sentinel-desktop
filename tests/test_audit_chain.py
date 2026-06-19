"""Tests for core/audit_chain.py — Tamper-Evident Hash-Chained Audit Log (v19)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from core.audit_chain import (
    GENESIS_HASH,
    AuditChain,
    _canonical,
    _compute_entry_hash,
    _sha256,
)

# ---------------------------------------------------------------------------
# Helper / unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_canonical_deterministic(self):
        obj = {"b": 2, "a": 1}
        assert _canonical(obj) == _canonical({"a": 1, "b": 2})

    def test_canonical_no_whitespace(self):
        out = _canonical({"key": "value"}).decode()
        assert " " not in out

    def test_sha256_length(self):
        assert len(_sha256(b"hello")) == 64

    def test_sha256_known_value(self):
        # SHA-256 of empty bytes is well-known
        assert _sha256(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_compute_entry_hash_excludes_entry_hash(self):
        entry = {
            "seq": 1,
            "timestamp": "2026-01-01T00:00:00.000000",
            "event_type": "test",
            "actor": "tester",
            "data": {},
            "prev_hash": GENESIS_HASH,
        }
        h1 = _compute_entry_hash(entry)
        entry_with_hash = dict(entry, entry_hash="some_hash")
        h2 = _compute_entry_hash(entry_with_hash)
        assert h1 == h2, "entry_hash field must be excluded from hash computation"

    def test_compute_entry_hash_sensitivity(self):
        entry = {
            "seq": 1,
            "timestamp": "2026-01-01T00:00:00.000000",
            "event_type": "test",
            "actor": "tester",
            "data": {},
            "prev_hash": GENESIS_HASH,
        }
        h1 = _compute_entry_hash(entry)
        entry["data"] = {"extra": "field"}
        h2 = _compute_entry_hash(entry)
        assert h1 != h2


# ---------------------------------------------------------------------------
# AuditChain core functionality
# ---------------------------------------------------------------------------


@pytest.fixture
def chain_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


@pytest.fixture
def chain(chain_path: Path) -> AuditChain:
    return AuditChain(chain_path)


class TestAuditChainAppend:
    def test_append_returns_entry(self, chain):
        entry = chain.append("login", actor="admin", data={"ip": "127.0.0.1"})
        assert entry["seq"] == 1
        assert entry["event_type"] == "login"
        assert entry["actor"] == "admin"
        assert entry["data"]["ip"] == "127.0.0.1"
        assert "entry_hash" in entry
        assert "prev_hash" in entry
        assert "timestamp" in entry

    def test_first_entry_prev_hash_is_genesis(self, chain):
        entry = chain.append("test")
        assert entry["prev_hash"] == GENESIS_HASH

    def test_second_entry_prev_hash_is_first_entry_hash(self, chain):
        e1 = chain.append("first")
        e2 = chain.append("second")
        assert e2["prev_hash"] == e1["entry_hash"]

    def test_sequence_increments(self, chain):
        e1 = chain.append("a")
        e2 = chain.append("b")
        e3 = chain.append("c")
        assert e1["seq"] == 1
        assert e2["seq"] == 2
        assert e3["seq"] == 3

    def test_empty_data_defaults(self, chain):
        entry = chain.append("event")
        assert entry["data"] == {}

    def test_tip_hash_updates(self, chain):
        assert chain.tip_hash == GENESIS_HASH
        e1 = chain.append("x")
        assert chain.tip_hash == e1["entry_hash"]
        e2 = chain.append("y")
        assert chain.tip_hash == e2["entry_hash"]

    def test_length_increments(self, chain):
        assert chain.length == 0
        chain.append("a")
        assert chain.length == 1
        chain.append("b")
        assert chain.length == 2


class TestAuditChainPersistence:
    def test_written_to_file(self, chain, chain_path):
        chain.append("login")
        assert chain_path.exists()
        lines = chain_path.read_text().splitlines()
        assert len(lines) == 1

    def test_multiple_entries_multiple_lines(self, chain, chain_path):
        for i in range(5):
            chain.append(f"event_{i}")
        lines = chain_path.read_text().splitlines()
        assert len(lines) == 5

    def test_each_line_is_valid_json(self, chain, chain_path):
        for i in range(3):
            chain.append("event", data={"i": i})
        for line in chain_path.read_text().splitlines():
            obj = json.loads(line)
            assert "entry_hash" in obj

    def test_reload_resumes_chain(self, chain_path):
        c1 = AuditChain(chain_path)
        e1 = c1.append("first")

        c2 = AuditChain(chain_path)  # reload
        e2 = c2.append("second")
        assert e2["prev_hash"] == e1["entry_hash"]
        assert e2["seq"] == 2

    def test_new_chain_no_file(self, chain_path):
        c = AuditChain(chain_path)
        assert c.length == 0
        assert c.tip_hash == GENESIS_HASH

    def test_parent_dirs_created(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "audit.jsonl"
        c = AuditChain(path)
        c.append("event")
        assert path.exists()


class TestAuditChainEntries:
    def test_entries_empty_when_no_file(self, chain_path):
        c = AuditChain(chain_path)
        assert c.entries() == []

    def test_entries_returns_all_in_order(self, chain):
        chain.append("a")
        chain.append("b")
        chain.append("c")
        entries = chain.entries()
        assert len(entries) == 3
        assert [e["event_type"] for e in entries] == ["a", "b", "c"]

    def test_entries_includes_all_fields(self, chain):
        chain.append("login", actor="bob", data={"key": "val"})
        e = chain.entries()[0]
        for field in ("seq", "timestamp", "event_type", "actor", "data", "prev_hash", "entry_hash"):
            assert field in e


# ---------------------------------------------------------------------------
# Verify (integrity checks)
# ---------------------------------------------------------------------------


class TestAuditChainVerify:
    def test_empty_chain_verifies_ok(self, chain):
        ok, bad = chain.verify()
        assert ok is True
        assert bad == []

    def test_clean_chain_verifies_ok(self, chain):
        for i in range(5):
            chain.append("event", data={"i": i})
        ok, bad = chain.verify()
        assert ok is True
        assert bad == []

    def test_tampered_data_detected(self, chain, chain_path):
        chain.append("login")
        chain.append("action", data={"target": "safe"})

        # Tamper with the second entry's data
        lines = chain_path.read_text().splitlines()
        entry2 = json.loads(lines[1])
        entry2["data"]["target"] = "evil"
        lines[1] = json.dumps(entry2)
        chain_path.write_text("\n".join(lines) + "\n")

        ok, bad = AuditChain(chain_path).verify()
        assert ok is False
        assert 2 in bad

    def test_tampered_hash_detected(self, chain, chain_path):
        chain.append("login")
        lines = chain_path.read_text().splitlines()
        entry1 = json.loads(lines[0])
        entry1["entry_hash"] = "a" * 64
        lines[0] = json.dumps(entry1)
        chain_path.write_text("\n".join(lines) + "\n")

        ok, bad = AuditChain(chain_path).verify()
        assert ok is False
        assert 1 in bad

    def test_entry_insertion_detected(self, chain, chain_path):
        """Inserting a new entry breaks prev_hash chain for subsequent entries."""
        e1 = chain.append("original_first")
        e2 = chain.append("original_second")

        # Insert a fake entry between line 0 and line 1 by constructing an
        # entry that chains correctly from e1 but breaks e2's prev_hash check.
        lines = chain_path.read_text().splitlines()
        fake = {
            "seq": 99,
            "timestamp": "2000-01-01T00:00:00.000000",
            "event_type": "injected",
            "actor": "attacker",
            "data": {},
            "prev_hash": e1["entry_hash"],
        }
        fake["entry_hash"] = _compute_entry_hash(fake)
        # Insert after line 0
        lines.insert(1, json.dumps(fake))
        chain_path.write_text("\n".join(lines) + "\n")

        # The third line (original_second) now has the wrong prev_hash
        ok, bad = AuditChain(chain_path).verify()
        assert ok is False
        assert e2["seq"] in bad

    def test_entry_deletion_detected(self, chain, chain_path):
        """Deleting an entry breaks the prev_hash chain of the next entry."""
        chain.append("a")
        chain.append("b")
        chain.append("c")

        lines = chain_path.read_text().splitlines()
        # Remove the second line
        del lines[1]
        chain_path.write_text("\n".join(lines) + "\n")

        ok, bad = AuditChain(chain_path).verify()
        assert ok is False

    def test_actor_tampering_detected(self, chain, chain_path):
        chain.append("sudo", actor="admin")
        lines = chain_path.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["actor"] = "anonymous"
        lines[0] = json.dumps(entry)
        chain_path.write_text("\n".join(lines) + "\n")

        ok, bad = AuditChain(chain_path).verify()
        assert ok is False
        assert 1 in bad

    def test_reload_and_verify(self, chain_path):
        c1 = AuditChain(chain_path)
        for i in range(10):
            c1.append("event", data={"i": i})

        c2 = AuditChain(chain_path)
        ok, bad = c2.verify()
        assert ok is True
        assert bad == []


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestAuditChainThreadSafety:
    def test_concurrent_appends(self, chain):
        errors = []

        def append_many():
            try:
                for _ in range(20):
                    chain.append("concurrent_event")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=append_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert chain.length == 100
        ok, bad = chain.verify()
        assert ok is True, f"Chain broken after concurrent writes: bad seqs={bad}"


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------


class TestAuditChainInspection:
    def test_summary_empty(self, chain):
        s = chain.summary()
        assert "0 entries" in s

    def test_summary_with_entries(self, chain):
        chain.append("a")
        chain.append("b")
        s = chain.summary()
        assert "2 entries" in s
