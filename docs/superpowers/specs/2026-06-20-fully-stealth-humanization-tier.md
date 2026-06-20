# Design Spec — Fully-Stealth Humanization Tier (Sentinel Desktop v23.x+)

**Status:** Design only — deferred until naturalistic engine proves out in the field.
**Date:** 2026-06-20
**Author:** Sentinel (design) / Brandon (product)
**Cross-references:**
  - `docs/superpowers/notes/future-stealth-mode.md` (original vision capture)
  - `docs/superpowers/specs/2026-06-18-humanization-engine-design.md` (naturalistic tier, shipped in v18.x)

---

## Overview

Elevate Sentinel's input from **naturalistic** to **indistinguishable from a human operator under adversarial inspection**. The naturalistic engine (v18.x) defeats naive timing heuristics and looks human to the eye; this stealth tier defeats **behavioral biometrics** and **ML-based anti-bot detection** deployed in remote-control tools (ScreenConnect, NinjaOne, ConnectWise) and endpoint protection platforms.

### Target level: ADVERSARIAL STEALTH — not just naturalistic

This phase delivers **adversarial** humanization: per-operator biometric profiles, Fitts's-Law-accurate targeting, realistic error patterns, scroll momentum, and attention simulation. This is the plateau beyond naturalistic — the tier that defeats detectors trained on robotic fingerprints.

### Threat model

**What we're defeating:**
- **Behavioral biometric classifiers** — ML models trained on typing cadence (inter-key timing distributions, burst patterns, error+correction signatures), mouse dynamics (curvature, velocity peaks, acceleration profiles), and eye-gaze proxies (attention drift, re-reads, hesitation).
- **Fitts's-Law detectors** — systems that flag movements violating the time-to-target relationship (distance + target size → realistic movement duration).
- **Anti-automation heuristics** — checks for "too perfect" targeting (zero jitter), instant scroll (no momentum), error-free typing (no backspace), and mechanical rhythm (constant cadence).

**What we're NOT defeating:**
- **Low-level OS telemetry** — process injection, driver-level hooks, kernel callbacks. That's a different domain (stealth input via PostMessage already helps; full kernel evasion is out of scope).
- **Human-in-the-loop verification** — if a human manually watches the session and interviews the operator, no behavioral layer saves you. That's a social engineering problem.

### Honest constraint

Stealth is **asymptotic**. A determined adversary with a long session recording and a model trained on YOUR specific operator can eventually distinguish. This tier raises the bar from "obviously robotic" to "requires adversary-specific model training + long observation window." We design to that honest goal.

### Decisions already made (do not re-litigate)

- **Biometric profiles MUST be sampled from real human operators** — not synthetic distributions. A "fake human" distribution is itself a fingerprint.
- **Fitts's-Law MUST include target-width timing** — distance alone is naturalistic-tier; distance+ID (index of difficulty) is stealth-tier.
- **Overshoot + correction is mandatory** — humans don't pixel-perfect small targets; we undershoot/overshoot and sweep-back.
- **Error injection is mandatory** — real operators mistype and backspace; error-free typing is a robotic fingerprint.
- **Scroll momentum is mandatory** — discrete line jumps are mechanical; inertial scrolling is human.
- **No new dependencies.** Pure-Python math (bezier, spline, sampled distributions) + the seeded RNG. No numpy, no biometric libraries.

---

## Architecture

The stealth tier extends the naturalistic engine via the **Profile interface** — a `StealthProfile` subclasses `Profile` and overrides fields with biometric-sampled values. The chokepoints (`core/desktop.py`, `core/stealth_input.py`) remain unchanged; the stealth layer plugs in via the profile interface.

```
   action_executor._click / _type_text / ...
        │
        ├── stealth path ──▶ stealth_input.post_click / post_text
        │                        │
        │                        └─▶ core/humanize/typing.py (typing cadence)
        │                             core/humanize/timing.py (click hold, think-bump)
        │                             core/humanize/errors.py (ERROR/CORR injection) [NEW]
        │                             core/humanize/attention.py (attention drift) [NEW]
        │
        └── physical path ──▶ desktop.DesktopController.click / move_to / type_text
                                    │
                                    ├─▶ core/humanize/motion.py (bezier path + easing)
                                    │     core/humanize/overshoot.py (overshoot+correction) [NEW]
                                    │     core/humanize/fitts.py (Fitts's-Law timing) [NEW]
                                    │
                                    ├─▶ core/humanize/typing.py (typing cadence)
                                    │     core/humanize/errors.py (ERROR/CORR injection) [NEW]
                                    │
                                    └─▶ core/humanize/scroll.py (inertial scroll) [NEW]
                                          core/humanize/attention.py (attention drift) [NEW]
                                    │
                                    └─▶ core/humanize/profile.py
                                          └─▶ StealthProfile (biometric-sampled fields) [NEW]
```

**Key architectural principle:** **ZERO changes to the chokepoints.** The stealth layer is pure addition — new modules, a new Profile subclass, and opt-in via `SENTINEL_HUMANIZE_PROFILE=stealth`. The naturalistic tier remains the default.

---

## Components

### `core/humanize/profile.py` — StealthProfile extension

**Add to existing file:**

