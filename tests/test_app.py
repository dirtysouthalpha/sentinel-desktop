"""Coverage tests for gui/app.py — SentinelApp and SettingsWindow.

These tests run fully headless: tkinter / customtkinter are stubbed by
tests/conftest.py. Collaborators that spin threads, hit the network, or run
the agent engine are patched out so the tests are deterministic and fast.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

import gui.app as app_mod
from gui.app import SentinelApp, SettingsWindow

# ── Test helpers ──────────────────────────────────────────────────────────


class _FakeRoot:
    """Stand-in for the CTk root window with the window-manager methods
    app.py calls (title/geometry/protocol/bind/withdraw/etc.).

    after() runs callbacks synchronously so scheduled main-thread updates
    actually execute during tests (kept deterministic — no real event loop).
    """

    def __init__(self, *a, **kw) -> None:
        pass

    def after(self, _delay, fn=None, *args):
        if callable(fn):
            fn(*args)
        return ""

    def __getattr__(self, _name):
        # Any other window-manager call (title, geometry, minsize, protocol,
        # bind, withdraw, deiconify, lift, attributes, mainloop, destroy, …)
        # becomes a no-op.
        return lambda *a, **kw: None


class _FakeTabview:
    """Stand-in for CTkTabview — the conftest stub lacks .add()."""

    def __init__(self, *a, **kw) -> None:
        pass

    def add(self, _name):
        return MagicMock()

    def __getattr__(self, _name):
        return lambda *a, **kw: None


class _FakeText:
    """Minimal stand-in for a CTkTextbox supporting get/insert/delete/see."""

    def __init__(self, *_a, **_kw) -> None:
        self._buf = ""

    def get(self, *_a, **_kw) -> str:
        return self._buf

    def insert(self, _index, text) -> None:
        if _index in ("1.0",):
            self._buf = text + self._buf
        else:
            self._buf += text

    def delete(self, *_a, **_kw) -> None:
        self._buf = ""

    def see(self, *_a, **_kw) -> None:
        pass

    def configure(self, *_a, **_kw) -> None:
        pass

    def focus_set(self, *_a, **_kw) -> None:
        pass

    def bind(self, *_a, **_kw) -> None:
        pass

    def grid(self, *_a, **_kw) -> None:
        pass


class _FakeConfig:
    """Dict-backed Config replacement with controllable load/save."""

    def __init__(self, data: dict | None = None) -> None:
        self._data = dict(data or {})
        self.saved: list[dict] = []
        self.save_raises = None

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def load(self) -> dict:
        return self._data

    def save(self, data=None) -> None:
        if self.save_raises is not None:
            raise self.save_raises
        if data:
            self._data.update(data)
        self.saved.append(dict(self._data))


def _make_app(cfg_data: dict | None = None) -> SentinelApp:
    """Construct a SentinelApp with stubbed widgets/collaborators."""
    cfg = _FakeConfig(cfg_data)
    # Patch the lazily-imported tab classes with MagicMocks so the
    # success branches in _build_tabs run without touching tab internals.
    with patch.object(app_mod.ctk, "CTk", _FakeRoot), patch.object(
        app_mod.ctk, "CTkTabview", _FakeTabview
    ), patch.object(app_mod.ctk, "CTkTextbox", _FakeText), patch(
        "gui.tabs.scripts_tab.ScriptsTab", MagicMock()
    ), patch("gui.tabs.workflows_tab.WorkflowsTab", MagicMock()), patch(
        "gui.tabs.history_tab.HistoryTab", MagicMock()
    ), patch("gui.tabs.settings_tab.SettingsTab", MagicMock()):
        app = SentinelApp(cfg)
    # The history_display widget is only built on demand; provide a fake.
    app.history_display = _FakeText()
    return app


@pytest.fixture
def app():
    return _make_app(
        {
            "theme": "sentinel",
            "provider": "openai",
            "model": "gpt-4o",
            "quick_actions": ["do a thing", "x" * 50],
            "recent_prompts": ["prompt one", "prompt two", "y" * 60],
        }
    )


# ── Construction / header variants ─────────────────────────────────────────


class TestConstruction:
    def test_basic_construction(self, app):
        assert app.root is not None
        assert app.overlay is not None
        assert app.tray is None

    def test_header_chips_dry_run_autonomous_stealth(self):
        app = _make_app(
            {
                "dry_run": True,
                "autonomous": True,
                "stealth_input": True,
                "quick_actions": [],
                "recent_prompts": [],
            }
        )
        # All three chip branches in _build_header should have executed.
        assert app.cfg.get("dry_run") is True

    def test_theme_helper(self, app):
        assert app._t("accent", "fallback") != ""
        assert app._t("nonexistent_key", "fb") == "fb"

    def test_recorder_panel_built_when_importable(self):
        """Cover the success branch of _build_recorder_panel.

        RecorderPanel imports tkinter.filedialog/messagebox which aren't in
        the headless stub; provide them so the import (and construction)
        succeeds.
        """
        import sys
        import tkinter
        import types

        fd = types.ModuleType("tkinter.filedialog")
        fd.askopenfilename = lambda *a, **k: ""
        fd.asksaveasfilename = lambda *a, **k: ""
        mb = types.ModuleType("tkinter.messagebox")
        mb.showerror = lambda *a, **k: None
        mb.showinfo = lambda *a, **k: None
        mb.askyesno = lambda *a, **k: True
        with patch.dict(
            sys.modules,
            {"tkinter.filedialog": fd, "tkinter.messagebox": mb},
        ), patch.object(tkinter, "filedialog", fd, create=True), patch.object(
            tkinter, "messagebox", mb, create=True
        ):
            app = _make_app({"quick_actions": [], "recent_prompts": []})
        assert app.recorder_panel is not None


# ── Tab fallbacks (ImportError branches) ───────────────────────────────────


class TestTabFallbacks:
    def test_tab_import_errors_fall_back(self):
        # Force the optional tab imports to fail so the except branches run.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name.startswith("gui.tabs.") or name == "gui.recorder_panel":
                raise ImportError("forced")
            return real_import(name, *a, **kw)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            app = _make_app({"quick_actions": [], "recent_prompts": []})
        assert app is not None


# ── Placeholder / prompt helpers ───────────────────────────────────────────


class TestPromptHelpers:
    def test_get_goal_text_placeholder_returns_empty(self, app):
        assert app._get_goal_text() == ""

    def test_get_goal_text_real_text(self, app):
        app.goal_entry = _FakeText()
        app.goal_entry.insert("1.0", "real goal")
        assert app._get_goal_text() == "real goal"

    def test_set_prompt(self, app):
        app._set_prompt("hello there")
        assert "hello there" in app.goal_entry.get("1.0", "end")

    def test_clear_placeholder_when_placeholder(self, app):
        app._clear_placeholder()
        assert app.goal_entry.get("1.0", "end") == ""

    def test_clear_placeholder_noop_when_real_text(self, app):
        app.goal_entry = _FakeText()
        app.goal_entry.insert("1.0", "user text")
        app._clear_placeholder()
        assert "user text" in app.goal_entry.get("1.0", "end")

    def test_restore_placeholder_when_empty(self, app):
        app.goal_entry = _FakeText()
        app._restore_placeholder()
        assert app._placeholder_text in app.goal_entry.get("1.0", "end")

    def test_restore_placeholder_noop_when_text(self, app):
        app.goal_entry = _FakeText()
        app.goal_entry.insert("1.0", "stuff")
        app._restore_placeholder()
        assert app.goal_entry.get("1.0", "end") == "stuff"

    def test_on_recent_pick_matches_truncated(self, app):
        app.recent_var = MagicMock()
        app._on_recent_pick("prompt one")
        assert "prompt one" in app.goal_entry.get("1.0", "end")
        app.recent_var.set.assert_called()

    def test_on_recent_pick_ellipsis(self, app):
        app.recent_var = MagicMock()
        # The third recent prompt is 60 'y' chars, truncated with an ellipsis.
        app._on_recent_pick("y" * 47 + "…")
        assert "y" in app.goal_entry.get("1.0", "end")

    def test_record_recent_prompt_dedup_and_save(self, app):
        app._record_recent_prompt("brand new prompt")
        assert app.cfg["recent_prompts"][0] == "brand new prompt"
        assert app.config.saved  # save was called

    def test_record_recent_prompt_empty_noop(self, app):
        before = app.cfg.get("recent_prompts")
        app._record_recent_prompt("")
        assert app.cfg.get("recent_prompts") == before

    def test_record_recent_prompt_save_error_swallowed(self, app):
        app.config.save_raises = OSError("disk full")
        # Should not raise.
        app._record_recent_prompt("another prompt")


# ── Chat display ───────────────────────────────────────────────────────────


class TestChat:
    def test_add_chat_marshals_to_main(self, app):
        # root.after is a no-op stub; just ensure no exception.
        app._add_chat("hello", "user")

    def test_add_chat_runtime_error_swallowed(self, app):
        app.root.after = MagicMock(side_effect=RuntimeError("destroyed"))
        app._add_chat("hello", "system")

    def test_add_chat_main_writes_buffer(self, app):
        app._add_chat_main("a message", "assistant")
        assert "a message" in app.chat_display.get("1.0", "end")
        assert "Agent" in app.chat_display.get("1.0", "end")

    def test_add_chat_main_unknown_tag(self, app):
        app._add_chat_main("msg", "weirdtag")
        assert "System" in app.chat_display.get("1.0", "end")


# ── Submit / stop / run ────────────────────────────────────────────────────


class TestSubmitStop:
    def test_on_submit_empty_with_event_returns_break(self, app):
        assert app._on_submit(event=object()) == "break"

    def test_on_submit_empty_no_event_returns_none(self, app):
        assert app._on_submit() is None

    def test_on_submit_real_goal_runs(self, app):
        app.goal_entry = _FakeText()
        app.goal_entry.insert("1.0", "open notepad")
        with patch.object(app, "_run_goal") as run:
            result = app._on_submit(event=object())
        run.assert_called_once_with("open notepad")
        assert result == "break"

    def test_on_stop_running(self, app):
        app.engine = MagicMock()
        app.engine.running = True
        app._on_stop()
        app.engine.stop.assert_called_once()

    def test_on_stop_not_running(self, app):
        app.engine = MagicMock()
        app.engine.running = False
        app._on_stop()
        app.engine.stop.assert_not_called()

    def test_on_stop_no_engine(self, app):
        app.engine = None
        app._on_stop()  # should not raise


class TestRunGoal:
    def test_run_goal_already_running(self, app):
        app.engine = MagicMock()
        app.engine.running = True
        with patch.object(app, "_add_chat") as chat:
            app._run_goal("goal")
        chat.assert_called()

    def test_run_goal_success(self, app):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.return_value = {"steps": 3, "notes": [], "finish_summary": "all good"}
        fake_engine.max_steps = 100
        fake_engine.notes = []

        # Run the worker synchronously instead of in a thread.
        captured = {}

        def fake_thread(target=None, **_kw):
            captured["target"] = target
            t = MagicMock()
            t.start = lambda: target()
            return t

        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=fake_thread
        ):
            app._run_goal("do work")
        fake_engine.run.assert_called_once_with("do work")

    def test_run_goal_engine_error_notes(self, app):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.return_value = {
            "steps": 0,
            "notes": ["bad config"],
            "error": "boom",
        }
        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ), patch.object(app, "_add_chat") as chat:
            app._run_goal("g")
        assert any("bad config" in str(c) for c in chat.call_args_list)

    def test_run_goal_zero_steps_with_notes(self, app):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.return_value = {
            "steps": 0,
            "notes": ["nothing to do"],
            "finish_summary": "",
        }
        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ), patch.object(app, "_add_chat") as chat:
            app._run_goal("g")
        assert any("nothing to do" in str(c) for c in chat.call_args_list)

    def test_run_goal_success_notifies_tray(self, app):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.return_value = {"steps": 1, "notes": [], "finish_summary": "done"}
        app.tray = MagicMock()
        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ):
            app._run_goal("g")
        app.tray.notify.assert_called_once()

    def test_run_goal_tray_notify_error_swallowed(self, app):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.return_value = {"steps": 2, "notes": [], "finish_summary": "ok"}
        app.tray = MagicMock()
        app.tray.notify.side_effect = RuntimeError("no tray")
        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ):
            app._run_goal("g")  # should not raise

    def test_run_goal_exception_writes_log(self, app, tmp_path, monkeypatch):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.side_effect = ValueError("kaboom")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ), patch.object(app, "_add_chat") as chat:
            app._run_goal("g")
        assert any("kaboom" in str(c) for c in chat.call_args_list)
        # last_error.log should have been written under APPDATA.
        assert (tmp_path / "SentinelDesktop" / "last_error.log").exists()

    def test_run_goal_exception_log_write_fails(self, app, monkeypatch):
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.side_effect = OSError("engine down")
        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ), patch("pathlib.Path.mkdir", side_effect=OSError("ro fs")), patch.object(
            app, "_add_chat"
        ):
            app._run_goal("g")  # should not raise even if log write fails

    def test_on_step_callback(self, app):
        """Exercise the inner _on_step callback wired onto the engine."""
        fake_engine = MagicMock()
        fake_engine.running = False
        fake_engine.run.return_value = {"steps": 1, "notes": [], "finish_summary": ""}
        fake_engine.max_steps = 50
        fake_engine.notes = ["n1"]

        with patch("core.engine.AgentEngine", return_value=fake_engine), patch.object(
            threading, "Thread", side_effect=self._sync_thread
        ):
            app._run_goal("g")
        on_step = fake_engine.on_step_callback
        # Call it with a full payload (action + ok result + screenshot).
        on_step(
            step=1,
            action={"action": "click", "x": 10, "y": 20},
            result={"ok": True, "msg": "clicked"},
            screenshot="abc",
        )
        # Call it with a failing result and no screenshot.
        on_step(
            step=2,
            action={"action": "type"},
            result={"ok": False, "error": "bad"},
        )

    @staticmethod
    def _sync_thread(target=None, **_kw):
        t = MagicMock()
        t.start = lambda: target()
        return t


# ── Step labels / approval / screenshot ────────────────────────────────────


class TestLabelsApprovalScreenshot:
    def test_update_step_labels(self, app):
        app.engine = MagicMock()
        app.engine.max_steps = 100
        app.engine.notes = ["a", "b"]
        app.step_label = MagicMock()
        app.notes_label = MagicMock()
        app._update_step_labels(5)
        app.step_label.configure.assert_called()

    def test_update_step_labels_no_engine(self, app):
        app.engine = None
        app._update_step_labels(5)  # should return early

    def test_approve_action_timeout_returns_false(self, app):
        # Make root.after a no-op so _prompt never runs; event.wait times out.
        app.root.after = MagicMock()
        with patch("threading.Event") as ev_cls:
            ev = MagicMock()
            ev.wait.return_value = False
            ev_cls.return_value = ev
            result = app._approve_action({"action": "delete", "path": "/x"})
        assert result is False

    def test_approve_action_prompt_builds_and_approves(self, app):
        """Run the scheduled _prompt synchronously and build the dialog."""
        # _FakeRoot.after runs callbacks synchronously, so _prompt executes.
        fake_top = MagicMock()
        with patch.object(app_mod.ctk, "CTkToplevel", return_value=fake_top), patch.object(
            app_mod.ctk, "CTkLabel"
        ), patch.object(app_mod.ctk, "CTkFrame"), patch.object(
            app_mod.ctk, "CTkButton"
        ) as btn:
            with patch("threading.Event") as ev_cls:
                ev = MagicMock()
                ev.wait.return_value = True
                ev_cls.return_value = ev
                app._approve_action({"action": "click", "x": 1})
        # Approve/Reject buttons were created during the dialog build.
        assert btn.called
        # The approve/reject inner callbacks were wired as button commands.
        commands = [c.kwargs.get("command") for c in btn.call_args_list if c.kwargs.get("command")]
        # Exercise both the approve and reject closures (lines for both paths).
        for cmd in commands:
            cmd()
        fake_top.destroy.assert_called()

    def test_approve_action_prompt_raises_sets_event(self, app):
        # _FakeRoot.after runs _prompt synchronously; CTkToplevel raises.
        with patch.object(
            app_mod.ctk, "CTkToplevel", side_effect=RuntimeError("no win")
        ), patch("threading.Event") as ev_cls:
            ev = MagicMock()
            ev.wait.return_value = False
            ev_cls.return_value = ev
            result = app._approve_action({"action": "x"})
        assert result is False
        ev.set.assert_called()

    def test_update_screenshot_success(self, app):
        import base64
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (20, 20)).save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        app.screenshot_label = MagicMock()
        app._update_screenshot(b64)
        app.screenshot_label.configure.assert_called()

    def test_update_screenshot_bad_data(self, app):
        app.screenshot_label = MagicMock()
        app._update_screenshot("not-valid-base64-image!!")  # should log & swallow


# ── Settings open / saved ──────────────────────────────────────────────────


class TestSettingsHooks:
    def test_open_settings(self, app):
        with patch.object(app_mod, "SettingsWindow") as sw:
            app._open_settings()
        sw.assert_called_once()

    def test_on_settings_saved_updates_label(self, app):
        app.provider_label = MagicMock()
        app.cfg["provider"] = "anthropic"
        app.cfg["model"] = "claude"
        app._on_settings_saved()
        app.provider_label.configure.assert_called()


# ── Command palette / screenshot / export ──────────────────────────────────


class TestCommandPalette:
    def test_show_command_palette_builds(self, app):
        fake_palette = MagicMock()
        with patch.object(app_mod.ctk, "CTkToplevel", return_value=fake_palette), patch.object(
            app_mod.ctk, "CTkEntry"
        ), patch.object(app_mod.ctk, "CTkScrollableFrame"), patch.object(
            app_mod.ctk, "CTkButton"
        ) as btn:
            app._show_command_palette()
        # Four commands -> four buttons.
        assert btn.call_count >= 4

    def test_take_screenshot_success(self, app):
        with patch("core.screenshot.capture_to_base64", return_value="b64"), patch.object(
            app, "_update_screenshot"
        ) as upd, patch.object(app, "_add_chat") as chat:
            app._take_screenshot()
        upd.assert_called_once_with("b64")
        chat.assert_called()

    def test_take_screenshot_error(self, app):
        with patch(
            "core.screenshot.capture_to_base64", side_effect=OSError("no screen")
        ), patch.object(app, "_add_chat") as chat:
            app._take_screenshot()
        assert any("failed" in str(c).lower() for c in chat.call_args_list)

    def test_export_log_no_engine(self, app):
        app.engine = None
        with patch.object(app, "_add_chat") as chat:
            app._export_log()
        chat.assert_called()

    def test_export_log_success(self, app, tmp_path, monkeypatch):
        app.engine = MagicMock()
        app.engine.forensic_log = [{"x": 1}]
        monkeypatch.chdir(tmp_path)
        with patch.object(app, "_add_chat") as chat:
            app._export_log()
        assert any("exported" in str(c).lower() for c in chat.call_args_list)

    def test_export_log_oserror(self, app):
        app.engine = MagicMock()
        app.engine.forensic_log = [{"x": 1}]
        with patch("pathlib.Path.open", side_effect=OSError("ro")), patch.object(
            app, "_add_chat"
        ) as chat:
            app._export_log()
        assert any("failed" in str(c).lower() for c in chat.call_args_list)


# ── Resume checkpoint ──────────────────────────────────────────────────────


class TestCheckpoint:
    def test_check_resume_no_checkpoint(self, app):
        fake_cp = MagicMock()
        fake_cp.load_latest.return_value = None
        with patch("core.checkpoint.CheckpointManager", return_value=fake_cp), patch.object(
            app, "_add_chat"
        ) as chat:
            app._check_resume_checkpoint()
        chat.assert_not_called()

    def test_check_resume_with_checkpoint(self, app):
        fake_cp = MagicMock()
        fake_cp.load_latest.return_value = {
            "goal": "do a thing",
            "step_num": 4,
            "status": "paused",
        }
        with patch("core.checkpoint.CheckpointManager", return_value=fake_cp), patch.object(
            app, "_add_chat"
        ) as chat:
            app._check_resume_checkpoint()
        chat.assert_called()

    def test_check_resume_error_swallowed(self, app):
        with patch(
            "core.checkpoint.CheckpointManager", side_effect=RuntimeError("oops")
        ):
            app._check_resume_checkpoint()  # should not raise

    def test_do_resume_no_checkpoint(self, app):
        fake_cp = MagicMock()
        fake_cp.load_latest.return_value = None
        with patch("core.checkpoint.CheckpointManager", return_value=fake_cp), patch.object(
            app, "_add_chat"
        ) as chat:
            app._do_resume_checkpoint()
        assert any("No resumable" in str(c) for c in chat.call_args_list)

    def test_do_resume_no_goal(self, app):
        fake_cp = MagicMock()
        fake_cp.load_latest.return_value = {"goal": ""}
        with patch("core.checkpoint.CheckpointManager", return_value=fake_cp), patch.object(
            app, "_add_chat"
        ) as chat:
            app._do_resume_checkpoint()
        assert any("no goal" in str(c).lower() for c in chat.call_args_list)

    def test_do_resume_success(self, app):
        fake_cp = MagicMock()
        fake_cp.load_latest.return_value = {"goal": "resume me"}
        with patch("core.checkpoint.CheckpointManager", return_value=fake_cp), patch.object(
            app, "_run_goal"
        ) as run:
            app._do_resume_checkpoint()
        run.assert_called_once_with("resume me")

    def test_do_resume_error(self, app):
        with patch(
            "core.checkpoint.CheckpointManager", side_effect=ValueError("bad")
        ), patch.object(app, "_add_chat") as chat:
            app._do_resume_checkpoint()
        assert any("failed" in str(c).lower() for c in chat.call_args_list)


# ── History panel / before-after screenshots ──────────────────────────────


class TestHistory:
    def test_build_history_panel(self, app):
        parent = MagicMock()
        frame = app._build_history_panel(parent)
        assert frame is not None

    def test_add_history_entry_ok(self, app):
        app.history_display = _FakeText()
        app._add_history_entry(1, "click", {"ok": True, "msg": "done"})
        assert "click" in app.history_display.get("1.0", "end")

    def test_add_history_entry_fail_icon(self, app):
        app.history_display = _FakeText()
        app._add_history_entry(2, "type", {"ok": False, "msg": "err"})
        assert "type" in app.history_display.get("1.0", "end")

    def test_add_history_entry_no_display(self, app):
        # configure raises -> error branch.
        app.history_display = MagicMock()
        app.history_display.configure.side_effect = RuntimeError("not built")
        app._add_history_entry(1, "a", {})  # swallowed

    def test_update_screenshot_with_diff(self, app):
        import base64
        import io

        from PIL import Image

        def mk():
            buf = io.BytesIO()
            Image.new("RGB", (30, 30)).save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()

        app.screenshot_label = MagicMock()
        # ImageTk.PhotoImage needs a real Tk display; stub it out.
        with patch("PIL.ImageTk.PhotoImage", return_value=MagicMock()):
            app._update_screenshot_with_diff(mk(), mk())
        app.screenshot_label.configure.assert_called()

    def test_update_screenshot_with_diff_bad(self, app):
        app.screenshot_label = MagicMock()
        app._update_screenshot_with_diff("bad", "data")  # swallowed


# ── Tray lifecycle ─────────────────────────────────────────────────────────


class TestTray:
    def test_start_tray_disabled(self, app):
        app.cfg["minimize_to_tray"] = False
        app.cfg["start_in_tray"] = False
        app._start_tray_if_enabled()
        assert app.tray is None

    def test_start_tray_unavailable(self, app):
        app.cfg["minimize_to_tray"] = True
        with patch.object(app_mod, "_tray_available", return_value=False), patch.object(
            app, "_add_chat"
        ) as chat:
            app._start_tray_if_enabled()
        chat.assert_called()
        assert app.tray is None

    def test_start_tray_enabled_runs(self, app):
        app.cfg["minimize_to_tray"] = True
        app.cfg["start_in_tray"] = False
        fake_tray = MagicMock()
        fake_tray.run.return_value = True
        with patch.object(app_mod, "_tray_available", return_value=True), patch.object(
            app_mod, "SentinelTray", return_value=fake_tray
        ):
            app._start_tray_if_enabled()
        assert app.tray is fake_tray
        fake_tray.run.assert_called_once()

    def test_start_tray_start_in_tray_hides(self, app):
        app.cfg["start_in_tray"] = True
        fake_tray = MagicMock()
        fake_tray.run.return_value = True
        with patch.object(app_mod, "_tray_available", return_value=True), patch.object(
            app_mod, "SentinelTray", return_value=fake_tray
        ):
            app._start_tray_if_enabled()
        # after(100, ...) scheduled the hide; no exception is enough here.
        assert app.tray is fake_tray

    def test_hide_to_tray_no_tray(self, app):
        app.tray = None
        app._hide_to_tray()  # returns early

    def test_hide_to_tray_withdraws(self, app):
        app.tray = MagicMock()
        app.root.withdraw = MagicMock()
        app._hide_to_tray()
        app.root.withdraw.assert_called_once()

    def test_hide_to_tray_withdraw_error(self, app):
        app.tray = MagicMock()
        app.root.withdraw = MagicMock(side_effect=RuntimeError("gone"))
        app._hide_to_tray()  # swallowed

    def test_show_from_tray(self, app):
        app.root.after = MagicMock()
        app._show_from_tray()
        assert app.root.after.called

    def test_show_from_tray_error(self, app):
        app.root.after = MagicMock(side_effect=RuntimeError("gone"))
        app._show_from_tray()  # swallowed

    def test_on_close_minimizes(self, app):
        app.cfg["minimize_to_tray"] = True
        app.tray = MagicMock()
        with patch.object(app, "_hide_to_tray") as hide:
            app._on_close_window()
        hide.assert_called_once()

    def test_on_close_destroys(self, app):
        app.cfg["minimize_to_tray"] = False
        app.tray = None
        app.root.destroy = MagicMock()
        app._on_close_window()
        app.root.destroy.assert_called_once()


# ── run() ──────────────────────────────────────────────────────────────────


class TestRun:
    def test_run_no_llm_configured_warns(self, app):
        app.cfg["api_key"] = ""
        app.cfg["provider"] = "openai"
        app.cfg["model"] = ""
        app.root.mainloop = MagicMock()
        with patch.object(app, "_check_resume_checkpoint"), patch.object(
            app, "_start_tray_if_enabled"
        ), patch.object(app, "_add_chat") as chat:
            app.run()
        assert any("No LLM" in str(c) for c in chat.call_args_list)
        app.root.mainloop.assert_called_once()

    def test_run_with_llm_configured(self, app):
        app.cfg["api_key"] = "sk-xxx"
        app.cfg["provider"] = "openai"
        app.cfg["model"] = "gpt-4o"
        app.root.mainloop = MagicMock()
        with patch.object(app, "_check_resume_checkpoint"), patch.object(
            app, "_start_tray_if_enabled"
        ), patch.object(app, "_add_chat") as chat:
            app.run()
        # No 'No LLM' warning when fully configured.
        assert not any("No LLM" in str(c) for c in chat.call_args_list)

    def test_run_local_provider_no_key_ok(self, app):
        app.cfg["api_key"] = ""
        app.cfg["provider"] = "ollama"
        app.cfg["model"] = "llama3"
        app.root.mainloop = MagicMock()
        with patch.object(app, "_check_resume_checkpoint"), patch.object(
            app, "_start_tray_if_enabled"
        ), patch.object(app, "_add_chat") as chat:
            app.run()
        assert not any("No LLM" in str(c) for c in chat.call_args_list)


# ── SettingsWindow ─────────────────────────────────────────────────────────


def _make_settings(cfg_data=None, app_obj=None):
    cfg = _FakeConfig(cfg_data or {"provider": "openai", "theme": "sentinel"})
    parent = MagicMock()
    return SettingsWindow(parent, cfg, on_save=MagicMock(), app=app_obj)


class TestSettingsWindow:
    def test_construct_builds(self):
        sw = _make_settings()
        assert sw.win is not None
        assert sw.provider_var is not None

    def test_construct_with_api_key(self):
        sw = _make_settings({"provider": "openai", "api_key": "sk-1", "model": "m"})
        assert sw is not None

    def test_construct_monitor_enum_fails(self):
        with patch("core.screenshot.list_monitors", side_effect=OSError("no mon")):
            sw = _make_settings()
        assert sw is not None

    def test_construct_with_virtual_monitor(self):
        mons = [
            {"index": 0, "width": 3840, "height": 1080, "is_virtual": True},
            {"index": 1, "width": 1920, "height": 1080, "is_primary": True},
        ]
        with patch("core.screenshot.list_monitors", return_value=mons):
            sw = _make_settings({"provider": "openai", "monitor": 1})
        assert sw is not None

    def test_on_theme_change_with_app(self):
        app = _make_app({"quick_actions": [], "recent_prompts": []})
        app.status_label = MagicMock()
        app.provider_label = MagicMock()
        sw = _make_settings(app_obj=app)
        sw._on_theme_change("midnight")
        assert app.current_theme is not None

    def test_on_theme_change_no_app(self):
        sw = _make_settings()
        sw.app = None
        sw._on_theme_change("midnight")  # no-op, no raise

    def test_on_provider_change_autofills(self):
        sw = _make_settings()
        sw.base_url_var = MagicMock()
        sw.base_url_var.get.return_value = ""
        sw._on_provider_change("openai")
        sw.base_url_var.set.assert_called()

    def test_reset_base_url(self):
        sw = _make_settings()
        sw.provider_var = MagicMock()
        sw.provider_var.get.return_value = "openai"
        sw.base_url_var = MagicMock()
        sw._reset_base_url()
        sw.base_url_var.set.assert_called()

    def test_detect_models_no_key(self):
        sw = _make_settings()
        sw.api_key_entry = MagicMock()
        sw.api_key_entry.get.return_value = ""
        sw.model_var = MagicMock()
        sw._detect_models()
        sw.model_var.set.assert_called_with("Enter API key first")

    def test_detect_models_found_single(self):
        sw = _make_settings()
        sw.provider_var = MagicMock()
        sw.provider_var.get.return_value = "openai"
        sw.api_key_entry = MagicMock()
        sw.api_key_entry.get.return_value = "sk-1"
        sw.model_var = MagicMock()
        sw.model_entry = MagicMock()
        with patch("core.provider_registry.fetch_models", return_value=["only-model"]):
            sw._detect_models()
        sw.model_var.set.assert_called_with("only-model")

    def test_detect_models_found_multiple(self):
        sw = _make_settings()
        sw.provider_var = MagicMock()
        sw.provider_var.get.return_value = "openai"
        sw.api_key_entry = MagicMock()
        sw.api_key_entry.get.return_value = "sk-1"
        sw.model_var = MagicMock()
        sw.model_entry = MagicMock()
        with patch(
            "core.provider_registry.fetch_models", return_value=["a", "b", "c"]
        ):
            sw._detect_models()
        sw.model_var.set.assert_called_with("")

    def test_detect_models_none_found(self):
        sw = _make_settings()
        sw.provider_var = MagicMock()
        sw.provider_var.get.return_value = "openai"
        sw.api_key_entry = MagicMock()
        sw.api_key_entry.get.return_value = "sk-1"
        sw.model_var = MagicMock()
        sw.model_entry = MagicMock()
        with patch("core.provider_registry.fetch_models", return_value=[]):
            sw._detect_models()
        sw.model_var.set.assert_called_with("")

    def test_save_full(self):
        sw = _make_settings()
        self._wire_save_vars(sw, monitor="1 — 1920x1080 (primary)", steps="50")
        sw.win = MagicMock()
        sw._save()
        assert sw.cfg["max_steps"] == 50
        assert sw.cfg["monitor"] == 1
        sw.on_save.assert_called_once()
        sw.win.destroy.assert_called_once()

    def test_save_auto_monitor(self):
        sw = _make_settings()
        self._wire_save_vars(sw, monitor="auto — focused", steps="bad")
        sw.win = MagicMock()
        sw._save()
        assert sw.cfg["monitor"] == "auto"
        # Non-integer steps fall back to 100.
        assert sw.cfg["max_steps"] == 100

    def test_save_invalid_monitor_index(self):
        sw = _make_settings()
        self._wire_save_vars(sw, monitor="notanint — junk", steps="10")
        sw.win = MagicMock()
        sw._save()
        assert sw.cfg["monitor"] == "auto"

    def test_save_oserror_shows_error(self):
        sw = _make_settings()
        self._wire_save_vars(sw, monitor="auto", steps="100")
        sw.config.save_raises = OSError("disk full")
        sw.win = MagicMock()
        fake_mb = MagicMock()
        import sys
        import tkinter as _tk
        import types

        mb_mod = types.ModuleType("tkinter.messagebox")
        mb_mod.showerror = fake_mb
        # Patch both the submodule entry AND the attribute so that
        # ``from tkinter import messagebox`` resolves the fake regardless of
        # test execution order (the headless tkinter stub has no messagebox).
        with (
            patch.dict(sys.modules, {"tkinter.messagebox": mb_mod}),
            patch.object(_tk, "messagebox", mb_mod, create=True),
        ):
            sw._save()
        fake_mb.assert_called_once()
        # on_save should NOT be called on error.
        sw.on_save.assert_not_called()

    @staticmethod
    def _wire_save_vars(sw, monitor, steps):
        sw.provider_var = MagicMock()
        sw.provider_var.get.return_value = "openai"
        sw.api_key_entry = MagicMock()
        sw.api_key_entry.get.return_value = "sk-1"
        sw.model_var = MagicMock()
        sw.model_var.get.return_value = "gpt-4o"
        sw.theme_var = MagicMock()
        sw.theme_var.get.return_value = "sentinel"
        sw.base_url_var = MagicMock()
        sw.base_url_var.get.return_value = "https://api.example.com/"
        sw.steps_entry = MagicMock()
        sw.steps_entry.get.return_value = steps
        sw.monitor_var = MagicMock()
        sw.monitor_var.get.return_value = monitor
        sw.autonomous_var = MagicMock()
        sw.autonomous_var.get.return_value = True
        sw.dry_run_var = MagicMock()
        sw.dry_run_var.get.return_value = False
        sw.stealth_var = MagicMock()
        sw.stealth_var.get.return_value = False
        sw.tray_var = MagicMock()
        sw.tray_var.get.return_value = False
        sw.start_tray_var = MagicMock()
        sw.start_tray_var.get.return_value = False
