"""Sentinel Desktop v18.0 — Neuralis Brain GUI Panel.

Brain tab for the cyberpunk HUD — a window into the shared, fleet-wide Neuralis Brain.
Surfaces all seven brain operations in a dense, themeable, offline-first layout.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)

# Source-agent color palette (stable mapping, not dynamic)
_SOURCE_COLORS: dict[str, str] = {
    "sentinel-desktop": "#00F0FF",
    "claude-code": "#95E400",
    "opencode": "#FBBC00",
    "mimo": "#FF6B6B",
    "omp": "#C084FC",
    "mcp": "#64B5F6",
    "dream-mode": "#7E57C2",
    "rss-ingestor": "#4DB6AC",
}
_SOURCE_COLOR_DEFAULT = "#b9cacb"

# Regions available for Think compose
_REGIONS = ["knowledge", "context", "preference", "decision"]

# Refresh interval for stats + feed (milliseconds)
_REFRESH_MS = 5000


class BrainTab(ctk.CTkFrame):
    """Neuralis Brain panel — fleet memory at a glance."""

    def __init__(self, parent_frame: ctk.CTkFrame, app: Any) -> None:
        super().__init__(parent_frame, corner_radius=0)
        self.app = app
        self._t = app._t

        self._available: bool = False
        self._pulse_state: bool = False
        self._refresh_job: str | None = None
        self._advanced_visible: bool = False
        self._busy_recall: bool = False
        self._busy_think: bool = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_stats_header()
        self._build_body()

        # Kick off the first refresh and pulse
        self.after(100, self._start_tick)

    # ── Stats header ──────────────────────────────────────────────────

    def _build_stats_header(self) -> None:
        t = self._t
        hdr = ctk.CTkFrame(self, height=52, corner_radius=4)
        hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        hdr.grid_columnconfigure(1, weight=1)

        # Pulse dot (brain-is-alive motif)
        self._pulse_dot = ctk.CTkLabel(
            hdr,
            text="●",
            font=("Segoe UI", 18),
            text_color=t("text_secondary", "#b9cacb"),
            width=24,
        )
        self._pulse_dot.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=4)

        self._status_line = ctk.CTkLabel(
            hdr,
            text="● Brain offline (homeserver:8000 unreachable)",
            font=("Consolas", 12, "bold"),
            text_color=t("status_error", "#ff3b3b"),
            anchor="w",
        )
        self._status_line.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))

        self._region_line = ctk.CTkLabel(
            hdr,
            text="",
            font=("Consolas", 10),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="w",
        )
        self._region_line.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(0, 6))

        ctk.CTkButton(
            hdr,
            text="↻",
            width=32,
            height=32,
            font=("Segoe UI", 14),
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=self._refresh_now,
        ).grid(row=0, column=2, rowspan=2, padx=(4, 8), pady=4)

    # ── Body: two-column split ────────────────────────────────────────

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

    # ── Left panel: live feed + advanced ─────────────────────────────

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
        t = self._t
        left = ctk.CTkFrame(parent, corner_radius=4)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=0)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # Live feed label bar
        feed_bar = ctk.CTkFrame(left, height=30, corner_radius=4)
        feed_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        feed_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            feed_bar,
            text="LIVE FEED",
            font=("Consolas", 10, "bold"),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        # Feed scrollable
        self._feed_frame = ctk.CTkScrollableFrame(
            left,
            corner_radius=4,
            fg_color=t("bg_secondary", "#0A0C10"),
        )
        self._feed_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(4, 0))
        self._feed_frame.grid_columnconfigure(0, weight=1)
        self._feed_placeholder = None

        # Advanced toggle
        self._advanced_toggle = ctk.CTkButton(
            left,
            text="▶ Advanced (opinions / fire / context)",
            height=28,
            font=("Segoe UI", 11),
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_secondary", "#b9cacb"),
            corner_radius=4,
            anchor="w",
            command=self._toggle_advanced,
        )
        self._advanced_toggle.grid(row=2, column=0, sticky="ew", padx=4, pady=(4, 0))

        self._advanced_panel = ctk.CTkFrame(left, corner_radius=4)
        self._build_advanced_panel(self._advanced_panel)
        # Hidden by default — shown on toggle

        self._left_footer = ctk.CTkFrame(left, height=4, corner_radius=0)
        self._left_footer.grid(row=4, column=0, sticky="ew")

    def _build_advanced_panel(self, panel: ctk.CTkFrame) -> None:
        t = self._t
        panel.grid_columnconfigure(0, weight=1)

        # Opinions
        ctk.CTkLabel(
            panel,
            text="Opinions",
            font=("Segoe UI", 11, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))

        opinions_row = ctk.CTkFrame(panel, corner_radius=4)
        opinions_row.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        opinions_row.grid_columnconfigure(0, weight=1)

        self._opinions_entry = ctk.CTkEntry(
            opinions_row,
            placeholder_text="topic…",
            font=("Segoe UI", 11),
            height=28,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        self._opinions_entry.grid(row=0, column=0, sticky="ew", padx=(4, 2), pady=4)

        ctk.CTkButton(
            opinions_row,
            text="Ask",
            width=50,
            height=28,
            font=("Segoe UI", 10, "bold"),
            fg_color=t("accent", "#00F0FF"),
            text_color="#ffffff",
            corner_radius=4,
            command=self._do_opinions,
        ).grid(row=0, column=1, padx=(2, 4), pady=4)

        self._opinions_output = ctk.CTkTextbox(
            panel,
            height=60,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_secondary", "#b9cacb"),
        )
        self._opinions_output.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))

        # Fire neuron
        ctk.CTkLabel(
            panel,
            text="Fire Neuron",
            font=("Segoe UI", 11, "bold"),
            text_color=t("text_primary", "#e2e2e8"),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(4, 2))

        fire_row = ctk.CTkFrame(panel, corner_radius=4)
        fire_row.grid(row=4, column=0, sticky="ew", padx=4, pady=(0, 4))
        fire_row.grid_columnconfigure(0, weight=1)

        self._fire_entry = ctk.CTkEntry(
            fire_row,
            placeholder_text="neuron_id…",
            font=("Consolas", 11),
            height=28,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        self._fire_entry.grid(row=0, column=0, sticky="ew", padx=(4, 2), pady=4)

        self._fire_btn = ctk.CTkButton(
            fire_row,
            text="⚡ Fire",
            width=60,
            height=28,
            font=("Segoe UI", 10, "bold"),
            fg_color=t("tag_action", "#FBBC00"),
            text_color="#ffffff",
            corner_radius=4,
            command=self._do_fire,
        )
        self._fire_btn.grid(row=0, column=1, padx=(2, 4), pady=4)

        self._fire_status = ctk.CTkLabel(
            panel,
            text="",
            font=("Consolas", 10),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="w",
        )
        self._fire_status.grid(row=5, column=0, sticky="w", padx=8, pady=(0, 8))

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._advanced_panel.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 4))
            self._advanced_toggle.configure(
                text="▼ Advanced (opinions / fire / context)",
            )
        else:
            self._advanced_panel.grid_forget()
            self._advanced_toggle.configure(
                text="▶ Advanced (opinions / fire / context)",
            )

    # ── Right panel: recall / search + think ─────────────────────────

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        t = self._t
        right = ctk.CTkFrame(parent, corner_radius=4)
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=0)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=2)
        right.grid_rowconfigure(3, weight=1)

        # Recall / Search section
        rs_hdr = ctk.CTkLabel(
            right,
            text="RECALL / SEARCH",
            font=("Consolas", 10, "bold"),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="w",
        )
        rs_hdr.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))

        rs_inputs = ctk.CTkFrame(right, corner_radius=4)
        rs_inputs.grid(row=0, column=0, sticky="ew", padx=4, pady=(24, 0))
        rs_inputs.grid_columnconfigure(0, weight=1)

        self._recall_entry = ctk.CTkEntry(
            rs_inputs,
            placeholder_text="recall: context query…",
            font=("Segoe UI", 11),
            height=30,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        self._recall_entry.grid(row=0, column=0, sticky="ew", padx=(4, 2), pady=(4, 2))

        recall_btn = ctk.CTkButton(
            rs_inputs,
            text="Recall",
            width=60,
            height=30,
            font=("Segoe UI", 10, "bold"),
            fg_color=t("accent", "#00F0FF"),
            text_color="#ffffff",
            corner_radius=4,
            command=self._do_recall,
        )
        recall_btn.grid(row=0, column=1, padx=(2, 4), pady=(4, 2))

        self._search_entry = ctk.CTkEntry(
            rs_inputs,
            placeholder_text="search: free text…",
            font=("Segoe UI", 11),
            height=30,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        self._search_entry.grid(row=1, column=0, sticky="ew", padx=(4, 2), pady=(2, 4))

        search_btn = ctk.CTkButton(
            rs_inputs,
            text="Search",
            width=60,
            height=30,
            font=("Segoe UI", 10, "bold"),
            fg_color=t("bg_hover", "#333539"),
            text_color=t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=self._do_search,
        )
        search_btn.grid(row=1, column=1, padx=(2, 4), pady=(2, 4))

        self._recall_entry.bind("<Return>", lambda _: self._do_recall())
        self._search_entry.bind("<Return>", lambda _: self._do_search())

        # Results area
        self._results_text = ctk.CTkTextbox(
            right,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
        )
        self._results_text.grid(row=1, column=0, sticky="nsew", padx=4, pady=(4, 0))

        # Divider
        ctk.CTkLabel(
            right,
            text="THINK  —  write to brain",
            font=("Consolas", 10, "bold"),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(8, 2))

        # Think compose
        think_frame = ctk.CTkFrame(right, corner_radius=4)
        think_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=(20, 0))
        think_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            think_frame,
            text="region",
            font=("Segoe UI", 10),
            text_color=t("text_secondary", "#b9cacb"),
            width=48,
            anchor="e",
        ).grid(row=0, column=0, padx=(8, 4), pady=(4, 2))

        self._region_var = ctk.StringVar(value="knowledge")
        self._region_menu = ctk.CTkOptionMenu(
            think_frame,
            values=_REGIONS,
            variable=self._region_var,
            font=("Segoe UI", 11),
            height=28,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            button_color=t("bg_hover", "#333539"),
            corner_radius=4,
        )
        self._region_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(4, 2))

        ctk.CTkLabel(
            think_frame,
            text="topic",
            font=("Segoe UI", 10),
            text_color=t("text_secondary", "#b9cacb"),
            width=48,
            anchor="e",
        ).grid(row=1, column=0, padx=(8, 4), pady=2)

        self._think_topic = ctk.CTkEntry(
            think_frame,
            placeholder_text="short topic tag…",
            font=("Segoe UI", 11),
            height=28,
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
            border_color=t("bg_hover", "#333539"),
        )
        self._think_topic.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=2)

        ctk.CTkLabel(
            think_frame,
            text="content",
            font=("Segoe UI", 10),
            text_color=t("text_secondary", "#b9cacb"),
            width=48,
            anchor="ne",
        ).grid(row=2, column=0, padx=(8, 4), pady=2, sticky="n")

        self._think_content = ctk.CTkTextbox(
            think_frame,
            height=60,
            wrap="word",
            font=("Segoe UI", 11),
            corner_radius=4,
            fg_color=t("bg_input", "#111418"),
            text_color=t("text_primary", "#e2e2e8"),
        )
        self._think_content.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=2)

        self._remember_btn = ctk.CTkButton(
            think_frame,
            text="Remember",
            height=30,
            font=("Segoe UI", 11, "bold"),
            fg_color=t("status_running", "#95E400"),
            text_color="#ffffff",
            corner_radius=4,
            command=self._do_think,
        )
        self._remember_btn.grid(
            row=3,
            column=1,
            sticky="e",
            padx=(0, 8),
            pady=(4, 8),
        )

        self._think_status = ctk.CTkLabel(
            think_frame,
            text="",
            font=("Consolas", 10),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="w",
        )
        self._think_status.grid(
            row=3,
            column=0,
            columnspan=1,
            sticky="w",
            padx=(8, 4),
            pady=(4, 8),
        )

        # Think output / extra results space
        self._think_output = ctk.CTkScrollableFrame(
            right,
            corner_radius=4,
            fg_color=t("bg_secondary", "#0A0C10"),
        )
        self._think_output.grid(row=3, column=0, sticky="nsew", padx=4, pady=(4, 4))
        self._think_output.grid_columnconfigure(0, weight=1)

    # ── Tick loop: refresh stats + feed every 5s ──────────────────────

    def _start_tick(self) -> None:
        self._refresh_now()
        self._pulse_tick()

    def _schedule_tick(self) -> None:
        if self.winfo_exists():
            self._refresh_job = self.after(_REFRESH_MS, self._refresh_now)

    def _refresh_now(self) -> None:
        threading.Thread(target=self._bg_refresh, daemon=True).start()

    def _bg_refresh(self) -> None:
        from core import brain

        available = brain.is_available()
        if available:
            try:
                brain_stats = brain.stats()
            except Exception:
                brain_stats = {}
            try:
                feed_data = brain.search("")
            except Exception:
                feed_data = {}
        else:
            brain_stats = {}
            feed_data = {}

        if self.winfo_exists():
            self.after(0, lambda: self._apply_refresh(available, brain_stats, feed_data))

    def _apply_refresh(
        self,
        available: bool,
        brain_stats: dict[str, Any],
        feed_data: dict[str, Any],
    ) -> None:
        self._available = available
        self._render_stats(available, brain_stats)
        self._render_feed(available, feed_data)
        self._apply_online_state(available)
        self._schedule_tick()

    def _apply_online_state(self, available: bool) -> None:
        state = "normal" if available else "disabled"
        try:
            self._remember_btn.configure(state=state)
            self._region_menu.configure(state=state)
        except Exception:
            pass

    # ── Stats header rendering ────────────────────────────────────────

    def _render_stats(self, available: bool, brain_stats: dict[str, Any]) -> None:
        t = self._t
        if not available:
            self._status_line.configure(
                text="● Brain offline  (homeserver:8000 unreachable)",
                text_color=t("status_error", "#ff3b3b"),
            )
            self._region_line.configure(text="")
            self._pulse_dot.configure(text_color=t("status_error", "#ff3b3b"))
            return

        totals = brain_stats.get("totals", {})
        neurons = totals.get("neurons", 0)
        synapses = totals.get("synapses", 0)

        region_counts: list[dict[str, Any]] = brain_stats.get("neurons_per_region", [])
        top_regions = sorted(region_counts, key=lambda r: r.get("count", 0), reverse=True)[:5]
        region_text = "  ·  ".join(f"{r['region']} {r['count']:,}" for r in top_regions)

        recent = brain_stats.get("recent_neurons_24h", [])
        last_write_s = ""
        if recent:
            try:
                last_created = recent[0].get("created", "")
                if last_created:
                    ts = last_created[:19].replace("T", " ")
                    struct = time.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    age = int(time.time() - time.mktime(struct))
                    if age < 60:
                        last_write_s = f" · last write {age}s ago"
                    elif age < 3600:
                        last_write_s = f" · last write {age // 60}m ago"
                    else:
                        last_write_s = f" · last write {age // 3600}h ago"
            except Exception:
                pass

        sources = len({r.get("source", "") for r in recent if r.get("source")})

        self._status_line.configure(
            text=(
                f"● Brain online · {neurons:,} thoughts · "
                f"{synapses:,} synapses · {sources} sources{last_write_s}"
            ),
            text_color=t("status_running", "#95E400"),
        )
        self._region_line.configure(text=region_text or "no regions")
        self._pulse_dot.configure(text_color=t("status_running", "#95E400"))

    # ── Feed rendering ────────────────────────────────────────────────

    def _render_feed(self, available: bool, feed_data: dict[str, Any]) -> None:
        t = self._t
        for w in self._feed_frame.winfo_children():
            w.destroy()

        if not available:
            ctk.CTkLabel(
                self._feed_frame,
                text="Brain offline — no feed available",
                font=("Segoe UI", 11),
                text_color=t("text_secondary", "#b9cacb"),
            ).grid(row=0, column=0, padx=8, pady=12)
            return

        neurons: list[dict[str, Any]] = feed_data.get("neurons", [])
        if not neurons:
            ctk.CTkLabel(
                self._feed_frame,
                text="No recent thoughts",
                font=("Segoe UI", 11),
                text_color=t("text_secondary", "#b9cacb"),
            ).grid(row=0, column=0, padx=8, pady=12)
            return

        for idx, neuron in enumerate(neurons[:30]):
            self._render_feed_row(idx, neuron)

    def _render_feed_row(self, idx: int, neuron: dict[str, Any]) -> None:
        t = self._t
        source = neuron.get("source", "unknown")
        region = neuron.get("region", "")
        content = neuron.get("content", "").replace("\n", " ")
        snippet = content[:80] + ("…" if len(content) > 80 else "")
        created = neuron.get("created", "")

        # Relative time
        age_str = ""
        if created:
            try:
                ts_str = created[:19].replace("T", " ")
                struct = time.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                age = int(time.time() - time.mktime(struct))
                if age < 60:
                    age_str = f"{age}s ago"
                elif age < 3600:
                    age_str = f"{age // 60}m ago"
                else:
                    age_str = f"{age // 3600}h ago"
            except Exception:
                age_str = created[:10]

        src_color = _SOURCE_COLORS.get(source, _SOURCE_COLOR_DEFAULT)

        card = ctk.CTkFrame(
            self._feed_frame,
            corner_radius=3,
            fg_color=t("bg_input", "#111418"),
        )
        card.grid(row=idx, column=0, sticky="ew", padx=2, pady=1)
        card.grid_columnconfigure(1, weight=1)

        # Source dot
        ctk.CTkLabel(
            card,
            text="◉",
            font=("Segoe UI", 12),
            text_color=src_color,
            width=20,
        ).grid(row=0, column=0, rowspan=2, padx=(6, 0), pady=4, sticky="n")

        # Source + region chip
        chip_text = f"{source}  ·  {region}" if region else source
        ctk.CTkLabel(
            card,
            text=chip_text[:60],
            font=("Consolas", 9, "bold"),
            text_color=src_color,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(6, 4), pady=(4, 0))

        # Snippet + age
        right_bar = ctk.CTkFrame(card, corner_radius=0, fg_color="transparent")
        right_bar.grid(row=1, column=1, sticky="ew", padx=(6, 4), pady=(0, 4))
        right_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right_bar,
            text=snippet,
            font=("Segoe UI", 10),
            text_color=t("text_primary", "#e2e2e8"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            right_bar,
            text=age_str,
            font=("Consolas", 9),
            text_color=t("text_secondary", "#b9cacb"),
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(4, 0))

    # ── Pulse animation ───────────────────────────────────────────────

    def _pulse_tick(self) -> None:
        if not self.winfo_exists():
            return
        self._pulse_state = not self._pulse_state
        if self._available:
            color = "#00F0FF" if self._pulse_state else "#95E400"
        else:
            color = "#ff3b3b" if self._pulse_state else "#331010"
        try:
            self._pulse_dot.configure(text_color=color)
        except Exception:
            return
        self.after(1200, self._pulse_tick)

    # ── Recall operation ──────────────────────────────────────────────

    def _do_recall(self) -> None:
        query = self._recall_entry.get().strip()
        if not query or self._busy_recall:
            return
        self._busy_recall = True
        self._set_results("Recalling…")
        threading.Thread(
            target=self._bg_recall,
            args=(query,),
            daemon=True,
        ).start()

    def _bg_recall(self, query: str) -> None:
        from core import brain

        try:
            data = brain.recall(query)
        except Exception as exc:
            data = {"error": str(exc)}
        if self.winfo_exists():
            self.after(0, lambda: self._render_recall_results(data))

    def _render_recall_results(self, data: dict[str, Any]) -> None:
        self._busy_recall = False
        if "error" in data:
            self._set_results(f"Error: {data['error']}")
            return

        neurons: list[dict[str, Any]] = data.get("neurons", [])
        if not neurons:
            self._set_results("Nothing found.")
            return

        lines = []
        for i, n in enumerate(neurons[:20], 1):
            content = n.get("content", "").replace("\n", " ")
            snippet = content[:100] + ("…" if len(content) > 100 else "")
            score = n.get("score", n.get("similarity", ""))
            score_str = f"  [{score:.2f}]" if isinstance(score, float) else ""
            lines.append(f"▸ {i}.{score_str} {snippet}")

        self._set_results("\n".join(lines))

    # ── Search operation ──────────────────────────────────────────────

    def _do_search(self) -> None:
        query = self._search_entry.get().strip()
        if self._busy_recall:
            return
        self._busy_recall = True
        label = f'Searching "{query}"…' if query else "Loading feed…"
        self._set_results(label)
        threading.Thread(
            target=self._bg_search,
            args=(query,),
            daemon=True,
        ).start()

    def _bg_search(self, query: str) -> None:
        from core import brain

        try:
            data = brain.search(query)
        except Exception as exc:
            data = {"error": str(exc)}
        if self.winfo_exists():
            self.after(0, lambda: self._render_search_results(data))

    def _render_search_results(self, data: dict[str, Any]) -> None:
        self._busy_recall = False
        if "error" in data:
            self._set_results(f"Error: {data['error']}")
            return

        neurons: list[dict[str, Any]] = data.get("neurons", [])
        if not neurons:
            self._set_results("No results.")
            return

        lines = []
        for i, n in enumerate(neurons[:20], 1):
            content = n.get("content", "").replace("\n", " ")
            snippet = content[:100] + ("…" if len(content) > 100 else "")
            score = n.get("score", n.get("similarity", ""))
            score_str = f"  [{score:.2f}]" if isinstance(score, float) else ""
            lines.append(f"▸ {i}.{score_str} {snippet}")

        self._set_results("\n".join(lines))

    def _set_results(self, text: str) -> None:
        self._results_text.configure(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.insert("end", text)
        self._results_text.configure(state="disabled")

    # ── Think operation ───────────────────────────────────────────────

    def _do_think(self) -> None:
        if not self._available:
            return
        topic = self._think_topic.get().strip()
        content = self._think_content.get("1.0", "end").strip()
        region = self._region_var.get()
        if not topic or not content or self._busy_think:
            return
        self._busy_think = True
        self._remember_btn.configure(text="Storing…", state="disabled")
        self._think_status.configure(text="")
        threading.Thread(
            target=self._bg_think,
            args=(topic, content, region),
            daemon=True,
        ).start()

    def _bg_think(self, topic: str, content: str, region: str) -> None:
        from core import brain

        full_content = f"[{topic}] {content}"
        try:
            data = brain.think(content=full_content, region=region)
            ok = data.get("success") or data.get("id") or "neuron_id" in data
            err = None if ok else data.get("error", "unknown")
        except Exception as exc:
            ok = False
            err = str(exc)
        if self.winfo_exists():
            self.after(0, lambda: self._finish_think(ok, err))

    def _finish_think(self, ok: bool, err: str | None) -> None:
        self._busy_think = False
        self._remember_btn.configure(text="Remember", state="normal")
        if ok:
            self._think_topic.delete(0, "end")
            self._think_content.delete("1.0", "end")
            self._think_status.configure(
                text="✓ Stored",
                text_color=self._t("status_running", "#95E400"),
            )
            self._refresh_now()
        else:
            self._think_status.configure(
                text=f"✗ {err or 'failed'}",
                text_color=self._t("status_error", "#ff3b3b"),
            )

    # ── Advanced: opinions ────────────────────────────────────────────

    def _do_opinions(self) -> None:
        topic = self._opinions_entry.get().strip()
        if not topic:
            return
        self._opinions_output.configure(state="normal")
        self._opinions_output.delete("1.0", "end")
        self._opinions_output.insert("end", "Loading…")
        self._opinions_output.configure(state="disabled")
        threading.Thread(
            target=self._bg_opinions,
            args=(topic,),
            daemon=True,
        ).start()

    def _bg_opinions(self, topic: str) -> None:
        try:
            from core.brain.client import get_default_client

            client = get_default_client()
            # opinions endpoint: GET /brain/opinions?topic=...
            data = client._request("GET", "/brain/opinions", params={"topic": topic})
        except Exception as exc:
            data = {"error": str(exc)}
        if self.winfo_exists():
            self.after(0, lambda: self._render_opinions(data))

    def _render_opinions(self, data: dict[str, Any]) -> None:
        self._opinions_output.configure(state="normal")
        self._opinions_output.delete("1.0", "end")
        if "error" in data:
            self._opinions_output.insert("end", f"Error: {data['error']}")
        else:
            neurons = data.get("neurons", [])
            if neurons:
                for n in neurons[:5]:
                    c = n.get("content", "").replace("\n", " ")[:80]
                    self._opinions_output.insert("end", f"· {c}\n")
            else:
                self._opinions_output.insert("end", "No opinions found.")
        self._opinions_output.configure(state="disabled")

    # ── Advanced: fire ────────────────────────────────────────────────

    def _do_fire(self) -> None:
        raw = self._fire_entry.get().strip()
        if not raw:
            return
        try:
            neuron_id = int(raw)
        except ValueError:
            self._fire_status.configure(text="✗ invalid neuron_id")
            return
        self._fire_status.configure(text="Firing…")
        threading.Thread(
            target=self._bg_fire,
            args=(neuron_id,),
            daemon=True,
        ).start()

    def _bg_fire(self, neuron_id: int) -> None:
        from core import brain

        try:
            data = brain.fire(neuron_id)
            ok = not data.get("error")
        except Exception:
            ok = False
        if self.winfo_exists():
            msg = "✓ Fired" if ok else "✗ failed"
            color = (
                self._t("status_running", "#95E400") if ok else self._t("status_error", "#ff3b3b")
            )
            self.after(
                0,
                lambda: self._fire_status.configure(text=msg, text_color=color),
            )
