"""Sentinel Desktop v8.0 — IT appliance login page detector.

Detects common IT admin login pages by matching URL patterns, page titles,
and form structures. When detected, offers to fill credentials from the
credential vault.

Supports: SonicWall, FortiGate/Fortinet, UniFi, Meraki, pfSense, OPNsense,
MikroTik, Juniper, Palo Alto, ConnectWise, NinjaOne, ScreenConnect, IT Glue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginProfile:
    """Pattern profile for a known IT appliance login page."""

    name: str
    url_patterns: tuple[str, ...]
    title_patterns: tuple[str, ...]
    username_selector: str
    password_selector: str
    submit_selector: str

    def matches_url(self, url: str) -> bool:
        url_lower = url.lower()
        return any(pat in url_lower for pat in self.url_patterns)

    def matches_title(self, title: str) -> bool:
        title_lower = title.lower()
        return any(pat in title_lower for pat in self.title_patterns)


# Known appliance login profiles.
# Each has URL patterns, title patterns, and CSS selectors for the login form.
# ruff: noqa: S106 — password_selector is a CSS selector, not a hardcoded password.
LOGIN_PROFILES: list[LoginProfile] = [
    LoginProfile(
        name="SonicWall",
        url_patterns=("sonicwall", "sw_management", "sonicos"),
        title_patterns=("sonicwall", "sonicos", "dell sonicwall"),
        username_selector="input[name='userName']",
        password_selector="input[name='password']",
        submit_selector="a[id='loginSubmit']",
    ),
    LoginProfile(
        name="FortiGate",
        url_patterns=("fortigate", "fortinet", "fgt_", "firewall/login"),
        title_patterns=("fortigate", "fortinet", "login - fortigate"),
        username_selector="input[name='username']",
        password_selector="input[name='secretkey']",
        submit_selector="button[id='login_button']",
    ),
    LoginProfile(
        name="UniFi",
        url_patterns=("unifi", "manage/site", ":8443/manage"),
        title_patterns=("unifi", "ubiquiti unifi"),
        username_selector="input[name='username']",
        password_selector="input[name='password']",
        submit_selector="button[type='submit']",
    ),
    LoginProfile(
        name="Meraki",
        url_patterns=("meraki", "dashboard.meraki", "n149.meraki.com"),
        title_patterns=("meraki", "cisco meraki", "dashboard login"),
        username_selector="input[name='email']",
        password_selector="input[name='password']",
        submit_selector="button[type='submit']",
    ),
    LoginProfile(
        name="pfSense",
        url_patterns=("pfsense", "index.php"),
        title_patterns=("pfsense", "pf sense"),
        username_selector="input[name='usernamefld']",
        password_selector="input[name='passwordfld']",
        submit_selector="button[name='login']",
    ),
    LoginProfile(
        name="OPNsense",
        url_patterns=("opnsense", "core/login"),
        title_patterns=("opnsense", "login - opnsense"),
        username_selector="input[name='usernamefld']",
        password_selector="input[name='passwordfld']",
        submit_selector="button[type='submit']",
    ),
    LoginProfile(
        name="MikroTik",
        url_patterns=("mikrotik", "webfig", ":8080/"),
        title_patterns=("mikrotik", "routeros", "webfig"),
        username_selector="input[name='name']",
        password_selector="input[name='password']",
        submit_selector="button[type='submit']",
    ),
    LoginProfile(
        name="NinjaOne",
        url_patterns=("ninjaone", "ninjarmm", "ninja/rmm"),
        title_patterns=("ninjaone", "ninja rmm", "login - ninja"),
        username_selector="input[name='email']",
        password_selector="input[name='password']",
        submit_selector="button[type='submit']",
    ),
    LoginProfile(
        name="ConnectWise",
        url_patterns=("connectwise", "screenconnect", "control."),
        title_patterns=("connectwise", "screenconnect", "access agent"),
        username_selector="input[name='username']",
        password_selector="input[name='password']",
        submit_selector="button[type='submit']",
    ),
    LoginProfile(
        name="IT Glue",
        url_patterns=("itglue", "it-glue"),
        title_patterns=("it glue", "login - it glue"),
        username_selector="input[name='email']",
        password_selector="input[name='password']",
        submit_selector="input[type='submit']",
    ),
]


def detect_login_page(
    url: str,
    title: str = "",
) -> LoginProfile | None:
    """Detect if the current page is a known IT appliance login page.

    Args:
        url: Current page URL.
        title: Current page title (optional, improves accuracy).

    Returns:
        LoginProfile if a known login page is detected, None otherwise.
    """
    for profile in LOGIN_PROFILES:
        if profile.matches_url(url):
            logger.info("Detected %s login page from URL: %s", profile.name, url)
            return profile
        if title and profile.matches_title(title):
            logger.info("Detected %s login page from title: %s", profile.name, title)
            return profile

    return None


def get_login_fields(
    url: str,
    title: str = "",
) -> dict[str, str] | None:
    """Get CSS selectors for login form fields if on a known login page.

    Args:
        url: Current page URL.
        title: Current page title.

    Returns:
        Dict with 'username', 'password', 'submit' selectors,
        or None if not a known login page.
    """
    profile = detect_login_page(url, title)
    if profile is None:
        return None

    return {
        "appliance": profile.name,
        "username_selector": profile.username_selector,
        "password_selector": profile.password_selector,
        "submit_selector": profile.submit_selector,
    }
