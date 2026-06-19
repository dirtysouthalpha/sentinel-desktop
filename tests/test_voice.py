"""Tests for core/voice.py (v22.0 — VoiceEngine)."""

from __future__ import annotations

import time
from unittest.mock import patch

from core.voice import VoiceEngine, VoiceMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine(**kwargs) -> VoiceEngine:
    return VoiceEngine(wake_word="sentinel", listen_timeout=0.1, **kwargs)


# ---------------------------------------------------------------------------
# Init + mode state
# ---------------------------------------------------------------------------


def test_default_mode_is_idle():
    eng = make_engine()
    assert eng.mode == VoiceMode.IDLE


def test_wake_word_stored_lowercase():
    eng = VoiceEngine(wake_word="SENTINEL")
    assert eng.wake_word == "sentinel"


def test_status_keys():
    eng = make_engine()
    s = eng.status()
    assert set(s.keys()) == {"mode", "wake_word", "is_ambient"}
    assert s["mode"] == VoiceMode.IDLE.value
    assert s["wake_word"] == "sentinel"
    assert s["is_ambient"] is False


# ---------------------------------------------------------------------------
# speak() wrapper
# ---------------------------------------------------------------------------


def test_speak_delegates_and_restores_mode():
    eng = make_engine()
    with patch("core.voice.speak", return_value=True) as mock_speak:
        result = eng.speak("hello", blocking=True)

    assert result is True
    mock_speak.assert_called_once_with("hello", blocking=True)
    assert eng.mode == VoiceMode.IDLE


def test_speak_sets_speaking_mode_then_restores(monkeypatch):
    eng = make_engine()
    observed = []

    def fake_speak(text, blocking):
        observed.append(eng.mode)
        return True

    monkeypatch.setattr("core.voice.speak", fake_speak)
    eng.speak("hi", blocking=True)
    assert VoiceMode.SPEAKING in observed
    assert eng.mode == VoiceMode.IDLE


# ---------------------------------------------------------------------------
# listen_once() wrapper
# ---------------------------------------------------------------------------


def test_listen_once_delegates():
    eng = make_engine()
    with patch("core.voice.listen", return_value="hello world") as mock_listen:
        transcript = eng.listen_once(timeout=2.0)

    assert transcript == "hello world"
    mock_listen.assert_called_once_with(timeout=2.0)
    assert eng.mode == VoiceMode.IDLE


def test_listen_once_uses_engine_timeout_when_not_passed():
    eng = VoiceEngine(listen_timeout=7.5)
    with patch("core.voice.listen", return_value="") as mock_listen:
        eng.listen_once()
    mock_listen.assert_called_once_with(timeout=7.5)


# ---------------------------------------------------------------------------
# Ambient mode
# ---------------------------------------------------------------------------


def test_start_ambient_returns_true():
    eng = make_engine()
    with patch("core.voice.listen", return_value=""):
        started = eng.start_ambient()
        assert started is True
        assert eng.is_ambient is True
        eng.stop_ambient()


def test_start_ambient_idempotent():
    eng = make_engine()
    with patch("core.voice.listen", return_value=""):
        eng.start_ambient()
        second = eng.start_ambient()
        assert second is False
        eng.stop_ambient()


def test_stop_ambient_returns_true_when_running():
    eng = make_engine()
    with patch("core.voice.listen", return_value=""):
        eng.start_ambient()
        stopped = eng.stop_ambient()
    assert stopped is True
    assert eng.is_ambient is False


def test_stop_ambient_returns_false_when_not_running():
    eng = make_engine()
    stopped = eng.stop_ambient()
    assert stopped is False


def test_ambient_fires_on_wake_callback():
    called = []
    eng = VoiceEngine(
        wake_word="sentinel",
        listen_timeout=0.05,
        on_wake=lambda t: called.append(t),
    )
    # First call returns the wake word, subsequent calls return ""
    responses = ["I hear sentinel now", "", ""]

    def fake_listen(timeout, phrase_limit):
        return responses.pop(0) if responses else ""

    with patch("core.voice.listen", side_effect=fake_listen):
        eng.start_ambient()
        time.sleep(0.3)
        eng.stop_ambient()

    assert len(called) >= 1
    assert "sentinel" in called[0].lower()


def test_ambient_on_wake_exception_does_not_crash():
    eng = VoiceEngine(
        wake_word="sentinel",
        listen_timeout=0.05,
        on_wake=lambda t: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    responses = ["sentinel is here", ""]

    def fake_listen(timeout, phrase_limit):
        return responses.pop(0) if responses else ""

    with patch("core.voice.listen", side_effect=fake_listen):
        eng.start_ambient()
        time.sleep(0.3)
        eng.stop_ambient()  # must not raise


def test_ambient_no_wake_word_not_triggered():
    called = []
    eng = VoiceEngine(
        wake_word="sentinel",
        listen_timeout=0.05,
        on_wake=lambda t: called.append(t),
    )
    with patch("core.voice.listen", return_value="something else"):
        eng.start_ambient()
        time.sleep(0.2)
        eng.stop_ambient()

    assert len(called) == 0


def test_ambient_mode_status_while_running():
    eng = make_engine()
    with patch("core.voice.listen", return_value=""):
        eng.start_ambient()
        s = eng.status()
        assert s["is_ambient"] is True
        assert s["mode"] == VoiceMode.AMBIENT.value
        eng.stop_ambient()
    assert eng.status()["mode"] == VoiceMode.IDLE.value
