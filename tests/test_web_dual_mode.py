"""Tests for core.web.dual_mode — dual-mode detection."""

from __future__ import annotations

import pytest

from core.web.dual_mode import (
    InteractionMode,
    classify_handoff,
    detect_mode_from_action,
    detect_mode_from_goal,
)


class TestDetectModeFromGoal:
    def test_url_triggers_web(self):
        assert detect_mode_from_goal("Go to https://192.168.1.1") == InteractionMode.WEB

    def test_ip_address_triggers_web(self):
        assert detect_mode_from_goal("Login to 10.0.0.1 firewall") == InteractionMode.WEB

    def test_localhost_triggers_web(self):
        assert detect_mode_from_goal("Open localhost:8080") == InteractionMode.WEB

    def test_http_url_triggers_web(self):
        assert detect_mode_from_goal("Navigate to http://router.local") == InteractionMode.WEB

    def test_keyword_browser(self):
        assert detect_mode_from_goal("Open the browser and check the SonicWall") == InteractionMode.WEB

    def test_keyword_firewall_ui(self):
        assert detect_mode_from_goal("Configure the firewall UI") == InteractionMode.WEB

    def test_keyword_portal(self):
        assert detect_mode_from_goal("Log into the admin portal") == InteractionMode.WEB

    def test_keyword_dashboard(self):
        assert detect_mode_from_goal("Check the NinjaOne dashboard") == InteractionMode.WEB

    def test_keyword_web_app(self):
        assert detect_mode_from_goal("Use the web app to export data") == InteractionMode.WEB

    def test_native_goal_open_excel(self):
        assert detect_mode_from_goal("Open Excel and create a spreadsheet") == InteractionMode.NATIVE

    def test_native_goal_move_file(self):
        assert detect_mode_from_goal("Move the file from Downloads to Documents") == InteractionMode.NATIVE

    def test_native_goal_print(self):
        assert detect_mode_from_goal("Print the document") == InteractionMode.NATIVE

    def test_empty_goal(self):
        assert detect_mode_from_goal("") == InteractionMode.NATIVE

    def test_case_insensitive(self):
        assert detect_mode_from_goal("CHECK THE FORTIGATE HTTPS://10.0.0.1") == InteractionMode.WEB

    def test_appliance_names(self):
        for name in ["sonicwall", "fortigate", "unifi", "meraki", "pfsense"]:
            assert detect_mode_from_goal(f"Login to {name}") == InteractionMode.WEB


class TestDetectModeFromAction:
    def test_web_open_action(self):
        assert detect_mode_from_action({"action": "web_open", "url": "https://x.com"}) == InteractionMode.WEB

    def test_web_click_action(self):
        assert detect_mode_from_action({"action": "web_click", "selector": "#btn"}) == InteractionMode.WEB

    def test_web_type_action(self):
        assert detect_mode_from_action({"action": "web_type", "text": "hello"}) == InteractionMode.WEB

    def test_web_read_action(self):
        assert detect_mode_from_action({"action": "web_read"}) == InteractionMode.WEB

    def test_web_extract_action(self):
        assert detect_mode_from_action({"action": "web_extract"}) == InteractionMode.WEB

    def test_web_screenshot_action(self):
        assert detect_mode_from_action({"action": "web_screenshot"}) == InteractionMode.WEB

    def test_web_eval_js_action(self):
        assert detect_mode_from_action({"action": "web_eval_js"}) == InteractionMode.WEB

    def test_web_download_action(self):
        assert detect_mode_from_action({"action": "web_download"}) == InteractionMode.WEB

    def test_web_upload_action(self):
        assert detect_mode_from_action({"action": "web_upload"}) == InteractionMode.WEB

    def test_web_tabs_action(self):
        assert detect_mode_from_action({"action": "web_tabs"}) == InteractionMode.WEB

    def test_native_click_action(self):
        assert detect_mode_from_action({"action": "click", "x": 100, "y": 200}) == InteractionMode.NATIVE

    def test_native_type_text_action(self):
        assert detect_mode_from_action({"action": "type_text", "text": "hi"}) == InteractionMode.NATIVE

    def test_native_open_app_action(self):
        assert detect_mode_from_action({"action": "open_app", "name": "Excel"}) == InteractionMode.NATIVE

    def test_unknown_action_defaults_native(self):
        assert detect_mode_from_action({"action": "unknown_thing"}) == InteractionMode.NATIVE

    def test_empty_action_defaults_native(self):
        assert detect_mode_from_action({}) == InteractionMode.NATIVE


class TestClassifyHandoff:
    def test_no_handoff_same_mode(self):
        assert classify_handoff(InteractionMode.NATIVE, {"action": "click", "x": 1, "y": 2}) is None
        assert classify_handoff(InteractionMode.WEB, {"action": "web_click", "selector": "#x"}) is None

    def test_handoff_native_to_web(self):
        result = classify_handoff(InteractionMode.NATIVE, {"action": "web_open", "url": "https://x.com"})
        assert result == InteractionMode.WEB

    def test_handoff_web_to_native(self):
        result = classify_handoff(InteractionMode.WEB, {"action": "click", "x": 100, "y": 200})
        assert result == InteractionMode.NATIVE
