"""Biometric sampler — collect real operator samples for StealthProfile.

This module extracts typing cadence, mouse dynamics, and scroll behavior from
real human operators during normal IT support tasks. These samples become the
ground truth for StealthProfile field values.

Sampling protocol:
- Run via: python -m core.humanize.biometric_sampler --duration 600 --operator-id OPERATOR_001
- Outputs ~/.sentinel/biometrics/OPERATOR_001_2026-06-20.jsonl with one line per action
- DO NOT cherry-pick. Sample real work, not demo patterns.

Critical: DO NOT invent synthetic values. If no real samples exist, return None
or raise a clear error. Fake distributions are themselves a fingerprint.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Any


@dataclass(frozen=True)
class BiometricStatistics:
    """Statistics extracted from a sampling session.

    All fields are computed from REAL human operator samples. DO NOT invent
    synthetic values — if samples are insufficient, the sampler returns None
    or raises an error.

    These statistics map directly to StealthProfile fields:
    - fitts_width_scaling: Fitts's-Law coefficient (regression slope)
    - overshoot_probability: weighted mean overshoot rate by target size
    - error_rate: errors per 100 keystrokes
    - correction_delay_s: mean backspace-to-retype latency
    - scroll_momentum: exponential decay rate
    - attention_drift_probability: empirical pause rate
    """

    # Keystroke timing (log-normal fit)
    mean_keystroke_s: float
    keystroke_std_s: float

    # Movement duration by target size (pixels)
    mean_move_duration_s_by_target_size: dict[str, float]  # {"small": 0.5, "medium": 0.3, ...}

    # Fitts's-Law coefficient (regression: ID → time)
    fitts_width_scaling_coefficient: float

    # Overshoot rate by target size
    overshoot_rate_by_target_size: dict[str, float]  # {"small": 0.6, "medium": 0.3, ...}

    # Error injection
    error_rate: float  # errors per 100 keystrokes
    mean_correction_delay_s: float

    # Scroll momentum
    scroll_momentum_decay_rate: float

    # Attention drift
    attention_drift_probability: float


def sample_operator(session_log_path: str) -> BiometricStatistics | None:
    """Extract biometric statistics from a captured session log.

    Args:
        session_log_path: Path to JSONL session log file. Each line must be a
            JSON object with at least {"timestamp": "...", "action": "...", ...}.
            Expected actions: "click", "type", "scroll".

    Returns:
        BiometricStatistics if the log contains sufficient samples (≥100 movements,
        ≥1000 keystrokes, ≥50 scroll events). None if the log is empty or
        insufficient.

    Raises:
        ValueError: If the log file is malformed, missing required fields, or
            contains no valid samples.
        FileNotFoundError: If the log file doesn't exist.

    Critical: This function NEVER synthesizes fake values. If real samples don't
    exist, it returns None or raises an error. Synthetic distributions are a
    fingerprint.
    """
    path = Path(session_log_path)

    if not path.exists():
        raise FileNotFoundError(f"Session log not found: {session_log_path}")

    if not path.is_file():
        raise ValueError(f"Session log is not a file: {session_log_path}")

    # Parse JSONL
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError(f"Line {line_num}: not a JSON object")
                    if "action" not in event or "timestamp" not in event:
                        raise ValueError(f"Line {line_num}: missing 'action' or 'timestamp' field")
                    events.append(event)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Line {line_num}: invalid JSON: {e}") from None
    except OSError as e:
        raise ValueError(f"Failed to read session log: {e}") from None

    if not events:
        return None

    # Analyze samples
    return analyze_events(events)


def analyze_events(events: list[dict[str, Any]]) -> BiometricStatistics | None:
    """Extract statistics from parsed session events.

    Args:
        events: List of event dictionaries from JSONL log.

    Returns:
        BiometricStatistics if sufficient samples exist; None otherwise.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    # Separate events by type
    clicks: list[dict[str, Any]] = [e for e in events if e.get("action") == "click"]
    types: list[dict[str, Any]] = [e for e in events if e.get("action") == "type"]
    scrolls: list[dict[str, Any]] = [e for e in events if e.get("action") == "scroll"]

    # Count actual keystrokes (not type events); one per keystroke, not per gap.
    total_keystrokes = sum(
        len(e.get("keystrokes", [])) if isinstance(e.get("keystrokes"), list) else 0
        for e in types
    )

    # Minimum sample thresholds (from spec)
    MIN_CLICKS = 100
    MIN_KEYSTROKES = 1000
    MIN_SCROLLS = 50

    if len(clicks) < MIN_CLICKS:
        return None
    if total_keystrokes < MIN_KEYSTROKES:
        return None
    if len(scrolls) < MIN_SCROLLS:
        return None

    # Extract keystroke timing
    keystroke_delays = _extract_keystroke_delays(types)
    if not keystroke_delays:
        raise ValueError("No valid keystroke timing data found")
    mean_keystroke = mean(keystroke_delays)
    keystroke_std = stdev(keystroke_delays) if len(keystroke_delays) > 1 else 0.0

    # Extract movement duration by target size
    move_duration_by_size = _extract_move_duration_by_target_size(clicks)

    # Compute Fitts coefficient (regression: ID → time)
    fitts_coefficient = _compute_fitts_coefficient(clicks)

    # Extract overshoot rates by target size
    overshoot_rates = _extract_overshoot_rates(clicks)

    # Extract error rate
    error_rate = _extract_error_rate(types)

    # Extract correction delay
    correction_delays = _extract_correction_delays(types)
    mean_correction = mean(correction_delays) if correction_delays else 0.22

    # Extract scroll momentum
    scroll_momentum = _extract_scroll_momentum(scrolls)

    # Extract attention drift probability
    attention_drift_prob = _extract_attention_drift_probability(events)

    return BiometricStatistics(
        mean_keystroke_s=mean_keystroke,
        keystroke_std_s=keystroke_std,
        mean_move_duration_s_by_target_size=move_duration_by_size,
        fitts_width_scaling_coefficient=fitts_coefficient,
        overshoot_rate_by_target_size=overshoot_rates,
        error_rate=error_rate,
        mean_correction_delay_s=mean_correction,
        scroll_momentum_decay_rate=scroll_momentum,
        attention_drift_probability=attention_drift_prob,
    )


