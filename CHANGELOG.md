# Changelog

## v31.0.0 (2026-07-26) — Security Hardening

Security-focused release. Every item below was verified against a regression
test; see `tests/test_sandbox_hardening.py`, `tests/test_api_auth_hardening.py`,
`tests/test_rbac_super_role.py`, `tests/test_injection_hardening.py`,
`tests/test_marketplace_url_allowlist.py`, `tests/test_fleet_bus_concurrency.py`,
`tests/test_auth_bootstrap_password.py`, `tests/test_event_bus_watchers.py`.

### Critical
- **Fix: the plugin sandbox was dead on Windows.** `core/sandbox.py` did
  `import resource` (Unix-only) at module scope, so the module raised
  `ModuleNotFoundError` on the Windows target and callers silently fell back to
  UNSANDBOXED plugin execution. `tests/test_sandbox.py` could not even be
  collected, which meant the whole suite aborted. There is now a real Windows
  backend built on Win32 **job objects** (`ProcessMemoryLimit` /
  `JobMemoryLimit` memory cap, `ActiveProcessLimit` to bound fork bombs,
  `KILL_ON_JOB_CLOSE` + `TerminateJobObject` for whole-tree teardown), with the
  POSIX `setrlimit`/`setsid` path preserved. If no isolation backend exists the
  sandbox now raises `SandboxUnavailableError` and **refuses to execute** — there
  is no silent unsandboxed fallback.
- **Fix: code injection in the sandbox runner.** `function_name` was
  interpolated raw into the generated runner source (`getattr(module,
  '{function_name}', None)`) while `plugin_path`/`args` correctly used `!r`.
  It is now both `!r`-quoted and validated against an identifier whitelist
  (dunders rejected).
- **Fix: timeout cleanup used the Unix-only `os.killpg`**, so on Windows a
  plugin's child processes were orphaned rather than reaped.

### High
- **Fix: the SUPER role was denied every permission.** `core/server/auth.py`
  built `_ROLE_PERMISSIONS[Role.SUPER]` from `dir(Permission)` — the attribute
  *names* (`"VIEW_STATUS"`) — while `check_permission` compares *values*
  (`"view_status"`). The highest-privilege role had strictly fewer rights than
  ADMIN. It now collects the values.
- **Fix: hardcoded `DEFAULT_ADMIN_PASSWORD`.** `core/auth.py` shipped a constant
  admin password in source and auto-provisioned an ADMIN account with it on
  first run. The bootstrap password is now taken from
  `SENTINEL_BOOTSTRAP_PASSWORD` or randomly generated per process, surfaced
  exactly once (log + stderr), never written in plaintext, and
  `requires_password_rotation()` stays true until rotated.
- **Fix: PowerShell injection in `smart_open`.** `f"Start-Process '{name}'"`
  let a single quote in an agent-supplied app name append arbitrary PowerShell.
  Now escaped via `_ps_escape_single_quoted`, with control characters refused.
- **Fix: `smart_open` bypassed the approval gate.** It was in
  `STATE_CHANGING_ACTIONS` but missing from `APPROVAL_REQUIRED_ACTIONS`, so the
  action that launches arbitrary programs was never shown for approval.
- **Fix: ~26 unauthenticated API handlers.** `_handle_marketplace_install`,
  `_handle_sandbox_*`, `_handle_swarm_*`, `_handle_fleet_*`, `_handle_memory_*`,
  `/vision/analyze`, `/voice/*`, `/workflows/generate`, `/telemetry*`,
  `/playbooks*` and `/update-check` never called `_check_auth` and did not even
  accept an `authorization` parameter. Setting `SENTINEL_API_TOKEN` protected
  `/goal` and `/powershell` but left plugin installation (which executes
  Python), agent spawning and fleet deployment open to anonymous callers. All
  are now gated; `/health` stays open for load balancers.
