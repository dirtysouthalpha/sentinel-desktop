# Sentinel Desktop — AI-Powered Cross-Platform Desktop Automation

Vision-driven desktop automation agent. Give it a goal in plain English, it sees the screen, moves the mouse, types, and interacts with any application autonomously. Used daily by an IT Support Technician. **v20.0 "Penguin": Linux desktop parity — window management and stealth input routed through `core/platform/` backend on Linux/macOS, xdotool-based click/type, 18 new cross-platform parity tests. See `docs/ROADMAP-v18-to-v22.md` for the v21–v22 plan (Operator/Voice).**

## What To Do (Priority Order)
**v20 Penguin complete — Linux desktop parity production-ready ✅**

All quality gates met:
- ✅ 8,411 tests passing (152 skipped)
- ✅ Zero lint errors (ruff check clean)
- ✅ window_manager: list_windows, focus_window, close_window, get_focused_window_rect routed through LinuxWindowBackend
- ✅ stealth_input: post_click, post_text routed through LinuxStealthInputBackend; is_available() detects xdotool
- ✅ 18 new cross-platform parity tests (`tests/test_platform_parity.py`) — mocked backends, run on any OS

> **Next:** v21 Operator — eval harness, cost dashboard, skill marketplace.
> See `docs/ROADMAP-v18-to-v22.md`.

**Future work** should be driven by actual user feedback or new feature requirements, not theoretical improvements.

## Commands
- Test: `python -m pytest tests/ -q`
- Lint: `ruff check core/ gui/ api/`
- Run GUI: `python main.py`
- Run API: `python main.py --api --port 8091`

