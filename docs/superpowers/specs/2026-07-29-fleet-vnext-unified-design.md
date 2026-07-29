# Fleet vNext — Unified Orchestration Design Spec

**Date:** 2026-07-29
**Author:** ZCode (on behalf of Brandon)
**Status:** Approved — proceeding to implementation planning
**Source:** Brainstorming session 2026-07-29

---

## 1. Vision

**Production-grade fleet:** The entire AI fleet (Sentinel Desktop, Neuralis, CNS, Prime, Agent Zero) runs 24/7 for a full month with zero human firefighting. Full autonomy — agents handle everything including edge cases. Brandon receives only a daily digest.

This is the capstone upgrade that ties together all 7 phases of the FLEET-VNEXT-PLAN into one unified, self-operating system.

---

## 2. Success Criteria

| Criterion | Bar |
|-----------|-----|
| **Uptime** | 24/7 autonomous operation for 30 consecutive days |
| **Human intervention** | Zero firefighting. Daily digest only. |
| **Single-node survival** | Any one node can die — fleet reroutes, no lost work |
| **Two-node survival** | Any two-node combination carries full workload |
| **Cross-session memory** | 85%+ recall hit rate across sessions |
| **Self-recovery** | All known failure modes recovered autonomously |
| **Auditability** | Every decision reconstructable from logs + Neuralis |
| **Safety** | Destructive/irreversible actions still gated by approval |

---

## 3. Architecture — Distributed Mesh with Neuralis Backbone

### 3.1 Design Principle

*Neuralis remembers. Desktop executes. CNS reasons. Prime displays. Any node can orchestrate.*

No single point of failure. No single conductor. The fleet survives any individual component failure.

### 3.2 Nodes

| Node | Hardware | Primary Role | Orchestration? |
|------|----------|--------------|----------------|
| **Prime** | NUKE (`:8091`) | Dashboard, HTTP API, task display | Candidate |
| **Neuralis** | homeserver (`:8000`) | Brain — memory, knowledge, cross-session persistence | No (memory layer) |
| **Sentinel Desktop** | homeserver (`:8091`) | Desktop automation, script execution, screenshots | Candidate |
| **CNS** | NUKE or homeserver | Reasoning — planning, evaluation, self-improvement | Candidate (primary planner) |
| **Agent Zero** | hackbox (edge) | Edge execution, dead-man's switch, fallback | Candidate (fallback) |

### 3.3 Event Bus

Lightweight pub/sub over WebSocket (no new dependencies — `websockets` already in project).

**Event types:**

```python
class FleetEvent(str, Enum):
    # Lifecycle
    NODE_HEARTBEAT = "fleet.event.node.heartbeat"    # node_id, load, timestamp
    NODE_JOINED = "fleet.event.node.joined"          # node_id, capabilities
    NODE_LEFT = "fleet.event.node.left"               # node_id, last_seen

    # Tasks
    TASK_CREATED = "fleet.event.task.created"         # task_id, plan_id, type
    TASK_ASSIGNED = "fleet.event.task.assigned"       # task_id, node_id
    TASK_PROGRESS = "fleet.event.task.progress"       # task_id, pct, checkpoint
    TASK_COMPLETED = "fleet.event.task.completed"     # task_id, result
    TASK_FAILED = "fleet.event.task.failed"           # task_id, error, retryable

    # Plans
    PLAN_CREATED = "fleet.event.plan.created"         # plan_id, task_graph
    PLAN_UPDATED = "fleet.event.plan.updated"         # plan_id, changes
    PLAN_COMPLETED = "fleet.event.plan.completed"     # plan_id, summary

    # Memory
    MEMORY_STORED = "fleet.event.memory.stored"       # neuron_id, region
    MEMORY_RECALLED = "fleet.event.memory.recalled"   # query, hit_count

    # Escalation
    ESCALATION_DAILY = "fleet.event.escalation.daily" # digest_payload
    ESCALATION_CRITICAL = "fleet.event.escalation.critical"  # rare, only if all recovery fails
```

### 3.4 Leader Election

- **Lease-based, priority-ordered:** leader is the highest-priority alive node with a valid 30-second lease
- Node priority: CNS > Prime > Desktop > Agent Zero (Neuralis is memory-only, never leader)
- Lease stored in Neuralis (region: "system") so it survives any single node failure
- Leader renews lease every 15s via heartbeat
- If lease expires, the next highest-priority alive node claims it within 5s
- Leader runs the orchestration loop; followers execute assigned tasks

