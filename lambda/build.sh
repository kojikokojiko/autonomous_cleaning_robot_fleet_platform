#!/usr/bin/env bash
# Build Lambda deployment packages (zip files)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUNCTIONS=("telemetry-processor" "ws-connection-manager" "ws-event-pusher")

for fn in "${FUNCTIONS[@]}"; do
  echo "Building $fn..."
  fn_dir="$SCRIPT_DIR/$fn"
  tmp_dir=$(mktemp -d)

  pip install -r "$fn_dir/requirements.txt" -t "$tmp_dir" --quiet
  cp "$fn_dir/handler.py" "$tmp_dir/"

  (cd "$tmp_dir" && zip -r "$fn_dir/function.zip" . -x "*.pyc" -x "__pycache__/*")
  rm -rf "$tmp_dir"
  echo "  → $fn/function.zip ($(du -sh "$fn_dir/function.zip" | cut -f1))"
done

echo "All Lambda packages built."
