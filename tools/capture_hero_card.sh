#!/bin/bash
# One-off capture helper for ledger row 131 (homepage hero card leg).
# Captures the homepage hero card region at 412 and 1440 into a target dir,
# with a hero-bounding-rect record per width. Usage:
#   tools/capture_hero_card.sh <docs-dir> <out-dir> <label>
# The label prefixes each file (e.g. before/after). Fails loud on any
# non-200, missing bytes, or blank crop.
set -euo pipefail

DOCS="$1"; OUT="$2"; LABEL="$3"
HOST_ID="host_yat733yf8z"
VIEWPORT_H=900
SETTLE_MS=700

mkdir -p "$OUT"

PORT="$(python3 - <<'PY'
import socket
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
PY
)"
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$DOCS" >/dev/null 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }

BASE="http://127.0.0.1:${PORT}/"
code=""
for _ in $(seq 1 50); do
  code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$BASE" || true)"
  [ "$code" = "200" ] && break
  sleep 0.2
done
[ "$code" = "200" ] || { echo "capture: $BASE never served 200; aborting" >&2; exit 1; }

S="$(bb browser-automation open --backend local --headless --machine "$HOST_ID" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")"
trap 'cleanup; bb browser-automation close "$S" >/dev/null 2>&1 || true' EXIT

for W in 412 1440; do
  FULL="$OUT/.${LABEL}-${W}-full.png"
  bb browser-automation run "$S" --script \
"const p = await browser.getPage('main');
await p.setViewport({width: ${W}, height: ${VIEWPORT_H}});
await p.goto('${BASE}index.html?vc=' + Date.now(), {waitUntil: 'load'});
if (typeof p.waitForNetworkIdle === 'function') {
  await Promise.race([
    p.waitForNetworkIdle({idleTime: 500, timeout: 8000}).catch(() => {}),
    new Promise(r => setTimeout(r, 8000))
  ]);
}
await new Promise(r => setTimeout(r, ${SETTLE_MS}));
const rect = await p.evaluate(() => {
  const r = document.querySelector('section.hero').getBoundingClientRect();
  return {x: r.x + window.scrollX, y: r.y + window.scrollY, w: r.width, h: r.height};
});
await p.screenshot({path: '${FULL}', fullPage: true});
return JSON.stringify(rect);" \
    --timeout-ms 60000 --json > "$OUT/.run-${W}.json"
  [ -s "$FULL" ] || { echo "capture: no bytes for ${W}; aborting" >&2; exit 1; }
done
bb browser-automation close "$S" >/dev/null 2>&1 || true

python3 - "$OUT" "$LABEL" <<'PY'
import json, sys, os
from PIL import Image
out, label = sys.argv[1], sys.argv[2]
rects = {}
for w in (412, 1440):
    run = json.load(open(os.path.join(out, f".run-{w}.json")))
    if run.get("exitCode"):
        raise SystemExit(f"capture: browser run failed for {w}: {run.get('text')}")
    full = os.path.join(out, f".{label}-{w}-full.png")
    rect = json.loads(run["text"])
    rects[str(w)] = rect
    im = Image.open(full)
    pad = 8
    box = (max(0, int(rect["x"]) - pad), max(0, int(rect["y"]) - pad),
           min(im.width, int(rect["x"] + rect["w"]) + pad), min(im.height, int(rect["y"] + rect["h"]) + pad))
    crop = im.crop(box)
    dest = os.path.join(out, f"{label}-hero-{w}.png")
    colors = crop.convert("RGB").getcolors(maxcolors=1 << 20)
    if colors is None or len(colors) < 64:
        raise SystemExit(f"capture: {dest} looks blank ({0 if colors is None else len(colors)} colors); aborting")
    crop.save(dest)
    os.remove(full)
manifest = {
    "leg": "ledger row 131, homepage hero card (2026-11-25)",
    "label": label,
    "base": "local http server over the leg's built docs/",
    "widths": [412, 1440],
    "hero_rects_css_px": rects,
    "files": [f"{label}-hero-412.png", f"{label}-hero-1440.png"],
}
json.dump(manifest, open(os.path.join(out, f".{label}-rects.json"), "w"), indent=2)
print("captured:", manifest["files"])
PY
