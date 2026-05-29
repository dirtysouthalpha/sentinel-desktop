"""
Sentinel Desktop v2 — Main GUI Application.

Dark-themed customtkinter interface with chat, live screenshot, and settings.
"""

from __future__ import annotations

import json
import logging
import os
import threading
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


class SentinelApp:
    """Main application window."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cfg = config.load()

        # Theme
        theme_name = self.cfg.get("theme", "sentinel")
        self.current_theme = get_theme(theme_name)
        apply_theme(theme_name)

        # Theme color helper
        self._t = lambda key, fb="": self.current_theme.get(key, fb)

        # Window
        self.root = ctk.CTk()
        self.root.title("SENTINEL DESKTOP v3.0")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # State
        self.engine: Any = None
        self.engine_thread: threading.Thread | None = None
        self._approval_event = threading.Event()

        # Widget refs for live theme switching
        self._stop_btn: Any = None
        self._run_btn: Any = None
        self._chip_btns: list[Any] = []
        self._autonomous_chip = None
        self._stealth_chip = None

        # Visible-action overlay (transparent click ring over each action).
        self.overlay = ActionOverlay(self.root)

        # Optional system-tray icon — populated lazily in run() if available.
        self.tray: SentinelTray = None  # type: ignore[assignment]

        # Intercept the window close button so it minimizes-to-tray when
        # the user has opted in.
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # Build UI
        self._build_header()
        self._build_tabs()
        self._build_recorder_panel()
        self._build_input()

        # Command palette
        self.root.bind("<Control-k>", self._show_command_palette)

    # ── Header ──────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.root, height=50)
        header.pack(fill="x", padx=8, pady=(8, 4))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="⬡ Sentinel Desktop", font=("Segoe UI", 16, "bold")).pack(
            side="left", padx=12
        )

        self.status_label = ctk.CTkLabel(
            header,
            text="● IDLE",
            font=("Segoe UI", 12),
            text_color=self._t("status_idle", "#849495"),
        )
        self.status_label.pack(side="left", padx=20)

        # Surface dry-run mode prominently so the user knows actions are
        # not actually firing.
        if self.cfg.get("dry_run"):
            ctk.CTkLabel(
                header,
                text="DRY-RUN",
                font=("Segoe UI", 11, "bold"),
                text_color="#000000",
                fg_color=self._t("tag_action", "#FBBC00"),
                corner_radius=3,
                padx=8,
            ).pack(side="left", padx=10)
        # Show AUTONOMOUS chip in red so users always know when approvals
        # are off and the agent is acting without confirmation.
        if self.cfg.get("autonomous"):
            ctk.CTkLabel(
                header,
                text="AUTONOMOUS",
                font=("Segoe UI", 11, "bold"),
                text_color="#ffffff",
                fg_color=self._t("status_error", "#ff3b3b"),
                corner_radius=3,
                padx=8,
            ).pack(side="left", padx=10)
        if self.cfg.get("stealth_input"):
            ctk.CTkLabel(
                header,
                text="STEALTH",
                font=("Segoe UI", 11, "bold"),
                text_color="#ffffff",
                fg_color=self._t("accent", "#00F0FF"),
                corner_radius=3,
                padx=8,
            ).pack(side="left", padx=10)

        # Provider / model
        provider = self.cfg.get("provider", "none")
        model = self.cfg.get("model", "none")
        self.provider_label = ctk.CTkLabel(
            header,
            text=f"{provider} / {model}",
            font=("Segoe UI", 10),
            text_color=self._t("text_secondary", "#849495"),
        )
        self.provider_label.pack(side="right", padx=12)

        # Settings button
        ctk.CTkButton(
            header,
            text="⚙",
            width=32,
            height=32,
            command=self._open_settings,
        ).pack(side="right", padx=4)

    # ── Tabbed Layout ──────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        """Build tabbed interface: Dashboard | Scripts | Workflows | History."""
        self.tabview = ctk.CTkTabview(
            self.root,
            fg_color=self._t("bg_secondary", "#0A0C10"),
            segmented_button_fg_color=self._t("bg_input", "#111418"),
            segmented_button_selected_color=self._t("accent", "#00F0FF"),
            segmented_button_unselected_color=self._t("bg_input", "#111418"),
            corner_radius=4,
        )
        self.tabview.pack(fill="both", expand=True, padx=8, pady=4)

        # Create tabs
        tab_dashboard = self.tabview.add("🖥️ Dashboard")
        tab_scripts = self.tabview.add("📜 Scripts")
        tab_workflows = self.tabview.add("🔀 Workflows")
        tab_history = self.tabview.add("📁 History")
        tab_settings = self.tabview.add("⚙️ Settings")

        # Dashboard tab = existing main area content
        self._build_main_area_into(tab_dashboard)

        # Scripts tab
        try:
            from gui.tabs.scripts_tab import ScriptsTab

            self.scripts_tab = ScriptsTab(tab_scripts, self)
        except ImportError:
            ctk.CTkLabel(
                tab_scripts,
                text="Scripts tab unavailable",
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(pady=20)

        # Workflows tab
        try:
            from gui.tabs.workflows_tab import WorkflowsTab

            self.workflows_tab = WorkflowsTab(tab_workflows, self)
        except ImportError:
            ctk.CTkLabel(
                tab_workflows,
                text="Workflows tab unavailable",
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(pady=20)

        # History tab
        try:
            from gui.tabs.history_tab import HistoryTab

            self.history_tab = HistoryTab(tab_history, self)
        except ImportError:
            ctk.CTkLabel(
                tab_history,
                text="History tab unavailable",
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(pady=20)

        # Settings tab
        try:
            from gui.tabs.settings_tab import SettingsTab

            self.settings_tab = SettingsTab(tab_settings, self)
        except ImportError:
            ctk.CTkLabel(
                tab_settings,
                text="Settings tab unavailable",
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(pady=20)

    def _build_main_area_into(self, parent: ctk.CTkFrame) -> None:
        """Build the original main area content into a given parent frame."""
        main = ctk.CTkFrame(parent, fg_color="transparent")
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # Chat panel
        chat_frame = ctk.CTkFrame(main)
        chat_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(
            chat_frame,
            wrap="word",
            font=("Consolas", 12),
            state="disabled",
            corner_radius=4,
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Right panel — screenshot + info
        right = ctk.CTkFrame(main, width=350)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right, text="Live View", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=4
        )

        self.screenshot_label = ctk.CTkLabel(right, text="No screenshot")
        self.screenshot_label.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        # Info
        info_frame = ctk.CTkFrame(right)
        info_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=4)

        self.step_label = ctk.CTkLabel(info_frame, text="Step: 0/100", font=("Consolas", 10))
        self.step_label.pack(anchor="w", padx=8, pady=2)

        self.notes_label = ctk.CTkLabel(info_frame, text="Notes: 0", font=("Consolas", 10))
        self.notes_label.pack(anchor="w", padx=8, pady=2)

    # ── Recorder Panel ────────────────────────────────────────────────────

    def _build_recorder_panel(self) -> None:
        """Record/playback toolbar above the input area."""
        try:
            from gui.recorder_panel import RecorderPanel

            self.recorder_panel = RecorderPanel(parent=self.root, app=self)
            # Panel packs itself above the input area
        except ImportError:
            logger.warning("Recorder panel not available — recorder_panel.py missing")

    # ── Input ───────────────────────────────────────────────────────────

    def _build_input(self) -> None:
        """Build multi-line input area with quick-action chips, recent-prompts dropdown, and run/stop buttons."""
        input_frame = ctk.CTkFrame(self.root)
        input_frame.pack(fill="x", padx=8, pady=(4, 8))
        input_frame.grid_columnconfigure(0, weight=1)
        self._build_quick_chips(input_frame)
        self._build_recent_dropdown(input_frame)
        self._build_prompt_textbox(input_frame)
        self._build_run_stop_buttons(input_frame)

    def _build_quick_chips(self, parent: Any) -> None:
        """Build preset quick-action chip buttons."""
        chips = ctk.CTkFrame(parent, fg_color="transparent")
        chips.grid(row=0, column=0, columnspan=3, sticky="ew", padx=4, pady=(4, 0))
        for preset in (self.cfg.get("quick_actions") or [])[:6]:
            short = preset if len(preset) <= 36 else preset[:33] + "…"
            ctk.CTkButton(
                chips, text=short, height=24, font=("Segoe UI", 10),
                fg_color=self._t("bg_input", "#111418"),
                hover_color=self._t("bg_hover", "#333539"),
                text_color=self._t("text_primary", "#e2e2e8"),
                corner_radius=6, command=lambda p=preset: self._set_prompt(p),
            ).pack(side="left", padx=2, pady=2)

    def _build_recent_dropdown(self, parent: Any) -> None:
        """Build the recent-prompts dropdown if there are any saved prompts."""
        recent = self.cfg.get("recent_prompts") or []
        if not recent:
            return
        recent_short = [(r if len(r) <= 50 else r[:47] + "…") for r in recent[:10]]
        self.recent_var = ctk.StringVar(value="↻ Recent")
        ctk.CTkOptionMenu(
            parent, variable=self.recent_var, values=recent_short,
            width=140, height=28, font=("Segoe UI", 10), command=self._on_recent_pick,
        ).grid(row=1, column=0, sticky="e", padx=(0, 4), pady=(4, 0))

    def _build_prompt_textbox(self, parent: Any) -> None:
        """Build the multi-line prompt textbox with placeholder and keyboard bindings."""
        self.goal_entry = ctk.CTkTextbox(
            parent, height=80, font=("Segoe UI", 13), wrap="word", corner_radius=4,
        )
        self.goal_entry.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        self._placeholder_text = (
            "Describe what you want done…   (Ctrl+Enter to run, Enter for newline)"
        )
        self.goal_entry.insert("1.0", self._placeholder_text)
        self.goal_entry.configure(text_color=self._t("text_secondary", "#849495"))
        self.goal_entry.bind("<FocusIn>", self._clear_placeholder)
        self.goal_entry.bind("<FocusOut>", self._restore_placeholder)
        self.goal_entry.bind("<Control-Return>", self._on_submit)
        self.goal_entry.bind("<Command-Return>", self._on_submit)

    def _build_run_stop_buttons(self, parent: Any) -> None:
        """Build the ▶ Run and ■ Stop buttons."""
        ctk.CTkButton(
            parent, text="▶ Run", width=80, height=80,
            font=("Segoe UI", 13, "bold"), command=self._on_submit,
        ).grid(row=2, column=1, padx=(0, 4), pady=(4, 8))
        ctk.CTkButton(
            parent, text="■ Stop", width=80, height=80,
            font=("Segoe UI", 13, "bold"), command=self._on_stop,
            fg_color=self._t("status_error", "#ff3b3b"),
            hover_color=self._t("tag_error", "#ff3b3b"),
        ).grid(row=2, column=2, padx=(0, 8), pady=(4, 8))

    # -- Placeholder + recent-prompt helpers ------------------------------

    def _get_goal_text(self) -> str:
        txt = self.goal_entry.get("1.0", "end").strip()
        if txt == self._placeholder_text:
            return ""
        return txt

    def _set_prompt(self, text: str) -> None:
        self.goal_entry.delete("1.0", "end")
        self.goal_entry.insert("1.0", text)
        self.goal_entry.configure(text_color=self._t("text_primary", "#e2e2e8"))
        self.goal_entry.focus_set()

    def _clear_placeholder(self, _event: Any = None) -> None:
        if self.goal_entry.get("1.0", "end").strip() == self._placeholder_text:
            self.goal_entry.delete("1.0", "end")
            self.goal_entry.configure(text_color=self._t("text_primary", "#e2e2e8"))

    def _restore_placeholder(self, _event: Any = None) -> None:
        if not self.goal_entry.get("1.0", "end").strip():
            self.goal_entry.insert("1.0", self._placeholder_text)
            self.goal_entry.configure(text_color=self._t("text_secondary", "#849495"))

    def _on_recent_pick(self, choice: str) -> None:
        # The dropdown shows truncated text — find the full prompt by prefix.
        recent = self.cfg.get("recent_prompts") or []
        target = next(
            (
                r
                for r in recent
                if r.startswith(choice.rstrip("…"))
                or (choice.endswith("…") and r.startswith(choice[:-1]))
            ),
            choice,
        )
        self._set_prompt(target)
        self.recent_var.set("↻ Recent")  # reset label

    def _record_recent_prompt(self, goal: str) -> None:
        if not goal:
            return
        recent = list(self.cfg.get("recent_prompts") or [])
        # Move existing entry to front instead of duplicating.
        recent = [r for r in recent if r != goal]
        recent.insert(0, goal)
        recent = recent[:10]
        self.cfg["recent_prompts"] = recent
        try:
            self.config.save(self.cfg)
        except (OSError, TypeError) as exc:
            logger.debug("Failed to save recent prompts: %s", exc)

    # ── Chat display ────────────────────────────────────────────────────

    def _add_chat(self, text: str, tag: str = "system") -> None:
        """Append a line to the chat log. Safe to call from any thread."""
        # Marshal Tk widget updates to the main thread.
        try:
            self.root.after(0, lambda: self._add_chat_main(text, tag))
        except RuntimeError:
            # Root may already be destroyed during shutdown — drop silently.
            pass

    def _add_chat_main(self, text: str, tag: str) -> None:
        self.chat_display.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        prefix_map = {
            "user": "You",
            "assistant": "Agent",
            "action": "Action",
            "error": "Error",
            "system": "System",
        }
        self.chat_display.insert(
            "end",
            f"[{ts}] {prefix_map.get(tag, 'System')}: {text}\n\n",
        )
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    # ── Event handlers ──────────────────────────────────────────────────

    def _on_submit(self, event: Any = None) -> str | None:
        goal = self._get_goal_text()
        if not goal:
            return "break" if event else None
        self.goal_entry.delete("1.0", "end")
        self._restore_placeholder()
        self._add_chat(goal, "user")
        self._record_recent_prompt(goal)
        self._run_goal(goal)
        # Returning 'break' prevents Tk from also inserting a newline on
        # Ctrl-Enter (the default binding would otherwise add one).
        return "break" if event else None

    def _on_stop(self) -> None:
        if self.engine and self.engine.running:
            self.engine.stop()
            self._add_chat("Agent stopped by user.", "system")

    def _run_goal(self, goal: str) -> None:
        """Start agent in background thread."""
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
            text="● RUNNING", text_color=self._t("status_running", "#95E400")
        )
        self.engine_thread = threading.Thread(
            target=lambda: self._agent_run_thread(goal), daemon=True
        )
        self.engine_thread.start()

    def _on_engine_step(self, **kwargs: Any) -> None:
        """Callback from engine on each step. Runs on worker thread."""
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
                self._add_chat(f"  → {msg}", "assistant" if ok else "error")
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
        """Thread target: run the agent and update the UI when done."""
        try:
            result = self.engine.run(goal)
            steps = result.get("steps", 0)
            notes = result.get("notes") or []
            summary = result.get("finish_summary") or ""

            if result.get("error"):
                for n in notes:
                    self._add_chat(f"❌ {n}", "error")
            elif steps == 0 and notes and not summary:
                for n in notes:
                    self._add_chat(f"⚠ {n}", "error")
            else:
                self._add_chat(
                    f"✅ Completed in {steps} step{'' if steps == 1 else 's'}."
                    + (f"\n{summary}" if summary else ""),
                    "assistant",
                )
                if self.tray:
                    try:
                        self.tray.notify(
                            "Sentinel Desktop",
                            f"Finished in {steps} steps. " + (summary[:120] if summary else ""),
                        )
                    except (OSError, RuntimeError) as exc:
                        logger.debug("Tray notification failed: %s", exc)
        except (OSError, RuntimeError, ValueError) as e:
            import traceback

            tb = traceback.format_exc()
            self._add_chat(f"❌ {type(e).__name__}: {e}", "error")
            log_path = (
                Path(os.environ.get("APPDATA", str(Path.home())))
                / "SentinelDesktop"
                / "last_error.log"
            )
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("w", encoding="utf-8") as f:
                    f.write(f"Goal: {goal}\n\n{tb}\n")
                self._add_chat(f"   Full traceback saved to: {log_path}", "system")
            except (OSError, RuntimeError) as exc2:
                logger.debug("Failed to write error log: %s", exc2)
            logger.exception("Agent run crashed")
        finally:
            if self.engine:
                self.engine.running = False
            self.root.after(
                0,
                lambda: self.status_label.configure(
                    text="● IDLE",
                    text_color=self._t("status_idle", "#849495"),
                ),
            )

    def _update_step_labels(self, step: int) -> None:
        """Main-thread helper for updating the step/notes labels."""
        if not self.engine:
            return
        self.step_label.configure(text=f"Step: {step}/{self.engine.max_steps}")
        self.notes_label.configure(text=f"Notes: {len(self.engine.notes)}")

    # ── Approval prompt ─────────────────────────────────────────────────

    def _approve_action(self, action: dict[str, Any]) -> bool:
        """Pop up an approval dialog for a state-changing action.

        Called from the engine worker thread. We use a threading.Event to
        block this thread until the user clicks Approve or Reject on the
        main thread.
        """
        decision = {"approved": False}
        event = threading.Event()

        def _prompt() -> None:
            try:
                top = ctk.CTkToplevel(self.root)
                top.title("Approve action?")
                top.geometry("480x220")
                top.transient(self.root)
                top.grab_set()

                action_name = action.get("action", "?")
                params = {k: v for k, v in action.items() if k != "action"}

                ctk.CTkLabel(
                    top,
                    text=f"The agent wants to run: {action_name}",
                    font=("Segoe UI", 13, "bold"),
                ).pack(anchor="w", padx=16, pady=(16, 4))

                detail = json.dumps(params, indent=2)[:600]
                ctk.CTkLabel(
                    top,
                    text=detail,
                    font=("Consolas", 10),
                    justify="left",
                    anchor="w",
                ).pack(fill="both", expand=True, padx=16, pady=4)

                btn_frame = ctk.CTkFrame(top)
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
                    text="✓ Approve",
                    command=_approve,
                    fg_color=self._t("status_running", "#95E400"),
                    hover_color=self._t("tag_assistant", "#95E400"),
                ).pack(side="right", padx=4)
                ctk.CTkButton(
                    btn_frame,
                    text="✗ Reject",
                    command=_reject,
                    fg_color=self._t("status_error", "#ff3b3b"),
                    hover_color=self._t("tag_error", "#ff3b3b"),
                ).pack(side="right", padx=4)

                top.protocol("WM_DELETE_WINDOW", _reject)
            except (RuntimeError, tk.TclError) as exc:
                logger.warning("approval prompt failed: %s", exc)
                event.set()

        self.root.after(0, _prompt)
        # Block worker thread until the user decides (or 60s timeout).
        event.wait(timeout=60)
        return decision["approved"]

    def _update_screenshot(self, b64_data: str) -> None:
        """Update the screenshot preview."""
        try:
            import base64
            import io

            from PIL import Image

            img_data = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(img_data))
            # Scale to fit panel
            max_w, max_h = 330, 250
            img.thumbnail((max_w, max_h))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            # Retain reference to prevent GC from collecting the image.
            self._screenshot_ctk_img = ctk_img
            self.screenshot_label.configure(image=ctk_img, text="")
        except (ValueError, OSError) as e:
            logger.warning("Screenshot update failed: %s", e)

    # ── Settings ────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        """Open settings window."""
        SettingsWindow(self.root, self.config, self._on_settings_saved, app=self)

    def _on_settings_saved(self) -> None:
        self.cfg = self.config.load()
        provider = self.cfg.get("provider", "none")
        model = self.cfg.get("model", "none")
        self.provider_label.configure(text=f"{provider} / {model}")

    # ── Command palette ─────────────────────────────────────────────────

    def _show_command_palette(self, event: Any = None) -> None:
        palette = ctk.CTkToplevel(self.root)
        palette.title("Command Palette")
        palette.geometry("500x400")
        palette.transient(self.root)
        palette.grab_set()

        entry = ctk.CTkEntry(palette, placeholder_text="Search commands…", height=40)
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
            ("Settings", lambda: (palette.destroy(), self._open_settings())),
            ("Screenshot", lambda: (self._take_screenshot(), palette.destroy())),
            ("Export Log", lambda: (self._export_log(), palette.destroy())),
        ]

        frame = ctk.CTkScrollableFrame(palette)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for name, cmd in commands:
            btn = ctk.CTkButton(frame, text=name, anchor="w", command=cmd)
            btn.pack(fill="x", pady=2)

        entry.focus()

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
        path = Path(f"sentinel_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(self.engine.forensic_log, f, indent=2)
            self._add_chat(f"Log exported to {path}", "system")
        except OSError as exc:
            self._add_chat(f"Failed to export log: {exc}", "error")

    # ── Run ─────────────────────────────────────────────────────────────

    # ── Tray ────────────────────────────────────────────────────────────

    # ── Resume Checkpoint ────────────────────────────────────────────────

    def _check_resume_checkpoint(self) -> None:
        """Check for resumable checkpoints and show banner."""
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
                f"🔄 **Resume previous run?** ({status}, stopped at step {step_num})\n"
                f"   Goal: {goal_preview}...\n"
                f"   Type 'resume' or press Ctrl+Shift+R to continue.",
                "system",
            )
        except (OSError, RuntimeError, ValueError) as exc:
            logger.debug("Checkpoint check failed: %s", exc)

    def _do_resume_checkpoint(self) -> None:
        """Resume from the latest checkpoint."""
        try:
            from core.checkpoint import CheckpointManager

            cp = CheckpointManager()
            latest = cp.load_latest()
            if not latest:
                self._add_chat("No resumable checkpoint found.", "system")
                return
            goal = latest.get("goal", "")
            if not goal:
                self._add_chat("Checkpoint has no goal — cannot resume.", "error")
                return
            self._add_chat(f"Resuming: {goal[:100]}...", "system")
            # Restore messages if available
            self._run_goal(goal)
        except (OSError, RuntimeError, ValueError) as exc:
            self._add_chat(f"Resume failed: {exc}", "error")

    # ── Action History ────────────────────────────────────────────────────

    def _build_history_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        """Build action history sidebar."""
        history_frame = ctk.CTkFrame(parent)
        history_frame.grid_rowconfigure(1, weight=1)
        history_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            history_frame,
            text="Action History",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        self.history_display = ctk.CTkTextbox(
            history_frame,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
            width=200,
            corner_radius=3,
        )
        self.history_display.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        return history_frame

    def _add_history_entry(self, step: int, action_name: str, result: dict[str, Any]) -> None:
        """Add an entry to the action history sidebar."""
        import time as _t

        timestamp = _t.strftime("%H:%M:%S")
        ok = result.get("ok", True)
        icon = "✅" if ok else "❌"
        msg = result.get("msg", "")[:60]
        line = f"{icon} {timestamp} #{step} {action_name}\n   {msg}\n"

        try:
            self.history_display.configure(state="normal")
            self.history_display.insert("end", line)
            self.history_display.configure(state="disabled")
            self.history_display.see("end")
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("History display update failed (panel not built yet): %s", exc)

    # ── Before/After Screenshots ──────────────────────────────────────────

    def _update_screenshot_with_diff(self, before_b64: str, after_b64: str) -> None:
        """Show before/after screenshots side by side in the right panel."""
        try:
            import base64
            import io

            from PIL import Image, ImageTk

            before_img = Image.open(io.BytesIO(base64.b64decode(before_b64)))
            after_img = Image.open(io.BytesIO(base64.b64decode(after_b64)))

            # Resize to fit panel
            max_w, max_h = 340, 200
            before_img.thumbnail((max_w, max_h))
            after_img.thumbnail((max_w, max_h))

            # Combine side by side
            total_w = before_img.width + after_img.width + 4
            combined = Image.new(
                "RGB", (total_w, max(before_img.height, after_img.height) + 20), (30, 30, 30)
            )
            combined.paste(before_img, (0, 0))
            combined.paste(after_img, (before_img.width + 4, 0))

            # Add labels
            from PIL import ImageDraw

            draw = ImageDraw.Draw(combined)
            draw.text((5, before_img.height + 3), "Before", fill=(150, 150, 150))
            draw.text((before_img.width + 9, after_img.height + 3), "After", fill=(150, 150, 150))

            self._screenshot_photo = ImageTk.PhotoImage(combined)
            self.screenshot_label.configure(image=self._screenshot_photo, text="")
        except (ValueError, OSError) as exc:
            logger.warning("Screenshot diff rendering failed: %s", exc)

    # ── Tray ────────────────────────────────────────────────────────────

    def _start_tray_if_enabled(self) -> None:
        if not self.cfg.get("minimize_to_tray") and not self.cfg.get("start_in_tray"):
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
                self.engine.stop() if self.engine and self.engine.running else None
            ),
            on_quit=lambda: self.root.after(0, self.root.destroy),
        )
        if self.tray.run() and self.cfg.get("start_in_tray"):
            # Hide the main window on launch.
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
            self.root.after(0, lambda: self.root.attributes("-topmost", True))
            self.root.after(200, lambda: self.root.attributes("-topmost", False))
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Failed to show window from tray: %s", exc)

    def _on_close_window(self) -> None:
        """User clicked the window's X button."""
        if self.cfg.get("minimize_to_tray") and self.tray:
            self._hide_to_tray()
        else:
            self.root.destroy()

    def run(self) -> None:
        """Start the main application event loop."""
        self._add_chat(
            "Sentinel Desktop v3.0 ready. Describe a goal and press Enter.\n"
            "Ctrl+K for command palette. ⚙ for settings.",
            "system",
        )
        # Check for resumable checkpoints
        self._check_resume_checkpoint()
        # Warn loudly if no LLM is configured — the most common first-run snag.
        cfg = self.config.load()
        provider = cfg.get("provider", "")
        if (
            not cfg.get("api_key") and provider not in ("ollama", "lmstudio", "custom")
        ) or not cfg.get("model"):
            self._add_chat(
                "⚠ No LLM configured yet. Click ⚙ in the top-right to choose a "
                "provider, paste your API key, and pick a model.",
                "error",
            )
        # Spin up the optional tray icon (does nothing if not configured).
        self._start_tray_if_enabled()
        self.root.mainloop()


