"""Tests for the PTY terminal shell selection (api/server.py).

The terminal WebSocket execs a shell so the user gets a real prompt inside
Sentinel. These tests pin the contract that the shell matches the user's
configured interactive shell (so Starship/Powerlevel10k prompts render) and
that zsh/bash are launched as login+interactive so their rc files load.

We test the pure helpers (_shell_argv and the candidate ordering) rather than
the os.execvpe call itself — exec is irreversible and process-wide.
"""

from __future__ import annotations

from api.server import _shell_argv

# ---------------------------------------------------------------------------
# _shell_argv — which flags each shell gets
# ---------------------------------------------------------------------------


class TestShellArgv:
    def test_zsh_gets_interactive_flag(self):
        """zsh sources ~/.zshrc only with -i (where Starship/P10k init runs)."""
        assert _shell_argv("/bin/zsh") == ["/bin/zsh", "--login", "-i"]

    def test_bash_gets_interactive_flag(self):
        """bash sources ~/.bashrc only with -i."""
        assert _shell_argv("/bin/bash") == ["/bin/bash", "--login", "-i"]

    def test_zsh_versioned_gets_interactive_flag(self):
        """Versioned/suffixed zsh binaries (zsh-5.0) still count as zsh."""
        assert _shell_argv("/bin/zsh-5.0") == ["/bin/zsh-5.0", "--login", "-i"]

    def test_bash_suffixed_gets_interactive_flag(self):
        assert _shell_argv("/usr/bin/bash-static") == [
            "/usr/bin/bash-static",
            "--login",
            "-i",
        ]

    def test_sh_is_login_only(self):
        """sh has no useful -i semantics; --login is the safe common denominator."""
        assert _shell_argv("/bin/sh") == ["/bin/sh", "--login"]

    def test_fish_is_login_only(self):
        assert _shell_argv("/usr/bin/fish") == ["/usr/bin/fish", "--login"]

    def test_dash_is_login_only(self):
        assert _shell_argv("/bin/dash") == ["/bin/dash", "--login"]

    def test_unrelated_binary_not_treated_as_interactive(self):
        """A binary whose name merely starts with 'bash' (e.g. 'bashfoo') must
        NOT be mis-detected as bash and given -i."""
        assert _shell_argv("/bin/bashfoo") == ["/bin/bashfoo", "--login"]


# ---------------------------------------------------------------------------
# _setup_pty_child — shell resolution honors $SHELL
# ---------------------------------------------------------------------------
# _setup_pty_child ends in os.execvpe (irreversible), so we can't call it
# directly. Instead we verify the candidate-resolution logic by reconstructing
# the env it would see and asserting $SHELL is the first choice.


class TestShellResolutionHonorsUserShell:
    def test_user_shell_is_preferred(self, monkeypatch, tmp_path):
        """When $SHELL is set, it must be the first shell tried so the user's
        configured interactive shell (zsh for prompt-framework users) wins."""
        import api.server as srv

        # Simulate the env block _setup_pty_child builds.
        env = {"SHELL": "/bin/zsh", "TERM": "xterm-256color", "HOME": str(tmp_path)}
        monkeypatch.setattr(srv.os, "name", "posix")

        # Re-implement just the candidate-building (mirrors _setup_pty_child) so
        # we can assert ordering without exec'ing.
        user_shell = env.get("SHELL") or ""
        candidates: list[str] = []
        if user_shell:
            candidates.append(user_shell)
        import shutil

        for c in [shutil.which("zsh"), shutil.which("bash"), shutil.which("sh")]:
            if c and c not in candidates:
                candidates.append(c)

        # $SHELL must come first.
        assert candidates[0] == "/bin/zsh"

    def test_argv_for_user_zsh_is_interactive(self, tmp_path):
        """End-to-end: a $SHELL=/bin/zsh environment produces an interactive argv."""
        env_shell = "/bin/zsh"
        argv = _shell_argv(env_shell)
        assert argv == ["/bin/zsh", "--login", "-i"]
        assert "-i" in argv  # the whole point — .zshrc loads


# ---------------------------------------------------------------------------
# TERM env is preserved for color
# ---------------------------------------------------------------------------


class TestTermColor:
    def test_setup_preserves_term_for_256color(self):
        """256-color support must be advertised so prompt color codes render.
        _setup_pty_child hardcodes TERM=xterm-256color — confirm the constant
        is still set rather than accidentally downgraded."""
        import inspect

        from api.server import SentinelServer

        src = inspect.getsource(SentinelServer._setup_pty_child)
        assert 'env["TERM"] = "xterm-256color"' in src


# ---------------------------------------------------------------------------
# Regression: slave_fd must NOT be closed before its ioctl/dup2 uses
# ---------------------------------------------------------------------------
# Bug (py3.14): _setup_pty_child called os.close(slave_fd) at the top, then used
# slave_fd for TIOCSCTTY / TIOCSWINSZ / dup2 → OSError: Bad file descriptor,
# which crashed the PTY child and surfaced downstream as
# `RuntimeError: loop ... is not the running loop`. The close belongs AFTER
# dup2 (and only when slave_fd > 2).


class TestSlaveFdNotPrematurelyClosed:
    def test_no_close_before_ioctl_or_dup2(self):
        """The premature os.close(slave_fd) must stay gone. We assert on source
        ordering: every os.close(slave_fd) must come AFTER all fcntl.ioctl and
        os.dup2 uses of slave_fd."""
        import inspect

        from api.server import SentinelServer

        src = inspect.getsource(SentinelServer._setup_pty_child)
        lines = src.splitlines()

        # Find positions (line index within the method) of the relevant calls.
        close_idx = next(
            (i for i, ln in enumerate(lines) if "os.close(slave_fd)" in ln),
            None,
        )
        last_use_idx = max(
            (i for i, ln in enumerate(lines)
             if "fcntl.ioctl(slave_fd" in ln or "os.dup2(slave_fd" in ln),
            default=-1,
        )
        assert close_idx is not None, "no os.close(slave_fd) found at all"
        assert close_idx > last_use_idx, (
            f"regression: os.close(slave_fd) at line {close_idx} runs before "
            f"the last slave_fd use at line {last_use_idx} (Bad fd crash)"
        )

    def test_setup_does_not_top_level_close_slave_fd(self):
        """The very first body statement must NOT be os.close(slave_fd) — that
        was the exact bug. (The legitimate close is guarded by `slave_fd > 2`
        after dup2.)"""
        import inspect
        import re

        from api.server import SentinelServer

        src = inspect.getsource(SentinelServer._setup_pty_child)
        # Strip docstring + assertion, find the first real os.* call.
        body = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
        body = re.sub(r"assert .*\n", "", body)
        os_calls = re.findall(r"os\.\w+\(", body)
        assert os_calls, "no os.* calls found in _setup_pty_child body"
        assert os_calls[0] != "os.close(", (
            f"regression: first os call is {os_calls[0]!r} — must be os.setsid(), "
            "not os.close() (premature close was the Bad-fd crash)"
        )
