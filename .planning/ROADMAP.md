# Roadmap: Sentinel Desktop v9.0–v12.0

## Overview

Four milestones shipping together: SSH network device control, fleet/daemon server, persistent memory, and multi-agent orchestration. All core modules were pre-built; this milestone adds full agent integration (action schemas, executor dispatch, tool schemas) for memory and conductor.

## Phases

- [x] **Phase 1: Netops Integration** — Verify SSH actions, schemas, executor dispatch ✅
- [x] **Phase 2: Server API Endpoints** — Verify daemon/fleet/jobs endpoints ✅
- [x] **Phase 3: Memory Agent Integration** — Action schemas + executor + tools for memory actions ✅
- [x] **Phase 4: Conductor Agent Integration** — Action schemas + executor + tools for conductor ✅
- [x] **Phase 5: Testing & Verification** — Comprehensive tests for all new integrations ✅

## Phase Details

### Phase 1: Netops Integration
**Goal**: Verify SSH network device control is fully wired up
**Requirements**: NET-01–11
**Success Criteria**:
  1. SSH client connects and runs commands
  2. Device-aware commands work for Cisco/Juniper/FortiGate/MikroTik
  3. Output parser extracts structured data
  4. All 5 SSH actions dispatch through executor
  5. Tool schemas expose SSH to LLM
**Plans**:
- [x] 01: Verify SSH client, command runner, output parser (pre-existing)
- [x] 02: Verify action schemas + executor dispatch + tool schemas (pre-existing)

### Phase 2: Server API Endpoints
**Goal**: Verify fleet/daemon/job queue API endpoints
**Requirements**: SRV-01–06
**Success Criteria**:
  1. Daemon start/stop/status endpoints work
  2. Fleet register/unregister/nodes endpoints work
  3. Job queue submit/list/cancel endpoints work
**Plans**:
- [x] 01: Verify daemon + fleet + job queue modules (pre-existing)
- [x] 02: Verify API endpoints (pre-existing)

### Phase 3: Memory Agent Integration
**Goal**: Wire memory modules into the agent action system
**Requirements**: MEM-04–10
**Success Criteria**:
  1. memory_store, memory_recall, memory_search, memory_forget Pydantic schemas
  2. Executor handlers for all memory actions
  3. Tool schemas for LLM tool calling
  4. End-to-end store → recall → search → forget through executor
**Plans**:
- [x] 01: Add memory action schemas to action_schemas.py
- [x] 02: Add memory executor handlers to action_executor.py
- [x] 03: Add memory tool schemas to tool_schemas.py
- [x] 04: Write integration tests (test_memory_executor.py)

### Phase 4: Conductor Agent Integration
**Goal**: Wire conductor into the agent action system
**Requirements**: CON-05–08
**Success Criteria**:
  1. conductor_run Pydantic schema
  2. Executor handler with async→sync bridge
  3. Tool schema for LLM tool calling
**Plans**:
- [x] 01: Add conductor action schema to action_schemas.py
- [x] 02: Add conductor executor handler to action_executor.py
- [x] 03: Add conductor tool schema to tool_schemas.py
- [x] 04: Write conductor dispatch tests

### Phase 5: Testing & Verification
**Goal**: Comprehensive test coverage for all new integrations
**Success Criteria**:
  1. All schema validation tests pass
  2. All executor dispatch tests pass
  3. Integration round-trip tests pass
  4. Tool schema coverage tests pass
**Plans**:
- [x] 01: Write test_memory_executor.py (41 tests)

## Progress

**Execution Order:** 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Netops Integration | 2/2 | ✅ Complete | 2026-06-07 |
| 2. Server API Endpoints | 2/2 | ✅ Complete | 2026-06-07 |
| 3. Memory Agent Integration | 4/4 | ✅ Complete | 2026-06-07 |
| 4. Conductor Agent Integration | 4/4 | ✅ Complete | 2026-06-07 |
| 5. Testing & Verification | 1/1 | ✅ Complete | 2026-06-07 |

---