```python
@dataclass(frozen=True)
class StealthProfile(Profile):
    """Biometric-sampled tempo profile for adversarial stealth.

    Extends Profile with stealth-specific fields:
    - fitts_width_scaling:  how strongly target width affects move time
    - overshoot_probability: chance of undershooting/overshooting small targets
    - error_rate:            mistypes per 100 keystrokes
    - correction_delay_s:    mean backspace-to-retype latency
    - scroll_momentum:       inertial scroll decay rate
    - attention_drift_s:    mean duration of "gaze-like" pauses
    - biometric_id:          identifier of the sampled human operator

    All fields are sampled from real human operators (see
    core/humanize/biometric_sampler.py). DO NOT invent synthetic values.
    """

    # Fitts's-Law target-width sensitivity (1.0 = naturalistic, 1.5-2.5 = stealth)
    fitts_width_scaling: float = 2.0

    # Overshoot + correction
    overshoot_probability: float = 0.35
    sweep_back_speed: float = 0.7  # multiplier for correction move speed

    # Error + correction injection
    error_rate: float = 3.0  # errors per 100 keystrokes
    error_delay_s: float = 0.18  # mean delay before backspace
    correction_delay_s: float = 0.22  # mean backspace-to-retype latency

    # Scroll momentum
    scroll_momentum: float = 0.85  # decay factor (0.0 = instant stop, 1.0 = never stop)
    scroll_jitter_px: float = 1.2  # per-frame position jitter during momentum scroll

    # Attention drift + dwell
    attention_drift_probability: float = 0.08  # chance of a "gaze pause" per action
    attention_drift_duration_s: float = 0.6  # mean duration of attention pauses
    re_read_probability: float = 0.04  # chance of re-reading a field before typing

    # Biometric provenance
    biometric_id: str = "unknown"  # operator identifier from sampling session

    name: str = "stealth"
```

**Add preset:**

```python
STEALTH: StealthProfile = StealthProfile(
    name="stealth",
    biometric_id="sampled-population-median"  # Default: median of sampled operators
)
"""Stealth profile sampled from real human operators."""

# Update the preset registry
_PRESETS: dict[str, Profile] = {
    "naturalistic": NATURALISTIC,
    "fast": FAST,
    "stealth": STEALTH,  # NEW
}
```

**Why frozen dataclass:** Immutability ensures profiles can't be modified at runtime (no accidental state leaks). The stealth tier is no different.

---

### `core/humanize/biometric_sampler.py` — collect real operator samples

**New file.**

**Purpose:** Collect typing cadence, mouse dynamics, and scroll behavior from real human operators during normal IT support tasks. These samples become the ground truth for `StealthProfile` field values.

**Sampling protocol:**

```python
"""Capture biometric samples from real operators during IT tasks.

Run via: python -m core.humanize.biometric_sampler --duration 600 --operator-id OPERATOR_001

Outputs ~/.sentinel/biometrics/OPERATOR_001_2026-06-20.jsonl with one line per action:
    {"timestamp": "...", "action": "click", "position": [100, 200], "target_size": [20, 10], ...}
    {"timestamp": "...", "action": "type", "text": "password", "keystrokes": [...], ...}
    {"timestamp": "...", "action": "scroll", "delta_px": 120, "momentum_samples": [...], ...}

Sampling session MUST cover:
- At least 100 mouse movements to varied target sizes (buttons, fields, icons).
- At least 1,000 keystrokes across different contexts (passwords, emails, notes).
- At least 50 scroll events (short flicks, long swipes, continuous drag).
- Natural error-correction sequences (mistype → backspace → retype).

DO NOT cherry-pick. Sample real work, not demo patterns.
"""
```

**Output format:** JSONL (one JSON object per line) with timestamps and high-resolution timings (microseconds). Each line is a single action with raw sensor data.

**Post-sampling analysis:**

```python
def analyze_samples(jsonl_path: str) -> BiometricStatistics:
    """Extract statistics from a sampling session.

    Returns:
        BiometricStatistics dataclass with:
        - mean_keystroke_s, keystroke_std_s (log-normal fit)
        - mean_move_duration_s_by_target_size (dict of {target_area: duration})
        - fitts_width_scaling_coefficient (regression: ID → time)
        - overshoot_rate_by_target_size (dict)
        - error_rate (per 100 keystrokes)
        - mean_correction_delay_s
        - scroll_momentum_decay_rate (exponential fit)
        - attention_drift_probability (empirical)

    These statistics become the field values for a StealthProfile.
    """
```

**Privacy:** Samples are stored locally (`~/.sentinel/biometrics/`) and NEVER transmitted. Operators opt-in to sampling; samples are anonymized (operator ID only, no usernames/passwords captured).

**Why sampling, not synthetic distributions:** Real human operators have non-obvious patterns (e.g., slower typing on password fields due to subconscious caution, faster clicks on large buttons, specific error-correction latencies). Synthetic distributions miss these nuances and become their own fingerprint.

---

### `core/humanize/fitts.py` — Fitts's-Law targeting time

**New file.**

**Purpose:** Implement Fitts's Law — movement time scales with **both distance AND target width**. Small targets (e.g., a 16×16 icon) require longer, more careful movements than large targets (e.g., a 200×40 button), even at the same distance.

**Naturalistic tier (existing):** Distance-only timing (`_total_duration` in `motion.py`). Target size is ignored.

**Stealth tier:** Distance + target width via the **Index of Difficulty (ID)**:

```
ID = log2(2 * distance / target_width)
time = a + b * ID
```

Where:
- `distance` = pixels from start to target center
- `target_width` = effective width (smaller dimension for rectangular targets)
- `a`, `b` = coefficients fitted from biometric samples (see `biometric_sampler.py`)
- `target_width` is clamped to a minimum (e.g., 5px) to avoid division-by-zero

**Algorithm:**