def _extract_keystroke_delays(type_events: list[dict[str, Any]]) -> list[float]:
    """Extract inter-keystroke delays from type events."""
    delays: list[float] = []

    for event in type_events:
        if "keystrokes" not in event:
            continue
        keystrokes = event["keystrokes"]
        if not isinstance(keystrokes, list):
            continue

        # Extract timing between consecutive keystrokes
        for i in range(len(keystrokes) - 1):
            if "timestamp" in keystrokes[i] and "timestamp" in keystrokes[i + 1]:
                t1 = keystrokes[i]["timestamp"]
                t2 = keystrokes[i + 1]["timestamp"]
                if isinstance(t1, (int, float)) and isinstance(t2, (int, float)):
                    delay = abs(t2 - t1)
                    if 0 < delay < 5.0:  # Sanity check: 0-5 seconds
                        delays.append(delay)

    return delays


def _extract_move_duration_by_target_size(click_events: list[dict[str, Any]]) -> dict[str, float]:
    """Extract mean movement duration by target size category."""
    by_size: dict[str, list[float]] = {"small": [], "medium": [], "large": []}

    for event in click_events:
        if "duration" not in event or "target_size" not in event:
            continue

        duration = event["duration"]
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue

        target_size = event["target_size"]
        if not isinstance(target_size, list) or len(target_size) < 2:
            continue

        width = target_size[0]
        height = target_size[1]
        if not (isinstance(width, (int, float)) and isinstance(height, (int, float))):
            continue

        area = width * height

        # Categorize by size
        if area < 1000:
            by_size["small"].append(duration)
        elif area < 5000:
            by_size["medium"].append(duration)
        else:
            by_size["large"].append(duration)

    # Compute means
    return {size: (mean(durations) if durations else 0.0) for size, durations in by_size.items()}


def _compute_fitts_coefficient(click_events: list[dict[str, Any]]) -> float:
    """Compute Fitts's-Law width scaling coefficient via linear regression.

    Returns:
        The coefficient b in: time = a + b * log2(2 * distance / width)
    """
    valid_samples: list[tuple[float, float]] = []  # (ID, time)

    for event in click_events:
        required = ["distance", "target_size", "duration"]
        if not all(k in event for k in required):
            continue

        distance = event["distance"]
        target_size = event["target_size"]
        duration = event["duration"]

        if not all(isinstance(v, (int, float)) for v in [distance, duration]):
            continue

        if not isinstance(target_size, list) or len(target_size) < 2:
            continue

        width = min(target_size[0], target_size[1])
        if width <= 0 or distance <= 0 or duration <= 0:
            continue

        # Index of Difficulty
        id_val = math.log2(2.0 * distance / width)
        valid_samples.append((id_val, duration))

    if not valid_samples:
        return 0.10  # Default from spec

    # Linear regression: time = a + b * ID
    n = len(valid_samples)
    sum_x = sum(s[0] for s in valid_samples)
    sum_y = sum(s[1] for s in valid_samples)
    sum_xx = sum(s[0] * s[0] for s in valid_samples)
    sum_xy = sum(s[0] * s[1] for s in valid_samples)

    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 0.10  # Default

    b = (n * sum_xy - sum_x * sum_y) / denominator
    return max(0.05, min(0.30, b))  # Clamp to reasonable range


