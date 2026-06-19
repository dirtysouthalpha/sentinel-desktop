# Design Spec — Brain GUI Panel (Sentinel Desktop v18.0)

**Status:** Design only — not yet implemented.
**Date:** 2026-06-18
**Author:** Sentinel (design) / Brandon (product)
**Depends on:** `2026-06-18-neuralis-brain-bridge-design.md` (the panel is a view over
the bridge; with the bridge down it shows the degraded state).
**References:** `docs/prompts/claude-design-brain-panel.md` (visual direction passed to
Claude Design).

---

## Overview

Add a **Brain** tab to Sentinel's cyberpunk HUD — a window into the shared, fleet-wide
Neuralis Brain. It surfaces the brain's seven operations and, more importantly, makes the
user *feel* it: neural, alive, growing. "The brain learns from all clients and gets
smarter with every task" should be visible at a glance.

This is the **view layer** over the Brain Bridge spec. It builds nothing in `core/`; it
consumes `core.brain` and renders it with CustomTkinter, matching the existing tab
patterns (`gui/tabs/memory_tab.py` is the closest analog).

### Decisions already made (do not re-litigate)

- **Full surface visible**, tiered: stats / live feed / recall / search / think primary;
  opinions / fire / context secondary (advanced section).
- **Style:** match the app's existing cyberpunk HUD language — dark-first, neon-cyan
  (`#00F0FF`) on near-black (`#050608`) default, themeable across all themes, mono for
  data / sans for prose, tasteful glow, dense-but-legible.
- **Signature "brain is alive" motif** — subtle pulse + neuron-firing micro-animation.
- **Prime-dashboard constraint:** the Sentinel Prime dashboard's exact brain styling
  could NOT be pulled (homeserver offline). This spec designs to the app's own cyberpunk
  language + standard neural-dashboard conventions; refine toward a fleet-wide visual
  match later.

---

## Architecture

One new tab module + one registration entry. Mirrors `MemoryTab` exactly.

```
   gui/app.py  _TAB_DEFS  +=  ("brain", "🧠", "Brain",
                                "gui.tabs.brain_tab", "BrainTab")
        │  (lazy import, same as every other tab)
        ▼
   gui/tabs/brain_tab.py
   class BrainTab(ctk.CTkFrame)
        │  calls
        ▼
   core/brain  (the bridge — separate spec)
        │  degrades to brain_unavailable when homeserver is down
        ▼
   Neuralis Brain API (homeserver:8000)
```

`BrainTab` is **pure presentation**. All brain access goes through `core.brain`'s public
functions (`stats`, `recall`, `search`, `think`, …) and its `is_available()` liveness
check. The tab never speaks HTTP directly.

---

## Components

### `gui/tabs/brain_tab.py` — `BrainTab(ctk.CTkFrame)`

Follows the `MemoryTab` contract: `__init__(self, parent_frame, app)`, `super().__init__`,
`self.app = app`, `self._t = app._t` (theme token getter with fallbacks), grid layout,
sub-tab bar for the advanced section.

**Layout (single screen, dense but legible):**

```
┌─────────────────────────────────────────────────────────────────┐
│  ● Brain online · 4,213 thoughts · 6 sources · last write 12s  │ ← stats header (live)
│    knowledge 2.1k · context 980 · decision 640 · preference 493 │
├──────────────────────────────────────┬──────────────────────────┤
│  LIVE FEED (recent thoughts)         │  RECALL / SEARCH         │
│  ┌────────────────────────────────┐  │  [ recall: ___________ ] │
│  │ ◉ sentinel-desktop · knowledge │  │  [ search: ___________ ] │
│  │   fortigate ha failover fix    │  │                          │
│  │   12s ago                      │  │  Results (ranked):       │
│  ├────────────────────────────────┤  │  ▸ fortigate ha … 0.94   │
│  │ ◉ claude-code · decision       │  │  ▸ ha split-brain  0.81  │
│  │   use tailscale for …          │  │  ...                     │
│  │   4m ago                       │  │                          │
│  └────────────────────────────────┘  │──────────────────────────│
│                                      │  THINK (write to brain)  │
│  [ pulse: brain activity indicator ] │  region: [knowledge ▾]   │
│                                      │  topic:   [___________]   │
│  [ ▾ Advanced: opinions / fire / … ] │  content: [___________]  │
│                                      │          [ Remember ]    │
└──────────────────────────────────────┴──────────────────────────┘
```

