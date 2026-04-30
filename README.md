# Sentinel Desktop - PC Assistant

A Claude-like AI assistant for Windows desktop automation with accurate mouse/keyboard control.

## Features

- **Mouse Control**: Click at coordinates, move mouse, take screenshots
- **Keyboard Automation**: Type text, press keys, special commands
- **System Monitoring**: CPU, memory, disk usage, process list
- **Application Control**: Open/close applications by name
- **Networking Tools**: Ping, IP config, network diagnostics
- **MSP Troubleshooting**: Services, connectivity checks

## Installation

### Windows
```bash
# Run the installer
install_and_run.bat
```

### Manual Installation
```bash
pip install -r requirements.txt
python main.py
```

## Requirements
- Python 3.8+
- Windows OS (designed for Windows)

## Usage

Type commands in the chat interface:

### Mouse Control
- `click at 500,300` - Click at specific coordinates
- `move to 100,200` - Move mouse to position
- `position` - Show current mouse position
- `screenshot` - Take a screenshot

### Keyboard
- `type hello world` - Type text
- `press enter` - Press Enter key
- `press ctrl+c` - Press key combination

### System Info
- `cpu` - Show CPU usage
- `memory` - Show RAM usage
- `disk` - Show disk usage
- `processes` - List top processes

### Applications
- `open chrome` - Launch application
- `close notepad` - Close application

### Networking
- `ping google.com` - Ping a host
- `ip` - Show IP configuration
- `network` - Run network diagnostics

## Project Structure
```
sentinel-desktop/
├── main.py              # Main application
├── requirements.txt     # Python dependencies
├── install_and_run.bat  # Windows installer
└── README.md           # This file
```

## License
MIT License