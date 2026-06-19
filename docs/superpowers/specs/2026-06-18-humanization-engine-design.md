# Design Spec — Humanization Engine (Sentinel Desktop v18.x)

**Status:** Design only — not yet implemented.
**Date:** 2026-06-18
**Author:** Sentinel (design) / Brandon (product)
**Cross-references:** `docs/superpowers/notes/future-stealth-mode.md` (deferred adversarial tier).

---

## Overview

Make Sentinel's input **flow like a human operator** — curved cursor paths, eased
velocity, variable typing cadence, natural micro-pauses. Today every input is either a
straight-line `pyautogui.moveTo(x, y, duration=0.3)` (robotic, constant velocity) or an
instant PostMessage injection (no motion at all). This is the fingerprint that
behavioral heuristics in remote-control tools (ScreenConnect, NinjaOne, endpoint
protection) flag, and it reads as obviously non-human to anyone watching a session.

The Humanization Engine is inserted at the **two existing input chokepoints** so every
action — present and future — becomes humanized automatically, with no changes to the
agent loop or action schemas.

### Target level: NATURALISTIC (behavioral) — not adversarial

This phase delivers **naturalistic** humanization: defeats naive timing/linearity
heuristics and looks genuinely human to the eye and to common checks. It is deliberately
**below** adversarial anti-detection (per-user typing biometrics, Fitts's-Law targeting,
error injection). Adversarial work is deferred — see
`docs/superpowers/notes/future-stealth-mode.md`. We pay a small architectural tax now
(see *Stealth-readiness*) so the deferred tier can slot in later without a rewrite.

### Honest constraint

"Flawless, indistinguishable from a human" is asymptotic. No humanization layer
*guarantees* evading every detector. This engine delivers movements and typing that look
human to the eye and to common heuristics. It massively raises the bar; it is not a
biological guarantee. We design to that honest goal.

### Decisions already made (do not re-litigate)

- **Target level:** Naturalistic behavioral only.
- **Insertion:** at the two input chokepoints (`core/desktop.py`, `core/stealth_input.py`).
- **No overshoot + sweep-back, no full Fitts (target-width) timing** — those are
  stealth-tier, deferred.
- **No new dependencies.** Pure-Python math (bezier via `math` + the seeded RNG). No numpy.

---

## Architecture

A new `core/humanize/` subpackage becomes the single source of truth for *motion and
timing*. The existing chokepoints call into it instead of hardcoding `duration=0.3` /
fixed `delay`s.

```
   action_executor._click / _type_text / ...
        │
        ├── stealth path ──▶ stealth_input.post_click / post_text
        │                        │  (timing-only humanization:
        │                        │   cadence + inter-action pauses;
        │                        │   no motion — there's no cursor)
        │                        ▼
        │                   core/humanize.timing + typing
        │
        └── physical path ──▶ desktop.DesktopController.click / move_to / type_text
                                    │  (full humanization:
                                    │   curved path + eased velocity +
                                    │   imprecise landing + cadence)
                                    ▼
                             core/humanize.motion + timing + typing
                                    │
                             uses: core/humanize.profile (tempo)
                                   core/humanize.rng (seeded, reproducible)
```

**Why at the chokepoints, not in the executor:** every input funnel goes through exactly
these two modules. Intercepting there means `_click`, `_type_text`, `_hotkey`, `_drag`,
`_scroll`, `_mouse_move` — and anything added later — are humanized with zero per-action
wiring. The executor's interface (keyword args, `**_`, dict return) is unchanged.

---

## Components

### `core/humanize/rng.py` — seeded, reproducible randomness

```python
"""Seeded RNG for humanization — reproducible for tests and session replay."""
def get_rng(seed: int | None = None) -> random.Random: ...
def reset(seed: int | None = None) -> None: ...   # reset module-default rng
```

