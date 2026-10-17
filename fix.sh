#!/usr/bin/env bash
# One-click wrapper for Linux and macOS. Requires python3 (preinstalled on virtually every distro).
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found. Install it with your package manager, then retry." >&2
  exit 1
fi
exec python3 fix.py "$@"
