"""
Tests for core/app_profiles.py — Application profile detection and lookup.

Covers detect_profile, get_profile, list_profiles, get_timing_for_app,
and the AppProfile dataclass.
"""

from __future__ import annotations

from core.app_profiles import (
    PROFILES,
    AppProfile,
    detect_profile,
    get_profile,
    get_timing_for_app,
    list_profiles,
)

# ── Tests: AppProfile dataclass ───────────────────────────────────────────


class TestAppProfileDataclass:
    """Tests for the AppProfile dataclass itself."""

    def test_default_timing_values(self):
        p = AppProfile(name="test", display_name="Test App", window_title_patterns=["Test"])
        assert p.timing["launch_delay"] == 2.0
        assert p.timing["action_delay"] == 0.3
        assert p.timing["page_load_delay"] == 2.0

    def test_default_stealth_compatible(self):
        p = AppProfile(name="test", display_name="Test App", window_title_patterns=["Test"])
        assert p.stealth_compatible == "partial"

    def test_default_preferred_input(self):
        p = AppProfile(name="test", display_name="Test App", window_title_patterns=["Test"])
        assert p.preferred_input == "uia"

    def test_custom_fields(self):
        p = AppProfile(
            name="custom",
            display_name="Custom App",
            window_title_patterns=["Custom"],
            stealth_compatible="none",
            preferred_input="physical",
            timing={"launch_delay": 5.0, "action_delay": 1.0, "page_load_delay": 3.0},
            known_controls={"main": "MainWindow"},
            menu_paths={"save": ["File", "Save"]},
            quirks=["weird"],
            strategies={"action": "do it"},
        )
        assert p.stealth_compatible == "none"
        assert p.preferred_input == "physical"
        assert p.timing["launch_delay"] == 5.0
        assert p.known_controls["main"] == "MainWindow"
        assert len(p.quirks) == 1


# ── Tests: detect_profile ─────────────────────────────────────────────────


class TestDetectProfile:
    """Tests for core.app_profiles.detect_profile."""

    def test_detects_chrome(self):
        profile = detect_profile("New Tab - Google Chrome")
        assert profile is not None
        assert profile.name == "chrome"

    def test_detects_edge(self):
        profile = detect_profile("Settings - Microsoft Edge")
        assert profile is not None
        assert profile.name == "edge"

    def test_detects_firefox(self):
        profile = detect_profile("Mozilla Firefox")
        assert profile is not None
        assert profile.name == "firefox"

    def test_detects_excel(self):
        profile = detect_profile("Book1 - Microsoft Excel")
        assert profile is not None
        assert profile.name == "excel"

    def test_detects_word(self):
        profile = detect_profile("Document1 - Microsoft Word")
        assert profile is not None
        assert profile.name == "word"

    def test_detects_outlook(self):
        profile = detect_profile("Inbox - Microsoft Outlook")
        assert profile is not None
        assert profile.name == "outlook"

    def test_detects_notepad(self):
        profile = detect_profile("Untitled - Notepad")
        assert profile is not None
        assert profile.name == "notepad"

    def test_detects_vscode(self):
        profile = detect_profile("main.py - Visual Studio Code")
        assert profile is not None
        assert profile.name == "vscode"

    def test_detects_file_explorer(self):
        profile = detect_profile("File Explorer")
        assert profile is not None
        assert profile.name == "file_explorer"

    def test_detects_teams(self):
        profile = detect_profile("Microsoft Teams")
        assert profile is not None
        assert profile.name == "teams"

    def test_detects_cmd(self):
        profile = detect_profile("Command Prompt")
        assert profile is not None
        assert profile.name == "cmd"

    def test_detects_powershell(self):
        profile = detect_profile("Windows PowerShell")
        assert profile is not None
        assert profile.name == "powershell"

    def test_detects_task_manager(self):
        profile = detect_profile("Task Manager")
        assert profile is not None
        assert profile.name == "task_manager"

    def test_detects_settings(self):
        profile = detect_profile("Settings")
        assert profile is not None
        assert profile.name == "settings"

    def test_detects_live2d(self):
        profile = detect_profile("Live2D Cubism Editor")
        assert profile is not None
        assert profile.name == "live2d_cubism"

    def test_empty_string_returns_none(self):
        assert detect_profile("") is None

    def test_unknown_window_returns_none(self):
        assert detect_profile("Totally Unknown App Window") is None

    def test_case_insensitive_match(self):
        profile = detect_profile("GOOGLE CHROME")
        assert profile is not None
        assert profile.name == "chrome"

    def test_partial_title_match(self):
        profile = detect_profile("Some Project - Visual Studio Code - [Workspace]")
        assert profile is not None
        assert profile.name == "vscode"


