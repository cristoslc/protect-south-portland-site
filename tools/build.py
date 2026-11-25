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
import html
import os
import re
import shutil
import sys
import urllib.parse

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

# The site-wide alert strip (staging-feedback issue #2, 2026-11-24): one
# element in the shared shell, above the masthead on every shell-built page,
# because the Dec. 1 meeting ask was filed for the top of the site, not for
# one page. The whole strip is one link to Act now. The two sentences are
# split on purpose — the suite's past-event-invitation rule refuses any single
# sentence carrying both a date and an invitation verb, and the ask's facts
# (Dec. 1, 6:30 p.m., City Hall Council Chambers, 25 Cottage Road) match the
# featured block's wording word for word. Persistent, not dismissible: a
# dismiss needs a stored preference, which the site's nothing-stored rule
# makes non-trivial. The map subtree is outside this shell and stays
# chrome-free by construction.
ALERT_STRIP = '<a class="alert-strip" href="act-now.html">Tuesday, Dec. 1 at 6:30 p.m. in City Hall Council Chambers, 25 Cottage Road. Wear green and come to the City Council meeting.</a>'

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
{alert}
{nav}
<main id="content">
{body}
</main>
{footer}
</body>
</html>
"""


# Ledger row 96, second operator instruction (2026-11-24, verbatim): "can we put
# the example message in the mailto body for the button?". The letter a reader
# reads in the blockquote and the draft the Email the Council button opens have
# to be one string, or an edit to the letter leaves the button behind. The page
# keeps the only copy, in the blockquote; this step runs at build time and
# writes that same text into the CTA's mailto body, so the button opens a
# populated draft with scripting off (the site's no-JS path rule) and no
# runtime script has to know the letter. Scoped by a marker rather than by page
# name: an anchor opts in with data-mailto-body="blockquote", every page that
# carries one is filled, and a marker with no blockquote refuses the build
# instead of shipping an empty draft. Deliberately not a templating system: one
# attribute, one parameter, one letter, and no second copy to drift.
MAILTO_BODY_MARKER = 'data-mailto-body="blockquote"'
MARKED_ANCHOR_RE = re.compile(
    r"<a\b[^>]*" + re.escape(MAILTO_BODY_MARKER) + r"[^>]*>", re.I)
BLOCKQUOTE_RE = re.compile(r"<blockquote>(?P<inner>.*?)</blockquote>", re.S)
PARAGRAPH_RE = re.compile(r"<p>(?P<inner>.*?)</p>", re.S)
BR_RE = re.compile(r"<br\s*/?>", re.I)
TAG_RE = re.compile(r"<[^>]+>")


def blockquote_text(markup: str) -> str:
    """Plain text of a page's blockquote: the visible letter, nothing else.

    Conversion, fixed by the operator's instruction: each <p> is one
    paragraph, paragraphs join with a blank line, <br> is a single newline,
    tags are stripped before entities are unescaped (so a literal "&lt;p&gt;"
    stays text and never becomes a tag), and the result is trimmed.
    """
    found = BLOCKQUOTE_RE.search(markup)
    if not found:
        raise ValueError(
            f"a {MAILTO_BODY_MARKER} anchor needs a <blockquote> to fill from")
    paragraphs = []
    for para in PARAGRAPH_RE.finditer(found.group("inner")):
        text = BR_RE.sub("\n", para.group("inner"))
        text = TAG_RE.sub("", text)
        paragraphs.append(html.unescape(text).strip())
    return "\n\n".join(paragraphs)


NEWSLETTER_SIGNUP_MARKER_RE = re.compile(
    r'<div\s+data-newsletter-signup="(full|reduced)"\s*>\s*</div>')

# The newsletter signup, one source of truth (ledger row 115). The label, the
# email field, the button, the honest note, the status line, the hand-writing
# fallback and the noscript explanation are assembled here at build time and
# injected wherever a page declares the marker, so no page carries its own
# copy of the block. The `variant` parameter carries the emphasis: "full"
# renders the callout panel the newsletter page shipped (row 91), "reduced"
# renders the same structure with no panel of its own, so the component
# matches the text around it where the ask is not the page's whole point.
# The guarantees are row 91's, carried unchanged: a real <label>, the typed
# value checked and encoded before anything is built, the status line written
# with textContent, and the plain address in the prose outside <noscript>.
NEWSLETTER_SIGNUP_SCRIPT = '''<script>
/* Newsletter signup, one shared component (see tools/build.py): every
   .signup box on the page is wired by this one script. The button builds a
   mailto: from the typed address and hands it to the visitor's mail app. No
   backend, no third-party form service, nothing stored, no analytics.

   Two habits are deliberate. The typed value is trimmed and its shape is
   checked before anything is built, so an empty field never opens a blank
   message and a typo gets a sentence instead of a silent nothing. And the
   value travels encoded: encodeURIComponent for the subject and the body, so
   a quote, an ampersand or a line break cannot break the URL or smuggle a
   second recipient in. Nothing a visitor types is ever parsed as markup: the
   status line is written with textContent, so typed markup stays text. */
(function () {
  var ADDRESS = "protectsouthportland@gmail.com";
  var SUBJECT = "Subscribe to the newsletter";
  var boxes = document.querySelectorAll(".signup");
  for (var i = 0; i < boxes.length; i++) { wire(boxes[i]); }
  function wire(box) {
    var field = box.querySelector("input[type=email]");
    var button = box.querySelector("button");
    var status = box.querySelector(".signup__status");
    function say(message) {
      status.textContent = message;
    }
    function open() {
      var typed = field.value.trim();
      if (!typed) {
        say("Add your email address above first, or write to " + ADDRESS + ".");
        field.focus();
        return;
      }
      if (!field.checkValidity()) {
        say("That does not look like an email address. Check it, or write to " + ADDRESS + ".");
        field.focus();
        return;
      }
      var body = "Please add this address to the Protect South Portland newsletter:\\n\\n" + typed + "\\n";
      window.location.href = "mailto:" + ADDRESS +
        "?subject=" + encodeURIComponent(SUBJECT) +
        "&body=" + encodeURIComponent(body);
      say("Opening your email app. If nothing opens, write to " + ADDRESS + ".");
    }
    button.addEventListener("click", open);
    field.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        open();
      }
    });
  }
})();
</script>'''


def newsletter_signup_html(variant: str, uid: str, with_script: bool) -> str:
    """One rendered signup instance; the script rides only on the page's
    first instance and wires every .signup box on the page."""
    root = "callout signup" if variant == "full" else "signup signup--reduced"
    block = f'''<div class="{root}">
        <label for="signup-email{uid}">Your email address</label>
        <div class="signup__row">
          <input type="email" id="signup-email{uid}" name="email" autocomplete="email" inputmode="email" spellcheck="false">
          <button type="button" class="btn btn--cta" id="signup-open{uid}">Open my email app</button>
        </div>
        <p class="signup__note">The button opens your own email app with the message ready to send. This does not subscribe you and it stores nothing: your address reaches the campaign when you press send in that app.</p>
        <p class="signup__status" role="status" aria-live="polite"></p>
      </div>

      <p class="signup__fallback">Writing by hand? Email <a href="mailto:protectsouthportland@gmail.com?subject=Subscribe%20to%20the%20newsletter">protectsouthportland@gmail.com</a> with &ldquo;Subscribe&rdquo; in the subject line.</p>

      <noscript>
        <p>The button above needs JavaScript. The email address in the line above works without it.</p>
      </noscript>'''
    return block + ("\n\n      " + NEWSLETTER_SIGNUP_SCRIPT if with_script else "")


def apply_newsletter_signups(body: str, name: str) -> str:
    """Replace every declared marker with the rendered component, failing
    loud on an unknown variant. The script is emitted once per page, riding
    on the first instance."""
    matches = list(NEWSLETTER_SIGNUP_MARKER_RE.finditer(body))
    if not matches:
        return body
    out, last = [], 0
    for i, match in enumerate(matches):
        out.append(body[last:match.start()])
        out.append(newsletter_signup_html(
            match.group(1), "" if i == 0 else "-" + match.group(1),
            with_script=(i == 0)))
        last = match.end()
    out.append(body[last:])
    return "".join(out)


def apply_mailto_bodies(body: str) -> str:
    """Fill every marked CTA's mailto body from the page's own blockquote.

    The marker attribute is consumed here, so the shipped page carries the
    populated href and no build plumbing. Fails loud rather than shipping a
    half-built button: a marker on an anchor that is not a mailto, a href that
    already declares a body (a hand-maintained second copy, which is exactly
    what one source of truth forbids), and a marker that matches no anchor all
    raise.
    """
    if MAILTO_BODY_MARKER not in body:
        return body
    encoded = urllib.parse.quote(blockquote_text(body), safe="")

    def fill(match):
        tag = match.group(0)
        href_match = re.search(r'href="(?P<href>mailto:[^"]*)"', tag)
        if not href_match:
            raise ValueError(
                f"a {MAILTO_BODY_MARKER} marker sits on an anchor with no mailto: href")
        href = href_match.group("href")
        if "body=" in href:
            raise ValueError(
                "a marked CTA already declares its own body; remove the hand-written copy")
        joined = ("&amp;" if "?" in href else "?") + "body=" + encoded
        tag = tag.replace(href_match.group(0), f'href="{href}{joined}"', 1)
        return tag.replace(" " + MAILTO_BODY_MARKER, "", 1)

    body, filled = MARKED_ANCHOR_RE.subn(fill, body)
    if not filled:
        raise ValueError(f"a {MAILTO_BODY_MARKER} marker matched no anchor")
    return body


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
        try:
            body = apply_newsletter_signups(raw[m.end():].strip(), name)
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from exc
        try:
            body = apply_mailto_bodies(body)
        except ValueError as exc:
            # The mailto refusals below describe the condition; on a 20+ page
            # build the traceback also has to say which page hit it, so the
            # name leads the message, the way the meta-line refusal above does.
            raise ValueError(f"{name}: {exc}") from exc
        nav = NAV_BODY
        if f'<a href="{name}">' in nav:
            nav = nav.replace(f'<a href="{name}">', f'<a href="{name}" aria-current="page">', 1)
        html = SHELL.format(title=title, desc=desc, alert=ALERT_STRIP, nav=nav, body=body, footer=FOOTER_BODY)
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