### 3.5 Local State Cache

Each node maintains a local SQLite cache (via existing `atomic_io` module) of:
- Active plans and task graphs (last 24h)
- Top-100 most-fired Neuralis neurons (refreshed every 5 min)
- Last 1000 fleet events (for local decision-making)
- Checkpoints for in-progress tasks (every 60s)

**Cache safety:** Stale cache is acceptable — neurons decay naturally, fresh ones fire on recall. The fleet operates in "degraded but functional" mode during brief Neuralis outages.

---

## 4. Cross-Session Memory

### 4.1 Three-Layer Model

| Layer | Storage | Scope | Persistence |
|-------|---------|-------|-------------|
| **Working Memory** | Local SQLite (per-node) | Current plan, active tasks, last 50 events | Survives reboot, lost on node death |
| **Session Memory** | Neuralis (brain) | Decisions, lessons, failures, successes | Permanent, cross-session, cross-node |
| **Fleet Memory** | Neuralis + local cache | Shared knowledge, top-100 neurons | Permanent, replicated to all nodes |

### 4.2 Memory Lifecycle

1. Agent encounters a lesson → `brain_think(topic=..., content=..., region="knowledge")`
2. Next session (any node) → `brain_recall(query=..., k=10)` → context injected into agent prompt
3. Local cache refreshed every 5 min via selective re-recall of high-fire neurons
4. On Neuralis recovery: nodes reconcile — push local lessons to brain, pull new shared knowledge

### 4.3 Memory Regions (mapping to Neuralis brain regions)

| Region | Content |
|--------|---------|
| `knowledge` | Fleet facts, infrastructure, decisions |
| `decisions` | Why choices were made (audit trail) |
| `context` | Current operational context |
| `project` | Project-specific knowledge |
| `infrastructure` | Node configs, network topology |
| `architecture` | Design decisions, patterns |

### 4.4 Target Metric

