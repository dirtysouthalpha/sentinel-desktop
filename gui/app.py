"""
Sentinel Desktop v2 — Main GUI Application.

Dark-themed customtkinter interface with chat, live screenshot, and settings.
"""

import json
import logging
import threading
import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from gui.themes import THEMES, apply_theme
from config import Config

logger = logging.getLogger(__name__)


class SentinelApp:
    """Main application window."""

    def __init__(self, config: Config):
        self.config = config
        self.cfg = config.load()

        # Theme
        ctk.set_appearance_mode("dark")
        theme_name = self.cfg.get("theme", "midnight")
        if theme_name in THEMES:
            apply_theme(THEMES[theme_name])

        # Window
        self.root = ctk.CTk()
        self.root.title("Sentinel Desktop v2")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # State
        self.engine = None
        self.engine_thread = None
        self._approval_event = threading.Event()

        # Build UI
        self._build_header()
        self._build_main_area()
        self._build_input()

        # Command palette
        self.root.bind("<Control-k>", self._show_command_palette)

    # ── Header ──────────────────────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self.root, height=50)
        header.pack(fill="x", padx=8, pady=(8, 4))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="⬡ Sentinel Desktop", font=("Segoe UI", 16, "bold")
        ).pack(side="left", padx=12)

        self.status_label = ctk.CTkLabel(
            header, text="● IDLE", font=("Segoe UI", 12),
            text_color="#888888"
        )
        self.status_label.pack(side="left", padx=20)

        # Provider / model
        provider = self.cfg.get("provider", "none")
        model = self.cfg.get("model", "none")
        self.provider_label = ctk.CTkLabel(
            header,
            text=f"{provider} / {model}",
            font=("Segoe UI", 10),
            text_color="#666666",
        )
        self.provider_label.pack(side="right", padx=12)

        # Settings button
        ctk.CTkButton(
            header, text="⚙", width=32, height=32,
            command=self._open_settings,
        ).pack(side="right", padx=4)

    # ── Main area ───────────────────────────────────────────────────────

    def _build_main_area(self):
        main = ctk.CTkFrame(self.root)
        main.pack(fill="both", expand=True, padx=8, pady=4)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # Chat panel
        chat_frame = ctk.CTkFrame(main)
        chat_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(
            chat_frame, wrap="word", font=("Consolas", 12),
            state="disabled", corner_radius=8,
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Right panel — screenshot + info
        right = ctk.CTkFrame(main, width=350)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            right, text="Live View", font=("Segoe UI", 12, "bold")
        ).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        self.screenshot_label = ctk.CTkLabel(right, text="No screenshot")
        self.screenshot_label.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        # Info
        info_frame = ctk.CTkFrame(right)
        info_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=4)

        self.step_label = ctk.CTkLabel(
            info_frame, text="Step: 0/100", font=("Consolas", 10)
        )
        self.step_label.pack(anchor="w", padx=8, pady=2)

        self.notes_label = ctk.CTkLabel(
            info_frame, text="Notes: 0", font=("Consolas", 10)
        )
        self.notes_label.pack(anchor="w", padx=8, pady=2)

    # ── Input ───────────────────────────────────────────────────────────

    def _build_input(self):
        input_frame = ctk.CTkFrame(self.root, height=60)
        input_frame.pack(fill="x", padx=8, pady=(4, 8))
        input_frame.pack_propagate(False)
        input_frame.grid_columnconfigure(0, weight=1)

        self.goal_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Describe what you want done… (Ctrl+K for commands)",
            height=40, font=("Segoe UI", 13),
        )
        self.goal_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.goal_entry.bind("<Return>", self._on_submit)

        ctk.CTkButton(
            input_frame, text="▶ Run", width=80, height=40,
            command=self._on_submit,
        ).grid(row=0, column=1, padx=(4, 8), pady=8)

        ctk.CTkButton(
            input_frame, text="■ Stop", width=80, height=40,
            command=self._on_stop, fg_color="#c0392b", hover_color="#e74c3c",
        ).grid(row=0, column=2, padx=(0, 8), pady=8)

    # ── Chat display ────────────────────────────────────────────────────

    def _add_chat(self, text: str, tag: str = "system"):
        self.chat_display.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "user": "#3498db",
            "assistant": "#2ecc71",
            "action": "#f39c12",
            "error": "#e74c3c",
            "system": "#95a5a6",
        }
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

    def _on_submit(self, event=None):
        goal = self.goal_entry.get().strip()
        if not goal:
            return
        self.goal_entry.delete(0, "end")
        self._add_chat(goal, "user")
        self._run_goal(goal)

    def _on_stop(self):
        if self.engine and self.engine.running:
            self.engine.stop()
            self._add_chat("Agent stopped by user.", "system")

    def _run_goal(self, goal: str):
        """Start agent in background thread."""
        if self.engine and self.engine.running:
            self._add_chat("Agent already running. Stop it first.", "error")
            return

        cfg = self.config.load()

        from core.engine import AgentEngine
        self.engine = AgentEngine(cfg)

        def _on_step(**kwargs):
            """Callback from engine on each step."""
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

            # Update UI
            self.step_label.configure(text=f"Step: {step}/{self.engine.max_steps}")
            self.notes_label.configure(text=f"Notes: {len(self.engine.notes)}")

            # Update screenshot if provided
            screenshot_b64 = kwargs.get("screenshot")
            if screenshot_b64:
                self._update_screenshot(screenshot_b64)

        self.engine.on_step_callback = _on_step

        def _run():
            try:
                result = self.engine.run(goal)
                summary = result.get("finish_summary", "Done.")
                self._add_chat(f"✅ Completed in {result.get('steps', 0)} steps.\n{summary}", "assistant")
            except Exception as e:
                self._add_chat(f"❌ Error: {e}", "error")
            finally:
                self.status_label.configure(text="● IDLE", text_color="#888888")

        self.status_label.configure(text="● RUNNING", text_color="#2ecc71")
        self.engine_thread = threading.Thread(target=_run, daemon=True)
        self.engine_thread.start()

    def _update_screenshot(self, b64_data: str):
        """Update the screenshot preview."""
        try:
            import base64
            from PIL import Image, ImageTk
            import io

            img_data = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(img_data))
            # Scale to fit panel
            max_w, max_h = 330, 250
            img.thumbnail((max_w, max_h))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.screenshot_label.configure(image=ctk_img, text="")
        except Exception as e:
            logger.debug(f"Screenshot update failed: {e}")

    # ── Settings ────────────────────────────────────────────────────────

    def _open_settings(self):
        """Open settings window."""
        SettingsWindow(self.root, self.config, self._on_settings_saved)

    def _on_settings_saved(self):
        self.cfg = self.config.load()
        provider = self.cfg.get("provider", "none")
        model = self.cfg.get("model", "none")
        self.provider_label.configure(text=f"{provider} / {model}")

    # ── Command palette ─────────────────────────────────────────────────

    def _show_command_palette(self, event=None):
        palette = ctk.CTkToplevel(self.root)
        palette.title("Command Palette")
        palette.geometry("500x400")
        palette.transient(self.root)
        palette.grab_set()

        entry = ctk.CTkEntry(palette, placeholder_text="Search commands…", height=40)
        entry.pack(fill="x", padx=12, pady=12)

        commands = [
            ("New Chat", lambda: (self.chat_display.configure(state="normal"),
                                   self.chat_display.delete("1.0", "end"),
                                   self.chat_display.configure(state="disabled"),
                                   palette.destroy())),
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

    def _take_screenshot(self):
        from core.screenshot import capture_to_base64
        b64 = capture_to_base64()
        self._update_screenshot(b64)
        self._add_chat("Screenshot captured.", "system")

    def _export_log(self):
        if not self.engine:
            self._add_chat("No log to export.", "system")
            return
        path = f"sentinel_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(path, "w") as f:
            json.dump(self.engine.forensic_log, f, indent=2)
        self._add_chat(f"Log exported to {path}", "system")

    # ── Run ─────────────────────────────────────────────────────────────

    def run(self):
        self._add_chat(
            "Sentinel Desktop v2 ready. Describe a goal and press Enter.\n"
            "Ctrl+K for command palette. ⚙ for settings.",
            "system"
        )
        self.root.mainloop()


class SettingsWindow:
    """Settings modal for provider/API key configuration."""

    def __init__(self, parent, config: Config, on_save=None):
        self.config = config
        self.cfg = config.load()
        self.on_save = on_save

        self.win = ctk.CTkToplevel(parent)
        self.win.title("Settings")
        self.win.geometry("550x500")
        self.win.transient(parent)
        self.win.grab_set()

        self._build()

    def _build(self):
        from core.provider_registry import PROVIDERS, get_provider_names

        # Provider
        ctk.CTkLabel(self.win, text="Provider", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(20, 4)
        )
        self.provider_var = ctk.StringVar(value=self.cfg.get("provider", "openai"))
        providers = get_provider_names()
        self.provider_menu = ctk.CTkOptionMenu(
            self.win, variable=self.provider_var, values=providers,
            command=self._on_provider_change,
        )
        self.provider_menu.pack(fill="x", padx=20, pady=4)

        # API Key
        ctk.CTkLabel(self.win, text="API Key", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        self.api_key_entry = ctk.CTkEntry(
            self.win, show="•", height=36,
            placeholder_text="Paste your API key…",
        )
        self.api_key_entry.pack(fill="x", padx=20, pady=4)
        if self.cfg.get("api_key"):
            self.api_key_entry.insert(0, self.cfg["api_key"])

        # Model
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
            model_frame, text="🔍 Detect", width=90, height=36,
            command=self._detect_models,
        ).grid(row=0, column=1)

        # Theme
        ctk.CTkLabel(self.win, text="Theme", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        self.theme_var = ctk.StringVar(value=self.cfg.get("theme", "midnight"))
        ctk.CTkOptionMenu(
            self.win, variable=self.theme_var, values=list(THEMES.keys()),
        ).pack(fill="x", padx=20, pady=4)

        # Step budget
        ctk.CTkLabel(self.win, text="Step Budget", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4)
        )
        self.steps_entry = ctk.CTkEntry(
            self.win, height=36,
            placeholder_text="100",
        )
        self.steps_entry.pack(fill="x", padx=20, pady=4)
        self.steps_entry.insert(0, str(self.cfg.get("max_steps", 100)))

        # Save
        ctk.CTkButton(
            self.win, text="💾 Save Settings", height=40,
            command=self._save,
        ).pack(fill="x", padx=20, pady=(20, 20))

    def _on_provider_change(self, choice):
        pass  # model will be auto-detected or manually entered

    def _detect_models(self):
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
            self.model_entry.configure(
                placeholder_text="No models found. Enter manually."
            )

    def _save(self):
        self.cfg["provider"] = self.provider_var.get()
        self.cfg["api_key"] = self.api_key_entry.get().strip()
        self.cfg["model"] = self.model_var.get().strip()
        self.cfg["theme"] = self.theme_var.get()
        try:
            self.cfg["max_steps"] = int(self.steps_entry.get() or "100")
        except ValueError:
            self.cfg["max_steps"] = 100
        self.config.save(self.cfg)
        if self.on_save:
            self.on_save()
        self.win.destroy()
