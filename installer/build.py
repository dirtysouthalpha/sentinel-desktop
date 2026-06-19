"""
Sentinel Desktop — Build Script
PyInstaller EXE builder + Inno Setup installer generator.

Usage:
    python installer/build.py --exe        # Build standalone EXE
    python installer/build.py --installer  # Generate Inno Setup .iss
    python installer/build.py --all        # Build everything
    python installer/build.py --clean      # Remove build artifacts
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Make the project root importable so we can read core.__version__.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core import __version__ as APP_VERSION  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────

APP_NAME = "SentinelDesktop"
APP_PUBLISHER = "Sentinel Labs"
APP_URL = "https://github.com/dirtysouthalpha/sentinel-desktop"
# Stable GUID for Inno Setup upgrade detection. Must NOT change across versions.
APP_GUID = "8C2F4A6E-3B5D-4F7C-A9E1-1D0E6B8F2A45"

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
SPEC_FILE = ROOT_DIR / f"{APP_NAME}.spec"
ICON_PATH = ROOT_DIR / "assets" / "icon.ico"
INSTALLER_DIR = ROOT_DIR / "installer"

HIDDEN_IMPORTS = [
    "core.engine",
    "core.action_executor",
    "core.screenshot",
    "core.llm_client",
    "core.forensic_log",
    "core.checkpoint",
    "core.smart_wait",
    "core.mfa_detection",
    "core.system_info",
    "core.window_manager",
    "core.virtual_desktop",
    "core.failsafe",
    "core.recorder",
    "core.script_engine",
    "core.powershell",
    "core.workflow",
    "core.scheduler",
    "core.notifications",
    "core.plugin_loader",
    "core.auth",
    "core.encryption",
    "core.audit_export",
    "core.command_palette",
    "core.provider_registry",
    "core.tool_schemas",
    "gui.app",
    "gui.themes",
    "gui.recorder_panel",
    "gui.tabs.scripts_tab",
    "gui.tabs.workflows_tab",
    "gui.tabs.history_tab",
    "gui.tabs.settings_tab",
    "gui.system_tray",
    "api.server",
    "customtkinter",
    "PIL",
    "pystray",
]


def _find_tesseract_binary(explicit_path: str | None = None) -> Path | None:
    """Locate the Tesseract binary for bundling.

    Priority: explicit path arg → pytesseract.tesseract_cmd → shutil.which.
    Returns None if not found (build continues with a warning, OCR degrades).
    """
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
        print(f"  ⚠ Tesseract binary not found at specified path: {p}")
        return None

    try:
        import pytesseract  # type: ignore

        cmd = pytesseract.pytesseract.tesseract_cmd
        if cmd and Path(cmd).exists():
            return Path(cmd)
    except ImportError:
        pass

    for name in ("tesseract", "tesseract.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)

    return None


def _find_tessdata_eng(tesseract_bin: Path) -> Path | None:
    """Locate eng.traineddata near the Tesseract binary.

    Checks tessdata/ directories relative to the binary, then common Linux
    system paths. Returns None if not found.
    """
    checks = [
        tesseract_bin.parent / "tessdata" / "eng.traineddata",
        tesseract_bin.parent.parent / "tessdata" / "eng.traineddata",
        tesseract_bin.parent.parent / "share" / "tessdata" / "eng.traineddata",
    ]
    for path in checks:
        if path.exists():
            return path

    # Linux: /usr/share/tesseract-ocr/<version>/tessdata/
    tesseract_ocr_dir = tesseract_bin.parent.parent / "share" / "tesseract-ocr"
    if tesseract_ocr_dir.is_dir():
        for version_dir in sorted(tesseract_ocr_dir.iterdir(), reverse=True):
            candidate = version_dir / "tessdata" / "eng.traineddata"
            if candidate.exists():
                return candidate

    return None


def clean() -> None:
    """Remove build artifacts."""
    for path in [BUILD_DIR, DIST_DIR]:
        if path.exists():
            try:
                shutil.rmtree(path)
                print(f"  Removed {path}")
            except OSError as exc:
                print(f"  ⚠ Could not remove {path}: {exc}")
    if SPEC_FILE.exists():
        try:
            SPEC_FILE.unlink()
            print(f"  Removed {SPEC_FILE}")
        except OSError as exc:
            print(f"  ⚠ Could not remove {SPEC_FILE}: {exc}")
    print("✅ Clean complete")


def build_exe() -> bool:
    """Build standalone Windows EXE via PyInstaller."""
    print(f"🔨 Building {APP_NAME} v{APP_VERSION}...")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("❌ PyInstaller not installed. Run: pip install pyinstaller")
        return False

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        APP_NAME,
        "--windowed",
        "--onefile",
        "--noconfirm",
    ]

    if ICON_PATH.exists():
        cmd.extend(["--icon", str(ICON_PATH)])
        print(f"  Icon: {ICON_PATH}")

    # Add data directories
    for data_dir in ["config", "scripts", "plugins", "assets"]:
        src = ROOT_DIR / data_dir
        if src.exists():
            cmd.extend(["--add-data", f"{src};{data_dir}"])
            print(f"  Data: {data_dir}/")

    # Hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    # UPX compression
    upx_path = shutil.which("upx")
    if upx_path:
        cmd.extend(["--upx-dir", str(Path(upx_path).parent)])
        print(f"  UPX: {upx_path}")

    cmd.extend(
        [
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(BUILD_DIR),
            "--specpath",
            str(ROOT_DIR),
            str(ROOT_DIR / "main.py"),
        ]
    )

    print("  Running PyInstaller...")
    try:
        result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"❌ PyInstaller invocation failed: {exc}")
        return False

    if result.returncode == 0:
        exe_path = DIST_DIR / f"{APP_NAME}.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"✅ Built: {exe_path} ({size_mb:.1f} MB)")
            return True
    print(f"❌ Build failed (exit {result.returncode})")
    return False


def generate_inno_setup() -> str:
    """Generate Inno Setup .iss file for Windows installer."""
    print("📜 Generating Inno Setup script...")

    iss_content = f"""; Sentinel Desktop v{APP_VERSION} — Inno Setup Installer
