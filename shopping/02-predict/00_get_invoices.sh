#!/bin/bash

python3 00_get_invoices.py

echo ""
echo "Opening 01-redact/input_invoices/ folder..."
if command -v open >/dev/null 2>&1; then
    if ! open ../01-redact/input_invoices/; then
        echo "Warning: Could not open folder automatically."
    fi
else
    echo "Warning: 'open' command not available."
fi

echo ""
echo "Please place all downloaded invoices in the folder below:"
echo "  → 01-redact/input_invoices/"
echo ""
