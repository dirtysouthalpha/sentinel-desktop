# Design Spec — Neuralis Brain Bridge (Sentinel Desktop v18.0)

**Status:** Design only — not yet implemented.
**Date:** 2026-06-18
**Author:** Sentinel (design) / Brandon (product)
**Depends on:** Neuralis brain API running on `homeserver:8000` (currently offline — see Open Questions).
**Referenced by:** `2026-06-18-brain-gui-panel-design.md`, `2026-06-18-portable-build-design.md`.

---

## Overview

Give Sentinel Desktop a direct, full-surface bridge to the **Neuralis Brain** — the
shared, fleet-wide memory that every agent in Brandon's fleet (Sentinel Desktop,
Claude Code, opencode, omp, mimo) reads from and writes to. With this bridge, Sentinel
becomes a full brain citizen: it writes what it learns (auto-write, no gate) and recalls
or searches what any other agent has learned, so it gets smarter with every task.

This is the **foundation** sub-project. The Brain GUI Panel and the future learning-loop
(automatic recall-at-task-start) both build on it.

### Decisions already made (do not re-litigate)

- **Connection:** Direct HTTP client to the brain API. Configured via
  `NEURALIS_BRAIN_URL` env var (default `http://100.70.240.55:8000`). Matches how Sentinel
  already reaches LLM providers and other services.
- **Surface:** Full — all 7 operations (`think`, `recall`, `search`, `context`,
  `opinions`, `fire`, `stats`). Sentinel is a full brain citizen.
- **Write control:** Auto-write, no approval gate. Friction kills the learning loop.
- **Recall scope (this phase):** Layer 1 only — `brain_recall`/`brain_search` are
  LLM-callable tools the agent chooses to invoke. Automatic recall-at-task-start is
  **out of scope** (lands in the later learning-loop phase).
- **No new dependencies.** Reuse `httpx` (already used in `core/http_client.py`,
  `core/dashboard.py`).

---

## Architecture

A new `core/brain/` subpackage, mirroring the shape of `core/netops/` (a client module
plus thin executor wrappers). One synchronous `BrainClient` speaks HTTP to the brain API.
Every operation maps 1:1 to a public function and an executor action.

```
                         ┌─────────────────────────────────────┐
   LLM ──action──▶ ActionExecutor._dispatch_table["brain_*"]
                         └──────────────┬──────────────────────┘
                                        │  (thin wrapper)
                                        ▼
                              core/brain/__init__.py
                              (public functions: think, recall, ...)
                                        │
                                        ▼
                              core/brain/client.py
                              BrainClient (sync httpx)
                                        │  HTTP
                                        ▼
                          Neuralis Brain API  (homeserver:8000)
```

The client degrades gracefully when the brain is unreachable — exactly like `_HAS_PARAMIKO`
in `core/netops/ssh_client.py`. Sentinel never crashes because the brain is down; brain
actions return a structured `{"success": False, "error": "brain_unavailable"}` instead.

### Placement rationale

