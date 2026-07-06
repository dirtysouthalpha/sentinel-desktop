"""
Sentinel Desktop v28.0.0 — Workflows Tab

Workflow management tab with left-panel list and right-panel detail view.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk

from core.workflow import WorkflowEngine

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = str(Path(__file__).resolve().parent.parent.parent / "workflows")

STEP_ICONS = {
    "script": "📜",
    "action": "⚡",
    "condition": "🔀",
    "loop": "🔄",
    "sub_workflow": "📦",
    "delay": "⏱",
    "notify": "🔔",
}


class WorkflowsTab(ctk.CTkFrame):
    """Workflow management tab — list + detail + step-flow visualization."""

    def __init__(self, parent_frame: ctk.CTkFrame, app: Any) -> None:
        super().__init__(parent_frame, corner_radius=0)
        self.app = app
        self._t = app._t
        self._selected_path: str | None = None
        self._workflow_data: dict[str, Any] | None = None
        self._workflows: list[dict[str, Any]] = []
        self._running = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self.refresh_workflows()

    # ── Left Panel ────────────────────────────────────────────────────

    def _build_left_panel(self) -> None:
        t = self._t
        left = ctk.CTkFrame(self, width=300, corner_radius=4)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        # Search bar
        self._search_var = ctk.StringVar()
        search = ctk.CTkEntry(
            left,
            placeholder_text="🔍 Search workflows…",
            textvariable=self._search_var,
            font=("Segoe UI", 12),
            height=32,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        search.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        search.bind("<KeyRelease>", lambda _e: self.refresh_workflows())

        # New Workflow button
        ctk.CTkButton(
            left,
            text="＋ New Workflow",
            height=32,
            font=("Segoe UI", 12, "bold"),
            fg_color=t("accent", "#00F0FF"),
            hover_color=t("accent_hover", "#00c8d4"),
            corner_radius=4,
            command=self._new_workflow,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 4))

        # Scrollable workflow list
        self._list_container = ctk.CTkScrollableFrame(
            left,
            corner_radius=4,
            fg_color=t("bg_secondary", "#0A0C10"),
        )
        self._list_container.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._list_container.grid_columnconfigure(0, weight=1)

    # ── Right Panel ───────────────────────────────────────────────────

    def _build_right_panel(self) -> None:
        t = self._t
        right = ctk.CTkFrame(self, corner_radius=4)
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=4)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=3)
        right.grid_rowconfigure(4, weight=1)
        right.grid_rowconfigure(5, weight=1)

        # Workflow name + description
        self._name_label = ctk.CTkLabel(
            right,
            text="Select a workflow",
            font=("Segoe UI", 18, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
        )
        self._name_label.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))

        self._desc_label = ctk.CTkLabel(
            right,
            text="",
            font=("Segoe UI", 12),
            text_color=t("text_secondary", "#b9cacb"),
            wraplength=600,
        )
        self._desc_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))

        # Step flow visualization
        self._steps_frame = ctk.CTkScrollableFrame(
            right,
            corner_radius=4,
            fg_color=t("bg_secondary", "#0A0C10"),
        )
        self._steps_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))
        self._steps_frame.grid_columnconfigure(0, weight=1)

        # Run button
        self._run_btn = ctk.CTkButton(
            right,
            text="▶ Run Workflow",
            height=36,
            font=("Segoe UI", 13, "bold"),
            fg_color=t("status_running", "#95E400"),
            hover_color=t("tag_assistant", "#95E400"),
            text_color="#ffffff",
            corner_radius=4,
            command=self.run_selected_workflow,
        )
        self._run_btn.grid(row=3, column=0, sticky="ew", padx=8, pady=4)

        # Variables section header + frame
        ctk.CTkLabel(
            right,
            text="🔧 Variables",
            font=("Segoe UI", 12, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
        ).grid(row=4, column=0, sticky="nw", padx=12, pady=(4, 0))
        self._vars_frame = ctk.CTkFrame(right, corner_radius=4, fg_color=t("bg_input", "#111418"))
        self._vars_frame.grid(row=4, column=0, sticky="nsew", padx=8, pady=(28, 4))
        self._vars_frame.grid_columnconfigure(1, weight=1)

        # Output area header + textbox
        ctk.CTkLabel(
            right,
            text="📋 Output",
            font=("Segoe UI", 12, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
        ).grid(row=5, column=0, sticky="nw", padx=12, pady=(4, 0))
        self._output_text = ctk.CTkTextbox(
            right,
            height=100,
            wrap="word",
            font=("Consolas", 11),
            state="disabled",
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
        )
        self._output_text.grid(row=5, column=0, sticky="nsew", padx=8, pady=(28, 8))

    # ── Refresh workflow list ─────────────────────────────────────────

    def refresh_workflows(self) -> None:
        """Reload workflow list from disk and rebuild cards."""
        t = self._t
        query = self._search_var.get().strip().lower()
        self._workflows = WorkflowEngine.list_workflows(WORKFLOWS_DIR)

        for w in self._list_container.winfo_children():
            w.destroy()

        filtered = [
            w
            for w in self._workflows
            if query in w.get("name", "").lower() or query in w.get("description", "").lower()
        ]

        for idx, wf in enumerate(filtered):
            card = ctk.CTkFrame(
                self._list_container,
                corner_radius=4,
                height=60,
                fg_color=t("bg_input", "#111418"),
                cursor="hand2",
            )
            card.grid(row=idx, column=0, sticky="ew", padx=2, pady=2)
            card.grid_columnconfigure(0, weight=1)

            name_lbl = ctk.CTkLabel(
                card,
                text=wf.get("name", "Untitled"),
                font=("Segoe UI", 12, "bold"),
                text_color=t("text_primary", "#e2e2e8"),
                anchor="w",
            )
            name_lbl.grid(row=0, column=0, sticky="w", padx=8, pady=(4, 0))

            desc = wf.get("description", "")
            steps = wf.get("steps", 0)
            sub = ctk.CTkLabel(
                card,
                text=f"{desc}  •  {steps} step{'s' if steps != 1 else ''}",
                font=("Segoe UI", 10),
                text_color=t("text_secondary", "#b9cacb"),
                anchor="w",
            )
            sub.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))

            path = wf.get("path", "")
            for widget in (card, name_lbl, sub):
                widget.bind("<Button-1>", lambda _e, p=path: self.select_workflow(p))

            if path == self._selected_path:
                card.configure(fg_color=t("accent", "#00F0FF"))
                name_lbl.configure(text_color="#ffffff")
                sub.configure(text_color="#e0e0e0")

    # ── Select & display workflow ─────────────────────────────────────

    def select_workflow(self, path: str) -> None:
        """Load and display a workflow from the given file path."""
        self._selected_path = path

        try:
            with Path(path).open(encoding="utf-8") as f:
                self._workflow_data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load workflow %s: %s", path, exc)
            self._name_label.configure(text="Error loading workflow")
            self._desc_label.configure(text=str(exc))
            return

        wf = self._workflow_data
        self._name_label.configure(text=wf.get("name", "Untitled"))
        self._desc_label.configure(text=wf.get("description", ""))
        self._render_steps(wf.get("steps", []))
        self._render_variables(wf.get("variables", {}))
        self.refresh_workflows()

    def _render_steps(self, steps: list[dict[str, Any]]) -> None:
        """Build step-flow cards inside the steps scrollable frame."""
        t = self._t
        for w in self._steps_frame.winfo_children():
            w.destroy()

        for idx, step in enumerate(steps):
            sid = step.get("id", f"s{idx + 1}")
            stype = step.get("type", "action")
            icon = STEP_ICONS.get(stype, "❓")
            summary = self._step_summary(step)

            card = ctk.CTkFrame(self._steps_frame, corner_radius=3, fg_color=t("bg_input", "#111418"))
            card.grid(row=idx * 2, column=0, sticky="ew", padx=4, pady=(4, 0))
            card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                card,
                text=f"{icon} {sid}",
                font=("Segoe UI", 11, "bold"),
                text_color=t("accent", "#00F0FF"),
                width=120,
                anchor="w",
            ).grid(row=0, column=0, padx=(8, 4), pady=4)

            ctk.CTkLabel(
                card,
                text=summary,
                font=("Segoe UI", 11),
                text_color=t("text_primary", "#e2e2e8"),
                anchor="w",
            ).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

            # Condition branch arrows
            if stype == "condition":
                bf = ctk.CTkFrame(self._steps_frame, fg_color="transparent", height=24)
                bf.grid(row=idx * 2 + 1, column=0, sticky="ew", padx=4)
                ctk.CTkLabel(
                    bf,
                    text=f"   ├─ ✅ true → {step.get('true_next', '—')}",
                    font=("Consolas", 10),
                    text_color=t("status_running", "#95E400"),
                    anchor="w",
                ).pack(anchor="w")
                ctk.CTkLabel(
                    bf,
                    text=f"   └─ ❌ false → {step.get('false_next', '—')}",
                    font=("Consolas", 10),
                    text_color=t("status_error", "#ff3b3b"),
                    anchor="w",
                ).pack(anchor="w")
            elif idx < len(steps) - 1:
                # Connector line between steps
                ctk.CTkLabel(
                    self._steps_frame,
                    text="│",
                    font=("Consolas", 12),
                    text_color=t("text_secondary", "#b9cacb"),
                ).grid(row=idx * 2 + 1, column=0, sticky="w", padx=18)

    @staticmethod
    def _step_summary(step: dict[str, Any]) -> str:
        """Build a one-line summary for a step."""
        stype = step.get("type", "action")
        if stype == "script":
            return f"Run script: {step.get('path', '?')}"
        if stype == "action":
            act = step.get("action", {})
            params = ", ".join(f"{k}={v}" for k, v in act.items() if k != "action")
            return f"Action: {act.get('action', '?')}({params})"
        if stype == "condition":
            return f"If: {step.get('check', '?')}"
        if stype == "loop":
            return f"Loop over: {step.get('over', '?')}"
        if stype == "sub_workflow":
            return f"Sub-workflow: {step.get('path', '?')}"
        if stype == "delay":
            return f"Wait {step.get('delay_seconds', 0)}s"
        if stype == "notify":
            return f"Notify: {step.get('message', '')}"
        return stype

    # ── Variables editing ─────────────────────────────────────────────

    def _render_variables(self, variables: dict[str, Any]) -> None:
        """Show editable variable entries."""
        t = self._t
        for w in self._vars_frame.winfo_children():
            w.destroy()

        if not variables:
            ctk.CTkLabel(
                self._vars_frame,
                text="No variables defined",
                font=("Segoe UI", 10),
                text_color=t("text_secondary", "#b9cacb"),
            ).grid(row=0, column=0, columnspan=2, padx=8, pady=4)
            return

        self._var_entries: dict[str, ctk.CTkEntry] = {}
        for row, (key, val) in enumerate(variables.items()):
            ctk.CTkLabel(
                self._vars_frame,
                text=key,
                font=("Consolas", 11, "bold"),
                text_color=t("accent", "#00F0FF"),
                width=120,
                anchor="e",
            ).grid(row=row, column=0, padx=(8, 4), pady=2)
            entry = ctk.CTkEntry(
                self._vars_frame,
                font=("Consolas", 11),
                height=28,
                fg_color=t("bg_primary", "#050608"),
                text_color=t("text_primary", "#e2e2e8"),
                border_color=t("bg_hover", "#333539"),
            )
            entry.grid(row=row, column=1, sticky="ew", padx=(4, 8), pady=2)
            entry.insert(0, str(val))
            self._var_entries[key] = entry

    def _collect_variables(self) -> dict[str, str]:
        """Read current values from variable entry widgets."""
        return {k: e.get() for k, e in getattr(self, "_var_entries", {}).items()}

    # ── Run workflow ──────────────────────────────────────────────────

    def run_selected_workflow(self) -> None:
        """Execute the selected workflow in a background thread."""
        if self._running:
            return
        if not self._selected_path or not self._workflow_data:
            self._append_output("⚠ No workflow selected.\n")
            return

        self._running = True
        self._run_btn.configure(text="⏳ Running…", state="disabled")
        self._append_output("▶ Starting workflow…\n")

        path = self._selected_path
        variables = self._collect_variables()

        def _run() -> None:
            engine = WorkflowEngine()
            result = engine.run_workflow(path, variables)
            lines = [
                f"\n{'✅' if result.success else '❌'} {'Success' if result.success else 'Failed'}",
                f"Steps: {result.steps_completed}/{result.steps_total}",
                f"Time: {result.elapsed_seconds:.1f}s",
            ]
            if result.error:
                lines.append(f"Error: {result.error}")
            for sr in result.step_results:
                mark = "✓" if sr.get("success") else "✗"
                lines.append(f"  {mark} {sr}")
            self.after(0, lambda: self._append_output("\n".join(lines) + "\n"))
            self.after(0, self._finish_run)

        threading.Thread(target=_run, daemon=True).start()

    def _finish_run(self) -> None:
        self._running = False
        self._run_btn.configure(text="▶ Run Workflow", state="normal")

    # ── New workflow ──────────────────────────────────────────────────

    def _new_workflow(self) -> None:
        """Create a minimal new workflow file and select it."""
        workflows_dir = Path(WORKFLOWS_DIR)
        workflows_dir.mkdir(parents=True, exist_ok=True)
        idx = len(self._workflows) + 1
        fpath = str(workflows_dir / f"workflow_{idx}.json")
        data = {
            "name": f"New Workflow {idx}",
            "description": "Describe this workflow…",
            "steps": [{"id": "s1", "type": "action", "action": {"action": "click"}}],
            "variables": {},
        }
        WorkflowEngine.save_workflow(fpath, data)
        self.refresh_workflows()
        self.select_workflow(fpath)

    # ── Output helper ─────────────────────────────────────────────────

    def _append_output(self, text: str) -> None:
        self._output_text.configure(state="normal")
        self._output_text.insert("end", text)
        self._output_text.see("end")
        self._output_text.configure(state="disabled")