## Architecture
- **core/platform/** — Cross-platform abstraction layer (v4.0): base interfaces + Windows/Linux/macOS backends
  - `base.py` — Abstract base classes (Accessibility, StealthInput, Credentials, Shell, Window, Overlay)
  - `windows_backend.py` — UIA, PostMessage, DPAPI, PowerShell, win32gui
  - `linux_backend.py` — AT-SPI, xdotool, libsecret, bash, wnck
  - `macos_backend.py` — NSAccessibility, AppleScript, Keychain, zsh
- **core/** — Core engine (45 modules): agent loop, LLM client, screenshot, OCR, UIAutomation, actions, scheduler, workflows
- **core/web/** — Web automation subpackage (v8.0): dual-mode detection, cert whitelist, login detector, session vault, web recorder
- **core/browser.py** — Playwright browser manager with 11 web actions (web_open, web_click, web_type, web_read, web_extract, web_wait_for, web_screenshot, web_eval_js, web_download, web_upload, web_tabs)
- **core/netops/** — SSH/network device control (v9.0): SSH client, command runner, output parser (Cisco/Juniper/FortiGate/MikroTik)
- **core/server/** — Fleet/daemon mode (v10.0): daemon service, fleet manager, persistent job queue
- **core/memory/** — Persistent memory (v11.0): episodic (JSONL), semantic (SQLite), working memory (in-memory scratchpad)
- **core/conductor/** — Multi-agent orchestration (v12.0): task planner, parallel executor, result synthesizer, coordinator
- **gui/** — Cyberpunk HUD GUI with tkinter (13 modules): app, cursor overlay, themes, tabs, system tray
- **api/** — FastAPI headless server (35+ endpoints, PTY terminal Unix-only)
- **plugins/** — Plugin system
- **scripts/** — Pre-built IT support scripts (JSON templates)
- **tests/** — pytest suite with 200+ test files including platform tests
- Multi-provider LLM support (20+ providers including OpenAI, Anthropic, Google, xAI, Z.ai GLM-5)

## v8.0 — Webhand (June 2026)
- ✅ Embedded Playwright browser control (Chromium/Firefox/WebKit)
- ✅ 11 web actions: web_open, web_click, web_type, web_read, web_extract, web_wait_for, web_screenshot, web_eval_js, web_download, web_upload, web_tabs
- ✅ Pydantic schemas for all web actions with validation
- ✅ Dual-mode detection (web vs native) with mode handoff
- ✅ Self-signed certificate whitelist for IT appliances
- ✅ IT appliance login page detection (10 vendors: SonicWall, FortiGate, UniFi, Meraki, pfSense, OPNsense, MikroTik, NinjaOne, ConnectWise, IT Glue)
- ✅ Session vault — encrypted cookie persistence and restore
- ✅ Web recorder — capture browser actions as replayable JSON scripts
- ✅ 325 new tests, 5,662 total passing

## v9.0 — Netops (June 2026)
- ✅ SSH client via paramiko with connect/disconnect/run_command/context manager
- ✅ Device-aware command runner (Cisco IOS/NX-OS, Juniper JunOS, FortiGate, MikroTik, pfSense, Linux)
- ✅ Output parser for interfaces, ARP, routing, ping, version, IPs, MACs
- ✅ 5 executor actions: ssh_connect, ssh_disconnect, ssh_run, ssh_show, ssh_ping
- ✅ Pydantic schemas + tool schemas + system prompt for all SSH actions

## v10.0 — Sentinel Server (June 2026)
- ✅ Daemon service manager (start/stop/heartbeat/job tracking)
- ✅ Fleet manager (register/unregister/heartbeat/nodes)
- ✅ Persistent job queue (submit/claim/complete/fail/cancel with priority ordering)
- ✅ 14 new API endpoints (/daemon/*, /fleet/*, /jobs/*)

## v11.0 — Memory (June 2026)
- ✅ Episodic memory — timestamped JSONL with search, compression of old episodes
- ✅ Semantic memory — SQLite key-value facts with categories, tags, access tracking
- ✅ Working memory — in-memory session scratchpad with key-value and bucket stores

## v12.0 — Conductor (June 2026)
- ✅ Task planner — rule-based goal decomposition with dependency detection
- ✅ Parallel executor — concurrent subtask execution respecting dependencies
- ✅ Result synthesizer — merge multi-agent results with status aggregation
- ✅ Conductor coordinator — end-to-end plan → execute → synthesize pipeline
- ✅ 606 new tests across v8-v12

## v13.0 — Sentinel-Plus (June 2026)
- ✅ MFA Detector — 4 detection strategies (keyword, DOM attributes, page structure, patterns)
- ✅ MFA Handler — 3 handling approaches (TOTP auto-generation, user prompt, SMS/Email retrieval)
- ✅ Browser integration — detect_mfa() and handle_mfa() methods
- ✅ Action executor integration — mfa_detect and mfa_handle actions
- ✅ TOTP provider supporting 9 authenticator apps (Google, Authy, Microsoft, etc.)
- ✅ Service name extraction from URLs for automatic TOTP lookup
- ✅ Code caching with TTL (5 min) to avoid regenerating codes
- ✅ 81 comprehensive MFA tests with full coverage
- ✅ Added pyotp ~= 2.9 dependency

## v14.0 — Resilience Engine (June 2026)
- ✅ `@retryable` decorator — exponential backoff with jitter, configurable exceptions, on_retry hook
- ✅ `CircuitBreaker` — CLOSED/OPEN/HALF_OPEN state machine, context-manager interface
- ✅ `RetryExhausted` / `CircuitBreakerOpen` typed exceptions
- ✅ Pre-wired breakers for: ssh, browser, ocr, llm, desktop, netops
- ✅ `get_all_breaker_stats()` / `reset_all_breakers()` for monitoring
- ✅ `retry_last` and `get_circuit_breakers` executor actions + tool schemas
- ✅ 30+ tests in `tests/test_resilience.py`

## v15.0 — Config Persistence + DNS Tools (June 2026)
- ✅ `ConfigStore` — dot-notation JSON persistence (`llm.provider`, `llm.model`, etc.)
- ✅ Process-wide singleton via `get_default_store()`
- ✅ `dns_lookup` — A/AAAA/MX/PTR/TXT via socket + dnspython fallback
- ✅ `ping_host` — subprocess ping with Windows/Unix output parsing
- ✅ `port_open` / `scan_ports` — TCP reachability checks
- ✅ `traceroute` — hop-by-hop path tracing
- ✅ `config_get`, `config_set`, `dns_lookup`, `ping`, `port_scan` executor actions
- ✅ Tests: `tests/test_config_store.py`, `tests/test_net_tools.py`

## v16.0 — Window Control, HTTP Client, File Monitor (June 2026)
- ✅ Window management: `resize_window`, `move_window`, `minimize_window`, `maximize_window`, `restore_window`, `get_window_state`, `get_monitors`
- ✅ HTTP client: `http_get`, `http_post`, `http_put`, `http_delete`, `http_download` (SSRF protection, 50k body cap)
- ✅ File/process watcher: `watch_file` (modify/create/delete), `watch_file_content` (log tailing), `watch_process` (start/stop/cpu_spike)
- ✅ All wired into executor dispatch table + tool schemas
- ✅ Tests: `tests/test_window_control.py`, `tests/test_http_client.py`, `tests/test_file_watcher.py`

## v17.0 — Audio/Voice (June 2026)
- ✅ TTS via Windows SAPI `SpVoice` (no new deps — uses pywin32) + PowerShell fallback
- ✅ STT via SAPI dictation grammar + SpeechRecognition library fallback
- ✅ `speak(text, blocking, rate, volume)` — rate clamped ±10, volume clamped 0–100
- ✅ `listen(timeout, phrase_limit)` — returns transcribed text
- ✅ `volume_get()` / `volume_set(level)` — pycaw (optional) + PowerShell fallback
- ✅ `mute_toggle()` — Windows audio endpoint mute
- ✅ `list_voices()` / `set_voice(name_or_id)` — enumerate and select SAPI voices
- ✅ Thread-safe `_tts_voice` cached instance
- ✅ `speak`, `listen`, `volume_get`, `volume_set`, `mute_toggle`, `list_voices` executor actions
- ✅ Tests: `tests/test_audio.py`

## v18.0 — Neuralis Brain Bridge (June 2026)
- ✅ HTTP bridge to Neuralis brain API (`core/brain/bridge.py`)
- ✅ Brain executor actions: `brain_recall`, `brain_think`, `brain_fire`, `brain_search`, `brain_context`
- ✅ GUI Brain tab — fleet-memory HUD panel in the cyberpunk interface
- ✅ Tests: `tests/test_brain_bridge.py`, `tests/test_brain_tab.py`

## v19.0 — Fortress (June 2026)
- ✅ HS256 JWT auth layer (`core/jwt_auth.py`) — stdlib-only, no new deps; token issue/verify/revoke
- ✅ OIDC id_token validation (`core/oidc.py`) — RS256/ES256, JWKS discovery, user auto-provisioning
- ✅ JWT wired into AuthManager + API server — Bearer token middleware, `/auth/token` endpoint
- ✅ Declarative policy guardrails (`core/policy.py`) — allow/deny rules over actions, endpoints, file paths
- ✅ Tamper-evident audit chain (`core/audit_chain.py`) — append-only, SHA-256 hash-chained log entries
- ✅ Audit export (`core/audit_export.py`) — JSON, CSV, HTML report generation with filtering
- ✅ Secrets vault broker (`core/secrets.py`) — OS keychain + encrypted vault.json fallback
- ✅ MDM deployment toolkit (`installer/mdm.py`) — Intune configuration profile + ADMX/ADML Group Policy templates
- ✅ 246 new tests; 8,393 total passing

## v20.0 — Penguin: Linux Desktop Parity (June 2026)
- ✅ `core/window_manager.py` — `list_windows`, `focus_window`, `close_window`, `get_focused_window_rect`, `_get_foreground_window_info` route through `LinuxWindowBackend` on Linux/macOS
- ✅ `_window_info_to_dict()` helper converts platform `WindowInfo` namedtuple to internal dict
- ✅ `core/stealth_input.py` — `post_click`, `post_text` route through `LinuxStealthInputBackend` when win32 unavailable; `is_available()` returns True when xdotool present on Linux
- ✅ 18 new cross-platform parity tests (`tests/test_platform_parity.py`) — all mocked, run on any OS
- ✅ 8,411 total tests passing

## v19.5 — Portable Build (June 2026)
- ✅ `core/paths.py` — `is_portable()` / `data_dir()` single source of truth; activates on `portable_data/` marker or `SENTINEL_PORTABLE=1`
- ✅ `installer/build.py` — `build_portable()` target: `--onedir` PyInstaller bundle, no installer/registry writes, USB-portable
- ✅ Embedded profile: selected `profiles/<name>/` directory bundled via `--add-data`; `portable_data/` marker created post-build
- ✅ Tesseract bundling: `_find_tesseract_binary()` + `_find_tessdata_eng()`; graceful degrade when not found
- ✅ Portable OCR: `_resolve_portable_tesseract()` in `core/utils.py`; injects bundled path + `TESSDATA_PREFIX` at runtime
- ✅ `core/profile.py` — `load_profile()`, `adopt_profile()`, `detect_profile()`, `needs_api_key()` helpers
- ✅ First-run API key prompt: `_portable_startup()` in `main.py` detects profile, adopts it, prompts for redacted key; headless mode reads `SENTINEL_API_KEY` env var
- ✅ `--profile` CLI arg added to `parse_args()`
- ✅ Tests: `tests/test_paths.py`, `tests/test_build_portable.py`, `tests/test_ocr_portable.py`, `tests/test_portable_startup.py`, `tests/test_profile.py`

## v4.0 — Multi-Platform Core (June 2025)
- ✅ Platform abstraction layer (`core/platform/`) with ABC interfaces for all OS-specific code
- ✅ Windows backend (UIA, PostMessage, DPAPI, PowerShell, win32gui overlays)
- ✅ Linux backend (AT-SPI accessibility, xdotool input, libsecret credentials, bash shell, wnck windows)
- ✅ macOS backend (AppleScript accessibility, osascript input, Keychain credentials, zsh shell)
- ✅ Thread-safe screenshot and UI tree caches (threading.Lock added to all shared dicts)
- ✅ OCR resolution caps raised from 1920x1080 → 3840x2160 (4K display support)
- ✅ Engine system prompt no longer hardcodes "Windows desktop"
- ✅ Subprocess command sanitization (blocks injection patterns and shell metacharacters)
- ✅ Terminal WebSocket cross-platform (dynamic shell discovery, Windows graceful degrade)
- ✅ Encryption cross-platform fallback (XOR with machine-specific key, not just base64)
- ✅ Image history raised from 3 → 5 screenshots in context
- ✅ 48 new platform abstraction tests

## Completed Features (May–June 2026)
- ✅ Popup handler — automatic dialog detection and dismissal (57 tests)
- ✅ Workflow builder API endpoints and system dashboard router
- ✅ System dashboard with CPU/memory/disk/GPU metrics
- ✅ Mouse action enhancements (mouse_move, double_click, right_click, retry_last_action)
- ✅ Scheduler overlap protection
- ✅ /health endpoint
- ✅ Agent pool cleanup
- ✅ All 21 previously failing tests fixed
- ✅ Cross-platform test compatibility (Win32 ctypes skips, Linux, Python 3.14 asyncio)
- ✅ Ruff lint/format pass across entire codebase
- ✅ 69 docstrings added to public functions
- ✅ Bare exception clauses narrowed in action_executor
- ✅ MFA support for web automation — TOTP, SMS/Email handling (81 tests)

## Code Standards
- Python 3.10+ with type hints on all public functions
- Google-style docstrings
- 4-space indentation
- ruff for linting
- pytest for testing

## Critical Rules
- NEVER break existing tests. If a test fails after your change, fix it.
- NEVER add pip dependencies without a compelling reason.
- Commit early, commit often. Small focused commits > big messy ones.
- Push after every commit so progress isn't lost.
- If you hit a wall, skip and move to the next task.
- Safety is paramount — this tool controls the desktop. Always maintain the approval gate and failsafe (Esc-x3 panic stop).
