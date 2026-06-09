# Sentinel Desktop — Ship History

Project milestones and their release dates.

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

*To be added...*
