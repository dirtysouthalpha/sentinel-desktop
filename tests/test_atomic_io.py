"""Tests for core.atomic_io — crash-safe, owner-only writes."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core.atomic_io import atomic_write_bytes, atomic_write_text


def test_writes_content(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_text(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "nested" / "deep" / "out.txt"
    atomic_write_text(target, "hi")
    assert target.read_text() == "hi"


def test_overwrites_existing(tmp_path: Path):
    target = tmp_path / "out.txt"
    target.write_text("old contents that are longer")
    atomic_write_text(target, "new")
    assert target.read_text() == "new"


def test_original_preserved_when_write_fails(tmp_path: Path):
    """A failure mid-write must leave the existing file intact — the whole
    point for the credential store."""
    target = tmp_path / "vault.json"
    target.write_text("ORIGINAL")

    # Fail during the temp-file write, after the original already exists.
    with patch("os.fsync", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            atomic_write_text(target, "REPLACEMENT")

    assert target.read_text() == "ORIGINAL"  # untouched


def test_no_temp_file_left_behind_on_failure(tmp_path: Path):
    target = tmp_path / "out.txt"
    with patch("os.fsync", side_effect=OSError("boom")):
        with pytest.raises(OSError):
            atomic_write_text(target, "x")
    # Only the (absent) target should be considered; no .tmp leftovers.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_bytes_roundtrip(tmp_path: Path):
    target = tmp_path / "blob.bin"
    payload = bytes(range(256))
    atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_owner_only_perms_on_posix(tmp_path: Path):
    target = tmp_path / "secret.json"
    atomic_write_text(target, "s", mode=0o600)
    assert (os.stat(target).st_mode & 0o777) == 0o600
