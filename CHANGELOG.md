# Changelog

## [18.0.0] — "Foundation" (reconciliation)

A reconciliation major version: closes the gap between what the project *claims* and what it *ships*. No new user-facing capability; this version pays down process and structural debt so v19+ (Fortress, Penguin, Operator, Voice) can land cleanly.

### Version & docs sync
- `core.__version__` → `18.0.0`; the FastAPI app now sources its `title`/`version` from `core.__version__` instead of the stale hardcoded `"3.1.0"` (unbumped since v3.1.0 across 14 major versions).
- `CHANGELOG.md` backfilled for v7–v17 (previously stopped at v6.0.0).
- README test count reconciled to reality (7,882 collected; the previous `5,244` was stale and the badge `7,823` was slightly off).
- New `docs/ROADMAP-v18-to-v22.md` names the next four themed versions.
- `.planning/` updated to reflect v18.

### Dependency unification (manifests no longer diverge)
- `pyproject.toml` is now the single source of truth; the previously-undeclared imports are exposed as extras: `[web]` (playwright), `[netops]` (paramiko), `[voice]` (SpeechRecognition, pyaudio, pycaw), `[mcp]` (fastmcp), `[net]` (dnspython), `[mfa]` (pyotp). `[all]` aggregates them.
- `requirements.txt` reduced to a `-e .[all]` pointer.
- `pip install sentinel-desktop[all]` now actually delivers the SSH, browser, MCP, and voice features that were advertised but silently uninstalled.

### Breaking changes (deprecation removal — justifies the major bump)
- **Removed** `LLMClient.chat_with_screenshot()` (`core/llm_client.py`) — deprecated since v3.1.0, zero callers.
- **Removed** async `ActionExecutor.execute()` (`core/action_executor.py`) — deprecated since v3.1.0; the engine loop uses `execute_sync()`. Callers updated.
- **Removed** the legacy SHA-256 password verification path (`core/auth.py`) along with the `S324` ruff per-file ignore it required. **Migration:** users whose stored hash is still pre-bcrypt SHA-256 must reset their password on first login under v18.
- **Removed** `gui/tray.py` (deprecated since v3.1.0); the GUI migrated to `gui/system_tray.SystemTrayIcon`, which provides status colours, IT quick actions, and a fuller menu.

### Structural
- New `core/action_registry.py`: `@register_action(name, aliases=[...])` decorator + `ActionRegistry` replaces the 110-entry `_dispatch_table` dict literal in `action_executor.py`. Future versions add actions without editing a monolithic table.
- New `api/routes.py`: `@api_route(method, path)` decorator evolving the imperative `_register_*_routes` methods into a collected registry wired at app-build time.
- Files are *not* physically split — only the extension seam is introduced.

### Release pipeline
- The first real `v18.0.0` git tag was created and pushed. No tag had ever existed before; the tag-driven `release.yml` (PyPI Trusted Publishing) is now exercised end-to-end.

### Phantom-feature reconciliation
- Removed from docs the v13–v17 feature claims that were never built (Docker management, tray/desktop-control actions, goal-learning, loguru, `dns_leak_test`, working-memory actions). They return as real, tested features in v19–v22.

## [17.0] — Audio/Voice (June 2026)

### Audio
- TTS via Windows SAPI `SpVoice` (pywin32, no new deps) + PowerShell fallback.
- STT via SAPI dictation grammar + SpeechRecognition library fallback.
- `speak(text, blocking, rate, volume)` — rate clamped ±10, volume clamped 0–100.
- `listen(timeout, phrase_limit)` — returns transcribed text.
- `volume_get()` / `volume_set(level)` — pycaw (optional) + PowerShell fallback.
- `mute_toggle()` — Windows audio endpoint mute.
- `list_voices()` / `set_voice(name_or_id)` — enumerate and select SAPI voices.
- Thread-safe `_tts_voice` cached instance.
- Actions: `speak`, `listen`, `volume_get`, `volume_set`, `mute_toggle`, `list_voices`.

## [16.0] — Window Control, HTTP Client, File Monitor (June 2026)

### Window management
- `resize_window`, `move_window`, `minimize_window`, `maximize_window`, `restore_window`, `get_window_state`, `get_monitors`.

### HTTP client
- `http_get`, `http_post`, `http_put`, `http_delete`, `http_download` with SSRF protection and a 50k body cap.

### File/process watcher
- `watch_file` (modify/create/delete), `watch_file_content` (log tailing), `watch_process` (start/stop/cpu_spike).
- All wired into executor dispatch table + tool schemas.

## [15.0] — Config Persistence + DNS Tools (June 2026)