# ── Tests: get_profile ────────────────────────────────────────────────────


class TestGetProfile:
    """Tests for core.app_profiles.get_profile."""

    def test_returns_existing_profile(self):
        profile = get_profile("chrome")
        assert profile is not None
        assert profile.name == "chrome"
        assert profile.display_name == "Google Chrome"

    def test_returns_none_for_unknown(self):
        assert get_profile("nonexistent_app_xyz") is None

    def test_returns_all_builtin_profiles(self):
        expected = [
            "chrome",
            "edge",
            "firefox",
            "excel",
            "word",
            "outlook",
            "notepad",
            "vscode",
            "live2d_cubism",
            "file_explorer",
            "teams",
            "cmd",
            "powershell",
            "task_manager",
            "settings",
        ]
        for name in expected:
            assert get_profile(name) is not None, f"Missing profile: {name}"


# ── Tests: list_profiles ──────────────────────────────────────────────────


class TestListProfiles:
    """Tests for core.app_profiles.list_profiles."""

    def test_returns_list(self):
        profiles = list_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) >= 15

    def test_all_are_app_profile_instances(self):
        profiles = list_profiles()
        for p in profiles:
            assert isinstance(p, AppProfile)

    def test_profiles_have_required_fields(self):
        for p in list_profiles():
            assert p.name
            assert p.display_name
            assert isinstance(p.window_title_patterns, list)
            assert len(p.window_title_patterns) > 0


# ── Tests: get_timing_for_app ─────────────────────────────────────────────


class TestGetTimingForApp:
    """Tests for core.app_profiles.get_timing_for_app."""

    def test_returns_profile_timing_when_matched(self):
        timing = get_timing_for_app("Something - Google Chrome")
        assert timing["launch_delay"] == 3.0
        assert timing["action_delay"] == 0.3
        assert timing["page_load_delay"] == 3.0

    def test_returns_defaults_when_no_match(self):
        timing = get_timing_for_app("Unknown App")
        assert timing["launch_delay"] == 2.0
        assert timing["action_delay"] == 0.3
        assert timing["page_load_delay"] == 2.0

    def test_excel_has_custom_timing(self):
        timing = get_timing_for_app("Book1 - Microsoft Excel")
        assert timing["launch_delay"] == 4.0
        assert timing["action_delay"] == 0.2

    def test_notepad_has_fast_timing(self):
        timing = get_timing_for_app("Untitled - Notepad")
        assert timing["launch_delay"] == 1.0
        assert timing["action_delay"] == 0.1


# ── Tests: PROFILES dict integrity ────────────────────────────────────────


class TestProfilesIntegrity:
    """Integrity checks for the PROFILES dictionary."""

    def test_profile_keys_match_names(self):
        for key, profile in PROFILES.items():
            assert key == profile.name, f"Key '{key}' doesn't match profile.name '{profile.name}'"

    def test_all_profiles_have_unique_names(self):
        names = [p.name for p in PROFILES.values()]
        assert len(names) == len(set(names)), "Duplicate profile names found"

    def test_all_stealth_compatible_values_valid(self):
        valid = {"full", "partial", "none"}
        for profile in PROFILES.values():
            assert profile.stealth_compatible in valid, (
                f"{profile.name}: invalid stealth_compatible '{profile.stealth_compatible}'"
            )

    def test_all_preferred_input_values_valid(self):
        valid = {"uia", "postmessage", "physical"}
        for profile in PROFILES.values():
            assert profile.preferred_input in valid, (
                f"{profile.name}: invalid preferred_input '{profile.preferred_input}'"
            )

    def test_all_timing_fields_are_positive(self):
        for profile in PROFILES.values():
            for key, value in profile.timing.items():
                assert value > 0, f"{profile.name}.timing[{key}] = {value}, expected > 0"

    def test_all_window_patterns_are_nonempty_strings(self):
        for profile in PROFILES.values():
            for pattern in profile.window_title_patterns:
                assert isinstance(pattern, str) and len(pattern) > 0, (
                    f"{profile.name}: empty or non-string pattern"
                )
