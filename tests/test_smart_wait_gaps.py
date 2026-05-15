"""Gap tests for smart_wait.py — pure-PIL 0x0 image edge case."""

from PIL import Image


class TestPurePilEmptyImage:
    """0x0 image in pure-PIL path returns 0.0 (line 146)."""

    def test_pure_pil_zero_size_returns_zero(self) -> None:
        import core.smart_wait as sw_mod

        original = sw_mod._HAS_NUMPY
        try:
            sw_mod._HAS_NUMPY = False
            a = Image.new("RGB", (0, 0))
            b = Image.new("RGB", (0, 0))
            score = sw_mod._compute_change_score(a, b)
            assert score == 0.0
        finally:
            sw_mod._HAS_NUMPY = original