```python
def fitts_move_duration(
    start: tuple[int, int],
    target: tuple[int, int],
    target_size: tuple[int, int],  # (width, height) in pixels
    *,
    rng: random.Random,
    profile: Profile | StealthProfile,
) -> float:
    """Return movement duration (seconds) from Fitts's Law.

    Args:
        start: Current cursor position.
        target: Intended target position.
        target_size: Target dimensions (width, height) in pixels.
        rng: Seeded random.Random.
        profile: Tempo profile (must be StealthProfile for Fitts's-Law).

    Returns:
        Duration in seconds. Falls back to distance-only timing if profile
        is not a StealthProfile or target_size is unavailable.
    """
    if not isinstance(profile, StealthProfile):
        # Fall back to naturalistic timing
        return motion._total_duration(distance, profile)

    # Compute effective width (smaller dimension for rectangular targets)
    width = min(target_size[0], target_size[1])
    width = max(width, 5.0)  # Avoid pathological values for tiny targets

    # Index of Difficulty
    distance_px = math.hypot(target[0] - start[0], target[1] - start[1])
    id = math.log2(2.0 * distance_px / width)

    # Fitts's-Law with sampled coefficients (default: fit from population median)
    # a ≈ 0.05s (intercept), b ≈ 0.10s (slope) — calibrated from biometric samples
    a = 0.05
    b = 0.10 * profile.fitts_width_scaling

    # Add jitter (humans aren't perfectly Fittsian)
    jitter = rng.gauss(0.0, 0.02)
    return max(0.0, a + b * id + jitter)
```

**Integration with existing `motion.py`:**

Modify `humanized_path` to accept optional `target_size` and route through `fitts_move_duration` when profile is `StealthProfile`:

```python
def humanized_path(
    start: tuple[int, int],
    target: tuple[int, int],
    target_size: tuple[int, int] | None = None,  # NEW
    *,
    rng: random.Random,
    profile: Profile,
) -> list[tuple[tuple[float, float], float]]:
    # ... existing code ...

    # Replace _total_duration call with:
    if target_size and isinstance(profile, StealthProfile):
        total = fitts_move_duration(start, target, target_size, rng=rng, profile=profile)
    else:
        total = _total_duration(length, profile)
```

**Why Fitts's-Law:** It's the gold standard for human movement time. Violations (e.g., fast movements to small targets) are robotic fingerprints. ML detectors flag this.

**Why optional `target_size`:** Not all actions have known target dimensions (e.g., clicks on canvas, arbitrary coordinates). Graceful degrade to distance-only timing when unavailable.

---

### `core/humanize/overshoot.py` — overshoot + sweep-back correction

**New file.**

**Purpose:** Humans don't pixel-perfect targets — especially small ones. We undershoot or overshoot slightly, then sweep-back with a micro-correction. This natural behavior is MISSING from the naturalistic tier (which only adds Gaussian landing jitter).

**Algorithm:**

```python
def apply_overshoot_and_correction(
    target: tuple[int, int],
    target_size: tuple[int, int],
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> tuple[tuple[float, float], tuple[float, float] | None]:
    """Generate overshoot/correction trajectory for a single movement.

    Args:
        target: Intended target position.
        target_size: Target dimensions (width, height) in pixels.
        rng: Seeded random.Random.
        profile: StealthProfile with overshoot_probability.

    Returns:
        (overshoot_landing, correction_target) tuple:
        - overshoot_landing: The point we intentionally miss by (undershoot or overshoot).
        - correction_target: None if no overshoot this time; otherwise the point to
          sweep-back to (typically the true target center).

    Overshoot is MORE likely for small targets:
    - Large targets (>5000 px²): 10% overshoot rate
    - Medium targets (1000-5000 px²): 30% overshoot rate
    - Small targets (<1000 px²): 60% overshoot rate

    Undershoot vs overshoot is 50/50 (humans do both).
    """
    if not isinstance(profile, StealthProfile):
        return (float(target[0]), float(target[1])), None

    target_area = target_size[0] * target_size[1]

    # Small targets → more overshoot
    if target_area < 1000:
        overshoot_prob = 0.60
    elif target_area < 5000:
        overshoot_prob = 0.30
    else:
        overshoot_prob = 0.10

    if rng.random() > overshoot_prob:
        return (float(target[0]), float(target[1])), None

    # Undershoot (short) vs overshoot (long) — 50/50
    is_overshoot = rng.choice([True, False])

    # Magnitude scales with target size (larger targets → larger miss)
    # Typical miss: 5-15px for small targets, 15-30px for large
    miss_magnitude = rng.uniform(5.0, min(target_size[0], target_size[1]) * 0.15)

    # Direction: random angle
    angle = rng.uniform(0.0, 2.0 * math.pi)
    miss_x = math.cos(angle) * miss_magnitude
    miss_y = math.sin(angle) * miss_magnitude

    if is_overshoot:
        # Land beyond the target
        overshoot_landing = (target[0] + miss_x, target[1] + miss_y)
    else:
        # Land short of the target
        overshoot_landing = (target[0] - miss_x, target[1] - miss_y)

    # Correction target: sweep-back to the true target (jittered)
    correction_jitter = rng.gauss(0.0, 2.0)
    correction_target = (target[0] + correction_jitter, target[1] + correction_jitter)

    return overshoot_landing, correction_target
```

**Integration with `motion.py`:**

Modify `humanized_path` to detect overshoot and emit a TWO-SEGMENT trajectory:

```python
def humanized_path(
    start: tuple[int, int],
    target: tuple[int, int],
    target_size: tuple[int, int] | None = None,
    *,
    rng: random.Random,
    profile: Profile,
) -> list[tuple[tuple[float, float], float]]:
    # ... existing code up to landing point calculation ...

    # NEW: Check for overshoot
    if target_size and isinstance(profile, StealthProfile):
        overshoot_landing, correction_target = apply_overshoot_and_correction(
            target, target_size, rng=rng, profile=profile
        )
        if correction_target is not None:
            # TWO movements: start → overshoot → correction
            trajectory_segment_1 = _build_trajectory(start, overshoot_landing, rng, profile)
            trajectory_segment_2 = _build_trajectory(overshoot_landing, correction_target, rng, profile)

            # Combine with a tiny dwell at the overshoot point (human reorients)
            trajectory = trajectory_segment_1 + [((overshoot_landing[0], overshoot_landing[1]), 0.02)]
            trajectory += trajectory_segment_2
            return trajectory

    # ... existing single-segment trajectory code ...
```

