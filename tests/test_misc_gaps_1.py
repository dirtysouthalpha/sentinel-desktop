"""Miscellaneous 1-liner gap tests — batch 1.

Covers uncovered lines across 12 files:
  core/conductor/coordinator.py   line 66    — empty decompose → no_tasks
  core/conductor/planner.py       line 104   — single-task path (no fragments)
  core/conductor/synthesizer.py   line 55    — overall_status = "failed"
  core/engine.py                  lines 570-573 — WEB mode + web_recording_enabled
  core/launcher.py                line 130   — Windows cmd.exe not found
  core/perception/types.py        line 176   — PerceptionResult.to_dict()
  core/resilience.py              line 227   — allow_call() already in HALF_OPEN
  core/server/fleet.py            line 145   — record_job nonexistent node
  core/swarm/bus.py               line 122   — history pruning when over max
  core/swarm/orchestrator.py      line 100   — receive returns non-None message
  core/registry.py                line 14    — import winreg on win32
  core/script_engine.py           line 269   — _handle_step_result success branch
"""

from __future__ import annotations

import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── coordinator.py line 66 ───────────────────────────────────────────────────


class TestConductorEmptyDecompose:
    """Line 66 — Conductor.run() returns no_tasks when planner decomposes to []."""

    @pytest.mark.asyncio
    async def test_empty_subtasks_returns_no_tasks(self):
        from core.conductor.coordinator import Conductor

        conductor = Conductor()
        with patch.object(conductor.planner, "decompose", return_value=[]):
            result = await conductor.run("some goal")

        assert result["status"] == "no_tasks"
        assert result["success"] is False
        assert result["tasks_total"] == 0


# ── planner.py line 104 ──────────────────────────────────────────────────────


class TestPlannerSingleTaskPath:
    """Line 104 — decompose() returns single Subtask when _split_goal returns []."""

    def test_short_single_letters_returns_one_subtask(self):
        from core.conductor.planner import TaskPlanner

        planner = TaskPlanner()
        # 6 words all 1 char, split on commas → all filtered (len <= 3) → fragments=[]
        subtasks = planner.decompose("a, b, c, d, e, f")

        assert len(subtasks) == 1
        assert subtasks[0].subtask_id == "t-1"
        assert "a" in subtasks[0].description


# ── synthesizer.py line 55 ───────────────────────────────────────────────────


class TestSynthesizerAllFailed:
    """Line 55 — overall_status = 'failed' when no successes and no errors."""

    def test_all_timeout_results_give_failed_status(self):
        from core.conductor.synthesizer import ResultSynthesizer

        synthesizer = ResultSynthesizer()
        results = [
            {"status": "timeout", "description": "task1"},
            {"status": "failed", "description": "task2"},
        ]
        final = synthesizer.synthesize("some goal", results)

        assert final["status"] == "failed"
        assert final["success"] is False


# ── engine.py lines 570-573 ──────────────────────────────────────────────────


def _make_engine(**extra_config):
    from core.engine import AgentEngine

    config = {"provider": "openai", "api_key": "k", "model": "gpt-4o"}
    config.update(extra_config)
    with patch("core.engine.capture_to_base64"), patch("core.engine.ActionExecutor"):
        return AgentEngine(config=config)


class TestEngineWebModeRecording:
    """Lines 570-573 — run() starts web recorder when mode=WEB and recording enabled."""

    def test_web_recorder_started_when_mode_is_web_and_enabled(self):
        from core.web.dual_mode import InteractionMode

        eng = _make_engine(web_recording_enabled=True)
        fake_recorder = MagicMock()
        eng._web_recorder = fake_recorder

        with patch("core.web.dual_mode.detect_mode_from_goal", return_value=InteractionMode.WEB), \
             patch.object(eng, "_run_inner", return_value={"steps": 0}):
            eng.run("open the dashboard website")

        fake_recorder.start.assert_called_once()
        call_kwargs = fake_recorder.start.call_args[1]
        assert "dashboard" in call_kwargs["goal"]

    def test_web_mode_without_recording_does_not_start_recorder(self):
        from core.web.dual_mode import InteractionMode

        eng = _make_engine()  # no web_recording_enabled
        fake_recorder = MagicMock()
        eng._web_recorder = fake_recorder

        with patch("core.web.dual_mode.detect_mode_from_goal", return_value=InteractionMode.WEB), \
             patch.object(eng, "_run_inner", return_value={"steps": 0}):
            eng.run("open the dashboard website")

        fake_recorder.start.assert_not_called()


# ── launcher.py line 130 ─────────────────────────────────────────────────────


class TestLauncherCmdNotFound:
    """Line 130 — _launch_new_app returns error when on Windows and cmd.exe missing."""

    def test_cmd_not_found_on_windows_returns_error(self):
        import shutil

        from core.launcher import _launch_new_app

        with patch("platform.system", return_value="Windows"), \
             patch.object(shutil, "which", return_value=None):
            result = _launch_new_app("MyApp", "myapp.exe")

        assert result["success"] is False
        assert result["error"] == "cmd_not_found"
        assert "cmd.exe" in result["output"]


