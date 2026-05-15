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
