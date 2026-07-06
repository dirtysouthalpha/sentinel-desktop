# Sentinel Desktop v25.0.0

AI-powered desktop automation assistant with vision-based agent loop, multi-provider LLM support, self-healing intelligence, and enterprise features.

## Architecture

Sentinel Desktop uses a **vision-based agent loop**: screenshot → LLM reasoning → action execution → repeat.

| Subsystem | Module | Description |
|-----------|--------|-------------|
| **Agent Engine** | `core/engine.py` | LLM-driven agent with vision, tool-calling, self-healing, forensic logging |
| **LLM Client** | `core/llm_client.py` | 16+ providers (OpenAI, Anthropic, Google, local, etc.) |
| **Platform Layer** | `core/platform/` | Cross-platform abstraction (Windows, macOS, Linux, headless) |
| **Action Executor** | `core/action_executor.py` | Mouse, keyboard, UIA, stealth input |
| **Self-Healing** | `core/healing/` | Diff detection, retry planning, vision grounding |
| **Memory** | `core/memory/` | Short-term and long-term agent memory |
| **Remote Fleet** | `core/remote/` | SSH tunneling, remote installation, fleet management |
| **Web Automation** | `core/web/` | Browser control, recording, replay |
| **Server** | `api/server.py` | FastAPI headless API with WebSocket live feed |
| **Security** | `core/auth.py`, `core/encryption.py` | RBAC, bcrypt auth, DPAPI credential vault |
| **Auto-Update** | `core/updater.py` | GitHub release checker |
| **GUI** | `gui/app.py` | CustomTkinter dark-themed desktop UI |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Launch GUI
python main.py

# CLI mode
python main.py --cli

# Headless API server
python main.py --api --port 8091

# Check version
python main.py --version
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/goal` | POST | Start agent with a natural language goal |
| `/command` | POST | Execute a single desktop command |
| `/status` | GET | Check agent status |
| `/health` | GET | System health (CPU, memory, engine status) |
| `/update-check` | GET | Check for newer versions on GitHub |
| `/screenshot` | GET | Capture current screen |
| `/config` | GET/PUT | Read/update configuration |
| `/ws` | WS | WebSocket live status feed |

## Security

- **Auth**: Optional shared-secret via `SENTINEL_API_TOKEN` env var
- **Rate Limiting**: 60 req/min per IP
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection
- **Credential Vault**: DPAPI encryption on Windows, base64 fallback elsewhere
- **RBAC**: Viewer, Operator, Admin roles with bcrypt password hashing

## Testing

```bash
python -m pytest tests/ -q
```

## License

MIT
