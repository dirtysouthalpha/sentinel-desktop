"""
Sentinel Desktop - Main UI Application
Professional dark-themed chat interface with system monitoring.
"""
import os
import threading
import tkinter as tk
from tkinter import filedialog
from datetime import datetime

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("customtkinter is required: pip install customtkinter")

import psutil

from src.config import (
    APP_TITLE, VERSION, COLORS, WINDOW_WIDTH, WINDOW_HEIGHT,
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, load_config, save_config,
    SCREENSHOT_DIR, BRAIN_URL
)
from src.core.engine import CommandEngine, CommandResult
from src.core.brain import BrainClient


class SentinelDesktopApp:
    """Main application window."""

    def __init__(self):
        self.config = load_config()
        self.brain = BrainClient(self.config.get("brain_url", BRAIN_URL))
        self.engine = CommandEngine(self.brain)
        self.command_history = []
        self.history_index = -1
        self.last_response = ""

        self._setup_window()
        self._setup_styles()
        self._build_ui()
        self._check_brain()
        self._start_sys_monitor()

    def _setup_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.app = ctk.CTk()
        self.app.title(APP_TITLE)
        self.app.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.app.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.app.configure(fg_color=COLORS["bg_primary"])

        # Set app icon
        import platform
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "assets", "sentinel_icon.png"
        )
        if os.path.exists(icon_path):
            icon_img = tk.PhotoImage(file=icon_path)
            self.app.iconphoto(True, icon_img)
            self._icon_img = icon_img  # Prevent garbage collection
        if platform.system() == "Windows":
            ico_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "assets", "sentinel_icon.ico"
            )
            if os.path.exists(ico_path):
                try:
                    self.app.iconbitmap(ico_path)
                except Exception:
                    pass

    def _setup_styles(self):
        self.font_title = ("Segoe UI", 20, "bold")
        self.font_header = ("Segoe UI", 14, "bold")
        self.font_body = ("Segoe UI", 12)
        self.font_mono = ("Consolas", 11)
        self.font_small = ("Segoe UI", 10)

    def _build_ui(self):
        self.app.grid_columnconfigure(0, weight=1)
        self.app.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_chat()
        self._build_input()

    def _build_header(self):
        header = ctk.CTkFrame(self.app, height=70, fg_color=COLORS["bg_secondary"])
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        header.grid_columnconfigure(1, weight=1)

        # Logo/Title
        ctk.CTkLabel(
            header, text="SENTINEL", font=self.font_title,
            text_color=COLORS["accent"]
        ).grid(row=0, column=0, padx=(16, 4), pady=12)
        ctk.CTkLabel(
            header, text=f"Desktop v{VERSION}", font=self.font_body,
            text_color=COLORS["text_secondary"]
        ).grid(row=0, column=1, sticky="w", pady=12)

        # System stats
        self.sys_label = ctk.CTkLabel(
            header, text="CPU: --% | MEM: --%", font=self.font_small,
            text_color=COLORS["text_secondary"]
        )
        self.sys_label.grid(row=0, column=2, padx=16)

        # Brain status
        self.brain_label = ctk.CTkLabel(
            header, text="BRAIN: ...", font=self.font_small,
            text_color=COLORS["warning"]
        )
        self.brain_label.grid(row=0, column=3, padx=(0, 8))

        # Settings button
        self.settings_btn = ctk.CTkButton(
            header, text="⚙", width=36, height=36,
            font=("Segoe UI", 16),
            command=self._open_settings,
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_secondary"]
        )
        self.settings_btn.grid(row=0, column=4, padx=(0, 16))


    def _open_settings(self):
        """Open settings dialog."""
        dialog = ctk.CTkToplevel(self.app)
        dialog.title("Settings")
        dialog.geometry("450x400")
        dialog.configure(fg_color=COLORS["bg_secondary"])
        dialog.transient(self.app)
        dialog.grab_set()

        # Title
        ctk.CTkLabel(
            dialog, text="Settings", font=self.font_header,
            text_color=COLORS["accent"]
        ).pack(pady=(16, 8))

        # Brain URL
        url_frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_tertiary"])
        url_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(url_frame, text="Neuralis Brain URL:", font=self.font_small).pack(anchor="w", padx=12, pady=(8, 0))
        url_entry = ctk.CTkEntry(url_frame, value=self.config.get("brain_url", ""), width=380)
        url_entry.pack(fill="x", padx=12, pady=(0, 8))

        # Mouse speed
        speed_frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_tertiary"])
        speed_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(speed_frame, text="Mouse Speed:", font=self.font_small).pack(anchor="w", padx=12, pady=(8, 0))
        speed_slider = ctk.CTkSlider(speed_frame, from_=0.1, to=1.0, width=350)
        speed_slider.set(self.config.get("mouse_speed", 0.3))
        speed_slider.pack(fill="x", padx=12, pady=(0, 8))

        # Screenshot format
        fmt_frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_tertiary"])
        fmt_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(fmt_frame, text="Screenshot Format:", font=self.font_small).pack(anchor="w", padx=12, pady=(8, 0))
        fmt_var = ctk.StringVar(value=self.config.get("screenshot_format", "png"))
        ctk.CTkSegmentedButton(fmt_frame, values=["png", "jpg"], variable=fmt_var).pack(fill="x", padx=12, pady=(0, 8))

        # Save button
        def save_settings():
            self.config["brain_url"] = url_entry.get()
            self.config["mouse_speed"] = speed_slider.get()
            self.config["screenshot_format"] = fmt_var.get()
            save_config(self.config)
            self.brain = BrainClient(self.config.get("brain_url", BRAIN_URL))
            self.engine.brain = self.brain
            self._add_message("Settings saved.", "success")
            self._check_brain()
            dialog.destroy()

        ctk.CTkButton(
            dialog, text="Save", command=save_settings,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"], height=36
        ).pack(pady=16)

    def _build_chat(self):
        chat_frame = ctk.CTkFrame(self.app, fg_color=COLORS["bg_primary"])
        chat_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        chat_frame.grid_columnconfigure(0, weight=1)
        chat_frame.grid_rowconfigure(0, weight=1)

        self.chat_scroll = ctk.CTkScrollableFrame(
            chat_frame, fg_color=COLORS["bg_primary"]
        )
        self.chat_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.chat_scroll.grid_columnconfigure(0, weight=1)

        # Welcome message
        self._add_welcome()

    def _build_input(self):
        input_frame = ctk.CTkFrame(self.app, height=70, fg_color=COLORS["bg_secondary"])
        input_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type a command... (e.g. 'check cpu', 'click 500,300', 'ping google.com')",
            font=self.font_body, height=42,
            fg_color=COLORS["bg_tertiary"],
            border_color=COLORS["accent"],
            border_width=1,
            text_color=COLORS["text_primary"]
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=12, pady=14)
        self.entry.bind("<Return>", lambda e: self._handle_send())
        self.entry.bind("<Up>", self._history_up)
        self.entry.bind("<Down>", self._history_down)

        # Global hotkeys
        self.app.bind("<Control-l>", lambda e: self._clear_chat())
        self.app.bind("<Control-Return>", lambda e: self._handle_send())
        self.app.bind("<Escape>", lambda e: self.entry.focus_set())

        self.send_btn = ctk.CTkButton(
            input_frame, text="Send", width=80, height=42,
            font=self.font_header, command=self._handle_send,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"]
        )
        self.send_btn.grid(row=0, column=1, padx=(4, 4), pady=14)

        self.copy_btn = ctk.CTkButton(
            input_frame, text="Copy", width=70, height=42,
            font=self.font_body, command=self._copy_last,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_secondary"]
        )
        self.copy_btn.grid(row=0, column=2, padx=(4, 4), pady=14)

        self.clear_btn = ctk.CTkButton(
            input_frame, text="Clear", width=70, height=42,
            font=self.font_body, command=self._clear_chat,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"]
        )
        self.clear_btn.grid(row=0, column=3, padx=(0, 12), pady=14)

    def _add_welcome(self):
        sep = "=" * 40
        welcome = f"""
{sep}
  SENTINEL DESKTOP v{VERSION}
{sep}

  Commands:
  - System: cpu, memory, disk, processes, battery, temp, uptime
  - Automation: click X,Y | type text | press ctrl+c | move X,Y
  - Network: ping host | ipconfig | network diagnostics
  - Process: open chrome | close notepad
  - Files: list C:/ | find report | read file.txt
  - AI: recall topic | think topic content | brain status
  - Type 'help' for full command list

{sep}"""
        self._add_message(welcome, "system")

    def _add_message(self, text: str, sender: str = "assistant"):
        """Add a message bubble to the chat."""
        colors = {
            "user": COLORS["user_bubble"],
            "assistant": COLORS["assistant_bubble"],
            "system": COLORS["bg_tertiary"],
            "error": "#3a1520",
            "success": "#0d2818",
        }
        text_colors = {
            "user": COLORS["text_primary"],
            "assistant": COLORS["text_primary"],
            "system": COLORS["accent"],
            "error": COLORS["error"],
            "success": COLORS["success"],
        }

        frame = ctk.CTkFrame(
            self.chat_scroll,
            fg_color=colors.get(sender, colors["assistant"]),
            corner_radius=10
        )
        frame.pack(fill="x", pady=3, padx=8)
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(
            frame, text=text, font=self.font_mono,
            text_color=text_colors.get(sender, COLORS["text_primary"]),
            wraplength=750, justify="left", anchor="w"
        )
        label.grid(row=0, column=0, sticky="w", padx=14, pady=8)

        # Right-click to copy message
        def copy_msg(msg=text):
            self.app.clipboard_clear()
            self.app.clipboard_append(msg)
        label.bind("<Button-3>", lambda e, fn=copy_msg: fn())

        self.chat_scroll._parent_canvas.yview_moveto(1.0)
        if sender in ("assistant", "system"):
            self.last_response = text

    def _handle_send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")

        # Save to history
        self.command_history.append(text)
        if len(self.command_history) > 100:
            self.command_history = self.command_history[-100:]
        self.history_index = len(self.command_history)

        # Show user message
        self._add_message(f"> {text}", "user")

        # Disable send, show processing
        self.send_btn.configure(state="disabled", text="...")

        # Process in thread
        threading.Thread(target=self._process_command, args=(text,), daemon=True).start()

    def _process_command(self, text: str):
        try:
            result = self.engine.execute(text)
            if result.success:
                self.app.after(0, lambda: self._add_message(result.message, "assistant"))
            else:
                self.app.after(0, lambda: self._add_message(result.message, "error"))
        except Exception as e:
            self.app.after(0, lambda err=str(e): self._add_message(f"Error: {err}", "error"))
        finally:
            self.app.after(0, lambda: self.send_btn.configure(state="normal", text="Send"))

    def _history_up(self, event=None):
        if self.command_history and self.history_index > 0:
            self.history_index -= 1
            self.entry.delete(0, "end")
            self.entry.insert(0, self.command_history[self.history_index])

    def _history_down(self, event=None):
        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.entry.delete(0, "end")
            self.entry.insert(0, self.command_history[self.history_index])
        else:
            self.history_index = len(self.command_history)
            self.entry.delete(0, "end")
    def _copy_last(self):
        """Copy last assistant response to clipboard."""
        if hasattr(self, 'last_response') and self.last_response:
            self.app.clipboard_clear()
            self.app.clipboard_append(self.last_response)
            self.copy_btn.configure(text="Copied!")
            self.app.after(2000, lambda: self.copy_btn.configure(text="Copy"))
        else:
            self.copy_btn.configure(text="Nothing")
            self.app.after(2000, lambda: self.copy_btn.configure(text="Copy"))


    def _clear_chat(self):
        for widget in self.chat_scroll.winfo_children():
            widget.destroy()
        self._add_welcome()

    def _check_brain(self):
        def check():
            health = self.brain.health()
            status = health.get("status", "unknown")
            if status == "ok" or status == "online":
                self.app.after(0, lambda: self.brain_label.configure(
                    text="BRAIN: ONLINE", text_color=COLORS["success"]
                ))
            else:
                self.app.after(0, lambda: self.brain_label.configure(
                    text="BRAIN: OFFLINE", text_color=COLORS["error"]
                ))
        threading.Thread(target=check, daemon=True).start()

    def _start_sys_monitor(self):
        def update():
            try:
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory().percent
                self.sys_label.configure(
                    text=f"CPU: {cpu:.0f}% | MEM: {mem:.0f}%",
                    text_color=COLORS["error"] if cpu > 85 else COLORS["text_secondary"]
                )
            except Exception:
                pass
            self.app.after(3000, update)
        self.app.after(1000, update)

    def run(self):
        self.app.mainloop()


def main():
    app = SentinelDesktopApp()
    app.run()