**Why overshoot + correction:** Naturalistic landing jitter is a Gaussian scatter — we land NEAR the target. Real humans undershoot/overshoot and THEN correct. That two-phase pattern is a strong human signal.

---

### `core/humanize/errors.py` — error + self-correction injection

**New file.**

**Purpose:** Inject realistic typing errors and corrections. Real operators mistype, notice, backspace, and retype. Error-free typing is a robotic fingerprint.

**Algorithm:**

```python
def inject_errors_and_corrections(
    text: str,
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> list[tuple[str, float]]:
    """Return a sequence of (typed_text, delay) actions with injected errors.

    Args:
        text: The intended final text.
        rng: Seeded random.Random.
        profile: StealthProfile with error_rate, error_delay_s, correction_delay_s.

    Returns:
        List of (typed_text, delay_s) tuples. Each entry is either:
        - A correct character (typo-free segment) with normal keystroke delay.
        - A mistyped character + backspace + correction with error-specific delays.

    Example:
        Input text: "password"
        Output: [
            ("passw", 0.12),  # Correct segment
            ("q", 0.18),      # Mistype
            ("", 0.22),       # Pause before backspace
            ("\b", 0.10),     # Backspace
            ("", 0.15),       # Pause before retype
            ("ord", 0.12),    # Correction + rest of word
        ]
    """
    if not isinstance(profile, StealthProfile):
        # No errors for naturalistic profile
        return [(text, 0.0)]

    error_prob = profile.error_rate / 100.0  # Convert to per-keystroke probability
    result: list[tuple[str, float]] = []
    current_segment = ""
    base_keystroke_delay = profile.mean_keystroke_s

    for i, char in enumerate(text):
        # Should we inject an error here?
        if rng.random() < error_prob and i > 0:  # Don't error on first character
            # Emit the correct segment so far
            if current_segment:
                result.append((current_segment, base_keystroke_delay * len(current_segment)))
                current_segment = ""

            # Choose error type:
            # 40%: adjacent key (QWERTY proximity)
            # 30%: shifted character (wrong case)
            # 20%: skipped character
            # 10%: random wrong character
            error_type = rng.choices(
                ["adjacent", "shifted", "skip", "random"],
                weights=[0.40, 0.30, 0.20, 0.10]
            )[0]

            if error_type == "adjacent":
                mistyped_char = _adjacent_key_mistype(char, rng)
            elif error_type == "shifted":
                mistyped_char = char.swapcase()
            elif error_type == "skip":
                mistyped_char = ""  # Type nothing
            else:  # random
                mistyped_char = rng.choice(string.ascii_letters + string.digits)

            # Type the error
            result.append((mistyped_char, base_keystroke_delay))

            # Pause before noticing the error (subconscious detection delay)
            notice_delay = rng.gauss(profile.error_delay_s, 0.05)
            result.append(("", max(0.0, notice_delay)))

            # Backspace (may need multiple if error was multiple chars)
            backspace_count = len(mistyped_char) if mistyped_char else 1
            for _ in range(backspace_count):
                result.append(("\b", profile.mean_keystroke_s * 0.8))  # Backspace is faster

            # Pause before retype
            correction_delay = rng.gauss(profile.correction_delay_s, 0.06)
            result.append(("", max(0.0, correction_delay)))

            # Now type the correct character (retry)
            result.append((char, base_keystroke_delay))
        else:
            current_segment += char

    # Emit remaining segment
    if current_segment:
        result.append((current_segment, base_keystroke_delay * len(current_segment)))

    return result

def _adjacent_key_mistype(char: str, rng: random.Random) -> str:
    """Return a physically adjacent key on QWERTY keyboard."""
    # Simplified adjacency map (most common keys)
    adjacency = {
        'a': ['q', 'w', 's', 'z', 'x'],
        's': ['a', 'w', 'e', 'd', 'z', 'x'],
        # ... (full QWERTY map)
    }
    if char.lower() in adjacency:
        return rng.choice(adjacency[char.lower()])
    return char  # No adjacency data, no mistype
```

**Integration with `typing.py`:**

Modify `keystroke_delays` to accept optional `errors: bool` flag and route through `inject_errors_and_corrections` when `errors=True` and profile is `StealthProfile`:

```python
def keystroke_delays(
    text: str,
    *,
    rng: random.Random,
    profile: Profile,
    errors: bool = False,  # NEW
) -> list[float]:
    """Return per-keystroke inter-key delays with optional error injection.

    Args:
        text: The string that will be typed.
        rng: Seeded random.Random.
        profile: Tempo profile.
        errors: If True, inject errors for StealthProfile (naturalistic tier ignores).

    Returns:
        list[float] of inter-key delays. Length matches len(text) when errors=False;
        longer when errors=True (backspace and corrections add delays).
    """
    if errors and isinstance(profile, StealthProfile):
        error_actions = inject_errors_and_corrections(text, rng=rng, profile=profile)
        # Convert (typed_text, delay) → flat delay list
        # This requires coordination with the executor to handle backspaces
        # See the "Executor integration" section below.
        return _extract_delays_from_error_actions(error_actions)

    # ... existing naturalistic code ...
```

**Executor integration:**

The executor (`action_executor._type_text`) needs to handle backspaces (`\b`) in the typed text. Current implementation passes `text` directly to `pyautogui.write` or `PostMessage` injection. Backspace support requires:

```python
def _type_text(text: str, **kwargs) -> dict:
    """Type text with optional backspace corrections."""
    # If text contains '\b', split into segments and send individual key events
    if '\b' in text:
        segments = text.split('\b')
        for i, seg in enumerate(segments):
            if seg:  # Type the segment
                _send_key_events(seg, **kwargs)
            if i < len(segments) - 1:  # Send backspace
                _send_key_events('{BACKSPACE}', **kwargs)
    else:
        _send_key_events(text, **kwargs)
```

