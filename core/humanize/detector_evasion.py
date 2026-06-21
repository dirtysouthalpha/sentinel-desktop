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

from abc import ABC, abstractmethod
from typing import Any

from core.humanize.profile import Profile, StealthProfile


class DetectorEvasionStrategy(ABC):
    """Base class for detector-evasion strategies."""

    @abstractmethod
    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Modify the trajectory to evade a specific detector class.

        Args:
            action: Action type (e.g., "click", "type", "scroll").
            context: Action metadata (target size, field type, etc.).
            trajectory: Current humanized trajectory.
            rng: Seeded random.Random.
            profile: Tempo profile (may be StealthProfile).

        Returns:
            Modified trajectory (may be the same object if no changes).
        """
        pass


class NoOpStrategy(DetectorEvasionStrategy):
    """No-op strategy that returns trajectory unchanged.

    Useful as a placeholder or for testing pipeline composition.
    """

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Return trajectory unchanged."""
        return trajectory


class FittsLawStrategy(DetectorEvasionStrategy):
    """Apply Fitts's-Law timing to movements.

    This strategy ensures movement duration scales with both distance AND
    target width (small targets take longer). Defeats timing-based detectors
    that flag robotic constant-velocity movements.
    """

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply Fitts's-Law timing to click/move actions.

        If not StealthProfile or target_size unavailable, returns trajectory unchanged.
        """
        if action not in ["click", "move"]:
            return trajectory

        if not isinstance(profile, StealthProfile):
            return trajectory

        target_size = context.get("target_size", None)
        if not target_size:
            return trajectory

        # Import here to avoid circular dependency
        from core.humanize.fitts import fitts_move_duration

        # Re-calculate trajectory duration with Fittsian timing
        start = context.get("start_position", (0, 0))
        target = context.get("target_position", (0, 0))

        try:
            fitts_duration = fitts_move_duration(
                start, target, target_size, rng=rng, profile=profile
            )

            # Scale trajectory to match Fitts duration
            if trajectory:
                current_total = sum(dwell for _, dwell in trajectory)
                if current_total > 0:
                    scale_factor = fitts_duration / current_total
                    scaled_trajectory = [
                        (pos, dwell * scale_factor) for pos, dwell in trajectory
                    ]
                    return scaled_trajectory
        except (ValueError, ZeroDivisionError):
            # Gracefully degrade on calculation errors
            pass

        return trajectory


class OvershootStrategy(DetectorEvasionStrategy):
    """Inject overshoot + correction for small targets.

    Real humans don't pixel-perfect targets — we undershoot/overshoot and
    then sweep-back with a micro-correction. This two-phase pattern is a
    strong human signal.
    """

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply overshoot+correction to click/move actions.

        If not StealthProfile or target_size unavailable, returns trajectory unchanged.
        """
        if action not in ["click", "move"]:
            return trajectory

        if not isinstance(profile, StealthProfile):
            return trajectory

        target_size = context.get("target_size", None)
        if not target_size:
            return trajectory

        # Import here to avoid circular dependency
        from core.humanize.overshoot import apply_overshoot_and_correction

        target = context.get("target_position", (0, 0))

        try:
            overshoot_landing, correction_target = apply_overshoot_and_correction(
                target, target_size, rng=rng, profile=profile
            )

            if correction_target is not None:
                # Build two-segment trajectory: start → overshoot → correction
                start = context.get("start_position", (0, 0))

                # Import motion helpers
                from core.humanize.motion import _build_trajectory_from_curve

                # Segment 1: start → overshoot
                segment1 = _build_trajectory_from_curve(
                    start, overshoot_landing, rng=rng, profile=profile
                )

                # Segment 2: overshoot → correction
                segment2 = _build_trajectory_from_curve(
                    overshoot_landing, correction_target, rng=rng, profile=profile
                )

                # Combine with tiny dwell at overshoot point (human reorients)
                combined = segment1 + [
                    ((overshoot_landing[0], overshoot_landing[1]), 0.02)
                ]
                combined += segment2

                return combined
        except (ValueError, AttributeError):
            # Gracefully degrade on errors
            pass

        return trajectory


