"""Coverage tests for gui.recorder_panel.

Runs headless against the tkinter/customtkinter stubs installed by
tests/conftest.py. Dialog-heavy methods need a few extra widget methods
(title/geometry/transient/grab_set/wait_window/insert/get/winfo_toplevel)
that the base stub does not provide, so those are patched locally per-test
rather than touching conftest.
"""

import json
import sys
import tkinter as _tk
import types
from pathlib import Path
from unittest import mock

import customtkinter as ctk
import pytest


def _install_tkinter_submodule_stubs() -> None:
    """Add filedialog/messagebox stubs to the headless tkinter stub.

    The conftest tkinter stub does not provide these submodules, yet
    gui.recorder_panel imports them at module load. Install them here
    (without touching conftest) before importing the module under test.
    """
    if not hasattr(_tk, "filedialog"):
        fd = types.ModuleType("tkinter.filedialog")
        fd.askopenfilename = lambda *a, **kw: ""
        fd.asksaveasfilename = lambda *a, **kw: ""
        _tk.filedialog = fd
        sys.modules["tkinter.filedialog"] = fd
    if not hasattr(_tk, "messagebox"):
        mb = types.ModuleType("tkinter.messagebox")
        mb.showinfo = lambda *a, **kw: None
        mb.showwarning = lambda *a, **kw: None
        mb.showerror = lambda *a, **kw: None
        mb.askyesno = lambda *a, **kw: False
        _tk.messagebox = mb
        sys.modules["tkinter.messagebox"] = mb


_install_tkinter_submodule_stubs()

import gui.recorder_panel as rp  # noqa: E402
from gui.recorder_panel import RecorderPanel, _ensure_scripts_dir  # noqa: E402

# ── Fakes ────────────────────────────────────────────────────────────────


