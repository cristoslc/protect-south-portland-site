"""UAT pins for ledger row 146: the sticky event banner stays FULLY visible
when scrolling — nothing may scroll partially under anything.

Operator directive (2026-11-25, verbatim): "Sticky sheet Banner should stay
fully visible when scrolling", with an act-now mobile screenshot mid-scroll
showing the red "Next event" banner PARTIALLY CLIPPED: its first lines had
scrolled under the masthead, only the tail line ("Road. Show up by wearing
green! Details") remained visible below the masthead.

Root cause (measured on main at 1ac7064 before any fix, headless Chrome): the
shell order is masthead then banner, and both are sticky siblings pinned to
`top: 0`. When both are stuck they occupy the same viewport band and the
masthead (z-index 50) paints over the banner (z-index 40). Measured:
- at 412: masthead stuck 0..69.7 (height 69.7), banner stuck 0..125.3 —
  occluded; only the tail band 69.7..125.3 shows below the masthead, exactly
  the operator's screenshot;
- at 1440: masthead stuck 0..70.7 (height 70.7), banner stuck 0..43.3 —
  occluded in full, the desktop banner disappears entirely mid-scroll.

The fix (ledger row 146): the banner's stuck position sits BELOW the
masthead's stuck height. The shipped stylesheet default is the measured
70px; the shell's existing banner script refines it live from the masthead's
own offsetHeight on load and on window resize (never on nav-panel open, so
the row-132 menus-above-banner composition stays the natural behavior).

Guards this file keeps alive: the dismiss-and-return-next-day localStorage
day-key; both breakpoints; row-132 layering (menus above banner, z 40)
composing with the new offset; site-wide coverage (act-now and about).

The browser pins run against a fresh build through the same headless-Chrome
mechanism tools/uat_snapshots.py uses (bb browser-automation), and are
skipped — with the reason named — only where the bb CLI itself is absent.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import uat_snapshots as us

BUILD = os.path.join(ROOT, "tools", "build.py")
STYLES = os.path.join(ROOT, "site", "styles.css")
BUILD_PY = os.path.join(ROOT, "tools", "build.py")


def test_alert_strip_no_longer_sticks_at_the_viewport_top():
    """The row-146 sticky-top contract in the shipped stylesheet.

    Red on main: the .alert-strip rule declared `top: 0`, so the stuck
    banner shared the masthead's viewport band and was painted over. The fix
    ships the measured 70px default (the masthead's stuck height at both
    breakpoints, 69.7 at 412 and 70.7 at 1440), refined live by the shell
    script to the masthead's own offsetHeight so real copies cannot drift
    from the constant. Pinned exactly so a regression cannot quietly put the
    banner back under the masthead.
    """
    text = open(STYLES, encoding="utf-8").read()
    block = re.search(r"\.alert-strip\s*\{([^}]*)\}", text)
    assert block, "the .alert-strip rule block is missing from styles.css"
    body = block.group(1)
    top = re.search(r"(?<![\w-])top:\s*([^;]+);", body)
    assert top, "the .alert-strip rule must declare a sticky top"
    assert top.group(1).strip() == "70px", (
        "the banner's stuck top must sit below the masthead's stuck height "
        "(row 146: measured 69.7px at 412 and 70.7px at 1440); `top: 0` put "
        f"the banner under the masthead mid-scroll, found: {top.group(1)!r}")
    shell = open(BUILD_PY, encoding="utf-8").read()
    assert "offsetHeight" in shell and "style.top" in shell, (
        "the shell script must refine the banner's stuck top from the "
        "masthead's own offsetHeight on load and on resize (row 146)")
    assert "psp-event-banner-day" in shell, (
        "the dismiss-and-return-next-day localStorage day-key must survive "
        "the sticky-top fix")


@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs-build")
    subprocess.run([sys.executable, BUILD, str(out)], check=True,
                   capture_output=True)
    return out


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


_SCROLL_PROBE = """const p = await browser.getPage('main');
await p.setViewport({width: WIDTH, height: 900});await p.goto(PAGE, {waitUntil: 'load'});
await new Promise(r => setTimeout(r, 700));
const out = {states: {}};
for (const [name, y] of [['top', 0], ['mid', 600], ['deep', 1200]]) {
  await p.evaluate(v => window.scrollTo({top: v, behavior: 'instant'}), y);
  await new Promise(r => setTimeout(r, 200));
  out.states[name] = await p.evaluate(() => {
    const m = document.querySelector('.masthead').getBoundingClientRect();
    const el = document.getElementById('alert-strip');
    const s = el.getBoundingClientRect();
    const overlap = s.top < m.bottom - 0.5 && s.bottom > m.top;
    return {mastheadBottom: +m.bottom.toFixed(2),
            stripTop: +s.top.toFixed(2), stripBottom: +s.bottom.toFixed(2),
            stripH: +s.height.toFixed(2), stripOffsetH: el.offsetHeight,
            stripLeftVisible: s.top >= 0,
            stripAboveFold: s.bottom <= innerHeight + 0.5,
            overlapWithMasthead: !!overlap,
            scrollY: Math.round(scrollY)};
  });
}
return JSON.stringify(out);"""

_DISMISS_PROBE = """const p = await browser.getPage('main');
await p.setViewport({width: 1440, height: 900});
await p.goto(PAGE, {waitUntil: 'load'});
await new Promise(r => setTimeout(r, 700));
await p.evaluate(() => window.scrollTo({top: 600, behavior: 'instant'}));
await new Promise(r => setTimeout(r, 200));
return await p.evaluate(() => {
  const s = document.getElementById('alert-strip');
  const close = s.querySelector('.alert-strip__close');
  if (!close || close.hidden) return {error: 'close button missing or hidden'};
  close.click();
  const stored = (() => { try { return localStorage.getItem('psp-event-banner-day'); } catch (e) { return null; } })();
  const r = s.getBoundingClientRect();
  return {hiddenAfterClick: s.hidden, dayKeyWritten: !!stored,
          renderedAfterHide: r.width > 0 || r.height > 0};
});"""


@pytest.mark.skipif(shutil.which("bb") is None,
                    reason="bb CLI not on PATH: the browser pins need the "
                           "bb browser-automation headless Chrome mechanism")
class TestBannerFullyVisibleWhileScrolling:
    """Browser-level mid-scroll pins: at every scrolled offset the stuck
    banner must sit fully below the masthead — no overlap, top at or below
    the masthead's bottom edge, whole banner inside the viewport."""

    @pytest.mark.parametrize("page", ["act-now.html", "about.html"])
    @pytest.mark.parametrize("width", [412, 1440])
    def test_banner_fully_below_masthead_and_in_viewport_while_scrolled(
            self, docs, session, page, width):
        """Red on main: at mid-scroll the masthead painted over the banner's
        first lines (412) — or over the whole banner (1440). After the fix
        the banner's stuck top always sits below the masthead's stuck bottom,
        and the banner is never clipped by the viewport."""
        base = docs.as_uri().rstrip("/") + "/"
        script = (_SCROLL_PROBE
                  .replace("WIDTH", str(width))
                  .replace("PAGE", repr(base + page)))
        result = _probe(session, script)
        for name, st in result["states"].items():
            assert st["stripLeftVisible"], (
                f"{page}@{width} scroll {name}: the banner itself is clipped "
                "at the viewport top")
            assert not st["overlapWithMasthead"], (
                f"{page}@{width} scroll {name}: the banner overlaps the "
                f"masthead band (strip {st['stripTop']}..{st['stripBottom']} "
                f"vs masthead bottom {st['mastheadBottom']})")
            assert st["stripTop"] >= st["mastheadBottom"] - 0.5, (
                f"{page}@{width} scroll {name}: the banner's stuck top sits "
                "above the masthead's stuck bottom — it will paint under "
                f"the masthead (strip {st['stripTop']}, masthead "
                f"{st['mastheadBottom']})")
            assert st["stripAboveFold"], (
                f"{page}@{width} scroll {name}: the banner's bottom runs "
                f"past the viewport (strip {st['stripBottom']})")
            assert abs(st["stripH"] - st["stripOffsetH"]) <= 0.5, (
                f"{page}@{width} scroll {name}: the banner is clipped "
                f"(rect {st['stripH']}px vs offsetHeight "
                f"{st['stripOffsetH']}px)")

    def test_banner_sticks_below_masthead_at_the_measured_band(self, docs, session):
        """The measured contract, named: the stuck banner top must sit below
        the stuck masthead bottom within a pixel at both breakpoints, so the
        fix holds on the real masthead, not just against overlap."""
        base = docs.as_uri().rstrip("/") + "/"
        for width in (412, 1440):
            script = (_SCROLL_PROBE
                      .replace("WIDTH", str(width))
                      .replace("PAGE", repr(base + "act-now.html")))
            st = _probe(session, script)["states"]["mid"]
            gap = st["stripTop"] - st["mastheadBottom"]
            assert -0.5 <= gap <= 1.0, (
                f"at {width} the stuck banner sits {gap:+.2f}px from the "
                "masthead's stuck bottom; row 146 pins the banner directly "
                "below the masthead, not in a gap")

    def test_dismiss_still_works_while_stuck(self, docs, session):
        """The dismiss-and-return-next-day guard, exercised on the stuck
        banner: the close button hides it at a scrolled offset, and the
        dismissal writes the day key so tomorrow brings it back on reload."""
        base = docs.as_uri().rstrip("/") + "/"
        out = _probe(session, _DISMISS_PROBE.replace(
            "PAGE", repr(base + "act-now.html")))
        assert out.get("hiddenAfterClick") is True, (
            f"the stuck banner must dismiss via its close button: {out}")
        assert out.get("dayKeyWritten"), (
            "the dismissal must write the localStorage day key")
        assert out.get("renderedAfterHide") is False, (
            "the dismissed banner must stop rendering (the [hidden] guard)")