A module-level `random.Random` with a configurable seed. Default seed derives from the
session/checkpoint id so a replayed session reproduces the *same* humanized paths.
Tests pin a fixed seed for deterministic assertions. **Critical for stealth-readiness:**
recorded/replayable trajectories are a hard requirement of the deferred adversarial tier,
so the RNG contract is fixed now.

### `core/humanize/profile.py` — tempo profile interface

```python
@dataclass(frozen=True)
class Profile:
    """Humanization tempo. Subclassable so a StealthProfile can slot in later."""
    name: str = "naturalistic"
    # Motion
    move_speed: float = 1.0          # multiplier on base move duration
    curve_deviation: float = 1.0     # how far control points bow off the line
    landing_jitter_px: float = 2.5   # std-dev of Gaussian landing error
    # Typing
    mean_keystroke_s: float = 0.12   # mean inter-key delay
    keystroke_jitter: float = 0.45   # coefficient of variation
    burst_probability: float = 0.15  # chance of a fast burst
    # Timing
    think_bump_s: float = (0.05, 0.35)  # range for inter-action micro-pauses
    click_hold_s: float = (0.04, 0.09)  # range for click down→up duration

NATURALISTIC = Profile(name="naturalistic")
FAST = Profile(name="fast", move_speed=1.8, mean_keystroke_s=0.06)
def get_default_profile() -> Profile: ...   # overridable via env/profile config

# Stealth-readiness: a future StealthProfile(Profile) subclass overrides the same
# fields with biometric-sampled values. No chokepoint changes needed.
```

**Stealth-readiness tax paid here:** the `Profile` dataclass is the single extension
point. The deferred stealth tier subclasses it; nothing in `desktop.py`/`stealth_input.py`
changes when it lands.

### `core/humanize/motion.py` — curve + easing + imprecise landing

```python
def humanized_path(
    start: tuple[int, int],
    target: tuple[int, int],
    *,
    rng: random.Random,
    profile: Profile,
) -> list[tuple[tuple[int, int], float]]:
    """Return [(point, dwell_seconds), ...] — the cursor trajectory to replay.

    - Quadratic bezier for short moves, cubic for long moves (bow in two directions).
    - Single control point pulled off the straight line by profile.curve_deviation
      (jittered per-move → no two moves trace identically).
    - Eased (bell-curve) velocity: samples N points, spaces them in time with
      ease-in/ease-out so velocity peaks mid-move (NOT pyautogui's constant velocity).
    - Terminal point is target + Gaussian(0, profile.landing_jitter_px) — humans
      don't pixel-perfect a target.
    """
```

Implementation notes:
- Bezier via De Casteljau (pure `math`, no deps). Number of samples scales with distance.
- Total move time scales with distance (farther ⇒ longer) with diminishing returns +
  jitter, so the same distance doesn't always take the same time.
- **Curve-agnostic by design** (stealth-readiness): the function returns a generic
  `(point, dwell)` list; the underlying curve generator can later be swapped for
  spline/recorded-path without changing the replay contract.

`DesktopController.move_to` changes from:
```python
pyautogui.moveTo(x=x, y=y, duration=duration)   # linear, constant velocity
```
to replaying the trajectory:
```python
for (px, py), dwell in humanize.humanized_path(current, (x, y),
                                                rng=humanize.get_rng(),
                                                profile=humanize.get_default_profile()):
    pyautogui.moveTo(px, py, _pause=False)
    time.sleep(dwell)
```

### `core/humanize/typing.py` — per-keystroke cadence from real distributions

```python
def keystroke_delays(text: str, *, rng: random.Random, profile: Profile) -> list[float]:
    """Per-keystroke inter-key delays sampled from a log-normal-ish distribution.

    NOT a fixed interval (pyautogui.write's `interval=` is constant). Includes:
    - log-normal base cadence around profile.mean_keystroke_s
    - occasional bursts (profile.burst_probability) where several keys fire fast
    - longer pauses at word boundaries (space) and punctuation
    """
```