class _FakeWidget:
    """A widget that records insert/get and supports dialog lifecycle calls."""

    def __init__(self, *a, **kw):
        self._text = ""
        self._destroyed = False
        for k, v in kw.items():
            setattr(self, k, v)

    # lifecycle / layout no-ops
    def grid(self, *a, **kw):
        pass

    def pack(self, *a, **kw):
        pass

    def place(self, *a, **kw):
        pass

    def configure(self, *a, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    config = configure

    def cget(self, key, default=None):
        return getattr(self, key, default)

    def bind(self, *a, **kw):
        pass

    def after(self, delay, func=None, *a):
        # Run scheduled callbacks immediately so we can assert their effects.
        if callable(func):
            func()
        return "job-id"

    def after_cancel(self, *a):
        pass

    def destroy(self):
        self._destroyed = True

    def winfo_children(self):
        return []

    def winfo_exists(self):
        return True

    def winfo_toplevel(self):
        return self

    def grid_remove(self):
        pass

    def grid_columnconfigure(self, *a, **kw):
        pass

    def grid_rowconfigure(self, *a, **kw):
        pass

    def pack_propagate(self, *a, **kw):
        pass

    def grid_propagate(self, *a, **kw):
        pass

    def update_idletasks(self):
        pass

    def update(self):
        pass

    # toplevel-ish methods
    def title(self, *a, **kw):
        pass

    def geometry(self, *a, **kw):
        pass

    def resizable(self, *a, **kw):
        pass

    def transient(self, *a, **kw):
        pass

    def grab_set(self, *a, **kw):
        pass

    def wait_window(self, *a, **kw):
        pass

    # entry/textbox methods
    def insert(self, *a, **kw):
        if len(a) == 2:
            self._text = str(a[1])

    def get(self, *a, **kw):
        return self._text


class _FakeMenu(_FakeWidget):
    def add_command(self, *a, **kw):
        pass

    def add_separator(self, *a, **kw):
        pass

    def tk_popup(self, *a, **kw):
        pass


class _Recorder:
    def __init__(self, is_recording=False, raise_on=None):
        self.is_recording = is_recording
        self._raise_on = raise_on or {}
        self.started = None
        self._stop_script = None

    def start_recording(self, name):
        if "start" in self._raise_on:
            raise self._raise_on["start"]
        self.started = name
        self.is_recording = True

    def stop_recording(self):
        if "stop" in self._raise_on:
            raise self._raise_on["stop"]
        self.is_recording = False
        return self._stop_script


class _Script:
    def __init__(self, steps=None, name="rec", description="", tags=None):
        self.steps = steps if steps is not None else []
        self.name = name
        self.description = description
        self.tags = tags or []
        self.saved_to = None
        self._raise_on_save = None

    def save(self, path):
        if self._raise_on_save:
            raise self._raise_on_save
        self.saved_to = path


class _Result:
    def __init__(self, success=True, steps_completed=3, steps_total=3, error=None):
        self.success = success
        self.steps_completed = steps_completed
        self.steps_total = steps_total
        self.error = error


class _Engine:
    def __init__(self, result=None, raise_exc=None):
        self._result = result or _Result()
        self._raise_exc = raise_exc
        self.progress_cb = None
        self.ran = None

    def set_progress_callback(self, cb):
        self.progress_cb = cb

    def run_script(self, path, params):
        self.ran = (path, params)
        if self._raise_exc:
            raise self._raise_exc
        return self._result


class _App:
    def __init__(self, recorder=None, engine=None):
        self.recorder = recorder
        self.script_engine = engine

    def _t(self, key, default=None):
        return default


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def panel():
    app = _App()
    p = RecorderPanel(parent=mock.MagicMock(), app=app)
    # Replace status_label/buttons with fakes that record configure() calls.
    p.status_label = _FakeWidget()
    p.btn_record = _FakeWidget()
    p.btn_stop = _FakeWidget()
    p.btn_play = _FakeWidget()
    p.btn_library = _FakeWidget()
    # Make panel-level after run callbacks immediately and winfo_toplevel work.
    p.after = _FakeWidget().after
    p.after_cancel = lambda *a, **kw: None
    p.winfo_toplevel = lambda: _FakeWidget()
    return p


@pytest.fixture(autouse=True)
def _patch_ctk_dialog_widgets():
    """Swap dialog/entry widgets for fakes that support insert/get/title/etc."""
    names = [
        "CTkToplevel",
        "CTkEntry",
        "CTkTextbox",
        "CTkScrollableFrame",
        "CTkFrame",
        "CTkLabel",
        "CTkButton",
    ]
    saved = {n: getattr(ctk, n) for n in names}
    for n in names:
        setattr(ctk, n, _FakeWidget)
    # tk.Menu used in _on_library
    saved_menu = rp.tk.Menu
    rp.tk.Menu = _FakeMenu
    try:
        yield
    finally:
        for n, v in saved.items():
            setattr(ctk, n, v)
        rp.tk.Menu = saved_menu


# ── _ensure_scripts_dir ──────────────────────────────────────────────────


def test_ensure_scripts_dir_creates(tmp_path, monkeypatch):
    target = tmp_path / "myscripts"
    monkeypatch.setattr(rp, "SCRIPTS_DIR", str(target))
    out = _ensure_scripts_dir()
    assert out == str(target)
    assert target.is_dir()


# ── construction ───────────────────────────────────────────────────────────


def test_construction_builds_toolbar():
    app = _App()
    p = RecorderPanel(parent=mock.MagicMock(), app=app)
    assert p.app is app
    assert p._t == app._t
    assert p._pulse_job is None
    assert p._pulse_on is False
    assert p._is_playing is False
    assert hasattr(p, "btn_record")
    assert hasattr(p, "status_label")


# ── _on_record ───────────────────────────────────────────────────────────


def test_on_record_no_recorder_warns(panel):
    panel.app.recorder = None
    with mock.patch.object(rp.messagebox, "showwarning") as warn:
        panel._on_record()
    warn.assert_called_once()


def test_on_record_already_recording_noop(panel):
    panel.app.recorder = _Recorder(is_recording=True)
    with mock.patch.object(panel, "_start_pulse") as sp:
        panel._on_record()
    sp.assert_not_called()


def test_on_record_runtime_error_warns(panel):
    panel.app.recorder = _Recorder(raise_on={"start": RuntimeError("busy")})
    with mock.patch.object(rp.messagebox, "showwarning") as warn:
        panel._on_record()
    warn.assert_called_once()


def test_on_record_success_starts_pulse(panel):
    rec = _Recorder()
    panel.app.recorder = rec
    # Non-recursing after so _start_pulse doesn't self-schedule forever.
    panel.after = mock.Mock(return_value="JOB")
    panel._on_record()
    assert rec.started == ""
    assert panel.status_label.text.startswith("Recording")
    # _start_pulse ran, pulse toggled on
    assert panel._pulse_on is True
    assert panel._pulse_job == "JOB"


# ── pulse ─────────────────────────────────────────────────────────────────


def test_start_pulse_toggles(panel):
    # Replace after to NOT recurse infinitely; capture the job id.
    panel.after = mock.Mock(return_value="JOB")
    panel._pulse_on = False
    panel._start_pulse()
    assert panel._pulse_on is True
    assert panel._pulse_job == "JOB"
    panel._start_pulse()
    assert panel._pulse_on is False


def test_stop_pulse_cancels_job(panel):
    cancel = mock.Mock()
    panel.after_cancel = cancel
    panel._pulse_job = "JOB"
    panel._stop_pulse()
    cancel.assert_called_once_with("JOB")
    assert panel._pulse_job is None


def test_stop_pulse_no_job(panel):
    panel._pulse_job = None
    panel._stop_pulse()  # should not raise
    assert panel._pulse_job is None


# ── _on_stop ─────────────────────────────────────────────────────────────


def test_on_stop_no_recorder_noop(panel):
    panel.app.recorder = None
    with mock.patch.object(panel, "_stop_pulse") as sp:
        panel._on_stop()
    sp.assert_not_called()


def test_on_stop_not_recording_noop(panel):
    panel.app.recorder = _Recorder(is_recording=False)
    with mock.patch.object(panel, "_stop_pulse") as sp:
        panel._on_stop()
    sp.assert_not_called()


def test_on_stop_raises_shows_error(panel):
    panel.app.recorder = _Recorder(is_recording=True, raise_on={"stop": OSError("io")})
    with mock.patch.object(rp.messagebox, "showerror") as err, mock.patch.object(
        panel, "_set_ready"
    ) as ready:
        panel._on_stop()
    err.assert_called_once()
    ready.assert_called_once()


def test_on_stop_no_steps_info(panel):
    rec = _Recorder(is_recording=True)
    rec._stop_script = _Script(steps=[])
    panel.app.recorder = rec
    with mock.patch.object(rp.messagebox, "showinfo") as info, mock.patch.object(
        panel, "_set_ready"
    ) as ready:
        panel._on_stop()
    info.assert_called_once()
    ready.assert_called_once()


def test_on_stop_with_steps_shows_save_dialog(panel):
    rec = _Recorder(is_recording=True)
    rec._stop_script = _Script(steps=[{"a": 1}])
    panel.app.recorder = rec
    with mock.patch.object(panel, "_show_save_dialog") as dlg:
        panel._on_stop()
    dlg.assert_called_once_with(rec._stop_script)


# ── _show_save_dialog ──────────────────────────────────────────────────────


def test_show_save_dialog_save_success(panel, tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "SCRIPTS_DIR", str(tmp_path))
    script = _Script(steps=[{"x": 1}], name="My Script", description="d")

    captured = {}

    class _Toplevel(_FakeWidget):
        pass

    # Capture the _save closure by intercepting the Save button command.
    real_button = _FakeWidget

    def button_factory(*a, **kw):
        w = real_button(*a, **kw)
        if kw.get("text", "").startswith("💾"):
            captured["save"] = kw.get("command")
        return w

    monkeypatch.setattr(ctk, "CTkButton", button_factory)
    panel._show_save_dialog(script)
    assert "save" in captured
    # Provide entry text by re-patching get on the entry the closure uses.
    captured["save"]()  # invoke _save
    assert script.saved_to is not None
    assert script.saved_to.endswith(".json")


def test_show_save_dialog_save_oserror(panel, tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "SCRIPTS_DIR", str(tmp_path))
    script = _Script(steps=[{"x": 1}], name="bad")
    script._raise_on_save = OSError("disk full")

    captured = {}

    def button_factory(*a, **kw):
        w = _FakeWidget(*a, **kw)
        if kw.get("text", "").startswith("💾"):
            captured["save"] = kw.get("command")
        return w

    monkeypatch.setattr(ctk, "CTkButton", button_factory)
    with mock.patch.object(rp.messagebox, "showerror") as err:
        panel._show_save_dialog(script)
        captured["save"]()
    err.assert_called_once()


# ── _on_play ─────────────────────────────────────────────────────────────


def test_on_play_cancelled(panel):
    with mock.patch.object(rp.filedialog, "askopenfilename", return_value=""):
        with mock.patch.object(panel, "_run_script") as run:
            panel._on_play()
    run.assert_not_called()


def test_on_play_bad_json(panel, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with mock.patch.object(rp.filedialog, "askopenfilename", return_value=str(bad)):
        with mock.patch.object(rp.messagebox, "showerror") as err:
            panel._on_play()
    err.assert_called_once()


def test_on_play_no_params_runs(panel, tmp_path):
    good = tmp_path / "ok.json"
    good.write_text(json.dumps({"steps": [{"a": 1}]}), encoding="utf-8")
    with mock.patch.object(rp.filedialog, "askopenfilename", return_value=str(good)):
        with mock.patch.object(panel, "_run_script") as run:
            panel._on_play()
    run.assert_called_once()
    assert run.call_args[0][1] == {}


def test_on_play_with_params_cancelled(panel, tmp_path):
    good = tmp_path / "p.json"
    good.write_text(
        json.dumps({"steps": [], "parameters": [{"name": "x"}]}), encoding="utf-8"
    )
    with mock.patch.object(rp.filedialog, "askopenfilename", return_value=str(good)):
        with mock.patch.object(panel, "_show_param_dialog", return_value=None):
            with mock.patch.object(panel, "_run_script") as run:
                panel._on_play()
    run.assert_not_called()


def test_on_play_with_params_provided(panel, tmp_path):
    good = tmp_path / "p2.json"
    good.write_text(
        json.dumps({"steps": [{"a": 1}], "parameters": [{"name": "x"}]}),
        encoding="utf-8",
    )
    with mock.patch.object(rp.filedialog, "askopenfilename", return_value=str(good)):
        with mock.patch.object(panel, "_show_param_dialog", return_value={"x": "1"}):
            with mock.patch.object(panel, "_run_script") as run:
                panel._on_play()
    run.assert_called_once()
    assert run.call_args[0][1] == {"x": "1"}


# ── _show_param_dialog ─────────────────────────────────────────────────────


def test_show_param_dialog_ok(panel, monkeypatch):
    captured = {}

    def button_factory(*a, **kw):
        w = _FakeWidget(*a, **kw)
        if kw.get("text") == "OK":
            captured["ok"] = kw.get("command")
        return w

    monkeypatch.setattr(ctk, "CTkButton", button_factory)
    params = [{"name": "user", "prompt": "User", "default": "bob"}]

    # Make wait_window invoke the OK callback (simulating user clicking OK).
    class _Top(_FakeWidget):
        def wait_window(self, *a, **kw):
            captured["ok"]()

    monkeypatch.setattr(ctk, "CTkToplevel", _Top)
    out = panel._show_param_dialog(params)
    assert out == {"user": "bob"}


def test_show_param_dialog_cancelled(panel, monkeypatch):
    # wait_window does nothing -> cancelled remains True -> returns None
    params = [{"name": "p"}]
    out = panel._show_param_dialog(params)
    assert out is None


# ── _run_script ────────────────────────────────────────────────────────────


def test_run_script_no_engine(panel):
    panel.app.script_engine = None
    with mock.patch.object(rp.messagebox, "showwarning") as warn:
        panel._run_script("p.json", {}, {"steps": []})
    warn.assert_called_once()


def test_run_script_success(panel):
    engine = _Engine(result=_Result(success=True))
    panel.app.script_engine = engine
    # Run the worker thread synchronously by replacing Thread.
    threads = []

    class _SyncThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            threads.append(self)
            self._target()

    with mock.patch.object(rp.threading, "Thread", _SyncThread):
        with mock.patch.object(panel, "_on_play_done") as done:
            panel._run_script("p.json", {"a": 1}, {"steps": [{}, {}]})
    assert panel._is_playing is True
    assert engine.ran == ("p.json", {"a": 1})
    done.assert_called_once()
    # progress callback was set and is safe to invoke
    assert engine.progress_cb is not None
    engine.progress_cb(1, 2, "act", "res")


def test_run_script_worker_exception(panel):
    engine = _Engine(raise_exc=RuntimeError("boom"))
    panel.app.script_engine = engine

    class _SyncThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            self._target()

    with mock.patch.object(rp.threading, "Thread", _SyncThread):
        with mock.patch.object(rp.messagebox, "showerror") as err, mock.patch.object(
            panel, "_set_ready"
        ) as ready:
            panel._run_script("p.json", {}, {"steps": [{}]})
    err.assert_called_once()
    ready.assert_called_once()


# ── _on_play_done ──────────────────────────────────────────────────────────


def test_on_play_done_success(panel):
    panel._is_playing = True
    with mock.patch.object(rp.messagebox, "showinfo") as info:
        panel._on_play_done(_Result(success=True, steps_completed=2, steps_total=2))
    assert panel._is_playing is False
    info.assert_called_once()
    # after(5000, _set_ready) runs immediately via fake -> status reset
    assert panel.status_label.text == "Ready"


def test_on_play_done_failure(panel):
    panel._is_playing = True
    with mock.patch.object(rp.messagebox, "showerror") as err:
        panel._on_play_done(_Result(success=False, error="kaboom"))
    err.assert_called_once()


def test_on_play_done_failure_no_error_text(panel):
    panel._is_playing = True
    with mock.patch.object(rp.messagebox, "showerror") as err:
        panel._on_play_done(_Result(success=False, error=None))
    args = err.call_args[0]
    assert "Unknown error" in args


# ── _on_library ────────────────────────────────────────────────────────────


def _make_recorder_module(scripts, raise_exc=None):
    mod = types.ModuleType("core.recorder")

    class ActionRecorder:
        @staticmethod
        def list_scripts(_dir):
            if raise_exc:
                raise raise_exc
            return scripts

    mod.ActionRecorder = ActionRecorder
    return mod


def test_on_library_import_error(panel, monkeypatch):
    # Force the `from core.recorder import ActionRecorder` to raise ImportError.
    real_import = __import__

    def fake_import(name, *a, **kw):
        if name == "core.recorder":
            raise ImportError("no module")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with mock.patch.object(rp.messagebox, "showerror") as err:
        panel._on_library()
    err.assert_called_once()


def test_on_library_list_scripts_error(panel, monkeypatch):
    mod = _make_recorder_module([], raise_exc=OSError("nope"))
    monkeypatch.setitem(sys.modules, "core.recorder", mod)
    # Empty scripts -> "No scripts found" branch
    panel._on_library()  # should not raise


def test_on_library_empty(panel, monkeypatch):
    mod = _make_recorder_module([])
    monkeypatch.setitem(sys.modules, "core.recorder", mod)
    panel._on_library()  # builds dialog, hits "No scripts found" path


def test_on_library_with_scripts(panel, tmp_path, monkeypatch):
    # Create a real script file so the step-count read succeeds.
    sfile = tmp_path / "s1.json"
    sfile.write_text(json.dumps({"steps": [{}, {}, {}]}), encoding="utf-8")
    scripts = [
        {
            "path": str(sfile),
            "name": "Login Flow",
            "description": "logs in",
            "tags": ["it", "auth"],
        },
        {
            "path": str(tmp_path / "missing.json"),  # triggers read except branch
            "name": "Broken",
            "description": "",
            "tags": [],
        },
    ]
    mod = _make_recorder_module(scripts)
    monkeypatch.setitem(sys.modules, "core.recorder", mod)

    # Capture _refresh + _run closures and StringVar behavior.
    captured = {"run": [], "refresh": None}

    real_run_script = panel._run_script
    panel._run_script = mock.Mock()

    def button_factory(*a, **kw):
        w = _FakeWidget(*a, **kw)
        if kw.get("text") == "▶":
            captured["run"].append(kw.get("command"))
        return w

    monkeypatch.setattr(ctk, "CTkButton", button_factory)

    # A StringVar whose trace_add records the callback and get() returns query.
    class _SV:
        def __init__(self, *a, **kw):
            self._cb = None
            self._val = ""

        def get(self):
            return self._val

        def set(self, v):
            self._val = v

        def trace_add(self, mode, cb):
            captured["refresh"] = cb

    monkeypatch.setattr(ctk, "StringVar", _SV)
    panel._on_library()

    # _refresh exercised with empty and non-empty queries
    assert captured["refresh"] is not None
    captured["refresh"]()  # empty query path

    # Invoke a row "Run" command to cover the _run closure.
    assert captured["run"]
    captured["run"][0]()
    panel._run_script.assert_called()
    panel._run_script = real_run_script


def test_on_library_refresh_filters(panel, tmp_path, monkeypatch):
    sfile = tmp_path / "s.json"
    sfile.write_text(json.dumps({"steps": [{}]}), encoding="utf-8")
    scripts = [
        {"path": str(sfile), "name": "Alpha", "description": "first", "tags": ["x"]},
        {"path": str(sfile), "name": "Beta", "description": "second", "tags": ["y"]},
    ]
    mod = _make_recorder_module(scripts)
    monkeypatch.setitem(sys.modules, "core.recorder", mod)

    captured = {"refresh": None}

    class _SV:
        def __init__(self, *a, **kw):
            self._val = ""

        def get(self):
            return self._val

        def set(self, v):
            self._val = v

        def trace_add(self, mode, cb):
            captured["refresh"] = cb

    monkeypatch.setattr(ctk, "StringVar", _SV)
    panel._on_library()
    # Drive the filter with the default (empty) query.
    captured["refresh"]()


# ── _delete_script ─────────────────────────────────────────────────────────


def test_delete_script_declined(panel, tmp_path):
    parent = _FakeWidget()
    target = str(tmp_path / "x.json")
    with mock.patch.object(rp.messagebox, "askyesno", return_value=False):
        with mock.patch.object(Path, "unlink") as unlink:
            panel._delete_script(target, parent)
    unlink.assert_not_called()


def test_delete_script_confirmed(panel, tmp_path):
    f = tmp_path / "del.json"
    f.write_text("{}", encoding="utf-8")
    parent = _FakeWidget()
    with mock.patch.object(rp.messagebox, "askyesno", return_value=True):
        with mock.patch.object(panel, "_on_library") as lib:
            panel._delete_script(str(f), parent)
    assert not f.exists()
    lib.assert_called_once()
    assert parent._destroyed is True


def test_delete_script_unlink_error(panel, tmp_path):
    parent = _FakeWidget()
    target = str(tmp_path / "y.json")
    with mock.patch.object(rp.messagebox, "askyesno", return_value=True):
        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            with mock.patch.object(rp.messagebox, "showerror") as err:
                with mock.patch.object(panel, "_on_library") as lib:
                    panel._delete_script(target, parent)
    err.assert_called_once()
    lib.assert_not_called()


# ── _set_ready / update_step_count ──────────────────────────────────────────


def test_set_ready(panel):
    panel._set_ready()
    assert panel.status_label.text == "Ready"


def test_update_step_count_recording(panel):
    panel.app.recorder = _Recorder(is_recording=True)
    panel.update_step_count(7)
    assert panel.status_label.text == "Recording… (7 steps)"


def test_update_step_count_not_recording(panel):
    panel.app.recorder = _Recorder(is_recording=False)
    panel.status_label.text = "unchanged"
    panel.update_step_count(3)
    assert panel.status_label.text == "unchanged"


def test_update_step_count_no_recorder(panel):
    panel.app.recorder = None
    panel.status_label.text = "unchanged"
    panel.update_step_count(3)
    assert panel.status_label.text == "unchanged"