class SettingsWindow:
    """Settings modal for provider/API key configuration."""

    def __init__(
        self, parent: ctk.CTk, config: Config, on_save: Any = None, app: Any = None
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
        """Build provider dropdown and base-URL entry."""
        from core.provider_registry import PROVIDERS, get_provider_names

        ctk.CTkLabel(self.win, text="Provider", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(20, 4)
        )
        self.provider_var = ctk.StringVar(value=self.cfg.get("provider", "openai"))
        self.provider_menu = ctk.CTkOptionMenu(
            self.win, variable=self.provider_var,
            values=get_provider_names(), command=self._on_provider_change,
        )
        self.provider_menu.pack(fill="x", padx=20, pady=4)

        ctk.CTkLabel(self.win, text="Base URL", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        url_frame = ctk.CTkFrame(self.win)
        url_frame.pack(fill="x", padx=20, pady=4)
        url_frame.grid_columnconfigure(0, weight=1)
        catalog_url = PROVIDERS.get(self.provider_var.get(), {}).get("base_url", "")
        self.base_url_var = ctk.StringVar(value=self.cfg.get("custom_base_url") or catalog_url)
        self.base_url_entry = ctk.CTkEntry(
            url_frame, textvariable=self.base_url_var, height=36,
            placeholder_text="Override the provider's base URL (optional)",
        )
        self.base_url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            url_frame, text="↺ Reset", width=90, height=36, command=self._reset_base_url,
        ).grid(row=0, column=1)
        ctk.CTkLabel(
            self.win,
            text=(
                "Leave as the catalog default for most providers. For Z.ai's "
                "Max Coding Plan use: https://api.z.ai/api/coding/paas/v4"
            ),
            font=("Segoe UI", 10), text_color="#b9cacb", wraplength=540, justify="left",
        ).pack(anchor="w", padx=20, pady=(2, 4))

    def _build_credentials_section(self) -> None:
        """Build API key and model name entry fields."""
        ctk.CTkLabel(self.win, text="API Key", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        self.api_key_entry = ctk.CTkEntry(
            self.win, show="•", height=36, placeholder_text="Paste your API key…",
        )
        self.api_key_entry.pack(fill="x", padx=20, pady=4)
        if self.cfg.get("api_key"):
            self.api_key_entry.insert(0, self.cfg["api_key"])

        ctk.CTkLabel(self.win, text="Model", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        model_frame = ctk.CTkFrame(self.win)
        model_frame.pack(fill="x", padx=20, pady=4)
        model_frame.grid_columnconfigure(0, weight=1)
        self.model_var = ctk.StringVar(value=self.cfg.get("model", ""))
        self.model_entry = ctk.CTkEntry(
            model_frame, textvariable=self.model_var, height=36,
            placeholder_text="Model name or auto-detect…",
        )
        self.model_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            model_frame, text="🔍 Detect", width=90, height=36, command=self._detect_models,
        ).grid(row=0, column=1)

    def _build_theme_section(self) -> None:
        """Build the theme dropdown."""
        ctk.CTkLabel(self.win, text="Theme", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        self.theme_var = ctk.StringVar(value=self.cfg.get("theme", "sentinel"))
        ctk.CTkOptionMenu(
            self.win, variable=self.theme_var,
            values=list(THEMES.keys()), command=self._on_theme_change,
        ).pack(fill="x", padx=20, pady=4)

    def _on_theme_change(self, choice: str) -> None:
        """Live theme switch from settings."""
        if self.app:
            self.app.current_theme = get_theme(choice)
            apply_theme(choice)
            self.app._t = lambda key, fb="": self.app.current_theme.get(key, fb)
            self.app.status_label.configure(text_color=self.app._t("status_idle", "#849495"))
            self.app.provider_label.configure(text_color=self.app._t("text_secondary", "#849495"))

    def _build_advanced(self) -> None:
        """Build monitor, run-mode, step-budget, and save controls."""
        self._build_monitor_section()
        self._build_run_mode_section()
        self._build_step_budget_section()
        ctk.CTkButton(
            self.win, text="💾 Save Settings", height=40, command=self._save,
        ).pack(fill="x", padx=20, pady=(20, 20))

    def _build_monitor_section(self) -> None:
        """Build the monitor-selection dropdown."""
        from core.screenshot import list_monitors

        ctk.CTkLabel(self.win, text="Monitor", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        monitor_choices: list[str] = ["auto — monitor with focused window (recommended)"]
        try:
            mons = list_monitors()
            if any(m.get("is_virtual") for m in mons):
                monitor_choices.append("0 — All monitors (virtual desktop)")
            for m in mons:
                if not m.get("is_virtual"):
                    label = (
                        f"{m['index']} — {m['width']}x{m['height']}"
                        f"{' (primary)' if m.get('is_primary') else ''}"
                    )
                    monitor_choices.append(label)
        except (OSError, RuntimeError) as exc:
            logger.debug("Monitor enumeration failed, using defaults: %s", exc)
            monitor_choices.extend(["0 — All monitors (virtual desktop)", "1 — Primary"])

        current_monitor = self.cfg.get("monitor")
        default_label = next(
            (s for s in monitor_choices if str(current_monitor) == s.split(" ", 1)[0]),
            monitor_choices[0],
        )
        self.monitor_var = ctk.StringVar(value=default_label)
        ctk.CTkOptionMenu(
            self.win, variable=self.monitor_var, values=monitor_choices,
        ).pack(fill="x", padx=20, pady=4)

    def _build_run_mode_section(self) -> None:
        """Build the run-mode toggle switches."""
        def _t(key: str, fb: str = "") -> str:
            return (self.app.current_theme.get(key, fb)) if self.app else fb

        ctk.CTkLabel(self.win, text="Run mode", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        toggles = [
            ("autonomous_var", "autonomous", "Fully autonomous (no approval prompts)"),
            ("dry_run_var", "dry_run", "Dry-run (log actions, don't execute)"),
            ("stealth_var", "stealth_input", "Stealth input (don't move my mouse/keyboard)"),
            ("tray_var", "minimize_to_tray", "Minimize to system tray (closes to tray instead of taskbar)"),
            ("start_tray_var", "start_in_tray", "Start hidden in tray (background-only launch)"),
        ]
        for attr, cfg_key, label in toggles:
            var = ctk.BooleanVar(value=bool(self.cfg.get(cfg_key)))
            setattr(self, attr, var)
            ctk.CTkSwitch(
                self.win, text=label, variable=var, onvalue=True, offvalue=False,
            ).pack(anchor="w", padx=20, pady=4)
        ctk.CTkLabel(
            self.win,
            text=(
                "Stealth mode sends clicks via Win32 PostMessage and UI "
                "Automation so the cursor stays put. Some apps (Chrome, "
                "games) may ignore synthesized input; falls back to "
                "physical mouse when that happens."
            ),
            font=("Segoe UI", 9),
            text_color=_t("text_secondary", "#b9cacb"),
            wraplength=540,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

    def _build_step_budget_section(self) -> None:
        """Build the step-budget entry field."""
        ctk.CTkLabel(self.win, text="Step Budget", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        self.steps_entry = ctk.CTkEntry(self.win, height=36, placeholder_text="100")
        self.steps_entry.pack(fill="x", padx=20, pady=4)
        self.steps_entry.insert(0, str(self.cfg.get("max_steps", 100)))

    def _on_provider_change(self, choice: str) -> None:
        """When the provider changes, refresh the Base URL placeholder."""
        from core.provider_registry import PROVIDERS

        catalog_url = PROVIDERS.get(choice, {}).get("base_url", "")
        # Only auto-fill the URL if the user hasn't typed a custom one.
        current = self.base_url_var.get().strip()
        if not current or current in {p.get("base_url", "") for p in PROVIDERS.values()}:
            self.base_url_var.set(catalog_url)

    def _reset_base_url(self) -> None:
        """Restore the selected provider's catalog default base URL."""
        from core.provider_registry import PROVIDERS

        provider = self.provider_var.get()
        self.base_url_var.set(PROVIDERS.get(provider, {}).get("base_url", ""))

    def _detect_models(self) -> None:
        """Fetch available models from the selected provider."""
        from core.provider_registry import fetch_models

        provider = self.provider_var.get()
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            self.model_var.set("Enter API key first")
            return

        models = fetch_models(provider, api_key)
        if models:
            self.model_var.set(models[0] if len(models) == 1 else "")
            # Show first few in a tooltip-like message
            self.model_entry.configure(
                placeholder_text=f"Found {len(models)} models: {', '.join(models[:5])}"
            )
        else:
            self.model_var.set("")
            self.model_entry.configure(placeholder_text="No models found. Enter manually.")

    def _save(self) -> None:
        from core.provider_registry import PROVIDERS

        provider = self.provider_var.get()
        self.cfg["provider"] = provider
        self.cfg["api_key"] = self.api_key_entry.get().strip()
        self.cfg["model"] = self.model_var.get().strip()
        self.cfg["theme"] = self.theme_var.get()

        # Only persist a custom base URL if it differs from the catalog
        # default — otherwise we'd freeze old URLs into config forever.
        url = self.base_url_var.get().strip().rstrip("/")
        catalog_url = PROVIDERS.get(provider, {}).get("base_url", "").rstrip("/")
        self.cfg["custom_base_url"] = url if url and url != catalog_url else ""

        try:
            self.cfg["max_steps"] = int(self.steps_entry.get() or "100")
        except ValueError:
            self.cfg["max_steps"] = 100

        # Parse monitor selection — first token is the index or "auto".
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
