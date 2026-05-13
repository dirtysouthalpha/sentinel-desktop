"""Engine must surface clear errors AND reset state when not configured."""

from core.engine import AgentEngine


def test_missing_api_key_returns_error_and_resets_running():
    eng = AgentEngine({"provider": "openai", "model": "gpt-4o", "api_key": ""})
    result = eng.run("do something")
    assert result["steps"] == 0
    assert result["error"] == "api_key_missing"
    assert any("API key" in n for n in result["notes"])
    # Critical: the engine must not stay "running" — otherwise the GUI's
    # "agent already running" check blocks the next goal forever.
    assert eng.running is False


def test_missing_model_returns_error_and_resets_running():
    eng = AgentEngine({"provider": "openai", "api_key": "sk-test", "model": ""})
    result = eng.run("do something")
    assert result["steps"] == 0
    assert result["error"] == "model_missing"
    assert eng.running is False


def test_missing_provider_returns_error_and_resets_running():
    eng = AgentEngine({"provider": "", "api_key": "x", "model": "y"})
    result = eng.run("do something")
    assert result["steps"] == 0
    assert result["error"] in ("api_key_missing", "provider_missing")
    assert eng.running is False


def test_local_providers_dont_need_api_key():
    # Ollama / LM Studio run locally — no key required, so the early-return
    # path for missing api_key must NOT fire for them.
    eng = AgentEngine({"provider": "ollama", "api_key": "", "model": ""})
    result = eng.run("do something")
    # It'll still fail on missing model, but NOT on api_key.
    assert result["error"] == "model_missing"
