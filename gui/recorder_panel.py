"""
Sentinel Desktop v26.0.0 — Recorder Panel

Horizontal toolbar providing record / stop / play controls for the
action recorder and script engine.  Sits at the top of the input area
inside the main SentinelApp window.
"""

import json
import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")


def _ensure_scripts_dir() -> str:
    Path(SCRIPTS_DIR).mkdir(parents=True, exist_ok=True)
    return SCRIPTS_DIR


class RecorderPanel(ctk.CTkFrame):
    """Toolbar with Record ⏺ / Stop ⏹ / Play ▶ and Script Library 📋 buttons."""

    def __init__(self, parent: ctk.CTkFrame, app: Any) -> None:
        super().__init__(parent, height=40, corner_radius=4)
        self.app = app
        self._t = app._t
        self._pulse_job: str | None = None
        self._pulse_on = False
        self._is_playing = False
        self._build_toolbar()

    def _build_toolbar(self) -> None:
        self.pack_propagate(False)
        t = self._t
        self.btn_record = ctk.CTkButton(
            self,
            text="⏺ Record",
            width=100,
            height=30,
            font=("Segoe UI", 11, "bold"),
            fg_color=t("status_error", "#ff3b3b"),
            hover_color=t("status_error", "#ff3b3b"),
            text_color="#ffffff",
            corner_radius=3,
            command=self._on_record,
        )
        self.btn_record.pack(side="left", padx=(8, 2), pady=4)

        self.btn_stop = ctk.CTkButton(
            self,
            text="⏹ Stop",
            width=80,
            height=30,
            font=("Segoe UI", 11, "bold"),
            fg_color=t("bg_input", "#111418"),
            hover_color=t("bg_hover", "#333539"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=3,
            command=self._on_stop,
        )
        self.btn_stop.pack(side="left", padx=2, pady=4)

        self.btn_play = ctk.CTkButton(
            self,
            text="▶ Play",
            width=80,
            height=30,
            font=("Segoe UI", 11, "bold"),
            fg_color=t("status_running", "#95E400"),
            hover_color="#6ed400",
            text_color="#ffffff",
            corner_radius=3,
            command=self._on_play,
        )
        self.btn_play.pack(side="left", padx=2, pady=4)

        self.btn_library = ctk.CTkButton(
            self,
            text="📋 Library",
            width=100,
            height=30,
            font=("Segoe UI", 11),
            fg_color=t("bg_input", "#111418"),
            hover_color=t("bg_hover", "#333539"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=3,
            command=self._on_library,
        )
        self.btn_library.pack(side="left", padx=2, pady=4)

        self.status_label = ctk.CTkLabel(
            self, text="Ready", font=("Segoe UI", 11), text_color=t("text_secondary", "#b9cacb")
        )
        self.status_label.pack(side="right", padx=12, pady=4)

    # ── Record ─────────────────────────────────────────────────────────

    def _on_record(self) -> None:
        recorder = getattr(self.app, "recorder", None)
        if recorder is None:
            messagebox.showwarning("Recorder", "No recorder instance available.")
            return
        if recorder.is_recording:
            return
        try:
            recorder.start_recording("")
        except RuntimeError as exc:
            messagebox.showwarning("Recorder", str(exc))
            return
        self.status_label.configure(text="Recording… (0 steps)", text_color=self._t("status_error", "#ff3b3b"))
        self.btn_record.configure(fg_color="#ff0000")
        self._start_pulse()

    def _start_pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        self.btn_record.configure(fg_color="#ff0000" if self._pulse_on else self._t("status_error", "#ff3b3b"))
        self._pulse_job = self.after(600, self._start_pulse)

    def _stop_pulse(self) -> None:
        if self._pulse_job:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.btn_record.configure(fg_color=self._t("status_error", "#ff3b3b"))

    # ── Stop ───────────────────────────────────────────────────────────

    def _on_stop(self) -> None:
        recorder = getattr(self.app, "recorder", None)
        if not recorder or not recorder.is_recording:
            return
        self._stop_pulse()
        try:
            script = recorder.stop_recording()
        except (OSError, RuntimeError) as exc:
            logger.exception("Failed to stop recording")
            self._set_ready()
            messagebox.showerror("Recorder Error", f"Failed to stop recording:\n{exc}")
            return
        if not script.steps:
            self._set_ready()
            messagebox.showinfo("Recorder", "No actions were recorded.")
            return
        self._show_save_dialog(script)

    def _show_save_dialog(self, script: Any) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Save Recorded Script")
        dlg.geometry("420x320")
        dlg.resizable(False, False)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        pad = dict(padx=12, pady=6, sticky="ew")
        dlg.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dlg, text="Name:", font=("Segoe UI", 12)).grid(row=0, column=0, **pad)
        name_e = ctk.CTkEntry(dlg, font=("Segoe UI", 12))
        name_e.insert(0, script.name)
        name_e.grid(row=0, column=1, **pad)

        ctk.CTkLabel(dlg, text="Description:", font=("Segoe UI", 12)).grid(row=1, column=0, **pad)
        desc_e = ctk.CTkTextbox(dlg, height=80, font=("Segoe UI", 12), wrap="word")
        desc_e.insert("1.0", script.description)
        desc_e.grid(row=1, column=1, **pad)

        ctk.CTkLabel(dlg, text="Tags:", font=("Segoe UI", 12)).grid(row=2, column=0, **pad)
        tags_e = ctk.CTkEntry(dlg, font=("Segoe UI", 12), placeholder_text="comma, separated")
        tags_e.grid(row=2, column=1, **pad)

        ctk.CTkLabel(
            dlg,
            text=f"Captured {len(script.steps)} step(s)",
            font=("Segoe UI", 10),
            text_color=self._t("text_secondary", "#b9cacb"),
        ).grid(row=3, column=0, columnspan=2, pady=(8, 2))

        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.grid(row=4, column=0, columnspan=2, pady=10)

        def _save() -> None:
            name = name_e.get().strip() or script.name
            script.description = desc_e.get("1.0", "end-1c").strip() or script.description
            script.tags = [t.strip() for t in tags_e.get().split(",") if t.strip()]
            script.name = name
            safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)
            try:
                script.save(str(Path(_ensure_scripts_dir()) / f"{safe}.json"))
            except OSError as exc:
                messagebox.showerror("Save Error", f"Cannot save script:\n{exc}")
                return
            dlg.destroy()
            self.status_label.configure(text=f"Saved: {name}")

        ctk.CTkButton(bf, text="💾 Save", width=100, command=_save).pack(side="left", padx=8)
        ctk.CTkButton(bf, text="Cancel", width=100, fg_color="transparent", command=dlg.destroy).pack(
            side="left", padx=8
        )

    # ── Play ───────────────────────────────────────────────────────────

    def _on_play(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Script to Replay",
            initialdir=_ensure_scripts_dir(),
            filetypes=[("JSON Scripts", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            with Path(path).open(encoding="utf-8") as fh:
                script_data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            messagebox.showerror("Playback Error", f"Cannot load script:\n{exc}")
            return

        params: dict[str, Any] = {}
        if script_data.get("parameters"):
            params = self._show_param_dialog(script_data["parameters"])
            if params is None:
                return
        self._run_script(path, params, script_data)

    def _show_param_dialog(self, parameters: list[dict[str, str]]) -> dict[str, Any] | None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Script Parameters")
        dlg.geometry("400x" + str(min(60 + len(parameters) * 50, 500)))
        dlg.resizable(False, False)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.grid_columnconfigure(1, weight=1)
        entries: dict[str, ctk.CTkEntry] = {}
        result: dict[str, Any] = {}
        cancelled = [True]

        for i, p in enumerate(parameters):
            nm = p.get("name", f"param{i}")
            ctk.CTkLabel(dlg, text=p.get("prompt", nm), font=("Segoe UI", 11)).grid(
                row=i, column=0, padx=12, pady=6, sticky="w"
            )
            e = ctk.CTkEntry(dlg, font=("Segoe UI", 11), width=220)
            e.insert(0, p.get("default", ""))
            e.grid(row=i, column=1, padx=12, pady=6, sticky="ew")
            entries[nm] = e

        br = len(parameters)

        def _ok() -> None:
            for n, e in entries.items():
                result[n] = e.get()
            cancelled[0] = False
            dlg.destroy()

        ctk.CTkButton(dlg, text="OK", width=80, command=_ok).grid(row=br, column=0, padx=8, pady=10)
        ctk.CTkButton(dlg, text="Cancel", width=80, fg_color="transparent", command=dlg.destroy).grid(
            row=br, column=1, padx=8, pady=10, sticky="w"
        )
        dlg.wait_window()
        return None if cancelled[0] else result

    def _run_script(self, path: str, params: dict[str, Any], script_data: dict[str, Any]) -> None:
        engine = getattr(self.app, "script_engine", None)
        if engine is None:
            messagebox.showwarning("Playback", "No script engine available.")
            return
        total = len(script_data.get("steps", []))
        self._is_playing = True
        self.status_label.configure(text=f"Playing step 0/{total}…", text_color=self._t("status_running", "#95E400"))
        engine.set_progress_callback(
            lambda s, t, a, r: self.after(0, lambda: self.status_label.configure(text=f"Playing step {s}/{t}…"))
        )

        def _worker() -> None:
            try:
                res = engine.run_script(path, params)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.exception("Script execution failed in worker")
                self.after(
                    0,
                    lambda: self._set_ready(),
                )
                self.after(
                    0,
                    lambda exc=exc: messagebox.showerror("Playback Error", f"Script execution failed:\n{exc}"),
                )
                return
            self.after(0, lambda: self._on_play_done(res))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_play_done(self, result: Any) -> None:
        self._is_playing = False
        if result.success:
            msg = f"Script completed ({result.steps_completed}/{result.steps_total} steps)"
            self.status_label.configure(text=msg, text_color=self._t("status_running", "#95E400"))
            messagebox.showinfo("Playback", msg)
        else:
            self.status_label.configure(
                text=f"Playback failed: {result.error}",
                text_color=self._t("status_error", "#ff3b3b"),
            )
            messagebox.showerror("Playback Error", result.error or "Unknown error")
        self.after(5000, self._set_ready)

    # ── Script Library ─────────────────────────────────────────────────

    def _on_library(self) -> None:
        try:
            from core.recorder import ActionRecorder
        except ImportError as exc:
            logger.error("Recorder module unavailable: %s", exc)
            messagebox.showerror("Library Error", f"Recorder module unavailable:\n{exc}")
            return
        try:
            scripts = ActionRecorder.list_scripts(_ensure_scripts_dir())
        except (OSError, ValueError):
            logger.exception("Failed to list scripts")
            scripts = []

        dlg = ctk.CTkToplevel(self)
        dlg.title("📋 Script Library")
        dlg.geometry("560x480")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.grid_rowconfigure(2, weight=1)
        dlg.grid_columnconfigure(0, weight=1)

        sv = ctk.StringVar()
        ctk.CTkEntry(
            dlg,
            placeholder_text="🔍 Search by name or tags…",
            font=("Segoe UI", 12),
            textvariable=sv,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        lf = ctk.CTkScrollableFrame(dlg)
        lf.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        items: list[dict[str, Any]] = []

        def _refresh(*_: Any) -> None:
            q = sv.get().lower()
            for it in items:
                d, r = it["data"], it["row"]
                ok = (
                    q in d["name"].lower()
                    or q in d["description"].lower()
                    or any(q in t.lower() for t in d.get("tags", []))
                )
                (r.grid if (ok or not q) else r.grid_remove)()

        sv.trace_add("write", _refresh)

        for info in scripts:
            row = ctk.CTkFrame(lf, height=50, corner_radius=3)
            row.pack(fill="x", pady=2, padx=2)
            p = info.get("path", "")
            sc = 0
            try:
                with Path(p).open(encoding="utf-8") as fh:
                    sc = len(json.load(fh).get("steps", []))
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("Failed to read workflow step count: %s", exc)
            ctk.CTkLabel(row, text="📜", font=("Segoe UI", 14), width=28).pack(side="left", padx=(8, 4))
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(side="left", fill="x", expand=True, padx=4, pady=4)
            ctk.CTkLabel(
                inner,
                text=info.get("name", "Untitled"),
                font=("Segoe UI", 12, "bold"),
                text_color=self._t("text_primary", "#e2e2e8"),
            ).pack(anchor="w")
            det = f"{sc} step(s)"
            desc = info.get("description", "")
            if desc:
                det += f" — {desc[:60]}"
            ctk.CTkLabel(
                inner,
                text=det,
                font=("Segoe UI", 10),
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(anchor="w")
            tags = info.get("tags", [])
            if tags:
                ctk.CTkLabel(
                    inner,
                    text=" ".join(f"#{t}" for t in tags),
                    font=("Segoe UI", 9),
                    text_color=self._t("accent", "#00F0FF"),
                ).pack(anchor="w")

            def _run(pp: str = p) -> None:
                dlg.destroy()
                self._run_script(pp, {}, {})

            ctk.CTkButton(
                row,
                text="▶",
                width=36,
                height=36,
                fg_color=self._t("status_running", "#95E400"),
                hover_color="#6ed400",
                text_color="#ffffff",
                corner_radius=3,
                command=_run,
            ).pack(side="right", padx=6, pady=4)
            menu = tk.Menu(row, tearoff=0)
            menu.add_command(label="▶ Run", command=_run)
            menu.add_command(label="🗑 Delete", command=lambda pp=p: self._delete_script(pp, dlg))
            row.bind("<Button-3>", lambda e, m=menu: m.tk_popup(e.x_root, e.y_root))
            row.bind("<Double-Button-1>", lambda e, fn=_run: fn())
            items.append({"data": info, "row": row})

        if not scripts:
            ctk.CTkLabel(
                lf,
                text="No scripts found.\nRecord an automation or drop .json into scripts/.",
                font=("Segoe UI", 12),
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(pady=40)

        ctk.CTkButton(dlg, text="Close", width=80, fg_color="transparent", command=dlg.destroy).grid(
            row=3, column=0, pady=(4, 12)
        )

    def _delete_script(self, path: str, parent: ctk.CTkToplevel) -> None:
        if messagebox.askyesno("Delete Script", f"Delete {Path(path).name}?"):
            try:
                Path(path).unlink()
            except OSError as exc:
                messagebox.showerror("Delete Error", str(exc))
                return
            parent.destroy()
            self._on_library()

    # ── Helpers / Public API ───────────────────────────────────────────

    def _set_ready(self) -> None:
        self.status_label.configure(text="Ready", text_color=self._t("text_secondary", "#b9cacb"))

    def update_step_count(self, count: int) -> None:
        """Called from the agent loop to refresh the 'Recording… (N steps)' label."""
        recorder = getattr(self.app, "recorder", None)
        if recorder and recorder.is_recording:
            self.status_label.configure(text=f"Recording… ({count} steps)")
