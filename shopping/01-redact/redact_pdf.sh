#!/usr/bin/env bash
set -euo pipefail

# Ensure bash even when invoked via sh
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if python3 is available
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 could not be found." >&2
    exit 1
fi

VENV_DIR=".venv"
REQ_FILE="requirements.txt"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install pinned dependencies (quiet, no progress bar to avoid noisy box characters)
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_PROGRESS_BAR=off
export PIP_NO_INPUT=1

echo "Installing dependencies from $REQ_FILE..."
if python3 -c "import fitz" >/dev/null 2>&1; then
    echo "Dependencies already available; skipping install."
else
    python3 -m pip install --upgrade pip --quiet
    python3 -m pip install --quiet --no-cache-dir -r "$REQ_FILE"
fi

# Run the redaction script
echo "Running PDF redaction script..."
python3 redact_pdf.py

echo "Done!"
