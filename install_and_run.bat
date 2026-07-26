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
echo [2/4] Creating config directory...
if not exist "%APPDATA%\SentinelDesktop" mkdir "%APPDATA%\SentinelDesktop"

echo.
echo [3/4] Checking Tesseract OCR (required for screen verification)...
set "TESS_FOUND="
where tesseract >nul 2>&1 && set "TESS_FOUND=1"
if not defined TESS_FOUND if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" set "TESS_FOUND=1"
if not defined TESS_FOUND if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" set "TESS_FOUND=1"
if defined TESS_FOUND (
    echo       Tesseract OCR detected.
) else (
    echo       [WARNING] Tesseract OCR not found. Screen text reading will be disabled.
    echo                 Install it with:  choco install tesseract -y
    echo                 or download:      https://github.com/UB-Mannheim/tesseract/wiki
    echo                 Sentinel will still run, but verification will be less reliable.
)

echo.
echo [4/4] Launching Sentinel Desktop...
echo.
python main.py
pause
