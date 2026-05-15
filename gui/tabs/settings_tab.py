"""
Sentinel Desktop v3.0 — Settings Tab
Full settings panel with sections for all configuration.
"""

import json
import logging
import os
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)


class SettingsTab:
    """Settings tab — full configuration panel for Sentinel Desktop."""

    # Theme color keys with Override fallbacks
    COLORS = {
        "bg": ("bg_primary", "#050608"),
        "bg2": ("bg_secondary", "#0A0C10"),
        "bg_input": ("bg_input", "#111418"),
        "accent": ("accent", "#00F0FF"),
        "green": ("status_running", "#95E400"),
        "red": ("status_error", "#ff3b3b"),
        "text": ("text_primary", "#e2e2e8"),
        "text2": ("text_secondary", "#b9cacb"),
    }

    def __init__(self, parent: ctk.CTkFrame, app: Any) -> None:
        self.app = app
        self.root = parent
        self._vars: dict[str, Any] = {}
        self._callbacks: dict[str, Callable[..., Any]] = {}

        # Color helper
        self._t = app._t if hasattr(app, "_t") else lambda k, f="": f

        self._build()

    # ── Build ────────────────────────────────────────────────────────

    def _build(self) -> None:
        """Build the scrollable settings panel."""
        self.scroll = ctk.CTkScrollableFrame(
            self.root,
            fg_color=self._t("bg_primary", "#050608"),
        )
        self.scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._section_provider()
        self._section_agent()
        self._section_theme()
        self._section_scheduler()
        self._section_notifications()
        self._section_security()
        self._section_advanced()
        self._section_plugins()
        self._build_buttons()

    def _make_section(self, title: str) -> ctk.CTkFrame:
        """Create a labeled section frame."""
        frame = ctk.CTkFrame(
            self.scroll,
            fg_color=self._t("bg_secondary", "#0A0C10"),
            corner_radius=4,
        )
        frame.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self._t("accent", "#00F0FF"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="x", padx=12, pady=(0, 10))

        return content

    def _add_field(
        self,
        parent: Any,
        label: str,
        var_name: str,
        default: str = "",
        field_type: str = "entry",
        values: list[str] | None = None,
        row: int = 0,
    ) -> None:
        """Add a labeled field to a section."""
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=self._t("text_secondary", "#b9cacb"),
            font=ctk.CTkFont(size=12),
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)

        if field_type == "entry":
            var = ctk.StringVar(value=default)
            widget = ctk.CTkEntry(
                parent,
                textvariable=var,
                fg_color=self._t("bg_input", "#111418"),
                text_color=self._t("text_primary", "#e2e2e8"),
                corner_radius=3,
                width=300,
            )
            self._vars[var_name] = var
        elif field_type == "dropdown":
            var = ctk.StringVar(value=default)
            widget = ctk.CTkOptionMenu(
                parent,
                variable=var,
                values=values or [default],
                fg_color=self._t("bg_input", "#111418"),
                text_color=self._t("text_primary", "#e2e2e8"),
                button_color=self._t("accent", "#00F0FF"),
                width=300,
            )
            self._vars[var_name] = var
        elif field_type == "slider":
            var = ctk.DoubleVar(value=float(default))
            widget = ctk.CTkSlider(
                parent,
                variable=var,
                from_=values[0] if values else 0,
                to=values[1] if values else 1,
                number_of_steps=values[2] if values and len(values) > 2 else 100,
                button_color=self._t("accent", "#00F0FF"),
                width=300,
            )
            self._vars[var_name] = var
        elif field_type == "checkbox":
            var = ctk.BooleanVar(value=default.lower() in ("true", "1", "yes"))
            widget = ctk.CTkCheckBox(
                parent,
                text="",
                variable=var,
                fg_color=self._t("accent", "#00F0FF"),
                checkmark_color=self._t("bg_primary", "#050608"),
            )
            self._vars[var_name] = var
        else:
            return

        widget.grid(row=row, column=1, sticky="w", pady=3)
        parent.grid_columnconfigure(1, weight=1)

    # ── Sections ────────────────────────────────────────────────────

    def _section_provider(self) -> None:
        s = self._make_section("🤖 Provider")
        s.grid_columnconfigure(1, weight=1)
        self._add_field(
            s,
            "Model",
            "model",
            "gpt-4o",
            "dropdown",
            values=[
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "claude-3.5-sonnet",
                "glm-4v",
                "qwen-vl-max",
                "gemini-1.5-flash",
            ],
            row=0,
        )
        self._add_field(s, "API Key", "api_key", "", "entry", row=1)
        self._add_field(s, "Base URL", "base_url", "", "entry", row=2)
        self._add_field(
            s, "Temperature", "temperature", "0.3", "slider", values=[0.0, 2.0, 20], row=3
        )

    def _section_agent(self) -> None:
        s = self._make_section("🤖 Agent")
        self._add_field(s, "Max Steps", "max_steps", "50", "slider", values=[5, 200, 39], row=0)
        self._add_field(s, "Timeout (s)", "timeout", "300", "entry", row=1)
        self._add_field(
            s,
            "Approval Mode",
            "approval_mode",
            "auto",
            "dropdown",
            values=["auto", "approve", "deny"],
            row=2,
        )

    def _section_theme(self) -> None:
        s = self._make_section("🎨 Theme")
        self._add_field(
            s,
            "Theme",
            "theme",
            "sentinel",
            "dropdown",
            values=[
                "sentinel",
                "midnight",
                "cyberpunk",
                "dracula",
                "nord",
                "tokyo-night",
                "solarized",
                "gruvbox",
                "catppuccin",
                "one-dark",
                "material",
                "monokai",
                "horizon",
                "rose-pine",
                "mono",
            ],
            row=0,
        )

    def _section_scheduler(self) -> None:
        s = self._make_section("⏰ Scheduler")
        self._add_field(s, "Enable Scheduler", "scheduler_enabled", "false", "checkbox", row=0)

    def _section_notifications(self) -> None:
        s = self._make_section("🔔 Notifications")
        self._add_field(s, "Toast", "notify_toast", "true", "checkbox", row=0)
        self._add_field(s, "Log", "notify_log", "true", "checkbox", row=1)
        self._add_field(s, "Discord Webhook", "notify_discord_webhook", "", "entry", row=2)
        self._add_field(s, "HTTP Webhook", "notify_webhook_url", "", "entry", row=3)

    def _section_security(self) -> None:
        s = self._make_section("🔒 Security")
        self._add_field(s, "Session Timeout (h)", "session_timeout", "24", "entry", row=0)
        self._add_field(s, "Encrypt Credentials", "encrypt_credentials", "true", "checkbox", row=1)

    def _section_advanced(self) -> None:
        s = self._make_section("⚙️ Advanced")
        self._add_field(
            s,
            "Screenshot Quality",
            "screenshot_quality",
            "85",
            "slider",
            values=[10, 100, 90],
            row=0,
        )
        self._add_field(s, "Debug Mode", "debug_mode", "false", "checkbox", row=1)
        self._add_field(
            s,
            "Log Level",
            "log_level",
            "INFO",
            "dropdown",
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            row=2,
        )

    def _section_plugins(self) -> None:
        s = self._make_section("🔌 Plugins")
        self.plugin_list_frame = ctk.CTkFrame(s, fg_color="transparent")
        self.plugin_list_frame.pack(fill="x", pady=4)

        ctk.CTkButton(
            s,
            text="🔄 Reload Plugins",
            fg_color=self._t("accent", "#00F0FF"),
            text_color="#ffffff",
            corner_radius=3,
            command=self._reload_plugins,
        ).pack(anchor="w", pady=4)

        self._refresh_plugin_list()

    # ── Plugin List ─────────────────────────────────────────────────

    def _refresh_plugin_list(self) -> None:
        for w in self.plugin_list_frame.winfo_children():
            w.destroy()

        try:
            if hasattr(self.app, "engine") and self.app.engine:
                plugins = self.app.engine.plugin_loader.list_plugins()
            else:
                plugins = []
        except Exception as exc:
            logger.debug("Failed to list plugins: %s", exc)
            plugins = []

        if not plugins:
            ctk.CTkLabel(
                self.plugin_list_frame,
                text="No plugins loaded",
                text_color=self._t("text_secondary", "#b9cacb"),
            ).pack(anchor="w")
            return

        for p in plugins:
            row = ctk.CTkFrame(
                self.plugin_list_frame,
                fg_color=self._t("bg_input", "#111418"),
                corner_radius=3,
            )
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row,
                text=f"{p.get('name', '?')} v{p.get('version', '?')}",
                text_color=self._t("text_primary", "#e2e2e8"),
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=8, pady=4)

            ctk.CTkLabel(
                row,
                text=p.get("description", ""),
                text_color=self._t("text_secondary", "#b9cacb"),
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=8, pady=4)

    def _reload_plugins(self) -> None:
        try:
            if hasattr(self.app, "engine") and self.app.engine:
                self.app.engine.plugin_loader.load_all()
            self._refresh_plugin_list()
            logger.info("Plugins reloaded")
        except Exception as exc:
            logger.error("Plugin reload failed: %s", exc)

    # ── Buttons ─────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        btn_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        btn_frame.pack(fill="x", padx=4, pady=10)

        ctk.CTkButton(
            btn_frame,
            text="💾 Save Settings",
            fg_color=self._t("status_running", "#95E400"),
            text_color="#ffffff",
            corner_radius=4,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame,
            text="↩ Reset Defaults",
            fg_color=self._t("bg_input", "#111418"),
            text_color=self._t("text_primary", "#e2e2e8"),
            corner_radius=4,
            command=self._reset,
        ).pack(side="left", padx=4)

    # ── Save / Load ─────────────────────────────────────────────────

    def _gather_config(self) -> dict[str, Any]:
        """Read all UI vars into a config dict."""
        cfg = {}
        for name, var in self._vars.items():
            if isinstance(var, ctk.DoubleVar):
                cfg[name] = round(var.get(), 2)
            elif isinstance(var, ctk.BooleanVar):
                cfg[name] = var.get()
            else:
                cfg[name] = var.get()
        return cfg

    def _save(self) -> None:
        """Save current settings to config/config.json."""
        cfg = self._gather_config()
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.json"
        )
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            # Merge with existing config
            existing = {}
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    existing = json.load(f)
            existing.update(cfg)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            logger.info("Settings saved to %s", config_path)

            # Apply theme immediately
            if "theme" in cfg and hasattr(self.app, "set_theme"):
                self.app.set_theme(cfg["theme"])

        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to save settings: %s", exc)

    def _reset(self) -> None:
        """Reset all fields to defaults."""
        defaults = {
            "model": "gpt-4o",
            "api_key": "",
            "base_url": "",
            "temperature": "0.3",
            "max_steps": "50",
            "timeout": "300",
            "approval_mode": "auto",
            "theme": "sentinel",
            "scheduler_enabled": "false",
            "notify_toast": "true",
            "notify_log": "true",
            "notify_discord_webhook": "",
            "notify_webhook_url": "",
            "session_timeout": "24",
            "encrypt_credentials": "true",
            "screenshot_quality": "85",
            "debug_mode": "false",
            "log_level": "INFO",
        }
        for name, val in defaults.items():
            if name in self._vars:
                var = self._vars[name]
                if isinstance(var, ctk.DoubleVar):
                    var.set(float(val))
                elif isinstance(var, ctk.BooleanVar):
                    var.set(val.lower() in ("true", "1", "yes"))
                else:
                    var.set(val)
        logger.info("Settings reset to defaults")

    def load_config(self, config: dict[str, Any]) -> None:
        """Load values from a config dict into UI vars."""
        for name, val in config.items():
            if name in self._vars:
                var = self._vars[name]
                if isinstance(var, ctk.DoubleVar):
                    var.set(float(val))
                elif isinstance(var, ctk.BooleanVar):
                    var.set(
                        bool(val)
                        if not isinstance(val, str)
                        else val.lower() in ("true", "1", "yes")
                    )
                else:
                    var.set(str(val))