**Sub-components (all `CTkFrame`/`CTkLabel`/`CTkButton`/`CTkTextbox`/`CTkEntry`/`CTkOptionMenu`,
themed via `self._t`):**

1. **Stats header** — `brain.stats()` rendered as a single dense line: connection dot
   (green `status_running` when `is_available()`, grey `status_idle`/red `status_error`
   otherwise), total thought count, source count, seconds-since-last-write. Region
   breakdown as a secondary line. Mono font for numbers. Refreshed on a 5s tick + on every
   successful write.
2. **Live feed** — scrollable list of recent thoughts (`brain.search("", limit=50)` or a
   dedicated recent endpoint if the API exposes one — **ASSUMPTION**, see Open Questions).
   Each row: source-agent chip (colored by source), region tag, topic (sans, bold),
   snippet (sans, truncated), relative timestamp (mono). New entries animate in (see
   *Brain-is-alive motif*).
3. **Recall / Search panel** — two entry boxes. Recall calls `brain.recall(query, k=10)`;
   search calls `brain.search(q, limit=20)`. Results rendered as a ranked list
   (topic + score if the API returns one — **ASSUMPTION**). Mono for scores.
4. **Think compose box** — region `CTkOptionMenu` (knowledge/context/preference/decision),
   topic entry, content textbox, "Remember" button → `brain.think(...)`. On success: clear
   the box, pulse the feed, bump the stats header.
5. **Advanced (collapsible)** — opinions (topic → list), fire (neuron_id entry → invoke),
   context (surface → snapshot). Tucked behind a `▾ Advanced` toggle so it doesn't crowd
   the primary surface.
