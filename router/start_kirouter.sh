#!/usr/bin/env bash
# =====================================================================
#   KiRouter - one-click server start for macOS / Linux.
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo
echo "  ===================================================================="
echo "    KiRouter - local web app autorouter for KiCad"
echo "    PSS Tools  -  github.com/IgmarMelis/kibridge"
echo "  ===================================================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is not installed or not on PATH."
    echo "Install Python 3.9+ from https://www.python.org/downloads/"
    exit 1
fi

# First-run venv
if [ ! -d ".venv" ]; then
    echo "  First run: creating virtual environment in .venv/"
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt

echo
echo "  Starting server on http://127.0.0.1:8765 ..."
echo "  Your browser should open automatically. Press Ctrl+C to stop."
echo

python -m kirouter
