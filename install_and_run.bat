@echo off
title Sentinel Windows - Installation and Launch

echo ========================================
echo Sentinel Windows Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo [2/3] Dependencies installed successfully!
echo.

echo [3/3] Launching Sentinel Windows...
echo.

python main.py

pause