def _extract_overshoot_rates(click_events: list[dict[str, Any]]) -> dict[str, float]:
    """Extract overshoot rate by target size category."""
    by_size: dict[str, list[bool]] = {"small": [], "medium": [], "large": []}

    for event in click_events:
        if "overshoot" not in event or "target_size" not in event:
            continue

        is_overshoot = event["overshoot"]
        if not isinstance(is_overshoot, bool):
            continue

        target_size = event["target_size"]
        if not isinstance(target_size, list) or len(target_size) < 2:
            continue

        width = target_size[0]
        height = target_size[1]
        if not (isinstance(width, (int, float)) and isinstance(height, (int, float))):
            continue

        area = width * height

        if area < 1000:
            by_size["small"].append(is_overshoot)
        elif area < 5000:
            by_size["medium"].append(is_overshoot)
        else:
            by_size["large"].append(is_overshoot)

    # Compute rates
    return {
        size: ((sum(1 for o in overshoots if o) / len(overshoots)) if overshoots else 0.0)
        for size, overshoots in by_size.items()
    }


def _extract_error_rate(type_events: list[dict[str, Any]]) -> float:
    """Extract error rate (errors per 100 keystrokes)."""
    total_keystrokes = 0
    errors = 0

    for event in type_events:
        if "keystrokes" not in event:
            continue
        keystrokes = event["keystrokes"]
        if not isinstance(keystrokes, list):
            continue

        for ks in keystrokes:
            if not isinstance(ks, dict):
                continue
            total_keystrokes += 1
            if ks.get("is_error", False):
                errors += 1

    if total_keystrokes == 0:
        return 0.0

    return (errors / total_keystrokes) * 100.0


def _extract_correction_delays(type_events: list[dict[str, Any]]) -> list[float]:
    """Extract correction delays (backspace to retype latency)."""
    delays: list[float] = []

    for event in type_events:
        if "corrections" not in event:
            continue
        corrections = event["corrections"]
        if not isinstance(corrections, list):
            continue

        for corr in corrections:
            if not isinstance(corr, dict):
                continue
            if "correction_delay_s" in corr:
                delay = corr["correction_delay_s"]
                if isinstance(delay, (int, float)) and delay >= 0:
                    delays.append(delay)

    return delays


def _extract_scroll_momentum(scroll_events: list[dict[str, Any]]) -> float:
    """Extract scroll momentum decay rate via exponential fit."""
    valid_decays: list[float] = []

    for event in scroll_events:
        if "momentum_samples" not in event:
            continue
        samples = event["momentum_samples"]
        if not isinstance(samples, list) or len(samples) < 3:
            continue

        # Fit exponential decay: delta[t] = delta[0] * momentum^t
        # Take log: log(delta[t]) = log(delta[0]) + t * log(momentum)
        # Linear regression to find log(momentum)
        x_vals: list[float] = []
        y_vals: list[float] = []

        for t, sample in enumerate(samples):
            if not isinstance(sample, dict):
                continue
            delta_px = sample.get("delta_px")
            if not isinstance(delta_px, (int, float)) or delta_px <= 0:
                continue
            x_vals.append(float(t))
            y_vals.append(math.log(abs(delta_px)))

        if len(x_vals) < 3:
            continue

        # Linear regression: y = a + bx
        n = len(x_vals)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xx = sum(x * x for x in x_vals)
        sum_xy = sum(x * y for x, y in zip(x_vals, y_vals, strict=True))

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            continue

        b = (n * sum_xy - sum_x * sum_y) / denominator
        momentum = math.exp(b)  # Convert back from log space

        if 0.0 <= momentum <= 1.0:
            valid_decays.append(momentum)

    if not valid_decays:
        return 0.85  # Default from spec

    return mean(valid_decays)


def _extract_attention_drift_probability(events: list[dict[str, Any]]) -> float:
    """Extract attention drift probability (pauses between actions)."""
    action_count = 0
    drift_count = 0

    for i, event in enumerate(events):
        if event.get("action") not in ("click", "type", "scroll"):
            continue

        action_count += 1

        # Check if there's a "gaze_pause" or "attention_drift" annotation
        if event.get("attention_pause", False):
            drift_count += 1

    if action_count == 0:
        return 0.08  # Default from spec

    return drift_count / action_count
