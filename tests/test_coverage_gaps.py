"""Tests for uncovered functions: read_screen_text_with_confidence, ActionExecutor.log,
LLMClient.chat.
"""

from unittest.mock import MagicMock

import pytest

import core.desktop as desktop_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeDesktop:
    def __init__(self):
        self.calls = []

    def click(self, *a, **kw):
        self.calls.append(("click", a, kw))


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor

    return ActionExecutor


# ---------------------------------------------------------------------------
# ActionExecutor.log property
# ---------------------------------------------------------------------------


class TestActionExecutorLog:
    def test_log_starts_empty(self, fake_executor):
        ex = fake_executor()
        assert ex.log == []

    def test_log_records_successful_action(self, fake_executor):
        ex = fake_executor()
        ex.execute_sync({"action": "note", "text": "hello"})
        assert len(ex.log) == 1
        entry = ex.log[0]
        assert entry["action"] == "note"
        assert entry["success"] is True

    def test_log_records_failed_action(self, fake_executor):
        ex = fake_executor()
        ex.execute_sync({"action": "warp_drive"})
        assert len(ex.log) == 1
        entry = ex.log[0]
        assert entry["action"] == "warp_drive"
        assert entry["success"] is False

    def test_log_accumulates_across_actions(self, fake_executor):
        ex = fake_executor()
        ex.execute_sync({"action": "note", "text": "a"})
        ex.execute_sync({"action": "note", "text": "b"})
        assert len(ex.log) == 2

    def test_log_sanitizes_long_params(self, fake_executor):
        ex = fake_executor()
        long_text = "x" * 500
        ex.execute_sync({"action": "note", "text": long_text})
        assert len(ex.log) == 1
        entry = ex.log[0]
        param_val = entry["params"].get("text", "")
        assert len(param_val) < 500

    def test_log_returns_new_list_each_call(self, fake_executor):
        ex = fake_executor()
        log1 = ex.log
        log2 = ex.log
        assert log1 is not log2
        assert log1 == log2


# ---------------------------------------------------------------------------
# read_screen_text_with_confidence
# ---------------------------------------------------------------------------


class TestReadScreenTextWithConfidence:
    def test_returns_empty_when_tesseract_unavailable(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "have_tesseract", lambda: False)
        text, conf = ocr.read_screen_text_with_confidence()
        assert text == ""
        assert conf["avg_confidence"] == 0
        assert conf["word_count"] == 0
        assert conf["low_confidence_words"] == []
        assert conf["low_confidence_regions"] == []

    def test_returns_ocr_result_with_confidence(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "have_tesseract", lambda: True)

        fake_img = MagicMock()
        monkeypatch.setattr(ocr, "capture_screen", lambda monitor=None: fake_img)

        expected_conf = {
            "avg_confidence": 85.3,
            "word_count": 12,
            "low_confidence_words": [],
            "low_confidence_regions": [],
        }
        monkeypatch.setattr(
            ocr,
            "_ocr_image_with_confidence",
            lambda img, preprocess=True: ("Hello World", expected_conf),
        )

        text, conf = ocr.read_screen_text_with_confidence()
        assert text == "Hello World"
        assert conf["avg_confidence"] == 85.3
        assert conf["word_count"] == 12

    def test_returns_empty_on_capture_exception(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "have_tesseract", lambda: True)
        monkeypatch.setattr(
            ocr,
            "capture_screen",
            lambda monitor=None: (_ for _ in ()).throw(RuntimeError("no screen")),
        )

        text, conf = ocr.read_screen_text_with_confidence()
        assert text == ""
        assert conf["avg_confidence"] == 0

    def test_passes_monitor_param(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "have_tesseract", lambda: True)

        captured_monitor = {}

        def mock_capture(monitor=None):
            captured_monitor["value"] = monitor
            return MagicMock()

        monkeypatch.setattr(ocr, "capture_screen", mock_capture)
        monkeypatch.setattr(
            ocr,
            "_ocr_image_with_confidence",
            lambda img, preprocess=True: (
                "",
                {
                    "avg_confidence": 0,
                    "word_count": 0,
                    "low_confidence_words": [],
                    "low_confidence_regions": [],
                },
            ),
        )

        ocr.read_screen_text_with_confidence(monitor=2)
        assert captured_monitor["value"] == 2


# ---------------------------------------------------------------------------
# LLMClient.chat — OpenAI-compatible path (non-Anthropic)
# ---------------------------------------------------------------------------


class TestLLMClientChatOpenAI:
    def test_chat_returns_text_content(self, monkeypatch):
        from core.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from GPT!"}}],
        }

        monkeypatch.setattr("requests.post", lambda *a, **kw: mock_response)

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])
        assert result == "Hello from GPT!"

    def test_chat_returns_tool_calls_json(self, monkeypatch):
        import json

        from core.llm_client import LLMClient

        tool_calls = [
            {"id": "tc1", "type": "function", "function": {"name": "click", "arguments": "{}"}}
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"tool_calls": tool_calls}}],
        }

        monkeypatch.setattr("requests.post", lambda *a, **kw: mock_response)

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Click"}])
        parsed = json.loads(result)
        assert "tool_calls" in parsed
        assert len(parsed["tool_calls"]) == 1

    def test_chat_raises_on_error_envelope(self, monkeypatch):
        from core.llm_client import LLMClient, LLMError

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": {"message": "model overloaded"},
        }

        monkeypatch.setattr("requests.post", lambda *a, **kw: mock_response)

        client = LLMClient()
        with pytest.raises(LLMError, match="model overloaded"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])

    def test_chat_raises_on_empty_choices(self, monkeypatch):
        from core.llm_client import LLMClient, LLMError

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}

        monkeypatch.setattr("requests.post", lambda *a, **kw: mock_response)

        client = LLMClient()
        with pytest.raises(LLMError, match="no 'choices'"):
            client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])

    def test_chat_handles_list_content(self, monkeypatch):
        from core.llm_client import LLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "Part1"},
                            {"type": "text", "text": "Part2"},
                        ]
                    }
                }
            ],
        }

        monkeypatch.setattr("requests.post", lambda *a, **kw: mock_response)

        client = LLMClient()
        result = client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}])
        assert "Part1" in result
        assert "Part2" in result

    def test_chat_passes_tools_in_payload(self, monkeypatch):
        from core.llm_client import LLMClient

        captured = {}

        def mock_post(url, **kw):
            captured["payload"] = kw.get("json", {})
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "done"}}],
            }
            return mock_response

        monkeypatch.setattr("requests.post", mock_post)

        tools = [{"type": "function", "function": {"name": "click"}}]
        client = LLMClient()
        client.chat("openai", "sk-test", "gpt-4o", [{"role": "user", "content": "Hi"}], tools=tools)

        assert "tools" in captured["payload"]
        assert captured["payload"]["tool_choice"] == "auto"

    def test_chat_uses_custom_url(self, monkeypatch):
        from core.llm_client import LLMClient

        captured = {}

        def mock_post(url, **kw):
            captured["url"] = url
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "ok"}}],
            }
            return mock_response

        monkeypatch.setattr("requests.post", mock_post)

        client = LLMClient()
        client.chat(
            "openai",
            "sk-test",
            "gpt-4o",
            [{"role": "user", "content": "Hi"}],
            custom_url="https://custom.api.example.com",
        )
        assert captured["url"].startswith("https://custom.api.example.com")
