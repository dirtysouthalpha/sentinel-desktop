"""Tests for portable-mode Tesseract path resolution in core/utils.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


def _reset_tesseract_cache():
    """Reset the module-level Tesseract probe cache so have_tesseract() re-runs."""
    import core.utils as utils_mod

    utils_mod._TESSERACT_OK = None
    utils_mod._pytesseract = None


# ---------------------------------------------------------------------------
# _resolve_portable_tesseract
# ---------------------------------------------------------------------------


class TestResolvePortableTesseract:
    def test_non_portable_returns_none(self):
        from core.utils import _resolve_portable_tesseract

        with patch("core.utils._is_portable", return_value=False):
            assert _resolve_portable_tesseract() is None

    def test_portable_no_meipass_no_internal_returns_none(self, tmp_path):
        """Portable mode but bundle dir doesn't exist → None (graceful degrade)."""
        from core.utils import _resolve_portable_tesseract

        with patch("core.utils._is_portable", return_value=True):
            # sys._MEIPASS absent, _internal/ not present next to exe
            with patch.object(sys, "_MEIPASS", str(tmp_path / "nonexistent"), create=True):
                with patch("sys.executable", str(tmp_path / "SentinelDesktop")):
                    result = _resolve_portable_tesseract()
        assert result is None

    def test_portable_meipass_binary_found_linux(self, tmp_path):
        """When _MEIPASS/tesseract/tesseract exists, return its path."""
        from core.utils import _resolve_portable_tesseract

        tess_dir = tmp_path / "tesseract"
        tess_dir.mkdir()
        binary = tess_dir / "tesseract"
        binary.touch()

        with patch("core.utils._is_portable", return_value=True):
            with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
                with patch("sys.platform", "linux"):
                    result = _resolve_portable_tesseract()

        assert result == str(binary)

    def test_portable_meipass_binary_found_windows(self, tmp_path):
        """On Windows, look for tesseract.exe."""
        from core.utils import _resolve_portable_tesseract

        tess_dir = tmp_path / "tesseract"
        tess_dir.mkdir()
        binary = tess_dir / "tesseract.exe"
        binary.touch()

        with patch("core.utils._is_portable", return_value=True):
            with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
                with patch("sys.platform", "win32"):
                    result = _resolve_portable_tesseract()

        assert result == str(binary)

    def test_portable_tessdata_sets_env_var(self, tmp_path, monkeypatch):
        """When tessdata/ dir is present, TESSDATA_PREFIX env var is set."""
        from core.utils import _resolve_portable_tesseract

        tess_dir = tmp_path / "tesseract"
        tess_dir.mkdir()
        binary = tess_dir / "tesseract"
        binary.touch()
        tessdata = tess_dir / "tessdata"
        tessdata.mkdir()

        with patch("core.utils._is_portable", return_value=True):
            with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
                with patch("sys.platform", "linux"):
                    _resolve_portable_tesseract()

        import os

        assert os.environ.get("TESSDATA_PREFIX") == str(tessdata)

    def test_portable_fallback_internal_dir(self, tmp_path):
        """Falls back to _internal/ next to exe when sys._MEIPASS not set."""
        from core.utils import _resolve_portable_tesseract

        internal = tmp_path / "_internal"
        tess_dir = internal / "tesseract"
        tess_dir.mkdir(parents=True)
        binary = tess_dir / "tesseract"
        binary.touch()

        with patch("core.utils._is_portable", return_value=True):
            # Remove _MEIPASS attribute if present
            original = getattr(sys, "_MEIPASS", None)
            if hasattr(sys, "_MEIPASS"):
                delattr(sys, "_MEIPASS")
            try:
                with patch("sys.executable", str(tmp_path / "SentinelDesktop")):
                    with patch("sys.platform", "linux"):
                        result = _resolve_portable_tesseract()
            finally:
                if original is not None:
                    sys._MEIPASS = original

        assert result == str(binary)


# ---------------------------------------------------------------------------
# have_tesseract() portable path injection
# ---------------------------------------------------------------------------


class TestHaveTesseractPortable:
    def setup_method(self):
        _reset_tesseract_cache()

    def teardown_method(self):
        _reset_tesseract_cache()

    def test_portable_sets_tesseract_cmd(self, tmp_path):
        """In portable mode, have_tesseract() injects the bundled binary path."""
        import core.utils as utils_mod

        tess_dir = tmp_path / "tesseract"
        tess_dir.mkdir()
        binary = tess_dir / "tesseract"
        binary.touch()

        fake_pytesseract = MagicMock()
        fake_pytesseract.pytesseract = MagicMock()
        fake_pytesseract.pytesseract.tesseract_cmd = "tesseract"  # default
        fake_pytesseract.get_tesseract_version.return_value = "5.3.0"

        with patch("core.utils._is_portable", return_value=True):
            with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
                with patch("sys.platform", "linux"):
                    with patch.dict(sys.modules, {"pytesseract": fake_pytesseract}):
                        result = utils_mod.have_tesseract()

        assert result is True
        assert fake_pytesseract.pytesseract.tesseract_cmd == str(binary)

    def test_non_portable_no_path_injection(self, tmp_path):
        """In non-portable mode, tesseract_cmd is NOT overridden."""
        import core.utils as utils_mod

        fake_pytesseract = MagicMock()
        fake_pytesseract.pytesseract = MagicMock()
        fake_pytesseract.pytesseract.tesseract_cmd = "tesseract"
        fake_pytesseract.get_tesseract_version.return_value = "5.3.0"

        with patch("core.utils._is_portable", return_value=False):
            with patch.dict(sys.modules, {"pytesseract": fake_pytesseract}):
                result = utils_mod.have_tesseract()

        assert result is True
        # tesseract_cmd unchanged — not set to any bundled path
        assert fake_pytesseract.pytesseract.tesseract_cmd == "tesseract"

    def test_portable_no_bundled_binary_falls_through(self, tmp_path):
        """Portable mode with no bundled binary still tries system Tesseract."""
        import core.utils as utils_mod

        fake_pytesseract = MagicMock()
        fake_pytesseract.pytesseract = MagicMock()
        fake_pytesseract.pytesseract.tesseract_cmd = "tesseract"
        # Simulate system Tesseract available
        fake_pytesseract.get_tesseract_version.return_value = "5.0.0"

        with patch("core.utils._is_portable", return_value=True):
            # _MEIPASS points to empty dir — no bundled binary
            with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
                with patch("sys.executable", str(tmp_path / "SentinelDesktop")):
                    with patch("sys.platform", "linux"):
                        with patch.dict(sys.modules, {"pytesseract": fake_pytesseract}):
                            result = utils_mod.have_tesseract()

        # Should still succeed via system Tesseract
        assert result is True
        # tesseract_cmd not overridden (no bundled binary found)
        assert fake_pytesseract.pytesseract.tesseract_cmd == "tesseract"