`DesktopController.type_text` changes from `pyautogui.write(text, interval=0.02)` to
typing char-by-char with the sampled delays. `stealth_input.post_text` (no cursor, so no
*motion* to humanize) replaces its fixed `delay=0.005` with the same cadence generator —
stopping the "40 instant WM_CHAR messages" fingerprint.

### `core/humanize/timing.py` — micro-pauses, click jitter, think-bumps

```python
def click_hold_duration(*, rng, profile) -> float: ...   # down→up time
def think_bump(*, rng, profile) -> float: ...            # inter-action pause
def maybe_pause(prob=0.1, *, rng, profile) -> float: ... # occasional longer hesitation
```

These are inserted: (a) between `mouseDown`/`mouseUp` in physical clicks, (b) between
`post_click` down/up in stealth clicks, (c) at action boundaries in the executor — **but
only via `humanize.timing` calls, never hardcoded constants in `action_executor.py`**
(stealth-readiness rule: every tempo number flows through the profile).

---

## Data flow

**A humanized click (physical path):**
1. `_click(sx, sy)` — stealth unavailable or disabled → `DesktopController.click`.
2. `click` → `move_to` generates a `humanized_path` from current cursor pos to
   `(sx, sy)`, replays it as micro-`moveTo` + dwells.
3. After landing (slightly off-target), `timing.click_hold_duration` sets the down→up gap.
4. Optional `timing.think_bump` before the next action.

**A humanized click (stealth path):**
1. `_click` → `stealth_input.post_click(sx, sy)`.
2. `post_click`'s internal `time.sleep(delay)` between down/up is replaced with
   `timing.click_hold_duration`. **No motion** (no cursor exists) — only timing is
   humanized. This is the honest limitation of stealth input and it's documented in code.

**Humanized typing:**
1. `_type_text` → `DesktopController.type_text` (physical) or `stealth_input.post_text`.
2. Both consume `typing.keystroke_delays(text, ...)` instead of a fixed interval.

---

## Error handling & graceful degradation

| Failure | Behavior |
|---------|----------|
| `humanized_path` math error | Log + fall back to a straight `pyautogui.moveTo` (never block input). |
| RNG unset | Module default rng auto-seeds from time; no crash. |
| `pyautogui.moveTo` raises mid-replay | Existing `_FailSafeException`/`OSError` handling in `desktop.py` catches it — unchanged. |
| Humanize disabled (`SENTINEL_HUMANIZE=off`) | Bypass entirely, behave exactly as today. **Required for parity tests.** |
| Profile misconfigured | Clamp out-of-range values with logged warnings. |

The `SENTINEL_HUMANIZE` env switch (default on) is **mandatory** — it lets the existing
7,823 tests keep asserting exact coordinates/timings where they do, by turning
humanization off. This is how we honor "NEVER break existing tests."

---

## Testing plan

All additions are new files; no existing test is modified. Where an existing test
asserts an exact `moveTo(x,y,duration)` call, that test runs with humanize disabled
(default in the test env via `SENTINEL_HUMANIZE=off` set in `tests/conftest.py`).

**`tests/test_humanize_motion.py`**:
- `test_path_is_curved` — waypoints deviate from the straight line (not colinear).
- `test_path_eased_velocity` — dwell sequence is longer at start/end than mid (bell shape).
- `test_landing_imprecise` — terminal point ≠ exact target (within jitter std-dev).
- `test_same_seed_same_path` — deterministic replay.
- `test_different_seeds_different_path` — variety across runs.
- `test_short_move_quadratic_long_move_cubic` — branch coverage on distance.
- `test_no_two_consecutive_identical` — repeated moves to same target vary.
- `test_zero_distance_returns_single_point` — degenerate input.

