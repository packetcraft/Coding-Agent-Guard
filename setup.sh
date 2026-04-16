#!/usr/bin/env bash
# ============================================================
#  Coding Agent Guard — Setup Script
#  Usage:
#    ./setup.sh            first-time install
#    ./setup.sh --repair   wipe venv and reinstall from scratch
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REPAIR=false
[[ "$1" == "--repair" ]] && REPAIR=true

HR="======================================================"

echo "$HR"
echo "  Coding Agent Guard — Setup"
[[ $REPAIR == true ]] && echo "  Mode: REPAIR (venv will be recreated)"
echo "$HR"

# ── 1. Python ─────────────────────────────────────────────────────────────────
echo ""
echo "[ 1/6 ] Checking Python..."

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "  ERROR: Python not found."
    echo "         Install Python 3.9+ from https://python.org"
    exit 1
fi

$PYTHON -c "
import sys
if sys.version_info < (3, 9):
    print(f'  ERROR: Python 3.9+ required (found {sys.version})')
    sys.exit(1)
" || exit 1

echo "  OK — $($PYTHON --version)"

# ── 2. Ollama ─────────────────────────────────────────────────────────────────
echo ""
echo "[ 2/6 ] Checking Ollama..."

OLLAMA_OK=false
if command -v ollama &>/dev/null; then
    OLLAMA_OK=true
    echo "  OK — $(ollama --version 2>/dev/null || echo 'ollama found')"
else
    echo "  WARNING: ollama not found on PATH."
    echo "           Install from https://ollama.com and re-run to pull the guard model."
    echo "           The guard will fail open (allow all calls) until Ollama is available."
fi

# ── 3. Virtual environment ────────────────────────────────────────────────────
echo ""
echo "[ 3/6 ] Virtual environment..."

if [[ $REPAIR == true && -d "venv" ]]; then
    echo "  Removing existing venv (repair mode)..."
    rm -rf venv
fi

if [ ! -d "venv" ]; then
    echo "  Creating venv..."
    $PYTHON -m venv venv
    echo "  OK — venv created."
else
    echo "  OK — venv already exists (run with --repair to recreate)."
fi

# Activate — handle Git Bash on Windows vs macOS/Linux
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -f "venv/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source venv/Scripts/activate
else
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

# ── 4. Install package ────────────────────────────────────────────────────────
echo ""
echo "[ 4/6 ] Installing package..."
pip install -e . --quiet
echo "  OK — coding-agent-guard installed at: $(which coding-agent-guard)"

# ── 5. Pull Ollama model ──────────────────────────────────────────────────────
echo ""
echo "[ 5/6 ] Guard model (qwen2.5:1.5b)..."

if [[ $OLLAMA_OK == true ]]; then
    echo "  Pulling model (this may take a minute on first run)..."
    ollama pull qwen2.5:1.5b
    echo "  OK — model ready."
else
    echo "  SKIPPED — Ollama not available."
fi

# ── 6. Install hooks for this repo ────────────────────────────────────────────
echo ""
echo "[ 6/6 ] Installing guard hooks for this repo..."
python install_hooks.py .
echo ""

# ── Audit dir ─────────────────────────────────────────────────────────────────
mkdir -p audit

# ── Done ──────────────────────────────────────────────────────────────────────
echo "$HR"
echo "  Setup complete!"
echo ""
echo "  Quick start:"
echo "    ./start.sh                          Launch the dashboard"
echo "    coding-agent-guard shadow-ai        Run a Shadow AI posture scan"
echo ""
echo "  Protect another repo:"
echo "    python install_hooks.py /path/to/repo"
echo ""
echo "  Enable blocking (default is audit-only / observe mode):"
echo "    Edit coding_agent_guard/rules/config.yaml"
echo "    Set:  audit_only: false"
echo "$HR"
