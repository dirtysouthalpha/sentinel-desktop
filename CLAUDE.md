# Sentinel Desktop — AI-Powered Cross-Platform Desktop Automation

Vision-driven desktop automation agent. Give it a goal in plain English, it sees the screen, moves the mouse, types, and interacts with any application autonomously. Used daily by an IT Support Technician. **v13.0: Sentinel-Plus — MFA support, enhanced web automation, multi-factor authentication handling.**

## What To Do (Priority Order)
**All priorities complete - project is production-ready ✅**

All quality gates met:
- ✅ 5,947 tests passing (147 skipped)
- ✅ Zero lint errors (ruff check clean)
- ✅ 89-94% test coverage (well above ≥80% target: 89% core/gui/api, 94% overall)
- ✅ All API endpoints fully implemented (workflow builder complete)
- ✅ All 19 IT support scripts validated and tested
- ✅ Edge cases covered (popup handler 57 tests, scheduler overlap protection, recovery engine, LLM client)
- ✅ Performance optimized (OCR caching, screenshot downsampling, async operations with timeouts)
- ✅ Documentation complete (docstrings on all public functions, module headers)
- ✅ Code quality excellent (proper exception handling, no functions over 50 lines needing refactor)

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
