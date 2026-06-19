# Future Phase: Fully-Stealth Mode (deferred, planned)

> **Status:** Deferred from the Humanization Engine (v18.x) work. Capture only — not
> designed in detail yet. Revisit once the naturalistic Humanization Engine ships and
> proves out in the field.
>
> **Note:** Intended to also be persisted to the Neuralis brain via `brain_think`
> (region: `decision`) so the rest of the fleet sees it. Blocked only because the brain
> API on homeserver is offline as of this writing. Persist when homeserver is back.

## Origin
During design of the Humanization Engine (2026-06-18), Brandon called out a longer-term
goal: a **fully stealth** mode where Sentinel's actions are not merely *naturalistic*
(curved paths, human typing cadence) but **indistinguishable from a human operator under
adversarial inspection** — defeating ML/behavioral anti-bot heuristics found in tools
like ScreenConnect, NinjaOne, and endpoint protection behind them.

The naturalistic engine was scoped deliberately *below* this (defeats naive timing
heuristics, looks human to eye + common checks) to ship something real. Full stealth is
the next plateau and needs to be designed as its own effort.

## Planned shape (high level — not a spec)
- **Biometric profiles** — per-operator typing cadence distributions (inter-key timing,
  burst patterns, error+correction rate) sampled from real captures, not synthetic
  distributions.
- **Fitts's-Law-accurate targeting** — movement time scales with distance/target-size;
  realistic **overshoot + correction** on small targets.
- **Scroll/input momentum** — inertial scrolling, not discrete line jumps.
- **Attention drift + dwell** — occasional gaze-like pauses, re-reads, hesitation on
  ambiguous UI.
- **Error + self-correction injection** — mistype→backspace→retype at human rates.
- **Pluggable detector-evasion layer** — abstracted so new heuristics can be countered
  without rewriting the core.

## Architectural debt to leave NOW (in the naturalistic engine) so this is reachable
- Keep the Humanizer behind a **profile interface** (`core/humanize/profile.py`) so a
  `StealthProfile` can slot in later without touching input chokepoints.
- Keep motion generation **curve-agnostic** (bezier now; spline/recorded-paths later).
- Keep the RNG **seeded/reproducible** so stealth profiles can be recorded, replayed,
  and unit-tested the same way naturalistic ones are.
- Do **not** hardcode timing constants in `action_executor.py` — always go through
  `humanize.timing` so the stealth layer can override globally.

## Anti-goal for now
Do not let stealth considerations bloat the naturalistic engine. Ship naturalistic clean
first; the profile interface is the only tax we pay today for tomorrow's stealth.
