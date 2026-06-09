"""Sentinel Desktop v18.0 — Main GUI Application.

Cyberpunk HUD interface with sidebar navigation, live metrics,
animated status indicators, and full Override-brand theming.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from config import Config
from gui.overlay import ActionOverlay
from gui.themes import THEMES, apply_theme, get_theme
from gui.tray import SentinelTray
from gui.tray import is_available as _tray_available

logger = logging.getLogger(__name__)

_VERSION = "18.0"

# Sidebar tab definitions: (key, icon, label, module, class)
_TAB_DEFS = [
    ("dashboard", "\U0001f5a5", "Dashboard", None, None),
    (
        "scripts",
        "\U0001f4dc",
        "Scripts",
        "gui.tabs.scripts_tab",
        "ScriptsTab",
    ),
    (
        "workflows",
        "\U0001f500",
        "Workflows",
        "gui.tabs.workflows_tab",
        "WorkflowsTab",
    ),
    (
        "memory",
        "\U0001f9e0",
        "Memory",
        "gui.tabs.memory_tab",
        "MemoryTab",
    ),
    (
        "history",
        "\U0001f4c1",
        "History",
        "gui.tabs.history_tab",
        "HistoryTab",
    ),
    (
        "settings",
        "\u2699",
        "Settings",
        "gui.tabs.settings_tab",
        "SettingsTab",
    ),
]


class SentinelApp:
    """Main application window — cyberpunk HUD with sidebar nav."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cfg = config.load()
        self._setup_theme()
        self._setup_window()
        self._initialize_state()
        self._setup_overlay_and_tray()
        self._build_ui()
        self._setup_keyboard_shortcuts()

    # ── Theme ────────────────────────────────────────────────────────

    def _setup_theme(self) -> None:
        theme_name = self.cfg.get("theme", "sentinel")
        self.current_theme = get_theme(theme_name)
        apply_theme(theme_name)
        self._t = lambda key, fb="": self.current_theme.get(key, fb)

    # ── Window ───────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.root = ctk.CTk()
        self.root.title(f"SENTINEL DESKTOP v{_VERSION}")
        self.root.geometry("1280x820")
        self.root.minsize(960, 640)
        self.root.configure(fg_color=self._t("bg_primary", "#050608"))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _initialize_state(self) -> None:
        self.engine: Any = None
        self.engine_thread: threading.Thread | None = None
        self._approval_event = threading.Event()
        self._stop_btn: Any = None
        self._run_btn: Any = None
        self._chip_btns: list[Any] = []
        self._active_tab = "dashboard"
        self._sidebar_collapsed = False
        self._status_pulse_on = False
        self._start_time = time.monotonic()
        self._compact_mode = False

    def _setup_overlay_and_tray(self) -> None:
        self.overlay = ActionOverlay(self.root)
        self.tray: SentinelTray = None  # type: ignore[assignment]

    # ── UI Build ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_sidebar()
        self._build_content_area()
        self._build_status_bar()
        self._build_input()

    # ── Header ───────────────────────────────────────────────────────

    def _build_header(self) -> None:
        header = ctk.CTkFrame(
            self.root,
            height=48,
            corner_radius=0,
            fg_color=self._t("bg_secondary", "#0A0C10"),
        )
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        # Logo + title
        ctk.CTkLabel(
            header,
            text="\U0001f6e1\ufe0f SENTINEL DESKTOP",
            font=("Segoe UI", 15, "bold"),
            text_color=self._t("accent", "#00F0FF"),
        ).grid(row=0, column=0, sticky="w", padx=(12, 4))

        # Version badge
        ctk.CTkLabel(
            header,
            text=f"v{_VERSION}",
            font=("Segoe UI", 9),
            text_color=self._t("text_secondary", "#b9cacb"),
            fg_color=self._t("bg_tertiary", "#111418"),
            corner_radius=3,
            padx=6,
        ).grid(row=0, column=0, sticky="w", padx=(210, 0))

        # Status — center
        self.status_label = ctk.CTkLabel(
            header,
            text="\u25cf IDLE",
            font=("Segoe UI", 12, "bold"),
            text_color=self._t("status_idle", "#849495"),
        )
        self.status_label.grid(row=0, column=1, padx=10)

        # Compact mode toggle
        ctk.CTkButton(
            header,
            text="\u25a1" if not self._compact_mode else "\u25a3",
            width=28,
            height=28,
            font=("Segoe UI", 12),
            fg_color=self._t("bg_tertiary", "#111418"),
            hover_color=self._t("bg_hover", "#333539"),
            text_color=self._t("text_secondary", "#b9cacb"),
            corner_radius=3,
            command=self._toggle_compact_mode,
        ).grid(row=0, column=2, padx=(0, 4))

        # Settings gear
        ctk.CTkButton(
            header,
            text="\u2699",
            width=28,
            height=28,
            font=("Segoe UI", 14),
            fg_color=self._t("bg_tertiary", "#111418"),
            hover_color=self._t("bg_hover", "#333539"),
            text_color=self._t("text_secondary", "#b9cacb"),
            corner_radius=3,
            command=self._open_settings,
        ).grid(row=0, column=3, padx=(0, 12))

        # Provider label
        provider = self.cfg.get("provider", "none")
        model = self.cfg.get("model", "none")
        self.provider_label = ctk.CTkLabel(
            header,
            text=f"{provider} / {model}",
            font=("Segoe UI", 10),
            text_color=self._t("text_tertiary", "#849495"),
        )
        self.provider_label.grid(row=0, column=4, padx=(0, 12))

        self._build_mode_badges(header)

    def _build_mode_badges(self, header: Any) -> None:
        badges = []
        if self.cfg.get("dry_run"):
            badges.append(
                ("DRY-RUN", "#000000", self._t("tag_action", "#FBBC00")),
            )
        if self.cfg.get("autonomous"):
            badges.append(
                (
                    "AUTONOMOUS",
                    "#ffffff",
                    self._t("status_error", "#ff3b3b"),
                ),
            )
        if self.cfg.get("stealth_input"):
            badges.append(
                ("STEALTH", "#ffffff", self._t("accent", "#00F0FF")),
            )
        for i, (text, fg, bg) in enumerate(badges):
            ctk.CTkLabel(
                header,
                text=text,
                font=("Segoe UI", 10, "bold"),
                text_color=fg,
                fg_color=bg,
                corner_radius=3,
                padx=6,
            ).grid(row=0, column=5 + i, padx=4)

    # ── Sidebar ──────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        self._sidebar_frame = ctk.CTkFrame(
            self.root,
            width=200,
            corner_radius=0,
            fg_color=self._t("sidebar_bg", "#0A0C10"),
        )
        self._sidebar_frame.grid(
            row=1, column=0, sticky="ns", padx=0, pady=0,
        )
        self._sidebar_frame.grid_propagate(False)
        self._sidebar_frame.grid_rowconfigure(
            len(_TAB_DEFS) + 1, weight=1,
        )

        # Hamburger
        self._hamburger_btn = ctk.CTkButton(
            self._sidebar_frame,
            text="\u2630",
            width=36,
            height=36,
            font=("Segoe UI", 14),
            fg_color=self._t("sidebar_bg", "#0A0C10"),
            hover_color=self._t("bg_hover", "#333539"),
            text_color=self._t("text_secondary", "#b9cacb"),
            corner_radius=3,
            command=self._toggle_sidebar,
        )
        self._hamburger_btn.grid(row=0, column=0, padx=4, pady=(8, 4))

        self._sidebar_buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, icon, label, _mod, _cls) in enumerate(_TAB_DEFS):
            btn = ctk.CTkButton(
                self._sidebar_frame,
                text=f"  {icon}  {label}",
                anchor="w",
                height=38,
                font=("Segoe UI", 12),
                fg_color=self._t("sidebar_bg", "#0A0C10"),
                hover_color=self._t("bg_hover", "#333539"),
                text_color=self._t("text_secondary", "#b9cacb"),
                corner_radius=3,
                border_width=0,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.grid(row=i + 1, column=0, sticky="ew", padx=4, pady=1)
            self._sidebar_buttons[key] = btn
        self._highlight_sidebar_tab("dashboard")

    def _toggle_sidebar(self) -> None:
        self._sidebar_collapsed = not self._sidebar_collapsed
        width = 48 if self._sidebar_collapsed else 200
        self._sidebar_frame.configure(width=width)
        for i, (key, icon, label, _, _) in enumerate(_TAB_DEFS):
            btn = self._sidebar_buttons[key]
            if self._sidebar_collapsed:
                btn.configure(text=f"  {icon}", width=40)
            else:
                btn.configure(
                    text=f"  {icon}  {label}", width=192,
                )

    def _highlight_sidebar_tab(self, active_key: str) -> None:
        accent = self._t("accent", "#00F0FF")
        text_dim = self._t("text_secondary", "#b9cacb")
        bg_active = self._t("bg_hover", "#333539")
        bg_idle = self._t("sidebar_bg", "#0A0C10")
        for key, btn in self._sidebar_buttons.items():
            if key == active_key:
                btn.configure(
                    fg_color=bg_active,
                    text_color=accent,
                    border_width=2,
                )
            else:
                btn.configure(
                    fg_color=bg_idle,
                    text_color=text_dim,
                    border_width=0,
                )

    # ── Content Area ─────────────────────────────────────────────────

    def _build_content_area(self) -> None:
        self._content_frame = ctk.CTkFrame(
            self.root,
            corner_radius=0,
            fg_color=self._t("bg_primary", "#050608"),
        )
        self._content_frame.grid(
            row=1, column=1, sticky="nsew", padx=0, pady=0,
        )
        self._content_frame.grid_columnconfigure(0, weight=1)
        self._content_frame.grid_rowconfigure(0, weight=1)

        self._tab_frames: dict[str, ctk.CTkFrame] = {}
        self._tab_instances: dict[str, Any] = {}

        # Build dashboard (inline)
        dash = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        dash.grid(row=0, column=0, sticky="nsew")
        self._tab_frames["dashboard"] = dash
        self._build_dashboard(dash)

        # Build external tabs
        for key, _icon, _label, module, cls_name in _TAB_DEFS:
            if module is None:
                continue
            frame = ctk.CTkFrame(
                self._content_frame, fg_color="transparent",
            )
            frame.grid(row=0, column=0, sticky="nsew")
            self._tab_frames[key] = frame
            self._safe_load_tab(frame, module, cls_name, key)

        # Show dashboard first, hide others
        for key, frame in self._tab_frames.items():
            if key != "dashboard":
                frame.grid_remove()

    def _switch_tab(self, key: str) -> None:
        for k, frame in self._tab_frames.items():
            if k == key:
                frame.grid()
            else:
                frame.grid_remove()
        self._active_tab = key
        self._highlight_sidebar_tab(key)

    def _safe_load_tab(
        self,
        parent: Any,
        module_path: str,
        class_name: str,
        attr: str,
    ) -> None:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            inst = getattr(mod, class_name)(parent, self)
            self._tab_instances[attr] = inst
        except ImportError:
            ctk.CTkLabel(
                parent,
                text=f"{class_name.replace('Tab', '')} tab unavailable",
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(pady=20)

    # ── Dashboard ────────────────────────────────────────────────────

    def _build_dashboard(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=3)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # Chat panel
        chat_frame = ctk.CTkFrame(
            parent,
            corner_radius=self._t("radius", 4),
            fg_color=self._t("bg_secondary", "#0A0C10"),
        )
        chat_frame.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(
            chat_frame,
            wrap="word",
            font=("Consolas", 12),
            state="disabled",
            corner_radius=self._t("radius", 4),
            fg_color=self._t("bg_primary", "#050608"),
            text_color=self._t("text_primary", "#e2e2e8"),
            border_width=1,
            border_color=self._t("border_color", "#3b494b"),
        )
        self.chat_display.grid(
            row=0, column=0, sticky="nsew", padx=4, pady=4,
        )

        # Right panel
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=4)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Live view header
        ctk.CTkLabel(
            right,
            text="LIVE VIEW",
            font=("Segoe UI", 11, "bold"),
            text_color=self._t("accent", "#00F0FF"),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(4, 2))

        # Screenshot with monitor-frame border
        ss_frame = ctk.CTkFrame(
            right,
            corner_radius=self._t("radius", 4),
            border_width=2,
            border_color=self._t("border_color", "#3b494b"),
            fg_color=self._t("bg_primary", "#050608"),
        )
        ss_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        self.screenshot_label = ctk.CTkLabel(
            ss_frame,
            text="No screenshot",
            font=("Segoe UI", 10),
            text_color=self._t("text_tertiary", "#849495"),
        )
        self.screenshot_label.pack(fill="both", expand=True, padx=2, pady=2)

        # Step progress bar
        self._progress_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._progress_frame.grid(
            row=2, column=0, sticky="ew", padx=4, pady=2,
        )
        ctk.CTkLabel(
            self._progress_frame,
            text="Step",
            font=("Consolas", 10),
            text_color=self._t("text_tertiary", "#849495"),
        ).pack(side="left", padx=4)
        self.step_progress = ctk.CTkProgressBar(
            self._progress_frame,
            height=8,
            corner_radius=4,
            fg_color=self._t("bg_tertiary", "#111418"),
            progress_color=self._t("accent", "#00F0FF"),
        )
        self.step_progress.pack(
            side="left", fill="x", expand=True, padx=4,
        )
        self.step_progress.set(0)
        self.step_label = ctk.CTkLabel(
            self._progress_frame,
            text="0/100",
            font=("Consolas", 10),
            text_color=self._t("text_tertiary", "#849495"),
        )
        self.step_label.pack(side="right", padx=4)

        # Metrics panel
        self._metrics_frame = ctk.CTkFrame(
            right,
            corner_radius=self._t("radius", 4),
            fg_color=self._t("bg_secondary", "#0A0C10"),
        )
        self._metrics_frame.grid(
            row=3, column=0, sticky="ew", padx=4, pady=(4, 4),
        )
        self._build_metrics(self._metrics_frame)

    def _build_metrics(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="SYSTEM",
            font=("Segoe UI", 10, "bold"),
            text_color=self._t("accent", "#00F0FF"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self._metric_bars: dict[str, ctk.CTkProgressBar] = {}
        for label in ("CPU", "RAM", "Disk"):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)
            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=("Consolas", 10),
                text_color=self._t("text_tertiary", "#849495"),
                width=40,
            ).pack(side="left")
            bar = ctk.CTkProgressBar(
                row,
                height=6,
                corner_radius=3,
                fg_color=self._t("bg_tertiary", "#111418"),
                progress_color=self._t("accent", "#00F0FF"),
            )
            bar.pack(side="left", fill="x", expand=True, padx=4)
            bar.set(0)
            self._metric_bars[label] = bar

    def _update_metrics(self) -> None:
        """Refresh CPU/RAM/Disk bars (called every 2s)."""
        try:
            import psutil
            self._metric_bars["CPU"].set(
                psutil.cpu_percent() / 100,
            )
            mem = psutil.virtual_memory()
            self._metric_bars["RAM"].set(mem.percent / 100)
            disk = psutil.disk_usage("/")
            self._metric_bars["Disk"].set(disk.percent / 100)
        except (ImportError, OSError):
            pass
        try:
            self.root.after(2000, self._update_metrics)
        except RecursionError:
            pass

    # ── Status Bar ───────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.root,
            height=28,
            corner_radius=0,
            fg_color=self._t("bg_secondary", "#0A0C10"),
        )
        bar.grid(
            row=2, column=0, columnspan=2, sticky="ew",
        )
        bar.grid_propagate(False)
        bar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            bar,
            text=f"v{_VERSION}",
            font=("Consolas", 9),
            text_color=self._t("text_tertiary", "#849495"),
        ).grid(row=0, column=0, padx=(8, 4))

        self._uptime_label = ctk.CTkLabel(
            bar,
            text="00:00:00",
            font=("Consolas", 9),
            text_color=self._t("text_tertiary", "#849495"),
        )
        self._uptime_label.grid(row=0, column=1, padx=4)

        self._thread_label = ctk.CTkLabel(
            bar,
            text="",
            font=("Consolas", 9),
            text_color=self._t("text_tertiary", "#849495"),
        )
        self._thread_label.grid(row=0, column=3, padx=4)

        self._notes_label = ctk.CTkLabel(
            bar,
            text="Notes: 0",
            font=("Consolas", 9),
            text_color=self._t("text_tertiary", "#849495"),
        )
        self._notes_label.grid(row=0, column=4, padx=(4, 8))

    def _tick_status_bar(self) -> None:
        """Update uptime and thread count every second."""
        elapsed = int(time.monotonic() - self._start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._uptime_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        threads = threading.active_count()
        self._thread_label.configure(text=f"Threads: {threads}")
        try:
            self.root.after(1000, self._tick_status_bar)
        except RecursionError:
            pass

    # ── Input ────────────────────────────────────────────────────────

    def _build_input(self) -> None:
        input_frame = ctk.CTkFrame(
            self.root,
            corner_radius=0,
            fg_color=self._t("bg_secondary", "#0A0C10"),
        )
        input_frame.grid(
            row=3, column=0, columnspan=2, sticky="ew",
        )
        input_frame.grid_columnconfigure(0, weight=1)
        self._build_quick_chips(input_frame)
        self._build_prompt_textbox(input_frame)
        self._build_run_stop_buttons(input_frame)

    def _build_quick_chips(self, parent: Any) -> None:
        chips = ctk.CTkFrame(parent, fg_color="transparent")
        chips.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(4, 0))
        for preset in (self.cfg.get("quick_actions") or [])[:6]:
            short = preset if len(preset) <= 36 else preset[:33] + "\u2026"
            ctk.CTkButton(
                chips,
                text=short,
                height=24,
                font=("Segoe UI", 10),
                fg_color=self._t("bg_tertiary", "#111418"),
                hover_color=self._t("bg_hover", "#333539"),
                text_color=self._t("text_primary", "#e2e2e8"),
                corner_radius=self._t("radius", 4),
                command=lambda p=preset: self._set_prompt(p),
            ).pack(side="left", padx=2, pady=2)

    def _build_prompt_textbox(self, parent: Any) -> None:
        self.goal_entry = ctk.CTkTextbox(
            parent,
            height=72,
            font=("Segoe UI", 13),
            wrap="word",
            corner_radius=self._t("radius", 4),
            fg_color=self._t("bg_input", "#0A0C10"),
            text_color=self._t("text_primary", "#e2e2e8"),
            border_width=1,
            border_color=self._t("border_color", "#3b494b"),
        )
        self.goal_entry.grid(row=1, column=0, sticky="ew", padx=(8, 4), pady=4)
        self._placeholder_text = (
            "Describe what you want done\u2026   "
            "(Ctrl+Enter to run, Ctrl+K for commands)"
        )
        self.goal_entry.insert("1.0", self._placeholder_text)
        self.goal_entry.configure(
            text_color=self._t("text_tertiary", "#849495"),
        )
        self.goal_entry.bind("<FocusIn>", self._clear_placeholder)
        self.goal_entry.bind("<FocusOut>", self._restore_placeholder)
        self.goal_entry.bind("<Control-Return>", self._on_submit)
        self.goal_entry.bind("<Command-Return>", self._on_submit)
        # Neon glow on focus
        self.goal_entry.bind(
            "<FocusIn>",
            lambda e: (
                self.goal_entry.configure(
                    border_color=self._t(
                        "border_active", "#00F0FF",
                    ),
                ),
                self._clear_placeholder(e),
            ),
        )
        self.goal_entry.bind(
            "<FocusOut>",
            lambda e: (
                self.goal_entry.configure(
                    border_color=self._t(
                        "border_color", "#3b494b",
                    ),
                ),
                self._restore_placeholder(e),
            ),
        )

    def _build_run_stop_buttons(self, parent: Any) -> None:
        self._run_btn = ctk.CTkButton(
            parent,
            text="\u25b6 Run",
            width=80,
            height=72,
            font=("Segoe UI", 13, "bold"),
            fg_color=self._t("glow_success", "#95E400"),
            hover_color=self._t("tag_assistant", "#95E400"),
            text_color=self._t("bg_primary", "#050608"),
            corner_radius=self._t("radius", 4),
            command=self._on_submit,
        )
        self._run_btn.grid(row=1, column=1, padx=(0, 4), pady=4)

        self._stop_btn = ctk.CTkButton(
            parent,
            text="\u25a0 Stop",
            width=80,
            height=72,
            font=("Segoe UI", 13, "bold"),
            fg_color=self._t("glow_error", "#ff3b3b"),
            hover_color=self._t("tag_error", "#ff3b3b"),
            text_color="#ffffff",
            corner_radius=self._t("radius", 4),
            command=self._on_stop,
        )
        self._stop_btn.grid(row=1, column=2, padx=(0, 8), pady=4)

    # ── Compact mode ─────────────────────────────────────────────────

    def _toggle_compact_mode(self) -> None:
        self._compact_mode = not self._compact_mode
        if self._compact_mode:
            self._metrics_frame.grid_remove()
            if hasattr(self, "screenshot_label"):
                self.screenshot_label.master.grid_remove()
            self._progress_frame.grid_remove()
        else:
            self._metrics_frame.grid()
            if hasattr(self, "screenshot_label"):
                self.screenshot_label.master.grid()
            self._progress_frame.grid()

    # -- Placeholder helpers ──────────────────────────────────────────

    def _get_goal_text(self) -> str:
        txt = self.goal_entry.get("1.0", "end").strip()
        if txt == self._placeholder_text:
            return ""
        return txt

    def _set_prompt(self, text: str) -> None:
        self.goal_entry.delete("1.0", "end")
        self.goal_entry.insert("1.0", text)
        self.goal_entry.configure(
            text_color=self._t("text_primary", "#e2e2e8"),
        )
        self.goal_entry.focus_set()

    def _clear_placeholder(self, _event: Any = None) -> None:
        if self.goal_entry.get("1.0", "end").strip() == self._placeholder_text:
            self.goal_entry.delete("1.0", "end")
            self.goal_entry.configure(
                text_color=self._t("text_primary", "#e2e2e8"),
            )

    def _restore_placeholder(self, _event: Any = None) -> None:
        if not self.goal_entry.get("1.0", "end").strip():
            self.goal_entry.insert("1.0", self._placeholder_text)
            self.goal_entry.configure(
                text_color=self._t("text_tertiary", "#849495"),
            )

    # ── Chat display ─────────────────────────────────────────────────

    def _add_chat(self, text: str, tag: str = "system") -> None:
        with contextlib.suppress(RuntimeError):
            self.root.after(0, lambda: self._add_chat_main(text, tag))

    def _add_chat_main(self, text: str, tag: str) -> None:
        prefix_map = {
            "user": "You",
            "assistant": "Agent",
            "action": "Action",
            "error": "Error",
            "system": "System",
        }
        self.chat_display.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.chat_display.insert(
            "end",
            f"[{ts}] {prefix_map.get(tag, 'System')}: {text}\n\n",
        )
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    # ── Status pulse ─────────────────────────────────────────────────

    def _start_status_pulse(self) -> None:
        self._status_pulse_on = True
        try:
            self._pulse_step()
        except RecursionError:
            pass  # Test environments run after() synchronously

    def _stop_status_pulse(self) -> None:
        self._status_pulse_on = False

    def _pulse_step(self) -> None:
        if not self._status_pulse_on:
            return
        dim = self._t("bg_hover", "#333539")
        bright = self._t("status_running", "#95E400")
        current = self.status_label.cget("text_color")
        next_c = dim if current == bright else bright
        self.status_label.configure(text_color=next_c)
        try:
            self.root.after(800, self._pulse_step)
        except RecursionError:
            pass

    # ── Event handlers ───────────────────────────────────────────────

    def _on_submit(self, event: Any = None) -> str | None:
        goal = self._get_goal_text()
        if not goal:
            return "break" if event else None
        self.goal_entry.delete("1.0", "end")
        self._restore_placeholder()
        self._add_chat(goal, "user")
        self._record_recent_prompt(goal)
        self._run_goal(goal)
        return "break" if event else None

    def _on_stop(self) -> None:
        if self.engine and self.engine.running:
            self.engine.stop()
            self._add_chat("Agent stopped by user.", "system")

    def _run_goal(self, goal: str) -> None:
        if self.engine and self.engine.running:
            self._add_chat("Agent already running. Stop it first.", "error")
            return
        cfg = self.config.load()
        from core.engine import AgentEngine
        self.engine = AgentEngine(
            cfg,
            approval_callback=self._approve_action,
            pre_action_callback=self.overlay.show_action,
        )
        self.engine.on_step_callback = self._on_engine_step
        self.status_label.configure(
            text="\u25cf RUNNING",
            text_color=self._t("status_running", "#95E400"),
        )
        self._start_status_pulse()
        self.engine_thread = threading.Thread(
            target=lambda: self._agent_run_thread(goal),
            daemon=True,
        )
        self.engine_thread.start()

    def _on_engine_step(self, **kwargs: Any) -> None:
        step = kwargs.get("step", 0)
        action = kwargs.get("action", {})
        result = kwargs.get("result", {})
        action_name = action.get("action", "?")
        params = {k: v for k, v in action.items() if k != "action"}
        self._add_chat(f"Step {step}: {action_name}({params})", "action")
        if result:
            ok = result.get("ok", True)
            msg = result.get("msg", result.get("error", ""))
            if msg:
                self._add_chat(
                    f"  \u2192 {msg}", "assistant" if ok else "error",
                )
        self.root.after(0, self._update_step_labels, step)
        self.root.after(
            0,
            self._add_history_entry,
            step,
            action_name,
            {"ok": result.get("ok", True), "msg": result.get("msg", "")},
        )
        screenshot_b64 = kwargs.get("screenshot")
        if screenshot_b64:
            self.root.after(0, self._update_screenshot, screenshot_b64)

    def _agent_run_thread(self, goal: str) -> None:
        try:
            result = self.engine.run(goal)
            self._handle_agent_result(result)
        except (OSError, RuntimeError, ValueError) as e:
            self._handle_agent_error(e, goal)
        finally:
            if self.engine:
                self.engine.running = False
            self._stop_status_pulse()
            self.root.after(
                0,
                lambda: self.status_label.configure(
                    text="\u25cf IDLE",
                    text_color=self._t("status_idle", "#849495"),
                ),
            )

    def _handle_agent_result(self, result: dict) -> None:
        steps = result.get("steps", 0)
        notes = result.get("notes") or []
        summary = result.get("finish_summary") or ""
        if result.get("error"):
            for n in notes:
                self._add_chat(f"\u274c {n}", "error")
        elif steps == 0 and notes and not summary:
            for n in notes:
                self._add_chat(f"\u26a0 {n}", "error")
        else:
            self._add_chat(
                f"\u2705 Completed in {steps} step"
                f"{'s' if steps != 1 else ''}."
                + (f"\n{summary}" if summary else ""),
                "assistant",
            )
            if self.tray:
                try:
                    self.tray.notify(
                        "Sentinel Desktop",
                        f"Finished in {steps} steps. "
                        + (summary[:120] if summary else ""),
                    )
                except (OSError, RuntimeError) as exc:
                    logger.debug("Tray notification failed: %s", exc)

    def _handle_agent_error(self, exc: Exception, goal: str) -> None:
        import traceback
        tb = traceback.format_exc()
        self._add_chat(f"\u274c {type(exc).__name__}: {exc}", "error")
        log_path = (
            Path(os.environ.get("APPDATA", str(Path.home())))
            / "SentinelDesktop"
            / "last_error.log"
        )
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as f:
                f.write(f"Goal: {goal}\n\n{tb}\n")
            self._add_chat(
                f"   Traceback: {log_path}", "system",
            )
        except (OSError, RuntimeError) as exc2:
            logger.debug("Failed to write error log: %s", exc2)
        logger.exception("Agent run crashed")

    def _update_step_labels(self, step: int) -> None:
        if not self.engine:
            return
        max_s = self.engine.max_steps
        self.step_label.configure(text=f"{step}/{max_s}")
        self.step_progress.set(step / max(max_s, 1))
        self._notes_label.configure(
            text=f"Notes: {len(self.engine.notes)}",
        )

    def _update_screenshot(self, b64_data: str) -> None:
        try:
            import base64
            import io

            from PIL import Image
            img_data = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(img_data))
            max_w, max_h = 330, 250
            img.thumbnail((max_w, max_h))
            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img, size=img.size,
            )
            self._screenshot_ctk_img = ctk_img
            self.screenshot_label.configure(image=ctk_img, text="")
        except (ValueError, OSError) as e:
            logger.warning("Screenshot update failed: %s", e)

    # ── Approval prompt ──────────────────────────────────────────────

    def _approve_action(self, action: dict[str, Any]) -> bool:
        decision = {"approved": False}
        event = threading.Event()
        self.root.after(
            0, lambda: self._build_approval_dialog(action, decision, event),
        )
        event.wait(timeout=60)
        return decision["approved"]

    def _build_approval_dialog(
        self,
        action: dict[str, Any],
        decision: dict[str, Any],
        event: threading.Event,
    ) -> None:
        try:
            top = ctk.CTkToplevel(self.root)
            top.title("Approve action?")
            top.geometry("480x220")
            top.transient(self.root)
            top.grab_set()
            top.configure(
                fg_color=self._t("bg_primary", "#050608"),
            )
            action_name = action.get("action", "?")
            params = {k: v for k, v in action.items() if k != "action"}
            ctk.CTkLabel(
                top,
                text=f"The agent wants to run: {action_name}",
                font=("Segoe UI", 13, "bold"),
                text_color=self._t("accent", "#00F0FF"),
            ).pack(anchor="w", padx=16, pady=(16, 4))
            ctk.CTkLabel(
                top,
                text=json.dumps(params, indent=2)[:600],
                font=("Consolas", 10),
                justify="left",
                anchor="w",
                text_color=self._t("text_primary", "#e2e2e8"),
            ).pack(fill="both", expand=True, padx=16, pady=4)
            self._add_approval_buttons(top, decision, event)
        except (RuntimeError, tk.TclError) as exc:
            logger.warning("approval prompt failed: %s", exc)
            event.set()

    def _add_approval_buttons(
        self,
        top: Any,
        decision: dict[str, Any],
        event: threading.Event,
    ) -> None:
        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=12)

        def _approve() -> None:
            decision["approved"] = True
            event.set()
            top.destroy()

        def _reject() -> None:
            decision["approved"] = False
            event.set()
            top.destroy()

        ctk.CTkButton(
            btn_frame,
            text="\u2713 Approve",
            command=_approve,
            fg_color=self._t("glow_success", "#95E400"),
            hover_color=self._t("tag_assistant", "#95E400"),
            text_color=self._t("bg_primary", "#050608"),
            corner_radius=self._t("radius", 4),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btn_frame,
            text="\u2717 Reject",
            command=_reject,
            fg_color=self._t("glow_error", "#ff3b3b"),
            hover_color=self._t("tag_error", "#ff3b3b"),
            corner_radius=self._t("radius", 4),
        ).pack(side="right", padx=4)
        top.protocol("WM_DELETE_WINDOW", _reject)

    # ── History ──────────────────────────────────────────────────────

    def _add_history_entry(
        self, step: int, action_name: str, result: dict[str, Any],
    ) -> None:
        pass  # History tab manages its own data

    # ── Settings ─────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        SettingsWindow(
            self.root, self.config, self._on_settings_saved, app=self,
        )

    def _on_settings_saved(self) -> None:
        self.cfg = self.config.load()
        provider = self.cfg.get("provider", "none")
        model = self.cfg.get("model", "none")
        self.provider_label.configure(text=f"{provider} / {model}")

    # ── Command palette ──────────────────────────────────────────────

    def _setup_keyboard_shortcuts(self) -> None:
        self.root.bind("<Control-k>", self._show_command_palette)
        for i, (key, _, _, _, _) in enumerate(_TAB_DEFS):
            self.root.bind(
                f"<Control-{i + 1}>",
                lambda e, k=key: self._switch_tab(k),
            )
        self.root.bind("<Control-f>", self._show_chat_search)

    def _show_command_palette(self, _event: Any = None) -> None:
        palette = ctk.CTkToplevel(self.root)
        palette.title("Command Palette")
        palette.geometry("500x400")
        palette.transient(self.root)
        palette.grab_set()
        palette.configure(fg_color=self._t("bg_primary", "#050608"))

        entry = ctk.CTkEntry(
            palette,
            placeholder_text="Search commands\u2026",
            height=40,
            font=("Segoe UI", 13),
            fg_color=self._t("bg_input", "#0A0C10"),
            text_color=self._t("text_primary", "#e2e2e8"),
            border_color=self._t("border_active", "#00F0FF"),
        )
        entry.pack(fill="x", padx=12, pady=12)

        commands = [
            (
                "New Chat",
                lambda: (
                    self.chat_display.configure(state="normal"),
                    self.chat_display.delete("1.0", "end"),
                    self.chat_display.configure(state="disabled"),
                    palette.destroy(),
                ),
            ),
            (
                "Settings",
                lambda: (palette.destroy(), self._open_settings()),
            ),
            (
                "Screenshot",
                lambda: (self._take_screenshot(), palette.destroy()),
            ),
            (
                "Export Log",
                lambda: (self._export_log(), palette.destroy()),
            ),
            (
                "Export Chat (Markdown)",
                lambda: (self._export_chat_md(), palette.destroy()),
            ),
        ]

        frame = ctk.CTkScrollableFrame(
            palette, fg_color="transparent",
        )
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for name, cmd in commands:
            ctk.CTkButton(
                frame,
                text=name,
                anchor="w",
                command=cmd,
                fg_color=self._t(
                    "bg_primary", "#050608"
                ),
                hover_color=self._t("bg_hover", "#333539"),
                text_color=self._t("text_primary", "#e2e2e8"),
            ).pack(fill="x", pady=2)

        entry.focus()

    # ── Chat Search ──────────────────────────────────────────────────

    def _show_chat_search(self, _event: Any = None) -> None:
        if not hasattr(self, "_search_frame"):
            self._search_frame = ctk.CTkFrame(
                self.root,
                height=32,
                fg_color=self._t("bg_secondary", "#0A0C10"),
            )
            self._search_var = ctk.StringVar()
            self._search_entry = ctk.CTkEntry(
                self._search_frame,
                textvariable=self._search_var,
                placeholder_text="Search chat\u2026 (Escape to close)",
                height=28,
                font=("Segoe UI", 11),
                fg_color=self._t("bg_input", "#0A0C10"),
                text_color=self._t("text_primary", "#e2e2e8"),
            )
            self._search_entry.pack(
                side="left", fill="x", expand=True, padx=4,
            )
            self._search_entry.bind("<Escape>", lambda e: self._search_frame.grid_remove())
        self._search_frame.grid(
            row=3, column=0, columnspan=2, sticky="ew",
        )
        self._search_entry.focus()

    # ── Utilities ────────────────────────────────────────────────────

    def _take_screenshot(self) -> None:
        from core.screenshot import capture_to_base64
        try:
            b64 = capture_to_base64()
        except OSError as exc:
            self._add_chat(f"Screenshot failed: {exc}", "error")
            return
        self._update_screenshot(b64)
        self._add_chat("Screenshot captured.", "system")

    def _export_log(self) -> None:
        if not self.engine:
            self._add_chat("No log to export.", "system")
            return
        path = Path(
            f"sentinel_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(self.engine.forensic_log, f, indent=2)
            self._add_chat(f"Log exported to {path}", "system")
        except OSError as exc:
            self._add_chat(f"Failed to export log: {exc}", "error")

    def _export_chat_md(self) -> None:
        text = self.chat_display.get("1.0", "end").strip()
        if not text:
            self._add_chat("Chat is empty.", "system")
            return
        path = Path(
            f"sentinel_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        )
        try:
            header = (
                f"# Sentinel Desktop Chat Export\n"
                f"**Date:** {datetime.now().isoformat()}\n"
                f"**Version:** v{_VERSION}\n\n---\n\n"
            )
            with path.open("w", encoding="utf-8") as f:
                f.write(header + text)
            self._add_chat(f"Chat exported to {path}", "system")
        except OSError as exc:
            self._add_chat(f"Export failed: {exc}", "error")

    def _record_recent_prompt(self, goal: str) -> None:
        if not goal:
            return
        recent = list(self.cfg.get("recent_prompts") or [])
        recent = [r for r in recent if r != goal]
        recent.insert(0, goal)
        recent = recent[:10]
        self.cfg["recent_prompts"] = recent
        try:
            self.config.save(self.cfg)
        except (OSError, TypeError) as exc:
            logger.debug("Failed to save recent prompts: %s", exc)

    # ── Notification Toast ───────────────────────────────────────────

    def _show_toast(self, message: str, duration_ms: int = 3000) -> None:
        """Show a brief notification toast in the top-right corner."""
        try:
            toast = ctk.CTkFrame(
                self.root,
                corner_radius=self._t("radius", 4),
                fg_color=self._t("bg_elevated", "#333539"),
                border_width=1,
                border_color=self._t("accent", "#00F0FF"),
            )
            ctk.CTkLabel(
                toast,
                text=message,
                font=("Segoe UI", 11),
                text_color=self._t("text_primary", "#e2e2e8"),
                padx=12,
                pady=6,
            ).pack()
            toast.place(relx=0.85, rely=0.05, anchor="ne")
            self.root.after(
                duration_ms,
                lambda: toast.destroy(),
            )
        except (RuntimeError, tk.TclError):
            pass

    # ── Resume Checkpoint ────────────────────────────────────────────

    def _check_resume_checkpoint(self) -> None:
        try:
            from core.checkpoint import CheckpointManager
            cp = CheckpointManager()
            latest = cp.load_latest()
            if not latest:
                return
            goal_preview = latest.get("goal_preview", latest.get("goal", ""))[:120]
            step_num = latest.get("step_num", 0)
            status = latest.get("status", "?")
            self._add_chat(
                f"\U0001f504 Resume previous run? ({status}, stopped at step {step_num})\n"
                f"   Goal: {goal_preview}...\n"
                f"   Type 'resume' or press Ctrl+Shift+R to continue.",
                "system",
            )
        except (OSError, RuntimeError, ValueError) as exc:
            logger.debug("Checkpoint check failed: %s", exc)

    # ── Tray ─────────────────────────────────────────────────────────

    def _start_tray_if_enabled(self) -> None:
        if not self.cfg.get("minimize_to_tray") and not self.cfg.get(
            "start_in_tray",
        ):
            return
        if not _tray_available():
            self._add_chat(
                "Tray mode requested but 'pystray' isn't installed. "
                "Install with: pip install pystray pillow",
                "system",
            )
            return
        self.tray = SentinelTray(
            on_show=self._show_from_tray,
            on_hide=self._hide_to_tray,
            on_stop_agent=lambda: (
                self.engine.stop()
                if self.engine and self.engine.running
                else None
            ),
            on_quit=lambda: self.root.after(0, self.root.destroy),
        )
        if self.tray.run() and self.cfg.get("start_in_tray"):
            self.root.after(100, self._hide_to_tray)

    def _hide_to_tray(self) -> None:
        if not self.tray:
            return
        try:
            self.root.withdraw()
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Failed to withdraw window: %s", exc)

    def _show_from_tray(self) -> None:
        try:
            self.root.after(0, self.root.deiconify)
            self.root.after(0, self.root.lift)
            self.root.after(
                0, lambda: self.root.attributes("-topmost", True),
            )
            self.root.after(
                200, lambda: self.root.attributes("-topmost", False),
            )
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Failed to show window: %s", exc)

    def _on_close_window(self) -> None:
        if self.cfg.get("minimize_to_tray") and self.tray:
            self._hide_to_tray()
        else:
            self.root.destroy()

    # ── Run ──────────────────────────────────────────────────────────

    def run(self) -> None:
        self._add_chat(
            f"Sentinel Desktop v{_VERSION} ready. "
            f"Describe a goal and press Enter.\n"
            f"Ctrl+K for command palette. \u2699 for settings.",
            "system",
        )
        self._check_resume_checkpoint()
        cfg = self.config.load()
        provider = cfg.get("provider", "")
        if (
            not cfg.get("api_key")
            and provider not in ("ollama", "lmstudio", "custom")
        ) or not cfg.get("model"):
            self._add_chat(
                "\u26a0 No LLM configured yet. Click \u2699 to choose a "
                "provider, paste your API key, and pick a model.",
                "error",
            )
        self._start_tray_if_enabled()
        self._tick_status_bar()
        self._update_metrics()
        self.root.mainloop()


class SettingsWindow:
    """Settings modal for provider/API key configuration."""

    def __init__(
        self,
        parent: ctk.CTk,
        config: Config,
        on_save: Any = None,
        app: Any = None,
    ) -> None:
        self.config = config
        self.cfg = config.load()
        self.on_save = on_save
        self.app = app
        self.win = ctk.CTkToplevel(parent)
        self.win.title("Settings")
        self.win.geometry("620x640")
        self.win.transient(parent)
        self.win.grab_set()
        self._build()

    def _build(self) -> None:
        self._build_provider_section()
        self._build_credentials_section()
        self._build_theme_section()
        self._build_advanced()

    def _build_provider_section(self) -> None:
        from core.provider_registry import PROVIDERS, get_provider_names
        ctk.CTkLabel(
            self.win, text="Provider", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 4))
        self.provider_var = ctk.StringVar(
            value=self.cfg.get("provider", "openai"),
        )
        self.provider_menu = ctk.CTkOptionMenu(
            self.win,
            variable=self.provider_var,
            values=get_provider_names(),
            command=self._on_provider_change,
        )
        self.provider_menu.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(
            self.win, text="Base URL", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        url_frame = ctk.CTkFrame(self.win)
        url_frame.pack(fill="x", padx=20, pady=4)
        url_frame.grid_columnconfigure(0, weight=1)
        catalog_url = PROVIDERS.get(
            self.provider_var.get(), {},
        ).get("base_url", "")
        self.base_url_var = ctk.StringVar(
            value=self.cfg.get("custom_base_url") or catalog_url,
        )
        self.base_url_entry = ctk.CTkEntry(
            url_frame,
            textvariable=self.base_url_var,
            height=36,
            placeholder_text="Override the provider's base URL (optional)",
        )
        self.base_url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            url_frame,
            text="\u21ba Reset",
            width=90,
            height=36,
            command=self._reset_base_url,
        ).grid(row=0, column=1)
        ctk.CTkLabel(
            self.win,
            text=(
                "Leave as the catalog default for most providers. For "
                "Z.ai's Max Coding Plan use: "
                "https://api.z.ai/api/coding/paas/v4"
            ),
            font=("Segoe UI", 10),
            text_color="#b9cacb",
            wraplength=540,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(2, 4))

    def _build_credentials_section(self) -> None:
        ctk.CTkLabel(
            self.win, text="API Key", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        self.api_key_entry = ctk.CTkEntry(
            self.win,
            show="\u2022",
            height=36,
            placeholder_text="Paste your API key\u2026",
        )
        self.api_key_entry.pack(fill="x", padx=20, pady=4)
        if self.cfg.get("api_key"):
            self.api_key_entry.insert(0, self.cfg["api_key"])
        ctk.CTkLabel(
            self.win, text="Model", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        model_frame = ctk.CTkFrame(self.win)
        model_frame.pack(fill="x", padx=20, pady=4)
        model_frame.grid_columnconfigure(0, weight=1)
        self.model_var = ctk.StringVar(
            value=self.cfg.get("model", ""),
        )
        self.model_entry = ctk.CTkEntry(
            model_frame,
            textvariable=self.model_var,
            height=36,
            placeholder_text="Model name or auto-detect\u2026",
        )
        self.model_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            model_frame,
            text="\U0001f50d Detect",
            width=90,
            height=36,
            command=self._detect_models,
        ).grid(row=0, column=1)

    def _build_theme_section(self) -> None:
        ctk.CTkLabel(
            self.win, text="Theme", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        self.theme_var = ctk.StringVar(
            value=self.cfg.get("theme", "sentinel"),
        )
        ctk.CTkOptionMenu(
            self.win,
            variable=self.theme_var,
            values=list(THEMES.keys()),
            command=self._on_theme_change,
        ).pack(fill="x", padx=20, pady=4)

    def _on_theme_change(self, choice: str) -> None:
        if self.app:
            self.app.current_theme = get_theme(choice)
            apply_theme(choice)
            self.app._t = lambda key, fb="": (
                self.app.current_theme.get(key, fb)
            )
            self.app.status_label.configure(
                text_color=self.app._t("status_idle", "#849495"),
            )
            self.app.provider_label.configure(
                text_color=self.app._t("text_tertiary", "#849495"),
            )

    def _build_advanced(self) -> None:
        self._build_monitor_section()
        self._build_run_mode_section()
        self._build_step_budget_section()
        ctk.CTkButton(
            self.win,
            text="\U0001f4be Save Settings",
            height=40,
            command=self._save,
        ).pack(fill="x", padx=20, pady=(20, 20))

    def _build_monitor_section(self) -> None:
        from core.screenshot import list_monitors
        ctk.CTkLabel(
            self.win, text="Monitor", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        monitor_choices: list[str] = [
            "auto \u2014 monitor with focused window (recommended)",
        ]
        try:
            mons = list_monitors()
            if any(m.get("is_virtual") for m in mons):
                monitor_choices.append(
                    "0 \u2014 All monitors (virtual desktop)",
                )
            for m in mons:
                if not m.get("is_virtual"):
                    label = (
                        f"{m['index']} \u2014 {m['width']}x{m['height']}"
                        f"{' (primary)' if m.get('is_primary') else ''}"
                    )
                    monitor_choices.append(label)
        except (OSError, RuntimeError) as exc:
            logger.debug("Monitor enumeration failed: %s", exc)
            monitor_choices.extend([
                "0 \u2014 All monitors",
                "1 \u2014 Primary",
            ])
        current_monitor = self.cfg.get("monitor")
        default_label = next(
            (
                s
                for s in monitor_choices
                if str(current_monitor) == s.split(" ", 1)[0]
            ),
            monitor_choices[0],
        )
        self.monitor_var = ctk.StringVar(value=default_label)
        ctk.CTkOptionMenu(
            self.win,
            variable=self.monitor_var,
            values=monitor_choices,
        ).pack(fill="x", padx=20, pady=4)

    def _build_run_mode_section(self) -> None:
        ctk.CTkLabel(
            self.win, text="Run mode", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        toggles = [
            (
                "autonomous_var",
                "autonomous",
                "Fully autonomous (no approval prompts)",
            ),
            (
                "dry_run_var",
                "dry_run",
                "Dry-run (log actions, don't execute)",
            ),
            (
                "stealth_var",
                "stealth_input",
                "Stealth input (don't move my mouse/keyboard)",
            ),
            (
                "tray_var",
                "minimize_to_tray",
                "Minimize to system tray",
            ),
            (
                "start_tray_var",
                "start_in_tray",
                "Start hidden in tray",
            ),
        ]
        for attr, cfg_key, label in toggles:
            var = ctk.BooleanVar(value=bool(self.cfg.get(cfg_key)))
            setattr(self, attr, var)
            ctk.CTkSwitch(
                self.win,
                text=label,
                variable=var,
                onvalue=True,
                offvalue=False,
            ).pack(anchor="w", padx=20, pady=4)

    def _build_step_budget_section(self) -> None:
        ctk.CTkLabel(
            self.win, text="Step Budget", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))
        self.steps_entry = ctk.CTkEntry(
            self.win, height=36, placeholder_text="100",
        )
        self.steps_entry.pack(fill="x", padx=20, pady=4)
        self.steps_entry.insert(0, str(self.cfg.get("max_steps", 100)))

    def _on_provider_change(self, choice: str) -> None:
        from core.provider_registry import PROVIDERS
        catalog_url = PROVIDERS.get(choice, {}).get("base_url", "")
        current = self.base_url_var.get().strip()
        if not current or current in {
            p.get("base_url", "") for p in PROVIDERS.values()
        }:
            self.base_url_var.set(catalog_url)

    def _reset_base_url(self) -> None:
        from core.provider_registry import PROVIDERS
        provider = self.provider_var.get()
        self.base_url_var.set(
            PROVIDERS.get(provider, {}).get("base_url", ""),
        )

    def _detect_models(self) -> None:
        from core.provider_registry import fetch_models
        provider = self.provider_var.get()
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            self.model_var.set("Enter API key first")
            return
        models = fetch_models(provider, api_key)
        if models:
            self.model_var.set(
                models[0] if len(models) == 1 else "",
            )
            self.model_entry.configure(
                placeholder_text=(
                    f"Found {len(models)} models: "
                    f"{', '.join(models[:5])}"
                ),
            )
        else:
            self.model_var.set("")
            self.model_entry.configure(
                placeholder_text="No models found. Enter manually.",
            )

    def _save(self) -> None:
        from core.provider_registry import PROVIDERS
        provider = self.provider_var.get()
        self.cfg["provider"] = provider
        self.cfg["api_key"] = self.api_key_entry.get().strip()
        self.cfg["model"] = self.model_var.get().strip()
        self.cfg["theme"] = self.theme_var.get()
        url = self.base_url_var.get().strip().rstrip("/")
        catalog_url = PROVIDERS.get(provider, {}).get(
            "base_url", "",
        ).rstrip("/")
        self.cfg["custom_base_url"] = (
            url if url and url != catalog_url else ""
        )
        try:
            self.cfg["max_steps"] = int(self.steps_entry.get() or "100")
        except ValueError:
            self.cfg["max_steps"] = 100
        mon_str = (self.monitor_var.get() or "auto").split(" ", 1)[0]
        if mon_str == "auto":
            self.cfg["monitor"] = "auto"
        else:
            try:
                self.cfg["monitor"] = int(mon_str)
            except (ValueError, AttributeError):
                self.cfg["monitor"] = "auto"
        self.cfg["autonomous"] = bool(self.autonomous_var.get())
        self.cfg["dry_run"] = bool(self.dry_run_var.get())
        self.cfg["stealth_input"] = bool(self.stealth_var.get())
        self.cfg["minimize_to_tray"] = bool(self.tray_var.get())
        self.cfg["start_in_tray"] = bool(self.start_tray_var.get())
        try:
            self.config.save(self.cfg)
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror("Save Error", f"Cannot save settings:\n{exc}")
            return
        if self.on_save:
            self.on_save()
        self.win.destroy()