; Generated by installer/build.py

#define MyAppName "{APP_NAME}"
#define MyAppVersion "{APP_VERSION}"
#define MyAppPublisher "{APP_PUBLISHER}"
#define MyAppURL "{APP_URL}"
#define MyAppExeName "{APP_NAME}.exe"

[Setup]
AppId={{{{{APP_GUID}}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppVerName={{#MyAppName}} {{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
OutputDir={INSTALLER_DIR / "output"}
OutputBaseFilename=SentinelDesktop-{APP_VERSION}-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayName={{#MyAppName}}
SetupIconFile={ICON_PATH if ICON_PATH.exists() else ""}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"
Name: "startmenuicon"; Description: "Create Start Menu shortcut"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
Source: "{DIST_DIR}\\{{#MyAppExeName}}"; DestDir: "{{app}}"; Flags: ignoreversion
Source: "{ROOT_DIR}\\config\\*"; DestDir: "{{app}}\\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{ROOT_DIR}\\scripts\\*"; DestDir: "{{app}}\\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{ROOT_DIR}\\plugins\\*"; DestDir: "{{app}}\\plugins"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{group}}\\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#MyAppName}}}}"; Flags: nowait postinstall skipifsilent
"""
    iss_path = INSTALLER_DIR / "sentinel-desktop.iss"
    try:
        INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
        with iss_path.open("w", encoding="utf-8") as f:
            f.write(iss_content)
    except OSError as exc:
        print(f"❌ Failed to write .iss file: {exc}")
        return ""

    print(f"✅ Generated: {iss_path}")
    return str(iss_path)


def build_portable(
    profile: str = "field-it-tech",
    bundle_playwright: bool = True,
    out_dir: Path | None = None,
    tesseract_bin: str | None = None,
) -> bool:
    """Build a portable --onedir bundle with an embedded profile.

    Unlike build_exe() which produces a single-file --onefile EXE, this
    produces an --onedir folder that is USB-portable:
    - No installer, no registry writes, no admin rights required.
    - ``portable_data/`` directory is created next to the exe so
      ``core.paths.is_portable()`` activates on first launch.
    - The chosen profile directory is embedded at ``profiles/<name>/``.
    - Tesseract binary + eng.traineddata are bundled when found so OCR
      works without a separate system install.

    Args:
        profile: Name of a directory under ``profiles/`` to embed (default
                 ``"field-it-tech"``).
        bundle_playwright: If True, include Playwright browser binaries.
        out_dir: Override output directory (default ``dist/portable/``).
        tesseract_bin: Explicit path to Tesseract binary. Auto-detected if
                       None; build continues with a warning when not found.

    Returns:
        True on success, False on failure.
    """
    print(f"📦 Building portable {APP_NAME} v{APP_VERSION} (profile={profile})...")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("❌ PyInstaller not installed. Run: pip install pyinstaller")
        return False

    profile_dir = ROOT_DIR / "profiles" / profile
    if not profile_dir.is_dir():
        print(f"❌ Profile not found: {profile_dir}")
        return False

    portable_out = out_dir or DIST_DIR / "portable"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        APP_NAME,
        "--windowed",
        "--onedir",  # NOT --onefile — portable bundles must be a folder
        "--noconfirm",
    ]

    if ICON_PATH.exists():
        cmd.extend(["--icon", str(ICON_PATH)])
        print(f"  Icon: {ICON_PATH}")

    # Bundle core data directories
    for data_dir in ["config", "plugins", "assets"]:
        src = ROOT_DIR / data_dir
        if src.exists():
            cmd.extend(["--add-data", f"{src};{data_dir}"])
            print(f"  Data: {data_dir}/")

    # Embed the selected profile
    cmd.extend(["--add-data", f"{profile_dir};profiles/{profile}"])
    print(f"  Profile: profiles/{profile}/")

    # Bundle Playwright if requested
    if bundle_playwright:
        playwright_browsers = Path.home() / ".cache" / "ms-playwright"
        if playwright_browsers.exists():
            cmd.extend(["--add-data", f"{playwright_browsers};ms-playwright"])
            print(f"  Playwright: {playwright_browsers}")
        else:
            print("  ℹ Playwright browsers not found — skipping bundling")

    # Bundle Tesseract binary + eng.traineddata (OCR without a separate install)
    tess = _find_tesseract_binary(tesseract_bin)
    if tess:
        cmd.extend(["--add-data", f"{tess};tesseract"])
        print(f"  Tesseract: {tess}")
        eng_data = _find_tessdata_eng(tess)
        if eng_data:
            cmd.extend(["--add-data", f"{eng_data};tesseract/tessdata"])
            print(f"  Tessdata: {eng_data}")
        else:
            print("  ⚠ eng.traineddata not found — OCR may be degraded in bundle")
    else:
        print("  ⚠ Tesseract not found — OCR unavailable in portable bundle")

    # Hidden imports (same as build_exe)
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    cmd.extend(
        [
            "--distpath",
            str(portable_out),
            "--workpath",
            str(BUILD_DIR / "portable"),
            "--specpath",
            str(ROOT_DIR),
            str(ROOT_DIR / "main.py"),
        ]
    )

    print("  Running PyInstaller (--onedir)...")
    try:
        result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"❌ PyInstaller invocation failed: {exc}")
        return False

    if result.returncode != 0:
        print(f"❌ Build failed (exit {result.returncode})")
        return False

    app_dir = portable_out / APP_NAME
    if not app_dir.exists():
        print(f"❌ Expected output directory not found: {app_dir}")
        return False

    # Create portable_data/ marker — presence activates core.paths portable mode
    portable_data = app_dir / "portable_data"
    portable_data.mkdir(exist_ok=True)
    (portable_data / ".gitkeep").touch()
    print(f"  Created portable marker: {portable_data}")

    print(f"✅ Portable build: {app_dir}")
    return True


def build_all() -> bool:
    """Build EXE then generate installer."""
    if not build_exe():
        return False
    iss_path = generate_inno_setup()
    print("\n🚀 Next step: compile the installer with Inno Setup:")
    print(f'   ISCC.exe "{iss_path}"')
    return True


def main() -> None:
    """Parse build-system CLI arguments and run requested build steps."""
    parser = argparse.ArgumentParser(description="Sentinel Desktop Build System")
    parser.add_argument("--exe", action="store_true", help="Build standalone EXE")
    parser.add_argument("--installer", action="store_true", help="Generate Inno Setup .iss")
    parser.add_argument("--all", action="store_true", help="Build everything")
    parser.add_argument("--clean", action="store_true", help="Remove build artifacts")
    parser.add_argument("--portable", action="store_true", help="Build portable --onedir bundle")
    parser.add_argument("--profile", default="field-it-tech", help="Profile to embed in portable build")
    parser.add_argument("--no-playwright", action="store_true", help="Skip bundling Playwright browsers")
    parser.add_argument("--out-dir", default=None, help="Override output directory for portable build")
    parser.add_argument("--tesseract-bin", default=None, dest="tesseract_bin",
                        help="Path to Tesseract binary (auto-detected if unset)")
    args = parser.parse_args()

    action_flags = (args.exe, args.installer, args.all, args.clean, args.portable)
    if not any(action_flags):
        parser.print_help()
        return

    if args.clean:
        clean()
    if args.exe:
        build_exe()
    if args.installer:
        generate_inno_setup()
    if args.all:
        build_all()
    if args.portable:
        out = Path(args.out_dir) if args.out_dir else None
        build_portable(
            profile=args.profile,
            bundle_playwright=not args.no_playwright,
            out_dir=out,
            tesseract_bin=args.tesseract_bin,
        )


if __name__ == "__main__":
    main()
