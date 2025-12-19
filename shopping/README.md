# Coles Order Prediction Toolkit

Automated pipeline for redacting Coles invoices, extracting purchase history, and predicting optimal reorder dates with $2 delivery windows.

## Quick Start

Run the complete pipeline:
```bash
./run.sh
```

This single command:
1. Shows latest invoice date and prompts you to download new invoices
2. Redacts sensitive data from PDFs
3. Converts invoices to structured data
4. Predicts next $2 delivery order windows

## Directory Structure

### `01-redact/`
Redacts sensitive data from invoice PDFs
- **Input:** `input_invoices/*.pdf` (raw downloads from Coles)
- **Output:** `input_invoices_redacted/*.pdf` (anonymized)
- **Scripts:**
  - `redact_pdf.sh` - Creates venv, installs dependencies, runs redaction
  - `redact_pdf.py` - Applies regex-based redactions (emails, addresses, card numbers)
  - `copy-invoices.sh` - Copies redacted PDFs to `02-predict/`

### `02-predict/`
Converts, extracts, and predicts future orders
- **Pipeline:**
  1. `00_get_invoices.sh` - Shows latest invoice date, opens input folder
  2. `01_convert.sh` - PDF → Markdown → obfuscated text → JSON extraction
  3. `05_predict_two_dollars_delivery_order.sh` - Forecasts next $2 delivery windows
- **Key Files:**
  - `output_extracted/extracted_data.json` - Structured purchase history
  - `output_extracted/in-stock.json` - Current stock levels
  - `05_predict_two_dollars_delivery_order.py` - Prophet-based forecasting with 30-day planning window

### `03-coles-invoice-processor-claude-skill/`
Claude skill for conversational invoice analysis
- Upload `coles-invoice-processor-claude-skill.zip` to https://claude.ai/settings/capabilities
- Enables chat-based predictions without local installation

### `04-pdf-presenation/`
User guide with screenshots and PDF generation scripts

## Processing Pipeline

```
Download → Redact → Convert → Extract → Predict
```

**Redaction:** Removes store numbers, emails, card hints, addresses using PyMuPDF
**Conversion:** PDF → Markdown (pymupdf4llm) → obfuscated text
**Extraction:** Parses categories, items, quantities, prices, dates into JSON
**Prediction:** Prophet forecasts purchase intervals, groups orders into $2 delivery windows

## Key Features

- **Automated Invoice Download Prompts:** Checks latest invoice and guides new downloads
- **Privacy-First:** Redacts all sensitive data before processing
- **Smart Forecasting:** 30-day planning window with promotional item analysis
- **Stock Management:** Tracks in-stock items to prevent duplicate orders
- **Delivery Optimization:** Groups predictions into $2 minimum delivery windows

## Commands

```bash
# Full pipeline (recommended)
./run.sh

# Individual steps
cd 01-redact && ./redact_pdf.sh
cd 02-predict && ./01_convert.sh
cd 02-predict && ./05_predict_two_dollars_delivery_order.sh

# Package Claude skill
./03-coles-invoice-processor-claude-skill/zip_skill.sh

# Regenerate guide
cd 04-pdf-presenation && ./create-presentation.sh
```
