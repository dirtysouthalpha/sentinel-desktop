# Grind Backlog

Worked top-down by `grind-phase.sh`. The loop does the topmost `[ ]` phase under
**## Active**, then **STOPS** — one phase per session. Each restart picks up the
next phase, so every phase gets a clean context.

**Rules:**
- Mark a phase `[x]` ONLY when: deliverables exist + `ruff check core/ gui/ api/`
  clean + `pytest` exit 0 + committed + pushed. Append the commit SHA: `(commit abc1234)`.
- The loop never invents work. If **## Active** is empty, it runs a maintenance pass
  (verify gates green, fix any newly-failing tests) and stops.
- Blocked? Move the phase to **## Blocked** with `[BLOCKED: <reason>]`, commit, push.
- A human can reorder/add/edit phases here freely at any time.

Format: `- [ ] Phase N: <title> — see \`docs/superpowers/specs/<spec>.md\``

---

## Active

<!-- Phase 3 BLOCKED 2026-06-21: PyPI publish failed with 403 Forbidden - invalid API
     token. Need to configure Trusted Publishers or refresh PYPI_API_TOKEN.
     GitHub Release succeeded. See run 27888597380. -->


  end-to-end with a NON-COLLIDING patch version. CRITICAL: v22.0.0 is ALREADY on
  PyPI (manual upload), so do NOT push a v22.0.0 tag (release.yml would re-build
  22.0.0 and PyPI rejects the duplicate file). Instead:
    1. Bump `core/__init__.py` `__version__` from "22.0.0" → "22.0.1".
    2. Commit with message "chore(release): bump to 22.0.1 for pipeline shakedown".
    3. Tag `v22.0.1` (annotated): `git tag -a v22.0.1 -m "v22.0.1 — release pipeline verification"`.
    4. Push the commit, then push the tag: `git push origin main && git push origin v22.0.1`.
    5. The tag triggers `.github/workflows/release.yml` (on: push tags v*) →
       test → build sdist+wheel → publish to PyPI via PYPI_API_TOKEN → GitHub Release.
    6. Watch the run: `gh run watch` (or Actions tab). Verify both the PyPI publish
       job AND the GitHub Release job succeed. Confirm 22.0.1 appears at
       pypi.org/pypi/sentinel-desktop and in the repo's Releases.
  Gate: release.yml run is green (all jobs), pypi.org shows 22.0.1, GitHub
  Release exists for v22.0.1. If publish fails, read the job log, fix, retag
  v22.0.2 (PyPI doesn't allow re-uploading a failed version either). This phase
  proves the whole release automation works — after it, every future stealth-tier
  release (v22.1.0+) is one tag push away.

<!-- STEALTH-TIER IMPLEMENTATION — sourced from the Phase 1 design spec
     (docs/superpowers/specs/2026-06-20-fully-stealth-humanization-tier.md).
     One phase per module, TDD, ordered by dependency. The spec's
     "## Deliverables" lists the exact files + tests for each. A phase is
     done when: the module exists, its tests/test_humanize_stealth_*.py passes,
     ruff clean, full pytest exit 0, committed + pushed. Do NOT wire a module
     into the chokepoints until its own phase is complete — wiring is its own
     dedicated phase (Phase 11) so a broken half-wire never lands on main. -->

- [ ] Phase 10: Biometric sampler — `core/humanize/biometric_sampler.py` (NEW).
  `sample_operator(session_log_path) -> BiometricStats` extracting real inter-key
  + inter-move distributions from a captured session, returning a dataclass the
  StealthProfile can consume. Spec §"biometric_sampler.py", Deliverable #2.
  IMPORTANT: the spec forbids inventing synthetic values — if no real samples
  exist, return None / raise a clear error, don't fake it. Gate:
  `tests/test_humanize_stealth_biometric.py` passes (parses a fixture session log
  into correct stats; returns None/raises on empty input; never synthesizes).
  Last of the leaf modules since it only feeds StealthProfile defaults.

- [ ] Phase 11: Stealth wiring at the chokepoints — modify `core/humanize/motion.py`
  (`humanized_path` accepts `target_size`, routes through fitts+overshoot when
  profile is StealthProfile), `core/humanize/typing.py` (`keystroke_delays`
  accepts `errors: bool`, routes through errors.py),
  `core/action_executor.py` (`_click`/`_type_text`/`_scroll` pass context:
  target_size, field_type, action_context), `core/desktop.py` (physical chokepoint
  uses `fitts_move_duration` for StealthProfile). Spec Deliverables #9-12.
  Gate: existing humanize tests still green with `SENTINEL_HUMANIZE=0` (the
  naturalistic path must NOT change); new tests assert the stealth path activates
  only under StealthProfile. ruff + full pytest exit 0. Do this ONLY after Phases
  4-10 are done — it's the integration point where a half-wire breaks main.

- [ ] Phase 12: Detector-evasion pipeline — `core/humanize/detector_evasion.py`
  (NEW). A pluggable `EvasionPipeline` that wraps the stealth modules and applies
  a configurable ordered list of evasion strategies. Spec §"detector_evasion.py",
  Deliverable #8. Gate: `tests/test_humanize_stealth_detector_evasion.py` passes
  (pipeline applies strategies in order; a no-op pipeline is a passthrough;
  adding a strategy changes output; per-strategy failure degrades gracefully).
  Last — it wraps everything, so all other stealth phases must be done first.


## Blocked

<!-- Move a phase here with a [BLOCKED: <one-line reason>] note if it can't proceed. -->

- [BLOCKED: PyPI 403 - invalid API token, need Trusted Publishing or valid PYPI_API_TOKEN refresh] Phase 3: First clean automated release — verify the release pipeline
  end-to-end with a NON-COLLIDING patch version. CRITICAL: v22.0.0 is ALREADY on
  PyPI (manual upload), so do NOT push a v22.0.0 tag (release.yml would re-build
  22.0.0 and PyPI rejects the duplicate file). Instead:
    1. Bump `core/__init__.py` `__version__` from "22.0.0" → "22.0.1".
    2. Commit with message "chore(release): bump to 22.0.1 for pipeline shakedown".
    3. Tag `v22.0.1` (annotated): `git tag -a v22.0.1 -m "v22.0.1 — release pipeline verification"`.
    4. Push the commit, then push the tag: `git push origin main && git push origin v22.0.1`.
    5. The tag triggers `.github/workflows/release.yml` (on: push tags v*) →
       test → build sdist+wheel → publish to PyPI via PYPI_API_TOKEN → GitHub Release.
    6. Watch the run: `gh run watch` (or Actions tab). Verify both the PyPI publish
       job AND the GitHub Release job succeed. Confirm 22.0.1 appears at
       pypi.org/pypi/sentinel-desktop and in the repo's Releases.
  Gate: release.yml run is green (all jobs), pypi.org shows 22.0.1, GitHub
  Release exists for v22.0.1. If publish fails, read the job log, fix, retag
  v22.0.2 (PyPI doesn't allow re-uploading a failed version either). This phase
  proves the whole release automation works — after it, every future stealth-tier
  release (v22.1.0+) is one tag push away.
  ATTEMPTED: v22.0.1 tag pushed 2026-06-21, tests passed, build passed, GitHub Release
  created successfully, but PyPI publish failed with 403 Forbidden - invalid token.
  Need to either configure Trusted Publishers or refresh the PYPI_API_TOKEN secret.
  Next attempt must use v22.0.2 (PyPI rejected re-upload of 22.0.1).


## Done

- [x] Phase 9: Attention drift + dwell — `core/humanize/attention.py` (NEW).
  `attention_pause(action_context, *, rng, profile) -> float` returning an
  occasional gaze-like pause, scaled by context (longer on ambiguous UI). Spec
  §"attention.py", Deliverable #7. Gate: `tests/test_humanize_stealth_attention.py`
  passes (pause probability, context-aware scaling, re-read pause branch, zero
  when disabled).
  Implements attention_pause() and re_read_pause() functions with context-aware
  probability (destructive 2×, password 1.5×, repetitive 0.5×), Gaussian duration
  sampling, StealthProfile-only activation, deterministic seeded RNG.
  19 comprehensive tests covering pause probability, context-aware scaling,
  re-read pauses, zero when disabled, determinism, duration bounds.
  ruff clean, all 8,810 tests passing. (commit bdd2c96)
- [x] Phase 6: Overshoot + sweep-back — `core/humanize/overshoot.py` (NEW).
  `overshoot_target(target, current, *, rng, profile, target_width_px) -> tuple`
  returning a point past the target (overshoot) or short of it (undershoot),
  probabilistically scaled by target size. Spec §"overshoot.py", Deliverable #4.
  Gate: `tests/test_humanize_stealth_overshoot.py` passes (overshoot probability
  scales inversely with target width; undershoot vs overshoot distribution;
  sweep-back lands within jitter of target). Depends on rng.py (exists) only.
  Implements overshoot probability scaling (60% small/30% medium/10% large),
  undershoot vs overshoot 50/50, miss magnitude scaling, correction jitter,
  non-StealthProfile fallback. 17 tests, all pass (8,702 total). ruff clean.
  (commit 89ad6a9)
- [x] Phase 5: Fitts's-Law targeting — `core/humanize/fitts.py`. Pure function
  `fitts_move_duration(start, target, target_size, *, rng, profile) -> float`
  computing Fitts's Law: time = a + b * log2(2 * distance / target_width).
  Implements ID computation, duration scaling with fitts_width_scaling,
  fallback to distance-only timing for NATURALISTIC profile, edge cases
  (tiny target < 5px clamped, zero-distance returns base intercept 0.05s,
  non-negative duration guarantee). 16 tests covering ID computation,
  duration scaling, edge cases, profile fallback, determinism. ruff clean,
  all humanize tests green (138 passing). (commit a9237cf)
- [x] Phase 4: StealthProfile extension — `core/humanize/profile.py`. Added a
  frozen `StealthProfile(Profile)` dataclass (subclass — inherits the naturalistic
  fields, overrides with biometric-sampled defaults) + a `STEALTH` preset registered
  in `_PRESETS`. Spec §"profile.py — StealthProfile extension", Deliverable #1.
  Gate: `tests/test_humanize_stealth_profile.py` passes (31/31 tests: instantiation,
  field validation, preset registry lookup via `get_default_profile()` under
  `SENTINEL_HUMANIZE_PROFILE=stealth`). ruff clean + full pytest exit 0. This is the
  foundation every other stealth phase imports — do it first. (commit 67f60ad)
- [x] Phase 2: Pre-load the Neuralis brain with the sentinel-desktop knowledge base
  — created scripts/seed_brain.py and successfully persisted v18-v22 architecture,
  grind-loop coordination protocol, and fleet topology to the brain (neurons 8891,
  8892, 8893). All fleet agents can now recall this knowledge. (commit 223d07b)
- [x] Phase 1: Design the deferred fully-stealth humanization tier — wrote
  comprehensive 1160-line design spec covering biometric profiles, Fitts's-Law,
  overshoot/correction, error injection, scroll momentum, attention simulation,
  and pluggable detector-evasion pipeline. Design-only, no code. (commit ff9f7e8)
- [x] Phase 0: v18-v22 shipped, red suite repaired (51 → 0 failures from the
  ExecutorConfig refactor), CLAUDE.md v18 section corrected. (commit 1e48802, 8f3ebb5)
