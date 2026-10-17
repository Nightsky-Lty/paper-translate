#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"
bash scripts/start.sh
