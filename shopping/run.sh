#!/bin/bash

set -e

echo "=== Step 0: Checking for new invoices ==="
cd 02-predict
./00_get_invoices.sh

echo ""
read -p "Have you downloaded all the latest invoices after the date shown above? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Pipeline cancelled. Please download the latest invoices and run again."
    exit 1
fi
echo "✓ User confirmed invoices downloaded"

cd ..

echo "=== Step 1: Running redact_pdf.py ==="
cd 01-redact

# Count files before redaction
BEFORE_COUNT=$(ls -1 input_invoices_redacted/*.pdf 2>/dev/null | wc -l | xargs)
echo "Files in input_invoices_redacted before: $BEFORE_COUNT"

# Run redaction
./redact_pdf.sh

# Count files after redaction
AFTER_COUNT=$(ls -1 input_invoices_redacted/*.pdf 2>/dev/null | wc -l | xargs)
echo "Files in input_invoices_redacted after: $AFTER_COUNT"

# Verify new files were created
if [ "$AFTER_COUNT" -gt "$BEFORE_COUNT" ]; then
    echo "✓ New redacted files created ($((AFTER_COUNT - BEFORE_COUNT)) new file(s))"
else
    echo "✗ No new files created in input_invoices_redacted"
fi

echo "=== Step 2: Cleaning input_invoices folder ==="
rm -rf input_invoices/*
echo "✓ Cleaned input_invoices folder"

echo "=== Step 3: Running copy-invoices.sh ==="
# Count files in destination before copy
DEST_BEFORE=$(ls -1 ../02-predict/input_invoices/*.pdf 2>/dev/null | wc -l | xargs)
echo "Files in 02-predict/input_invoices before: $DEST_BEFORE"

./copy-invoices.sh

# Count files in destination after copy
DEST_AFTER=$(ls -1 ../02-predict/input_invoices/*.pdf 2>/dev/null | wc -l | xargs)
echo "Files in 02-predict/input_invoices after: $DEST_AFTER"

if [ "$DEST_AFTER" -gt "$DEST_BEFORE" ]; then
    echo "✓ Files copied successfully ($((DEST_AFTER - DEST_BEFORE)) new file(s))"
else
    echo "✗ No new files copied to 02-predict/input_invoices"
fi

cd ..

echo "=== Step 4: Running 02-predict/01_convert.sh ==="
cd 02-predict
./01_convert.sh

echo "=== Step 5: Running 02-predict/05_predict_two_dollars_delivery_order.sh ==="
./05_predict_two_dollars_delivery_order.sh

cd ..
echo "=== Pipeline completed successfully ==="
