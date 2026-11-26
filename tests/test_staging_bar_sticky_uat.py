"""Browser UAT pins for ledger row 148: the staging preview bar is sticky
and the chrome stack reseats below it, fully visible mid-scroll.

Operator directive 2026-11-25, relayed verbatim in substance: "on staging,
the staging preview bar should be STICKY — it must not disappear when
scrolling." The operator's desktop screenshot showed the mint strip scrolled
half off the viewport top mid-scroll.

Red on main at a4493fc, measured before any fix: the bar renders in document
flow, so a 600px scroll puts the bar's rect top near -600 and the masthead
sticks at top 0 — the bar is gone and the seats never reference it.

The fix makes the bar sticky at top 0 (z 60, above the masthead's 50 and the
banner's 40, below the gated state's max-int layer) and seats the stack from
real rendered heights — masthead top = the bar's offsetHeight, banner top =
bar height + masthead height — measured on load and on resize (the row-146
refine pattern), because at 412 the bar wraps to two lines and its height
varies. The bar renders only on staging hosts (the shared matcher), so the
browser pins serve the build over staging.protectsouthportland.localhost —
Chromium maps *.localhost to loopback — and the real shipped script runs end
to end.

The row-132 pins (nav links hit-test above the event banner, dropdown clicks
land) run unchanged and keep their verdicts; the gated staging bar's max-int
layer and the gate curtain stay untouched above everything.
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import uat_snapshots as us

BUILD = os.path.join(ROOT, "tools", "build.py")
SCROLL_TO = 600  # deep enough that every chrome element must be stuck


@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs-build")
    subprocess.run([sys.executable, BUILD, str(out)], check=True,
                   capture_output=True)
    return out


@pytest.fixture(scope="module")
def staging_base(docs):
    """Serve the fresh build over staging.protectsouthportland.localhost so
    the real shipped matcher and seating script run end to end."""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(docs), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://staging.protectsouthportland.localhost:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def session():
    sess = us.bb_open()
    try:
        yield sess
    finally:
        us.bb_close(sess)


def _probe(session, script):
    data = us.run_script(session, script, timeout_ms=90000)
    try:
        return json.loads(data.get("text") or "{}")
    except ValueError as exc:
        raise AssertionError(f"probe unreadable: {data}") from exc


def _midscroll_probe_script(base, width):
    """Scroll, then measure the stuck stack: bar at viewport top, masthead
    seated at the bar's rendered height, banner seated below both, and every
    nav link still the top element at its own center (nothing occludes)."""
    return f"""const p = await browser.getPage('main');
await p.setViewport({{width: {width}, height: 900}});
await p.goto('{base}index.html', {{waitUntil: 'load'}});
await new Promise(r => setTimeout(r, 700));
await p.evaluate(() => window.scrollTo(0, {SCROLL_TO}));
await new Promise(r => setTimeout(r, 300));
return await p.evaluate(() => {{
  const bar = document.querySelector('.staging-bar');
  const masthead = document.querySelector('.masthead');
  const banner = document.getElementById('alert-strip');
  const rects = el => {{ const r = el.getBoundingClientRect();
    return {{top: r.top, bottom: r.bottom, height: r.height}}; }};
  const blocked = [];
  for (const a of document.querySelectorAll('.masthead a')) {{
    const r = a.getBoundingClientRect();
    if (r.height === 0 || r.width === 0) continue;
    if (r.top < 0 || r.bottom > window.innerHeight) continue;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!(hit === a || a.contains(hit) || (hit && a.contains(hit.parentElement)))) {{
      blocked.push({{text: a.textContent.trim().slice(0, 40),
                    hit: hit ? (hit.textContent || '').trim().slice(0, 40) : null}});
    }}
  }}
  return {{
    width: window.innerWidth,
    scrolled: window.scrollY,
    barText: bar ? bar.textContent.slice(0, 60) : null,
    barRect: bar ? rects(bar) : null,
    mastheadRect: masthead ? rects(masthead) : null,
    bannerRect: banner ? rects(banner) : null,
    navBlocked: blocked
  }};
}});"""


@pytest.mark.skipif(shutil.which("bb") is None,
                    reason="bb CLI not on PATH: the browser pins need the "
                           "bb browser-automation headless Chrome mechanism")
class TestStagingBarSticky:
    """The bar stays at the viewport top mid-scroll and the stack seats
    below it from measured heights; nothing partially occludes."""

    def test_bar_sticks_and_stack_seats_at_1440(self, docs, session, staging_base):
        result = _probe(session, _midscroll_probe_script(staging_base, 1440))
        self._assert_stack(result)

    def test_bar_sticks_and_stack_seats_at_412(self, docs, session, staging_base):
        """The two-line mobile wrap makes the bar's height variable: the
        seats must still track the real rendered height, never a constant."""
        result = _probe(session, _midscroll_probe_script(staging_base, 412))
        self._assert_stack(result)
        assert result["barRect"]["height"] > 36, (
            "at 412 the bar wraps and must be taller than the single-line "
            "band; a flat constant here would mean the seats are magic "
            "numbers")

    @staticmethod
    def _assert_stack(result):
        assert result["scrolled"] == SCROLL_TO, "the probe must measure mid-scroll"
        bar, masthead, banner = (result["barRect"], result["mastheadRect"],
                                 result["bannerRect"])
        assert bar and masthead and banner, "all three chrome elements must exist"
        assert abs(bar["top"]) < 0.5, (
            f"the sticky bar must sit at the viewport top mid-scroll, saw "
            f"top {bar['top']}")
        assert abs(masthead["top"] - bar["height"]) < 0.5, (
            f"the masthead must seat below the bar's rendered height "
            f"({bar['height']}px), saw top {masthead['top']}")
        banner_seat = bar["height"] + masthead["height"]
        assert abs(banner["top"] - banner_seat) < 0.5, (
            f"the banner must seat below bar + masthead ({banner_seat}px), "
            f"saw top {banner['top']}")
        assert (bar["bottom"] <= masthead["top"] + 0.5
                and masthead["bottom"] <= banner["top"] + 0.5), (
            "the stack must not partially occlude: each element's bottom "
            "stays above the next one's top")
        assert result["navBlocked"] == [], (
            "nav links hit-blocked mid-scroll by the sticky stack: "
            f"{result['navBlocked']}")
        assert result["barText"].startswith(
            "Staging preview. Live site: protectsouthportland.org."), (
            "the sticky state must keep the row-133 format")
