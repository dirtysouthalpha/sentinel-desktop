"""Tests for core/app_profiles.py — application detection and profiles."""

from core.app_profiles import (
    PROFILES,
    AppProfile,
    detect_profile,
    get_profile,
    get_timing_for_app,
    list_profiles,
)


class TestDetectProfile:
    def test_chrome_detected(self):
        p = detect_profile("Google Chrome")
        assert p is not None
        assert p.name == "chrome"

    def test_edge_detected(self):
        p = detect_profile("Microsoft Edge")
        assert p is not None
        assert p.name == "edge"

    def test_excel_detected(self):
        p = detect_profile("Book1 - Excel")
        assert p is not None
        assert p.name == "excel"

    def test_notepad_detected(self):
        p = detect_profile("Untitled - Notepad")
        assert p is not None
        assert p.name == "notepad"

    def test_unknown_returns_none(self):
        assert detect_profile("Some Random App") is None

    def test_empty_string_returns_none(self):
        assert detect_profile("") is None

    def test_case_insensitive(self):
        p = detect_profile("GOOGLE CHROME")
        assert p is not None
        assert p.name == "chrome"

    def test_partial_match(self):
        p = detect_profile("Settings - Windows")
        assert p is not None
        assert p.name == "settings"


class TestGetProfile:
    def test_known_profile(self):
        p = get_profile("chrome")
        assert p is not None
        assert p.name == "chrome"

    def test_unknown_returns_none(self):
        assert get_profile("nonexistent_app") is None


class TestListProfiles:
    def test_returns_all_profiles(self):
        profiles = list_profiles()
        assert len(profiles) == len(PROFILES)
        assert all(isinstance(p, AppProfile) for p in profiles)


class TestGetTimingForApp:
    def test_known_app_timing(self):
        timing = get_timing_for_app("Chrome")
        assert "launch_delay" in timing
        assert "action_delay" in timing
        assert "page_load_delay" in timing

    def test_unknown_app_defaults(self):
        timing = get_timing_for_app("Unknown App")
        assert timing == {"launch_delay": 2.0, "action_delay": 0.3, "page_load_delay": 2.0}


class TestAppProfileDataclass:
    def test_profile_has_required_fields(self):
        p = PROFILES["chrome"]
        assert p.display_name
        assert p.window_title_patterns
        assert p.stealth_compatible in ("full", "partial", "none")
        assert p.preferred_input in ("uia", "postmessage", "physical")
        assert isinstance(p.timing, dict)
        assert isinstance(p.quirks, list)

    def test_all_profiles_have_name_key(self):
        for key, profile in PROFILES.items():
            assert profile.name == key


# ---------------------------------------------------------------------------
# Additional tests for broader coverage
# ---------------------------------------------------------------------------


class TestDetectProfileAdditional:
    """Additional detect_profile tests for uncovered profiles and edge cases."""

    def test_firefox_detected(self):
        p = detect_profile("Download - Mozilla Firefox")
        assert p is not None
        assert p.name == "firefox"

    def test_word_detected(self):
        p = detect_profile("Document1 - Microsoft Word")
        assert p is not None
        assert p.name == "word"

    def test_outlook_detected(self):
        p = detect_profile("Inbox - Outlook")
        assert p is not None
        assert p.name == "outlook"

    def test_vscode_detected(self):
        p = detect_profile("main.py - Visual Studio Code")
        assert p is not None
        assert p.name == "vscode"

    def test_vscode_alias_detected(self):
        p = detect_profile("app.ts - VS Code")
        assert p is not None
        assert p.name == "vscode"

    def test_live2d_detected(self):
        p = detect_profile("model.cmo3 - Cubism Editor")
        assert p is not None
        assert p.name == "live2d_cubism"

    def test_file_explorer_detected(self):
        p = detect_profile("Downloads - File Explorer")
        assert p is not None
        assert p.name == "file_explorer"

    def test_teams_detected(self):
        p = detect_profile("Meeting - Microsoft Teams")
        assert p is not None
        assert p.name == "teams"

    def test_cmd_detected(self):
        p = detect_profile("C:\\Users\\Admin - Command Prompt")
        assert p is not None
        assert p.name == "cmd"

    def test_cmd_alias_detected(self):
        p = detect_profile("C:\\Users\\Admin - cmd.exe")
        assert p is not None
        assert p.name == "cmd"

    def test_powershell_detected(self):
        p = detect_profile("PS C:\\Users> - PowerShell")
        assert p is not None
        assert p.name == "powershell"

    def test_task_manager_detected(self):
        p = detect_profile("Task Manager")
        assert p is not None
        assert p.name == "task_manager"

    def test_whitespace_only_returns_none(self):
        assert detect_profile("   ") is None

    def test_none_like_returns_none(self):
        """Empty string and whitespace should both return None."""
        assert detect_profile("") is None
        assert detect_profile("   ") is None

    def test_first_match_wins(self):
        """When multiple patterns could match, the first matching profile wins."""
        # "Edge" appears in both "edge" and other titles potentially.
        # Verify we get a non-None result (order-dependent).
        p = detect_profile("Microsoft Edge")
        assert p is not None

    def test_partial_title_match(self):
        """Patterns are substring-matched against the lowercased title."""
        p = detect_profile("something with Firefox inside it")
        assert p is not None
        assert p.name == "firefox"