class ErrorInjectionStrategy(DetectorEvasionStrategy):
    """Inject realistic typing errors and corrections.

    Perfect typing is robotic. Real operators mistype, notice, backspace,
    and retype. This strategy adds error-correction sequences to typed text.
    """

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply error injection to type actions.

        Note: For typing actions, 'trajectory' is interpreted as keystroke delays.
        Returns a modified delay list with backspaces and corrections included.
        """
        if action != "type":
            return trajectory

        if not isinstance(profile, StealthProfile):
            return trajectory

        # Import here to avoid circular dependency
        from core.humanize.errors import inject_errors_and_corrections

        text = context.get("text", "")
        if not text:
            return trajectory

        try:
            error_actions = inject_errors_and_corrections(text, rng=rng, profile=profile)

            # Convert (typed_text, delay) → flat delay list
            # This is a simplified conversion — executor handles actual backspace execution
            delays = []
            for typed, delay in error_actions:
                if typed:  # Regular keystrokes
                    char_count = len(typed.replace("\b", ""))
                    if char_count > 0:
                        delays.extend([delay] * char_count)
                else:  # Pause (empty string)
                    if delay > 0:
                        delays.append(delay)

            return delays if delays else trajectory
        except (ValueError, AttributeError):
            # Gracefully degrade on errors
            pass

        return trajectory


class MomentumScrollStrategy(DetectorEvasionStrategy):
    """Apply inertial scroll momentum.

    Mechanical scroll (fixed delta per click) is robotic. Real scroll wheels
    have physical inertia — the content keeps moving. This strategy converts
    discrete scroll events into momentum trajectories.
    """

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply momentum scroll to scroll actions.

        Note: For scroll actions, 'trajectory' is interpreted as (delta, dwell) tuples.
        """
        if action != "scroll":
            return trajectory

        if not isinstance(profile, StealthProfile):
            return trajectory

        # Import here to avoid circular dependency
        from core.humanize.scroll import momentum_scroll_trajectory

        delta = context.get("scroll_delta", 0)
        if not delta:
            return trajectory

        try:
            momentum_traj = momentum_scroll_trajectory(delta, rng=rng, profile=profile)

            # Interpret trajectory frames as (delta, dwell) instead of (position, dwell)
            # Return momentum trajectory which replaces single discrete scroll
            return momentum_traj
        except (ValueError, AttributeError):
            # Gracefully degrade on errors
            pass

        return trajectory


class AttentionSimulationStrategy(DetectorEvasionStrategy):
    """Simulate human attention patterns.

    Humans pause, re-read, and hesitate. Constant action tempo is robotic.
    This strategy inserts attention pauses before actions based on context.
    """

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply attention simulation to all actions.

        Inserts pauses at trajectory start when attention pause is triggered.
        """
        if not isinstance(profile, StealthProfile):
            return trajectory

        # Import here to avoid circular dependency
        from core.humanize.attention import attention_pause

        action_context = context.get("action_context", "")

        try:
            duration = attention_pause(
                action_context, rng=rng, profile=profile
            )

            if duration > 0:
                # Prepend attention pause to trajectory
                pause_point = ((0.0, 0.0), duration)
                return [pause_point] + trajectory
        except (ValueError, AttributeError):
            # Gracefully degrade on errors
            pass

        return trajectory


class DetectorEvasionPipeline:
    """Compose multiple strategies into a single pipeline.

    Strategies are applied in sequence. Each strategy receives the output
    of the previous strategy, allowing composition of multiple evasion
    techniques.
    """

    def __init__(self, strategies: list[DetectorEvasionStrategy]):
        """Initialize pipeline with a list of strategies.

        Args:
            strategies: Ordered list of strategies to apply. First strategy
                        runs first, last strategy runs last.
        """
        self.strategies = strategies

    def apply(
        self,
        action: str,
        context: dict[str, Any],
        trajectory: list[tuple[tuple[float, float], float]],
        *,
        rng: Any,  # random.Random
        profile: Profile,
    ) -> list[tuple[tuple[float, float], float]]:
        """Apply all strategies in sequence.

        Each strategy receives the trajectory output by the previous strategy.

        Args:
            action: Action type (e.g., "click", "type", "scroll").
            context: Action metadata (target size, field type, etc.).
            trajectory: Initial humanized trajectory.
            rng: Seeded random.Random.
            profile: Tempo profile.

        Returns:
            Final trajectory after all strategies applied.
        """
        result = trajectory

        for strategy in self.strategies:
            try:
                result = strategy.apply(action, context, result, rng=rng, profile=profile)
            except Exception:
                # Per-strategy failure degrades gracefully — continue with other strategies
                # This ensures a broken strategy doesn't break the entire pipeline
                pass

        return result


# Default pipeline for stealth mode
DEFAULT_STEALTH_PIPELINE = DetectorEvasionPipeline(
    [
        FittsLawStrategy(),
        OvershootStrategy(),
        ErrorInjectionStrategy(),
        MomentumScrollStrategy(),
        AttentionSimulationStrategy(),
    ]
)
"""Default stealth pipeline with all evasion strategies.

Applies strategies in order:
1. Fitts's-Law timing (movement scaling)
2. Overshoot+correction (target miss patterns)
3. Error injection (typing mistakes)
4. Momentum scroll (inertial scrolling)
5. Attention simulation (human pauses)

Strategies are applied to relevant actions only (e.g., scroll strategies
only affect scroll actions). Irrelevant strategies return trajectory unchanged.
"""
