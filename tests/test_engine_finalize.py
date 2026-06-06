"""Tests for core/engine.py — _finalize_run, _validate_run_config, _build_initial_messages."""

from unittest.mock import patch

from core.engine import AgentEngine

# ---------------------------------------------------------------------------
# _finalize_run
# ---------------------------------------------------------------------------


class TestFinalizeRun:
    """Tests for AgentEngine._finalize_run (lines 1072-1097)."""

    def _make_engine(self, **overrides):
        """Create a minimal engine for finalize testing."""
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = overrides.get("step", 5)
        eng.notes = overrides.get("notes", ["note1", "note2"])
        eng.forensic_log = overrides.get("forensic_log", [{"step": 1}])
        eng.finish_summary = overrides.get("finish_summary", "All done")
        eng.config = overrides.get("config", {})
        eng.max_steps = 20
        # _generate_report needs these
        eng._consecutive_failures = 0
        return eng

    @patch("core.engine.time")
    def test_returns_expected_keys(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine()
        # _generate_report references SYSTEM_PROMPT; mock it to avoid import issues
        with patch.object(eng, "_generate_report", return_value="report text"):
            result = eng._finalize_run("test goal", 90.0)

        assert "steps" in result
        assert "notes" in result
        assert "log" in result
        assert "finish_summary" in result
        assert "elapsed_seconds" in result
        assert "report" in result

    @patch("core.engine.time")
    def test_elapsed_seconds_rounded(self, mock_time):
        mock_time.time.return_value = 105.678
        eng = self._make_engine()
        with patch.object(eng, "_generate_report", return_value=""):
            result = eng._finalize_run("goal", 100.0)

        assert result["elapsed_seconds"] == 5.68

    @patch("core.engine.time")
    def test_steps_matches_engine_step(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(step=42)
        with patch.object(eng, "_generate_report", return_value=""):
            result = eng._finalize_run("goal", 95.0)

        assert result["steps"] == 42

    @patch("core.engine.time")
    def test_finish_summary_included(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(finish_summary="Task completed successfully")
        with patch.object(eng, "_generate_report", return_value=""):
            result = eng._finalize_run("goal", 95.0)

        assert result["finish_summary"] == "Task completed successfully"

    @patch("core.engine.time")
    def test_notes_included(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(notes=["alpha", "beta", "gamma"])
        with patch.object(eng, "_generate_report", return_value=""):
            result = eng._finalize_run("goal", 95.0)

        assert result["notes"] == ["alpha", "beta", "gamma"]

    @patch("core.engine.time")
    def test_forensic_log_included(self, mock_time):
        mock_time.time.return_value = 100.0
        log = [{"step": 1}, {"step": 2}]
        eng = self._make_engine(forensic_log=log)
        with patch.object(eng, "_generate_report", return_value=""):
            result = eng._finalize_run("goal", 95.0)

        assert result["log"] is log

    @patch("core.engine.time")
    def test_generates_report(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine()
        with patch.object(eng, "_generate_report", return_value="FULL REPORT") as mock_report:
            mock_report.return_value = "FULL REPORT"
            result = eng._finalize_run("my goal", 95.0)

        assert result["report"] == "FULL REPORT"
        mock_report.assert_called_once_with("my goal", 5.0)

    @patch("core.engine.time")
    def test_plays_complete_sound_on_success(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(finish_summary="Done")
        with patch.object(eng, "_generate_report", return_value=""):
            with patch("core.sound.play_sound") as mock_sound:
                eng._finalize_run("goal", 95.0)

        mock_sound.assert_called_once_with("complete")

    @patch("core.engine.time")
    def test_plays_error_sound_on_failure(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(finish_summary="")
        with patch.object(eng, "_generate_report", return_value=""):
            with patch("core.sound.play_sound") as mock_sound:
                eng._finalize_run("goal", 95.0)

        mock_sound.assert_called_once_with("error")

    @patch("core.engine.time")
    def test_sound_import_error_is_handled(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine()
        with patch.object(eng, "_generate_report", return_value=""):
            with patch("core.sound.play_sound", side_effect=ImportError("no sound")):
                # Should not raise
                result = eng._finalize_run("goal", 95.0)

        assert result["steps"] == 5

    @patch("core.engine.time")
    def test_sound_oserror_is_handled(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine()
        with patch.object(eng, "_generate_report", return_value=""):
            with patch("core.sound.play_sound", side_effect=OSError("device busy")):
                result = eng._finalize_run("goal", 95.0)

        assert result["steps"] == 5

    @patch("core.engine.time")
    def test_empty_summary_triggers_error_sound(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(finish_summary="")
        with patch.object(eng, "_generate_report", return_value=""):
            with patch("core.sound.play_sound") as mock_sound:
                eng._finalize_run("goal", 95.0)

        mock_sound.assert_called_once_with("error")

    @patch("core.engine.time")
    def test_zero_step_run(self, mock_time):
        mock_time.time.return_value = 100.0
        eng = self._make_engine(step=0, finish_summary="")
        with patch.object(eng, "_generate_report", return_value=""):
            result = eng._finalize_run("goal", 100.0)

        assert result["steps"] == 0
        assert result["elapsed_seconds"] == 0.0


# ---------------------------------------------------------------------------
# _validate_run_config
# ---------------------------------------------------------------------------


class TestValidateRunConfig:
    """Tests for AgentEngine._validate_run_config (lines 656-684)."""

    def _make_engine(self, config=None):
        eng = AgentEngine.__new__(AgentEngine)
        eng.config = config or {}
        eng.notes = []
        eng.running = True
        return eng

    def test_valid_config_returns_none(self):
        eng = self._make_engine(
            {
                "provider": "openai",
                "api_key": "sk-test123",
                "model": "gpt-4",
            }
        )
        assert eng._validate_run_config() is None

    def test_missing_api_key_returns_error(self):
        eng = self._make_engine(
            {
                "provider": "openai",
                "model": "gpt-4",
            }
        )
        result = eng._validate_run_config()

        assert result is not None
        assert result["error"] == "api_key_missing"
        assert result["steps"] == 0

    def test_missing_api_key_stops_running(self):
        eng = self._make_engine(
            {
                "provider": "openai",
                "model": "gpt-4",
            }
        )
        eng._validate_run_config()

        assert eng.running is False

    def test_missing_api_key_sets_notes(self):
        eng = self._make_engine(
            {
                "provider": "openai",
                "model": "gpt-4",
            }
        )
        eng._validate_run_config()

        assert len(eng.notes) == 1
        assert "API key" in eng.notes[0]

    def test_ollama_no_api_key_is_ok(self):
        eng = self._make_engine(
            {
                "provider": "ollama",
                "model": "llama3",
            }
        )
        assert eng._validate_run_config() is None

    def test_lmstudio_no_api_key_is_ok(self):
        eng = self._make_engine(
            {
                "provider": "lmstudio",
                "model": "local-model",
            }
        )
        assert eng._validate_run_config() is None

    def test_custom_no_api_key_is_ok(self):
        eng = self._make_engine(
            {
                "provider": "custom",
                "model": "my-model",
            }
        )
        assert eng._validate_run_config() is None

    def test_missing_provider_returns_error(self):
        eng = self._make_engine(
            {
                "api_key": "sk-test",
                "model": "gpt-4",
            }
        )
        result = eng._validate_run_config()

        assert result is not None
        assert result["error"] == "provider_missing"

    def test_missing_provider_stops_running(self):
        eng = self._make_engine(
            {
                "api_key": "sk-test",
                "model": "gpt-4",
            }
        )
        eng._validate_run_config()

        assert eng.running is False

    def test_missing_model_returns_error(self):
        eng = self._make_engine(
            {
                "provider": "openai",
                "api_key": "sk-test",
            }
        )
        result = eng._validate_run_config()

        assert result is not None
        assert result["error"] == "model_missing"

    def test_missing_model_stops_running(self):
        eng = self._make_engine(
            {
                "provider": "openai",
                "api_key": "sk-test",
            }
        )
        eng._validate_run_config()

        assert eng.running is False

    def test_missing_model_mentions_provider(self):
        eng = self._make_engine(
            {
                "provider": "anthropic",
                "api_key": "sk-test",
            }
        )
        eng._validate_run_config()

        assert "anthropic" in eng.notes[0]

    def test_empty_config_returns_api_key_error(self):
        """Empty config: api_key checked first, then provider, then model."""
        eng = self._make_engine({})
        result = eng._validate_run_config()

        assert result is not None
        # provider is "" (falsy), api_key is "" (falsy)
        # api_key check fires first because provider isn't in the exempt list
        assert result["error"] == "api_key_missing"

    def test_all_empty_strings(self):
        eng = self._make_engine(
            {
                "provider": "",
                "api_key": "",
                "model": "",
            }
        )
        result = eng._validate_run_config()

        assert result is not None
        # "" provider isn't in (ollama, lmstudio, custom), so api_key check fires
        assert result["error"] == "api_key_missing"


# ---------------------------------------------------------------------------
# _build_initial_messages
# ---------------------------------------------------------------------------


class TestBuildInitialMessages:
    """Tests for AgentEngine._build_initial_messages (lines 686-716)."""

    def _make_engine(self, config=None):
        eng = AgentEngine.__new__(AgentEngine)
        eng.config = config or {}
        eng.notes = []
        # Add mock executor to avoid AttributeError
        from unittest.mock import MagicMock
        eng.executor = MagicMock()
        eng.executor.perception_result = None
        return eng

    def test_returns_list_of_dicts(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value="env info"):
            with patch.object(eng, "_build_app_context", return_value="app info"):
                with patch("core.engine.capture_to_base64", return_value="fake_b64"):
                    with patch.object(eng, "_add_vision_message"):
                        msgs = eng._build_initial_messages("Click the button")

        assert isinstance(msgs, list)
        assert all(isinstance(m, dict) for m in msgs)

    def test_first_message_is_system(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value="env"):
            with patch.object(eng, "_build_app_context", return_value="app"):
                with patch("core.engine.capture_to_base64", return_value="b64"):
                    with patch.object(eng, "_add_vision_message"):
                        msgs = eng._build_initial_messages("goal")

        assert msgs[0]["role"] == "system"
        assert "env" in msgs[0]["content"]
        assert "app" in msgs[0]["content"]

    def test_system_prompt_contains_env_context(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value="OS: Linux"):
            with patch.object(eng, "_build_app_context", return_value=""):
                with patch("core.engine.capture_to_base64", return_value="b64"):
                    with patch.object(eng, "_add_vision_message"):
                        msgs = eng._build_initial_messages("goal")

        assert "OS: Linux" in msgs[0]["content"]

    def test_system_prompt_contains_app_context(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value=""):
            with patch.object(eng, "_build_app_context", return_value="App: Chrome"):
                with patch("core.engine.capture_to_base64", return_value="b64"):
                    with patch.object(eng, "_add_vision_message"):
                        msgs = eng._build_initial_messages("goal")

        assert "App: Chrome" in msgs[0]["content"]

    def test_screenshot_failure_uses_empty_string(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value=""):
            with patch.object(eng, "_build_app_context", return_value=""):
                with patch("core.screenshot.capture_screen", side_effect=OSError("no screen")):
                    with patch.object(eng, "_add_vision_message") as mock_vision:
                        eng._build_initial_messages("goal")

        # Should still call _add_vision_message with empty string
        mock_vision.assert_called_once()
        call_args = mock_vision.call_args[0]
        assert call_args[1] == ""

    def test_goal_included_in_vision_message(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value=""):
            with patch.object(eng, "_build_app_context", return_value=""):
                with patch("core.engine.capture_to_base64", return_value="b64"):
                    with patch.object(eng, "_add_vision_message") as mock_vision:
                        eng._build_initial_messages("Open Firefox")

        # The goal should appear in the vision message text
        call_args = mock_vision.call_args[0]
        assert "Open Firefox" in call_args[2]

    def test_add_vision_message_called_with_messages_list(self):
        eng = self._make_engine()
        with patch.object(eng, "_build_env_context", return_value=""):
            with patch.object(eng, "_build_app_context", return_value=""):
                with patch("core.engine.capture_to_base64", return_value="b64"):
                    with patch.object(eng, "_add_vision_message") as mock_vision:
                        msgs = eng._build_initial_messages("goal")

        # First arg to _add_vision_message should be the messages list
        assert mock_vision.call_args[0][0] is msgs
