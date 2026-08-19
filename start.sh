#!/usr/bin/env bash
set -e

echo "========================================================"
echo " [NoteFlow] Starting 100% Offline AI Meeting Notetaker"
echo "========================================================"
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[ERROR] Virtual environment not found."
    echo "Please run the installation script first:"
    echo "  bash scripts/install.sh"
    echo ""
    exit 1
fi

"$VENV_PYTHON" -m noteflow.main "$@"
