"""Fleet Mesh dashboard tab for Sentinel Desktop GUI."""
from __future__ import annotations

import logging
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)


class FleetTab:
    """Displays fleet mesh status: nodes, tasks, events, leader."""

    def __init__(self, parent_frame: ctk.CTkFrame, app: Any) -> None:
        self.app = app
        self._t = app._t
        self.frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        self._build_ui()
        self._poll_interval = 2000  # ms
        self._scheduled_poll: str | None = None
        self._start_polling()

    def _build_ui(self) -> None:
        """Build the fleet dashboard UI."""
        # Title
        title = ctk.CTkLabel(
            self.frame,
            text="🛰️ Fleet Mesh",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=(10, 5), padx=10, anchor="w")

        # Status frame
        status_frame = ctk.CTkFrame(self.frame)
        status_frame.pack(fill="x", padx=10, pady=5)

        self._leader_label = ctk.CTkLabel(
            status_frame, text="Leader: —", font=ctk.CTkFont(size=12)
        )
        self._leader_label.pack(anchor="w", padx=10, pady=2)

        self._nodes_label = ctk.CTkLabel(
            status_frame, text="Nodes: 0", font=ctk.CTkFont(size=12)
        )
        self._nodes_label.pack(anchor="w", padx=10, pady=2)

        self._tasks_label = ctk.CTkLabel(
            status_frame, text="Tasks: 0 active", font=ctk.CTkFont(size=12)
        )
        self._tasks_label.pack(anchor="w", padx=10, pady=2)

        # Node list
        nodes_header = ctk.CTkLabel(
            self.frame, text="Nodes", font=ctk.CTkFont(size=14, weight="bold")
        )
        nodes_header.pack(pady=(10, 2), padx=10, anchor="w")

        self._nodes_text = ctk.CTkTextbox(self.frame, height=120, font=ctk.CTkFont(size=11))
        self._nodes_text.pack(fill="x", padx=10, pady=2)

        # Event log
        events_header = ctk.CTkLabel(
            self.frame, text="Recent Events", font=ctk.CTkFont(size=14, weight="bold")
        )
        events_header.pack(pady=(10, 2), padx=10, anchor="w")

        self._events_text = ctk.CTkTextbox(self.frame, height=200, font=ctk.CTkFont(size=11))
        self._events_text.pack(fill="both", expand=True, padx=10, pady=2)

        # Control buttons
        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)

        self._refresh_btn = ctk.CTkButton(
            btn_frame, text="🔄 Refresh", command=self._refresh, width=100
        )
        self._refresh_btn.pack(side="left", padx=5)

        self._clear_btn = ctk.CTkButton(
            btn_frame, text="🗑️ Clear Events", command=self._clear_events, width=120
        )
        self._clear_btn.pack(side="left", padx=5)

    def _start_polling(self) -> None:
        """Start periodic refresh."""
        self._refresh()
        self._schedule_next_poll()

    def _schedule_next_poll(self) -> None:
        """Schedule the next poll."""
        if hasattr(self.app, 'root') and self.app.root is not None:
            try:
                self._scheduled_poll = self.app.root.after(
                    self._poll_interval, self._poll_callback
                )
            except RuntimeError:
                pass  # Root destroyed

    def _poll_callback(self) -> None:
        """Called by after() — reschedule and refresh."""
        self._refresh()
        self._schedule_next_poll()

    def _refresh(self) -> None:
        """Refresh the display with current fleet state."""
        try:
            # Get fleet data from the app's mesh components
            mesh_data = getattr(self.app, '_fleet_data', None)
            if mesh_data is None:
                self._leader_label.configure(text="Leader: — (mesh not started)")
                return

            leader = mesh_data.get("leader", "—")
            nodes = mesh_data.get("nodes", [])
            tasks = mesh_data.get("tasks", [])

            self._leader_label.configure(text=f"Leader: {leader}")
            self._nodes_label.configure(text=f"Nodes: {len(nodes)}")
            self._tasks_label.configure(text=f"Tasks: {len(tasks)} active")

            # Update nodes text
            self._nodes_text.configure(state="normal")
            self._nodes_text.delete("0.0", "end")
            for node in nodes:
                status_icon = "🟢" if node.get("alive") else "🔴"
                self._nodes_text.insert(
                    "end",
                    f"{status_icon} {node.get('node_id', '?')} "
                    f"(pri={node.get('priority', '?')}) — "
                    f"{node.get('status', '?')}\n",
                )
            self._nodes_text.configure(state="disabled")

        except Exception as e:
            logger.debug("Fleet refresh error: %s", e)

    def _clear_events(self) -> None:
        """Clear the event log."""
        self._events_text.configure(state="normal")
        self._events_text.delete("0.0", "end")
        self._events_text.configure(state="disabled")

    def add_event(self, event_text: str) -> None:
        """Add an event to the log (thread-safe)."""
        try:
            if hasattr(self.app, 'root') and self.app.root is not None:
                self.app.root.after(0, lambda: self._append_event(event_text))
        except RuntimeError:
            pass

    def _append_event(self, event_text: str) -> None:
        """Append event on main thread."""
        self._events_text.configure(state="normal")
        self._events_text.insert("0.0", event_text + "\n")
        # Cap at 500 lines
        lines = self._events_text.get("0.0", "end").split("\n")
        if len(lines) > 500:
            self._events_text.delete("500.0", "end")
        self._events_text.configure(state="disabled")

    def destroy(self) -> None:
        """Clean up polling."""
        if self._scheduled_poll and hasattr(self.app, 'root') and self.app.root is not None:
            try:
                self.app.root.after_cancel(self._scheduled_poll)
            except RuntimeError:
                pass
