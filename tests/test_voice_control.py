"""
Tests for the v30.0.0 Voice Control module.
"""
from core.voice.control import check_wake_word, extract_goal, get_voice_status, VoiceResult


class TestWakeWord:
    def test_wake_word_present(self):
        assert check_wake_word("hey sentinel open notepad")

    def test_wake_word_absent(self):
        assert not check_wake_word("open notepad")

    def test_case_insensitive(self):
        assert check_wake_word("Hey SENTINEL do something")


class TestExtractGoal:
    def test_extract_with_wake_word(self):
        goal = extract_goal("hey sentinel open notepad and type hello")
        assert goal == "open notepad and type hello"

    def test_extract_without_wake_word(self):
        goal = extract_goal("just open notepad")
        assert goal == "just open notepad"


class TestVoiceStatus:
    def test_status_returns_dict(self):
        status = get_voice_status()
        assert "tts_engine" in status
        assert "stt_engine" in status
        assert "wake_word" in status


class TestVoiceResult:
    def test_dataclass(self):
        r = VoiceResult(success=True, text="hello")
        assert r.success
        assert r.text == "hello"