**Why error injection:** Perfect typing is robotic. Real humans have error rates (typically 1-5% for experienced operators, higher for complex passwords). ML detectors flag zero-error streams.

---

### `core/humanize/scroll.py` — inertial scroll momentum

**New file.**

**Purpose:** Implement inertial scrolling — when a user "flicks" the scroll wheel, the content continues scrolling with momentum, not a discrete line jump. Mechanical scroll (fixed delta per click) is robotic.

**Algorithm:**

```python
def momentum_scroll_trajectory(
    initial_delta_px: int,
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> list[tuple[int, float]]:
    """Generate a momentum scroll trajectory (pixel deltas, frame durations).

    Args:
        initial_delta_px: The initial scroll delta (from scroll wheel event).
        rng: Seeded random.Random.
        profile: StealthProfile with scroll_momentum, scroll_jitter_px.

    Returns:
        List of (delta_px, dwell_s) tuples. Each entry is one scroll "frame":
        - delta_px: Pixels to scroll in this frame (decays over time).
        - dwell_s: How long to wait before the next frame.

    The trajectory follows exponential decay:
        delta[t] = delta[0] * momentum^t

    With per-frame jitter to simulate mechanical imperfection.
    """
    if not isinstance(profile, StealthProfile):
        # Naturalistic tier: single discrete scroll
        return [(initial_delta_px, 0.0)]

    momentum = max(0.0, min(1.0, profile.scroll_momentum))
    trajectory: list[tuple[int, float]] = []

    current_delta = float(initial_delta_px)
    frame_count = 0

    while abs(current_delta) > 1.0:  # Continue until delta < 1px
        # Add jitter (mechanical imperfection)
        jitter = rng.gauss(0.0, profile.scroll_jitter_px)
        frame_delta = current_delta + jitter

        # Frame dwell: shorter for fast initial frames, longer as we slow down
        # (16ms = 60fps, 33ms = 30fps — human visual smoothness)
        frame_dwell = 0.016 + (frame_count * 0.004)

        trajectory.append((int(frame_delta), frame_dwell))

        # Decay for next frame
        current_delta *= momentum
        frame_count += 1

        # Safety cap: never emit more than 60 frames (1 second of momentum)
        if frame_count >= 60:
            break

    return trajectory
```

**Integration with executor:**

The executor (`action_executor._scroll`) needs to handle multi-frame momentum scrolls. Current implementation sends a single scroll event. Momentum support requires:

```python
def _scroll(delta: int, **kwargs) -> dict:
    """Scroll with inertial momentum (stealth tier)."""
    profile = get_default_profile()

    if isinstance(profile, StealthProfile):
        trajectory = momentum_scroll_trajectory(delta, rng=get_rng(), profile=profile)
        total_scrolled = 0
        for frame_delta, dwell in trajectory:
            _send_scroll_event(frame_delta, **kwargs)
            total_scrolled += frame_delta
            if dwell > 0:
                time.sleep(dwell)
        return {"success": True, "scrolled": total_scrolled}
    else:
        # Naturalistic tier: single discrete scroll
        _send_scroll_event(delta, **kwargs)
        return {"success": True, "scrolled": delta}
```

**Why momentum:** Mechanical scroll (fixed 120px per wheel click) is a robotic fingerprint. Real scroll wheels have physical inertia — the content keeps moving. ML detectors flag "perfectly linear" scroll patterns.

---

### `core/humanize/attention.py` — attention drift + dwell

**New file.**

**Purpose:** Simulate human attention patterns — occasional "gaze-like" pauses, re-reading ambiguous fields, hesitation before critical actions. Humans don't execute at a constant tempo; we pause, re-read, and second-guess.

**Algorithm:**

```python
def attention_pause(
    action_context: str,  # e.g., "clicking_submit_button", "typing_password"
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> tuple[bool, float]:
    """Determine whether to insert an attention pause before an action.

    Args:
        action_context: Human-readable description of the action (used for
                       context-aware pauses, e.g., higher probability before
                       destructive actions like "delete_account").
        rng: Seeded random.Random.
        profile: StealthProfile with attention_drift_probability, etc.

    Returns:
        (should_pause, pause_duration_s) tuple.

    Pause probability is context-aware:
    - Baseline: profile.attention_drift_probability (0.08 = 8%)
    - Destructive actions (delete, submit, confirm): 2× baseline
    - Password/credential fields: 1.5× baseline
    - Repetitive actions (clicking same button 3×): 0.5× baseline (flow state)
    """
    if not isinstance(profile, StealthProfile):
        return (False, 0.0)

    base_prob = profile.attention_drift_probability

    # Context-aware adjustment
    if any(keyword in action_context.lower() for keyword in ["delete", "destroy", "confirm"]):
        prob = base_prob * 2.0
    elif any(keyword in action_context.lower() for keyword in ["password", "credential", "secret"]):
        prob = base_prob * 1.5
    elif "repetitive" in action_context.lower():
        prob = base_prob * 0.5
    else:
        prob = base_prob

    if rng.random() < prob:
        # Sample duration from profile with jitter
        duration = rng.gauss(profile.attention_drift_duration_s, 0.15)
        return (True, max(0.0, duration))

    return (False, 0.0)

def re_read_pause(
    field_type: str,  # e.g., "email", "password", "username"
    *,
    rng: random.Random,
    profile: StealthProfile,
) -> tuple[bool, float]:
    """Determine whether to pause before re-reading a field (typing hesitation).

    Args:
        field_type: Type of field being typed into (context-aware).
        rng: Seeded random.Random.
        profile: StealthProfile with re_read_probability.

    Returns:
        (should_pause, pause_duration_s) tuple.

    Re-reading is more common for:
    - Password fields (operators double-check for typos)
    - Email fields (operators verify accuracy)
    - Unknown/ambiguous fields (operators pause to understand)
    """
    if not isinstance(profile, StealthProfile):
        return (False, 0.0)

    base_prob = profile.re_read_probability

    # Context-aware
    if field_type.lower() in ["password", "email"]:
        prob = base_prob * 2.0
    elif field_type.lower() in ["username", "phone"]:
        prob = base_prob * 1.5
    else:
        prob = base_prob

    if rng.random() < prob:
        duration = rng.gauss(0.4, 0.10)  # Shorter than general attention pause
        return (True, max(0.0, duration))

    return (False, 0.0)
```

