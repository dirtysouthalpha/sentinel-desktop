"""Tests for core.web.web_recorder — browser action recording."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.web.web_recorder import WebRecorder, WebRecording


class TestWebRecording:
    def test_empty_recording(self):
        rec = WebRecording(name="test", goal="test goal")
        assert rec.step_count == 0
        assert rec.name == "test"
        assert rec.goal == "test goal"

    def test_add_action(self):
        rec = WebRecording(name="login")
        rec.add_action(
            action={"action": "web_open", "url": "https://192.168.1.1"},
            result={"success": True},
            page_url="https://192.168.1.1",
            page_title="Login",
        )
        assert rec.step_count == 1
        assert rec.actions[0]["action"] == "web_open"
        assert rec.actions[0]["params"]["url"] == "https://192.168.1.1"
        assert rec.actions[0]["result_success"] is True
        assert rec.actions[0]["page_url"] == "https://192.168.1.1"
        assert rec.actions[0]["page_title"] == "Login"

    def test_add_action_without_extras(self):
        rec = WebRecording()
        rec.add_action(action={"action": "web_click", "selector": "#btn"})
        entry = rec.actions[0]
        assert "result_success" not in entry
        assert "page_url" not in entry
        assert "page_title" not in entry
        assert "timestamp" in entry

    def test_params_exclude_action_key(self):
        rec = WebRecording()
        rec.add_action({"action": "web_type", "text": "admin", "selector": "#user"})
        assert "action" not in rec.actions[0]["params"]
        assert rec.actions[0]["params"]["text"] == "admin"

    def test_multiple_actions(self):
        rec = WebRecording(name="multi")
        rec.add_action({"action": "web_open", "url": "https://x.com"})
        rec.add_action({"action": "web_type", "text": "admin"})
        rec.add_action({"action": "web_click", "selector": "#login"})
        assert rec.step_count == 3

    def test_to_dict(self):
        rec = WebRecording(name="test", goal="do things")
        rec.add_action({"action": "web_open", "url": "https://x.com"})
        d = rec.to_dict()
        assert d["version"] == "2.0"
        assert d["type"] == "web_recording"
        assert d["name"] == "test"
        assert d["goal"] == "do things"
        assert d["steps_total"] == 1
        assert len(d["actions"]) == 1

    def test_to_json(self):
        rec = WebRecording(name="json_test")
        rec.add_action({"action": "web_open", "url": "https://x.com"})
        j = rec.to_json()
        parsed = json.loads(j)
        assert parsed["name"] == "json_test"
        assert parsed["actions"][0]["action"] == "web_open"

    def test_save_and_load(self, tmp_path: Path):
        filepath = tmp_path / "recording.json"
        rec = WebRecording(name="persist", goal="login flow")
        rec.add_action({"action": "web_open", "url": "https://fw.local"})
        rec.add_action({"action": "web_type", "text": "admin", "selector": "#user"})
        rec.save(filepath)

        loaded = WebRecording.load(filepath)
        assert loaded.name == "persist"
        assert loaded.goal == "login flow"
        assert loaded.step_count == 2
        assert loaded.actions[0]["action"] == "web_open"

    def test_from_dict(self):
        data = {
            "name": "dict_test",
            "goal": "test",
            "created_at": "2026-01-01T00:00:00",
            "actions": [
                {"action": "web_click", "params": {"selector": "#btn"}},
            ],
        }
        rec = WebRecording.from_dict(data)
        assert rec.name == "dict_test"
        assert rec.step_count == 1

    def test_save_creates_directory(self, tmp_path: Path):
        filepath = tmp_path / "deep" / "nested" / "rec.json"
        rec = WebRecording(name="deep")
        rec.add_action({"action": "web_open", "url": "https://x.com"})
        rec.save(filepath)
        assert filepath.exists()


class TestWebRecorder:
    def test_start_sets_active(self):
        rec = WebRecorder()
        assert rec.is_recording is False
        rec.start(name="test")
        assert rec.is_recording is True

    def test_stop_returns_recording(self):
        rec = WebRecorder()
        rec.start(name="test", goal="test goal")
        recording = rec.stop()
        assert recording is not None
        assert recording.name == "test"
        assert recording.goal == "test goal"
        assert rec.is_recording is False

    def test_stop_when_not_recording(self):
        rec = WebRecorder()
        assert rec.stop() is None

    def test_capture_web_action(self):
        rec = WebRecorder()
        rec.start(name="cap")
        captured = rec.capture({"action": "web_open", "url": "https://x.com"})
        assert captured is True
        assert rec.current_recording is not None
        assert rec.current_recording.step_count == 1

    def test_capture_ignores_native_actions(self):
        rec = WebRecorder()
        rec.start(name="cap")
        captured = rec.capture({"action": "click", "x": 100, "y": 200})
        assert captured is False
        assert rec.current_recording.step_count == 0

    def test_capture_ignores_when_not_recording(self):
        rec = WebRecorder()
        captured = rec.capture({"action": "web_open", "url": "https://x.com"})
        assert captured is False

    def test_capture_with_result_and_page_info(self):
        rec = WebRecorder()
        rec.start(name="cap")
        rec.capture(
            {"action": "web_open", "url": "https://fw.local"},
            result={"success": True},
            page_url="https://fw.local/login",
            page_title="Firewall Login",
        )
        entry = rec.current_recording.actions[0]
        assert entry["result_success"] is True
        assert entry["page_url"] == "https://fw.local/login"
        assert entry["page_title"] == "Firewall Login"

    def test_full_workflow(self):
        """Start → capture multiple actions → stop → save → reload."""
        rec = WebRecorder()
        rec.start(name="login_flow", goal="Login to firewall")

        rec.capture({"action": "web_open", "url": "https://192.168.1.1"})
        rec.capture({"action": "web_type", "text": "admin", "selector": "#user"})
        rec.capture({"action": "web_type", "text": "secret", "selector": "#pass"})
        rec.capture({"action": "web_click", "selector": "#login"})

        recording = rec.stop()
        assert recording is not None
        assert recording.step_count == 4
        assert rec.is_recording is False

    def test_all_web_actions_are_recordable(self):
        """Every web action type should be captured."""
        rec = WebRecorder()
        rec.start(name="all")
        web_actions = [
            "web_open", "web_click", "web_type", "web_read", "web_extract",
            "web_wait_for", "web_screenshot", "web_eval_js", "web_download",
            "web_upload", "web_tabs",
        ]
        for action_name in web_actions:
            captured = rec.capture({"action": action_name})
            assert captured is True, f"{action_name} was not recorded"

        assert rec.current_recording.step_count == 11

    def test_current_recording_none_when_not_active(self):
        rec = WebRecorder()
        assert rec.current_recording is None
