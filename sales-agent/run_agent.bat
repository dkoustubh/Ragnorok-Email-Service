@echo off
title Ragnarok Sales Agent Launcher
cd /d "%~dp0"

echo [Ragnarok] Checking Python installation...

:: Try running default python from PATH
set "PYTHON_CMD=python"
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% equ 0 goto python_found

:: Check common default User AppData Python paths
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
    goto python_found
)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    goto python_found
)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    goto python_found
)

echo [Ragnarok] Python not found on this machine.
echo [Ragnarok] Starting automatic silent download and installation of Python 3.10...

:: Download Python installer using built-in curl
set "INSTALLER_URL=https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
set "INSTALLER_FILE=%TEMP%\python-3.10.11-amd64.exe"

echo [Ragnarok] Downloading Python installer...
curl -L -o "%INSTALLER_FILE%" "%INSTALLER_URL%"
if not exist "%INSTALLER_FILE%" (
    echo [ERROR] Failed to download Python installer. Please install Python 3.10 manually.
    pause
    exit /b 1
)

echo [Ragnarok] Installing Python silently (User folder, prepending to path)...
start /wait "" "%INSTALLER_FILE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1

:: Delete the installer
del "%INSTALLER_FILE%" >nul 2>&1

:: Re-verify installation paths
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
    goto python_found
)

%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python installation completed but python command could not be located.
    echo Please restart this terminal or install Python 3.10 manually.
    pause
    exit /b 1
)

:python_found
echo [Ragnarok] Python verified successfully.

:: Copy env file template if not exists
if not exist ".env" (
    echo [Ragnarok] Creating .env file from template...
    copy .env.example .env
)

:: Create virtual environment if not exists
if not exist "venv" (
    echo [Ragnarok] Creating virtual environment...
    "%PYTHON_CMD%" -m venv venv
)

echo [Ragnarok] Installing/updating dependencies...
venv\Scripts\pip install --upgrade pip
venv\Scripts\pip install -r requirements.txt

echo [Ragnarok] Starting Sales Agent daemon...
venv\Scripts\python main.py

pause
