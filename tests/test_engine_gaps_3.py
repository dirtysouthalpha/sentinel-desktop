"""Gap tests for core.engine — covers lines 526-548, 570-573, 683-688, 797,
904, 1181-1183, 1198-1209, 1316-1317, 1598, 1601, 1606-1608."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from core.engine import AgentEngine


def _make_engine(**overrides):
    config = {"provider": "openai", "api_key": "k", "model": "gpt-4o"}
    config.update(overrides)
    with patch("core.engine.capture_to_base64"), patch("core.engine.ActionExecutor"):
        return AgentEngine(config=config)


# ── Lazy web subsystem properties (lines 526-548) ────────────────────────


class TestWebRecorderLazyProp:
    """Lines 526-530 — web_recorder property creates WebRecorder on first access."""

    def test_web_recorder_lazy_creation(self):
        eng = _make_engine()
        fake_recorder = MagicMock()
        with patch("core.web.web_recorder.WebRecorder", return_value=fake_recorder):
            r = eng.web_recorder
        assert r is fake_recorder

    def test_web_recorder_cached_on_second_access(self):
        eng = _make_engine()
        fake_recorder = MagicMock()
        with patch("core.web.web_recorder.WebRecorder", return_value=fake_recorder):
            r1 = eng.web_recorder
            r2 = eng.web_recorder
        assert r1 is r2


class TestSessionVaultLazyProp:
    """Lines 535-539 — session_vault property creates SessionVault on first access."""

    def test_session_vault_lazy_creation(self):
        eng = _make_engine()
        fake_vault = MagicMock()
        with patch("core.web.session_vault.SessionVault", return_value=fake_vault):
            v = eng.session_vault
        assert v is fake_vault

    def test_session_vault_cached_on_second_access(self):
        eng = _make_engine()
        fake_vault = MagicMock()
        with patch("core.web.session_vault.SessionVault", return_value=fake_vault):
            v1 = eng.session_vault
            v2 = eng.session_vault
        assert v1 is v2


class TestInteractionModeLazyProp:
    """Lines 544-548 — interaction_mode property initializes to NATIVE."""

    def test_interaction_mode_default_native(self):
        from core.web.dual_mode import InteractionMode
        eng = _make_engine()
        mode = eng.interaction_mode
        assert mode == InteractionMode.NATIVE

    def test_interaction_mode_cached(self):
        eng = _make_engine()
        m1 = eng.interaction_mode
        m2 = eng.interaction_mode
        assert m1 is m2


# ── _build_memory_context (lines 1598, 1601, 1606-1608) ──────────────────


class TestBuildMemoryContext:
    """Lines 1598/1601/1606-1608 — _build_memory_context early-returns and exception."""

    def test_returns_empty_when_count_zero(self):
        """Line 1598 — count() == 0 → return ''."""
        eng = _make_engine()
        fake_mem = MagicMock()
        fake_mem.count.return_value = 0
        with patch("core.memory.semantic.SemanticMemory", return_value=fake_mem):
            result = eng._build_memory_context()
        assert result == ""

    def test_returns_empty_when_no_recent_facts(self):
        """Line 1601 — query() returns [] → return ''."""
        eng = _make_engine()
        fake_mem = MagicMock()
        fake_mem.count.return_value = 5
        fake_mem.query.return_value = []
        with patch("core.memory.semantic.SemanticMemory", return_value=fake_mem):
            result = eng._build_memory_context()
        assert result == ""

    def test_exception_returns_empty(self):
        """Lines 1606-1608 — any exception → return ''."""
        eng = _make_engine()
        with patch("core.memory.semantic.SemanticMemory", side_effect=OSError("db locked")):
            result = eng._build_memory_context()
        assert result == ""

    def test_returns_facts_when_present(self):
        """Happy path — mem has facts → returns formatted string."""
        eng = _make_engine()
        fake_mem = MagicMock()
        fake_mem.count.return_value = 2
        fake_mem.query.return_value = [
            {"key": "os", "value": "Linux"},
            {"key": "user", "value": "admin"},
        ]
        with patch("core.memory.semantic.SemanticMemory", return_value=fake_mem):
            result = eng._build_memory_context()
        assert "Known Facts" in result
        assert "os" in result


# ── _finalize_run episodic memory exception (lines 1316-1317) ────────────


class TestFinalizeRunMemoryException:
    """Lines 1316-1317 — episodic memory store exception is caught."""

    def test_episodic_store_exception_does_not_raise(self):
        eng = _make_engine()
        eng.step = 0
        eng.forensic_log = []
        eng.finish_summary = "done"
        eng.notes = []

        fake_em = MagicMock()
        fake_em.store.side_effect = OSError("disk full")

        with patch("core.memory.episodic.EpisodicMemory", return_value=fake_em), \
             patch("core.sound.play_sound"):
            result = eng._finalize_run(goal="click ok", start_time=time.time() - 1)

        assert "steps" in result
        assert result["finish_summary"] == "done"


# ── _build_initial_messages perception with no annotated image (line 904) ─


class TestBuildInitialMessagesPerceptionNoAnnotated:
    """Line 904 — perception_result.annotated_image is None → raw image used."""

    def test_no_annotated_image_uses_raw_b64(self):
        eng = _make_engine()
        fake_img = MagicMock()

        fake_result = MagicMock()
        fake_result.annotated_image = None
        fake_result.to_llm_context.return_value = "elements: []"

        with patch("core.screenshot.capture_screen", return_value=fake_img), \
             patch("core.screenshot.image_to_base64", return_value="raw_b64"), \
             patch.object(eng, "_run_perception", return_value=fake_result), \
             patch.object(eng, "_build_env_context", return_value=""), \
             patch.object(eng, "_build_app_context", return_value=""), \
             patch.object(eng, "_build_memory_context", return_value=""):
            msgs = eng._build_initial_messages("open browser")

        assert isinstance(msgs, list)
        assert any(m["role"] == "user" for m in msgs)


# ── _capture_next_screenshot (lines 1181-1209) ────────────────────────────


class TestCaptureNextScreenshot:
    """Lines 1181-1183/1198-1209 — capture_next_screenshot exception and perception paths."""

    def test_capture_screen_oserror_returns_none(self):
        """Lines 1181-1183 — OSError from capture_screen → return None."""
        eng = _make_engine()
        eng.running = True

        with patch("core.screenshot.capture_screen", side_effect=OSError("no display")):
            result = eng._capture_next_screenshot([], "step done", "prev_b64")

        assert result is None

    def test_perception_result_no_annotated_image(self):
        """Lines 1198-1200 — annotated_image is None → uses raw image."""
        eng = _make_engine()
        eng.running = True

        fake_img = MagicMock()
        fake_result = MagicMock()
        fake_result.annotated_image = None
        fake_result.to_llm_context.return_value = ""

        with patch("core.screenshot.capture_screen", return_value=fake_img), \
             patch("core.screenshot.image_to_base64", return_value="raw_b64"), \
             patch.object(eng, "_run_perception", return_value=fake_result), \
             patch.object(eng, "_prune_old_screenshots"):
            result = eng._capture_next_screenshot([], "step done", "prev_b64")

        assert result == "raw_b64"

    def test_no_perception_result_uses_raw(self):
        """Lines 1202-1204 — perception returns None → uses raw image."""
        eng = _make_engine()
        eng.running = True

        fake_img = MagicMock()

        with patch("core.screenshot.capture_screen", return_value=fake_img), \
             patch("core.screenshot.image_to_base64", return_value="raw_b64"), \
             patch.object(eng, "_run_perception", return_value=None), \
             patch.object(eng, "_prune_old_screenshots"):
            result = eng._capture_next_screenshot([], "step done", "prev_b64")

        assert result == "raw_b64"

    def test_perception_exception_falls_back_to_raw(self):
        """Lines 1205-1209 — perception raises → falls back to raw screenshot."""
        eng = _make_engine()
        eng.running = True

        fake_img = MagicMock()

        with patch("core.screenshot.capture_screen", return_value=fake_img), \
             patch("core.screenshot.image_to_base64", return_value="raw_b64"), \
             patch.object(eng, "_run_perception", side_effect=RuntimeError("pipeline crash")), \
             patch.object(eng, "_prune_old_screenshots"):
            result = eng._capture_next_screenshot([], "step done", "prev_b64")

        assert result == "raw_b64"


# ── _execute_action web recorder capture (line 797) ──────────────────────


class TestExecuteActionWebRecorderCapture:
    """Line 797 — _execute_action() calls web_recorder.capture() when recording."""

    def test_capture_called_when_recorder_is_active(self):
        eng = _make_engine()

        fake_recorder = MagicMock()
        fake_recorder.is_recording = True
        eng._web_recorder = fake_recorder
        eng.executor.execute_sync.return_value = {"success": True, "output": "done"}

        action = {"action": "web_click", "selector": "#submit"}

        with patch.object(eng, "_handle_action_failure"), \
             patch.object(eng, "_handle_post_action_success", return_value="ok"), \
             patch.object(eng, "_capture_next_screenshot", return_value=None):
            eng._execute_action(action, "web_click", "goal", [], None)

        fake_recorder.capture.assert_called_once_with(action)


# ── Finish action with web recorder save exception (lines 683-688) ────────


class TestRunOneStepFinishWebRecorderSaveException:
    """Lines 683-688 — finish action with active recorder whose save() raises."""

    def test_save_exception_does_not_propagate(self):
        eng = _make_engine()

        fake_recording = MagicMock()
        fake_recording.step_count = 3
        fake_recording.save.side_effect = OSError("disk full")

        fake_recorder = MagicMock()
        fake_recorder.is_recording = True
        fake_recorder.stop.return_value = fake_recording
        eng._web_recorder = fake_recorder

        action = {"action": "finish", "summary": "All done"}

        with patch.object(eng, "_prepare_step_action", return_value=(action, None)), \
             patch.object(eng, "_log_step"):
            outcome, _ = eng._run_one_step(
                provider="openai",
                api_key="k",
                model="gpt-4o",
                goal="do stuff",
                messages=[],
                screenshot_b64=None,
            )

        assert outcome == "abort"
        fake_recording.save.assert_called_once()
