#!/bin/bash
# Create PDF presentation for Coles Order Prediction Guide
# Usage: ./create-presentation.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Coles Order Prediction Guide - PDF Generator ==="

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install requirements from requirements-presentation.txt
echo "Installing dependencies..."
pip install --quiet -r requirements-presentation.txt

# Generate presentation
echo "Generating PDF presentation..."
python3 create_presentation.py

OUTPUT_FILE="Coles-Order-Prediction-Claude-Skill-Guide.pdf"
echo "Opening $OUTPUT_FILE..."
if command -v open >/dev/null 2>&1; then
    open -a Preview "$OUTPUT_FILE" || true
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$OUTPUT_FILE" || true
else
    echo "No opener found; PDF generated at: $SCRIPT_DIR/$OUTPUT_FILE"
fi

echo "=== Done ==="
