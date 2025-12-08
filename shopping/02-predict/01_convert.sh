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
    echo "Installing dependencies..."
    pip install -r requirements.txt
else
    echo "Error: requirements.txt not found."
    exit 1
fi

# Run the conversion script
echo "Running conversion script..."
python3 01_convert.py

# Run the obfuscation script
echo "Running obfuscation script..."
python3 02_obfuscate.py

# Run the extraction script
echo "Running extraction script..."
python3 03_extract_data.py

echo "Done!"
