@echo off
:: ============================================================
::  Coding Agent Guard — Start Dashboard (Windows)
::  Usage: start.bat
:: ============================================================
setlocal

cd /d "%~dp0"

set HR=======================================================

echo !HR!
echo   Coding Agent Guard -- Dashboard
echo !HR!

:: ── Check venv ────────────────────────────────────────────────────────────────
if not exist venv (
    echo.
    echo   ERROR: venv not found.
    echo          Run setup first:  setup.bat
    exit /b 1
)

:: ── Activate ──────────────────────────────────────────────────────────────────
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo   ERROR: Could not activate venv.
    echo          Try running setup.bat /repair
    exit /b 1
)

:: ── Check Ollama ──────────────────────────────────────────────────────────────
ollama list >nul 2>&1
if errorlevel 1 (
    echo.
    echo   WARNING: Ollama does not appear to be running.
    echo            Start it in a separate window:  ollama serve
    echo            The guard will fail open ^(allow all^) until Ollama responds.
    echo.
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo   Starting dashboard...
echo   URL  : http://localhost:8501
echo   Logs : %CD%\audit\
echo   Stop : Ctrl+C
echo.

python dashboard.py

endlocal
