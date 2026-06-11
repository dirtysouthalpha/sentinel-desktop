"""Sentinel Desktop v12.0 — Memory & Conductor Tab.

Split-view tab with a Memory sub-tab (semantic facts + episodic history)
and a Conductor sub-tab (goal decomposition + parallel execution).
"""

import asyncio
import logging
import threading
from typing import Any

import customtkinter as ctk

from core.memory.episodic import EpisodicMemory
from core.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)


class MemoryTab(ctk.CTkFrame):
    """Memory and Conductor management tab."""

    def __init__(self, parent_frame: ctk.CTkFrame, app: Any) -> None:
        """Build the memory tab layout.

        Args:
            parent_frame: Parent frame to embed this tab into.
            app: Main SentinelApp instance for theme and callbacks.
        """
        super().__init__(parent_frame, corner_radius=0)
        self.app = app
        self._t = app._t

        self._semantic = SemanticMemory()
        self._episodic = EpisodicMemory()
        self._selected_key: str | None = None
        self._running_conductor = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_sub_tabs()
        self._refresh_facts()

    # ── Sub-tab switcher ──────────────────────────────────────────────

    def _build_sub_tabs(self) -> None:
        t = self._t
        bar = ctk.CTkFrame(self, height=40, corner_radius=4)
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        bar.grid_columnconfigure(2, weight=1)

        self._sub_btn_memory = ctk.CTkButton(
            bar,
            text="🧠 Memory",
            width=120,
            height=32,
            font=("Segoe UI", 12, "bold"),
            fg_color=t("accent", "#00F0FF"),
            text_color="#ffffff",
            corner_radius=4,
            command=lambda: self._switch_sub("memory"),
        )
        self._sub_btn_memory.grid(row=0, column=0, padx=(8, 4), pady=4)

        self._sub_btn_conductor = ctk.CTkButton(
            bar,
            text="⚡ Conductor",
            width=120,
            height=32,
            font=("Segoe UI", 12, "bold"),
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=lambda: self._switch_sub("conductor"),
        )
        self._sub_btn_conductor.grid(row=0, column=1, padx=4, pady=4)

        # Container for sub-panels
        self._container = ctk.CTkFrame(self, corner_radius=0)
        self._container.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._container.grid_columnconfigure(0, weight=1)
        self._container.grid_rowconfigure(0, weight=1)

        self._memory_panel = ctk.CTkFrame(
            self._container, corner_radius=4,
        )
        self._conductor_panel = ctk.CTkFrame(
            self._container, corner_radius=4,
        )

        self._build_memory_panel()
        self._build_conductor_panel()
        self._switch_sub("memory")

    def _switch_sub(self, which: str) -> None:
        t = self._t
        self._memory_panel.grid_forget()
        self._conductor_panel.grid_forget()

        if which == "memory":
            self._memory_panel.grid(
                row=0, column=0, sticky="nsew",
            )
            self._sub_btn_memory.configure(
                fg_color=t("accent", "#00F0FF"),
                text_color="#ffffff",
            )
            self._sub_btn_conductor.configure(
                fg_color=t("bg_input", "#111418"),
                text_color=t("text_primary", "#e2e2e8"),
            )
        else:
            self._conductor_panel.grid(
                row=0, column=0, sticky="nsew",
            )
            self._sub_btn_conductor.configure(
                fg_color=t("accent", "#00F0FF"),
                text_color="#ffffff",
            )
            self._sub_btn_memory.configure(
                fg_color=t("bg_input", "#111418"),
                text_color=t("text_primary", "#e2e2e8"),
            )

    # ── Memory Panel ─────────────────────────────────────────────────

    def _build_memory_panel(self) -> None:
        t = self._t
        panel = self._memory_panel
        panel.grid_columnconfigure(0, weight=2)
        panel.grid_columnconfigure(1, weight=3)
        panel.grid_rowconfigure(1, weight=1)

        # Top bar
        top = ctk.CTkFrame(panel, height=40, corner_radius=4)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        top.grid_columnconfigure(1, weight=1)

        self._search_var = ctk.StringVar()
        search = ctk.CTkEntry(
            top,
            placeholder_text="🔍 Search facts…",
            textvariable=self._search_var,
            font=("Segoe UI", 12),
            height=32,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        search.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=4)
        top.grid_columnconfigure(0, weight=1)
        search.bind("<KeyRelease>", lambda _: self._refresh_facts())

        ctk.CTkButton(
            top,
            text="＋ Store Fact",
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color=t("status_running", "#95E400"),
            text_color="#ffffff",
            corner_radius=4,
            command=self._show_store_dialog,
        ).grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkButton(
            top,
            text="↻",
            width=36,
            height=32,
            font=("Segoe UI", 14),
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=self._refresh_facts,
        ).grid(row=0, column=2, padx=(4, 8), pady=4)

        # Left: fact list
        left = ctk.CTkScrollableFrame(
            panel, corner_radius=4,
            fg_color=t("bg_secondary", "#0A0C10"),
        )
        left.grid(row=1, column=0, sticky="nsew", padx=(4, 2), pady=(0, 4))
        left.grid_columnconfigure(0, weight=1)
        self._facts_list = left

        # Right: fact detail + episodes
        right = ctk.CTkFrame(panel, corner_radius=4)
        right.grid(row=1, column=1, sticky="nsew", padx=(2, 4), pady=(0, 4))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=2)
        right.grid_rowconfigure(2, weight=1)

        # Fact detail
        self._fact_detail = ctk.CTkTextbox(
            right,
            wrap="word",
            font=("Consolas", 11),
            state="disabled",
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
        )
        self._fact_detail.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 2))

        # Episodes section
        ctk.CTkLabel(
            right,
            text="📋 Recent Episodes",
            font=("Segoe UI", 11, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(4, 0))

        self._episodes_text = ctk.CTkTextbox(
            right,
            height=120,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_secondary", "#b9cacb"),
        )
        self._episodes_text.grid(
            row=2, column=0, sticky="nsew", padx=4, pady=(2, 4),
        )

    # ── Conductor Panel ──────────────────────────────────────────────

    def _build_conductor_panel(self) -> None:
        t = self._t
        panel = self._conductor_panel
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=2)
        panel.grid_rowconfigure(3, weight=1)

        # Goal input bar
        top = ctk.CTkFrame(panel, height=44, corner_radius=4)
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        top.grid_columnconfigure(0, weight=1)

        self._goal_var = ctk.StringVar()
        goal_entry = ctk.CTkEntry(
            top,
            placeholder_text="Enter goal (e.g. Login to firewall and check ARP table)…",
            textvariable=self._goal_var,
            font=("Segoe UI", 12),
            height=36,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        goal_entry.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=4)
        top.grid_columnconfigure(0, weight=1)

        self._run_conductor_btn = ctk.CTkButton(
            top,
            text="▶ Run",
            width=80,
            height=36,
            font=("Segoe UI", 12, "bold"),
            fg_color=t("status_running", "#95E400"),
            text_color="#ffffff",
            corner_radius=4,
            command=self._run_conductor,
        )
        self._run_conductor_btn.grid(row=0, column=1, padx=4, pady=4)

        # Timeout slider
        timeout_frame = ctk.CTkFrame(top, corner_radius=4)
        timeout_frame.grid(row=0, column=2, padx=(4, 8), pady=4)
        ctk.CTkLabel(
            timeout_frame,
            text="⏱",
            font=("Segoe UI", 12),
            text_color=t("text_secondary", "#b9cacb"),
        ).pack(side="left", padx=(4, 0))
        self._timeout_slider = ctk.CTkSlider(
            timeout_frame,
            from_=10,
            to=300,
            width=100,
            height=20,
            number_of_steps=10,
        )
        self._timeout_slider.set(120)
        self._timeout_slider.pack(side="left", padx=4)
        self._timeout_label = ctk.CTkLabel(
            timeout_frame,
            text="120s",
            font=("Consolas", 10),
            text_color=t("text_secondary", "#b9cacb"),
            width=40,
        )
        self._timeout_label.pack(side="left", padx=(0, 4))
        self._timeout_slider.configure(
            command=lambda v: self._timeout_label.configure(
                text=f"{int(v)}s",
            ),
        )

        # Subtask progress area
        self._subtasks_frame = ctk.CTkScrollableFrame(
            panel,
            corner_radius=4,
            fg_color=t("bg_secondary", "#0A0C10"),
        )
        self._subtasks_frame.grid(
            row=1, column=0, sticky="nsew", padx=4, pady=(0, 4),
        )
        self._subtasks_frame.grid_columnconfigure(0, weight=1)

        # Result area
        ctk.CTkLabel(
            panel,
            text="📋 Result",
            font=("Segoe UI", 11, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(4, 0))

        self._conductor_output = ctk.CTkTextbox(
            panel,
            wrap="word",
            font=("Consolas", 11),
            state="disabled",
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
        )
        self._conductor_output.grid(
            row=3, column=0, sticky="nsew", padx=4, pady=(2, 4),
        )

    # ── Memory: refresh fact list ────────────────────────────────────

    def _refresh_facts(self) -> None:
        t = self._t
        query = self._search_var.get().strip()

        for w in self._facts_list.winfo_children():
            w.destroy()

        try:
            if query:
                results = self._semantic.query(query, limit=50)
                keys = [r.get("key", "") for r in results]
            else:
                keys = self._semantic.list_keys()
        except Exception as exc:
            logger.debug("Memory refresh error: %s", exc)
            keys = []

        if not keys:
            ctk.CTkLabel(
                self._facts_list,
                text="No facts stored yet",
                font=("Segoe UI", 11),
                text_color=t("text_secondary", "#b9cacb"),
            ).grid(row=0, column=0, padx=8, pady=8)
            self._refresh_episodes()
            return

        for idx, key in enumerate(keys):
            card = ctk.CTkFrame(
                self._facts_list,
                corner_radius=4,
                height=36,
                fg_color=t("bg_input", "#111418"),
                cursor="hand2",
            )
            card.grid(row=idx, column=0, sticky="ew", padx=2, pady=1)
            card.grid_columnconfigure(0, weight=1)

            lbl = ctk.CTkLabel(
                card,
                text=key,
                font=("Consolas", 11),
                text_color=t("text_primary", "#e2e2e8"),
                anchor="w",
            )
            lbl.grid(row=0, column=0, sticky="w", padx=8, pady=4)

            for widget in (card, lbl):
                widget.bind(
                    "<Button-1>",
                    lambda _, k=key: self._select_fact(k),
                )

            if key == self._selected_key:
                card.configure(fg_color=t("accent", "#00F0FF"))
                lbl.configure(text_color="#ffffff")

        self._refresh_episodes()

    def _select_fact(self, key: str) -> None:
        self._selected_key = key

        try:
            fact = self._semantic.recall(key)
        except Exception as exc:
            logger.debug("Recall error: %s", exc)
            fact = None

        self._fact_detail.configure(state="normal")
        self._fact_detail.delete("1.0", "end")

        if fact is None:
            self._fact_detail.insert("end", f"Key: {key}\n\n(not found)")
        else:
            lines = [
                f"Key:       {fact.get('key', key)}",
                f"Value:     {fact.get('value', '')}",
                f"Category:  {fact.get('category', '—')}",
                f"Tags:      {', '.join(fact.get('tags', [])) or '—'}",
                f"Source:    {fact.get('source', '—')}",
                f"Created:   {fact.get('created_at', '—')}",
                f"Updated:   {fact.get('updated_at', '—')}",
                f"Accessed:  {fact.get('access_count', 0)}x",
            ]
            self._fact_detail.insert("end", "\n".join(lines))

            # Delete button at the bottom
            self._fact_detail.insert("end", "\n\n")
            self._fact_detail.insert("end", "[Press Delete key to remove]")

        self._fact_detail.configure(state="disabled")
        self._refresh_facts()

    def _refresh_episodes(self) -> None:
        try:
            episodes = self._episodic.recall(limit=20)
        except Exception as exc:
            logger.debug("Episodes error: %s", exc)
            episodes = []

        self._episodes_text.configure(state="normal")
        self._episodes_text.delete("1.0", "end")

        if not episodes:
            self._episodes_text.insert("end", "No episodes recorded yet.")
        else:
            for ep in episodes:
                goal = ep.get("goal", "—")
                ts = ep.get("started_at", "")
                actions = ep.get("actions", [])
                status = ep.get("status", "?")
                icon = "✓" if status == "completed" else "○"
                line = (
                    f"{icon} [{ts[:16] if ts else '—'}] "
                    f"{goal[:60]}  ({len(actions)} actions)\n"
                )
                self._episodes_text.insert("end", line)

        self._episodes_text.configure(state="disabled")

    # ── Memory: store dialog ─────────────────────────────────────────

    def _show_store_dialog(self) -> None:
        t = self._t
        dialog = ctk.CTkToplevel(self)
        dialog.title("Store New Fact")
        dialog.geometry("400x320")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, corner_radius=4)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        frame.grid_columnconfigure(1, weight=1)

        fields = [
            ("Key:", "key_entry", ""),
            ("Value:", "value_entry", ""),
            ("Category:", "cat_entry", ""),
            ("Tags (comma-sep):", "tags_entry", ""),
        ]

        entries: dict[str, ctk.CTkEntry] = {}
        for row, (label, attr, default) in enumerate(fields):
            ctk.CTkLabel(
                frame,
                text=label,
                font=("Segoe UI", 11),
                text_color=t("text_secondary", "#b9cacb"),
                anchor="e",
                width=120,
            ).grid(row=row, column=0, padx=(8, 4), pady=4)
            entry = ctk.CTkEntry(
                frame,
                font=("Consolas", 11),
                height=28,
                fg_color=t("bg_primary", "#050608"),
                text_color=t("text_primary", "#e2e2e8"),
                border_color=t("bg_hover", "#333539"),
            )
            entry.grid(row=row, column=1, sticky="ew", padx=(4, 8), pady=4)
            if default:  # pragma: no cover
                entry.insert(0, default)
            entries[attr] = entry

        def _save() -> None:
            key = entries["key_entry"].get().strip()
            value = entries["value_entry"].get().strip()
            category = entries["cat_entry"].get().strip()
            tags_raw = entries["tags_entry"].get().strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

            if not key or not value:
                return

            try:
                self._semantic.store(
                    key, value, category, tags, source="gui",
                )
            except Exception as exc:
                logger.warning("Store failed: %s", exc)

            dialog.destroy()
            self._refresh_facts()

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(
            row=len(fields), column=0, columnspan=2, pady=(12, 8),
        )
        ctk.CTkButton(
            btn_frame,
            text="Save",
            width=100,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color=t("status_running", "#95E400"),
            text_color="#ffffff",
            corner_radius=4,
            command=_save,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=32,
            font=("Segoe UI", 11),
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=dialog.destroy,
        ).pack(side="left", padx=8)

        entries["key_entry"].focus_set()

    # ── Conductor: run ───────────────────────────────────────────────

    def _run_conductor(self) -> None:
        goal = self._goal_var.get().strip()
        if not goal or self._running_conductor:
            return

        self._running_conductor = True
        self._run_conductor_btn.configure(
            text="⏳ Running…", state="disabled",
        )
        timeout = int(self._timeout_slider.get())

        self._set_conductor_output("▶ Decomposing goal…\n")

        def _run() -> None:
            try:
                from core.conductor.coordinator import Conductor

                conductor = Conductor()

                async def _async_run() -> dict[str, Any]:
                    return await conductor.run(goal, timeout=float(timeout))

                result = asyncio.run(_async_run())

                lines = [
                    f"{'✅' if result.get('success') else '❌'} "
                    f"{'Completed' if result.get('success') else 'Failed'}",
                    f"Subtasks: {result.get('total_subtasks', '?')}",
                    f"Time: {result.get('elapsed_ms', 0) / 1000:.1f}s",
                    "",
                ]
                for st in result.get("results", []):
                    status = st.get("status", "?")
                    icon = {"success": "✓", "error": "✗", "timeout": "⏱"}.get(status, "?")
                    desc = st.get("description", st.get("subtask_id", ""))
                    lines.append(f"  {icon} {desc}")
                    if st.get("error"):
                        lines.append(f"    Error: {st['error']}")

                if result.get("error"):
                    lines.append(f"\nError: {result['error']}")

                self.after(0, lambda: self._set_conductor_output(
                    "\n".join(lines) + "\n",
                ))
                self.after(
                    0,
                    lambda: self._render_subtask_cards(
                        result.get("results", []),
                    ),
                )

            except Exception as exc:
                msg = f"❌ Error: {exc}\n"
                self.after(
                    0,
                    lambda: self._set_conductor_output(msg),
                )
            finally:
                self.after(0, self._finish_conductor)

        threading.Thread(target=_run, daemon=True).start()

    def _finish_conductor(self) -> None:
        self._running_conductor = False
        self._run_conductor_btn.configure(
            text="▶ Run", state="normal",
        )

    def _render_subtask_cards(self, results: list[dict[str, Any]]) -> None:
        t = self._t
        for w in self._subtasks_frame.winfo_children():
            w.destroy()

        status_colors = {
            "success": t("status_running", "#95E400"),
            "error": t("status_error", "#ff3b3b"),
            "timeout": t("tag_action", "#FBBC00"),
            "pending": t("text_secondary", "#b9cacb"),
        }

        for idx, st in enumerate(results):
            status = st.get("status", "pending")
            color = status_colors.get(status, t("text_secondary", "#b9cacb"))
            desc = st.get("description", st.get("subtask_id", f"task-{idx}"))
            task_type = st.get("task_type", "?")

            card = ctk.CTkFrame(
                self._subtasks_frame,
                corner_radius=3,
                fg_color=t("bg_input", "#111418"),
            )
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=2)
            card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                card,
                text="●",
                font=("Segoe UI", 12),
                text_color=color,
                width=24,
            ).grid(row=0, column=0, padx=(8, 0), pady=4)

            ctk.CTkLabel(
                card,
                text=f"[{task_type}] {desc[:80]}",
                font=("Segoe UI", 11),
                text_color=t("text_primary", "#e2e2e8"),
                anchor="w",
            ).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

    # ── Output helpers ───────────────────────────────────────────────

    def _set_conductor_output(self, text: str) -> None:
        self._conductor_output.configure(state="normal")
        self._conductor_output.delete("1.0", "end")
        self._conductor_output.insert("end", text)
        self._conductor_output.configure(state="disabled")
