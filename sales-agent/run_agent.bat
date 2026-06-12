@echo off
title Ragnarok Sales Agent Launcher
cd /d "%~dp0"

echo [Ragnarok] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH! Please install Python 3.10+ from python.org.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [Ragnarok] Creating .env file from .env.example...
    copy .env.example .env
)

if not exist "venv" (
    echo [Ragnarok] Creating virtual environment...
    python -m venv venv
)

echo [Ragnarok] Activating virtual environment...
call venv\Scripts\activate

echo [Ragnarok] Installing/updating requirements...
pip install -r requirements.txt

echo [Ragnarok] Starting Sales Agent...
python main.py

pause
