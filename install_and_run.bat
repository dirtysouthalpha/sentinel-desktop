@echo off
title Sentinel Desktop v2 - Installer
echo ============================================
echo   Sentinel Desktop v2 - Installer
echo   AI-powered Windows desktop automation
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.8+ from python.org
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/3] Creating config directory...
if not exist "%APPDATA%\SentinelDesktop" mkdir "%APPDATA%\SentinelDesktop"

echo.
echo [3/3] Launching Sentinel Desktop...
echo.
python main.py
pause
