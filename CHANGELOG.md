# Changelog

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