- **`core/brain/` not `core/brain.py`** — mirrors `core/netops/`, `core/memory/`,
  `core/web/`. Room to grow (a future `consolidation.py` for the learning loop, a
  `snapshot.py` for the portable build's offline cache).
- **Synchronous client** — the executor dispatch table is sync (`_ssh_run` etc. are sync),
  and brain ops are fast single calls. No need to introduce async here.
- **httpx.Client reused** — a module-level lazy singleton, created on first use, so we
  don't pay connection setup until something actually calls the brain.

---

## Components

### `core/brain/__init__.py`

Public API. Re-exports the client and convenience functions so callers never touch
`client.py` directly.

```python
"""Sentinel Desktop v18.0 — Neuralis Brain bridge.

Direct HTTP client to the Neuralis Brain API (shared fleet memory).
Mirrors the shape of core/netops/. Degrades gracefully when unreachable.
"""
from core.brain.client import (
    BrainClient,
    BrainError,
    BrainUnavailableError,
    get_default_client,
    is_available,
    think,
    recall,
    search,
    context,
    opinions,
    fire,
    stats,
)

__all__ = [
    "BrainClient", "BrainError", "BrainUnavailableError",
    "get_default_client", "is_available",
    "think", "recall", "search", "context", "opinions", "fire", "stats",
]
```

### `core/brain/client.py`

The client. Responsibilities: read `NEURALIS_BRAIN_URL`, own a lazy `httpx.Client`,
translate the 7 ops to HTTP calls, parse responses, map network failures to
`BrainUnavailableError`. **Every endpoint/path/body below is an ASSUMPTION** pending live
introspection of the brain API's OpenAPI schema (see Open Questions).

```python
"""BrainClient — synchronous HTTP client for the Neuralis Brain API.

Connection:
    NEURALIS_BRAIN_URL env var (default http://100.70.240.55:8000).

ASSUMPTION (verify against homeserver:8000/openapi.json when it returns):
    The exact endpoint paths, HTTP methods, and request bodies below are inferred from
    the brain MCP tool signatures (brain_think(topic, content, region, source),
    brain_recall(query, k), etc.). They MUST be confirmed against the live API before
    implementation. Do not code these paths as fact.
"""
```

Key members:

- `class BrainError(Exception)` — base for all brain failures.
- `class BrainUnavailableError(BrainError)` — network/timeout/connection. The one the
  executor catches to return `brain_unavailable`.
- `class BrainClient`:
  - `__init__(base_url: str | None = None, timeout: float = 5.0)` — `base_url` falls back
    to `os.environ.get("NEURALIS_BRAIN_URL", "http://100.70.240.55:8000")`.
  - `_request(method, path, **kwargs)` — central HTTP wrapper. On `httpx.ConnectError` /
    `httpx.TimeoutException` / `httpx.NetworkError`, raises `BrainUnavailableError`. On
    non-2xx, raises `BrainError` with status + body excerpt.
  - `think(topic, content, region="knowledge", source="sentinel-desktop") -> dict`
  - `recall(query, k=10) -> dict`
  - `search(q, limit=10) -> dict`
  - `context(surface="sentinel-desktop") -> dict`
  - `opinions(topic) -> dict`
  - `fire(neuron_id) -> dict`
  - `stats() -> dict`
- `is_available() -> bool` — quick liveness check (one short GET); never raises.
- `get_default_client() -> BrainClient` — module-level lazy singleton.

**ASSUMPTION — endpoint sketch (NOT to be coded as fact):**

| Op | Method | Path (ASSUMED) | Body (ASSUMED) |
|----|--------|----------------|----------------|
| think | POST | `/think` | `{"topic","content","region","source"}` |
| recall | POST or GET | `/recall` | `{"query","k"}` |
| search | GET | `/search` | `?q=...&limit=...` |
| context | GET | `/context` | `?surface=...` |
| opinions | GET | `/opinions` | `?topic=...` |
| fire | POST | `/fire` | `{"neuron_id"}` |
| stats | GET | `/stats` | — |

The real paths may be under `/api/...`, `/v1/...`, or namespaced differently. **Confirm
before implementing.**

### Executor wiring — `core/action_executor.py`

Seven new handler methods, following the exact pattern of `_ssh_run` / `_dns_lookup`:
keyword-only args, `**_` sink, return a `dict` with `success` / `output` / `error`.

```python
def _brain_think(self, *, topic: str, content: str, region: str = "knowledge", **_) -> dict:
    """Persist a thought to the Neuralis Brain (auto-write, no gate)."""
    from core import brain
    try:
        result = brain.think(topic=topic, content=content, region=region,
                              source="sentinel-desktop")
        return {"success": True, "output": result, "op": "brain_think"}
    except brain.BrainUnavailableError:
        return {"success": False, "error": "brain_unavailable",
                "output": "Brain API unreachable (homeserver:8000)."}
    except brain.BrainError as exc:
        return {"success": False, "error": "brain_error", "output": str(exc)}
```

The other six (`_brain_recall`, `_brain_search`, `_brain_context`, `_brain_opinions`,
`_brain_fire`, `_brain_stats`) follow the same shape with their own params. Each is
registered in `_dispatch_table`:

```python
"brain_think":    _brain_think,
"brain_recall":   _brain_recall,
"brain_search":   _brain_search,
"brain_context":  _brain_context,
"brain_opinions": _brain_opinions,
"brain_fire":     _brain_fire,
"brain_stats":    _brain_stats,
```

### Schemas — `core/action_schemas.py`

Seven new pydantic models extending `_ActionBase`, registered in `ACTION_MODELS`.
Mirrors how SSH actions are modeled (see `tests/test_netops_executor.py` for the pattern).

```python
class BrainThinkAction(_ActionBase):
    action: Literal["brain_think"]
    topic: _NonEmptyStr
    content: _NonEmptyStr
    region: Literal["knowledge", "context", "preference", "decision"] = "knowledge"

class BrainRecallAction(_ActionBase):
    action: Literal["brain_recall"]
    query: _NonEmptyStr
    k: Annotated[int, Field(ge=1, le=50)] = 10

# ... search, context, opinions, fire (neuron_id: int), stats (no params)
```

### System prompt — `core/engine.py` (system-prompt template)

A short block added to the system prompt so the LLM knows the brain exists and when to
use it. Follows the existing style of the netops/memory prompt sections.

```
You have access to the NEURALIS BRAIN — a shared memory across the entire agent fleet.

- brain_think(topic, content, region) — remember something durable so every agent
  (Sentinel, Claude Code, opencode, ...) benefits. Use after solving a non-trivial
  problem, fixing a tricky issue, or learning a useful fact. Auto-writes; no confirmation.
- brain_recall(query, k) — retrieve the most relevant stored thoughts on a topic.
- brain_search(q, limit) — free-text search across the whole brain.
- brain_stats() — see how much the brain holds.
Use recall/search BEFORE tackling a technical issue — another agent may have already
solved it. Use think AFTER landing a fix worth sharing.
```

---

## Data flow

**Write path (auto-write, e.g. after a successful fix):**
1. Agent decides to persist a learning → emits `{"action":"brain_think", ...}`.
2. `validate_action` checks it against `BrainThinkAction`.
3. `_dispatch_action_async` routes to `_brain_think`.
4. `_brain_think` calls `core.brain.think(...)` → `get_default_client().think(...)`.
5. `BrainClient._request` POSTs to the brain; on success returns the API's response dict.
6. Result logged to the forensic log like any other action.

**Read path (recall, chosen by the agent):**
1. Agent emits `{"action":"brain_recall","query":"fortigate ha failover"}`.
2. Schema validates → dispatch → `_brain_recall` → `brain.recall(query, k)`.
3. Returns ranked thoughts; the agent sees them in its action-result context and can
   factor them into the next step.

**Degraded path (brain down — the common case right now):**
1. `_request` catches `httpx.ConnectError`/`TimeoutException` → raises
   `BrainUnavailableError`.
2. Handler catches it → returns `{"success": False, "error": "brain_unavailable", ...}`.
3. Agent sees the brain is unreachable and proceeds without it. **No crash, no hang.**

---

## Error handling & graceful degradation

| Failure | Behavior |
|---------|----------|
| Brain host unreachable / API down | `BrainUnavailableError` → action returns `brain_unavailable`; agent continues. |
| Request timeout (default 5s) | Same as above — never block the agent loop on the brain. |
| Non-2xx response | `BrainError(status, body)` → action returns `brain_error` with the message. |
| Malformed response JSON | `BrainError` → `brain_error`. |
| `NEURALIS_BRAIN_URL` unset | Falls back to default; if default also unreachable, degrades as above. |
| Invalid action params | Caught by pydantic in `validate_action` before reaching the client. |

The 5-second timeout is deliberate: brain ops are *augmentation*, never on the critical
path of completing a desktop task. Better to skip the brain than stall a fix.

`is_available()` is provided for the GUI panel to show a live connection indicator
without a full op.

---

## Testing plan

Honors the "NEVER break existing tests" rule — all additions are new files/entries; no
existing test is modified.

**`tests/test_brain_client.py`** (unit, mocked httpx — no live calls):
- `test_is_available_true` / `test_is_available_false` — mock `_request` outcomes.
- `test_think_success` — asserts POST path/body (against ASSUMED contract) + parsed return.
- `test_recall_returns_ranked` / `test_search_returns_results`.
- `test_stats_returns_counts`.
- `test_opinions_topic` / `test_context_surface` / `test_fire_neuron_id`.
- `test_unreachable_raises_brain_unavailable` — mock `httpx.ConnectError`.
- `test_timeout_raises_brain_unavailable` — mock `httpx.TimeoutException`.
- `test_non_2xx_raises_brain_error`.
- `test_default_url_from_env` — `NEURALIS_BRAIN_URL` overrides default.
- `test_default_url_fallback` — unset env → default homeserver URL.
- `test_get_default_client_singleton` — same instance returned twice.

**`tests/test_brain_executor.py`** (executor dispatch + schemas):
- One test per action asserting: valid payload passes `validate_action`; missing required
  field produces errors (pattern from `tests/test_netops_executor.py`).
- `test_brain_think_dispatch_success` — patch `core.brain.think`, assert handler returns
  `{"success": True, ...}`.
- `test_brain_recall_dispatch_unavailable` — patch to raise `BrainUnavailableError`,
  assert `{"success": False, "error": "brain_unavailable"}` and that **no exception
  escapes** the executor.
- `test_brain_stats_no_params` — stats takes no args and still validates.
- `test_dispatch_table_has_all_seven` — assert all 7 keys present in `_dispatch_table`.

**Live integration (manual, gated, NOT in the automated suite):**
- A `tests/manual/test_brain_live.py` (skipped unless `NEURALIS_BRAIN_URL` reachable)
  that round-trips think→recall against the real API. Skipped by default so CI never
  depends on homeserver.

All new tests run under the existing `pytest tests/ -q` harness and add to the 7,823
count without touching any existing file.

---

## Open questions

1. **CRITICAL — brain API contract is ASSUMED.** Every endpoint path/method/body in this
   spec is inferred from MCP tool signatures, not verified. Homeserver (`:8000`) is
   offline as of writing. Before implementation: bring homeserver up, fetch
   `http://100.70.240.55:8000/openapi.json`, and replace the ASSUMED endpoint table with
   the real one. **Do not implement the client until this is done.**
2. **Auth:** Does the brain API require a token/header? The MCP tools don't expose one,
   but the raw HTTP API might. Confirm via OpenAPI. If yes, add `NEURALIS_BRAIN_TOKEN`.
3. **Response shapes:** What exactly do `recall`/`search` return (list of dicts? ranked
   scores?). The executor currently forwards the dict whole; confirm the GUI panel can
   consume it.
4. **Rate limiting / write quotas:** If auto-write fires often, does the brain throttle?
   Unknown. Confirm; may need client-side debouncing in the learning-loop phase (not here).
5. **`fire(neuron_id)` semantics:** "activate a neuron" is vague from the tool signature.
   Needs a sentence from the brain's own docs on what it actually does.

---

## Out of scope (this phase)

- **Automatic recall-at-task-start** — the "gets smarter" engine that injects brain
  knowledge into context without the agent asking. This is the learning-loop sub-project.
- **Episodic→brain consolidation** — automatically distilling finished task episodes
  (`core/memory/episodic.py`) into `brain_think` calls. Also learning-loop territory.
- **Brain GUI panel** — separate spec (`2026-06-18-brain-gui-panel-design.md`); consumes
  this bridge but builds nothing here.
- **Offline brain cache / snapshot** — used by the portable build
  (`2026-06-18-portable-build-design.md`); a separate `core/brain/snapshot.py` later.
- **Approval gate on writes** — explicitly declined; auto-write, no gate.
- **New dependencies** — httpx only, already present.

---

## Recommended build order (within this spec)

1. `core/brain/client.py` + `__init__.py` with graceful degradation — against the
   **confirmed** (not ASSUMED) API contract.
2. Unit tests (`test_brain_client.py`) — all mocked, no live calls.
3. Executor handlers + dispatch entries + pydantic schemas.
4. Executor tests (`test_brain_executor.py`).
5. System-prompt block.
6. Manual live round-trip test once homeserver is up.