### Config persistence
- `ConfigStore` — dot-notation JSON persistence (`llm.provider`, `llm.model`, etc.); process-wide singleton via `get_default_store()`.

### Network diagnostics
- `dns_lookup` — A/AAAA/MX/PTR/TXT via socket + dnspython fallback.
- `ping_host` — subprocess ping with Windows/Unix output parsing.
- `port_open` / `scan_ports` — TCP reachability checks.
- `traceroute` — hop-by-hop path tracing.
- Actions: `config_get`, `config_set`, `dns_lookup`, `ping`, `port_scan`.

## [14.0] — Resilience Engine (June 2026)

- `@retryable` decorator — exponential backoff with jitter, configurable exceptions, `on_retry` hook.
- `CircuitBreaker` — CLOSED/OPEN/HALF_OPEN state machine, context-manager interface.
- `RetryExhausted` / `CircuitBreakerOpen` typed exceptions.
- Pre-wired breakers for: ssh, browser, ocr, llm, desktop, netops.
- `get_all_breaker_stats()` / `reset_all_breakers()` for monitoring.
- Actions: `retry_last`, `get_circuit_breakers`.

## [13.0] — Sentinel-Plus: MFA (June 2026)

- MFA Detector — 4 strategies (keyword, DOM attributes, page structure, patterns).
- MFA Handler — 3 approaches (TOTP auto-generation, user prompt, SMS/Email retrieval).
- Browser integration — `detect_mfa()` and `handle_mfa()` methods.
- TOTP provider supporting 9 authenticator apps (Google, Authy, Microsoft, etc.).
- Service name extraction from URLs for automatic TOTP lookup; code caching with 5-min TTL.
- Actions: `mfa_detect`, `mfa_handle`.
- Added `pyotp ~= 2.9` dependency.

## [12.0] — Conductor: Multi-Agent Orchestration (2026-06-07)

- Task planner — rule-based goal decomposition with dependency detection.
- Parallel executor — concurrent subtask execution respecting dependencies.
- Result synthesizer — merge multi-agent results with status aggregation.
- Conductor coordinator — end-to-end plan → execute → synthesize pipeline.
- Action: `conductor_run` (async→sync bridge), Pydantic schema, tool schema.

## [11.0] — Memory: Persistent Agent Memory (2026-06-07)

- Episodic memory — timestamped JSONL with search, compression of old episodes.
- Semantic memory — SQLite key-value facts with categories, tags, access tracking.
- Working memory — in-memory session scratchpad with key-value and bucket stores.
- Actions: `memory_store`, `memory_recall`, `memory_search`, `memory_forget`.

## [10.0] — Sentinel Server: Fleet/Daemon Mode (2026-06-07)

- Daemon service manager (start/stop/heartbeat/job tracking).
- Fleet manager (register/unregister/heartbeat/nodes).
- Persistent job queue (submit/claim/complete/fail/cancel with priority).
- 14 API endpoints (`/daemon/*`, `/fleet/*`, `/jobs/*`).

## [9.0] — Netops: SSH Network Device Control (2026-06-07)

- SSH client via paramiko (connect, run_command, context manager).
- Device-aware command runner (Cisco IOS/NX-OS, Juniper JunOS, FortiGate, SonicWall, MikroTik, pfSense, Linux).
- Output parser for interfaces, ARP, routing, ping, version, IPs, MACs.
- Actions: `ssh_connect`, `ssh_disconnect`, `ssh_run`, `ssh_show`, `ssh_ping`.

## [8.0.0] — Webhand: Browser Automation (2026-06-06)

- Embedded Playwright browser control (Chromium/Firefox/WebKit).
- 11 web actions: `web_open`, `web_click`, `web_type`, `web_read`, `web_extract`, `web_wait_for`, `web_screenshot`, `web_eval_js`, `web_download`, `web_upload`, `web_tabs`.
- Dual-mode detection (web vs native) with mode handoff.
- Self-signed certificate whitelist for IT appliances.
- IT appliance login page detection (10 vendors: SonicWall, FortiGate, UniFi, Meraki, pfSense, OPNsense, MikroTik, NinjaOne, ConnectWise, IT Glue).
- Session vault — encrypted cookie persistence and restore.
- Web recorder — capture browser actions as replayable JSON scripts.
- 325 new tests, 5,662 total passing.

## [7.0.0] — Perception: Grounding Revolution (2026-06-06)

