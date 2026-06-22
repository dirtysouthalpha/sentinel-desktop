"""Regression tests for correctness bugs found in a focused review pass.

Each test documents the exact defect it guards against so the bug cannot be
reintroduced silently. These are NOT speculative/theoretical tests — every one
covers a concrete defect that was live in main (see commit message).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.action_executor import ActionExecutor, DragCoordinates

# ---------------------------------------------------------------------------
# Bug: _eval_run called self.execute(...) — a method that does not exist on
# ActionExecutor (only execute_sync exists). Every eval step raised
# AttributeError, caught by the runner, marking every step as failed.
# Fix: route through self.execute_sync({"action": action, **params}).
# ---------------------------------------------------------------------------


def test_eval_run_routes_steps_through_execute_sync(monkeypatch):
    """eval_run's per-step executor must call execute_sync, not the missing execute()."""
    import eval.registry as er
    import eval.runner as eRunner  # noqa: N812

    ex = ActionExecutor()
    captured_calls: list[dict] = []

    def fake_execute_sync(action: dict) -> dict:
        captured_calls.append(action)
        return {"success": True, "output": "ok"}

    monkeypatch.setattr(ex, "execute_sync", fake_execute_sync)

    # Registry: load returns any non-None scenario; record/compare are no-ops.
    monkeypatch.setattr(er.EvalRegistry, "load", lambda self, name: object())
    monkeypatch.setattr(er.EvalRegistry, "save_result", lambda self, result: None)
    monkeypatch.setattr(er.EvalRegistry, "compare_to_baseline", lambda self, result: {})

    invoke: dict | None = {"fn": None}

    class _FakeRunner:
        def __init__(self, executor_fn, stop_on_failure=False):
            invoke["fn"] = executor_fn

        def run(self, scenario):
            # Mimic ScenarioRunner: it calls the executor as executor(action, **params).
            invoke["fn"]("speak", text="hi")
            result = MagicMock()
            result.to_dict.return_value = {}
            result.score = 1.0
            result.passed = True
            result.steps_passed = 1
            result.steps_total = 1
            return result

    monkeypatch.setattr(eRunner, "ScenarioRunner", _FakeRunner)

    out = ex._eval_run(name="does_not_matter")

    # Before the fix, the executor raised AttributeError -> step failed -> steps_passed=0
    # and captured_calls stayed empty.
    assert captured_calls == [{"action": "speak", "text": "hi"}]
    assert out["success"] is True
    assert out["steps_passed"] == 1


# ---------------------------------------------------------------------------
# Bug: _trigger_fire_custom built executor_fn=lambda a: self.execute(**a),
# referencing the nonexistent self.execute. Fired custom triggers dispatched
# their action into an AttributeError and silently never executed.
# Fix: lambda a: self.execute_sync(a).
# ---------------------------------------------------------------------------


def test_trigger_fire_custom_executor_routes_through_execute_sync(monkeypatch):
    """The trigger executor_fn must call execute_sync with the action dict."""
    import core.triggers as trig

    ex = ActionExecutor()
    captured: list[dict] = []

    def fake_execute_sync(action: dict) -> dict:
        captured.append(action)
        return {"success": True}

    monkeypatch.setattr(ex, "execute_sync", fake_execute_sync)
    # Don't start a background thread in the test.
    monkeypatch.setattr(trig.TriggerEngine, "start", lambda self: None)
    # Force a fresh singleton so the production executor_fn is wired by our call.
    monkeypatch.setattr(trig, "_engine", None, raising=False)

    ex._trigger_fire_custom(event_name="ping")

    engine = trig.get_trigger_engine()
    assert engine._executor_fn is not None
    action = {"action": "speak", "text": "fired"}
    # This invokes the PRODUCTION lambda captured inside _trigger_fire_custom.
    engine._executor_fn(action)
    assert captured == [action]


# ---------------------------------------------------------------------------
# Invariant guard: ActionExecutor has no .execute() method, so no call site
# inside action_executor.py may use self.execute(...). Catches the eval_run and
# trigger_fire_custom class of bug for any future addition.
# ---------------------------------------------------------------------------


def test_action_executor_has_no_bogus_self_execute_calls():
    import pathlib

    import core.action_executor as ae

    src = pathlib.Path(ae.__file__).read_text()
    assert not hasattr(ae.ActionExecutor, "execute"), "ActionExecutor.execute must not exist"
    assert "self.execute(" not in src, (
        "self.execute(...) is a bug — ActionExecutor has no .execute method; use execute_sync"
    )