class TestGetProfileAdditional:
    def test_all_known_profiles_retrievable(self):
        expected_keys = [
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
        for key in expected_keys:
            p = get_profile(key)
            assert p is not None, f"Profile {key!r} should exist"
            assert p.name == key

    def test_case_sensitive_lookup(self):
        """get_profile uses dict key lookup which is case-sensitive."""
        assert get_profile("Chrome") is None
        assert get_profile("CHROME") is None


class TestListProfilesAdditional:
    def test_includes_all_expected_profiles(self):
        profiles = list_profiles()
        names = {p.name for p in profiles}
        expected = {
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
        }
        assert expected.issubset(names)

    def test_returns_list_not_dict(self):
        result = list_profiles()
        assert isinstance(result, list)


class TestGetTimingForAppAdditional:
    def test_firefox_timing(self):
        timing = get_timing_for_app("Firefox")
        assert timing["launch_delay"] == 3.0
        assert timing["action_delay"] == 0.3

    def test_vscode_timing(self):
        timing = get_timing_for_app("Visual Studio Code")
        assert timing["launch_delay"] == 4.0
        assert "preferred_input" not in timing

    def test_outlook_timing(self):
        timing = get_timing_for_app("Outlook")
        assert timing["launch_delay"] == 5.0

    def test_notepad_timing(self):
        timing = get_timing_for_app("Notepad")
        assert timing["launch_delay"] == 1.0
        assert timing["action_delay"] == 0.1

    def test_cmd_timing(self):
        timing = get_timing_for_app("Command Prompt")
        assert timing["launch_delay"] == 1.0

    def test_case_insensitive_timing(self):
        """get_timing_for_app calls detect_profile which lowercases."""
        timing1 = get_timing_for_app("Chrome")
        timing2 = get_timing_for_app("CHROME")
        assert timing1 == timing2


class TestAppProfileFieldsAdditional:
    """Test specific field values across profiles for completeness."""

    def test_chrome_stealth_compatible(self):
        assert PROFILES["chrome"].stealth_compatible == "partial"

    def test_notepad_preferred_input(self):
        assert PROFILES["notepad"].preferred_input == "postmessage"

    def test_vscode_preferred_input(self):
        assert PROFILES["vscode"].preferred_input == "physical"

    def test_live2d_stealth_compatible_none(self):
        assert PROFILES["live2d_cubism"].stealth_compatible == "none"

    def test_excel_has_menu_paths(self):
        assert "save" in PROFILES["excel"].menu_paths
        assert "insert_row" in PROFILES["excel"].menu_paths

    def test_excel_has_strategies(self):
        assert "edit_cell" in PROFILES["excel"].strategies

    def test_chrome_has_known_controls(self):
        assert "address_bar" in PROFILES["chrome"].known_controls

    def test_all_profiles_have_valid_stealth(self):
        valid = {"full", "partial", "none"}
        for name, profile in PROFILES.items():
            assert profile.stealth_compatible in valid, f"{name} has invalid stealth_compatible"

    def test_all_profiles_have_valid_input(self):
        valid = {"uia", "postmessage", "physical"}
        for name, profile in PROFILES.items():
            assert profile.preferred_input in valid, f"{name} has invalid preferred_input"

    def test_all_profiles_timing_has_required_keys(self):
        required_keys = {"launch_delay", "action_delay", "page_load_delay"}
        for name, profile in PROFILES.items():
            assert required_keys.issubset(profile.timing.keys()), f"{name} missing timing keys"

    def test_all_profiles_timing_values_are_positive(self):
        for name, profile in PROFILES.items():
            for key, value in profile.timing.items():
                assert value > 0, f"{name}.{key}={value} should be positive"

    def test_profile_display_name_is_nonempty(self):
        for name, profile in PROFILES.items():
            assert profile.display_name, f"{name} has empty display_name"

    def test_profile_window_title_patterns_nonempty(self):
        for name, profile in PROFILES.items():
            assert profile.window_title_patterns, f"{name} has empty window_title_patterns"