- **Fix: auth was a no-op by default while binding `0.0.0.0`.** `main.py` now
  calls `api.server.require_secure_bind()`, which refuses to start on a
  non-loopback interface when `SENTINEL_API_TOKEN` is unset — because
  `/powershell` and `/command` execute arbitrary code. Override explicitly with
  `SENTINEL_ALLOW_INSECURE_BIND=1` (e.g. behind an authenticating proxy).

### Medium
- Fix: path traversal on write in `POST /recorder/stop` — only spaces were
  sanitised, so `..`, `/` and `\` in `name` escaped `scripts/`. Now uses the
  same alphanumeric whitelist as `gui/recorder_panel.py`.
- Fix: `core/sandbox.py` `list_active()` popped from `_active_plugins` while
  iterating it, raising `RuntimeError: dictionary changed size during iteration`
  exactly when a plugin finished.
- Fix: `gui/app.py` `_detect_models` ran a network call on the Tk UI thread,
  freezing the settings window; now threaded with an `after()` callback.
- Fix: PowerShell/JS/shell injection via string interpolation in
  `core/commands/notify.py` (title/message), `core/commands/voice.py`
  (`Speak('{text}')`), `core/web/browser.py` (`localStorage.getItem('{key}')` —
  now passed as an `evaluate()` argument), and `core/commands/process.py`
  (`Popen(["start", "", name], shell=True)` flattened the list on Windows so
  `name` reached cmd).
- Fix: `core/marketplace.py` only blocked cloud-metadata hosts, so a
  registry-supplied `file://` or `http://localhost/...` download URL was still
  fetched and installed as importable Python. Now https-only with loopback /
  link-local / unspecified addresses refused. A valid `sha256` is **required** —
  previously `if plugin.sha256:` silently skipped integrity checking whenever
  the registry omitted it. Plugin-name validation also moved ahead of the
  download.
- Fix: `core/fleet/redis_bus.py` invoked subscriber callbacks while holding a
  non-reentrant lock, so any callback that published deadlocked; callbacks now
  fire after the lock is released. `node.agents_running += 1` moved inside the
  lock (lost updates under concurrent deploys).
- Fix: `core/remote/ssh.py` used `StrictHostKeyChecking=accept-new`, trusting a
  first-connection MITM. Default is now `yes` with a Sentinel-managed
  `known_hosts` (`SENTINEL_SSH_KNOWN_HOSTS`); `accept-new` is opt-in per host
  and logs a warning.
- Fix: `core/server/auth.py` rewrote the entire auth store on every
  authenticated request just to bump `last_used` (write amplification plus a
  corruption window per request); now throttled to once per 5 minutes.
- Fix: bearer and WebSocket tokens compared with `!=`; now
  `hmac.compare_digest`.
- Fix: `core/powershell.py` `run_as_admin` never read back output — it scanned
  `command` for a `.tmp` path that only existed in `wrapped`, so stdout was
  always empty. It also meant any `.tmp` token in the caller's command was
  deleted.

### Low
- Fix: `core/commands/voice.py` `shutil.which(" pocketsphinx_continuous")` had a
  leading space, so STT detection could never succeed.
- Fix: `core/platform/windows_backend.py` used `os.system` for sleep/hibernate;
  now `subprocess.run` with an argument list.
- Fix: `core/server/event_bus.py` started watcher threads untracked
  (`_poll_thread` was never assigned), so they leaked and could not be joined.
  Now tracked with `watcher_threads` / `stop_watchers()`.
- Fix: `core/fleet/redis_bus.py` had `import os` at the bottom of the file though
  `__init__` used it.

### Meta
- Version: bumped to 31.0.0 (`core/__init__.py`, `setup.py`,
  `core/config_legacy.py`, FastAPI app version, `main.py`).
- Tests: 8 new regression files (+283 tests), plus `tests/test_sandbox.py`
  (12 tests) becoming collectable again now that `core.sandbox` imports on
  Windows. Suite: 4456 passed before (with `test_sandbox.py` un-collectable and
  aborting the run) → 4751 passed, 25 skipped, 0 failed.