- **Cross-session recall hit rate: 85%+** (matching P4's Neuralis improvement target)
- Measured by: does the agent find relevant context within the top-10 recall results?

---

## 5. Unified Orchestration Loop

### 5.1 The Cycle

```
┌─────────────────────────────────────────────────────────┐
│                 ORCHESTRATION LOOP                        │
│                                                           │
│  1. PLAN (leader node, typically CNS)                     │
│     ├─ Recall relevant memories from Neuralis             │
│     ├─ Build task graph (dependencies, priorities)        │
│     ├─ Store plan in Neuralis as "active_plan"            │
│     └─ Publish: plan.created                              │
│                                                           │
│  2. DELEGATE (leader assigns to best node)                │
│     ├─ Desktop: UI automation, scripts, screenshots       │
│     ├─ CNS: reasoning, evaluation, self-improvement       │
│     ├─ Agent Zero: edge tasks, fallback execution         │
│     └─ Publish: task.assigned                             │
│                                                           │
│  3. EXECUTE (assigned node)                               │
│     ├─ Run with checkpointing every 60s                   │
│     ├─ Publish: task.progress                             │
│     ├─ On failure: retry (3x), rollback, try alt node     │
│     └─ On success: publish task.completed                 │
│                                                           │
│  4. REMEMBER (all nodes, continuous)                      │
│     ├─ Log lessons to Neuralis                            │
│     ├─ Update local cache                                 │
│     └─ Publish: memory.stored                             │
│                                                           │
│  5. DIGEST (daily, leader → Brandon)                      │
│     ├─ Auto-generated report: tasks, failures, lessons    │
│     └─ Delivered via Telegram/Discord webhook             │
│                                                           │
│  Loop repeats. Leader re-evaluates plan every cycle.      │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Task Graph Model

```python
@dataclass
class Task:
    id: str
    type: str                          # "desktop_automation" | "reasoning" | "self_improvement" | "monitoring"
    status: TaskStatus                # pending | assigned | running | completed | failed
    assigned_node: Optional[str]
    dependencies: list[str]            # task IDs that must complete first
    max_retries: int = 3
    retry_count: int = 0
    checkpoint: Optional[dict]         # last checkpoint payload
    created_at: datetime
    budget: Optional[TaskBudget]       # cost/compute cap

@dataclass
class TaskBudget:
    max_api_calls: int = 100
    max_runtime_seconds: int = 3600
    max_cost_usd: float = 5.0
```

### 5.3 Checkpointing

- Every executing node writes checkpoint to local SQLite every 60 seconds
- Checkpoint contains: task ID, current state, retry count, intermediate results
- On crash: new leader reads last checkpoint → resumes from checkpoint (no lost progress)
- Checkpoints purged after 24h (configurable)

### 5.4 Failure Handling Ladder

| Step | Action | Next if fails |
|------|--------|---------------|
| 1 | Retry same node (up to 3x with exponential backoff) | → Step 2 |
| 2 | Retry different node (if available) | → Step 3 |
| 3 | Rollback + re-plan (CNS evaluates failure context) | → Step 4 |
| 4 | Self-update (if code bug — trigger P7 self-improvement) | → Step 5 |
| 5 | Queue for next daily digest (never blocks, never pages) | → Done |

---

## 6. Autonomy & Self-Recovery

### 6.1 Escalation Model: Full Auto

The fleet handles everything autonomously. Brandon receives a daily digest only. No blocking alerts, no pages, no "approve this" prompts.

### 6.2 Self-Recovery Matrix

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Node crash | Heartbeat timeout (>30s) | Leader reassigns tasks to alive nodes |
| Neuralis down | `/api/brain/stats` 404/timeout | Nodes use local cache → operate degraded → reconcile on recovery |
| Task fails 3x | `task.failed` event, retry_count=3 | CNS re-plans with failure context → new task graph |
| Fleet partition | Split heartbeat sets | Each partition operates independently → reconcile on heal (timestamp + Neuralis arbiter) |
| Disk full | Node self-monitoring | Self-cleanup: purge old checkpoints, compress logs, note in digest |
| Auth token expiry | API 401 response | Auto-rotate via existing token management |
| API rate limit | 429 response | Exponential backoff + queue for retry |
| Checksum corruption | `atomic_io` verification | Restore from backup copy (existing pattern) |

### 6.3 Resilience Bar

- **Any single node failure:** Fleet continues, no lost work
- **Any two-node combination:** Carries full workload
- **Three-node failure:** Extremely unlikely. Agent Zero on hackbox is dead-man's switch — if all primary nodes are down, Agent Zero attempts recovery and includes in next digest

---

## 7. Fleet Observability

### 7.1 Daily Digest (Brandon's only touchpoint)

Auto-generated by the leader node, delivered via existing Telegram/Discord webhook:

```
📊 FLEET DAILY DIGEST — 2026-07-29
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Tasks: 47 completed, 2 retried, 0 failed
🧠 Memory: 12 new lessons stored | recall hit: 87%
🏥 Health: Prime ✅ | Neuralis ✅ | Desktop ✅ | CNS ✅ | AgentZero ⚠️ (disk 85%)
📝 Top lessons:
   1. "catbox.moe paused uploads — use litterbox+tmpfiles fallback"
   2. "hackbox drifted 6d silently — node-down-alerter now catches it"
   3. "empire score bug: r['neurons'] vs r['results']"
📅 Tomorrow: continue empire content grind, CNS self-eval #47
```

### 7.2 Real-Time Monitoring (fleet-facing)

- Heartbeat every 15s from each node
- Leader maintains fleet health matrix (CPU, RAM, disk, error rate, last heartbeat)
- Anomaly detection: error rate spike → proactive task reassignment
- All events logged to Neuralis (region: "monitoring") + local forensic log

### 7.3 Audit Trail

Every decision, retry, and recovery action is reconstructable:
- **Neuralis:** Decisions, lessons, plan states (region: "decision")
- **Local forensic log:** Every action with timestamp + context
- **Event bus log:** Last 1000 events cached locally per node

---

## 8. Security & Safety

### 8.1 Existing Security (carried forward from v31)

- API auth via `SENTINEL_API_TOKEN` (fixed in PR #11)
- RBAC on destructive actions (v31)
- Approval gate: 23 `approvals.deny` rules (from Empire Upgrade)
- Atomic writes for credentials and config (v31)

### 8.2 New Safety Layer

| Rule | Behavior |
|------|----------|
| **Budget caps** | Each task has max API calls / runtime / cost. Exceeding → pause + re-plan. |
| **Destructive action lock** | rm -rf, DROP TABLE, git force-push, etc. require approval gate. Fleet can *propose* but not *execute* without trust dial ON (default OFF). |
| **Reversibility check** | Before any action, node checks reversibility. Irreversible actions get checkpointed/snapshotted first so rollback is always possible. |
| **Trust dial** | Per-action-type autonomy level (off → propose → execute). Default: propose-only for destructive, execute for safe. |

### 8.3 Conflict Resolution

For concurrent writes (e.g., two nodes update the same plan):
- **Last-write-wins** by timestamp for independent updates
- **Neuralis as arbiter** for conflicting state (brain's version is source of truth)
- **Vector clocks** for ordering events across partitions (lightweight: node_id + counter)

---

## 9. Phased Rollout

### Phase Summary

| Phase | Focus | Key Deliverable | Depends On |
|-------|-------|-----------------|------------|
| **P1** Desktop v31→vNext Unified | Port v22 hardening + tests by capability, GUI decision, event mesh client | Hardened Desktop with mesh client | — |
| **P2** CLI GA | Claude Code/Warp parity, unified fleet CLI | `sentinel` CLI for all fleet ops | — |
| **P3** CNS 1.0 | Complete 7-phase CNS roadmap, run live headless | Reasoning engine that plans + evaluates | — |
| **P4** Neuralis recall 85%+ | Embeddings, tests, restore drills | Brain that remembers reliably | — |
| **P5** Gateway + MCP hardening | Proxy → v8, MCP 12→13 | Secure communication layer | — |
| **P6** ⭐ Unified Orchestration | The mesh + plan→remember→execute loop | Fleet that runs itself | P4, P5 |
| **P7** Fleet observability + golden evals | Monitoring, self-improvement, eval-gated autonomy | Fleet that improves itself | P6 |

### Parallelization

```
P1 ───────────────────────────────────────────
P2 ─────────────────────────
P3 ───────────────────────────────────────────
P4 ─────────────────────────
P5 ──────────────────
                        P6 ──────────────────────────────
                                                          P7 ────
```

- **Wave 1 (parallel):** P1 + P2 + P3 + P4 + P5
- **Wave 2:** P6 (requires P4 + P5)
- **Wave 3:** P7 (requires P6)

### Duration Estimate

| Wave | Phases | Estimate |
|------|--------|----------|
| Wave 1 | P1–P5 (parallel, critical path = P3) | 3-4 weeks |
| Wave 2 | P6 | 4-6 weeks |
| Wave 3 | P7 | 2-3 weeks |
| **Total** | | **9-13 weeks** |

### Production Test (after all phases)

- **30-day autonomous run:** Fleet operates 24/7, zero human firefighting
- **Daily digest only** to Brandon
- **Success = production-grade fleet** achieved

---

## 10. Key Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Distributed mesh (not central conductor) | No single point of failure. Required for 24/7 bar. |
| Neuralis as memory backbone (not conductor) | Brain is optimized for recall, not real-time orchestration. Avoids bottleneck. |
| WebSocket event bus (no new deps) | `websockets` already in project. No Kafka/Redis/RabbitMQ needed at this scale. |
| Lease-based leader election | Simple, proven, survives any single failure. Lease in Neuralis = survives leader death. |
| Full-auto escalation (no human pages) | Matches Brandon's stated preference. Daily digest only. |
| Local SQLite cache on each node | Survives Neuralis outages. `atomic_io` module already exists. |
| Checkpointing every 60s | Balance between recovery granularity and I/O overhead. |
| 3-retry → rollback → re-plan ladder | Covers transient failures without human intervention. |
| Destructive actions stay gated | Safety invariant from Empire Upgrade. Trust dial default OFF. |

---

## 11. Open Questions (to resolve during implementation)

1. **CNS location:** NUKE or homeserver? Affects latency for reasoning-heavy tasks.
2. **Event bus topology:** Full mesh (every node connects to every other) or star (via Prime)? Full mesh is simpler at 5 nodes.
3. **GUI decision (P1):** Keep customtkinter HUD or migrate to web-based? Affects P1 scope.
4. **Self-improvement safety (P7):** What classes of self-modification are safe without human review?
5. **Daily digest delivery:** Telegram (existing) or Discord (existing webhook)? Or both?

---

## 12. Out of Scope

- New hardware (design runs on existing fleet)
- New third-party dependencies beyond what's already in the fleet
- Mobile app / iOS / Android
- Multi-tenant / team features (single operator: Brandon)
- Replacing the existing Empire Upgrade infrastructure (it works, leave it)

---

*Spec approved 2026-07-29. Proceeding to implementation planning.*
