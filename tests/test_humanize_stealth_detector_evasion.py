"""Tests for detector_evasion.py module.

Tests the pluggable detector-evasion pipeline including:
- Pipeline applies strategies in order
- No-op pipeline is a passthrough
- Adding a strategy changes output
- Per-strategy failure degrades gracefully
"""

import random

from unittest.mock import MagicMock

import pytest

from core.humanize.detector_evasion import (
    AttentionSimulationStrategy,
    DetectorEvasionPipeline,
    DetectorEvasionStrategy,
    ErrorInjectionStrategy,
    FittsLawStrategy,
    MomentumScrollStrategy,
    NoOpStrategy,
    OvershootStrategy,
    DEFAULT_STEALTH_PIPELINE,
)
from core.humanize.profile import Profile, StealthProfile


class TestDetectorEvasionStrategy:
    """Test DetectorEvasionStrategy abstract base class."""

    def test_is_abstract(self):
        """DetectorEvasionStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DetectorEvasionStrategy()  # type: ignore


class TestNoOpStrategy:
    """Test NoOpStrategy placeholder."""

    def test_returns_trajectory_unchanged(self):
        """NoOpStrategy should return trajectory unchanged."""
        strategy = NoOpStrategy()
        trajectory = [((0.0, 0.0), 0.1), ((10.0, 10.0), 0.2)]

        result = strategy.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=random.Random(42),
            profile=Profile(),
        )

        assert result == trajectory

    def test_works_for_all_actions(self):
        """NoOpStrategy should handle any action type."""
        strategy = NoOpStrategy()
        trajectory = [((0.0, 0.0), 0.1)]

        for action in ["click", "move", "type", "scroll", "unknown"]:
            result = strategy.apply(
                action=action,
                context={},
                trajectory=trajectory,
                rng=MagicMock(),
                profile=Profile(),
            )
            assert result == trajectory


class TestFittsLawStrategy:
    """Test FittsLawStrategy."""

    def test_ignores_non_movement_actions(self):
        """FittsLawStrategy should ignore type and scroll actions."""
        strategy = FittsLawStrategy()
        trajectory = [((0.0, 0.0), 0.1)]

        for action in ["type", "scroll", "unknown"]:
            result = strategy.apply(
                action=action,
                context={},
                trajectory=trajectory,
                rng=MagicMock(),
                profile=StealthProfile(),
            )
            assert result == trajectory

    def test_ignores_naturalistic_profile(self):
        """FittsLawStrategy should return unchanged trajectory for NATURALISTIC profile."""
        strategy = FittsLawStrategy()
        trajectory = [((0.0, 0.0), 0.1), ((10.0, 10.0), 0.2)]
        context = {
            "target_size": (20, 10),
            "start_position": (0, 0),
            "target_position": (10, 10),
        }

        result = strategy.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_ignores_missing_target_size(self):
        """FittsLawStrategy should return unchanged trajectory when target_size missing."""
        strategy = FittsLawStrategy()
        trajectory = [((0.0, 0.0), 0.1)]
        context = {"start_position": (0, 0), "target_position": (10, 10)}

        result = strategy.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert result == trajectory

    def test_applies_fitts_timing_for_click_with_stealth_profile(self):
        """FittsLawStrategy should apply Fitts timing for click with StealthProfile."""
        strategy = FittsLawStrategy()
        trajectory = [((0.0, 0.0), 0.1), ((10.0, 10.0), 0.2)]
        context = {
            "target_size": (20, 10),
            "start_position": (0, 0),
            "target_position": (10, 10),
        }

        result = strategy.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=random.Random(42),  # Use seeded random for reproducibility
            profile=StealthProfile(),
        )

        # Result should be a list (may be modified by Fitts timing)
        assert isinstance(result, list)
        assert len(result) > 0


class TestOvershootStrategy:
    """Test OvershootStrategy."""

    def test_ignores_non_movement_actions(self):
        """OvershootStrategy should ignore type and scroll actions."""
        strategy = OvershootStrategy()
        trajectory = [((0.0, 0.0), 0.1)]

        for action in ["type", "scroll", "unknown"]:
            result = strategy.apply(
                action=action,
                context={},
                trajectory=trajectory,
                rng=MagicMock(),
                profile=StealthProfile(),
            )
            assert result == trajectory

    def test_ignores_naturalistic_profile(self):
        """OvershootStrategy should return unchanged trajectory for NATURALISTIC profile."""
        strategy = OvershootStrategy()
        trajectory = [((0.0, 0.0), 0.1)]
        context = {"target_size": (20, 10), "target_position": (10, 10)}

        result = strategy.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_ignores_missing_target_size(self):
        """OvershootStrategy should return unchanged trajectory when target_size missing."""
        strategy = OvershootStrategy()
        trajectory = [((0.0, 0.0), 0.1)]
        context = {"target_position": (10, 10)}

        result = strategy.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert result == trajectory


class TestErrorInjectionStrategy:
    """Test ErrorInjectionStrategy."""

    def test_ignores_non_type_actions(self):
        """ErrorInjectionStrategy should ignore non-type actions."""
        strategy = ErrorInjectionStrategy()
        trajectory = [((0.0, 0.0), 0.1)]

        for action in ["click", "move", "scroll", "unknown"]:
            result = strategy.apply(
                action=action,
                context={},
                trajectory=trajectory,
                rng=MagicMock(),
                profile=StealthProfile(),
            )
            assert result == trajectory

    def test_ignores_naturalistic_profile(self):
        """ErrorInjectionStrategy should return unchanged trajectory for NATURALISTIC profile."""
        strategy = ErrorInjectionStrategy()
        trajectory = [0.1, 0.2, 0.15]
        context = {"text": "password"}

        result = strategy.apply(
            action="type",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_ignores_empty_text(self):
        """ErrorInjectionStrategy should return unchanged trajectory for empty text."""
        strategy = ErrorInjectionStrategy()
        trajectory = [0.1, 0.2]
        context = {"text": ""}

        result = strategy.apply(
            action="type",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert result == trajectory


class TestMomentumScrollStrategy:
    """Test MomentumScrollStrategy."""

    def test_ignores_non_scroll_actions(self):
        """MomentumScrollStrategy should ignore non-scroll actions."""
        strategy = MomentumScrollStrategy()
        trajectory = [((0.0, 0.0), 0.1)]

        for action in ["click", "move", "type", "unknown"]:
            result = strategy.apply(
                action=action,
                context={},
                trajectory=trajectory,
                rng=MagicMock(),
                profile=StealthProfile(),
            )
            assert result == trajectory

    def test_ignores_naturalistic_profile(self):
        """MomentumScrollStrategy should return unchanged trajectory for NATURALISTIC profile."""
        strategy = MomentumScrollStrategy()
        trajectory = [(120, 0.0)]
        context = {"scroll_delta": 120}

        result = strategy.apply(
            action="scroll",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_ignores_zero_delta(self):
        """MomentumScrollStrategy should return unchanged trajectory for zero delta."""
        strategy = MomentumScrollStrategy()
        trajectory = [(0, 0.0)]
        context = {"scroll_delta": 0}

        result = strategy.apply(
            action="scroll",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert result == trajectory


class TestAttentionSimulationStrategy:
    """Test AttentionSimulationStrategy."""

    def test_ignores_naturalistic_profile(self):
        """AttentionSimulationStrategy should return unchanged trajectory for NATURALISTIC profile."""
        strategy = AttentionSimulationStrategy()
        trajectory = [((0.0, 0.0), 0.1)]
        context = {"action_context": "clicking_button"}

        result = strategy.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_returns_trajectory_for_any_action_with_stealth_profile(self):
        """AttentionSimulationStrategy should handle any action with StealthProfile."""
        strategy = AttentionSimulationStrategy()
        trajectory = [((0.0, 0.0), 0.1)]

        for action in ["click", "type", "scroll", "move"]:
            result = strategy.apply(
                action=action,
                context={},
                trajectory=trajectory,
                rng=random.Random(42),  # Use seeded random for reproducibility
                profile=StealthProfile(),
            )
            # Should always return a list
            assert isinstance(result, list)


class TestDetectorEvasionPipeline:
    """Test DetectorEvasionPipeline composition."""

    def test_no_op_pipeline_is_passthrough(self):
        """Pipeline with only NoOpStrategy should be a passthrough."""
        pipeline = DetectorEvasionPipeline([NoOpStrategy()])
        trajectory = [((0.0, 0.0), 0.1), ((10.0, 10.0), 0.2)]

        result = pipeline.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_empty_pipeline_is_passthrough(self):
        """Empty pipeline should return trajectory unchanged."""
        pipeline = DetectorEvasionPipeline([])
        trajectory = [((0.0, 0.0), 0.1)]

        result = pipeline.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        assert result == trajectory

    def test_adding_strategy_changes_output(self):
        """Adding a strategy should change the output trajectory."""
        # Create a custom strategy that modifies trajectory
        class CustomStrategy(DetectorEvasionStrategy):
            def apply(self, action, context, trajectory, *, rng, profile):
                # Add a point to trajectory
                return trajectory + [((99.0, 99.0), 0.5)]

        pipeline_without = DetectorEvasionPipeline([NoOpStrategy()])
        pipeline_with = DetectorEvasionPipeline([NoOpStrategy(), CustomStrategy()])
        trajectory = [((0.0, 0.0), 0.1)]

        result_without = pipeline_without.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        result_with = pipeline_with.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        # Pipeline with custom strategy should have longer trajectory
        assert len(result_with) == len(result_without) + 1

    def test_strategies_apply_in_order(self):
        """Strategies should be applied in the order they are provided."""
        call_order = []

        class OrderStrategy(DetectorEvasionStrategy):
            def __init__(self, name):
                self.name = name

            def apply(self, action, context, trajectory, *, rng, profile):
                call_order.append(self.name)
                return trajectory

        pipeline = DetectorEvasionPipeline(
            [
                OrderStrategy("first"),
                OrderStrategy("second"),
                OrderStrategy("third"),
            ]
        )

        pipeline.apply(
            action="click",
            context={},
            trajectory=[((0.0, 0.0), 0.1)],
            rng=MagicMock(),
            profile=Profile(),
        )

        assert call_order == ["first", "second", "third"]

    def test_per_strategy_failure_degrades_gracefully(self):
        """Pipeline should continue even if one strategy fails."""
        class FailingStrategy(DetectorEvasionStrategy):
            def apply(self, action, context, trajectory, *, rng, profile):
                raise RuntimeError("Strategy failed!")

        class WorkingStrategy(DetectorEvasionStrategy):
            def __init__(self):
                self.called = False

            def apply(self, action, context, trajectory, *, rng, profile):
                self.called = True
                return trajectory

        working = WorkingStrategy()
        pipeline = DetectorEvasionPipeline([FailingStrategy(), working])

        # Should not raise exception
        result = pipeline.apply(
            action="click",
            context={},
            trajectory=[((0.0, 0.0), 0.1)],
            rng=MagicMock(),
            profile=Profile(),
        )

        # Working strategy should still be called
        assert working.called
        # Result should still be a list
        assert isinstance(result, list)

    def test_multiple_strategies_compose(self):
        """Multiple strategies should compose their effects."""
        class AddPointStrategy(DetectorEvasionStrategy):
            def __init__(self, point):
                self.point = point

            def apply(self, action, context, trajectory, *, rng, profile):
                return trajectory + [self.point]

        pipeline = DetectorEvasionPipeline(
            [
                AddPointStrategy(((1.0, 1.0), 0.1)),
                AddPointStrategy(((2.0, 2.0), 0.2)),
                AddPointStrategy(((3.0, 3.0), 0.3)),
            ]
        )

        result = pipeline.apply(
            action="click",
            context={},
            trajectory=[((0.0, 0.0), 0.0)],
            rng=MagicMock(),
            profile=Profile(),
        )

        # Should have all 3 added points plus original
        assert len(result) == 4
        assert ((1.0, 1.0), 0.1) in result
        assert ((2.0, 2.0), 0.2) in result
        assert ((3.0, 3.0), 0.3) in result


class TestDefaultStealthPipeline:
    """Test DEFAULT_STEALTH_PIPELINE."""

    def test_default_pipeline_exists(self):
        """DEFAULT_STEALTH_PIPELINE should be defined."""
        assert DEFAULT_STEALTH_PIPELINE is not None
        assert isinstance(DEFAULT_STEALTH_PIPELINE, DetectorEvasionPipeline)

    def test_default_pipeline_has_strategies(self):
        """DEFAULT_STEALTH_PIPELINE should have strategies."""
        assert len(DEFAULT_STEALTH_PIPELINE.strategies) > 0

    def test_default_pipeline_contains_expected_strategies(self):
        """DEFAULT_STEALTH_PIPELINE should contain all expected strategies."""
        strategy_types = [type(s) for s in DEFAULT_STEALTH_PIPELINE.strategies]

        assert FittsLawStrategy in strategy_types
        assert OvershootStrategy in strategy_types
        assert ErrorInjectionStrategy in strategy_types
        assert MomentumScrollStrategy in strategy_types
        assert AttentionSimulationStrategy in strategy_types

    def test_default_pipeline_applies_strategies(self):
        """DEFAULT_STEALTH_PIPELINE should apply strategies without crashing."""
        trajectory = [((0.0, 0.0), 0.1), ((10.0, 10.0), 0.2)]

        result = DEFAULT_STEALTH_PIPELINE.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        # Should return a list
        assert isinstance(result, list)

    def test_default_pipeline_with_naturalistic_profile(self):
        """DEFAULT_STEALTH_PIPELINE should handle NATURALISTIC profile gracefully."""
        trajectory = [((0.0, 0.0), 0.1)]

        result = DEFAULT_STEALTH_PIPELINE.apply(
            action="click",
            context={},
            trajectory=trajectory,
            rng=MagicMock(),
            profile=Profile(),
        )

        # Should return a list (unchanged because NATURALISTIC profile)
        assert isinstance(result, list)


class TestPipelineIntegration:
    """Integration tests for pipeline with real scenarios."""

    def test_click_action_with_full_context(self):
        """Pipeline should handle click action with full context."""
        trajectory = [((0.0, 0.0), 0.1), ((100.0, 100.0), 0.3)]
        context = {
            "target_size": (20, 10),
            "start_position": (0, 0),
            "target_position": (100, 100),
            "action_context": "clicking_submit_button",
        }

        result = DEFAULT_STEALTH_PIPELINE.apply(
            action="click",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_type_action_with_full_context(self):
        """Pipeline should handle type action with full context."""
        trajectory = [0.1, 0.15, 0.12]
        context = {"text": "password", "field_type": "password"}

        result = DEFAULT_STEALTH_PIPELINE.apply(
            action="type",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert isinstance(result, list)

    def test_scroll_action_with_full_context(self):
        """Pipeline should handle scroll action with full context."""
        trajectory = [(120, 0.0)]
        context = {"scroll_delta": 120}

        result = DEFAULT_STEALTH_PIPELINE.apply(
            action="scroll",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert isinstance(result, list)

    def test_move_action_with_full_context(self):
        """Pipeline should handle move action with full context."""
        trajectory = [((0.0, 0.0), 0.1), ((50.0, 50.0), 0.2)]
        context = {
            "target_size": (30, 15),
            "start_position": (0, 0),
            "target_position": (50, 50),
        }

        result = DEFAULT_STEALTH_PIPELINE.apply(
            action="move",
            context=context,
            trajectory=trajectory,
            rng=MagicMock(),
            profile=StealthProfile(),
        )

        assert isinstance(result, list)
