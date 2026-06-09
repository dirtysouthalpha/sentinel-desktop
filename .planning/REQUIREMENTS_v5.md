# SENTINEL DESKTOP v5.0 — REQUIREMENTS

> Full requirements traceability for v13.0 through v17.0
> Each requirement has a unique ID for test traceability.

---

## v13.0 — OS Integration

### FOP: File Operations Plus

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| FOP-01 | `delete_file` action — delete a file by path with optional force flag | Action | Unit test: delete temp file, verify gone |
| FOP-02 | `move_file` action — move/rename file from src to dst | Action | Unit test: move file, verify at new path |
| FOP-03 | `copy_file` action — copy file from src to dst | Action | Unit test: copy file, verify both exist |
| FOP-04 | `mkdir` action — create directory (with parents flag) | Action | Unit test: create nested dir, verify exists |
| FOP-05 | `stat_file` action — return file metadata (size, modified, permissions, type) | Action | Unit test: stat a known file, verify fields |
| FOP-06 | `find_files` action — glob-pattern file search returning list of matches | Action | Unit test: search *.py in tests/, verify results |
| FOP-07 | `archive_create` action — create zip/tar archive from file list | Action | Unit test: zip 2 files, extract, verify contents |
| FOP-08 | `archive_extract` action — extract zip/tar to destination | Action | Unit test: extract known zip, verify files |
| FOP-09 | All file actions validate paths are within allowed directories | Safety | Unit test: attempt path traversal, verify blocked |
| FOP-10 | All file actions handle missing source gracefully (success=False) | Robustness | Unit test: delete nonexistent file, verify no crash |

### PSC: Process & Service Control

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| PSC-01 | `set_priority` action — change process priority (idle, normal, high, realtime) | Action | Unit test: start process, set priority, verify |
| PSC-02 | `get_env` action — read environment variable by name | Action | Unit test: get PATH, verify non-empty |
| PSC-03 | `set_env` action — set environment variable (current process or user-level) | Action | Unit test: set TEST_VAR, get, verify match |
| PSC-04 | `service_control` action — start/stop/restart/query Windows services | Action | Unit test: query service status, verify response |
| PSC-05 | `start_process` returns PID on success | Refinement | Unit test: start notepad, verify PID > 0 |
| PSC-06 | `kill_process` supports graceful (SIGTERM) then force (SIGKILL) escalation | Refinement | Unit test: kill hung process with timeout |
| PSC-07 | `list_processes` includes CPU% and memory usage per process | Refinement | Unit test: list processes, verify CPU/RAM fields |
| PSC-08 | All process actions sanitize command arguments against injection | Safety | Unit test: attempt shell injection, verify blocked |

### CVT: Credential Vault Integration

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| CVT-01 | `cred_store` action — store credential in OS credential manager | Action | Unit test: store/retrieve, verify round-trip |
| CVT-02 | `cred_read` action — retrieve credential from OS credential manager | Action | Unit test: store then read, verify value |
| CVT-03 | `ssh_connect` can optionally resolve password from cred vault | Integration | Unit test: store SSH creds, connect using ref |
| CVT-04 | Credential actions never log or expose raw values in output | Safety | Unit test: verify cred_store output has no raw value |
| CVT-05 | Credential vault namespace is sentinel/<key> | Convention | Unit test: verify stored key prefix |

### REG: Registry & Environment

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| REG-01 | `registry_read` action — read Windows registry key/value | Action | Unit test: read known HKLM key, verify value |
| REG-02 | `registry_write` action — write Windows registry key/value | Action | Unit test: write to HKCU test key, read back |
| REG-03 | `registry_delete` action — delete registry key or value | Action | Unit test: create then delete, verify gone |
| REG-04 | Registry write/delete requires confirmation for HKLM | Safety | Unit test: attempt HKLM write, verify gate |
| REG-05 | Registry actions validate key paths (no traversal) | Safety | Unit test: attempt invalid path, verify blocked |
| REG-06 | Registry actions work on all root hives (HKCR/HKCU/HKLM/HKU/HKCC) | Coverage | Unit test: test at least HKCU and HKLM |

