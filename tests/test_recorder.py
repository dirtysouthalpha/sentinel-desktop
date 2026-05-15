"""Tests for the action recorder and Script data model."""

import json

import pytest

from core.recorder import ActionRecorder, Script

# ---------------------------------------------------------------------------
# Script data model tests
# ---------------------------------------------------------------------------


def test_script_to_round_trip(tmp_path):
    """Script.save + Script.load should produce an equivalent Script."""
    original = Script(
        name="Test Script",
        description="A test",
        tags=["smoke"],
        steps=[{"action": "click", "params": {"x": 100, "y": 200}}],
    )
    path = str(tmp_path / "test.json")
    original.save(path)
    loaded = Script.load(path)

    assert loaded.name == "Test Script"
    assert loaded.description == "A test"
    assert loaded.tags == ["smoke"]
    assert len(loaded.steps) == 1
    assert loaded.steps[0]["action"] == "click"


def test_script_to_dict_keys():
    """to_dict should return all expected keys."""
    s = Script(name="X")
    d = s.to_dict()

    for key in (
        "name",
        "description",
        "author",
        "created",
        "version",
        "tags",
        "parameters",
        "steps",
    ):
        assert key in d


def test_script_to_json_is_valid():
    """to_json should produce valid JSON."""
    s = Script(name="JSON Test")
    parsed = json.loads(s.to_json())
    assert parsed["name"] == "JSON Test"


def test_script_save_creates_parent_dirs(tmp_path):
    """save should create missing parent directories."""
    path = str(tmp_path / "deep" / "nested" / "script.json")
    Script(name="Nested").save(path)
    loaded = Script.load(path)
    assert loaded.name == "Nested"


def test_script_save_io_error(tmp_path):
    """save should log and re-raise OSError when the write fails."""
    from unittest.mock import patch

    script = Script(name="Bad")
    with patch("builtins.open", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            script.save(str(tmp_path / "script.json"))


def test_script_load_missing_file(tmp_path):
    """load should raise OSError for missing files."""
    with pytest.raises(OSError):
        Script.load(str(tmp_path / "nonexistent.json"))


def test_script_load_invalid_json(tmp_path):
    """load should raise JSONDecodeError for invalid JSON."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        Script.load(str(bad))


def test_script_load_missing_keys_uses_defaults(tmp_path):
    """load should use defaults when JSON keys are missing."""
    path = tmp_path / "minimal.json"
    path.write_text("{}", encoding="utf-8")
    s = Script.load(str(path))

    assert s.name == "Untitled Script"
    assert s.description == ""
    assert s.steps == []


# ---------------------------------------------------------------------------
# ActionRecorder tests
# ---------------------------------------------------------------------------


def test_recorder_lifecycle():
    """start → capture → stop should produce a Script with steps."""
    rec = ActionRecorder()
    rec.start_recording("Test goal")

    rec.capture_action(
        {"type": "click", "params": {"x": 10, "y": 20}},
        {"status": "done"},
    )
    rec.capture_action(
        {"type": "type", "params": {"text": "hello"}},
        {"status": "done"},
    )

    script = rec.stop_recording()
    assert script.name  # auto-generated
    assert len(script.steps) == 2
    assert script.steps[0]["action"] == "click"
    assert script.steps[1]["action"] == "type"


def test_recorder_not_recording_captures_nothing():
    """capture_action outside a recording session should be a no-op."""
    rec = ActionRecorder()
    rec.capture_action({"type": "click", "params": {}}, {"status": "ok"})
    # Not recording, so nothing should happen


def test_recorder_double_start_raises():
    """Starting a recording while already recording should raise."""
    rec = ActionRecorder()
    rec.start_recording("first")
    with pytest.raises(RuntimeError, match="already in progress"):
        rec.start_recording("second")


def test_recorder_stop_without_start_raises():
    """Stopping without a recording should raise."""
    rec = ActionRecorder()
    with pytest.raises(RuntimeError, match="No recording"):
        rec.stop_recording()


def test_recorder_is_recording_property():
    rec = ActionRecorder()
    assert rec.is_recording is False
    rec.start_recording("x")
    assert rec.is_recording is True
    rec.stop_recording()
    assert rec.is_recording is False


def test_recorder_parameter_detection():
    """Repeated text values across steps should be promoted to parameters."""
    rec = ActionRecorder()
    rec.start_recording("test")

    for _ in range(3):
        rec.capture_action(
            {"type": "type", "params": {"text": "repeated_value"}},
            {"status": "done"},
        )

    script = rec.stop_recording()
    assert len(script.parameters) >= 1
    param_names = [p["name"] for p in script.parameters]
    assert "repeated_value" in param_names


def test_generate_description_empty():
    desc = ActionRecorder.generate_description([])
    assert "no actions" in desc.lower() or "empty" in desc.lower()


def test_generate_description_single():
    desc = ActionRecorder.generate_description([{"action": "click", "params": {"x": 1, "y": 2}}])
    assert "1 step" in desc


def test_generate_description_multiple():
    steps = [
        {"action": "click", "params": {"text": "OK"}},
        {"action": "type", "params": {"text": "hello"}},
        {"action": "click", "params": {"text": "Submit"}},
    ]
    desc = ActionRecorder.generate_description(steps)
    assert "3 steps" in desc


def test_list_scripts(tmp_path):
    """list_scripts should find .json files and skip invalid ones."""
    valid = tmp_path / "good.json"
    valid.write_text(
        json.dumps({"name": "Good Script", "description": "x", "tags": []}), encoding="utf-8"
    )

    invalid = tmp_path / "bad.json"
    invalid.write_text("not json", encoding="utf-8")

    results = ActionRecorder.list_scripts(str(tmp_path))
    assert len(results) == 1
    assert results[0]["name"] == "Good Script"


def test_save_and_load_script_convenience(tmp_path):
    """Static convenience methods should work."""
    script = Script(name="Convenience Test")
    path = str(tmp_path / "conv.json")
    ActionRecorder.save_script(script, path)
    loaded = ActionRecorder.load_script(path)
    assert loaded.name == "Convenience Test"
