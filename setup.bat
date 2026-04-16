@echo off
:: ============================================================
::  Coding Agent Guard — Setup Script (Windows)
::  Usage:
::    setup.bat            first-time install
::    setup.bat /repair    wipe venv and reinstall from scratch
:: ============================================================
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set REPAIR=0
if /i "%1"=="/repair"  set REPAIR=1
if /i "%1"=="--repair" set REPAIR=1

set HR=======================================================

echo !HR!
echo   Coding Agent Guard -- Setup
if !REPAIR!==1 echo   Mode: REPAIR (venv will be recreated^)
echo !HR!

:: ── 1. Python ────────────────────────────────────────────────────────────────
echo.
echo [ 1/6 ] Checking Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python not found.
    echo          Install Python 3.9+ from https://python.org
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,9) else 1)"
if errorlevel 1 (
    echo   ERROR: Python 3.9+ required.
    python --version
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   OK -- %%v

:: ── 2. Ollama ─────────────────────────────────────────────────────────────────
echo.
echo [ 2/6 ] Checking Ollama...

set OLLAMA_OK=0
ollama --version >nul 2>&1
if not errorlevel 1 (
    set OLLAMA_OK=1
    for /f "tokens=*" %%v in ('ollama --version 2^>^&1') do echo   OK -- %%v
) else (
    echo   WARNING: ollama not found on PATH.
    echo            Install from https://ollama.com and re-run to pull the guard model.
    echo            The guard will fail open ^(allow all calls^) until Ollama is available.
)

:: ── 3. Virtual environment ────────────────────────────────────────────────────
echo.
echo [ 3/6 ] Virtual environment...

if !REPAIR!==1 (
    if exist venv (
        echo   Removing existing venv (repair mode^)...
        rmdir /s /q venv
    )
)

if not exist venv (
    echo   Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo   ERROR: Failed to create venv.
        exit /b 1
    )
    echo   OK -- venv created.
) else (
    echo   OK -- venv already exists. Run with /repair to recreate.
)

:: Activate
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo   ERROR: Could not activate venv.
    exit /b 1
)

:: ── 4. Install package ────────────────────────────────────────────────────────
echo.
echo [ 4/6 ] Installing package...

pip install -e . --quiet
if errorlevel 1 (
    echo   ERROR: pip install failed.
    exit /b 1
)

for /f "tokens=*" %%p in ('where coding-agent-guard 2^>nul') do (
    echo   OK -- coding-agent-guard installed at: %%p
    goto :pip_done
)
echo   OK -- coding-agent-guard installed.
:pip_done

:: ── 5. Pull Ollama model ──────────────────────────────────────────────────────
echo.
echo [ 5/6 ] Guard model (qwen2.5:1.5b^)...

if !OLLAMA_OK!==1 (
    echo   Pulling model (this may take a minute on first run^)...
    ollama pull qwen2.5:1.5b
    echo   OK -- model ready.
) else (
    echo   SKIPPED -- Ollama not available.
)

:: ── 6. Install hooks for this repo ───────────────────────────────────────────
echo.
echo [ 6/6 ] Installing guard hooks for this repo...
python install_hooks.py .
echo.

:: Ensure audit dir exists
if not exist audit mkdir audit

:: ── Done ──────────────────────────────────────────────────────────────────────
echo !HR!
echo   Setup complete!
echo.
echo   Quick start:
echo     start.bat                          Launch the dashboard
echo     coding-agent-guard shadow-ai       Run a Shadow AI posture scan
echo.
echo   Protect another repo:
echo     python install_hooks.py C:\path\to\repo
echo.
echo   Enable blocking (default is audit-only / observe mode^):
echo     Edit coding_agent_guard\rules\config.yaml
echo     Set:  audit_only: false
echo !HR!

endlocal
