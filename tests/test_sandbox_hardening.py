"""Regression tests for the v31 plugin-sandbox hardening.

Covers four defects:

1. ``import resource`` at module scope made ``core.sandbox`` unimportable on
   Windows (ModuleNotFoundError), so the sandbox was dead and callers fell
   back to unsandboxed plugin execution.
2. ``function_name`` was interpolated into the generated runner source raw,
   giving code injection into the sandbox process.
3. ``list_active()`` popped from ``_active_plugins`` while iterating it, so it
   raised ``RuntimeError: dictionary changed size during iteration`` exactly
   when a plugin finished.
4. Timeout cleanup used the Unix-only ``os.killpg``, so on Windows a plugin's
   children were orphaned.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time

import pytest

from core import sandbox
from core.sandbox import (
    BACKEND_NONE,
    SandboxedPlugin,
    SandboxUnavailableError,
    execute_plugin,
    list_active,
    sandbox_available,
    sandbox_backend,
)

# ---------------------------------------------------------------------------
# 1. The module imports and reports a real backend on this platform
# ---------------------------------------------------------------------------


def test_sandbox_module_imports_on_this_platform():
    """The old ``import resource`` at module scope broke this outright."""
    assert sandbox.__name__ == "core.sandbox"


def test_a_real_isolation_backend_is_available():
    backend = sandbox_backend()
    assert backend != BACKEND_NONE, f"no isolation backend on {sys.platform}"
    assert sandbox_available() is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job-object backend")
def test_windows_uses_job_object_backend():
    assert sandbox_backend() == "windows-job-object"


# ---------------------------------------------------------------------------
# 2. No silent unsandboxed fallback
# ---------------------------------------------------------------------------


def test_refuses_to_execute_when_no_backend(tmp_path, monkeypatch):
    """With no isolation backend, the plugin must NOT run — it must raise."""
    plugin = tmp_path / "canary_plugin.py"
    canary = tmp_path / "canary.txt"
    plugin.write_text(
        "import pathlib\n"
        f"def run(args):\n"
        f"    pathlib.Path({str(canary)!r}).write_text('RAN')\n"
        "    return 'ran'\n"
    )

    monkeypatch.setattr(sandbox, "sandbox_backend", lambda: BACKEND_NONE)

    with pytest.raises(SandboxUnavailableError):
        execute_plugin(plugin, timeout=10)

    # The decisive assertion: refusing must mean *not executing*.
    assert not canary.exists(), "plugin executed despite having no sandbox"


def test_refusal_message_names_the_plugin(tmp_path, monkeypatch):
    plugin = tmp_path / "p.py"
    plugin.write_text("def run(args):\n    return 1\n")
    monkeypatch.setattr(sandbox, "sandbox_backend", lambda: BACKEND_NONE)
    with pytest.raises(SandboxUnavailableError, match="refusing to execute"):
        execute_plugin(plugin)


# ---------------------------------------------------------------------------
# 3. function_name injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil_name",
    [
        "run', None) or __import__('os').system('echo pwned') or getattr(module, 'run",
        "run'); import os; os.remove('x'); getattr(module, 'run",
        "run\\'",
        'run") or 1 or getattr(module, "run',
        "run\nimport os",
        "0bad",
        "has-dash",
        "has space",
        "",
        "__import__",  # valid identifier, but dunders are refused too
        "__builtins__",
    ],
)
def test_invalid_entry_point_names_are_rejected(tmp_path, evil_name):
    plugin = tmp_path / "plug.py"
    plugin.write_text("def run(args):\n    return 'ok'\n")
    result = execute_plugin(plugin, function_name=evil_name, timeout=10)
    assert result.success is False
    assert "Invalid entry point name" in result.error


def test_injected_entry_point_does_not_execute(tmp_path):
    """The injected payload must never reach the sandbox process."""
    plugin = tmp_path / "plug.py"
    plugin.write_text("def run(args):\n    return 'ok'\n")
    canary = tmp_path / "pwned.txt"
    evil = (
        "run', None) or __import__('pathlib').Path("
        + repr(str(canary))
        + ").write_text('PWNED') or getattr(module, 'run"
    )
    result = execute_plugin(plugin, function_name=evil, timeout=10)
    assert result.success is False
    assert not canary.exists()


def test_valid_entry_point_names_still_work(tmp_path):
    plugin = tmp_path / "plug.py"
    plugin.write_text("def my_entry(args):\n    return 'custom'\n")
    result = execute_plugin(plugin, function_name="my_entry", timeout=20)
    assert result.success is True
    assert "custom" in result.output


def test_missing_entry_point_reports_cleanly(tmp_path):
    plugin = tmp_path / "plug.py"
    plugin.write_text("def run(args):\n    return 'ok'\n")
    result = execute_plugin(plugin, function_name="not_there", timeout=20)
    assert result.success is False
    assert "not_there" in result.error


def test_runner_source_quotes_the_entry_point(tmp_path):
    """The generated source must carry the name as a literal, not bare code."""
    plugin = tmp_path / "plug.py"
    plugin.write_text("def run(args):\n    return 1\n")
    code = sandbox._build_runner_code(plugin, "run", None, 256, apply_rlimit=False)
    assert "getattr(module, 'run', None)" in code


# ---------------------------------------------------------------------------
# 4. list_active() must survive a plugin finishing mid-iteration
# ---------------------------------------------------------------------------


class _FinishedProc:
    """Stand-in for a Popen whose process has already exited."""

    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid

    def poll(self):
        return 0  # exited


def test_list_active_survives_finished_plugins(monkeypatch):
    """Pre-v31 this raised RuntimeError: dictionary changed size during iteration."""
    registry = {
        f"done{i}": SandboxedPlugin(
            name=f"done{i}", pid=1000 + i, started_at=1.0, process=_FinishedProc(1000 + i)
        )
        for i in range(12)
    }
    monkeypatch.setattr(sandbox, "_active_plugins", registry)

    result = list_active()  # must not raise

    assert result == []
    assert registry == {}, "finished plugins should have been reaped"


def test_list_active_reports_running_plugins(monkeypatch):
    class _RunningProc:
        pid = 777

        def poll(self):
            return None

    registry = {
        "alive": SandboxedPlugin(
            name="alive",
            pid=777,
            started_at=1.0,
            permissions=["clipboard"],
            process=_RunningProc(),
        ),
        "dead": SandboxedPlugin(name="dead", pid=778, started_at=1.0, process=_FinishedProc(778)),
    }
    monkeypatch.setattr(sandbox, "_active_plugins", registry)

    result = list_active()

    assert [r["name"] for r in result] == ["alive"]
    assert result[0]["permissions"] == ["clipboard"]
    assert "dead" not in registry


# ---------------------------------------------------------------------------
# 5. Resource limits and process-tree teardown actually enforce
# ---------------------------------------------------------------------------


def test_memory_limit_is_enforced(tmp_path):
    """A plugin over its cap must fail; the same plugin under it must succeed."""
    plugin = tmp_path / "hog.py"
    plugin.write_text("def run(args):\n    x = bytearray(400 * 1024 * 1024)\n    return len(x)\n")

    capped = execute_plugin(plugin, timeout=90, memory_limit_mb=64)
    assert capped.success is False, "400MB allocation succeeded under a 64MB cap"

    roomy = execute_plugin(plugin, timeout=90, memory_limit_mb=1024)
    assert roomy.success is True, f"legitimate allocation blocked: {roomy.error}"
    assert roomy.output == str(400 * 1024 * 1024)


def test_timeout_kills_the_whole_process_tree(tmp_path):
    """A grandchild spawned by the plugin must not survive the timeout.

    On Windows the old cleanup path called ``os.killpg`` (which does not exist),
    fell through to ``proc.kill()``, and orphaned anything the plugin spawned.
    """
    psutil = pytest.importorskip("psutil")

    pidfile = tmp_path / "grandchild.pid"
    grandchild = (
        "import os, time; open(r'" + str(pidfile) + "', 'w').write(str(os.getpid())); time.sleep(120)"
    )
    plugin = tmp_path / "tree.py"
    plugin.write_text(
        "import subprocess, sys, time\n"
        "def run(args):\n"
        "    subprocess.Popen([sys.executable, '-c', " + repr(grandchild) + "])\n"
        "    time.sleep(120)\n"
    )

    result = execute_plugin(plugin, timeout=8, memory_limit_mb=256)
    assert result.timed_out is True

    if not pidfile.exists():
        pytest.skip("grandchild never recorded its pid")

    gc_pid = int(pidfile.read_text())
    # Give the OS a moment to finish reaping the job / process group.
    for _ in range(20):
        if not psutil.pid_exists(gc_pid):
            break
        time.sleep(0.25)

    still_running = psutil.pid_exists(gc_pid) and psutil.Process(gc_pid).is_running()
    if still_running:  # don't leak a sleeping process into the rest of the run
        with contextlib.suppress(Exception):
            psutil.Process(gc_pid).kill()
    assert not still_running, f"grandchild {gc_pid} survived the sandbox timeout"


def test_result_records_the_backend(tmp_path):
    plugin = tmp_path / "plug.py"
    plugin.write_text("def run(args):\n    return 'ok'\n")
    result = execute_plugin(plugin, timeout=20)
    assert result.backend == sandbox_backend()


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NEW_PROCESS_GROUP is Windows-only")
def test_windows_child_gets_its_own_process_group(tmp_path, monkeypatch):
    """The Windows path must not pass the Unix-only preexec_fn."""
    captured: dict = {}
    real_popen = subprocess.Popen

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "Popen", _spy)
    plugin = tmp_path / "plug.py"
    plugin.write_text("def run(args):\n    return 'ok'\n")
    execute_plugin(plugin, timeout=20)

    assert "preexec_fn" not in captured
    assert captured.get("creationflags") == subprocess.CREATE_NEW_PROCESS_GROUP
