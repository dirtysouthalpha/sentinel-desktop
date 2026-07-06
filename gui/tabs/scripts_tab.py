"""
Sentinel Desktop v30.0.0 — Script Library tab.

Two-panel layout: browseable/searchable script list on the left,
script detail + parameter entry + run controls on the right.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)

_SCRIPT_DIRS = ["scripts/it_support", "scripts/custom", "scripts/recorded"]
_CATEGORIES = ["All", "IT Support", "Custom", "Recorded"]
_DIR_MAP = {
    "IT Support": "scripts/it_support",
    "Custom": "scripts/custom",
    "Recorded": "scripts/recorded",
}


class ScriptsTab:
    """Script Library tab — browse, parameterise, and run automation scripts."""

    def __init__(self, parent_frame: ctk.CTkFrame, app: Any) -> None:
        self.app = app
        self._t = app._t
        self._scripts: list[dict[str, Any]] = []
        self._selected_script: dict[str, Any] | None = None
        self._selected_path: str | None = None
        self._param_entries: dict[str, ctk.CTkEntry] = {}
        self._active_category = "All"

        self.frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        self.frame.grid_columnconfigure(0, weight=2, minsize=320)
        self.frame.grid_columnconfigure(1, weight=3, minsize=400)
        self.frame.grid_rowconfigure(1, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self.refresh_scripts()

    # ── Left panel ────────────────────────────────────────────────────

    def _build_left_panel(self) -> None:
        left = ctk.CTkFrame(self.frame, fg_color=self._t("bg_secondary", "#0A0C10"), corner_radius=5)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 4))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(3, weight=1)

        # Search bar
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        ctk.CTkEntry(
            left,
            placeholder_text="🔍 Search scripts…",
            textvariable=self._search_var,
            height=36,
            font=("Segoe UI", 12),
            fg_color=self._t("bg_input", "#111418"),
            border_color=self._t("bg_hover", "#333539"),
            text_color=self._t("text_primary", "#e2e2e8"),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        # Category filter chips
        chips = ctk.CTkFrame(left, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        self._chip_btns: list[ctk.CTkButton] = []
        for cat in _CATEGORIES:
            btn = ctk.CTkButton(
                chips,
                text=cat,
                height=26,
                width=80,
                font=("Segoe UI", 11),
                fg_color=self._t("bg_input", "#111418"),
                hover_color=self._t("bg_hover", "#333539"),
                text_color=self._t("text_secondary", "#b9cacb"),
                corner_radius=6,
                command=lambda c=cat: self._set_category(c),
            )
            btn.pack(side="left", padx=2)
            self._chip_btns.append(btn)
        self._highlight_chip(0)

        # Script count
        self._count_label = ctk.CTkLabel(
            left,
            text="0 scripts",
            font=("Segoe UI", 10),
            text_color=self._t("text_secondary", "#b9cacb"),
        )
        self._count_label.grid(row=2, column=0, sticky="w", padx=12, pady=(4, 0))

        # Scrollable script list
        self._list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent", corner_radius=0)
        self._list_frame.grid(row=3, column=0, sticky="nsew", padx=4, pady=(4, 8))
        self._list_frame.grid_columnconfigure(0, weight=1)

    # ── Right panel ───────────────────────────────────────────────────

    def _build_right_panel(self) -> None:
        right = ctk.CTkFrame(self.frame, fg_color=self._t("bg_secondary", "#0A0C10"), corner_radius=5)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(4, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(5, weight=1)

        # Script name (large)
        self._name_label = ctk.CTkLabel(
            right,
            text="Select a script",
            font=("Segoe UI", 18, "bold"),
            text_color=self._t("text_primary", "#e2e2e8"),
            anchor="w",
        )
        self._name_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 2))

        # Description
        self._desc_label = ctk.CTkLabel(
            right,
            text="",
            font=("Segoe UI", 12),
            text_color=self._t("text_secondary", "#b9cacb"),
            wraplength=500,
            justify="left",
            anchor="w",
        )
        self._desc_label.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        # Meta: steps · author · date
        self._meta_label = ctk.CTkLabel(
            right,
            text="",
            font=("Segoe UI", 10),
            text_color=self._t("text_secondary", "#b9cacb"),
            anchor="w",
        )
        self._meta_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Parameters header
        self._params_label = ctk.CTkLabel(
            right,
            text="Parameters",
            font=("Segoe UI", 12, "bold"),
            text_color=self._t("text_primary", "#e2e2e8"),
            anchor="w",
        )
        self._params_label.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 2))

        # Dynamic parameter entry fields container
        self._params_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._params_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._params_frame.grid_columnconfigure(1, weight=1)

        # Action buttons
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="nw", padx=16, pady=(4, 4))

        self._run_btn = ctk.CTkButton(
            btn_row,
            text="▶ Run Script",
            width=140,
            height=38,
            font=("Segoe UI", 13, "bold"),
            fg_color=self._t("accent", "#00F0FF"),
            hover_color=self._t("accent_hover", "#00c8d4"),
            text_color="#ffffff",
            corner_radius=4,
            command=self.run_selected_script,
        )
        self._run_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="⏺ Record New",
            width=140,
            height=38,
            font=("Segoe UI", 13),
            fg_color=self._t("bg_input", "#111418"),
            hover_color=self._t("bg_hover", "#333539"),
            text_color=self._t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=self._open_recorder,
        ).pack(side="left")

        # Output header
        ctk.CTkLabel(
            right,
            text="Output",
            font=("Segoe UI", 12, "bold"),
            text_color=self._t("text_primary", "#e2e2e8"),
            anchor="w",
        ).grid(row=6, column=0, sticky="ew", padx=16, pady=(8, 2))

        # Output textbox
        self._output_box = ctk.CTkTextbox(
            right,
            height=120,
            font=("Consolas", 11),
            wrap="word",
            state="disabled",
            fg_color=self._t("bg_input", "#111418"),
            text_color=self._t("text_primary", "#e2e2e8"),
            corner_radius=4,
        )
        self._output_box.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 16))

    # ── Script scanning ───────────────────────────────────────────────

    def refresh_scripts(self) -> None:
        """Rescan scripts/ directory and rebuild the script list."""
        self._scripts.clear()
        base = Path(self.app.cfg.get("script_base", "."))
        for rel_dir in _SCRIPT_DIRS:
            folder = base / rel_dir
            if not folder.is_dir():
                continue
            for fp in sorted(folder.rglob("*.json")):
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    data["_path"] = str(fp)
                    data["_folder"] = rel_dir
                    self._scripts.append(data)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.debug("Skipping %s: %s", fp, exc)
        self._apply_filter()

    # ── Filtering ─────────────────────────────────────────────────────

    def _set_category(self, category: str) -> None:
        self._active_category = category
        self._highlight_chip(_CATEGORIES.index(category) if category in _CATEGORIES else 0)
        self._apply_filter()

    def _highlight_chip(self, active_idx: int) -> None:
        for i, btn in enumerate(self._chip_btns):
            if i == active_idx:
                btn.configure(fg_color=self._t("accent", "#00F0FF"), text_color="#ffffff")
            else:
                btn.configure(
                    fg_color=self._t("bg_input", "#111418"),
                    text_color=self._t("text_secondary", "#b9cacb"),
                )

    def _apply_filter(self) -> None:
        query = self._search_var.get().strip().lower()
        cat = self._active_category
        filtered = []
        for s in self._scripts:
            if cat != "All":
                expected = _DIR_MAP.get(cat, "")
                if expected and not s.get("_folder", "").startswith(expected):
                    continue
            if query and query not in s.get("name", "").lower() and query not in s.get("description", "").lower():
                continue
            filtered.append(s)
        self._populate_list(filtered)
        n = len(filtered)
        self._count_label.configure(text=f"{n} script{'s' if n != 1 else ''}")

    def _populate_list(self, scripts: list[dict[str, Any]]) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        for script in scripts:
            card = ctk.CTkFrame(
                self._list_frame,
                fg_color=self._t("bg_input", "#111418"),
                corner_radius=4,
                height=68,
            )
            card.pack(fill="x", pady=2, padx=2)
            card.pack_propagate(False)
            card.grid_columnconfigure(0, weight=1)

            name = script.get("name", "Untitled")
            desc = script.get("description", "")
            steps = len(script.get("steps", []))
            icon = script.get("icon", "📄")

            ctk.CTkLabel(
                card,
                text=f"{icon} {name}",
                font=("Segoe UI", 12, "bold"),
                text_color=self._t("text_primary", "#e2e2e8"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
            short = (desc[:60] + "…") if len(desc) > 60 else desc
            ctk.CTkLabel(
                card,
                text=short,
                font=("Segoe UI", 10),
                text_color=self._t("text_secondary", "#b9cacb"),
                anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=10)
            ctk.CTkLabel(
                card,
                text=f"{steps} step{'s' if steps != 1 else ''}",
                font=("Segoe UI", 9),
                text_color=self._t("text_secondary", "#b9cacb"),
            ).grid(row=0, column=1, rowspan=2, padx=(0, 10))

            path = script.get("_path", "")
            for widget in (card,) + tuple(card.winfo_children()):
                widget.bind("<Button-1>", lambda _e, p=path: self.select_script(p))

    # ── Script selection / detail ──────────────────────────────────────

    def select_script(self, path: str) -> None:
        """Show script details on the right panel."""
        script = next((s for s in self._scripts if s.get("_path") == path), None)
        if script is None:
            return
        self._selected_script = script
        self._selected_path = path

        self._name_label.configure(text=f"{script.get('icon', '📄')} {script.get('name', 'Untitled')}")
        self._desc_label.configure(text=script.get("description", "No description."))

        steps = len(script.get("steps", []))
        author = script.get("author", "unknown")
        created = script.get("created", "")
        if created:
            try:
                created = datetime.fromisoformat(created).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
        self._meta_label.configure(text=f"{steps} step{'s' if steps != 1 else ''}  ·  {author}  ·  {created}")
        self._build_param_fields(script)

    def _build_param_fields(self, script: dict[str, Any]) -> None:
        """Rebuild dynamic CTkEntry fields based on script parameters."""
        for w in self._params_frame.winfo_children():
            w.destroy()
        self._param_entries.clear()

        params = script.get("parameters", [])
        if not params:
            self._params_label.configure(text="Parameters  (none)")
            return
        self._params_label.configure(text=f"Parameters  ({len(params)})")

        for i, p in enumerate(params):
            lbl = p.get("label", p.get("name", ""))
            if p.get("required"):
                lbl += " *"
            ctk.CTkLabel(
                self._params_frame,
                text=lbl,
                font=("Segoe UI", 11),
                text_color=self._t("text_secondary", "#b9cacb"),
                anchor="w",
            ).grid(row=i, column=0, sticky="w", pady=3)
            entry = ctk.CTkEntry(
                self._params_frame,
                height=32,
                font=("Segoe UI", 12),
                placeholder_text=p.get("description", ""),
                fg_color=self._t("bg_input", "#111418"),
                text_color=self._t("text_primary", "#e2e2e8"),
                border_color=self._t("bg_hover", "#333539"),
            )
            entry.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
            default = p.get("default")
            if default is not None:
                entry.insert(0, str(default))
            self._param_entries[p.get("name", f"param_{i}")] = entry

    # ── Run script ─────────────────────────────────────────────────────

    def run_selected_script(self) -> None:
        """Run the selected script with current parameter values."""
        if not self._selected_script or not self._selected_path:
            self._append_output("⚠ No script selected.")
            return

        params = {name: entry.get().strip() for name, entry in self._param_entries.items()}
        self._append_output(f"▶ Running: {self._selected_script.get('name', '')}…")
        self._run_btn.configure(state="disabled", text="⏳ Running…")
        script_path = self._selected_path

        def _run() -> None:
            try:
                from core.action_executor import ActionExecutor
                from core.script_engine import ScriptEngine

                executor = ActionExecutor()
                engine = ScriptEngine(executor)
                engine.set_progress_callback(self._on_script_progress)
                result = engine.run_script(script_path, params or None)

                mark = "✅" if result.success else "❌"
                word = "Completed" if result.success else "Failed"
                lines = [
                    f"\n{mark} {word} — {result.steps_completed}/{result.steps_total} steps in {result.duration_ms}ms"
                ]
                if result.error:
                    lines.append(f"   Error: {result.error}")
                for idx, r in enumerate(result.results):
                    ok = r.get("success", False)
                    out = r.get("output", r.get("error", ""))
                    lines.append(f"   Step {idx + 1}: {'✓' if ok else '✗'} {out}")
                self._append_output("\n".join(lines))
            except (OSError, RuntimeError, ValueError) as exc:
                self._append_output(f"\n❌ Exception: {exc}")
            finally:
                self.app.root.after(0, lambda: self._run_btn.configure(state="normal", text="▶ Run Script"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_script_progress(self, step_num: int, total: int, action: str, result: dict[str, Any]) -> None:
        """Progress callback from ScriptEngine (worker thread)."""
        ok = result.get("success", False)
        out = result.get("output", result.get("error", ""))
        self.app.root.after(
            0,
            lambda: self._append_output(f"   Step {step_num}/{total}: {'✓' if ok else '✗'} {action} — {out}"),
        )

    # ── Recorder ───────────────────────────────────────────────────────

    def _open_recorder(self) -> None:
        """Open the recorder panel to create a new script."""
        try:
            if hasattr(self.app, "recorder_panel") and self.app.recorder_panel:
                self.app.recorder_panel.start_recording()
            else:
                self._append_output("⏺ Recording started — use the main chat to drive actions.")
        except (OSError, RuntimeError, AttributeError) as exc:
            self._append_output(f"⚠ Could not start recorder: {exc}")

    # ── Output helper ──────────────────────────────────────────────────

    def _append_output(self, text: str) -> None:
        """Append text to the output box (thread-safe)."""

        def _do() -> None:
            self._output_box.configure(state="normal")
            self._output_box.insert("end", text + "\n")
            self._output_box.configure(state="disabled")
            self._output_box.see("end")

        try:
            self.app.root.after(0, _do)
        except RuntimeError:
            pass
