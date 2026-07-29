# Fleet Mesh Phase 6 — Production Hardening & Expansion

**Date:** 2026-07-29
**Scope:** Prove the mesh works, expand to 3 nodes, integrate empire, build real-time dashboard, harden production.
**Depends on:** Phases 1–5 (21 mesh modules, 159+ tests, 2-node live mesh)

---

## Architecture Overview

The mesh is alive (NUKE ↔ homeserver). Phase 6 proves it does real work, expands it, and hardens it for 24/7 autonomous operation.

```
┌─────────────────────────────────────────────────────────────┐
│                    Fleet Mesh Phase 6                        │
│                                                             │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐                 │
│  │  NUKE   │───│homeserver│───│PremierBot│  (Phase 6B)     │
│  │ (CNS)   │   │ (PRIME)  │   │(DESKTOP) │                 │
│  └────┬────┘   └────┬─────┘   └────┬─────┘                 │
│       │              │              │                        │
│       └──────────────┼──────────────┘                        │
│                      │                                       │
│              ┌───────▼───────┐                               │
│              │  Real-Time    │  (Phase 6D)                   │
│              │  Dashboard    │                               │
│              └───────────────┘                               │
│                      │                                       │
│              ┌───────▼───────┐                               │
│              │    Empire     │  (Phase 6C)                   │
│              │  (Raven/Buffer│                               │
│              │   /YT/Alpaca) │                               │
│              └───────────────┘                               │
│                                                             │
│  Cross-cutting: Trust Dial (6E), MCP (6E), CLI (6E)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 6A: Prove It Works

**Goal:** Demonstrate the mesh does real work end-to-end.

### 6A.1 Cross-Node Task Execution
- Create a plan on NUKE with a shell task assigned to homeserver
- Verify: TASK_ASSIGNED → execution → TASK_COMPLETED flows back to NUKE
- Verify: result data is correct (stdout matches expected)
- Test all 4 task types: shell, python, action, llm

### 6A.2 Failure Injection & Recovery
- Create a task assigned to homeserver that will fail (e.g., `exit 1` shell)
- Verify: watcher detects stuck/failed task
- Verify: recovery ladder publishes TASK_RETRY
- Verify: after max retries, task marked FAILED
- Verify: escalation logged

### 6A.3 Leader Election Under Failure
- With both nodes running, verify NUKE (CNS) is leader
- Stop NUKE mesh node → verify homeserver detects leader loss
- Restart NUKE → verify re-election (NUKE should win, higher priority)
- Verify: LEADER_CHANGED events published

### 6A.4 Neuralis Checkpoint Resume
- Create plan → complete some tasks → verify checkpoint stored in Neuralis
- Simulate restart → verify `find_incomplete_plans()` returns the plan
- Verify: checkpoint data matches (task statuses, results)

### Audit Criteria:
- [ ] Shell task on homeserver returns correct stdout to NUKE
- [ ] Failed task triggers retry → eventual FAILED + escalation log
- [ ] Leader election produces LEADER_CHANGED event when NUKE drops/restores
- [ ] Neuralis checkpoint created + loadable after "restart"

---

## Phase 6B: Expand to 3 Nodes

**Goal:** Add PremierBot as a third mesh node.

### 6B.1 Deploy to PremierBot
- PremierBot: `pn-bcw5w54` (`100.89.53.128`), Windows 11, Tailscale active
- Clone sentinel-desktop repo
- Install as NSSM service (same pattern as homeserver)
- Priority: DESKTOP (10) — lowest of the three
- Port: 4435

### 6B.2 Three-Node Mesh Verification
- All 3 nodes connected (full mesh: each connects to 2 peers)
- Leader election with 3 nodes: CNS > PRIME > DESKTOP
- Task routing: assign task to each node, verify execution
- Partition tolerance: kill one node, verify other two continue

### Audit Criteria:
- [ ] PremierBot mesh node running (SERVICE_RUNNING)
- [ ] All 3 nodes show ESTABLISHED connections
- [ ] Task can be assigned to and executed by PremierBot
- [ ] Mesh survives single-node failure (other 2 still connected)

---

## Phase 6C: Empire × Mesh Integration

**Goal:** The mesh orchestrates the dormant empire.

### 6C.1 Empire Task Types
- New task type: `empire` — execute empire operations via mesh
- Empire operations: content generation, Buffer publishing, YT analytics, Alpaca P&L
- Each empire operation is a task in a plan

### 6C.2 Empire Plan Flow
- Create plan: "Daily Empire Report"
- Tasks:
  1. shell: pull YT analytics stats
  2. shell: pull Alpaca P&L
  3. shell: pull Buffer post metrics
  4. python: aggregate into empire score
  5. llm: generate narrative summary
- Execute across mesh nodes
- Store result in Neuralis as empire checkpoint

### Audit Criteria:
- [ ] Empire plan created with mixed task types
- [ ] All tasks execute and return results
- [ ] Empire score computed and stored in Neuralis
- [ ] Plan completes end-to-end

---

## Phase 6D: Real-Time Dashboard

**Goal:** Fleet tab shows live mesh data from the EventBus.

### 6D.1 Live Event Streaming
- Fleet tab subscribes to ALL FleetEvent types
- Real-time updates: no polling delay
- Show: leader changes, task state transitions, node join/leave, recovery actions

### 6D.2 Dashboard Widgets
- **Node Health Grid** — CPU/memory per node, heartbeat age, connection status
- **Task Pipeline** — visual flow: PENDING → ASSIGNED → RUNNING → COMPLETED/FAILED
- **Event Log** — scrolling list of mesh events with timestamps
- **Recovery Feed** — active recoveries, retry counts, escalations
- **Leader Badge** — current leader node, election history

### 6D.3 Mesh Control Panel
- Button: Create Plan (modal with task builder)
- Button: Assign Task (select plan → task → node)
- Button: Inject Failure (for testing recovery)
- Button: View Neuralis Checkpoints

### Audit Criteria:
- [ ] Fleet tab shows live node health without page refresh
- [ ] Task state transitions appear in real-time
- [ ] Leader change visible immediately when node drops
- [ ] Recovery actions logged in recovery feed
- [ ] Create Plan button actually creates + assigns tasks

---

## Phase 6E: Production Hardening

**Goal:** Trust dial, MCP, and CLI wired to live mesh.

### 6E.1 Trust Dial Enforcement
- Executor checks trust dial before executing actions
- SAFE actions: execute immediately
- DESTRUCTIVE/IRREVERSIBLE: require approval gate
- Wire `TrustDial.can_execute()` into `_exec_action()`
- Trust level configurable per node via CLI

### 6E.2 MCP Server → Live Mesh
- MCP tools reach the live EventBus (not stubs)
- `fleet_status`: real node count, health from MetricsAggregator
- `list_nodes`: real node data with live metrics
- `create_plan`: creates plan on the orchestrator, assigns tasks
- `deploy_task`: publishes TASK_ASSIGNED to target node
- `get_metrics`: real-time CPU/memory from aggregator
- Add 3 new tools: `get_plans`, `get_events`, `inject_failure`

### 6E.3 Fleet CLI → Live Control
- `fleet status`: queries live EventBus + MetricsAggregator
- `fleet nodes`: lists nodes with real metrics
- `fleet plans`: lists active plans from orchestrator
- `fleet deploy`: creates + deploys plan to mesh
- `fleet inject-failure`: injects a stuck task for recovery testing
- `fleet trust`: get/set trust dial levels

### 6E.4 Audit & Verification
- Every new feature has tests
- Every feature verified working on live mesh
- Final audit: all Phase 6 criteria checked off

### Audit Criteria:
- [ ] Trust dial blocks destructive action without approval
- [ ] MCP fleet_status returns real live data
- [ ] CLI `fleet deploy` creates and assigns a real task
- [ ] CLI `fleet inject-failure` triggers recovery ladder
- [ ] All new code tested (target: 50+ new tests)
- [ ] Lint clean (ruff check)

---

## Final Audit (Phase 6 Complete)

### Automated Checks
1. `pytest tests/test_mesh_*.py -q` → all pass (existing + new)
2. `ruff check core/mesh/` → zero errors
3. Both mesh nodes still running (systemctl + nssm status)
4. Health log shows continuous uptime

### Functional Checks
1. Cross-node task execution verified (shell on homeserver → result on NUKE)
2. Failure injection → recovery → escalation verified
3. Leader election under failure verified
4. Neuralis checkpoint resume verified
5. PremierBot node online (if 6B done)
6. Empire plan executes end-to-end (if 6C done)
7. Dashboard shows live data (if 6D done)
8. Trust dial enforcement verified (if 6E done)
9. MCP tools return live data (if 6E done)
10. CLI controls live mesh (if 6E done)

### Hallucination Prevention
- Every feature verified by running it, not just asserting it compiles
- Every test verified by running the test suite
- Every live feature verified by checking actual node responses
- Audit report written to `docs/superpowers/specs/2026-07-29-phase6-audit.md`

---

## Implementation Order

1. **6A** first — prove the foundation works before building on it
2. **6E** second — hardening makes the proven system production-ready
3. **6B** third — expand once hardened
4. **6D** fourth — dashboard visualizes the hardened multi-node mesh
5. **6C** last — empire integration uses all the above

Each phase has its own commit batch and verification checkpoint.