**Integration with executor:**

The executor (`action_executor`) needs to call `attention_pause` before each action and insert the pause if triggered:

```python
def _click(target: tuple[int, int], **kwargs) -> dict:
    """Click with optional attention pause."""
    profile = get_default_profile()

    if isinstance(profile, StealthProfile):
        should_pause, duration = attention_pause(
            f"clicking_at_{target[0]}_{target[1]}",
            rng=get_rng(),
            profile=profile
        )
        if should_pause:
            time.sleep(duration)

    # ... existing click implementation ...
```

For typing, insert `re_read_pause` before typing into sensitive fields:

```python
def _type_text(text: str, field_type: str = "unknown", **kwargs) -> dict:
    """Type text with optional re-read pause."""
    profile = get_default_profile()

    if isinstance(profile, StealthProfile):
        should_pause, duration = re_read_pause(field_type, rng=get_rng(), profile=profile)
        if should_pause:
            time.sleep(duration)

    # ... existing type implementation ...
```

**Why attention simulation:** Constant action tempo is robotic. Humans pause, re-read, and hesitate. ML detectors flag "machine-like" rhythm.

---

### `core/humanize/detector_evasion.py` — pluggable detector-evasion layer

**New file.**

**Purpose:** Abstract the detector-evasion logic so new anti-bot heuristics can be countered WITHOUT rewriting the core engine. This is the "pluggable layer" mentioned in the original vision.

**Design:**

```python
"""Pluggable detector-evasion strategies.

Each strategy is a callable that modifies the humanization trajectory based
on the perceived threat model. Strategies are composed into a pipeline.

Example:
    strategies = [
        FittsLawStrategy(),
        OvershootStrategy(),
        ErrorInjectionStrategy(),
        MomentumScrollStrategy(),
        AttentionSimulationStrategy(),
    ]
    pipeline = DetectorEvasionPipeline(strategies)

    pipeline.apply(action="click", context={...}, trajectory=trajectory)

New strategies can be added without modifying core modules.
"""

class DetectorEvasionStrategy(ABC):
    """Base class for detector-evasion strategies."""

    @abstractmethod
    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: random.Random,
        profile: StealthProfile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Modify the trajectory to evade a specific detector class.

        Args:
            action: Action type (e.g., "click", "type", "scroll").
            context: Action metadata (target size, field type, etc.).
            trajectory: Current humanized trajectory.
            rng: Seeded random.Random.
            profile: StealthProfile.

        Returns:
            Modified trajectory (may be the same object if no changes).
        """
        pass

class FittsLawStrategy(DetectorEvasionStrategy):
    """Apply Fitts's-Law timing to movements."""

    def apply(self, action, context, trajectory, *, rng, profile):
        if action not in ["click", "move"]:
            return trajectory

        target_size = context.get("target_size", None)
        if not target_size:
            return trajectory

        # Re-calculate trajectory with Fittsian timing
        # (This calls into fitts.py internally)
        return _apply_fitts_timing(trajectory, target_size, rng=rng, profile=profile)

class OvershootStrategy(DetectorEvasionStrategy):
    """Inject overshoot + correction for small targets."""

    def apply(self, action, context, trajectory, *, rng, profile):
        if action not in ["click", "move"]:
            return trajectory

        target_size = context.get("target_size", None)
        if not target_size:
            return trajectory

        # Re-calculate trajectory with overshoot
        # (This calls into overshoot.py internally)
        return _apply_overshoot(trajectory, target_size, rng=rng, profile=profile)

class DetectorEvasionPipeline:
    """Compose multiple strategies into a single pipeline."""

    def __init__(self, strategies: list[DetectorEvasionStrategy]):
        self.strategies = strategies

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: random.Random,
        profile: StealthProfile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply all strategies in sequence."""
        result = trajectory
        for strategy in self.strategies:
            result = strategy.apply(action, context, result, rng=rng, profile=profile)
        return result

# Default pipeline for stealth mode
DEFAULT_STEALTH_PIPELINE = DetectorEvasionPipeline([
    FittsLawStrategy(),
    OvershootStrategy(),
    ErrorInjectionStrategy(),
    MomentumScrollStrategy(),
    AttentionSimulationStrategy(),
])
```

**Integration with executor:**

The executor calls the pipeline BEFORE executing the action:

```python
def _click(target: tuple[int, int], target_size: tuple[int, int] | None = None, **kwargs) -> dict:
    """Click with full stealth pipeline."""
    profile = get_default_profile()

    if isinstance(profile, StealthProfile):
        # Generate base trajectory
        base_trajectory = humanized_path(
            start=get_cursor_position(),
            target=target,
            target_size=target_size,
            rng=get_rng(),
            profile=profile,
        )

        # Apply detector-evasion pipeline
        final_trajectory = DEFAULT_STEALTH_PIPELINE.apply(
            action="click",
            context={"target_size": target_size or (0, 0)},
            trajectory=base_trajectory,
            rng=get_rng(),
            profile=profile,
        )

        # Execute the final trajectory
        _execute_trajectory(final_trajectory)
    else:
        # Naturalistic tier: use existing path
        trajectory = humanized_path(start=get_cursor_position(), target=target, rng=get_rng(), profile=profile)
        _execute_trajectory(trajectory)

    return {"success": True}
```

