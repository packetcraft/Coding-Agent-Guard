#!/usr/bin/env bash
# ============================================================
#  Coding Agent Guard — Start Dashboard
#  Usage: ./start.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HR="======================================================"

echo "$HR"
echo "  Coding Agent Guard — Dashboard"
echo "$HR"

# ── Check venv ────────────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo ""
    echo "  ERROR: venv not found."
    echo "         Run setup first:  ./setup.sh"
    exit 1
fi

# ── Activate ──────────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -f "venv/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source venv/Scripts/activate
else
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

# ── Check Ollama ──────────────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    if ! ollama list &>/dev/null 2>&1; then
        echo ""
        echo "  WARNING: Ollama is installed but does not appear to be running."
        echo "           Start it in a separate terminal:  ollama serve"
        echo "           The guard will fail open (allow all) until Ollama responds."
        echo ""
    fi
else
    echo ""
    echo "  WARNING: ollama not found — guard model unavailable."
    echo "           Install from https://ollama.com and run ./setup.sh"
    echo ""
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "  Starting dashboard..."
echo "  URL  : http://localhost:8501"
echo "  Logs : $(pwd)/audit/"
echo "  Stop : Ctrl+C"
echo ""

python dashboard.py