---

## v14.0 — Resilience Engine

### RTF: Retry & Backoff Framework

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| RTF-01 | `@retryable` decorator for executor methods with configurable max attempts | Infra | Unit test: flaky func fails 2x then succeeds |
| RTF-02 | Exponential backoff with jitter (base 1s, max 30s) | Infra | Unit test: verify increasing delays with jitter |
| RTF-03 | Retry only on transient errors (timeout, connection, rate-limit) | Logic | Unit test: ValueError does NOT trigger retry |
| RTF-04 | `retry_last` action — manually retry the last failed action | Action | Unit test: fail action, retry_last, verify re-exec |
| RTF-05 | Retry state persists in run log (attempt number, delay) | Logging | Unit test: verify retry entries in forensic log |
| RTF-06 | Configurable retry policy per action type | Config | Unit test: ssh_retry=3, click_retry=1 |

### CBR: Circuit Breakers

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| CBR-01 | Circuit breaker per subsystem (SSH, browser, OCR, LLM) | Infra | Unit test: trip SSH breaker, verify blocked |
| CBR-02 | Breaker trips after N consecutive failures (configurable, default 3) | Logic | Unit test: 3 failures → open state |
| CBR-03 | Breaker auto-recovers after cooldown (default 60s) | Logic | Unit test: wait cooldown, verify half-open |
| CBR-04 | Breaker state visible via API (`GET /health/circuits`) | API | Unit test: trip breaker, GET, verify state |
| CBR-05 | Manual breaker reset via API (`POST /health/circuits/{name}/reset`) | API | Unit test: trip, reset, verify closed |

### SLOG: Structured Logging

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| SLOG-01 | Replace stdlib logging with loguru across all core modules | Infra | Unit test: verify loguru is active |
| SLOG-02 | JSON-structured log format (timestamp, module, level, action, duration_ms) | Format | Unit test: parse log line as JSON |
| SLOG-03 | Log rotation (10MB files, keep 7 days) | Config | Unit test: verify rotation config |
| SLOG-04 | `get_logs` action — retrieve recent log entries filtered by level/module | Action | Unit test: log message, retrieve, verify present |
| SLOG-05 | `set_log_level` action — change log level at runtime | Action | Unit test: set DEBUG, verify more output |

### SHL: Self-Healing Upgrades

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| SHL-01 | Recovery engine retries with alternative targeting on click miss | Enhancement | Unit test: miss click, verify auto-retry |
| SHL-02 | Recovery engine re-launches crashed browser automatically | Enhancement | Unit test: kill browser, verify relaunch |
| SHL-03 | Recovery engine re-establishes dropped SSH connections | Enhancement | Unit test: close socket, verify reconnect |
| SHL-04 | Self-healing events logged with recovery strategy | Logging | Unit test: trigger recovery, verify log entry |
| SHL-05 | Max recovery attempts before giving up (configurable, default 3) | Safety | Unit test: exhaust attempts, verify stop |

---

## v15.0 — Knowledge & Configuration

### WMA: Working Memory API

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| WMA-01 | `GET /memory/working` — list all working memory keys | API | Unit test: set value, list, verify present |
| WMA-02 | `GET /memory/working/{key}` — get working memory value | API | Unit test: set then get, verify value |
| WMA-03 | `POST /memory/working` — set working memory key-value | API | Unit test: post value, get, verify match |
| WMA-04 | `DELETE /memory/working/{key}` — clear working memory entry | API | Unit test: set then delete, verify gone |
| WMA-05 | `working_get` / `working_set` executor actions | Action | Unit test: store then recall via executor |

### CFG: Configuration Persistence

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| CFG-01 | Pydantic `AppConfig` model with all settings fields | Model | Unit test: validate full config, no errors |
| CFG-02 | Config loaded from `config.json` on startup | Infra | Unit test: write config file, restart, verify loaded |
| CFG-03 | Config saved to `config.json` on change | Infra | Unit test: update config, verify file written |
| CFG-04 | `config_get` action — read config value by key path | Action | Unit test: get provider, verify match |
| CFG-05 | `config_set` action — update config value by key path | Action | Unit test: set theme, verify persisted |
| CFG-06 | Config changes apply immediately (no restart needed) | UX | Unit test: change provider, verify used on next run |

