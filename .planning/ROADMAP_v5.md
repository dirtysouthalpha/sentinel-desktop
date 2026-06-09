# SENTINEL DESKTOP — v5.0 ROADMAP

> Goal: A desktop automation agent that can literally do anything on a computer.
> Starting point: v12.0 (6,072 tests, 62 tools, 69 executor handlers, 59 API routes)

---

## COMPLETED MILESTONES

| Version | Name | Status | Tests Added |
|---------|------|--------|-------------|
| v4.0 | Multi-Platform Core | ✅ Shipped | 48 |
| v5.0 | Perception Pipeline | ✅ Shipped | 33 |
| v6.0 | Deep Control Layer | ✅ Shipped | 24 |
| v7.0 | Computer-Use + Click Verify | ✅ Shipped | 65 |
| v8.0 | Webhand (Browser) | ✅ Shipped | 325 |
| v9.0 | Netops (SSH) | ✅ Shipped | 54 |
| v10.0 | Sentinel Server | ✅ Shipped | 31 |
| v11.0 | Memory | ✅ Shipped | 56 |
| v12.0 | Conductor + GUI Memory Tab | ✅ Shipped | 47 |
| v12.1 | Code Quality (E501/lint/sklearn fix) | ✅ Shipped | 30 |

---

## UPCOMING MILESTONES

### v13.0 — OS Integration
**Theme:** Filesystem mastery, process control, credential vault, system settings

| Phase | Description | Requirements |
|-------|-------------|-------------|
| 13-A | File Operations Plus | FOP-01 through FOP-10 |
| 13-B | Process & Service Control | PSC-01 through PSC-08 |
| 13-C | Credential Vault Integration | CVT-01 through CVT-05 |
| 13-D | Registry & Environment | REG-01 through REG-06 |

**New actions:** 15 (delete_file, move_file, copy_file, mkdir, stat_file, find_files, archive_create, archive_extract, set_priority, get_env, set_env, service_control, cred_store, cred_read, registry)

**New tools:** 15
**New API endpoints:** 8
**Target tests:** 200+

### v14.0 — Resilience Engine
**Theme:** Retry/backoff, self-healing, circuit breakers, structured logging

| Phase | Description | Requirements |
|-------|-------------|-------------|
| 14-A | Retry & Backoff Framework | RTF-01 through RTF-06 |
| 14-B | Circuit Breakers | CBR-01 through CBR-05 |
| 14-C | Structured Logging (loguru) | SLOG-01 through SLOG-05 |
| 14-D | Self-Healing Upgrades | SHL-01 through SHL-05 |

**New actions:** 3 (retry_last, get_logs, set_log_level)
**New infrastructure:** retry decorator, circuit breaker class, loguru migration
**Target tests:** 150+

### v15.0 — Knowledge & Configuration
**Theme:** Working memory API, config persistence, DNS tools, plugin hot-reload

| Phase | Description | Requirements |
|-------|-------------|-------------|
| 15-A | Working Memory API | WMA-01 through WMA-05 |
| 15-B | Configuration Persistence | CFG-01 through CFG-06 |
| 15-C | DNS & Network Diagnostics | DND-01 through DND-05 |
| 15-D | Plugin Hot-Reload | PLG-01 through PLG-04 |

**New actions:** 6 (working_get, working_set, dns_lookup, dns_leak_test, config_get, config_set)
**New API endpoints:** 6
**Target tests:** 120+

### v16.0 — Advanced Automation
**Theme:** Window management, system tray, dialogs, HTTP client, Docker, monitoring

| Phase | Description | Requirements |
|-------|-------------|-------------|
| 16-A | Window Management Plus | WMP-01 through WMP-08 |
| 16-B | System Tray & Desktop | STD-01 through STD-06 |
| 16-C | HTTP Client | HTC-01 through HTC-05 |
| 16-D | Docker Management | DOK-01 through DOK-06 |
| 16-E | File & Process Monitoring | MON-01 through MON-05 |

**New actions:** 20 (resize_window, minimize_window, maximize_window, move_window, get_window_state, tray_click, tray_read, desktop_control, http_get, http_post, http_download, docker_ps, docker_run, docker_stop, docker_logs, docker_pull, watch_file, watch_process, watch_window, get_monitors)
**New API endpoints:** 12
**Target tests:** 250+

### v17.0 — Intelligence
**Theme:** Adaptive retry, goal learning, pattern recognition, audio

| Phase | Description | Requirements |
|-------|-------------|-------------|
| 17-A | Adaptive Intelligence | ADP-01 through ADP-05 |
| 17-B | Audio & Speech | AUD-01 through AUD-06 |
| 17-C | Goal Learning | GLN-01 through GLN-05 |

**New actions:** 6 (text_to_speech, volume_set, volume_get, mute_toggle, learn_pattern, suggest_action)
**Target tests:** 120+

---

## EXECUTION ORDER

```
v13-A → v13-B → v13-C → v13-D →
v14-A → v14-B → v14-C → v14-D →
v15-A → v15-B → v15-C → v15-D →
v16-A → v16-B → v16-C → v16-D → v16-E →
v17-A → v17-B → v17-C
```

Each phase follows: **spec → implement → test → verify → commit**

---

## FINAL TARGET

| Metric | Current (v12.1) | Target (v17) |
|--------|----------------|-------------|
| Tools | 62 | 112+ |
| Executor handlers | 69 | 113+ |
| API endpoints | 59 | 91+ |
| Tests | 6,072 | 6,700+ |
| Core modules | 81 | 100+ |
| GUI tabs | 5 | 7+ |
| Lint warnings | 0 | 0 |