# ── perception/types.py line 176 ─────────────────────────────────────────────


class TestPerceptionResultToDict:
    """Line 176 — PerceptionResult.to_dict() serializes the result."""

    def test_to_dict_returns_expected_keys(self):
        from core.perception.types import PerceptionResult

        result = PerceptionResult(accessibility_count=3, ocr_count=1)
        d = result.to_dict()

        assert "element_count" in d
        assert "accessibility_count" in d
        assert d["accessibility_count"] == 3
        assert d["ocr_count"] == 1


# ── resilience.py line 227 ───────────────────────────────────────────────────


class TestCircuitBreakerHalfOpenAllow:
    """Line 227 — allow_call() returns True when already in HALF_OPEN state."""

    def test_allow_call_returns_true_when_already_half_open(self):
        from core.resilience import CircuitBreaker

        cb = CircuitBreaker(name="test_breaker", failure_threshold=2, recovery_timeout=0.001)

        # Trip the breaker
        for _ in range(2):
            cb.record_failure()

        assert cb._state == cb.OPEN

        # Wait for recovery timeout to elapse
        time.sleep(0.01)

        # First allow_call() transitions OPEN → HALF_OPEN (hits line 224)
        first = cb.allow_call()
        assert first is True
        assert cb._state == cb.HALF_OPEN

        # Second allow_call() already in HALF_OPEN (hits line 227)
        second = cb.allow_call()
        assert second is True


# ── server/fleet.py line 145 ─────────────────────────────────────────────────


class TestFleetRecordJobNotFound:
    """Line 145 — record_job() returns error when node_id not registered."""

    def test_record_job_unknown_node_returns_error(self, tmp_path):
        from core.server.fleet import FleetManager

        fleet = FleetManager(path=tmp_path / "fleet.json")
        result = fleet.record_job("ghost-node-99", success=True)

        assert result["success"] is False
        assert "ghost-node-99" in result["error"]


# ── swarm/bus.py line 122 ────────────────────────────────────────────────────


class TestMessageBusHistoryPruning:
    """Line 122 — history is pruned when it exceeds _history_max."""

    @pytest.mark.asyncio
    async def test_history_pruned_when_over_max(self):
        from core.swarm.bus import AgentMessage, MessageBus

        bus = MessageBus()
        bus._history_max = 2  # reduce max so we can trigger pruning easily
        bus.register("agent1")

        for i in range(3):
            await bus.send(AgentMessage(
                sender="agent1",
                recipient="agent1",
                msg_type="task",
                payload={"i": i},
            ))

        assert len(bus._history) == 2


# ── swarm/orchestrator.py line 100 ───────────────────────────────────────────


class TestOrchestratorResultReceived:
    """Line 100 — _run_agent_loop appends result when bus.receive returns message."""

    @pytest.mark.asyncio
    async def test_receive_non_none_appends_success_result(self):
        from core.swarm.bus import AgentMessage, MessageBus
        from core.swarm.orchestrator import SwarmOrchestrator
        from core.swarm.specialist import DesktopAgent

        bus = MessageBus()
        swarm = SwarmOrchestrator(bus=bus)

        # Register a desktop agent so the orchestrator can assign tasks
        agent = DesktopAgent(bus, "desktop-1")
        swarm.registry.register(agent)

        # Patch bus.receive to return a mock result message
        result_payload = {"agent_id": "desktop-1", "success": True, "output": "done"}
        fake_msg = AgentMessage(
            sender="desktop-1",
            recipient="orchestrator",
            msg_type="result",
            payload=result_payload,
        )

        with patch.object(bus, "receive", new=AsyncMock(return_value=fake_msg)), \
             patch.object(bus, "send", new=AsyncMock(return_value=1)):
            result = await swarm.execute("click on the icon", timeout=10.0)

        # At least one result was appended via line 100
        success_results = [r for r in result["results"] if r.get("status") == "success"]
        assert len(success_results) >= 1
        assert success_results[0]["agent"] == "desktop-1"


# ── registry.py line 14 ──────────────────────────────────────────────────────


class TestRegistryWinregImport:
    """Line 14 — import winreg is executed on win32 platform."""

    def test_reload_with_win32_imports_winreg(self):
        import importlib

        import core.registry as registry_mod

        fake_winreg = MagicMock()
        with patch.dict(sys.modules, {"winreg": fake_winreg}), \
             patch("sys.platform", "win32"):
            importlib.reload(registry_mod)
            # winreg should now be bound in the module
            assert hasattr(registry_mod, "winreg") or "winreg" in dir(registry_mod)

        # Restore
        importlib.reload(registry_mod)


# ── script_engine.py line 269 ────────────────────────────────────────────────


class TestScriptEngineHandleStepResultSuccess:
    """Line 269 — _handle_step_result returns (True, None) for a successful result."""

    def test_success_result_returns_continue_true(self):
        from core.script_engine import ScriptEngine

        executor = MagicMock()
        engine = ScriptEngine(action_executor=executor)

        should_continue, error_msg = engine._handle_step_result(
            result={"success": True, "output": "clicked"},
            step_num=1,
            action="click",
        )

        assert should_continue is True
        assert error_msg is None
