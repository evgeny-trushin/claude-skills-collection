#!/bin/bash

# Exit on error
set -e

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 could not be found."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install requirements
if [ -f "requirements.txt" ]; then
    if python3 -c "import pandas; import prophet" >/dev/null 2>&1; then
        echo "Dependencies already available; skipping install."
    else
        echo "Installing dependencies (this may take a while for Prophet)..."
        pip install -r requirements.txt
    fi
else
    echo "Error: requirements.txt not found."
    exit 1
fi

# Run the prediction script
echo "Running prediction script..."
python3 04_predict_orders.py

echo "Done!"
