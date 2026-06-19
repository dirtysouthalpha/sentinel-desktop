"""Tests for installer/build.py build_portable() function."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure installer/ is importable from the project root
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import installer.build as build_mod
from installer.build import build_portable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_pyinstaller(monkeypatch):
    """Patch PyInstaller import to succeed and subprocess.run to return 0."""
    fake_pyi = MagicMock()
    monkeypatch.setitem(sys.modules, "PyInstaller", fake_pyi)


def _fake_run_ok(app_dir: Path):
    """Return a subprocess.run that succeeds and creates the expected app dir."""

    def _run(cmd, **kwargs):
        app_dir.mkdir(parents=True, exist_ok=True)
        result = MagicMock()
        result.returncode = 0
        return result

    return _run


# ---------------------------------------------------------------------------
# build_portable
# ---------------------------------------------------------------------------

class TestBuildPortable:
    def test_build_portable_invokes_onedir(self, tmp_path, monkeypatch):
        """--onedir must appear in the PyInstaller command."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")  # not exists

        profile_dir = tmp_path / "profiles" / "test-profile"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()

        app_dir = tmp_path / "dist" / "portable" / "SentinelDesktop"

        captured = []

        def _run(cmd, **kwargs):
            captured.extend(cmd)
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run):
            result = build_portable(
                profile="test-profile",
                bundle_playwright=False,
                out_dir=tmp_path / "dist" / "portable",
            )

        assert result is True
        assert "--onedir" in captured

    def test_build_portable_no_onefile(self, tmp_path, monkeypatch):
        """--onefile must NOT appear in the portable PyInstaller command."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()
        app_dir = tmp_path / "dist" / "portable" / "SentinelDesktop"

        captured = []

        def _run(cmd, **kwargs):
            captured.extend(cmd)
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run):
            build_portable(profile="p", bundle_playwright=False, out_dir=tmp_path / "dist" / "portable")

        assert "--onefile" not in captured

    def test_build_portable_no_inno_setup(self, tmp_path, monkeypatch):
        """Inno Setup (generate_inno_setup) must NOT be called during portable build."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()
        app_dir = tmp_path / "dist" / "portable" / "SentinelDesktop"

        def _run(cmd, **kwargs):
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run), \
             patch.object(build_mod, "generate_inno_setup") as mock_inno:
            build_portable(profile="p", bundle_playwright=False, out_dir=tmp_path / "dist" / "portable")

        mock_inno.assert_not_called()

    def test_build_portable_embeds_profile(self, tmp_path, monkeypatch):
        """The chosen profile directory must be passed via --add-data."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "my-profile"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()
        app_dir = tmp_path / "dist" / "portable" / "SentinelDesktop"

        captured = []

        def _run(cmd, **kwargs):
            captured.extend(cmd)
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run):
            build_portable(profile="my-profile", bundle_playwright=False, out_dir=tmp_path / "dist" / "portable")

        # --add-data should include the profile path
        add_data_args = [
            captured[i + 1]
            for i, v in enumerate(captured)
            if v == "--add-data"
        ]
        assert any("my-profile" in arg for arg in add_data_args)

    def test_build_portable_creates_portable_data_marker(self, tmp_path, monkeypatch):
        """portable_data/ must be created next to exe to activate portable mode."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()
        app_dir = tmp_path / "dist" / "portable" / "SentinelDesktop"

        def _run(cmd, **kwargs):
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run):
            result = build_portable(profile="p", bundle_playwright=False, out_dir=tmp_path / "dist" / "portable")

        assert result is True
        assert (app_dir / "portable_data").is_dir()

    def test_build_portable_missing_profile_returns_false(self, tmp_path, monkeypatch):
        """Return False without calling PyInstaller if profile dir does not exist."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")
        (tmp_path / "main.py").touch()

        with patch("installer.build.subprocess.run") as mock_run:
            result = build_portable(profile="nonexistent", bundle_playwright=False)

        assert result is False
        mock_run.assert_not_called()

    def test_build_portable_pyinstaller_missing_returns_false(self, tmp_path, monkeypatch):
        """Return False when PyInstaller is not installed."""
        # Ensure PyInstaller raises ImportError
        monkeypatch.setitem(sys.modules, "PyInstaller", None)

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)

        result = build_portable(profile="p", bundle_playwright=False)
        assert result is False

    def test_build_portable_pyinstaller_failure_returns_false(self, tmp_path, monkeypatch):
        """Return False when PyInstaller exits with non-zero."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()

        def _fail(cmd, **kwargs):
            r = MagicMock()
            r.returncode = 1
            return r

        with patch("installer.build.subprocess.run", side_effect=_fail):
            result = build_portable(profile="p", bundle_playwright=False, out_dir=tmp_path / "dist" / "portable")

        assert result is False

    def test_build_portable_skips_playwright_when_flag_false(self, tmp_path, monkeypatch):
        """ms-playwright must not appear in --add-data when bundle_playwright=False."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()
        app_dir = tmp_path / "dist" / "portable" / "SentinelDesktop"

        captured = []

        def _run(cmd, **kwargs):
            captured.extend(cmd)
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run):
            build_portable(profile="p", bundle_playwright=False, out_dir=tmp_path / "dist" / "portable")

        add_data_args = [
            captured[i + 1]
            for i, v in enumerate(captured)
            if v == "--add-data"
        ]
        assert not any("ms-playwright" in arg for arg in add_data_args)

    def test_build_portable_custom_out_dir(self, tmp_path, monkeypatch):
        """Custom --out-dir is passed as the --distpath to PyInstaller."""
        _make_fake_pyinstaller(monkeypatch)
        monkeypatch.setattr(build_mod, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(build_mod, "DIST_DIR", tmp_path / "dist")
        monkeypatch.setattr(build_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(build_mod, "ICON_PATH", tmp_path / "icon.ico")

        profile_dir = tmp_path / "profiles" / "p"
        profile_dir.mkdir(parents=True)
        (tmp_path / "main.py").touch()
        custom_out = tmp_path / "my-output"
        app_dir = custom_out / "SentinelDesktop"

        captured = []

        def _run(cmd, **kwargs):
            captured.extend(cmd)
            app_dir.mkdir(parents=True, exist_ok=True)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("installer.build.subprocess.run", side_effect=_run):
            result = build_portable(profile="p", bundle_playwright=False, out_dir=custom_out)

        assert result is True
        # --distpath should point to custom_out
        distpath_idx = captured.index("--distpath")
        assert captured[distpath_idx + 1] == str(custom_out)