6. **Brain-is-alive motif** — a small pulsing node indicator (a `CTkLabel` whose color
   cycles accent→bg on a 1.2s `after()` loop, paused when the tab is hidden to save CPU).
   On a new thought arriving in the feed, a one-shot "neuron fire" flash (brief glow on
   the new row's source chip). Subtle, not cheesy — per the Claude Design brief.

### Registration — `gui/app.py`

One entry added to `_TAB_DEFS` (the lazy-import tab registry):

```python
(
    "brain",
    "\U0001f9e0",                 # 🧠 — note: Memory also uses 🧠; pick a distinct
                                  #       icon to avoid sidebar collision (candidate: 🧫
                                  #       or a custom asset). See Open Questions.
    "Brain",
    "gui.tabs.brain_tab",
    "BrainTab",
),
```

No other change to `app.py`. The lazy-import machinery handles the rest exactly as it
does for the other five tabs.

### Threading model

Brain calls are **network I/O** and must not block the UI thread. Pattern follows
`MemoryTab`'s conductor runs: a `threading.Thread` per action, results marshalled back to
the UI via `self.after(0, lambda: ...)` (CustomTkinter's thread-safe enqueue). The 5s
stats-refresh tick uses a single recurring `after()` that re-arms itself. All calls
respect the bridge's 5s timeout, so a hung brain never freezes the panel — it shows the
degraded state instead.

---

## Data flow

**On tab open / refresh tick:**
1. `brain.is_available()` → set the connection dot color.
2. If available: `brain.stats()` → render header; `brain.search("", limit=50)` → render
   feed. Both on a worker thread, results via `after(0, ...)`.
3. If unavailable: header shows "● Brain offline (homeserver:8000 unreachable)", feed
   shows a single informational row, compose box disables with a tooltip.

**Recall/Search submit:**
1. User types + Enter → disable input, show spinner.
2. Worker thread → `brain.recall`/`brain.search`.
3. Results rendered ranked; on `brain_unavailable`, show inline error row (not a dialog).

**Think submit:**
1. User fills region/topic/content → "Remember".
2. Worker thread → `brain.think(...)` (auto-write, no confirmation per the bridge spec).
3. On success: clear box, pulse the feed, refresh stats. On failure: inline error.

---

## Error handling & graceful degradation

| State | Display |
|-------|---------|
| Brain offline (homeserver down) | Red dot, "Brain offline" header, feed shows info row, compose disabled with tooltip. **This is the expected state right now** — must look intentional, not broken. |
| Request timeout (5s) | Inline "brain slow/unreachable" row; UI stays responsive. |
| Op returns `brain_error` | Inline error text in the relevant panel; no modal dialogs. |
| Empty recall/search results | Friendly "nothing in the brain yet for '<q>'" row. |
| Tab hidden | Pulse animation + refresh tick pause (CPU hygiene). |
| Theme change | All tokens via `self._t(...)` → instant retheme like other tabs. |

The degraded (offline) state is first-class because, as of writing, homeserver is down and
the panel will *open* in that state. It must read as "intentionally offline," not
"crashed."

---

## Testing plan

GUI tests are added under the same harness. CustomTkinter widgets can be instantiated
headless for structural assertions; network calls are mocked via `core.brain`.

**`tests/test_brain_tab.py`**:
- `test_tab_instantiates` — `BrainTab(parent, app_stub)` builds without raising.
- `test_registered_in_tab_defs` — `("brain", ..., "BrainTab")` present in `_TAB_DEFS`.
- `test_stats_header_offline_when_unavailable` — patch `brain.is_available`→False, assert
  offline rendering.
- `test_stats_header_online_renders_counts` — patch `brain.stats`→fixture, assert counts.
- `test_feed_renders_thoughts` — patch `brain.search`→fixture list, assert rows.
- `test_recall_submits_and_renders` — patch `brain.recall`, simulate entry+Enter, assert
  ranked results (via `after` polling or direct callback).
- `test_think_submits_and_clears` — patch `brain.think`, fill box, click Remember, assert
  call args + box cleared.
- `test_think_disabled_when_offline` — offline + button disabled.
- `test_advanced_section_collapses` — opinions/fire/context hidden until toggled.
- `test_pulse_pauses_when_tab_hidden` — assert `after` loop stops on hide.
- `test_theme_tokens_used` — no hardcoded colors; all via `self._t`.

No existing test modified; all additions are new. Mocks ensure no homeserver dependency in
CI.

---

## Open questions

1. **Icon collision** — Memory and Brain both wanting 🧠. Candidate: keep 🧠 on Brain
   (it's the literal brain), move Memory to 🗃/💾/📚. Needs Brandon's pick.
2. **"Recent thoughts" source** — is there a dedicated recent-feed endpoint, or do we use
   `search("", limit=N)`? **ASSUMPTION: search with empty query.** Confirm against live API.
3. **Score field** — do `recall`/`search` return a relevance score to render? **ASSUMPTION:
   yes**, but verify; if not, drop the ranking numbers.
4. **Source-agent color mapping** — pick a stable palette per source (sentinel-desktop,
   claude-code, opencode, …). Needs a small registry; fine to hardcode initially.
5. **Live push vs poll** — the brain may support push (SSE/WS) for new thoughts. Polling
   on a 5s tick is the safe default; upgrade to push later if the API offers it.
6. **Prime-dashboard visual match** — deferred until homeserver is back and the Prime
   dashboard's brain view can be screenshotted/CSS-pulled. This spec ships a
   cyberpunk-native panel; refine later.

---

## Out of scope (this phase)

- **The Brain Bridge itself** — separate spec; this panel only consumes it.
- **Automatic recall-at-task-start** UI — learning-loop phase.
- **Push-based live feed** (SSE/WebSocket) — polling now.
- **Editing/deleting thoughts** from the UI — the bridge exposes no delete op today.
- **Custom brain visualizations** (full neural graph, timelines) — future enhancement
  after the basic panel lands and real usage shapes it.
- **Prime-dashboard pixel match** — homeserver offline; cyberpunk-native for now.
- **New dependencies** — CustomTkinter already in use; nothing added.

---

## Recommended build order (within this spec)

1. `gui/tabs/brain_tab.py` skeleton: `BrainTab` frame + registration in `_TAB_DEFS` +
   offline-state rendering (this is the state it'll open in first — get it right).
2. Stats header (online + offline).
3. Live feed + 5s refresh tick + pulse motif.
4. Recall/Search panel.
5. Think compose box.
6. Advanced (collapsible opinions/fire/context).
7. `tests/test_brain_tab.py`.
8. (Post-homeserver) live smoke test against the real brain.
