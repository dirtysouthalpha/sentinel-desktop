# Stealth Profile — Operator Sampling Guide

How to replace the hand-tuned `StealthProfile` defaults with statistics measured
from a **real human operator**. This guide is for an operator (or developer) who
wants stronger stealth realism than the shipped defaults provide.

> **This is a measurement protocol, not a synthetic generator.** The sampler
> (`core/humanize/biometric_sampler.py`) deliberately refuses to fabricate
> values — fake distributions are themselves a fingerprint. If you don't have
> real samples, you get `None`, not made-up numbers.

---

## What sampling gives you

`sample_operator()` reads a captured session log and returns a
`BiometricStatistics` object whose fields map onto `StealthProfile`:

| `BiometricStatistics` field | Feeds `StealthProfile` field |
|---|---|
| `fitts_width_scaling_coefficient` | `fitts_width_scaling` |
| `overshoot_rate_by_target_size` | `overshoot_probability` (weighted mean) |
| `error_rate` | `error_rate` |
| `mean_correction_delay_s` | `correction_delay_s` |
| `scroll_momentum_decay_rate` | `scroll_momentum` |
| `attention_drift_probability` | `attention_drift_probability` |
| `mean_keystroke_s` / `keystroke_std_s` | `mean_keystroke_s` / `keystroke_jitter` |
| `mean_move_duration_s_by_target_size` | (reference / validation) |

---

## The real entry points

> ⚠️ **The module docstring advertises a CLI**
> (`python -m core.humanize.biometric_sampler --duration … --operator-id …`).
> **That CLI does not exist** — there is no `argparse` / `__main__` block in the
> module. Treat that docstring line as aspirational. The working entry points are
> the Python functions below.

### `sample_operator(session_log_path: str) -> BiometricStatistics | None`

Parses a JSONL session log and returns statistics, or `None` if the log is
empty/insufficient. Raises `ValueError` on malformed input and `FileNotFoundError`
if the path is missing.

```python
from core.humanize.biometric_sampler import sample_operator

stats = sample_operator("~/.sentinel/biometrics/OPERATOR_001.jsonl")
if stats is None:
    print("Not enough samples — see the thresholds below.")
else:
    print(stats.error_rate, stats.scroll_momentum_decay_rate, ...)
```

### `analyze_events(events: list[dict]) -> BiometricStatistics | None`

Same computation, but takes already-parsed event dicts (useful if your capture
tool produces events in memory rather than to disk).

---

## The session-log format (the real contract)

`sample_operator()` parses **JSON Lines**: one JSON object per line. Every line
**must** contain `"action"` and `"timestamp"`. Recognized actions are `click`,
`type`, `scroll`.

### Minimum sample counts

The sampler returns `None` unless the log contains **at least**:

- **100** click events
- **1000** keystrokes (counted across `type` events)
- **50** scroll events

Aim well above these floors — a thin dataset produces noisy statistics.

### Per-action fields the sampler reads

Fields beyond `action`/`timestamp` are **optional**; the sampler skips events
that lack what it needs for a given statistic. To get every statistic, include
the fields below.

**`type` event:**
```json
{
  "action": "type",
  "timestamp": 1718800000.123,
  "keystrokes": [
    {"timestamp": 1718800000.123, "is_error": false},
    {"timestamp": 1718800000.245, "is_error": true}
  ],
  "corrections": [
    {"correction_delay_s": 0.21}
  ]
}
```
- `keystrokes[].timestamp` → inter-keystroke delays (must be within 0–5 s).
- `keystrokes[].is_error` → drives `error_rate`.
- `corrections[].correction_delay_s` → drives `mean_correction_delay_s`.

**`click` event:**
```json
{
  "action": "click",
  "timestamp": 1718800000.500,
  "duration": 0.42,
  "distance": 680,
  "target_size": [24, 18],
  "overshoot": true
}
```
- `duration` + `target_size` → mean move duration by size bucket.
- `distance` + `target_size` + `duration` → Fitts regression coefficient.
- `overshoot` (bool) + `target_size` → overshoot rate by size bucket.
- Size buckets use **area** (`width × height`): `<1000` small, `<5000` medium,
  `>=5000` large (px²).

**`scroll` event:**
```json
{
  "action": "scroll",
  "timestamp": 1718800001.000,
  "momentum_samples": [
    {"delta_px": 38}, {"delta_px": 22}, {"delta_px": 13}
  ]
}
```
- `momentum_samples` (≥3 per scroll) → exponential-decay fit →
  `scroll_momentum_decay_rate` (clamped to `0.0–1.0`).

**Any event** may carry `"attention_pause": true` to contribute to
`attention_drift_probability` (fraction of click/type/scroll events flagged).

---

## Producing the log

There is **no shipped session-recording harness** — the sampler can *parse* a log
but does not *capture* one. To produce a log, you must instrument Sentinel (or an
external input logger) to emit the JSONL above during real work.

A realistic capture session per the spec's protocol:

- **30 minutes** of genuine IT-support tasks: password resets, ticket updates,
  remote-desktop connections, log analysis.
- Sample **real work, not demo patterns** — don't cherry-pick smooth segments.
- At least one operator; for a population-median default, **5+** operators.

### Quick local capture (developer note)

If you want to record Sentinel's *own* humanized actions as a dry run (useful for
validating the parser, less useful as a "real human" biometric source), hook the
humanization chokepoints in `core/desktop.py` (`_humanized_move_to`,
`_humanized_type`, `scroll`) to append the matching event dicts to a JSONL file.
That wiring is **not built**; it's the natural place to add a recorder if you
take sampling further.

---

## Honest limits of the current system

Two gaps mean sampling is, today, partly diagnostic:

1. **No profile loader.** `get_default_profile()` resolves only the named presets
   (`naturalistic`, `fast`, `stealth`). There is no way to point Sentinel at a
   JSON profile built from your `BiometricStatistics` and have it become the
   active profile. Building the sampled values into a `StealthProfile` instance
   works in Python, but it won't be picked up by the running agent without a
   loader. (Future-work wiring.)
2. **Built-in `STEALTH` uses hand-tuned defaults.** The shipped preset's
   `biometric_id="sampled-population-median"` label is aspirational; no
   population dataset exists. Sampling is how that label eventually becomes
   truthful.

Until the loader exists, treat sampling as: **measure → inspect the
`BiometricStatistics` → use it to sanity-check or hand-tune the preset**, with
direct runtime loading as the next milestone.

---

## Reference

- Sampler implementation: `core/humanize/biometric_sampler.py`
- Profile definition + fields: `core/humanize/profile.py`
- Design rationale (Fitts, overshoot, error injection, scroll momentum,
  attention): `docs/superpowers/specs/2026-06-20-fully-stealth-humanization-tier.md`
- How to enable the (current) stealth profile at runtime:
  `docs/superpowers/guides/stealth-mode-activation.md`