- Phase 1: DPI & coordinate calibration (per-monitor scaling, HiDPI transform, calibration persistence).
- Phase 2: Hybrid grounding pipeline (a11y-first element map, ID-based targeting, vision fallback).
- Phase 3: Set-of-Marks screenshots (numbered bounding boxes, multi-source fusion, CV contour detection).
- Phase 4: Native computer-use adapters (Anthropic computer_20250124, OpenAI computer-use-preview, JSON fallback).
- Phase 5: Click verification & self-correction (post-action diff, tiered retry, enforced self-healing).
- Phase 6: Local grounding model (optional, feature-flagged, OmniParser/Florence-2/YOLO interface).
- 179 new tests; 5,337 total passing.

## [6.0.0] - 2026-06-05

### Dependency upgrades
- **fastapi** 0.110 → 0.136 (major performance and typing improvements)
- **uvicorn** 0.27 → 0.47 (HTTP/1.1 pipelining, improved websocket handling)
- **httpx** 0.27 → 0.28
- **pydantic** 2.5 → 2.13 (V2 mature, faster validation, better errors)
- **websockets** 12.0 → 16.0 (major rewrite, faster, better API)
- **bcrypt** 4.1 → 4.3
- **pytest** 8.0 → 8.4
- **pytest-asyncio** 0.23 → 0.26
- **pytest-cov** 4.1 → 7.1
- **ruff** 0.4 → 0.15 (massively faster, many new rules)
- **mypy** 1.8 → 2.1

### Lint fixes (36 errors → 0)
- Restructured `api/server.py` imports to fix E402 (Unix-only PTY modules now after all stdlib/third-party imports)
- Removed unused imports across `core/perception/`, `core/platform/`, `core/swarm/`
- Fixed undefined `PlanStepStatus` → `StepStatus` in `core/control/loop.py`
- Removed unused variables in `core/control/grounder.py` and `core/control/loop.py`
- Added `usedforsecurity=False` to non-cryptographic `md5` calls in `core/control/verifier.py` and `core/perception/pipeline.py`
- Added `strict=False` to `zip()` in `core/control/verifier.py`
- Fixed `OSError, IOError` tuple → `OSError` in `core/perception/annotator.py`
- Sorted import blocks across `core/control/`, `core/perception/`, `core/swarm/`

### Test fixes
- Fixed `test_it_scripts.py` — added `encoding="utf-8"` to JSON file reads (emoji characters in script templates)
- Fixed `test_launcher.py` — subprocess resolves `cmd` to full path on Windows/Python 3.13
- Fixed `test_notifications_gaps.py` — patch `ctypes.windll` on the actual `ctypes` module while calling `_show_box` thread target
- Fixed `test_ocr_gaps2.py` — updated resolution thresholds to match 4K caps (3840x2160 / 5120x2880 aggressive)
- Fixed `test_powershell_gaps.py` — added `@skipif(win32)` for Linux-only PowerShell behavior tests
- Fixed `test_stealth_input.py` — added `@skipif(win32)` for Linux-only `post_named_key` test
- Fixed `test_stealth_input_gaps.py` — added `autouse` reload fixture to prevent cross-test state pollution
- Fixed `test_utils.py` — reset `_UIA_OK` cache before UIA availability test
- Fixed `test_virtual_desktop.py` — added `@skipif(win32)` for tests using `/bin/true`, `/bin/echo`
- Fixed `test_virtual_desktop_gaps.py` — split Linux-only stub factory tests into `@skipif(win32)` class
- Fixed `test_popup_handler_gaps.py` — mock `window_manager.list_windows` in "all fail" test
- Fixed `test_stealth_input_win32_paths.py` — patch `_get_focus_hwnd` to avoid ctypes mock recursion

## [3.1.0] - 2026-06-04

### Critical fixes
- **GUI now actually launches** — `gui/themes.py` was missing the `THEMES` dict and `apply_theme()` function that `gui/app.py` imports. Added both, including the `midnight` / `ocean` / `ember` themes the README advertises.
- **Approval mode now actually works** — engine wires an approval callback through to the executor and the GUI now shows a real Approve / Reject dialog for state-changing actions.
- **`close_window` action handler added** — it was advertised in the system prompt but missing from the dispatch table.
- **`wait` action handler added** — same issue; declared in tool schemas, missing handler.

### Reliability
- **LLM retry/backoff**: 408/425/429/5xx are retried with exponential backoff + jitter; non-retriable errors map to human-readable messages (`"Invalid API key"`, `"Model not found"`, etc.).
- **Bounded conversation context**: only the most recent N screenshots stay in the message list; older ones become text stubs. Default `image_history=3`, configurable.
- **Image MIME mismatch fixed**: screenshots default to PNG so the `image/png` media type matches the bytes. Anthropic was rejecting JPEG-as-PNG.
- **Robust JSON action parser**: replaced the regex (which broke on nested braces) with a balanced-brace scanner that understands strings and escapes.
- **`note` action no longer double-logged.**

