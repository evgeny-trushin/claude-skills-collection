#!/usr/bin/env bash

set -euo pipefail

# Resolve paths relative to the repository root (script lives in 01-redact/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${PROJECT_ROOT}/01-redact/input_invoices_redacted"
DST_DIR="${PROJECT_ROOT}/02-predict/input_invoices"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "Source directory not found: ${SRC_DIR}" >&2
  exit 1
fi

mkdir -p "${DST_DIR}"

echo "Copying invoices from ${SRC_DIR} to ${DST_DIR}..."
cp -av "${SRC_DIR}/." "${DST_DIR}/"
echo "Done."
