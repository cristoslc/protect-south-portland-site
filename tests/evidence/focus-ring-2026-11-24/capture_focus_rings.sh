#!/bin/bash
# Focus-ring evidence capture (ledger row 95): focused-state frames at 412,
# 768 and 1440 for the two surfaces the .btn family renders on.
#
# Focus is reached with real Tab presses (capture_script.js), so the ring in
# the picture is the ring a keyboard reader gets, not a forced :focus style.
# Every frame is a viewport shot at the element's real rect, and
# measure_focus_rings.py then samples the ring stroke and the surface behind
# it from the pixels and writes manifest.json.
#
# Usage: BB_SESSION=<id> BB_HOST=<host-id> tests/evidence/focus-ring-2026-11-24/capture_focus_rings.sh
set -euo pipefail

EVID="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$EVID/../../.." && pwd)"
DOCS="$ROOT/docs"
BASE="${PSP_CAPTURE_BASE:-http://127.0.0.1:8899/}"
: "${BB_SESSION:?set BB_SESSION to a bb browser-automation session id}"
: "${BB_HOST:?set BB_HOST to the host id that holds this script}"

if ! curl -sf -o /dev/null "$BASE"; then
  echo "capture: no server answering at $BASE; start one over $DOCS first" >&2
  exit 1
fi

for W in 412 768 1440; do
  SCRIPT="$(mktemp)"
  sed -e "s|WIDTH_PLACEHOLDER|$W|g" -e "s|BASE_PLACEHOLDER|$BASE|g" \
    -e "s|OUT_PLACEHOLDER|$EVID|g" \
    "$EVID/capture_script.js" > "$SCRIPT"
  echo "capture: ${W}px"
  bb browser-automation run "$BB_SESSION" \
    --script-file "$SCRIPT" \
    --script-host "$BB_HOST" \
    --timeout-ms 120000 --json > "$EVID/${W}-run.json"
  rm -f "$SCRIPT"
done

echo "capture: frames written to $EVID"