### New features
- **8 new LLM providers**: MiniMax (M1, abab), Moonshot/Kimi (kimi-k2, moonshot-v1-128k), Qwen / Alibaba DashScope (qwen-max, qwen2.5-72b, qwen2-vl), Cohere (command-a, command-r-plus), NVIDIA NIM, HuggingFace Router, GitHub Models, DeepInfra. Plus an Azure OpenAI placeholder.
- **Z.ai coding plan model list expanded** to GLM-5 / GLM-5-Pro / GLM-5-Flash / GLM-4.6 / GLM-4.5 / GLM-4.5-Air / GLM-Z1 family. The provider now points at Z.ai's coding-plan endpoint (`api.z.ai/api/coding/paas/v4`).
- **OCR-backed `click_text`** — uses Tesseract (via pytesseract) to find visible text on screen and click its centre. New `read_text` action returns the full OCR of the screen. Degrades gracefully when Tesseract isn't installed.
- **Windows UIAutomation** — `click_control`, `set_text`, and `list_controls` actions drive native Windows controls by accessibility metadata (name / automation_id / control_type). The desktop equivalent of clicking a DOM element by selector. Requires the optional `uiautomation` package; no-ops cleanly on non-Windows.
- **Action overlay** — every state-changing action briefly draws a click-through orange ring + label at the target coordinates so you can see what the agent is doing. Different colours per action class (click / type / hotkey).
- **`ActionExecutor.pre_action_callback`** — lets the GUI (or any consumer) hook into every action immediately before it dispatches.
- **Dry-run mode** — `--dry-run` CLI flag or `dry_run: true` in config. State-changing actions log instead of executing; the GUI shows a yellow `DRY-RUN` chip in the header.
- **Esc-x3 failsafe** — three rapid Esc presses stop the agent. Uses the optional `keyboard` package; silently no-ops if it can't install global hooks.
- **Multi-monitor screenshots** — set `monitor: 0` (virtual desktop), `1` (primary), `2+` (secondary) via the `mss` library when installed; falls back to pyautogui.
- **Native tool/function calling** — OpenAI, Anthropic, and other compatible providers now use structured tool calls instead of JSON-in-text. Falls back to JSON parsing for providers without tool support.
- **WebSocket live feed** — the `/ws` endpoint now broadcasts each agent step to connected clients.
- **API auth** — set `SENTINEL_API_TOKEN` to require `Authorization: Bearer <token>` on every endpoint. CORS defaults to localhost-only when no token is set.

### Platform fixes
- **`disk_usage("/")`** now uses the system drive on Windows. Returns zeros instead of 500-ing if the call fails.
- **`kill_process(None)`** no longer crashes.
- **GUI thread safety**: all widget updates from the agent worker thread are marshaled to the Tk main thread via `root.after`.
- **API: Pydantic v2** — `model_dump` with fallback to `.dict()`.
- **API: `/command`** returns 400 with a clear message for malformed JSON instead of a 500 stack trace.
- **API: `/config`** masks `api_key` in responses so the key isn't echoed back over the wire.

### Workflow & dashboard
- **Workflow builder** — CRUD API endpoints for building multi-step automation workflows, with templates and step management (`core/workflow_builder.py`).
- **System dashboard** — real-time CPU, memory, disk, and GPU metrics via `core/dashboard.py` with REST endpoints.

### Actions
- **`mouse_move` + `retry_last_action`** — new actions for explicit cursor positioning and replaying the last failed action.
- **Dedicated `double_click` / `right_click`** — no longer require `button=` parameter in `click`.
- **Popup handler** — automatic dialog detection and dismissal via `core/popup_handler.py` (57 tests).

### Testing & CI
- **CI coverage reporting** — pytest now runs with `--cov=sentinel_desktop --cov-report=term-missing --cov-report=xml` across all Python versions.
- **Test suite expansion** — 83 new tests for recovery engine and LLM client coverage; popup handler tests; all platform-specific tests properly skipped on non-Windows.
- **Test fixes** — resolved async/tkinter mock issues, recovery test assertion formats, and bare-except clauses.

### Docs & style
- **Docstrings added** to 69 public functions across core and gui modules.
- **Ruff formatting** applied consistently across 11+ files.
- **Error handling** narrowed from bare `except` to specific exception types in `action_executor` and other core modules.

### Repo hygiene
- Added `LICENSE` (MIT).
- Added `.gitignore` that excludes `config.json` (contains API keys), caches, build artifacts, exported forensic logs.
- Added `mypy.ini` with permissive defaults.
- Added smoke tests in `tests/` — 36 tests across 7 modules, all passing.
