#!/bin/bash

python3 00_get_invoices.py

echo ""
echo "Opening 01-redact/input_invoices/ folder..."
open ../01-redact/input_invoices/

echo ""
echo "Please place all downloaded invoices in the folder that just opened:"
echo "  → 01-redact/input_invoices/"
echo ""