**`tests/test_humanize_typing.py`**:
- `test_delays_variable` — not all delays equal (defeats fixed-interval fingerprint).
- `test_word_boundary_longer_pause` — space/punctuation delays > mean.
- `test_burst_present_occasionally` — some fast clusters over many samples.
- `test_seed_reproducible`.

**`tests/test_humanize_timing.py`**:
- `test_click_hold_within_range`, `test_think_bump_within_range`,
  `test_maybe_pause_zero_when_disabled`.

**`tests/test_humanize_profile.py`**:
- `test_default_is_naturalistic`, `test_clamps_out_of_range`, `test_env_override`.

**`tests/test_humanize_integration.py`** (chokepoint wiring, mocked pyautogui):
- `test_desktop_move_to_uses_humanized_path` — assert pyautogui.moveTo called with path
  waypoints, not one linear call (humanize ON).
- `test_desktop_move_to_linear_when_disabled` — humanize OFF → single `moveTo` (parity).
- `test_stealth_post_click_uses_humanized_hold` — down/up gap from `timing`.
- `test_stealth_post_text_uses_humanized_cadence` — per-char sleep from `typing`.
- `test_env_switch_off_restores_old_behavior` — the safety net for existing tests.

All mocked — no real mouse/keyboard movement in CI. Adds to the 7,823 count.

---

## Stealth-readiness (architectural debt kept on purpose)

These are paid now so the deferred adversarial tier (`future-stealth-mode.md`) needs no
chokepoint rewrite:
1. **Profile interface** — `core/humanize/profile.py`; a future `StealthProfile` subclass
   overrides the same fields.
2. **Curve-agnostic motion** — `humanized_path` returns a generic trajectory list;
   underlying generator is swappable (bezier now → spline/recorded later).
3. **Seeded reproducible RNG** — `core/humanize/rng.py`; required for record/replay of
   stealth trajectories.
4. **No timing constants in `action_executor.py`** — all tempo flows through
   `humanize.timing` so the stealth layer overrides globally.

---

## Open questions

1. **Default ON or OFF in production?** Proposal: ON by default for GUI runs, OFF in the
   test/CI env (via conftest). Needs Brandon's sign-off — affects every operator session.
2. **Per-action opt-out:** should the agent be able to emit `{"action":"click",...,
   "humanize":false}` for speed-critical steps? Adds schema surface. Proposal: yes, as an
   optional field defaulting to true, but defer until a real need appears.
3. **Move-distance→duration curve:** the exact Fitts-ish mapping needs empirical tuning
   on real hardware. Proposal: ship a reasonable default, tune from forensic-log timings
   later.
4. **Stealth path can't show motion** — accept and document, or attempt a "ghost cursor"
   animation for stealth mode? Proposal: accept the limitation now (it's inherent);
   revisit only if a specific remote tool demands visible motion.

---

## Out of scope (this phase)

- **Adversarial / anti-detection humanization** — biometric typing profiles, Fitts's-Law
  target-width timing, overshoot + sweep-back, error + self-correction injection, scroll
  momentum, attention drift. All deferred to `future-stealth-mode.md`.
- **Remote-session detection** ("am I inside ScreenConnect/NinjaOne?") — separate concern;
  Sentinel already drives remote windows as pixels. Not needed for naturalistic input.
- **GUI controls for tuning** the profile live — future GUI work.
- **New dependencies** (numpy/scipy for fancier curves) — pure-Python only.

---

## Recommended build order (within this spec)

1. `core/humanize/rng.py` + `profile.py` (foundations, fully testable in isolation).
2. `motion.py` + `tests/test_humanize_motion.py` (no pyautogui needed).
3. `typing.py` + `timing.py` + their tests.
4. Wire `desktop.py` chokepoint + `test_humanize_integration.py`.
5. Wire `stealth_input.py` chokepoint (timing-only).
6. `SENTINEL_HUMANIZE` switch in conftest; run full suite green.
7. Empirical tuning pass on move-distance→duration from forensic logs.