## v26.0.0 (2026-07-05) — Enterprise Edition
- New: **Plugin Marketplace** (`core/marketplace.py`) — browse, install, uninstall community plugins with SHA256 verification
- New: **Telemetry & Analytics** (`core/telemetry.py`) — SQLite-backed metrics: runs, actions, LLM tokens, success rates
- New: **Multi-Tenant Web Dashboard** (`dashboard/`) — full static HTML/CSS/JS dashboard at `/dashboard`
- New: `/marketplace/list`, `/marketplace/install`, `DELETE /marketplace/{name}` endpoints
- New: `/telemetry/summary`, `/telemetry/runs` endpoints
- New: Dashboard auto-refreshes every 10s with health, agent status, telemetry, plugins
- New: `plugins/registry.json` template for marketplace
- Fix: `create_app()` structure restored after middleware injection broke CORS
- Fix: Engine creation reverted to fresh-per-goal with cleanup (backward compatible)
- Version: bumped to 26.0.0 across all modules
- Tests: 12 new tests (7 telemetry + 5 marketplace), all passing

# Changelog

## v25.0.0 (2026-07-05) — Enterprise & Polish
- New: Auto-update checker (`core/updater.py`) — checks GitHub releases for newer versions
- New: `/health` endpoint — system health for load balancers and monitoring (CPU, memory, engine status)
- New: `/update-check` endpoint — check if newer version available
- Version: unified to 25.0.0 across all modules
- Polish: all docstrings updated to v25.0.0

## v24.0.0 (2026-07-05) — Security & Reliability Hardening
- Fix: duplicate AgentEngine creation in `/goal` endpoint (reuse persistent engine, prevent memory leaks)
- New: rate limiting middleware (60 req/min per IP) on all API endpoints
- New: security headers on all responses (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy)
- New: input validation on goal endpoint (empty check, 10K char limit)
- New: DELETE method added to CORS allowed methods
- Fix: FastAPI app title unified from v2 to branded name
- Tests: updated _FakeEngine mock to support engine reuse pattern

## v23.0.0 (2026-07-05) — Architecture Consolidation
- Fix: unified all version strings to 23.0.0 (was split across 6.1.0/2.0.0/v3.0/22.0.2)
- Fix: rewrote requirements.txt with all 20+ real dependencies (was stale from v2.0 era)
- Fix: unified main.py routing — default GUI now uses v23 engine (`gui/app.py`)
- New: `--legacy-gui` flag for old v6.x GUI fallback (deprecated path)
- New: graceful fallback if new GUI dependencies are missing
- Updated all docstrings from v2.0/v3.0/v5.0 to unified version

## v22.0.2 (2026-07-03)
- CI: add mss to requirements.txt so screenshot tests pass on runners
- Tests: skip WindowsBackend test on non-Windows (pygetwindow Linux-incompatible)
- Tests: fix ctypes.windll leak from stealth_input fixture that broke Linux tests
- Fix: correct WindowsInfo -> WindowInfo typo in macos_backend
- Lint: ruff clean across core/gui/api/tests (70 auto-fixed + 1 manual)
- Format: ruff format applied to 66 files
- Version: bump 3.1.0 -> 22.0.2 to match latest tag series

## v5.0.0 (2026-06-23)
- Final release with comprehensive documentation
- 168 tests across all modules
- 13 command modules with full coverage
- 5 themes, plugin system, macro recording
- Voice TTS/STT integration

## v4.2.0 (2026-06-23)
- Edge case hardening (empty input, unicode, long strings)
- Integration tests for all 13 modules
- 168 tests

## v4.1.0 (2026-06-23)
- Voice commands module (TTS/STT)
- Engine detection of espeak, flite, say, SAPI
- 143 tests

## v4.0.0 (2026-06-23)
- Macro recording and playback

## v3.0.0 (2026-06-23)
- Web module (fetch/brief/open/search)

## v2.0.0
- Initial release
