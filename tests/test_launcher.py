"""Tests for the smart app launcher."""
import pytest

from core import launcher
from core import window_manager as wm


def test_smart_open_focuses_existing_window(monkeypatch):
    calls = {"focus": None, "launched": False}

    def fake_list_windows():
        return [
            {"title": "Inbox - Brandon - Outlook", "is_focused": False},
            {"title": "Chrome", "is_focused": True},
        ]

    def fake_focus_window(title):
        calls["focus"] = title
        return True

    def fake_popen(*a, **kw):
        calls["launched"] = True

    monkeypatch.setattr(wm, "list_windows", fake_list_windows)
    monkeypatch.setattr(wm, "focus_window", fake_focus_window)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    result = launcher.smart_open("outlook")

    assert result["success"] is True
    assert result.get("focused") is True
    assert "Outlook" in calls["focus"]
    assert calls["launched"] is False, \
        "launcher should NOT spawn a new Outlook when one is open"


def test_smart_open_launches_when_no_match(monkeypatch):
    spawned = []

    monkeypatch.setattr(wm, "list_windows", lambda: [])

    def fake_popen(cmd, *a, **kw):
        spawned.append(cmd)
        class _P: pid = 1234
        return _P()

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    result = launcher.smart_open("outlook")

    assert result["success"] is True
    assert result.get("focused") is False
    # Spawned via 'cmd /c start "" <launcher>' so PATH + URI resolve.
    assert spawned and spawned[0][:3] == ["cmd", "/c", "start"]
    assert "outlook" in spawned[0]


def test_smart_open_empty_name_rejected():
    result = launcher.smart_open("")
    assert result["success"] is False
    assert result["error"] == "empty_name"


def test_smart_open_unknown_app_uses_name_as_command(monkeypatch):
    spawned = []

    monkeypatch.setattr(wm, "list_windows", lambda: [])
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda cmd, *a, **kw: spawned.append(cmd) or type("P", (), {"pid": 1})())

    launcher.smart_open("brand-new-app")
    assert any("brand-new-app" in token for token in spawned[0])


def test_alias_table_has_outlook_and_chrome():
    """Smoke check: the most common apps are in the alias table."""
    for app in ("outlook", "chrome", "edge", "excel", "word",
                "notepad", "explorer", "calc", "teams"):
        assert app in launcher.APP_ALIASES, f"missing alias: {app}"


# ---------------------------------------------------------------------------
# Shell-metacharacter rejection on the unknown-name fallback path.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "foo & calc",       # & chains commands in cmd.exe
    "; rm -rf /",       # semicolon command separator
    "app|other",        # pipe
    "name`whoami`",     # backticks
    "$(whoami)",        # command substitution
    "foo>out.txt",      # redirection
    "foo<in.txt",       # redirection
    "evil\nname",       # embedded newline
    "name with space",  # space splits args
    "evil%PATH%",       # %VAR% expansion in cmd
])
def test_smart_open_rejects_shell_metachars(name, monkeypatch):
    """Unknown app names with shell metacharacters must not be spawned."""
    spawned = []
    monkeypatch.setattr(wm, "list_windows", lambda: [])
    monkeypatch.setattr(
        launcher.subprocess, "Popen",
        lambda cmd, *a, **kw: spawned.append(cmd) or type("P", (), {"pid": 1})(),
    )

    result = launcher.smart_open(name)
    assert result["success"] is False
    assert result["error"] == "unsafe_app_name"
    assert spawned == [], f"refused to spawn but got: {spawned}"


def test_smart_open_known_alias_with_uri_protocol_still_works(monkeypatch):
    """Curated APP_ALIASES (e.g. ``ms-settings:``) must keep working."""
    spawned = []
    monkeypatch.setattr(wm, "list_windows", lambda: [])
    monkeypatch.setattr(
        launcher.subprocess, "Popen",
        lambda cmd, *a, **kw: spawned.append(cmd) or type("P", (), {"pid": 1})(),
    )

    result = launcher.smart_open("settings")
    assert result["success"] is True
    assert any("ms-settings" in token for token in spawned[0])


def test_is_safe_launch_token_unit():
    assert launcher._is_safe_launch_token("chrome")
    assert launcher._is_safe_launch_token("notepad++")
    assert launcher._is_safe_launch_token("v1.2.3-rc")
    assert not launcher._is_safe_launch_token("")
    assert not launcher._is_safe_launch_token("foo bar")
    assert not launcher._is_safe_launch_token("foo&bar")
    assert not launcher._is_safe_launch_token("ms-settings:")  # colon not allowed for unknowns