# ---------------------------------------------------------------------------
# Bug: _stealth_drag_win32 hardcoded WM_LBUTTONDOWN/UP regardless of button,
# so a right-button stealth drag was sent as a left-button drag.
# Fix: pick WM_xBUTTONDOWN/UP by drag_params.button (mirrors stealth_input.post_click).
# ---------------------------------------------------------------------------


def test_stealth_drag_win32_uses_right_button_messages_for_right_button(monkeypatch):
    ex = ActionExecutor()

    posted: list[tuple] = []
    mock_win32api = MagicMock()
    mock_win32api.PostMessage.side_effect = lambda hwnd, msg, wp, lp: posted.append((msg, wp))

    mock_win32con = MagicMock()
    mock_win32con.MK_LBUTTON = 0x0001
    mock_win32con.MK_RBUTTON = 0x0002
    mock_win32con.MK_MBUTTON = 0x0010
    mock_win32con.WM_LBUTTONDOWN = 0x0201
    mock_win32con.WM_LBUTTONUP = 0x0202
    mock_win32con.WM_RBUTTONDOWN = 0x0204
    mock_win32con.WM_RBUTTONUP = 0x0205
    mock_win32con.WM_MBUTTONDOWN = 0x0207
    mock_win32con.WM_MBUTTONUP = 0x0208
    mock_win32con.WM_MOUSEMOVE = 0x0200

    mock_win32gui = MagicMock()
    mock_win32gui.WindowFromPoint.return_value = 1
    mock_win32gui.ScreenToClient.side_effect = lambda hwnd, pt: pt

    monkeypatch.setitem(sys.modules, "win32api", mock_win32api)
    monkeypatch.setitem(sys.modules, "win32con", mock_win32con)
    monkeypatch.setitem(sys.modules, "win32gui", mock_win32gui)

    drag = DragCoordinates(from_x=0, from_y=0, to_x=5, to_y=5, duration=0.0, button="right")
    result = ex._stealth_drag_win32((0, 0), (5, 5), drag)

    assert result is not None
    # First PostMessage must be a right-button DOWN (not the old hardcoded left).
    assert posted[0][0] == mock_win32con.WM_RBUTTONDOWN
    assert posted[0][1] == mock_win32con.MK_RBUTTON
    # Last PostMessage must be a right-button UP.
    assert posted[-1][0] == mock_win32con.WM_RBUTTONUP


# ---------------------------------------------------------------------------
# Bug: cost_tracker fuzzy model match iterated pricing keys in insertion order
# and returned the first startswith/substring hit. "gpt-4o" precedes
# "gpt-4o-mini", so "gpt-4o-mini-2024-07-18" matched the $2.50 tier instead of
# the $0.15 mini tier (~16x overestimate).
# Fix: try longest keys first.
# ---------------------------------------------------------------------------


