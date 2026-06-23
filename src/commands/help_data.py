"""Help text data for Sentinel Desktop."""

HELP_TEXT = """
Sentinel Desktop v5.0.0 - Available Commands
============================================

System Monitoring:
  cpu                    - Show CPU usage
  memory                 - Show memory usage
  disk                   - Show disk usage
  processes              - List running processes
  system info            - Show system information
  battery                - Show battery status
  temperature            - Show CPU temperature
  uptime                 - Show system uptime

Power Management:
  shutdown [seconds]     - Shutdown the system
  restart [seconds]      - Restart the system
  sleep                  - Put system to sleep
  lock screen            - Lock the screen
  cancel shutdown        - Cancel pending shutdown

Automation:
  click x,y              - Click at coordinates
  right-click x,y        - Right-click at coordinates
  type text              - Type text
  press key              - Press a key
  move x,y               - Move mouse
  scroll direction       - Scroll up/down
  drag x1,y1 x2,y2      - Drag from point to point
  screenshot             - Take a screenshot

Network:
  ping host              - Ping a host
  ipconfig               - Show IP configuration
  network diagnostics    - Run network diagnostics
  speedtest              - Run internet speed test

Process Management:
  open appname           - Open an application
  kill processname       - Kill a process

File Operations:
  list path              - List directory contents
  find filename          - Search for files
  read filepath          - Read file contents

Clipboard:
  copy text              - Copy text to clipboard
  paste                  - Read from clipboard

Window Management:
  list windows           - List open windows

Media Controls:
  volume up              - Increase volume
  volume down            - Decrease volume
  mute                   - Toggle mute
  play/pause             - Toggle media playback
  next track             - Next media track
  previous track         - Previous media track

Notifications:
  notify title message   - Send a notification
  alert message          - Send an alert
  remind message         - Send a reminder

Scheduler:
  timer seconds [label]  - Set a countdown timer
  list timers            - List active timers
  cancel timer id        - Cancel a timer

Voice:
  speak text             - Text-to-speech
  listen                 - Listen for voice input
  voice status           - Show voice engine status

Macros:
  start recording        - Begin macro recording
  stop recording         - Stop recording
  save macro name        - Save recorded macro
  load macro name        - Load a saved macro
  list macros            - List saved macros
  delete macro name      - Delete a macro

Plugins:
  list plugins           - List available plugins
  load plugin name       - Load a plugin

Brain AI:
  brain status           - Check brain status
  recall topic           - Recall knowledge
  think topic content    - Store knowledge

Type 'help' or '?' to see this list again.
"""
