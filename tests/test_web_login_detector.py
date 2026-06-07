"""Tests for core.web.login_detector — IT appliance login page detection."""

from __future__ import annotations

import pytest

from core.web.login_detector import (
    LOGIN_PROFILES,
    LoginProfile,
    detect_login_page,
    get_login_fields,
)


class TestLoginProfile:
    def test_matches_url_exact(self):
        profile = LoginProfile(
            name="Test",
            url_patterns=("example.com",),
            title_patterns=(),
            username_selector="input[name='user']",
            password_selector="input[name='pass']",
            submit_selector="button",
        )
        assert profile.matches_url("https://example.com/login") is True
        assert profile.matches_url("https://other.com/login") is False

    def test_matches_url_case_insensitive(self):
        profile = LoginProfile(
            name="Test",
            url_patterns=("example.com",),
            title_patterns=(),
            username_selector="input",
            password_selector="input",
            submit_selector="button",
        )
        assert profile.matches_url("https://EXAMPLE.COM/") is True

    def test_matches_title(self):
        profile = LoginProfile(
            name="Test",
            url_patterns=(),
            title_patterns=("login page",),
            username_selector="input",
            password_selector="input",
            submit_selector="button",
        )
        assert profile.matches_title("Welcome to the Login Page") is True
        assert profile.matches_title("Dashboard") is False


class TestDetectLoginPage:
    @pytest.mark.parametrize(
        "url,name",
        [
            ("https://192.168.1.1/sonicwall/login", "SonicWall"),
            ("https://10.0.0.1/fgt_login", "FortiGate"),
            ("https://unifi.local:8443/manage", "UniFi"),
            ("https://dashboard.meraki.com", "Meraki"),
            ("https://firewall.local/index.php", "pfSense"),
            ("https://router.local/core/login", "OPNsense"),
            ("https://10.0.0.1/webfig", "MikroTik"),
            ("https://app.ninjaone.com/login", "NinjaOne"),
            ("https://control.connectwise.com/access", "ConnectWise"),
            ("https://app.itglue.com/login", "IT Glue"),
        ],
    )
    def test_detects_known_appliances_by_url(self, url, name):
        profile = detect_login_page(url)
        assert profile is not None
        assert profile.name == name

    def test_detects_by_title_only(self):
        profile = detect_login_page(
            url="https://192.168.99.1/",
            title="Login - FortiGate",
        )
        assert profile is not None
        assert profile.name == "FortiGate"

    def test_url_match_takes_priority(self):
        profile = detect_login_page(
            url="https://sonicwall.local/",
            title="Dashboard",  # generic, doesn't match
        )
        assert profile is not None
        assert profile.name == "SonicWall"

    def test_unknown_url_no_match(self):
        profile = detect_login_page("https://www.google.com")
        assert profile is None

    def test_unknown_title_no_match(self):
        profile = detect_login_page(
            url="https://example.com",
            title="Welcome",
        )
        assert profile is None

    def test_empty_inputs(self):
        assert detect_login_page("", "") is None

    def test_all_profiles_have_selectors(self):
        for profile in LOGIN_PROFILES:
            assert profile.username_selector, f"{profile.name} missing username selector"
            assert profile.password_selector, f"{profile.name} missing password selector"
            assert profile.submit_selector, f"{profile.name} missing submit selector"

    def test_all_profiles_have_patterns(self):
        for profile in LOGIN_PROFILES:
            assert profile.url_patterns or profile.title_patterns, (
                f"{profile.name} has no URL or title patterns"
            )


class TestGetLoginFields:
    def test_returns_selectors_for_known_page(self):
        fields = get_login_fields("https://192.168.1.1/sonicwall/login")
        assert fields is not None
        assert "username_selector" in fields
        assert "password_selector" in fields
        assert "submit_selector" in fields
        assert fields["appliance"] == "SonicWall"

    def test_returns_none_for_unknown(self):
        fields = get_login_fields("https://www.google.com")
        assert fields is None

    def test_selectors_are_css_strings(self):
        fields = get_login_fields("https://app.ninjaone.com/login")
        assert fields is not None
        for key in ("username_selector", "password_selector", "submit_selector"):
            val = fields[key]
            assert isinstance(val, str)
            assert len(val) > 0
