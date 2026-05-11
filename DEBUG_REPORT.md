# Sentinel Desktop v2 — Debug Report

Date: 2026-05-11

Static analysis of the codebase turned up a mix of show-stopping bugs and quality issues. This document records what was found and what was changed. Every fix is in the corresponding source file; this report is a summary, not a code listing.

## Critical (would break the app on first run)

### 1. GUI won't launch — missing imports
`gui/app.py` imported `THEMES` and `apply_theme` from `gui/themes.py`, but neither name existed there. Any user double-clicking `install_and_run.bat` would hit `ImportError` immediately.

**Fix:** Added a `THEMES` dict (with the `midnight` / `ocean` / `ember` names the README advertises plus `light`) and an `apply_theme()` helper to `gui/themes.py`. The helper wraps `customtkinter.set_appearance_mode` and `set_default_color_theme` and swallows errors so it can't crash startup.

### 2. `close_window` action handler missing
The README, the system prompt, and the action table all advertise a `close_window` action, but the dispatch table in `core/action_executor.py` only had `close_app`. Every `close_window` request from the LLM was returning `unknown_action`.

**Fix:** Added a `_close_window` handler that calls `wm.close_window(title)` and registered it in `_dispatch_table`.

### 3. Approval mode was a no-op
`config.py` defaults `approval_mode=True` and `ActionExecutor` accepts an `approval_callback`, but `core/engine.py` never created or passed one. The README's "Every action requires user confirmation" was untrue.

**Fix:** `AgentEngine.__init__` now accepts `approval_callback`. The run loop checks `config['approval_mode']` and gates state-changing actions (clicks, typing, file writes, process kills, window close, etc.) on the callback's response. Rejections are surfaced back to the LLM as a user message so it can pick another approach. The GUI wires a real Approve/Reject CTkToplevel dialog.

## High-impact

### 4. JPEG bytes sent with `image/png` mime type
`capture_to_base64()` encoded JPEG, but both `engine._add_vision_message` and `llm_client.chat_with_vision` sent the result as `image/png` (in data URLs and in Anthropic's `source.media_type`). Anthropic's API strictly validates `media_type` and rejects mismatched bytes.

**Fix:** `core/screenshot.py` now defaults to PNG encoding (with an optional `fmt='JPEG'` opt-in for smaller payloads). The vision messages remain `image/png`, so bytes and metadata agree.

### 5. Conversation grew without bound
Every step appended a fresh screenshot to the message list. After ~20 steps the context payload contained 20 full screenshots; well before the 100-step budget the run would either crash on context overflow or rack up enormous bills.

**Fix:** `AgentEngine` keeps the most recent `image_history` screenshots (default 3, configurable) and rewrites older ones to `[screenshot at step N — omitted to save tokens]`. Internal `_sentinel_*` markers track which messages carried images; a `_clean_messages_for_api()` helper strips those markers before any payload leaves the engine, so providers never see them.

### 6. GUI updated widgets from the wrong thread
The engine's `on_step_callback` runs on a worker thread, but the GUI's callback directly mutated `chat_display`, `step_label`, and `screenshot_label`. On Windows this races the Tk event loop and crashes intermittently.

**Fix:** Every Tk widget write in `gui/app.py` now goes through `self.root.after(0, ...)` so it runs on the main thread. `_add_chat` is now safe to call from anywhere; helper methods `_update_step_labels` and `_update_screenshot` are scheduled rather than invoked directly.

## Medium

### 7. `psutil.disk_usage("/")` on Windows
`core/system_info.py` always passed `"/"` to `psutil.disk_usage`, which is invalid on Windows. **Fix:** select the path based on `platform.system()`, defaulting to `%SystemDrive%\\` on Windows. Errors fall back to zeros so the `/system` endpoint never 500s.

### 8. Pydantic v2 deprecation
`api/server.py` called `req.dict(exclude_none=True)`, deprecated in Pydantic v2 (which `requirements.txt` pins via `>=2.0.0`). **Fix:** prefer `model_dump` and fall back to `dict` so both major versions work.

### 9. `/command` could crash on bad input
The endpoint called `json.loads(req.command)` with no error handling — malformed JSON returned a 500 with a stack trace. **Fix:** catch `JSONDecodeError`, return a 400 with the parser's message, and reject payloads that aren't an object with an `action` key.

### 10. WebSocket clients list was inert
`/ws` accepted clients into `_ws_clients` but the engine's step events were never broadcast — the live feed advertised in the README didn't actually feed anything. **Fix:** the API server now sets the engine's `on_step_callback` to a broadcaster that schedules `send_json` onto the event loop. A `threading.Lock` guards the client list; dead sockets are pruned.

### 11. `kill_process(None)` crashed
The name path called `target.lower()` without a guard. A misformed action like `{"action":"kill_process"}` would 500. **Fix:** explicit None/empty check at the top.

### 12. No API auth, CORS wide open
`/goal`, `/command`, `/stop`, and the rest had no auth and CORS allowed `*`. Anyone on the LAN could drive the desktop. **Fix:** every endpoint reads an optional `Authorization: Bearer <token>` header against `SENTINEL_API_TOKEN`. When no token is configured, CORS narrows to localhost only (override with `SENTINEL_CORS_ORIGINS` if needed). `/config` also masks `api_key` in responses so the key is never echoed back.

## Low / cleanup

- Removed the dead `hasattr(sysinfo, 'brief_system_info')` check in `_build_env_context` and replaced it with a real try/except so unexpected import failures don't silently produce empty context.
- Removed the duplicate `note` logging path (the executor was already running `_note`, then the engine was appending again).
- `system_info.py` now also imports `os` for the `SystemDrive` lookup.

## Not changed (worth considering later)

- `core/engine._parse_action` uses a regex that breaks on JSON objects with nested braces. Modern providers usually return clean JSON, but a json-extraction library would be more robust.
- `LLMClient.chat` hardcodes `max_tokens`. The new OpenAI o1/o3 models require `max_completion_tokens`. Worth gating on the model id.
- No retry/backoff on transient LLM errors. A single transient 429 currently aborts the run.
- The agent never produces an end-of-run forensic export when running in CLI mode — easy improvement.
- `_handle_command` builds a fresh `AgentEngine` on every request just to reach `.executor` — could be hoisted onto the server.

## Verification

Every edited file was reviewed in full after editing. The sandbox's bash mount lagged behind the file-tool writes, so end-to-end `py_compile` checks weren't possible there, but each edit's syntax was verified by inspection.