def test_cost_estimate_prefers_most_specific_model_prefix():
    from core.cost_tracker import estimate_cost

    # 1M prompt tokens at the mini input rate ($0.15/1M) = $0.15.
    # At the wrongly-matched gpt-4o rate ($2.50/1M) it would be $2.50.
    cost = estimate_cost("openai", "gpt-4o-mini-2024-07-18", 1_000_000, 0)
    assert cost == pytest.approx(0.15)
    # And the full-name mini still works.
    assert estimate_cost("openai", "gpt-4o-mini", 1_000_000, 0) == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Bug: v10/v11/v12 mutation handlers (daemon start/stop, fleet register/
# unregister, jobs submit/cancel, memory store/delete, conductor run) did not
# call _check_auth, so with SENTINEL_API_TOKEN set they accepted unauthenticated
# requests — an auth bypass under the v19 Fortress layer.
# Fix: add the authorization Header param + _check_auth to each handler.
# ---------------------------------------------------------------------------


@dataclass
class _TokenGuard:
    token: str

    def __enter__(self):
        import os

        os.environ["SENTINEL_API_TOKEN"] = self.token
        return self

    def __exit__(self, *exc):
        import os

        os.environ.pop("SENTINEL_API_TOKEN", None)
        return False


def _make_server():
    from api.server import SentinelServer
    from config import Config

    return SentinelServer(Config())


def test_mutation_handlers_enforce_auth_when_token_configured():
    from fastapi import HTTPException

    server = _make_server()
    import asyncio

    # Representative handlers from each affected group. Before the fix none of
    # these raised; after the fix each must 401 without a Bearer token.
    targets = [
        lambda: server._handle_daemon_start(authorization=None),
        lambda: server._handle_fleet_register({}, authorization=None),
        lambda: server._handle_jobs_submit({}, authorization=None),
        lambda: server._handle_job_cancel("j1", authorization=None),
        lambda: server._handle_memory_store({}, authorization=None),
        lambda: server._handle_memory_delete("k", authorization=None),
    ]
    with _TokenGuard("super-secret"):
        for call in targets:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(call())
            assert exc.value.status_code == 401


def test_mutation_handlers_accept_correct_bearer(monkeypatch):
    """With the correct bearer token, _check_auth passes (no 401)."""
    import asyncio

    server = _make_server()
    # Stub the daemon/fleet/jobs/memory backends so handlers return cleanly.
    import core.server.daemon as daemon_mod

    monkeypatch.setattr(daemon_mod.SentinelDaemon, "start", lambda self: {"started": True})

    with _TokenGuard("super-secret"):
        out = asyncio.run(server._handle_daemon_start(authorization="Bearer super-secret"))
    assert out["success"] is True


# ---------------------------------------------------------------------------
# Bug: smart_open's PowerShell fallback interpolated `name` into a single-quoted
# PS string without escaping, so a name containing ' broke out and could inject
# arbitrary PowerShell. Defense-in-depth beyond the approval gate.
# Fix: escape ' as '' (PowerShell doubling rule).
# ---------------------------------------------------------------------------


def test_smart_open_powershell_fallback_escapes_single_quotes(monkeypatch):
    import shutil
    import subprocess

    ex = ActionExecutor()

    popen = MagicMock(return_value=MagicMock())

    # Force the fallback path: launcher.smart_open fails, powershell is "found".
    monkeypatch.setattr("core.action_executor.launcher.smart_open", lambda name: {"success": False})
    monkeypatch.setattr(shutil, "which", lambda exe: "/fake/pwsh")
    monkeypatch.setattr(subprocess, "Popen", popen)

    # Malicious name attempting to break out of the single-quoted PS string.
    ex._smart_open(name="calc'; Remove-Item -Recurse C:\\x; '")

    assert popen.called
    cmd_arg = popen.call_args[0][0][-1]  # the "-Command" payload
    # The payload must remain a single Start-Process literal — quotes balanced,
    # no raw breakout. The dangerous text is now harmless data inside the string.
    assert cmd_arg.startswith("Start-Process '") and cmd_arg.endswith("'")
    assert cmd_arg.count("'") % 2 == 0
    assert "Remove-Item" in cmd_arg


def test_smart_open_powershell_fallback_clean_name_unchanged(monkeypatch):
    """A normal name with no quotes must pass through verbatim."""
    import shutil
    import subprocess

    ex = ActionExecutor()
    popen = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("core.action_executor.launcher.smart_open", lambda name: {"success": False})
    monkeypatch.setattr(shutil, "which", lambda exe: "/fake/pwsh")
    monkeypatch.setattr(subprocess, "Popen", popen)

    ex._smart_open(name="notepad.exe")
    cmd_arg = popen.call_args[0][0][-1]
    assert cmd_arg == "Start-Process 'notepad.exe'"


# ---------------------------------------------------------------------------
# Bug: estimate_cost's fuzzy lookup had an `or key in model` substring branch,
# so a short pricing key matched as a substring of an UNRELATED model name —
# "video3" matched "o3" ($10/M input), billing a non-existent model at the
# premium reasoning tier. Same class as the gpt-4o / gpt-4o-mini prefix bug.
# Fix: prefix-only match (startswith). The longest-first sort still resolves
# the legitimate versioned-name prefix collisions.
# ---------------------------------------------------------------------------


def test_cost_estimate_substring_branch_no_longer_false_matches():
    from core.cost_tracker import estimate_cost

    # "video3" / "promo3" contain the substring "o3" ($10/M). Before the fix
    # these returned $10.00 for 1M input tokens; now they are unknown → $0.0.
    assert estimate_cost("openai", "video3", 1_000_000, 0) == 0.0
    assert estimate_cost("openai", "promo3", 1_000_000, 0) == 0.0
    # Prefix matching still resolves the real versioned name to the mini tier.
    assert estimate_cost("openai", "gpt-4o-mini-2024-07-18", 1_000_000, 0) == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Bug: POST /recorder/stop built the save path from req.name with only
# .replace(' ', '_').lower() — path separators passed through, so a name like
# "../../etc/cron.d/backdoor" wrote outside the scripts/ directory.
# Fix: os.path.basename the normalized name; fall back to "untitled" when the
# result is empty / "." / "..".
# ---------------------------------------------------------------------------


def _stub_recorder_save() -> tuple[MagicMock, dict]:
    """Wire a fake engine+recorder onto a server; return (server, saved-path sink)."""
    server = _make_server()
    saved: dict = {}
    fake_script = MagicMock()
    fake_script.save = lambda path: saved.__setitem__("path", path)
    fake_script.steps = []
    engine = MagicMock()
    engine.recorder.stop_recording.return_value = fake_script
    server.engine = engine
    return server, saved


def test_recorder_stop_contains_traversal_name_inside_scripts_dir():
    import asyncio

    from api.server import RecorderStopRequest

    server, saved = _stub_recorder_save()
    req = RecorderStopRequest(name="../../etc/cron.d/backdoor", description="x")
    asyncio.run(server._handle_recorder_stop(req, authorization=None))

    path = saved["path"]
    # Must land directly inside scripts/ — basename applied, no parent escape.
    assert path.endswith(os.path.join("scripts", "backdoor.json"))
    assert ".." not in path


def test_recorder_stop_clean_name_passes_through():
    import asyncio

    from api.server import RecorderStopRequest

    server, saved = _stub_recorder_save()
    req = RecorderStopRequest(name="My Cool Script", description="x")
    asyncio.run(server._handle_recorder_stop(req, authorization=None))

    assert saved["path"].endswith(os.path.join("scripts", "my_cool_script.json"))


# ---------------------------------------------------------------------------
# Bug: the /ws/terminal WebSocket endpoint called ws.accept() and forked a PTY
# shell with NO auth check — so with SENTINEL_API_TOKEN configured, anyone who
# could reach the port got an unauthenticated interactive shell. Every other
# mutating handler gates on _check_auth; this one (the most powerful — arbitrary
# command execution) was wide open.
# Fix: when SENTINEL_API_TOKEN is set, require ?token=<token> (constant-time
# compare) before spawning the shell; close on mismatch. No-op when unset.
# ---------------------------------------------------------------------------


def test_terminal_ws_rejects_missing_token_when_configured():
    import asyncio

    import api.server as server_mod

    server = _make_server()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.query_params = {}  # no token presented

    mock_pty = MagicMock()
    with _TokenGuard("super-secret"):
        # Force _HAS_PTY True and patch os.fork so a regression (auth skipped)
        # fails loudly instead of forking the test process.
        orig = server_mod._HAS_PTY
        server_mod._HAS_PTY = True
        try:
            with patch("api.server.pty", mock_pty), patch(
                "os.fork", side_effect=AssertionError("shell must not spawn without auth")
            ):
                asyncio.run(server._handle_terminal_ws(ws))
        finally:
            server_mod._HAS_PTY = orig

    sent = ws.send_json.call_args[0][0]
    assert sent["type"] == "auth_error"
    ws.close.assert_called_once()
    mock_pty.openpty.assert_not_called()


def test_terminal_ws_accepts_correct_token_then_proceeds():
    import asyncio

    import api.server as server_mod

    server = _make_server()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.query_params = {"token": "super-secret"}

    with _TokenGuard("super-secret"):
        # _HAS_PTY False so that, after auth passes, the handler hits the
        # "not available" branch and closes cleanly — proving auth passed.
        orig = server_mod._HAS_PTY
        server_mod._HAS_PTY = False
        try:
            asyncio.run(server._handle_terminal_ws(ws))
        finally:
            server_mod._HAS_PTY = orig

    sent = ws.send_json.call_args[0][0]
    assert sent["type"] != "auth_error"  # auth passed
    assert sent["type"] == "error"  # reached the no-PTY branch
    ws.close.assert_called_once()


# ---------------------------------------------------------------------------
# Bug: service_control passed `action` straight into the `net` subprocess argv
# with no validation. The tool schema's enum is LLM-side only, so a caller
# bypassing it could re-route `net` — action="user" runs `net user ...`.
# Fix: allow-list {start, stop, restart, query} before the subprocess call.
# ---------------------------------------------------------------------------


def test_service_control_rejects_unknown_action():
    import core.process_manager as pm

    mock_ctypes = MagicMock()
    run = MagicMock()
    with (
        patch("sys.platform", "win32"),
        patch("core.process_manager.ctypes", mock_ctypes, create=True),
        patch.dict("sys.modules", {"ctypes": mock_ctypes}),
        patch("core.process_manager.subprocess.run", run),
    ):
        result = pm.service_control("Spooler", "user admin password")
    assert result["success"] is False
    assert "Invalid service action" in result["error"]
    run.assert_not_called()  # `net user ...` never reached

