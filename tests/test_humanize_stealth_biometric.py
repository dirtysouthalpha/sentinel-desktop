"""Tests for core/humanize/biometric_sampler.py — biometric statistics extraction.

Tests that sample_operator() parses session logs into correct BiometricStatistics,
returns None on insufficient samples, raises on malformed input, and NEVER
synthesizes fake values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.humanize.biometric_sampler import (
    BiometricStatistics,
    analyze_events,
    sample_operator,
)


# Fixtures
@pytest.fixture
def empty_session_log(tmp_path: Path) -> Path:
    """Empty session log file."""
    log = tmp_path / "empty.jsonl"
    log.write_text("")
    return log


@pytest.fixture
def minimal_session_log(tmp_path: Path) -> Path:
    """Session log with insufficient samples (below thresholds)."""
    log = tmp_path / "minimal.jsonl"
    lines = [
        json.dumps({"timestamp": 0.0, "action": "click", "distance": 100, "target_size": [20, 10], "duration": 0.3}),
    ] * 10  # Only 10 clicks (needs 100)
    log.write_text("\n".join(lines))
    return log


@pytest.fixture
def valid_session_log(tmp_path: Path) -> Path:
    """Session log with sufficient valid samples."""
    log = tmp_path / "valid.jsonl"
    lines = []

    # 100 click events with varied targets
    for i in range(100):
        lines.append(
            json.dumps({
                "timestamp": i * 1.0,
                "action": "click",
                "distance": 100 + i,
                "target_size": [20 + i, 10 + i],
                "duration": 0.2 + i * 0.001,
                "overshoot": i % 3 == 0,  # 33% overshoot rate
            })
        )

    # 1000 keystroke events with timing
    for i in range(1000):
        lines.append(
            json.dumps({
                "timestamp": 100.0 + i * 0.1,
                "action": "type",
                "keystrokes": [
                    {"timestamp": i * 0.1, "key": "a"},
                    {"timestamp": i * 0.1 + 0.12, "key": "b"},
                ],
            })
        )

    # 50 scroll events with momentum
    for i in range(50):
        lines.append(
            json.dumps({
                "timestamp": 200.0 + i * 0.5,
                "action": "scroll",
                "delta_px": 120,
                "momentum_samples": [
                    {"delta_px": 120 * (0.85 ** t), "frame_dwell_s": 0.016}
                    for t in range(10)
                ],
            })
        )

    log.write_text("\n".join(lines))
    return log


@pytest.fixture
def session_log_with_errors(tmp_path: Path) -> Path:
    """Session log with error-correction sequences."""
    log = tmp_path / "with_errors.jsonl"
    lines = []

    # Type events with error annotations (need 1000+ keystrokes)
    for i in range(500):  # 500 events with 2 keystrokes each = 1000 keystrokes
        lines.append(
            json.dumps({
                "timestamp": i * 0.5,
                "action": "type",
                "keystrokes": [
                    {"timestamp": i * 0.5, "key": "a", "is_error": False},
                    {"timestamp": i * 0.5 + 0.12, "key": "b", "is_error": i % 10 == 0},  # 10% error rate
                ],
                "corrections": (
                    [
                        {"correction_delay_s": 0.22}
                    ] if i % 10 == 0 else []
                ),
            })
        )

    # Fill with other events to meet thresholds
    for i in range(100):
        lines.append(json.dumps({
            "timestamp": 250.0 + i,
            "action": "click",
            "distance": 100,
            "target_size": [20, 10],
            "duration": 0.3,
        }))

    for i in range(50):
        lines.append(json.dumps({
            "timestamp": 350.0 + i,
            "action": "scroll",
            "delta_px": 100,
            "momentum_samples": [{"delta_px": 100 * (0.9 ** t), "frame_dwell_s": 0.016} for t in range(5)],
        }))

    log.write_text("\n".join(lines))
    return log


@pytest.fixture
def session_log_with_attention_drift(tmp_path: Path) -> Path:
    """Session log with attention drift annotations."""
    log = tmp_path / "with_drift.jsonl"
    lines = []

    for i in range(100):
        lines.append(
            json.dumps({
                "timestamp": i * 1.0,
                "action": "click",
                "distance": 100,
                "target_size": [20, 10],
                "duration": 0.3,
                "attention_pause": i % 10 == 0,  # 10% drift rate
            })
        )

    # Fill with type events
    for i in range(1000):
        lines.append(json.dumps({
            "timestamp": 100.0 + i * 0.1,
            "action": "type",
            "keystrokes": [{"timestamp": i * 0.1, "key": "a"}, {"timestamp": i * 0.1 + 0.12, "key": "b"}],
        }))

    # Fill with scroll events
    for i in range(50):
        lines.append(json.dumps({
            "timestamp": 200.0 + i * 0.5,
            "action": "scroll",
            "delta_px": 100,
            "momentum_samples": [{"delta_px": 100 * (0.85 ** t), "frame_dwell_s": 0.016} for t in range(8)],
        }))

    log.write_text("\n".join(lines))
    return log


@pytest.fixture
def malformed_session_log(tmp_path: Path) -> Path:
    """Session log with malformed JSON."""
    log = tmp_path / "malformed.jsonl"
    lines = [
        json.dumps({"timestamp": 0.0, "action": "click", "distance": 100, "target_size": [20, 10], "duration": 0.3}),
        "this is not json",
        json.dumps({"timestamp": 1.0, "action": "type", "keystrokes": []}),
    ]
    log.write_text("\n".join(lines))
    return log


@pytest.fixture
def missing_fields_session_log(tmp_path: Path) -> Path:
    """Session log with missing required fields."""
    log = tmp_path / "missing_fields.jsonl"
    lines = [
        json.dumps({"timestamp": 0.0}),  # Missing 'action'
        json.dumps({"action": "click"}),  # Missing 'timestamp'
        json.dumps({"timestamp": 2.0, "action": "scroll"}),  # Missing scroll-specific fields
    ]
    log.write_text("\n".join(lines))
    return log


# Tests: File not found
class TestFileNotFound:
    def test_sample_operator_raises_on_nonexistent_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Session log not found"):
            sample_operator(str(tmp_path / "does_not_exist.jsonl"))


# Tests: Empty/insufficient samples
class TestInsufficientSamples:
    def test_empty_log_returns_none(self, empty_session_log: Path):
        result = sample_operator(str(empty_session_log))
        assert result is None

    def test_minimal_samples_returns_none(self, minimal_session_log: Path):
        result = sample_operator(str(minimal_session_log))
        assert result is None


# Tests: Valid parsing
class TestValidParsing:
    def test_valid_log_returns_biometric_statistics(self, valid_session_log: Path):
        result = sample_operator(str(valid_session_log))
        assert isinstance(result, BiometricStatistics)

    def test_keystroke_timing_extraction(self, valid_session_log: Path):
        result = sample_operator(str(valid_session_log))
        assert result.mean_keystroke_s > 0
        assert result.keystroke_std_s >= 0
        assert 0.05 < result.mean_keystroke_s < 1.0  # Reasonable range

    def test_move_duration_by_target_size(self, valid_session_log: Path):
        result = sample_operator(str(valid_session_log))
        assert "small" in result.mean_move_duration_s_by_target_size
        assert "medium" in result.mean_move_duration_s_by_target_size
        assert "large" in result.mean_move_duration_s_by_target_size

    def test_fitts_coefficient_extraction(self, valid_session_log: Path):
        result = sample_operator(str(valid_session_log))
        assert 0.05 <= result.fitts_width_scaling_coefficient <= 0.30

    def test_overshoot_rates_by_target_size(self, valid_session_log: Path):
        result = sample_operator(str(valid_session_log))
        assert "small" in result.overshoot_rate_by_target_size
        assert "medium" in result.overshoot_rate_by_target_size
        assert "large" in result.overshoot_rate_by_target_size
        # All rates should be in reasonable range [0, 1]
        for size, rate in result.overshoot_rate_by_target_size.items():
            assert 0.0 <= rate <= 1.0

    def test_scroll_momentum_extraction(self, valid_session_log: Path):
        result = sample_operator(str(valid_session_log))
        assert 0.0 <= result.scroll_momentum_decay_rate <= 1.0


# Tests: Error-correction extraction
class TestErrorCorrectionExtraction:
    def test_error_rate_extraction(self, session_log_with_errors: Path):
        result = sample_operator(str(session_log_with_errors))
        assert result.error_rate > 0
        assert result.error_rate < 20.0  # Reasonable range

    def test_correction_delay_extraction(self, session_log_with_errors: Path):
        result = sample_operator(str(session_log_with_errors))
        assert result.mean_correction_delay_s > 0
        assert 0.1 < result.mean_correction_delay_s < 1.0  # Reasonable range


# Tests: Attention drift extraction
class TestAttentionDriftExtraction:
    def test_attention_drift_probability(self, session_log_with_attention_drift: Path):
        result = sample_operator(str(session_log_with_attention_drift))
        assert result.attention_drift_probability > 0
        assert result.attention_drift_probability <= 1.0


# Tests: Malformed input handling
class TestMalformedInput:
    def test_malformed_json_raises_value_error(self, malformed_session_log: Path):
        with pytest.raises(ValueError, match="invalid JSON"):
            sample_operator(str(malformed_session_log))

    def test_missing_required_fields_raises_value_error(self, missing_fields_session_log: Path):
        with pytest.raises(ValueError, match="missing 'action' or 'timestamp'"):
            sample_operator(str(missing_fields_session_log))


# Tests: No synthesis
class TestNoSynthesis:
    def test_returns_none_on_no_keystrokes(self, tmp_path: Path):
        """Must not synthesize keystroke timing when no keystrokes exist."""
        log = tmp_path / "no_keystrokes.jsonl"
        lines = [json.dumps({
            "timestamp": i * 1.0,
            "action": "click",
            "distance": 100,
            "target_size": [20, 10],
            "duration": 0.3,
        }) for i in range(100)]

        # Add scroll events to meet threshold but no type events
        lines.extend([
            json.dumps({
                "timestamp": 100.0 + i * 0.5,
                "action": "scroll",
                "delta_px": 100,
                "momentum_samples": [{"delta_px": 100, "frame_dwell_s": 0.016}],
            }) for i in range(50)
        ])

        log.write_text("\n".join(lines))
        result = sample_operator(str(log))
        # Should return None because no keystrokes exist
        assert result is None

    def test_returns_none_on_no_clicks(self, tmp_path: Path):
        """Must not synthesize movement data when no clicks exist."""
        log = tmp_path / "no_clicks.jsonl"
        lines = [json.dumps({
            "timestamp": i * 0.1,
            "action": "type",
            "keystrokes": [{"timestamp": i * 0.1, "key": "a"}, {"timestamp": i * 0.1 + 0.12, "key": "b"}],
        }) for i in range(1000)]

        # Add scroll events to meet threshold but no click events
        lines.extend([
            json.dumps({
                "timestamp": 100.0 + i * 0.5,
                "action": "scroll",
                "delta_px": 100,
                "momentum_samples": [{"delta_px": 100, "frame_dwell_s": 0.016}],
            }) for i in range(50)
        ])

        log.write_text("\n".join(lines))
        result = sample_operator(str(log))
        # Should return None because no clicks exist
        assert result is None

    def test_returns_none_on_no_scrolls(self, tmp_path: Path):
        """Must not synthesize scroll data when no scrolls exist."""
        log = tmp_path / "no_scrolls.jsonl"
        lines = [json.dumps({
            "timestamp": i * 1.0,
            "action": "click",
            "distance": 100,
            "target_size": [20, 10],
            "duration": 0.3,
        }) for i in range(100)]

        lines.extend([
            json.dumps({
                "timestamp": 100.0 + i * 0.1,
                "action": "type",
                "keystrokes": [{"timestamp": i * 0.1, "key": "a"}, {"timestamp": i * 0.1 + 0.12, "key": "b"}],
            }) for i in range(1000)
        ])

        log.write_text("\n".join(lines))
        result = sample_operator(str(log))
        # Should return None because no scrolls exist
        assert result is None


# Tests: analyze_events directly
class TestAnalyzeEvents:
    def test_analyze_events_with_valid_data(self):
        events = [
            {"timestamp": 0.0, "action": "click", "distance": 100, "target_size": [20, 10], "duration": 0.3},
        ] * 100 + [
            {"timestamp": 100.0, "action": "type", "keystrokes": [
                {"timestamp": 0.0, "key": "a"},
                {"timestamp": 0.12, "key": "b"},
            ]},
        ] * 1000 + [
            {"timestamp": 200.0, "action": "scroll", "delta_px": 100, "momentum_samples": [
                {"delta_px": 100 * (0.85 ** t), "frame_dwell_s": 0.016} for t in range(5)
            ]},
        ] * 50

        result = analyze_events(events)
        assert isinstance(result, BiometricStatistics)

    def test_analyze_events_with_insufficient_clicks(self):
        events = [
            {"timestamp": 0.0, "action": "click", "distance": 100, "target_size": [20, 10], "duration": 0.3},
        ] * 10  # Below threshold
        result = analyze_events(events)
        assert result is None

    def test_analyze_events_with_insufficient_keystrokes(self):
        events = [
            {"timestamp": 0.0, "action": "click", "distance": 100, "target_size": [20, 10], "duration": 0.3},
        ] * 100 + [
            {"timestamp": 100.0, "action": "type", "keystrokes": [
                {"timestamp": 0.0, "key": "a"},
            ]},
        ] * 100  # Below threshold
        result = analyze_events(events)
        assert result is None

    def test_analyze_events_with_insufficient_scrolls(self):
        events = [
            {"timestamp": 0.0, "action": "click", "distance": 100, "target_size": [20, 10], "duration": 0.3},
        ] * 100 + [
            {"timestamp": 100.0, "action": "type", "keystrokes": [
                {"timestamp": 0.0, "key": "a"},
                {"timestamp": 0.12, "key": "b"},
            ]},
        ] * 1000 + [
            {"timestamp": 200.0, "action": "scroll", "delta_px": 100, "momentum_samples": [
                {"delta_px": 100, "frame_dwell_s": 0.016}
            ]},
        ] * 10  # Below threshold
        result = analyze_events(events)
        assert result is None
