# Sentinel Windows - System Automation & Troubleshooting
# Python desktop app for keyboard/mouse control and system diagnostics

import customtkinter as ctk
import pyautogui
import psutil
import subprocess
import os
import json
import threading
import time
from datetime import datetime

# Set appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class SentinelWindows:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("Sentinel Windows - System Automation")
        self.app.geometry("900x700")
        self.app.minsize(800, 600)

        # State
        self.agent_active = False
        self.command_history = []

        self.setup_ui()

    def setup_ui(self):
        # Main layout
        self.app.grid_columnconfigure(0, weight=1)
        self.app.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self.app, height=60)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="Sentinel Windows", font=("Arial", 18, "bold")).grid(
            row=0, column=0, padx=10
        )

        self.status_indicator = ctk.CTkLabel(header, text="IDLE", text_color="gray")
        self.status_indicator.grid(row=0, column=1, sticky="e", padx=10)

        # Chat display
        self.chat_frame = ctk.CTkScrollableFrame(self.app)
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # Input area
        input_frame = ctk.CTkFrame(self.app, height=80)
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_frame, 
            placeholder_text="Type command (e.g., 'click at 100,200' or 'check cpu usage')",
            height=40
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=5)
        self.entry.bind("<Return>", self.handle_command)

        self.send_btn = ctk.CTkButton(
            input_frame, 
            text="Send", 
            width=80,
            command=self.handle_command
        )
        self.send_btn.grid(row=0, column=1, padx=5)

        # System info panel
        self.create_system_panel()

    def create_system_panel(self):
        # System info in header area
        self.cpu_label = ctk.CTkLabel(
            self.app, 
            text=f"CPU: {psutil.cpu_percent()}% | MEM: {psutil.virtual_memory().percent}%"
        )
        self.cpu_label.grid(row=0, column=2, padx=10)

        # Update periodically
        self.update_system_info()

    def update_system_info(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        self.cpu_label.configure(text=f"CPU: {cpu}% | MEM: {mem}%")
        self.app.after(2000, self.update_system_info)

    def add_message(self, text, sender="assistant"):
        """Add a message to the chat"""
        frame = ctk.CTkFrame(self.chat_frame)
        frame.pack(fill="x", pady=2, padx=5)

        label = ctk.CTkLabel(
            frame, 
            text=text,
            wraplength=800,
            justify="left"
        )
        label.pack(anchor="w", padx=10, pady=5)

        self.chat_frame._parent_canvas.yview_moveto(1.0)

    def handle_command(self, event=None):
        cmd = self.entry.get().strip()
        if not cmd:
            return

        self.entry.delete(0, "end")
        self.add_message(f"You: {cmd}", "user")

        # Process command in thread
        threading.Thread(target=self.process_command, args=(cmd,), daemon=True).start()

    def process_command(self, cmd):
        """Process user command and execute actions"""
        self.set_active(True)

        try:
            cmd_lower = cmd.lower()

            # System diagnostics
            if "cpu" in cmd_lower:
                cpu = psutil.cpu_percent(interval=1)
                self.add_message(f"CPU Usage: {cpu}%")

            elif "memory" in cmd_lower or "ram" in cmd_lower:
                mem = psutil.virtual_memory()
                self.add_message(f"Memory: {mem.percent}% used ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)")

            elif "disk" in cmd_lower:
                disk = psutil.disk_usage("/")
                self.add_message(f"Disk: {disk.percent}% used ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)")

            elif "processes" in cmd_lower or "tasks" in cmd_lower:
                procs = list(psutil.process_iter(["pid", "name", "cpu_percent"]))[:10]
                proc_list = chr(10).join([f"{p.info['pid']}: {p.info['name']} ({p.info['cpu_percent']}%)" for p in procs])
                self.add_message(f"Top Processes:" + chr(10) + proc_list)

            elif "screenshot" in cmd_lower:
                self.take_screenshot()

            # Mouse/keyboard control
            elif cmd_lower.startswith("click"):
                self.handle_click(cmd)

            elif cmd_lower.startswith("type"):
                text = cmd[5:].strip()
                pyautogui.typewrite(text)
                self.add_message(f"Typed: {text}")

            elif cmd_lower.startswith("press"):
                key = cmd[6:].strip()
                pyautogui.press(key)
                self.add_message(f"Pressed: {key}")

            elif cmd_lower.startswith("move"):
                parts = cmd.split()
                if len(parts) >= 3:
                    x, y = int(parts[1]), int(parts[2])
                    pyautogui.moveTo(x, y)
                    self.add_message(f"Moved mouse to ({x}, {y})")

            elif "help" in cmd_lower:
                self.show_help()

            else:
                self.add_message("I can help with:" + chr(10) + "- System info (cpu, memory, disk, processes)" + chr(10) + "- Mouse control (click, move)" + chr(10) + "- Keyboard (type, press)" + chr(10) + "- Screenshot" + chr(10) + "Type 'help' for examples")

        except Exception as e:
            self.add_message(f"Error: {str(e)}")

        self.set_active(False)

    def handle_click(self, cmd):
        """Handle mouse click commands"""
        import re
        # Parse coordinates from command
        match = re.search(r'(\d+)\s*[,x]\s*(\d+)', cmd)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            pyautogui.click(x, y)
            self.add_message(f"Clicked at ({x}, {y})")
        else:
            pyautogui.click()
            pos = pyautogui.position()
            self.add_message(f"Clicked at current position ({pos.x}, {pos.y})")

    def take_screenshot(self):
        """Take a screenshot"""
        try:
            screenshot = pyautogui.screenshot()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            screenshot.save(filename)
            self.add_message(f"Screenshot saved: {filename}")
        except Exception as e:
            self.add_message(f"Screenshot failed: {str(e)}")

    def show_help(self):
        """Show help message"""
        help_text = "Available Commands:" + chr(10) + chr(10) + "System Info:" + chr(10) + "- cpu - Show CPU usage" + chr(10) + "- memory - Show RAM usage" + chr(10) + "- disk - Show disk usage" + chr(10) + "- processes - List top processes" + chr(10) + chr(10) + "Mouse Control:" + chr(10) + "- click - Click at current position" + chr(10) + "- click 100,200 - Click at coordinates" + chr(10) + "- move 500,300 - Move mouse to position" + chr(10) + chr(10) + "Keyboard:" + chr(10) + "- type hello - Type text" + chr(10) + "- press enter - Press a key" + chr(10) + "- press ctrl+c - Press key combination" + chr(10) + chr(10) + "Other:" + chr(10) + "- screenshot - Take screenshot" + chr(10) + "- help - Show this help"
        self.add_message(help_text)

    def set_active(self, active):
        """Update status indicator"""
        self.agent_active = active
        if active:
            self.status_indicator.configure(text="ACTIVE", text_color="green")
        else:
            self.status_indicator.configure(text="IDLE", text_color="gray")

    def run(self):
        self.app.mainloop()


if __name__ == "__main__":
    app = SentinelWindows()
    app.run()