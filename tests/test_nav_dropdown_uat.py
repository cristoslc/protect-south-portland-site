"""UAT pins for ledger row 132: the alert banner must never sit in front of
the navigation or its menus.

Operator directive with screenshot (2026-11-25, verbatim): the sticky orange
alert banner "shouldn't be more forward than menus, makes menus unclickable".
The screenshot showed the "Our work" dropdown open at desktop width with its
items hidden behind the banner.

Root cause (measured on main at a8453bc before any fix): the banner and the
masthead are sticky siblings both pinned to the viewport top, and the banner's
`z-index: 60` outranked the masthead's `z-index: 50`. The dropdown panel's own
`z-index: 60` never competes with the banner: the masthead is a stacking
context, so the panel's layer only counts inside it, and the whole masthead —
dropdown included — sat below the banner in the root context. The banner
painted over the dropdown's first item ("South Portland Tank Farms", fully
blocked) and clipped the second ("Coastal Flooding"); when the page was
scrolled it covered the stuck masthead's nav links outright. At 412 the open
MENU panel's links were blocked the same way.

The fix moves only the banner's z-index, 60 -> 40, below the masthead's 50 and
above the page content layers (the hero photo at 0, the hero card at 1), so:
nav dropdowns paint and hit-test above the banner and are clickable while
open; the banner still sits above ordinary page content whenever it is the
topmost chrome; the staging preview bar (max-int z-index on the gated host)
and the gate curtain (max-int minus one) are untouched above everything.

The browser pins run against a fresh build through the same headless-Chrome
mechanism tools/uat_snapshots.py uses (bb browser-automation), and are skipped
— with the reason named — only where the bb CLI itself is absent. The static
pin pins the stylesheet layering contract everywhere else.
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

# The operator's red state, measured on main at a8453bc before the fix:
MASTHEAD_Z_BEFORE = 50
ALERT_STRIP_Z_BEFORE = 60
# The fix: the banner sinks below the masthead, above page content.
MASTHEAD_Z_AFTER = 50
ALERT_STRIP_Z_AFTER = 40
PAGE_CONTENT_Z = 1  # .hero__inner, the highest ordinary content layer


def _z_index(selector, text):
    """The z-index declared in the selector's own rule block, or None."""
    block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text)
    if not block:
        return None
    found = re.search(r"(?<![\w-])z-index:\s*(-?\d+)\s*;", block.group(1))
    return int(found.group(1)) if found else None


def test_alert_strip_layers_below_the_masthead_and_above_page_content():
    """The row-132 layering contract in the shipped stylesheet.

    Red on main: the banner's 60 outranked the masthead's 50, so the banner
    painted over the nav's dropdown menu and hit-blocked it. The fix drops
    the banner to 40: the masthead (and every menu that lives inside its
    stacking context) wins, and the banner still clears the highest ordinary
    page content layer (the hero card region at 1). Values pinned exactly so
    a future edit cannot quietly reorder the three layers again.
    """
    text = open(STYLES, encoding="utf-8").read()
    masthead = _z_index(".masthead", text)
    strip = _z_index(".alert-strip", text)
    content = _z_index(".hero__inner", text)
    assert masthead == MASTHEAD_Z_AFTER
    assert strip == ALERT_STRIP_Z_AFTER
    assert content == PAGE_CONTENT_Z
    assert masthead > strip, (
        "the alert banner must layer below the masthead: the operator ruled "
        "the banner 'shouldn't be more forward than menus' (ledger row 132)")
    assert strip > content, (
        "the stuck banner must still layer above ordinary page content "
        "(ledger row 132 keeps that property alive)")


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


@pytest.mark.skipif(shutil.which("bb") is None,
                    reason="bb CLI not on PATH: the browser pins need the "
                           "bb browser-automation headless Chrome mechanism")
