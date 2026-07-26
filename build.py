#!/usr/bin/env python3
"""Build Sentinel Desktop Steel into a standalone Windows executable."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "sentinel_desktop.spec"


def clean():
    for d in (DIST, BUILD):
        if d.exists():
            print(f"Cleaning {d}...")
            shutil.rmtree(d)


def build():
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"Build failed with exit code {result.returncode}")
        sys.exit(1)


def create_installer():
    installer_dir = DIST / "SentinelDesktop"

    bat = r"""@echo off
echo ============================================
echo   Sentinel Desktop - Installer
echo ============================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\SentinelDesktop"

echo Installing to: %INSTALL_DIR%
echo.

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy /E /I /Y "%~dp0SentinelDesktop\*" "%INSTALL_DIR%"

echo.
echo Creating desktop shortcut...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Sentinel Desktop.lnk'); $s.TargetPath = '%INSTALL_DIR%\SentinelDesktop.exe'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Sentinel Desktop - AI Desktop Automation'; $s.Save()"

echo.
echo Creating start menu shortcut...
if not exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Sentinel Desktop" mkdir "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Sentinel Desktop"
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Sentinel Desktop\Sentinel Desktop.lnk'); $s.TargetPath = '%INSTALL_DIR%\SentinelDesktop.exe'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Sentinel Desktop - AI Desktop Automation'; $s.Save()"

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo   Launch from Desktop shortcut, Start Menu,
echo   or: %INSTALL_DIR%\SentinelDesktop.exe
echo.
pause
"""
    (DIST / "install.bat").write_text(bat, encoding="utf-8")

    uninstall = r"""@echo off
echo Uninstalling Sentinel Desktop...
rmdir /S /Q "%LOCALAPPDATA%\SentinelDesktop"
del "%USERPROFILE%\Desktop\Sentinel Desktop.lnk" 2>nul
rmdir /S /Q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Sentinel Desktop" 2>nul
echo Uninstall complete.
pause
"""
    (DIST / "uninstall.bat").write_text(uninstall, encoding="utf-8")


def main():
    print("=== Sentinel Desktop Steel Build ===\n")
    clean()
    build()
    create_installer()
    exe = DIST / "SentinelDesktop" / "SentinelDesktop.exe"
    if exe.exists():
        mb = exe.stat().st_size / (1024 * 1024)
        print(f"\nBuild successful! {mb:.1f} MB")
        print(f"  Run:  dist\\SentinelDesktop\\SentinelDesktop.exe")
        print(f"  Install:  dist\\install.bat")
    else:
        print(f"\nBuild failed - no exe at {exe}")
        sys.exit(1)


if __name__ == "__main__":
    main()