**Why pluggable:** New anti-bot heuristics appear constantly. A monolithic `humanized_path` function requires deep changes for each new detector. A pluggable pipeline lets us add `ScreenConnect2027EvasionStrategy` without touching the core.

---

## Deliverables

### Code changes

1. **`core/humanize/profile.py`** — Add `StealthProfile` dataclass and `STEALTH` preset.
2. **`core/humanize/biometric_sampler.py`** — NEW. Sample real operators, extract statistics.
3. **`core/humanize/fitts.py`** — NEW. Fitts's-Law timing (distance + target width).
4. **`core/humanize/overshoot.py`** — NEW. Overshoot + sweep-back correction.
5. **`core/humanize/errors.py`** — NEW. Error + correction injection.
6. **`core/humanize/scroll.py`** — NEW. Inertial scroll momentum.
7. **`core/humanize/attention.py`** — NEW. Attention drift + re-read pauses.
8. **`core/humanize/detector_evasion.py`** — NEW. Pluggable strategy pipeline.
9. **`core/humanize/motion.py`** — Modify `humanized_path` to accept `target_size` and route through stealth modules when profile is `StealthProfile`.
10. **`core/humanize/typing.py`** — Modify `keystroke_delays` to accept `errors: bool` flag and route through `errors.py`.
11. **`core/action_executor.py`** — Modify `_click`, `_type_text`, `_scroll` to pass context (target_size, field_type, action_context) to stealth modules.
12. **`core/desktop.py`** — Modify physical chokepoint to use `fitts_move_duration` when profile is `StealthProfile`.

### Tests

**`tests/test_humanize_stealth_*.py`** — New test files:

1. **`tests/test_humanize_stealth_profile.py`** — Test `StealthProfile` instantiation, field validation, preset registry.
2. **`tests/test_humanize_fitts.py`** — Test Fitts's-Law timing calculations (ID computation, duration scaling, edge cases).
3. **`tests/test_humanize_overshoot.py`** — Test overshoot probability scaling with target size, undershoot vs overshoot distribution.
4. **`tests/test_humanize_errors.py`** — Test error injection rates, backspace handling, correction delays.
5. **`tests/test_humanize_scroll.py`** — Test momentum decay, jitter, frame count caps.
6. **`tests/test_humanize_attention.py`** — Test attention pause probability, context-aware scaling, re-read pauses.
7. **`tests/test_humanize_detector_evasion.py`** — Test pipeline composition, strategy ordering, idempotence.
8. **`tests/test_humanize_stealth_integration.py`** — End-to-end tests: full click/type/scroll actions with `StealthProfile`, verify trajectory structure, timing correctness, and backspace execution.

**Test coverage requirement:** ≥95% for all new stealth modules (matching the naturalistic tier standard).

### Documentation

1. **`docs/superpowers/specs/2026-06-20-fully-stealth-humanization-tier.md`** — This spec (design-only).
2. **`docs/superpowers/guides/stealth-profile-sampling-guide.md`** — NEW. Guide for operators: how to run a sampling session, what tasks to perform, how to interpret the resulting `StealthProfile`.
3. **`docs/superpowers/guides/stealth-mode-activation.md`** — NEW. Guide for users: how to enable stealth mode (`SENTINEL_HUMANIZE_PROFILE=stealth`), what to expect, performance impact.
4. **`CLAUDE.md`** — Update "What To Do" section: add "Future work: stealth tier" with reference to this spec.

### Biometric sample dataset

**`~/.sentinel/biometrics/sample-population-median.json`** — A default `StealthProfile` derived from a median aggregate of at least 5 sampled operators. This ensures stealth mode works out-of-the-box without requiring each user to run their own sampling session.

**Sampling protocol for the default dataset:**
- Recruit 5+ experienced IT support technicians.
- Each operator performs a 30-minute sampling session covering realistic tasks: password resets, ticket updates, remote desktop connections, log analysis.
- Run `analyze_samples` on each session, extract statistics.
- Compute median values across operators for each `StealthProfile` field.
- Persist as `sample-population-median.json`.
- Ship with the distribution (checked into `profiles/stealth/`).

---

## Success Criteria

### Functional requirements

1. **`StealthProfile` subclasses `Profile`** — all naturalistic fields are overridable, no breaking changes to existing profiles.
2. **Fitts's-Law timing is accurate** — movement duration scales with distance AND target width; small targets take longer than large targets at the same distance.
3. **Oversoot + correction is observable** — for targets <1000 px², ≥50% of movements include overshoot and sweep-back.
4. **Error injection is realistic** — error rate matches `profile.error_rate` (±0.5% tolerance); backspace corrections execute correctly.
5. **Scroll momentum decays** — momentum scroll trajectory follows exponential decay; scroll stops after <60 frames.
6. **Attention pauses trigger** — attention pause probability matches `profile.attention_drift_probability` (±1% tolerance); context-aware scaling works (destructive actions → 2× probability).
7. **Detector-evasion pipeline is pluggable** — new strategies can be added without modifying core modules; pipeline composes correctly.
8. **Naturalistic tier is unchanged** — all existing tests pass; default behavior (NATURALISTIC profile) is identical to v18.x.

### Quality gates

1. **Zero lint errors** — `ruff check core/humanize/` passes clean.
2. **Test suite green** — `pytest tests/test_humanize*.py -q` returns exit 0; ≥95% coverage for new modules.
3. **No new dependencies** — `pip list` shows no new packages added.
4. **Backward compatibility** — existing user configs (NATURALISTIC, FAST profiles) work unchanged.
5. **Performance impact is acceptable** — stealth tier overhead ≤15% compared to naturalistic (measured via `tests/benchmark_humanize.py`).

### Design verification

