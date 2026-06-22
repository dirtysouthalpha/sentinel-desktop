"""Tests for scripts/pre-push-gate.sh — the pre-push gate that blocks pushes to
main when ruff fails or a test file fails to import.

The gate is a shell script invoked by git as a pre-push hook. These tests drive
it directly by piping a fake stdin line (mimicking what git passes) and asserting
on exit code + stderr. No live `git push` is performed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parent.parent / "scripts" / "pre-push-gate.sh"


def _run_gate(cwd: Path, remote_ref: str = "refs/heads/main", skip: bool = False,
              env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke the gate script with a fake git stdin line.

    Args:
        cwd: Directory to run the gate in (acts as the repo root).
        remote_ref: The remote ref git would report (e.g. refs/heads/main).
        skip: If True, set SKIP_GATE=1.
        env_extra: Additional env vars.

    Returns:
        The completed process (exit code in .returncode, stderr in .stderr).
    """
    env = os.environ.copy()
    env["SKIP_GATE"] = "1" if skip else "0"
    if env_extra:
        env.update(env_extra)
    # git passes: <local ref> <local sha> <remote ref> <remote sha>
    fake_stdin = f"refs/heads/main 0000000000000000000000000000000000000000 {remote_ref} 1111111111111111111111111111111111111111\n"
    return subprocess.run(
        ["bash", str(GATE)],
        input=fake_stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=120,
    )


def _make_fake_repo(tmp_path: Path, with_venv_bins: bool = True) -> Path:
    """Build a minimal fake-repo layout in tmp_path with the gate's expectations.

    Creates core/ gui/ api/ dirs (so ruff has targets) and a passing test file,
    plus a fake .venv/bin that points ruff/python at the real project bins.
    The temp dir is `git init`-ed so the gate's `git rev-parse --show-toplevel`
    resolves to it (not the real project root) — this isolates the gate from
    the real tests/ dir.
    """
    repo = tmp_path / "repo"
    (repo / "core").mkdir(parents=True)
    (repo / "gui").mkdir()
    (repo / "api").mkdir()
    (repo / "tests").mkdir()
    (repo / "core" / "__init__.py").write_text("")
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_smoke.py").write_text(
        "def test_ok():\n    assert True\n"
    )
    # Make it a real git repo so the gate's `git rev-parse --show-toplevel`
    # resolves here instead of the real project root.
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=30)
    if with_venv_bins:
        venv_bin = repo / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        project_root = Path(__file__).resolve().parent.parent
        # Symlink the real project's python + ruff so the gate finds them.
        # Use absolute symlinks because the real .venv/bin/python is itself a relative symlink.
        (venv_bin / "python").symlink_to((project_root / ".venv" / "bin" / "python").resolve())
        (venv_bin / "ruff").symlink_to((project_root / ".venv" / "bin" / "ruff").resolve())
    return repo


# ---------------------------------------------------------------------------
# main is gated, other refs are not
# ---------------------------------------------------------------------------


class TestGateAppliesToMainOnly:
    def test_non_main_ref_skips_gate(self, tmp_path):
        """Pushes to a feature branch must pass even if the repo is dirty."""
        repo = _make_fake_repo(tmp_path)
        # Drop a guaranteed lint error — gate should NOT run for a feature ref.
        (repo / "core" / "bad.py").write_text("import os, sys\n")
        result = _run_gate(repo, remote_ref="refs/heads/feature/x")
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# green path
# ---------------------------------------------------------------------------


class TestGreenPath:
    def test_allows_when_clean(self, tmp_path):
        repo = _make_fake_repo(tmp_path)
        result = _run_gate(repo)
        assert result.returncode == 0, result.stderr
        assert "green" in result.stderr.lower()


# ---------------------------------------------------------------------------
# ruff failure
# ---------------------------------------------------------------------------


class TestRuffFailure:
    def test_blocks_on_lint_error(self, tmp_path):
        repo = _make_fake_repo(tmp_path)
        # Unused import — F401, a real lint error ruff will flag.
        (repo / "core" / "bad.py").write_text("import os\n")
        result = _run_gate(repo)
        assert result.returncode != 0, "gate should block on a lint error"
        assert "BLOCKED" in result.stderr


# ---------------------------------------------------------------------------
# import failure
# ---------------------------------------------------------------------------


class TestImportFailure:
    def test_blocks_on_test_import_error(self, tmp_path):
        repo = _make_fake_repo(tmp_path)
        # A test file that raises at import/collection time.
        (repo / "tests" / "test_broken.py").write_text(
            "raise RuntimeError('boom at import')\n"
        )
        result = _run_gate(repo)
        assert result.returncode != 0, "gate should block on an import error"
        assert "BLOCKED" in result.stderr
        assert "collection failed" in result.stderr


# ---------------------------------------------------------------------------
# override
# ---------------------------------------------------------------------------


class TestSkipOverride:
    def test_skip_gate_env_allows_push_despite_errors(self, tmp_path):
        repo = _make_fake_repo(tmp_path)
        (repo / "core" / "bad.py").write_text("import os\n")
        result = _run_gate(repo, skip=True)
        assert result.returncode == 0, result.stderr
        assert "SKIP_GATE=1" in result.stderr


# ---------------------------------------------------------------------------
# venv bin preference
# ---------------------------------------------------------------------------


class TestVenvBinPreference:
    def test_prefers_venv_bins_when_present(self, tmp_path):
        """The gate resolves .venv/bin/ruff over a PATH ruff. We assert it runs
        without falling back to a bare 'ruff' (which may not exist in the test
        env) by giving it a real venv and confirming a clean run."""
        repo = _make_fake_repo(tmp_path, with_venv_bins=True)
        result = _run_gate(repo)
        assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
