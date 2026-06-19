"""Tests for main.py parse_args and installer/build.py functions."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── main.py: parse_args ──────────────────────────────────────────────────


class TestParseArgs:
    """Argument parsing for the main entry point."""

    def test_default_args(self) -> None:
        sys.argv = ["sentinel-desktop"]
        from main import parse_args

        args = parse_args()
        assert args.api is False
        assert args.command is None
        assert args.port == 8091
        assert args.host == "0.0.0.0"
        assert args.debug is False
        assert args.dry_run is False
        assert args.autonomous is False

    def test_api_mode(self) -> None:
        sys.argv = ["sentinel-desktop", "--api"]
        from main import parse_args

        args = parse_args()
        assert args.api is True

    def test_cli_mode(self) -> None:
        sys.argv = ["sentinel-desktop", "-c", "open notepad"]
        from main import parse_args

        args = parse_args()
        assert args.command == "open notepad"

    def test_custom_port_and_host(self) -> None:
        sys.argv = ["sentinel-desktop", "--api", "--port", "9999", "--host", "127.0.0.1"]
        from main import parse_args

        args = parse_args()
        assert args.port == 9999
        assert args.host == "127.0.0.1"

    def test_debug_and_dry_run(self) -> None:
        sys.argv = ["sentinel-desktop", "--debug", "--dry-run"]
        from main import parse_args

        args = parse_args()
        assert args.debug is True
        assert args.dry_run is True

    def test_autonomous_flag(self) -> None:
        sys.argv = ["sentinel-desktop", "--autonomous"]
        from main import parse_args

        args = parse_args()
        assert args.autonomous is True


# ── installer/build.py: generate_inno_setup ──────────────────────────────


class TestGenerateInnoSetup:
    """Inno Setup .iss generation."""

    def test_generates_iss_file(self, tmp_path: Path) -> None:
        with patch.dict(sys.modules, {"core": MagicMock(__version__="1.0.0")}):
            from installer import build

            # Override paths to use tmp_path
            orig_installer_dir = build.INSTALLER_DIR
            orig_dist_dir = build.DIST_DIR
            orig_root_dir = build.ROOT_DIR
            orig_icon_path = build.ICON_PATH
            orig_version = build.APP_VERSION

            build.INSTALLER_DIR = tmp_path / "installer"
            build.DIST_DIR = tmp_path / "dist"
            build.ROOT_DIR = tmp_path
            build.ICON_PATH = tmp_path / "assets" / "icon.ico"
            build.APP_VERSION = "1.0.0"

            try:
                result = build.generate_inno_setup()
                assert result  # non-empty string
                assert Path(result).exists()
                content = Path(result).read_text(encoding="utf-8")
                assert "SentinelDesktop" in content
                assert "1.0.0" in content
                assert "[Setup]" in content
                assert "[Files]" in content
            finally:
                build.INSTALLER_DIR = orig_installer_dir
                build.DIST_DIR = orig_dist_dir
                build.ROOT_DIR = orig_root_dir
                build.ICON_PATH = orig_icon_path
                build.APP_VERSION = orig_version

    def test_iss_contains_app_guid(self, tmp_path: Path) -> None:
        with patch.dict(sys.modules, {"core": MagicMock(__version__="2.5.0")}):
            from installer import build

            orig_installer_dir = build.INSTALLER_DIR
            orig_dist_dir = build.DIST_DIR
            orig_root_dir = build.ROOT_DIR
            orig_icon_path = build.ICON_PATH
            orig_version = build.APP_VERSION

            build.INSTALLER_DIR = tmp_path / "installer"
            build.DIST_DIR = tmp_path / "dist"
            build.ROOT_DIR = tmp_path
            build.ICON_PATH = tmp_path / "assets" / "icon.ico"
            build.APP_VERSION = "2.5.0"

            try:
                result = build.generate_inno_setup()
                content = Path(result).read_text(encoding="utf-8")
                assert build.APP_GUID in content
                assert "2.5.0" in content
            finally:
                build.INSTALLER_DIR = orig_installer_dir
                build.DIST_DIR = orig_dist_dir
                build.ROOT_DIR = orig_root_dir
                build.ICON_PATH = orig_icon_path
                build.APP_VERSION = orig_version


# ── installer/build.py: clean ────────────────────────────────────────────


class TestBuildClean:
    """clean() removes build artifacts safely."""

    def test_clean_with_no_artifacts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from installer import build

        orig_build_dir = build.BUILD_DIR
        orig_dist_dir = build.DIST_DIR
        orig_spec_file = build.SPEC_FILE

        build.BUILD_DIR = tmp_path / "build"
        build.DIST_DIR = tmp_path / "dist"
        build.SPEC_FILE = tmp_path / "test.spec"

        try:
            build.clean()
            captured = capsys.readouterr()
            assert "Clean complete" in captured.out
        finally:
            build.BUILD_DIR = orig_build_dir
            build.DIST_DIR = orig_dist_dir
            build.SPEC_FILE = orig_spec_file

    def test_clean_removes_dirs(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from installer import build

        build_dir = tmp_path / "build"
        dist_dir = tmp_path / "dist"
        spec_file = tmp_path / "test.spec"
        build_dir.mkdir()
        dist_dir.mkdir()
        spec_file.write_text("spec", encoding="utf-8")

        orig_build_dir = build.BUILD_DIR
        orig_dist_dir = build.DIST_DIR
        orig_spec_file = build.SPEC_FILE

        build.BUILD_DIR = build_dir
        build.DIST_DIR = dist_dir
        build.SPEC_FILE = spec_file

        try:
            build.clean()
            assert not build_dir.exists()
            assert not dist_dir.exists()
            assert not spec_file.exists()
        finally:
            build.BUILD_DIR = orig_build_dir
            build.DIST_DIR = orig_dist_dir
            build.SPEC_FILE = orig_spec_file


# ── installer/build.py: build_exe ────────────────────────────────────────


class TestBuildExe:
    """build_exe() handles missing PyInstaller gracefully."""

    def test_build_exe_no_pyinstaller(self, capsys: pytest.CaptureFixture[str]) -> None:
        from installer import build

        with patch.dict(sys.modules, {"PyInstaller": None}):
            # Force ImportError
            with patch("builtins.__import__", side_effect=ImportError("no pyinstaller")):
                result = build.build_exe()
                assert result is False
                captured = capsys.readouterr()
                assert "PyInstaller" in captured.out


# ── installer/build.py: build_main ───────────────────────────────────────


class TestBuildMain:
    """main() dispatches to correct functions."""

    def test_main_clean(self, capsys: pytest.CaptureFixture[str]) -> None:
        from installer import build

        with patch.object(build, "clean") as mock_clean:
            with patch("sys.argv", ["build.py", "--clean"]):
                build.main()
                mock_clean.assert_called_once()

    def test_main_no_args_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        from installer import build

        with patch("sys.argv", ["build.py"]):
            build.main()
            captured = capsys.readouterr()
            assert "Sentinel Desktop Build System" in captured.out