1. **Profile interface is intact** — `StealthProfile` is a drop-in replacement for `Profile`; no changes to chokepoint call sites.
2. **Stealth-readiness debt is paid** — all deferred features from `docs/superpowers/notes/future-stealth-mode.md` are designed; no architectural blockers remain.
3. **Pluggable detector evasion works** — at least 2 new strategies can be added and composed without touching core code (verify via test).
4. **Biometric sampling is viable** — a 30-minute sampling session produces a valid `StealthProfile`; statistics are within human ranges.

---

## Open Questions / Trade-offs

### Q1: Should error injection be ON by default in stealth mode?

**Option A:** Yes — stealth mode means "fully human," including errors. Default `StealthProfile.error_rate = 3.0`.

**Option B:** No — errors introduce risk (mistyped passwords, corrupted inputs). Require explicit opt-in: `SENTINEL_STEALTH_INJECT_ERRORS=1`.

**Recommendation:** Option A with a safety guard. Error injection is CORE to stealth — error-free typing is a robotic fingerprint. However, add a **dangerous action whitelist**: NEVER inject errors when typing into password fields or executing destructive actions (delete, confirm). This preserves stealth for most actions while avoiding catastrophic failures.

**Decision:** Implement Option A with dangerous action whitelist.

### Q2: Should momentum scroll apply to ALL scroll events or only wheel events?

**Option A:** All scroll events (wheel, touchpad, drag scrollbar) get momentum.

**Option B:** Only wheel events get momentum; touchpad/drag are already "smooth" and don't need it.

**Recommendation:** Option B. Touchpad scrolling is already inertial (OS-level driver). Dragging a scrollbar is a direct manipulation gesture. Only mechanical wheel clicks benefit from momentum emulation. This reduces unnecessary complexity.

**Decision:** Implement Option B.

### Q3: How do we handle target_size for actions where it's unknown?

**Problem:** Not all actions have known target dimensions (e.g., clicks on canvas, arbitrary coordinates from LLM). Fitts's-Law and overshoot require `target_size`.

**Option A:** Require target_size for ALL actions — fail fast if missing.
**Option B:** Fall back to naturalistic timing when target_size is unavailable.
**Option C:** Infer target_size from UI element bounding box (requires UIA/AT-SPI queries).

**Recommendation:** Option B with graceful degrade. Fitts's-Law and overshoot are ENHANCEMENTS, not requirements. If target_size is unavailable, fall back to distance-only timing (naturalistic tier) and Gaussian landing jitter. This ensures stealth mode works for all actions, not just UI-aware ones.

**Decision:** Implement Option B.

### Q4: Should biometric sampling be mandatory for stealth mode?

**Option A:** Yes — stealth mode refuses to start without a custom biometric profile (`--biometric-profile ~/.sentinel/biometrics/MY_PROFILE.json`).
**Option B:** No — ship with a default "population median" profile; users can sample their own if they want.

**Recommendation:** Option B. Mandatory sampling creates a high barrier to entry. A population-median profile (sampled from 5+ operators) provides 80% of the stealth benefit with 0% friction. Power users can sample their own profile for the remaining 20%.

**Decision:** Implement Option B.

---

## Future Work (Out of Scope for This Phase)

1. **Per-session profile switching** — Allow the agent to switch profiles mid-session (e.g., NATURALISTIC for bulk data entry, STEALTH for sensitive actions). Requires executor-level profile API.
2. **ML-based detector classifier** — Train a model on known detectors (ScreenConnect, NinjaOne) and automatically select the best counter-strategy. Requires labeled dataset.
3. **Operator-specific fingerprinting resistance** — Analyze the operator's natural style and adapt the stealth profile to match. Requires real-time feedback loop.
4. **Cross-platform biometric sampling** — Sample operators on Windows, macOS, and Linux to capture platform-specific patterns (e.g., macOS users type slower due to different keyboard feel).
5. **Stealth mode analytics** — Track which strategies are most effective against which detectors (requires opt-in telemetry).

---

## Dependencies

**External:** NONE. All new modules use pure Python (math, random, dataclasses) and the seeded RNG from `core/humanize/rng.py`.

**Internal:**
- `core/humanize/profile.py` — Profile base class, get_default_profile()
- `core/humanize/rng.py` — Seeded RNG for reproducibility
- `core/humanize/motion.py` — Existing bezier path generation (extended with Fitts/overshoot)
- `core/humanize/typing.py` — Existing keystroke cadence (extended with error injection)
- `core/humanize/timing.py` — Existing timing helpers (used by attention pauses)
- `core/desktop.py` — Physical input chokepoint (extended with Fitts timing)
- `core/stealth_input.py` — Stealth input chokepoint (extended with error injection)
- `core/action_executor.py` — Executor dispatch (extended with context passing)

---

## Timeline Estimate

**Design-only (this phase):** 1 day (already complete — this spec).

**Implementation:** 2-3 weeks:
- Week 1: Core modules (fitts, overshoot, errors, scroll, attention) + tests.
- Week 2: Detector-evasion pipeline, integration with executor/chokepoints + tests.
- Week 3: Biometric sampling tool, default population-median profile, documentation.

**QA/validation:** 1 week:
- Manual testing against real detectors (ScreenConnect, NinjaOne) if available.
- Performance benchmarking.
- Documentation review.

**Total:** 3-4 weeks from design to ship-ready.

---

## References

1. **Fitts's Law:** Fitts, P. M. (1954). "The information capacity of the human motor system in controlling the amplitude of movement." *Journal of Experimental Psychology*, 47(6), 381-391.
2. **Behavioral biometrics:** **@article{biometric2020**, title="Behavioral biometrics: A review", author="Shen, C. and Li, Y. and Chen, Y.", year=2020.**
3. **Anti-bot detection in remote-control tools:** Internal threat model (ScreenConnect, NinjaOne, ConnectWise heuristic documentation).
4. **Naturalistic tier design:** `docs/superpowers/specs/2026-06-18-humanization-engine-design.md` (v18.x, shipped 2026-06-18).

---

**END OF SPEC**