### DND: DNS & Network Diagnostics

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| DND-01 | `dns_lookup` action — resolve hostname via dnspython | Action | Unit test: resolve google.com, verify IP |
| DND-02 | `dns_leak_test` action — query multiple resolvers, compare responses | Action | Unit test: run test, verify results structure |
| DND-03 | DNS actions work cross-platform (Linux/macOS use system resolver) | Platform | Unit test: mock dns.resolver, verify call |
| DND-04 | `GET /network/dns` API endpoint | API | Unit test: GET, verify response shape |
| DND-05 | DNS results cached for 60s to avoid redundant queries | Perf | Unit test: 2 lookups, verify cache hit |

### PLG: Plugin Hot-Reload

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| PLG-01 | Plugin directory watcher detects new/changed .py files | Infra | Unit test: drop plugin file, verify detected |
| PLG-02 | Changed plugins auto-reload without restart | Infra | Unit test: modify plugin, verify new behavior |
| PLG-03 | Plugin reload logged with before/after state | Logging | Unit test: reload, verify log entry |
| PLG-04 | Hot-reload respects plugin dependencies (reload order) | Logic | Unit test: dependent plugins reload in order |

---

## v16.0 — Advanced Automation

### WMP: Window Management Plus

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| WMP-01 | `resize_window` action — set window to specific WxH | Action | Unit test: resize notepad, verify size |
| WMP-02 | `minimize_window` action — minimize window by handle/title | Action | Unit test: minimize, verify state |
| WMP-03 | `maximize_window` action — maximize window | Action | Unit test: maximize, verify state |
| WMP-04 | `move_window` action — position window at x,y | Action | Unit test: move, verify position |
| WMP-05 | `get_window_state` action — return position, size, state (min/max/normal) | Action | Unit test: get state of known window |
| WMP-06 | Window actions support targeting by title substring (fuzzy match) | UX | Unit test: target "notepad" matches "Untitled - Notepad" |
| WMP-07 | `list_windows` returns handle, title, position, size, PID, state | Refinement | Unit test: verify all fields present |
| WMP-08 | Virtual desktop switch action | Action | Unit test: switch desktop, verify active changed |

### STD: System Tray & Desktop

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| STD-01 | `tray_read` action — read system tray icon names/tooltip text | Action | Unit test: verify tray icons listed |
| STD-02 | `tray_click` action — click system tray icon by name | Action | Unit test: click known tray icon |
| STD-03 | `desktop_control` action — set wallpaper, get screen count, get resolution | Action | Unit test: get screen count, verify ≥1 |
| STD-04 | `get_monitors` action — list all monitors with DPI, resolution, position | Action | Unit test: verify monitor list matches system |
| STD-05 | `power_action` — shutdown, restart, sleep, hibernate, lock screen | Action | Unit test: lock screen (safe), verify no error |
| STD-06 | Power actions require confirmation (cannot be accidental) | Safety | Unit test: verify confirm_required flag |

### HTC: HTTP Client

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| HTC-01 | `http_get` action — GET request to URL with headers/params | Action | Unit test: GET httpbin.org/get, verify response |
| HTC-02 | `http_post` action — POST with JSON/form body | Action | Unit test: POST httpbin.org/post, verify echo |
| HTC-03 | `http_download` action — download file from URL to local path | Action | Unit test: download small file, verify exists |
| HTC-04 | HTTP actions support auth (basic, bearer token from cred vault) | Security | Unit test: verify Authorization header sent |
| HTC-05 | HTTP actions have configurable timeout (default 30s) | Config | Unit test: verify timeout respected |

