"""Sentinel Desktop v3.0 — History Tab.

Run history browser with session replay and log export.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)


class HistoryTab(ctk.CTkFrame):
    """Run history browser — session list + detail timeline."""

    def __init__(self, parent: ctk.CTkFrame, app: Any) -> None:
        """Build the history tab layout.

        Args:
            parent: Parent frame to embed this tab in.
            app: Main :class:`SentinelApp` instance for theme access.

        """
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.sessions: list[dict[str, Any]] = []
        self.selected_index = -1

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        self._build_left()
        self._build_right()
        self.refresh_history()

    def _t(self, key: str, fallback: str = "#ffffff") -> str:
        return self.app._t(key, fallback) if hasattr(self.app, "_t") else fallback

    # ── Left panel ────────────────────────────────────────────────────

    def _build_left(self) -> None:
        left = ctk.CTkFrame(self, fg_color=self._t("bg_secondary", "#0A0C10"), corner_radius=4)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        # Filter bar
        filter_frame = ctk.CTkFrame(left, fg_color="transparent")
        filter_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            filter_frame,
            text="📁 Run History",
            font=("Segoe UI", 14, "bold"),
            text_color=self._t("text_primary", "#e2e2e8"),
        ).pack(side="left")

        self.filter_var = ctk.StringVar(value="All")
        filter_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.filter_var,
            values=["All", "Today", "This Week", "Failed"],
            width=100,
            height=28,
            fg_color=self._t("bg_input", "#111418"),
            button_color=self._t("accent", "#00F0FF"),
            text_color=self._t("text_primary", "#e2e2e8"),
            command=lambda _: self.refresh_history(),
        )
        filter_menu.pack(side="right")

        # Search
        self.search_entry = ctk.CTkEntry(
            left,
            placeholder_text="Search sessions...",
            height=32,
            fg_color=self._t("bg_input", "#111418"),
            text_color=self._t("text_primary", "#e2e2e8"),
            border_color=self._t("border", "#333539"),
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.search_entry.bind("<KeyRelease>", lambda _: self.refresh_history())

        # Session list
        self.session_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.session_list.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)

    # ── Right panel ───────────────────────────────────────────────────

    def _build_right(self) -> None:
        right = ctk.CTkFrame(self, fg_color=self._t("bg_secondary", "#0A0C10"), corner_radius=4)
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=4)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        self._build_right_header(right)
        self._build_right_actions(right)
        self.timeline = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.timeline.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.output_text = ctk.CTkTextbox(
            right,
            height=120,
            font=("Consolas", 11),
            fg_color=self._t("bg_primary", "#050608"),
            text_color=self._t("text_secondary", "#b9cacb"),
        )
        self.output_text.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 12))

    def _build_right_header(self, right: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(right, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.goal_label = ctk.CTkLabel(
            header,
            text="Select a session to view details",
            font=("Segoe UI", 16, "bold"),
            text_color=self._t("text_primary", "#e2e2e8"),
            wraplength=600,
            justify="left",
        )
        self.goal_label.pack(side="left", fill="x", expand=True)

    def _build_right_actions(self, right: ctk.CTkFrame) -> None:
        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.status_badge = ctk.CTkLabel(actions, text="", font=("Segoe UI", 11))
        self.status_badge.pack(side="left")
        self.replay_btn = ctk.CTkButton(
            actions,
            text="🔄 Replay",
            width=90,
            height=30,
            fg_color=self._t("accent", "#00F0FF"),
            hover_color=self._t("bg_hover", "#333539"),
            command=self._replay_session,
        )
        self.replay_btn.pack(side="right", padx=4)
        self.export_btn = ctk.CTkButton(
            actions,
            text="📋 Export Log",
            width=100,
            height=30,
            fg_color=self._t("bg_input", "#111418"),
            hover_color=self._t("bg_hover", "#333539"),
            text_color=self._t("text_primary", "#e2e2e8"),
            command=self._export_log,
        )
        self.export_btn.pack(side="right", padx=4)

    # ── Data ──────────────────────────────────────────────────────────

    def _parse_forensic_log(self, flog: list[dict[str, Any]]) -> None:
        """Group forensic log entries into sessions and append to self.sessions."""
        current_session: dict[str, Any] | None = None
        current_goal: str = ""
        for entry in flog:
            step = entry.get("step", {})
            action = step.get("action", "")
            entry_goal = entry.get("goal", "")

            # A new session starts when a "start" action appears or the goal changes.
            if action == "start" or (entry_goal and entry_goal != current_goal):
                if current_session is not None and current_session["steps"]:
                    self._finalize_session(current_session)
                current_session = {"steps": [], "goal": "", "start": "", "status": ""}
                current_goal = entry_goal

            if current_session is None:
                current_session = {"steps": [], "goal": "", "start": "", "status": ""}
                current_goal = entry_goal

            if action == "finish":
                current_session["status"] = "completed"
                current_session["summary"] = step.get("summary", "")
            current_session["steps"].append(entry)

        if current_session is not None and current_session["steps"]:
            self._finalize_session(current_session)

    def refresh_history(self) -> None:
        """Reload session history from forensic log."""
        self.sessions.clear()

        if hasattr(self.app, "engine") and self.app.engine:
            flog = getattr(self.app.engine, "forensic_log", [])
            if flog:
                self._parse_forensic_log(flog)

            notes = getattr(self.app.engine, "notes", [])
            if notes and not self.sessions:
                self.sessions.append(
                    {
                        "goal": "Previous session",
                        "start": datetime.now().isoformat(),
                        "status": "completed",
                        "steps": [],
                        "notes": notes,
                    },
                )

        if not self.sessions:
            self.sessions.append(
                {
                    "goal": "No sessions recorded yet",
                    "start": datetime.now().isoformat(),
                    "status": "empty",
                    "steps": [],
                },
            )

        self._apply_filter()
        self._render_sessions()

    def _finalize_session(self, session: dict[str, Any]) -> None:
        """Fill in derived fields and append to self.sessions."""
        if not session["goal"]:
            session["goal"] = session["steps"][0].get("goal", "Unknown")
        if not session["start"]:
            session["start"] = session["steps"][0].get("timestamp", "")
        if not session["status"]:
            session["status"] = "completed" if session["steps"][-1].get("ok", True) else "failed"
        self.sessions.append(session)

    def _apply_filter(self) -> None:
        """Apply current filter to sessions."""
        f = self.filter_var.get()
        now = datetime.now()
        if f == "Today":
            self.sessions = [
                s for s in self.sessions if s.get("start", "").startswith(now.strftime("%Y-%m-%d"))
            ]
        elif f == "This Week":
            week_ago = (now - timedelta(days=7)).isoformat()
            self.sessions = [s for s in self.sessions if s.get("start", "") >= week_ago]
        elif f == "Failed":
            self.sessions = [s for s in self.sessions if s.get("status") == "failed"]

    def _render_sessions(self) -> None:
        """Render session cards in left panel."""
        for w in self.session_list.winfo_children():
            w.destroy()

        query = self.search_entry.get().lower() if hasattr(self, "search_entry") else ""
        for i, session in enumerate(self.sessions):
            goal = session.get("goal", "Unknown")
            if query and query not in goal.lower():
                continue

            status = session.get("status", "unknown")
            icon = {"completed": "✅", "failed": "❌", "running": "🔄", "empty": "📭"}.get(
                status,
                "❓",
            )
            steps = len(session.get("steps", []))
            start = session.get("start", "")[:19].replace("T", " ")

            card = ctk.CTkFrame(
                self.session_list,
                fg_color=self._t("bg_input", "#111418")
                if i != self.selected_index
                else self._t("accent", "#00F0FF"),
                corner_radius=3,
                height=60,
            )
            card.pack(fill="x", pady=2, padx=4)
            card.pack_propagate(False)

            text_color = self._t("text_primary", "#e2e2e8")
            sub_color = self._t("text_secondary", "#b9cacb")

            ctk.CTkLabel(
                card,
                text=f"{icon} {goal[:50]}",
                font=("Segoe UI", 11, "bold"),
                text_color=text_color,
                anchor="w",
            ).pack(fill="x", padx=8, pady=(6, 0))

            ctk.CTkLabel(
                card,
                text=f"{start}  •  {steps} steps",
                font=("Segoe UI", 9),
                text_color=sub_color,
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 4))

            idx = i
            card.bind("<Button-1>", lambda _e, idx=idx: self.select_session(idx))

    def select_session(self, index: int) -> None:
        """Show session details in right panel."""
        self.selected_index = index
        if index < 0 or index >= len(self.sessions):
            return

        session = self.sessions[index]
        self.goal_label.configure(text=session.get("goal", "Unknown"))

        status = session.get("status", "unknown")
        status_colors = {
            "completed": self._t("status_running", "#95E400"),
            "failed": self._t("status_error", "#ff3b3b"),
            "running": self._t("accent", "#00F0FF"),
            "empty": self._t("text_secondary", "#b9cacb"),
        }
        self.status_badge.configure(
            text=f"● {status.upper()}",
            text_color=status_colors.get(status, "#b9cacb"),
        )

        self._render_session_timeline(session)
        self._render_session_output(session)
        self._render_sessions()

    def _render_session_timeline(self, session: dict) -> None:
        """Rebuild the step timeline widget from session data."""
        for w in self.timeline.winfo_children():
            w.destroy()
        for i, step_data in enumerate(session.get("steps", [])):
            step = step_data.get("step", step_data)
            action = step.get("action", "unknown")
            ok = step_data.get("ok", True)
            ts = step_data.get("timestamp", "")[11:19]
            if ok:
                color = self._t("status_running", "#95E400")
            else:
                color = self._t("status_error", "#ff3b3b")
            icon = "✓" if ok else "✗"
            row = ctk.CTkFrame(self.timeline, fg_color="transparent", height=28)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(
                row,
                text=f"  {icon} Step {i + 1}: {action}",
                font=("Consolas", 11),
                text_color=color,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=ts,
                font=("Consolas", 9),
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(side="right")

    def _render_session_output(self, session: dict) -> None:
        """Populate the output textbox with session notes and summary."""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        summary = session.get("summary", "")
        if summary:
            self.output_text.insert("end", f"Summary: {summary}\n\n")
        notes = session.get("notes", [])
        if notes:
            self.output_text.insert("end", "Notes:\n")
            for n in notes:
                self.output_text.insert("end", f"  • {n}\n")
        self.output_text.configure(state="disabled")

    def _replay_session(self) -> None:
        """Re-run the selected session's goal."""
        if self.selected_index < 0 or self.selected_index >= len(self.sessions):
            return
        session = self.sessions[self.selected_index]
        goal = session.get("goal", "")
        if goal and hasattr(self.app, "_on_submit"):
            self.app.goal_entry.delete("1.0", "end")
            self.app.goal_entry.insert("1.0", goal)
            self.app._on_submit()

    def _export_log(self) -> None:
        """Export forensic log as text file."""
        if self.selected_index < 0 or self.selected_index >= len(self.sessions):
            return
        session = self.sessions[self.selected_index]

        export_path = (
            Path.home() / "Desktop" / f"sentinel_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with export_path.open("w", encoding="utf-8") as f:
                f.write("Sentinel Desktop — Session Log\n")
                f.write(f"{'=' * 50}\n")
                f.write(f"Goal: {session.get('goal', '')}\n")
                f.write(f"Status: {session.get('status', '')}\n")
                f.write(f"Started: {session.get('start', '')}\n")
                f.write(f"Steps: {len(session.get('steps', []))}\n")
                f.write(f"{'=' * 50}\n\n")

                f.writelines(
                    f"Step {i + 1}: {json.dumps(step, indent=2, default=str)}\n\n"
                    for i, step in enumerate(session.get("steps", []))
                )
        except OSError as exc:
            logger.error("Export failed: %s", exc)
            return

        self.output_text.configure(state="normal")
        self.output_text.insert("end", f"\n Log exported to: {export_path}")
        self.output_text.configure(state="disabled")
