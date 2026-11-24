#!/usr/bin/env python3
"""Assemble the static Protect South Portland website.

site/pages/*.html hold each page's <main> content. The first line of each file
must be an HTML comment carrying the page metadata:

  <!-- meta: title="..." | desc="..." -->

build.py wraps each body in the shared shell — masthead, navigation, footer —
writes the result to docs/, copies site/styles.css and site/assets/, and is
deliberately boring: stdlib only, no dependencies. CI runs the tests and the
build; publishing is the mirror pipeline (tools/publish.py, see AGENTS.md
"Publishing to the public mirror").
"""
import os
import re
import shutil
import sys

import psp_public

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
PAGES = os.path.join(SITE, "pages")

# Pages that were merged away: each writes a tiny meta-refresh stub pointing at
# the live location so inbound links and bookmarks keep working.
REDIRECTS = {
    "oil-tank-emissions.html": "tank-farms.html",
    "vocs.html": "tank-farms.html#health-effects-of-vocs",
    # 2026-11-21 strip-back (operator approval): these agent-built pages left
    # the site; their URLs redirect so no inbound link or bookmark breaks.
    "tank-farms-history.html": "tank-farms.html#how-we-got-here",
    "library.html": "tank-farms.html#reference-documents",
    "press.html": "act-now.html",
    # 2026-11-24 (operator copy-doc revision): the doc's action section is now
    # "Act Now" and delegates its two children, Donate and Report an Odor, to
    # pages of their own, so the doc no longer describes a Get involved page.
    # Its action content lives on act-now.html and its odor section on
    # report-an-odor.html; the old URL redirects to the action page.
    "get-involved.html": "act-now.html",
}

META_RE = re.compile(r'<!--\s*meta:\s*title="(?P<title>[^"]*)"\s*\|\s*desc="(?P<desc>[^"]*)"\s*-->\s*\n?')

NAV_BODY = """
<a class="skip-link" href="#content">Skip to content</a>
<header class="masthead">
  <div class="masthead__inner">
    <a class="logo-link" href="index.html">
      <img src="assets/psp-logo.png" alt="Protect South Portland">
    </a>
    <input type="checkbox" id="nav-toggle" class="nav-toggle">
    <label class="nav-toggle-label" for="nav-toggle" aria-label="Toggle navigation">MENU</label>
    <nav class="main-nav" aria-label="Main">
      <!-- Header items, in order: Home, Our work, About, Share your story,
           Contact, then the Act now pill. Home returned here after the
           2026-11-23 header pass dropped it on the reasoning that the seal
           already links home; Newsletter left the header for the signup on
           its own page, which the footer still links. -->
      <ul>
        <li><a href="index.html">Home</a></li>
        <li class="has-sub">
          <a href="our-campaigns.html" aria-haspopup="true" aria-expanded="false">Our work</a>
          <ul class="submenu">
            <li><a href="tank-farms.html">South Portland Tank Farms</a></li>
            <li><a href="coastal-flooding.html">Coastal Flooding</a></li>
            <li class="has-sub has-flyout">
              <a href="past-work.html" aria-haspopup="true" aria-expanded="false">Past work</a>
              <ul class="submenu flyout">
                <li><a href="past-work.html">All past work</a></li>
                <li><a href="yard-south-proposal.html">Yard South Proposal</a></li>
                <li><a href="clear-skies.html">Clear Skies</a></li>
                <li><a href="fertilizer-ban.html">Fertilizer Ban</a></li>
                <li><a href="pesticides.html">Pesticides</a></li>
              </ul>
            </li>
          </ul>
        </li>
        <li><a href="about.html">About</a></li>
        <li><a href="share-your-story.html">Share your story</a></li>
        <li><a href="contact.html">Contact</a></li>
        <li class="nav-cta"><a href="act-now.html">Act now</a></li>
      </ul>
    </nav>
  </div>
</header>
"""

