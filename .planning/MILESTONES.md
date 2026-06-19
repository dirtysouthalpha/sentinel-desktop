# Sentinel Desktop — Ship History

Project milestones and their release dates.

## v18.0.0 — Foundation (2026-06-19)

A reconciliation major version: no new capability, but closes the gap between the project's
claims and reality.

**Shipped:**
- Version & docs sync: `core.__version__` → 18.0.0; FastAPI app sources `title`/`version`
  from `core.__version__` (was hardcoded "3.1.0"); `CHANGELOG.md` backfilled for v7–v17;
  README test count reconciled (7,882); new `docs/ROADMAP-v18-to-v22.md`.
- Dependency unification: `pyproject.toml` is the single source; new extras `[web]`,
  `[netops]`, `[voice]`, `[mcp]`, `[net]`, `[mfa]`, `[all]`; `requirements.txt` → pointer.
- Breaking changes (deprecation removal): dropped `LLMClient.chat_with_screenshot()`,
  async `ActionExecutor.execute()`, legacy SHA-256 auth path, `gui/tray.py` (migrated to
  `gui/system_tray.SystemTrayIcon`); removed `S324` ruff per-file ignore.
- Structural: new `core/action_registry.py` (`@register_action`) and `api/routes.py`
  (`@api_route`) registry patterns replace the 110-entry dispatch dict literal and the
  imperative `_register_*_routes` calls. No file splitting.
- Release pipeline: first real `v18.0.0` git tag; `release.yml` (PyPI Trusted Publishing)
  exercised end-to-end.
- Phantom v13–v17 feature claims removed from docs.

## v17.0 — Audio/Voice (June 2026)

**Shipped:**
- TTS via Windows SAPI `SpVoice` + PowerShell fallback; STT via SAPI dictation +
  SpeechRecognition fallback; volume_get/set, mute_toggle, list_voices, speak, listen.
- pycaw (optional) for volume control; thread-safe cached `_tts_voice`.

## v16.0 — Window Control, HTTP Client, File Monitor (June 2026)

**Shipped:**
- Window management: resize/move/minimize/maximize/restore_window, get_window_state,
  get_monitors.
- HTTP client: http_get/post/put/delete/download with SSRF protection and 50k body cap.
- File/process watcher: watch_file, watch_file_content, watch_process.

## v15.0 — Config Persistence + DNS Tools (June 2026)

**Shipped:**
- `ConfigStore` dot-notation JSON persistence + process-wide singleton.
- Network diagnostics: dns_lookup, ping, port_scan, traceroute.

## v14.0 — Resilience Engine (June 2026)

**Shipped:**
- `@retryable` decorator (exponential backoff + jitter) and `CircuitBreaker` state machine.
- Pre-wired breakers for ssh/browser/ocr/llm/desktop/netops; retry_last,
  get_circuit_breakers actions.

## v13.0 — Sentinel-Plus: MFA (June 2026)

**Shipped:**
- MFA Detector (4 strategies) and MFA Handler (TOTP/user-prompt/SMS-Email).
- TOTP provider supporting 9 authenticator apps; service-name extraction; 5-min code cache.
- mfa_detect, mfa_handle actions; added `pyotp ~= 2.9`.

## v7.0.0 — Perception: Grounding Revolution (2026-06-06)

**Shipped:**
- Phase 1: DPI & coordinate calibration (per-monitor scaling, HiDPI transform, calibration persistence)
- Phase 2: Hybrid grounding pipeline (a11y-first element map, ID-based targeting, vision fallback)
- Phase 3: Set-of-Marks screenshots (numbered bounding boxes, multi-source fusion, CV contour detection)
- Phase 4: Native computer-use adapters (Anthropic computer_20250124, OpenAI computer-use-preview, JSON fallback)
- Phase 5: Click verification & self-correction (post-action diff, tiered retry, enforced self-healing)
- Phase 6: Local grounding model (optional, feature-flagged, OmniParser/Florence-2/YOLO interface)
- 179 new tests across 6 test files
- Full suite: 5,337 tests passing, 0 failures

## v6.0.0 — Dependency Upgrades + Cleanup (2026-06-06)

**Shipped:**
- 11 dependency version bumps (fastapi, uvicorn, pydantic, websockets, httpx, bcrypt, pytest, ruff, mypy, pytest-asyncio, pytest-cov)
- 36 lint errors fixed (zero remaining)
- 12 test files fixed for Windows/Python 3.13 compatibility
- Version bumped to 6.0.0

## v3.1.0 — Production Foundation (2026-06-04)