### DOK: Docker Management

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| DOK-01 | `docker_ps` action — list running containers (name, image, status, ports) | Action | Unit test: mock docker client, verify list |
| DOK-02 | `docker_run` action — run container from image with options | Action | Unit test: mock run, verify config |
| DOK-03 | `docker_stop` action — stop container by name/ID | Action | Unit test: mock stop, verify called |
| DOK-04 | `docker_logs` action — get container logs (tail N lines) | Action | Unit test: mock logs, verify output |
| DOK-05 | `docker_pull` action — pull image from registry | Action | Unit test: mock pull, verify image tag |
| DOK-06 | Docker actions gracefully degrade when Docker not installed | Robustness | Unit test: no docker, verify helpful error |

### MON: File & Process Monitoring

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| MON-01 | `watch_file` action — start watching a file/directory for changes | Action | Unit test: watch dir, create file, verify event |
| MON-02 | `watch_process` action — monitor process for start/stop | Action | Unit test: watch PID, kill, verify event |
| MON-03 | `watch_window` action — monitor for new/closed windows | Action | Unit test: watch, open window, verify event |
| MON-04 | Watchers return events via polling or callback queue | Infra | Unit test: poll watcher, verify event returned |
| MON-05 | Max concurrent watchers limited to 10 (configurable) | Safety | Unit test: start 11 watchers, verify rejection |

---

## v17.0 — Intelligence

### ADP: Adaptive Intelligence

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| ADP-01 | Executor learns which actions frequently fail together | Learning | Unit test: record failures, verify pattern detected |
| ADP-02 | Suggest alternative action sequences based on episode history | Suggestion | Unit test: similar goal, verify suggestion |
| ADP-03 | Adaptive retry delays based on historical failure types | Tuning | Unit test: network failures → longer delays |
| ADP-04 | Success rate tracking per action type in semantic memory | Metrics | Unit test: run actions, verify stats stored |
| ADP-05 | `learn_pattern` action — manually store a goal→action mapping | Action | Unit test: store pattern, recall, verify match |

### AUD: Audio & Speech

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| AUD-01 | `text_to_speech` action — speak text via system TTS engine | Action | Unit test: call TTS, verify no error |
| AUD-02 | `volume_set` action — set system volume (0-100) | Action | Unit test: set volume, verify level |
| AUD-03 | `volume_get` action — get current system volume | Action | Unit test: get volume, verify range |
| AUD-04 | `mute_toggle` action — toggle system mute | Action | Unit test: toggle mute, verify state change |
| AUD-05 | Audio actions work cross-platform (Windows/macOS/Linux) | Platform | Unit test: mock platform, verify correct API |
| AUD-06 | TTS supports voice selection (system voices) | Feature | Unit test: list voices, select one, speak |

### GLN: Goal Learning

| ID | Requirement | Type | UAT |
|----|-------------|------|-----|
| GLN-01 | Episode analyzer extracts successful goal→action patterns | Analysis | Unit test: analyze episode, verify pattern |
| GLN-02 | `suggest_action` action — suggest next action based on context | Action | Unit test: provide context, verify suggestion |
| GLN-03 | Pattern confidence scoring (0-1) based on success frequency | Scoring | Unit test: 5/5 success = 1.0, 3/5 = 0.6 |
| GLN-04 | Low-confidence suggestions flagged for human review | Safety | Unit test: confidence < 0.5, verify flag |
| GLN-05 | Learning respects privacy (no credential/PII in patterns) | Privacy | Unit test: verify no password in learned pattern |

---

## SUMMARY

| Version | Phase | Requirements |
|---------|-------|-------------|
| v13.0 | OS Integration | 29 (FOP-10 + PSC-08 + CVT-05 + REG-06) |
| v14.0 | Resilience Engine | 21 (RTF-06 + CBR-05 + SLOG-05 + SHL-05) |
| v15.0 | Knowledge & Config | 20 (WMA-05 + CFG-06 + DND-05 + PLG-04) |
| v16.0 | Advanced Automation | 30 (WMP-08 + STD-06 + HTC-05 + DOK-06 + MON-05) |
| v17.0 | Intelligence | 16 (ADP-05 + AUD-06 + GLN-05) |
| **TOTAL** | | **116 requirements** |