class TestNavAboveAlertBannerBrowser:
    """Browser-level hit-testing pins: every link of an open nav must be the
    element the browser would really click at its center — never the banner."""

    def _probe(self, session, script):
        data = us.run_script(session, script, timeout_ms=90000)
        try:
            return json.loads(data.get("text") or "{}")
        except ValueError as exc:
            raise AssertionError(f"probe unreadable: {data}") from exc

    def _open_nav_probe_script(self, base, width):
        """Open the nav (desktop: focus 'Our work' then 'Past work' so both
        dropdown levels render; 412: check the MENU toggle) and hit-test the
        center of every visible nav link."""
        return f"""const p = await browser.getPage('main');
await p.setViewport({{width: {width}, height: 900}});
await p.goto('{base}index.html', {{waitUntil: 'load'}});
await new Promise(r => setTimeout(r, 700));
return await p.evaluate(() => {{
  if (window.innerWidth <= 1120) {{
    document.getElementById('nav-toggle').checked = true;
  }} else {{
    const trigger = document.querySelector('.main-nav .has-sub > a');
    trigger.focus();
    const flyoutTrigger = [...document.querySelectorAll('.main-nav .has-sub.has-flyout > a')]
      .find(a => a.getBoundingClientRect().height > 0);
    if (flyoutTrigger) flyoutTrigger.focus();
  }}
  const strip = document.getElementById('alert-strip');
  const blocked = [];
  for (const a of document.querySelectorAll('.main-nav a')) {{
    const r = a.getBoundingClientRect();
    if (r.height === 0 || r.width === 0) continue;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!(hit === a || a.contains(hit) || (hit && a.contains(hit.parentElement)))) {{
      blocked.push({{text: a.textContent.trim().slice(0, 40),
                    hit: hit ? (hit.textContent || '').trim().slice(0, 40) : null}});
    }}
  }}
  return {{width: window.innerWidth, stripVisible: !!(strip && !strip.hidden),
          blocked, blockedCount: blocked.length}};
}});"""

    def test_every_open_nav_link_hit_tests_above_the_banner_at_1440(self, docs, session):
        """Red on main: 'South Portland Tank Farms' hit-tested to the banner's
        text and 'Coastal Flooding' was clipped by it — the operator's
        screenshot. After the fix every link of the open dropdowns (both
        levels) is the top element at its own center."""
        result = self._probe(session, self._open_nav_probe_script(
            docs.as_uri().rstrip('/') + '/', 1440))
        assert result["stripVisible"], "the alert banner must be present for this pin to mean anything"
        assert result["blocked"] == [], (
            "nav links hit-blocked behind the alert banner at 1440: "
            f"{result['blocked']}")

    def test_every_open_nav_link_hit_tests_above_the_banner_at_412(self, docs, session):
        """The same conflict on the phone: with the MENU panel open the
        wrapped banner (y 70-195 on main) sat over the panel's links. Red on
        main for 'Home' and 'Our work'."""
        result = self._probe(session, self._open_nav_probe_script(
            docs.as_uri().rstrip('/') + '/', 412))
        assert result["stripVisible"]
        assert result["blocked"] == [], (
            "MENU panel links hit-blocked behind the alert banner at 412: "
            f"{result['blocked']}")

    def test_dropdown_item_click_reaches_its_page_at_1440(self, docs, session):
        """Red on main: a click at the 'South Portland Tank Farms' item's
        center — the dropdown's first item, the one the banner fully covers —
        landed on the banner's text, so no navigation happened. After the fix
        the same click lands on the item and reaches tank-farms.html. The
        click goes through the element the browser hit-tests at that point —
        the very element a real visitor's click would land on."""
        base = docs.as_uri().rstrip("/") + "/"
        script = f"""const p = await browser.getPage('main');
await p.setViewport({{width: 1440, height: 900}});
await p.goto('{base}index.html', {{waitUntil: 'load'}});
await new Promise(r => setTimeout(r, 700));
await p.evaluate(() => {{
  document.querySelector('.main-nav .has-sub > a').focus();
  const item = [...document.querySelectorAll('.main-nav .has-sub > .submenu a')]
    .find(a => a.textContent.trim() === 'South Portland Tank Farms' && a.getBoundingClientRect().height > 0);
  const r = item.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  window.__clicked = (hit.textContent || '').trim().slice(0, 40);
  hit.click();
}});
await new Promise(r => setTimeout(r, 800));
return await p.evaluate(() => ({{landed: location.pathname.split('/').pop(),
                                clicked: window.__clicked || null}}));"""
        data = us.run_script(session, script, timeout_ms=90000)
        try:
            result = json.loads(data.get("text") or "{}")
        except ValueError as exc:
            raise AssertionError(f"click probe unreadable: {data}") from exc
        assert result.get("landed") == "tank-farms.html", (
            f"clicking the 'South Portland Tank Farms' dropdown item did not "
            f"reach its page: the click landed on {result.get('clicked')!r} "
            f"and the browser stayed on {result.get('landed')!r}")
