# Requirements: Sentinel Desktop v9.0–v12.0

**Defined:** 2026-06-07
**Core Value:** Automate any Windows desktop task through natural language — safely, reliably, and with full visibility.

## v9 Requirements — Netops (SSH/Network Device Control)

- [x] **NET-01**: SSH client via paramiko — connect, run_command, run_commands, context manager
- [x] **NET-02**: Device-aware command runner — Cisco IOS/NX-OS, Juniper JunOS, FortiGate, SonicWall, MikroTik, pfSense, Linux
- [x] **NET-03**: Output parser — interfaces, ARP, routing, ping, version, IPs, MACs
- [x] **NET-04**: `ssh_connect` action — connect to device with password or key auth
- [x] **NET-05**: `ssh_disconnect` action — disconnect from device
- [x] **NET-06**: `ssh_run` action — execute raw command on connected device
- [x] **NET-07**: `ssh_show` action — device-aware show commands with parsed output
- [x] **NET-08**: `ssh_ping` action — ping from connected device with parsed results
- [x] **NET-09**: Pydantic action schemas for all SSH actions
- [x] **NET-10**: Tool schemas for LLM tool calling
- [x] **NET-11**: Executor dispatch handlers for all SSH actions

## v10 Requirements — Sentinel Server (Fleet/Daemon Mode)

- [x] **SRV-01**: Daemon service manager — start, stop, heartbeat, job tracking
- [x] **SRV-02**: Fleet manager — register, unregister, heartbeat, node listing
- [x] **SRV-03**: Persistent job queue — submit, claim, complete, fail, cancel with priority
- [x] **SRV-04**: API endpoints for daemon — GET /daemon/status, POST /daemon/start, POST /daemon/stop
- [x] **SRV-05**: API endpoints for fleet — GET /fleet/nodes, POST /fleet/register, POST /fleet/unregister
- [x] **SRV-06**: API endpoints for jobs — GET /jobs, POST /jobs/submit, GET /jobs/{id}, POST /jobs/{id}/cancel

## v11 Requirements — Memory (Persistent Memory)

- [x] **MEM-01**: Episodic memory — timestamped JSONL episodes with search and compression
- [x] **MEM-02**: Semantic memory — SQLite key-value facts with categories, tags, access tracking
- [x] **MEM-03**: Working memory — in-memory session scratchpad with key-value and bucket stores
- [x] **MEM-04**: `memory_store` action — store facts in semantic memory via agent
- [x] **MEM-05**: `memory_recall` action — recall facts by exact key
- [x] **MEM-06**: `memory_search` action — keyword search across keys, values, tags
- [x] **MEM-07**: `memory_forget` action — delete facts by key
- [x] **MEM-08**: Pydantic action schemas for all memory actions
- [x] **MEM-09**: Tool schemas for LLM tool calling
- [x] **MEM-10**: Executor dispatch handlers for all memory actions

## v12 Requirements — Conductor (Multi-Agent Orchestration)

- [x] **CON-01**: Task planner — rule-based goal decomposition with dependency detection
- [x] **CON-02**: Parallel executor — concurrent subtask execution respecting dependencies
- [x] **CON-03**: Result synthesizer — merge multi-agent results with status aggregation
- [x] **CON-04**: Conductor coordinator — end-to-end plan → execute → synthesize pipeline
- [x] **CON-05**: `conductor_run` action — decompose and execute complex goals
- [x] **CON-06**: Pydantic action schema for conductor
- [x] **CON-07**: Tool schema for LLM tool calling
- [x] **CON-08**: Executor dispatch handler with sync wrapper for async conductor

## Out of Scope

| Feature | Reason |
|---------|--------|
| Visual regression testing | Not core to IT automation |
| Voice input | Text-based NL only |
| Mobile platform | Windows-only |
| Custom action plugins | Not priority |
| Auto-updates | Manual updates only |

## Traceability

| Requirement | Module | Status |
|-------------|--------|--------|
| NET-01 | core/netops/ssh_client.py | ✅ Complete |
| NET-02 | core/netops/command_runner.py | ✅ Complete |
| NET-03 | core/netops/output_parser.py | ✅ Complete |
| NET-04–08 | core/action_executor.py + tool_schemas.py | ✅ Complete |
| NET-09–11 | core/action_schemas.py + action_executor.py + tool_schemas.py | ✅ Complete |
| SRV-01 | core/server/daemon.py | ✅ Complete |
| SRV-02 | core/server/fleet.py | ✅ Complete |
| SRV-03 | core/server/job_queue.py | ✅ Complete |
| SRV-04–06 | api/server.py | ✅ Complete |
| MEM-01 | core/memory/episodic.py | ✅ Complete |
| MEM-02 | core/memory/semantic.py | ✅ Complete |
| MEM-03 | core/memory/working.py | ✅ Complete |
| MEM-04–10 | core/action_schemas.py + action_executor.py + tool_schemas.py | ✅ Complete |
| CON-01 | core/conductor/planner.py | ✅ Complete |
| CON-02 | core/conductor/parallel.py | ✅ Complete |
| CON-03 | core/conductor/synthesizer.py | ✅ Complete |
| CON-04 | core/conductor/coordinator.py | ✅ Complete |
| CON-05–08 | core/action_schemas.py + action_executor.py + tool_schemas.py | ✅ Complete |

**Coverage:**
- v9–v12 requirements: 35 total
- Mapped to modules: 35
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-07*
