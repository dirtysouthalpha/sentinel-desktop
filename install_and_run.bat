@echo off
title Sentinel Desktop v2.0 - Installer

echo ========================================
echo   Sentinel Desktop v2.0 - Installer
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo [OK] Python found.
echo.

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
echo.

REM Launch
echo Launching Sentinel Desktop...
python main.py
pause