**Shipped:**
- Critical GUI fixes (themes, approval mode)
- LLM retry/backoff and bounded conversation context
- 8 new LLM providers (MiniMax, Moonshot/Kimi, Qwen, Cohere, NVIDIA NIM, HuggingFace, GitHub Models, DeepInfra)
- OCR-backed `click_text` and `read_text` actions
- Windows UIAutomation integration
- Action overlay for visual feedback
- Pre-action callback hook for GUI integration
- Dry-run mode
- Esc-x3 failsafe
- Multi-monitor screenshot support
- Native tool/function calling
- WebSocket live feed
- API authentication
- Workflow builder CRUD API
- System dashboard with CPU/memory/disk/GPU metrics
- Popup handler (57 tests)
- Recovery engine expansion
- Test suite expansion (83 new tests)
- Docstrings and code quality improvements

## v12.0 — Conductor: Multi-Agent Orchestration (2026-06-07)

**Shipped:**
- Task planner — rule-based goal decomposition with dependency detection
- Parallel executor — concurrent subtask execution respecting dependencies
- Result synthesizer — merge multi-agent results with status aggregation
- Conductor coordinator — end-to-end plan → execute → synthesize pipeline
- conductor_run agent action with async→sync bridge
- Pydantic schema, executor handler, tool schema for LLM tool calling
- 8 requirements (CON-01–08)

## v11.0 — Memory: Persistent Agent Memory (2026-06-07)

**Shipped:**
- Episodic memory — timestamped JSONL with search, compression of old episodes
- Semantic memory — SQLite key-value facts with categories, tags, access tracking
- Working memory — in-memory session scratchpad with key-value and bucket stores
- 4 agent actions: memory_store, memory_recall, memory_search, memory_forget
- Pydantic schemas, executor handlers, tool schemas for all memory actions
- End-to-end integration tests (store → recall → search → forget)
- 10 requirements (MEM-01–10)

## v10.0 — Sentinel Server: Fleet/Daemon Mode (2026-06-07)

**Shipped:**
- Daemon service manager (start/stop/heartbeat/job tracking)
- Fleet manager (register/unregister/heartbeat/nodes)
- Persistent job queue (submit/claim/complete/fail/cancel with priority)
- 14 API endpoints (/daemon/*, /fleet/*, /jobs/*)
- 6 requirements (SRV-01–06)

## v9.0 — Netops: SSH Network Device Control (2026-06-07)

**Shipped:**
- SSH client via paramiko (connect, run_command, context manager)
- Device-aware command runner (Cisco IOS/NX-OS, Juniper JunOS, FortiGate, SonicWall, MikroTik, pfSense, Linux)
- Output parser for interfaces, ARP, routing, ping, version, IPs, MACs
- 5 executor actions: ssh_connect, ssh_disconnect, ssh_run, ssh_show, ssh_ping
- Pydantic schemas + tool schemas + system prompt for all SSH actions
- 54 tests (ssh_client, output_parser, executor dispatch)
- 11 requirements (NET-01–11)

## v8.0.0 — Webhand: Browser Automation (2026-06-06)

**Shipped:**
- Embedded Playwright browser control (Chromium/Firefox/WebKit)
- 11 web actions: web_open, web_click, web_type, web_read, web_extract, web_wait_for, web_screenshot, web_eval_js, web_download, web_upload, web_tabs
- Dual-mode detection (web vs native) with mode handoff
- Self-signed certificate whitelist for IT appliances
- IT appliance login page detection (10 vendors)
- Session vault — encrypted cookie persistence and restore
- Web recorder — capture browser actions as replayable JSON scripts
- 325 new tests, 5,662 total passing
- 19 requirements

## Future Milestones

v18 reconciled the project with its claims and laid the foundation. The next four themed
versions are scheduled in `docs/ROADMAP-v18-to-v22.md`:

- **v19 — Fortress** (enterprise security): SSO/OIDC, declarative policy guardrails,
  secrets vault, tamper-evident audit logs, MDM deployment.
- **v20 — Penguin** (real Linux desktop parity): route scattered `win32` imports through
  `core/platform/`, AT-SPI on Linux, Wayland support, cross-platform parity test matrix.
  Pairs naturally with a Docker management action group.
- **v21 — Operator** (eval harness + skill marketplace): `eval/` simulation/scoring
  harness, cost dashboard, skill/profile marketplace, long-horizon autonomy. Pairs
  naturally with goal-learning actions.
- **v22 — Voice** (ambient / proactive): wake words, ambient monitoring, event triggers,
  full `core/voice.py` built on the v17 `core/audio.py` foundation.

Each returns as a real, tested feature. The v13–v17 phantom-feature claims (Docker
management, tray/desktop-control actions, goal-learning, loguru, `dns_leak_test`,
working-memory actions) were removed from docs in v18 and will reappear here as they
become real.