# Ruling A (2026-11-05): the dated Oct. 27 workshop strip is retired. The
# shared footer now carries the ruling's fallback call to action, linked to the
# action page that branches into both odor paths and the petition. Since the
# 2026-11-24 page-set revision that page is act-now.html: it carries the
# petition and offers the Report an odor child page.
FOOTER_BODY = """
<div class="action-strip" role="note">
  <p><a href="act-now.html">Report every odor. Sign the petition.</a></p>
</div>
<footer class="footer">
  <div class="wrap footer__grid">
    <div>
      <img src="assets/psp-logo.png" alt="Protect South Portland logo">
    </div>
    <div class="footer__links">
      <ul>
        <li><a href="index.html">Home</a></li>
        <li><a href="about.html">About</a></li>
        <li><a href="our-campaigns.html">Our work</a></li>
        <li><a href="tank-farms.html">Tank farms</a></li>
        <li><a href="toolkit.html">Tank farms toolkit</a></li>
        <li><a href="fertilizer-ban.html">Fertilizer ban</a></li>
        <li><a href="coastal-flooding.html">Coastal flooding</a></li>
        <li><a href="past-work.html">Past work</a></li>
        <li><a href="yard-south-proposal.html">Yard South proposal</a></li>
        <li><a href="clear-skies.html">Clear Skies</a></li>
        <li><a href="pesticides.html">Pesticides</a></li>
        <li><a href="newsletter.html">Newsletter</a></li>
        <li><a href="act-now.html">Act now</a></li>
        <li><a href="report-an-odor.html">Report an odor</a></li>
        <li><a href="donate.html">Donate</a></li>
        <li><a href="contact.html">Contact</a></li>
      </ul>
    </div>
    <div class="footer__donate">
      <p>Help defend our <strong>COMMUNITY</strong>. Please donate to Protect South Portland.</p>
      <a class="btn btn--cta" href="donate.html">Donate</a>
    </div>
  </div>
  <div class="wrap footer__base">
    <div class="social">
      <a href="https://x.com/ProtectSoPo" rel="noopener">X</a>
      <a href="https://www.facebook.com/protectsouthportland/" rel="noopener">Facebook</a>
    </div>
    <p class="credit">A special thank you goes out to Dan Woods and Karen Silverman for their photography donations.</p>
  </div>
</footer>
<script>
/* Dropdown a11y (2026-10-15), progressive enhancement only. The menus already
   open and close in CSS (:hover and :focus-within; blur closes) with no
   JavaScript at all; this script adds Escape-to-close (drop focus, the
   :focus-within release closes the panel) and keeps aria-expanded truthful
   on the two parent links, including the mobile static list where the
   children are always visible at <=1120px. */
(function () {
  var nav = document.querySelector(".main-nav");
  if (!nav) return;
  var parents = nav.querySelectorAll(".has-sub > a");
  var MOBILE = window.matchMedia("(max-width: 1120px)");
  function sync() {
    parents.forEach(function (a) {
      var li = a.parentElement;
      var open = MOBILE.matches || li.matches(":hover") || li.matches(":focus-within");
      a.setAttribute("aria-expanded", String(open));
    });
  }
  parents.forEach(function (a) {
    ["focusin", "focusout", "mouseenter", "mouseleave"].forEach(function (type) {
      a.addEventListener(type, function () { setTimeout(sync, 0); });
    });
  });
  nav.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !e.target.closest(".has-sub")) return;
    e.preventDefault();
    if (document.activeElement) document.activeElement.blur();
    sync();
  });
  if (typeof MOBILE.addEventListener === "function") MOBILE.addEventListener("change", sync);
  sync();
})();
</script>
"""

SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" type="image/png" href="assets/psp-favicon.png">
<link rel="stylesheet" href="styles.css">
</head>
<body>
{nav}
<main id="content">
{body}
</main>
{footer}
</body>
</html>
"""


def build(out_dir: str) -> list:
    """Assemble every page into out_dir; return the list of pages written."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name in sorted(os.listdir(PAGES)):
        if not name.endswith(".html"):
            continue
        raw = open(os.path.join(PAGES, name), encoding="utf-8").read()
        m = META_RE.match(raw)
        if not m:
            raise ValueError(f"{name}: first line must be the <!-- meta: ... --> comment")
        title = m.group("title")
        desc = m.group("desc")
        body = raw[m.end():].strip()
        nav = NAV_BODY
        if f'<a href="{name}">' in nav:
            nav = nav.replace(f'<a href="{name}">', f'<a href="{name}" aria-current="page">', 1)
        html = SHELL.format(title=title, desc=desc, nav=nav, body=body, footer=FOOTER_BODY)
        dest = os.path.join(out_dir, name)
        open(dest, "w", encoding="utf-8").write(html)
        written.append(name)
    for old, new in sorted(REDIRECTS.items()):
        open(os.path.join(out_dir, old), "w", encoding="utf-8").write(
            '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta http-equiv="refresh" content="0; url={new}">\n'
            f'<title>Redirecting to {new}</title>\n'
            f'<link rel="canonical" href="{new}">\n</head>\n'
            f'<body><p>This page moved to <a href="{new}">{new}</a>.</p></body>\n</html>\n')
        written.append(old)
    shutil.copy(os.path.join(SITE, "styles.css"), os.path.join(out_dir, "styles.css"))
    shutil.copytree(os.path.join(SITE, "assets"), os.path.join(out_dir, "assets"), dirs_exist_ok=True)
    copied_map = psp_public.refresh_map_dir(out_dir)
    if copied_map:
        print("map:", ", ".join(copied_map))
    print("pages:", ", ".join(written))
    return written


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs")
    build(out)
    print("built into", out)