# Stealth Mode — Activation Guide

How to turn on Sentinel's adversarial humanization tier ("stealth mode") and what
it actually does at runtime. For *why* each behavior exists and how the modules fit
together, see the design spec:
`docs/superpowers/specs/2026-06-20-fully-stealth-humanization-tier.md`.

> **Read this carefully.** This guide describes what stealth mode **actually does
> today**, not what the spec aspires to. Several capabilities in the spec are
> implemented and unit-tested but are **not yet wired into the live input path** —
> those are called out explicitly below so you don't get a false sense of the
> stealth posture.

---

## TL;DR

```bash
export SENTINEL_HUMANIZE=1                 # master switch; ON by default in production
export SENTINEL_HUMANIZE_PROFILE=stealth   # choose the stealth tempo profile
python main.py
```

To revert to the default humanistic profile, unset the var or set it to
`naturalistic` (or `fast`).

---

## The two environment variables

Humanization is controlled by **two** independent switches. Understand both:

| Variable | Default | Values | Effect |
|---|---|---|---|
| `SENTINEL_HUMANIZE` | `1` (ON) | `1`/`on`/`true`/`yes` → on · `0`/`off`/`false`/`no` → off | **Master switch.** Turns *all* humanization (naturalistic + stealth) on or off. The test suite forces this to `0` so existing coordinate/timing assertions stay deterministic; production runs leave it on. See `core/humanize/__init__.py:is_enabled()`. |
| `SENTINEL_HUMANIZE_PROFILE` | (unset → `naturalistic`) | `naturalistic` · `fast` · `stealth` | **Which tempo profile** to use when humanization is on. Unknown names fall back **silently** to `naturalistic` — humanization never raises. See `core/humanize/profile.py:get_default_profile()`. |

Both must be set correctly: if `SENTINEL_HUMANIZE=0`, the profile choice is
irrelevant (everything is raw input).

---

## What actually changes at runtime

When `SENTINEL_HUMANIZE=1` and `SENTINEL_HUMANIZE_PROFILE=stealth`, the
`StealthProfile` tempo values (defined in `core/humanize/profile.py`) feed the
humanization chokepoints in `core/desktop.py` and `core/stealth_input.py`. The
following behaviors are **active on the live input path**:

| Behavior | Module | Runtime status |
|---|---|---|
| **Fitts's-Law cursor timing** — movement duration scales with distance *and* target width (small targets take longer). | `core/humanize/fitts.py`, wired via `core/humanize/motion.py` + `desktop._humanized_move_to` | ✅ Active |
| **Overshoot + sweep-back** — small targets are overshot/undershot, then corrected. | `core/humanize/overshoot.py`, wired via `motion.py` | ✅ Active |
| **Momentum scrolling** — wheel scrolls decay inertially instead of stopping dead. | `core/humanize/scroll.py`, wired via `desktop.scroll` | ✅ Active |
| **Attention / re-read pauses** — occasional gaze-like pauses before typing, scaled by field type (longer on sensitive/ambiguous fields). | `core/humanize/attention.py`, wired via `action_executor._apply_re_read_pause` | ✅ Active |

### Capabilities that are BUILT but NOT on the live path (dormant)

These exist, are unit-tested, and are safe — but the default input chokepoints do
not currently invoke them. Do **not** assume they are protecting you:

- **Typing-error injection** (`core/humanize/errors.py`). The function
  `inject_errors_and_corrections` and the `errors: bool` flag on
  `keystroke_delays` are implemented and tested, but `desktop._humanized_type`
  calls `keystroke_delays(..., errors=False)` by default. Realistic typos are
  therefore **not** injected at runtime, even in stealth mode. (The spec's
  "never inject into password fields" whitelist is consequently moot — there's
  nothing to whitelist because nothing is injected.)
- **Detector-evasion pipeline** (`core/humanize/detector_evasion.py`). The
  pluggable `DetectorEvasionPipeline` and its strategies
  (`FittsLawStrategy`, `OvershootStrategy`, `ErrorInjectionStrategy`,
  `MomentumScrollStrategy`, `AttentionSimulationStrategy`) compose correctly in
  tests, but no live call site applies the pipeline automatically.

If you need either of these, they must be wired explicitly (a future-work task;
see the bottom of this guide). Until then, stealth mode's anti-detection benefit
comes from motion/scroll/attention realism only — not from typo emulation.

### What the `stealth` preset's numbers actually are

`STEALTH` (in `profile.py`) is a `StealthProfile(name="stealth",
biometric_id="sampled-population-median")`. The tempo fields
(`fitts_width_scaling=2.0`, `overshoot_probability=0.35`, `error_rate=3.0`,
`scroll_momentum=0.85`, `attention_drift_probability=0.08`, …) are
**hand-authored defaults**, not measurements. The `biometric_id` label
("sampled-population-median") is aspirational: **no population-median dataset
exists** — no 5+ operator sampling campaign was ever run, and
`~/.sentinel/biometrics/sample-population-median.json` is not shipped.

To eventually replace these hand-tuned values with real measurements, see
`stealth-profile-sampling-guide.md`. Note that today there is **also no way to
load a custom-sampled profile** — `get_default_profile()` resolves only the three
named presets (`naturalistic`, `fast`, `stealth`); it does not read a profile
from a JSON path. Sampled statistics are diagnostic until that loader is added.

---

## Performance impact

Stealth mode is **slower** than the default naturalistic profile, because:

- Overshoot corrections add extra mouse travel on small targets.
- Attention pauses insert occasional inter-action delays (mean ~0.6 s when they
  fire, controlled by `attention_drift_probability`).
- Fitts's-Law timing lengthens moves to small targets.

The spec targets ≤15% overhead vs. naturalistic (measured via
`tests/benchmark_humanize.py`). For speed-tolerant, non-sensitive bulk tasks,
prefer `SENTINEL_HUMANIZE_PROFILE=fast` or the default `naturalistic`; reserve
`stealth` for contexts where humanistic realism matters more than throughput.

---

## Verifying it's active

A quick sanity check from Python (does not move the mouse):

```python
from core.humanize import is_enabled
from core.humanize.profile import get_default_profile

print("humanization on:", is_enabled())          # True when SENTINEL_HUMANIZE != 0
print("profile:", get_default_profile().name)    # "stealth" when the env var is set
```

Both the GUI (`python main.py`) and the API server (`python main.py --api`)
honor these environment variables.

---

## Disabling / reverting

```bash
# Back to the default humanistic profile:
unset SENTINEL_HUMANIZE_PROFILE        # → naturalistic

# Turn humanization off entirely (raw input, fastest, least human):
export SENTINEL_HUMANIZE=0
```

---

## Honest summary

Stealth mode today = **naturalistic humanization + Fitts-based motion, overshoot
correction, momentum scrolling, and attention pauses**, using hand-tuned tempo
defaults. It is **stronger** than the default naturalistic tier on cursor/scroll
realism, and **equal** on typing (errors are dormant). It is not a full
anti-detection system until error injection and the detector-evasion pipeline are
wired into the live path and the tempo values are replaced with measured
biometrics. Those are tracked as future work, not blockers.
