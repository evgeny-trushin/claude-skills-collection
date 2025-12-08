#!/usr/bin/env bash
set -euo pipefail

# Ensure we are running under bash even if invoked via /bin/sh
if [[ -z "${BASH_VERSION:-}" ]]; then
  exec bash "$0" "$@"
fi

# Zip the Claude skill folder into coles-invoice-processor-claude-skill.zip

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_dir="$repo_root/03-coles-invoice-processor-claude-skill"
dest_zip="$repo_root/coles-invoice-processor-claude-skill.zip"

if [[ ! -d "$src_dir" ]]; then
  echo "Missing source directory: $src_dir" >&2
  exit 1
fi

rm -f "$dest_zip"
(
  cd "$repo_root"
  zip -r "$dest_zip" "$(basename "$src_dir")" >/dev/null
)

echo "Created $dest_zip"
