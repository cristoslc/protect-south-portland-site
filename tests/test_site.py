"""Tests for the generated Protect South Portland site.

Builds site/pages into a temp dir via tools/build.py and pins the hard rules:

- Ledger row 5: the verbatim docx banner sits at the very top of the homepage.
- Ledger row 7 + row 3: the map section is titled "South Portland Tank Farms",
  the interactive map sits top-center, and the website-addition text follows.
- Ledger row 6: the old "Make a difference / act now and donate" hero is gone;
  the tank-farms call to action replaces it and ACT NOW points to act-now.html
  (the email-the-Council landing page).
- Ledger row 1: no private links — research report, fact-check log, data files,
  GitHub repo — anywhere in the generated HTML.
- Ledger row 9 (constraint): no mention of the Oct 15 community assembly,
  ever — REVERSED 2026-10-15 by ledger row 33 (operator/Mindy sanctioned the
  meeting copy; the meeting is tonight): the ban is retired and the
  Action-Oriented meeting bullet ships with the flyer link.
- Site hygiene: internal links resolve, external links use an allowlist, every
  page has a title/description, and every image resolves locally with alt text.
- Photography and graphics are copied from the live Wix site into
  site/assets/photos (operator directive 2026-10-13) and served locally; hotlinking
  static.wixstatic.com is banned by test_no_wix_assets_copied.
"""

import datetime
import html
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from html.parser import HTMLParser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "tools", "build.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build
import gate_report
import psp_public
import publish
import uat_payload
import uat_snapshots

# Ledger row 5 banner, single-sourced from tools/psp_public.py so the
# tests and publish.py's domain check pin the same string.
BANNER_TEXT = psp_public.BANNER_TEXT
EMBED_URL = "map/embed.html"

# Ledger row 1: private map-site surface must never leak onto the public site.
# Ledger row 9's Oct-15 event-marker ban is reversed by row 33 (2026-10-15):
# EVENT_MARKERS must be retired-empty in psp_public and only the sanctioned
# meeting copy ships. The marker sets live in tools/psp_public.py — shared
# with build.py and tools/publish.py so every entry point enforces the same
# rules.
PRIVATE_MARKERS = psp_public.PRIVATE_MARKERS
FORBIDDEN_EVENT_MARKERS = psp_public.EVENT_MARKERS
FORBIDDEN_DRAFT_MARKERS = psp_public.DRAFT_MARKERS

EXTERNAL_ALLOWLIST = (
    "southportland.gov",
    "southportland.org",
    "protectsouthportland.com",
    # ledger row 129 (operator directive, 2026-11-25): the Act now Add to
    # Calendar dropdown links Google's standard no-auth template URL
    # (calendar.google.com/render?action=TEMPLATE) — a hand-built link to the
    # reader's own calendar, not an embedded widget or service script.
    "calendar.google.com",
    "docs.google.com",
    "drive.google.com",
    "diligentoneplatform.com",
    "smellmycity.org",
    "southportland2040.com",
    "oneclimatefuture.org",
    "gmri.maps.arcgis.com",
    "storymaps.arcgis.com",
    "pressherald.com",
    "insideclimatenews.org",
    "justice.gov",
    "cdc.gov",
    "maine.gov",
    "mainelegislature.org",
    "legiscan.com",
    "bostonglobe.com",
    "dropbox.com",
    "nytimes.com",
    "scientificamerican.com",
    "beyondpesticides.org",
    "plantcatalyst.com",
    "extension.umaine.edu",
    "paypal.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "themainemonitor.org",
    # 2026-11-24 (toolkit reference page): hosts the carried toolkit chapters
    # cite. Pulitzer Center reported on South Portland's role as the state's
    # petroleum hub; the Conservation Law Foundation posts the tank-farm
    # closures the FAQ answer points at.
    "pulitzercenter.org",
    "clf.org",
    "cascobayestuary.org",
    "digital.sierramagazine.org",
    "edition.pagesuite.com",
    "mainebeacon.com",
    "portlandphoenix.me",
    "centralmaine.com",
    "wmtw.com",
    "web.archive.org",
    "youtu.be",
    "youtube.com",
)


@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    out = tmp_path_factory.mktemp("site_out")
    subprocess.run([sys.executable, BUILD, str(out)], check=True, capture_output=True)
    return out


def read(docs, name):
    return open(os.path.join(docs, name), encoding="utf-8").read()


def reading_text(markup):
    """Tag-stripped, whitespace-normalized text of a built page.

    Copy pins (ledger rulings on wording) assert against this, not raw markup,
    so an emphasis-only edit (2026-11-24 bold pass) cannot break a copy rule.
    """
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def html_files(docs):
    return sorted(n for n in os.listdir(docs) if n.endswith(".html"))


def test_fragments_survive_the_build_structurally(docs):
    """A page fragment is copied into the chrome, never converted, so every
    class token, figure and iframe in the source must exist in the built page.

    This exists because the Pages CMS assessment (Nov 6) showed the converse: a
    rich-text round trip stripped 223 class attributes down to 16, flattened
    every card grid and dropped both iframes, and the whole suite still passed,
    because no pin looked at structure. Copy is reviewed; structure was not.
    """
    pages_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "site", "pages")
    for name in sorted(os.listdir(pages_dir)):
        if not name.endswith(".html"):
            continue
        source = open(os.path.join(pages_dir, name), encoding="utf-8").read()
        built_path = os.path.join(docs, name)
        if not os.path.exists(built_path):
            continue
        built = open(built_path, encoding="utf-8").read()
        for cls in set(re.findall(r'class="([^"]+)"', source)):
            assert built.count(f'class="{cls}"') >= source.count(f'class="{cls}"'), (
                f"{name}: the build lost class=\"{cls}\"")
        for tag in ("figure", "iframe", "table"):
            assert built.count(f"<{tag}") >= source.count(f"<{tag}"), (
                f"{name}: the build lost a <{tag}> element")


def test_kicker_never_repeats_the_h1(docs):
    """2026-11-24 confirmation review: our-campaigns.html rendered a kicker
    "Our work" directly above an h1 that also said "Our work", the only such
    duplication on the site, created when the kicker was retagged to match the
    nav. The h1 carries the page label; the kicker exists to add a different
    frame, so the two never say the same thing.

    Rule-shaped rather than a page pin, because the failure is a class: every
    other page pairs a label with a different line ("About" over the Satoro
    quote, "The campaign" over "South Portland Tank Farms"), and 404.html
    carries no kicker at all. A page may do either; it may not repeat itself.
    """
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        page = read(docs, name)
        kicker = re.search(r'<span class="kicker">(.*?)</span>', page, re.S)
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        if not kicker or not heading:
            continue
        def text_of(match):
            return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip().lower()
        assert text_of(kicker) != text_of(heading), (
            f"{name}: the kicker and the h1 both say {text_of(heading)!r}")


def test_expected_pages_built(docs):
    names = html_files(docs)
    for expected in (
        "index.html", "act-now.html", "report-an-odor.html", "about.html",
        "our-campaigns.html",
        "coastal-flooding.html", "yard-south-proposal.html", "oil-tank-emissions.html",
        "clear-skies.html", "fertilizer-ban.html", "pesticides.html", "vocs.html",
        "newsletter.html", "get-involved.html", "donate.html", "contact.html",
        "404.html", "past-work.html", "tank-farms.html", "share-your-story.html",
        # 2026-11-24 ruling (one reference page, durable chapters only)
        "toolkit.html",
    ):
        assert expected in names, expected
    assert "styles.css" in os.listdir(docs)
    assert os.path.exists(os.path.join(docs, "assets", "psp-logo.png"))


# merged campaign pages write tiny meta-refresh stubs instead of full shells;
# shell-level tests skip them.
REDIRECT_PAGES = {
    "oil-tank-emissions.html", "vocs.html",
    # 2026-11-21 strip-back: agent-built pages retired to redirects
    "tank-farms-history.html", "library.html", "press.html",
    # 2026-11-24 page-set revision: the doc's action section is Act Now and the
    # odor section is its Report an Odor child, so Get involved leaves the set
    "get-involved.html",
}


def test_merged_redirects(docs):
    stub = read(docs, "oil-tank-emissions.html")
    assert 'url=tank-farms.html' in stub and "content=\"0; url=" in stub
    stub2 = read(docs, "vocs.html")
    assert "tank-farms.html#health-effects-of-vocs" in stub2
    # stubs must not be full shells
    for name in REDIRECT_PAGES:
        page = read(docs, name)
        assert 'class="masthead"' not in page and len(page) < 800, name


def test_get_involved_retires_into_act_now(docs):
    """2026-11-24 page-set revision: the copy document renamed its action
    section Act Now and split two children out of it, Donate and Report an
    Odor. The document no longer describes a Get involved page, so the page
    leaves the set the same way the 2026-11-21 strip-back pages did: a
    meta-refresh stub at the old URL, its content living where the document
    now puts it.

    The stub shape is the existing redirect shape; the two halves of the old
    page have to be reachable afterwards, or the retirement strands a reader
    who came for the odor instructions or the legislator list.
    """
    stub = read(docs, "get-involved.html")
    assert 'content="0; url=act-now.html"' in stub, stub
    assert '<link rel="canonical" href="act-now.html">' in stub, stub
    assert 'class="masthead"' not in stub and len(stub) < 800, "stubs carry no chrome"
    # the source fragment is gone, not merely unpinned
    assert not os.path.exists(
        os.path.join(ROOT, "site", "pages", "get-involved.html"))
    # no live page links the retired URL
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        assert 'href="get-involved.html"' not in read(docs, name), (
            f"{name} links the retired get-involved.html")
    # the action half is on act-now.html, the odor half on report-an-odor.html
    act = read(docs, "act-now.html")
    assert "Write to Maine state legislators" in act
    assert "Writing a letter to the editor" in act
    assert "More ways to help" in act
    odor = read(docs, "report-an-odor.html")
    assert "<h1 id=\"report-an-odor\">Report an odor two ways</h1>" in odor
    # the campaign page's inbound odor link lands on the live page, not a stub
    assert 'href="report-an-odor.html"' in read(docs, "tank-farms.html")
    assert 'href="get-involved.html#' not in read(docs, "tank-farms.html")


def test_share_your_story_page(docs):
    """The voice-memo page (PSP Comms Team doc, 2026-11-20): an invitation to
    leave a recording ahead of the Dec. 1 workshop.

    Two things matter here beyond the copy. The consent sentence is a promise
    about what happens to a stranger's recording, so it must ship verbatim. And
    the phone number does not exist yet, so the page carries a visible
    placeholder instead of a dead tel: link, and the nav does not offer a page
    whose only action is missing.
    """
    page = read(docs, "share-your-story.html")
    # the invitation, and the date it serves
    assert "We want to hear your voice" in page
    assert "Dec. 1" in page
    # consent: permission to publish, stated plainly, plus the newsletter route
    assert ("you are giving Protect South Portland permission to share any part "
            "of your recording") in page
    assert "newsletter" in page
    # three-minute cap and the call-more-than-once answer
    assert "three minutes" in page
    assert "more than once" in page
    # prompts, and the optional image route
    assert "I remember" in page
    assert "optional image" in page.lower()
    assert "protectsouthportland@gmail.com" in page
    # the number exists now: a real tel: link with the digits stripped of any
    # invisible directional marks (the number arrived carrying U+202C), an
    # email fallback, and no placeholder
    m = re.search(r'href="tel:\+?([0-9]{10,13})"', page)
    assert m, "the call button must be a tel: link"
    assert m.group(1) in ("2073702160", "12073702160"), (
        "the Google Voice number, digits only, with or without the US 1-")
    assert "(207) 370-2160" in page, "the visible number, formatted"
    assert "placeholder-block" not in page, "the number era replaced the placeholder"
    import unicodedata as _uc
    invisible = [c for c in page if _uc.category(c) in ("Cf", "Cs", "Co", "Cn")]
    assert not invisible, f"invisible/bidi characters on the page: {[hex(ord(c)) for c in invisible]}"
    # reachable, and now in the nav too: the page's only action is live
    assert 'href="share-your-story.html"' in read(docs, "act-now.html")
    assert 'href="share-your-story.html"' in read(docs, "contact.html")
    nav = re.search(r'<nav class="main-nav".*?</nav>',
                    read(docs, "index.html"), re.S).group(0)
    assert 'href="share-your-story.html"' in nav, (
        "the page's action is live; the nav must offer it")


def test_share_your_story_how_to_share_leaves_the_callout(docs):
    """Ledger row 114 (2026-11-24). The operator, verbatim: "let's pull the top
    section out of the blue callout (no blue callout there, regular paragraph
    w/ header) and leave the callout for 'What you agree we can do with your
    recording'". "How to share" becomes a real heading with the call
    instruction and its button in the page's normal flow, the three-minute
    paragraph stays a regular paragraph between them, and the permission
    callout keeps its box under the consent framing the operator quoted."""
    page = read(docs, "share-your-story.html")
    # the how-to section is regular flow: a real heading, no box around it
    assert "<h2>How to share</h2>" in page
    start = page.index("<h2>How to share</h2>")
    consent_callout = page.index('<div class="callout">', start)
    between = page[start:consent_callout]
    assert 'class="callout"' not in between, (
        "no callout may sit between the How to share heading and the consent callout")
    # the call instruction and its button are in the normal flow
    assert "Call our Google Voice number and leave us a message:" in between
    assert 'href="tel:+12073702160"' in between
    # the shorter-messages paragraph stays a regular paragraph between the two
    assert "Google Voice caps messages at three minutes" in between
    # the consent callout is retitled to the operator's quoted framing
    assert "What you agree we can do with your recording" in page
    assert "What we will do with your recording" not in page


def test_site_wide_alert_strip(docs):
    """staging-feedback issue #2 (2026-11-24), the operator's first ask this
    morning with Dec. 1 seven days out: "We need an alert banner at the top
    of the site, on every page, that asks people to come to the 12/1 meeting
    and wear green." Upgraded 2026-11-25 (ledger row 124) by the operator's
    mobile-screenshot directive, quoted verbatim: "Banner should be sticky /
    Banner should be under nav / Banner should be dismissible (but not
    cookies, or short lived so it returns next day) / Shouldn't have so much
    empty room, not so much sky on Mobile / Banner text more like 'Next
    event: City council meeting, {{when & where}}. Show up by wearing green!
    {{Glyph/minor text for more}}'".

    The one banner element stays: restyled and repositioned, never a second
    banner. The nav comes first and the banner sits directly below it; the
    copy leads with the event in the operator's shape with a Details link as
    the glyph; the banner is sticky while the page scrolls; the close button
    dismisses until local midnight (date-keyed localStorage, no cookies); the
    dismissal pin is test_alert_banner_dismissal_is_day_keyed. The no-JS page
    shows the banner and hides the close affordance, so the meeting facts
    never depend on scripting.
    """
    for name in ("index.html", "act-now.html", "contact.html", "donate.html",
                 "share-your-story.html", "toolkit.html", "newsletter.html"):
        page = read(docs, name)
        # the nav comes first; the banner sits directly below it
        assert page.index('<header class="masthead"') < page.index('class="alert-strip"'), (
            f"{name}: the banner must sit below the nav")
        # the operator's copy, verbatim, with the Details glyph
        assert "Next event: City Council meeting, Tuesday, Dec. 1 at 6:30 p.m., City Hall Council Chambers, 25 Cottage Road. Show up by wearing green!" in page, name
        assert '<a class="alert-strip__details" href="act-now.html">Details</a>' in page, name
        # the close affordance ships hidden and carries a real label
        assert 'class="alert-strip__close" type="button" aria-label="Dismiss the event banner; it comes back tomorrow" hidden' in page, name
        # sticky while the page scrolls, in the shared stylesheet
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    start = css.index(".alert-strip {")
    block = css[start:css.index("}", start)]
    assert "position: sticky" in block and "top: 0" in block, "the banner must stick while the page scrolls"
    assert "var(--orange-dark)" in block
    assert "color: #fff" in block
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", block.replace("color: #fff", "")), (
        "the banner introduces a literal colour")
    # the day-key dismissal: the stored key is the local date string, the load
    # check hides only when the stored day equals today, so tomorrow's
    # mismatch returns the banner (behavioral proof in the leg's manifest)
    for page_name in ("index.html", "act-now.html"):
        page = read(docs, page_name)
        assert "psp-event-banner-day" in page, page_name
        assert "new Date().toDateString()" in page, page_name
        assert "if (stored === today) { strip.hidden = true; return; }" in page, page_name
    # the no-JS path: the banner has no hidden attribute in the served markup
    # (it shows without scripting; only the script reveals the close button)
    idx = read(docs, "index.html")
    assert '<div class="alert-strip" id="alert-strip">' in idx
    # the featured block's facts agree with the banner's facts (wording
    # divergence named: the operator's comma form vs the block's "in")
    act = read(docs, "act-now.html")
    assert "Tuesday, Dec. 1 at 6:30 p.m. in City Hall Council Chambers, 25 Cottage Road" in act
    # the map subtree is chrome-free by construction and stays outside the shell
    map_dir = os.path.join(docs, "map")
    if os.path.exists(os.path.join(map_dir, "map.html")):
        map_html = open(os.path.join(map_dir, "map.html"), encoding="utf-8").read()
        assert "alert-strip" not in map_html


def test_alert_banner_dismissal_is_day_keyed(docs):
    """Ledger row 124 (2026-11-25), the operator's dismissal rule: "Banner
    should be dismissible (but not cookies, or short lived so it returns next
    day)." The named return rule is DISMISSED UNTIL LOCAL MIDNIGHT: the click
    stores the local date string; the load hides the banner only while the
    stored day equals today, so a dismissal today still shows the banner under
    a faked tomorrow date — tomorrow's toDateString mismatches the stored day
    and the banner returns. No cookies, no consent machinery; the banner is
    the only thing the key controls. The behavioral proof (dismiss, reload,
    banner hidden; store yesterday's day, reload, banner back) is captured and
    read in tests/evidence/alert-banner-2026-11-25/."""
    idx = read(docs, "index.html")
    # the click path stores the day AT CLICK TIME (so a dismissal at 11:59 p.m.
    # stores that day, and the next day's load mismatches)
    assert "localStorage.setItem(KEY, new Date().toDateString())" in idx
    # the load path compares the stored day against TODAY'S day, not a fixed
    # string, so the rule is day-keyed end to end
    assert "var today = new Date().toDateString();" in idx
    assert "if (stored === today) { strip.hidden = true; return; }" in idx
    # nothing else is stored and nothing is sent: the key is write-only state
    assert idx.count("psp-event-banner-day") == 1
    assert "document.cookie" not in idx


def test_homepage_hero_card_is_centered_on_desktop(docs):
    """staging-feedback issue #4 (2026-11-24), the filer's ask verbatim: "Hero
    card should be roughly centered, vertically and horizontally. See red
    outline in this screenshot." / "Hero card is offset at bottom and
    slightly left."

    The fix is geometry on the band, not a re-crop: the 41.125vw cap rule
    stays whole, object-fit and object-position are untouched, and from
    1200px up the card centers on both axes with equal padding above and
    below. The centered card stands beside the lighthouse (the card's left
    edge lands at (viewport - 828) / 2, measured against the tower's white
    body at x ~ 233-266 in the leg's 1369 capture, so about 5px of clear
    water sits between them), so the tower reads in the clear at any card
    height, and the
    sails pass behind the card's translucent fill the way the filer's own
    outline drew them. Below 1200 the tablet and phone keep the shipped
    composition: there the card is 728px of a 768px window, so a centered
    card would sit behind the tower instead of beside it."""
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    # the centered geometry is scoped above 1200px and keeps the cap rule
    assert "@media (min-width: 1200px) {\n  .hero__inner { padding: 170px 20px 170px; align-items: center; justify-content: center; }\n}" in css
    assert "min-height: 41.125vw" in css, (
        "the row-112 cap rule must stay whole — this leg is geometry on the band, not a re-crop")
    assert re.search(r"object-position: 20% 100%", css), (
        "the focal point does not move")
    # the centered card's equal gaps and the lighthouse-beside reading are
    # measured in the leg's manifest; the CSS-side check is the scoping
    start = css.index("@media (min-width: 1200px) {\n  .hero__inner")
    assert css[start:].count("hero__inner") == 1, (
        "the centered block is one rule, kept clearly separated")


def test_act_now_leads_with_the_newcomer_plea(docs):
    """staging-feedback #3, the operator's mid-work comment (2026-11-25,
    verbatim): "This is probably needed on the Act Now page, as well" — the
    homepage's newcomer call-to-action lead is placed on the Act Now page as
    the lead-in above the featured block, wording consistent with the
    homepage lead. The two sentences pin that consistency on both pages; the
    date, venue and wear-green facts stay in the featured block and the
    site-wide strip, so nothing is duplicated."""
    act = read(docs, "act-now.html")
    idx = read(docs, "index.html")
    for page, name in ((act, "act-now.html"), (idx, "index.html")):
        assert "We know more than ever about how the tank farms are affecting this community" in page, name
        assert "Join us in urging the council to take the strongest action possible." in page, name
def test_act_now_leads_with_the_newcomer_plea(docs):
    """staging-feedback #3, the operator's mid-work comment (2026-11-25,
    verbatim): "This is probably needed on the Act Now page, as well" — the
    homepage's newcomer call-to-action lead is placed on the Act Now page as
    the lead-in above the featured block, wording consistent with the
    homepage lead. The two sentences pin that consistency on both pages; the
    date, venue and wear-green facts stay in the featured block and the
    site-wide strip, so nothing is duplicated.

    staging-website-feedback issue #7 (2026-11-25), recorded correction: the
    homepage's newcomer treatment ends with a direct push ("Write to the city
    council today... Wear green!"), but the Act now lede stopped at the
    abstract "urging... strongest action possible" and gave a newcomer no
    instruction. On the Act now page the urge now resolves into the concrete
    ask with a colon; the homepage keeps its original full-stop sentence. The
    lede still carries NO date/time/venue fact: the rows-129/130 facts-once
    rule keeps those in the featured block below.
    """
    act = read(docs, "act-now.html")
    idx = read(docs, "index.html")
    for page, name in ((act, "act-now.html"), (idx, "index.html")):
        assert "We know more than ever about how the tank farms are affecting this community" in page, name
    # the homepage keeps its shipped full-stop sentence (issue #7 changes
    # the Act now page's continuation, not the homepage's lead)
    assert "Join us in urging the council to take the strongest action possible." in idx, "index.html"
    # the Act now lede resolves the urge into concrete second-person verbs
    # (the meeting wording mirrors the featured block's own show-up step)
    assert "Join us in urging the council to take the strongest action possible: write to the City Council below, then come to the City Council meeting and wear green." in act, "act-now.html"
    # the lead-in sits above the featured block it introduces
    assert act.index("We know more than ever") < act.index('class="callout callout--ask"')
    # fact discipline: the lede adds no date/time/venue fact of its own
    lede = act[act.index("We know more than ever"):act.index('class="callout callout--ask"')]
    for fact in ("Tuesday, Dec. 1", "6:30", "6:15", "25 Cottage Road", "Dec. 1"):
        assert fact not in lede, (
            f"the lede must not duplicate the featured block's facts ({fact})")


def test_no_petition_styling_or_campaign_remains(docs):
    """The operator's clarification (2026-11-25, ledger row 126), verbatim:
    "remove the petition from all current asks/active campaigns, we don't have
    one running right now." The petition left the copy first (row 125); this
    pin retires its styling: the shared stylesheet's dead `.petition` /
    `.petition__inner` block (shipped with no user on any built page, kept
    from an earlier homepage era) is removed, and the suite-wide pins already
    assert the copy is gone. No petition may present as a current action
    anywhere; archive history that is neither CTA nor ask-adjacent could stay,
    and the sweep found none to keep."""
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    assert ".petition" not in css, (
        "no petition styling ships in the shared stylesheet (row 126)")
    built_css = read(docs, "styles.css")
    assert ".petition" not in built_css
    for name in html_files(docs):
        page = read(docs, name)
        assert "petition" not in page.lower(), (
            f"{name}: no petition reference remains in user-facing copy")


def test_staging_bar_ships_on_every_page(docs):
    """Ledger row 127 (2026-11-25), the operator's directive verbatim: "on the
    staging site ONLY, need the staging warning + last updated bar at top,
    above nav, non-dismissable. Maybe do it as a js injection feature toggled
    on the site url (match only root domain staging.protectsouthportland.*)".

    One script, shipped in the same built bytes as production - the toggle is
    the URL, not the build - so no served tree diverges. The script ships on
    every page; the BAR renders only under the matcher."""
    script = open(os.path.join(ROOT, "site", "assets", "js", "staging-bar.js"),
                  encoding="utf-8").read()
    built = open(os.path.join(docs, "assets", "js", "staging-bar.js"),
                 encoding="utf-8").read()
    assert script == built, "the built staging-bar bytes must match the source"
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        page = read(docs, name)
        assert '<script src="assets/js/staging-bar.js" defer></script>' in page, name
        # the bar markup itself ships NOWHERE in the served bytes - it is
        # JS-injected under the matcher only
        assert "staging preview. this is not the live site" not in page.lower(), name
        assert 'class="staging-bar"' not in page, name


def test_staging_bar_matches_only_the_staging_host(docs):
    """The matcher is the toggle: the root domain staging.protectsouthportland
    with any top-level domain hits (the operator's "hostname variants still
    hit"); production www/host variants, bare domains, localhost previews,
    file:// (empty hostname) and attacker suffixes do not. The Python pin
    mirrors the JS pattern exactly and the JS file must carry that exact
    token, so the tested rule is the shipped rule."""
    js = open(os.path.join(docs, "assets", "js", "staging-bar.js"),
              encoding="utf-8").read()
    token = "/^staging\\.protectsouthportland\\.[a-z]{2,}$/i"
    assert token in js, "the shipped matcher must be the tested pattern"
    match = re.fullmatch(r"staging\.protectsouthportland\.[a-z]{2,}",
                         "placeholder", re.I)
    assert match is None  # the pin's own helper sanity
    hits = ["staging.protectsouthportland.org", "staging.protectsouthportland.com",
            "staging.protectsouthportland.localhost",
            "STAGING.PROTECTSOUTHPORTLAND.ORG"]
    misses = ["www.protectsouthportland.org", "protectsouthportland.org",
              "protectsouthportland.com", "localhost", "127.0.0.1",
              "staging.example.com", "www.staging.protectsouthportland.org",
              "staging.protectsouthportland.org.evil.com", ""]
    for host in hits:
        assert re.fullmatch(r"staging\.protectsouthportland\.[a-z]{2,}", host, re.I), host
    for host in misses:
        assert not re.fullmatch(r"staging\.protectsouthportland\.[a-z]{2,}", host, re.I), host


def test_staging_bar_is_not_dismissable(docs):
    """Non-dismissable per the directive: no close affordance anywhere in the
    emitted markup, no state stored (localStorage/sessionStorage/cookies are
    absent from the script), and the bar carries the warning in the brand
    voice with the manifest-backed "last updated" fact. In document flow -
    the pin binds the insert to sit after the matcher guard, so nothing
    renders off the staging host."""
    js = open(os.path.join(docs, "assets", "js", "staging-bar.js"),
              encoding="utf-8").read()
    code = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)  # comments are record, not code
    assert "close" not in code.lower(), "no close affordance"
    assert "button" not in code.lower(), "no button, dismissable or otherwise"
    assert "localStorage" not in code and "sessionStorage" not in code
    assert "document.cookie" not in code, "nothing stored, period"
    assert "Last updated: " in js
    # the matcher guard returns before any DOM insertion: find the guard and
    # check every bar-creation call sits after it
    guard = js.index("if (!STAGING_HOST.test(window.location.hostname)) return;")
    insert = js.index("insertBefore(bar, masthead)")
    prepend = js.index("document.body.prepend(bar)")
    assert guard < insert and guard < prepend


def test_staging_bar_copy_time_hash_and_feedback(docs):
    """Ledger row 133 (2026-11-25), the operator's restyle directive verbatim:
    "Staging preview. Live site: protectsouthportland.org. Last updated:
    {{US Eastern time}} ({{commit hash}}). Feedback >>" (the {{...}} are
    placeholders; the bar ships the rendered format).

    RECORD CORRECTION (this leg): the row-127 copy pin asserted the old
    string "Staging preview. This is not the live site; the live site is
    protectsouthportland.org." - the operator's new format replaces it, so
    that pin is updated here, not extended.

    Pinned here: the exact copy string; the time as US Eastern with a fixed
    UTC input mirrored through the same pattern in Python; the fork sha in
    12-char short form; the feedback link's href, target and rel and its
    screen-reader name."""
    js = open(os.path.join(docs, "assets", "js", "staging-bar.js"),
              encoding="utf-8").read()

    # COPY: the operator's format, rendered, exactly (the manifest-backed
    # "Last updated:" span sits between the fixed lead and the feedback link)
    assert "Staging preview. Live site: protectsouthportland.org." in js
    assert "Feedback >>" in js

    # TIME: the manifest stays the data source and the formatter renders US
    # Eastern. The JS must carry the exact zone and pattern tokens; the
    # Python mirror below proves the pattern itself on a fixed UTC input.
    assert "timeZone: 'America/New_York'" in js, "the bar renders US Eastern"
    assert "month: 'short'" in js and "day: 'numeric'" in js
    assert "year: 'numeric'" in js and "minute: '2-digit'" in js
    assert "timeZoneName: 'short'" in js, "the named EST/EDT suffix"
    assert "a.m.' : 'p.m.'" in js, "the lowercase day period"
    # no build-time timestamp: the only time the script shows comes from the
    # manifest's served field
    assert "manifest.served" in js
    from datetime import datetime
    from zoneinfo import ZoneInfo
    eastern = datetime.fromisoformat(
        "2026-11-25T15:18:33+00:00").astimezone(ZoneInfo("America/New_York"))
    month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][eastern.month - 1]
    hour12 = eastern.hour % 12 or 12
    period = "a.m." if eastern.hour < 12 else "p.m."
    expected = (f"{month} {eastern.day}, {eastern.year}, "
                f"{hour12}:{eastern.minute:02d} {period} {eastern.tzname()}")
    assert expected == "Nov 25, 2026, 10:18 a.m. EST", expected

    # HASH: the fork sha in short form, first 12 chars (the length the bar
    # has shown since row 127, kept)
    assert "String(manifest.head).slice(0, 12)" in js

    # FEEDBACK LINK: exact href, new tab, no opener leak, screen-reader name
    feedback_url = ("https://github.com/Protect-South-Portland/"
                    "staging-website-feedback/issues/"
                    "new?template=website-feedback.yml")
    assert feedback_url in js
    assert "feedback.target = '_blank'" in js
    assert "feedback.rel = 'noopener noreferrer'" in js
    assert ("aria-label', 'Feedback — file a comment on the staging preview'"
            in js), "the accessible name"


def test_toolkit_reference_page(docs):
    """Ruling on `dec_inuqu6bhpw6r`, option one-page ("One reference page,
    durable chapters only"), ledger row 78: `toolkit.html` carries four
    chapters of the campaign's 2026 South Portland Tanks Toolkit — the tank
    timeline, the fenceline findings, the Oct. 15 community-meeting FAQs, and
    the letter-to-the-editor guidance.

    The copy is carried from that document, not rewritten, so the only words a
    writer composed here are the chapter headings, the anchor labels, one
    orientation line and the pointer back to the live document. This pins the
    document's own opening lines, the artifacts that must never ship, the
    chapters the ruling left behind, and the two places that reach the page.
    The header's own five-item pin lives in
    `test_header_nav_pins_the_five_items`, which now carries the three
    rulings that shaped it.

    Two carried-copy defects stay on the page by decision, taken in the gate
    review of 2026-11-24, and a later agent must not "fix" them silently:

    - "The lawsuits create a public outcry but ends in consent decrees" is the
      campaign document's own subject-verb slip. Correcting it would rewrite
      campaign prose, so the page keeps it and the campaign fixes the source.
    - Two FAQ answers name the Oct. 27 workshop and "this year's" council
      candidates. The chapter lede already dates every answer to the October 15
      meeting, so the dated answer is honest as the snapshot it is.
      (Record note 2026-11-24, ledger row 123: the FAQ answers no longer carry
      the Oct. 27 date; they read forward, "The Dec. 1 workshop is set to
      consider licensing fees…" — this comment is superseded by that change,
      verified by the tree-wide sweep, so do not read it as a guard to
      restore.)

    The same review fixed four others, and those came down to a proper-noun
    spelling or an anchor label rather than campaign wording: Bug Light (the
    source writes "Bug LIght"), Ligonia (the source writes "Lygonia"), the
    orientation line, and the Press Herald letters link's anchor text.
    """
    page = read(docs, "toolkit.html")

    # 1. the four chapters, each a heading with an anchor the jump row reaches
    chapters = (
        ("timeline", "Timeline of the tanks"),
        ("fenceline-findings", "Fenceline findings, point by point"),
        ("faqs", "FAQs from the Oct. 15 community meeting"),
        ("letter-to-the-editor", "Letter to the editor guidance"),
    )
    for anchor, heading in chapters:
        assert f'id="{anchor}"' in page, anchor
        assert f"<h2>{heading}</h2>" in page, heading
        assert f'href="#{anchor}"' in page, f"the jump row must reach {anchor}"

    # the copy is the document's, not a paraphrase: each chapter's own first
    # line, plus the sentences a reader would check it by
    for carried in (
        "The Troubled History of Tank Farms in South Portland",
        "The first tank farms were built in South Portland in the 1940s to "
        "support fuel movement during World War II",
        "10 of the 11 facilities statewide had at least one fenceline "
        "monitoring location",
        "Questions posed by community members at the community meeting on "
        "October 15, 2026.",
        "Letters to the Editor - Points for Writing - 150 words maximum",
        "Why the hell is this taking so long?",
        "What residents can do: Read the Tank Farms Toolkit",
    ):
        assert carried in page, f"carried copy missing: {carried[:60]}"

    # the benzene correction (tier-two, row-74 class): the document still says
    # "state standards"; the page carries it in the site's framing instead
    assert ("regularly and dramatically exceeds Maine&rsquo;s ambient air "
            "guideline for long-term exposure") in page
    assert "guideline" in page and "state standards" not in page

    # 2. the two places that reach the page, and neither is the header. The
    # copy pins read tag-stripped text (2026-11-24 bold pass), and the href
    # pins the target, so an emphasis edit cannot break the placement rule.
    act = read(docs, "act-now.html")
    act_text = reading_text(act)
    assert "read the tank farms toolkit" in act_text, (
        "the Act now block must link the toolkit page")
    assert '<a href="toolkit.html">read the tank farms toolkit</a>' in act
    act_tail = act[act.index("get plugged into local tank farm efforts"):]
    assert "toolkit.html" in act_tail, (
        "the toolkit block belongs at the end of the page")
    footer = read(docs, "index.html")
    footer = footer[footer.index('class="footer"'):]
    assert '<a href="toolkit.html">Tank farms toolkit</a>' in footer

    # 3. draft artifacts and unpublished answers never ship
    banned = (
        # the two tabs outside this page's four: never carried at all
        "UPDATES IN PROGRESS", "TO BE UPDATED",
        # the unanswered FAQ items and the note that followed them
        "****",
        "To sit on my deck",
        "As toxins seep into the ground water",
        "Is there a way to test our residential land",
        "These are great questions to ask at the city council meeting",
    )
    for needle in banned:
        assert needle not in page, f"toolkit.html ships a draft artifact: {needle}"

    # 4. the chapters the ruling left in the live document
    for excluded in (
        "Glossary", "Health Impacts of Benzene", "VOC and HAP",
        "mi from fenceline", "Demand for action",
    ):
        assert excluded not in page, (
            f"toolkit.html smuggles in an excluded chapter: {excluded}")
    # the live document is linked instead, because its goals chapter is
    # rewritten after every meeting
    assert ("https://docs.google.com/document/d/"
            "1O8EaHEJALZtTCUBoxFAwR_1ySOY08xbmvub4wx5FFLc/edit") in page


class _TopNavLinks(HTMLParser):
    """Top-level hrefs of the main navigation: one per item, submenus excluded."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "ul":
            self.depth += 1
        elif tag == "a" and self.depth == 1:
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)

    def handle_endtag(self, tag):
        if tag == "ul":
            self.depth -= 1


def test_header_nav_pins_the_five_items(docs):
    """The header nav: five items plus the Act now pill, in this order —
    Home, Our work, About, Share your story, Contact.

    This pin has been rewritten once and it carries all three rulings, in the
    order they were made, because the third reverses the first:

    1. 2026-11-23 (`9474c5e`): the header was cut to five items because Act
       now, Get involved and Donate all read as the same call to action. That
       pass removed Home, Get involved and Donate, leaving Our work, About,
       Share your story, Newsletter, Contact. Home went on the reasoning that
       the seal already links home, so a second Home link only repeated the
       logo.
    2. 2026-11-24: Newsletter left the header. Its page did not move and did
       not close; the subscription became a mailto component on
       `newsletter.html` itself, and the header stopped spending one of its
       five slots on a page the footer still links.
    3. 2026-11-24, same day: Home returned as the first item, by operator
       instruction. The count held at five, so this was a swap of one item
       for another rather than a sixth entry.

    The assertion stays exact on purpose: not a count, not a subset, not a
    membership test. A quiet sixth item, a reordering, or a renamed target
    fails by name.
    """
    nav = re.search(r'<nav class="main-nav".*?</nav>',
                    read(docs, "index.html"), re.S).group(0)
    collector = _TopNavLinks()
    collector.feed(nav)
    assert collector.hrefs == [
        "index.html", "our-campaigns.html", "about.html",
        "share-your-story.html", "contact.html", "act-now.html",
    ], collector.hrefs
    assert nav.count('class="nav-cta"') == 1, "one pill, the Act now link"
    assert "toolkit.html" not in nav, "the toolkit page is not a nav item"
    assert "newsletter.html" not in nav, (
        "Newsletter left the header; the signup lives on its own page")
    # the dropped item's page keeps a sitewide path, or the header change
    # would orphan it
    footer = read(docs, "index.html")
    footer = footer[footer.index('class="footer"'):]
    assert '<a href="newsletter.html">Newsletter</a>' in footer, (
        "the newsletter page must stay reachable from the footer once the "
        "header stops carrying it")


def test_nav_structure_after_split(docs):
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        m = re.search(r'<nav class="main-nav".*?</nav>', read(docs, name), re.S)
        nav = m.group(0)
        # row 40 (2026-10-15): one "Our work" header item; the active
        # campaigns are its first children and the past-work pages live in a
        # nested flyout labeled Past work
        assert "Our work" in nav, name
        assert "Active campaigns" not in nav, name
        assert "Past work" in nav, name
        assert 'href="our-campaigns.html"' in nav, name
        assert 'aria-haspopup="true"' in nav, name
        assert "aria-expanded=" in nav, name
        first_child = nav.index(">South Portland Tank Farms<")
        past_label = nav.index(">Past work<")
        all_past = nav.index(">All past work<")
        yard = nav.index(">Yard South Proposal<")
        assert first_child < past_label < all_past < yard, name
        assert "Our Campaigns" not in nav, name
        assert "oil-tank-emissions.html" not in nav, name
        assert "vocs.html" not in nav, name
        assert 'href="tank-farms.html"' in nav, name
    tf = read(docs, "tank-farms.html")
    assert '<h1>South Portland Tank Farms</h1>' in tf
    assert EMBED_URL in tf
    assert 'id="health-effects-of-vocs"' in tf
    assert "assets/files/hem3-report-summary.pdf" in tf


def test_row40_flyout_structure_on_built_page(docs):
    # row 40 (2026-10-15): the Past work flyout + its five children render in
    # the built chrome on a page nobody edited for this row (404.html): one
    # nested flyout per nav, every child a real link
    nav = re.search(r'<nav class="main-nav".*?</nav>', read(docs, "404.html"), re.S).group(0)
    assert nav.count('<li class="has-sub has-flyout">') == 1, nav
    assert nav.count('class="submenu flyout"') == 1, nav
    for link in (
        'href="past-work.html">All past work</a>',
        'href="yard-south-proposal.html">Yard South Proposal</a>',
        'href="clear-skies.html">Clear Skies</a>',
        'href="fertilizer-ban.html">Fertilizer Ban</a>',
        'href="pesticides.html">Pesticides</a>',
    ):
        assert link in nav, link


def test_row40_landing_retitle(docs):
    # row 40 landing coherence: the "Our work" nav item lands on a page whose
    # h1 + title carry the dictated label; the archive + the four past-work
    # items are linked from the body (compact section, no prose changes)
    page = read(docs, "our-campaigns.html")
    assert "<h1>Our work</h1>" in page, page[:400]
    assert re.search(r"<title>Our work[^<]*</title>", page), page[:400]
    for href in (
        "past-work.html", "yard-south-proposal.html",
        "clear-skies.html", "fertilizer-ban.html", "pesticides.html",
    ):
        assert f'href="{href}"' in page, href


# ---- row 42 (2026-10-15): staging obscurity + cookie gate (staging leg only) ----

GATE_TEST_PASSPHRASE = "correct pass"


def staged_tree(tmp_path, docs, name):
    tree = tmp_path / name
    tree.mkdir()
    publish.stage_publish_tree(str(tree), docs_dir=str(docs))
    return str(tree)


def html_relpaths(tree):
    paths = []
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".html"):
                paths.append(os.path.relpath(os.path.join(dirpath, name), tree))
    return sorted(paths)


def test_row42_flag_constants():
    assert publish.STAGING_GATE is True, "staging target ships the gate by default (row 42)"
    assert publish.GATE_COOKIE == "psp_staging"
    assert publish.GATE_MARKER == "staging-gate"
    assert "Disallow: /" in publish.GATE_ROBOTS_TEXT


def test_row42_prod_staged_tree_has_no_gate(tmp_path, docs):
    # prod/mirror staged tree: never gated, never disallowed. The map
    # artifacts keep their pre-existing embed noindex (unchanged behavior)
    tree = staged_tree(tmp_path, docs, "prod")
    assert not os.path.exists(os.path.join(tree, "robots.txt"))
    assert "staging-gate" in psp_public.PRIVATE_MARKERS
    for rel in html_relpaths(tree):
        text = open(os.path.join(tree, rel), encoding="utf-8").read()
        assert "staging-gate" not in text, rel
        assert "Disallow: /" not in text, rel
        if rel.startswith("map/"):
            continue
        assert 'name="robots"' not in text, rel


def test_row42_prod_scan_refuses_a_gated_tree(tmp_path, docs):
    # the prod-side guard (row 42): a tree carrying the gate marker fails
    # the mirror scan loud — a gated tree can never reach a prod leg quietly
    tree = staged_tree(tmp_path, docs, "prod-scan")
    open(os.path.join(tree, "index.html"), "a", encoding="utf-8").write("<!-- staging-gate -->")
    with pytest.raises(SystemExit):
        psp_public.assert_clean(psp_public.scan_tree(tree), "scratch")


def test_row42_staging_gate_positive(tmp_path, docs):
    # the staging leg's gate: Disallow-all robots + noindex/nofollow meta +
    # the per-page cookie-gate script on EVERY staged html; the passphrase
    # itself never ships — only its SHA-256 hex
    tree = staged_tree(tmp_path, docs, "staging")
    before = html_relpaths(tree)
    expected_hash = hashlib.sha256(GATE_TEST_PASSPHRASE.encode("utf-8")).hexdigest()
    count = publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE)
    # the built tree's size depends on whether the sibling map repo is present
    # (CI has no sibling: 16 source pages + 2 generated redirect stubs = 18;
    # locally the map adds 2 more), so the floor is derived from the repo, not
    # a frozen literal. The real contract is that the gate touches every
    # staged page and renames none.
    source_pages = [n for n in os.listdir(os.path.join(ROOT, "site", "pages"))
                    if n.endswith(".html")]
    assert len(before) >= len(source_pages), (
        f"every built source page is staged ({len(before)} < {len(source_pages)})")
    assert count == len(before), "the gate touches every staged page, renames none"
    assert html_relpaths(tree) == before, "the gate adds robots.txt, renames no page"
    assert open(os.path.join(tree, "robots.txt"), encoding="utf-8").read() == publish.GATE_ROBOTS_TEXT
    for rel in html_relpaths(tree):
        text = open(os.path.join(tree, rel), encoding="utf-8").read()
        assert '<meta name="robots" content="noindex, nofollow">' in text, rel
        assert "staging-gate" in text, rel
        assert "psp_staging" in text, rel
        assert expected_hash in text, rel
        assert GATE_TEST_PASSPHRASE not in text, rel


def test_row42_gate_refuses_missing_head(tmp_path):
    tree = tmp_path / "headless"
    tree.mkdir()
    open(os.path.join(str(tree), "page.html"), "w", encoding="utf-8").write(
        "<html><body>hi</body></html>")
    with pytest.raises(SystemExit):
        publish.apply_staging_gate(str(tree), GATE_TEST_PASSPHRASE)


def test_row42_gate_refuses_double_gate(tmp_path, docs):
    tree = staged_tree(tmp_path, docs, "twice")
    assert publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE) > 0
    with pytest.raises(SystemExit):
        publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE)


def test_row42_gate_rewrites_the_prod_robots_variant(tmp_path, docs):
    # docs/ ships a tracked Allow-all robots.txt (2026-10-12) that reaches
    # every staged (real) tree; the staging gate REWRITES it to the
    # Disallow-all staging variant (row 42: "staged robots.txt rewritten to
    # Disallow-all"). The tmp build fixture does not include that tracked
    # file, so the test seeds the tree with it.
    tree = staged_tree(tmp_path, docs, "rewrite")
    open(os.path.join(tree, "robots.txt"), "w", encoding="utf-8").write("User-agent: *\nAllow: /\n")
    publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE)
    assert open(os.path.join(tree, "robots.txt"), encoding="utf-8").read() == publish.GATE_ROBOTS_TEXT


def test_row42_passphrase_sources_and_loud_refusal(tmp_path, monkeypatch):
    # passphrase: env wins, then the gitignored .env beside the checkout;
    # neither present = the staging leg refuses loud (no placeholder, ever)
    monkeypatch.setattr(publish, "STAGING_DOTENV", os.path.join(str(tmp_path), "env"))
    monkeypatch.delenv(publish.ENV_NAME, raising=False)
    with pytest.raises(SystemExit) as missing:
        publish.staging_passphrase()
    assert publish.ENV_NAME in str(missing.value)
    open(os.path.join(str(tmp_path), "env"), "w", encoding="utf-8").write(
        "# comment\nOTHER=1\n" + publish.ENV_NAME + "=from-dotenv\n")
    assert publish.staging_passphrase() == "from-dotenv"
    monkeypatch.setenv(publish.ENV_NAME, "from-env")
    assert publish.staging_passphrase() == "from-env"


# ---- row 79 (2026-11-24): staging publish-time stamp (staging leg only) ----

# The stamp is generated from the clock the staging leg is handed, never typed
# into a page. 19:32 UTC on 2026-11-24 is 2:32 PM EST in South Portland.
STAMP_WHEN = datetime.datetime(2026, 11, 24, 19, 32, tzinfo=datetime.timezone.utc)
STAMP_LABEL = "Staging preview, updated Nov 24, 2026 at 2:32 PM EST"
MASTHEAD_OPEN = '<header class="masthead">'
NAV_OPEN = '<nav class="main-nav"'


def header_block(markup):
    """The masthead element's markup, from its opening tag to its close."""
    start = markup.index(MASTHEAD_OPEN)
    return markup[start:markup.index("</header>", start)]


def nav_block(markup):
    """The main nav's markup, from <nav class="main-nav" to </nav>."""
    start = markup.index(NAV_OPEN)
    return markup[start:markup.index("</nav>", start)]


def masthead_pages(tree):
    """Staged pages that carry the site chrome (the stamp's injection point).

    The redirect stubs and the copied standalone map pages have no masthead,
    so they are not stampable by construction; every other staged page is.
    """
    found = []
    for rel in html_relpaths(tree):
        text = open(os.path.join(tree, rel), encoding="utf-8").read()
        if MASTHEAD_OPEN in text:
            found.append(rel)
    return found


def test_row79_staging_leg_stamps_every_page_with_the_publish_time(tmp_path, docs):
    # The line rides the staging leg: every built page whose chrome carries a
    # masthead gets it, and the date inside it is the clock the leg was given,
    # so a hand-typed date can never be what ships.
    tree = staged_tree(tmp_path, docs, "stamp")
    publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE)
    stamped = publish.apply_staging_update_stamp(tree, STAMP_WHEN)
    pages = masthead_pages(tree)
    source_pages = [n for n in os.listdir(os.path.join(ROOT, "site", "pages"))
                    if n.endswith(".html")]
    assert stamped == len(pages)
    assert stamped == len(source_pages), (
        f"every built source page is stamped ({stamped} != {len(source_pages)})")
    for rel in pages:
        text = open(os.path.join(tree, rel), encoding="utf-8").read()
        assert publish.STAMP_MARKER in text, rel
        assert STAMP_LABEL in text, rel


def test_row79_stamp_follows_the_clock_it_is_given(tmp_path, docs):
    # two publishes, two different minutes: the label is generated, not fixed
    later = STAMP_WHEN + datetime.timedelta(hours=1)
    first = staged_tree(tmp_path, docs, "clock-a")
    second = staged_tree(tmp_path, docs, "clock-b")
    publish.apply_staging_update_stamp(first, STAMP_WHEN)
    publish.apply_staging_update_stamp(second, later)
    a = open(os.path.join(first, "index.html"), encoding="utf-8").read()
    b = open(os.path.join(second, "index.html"), encoding="utf-8").read()
    assert STAMP_LABEL in a
    assert "Staging preview, updated Nov 24, 2026 at 3:32 PM EST" in b
    assert STAMP_LABEL not in b


def test_row79_prod_leg_carries_no_stamp(tmp_path, docs):
    # the staging leg is the only caller: a production-targeted publish builds
    # the same tree and never stamps it, and the leg decision is a function
    # main() reads, so this is provable without a push
    assert publish.staging_leg_gated(publish.PROD_REPO) is False
    assert publish.staging_leg_gated(publish.STAGING_REPO) is True
    tree = staged_tree(tmp_path, docs, "prod-stamp")
    for rel in html_relpaths(tree) + ["styles.css"]:
        text = open(os.path.join(tree, rel), encoding="utf-8").read()
        assert publish.STAMP_MARKER not in text, rel
        assert "Staging preview" not in text, rel


def test_row79_stamp_marker_is_a_private_surface_marker():
    # containment: the marker joins the private-surface set, so any leg that
    # somehow carries the stamp fails the publication scan loud
    assert publish.STAMP_MARKER in psp_public.PRIVATE_MARKERS
    page = (MASTHEAD_OPEN +
            f'<p class="{publish.STAMP_MARKER}">{STAMP_LABEL}</p></header>')
    violations = psp_public.scan_text(page, "scratch page")
    assert violations, "the stamp marker must fail the publication scan"
    assert any(publish.STAMP_MARKER in v for v in violations), violations


def test_row79_prod_scan_refuses_a_stamped_tree(tmp_path, docs):
    tree = staged_tree(tmp_path, docs, "prod-stamp-scan")
    publish.apply_staging_update_stamp(tree, STAMP_WHEN)
    with pytest.raises(SystemExit):
        psp_public.assert_clean(psp_public.scan_tree(tree), "scratch")


def test_row79_stamp_leaves_the_nav_alone(tmp_path, docs):
    # the line is chrome above the masthead's inner row: five nav items plus
    # the pill stay byte-identical, and the label never lands inside the nav
    tree = staged_tree(tmp_path, docs, "nav")
    before = open(os.path.join(tree, "index.html"), encoding="utf-8").read()
    publish.apply_staging_update_stamp(tree, STAMP_WHEN)
    after = open(os.path.join(tree, "index.html"), encoding="utf-8").read()
    assert nav_block(after) == nav_block(before), "the stamp must not touch the nav"
    header = header_block(after)
    assert header.count("<li") == header_block(before).count("<li") == 14, (
        "six top-level items (five links + the Act now pill) and eight submenu items")
    inner = header.index('<div class="masthead__inner">')
    stamp = header.index(f'class="{publish.STAMP_MARKER}"')
    assert stamp < inner, "the label sits above the logo/nav row, in the masthead"
    assert stamp < header.index(NAV_OPEN)
    assert publish.STAMP_MARKER not in nav_block(after)
    assert header.count(f'class="{publish.STAMP_MARKER}"') == 1, "one stamp per page"


def test_row79_stamp_refuses_a_chromeless_page(tmp_path):
    # a page with neither a masthead nor a redirect stub would silently ship
    # unstamped; the injection refuses instead
    tree = tmp_path / "chromeless"
    tree.mkdir()
    (tree / "page.html").write_text(
        "<!DOCTYPE html><html lang=\"en\"><head><title>x</title></head>"
        "<body><p>hi</p></body></html>", encoding="utf-8")
    with pytest.raises(SystemExit):
        publish.apply_staging_update_stamp(str(tree), STAMP_WHEN)


def test_row79_stamp_refuses_a_double_stamp(tmp_path, docs):
    tree = staged_tree(tmp_path, docs, "stamp-twice")
    assert publish.apply_staging_update_stamp(tree, STAMP_WHEN) > 0
    with pytest.raises(SystemExit):
        publish.apply_staging_update_stamp(tree, STAMP_WHEN)


# ---- row 79, second pass: the comparison boundary (operator, 2026-11-24) ----
#
# The production lane verifies a staging tree by fetching the HTML staging
# serves and comparing it against the page hashes in the gate report. Both
# publish-time injections (the row-42 gate block and the row-79 stamp) make
# served bytes differ from the hashed bytes, so ONE strip function takes both
# off before any such comparison.

def injected_tree(tmp_path, docs, name):
    """A staged tree carrying both injections, as the staging leg ships it."""
    tree = staged_tree(tmp_path, docs, name)
    publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE)
    publish.apply_staging_update_stamp(tree, STAMP_WHEN)
    return tree


def test_row79_strip_removes_both_injections_and_restores_the_build(tmp_path, docs):
    tree = staged_tree(tmp_path, docs, "strip-src")
    built = {rel: open(os.path.join(tree, rel), encoding="utf-8").read()
             for rel in html_relpaths(tree)}
    publish.apply_staging_gate(tree, GATE_TEST_PASSPHRASE)
    publish.apply_staging_update_stamp(tree, STAMP_WHEN)
    assert publish.INJECTED_BLOCK_MARKERS == (
        publish.GATE_MARKER, publish.STAMP_MARKER), (
        "one registry, both publish-time injections")
    for rel, before in sorted(built.items()):
        served = open(os.path.join(tree, rel), encoding="utf-8").read()
        assert served != before, f"{rel}: nothing was injected"
        assert publish.GATE_MARKER in served, rel
        stripped = publish.strip_injected_blocks(served)
        assert stripped == before, f"{rel}: the strip must restore the build byte for byte"
        assert publish.GATE_MARKER not in stripped, rel
        assert publish.STAMP_MARKER not in stripped, rel


def test_row79_served_pages_hash_equal_the_gate_report_after_the_strip(tmp_path, docs):
    # the comparison the production lane runs: fetch what staging serves, strip
    # the two injections, hash, compare with the report's page hash
    tree = injected_tree(tmp_path, docs, "compare")
    pages = [n for n in os.listdir(os.path.join(ROOT, "site", "pages"))
             if n.endswith(".html")]
    for page in pages:
        served = open(os.path.join(tree, page), encoding="utf-8").read()
        built_sha = publish.page_sha256(page, docs_dir=str(docs))
        assert publish.served_page_sha256(served) == built_sha, page
        assert publish.served_page_matches(served, page, docs_dir=str(docs)) is True, page
        # without the strip the same page does not match: that is the defect
        assert hashlib.sha256(served.encode("utf-8")).hexdigest() != built_sha, page


def test_row79_index_check_sees_through_both_injections(tmp_path, docs):
    # strict equality after the strip, with no fallback anywhere: the served
    # index matches because the bytes match
    tree = injected_tree(tmp_path, docs, "index-check")
    served = open(os.path.join(tree, "index.html"), encoding="utf-8").read()
    built_path = os.path.join(str(docs), "index.html")
    assert publish.index_matches_built(served, built_path) is True, (
        "both injections must come off before the served index is compared")


def body_edit(text, old, new):
    """One character changed inside <main>, leaving the banner and the chrome
    alone. Used to prove the strip cannot swallow a real difference."""
    start = text.index("<main")
    head, body = text[:start], text[start:]
    assert old in body, f"{old!r} is not in the body, pick another character"
    return head + body.replace(old, new, 1)


def test_row79_index_check_refuses_one_body_character(tmp_path, docs):
    # one character inside the body must fail. The banner line is still on the
    # page and there is no longer any branch that reads it, so a pass here would
    # mean the strip had eaten real copy.
    tree = injected_tree(tmp_path, docs, "index-body")
    served = open(os.path.join(tree, "index.html"), encoding="utf-8").read()
    built_path = os.path.join(str(docs), "index.html")
    assert psp_public.BANNER_TEXT in served, "the fixture must carry the banner"
    assert publish.index_matches_built(served, built_path) is True
    tampered = body_edit(served, "e", "E")
    assert tampered != served
    assert publish.index_matches_built(tampered, built_path) is False, (
        "one changed body character must fail the strict comparison")


def test_row79_served_page_matches_refuses_one_body_character(tmp_path, docs):
    tree = injected_tree(tmp_path, docs, "page-body")
    served = open(os.path.join(tree, "about.html"), encoding="utf-8").read()
    assert publish.served_page_matches(served, "about.html", docs_dir=str(docs)) is True
    tampered = body_edit(served, "e", "E")
    assert publish.strip_injected_blocks(tampered) != publish.strip_injected_blocks(served)
    assert publish.served_page_matches(
        tampered, "about.html", docs_dir=str(docs)) is False, (
        "a one-character body edit must change the served page's hash")


def test_row79_strip_is_bounded_by_its_own_markers():
    # the strip may only remove a region that opens and closes with OUR exact
    # marker pair. Real copy survives: an unmatched open, an unmatched close, a
    # near-miss comment, and anything outside a complete pair.
    open_gate = publish.injected_block_open(publish.GATE_MARKER)
    close_gate = publish.injected_block_close(publish.GATE_MARKER)
    # an unmatched open, with no close anywhere: nothing is removed
    stray_open = f"<p>KEEP ONE</p>{open_gate}<p>KEEP TWO</p>"
    assert publish.strip_injected_blocks(stray_open) == stray_open
    # an unmatched close: nothing is removed either
    stray_close = f"<p>KEEP THREE</p>{close_gate}<p>KEEP FOUR</p>"
    assert publish.strip_injected_blocks(stray_close) == stray_close
    # a comment that only looks like a marker is not ours and stays put
    near_miss = "<p><!-- staging-gate:injection --> KEEP FIVE</p>"
    assert publish.strip_injected_blocks(near_miss) == near_miss
    # one complete region between copy: the region goes, the copy stays
    around = f"<p>KEEP SIX</p>{open_gate}<p>gate body</p>{close_gate}<p>KEEP SEVEN</p>"
    stripped = publish.strip_injected_blocks(around)
    assert "<p>gate body</p>" not in stripped
    assert "KEEP SIX" in stripped and "KEEP SEVEN" in stripped
    # a truncated pair (open, copy, open, body, close) must not swallow the copy
    # between the two opens: the later region goes, the earlier open stays, so a
    # comparison fails loud instead of silently deleting a page chunk
    truncated = f"{open_gate}<p>KEEP EIGHT</p>{open_gate}<p>gate body</p>{close_gate}"
    kept = publish.strip_injected_blocks(truncated)
    assert "KEEP EIGHT" in kept, kept
    assert "<p>gate body</p>" not in kept, kept


def test_row79_index_check_waits_out_a_rebuild_then_passes(tmp_path, docs):
    # the deleted fallback covered one real case: a Pages rebuild that has not
    # landed yet. The answer is to wait for the real bytes.
    built_path = os.path.join(str(docs), "index.html")
    built = open(built_path, encoding="utf-8").read()
    stale = "<p>the previous build</p>"
    now = [0.0]
    reads = [stale, stale, built]

    def fetch():
        return reads.pop(0)

    def clock():
        return now[0]

    def pause(seconds):
        now[0] += seconds

    assert publish.wait_for_built_index(
        built_path, fetch, minutes=2, clock=clock, pause=pause) == built


def test_row79_index_check_fails_loud_when_the_rebuild_never_lands(tmp_path, docs):
    built_path = os.path.join(str(docs), "index.html")
    now = [0.0]
    calls = []

    def fetch():
        calls.append(1)
        return "<p>the previous build</p>"

    def clock():
        return now[0]

    def pause(seconds):
        now[0] += seconds

    with pytest.raises(SystemExit) as stopped:
        publish.wait_for_built_index(
            built_path, fetch, minutes=1, clock=clock, pause=pause)
    assert "did not serve the built index" in str(stopped.value)
    assert len(calls) > 1, "the wait must poll, not read once"


def test_row79_prod_leg_refuses_a_tree_that_already_carries_the_stamp(
        tmp_path, docs, monkeypatch, capsys):
    # the ban, exercised through the production leg's own path: a docs tree
    # that already carries the stamp reaches the mirror scan and is refused
    # with the marker named. Nothing is built (build_site is stubbed) and
    # nothing leaves the temp dir (custom --mirror-dir = local run).
    root = tmp_path / "repo"
    shutil.copytree(str(docs), str(root / "docs"))
    shutil.copytree(os.path.join(ROOT, "site", "pages"),
                    str(root / "site" / "pages"))
    assert publish.apply_staging_update_stamp(
        str(root / "docs"), STAMP_WHEN) > 0
    monkeypatch.setattr(publish, "ROOT", str(root))
    monkeypatch.setattr(publish, "build_site", lambda: None)
    monkeypatch.setattr(publish, "require_clean_worktree", lambda: None)
    monkeypatch.setattr(publish, "source_provenance", lambda: ("deadbee", ""))
    pages = sorted(n for n in os.listdir(root / "site" / "pages")
                   if n.endswith(".html"))
    report = {
        "date": "row79-test",
        "review_model": "test/full-class",
        "review_class": "full",
        "pages": {page: {"rounds": 1, "outcome": "pass",
                         "sha256": publish.page_sha256(page)}
                  for page in pages},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "publish.py", "--gate-report", str(report_path),
        "--repo", publish.PROD_REPO,
        "--mirror-dir", str(tmp_path / "mirror"),
        "--changelog-waiver", "test run, nothing is published anywhere",
    ])
    with pytest.raises(SystemExit) as refused:
        publish.main()
    assert publish.STAMP_MARKER in str(refused.value), (
        "the production leg's scan must name the marker: " + str(refused.value))
    assert not (tmp_path / "mirror").exists(), "nothing is pushed or committed"


def test_map_not_the_lead_on_tank_farms_page(docs):
    """Operator directive 2026-10-13: on the dedicated campaign page the map is
    never the lead element — where-things-stand text and the tank narrative
    come first."""
    tf = read(docs, "tank-farms.html")
    iframe = tf.index(EMBED_URL)
    assert tf.index("id=\"where-things-stand\"") < iframe
    assert tf.index("120 large petroleum tanks") < iframe
    # row 77 (2026-11-24) exchanged the map and the aerial photo on the
    # homepage, so there the photo leads and the map follows the prose; the
    # campaign page keeps text-before-map exactly as row 3 rules it.
    idx = read(docs, "index.html")
    assert idx.index("assets/photos/tank-farms-aerial.jpg") < idx.index(EMBED_URL)


def test_row5_banner_verbatim_on_homepage(docs):
    idx = read(docs, "index.html")
    assert BANNER_TEXT in idx
    # banner is the very top of the page body: before the tank-farms section
    assert idx.index(BANNER_TEXT) < idx.index('id="tank-farms"')


def test_row7_section_relabelled(docs):
    idx = read(docs, "index.html")
    assert '<h2>South Portland Tank Farms</h2>' in idx
    assert 'id="tank-farms"' in idx


def test_row77_photo_prose_map_replaces_row3_on_homepage(docs):
    """Ledger row 77 (operator, 2026-11-24): the homepage tank-farms section
    exchanges the map and the aerial photo, so it runs the photo, then the
    two prose paragraphs, then the map with its slider note. Photo, prose,
    map; not photo, map, prose.

    This supersedes ledger row 3 (Mindy, 2026-10-12), which put the map
    top-center with her text below it. Row 3 still rules every page where the
    map is not sharing a section with a photograph, which is why
    test_map_not_the_lead_on_tank_farms_page keeps pinning text-before-map on
    the campaign page. The map-first assertion is retargeted to the new
    order, never dropped.

    The same row renames the kicker: the long sentence label becomes a short
    one in the house kicker style, matching "The campaign" and "Past work"."""
    idx = read(docs, "index.html")
    kicker = '<span class="kicker">Current campaign</span>'
    assert "The issue front and center" not in idx, "the old sentence label is replaced, not joined"
    iframe_pos = idx.index(EMBED_URL)
    assert '<iframe' in idx
    kicker_pos = idx.index(kicker)
    h2_pos = idx.index("<h2>South Portland Tank Farms</h2>")
    figure_pos = idx.index('<figure class="figure">')
    img_pos = idx.index("assets/photos/tank-farms-aerial.jpg")
    caption_pos = idx.index("The tank farms along South Portland&rsquo;s working waterfront.")
    prose_pos = idx.index("120 large petroleum tanks in South Portland")
    map_pos = idx.index('<div class="map-frame">')
    note_pos = idx.index("Use the slider inside the map")
    assert kicker_pos < h2_pos < figure_pos < img_pos < caption_pos < prose_pos
    assert prose_pos < map_pos < iframe_pos < note_pos, "the map and its note follow the prose"
    # the slider note belongs to the map: the prose must not sit between them
    assert "120 large petroleum tanks" not in idx[map_pos:note_pos]
    assert idx[map_pos:note_pos].count('class="map-note"') == 1
    assert idx.index("</figure>", figure_pos) > caption_pos, "the caption stays inside the figure"
    # the whole block stays inside the section, above the call to act
    assert iframe_pos < idx.index("Now is the time to act")


def test_row7_map_swap_stays_silent(docs):
    """Operator directive 2026-10-14: the 'Final public map graphic: in
    design' notice is killed. The interactive embed is the shipping feature;
    when Nate's final graphic lands it slots in silently via the row-7
    staged swap, so no page announces a future graphic."""
    for name in ("index.html", "tank-farms.html"):
        page = read(docs, name)
        assert "Final public map graphic" not in page, name
        assert "in design" not in page, name
        assert "once design work wraps" not in page, name
        assert "map-placeholder" not in page, name


def test_row6_hero_replaced_and_act_now_landing(docs):
    idx = read(docs, "index.html")
    assert "Now is the time to act" in idx
    assert 'href="act-now.html"' in idx
    all_html = "\n".join(read(docs, n) for n in html_files(docs))
    assert "Make a difference" not in all_html
    act = read(docs, "act-now.html")
    assert "https://southportland.gov/411/City-Council" in act
    assert "require better technology at the tank farms" in act
    assert "make public what special counsel advises" in act
    assert "legal opinion the city is waiting on" not in act


def test_row33_oct15_meeting_copy_published(docs):
    """Ledger row 33 (2026-10-15) put this meeting in the record, and the
    operator directed the past-tense conversion on 2026-11-05 (the meeting had
    happened). The pin now runs the other way, by operator order: the copy
    document's own margin note on the bullet said "remove this after 10/15",
    and the operator ordered the stale blocks removed from the act block on
    2026-11-24 (ledger row 84). So the bullet must NOT ship, in either the
    past-tense or the invitation form, and neither may the event-only flyer
    link; the flyer file itself stays archived in the built tree."""
    idx = read(docs, "index.html")
    # 2026-11-24: the copy pin reads the tag-stripped text, because the bold
    # pass moved emphasis inside this bullet; what row 33 ruled on is the
    # sentence, not where the <strong> sits.
    idx_text = reading_text(idx)
    bullet = ("Neighbors met on Thursday, Oct. 15 for a community meeting to "
              "share ideas, concerns, and stories: 5:30 p.m. food and "
              "community; 6-7 p.m. discussion, at First Congregational Church "
              "UCC, 301 Cottage Road. Kids were welcome.")
    assert bullet not in idx_text, "the Oct. 15 meeting bullet is retired (row 84)"
    assert "Join neighbors on Thursday, Oct. 15" not in idx, "the invitation form is retired"
    assert 'href="assets/files/tank-talk-flyer.pdf"' not in idx, "the event-only flyer link is dropped"
    flyer = os.path.join(ROOT, "docs", "assets", "files", "tank-talk-flyer.pdf")
    assert os.path.exists(flyer), "the Tank Talk flyer stays archived in the built tree"
    # the surviving bullets keep their order: the forward campaign line leads
    # the callout and the Dec. 1 workshop follows it (row 121)
    callout_pos = idx_text.index("Now is the time to act")
    assert idx_text.index("The Council is weighing what to require at the tank farms", callout_pos) < \
        idx_text.index("The Council plans its next workshop for", callout_pos)
    # the scan ban is retired: no event markers remain to reject it
    assert tuple(FORBIDDEN_EVENT_MARKERS) == ()


def test_no_draft_language_anywhere(docs):
    """Release-gate rule 4: internal-draft language never reaches the surface."""
    patterns = ("as now written", "most recent draft", "TODO", "FIXME", "[Placeholder")
    for name in html_files(docs):
        page = read(docs, name)
        for p in patterns:
            assert p not in page, f"{name}: draft language leaked: {p}"


# ---- retired claims: phrases the site may never publish again --------------
#
# One entry per retired claim: the phrase, matched case-insensitively against
# every built page, and why it was retired. Adding the next retirement is one
# dict entry here; the guard below reads the whole map, so no new test is
# needed when another claim is retired.
RETIRED_CLAIMS = {
    "state standards": (
        "2026-11-23: Maine publishes ambient air guidelines, not standards, so "
        "the campaign retired the 'exceeded state standards' framing"),
    "12 times": (
        "2026-11-23: the single '12 times higher' reading went with the "
        "standards framing; the benchmark is four and a half times the "
        "guideline"),
}


def test_no_retired_benzene_claim(docs):
    """No built page may carry a retired claim; the first entries are the
    benzene restatement retired on 2026-11-23.

    That day a single-file `git checkout --` reverted the homepage rewrite of
    the benzene numbers along with an unrelated pinned bullet. The commit that
    followed shipped three corrected pages and one wrong one, and nothing
    noticed for a day, because the release gate checks content hashes and prose
    quality and never a list of claims the campaign has retired.

    This test is that list. Every page under docs/ is scanned for each phrase
    in RETIRED_CLAIMS, matched case-insensitively, and a hit fails loudly with
    the page, the phrase and the text around it.
    """
    for phrase, reason in RETIRED_CLAIMS.items():
        needle = phrase.lower()
        for name in html_files(docs):
            page = read(docs, name)
            at = page.lower().find(needle)
            if at == -1:
                continue
            context = " ".join(page[max(0, at - 80):at + len(phrase) + 80].split())
            raise AssertionError(
                f"{name}: retired claim {phrase!r} is still published "
                f"({reason}); context: ...{context}...")


def test_row1_no_private_links_anywhere(docs):
    all_html = "\n".join(read(docs, n) for n in html_files(docs))
    for marker in PRIVATE_MARKERS:
        assert marker not in all_html, marker


def test_no_draft_artifacts_anywhere(docs):
    """Release gate rule 4 (AGENTS.md, 2026-10-13): internal working-draft
    language never reaches the public surface. Known live artifact:
    `THE #1 GOAL AS NOW WRITTEN IN THE MOST RECENT DRAFT:` (past-work.html)."""
    violations = []
    for name in html_files(docs):
        violations.extend(psp_public.scan_text(read(docs, name), name, FORBIDDEN_DRAFT_MARKERS))
    assert not violations, "\n" + "\n".join(violations)


@pytest.mark.skipif(
    psp_public.find_map_source_docs() is None,
    reason="standalone map pages not available (no tank-farms checkout)")
def test_map_pages_published_chrome_free(docs):
    """The site build ships the standalone map pages under map/ (published by
    tools/publish.py as the mirror's map subtree, and committed so CI can
    serve the relative iframe). Research chrome must be gone from map.html;
    every map file must be marker-clean."""
    map_dir = os.path.join(docs, "map")
    for name in psp_public.MAP_FILES:
        assert os.path.exists(os.path.join(map_dir, name)), name
    map_html = read(map_dir, "map.html")
    assert "<nav>" not in map_html
    violations = []
    for name in psp_public.MAP_FILES:
        violations.extend(psp_public.scan_file(os.path.join(map_dir, name), f"map/{name}"))
    assert not violations, "\n" + "\n".join(violations)


def test_no_wix_assets_copied(docs):
    """Images from the live site are served locally; never hotlink wixstatic."""
    all_html = "\n".join(read(docs, n) for n in html_files(docs))
    assert "static.wixstatic.com" not in all_html


def test_images_resolve_and_have_alt(docs):
    img_re = re.compile(r"<img\b[^>]*>")
    src_re = re.compile(r'src="([^"]+)"')
    alt_re = re.compile(r'alt="([^"]*)"')
    for name in html_files(docs):
        for tag in img_re.findall(read(docs, name)):
            src_m = src_re.search(tag)
            assert src_m, f"{name}: img without src"
            src = src_m.group(1)
            assert not src.startswith("http"), f"{name}: images must be local, got {src}"
            alt_m = alt_re.search(tag)
            assert alt_m and alt_m.group(1).strip(), f"{name}: img without alt text: {src}"
            assert os.path.exists(os.path.join(docs, src)), f"{name}: missing image file {src}"


def test_favicon_present(docs):
    favicon = os.path.join(docs, "assets", "psp-favicon.png")
    assert os.path.exists(favicon)
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        assert 'href="assets/psp-favicon.png"' in read(docs, name), name


def test_cname_ready_for_domain_flip(docs):
    """docs/CNAME: the apex staging plan is superseded; the file returns at cutover.

    Two decisions, both on the record here. The OLD domain-flip plan (ledger
    row 4 era) staged the apex hostname protectsouthportland.org as a tracked
    docs/CNAME, and this test pinned the file's existence and content. The
    fork model (2026-11-24 migration plan, section 5) supersedes that plan: a
    branch deployment reads the served directory's CNAME file as its custom
    domain, so a tracked file would make Pages claim the apex the moment it
    starts serving main, at a moment nobody chose. The file is untracked and
    gitignored, and the domain is set deliberately at cutover, when docs/CNAME
    returns committed with www.protectsouthportland.org, the live canonical —
    not the apex.

    Pinned in every checkout: the ignore rule covers the path, and the file is
    not in the tracked tree. If the operator's local checkout still carries
    the staged-flip file, it reads the apex unchanged — a local artifact like
    .env until the cutover PR replaces it.
    """
    import subprocess
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "docs/CNAME"],
        cwd=ROOT, capture_output=True)
    assert ignored.returncode == 0, (
        "docs/CNAME must stay covered by the ignore rule: the fork model "
        "sets the domain deliberately at cutover, never via a file that "
        "rides back into the tracked tree by accident")
    tracked = subprocess.run(
        ["git", "ls-files", "docs/CNAME"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert tracked == [], (
        "docs/CNAME tracked: a branch deployment reads it as the custom "
        "domain, so Pages would claim its hostname the instant it serves "
        "main — commit the cutover-time CNAME (www.protectsouthportland.org) "
        "deliberately, in the cutover PR")
    cname = os.path.join(ROOT, "docs", "CNAME")
    if os.path.exists(cname):
        # local staged-flip artifact; a fresh CI checkout does not carry it
        assert open(cname, encoding="utf-8").read().strip() == "protectsouthportland.org", (
            "the staged-flip file still reads the apex; the cutover PR "
            "replaces it with www.protectsouthportland.org")


def test_every_page_shell_complete(docs):
    # masthead boundary (2026-10-15 readability re-measure): the older-visitor
    # root scale (112.5%) enlarged the rem-based nav row past the masthead's
    # 1060px content cap, so nav links settle at 0.9rem (gaps halved to 2px)
    # and the boundary was re-measured (1021px content + 40 padding + 16
    # scrollbar tax + 30 margin = 1107, rounded to 1120) — numbers recorded in styles.css above the
    # boundary. The served stylesheet carries that boundary and no stale
    # query. The de-duped masthead keeps exactly one brand carrier: the seal,
    # whose alt is the accessible brand name.
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    assert "@media (max-width: 1120px)" in css, "masthead MENU boundary"
    assert "@media (max-width: 1080px)" not in css and "@media (max-width: 1200px)" not in css, "stale boundary"
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        page = read(docs, name)
        assert '<html lang="en">' in page, name
        assert "<title>" in page, name
        assert '<meta name="description"' in page, name
        assert 'name="viewport"' in page, name
        assert 'href="styles.css"' in page, name
        assert 'href="donate.html"' in page, name  # footer donate strip
        assert 'class="masthead"' in page, name
        assert 'class="footer"' in page, name
        # page-structure patch (2026-10-14 review, fixes 4 + 6): every page
        # carries one main landmark between the masthead and the footer, a
        # skip link that targets it without the stuck off-screen wrapper,
        # and a keyboard-focusable nav toggle with no aria-hidden.
        assert page.count('<main id="content">') == 1 and page.count("</main>") == 1, name
        assert page.index('class="masthead"') < page.index('<main id="content">') < page.index('class="footer"'), name
        assert '<a class="skip-link" href="#content">Skip to content</a>' in page, name
        assert 'div class="skip-link"' not in page, name
        assert 'id="nav-toggle"' in page and 'aria-hidden="true"' not in page, name
        # de-dupe (2026-10-15): one brand carrier — the seal alone in the
        # masthead with its alt as the accessible brand name; the text
        # wordmark never renders on any page (the footer's seal keeps its
        # own "... logo" alt, untouched by the de-dupe).
        assert '<img src="assets/psp-logo.png" alt="Protect South Portland">' in page, name
        assert 'wordmark' not in page, name


def test_hero_homepage_only(docs):
    """Ledger row 98 (operator, 2026-11-24): the homepage's top-of-page block is
    a photo hero, and it is the homepage's alone.

    Retargeted from `test_banner_homepage_only`, which pinned `class="banner"`
    on the homepage and banned it everywhere else. The ruling did not change,
    only the block's name: the solid teal banner and the decorative
    `hero-band--home` strip under it became one `<section class="hero">`, so
    the pin follows the region. Other pages keep their own `.hero-band` band,
    which is a different component and is pinned separately below.
    """
    for name in html_files(docs):
        page = read(docs, name)
        has_hero = 'class="hero"' in page
        if name == "index.html":
            assert has_hero, "homepage must carry the photo hero"
        else:
            assert not has_hero, f"{name} must not carry the homepage hero"


def test_internal_links_resolve(docs):
    anchor_re = re.compile(r'id="(.*?)"')
    href_re = re.compile(r'href="([^"]*)"')
    ids_by_page = {}
    for name in html_files(docs):
        ids_by_page[name] = set(anchor_re.findall(read(docs, name)))
    for name in html_files(docs):
        for href in href_re.findall(read(docs, name)):
            if href.startswith("mailto:") or href.startswith("#"):
                continue
            if href.startswith("tel:"):
                assert re.fullmatch(r"tel:\+?[0-9]{10,13}", href), (
                    f"{name}: malformed tel link {href}")
                continue
            if href.startswith("http://") or href.startswith("https://"):
                continue
            target, _, frag = href.partition("#")
            path = os.path.join(docs, target)
            assert os.path.exists(path), f"{name}: broken link {href}"
            if frag:
                frag_ids = ids_by_page.get(target) or set(
                    anchor_re.findall(open(path, encoding="utf-8").read()))
                assert frag in frag_ids, f"{name}: missing anchor {href}"


def test_external_links_allowlisted(docs):
    href_re = re.compile(r'href="(https?://[^"]*)"')
    src_re = re.compile(r'src="(https?://[^"]*)"')
    for name in html_files(docs):
        page = read(docs, name)
        for url in href_re.findall(page) + src_re.findall(page):
            host = re.match(r"https?://([^/?#]*)", url).group(1).lower()
            host = host.removeprefix("www.")
            assert any(host == a or host.endswith("." + a) for a in EXTERNAL_ALLOWLIST), (
                f"{name}: external link not allowlisted: {url}"
            )

def test_donate_page_has_one_paypal_path(docs):
    """Ledger row 25 (live-site parity): donate.html restores the live site's
    PayPal giving path — exactly one PayPal donate link, aimed at PSP's own
    account, opening safely in a new tab. The UAT suite's
    donate-page-has-mechanism expectation now meets its external_link branch;
    the suite file itself was not edited."""
    page = read(docs, "donate.html")
    tags = re.findall(r"<a\s[^>]*paypal\.com[^>]*>", page)
    assert len(tags) == 1, (
        f"donate.html: expected exactly one PayPal link, got {len(tags)}")
    tag = tags[0]
    assert 'target="_blank"' in tag, tag
    assert 'rel="noopener"' in tag, tag
    href = html.unescape(re.search(r'href="([^"]*)"', tag).group(1))
    assert href.startswith("https://www.paypal.com/donate"), href
    assert "business=protectsouthportland%40gmail.com" in href, href
    assert "currency_code=USD" in href, href


def test_sprague_complaint_asset_mirrored(docs):
    """RED-1 (wix-vs-staging-comparison.md): the DOJ complaint document the
    live Wix /global page links ("Read the complaint>>") is mirrored into
    site/assets/files/ and anchored from the Sprague paragraph, which moved
    to tank-farms-history.html in the Nov. 2026 cut, so it survives Wix going dark."""
    tf = read(docs, "tank-farms.html")
    assert "Read the complaint (PDF)" in tf, "anchor text missing"
    hrefs = re.findall(r'href="(assets/files/[^"]*\.pdf)"', tf)
    sprague = [h for h in hrefs if "sprague-doj-complaint" in h]
    assert len(sprague) == 1, f"expected one Sprague complaint link, got {sprague}"
    asset = os.path.join(docs, sprague[0])
    assert os.path.exists(asset), "mirrored Sprague complaint is not reachable"
    with open(asset, "rb") as f:
        assert f.read(5) == b"%PDF-", "mirrored Sprague asset is not a PDF"
    assert tf.index("notice of violation from the EPA on May 29, 2020") < tf.index("Read the complaint (PDF)")


def test_about_links_the_award_video(docs):
    """RED-2 (wix-vs-staging-comparison.md): the Local Hero award video has a
    live public Dropbox copy; about.html links it instead of promising a
    future copy. Operator addendum 2026-10-14: the interim parenthetical is
    stripped too - shipped pages carry the link, not construction notes."""
    page = read(docs, "about.html")
    assert "when a public copy is available" not in page, "false pending claim still present"
    assert 'href="https://www.dropbox.com/s/6kizeqdtod6fr52/ME%20-%20Final.mp4?dl=0"' in page, "Dropbox copy link missing"
    assert "Watch the award video" in page, "video link anchor text missing"
    assert "(temporary link" not in page, "interim parenthetical must be gone"


def test_pages_carry_no_coming_soon_promises(docs):
    """Ledger rows 28/29 (operator addendum): shipped pages do not narrate
    coming mechanics. The subscribe-by-email and email-contact instructions
    ARE the mechanism; the 'coming soon' promises go, sentence-delete only."""
    for name in ("contact.html", "newsletter.html"):
        page = read(docs, name)
        assert "coming soon" not in page, name


def test_homepage_who_we_are_block(docs):
    """Ledger row 27 (Mindy-sanctioned homepage about-block from Alex's
    homepage pass): the mission line and the About-PSP paragraph sit verbatim
    on the homepage — the mission folds into the hero's card as its sign-off
    and the About paragraph sits in a compact strip under the hero photo and
    above the issue section (2026-10-14 single-hero design pass, carried into
    the 2026-11-24 photo hero unchanged), with the Read
    more link (labelled "Our Story" by row 27, relabelled "Our Work" by the
    operator by hand on 2026-11-24) linking about.html
    and an Act now link to act-now.html (the doc's action
    section renamed page on 2026-11-24) — after
    the 2026-10-14 design round 2 both read as list items in a two-item link
    row (page-structure patch): prose, not buttons; the hero's Act now is the
    only button idiom in the first screen. The
    docx parentheticals are author instructions and must not ship; the
    working-note strings and the fact-flagged grammar quirks stay exactly as
    written (tone check)."""
    idx = read(docs, "index.html")
    assert "We are a community-based, volunteer-run organization working together to protect the environment and the health and well-being of South Portland residents." in idx
    assert "For over a decade, we" in idx
    assert "South Portland&rsquo;s precedent-setting Clear Skies Ordinance" in idx
    assert "a ban on synthetic pesticide" in idx, "grammar quirk must stay verbatim"
    assert "tar sands oils" in idx, "grammar quirk must stay verbatim"
    assert "Read more: Our Work" in idx
    # 2026-11-24: the operator rewrote this label by hand from "Read more:
    # Our Story" to "Read more: Our Work" while capturing their manual edit
    # (ledger row 89). The target did not move, so the pin moves to their
    # words and the destination guard below is untouched. Same move the lane
    # made for row 33's Oct. 15 pin, row 86's brace pin and row 82's button
    # pin: a pin that encodes a sentence the operator has replaced follows
    # their sentence, and the guard the pin exists for stays.
    assert 'href="about.html"' in idx, "the Read more link must reach about.html"
    # 2026-11-24 page-set revision: the doc renamed its action section Act Now,
    # so the link row names the destination the site now has.
    assert "Act now" in idx
    assert 'href="act-now.html"' in idx, "the action link must reach act-now.html"
    # design round 2 + page-structure patch: exactly one button idiom in the
    # first screen — the hero's Act now — and the strip's links read as a
    # two-item link row after the paragraph (labels and hrefs char-for-char;
    # the paragraph ends at its own period), not a run-on, not stacked buttons.
    # Retargeted 2026-11-24 (ledger row 98): the slice starts at the hero
    # region instead of the retired `.banner` block, and the count is still
    # one, because the card's CTA is the only button above the campaign.
    idx_top = idx[idx.index('<section class="hero">'):idx.index('<span class="kicker">Current campaign</span>')]
    assert idx_top.count('class="btn') == 1, "only the hero's Act now is a button in the top flow"
    assert "intro-cta" not in idx and "btn--ghost" not in idx_top
    assert "meaningful actions.</p>" in idx and "Our Story</a> <a" not in idx, "strip ends at its own period"
    row_pos = idx.index('<ul class="link-row">')
    row = idx[row_pos:idx.index("</ul>", row_pos)]
    assert row.count('<li><a href="about.html">Read more: Our Work</a></li>') == 1
    assert row.count('<li><a href="act-now.html">Act now</a></li>') == 1
    # heading order (fix 3): the hero headline is the page's single h1
    assert idx.count("<h1") == 1 and '<h1 class="hero__headline">' in idx
    assert '<p class="hero__headline">' not in idx
    # final top-of-page order: hero region (its card holds the h1, the ask and
    # the CTA, with the mission folded in as its sign-off) -> who-we-are strip
    # -> link row (inside the strip, after the paragraph) -> issue section
    hero_pos = idx.index('<section class="hero">')
    card_pos = idx.index('class="hero__card"')
    headline_pos = idx.index('<h1 class="hero__headline">')
    cta_pos = idx.index('class="btn btn--cta"')
    mission_pos = idx.index("We are a community-based")
    strip_pos = idx.index("For over a decade, we")
    issue_pos = idx.index('<span class="kicker">Current campaign</span>')
    assert hero_pos < card_pos < headline_pos < cta_pos < mission_pos < strip_pos
    assert mission_pos < strip_pos < row_pos < issue_pos
    # author working notes are not copy
    for leak in ("Something like this", "Something like that", "link to About Us"):
        assert leak not in idx, leak


def test_homepage_hero_photo_keeps_its_proportions(docs):
    """Operator, 2026-11-24 (ledger row 98), verbatim: "This photo of bug light
    is still too squashed. what about filling the red outline with the photo
    and using a floating card over the photo (with or without transparency,
    you decide) for the text where the semi-opaque red rectangle is?"

    Retargeted from `test_homepage_hero_band_shows_the_shoreline`, which pinned
    the photograph as a CSS background on an empty `role="img"` div. The
    operator's complaint is that the band squashed the frame: a fixed height
    over a 1600x898 photo is a 5.5:1 letterbox at 1440. The picture is now a
    real `<img>` in the hero region, and `object-fit: cover` with a declared
    `object-position` is what keeps its proportions at every width, so the pin
    moves from "a background image exists" to "the element cannot stretch it
    and the focal point is stated". The `role="img"` div, its aria-label and
    the `.hero-band--home` class are all gone with the strip they served.
    """
    idx = read(docs, "index.html")
    m = re.search(
        r'<section class="hero">\s*\n\s*<img class="hero__photo" '
        r'src="([^"]+)" alt="([^"]+)"', idx)
    assert m, (
        'the homepage hero opens with a real <img class="hero__photo"> carrying '
        'src and alt, not an empty role="img" div')
    src, alt = m.group(1), m.group(2)
    assert src == "assets/photos/hero-coast.jpg", (
        "the hero keeps the Bug Light frame the operator named")
    assert os.path.isfile(os.path.join(docs, src)), \
        "hero-coast.jpg must exist in the built tree"
    assert 'role="img"' not in idx, (
        "the hero is a real region with an h1, not a decorative image with an "
        "aria-label standing in for content")
    assert ".hero-band" not in idx, (
        "the homepage no longer carries a decorative band; the photo is the hero")
    assert "tank" not in alt.lower(), "the hero no longer describes tanks"
    for landmark in ("Bug Light", "schooner"):
        assert landmark in alt, f"the alt names the {landmark} the photo shows"
    assert len(alt.split()) >= 8, "the alt stays a real sentence, not a file name"

    css = read(docs, "styles.css")
    rule = re.search(r"\.hero__photo\s*\{([^}]*)\}", css)
    assert rule, "the photo's fit and focus are declared on .hero__photo"
    body = rule.group(1)
    assert "object-fit: cover" in body, (
        "cover is what keeps the frame's proportions at every width; anything "
        "else stretches the photograph")
    assert "object-position" in body, "the focal point must be stated, not default"
    assert "height: 100%" in body and "width: 100%" in body, (
        "the photograph fills the hero region in both axes")


def test_homepage_hero_band_dead_code_is_gone_and_other_bands_are_intact(docs):
    """Ledger row 98: the homepage-only band classes went with the strip they
    styled, and the shared band the other pages use did not move.

    `.hero-band--home` and `.hero-band--low` were the homepage's alone; after
    the photo hero replaced the strip nothing renders either class, so leaving
    them in the stylesheet would be dead code that the next reader has to
    reverse-engineer. `.hero-band` itself is a different component with three
    live users, and this pin walks the built tree for them instead of naming
    pages, so a page that adopts or drops a band updates the pin by building.
    """
    css = read(docs, "styles.css")
    assert not re.search(r"\.hero-band--home\s*\{", css), (
        ".hero-band--home has no user left; the hero owns its own photograph")
    assert not re.search(r"\.hero-band--low\s*\{", css), (
        ".hero-band--low has no user left either")
    # the comment above the shared rule may name the retired members (that is
    # how the next reader learns why they are gone); no page may still wear one
    for name in html_files(docs):
        page = read(docs, name)
        assert "hero-band--home" not in page, f"{name} still wears hero-band--home"
        assert "hero-band--low" not in page, f"{name} still wears hero-band--low"
    assert re.search(r"\.hero-band\s*\{[^}]*min-height", css), (
        "the shared .hero-band rule still has to exist for the other pages")
    users = [name for name in html_files(docs)
             if name != "index.html" and 'class="hero-band"' in read(docs, name)]
    assert users, "no page renders a .hero-band any more; the shared rule is dead"
    for name in users:
        assert 'role="img"' in read(docs, name), (
            f"{name}: the decorative band keeps its role and label")


def test_embed_url_is_the_public_embedding(docs):
    """The map is self-hosted: both mapping pages iframe map/embed.html from
    this same published tree — no absolute cristoslc.github.io source."""
    for name in ("index.html", "tank-farms.html"):
        assert 'src="map/embed.html"' in read(docs, name), name


def test_homepage_top_is_forward_looking(docs):
    """Recorded correction (2026-11-24), the operator's ruling verbatim on
    staging-feedback #3: "specifically, I meant that we should be
    forward-looking, not referencing the Oct 27 meeting. Don't repeat homepage
    text that's not directly relevant to that goal." The vote is history; the
    page stops narrating October: the sweep below pins the count of "Oct. 27"
    and no-vote wording to zero across the whole homepage (the top section and
    the callout carried the only mentions), and the venue address stays gone
    with the invitation (operator ruling, 2026-11-05). The history survives in
    the ledger (row 121) and this docstring, not on the page."""
    idx = read(docs, "index.html")
    assert "Oct. 27" not in idx
    assert "took no vote" not in idx
    assert "The Council is weighing what to require at the tank farms" in idx
    assert "637 Highland Ave" not in idx


# ---- content-gap rewrite (Oct 13, 2026): homepage cut-down, archive page, ----
# ---- dated footer strip, dead-link sweep                                      ----

DATED_PHRASE = "Next: City Council workshop - Tuesday, Oct. 27, 6 p.m., South Portland High School."
# Ruling A (2026-11-05): the fallback call to action that replaces it in the
# shared footer strip on every page.
ACTION_PHRASE = "Report every odor."
# Recorded correction (2026-11-25, ledger row 125), the operator's directive
# verbatim: 'remove "sign the petition" language, petition was already
# delivered' — the petition sentence left the shared footer strip; the odor
# sentence is the fallback call to action that remains.
# the internal DATED marker lives only in tools/build.py as a Python comment;
# the served HTML must never carry it (release-gate rule 4, reviewer R1)
DATED_COMMENT = "DATED: remove after 2026-10-27 workshop"

PETITION_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSfPIeWgfe7GGgNqhxVatcPAEffmqo5jJJ-iGYcCh4ltcQsZcA/viewform"
)
# Recorded correction (2026-11-25, ledger row 125): the petition was delivered,
# so the form URL is no longer offered from any page; the pins below assert its
# ABSENCE where they once asserted its presence.

MIRRORED_PDFS = (
    "hem3-report-summary.pdf",
    "newsletter-2021-01-13.pdf",
    "newsletter-2020-12-13.pdf",
    "fertilizer-ordinance-2020.pdf",
    "maine-dep-report-ld1915.pdf",
    "psp-submission-enr.pdf",
    "falatko-comments.pdf",
    "mikulka-comments.pdf",
    "pesticide-ordinance-ch32.pdf",
    "pesticide-ordinance-faqs.pdf",
    "clear-skies-ordinance-2014.pdf",
)


def test_homepage_cut_down(docs):
    idx = read(docs, "index.html")
    assert "Comprehensive Plan for South Portland is mandated" not in idx
    assert "Yard South development" not in idx
    assert PETITION_URL not in idx
    # the pinned surface survives untouched
    assert BANNER_TEXT in idx and 'id="tank-farms"' in idx


def test_past_work_archives_and_nav_exclusion(docs):
    pw = read(docs, "past-work.html")
    assert pw.count("Historical campaign") >= 2
    assert "Comprehensive Plan advocacy, 2024" in pw
    assert "Yard South proposal, 2023&ndash;2024" in pw
    assert 'href="yard-south-proposal.html"' in pw
    assert "Comprehensive Plan for South Portland is mandated" in pw
    # promoted into the header nav by the pre-workshop restructure (was footer-only)
    page = read(docs, "contact.html")
    m = re.search(r'<nav class="main-nav".*?</nav>', page, re.S)
    assert m and 'href="past-work.html"' in m.group(0)
    # footer carries the archive link
    assert 'href="past-work.html"' in page


def test_act_now_in_header_nav(docs):
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        m = re.search(r'<nav class="main-nav".*?</nav>', read(docs, name), re.S)
        assert m and 'href="act-now.html"' in m.group(0), name


def test_action_strip_every_page(docs):
    # Ruling A (2026-11-05): the dated workshop strip is retired. The footer
    # strip now carries the fallback call to action, linked to the page that
    # branches into the odor paths. Since the 2026-11-24 page-set revision that
    # page is act-now.html. Recorded correction (2026-11-25, ledger row 125),
    # the operator's directive verbatim: 'remove "sign the petition" language,
    # petition was already delivered' — the petition sentence left the strip
    # and the strip's target still branches into the odor path.
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        page = read(docs, name)
        assert DATED_PHRASE not in page, f"{name}: the retired Oct. 27 strip is still present"
        assert ACTION_PHRASE in page, name
        assert "Sign the petition" not in page, (
            f"{name}: the delivered petition's sign language is retired (row 125)")
        assert DATED_COMMENT not in page, f"{name}: internal DATED comment leaked into served HTML"
        assert 'class="action-strip"' in page, name
        assert re.search(
            r'<a href="act-now\.html">Report every odor\.</a>',
            page), name
    # and the target really is the branch page: the way to report an odor
    # lives there, and the petition form is offered nowhere
    act = read(docs, "act-now.html")
    assert PETITION_URL not in act, "the delivered petition's form is retired (row 125)"
    assert 'href="report-an-odor.html"' in act, "the strip promises the odor path"


def test_no_public_todo_strings(docs):
    for name in html_files(docs):
        assert "TODO" not in read(docs, name), name


def test_act_now_current_ask_and_relocation(docs):
    """The current ask, the petition and the letter-to-the-editor guidance moved
    here from get-involved.html on 2026-11-24, when the copy document renamed
    its action section Act Now and gave the odor section its own page."""
    act = read(docs, "act-now.html")
    # recorded correction (2026-11-24, row 121), the operator's ruling verbatim:
    # "specifically, I meant that we should be forward-looking, not referencing
    # the Oct 27 meeting. Don't repeat homepage text that's not directly
    # relevant to that goal." Retargeted from asserting the Oct. 27 retelling
    # to asserting the forward ask it became. Retargeted again 2026-11-25
    # (row 130): the operator's target lead with its mandated corrections -
    # "The City Council is considering what - if any - action to take with
    # the tank farms" (grammar: "is considering"; typography: the page's own
    # spaced em-dash entity convention)
    assert "The City Council is considering what" in act
    assert "Oct. 27" not in act
    # recorded correction (2026-11-25, ledger row 125), the operator's directive
    # verbatim: 'remove "sign the petition" language, petition was already
    # delivered' — the delivered petition's form is offered nowhere on the page
    assert PETITION_URL not in act
    assert "Sign the petition" not in act
    # 2026-11-24 (ledger row 113): the operator ruled "we should provide the
    # emails for all of these, like `see the Sentry's website for the
    # submissions address`", so the letter-to-the-editor block carries the
    # submission addresses directly instead of the contact-page hop this pin
    # used to assert. The retarget pins the direct addresses the newsrooms'
    # own pages name (see the row-113 PR for each citation): the shared
    # Maine Trust for Local News letters desk for the Sentry and the
    # Forecaster, the Press Herald's own letters address, and the submission
    # form all three route to.
    assert "letters@metln.org" in act
    assert "letterstotheeditor@pressherald.com" in act
    assert "https://www.pressherald.com/reader-services/letters-editor/" in act
    # the addition to the same ruling: the letters block links the campaign's
    # own how-to-write-a-letter guidance, which lives on the toolkit page
    # (from the 2026 South Portland Tanks Toolkit in the campaign Drive; the
    # Drive listing carries no dedicated LTTE guide)
    assert 'How to write a letter: the toolkit&rsquo;s <a href="toolkit.html#letter-to-the-editor">letter-to-the-editor guidance</a>.' in act
    assert 'id="letter-to-the-editor"' in read(docs, "toolkit.html"), (
        "the letters block's how-to link must land on a real anchor")
    # the indirection the operator ruled against never returns
    assert "submissions address" not in act
    # the non-indirection facts stay
    assert "350 words" in act and "300 words" in act
    assert "The deadline is Monday at noon" in act


def test_act_now_workshop_is_past_tense(docs):
    # Retargeted 2026-11-24 (ledger row 121) as a recorded correction: the
    # operator ruled "specifically, I meant that we should be forward-looking,
    # not referencing the Oct 27 meeting. Don't repeat homepage text that's not
    # directly relevant to that goal." The Oct. 27 retelling left the page; the
    # two spots that carried it now lead forward, so the pin follows the
    # forward opener into both. The high-school address that served only the
    # past night stays gone, as does every invitation to a past event.
    act = read(docs, "act-now.html")
    # ledger row 125: the count is 2 — the Current ask and the forward
    # workshop card that replaced the petition card both open with the same
    # forward sentence, deliberately the same words
    # recorded corrections: the operator's row-129 redundancy ruling removed
    # the card that repeated the forward sentence, and the row-130 lead
    # rewrite then replaced the lead itself with the City-Council wording, so
    # the "council is weighing" phrasing no longer appears on act-now at all
    # (the about page keeps its own copy, pinned by the about-page test)
    assert act.count("The council is weighing what to require at the tank farms") == 0
    assert "Dec. 1: the council weighs what to require" not in act
    assert "WORKSHOP DETAILS" not in act
    assert "The council&rsquo;s next workshop is" in act
    assert "Make plans to come to the City Council workshop" not in act
    assert "Attend the City Council workshop" not in act
    assert "637 Highland Ave" not in act


class _BlockquoteText(HTMLParser):
    """Visible text of the first <blockquote> on a built page.

    Deliberately independent of tools/build.py's converter: this walks the
    markup with html.parser, the build walks it with regexes, and the two
    readings are compared. If both sides shared one helper the pin would be
    comparing the converter to itself.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.in_p = 0
        self.paras = []
        self.buf = []
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag == "blockquote":
            self.depth += 1
        elif self.depth and tag == "p":
            self.in_p += 1
            self.buf = []
        elif self.depth and self.in_p and tag == "br":
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if self.done:
            return
        if tag == "blockquote" and self.depth:
            self.depth -= 1
            self.done = True
        elif self.depth and tag == "p" and self.in_p:
            self.in_p -= 1
            self.paras.append("".join(self.buf).strip())

    def handle_data(self, data):
        if self.depth and self.in_p and not self.done:
            self.buf.append(data)

    def text(self):
        return "\n\n".join(self.paras)


def _act_now_cta_href(page):
    """The mailto href on Act now's orange Email the Council button."""
    m = re.search(
        r'<a [^>]*class="btn btn--cta"[^>]*href="(?P<href>mailto:[^"]+)"', page)
    assert m, "act-now.html no longer carries the Email the Council CTA"
    return html.unescape(m.group("href"))


def _mailto_param(href, name):
    """Raw (still percent-encoded) value of one parameter of a mailto href.

    Split by hand rather than through urllib.parse.parse_qs, which turns "+"
    into a space; the body must compare byte for byte after a plain unquote.
    """
    query = href.split("?", 1)[1] if "?" in href else ""
    for part in query.split("&"):
        key, _, value = part.partition("=")
        if key == name:
            return value
    return None


def test_act_now_cta_body_decodes_to_the_blockquote(docs):
    """The CTA's mailto body decodes back to exactly the blockquote text.

    Ledger row 96, second operator instruction on 2026-11-24, verbatim: "can
    we put the example message in the mailto body for the button?". One source
    of truth: tools/build.py composes the body from the page's blockquote at
    build time, so an edit to the letter cannot drift from the button. This
    pin reads the rendered blockquote and the rendered href separately and
    requires them to be the same letter, greeting and sign-off included.
    """
    page = read(docs, "act-now.html")
    assert page.count("<blockquote>") == 1, "act-now.html should carry one letter"

    body = _mailto_param(_act_now_cta_href(page), "body")
    assert body is not None, "the CTA href carries no body parameter"
    decoded = urllib.parse.unquote(body)

    parser = _BlockquoteText()
    parser.feed(page)
    visible = parser.text()

    assert visible.startswith("Dear Councilors,"), visible[:60]
    assert visible.endswith("[Your name and street or neighborhood]"), visible[-60:]
    assert decoded == visible
    assert "\n\n" in decoded, "paragraphs must join with a blank line"
    assert "\r" not in decoded


def test_act_now_cta_body_is_populated_in_the_html(docs):
    """The populated draft ships in the markup, so it works with scripting off.

    Same ruling as the test above. The site's no-JS path rule means the href a
    reader's browser receives must already carry the message; nothing may fill
    it in at runtime, and the build's own marker must not survive into the
    shipped page.
    """
    page = read(docs, "act-now.html")
    href = _act_now_cta_href(page)

    assert "body=" in href, "the shipped CTA href has no body parameter"
    body = _mailto_param(href, "body")
    assert body, "the body parameter is present but empty"
    # The letter is 632 decoded characters and encodes to 892, so a populated
    # body is far past this floor; an empty or truncated one is not.
    assert len(body) > 600, f"body is only {len(body)} encoded characters"
    assert "data-mailto-body" not in page, "the build marker must not ship"
    assert "Dear%20Councilors%2C" in href, "the greeting is not in the shipped href"


def test_mailto_body_refusal_names_the_page(tmp_path, monkeypatch):
    """Every mailto-body refusal says which page failed, not only what failed.

    Full-class review of PR #78, finding verbatim: "All four refusals exist,
    raise ValueError, and abort the build, but none of the mailto error
    messages names the page, unlike the build loop's own meta-line error that
    does; a failed 20+ page build yields a traceback with no page name."

    The condition here is a marked anchor with no blockquote to fill from; on a
    20+ page build the page carrying it is the one thing the traceback has to
    name for the failure to be actionable. The message must keep saying what
    was wrong as well, so the page name is added, not swapped in.
    """
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "broken-page.html").write_text(
        '<!-- meta: title="Broken" | desc="A synthetic page for the refusal." -->\n'
        '<main>\n'
        '<a class="btn btn--cta" href="mailto:council@example.gov" '
        'data-mailto-body="blockquote">Email the Council</a>\n'
        '</main>\n',
        encoding="utf-8")
    monkeypatch.setattr(build, "PAGES", str(pages))

    with pytest.raises(ValueError) as refused:
        build.build(str(tmp_path / "out"))

    message = str(refused.value)
    assert "broken-page.html" in message, message
    assert "blockquote" in message, message


def test_report_an_odor_page_dual_channel(docs):
    """Row 45: the city's Odor Report form joins the SMC app as the dual
    reporting channel; the two dictated paragraphs sit directly under the
    SMC download paragraph inside the same section.

    2026-11-24: the section became page report-an-odor.html (the copy
    document's Report an Odor child), moved byte-for-byte. Every assertion
    below is the one get-involved.html carried, copied unchanged; only the
    closing boundary moved, because the section that used to follow on that
    page now lives on act-now.html."""
    gi = read(docs, "report-an-odor.html")
    assert "https://www.southportland.gov/FormCenter/Air-Quality-9/City-of-South-Portland-Odor-Report-Form-60" in gi
    assert ">Odor Report form</a>" in gi
    assert "Smell My City App" in gi
    assert "preferred method" in gi
    assert "not publicly available in real-time" in gi
    smc = gi.index("Download the Smell My City app")
    form = gi.index("Odor Report form")
    next_section = gi.index("File the report form")
    assert smc < form < next_section, "form paragraphs must land under the SMC copy"


def test_row48_odor_report_visual_hierarchy(docs):
    """Row 48: the reporting block reads as two peer actions. Both mechanisms
    are present and linked, and the four row-45 dictated sentences survive
    byte-exact — the pin asserts the sentences themselves, so any rewording
    (or a split/merge that drops a word) fails loudly here."""
    gi = read(docs, "report-an-odor.html")

    # both mechanisms present and linked
    assert 'href="https://smellmycity.org/"' in gi
    assert 'href="https://www.southportland.gov/FormCenter/Air-Quality-9/City-of-South-Portland-Odor-Report-Form-60"' in gi

    # the two row-45 sentences, asserted byte-exact
    smc_sentence = (
        "In addition to using the Smell My City App which displays results "
        "publicly and in real-time, please also fill out the city&rsquo;s "
        '<a href="https://www.southportland.gov/FormCenter/Air-Quality-9/'
        'City-of-South-Portland-Odor-Report-Form-60">Odor Report form</a>.')
    assert smc_sentence in gi, "the dictated bridge sentence must survive byte-exact"
    preferred_sentence = (
        "This is the city&rsquo;s preferred method for you to tell them about "
        "each time you smell something bad. However, the log of odor reports "
        "are not publicly available in real-time.")
    assert preferred_sentence in gi, "the dictated preferred-method sentence must survive byte-exact"

    # the two mechanisms read as sibling actions: their buttons sit in one
    # shared row, and document order keeps the app before the form
    assert gi.count("report-actions") >= 1
    smc_btn = gi.index("smellmycity.org/")
    form_btn = gi.index("City-of-South-Portland-Odor-Report-Form-60")
    assert smc_btn < form_btn, "the app action must precede the form action"


ROW47_COUNCILORS = (
    # (name, seat label as published, mail alias, in the prefilled cc list?)
    ("Carter Scott", "District 1", "cscott", True),
    # District 2 (operator ruling, 2026-11-21): Rachael Coleman is the
    # councilor — the current council casts December's pre-inauguration
    # votes, so the roster and the prefilled mailto reach her. Ellen Clancy
    # takes the seat at the Dec. 7 inauguration; she is named in the roster
    # line's transition note WITHOUT an address, because the city has not
    # published one and an invented alias must never ship.
    ("Rachael Coleman", "District 2", "rcoleman", True),
    ("Misha Pride", "District 3", "mpride", True),
    ("Jessica Walker", "District 4", "jwalker", True),
    ("Elyse Tipton", "Mayor &mdash; District 5", "etipton", True),
    ("Richard Matthews", "At-Large", "rmatthews", True),
    ("Natalie West", "At-Large", "nwest", True),
)
# The incoming District 2 councilor: on the page, never with an address
# until the city publishes one (southportland.gov directory or Clerk).
INCOMING_DISTRICT_2 = ("Ellen Clancy", "Dec. 7 inauguration")


def test_row47_city_council_roster(docs):
    """Row 47: the live contact page carries the City's current councilor
    roster (verified against southportland.gov/m/directory), with the general
    address above it, in district order; the retired names and the dead domain
    are gone. past-work.html keeps the historical 2024 list untouched.

    2026-11-24: the roster ran over get-involved.html and act-now.html; with
    get-involved.html retired to a redirect, act-now.html is the one live page
    that carries it, and the pins stay here so the roster keeps a guard."""
    for name in ("act-now.html",):
        page = read(docs, name)
        for person, seat, alias, _ in ROW47_COUNCILORS:
            if seat is None:
                assert person in page, f"{name}: missing {person}"
            else:
                assert f"{person} ({seat})" in page, f"{name}: missing {person} ({seat})"
            assert f'href="mailto:{alias}@southportland.gov"' in page, (
                f"{name}: missing {alias} mailto")
            assert f">{alias}@southportland.gov</a>" in page, (
                f"{name}: missing {alias} visible address")
        assert "citycouncil@southportland.gov" in page, (
            f"{name}: general council address missing")
        # incoming District 2: named, transition-dated, never addressed.
        # The city publishes no Clancy address yet; an alias following the
        # first-initial convention is an inference and must not ship.
        incoming, transition = INCOMING_DISTRICT_2
        assert incoming in page, f"{name}: missing incoming member {incoming}"
        assert transition in page, f"{name}: missing the {transition} note"
        assert "eclancy" not in page, (
            f"{name}: the incoming member carries an unverified address")
        assert "Linda Cohen" not in page, f"{name}: retired name Linda Cohen"
        assert "Steven Riley" not in page, f"{name}: retired name Steven Riley"
        mailtos = re.findall(r'href="(mailto:[^"]+)"', page)
        assert not any(m.lower().endswith("@southportland.org") for m in mailtos), (
            f"{name}: dead-domain mailto survived")
        # district order: walk forward with a cursor so each roster entry
        # matches after the previous one. The preamble names the District-2
        # pair before the list; the cursor skips that, and Coleman's entry
        # must match inside Clancy's roster line, not the preamble.
        cursor = 0
        positions = []
        for p, s_, _, _ in ROW47_COUNCILORS:
            needle = f"{p} ({s_})" if s_ else p
            cursor = page.index(needle, cursor)
            positions.append(cursor)
        assert positions == sorted(positions), f"{name}: roster out of district order"
    # the general address line sits directly above the list
    for name in ("act-now.html",):
        page = read(docs, name)
        expected_line = (
            'We recommend sending your email to the general email address '
            '(<a href="mailto:citycouncil@southportland.gov">citycouncil@southportland.gov</a>), '
            'as well as each councilor individually:')
        assert expected_line in page, (
            f"{name}: the dictated general-address line must ship byte-exact")
        general = page.index("citycouncil@southportland.gov")
        first = page.index("Carter Scott")
        assert general < first, f"{name}: general address must precede the list"



def test_strip_back_to_doc_pages(docs):
    """Operator approval, 2026-11-21: the site strips back to the pages the
    website-copy doc describes. The three agent-built surfaces (Library,
    Press, How-we-got-here) are retired: library and press never existed in
    the doc, and the history split was an agent invention the doc writes as
    one long campaign page. Their URLs redirect so no inbound link breaks.

    The doc's page set is the sanctioned surface list; nothing new may join
    it without operator direction that names the page.
    """
    # the retired URLs are meta-refresh stubs to real destinations
    stubs = {
        "library.html": "tank-farms.html#reference-documents",
        "press.html": "act-now.html",
        "tank-farms-history.html": "tank-farms.html#how-we-got-here",
        # 2026-11-24 page-set revision: the doc has no Get involved page; the
        # action content is Act Now and the odor section is Report an odor
        "get-involved.html": "act-now.html",
    }
    for src, dest in stubs.items():
        stub = read(docs, src)
        assert f"url={dest}" in stub, f"{src} must redirect to {dest}"
        assert 'class="masthead"' not in stub and len(stub) < 800, src
    # the nav offers only the doc's pages: no library, no press
    idx = read(docs, "index.html")
    nav = re.search(r'<nav class="main-nav".*?</nav>', idx, re.S).group(0)
    assert 'href="library.html"' not in nav
    assert 'href="press.html"' not in nav
    footer = idx[idx.index('class="footer'):]
    assert 'href="library.html"' not in footer
    assert 'href="press.html"' not in footer
    # no live page links to a retired URL
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        page = read(docs, name)
        for gone in stubs:
            assert f'href="{gone}"' not in page, f"{name} links retired {gone}"
    # the fold: the history content, the archive note, and the 600-ton
    # verbatim record all live on the campaign page now
    tank = read(docs, "tank-farms.html")
    for heading in ("How we got here: EPA and Global Partners in court",
                    "Selected reading", "EPA action",
                    "Protect South Portland&rsquo;s role",
                    "Clean Air Advisory Committee", "DEP air quality findings",
                    "Resolve LD 1915", "Reference documents", "LD 163",
                    "Rulemaking", "LD 71", "Media coverage"):
        assert heading in tank, f"campaign page missing {heading}"
    # the archive-note ruling survives the fold: one standing note above the
    # record, no inline corrections, superseded figure verbatim and unique
    assert "An archive, not a snapshot." in tank
    assert "Some figures in it are now out of date." in tank
    assert tank.count("An archive, not a snapshot.") == 1
    assert tank.index("An archive, not a snapshot.") < \
        tank.index("How we got here: EPA and Global Partners in court")
    assert "600 tons" in tank
    built = []
    for root, _dirs, files in os.walk(docs):
        for fname in files:
            if fname.endswith(".html"):
                with open(os.path.join(root, fname), encoding="utf-8") as f:
                    built.append(f.read())
    # 2026-11-24 (toolkit reference page): the figure now ships twice, and
    # both counts are named. One is the archived record on the campaign page.
    # The other is the toolkit page's FAQ answer, which is the campaign
    # document's own sentence carried forward, not new agent copy. The pin
    # keeps the figure out of every other page, which is what the press-kit
    # ruling was for.
    #
    # 2026-11-24 (ruling `dec_wousd5kpjj8r`): a figure that ships twice has to
    # say the same thing in both places, and it did not. The document says
    # "approximately 600 tons" on two tabs and "more than 600 tons" on the FAQ
    # tab, so both surfaces now read "approximately 600 tons" and the two
    # disagreeing forms are banned outright.
    assert sum(t.count("600 tons") for t in built) == 2, (
        "the verbatim 600-ton figure survives in exactly two places: the "
        "archived record and the carried toolkit FAQ answer")
    assert tank.count("600 tons") == 1, "the archived record keeps its figure"
    assert read(docs, "toolkit.html").count("600 tons") == 1, (
        "the toolkit FAQ answer keeps the document's figure")
    for name in html_files(docs):
        page = read(docs, name)
        for disagreed in ("more than 600 tons", "almost 600 tons"):
            assert disagreed not in page, (
                f"{name}: the document disagrees with itself on this figure; "
                f"both surfaces read 'approximately 600 tons' ({disagreed!r})")
    assert "approximately 600 tons of volatile organic compounds" in tank
    assert "approximately 600 tons of VOCs" in read(docs, "toolkit.html")
    for name in html_files(docs):
        if name in REDIRECT_PAGES or name in ("tank-farms.html", "toolkit.html"):
            continue
        assert "600 tons" not in read(docs, name), (
            f"{name}: the 600-ton figure belongs to the record and the doc")
    # the press-kit cap ruling survives the retirement, scoped as ruled: the
    # 600-ton VOC / 104-ton HAP cap stays off pages an agent authors. The
    # archived LD 163 paragraph keeps its original figures verbatim (the
    # archive-note ruling), so the ban is on NEW agent copy, not the record.
    # The strongest honest form: the cap figure appears nowhere except
    # inside the archived record section, exactly once.
    tank_body = tank[tank.index("An archive, not a snapshot."):]
    assert tank_body.count("104 tons") == 1, (
        "the cap figure must appear only in the archived record")
    for name in html_files(docs):
        if name in REDIRECT_PAGES or name == "tank-farms.html":
            continue
        assert "104 tons" not in read(docs, name), (
            f"{name}: agent-authored copy carries the cap figure")


def test_about_tense_fixes(docs):
    ab = read(docs, "about.html")
    assert "fifth year" not in ab
    assert "docket" not in ab
    assert "12 coordinators" not in ab
    assert "core group of coordinators" in ab
    # 2026-11-24: "Now in its 13th year" counted from the 2013 founding and had
    # drifted, so the page states the span without a count.
    assert "13th year" not in ab
    assert "More than a decade on" in ab
    assert "What we're doing now" in ab


def test_where_things_stand_section(docs):
    ot = read(docs, "tank-farms.html")
    # 2026-11-20: the state's analysis published, so the heading advances. The
    # section keeps its anchors and its citation links either way.
    assert "Where things stand &mdash; November 2026" in ot
    assert "southportland.gov/522/Air-Quality-Concerns-Monitoring" in ot
    assert "DocumentCenter/View/5116" in ot
    assert "DocumentCenter/View/4819" in ot
    assert "fence-line data" in ot
    # 2026-11-21 strip-back: the history run folded back into the campaign
    # page, so the DEP findings link lives there again
    assert "spo-voc-monitor.html" in ot


def test_wix_pdfs_mirrored_locally(docs):
    all_html = "\n".join(read(docs, n) for n in html_files(docs))
    assert "protectsouthportland.com/_files" not in all_html
    for pdf in MIRRORED_PDFS:
        assert os.path.exists(os.path.join(docs, "assets", "files", pdf)), pdf


def test_no_southportland_org_links(docs):
    for name in html_files(docs):
        page = read(docs, name)
        for url in re.findall(r'href="(https?://[^"]*)"', page):
            host = re.match(r"https?://([^/?#]*)", url).group(1).lower().removeprefix("www.")
            assert host != "southportland.org", f"{name}: dead-domain link {url}"


def test_local_pdfs_resolve(docs):
    href_re = re.compile(r'href="(assets/files/[^"]+)"')
    for name in html_files(docs):
        for href in href_re.findall(read(docs, name)):
            assert os.path.exists(os.path.join(docs, href)), f"{name}: missing {href}"


def test_newsletter_archive_demoted(docs):
    nl = read(docs, "newsletter.html")
    assert "Newsletter archive" in nl
    assert "Most recent newsletter" not in nl


def test_newsletter_signup_component(docs):
    """Ledger row 91, moved to the component by row 115: the subscription is
    a mailto component assembled at build time from one source of truth in
    tools/build.py, and this pin reads its rendered instances rather than any
    page's hand-written copy.

    What it is: a labelled email field and a button in the .btn family that
    hands the visitor's own mail app a message carrying the typed address.
    What it is not: a subscription. Nothing is posted, nothing is stored, and
    no request leaves the browser until the visitor presses send in that app,
    so the component says so in words.

    Four things are pinned rather than assumed: an empty field never opens a
    blank message; a value that does not parse as an email is named as a
    problem instead of vanishing; the typed value is encoded and only ever
    written as text, never parsed as markup; and a reader with scripting off
    still has the plain address, in the prose, outside `<noscript>`.

    Row 115 adds the component contract: the full variant renders on the
    newsletter page exactly as the row-91 block shipped; the reduced variant
    (same structure, no panel) renders at the contact page's ask; the build
    consumes the declaration markers so no page carries two sources; and the
    wiring script appears once per page and drives every `.signup` box on it.
    """
    page = read(docs, "newsletter.html")

    # the field is labelled by a real <label>, not by a placeholder
    assert '<label for="signup-email">Your email address</label>' in page
    assert '<input type="email" id="signup-email"' in page
    assert "placeholder=" not in page, (
        "a placeholder cannot stand in for the label")

    # a button, not a submit control: there is no endpoint to submit to
    assert '<button type="button" class="btn btn--cta" id="signup-open">' in page
    assert 'type="submit"' not in page
    assert "<form" not in page, (
        "no form element: a form's implicit submission would reload the page "
        "and put the typed address in the URL, with no backend to receive it")

    # the mailto and its two agent-composed strings
    assert 'var ADDRESS = "protectsouthportland@gmail.com";' in page
    assert 'var SUBJECT = "Subscribe to the newsletter";' in page
    assert ("Please add this address to the Protect South Portland newsletter"
            in page)
    assert '"mailto:" + ADDRESS' in page

    # encoded, never concatenated raw into the URL, never parsed as markup
    assert "encodeURIComponent(SUBJECT)" in page
    assert "encodeURIComponent(body)" in page
    assert "innerHTML" not in page, "typed input is written as text only"
    assert "status.textContent = message;" in page

    # the empty case is handled, and it is handled before anything is built
    assert "if (!typed) {" in page
    assert page.index("if (!typed) {") < page.index('"mailto:" + ADDRESS')
    assert "if (!field.checkValidity()) {" in page

    # the component says what it does and does not do
    assert "does not subscribe you" in page

    # scripting off: the address is in the prose, not only in <noscript>
    without_noscript = re.sub(r"<noscript>.*?</noscript>", "", page, flags=re.S)
    assert 'href="mailto:protectsouthportland@gmail.com' in without_noscript, (
        "a reader with scripting off needs a plain address outside <noscript>")
    assert "<noscript>" in page, "the button's JS dependency is explained"

    # row 115: the full variant keeps the callout panel it shipped
    assert '<div class="callout signup">' in page
    # the build consumed the declaration marker: one source of truth, no
    # page ships the plumbing
    assert "data-newsletter-signup" not in page

    # the reduced variant at the contact page's ask: same structure, no
    # panel, and the same guarantees. Instance ids are unique per document
    # (one instance on this page takes the base ids; a second instance on
    # the same page would take the variant-suffixed ones).
    contact = read(docs, "contact.html")
    assert '<div class="signup signup--reduced">' in contact
    assert '<label for="signup-email">Your email address</label>' in contact
    assert '<input type="email" id="signup-email"' in contact
    assert '<button type="button" class="btn btn--cta" id="signup-open">' in contact
    assert "does not subscribe you" in contact
    assert "data-newsletter-signup" not in contact
    # one wiring script per page, driving every .signup box on it
    assert contact.count('var ADDRESS = "protectsouthportland@gmail.com";') == 1
    assert "querySelectorAll" in contact
    # scripting off on the contact page too: the plain address outside <noscript>
    c_without_noscript = re.sub(r"<noscript>.*?</noscript>", "", contact, flags=re.S)
    assert 'href="mailto:protectsouthportland@gmail.com' in c_without_noscript


def test_newsletter_signup_css_adds_no_colour():
    """Ledger row 91: the signup is the site's first form control, so its
    block is the one place new visual rules appear. It may declare a border,
    padding, a background, a radius and a focus ring; it may not introduce a
    colour. Every value it uses is an existing token, and the button is the
    .btn family unchanged, so the pill keeps its measured contrast.
    """
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    start = css.index("/* ---------- newsletter signup")
    end = css.index("/* ---------- generic sections")
    block = css[start:end]
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", block) == [], (
        "the signup block introduces a literal colour")
    assert ".signup input {" in block
    assert "border-radius: 8px" in block, "the site's small-control rounding"
    assert "focus-visible" in block, "a keyboard needs to find the field"
    assert "font-size: 1rem" in block, "the input inherits the reading floor"


# ---- publication-safety helpers (tools/psp_public.py): the mirror tree's ----
# ---- scan rules are unit-pinned here so build/publish/enforcement stay   ----
# ---- in one place.                                                       ----

def test_strip_research_chrome_removes_nav_and_sidebar_links():
    sample = (
        '<header class="site"><div class="wrap"><h1>Protect South Portland</h1><nav>'
        '<a href="index.html">Home</a><a href="report.html">Research Report</a>'
        '<a href="https://github.com/cristoslc/south-portland-tank-farms">GitHub'
        "</a></nav></div></header>\n"
        "<p>Closest pairings stand.</p>\n"
        '<p style="margin-top:8px">\n'
        '  <a class="side-link" href="report.html">Research report</a> &middot;\n'
        '  <a class="side-link" href="data.html">Data files</a>\n'
        "</p>\n"
    )
    stripped = psp_public.strip_research_chrome(sample)
    assert "<nav>" not in stripped
    assert 'href="report.html"' not in stripped
    assert "Research report" not in stripped
    assert "Protect South Portland" in stripped  # brand header stays
    assert "Closest pairings stand." in stripped  # non-link copy stays


def test_public_scan_catches_private_strings(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '<a href="https://github.com/cristoslc/south-portland-tank-farms">GitHub</a>',
        encoding="utf-8",
    )
    violations = psp_public.scan_tree(tmp_path)
    assert any("south-portland-tank-farms" in v for v in violations), violations


def test_public_scan_catches_draft_and_path_rails(tmp_path):
    (tmp_path / "past-work.html").write_text(
        "<p>THE #1 GOAL AS NOW WRITTEN IN THE MOST RECENT DRAFT:</p>", encoding="utf-8")
    (tmp_path / "gap-analysis.html").write_text("<p>internal</p>", encoding="utf-8")
    (tmp_path / "meeting-notes.md").write_text("internal", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Public snapshot", encoding="utf-8")
    violations = psp_public.scan_tree(tmp_path)
    assert any("most recent draft" in v for v in violations), violations
    assert any("gap-analysis.html" in v for v in violations), violations
    assert any("meeting-notes.md" in v for v in violations), violations
    assert not any(v.startswith("README.md") for v in violations), violations


def test_public_scan_skips_binary_formats(tmp_path):
    bogus = tmp_path / "looks-private.pdf"
    bogus.write_bytes(b"%PDF-1.4 fake payload south-portland-tank-farms")
    assert psp_public.scan_tree(tmp_path) == []


# ---- internal process references (2026-11-24) ----------------------------
# The marker sets match literal strings only, so the footer script comment
# `row-40 dropdown a11y` rode into every page and sat on staging and on
# production for weeks. The pattern layer is what stops the next one.

def test_public_scan_catches_the_footer_comment_as_it_stood():
    """The exact pre-fix footer script comment must fail the scan now.

    This is the byte-level shape that shipped, led by its ledger row id.
    """
    shipped = (
        "<script>\n"
        "/* row-40 dropdown a11y — progressive enhancement only. The menus already\n"
        "   open and close in CSS (:hover and :focus-within; blur closes). */\n"
        "</script>")
    violations = psp_public.scan_text(shipped, "index.html")
    assert any('internal reference "row-40"' in v for v in violations), violations


def test_public_scan_catches_ids_and_gate_report_paths():
    """Thread, decision and project ids and gate-report paths are
    unambiguous: no campaign page would ever carry one."""
    planted = (
        '<p>Ask thread thr_g57ekquphp about decision dec_2x1vefwof9lj in project '
        'proj_abc123xyz, then read gate-reports/2026-11-24-1.json, which lives '
        'under /Users/cristos/Documents.</p>')
    violations = psp_public.scan_text(planted, "past-work.html")
    for expected in (
        "thr_g57ekquphp",
        "dec_2x1vefwof9lj",
        "proj_abc123xyz",
        "gate-reports/",
        "2026-11-24-1.json",
        "/Users/",
    ):
        assert any(expected in v for v in violations), (expected, violations)


def test_public_scan_leaves_ordinary_row_prose_alone():
    """The bare-row rule must not fire on geometry or ordinary prose, and the
    literal-marker argument must keep working alongside the patterns."""
    prose = (
        "<p>The tanks stand in a row beside the fence line.</p>"
        "<style>/* the nav row 909px at this width */</style>")
    assert psp_public.scan_text(prose, "styles.css") == []
    assert not [v for v in psp_public.scan_text(prose, "x.html") if "internal" in v]
    # a caller-supplied marker set still applies, and patterns still apply with it
    assert psp_public.scan_text("wixstatic", "x.html", ("wixstatic",))
    assert psp_public.scan_text("row-40", "x.html", ())


def test_public_scan_catches_staging_audit_provenance():
    """Second pass on the same class (2026-11-24): the copied map pages cited
    their audit cycle in marker a11y comments, and the stylesheet cited a
    "page-structure review, fix N" and a "staging audit, digest #4". The audit
    cycle is internal bookkeeping, so the phrase itself is now a pattern.

    "digest #" and "issue #" are deliberately left out: a newsletter issue
    number is legitimate public copy, and both real leaks sit inside the
    "staging audit" phrase this pattern covers whole.
    """
    for text in (
        "/* a11y (staging audit issue #4, Lighthouse aria-command-name): x */",
        "/* a11y (PSP staging audit issue #4, Lighthouse aria-command-name): x */",
        "/* heading-order fix (2026-10-15 staging audit, digest #4): pages */",
    ):
        violations = psp_public.scan_text(text, "docs/map/embed.html")
        assert any("staging audit" in v for v in violations), (text, violations)
    # and the generic shapes alone stay clean
    assert psp_public.scan_text("<p>Our newsletter, issue #12, is out.</p>",
                                "newsletter.html") == []


def test_map_copy_strips_audit_provenance(tmp_path):
    """The map pages are regenerated from the sibling checkout, so the strip
    has to live in the copy step: a fresh source carrying an audit citation
    must come out clean, with the rest of the note kept."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "embed.html").write_text(
        "<script>\n/* a11y (staging audit issue #4, Lighthouse "
        "aria-command-name): x */\n</script>", encoding="utf-8")
    (src / "map.html").write_text(
        "<html><body><header><nav><a href=\"report.html\">Research Report</a>"
        "</nav></header>\n<script>\n/* a11y (PSP staging audit issue #4, "
        "Lighthouse aria-command-name): x */\n</script></body></html>",
        encoding="utf-8")
    (src / "styles.css").write_text("/* nothing internal */\n", encoding="utf-8")
    out = tmp_path / "out"
    psp_public.copy_map_pages(str(out), str(src))
    for name in psp_public.MAP_FILES:
        copied = (out / "map" / name).read_text(encoding="utf-8")
        assert "staging audit" not in copied, name
        assert psp_public.scan_file(str(out / "map" / name), f"map/{name}") == [], name
    embed = (out / "map" / "embed.html").read_text(encoding="utf-8")
    assert "Lighthouse aria-command-name" in embed, (
        "the strip must drop the citation, not the note around it")


def test_build_strips_planted_map_citation(tmp_path):
    """End to end through tools/build.py: the copy boundary holds even when
    the map source itself carries an audit citation.

    This is the guarantee that matters, because the public tree must not
    depend on the upstream tank-farms repo staying clean.
    """
    src = tmp_path / "map-src"
    src.mkdir()
    (src / "embed.html").write_text(
        "<script>\n/* a11y (staging audit issue #4, Lighthouse "
        "aria-command-name): x */\n</script>", encoding="utf-8")
    (src / "map.html").write_text(
        "<html><body><nav><a href=\"report.html\">Research Report</a></nav>\n"
        "<script>\n/* a11y (PSP staging audit issue #4, Lighthouse "
        "aria-command-name): x */\n</script></body></html>", encoding="utf-8")
    (src / "styles.css").write_text("/* nothing internal */\n", encoding="utf-8")
    out = tmp_path / "out"
    env = dict(os.environ, PSP_MAP_DOCS_DIR=str(src))
    subprocess.run([sys.executable, BUILD, str(out)], check=True,
                   capture_output=True, env=env)
    for name in psp_public.MAP_FILES:
        built = (out / "map" / name).read_text(encoding="utf-8")
        assert "staging audit" not in built, name
    assert "Lighthouse aria-command-name" in (
        out / "map" / "embed.html").read_text(encoding="utf-8")


def test_built_tree_scans_clean(docs):
    """The freshly built tree carries no private markers and no internal
    process references."""
    violations = psp_public.scan_tree(str(docs))
    assert not violations, "\n" + "\n".join(violations)


# ---- tools/publish.py --repo/--domain after the 2026-10-14            ----
# ---- staging-first hardening: a bare run targets the staging mirror,  ----
# ---- production is reachable ONLY through an explicit --repo, and a   ----
# ---- publish auto-keeps (never silently clears) a custom domain the   ----
# ---- target already carries.                                          ----

STAGING_PUBLISH_REPO = "cristoslc/protect-south-portland-staging"
STAGING_PUBLISH_DOMAIN = "staging.protectsouthportland.org"


def test_publish_defaults_stay_on_staging():
    """Operator directive 2026-10-14: a bare publish targets the staging
    mirror; production is reachable ONLY through an explicit --repo."""
    args = publish.build_parser().parse_args(["--gate-report", "g.json"])
    assert args.repo == publish.DEFAULT_REPO == publish.STAGING_REPO
    assert args.domain is None
    explicit = publish.build_parser().parse_args(
        ["--gate-report", "g.json", "--repo", publish.PROD_REPO])
    assert explicit.repo == publish.PROD_REPO


def test_publish_flags_select_staging_repo_and_domain():
    args = publish.build_parser().parse_args([
        "--gate-report", "g.json",
        "--repo", STAGING_PUBLISH_REPO, "--domain", STAGING_PUBLISH_DOMAIN])
    assert args.repo == STAGING_PUBLISH_REPO
    assert args.domain == STAGING_PUBLISH_DOMAIN


def test_publish_pages_base_and_default_dir_follow_repo():
    assert publish.repo_pages_base(publish.PROD_REPO) == \
        "https://cristoslc.github.io/protect-south-portland-published"
    assert publish.repo_pages_base(STAGING_PUBLISH_REPO) == \
        "https://cristoslc.github.io/protect-south-portland-staging"
    assert publish.default_mirror_dir(publish.PROD_REPO) == os.path.join(
        os.path.dirname(psp_public.SITE_REPO_ROOT),
        "protect-south-portland-published")
    assert publish.default_mirror_dir(STAGING_PUBLISH_REPO) == os.path.join(
        os.path.dirname(psp_public.SITE_REPO_ROOT),
        "protect-south-portland-staging")


def test_publish_stages_cname_only_when_domain_given(docs, tmp_path):
    """No --domain: the tree carries no CNAME (today's mirror behavior).
    With --domain: exactly that hostname is staged and passes the scan."""
    # Production hands stage_publish_tree an mkdtemp'd (existing) dir.
    default_stage = tmp_path / "default"
    default_stage.mkdir()
    publish.stage_publish_tree(str(default_stage), docs_dir=str(docs))
    assert not os.path.exists(str(default_stage / "CNAME"))

    staged = tmp_path / "staged"
    staged.mkdir()
    publish.stage_publish_tree(str(staged), cname=STAGING_PUBLISH_DOMAIN,
                               docs_dir=str(docs))
    staged_cname = open(str(staged / "CNAME"), encoding="utf-8").read().strip()
    assert staged_cname == STAGING_PUBLISH_DOMAIN, staged_cname
    # The staging hostname must survive the publication scan: no private
    # marker, no draft marker, no event marker.
    assert psp_public.scan_tree(str(staged)) == []

# ---- publish-tool hardening from domain-flip-readiness.md gaps 2-4: the ----
# ---- post-push verification must not follow redirects outside the      ----
# ---- allowed hosts, must wait for the TLS certificate and enforce      ----
# ---- HTTPS, and a default (no --domain) publish must never clear a     ----
# ---- custom domain the target repo already carries.                    ----


def _fake_urlopen(final_url, status=200):
    """Stub for publish.urllib.request.urlopen: 200 at `final_url`."""

    class FakeResp:
        def __init__(self):
            self.status = status

        def read(self):
            return b""

        def geturl(self):
            return final_url

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return lambda url, timeout=20: FakeResp()


def test_banner_text_single_source():
    assert BANNER_TEXT == ("Tell our leaders to stop tank farms from dumping "
                           "hazardous pollutants in our neighborhoods.")


def test_publish_wait_fails_loud_when_redirect_leaves_github_io(monkeypatch):
    monkeypatch.setattr(
        publish.urllib.request, "urlopen",
        _fake_urlopen("https://www.protectsouthportland.com/map/embed.html"))
    with pytest.raises(SystemExit, match="custom DNS already live"):
        publish.wait_for_pages(
            ["https://cristoslc.github.io/protect-south-portland-published/"
             "map/embed.html"], minutes=0.02)


def test_publish_wait_accepts_the_explicit_custom_domain(monkeypatch):
    monkeypatch.setattr(
        publish.urllib.request, "urlopen",
        _fake_urlopen(f"https://{STAGING_PUBLISH_DOMAIN}/"))
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    publish.wait_for_pages([f"https://{STAGING_PUBLISH_DOMAIN}/"],
                           minutes=0.02,
                           allowed_domains=(STAGING_PUBLISH_DOMAIN,))


def test_publish_wait_timeout_names_the_domain_provisioning_hint(monkeypatch):
    def broken(url, timeout=20):
        raise OSError("connection failed")

    monkeypatch.setattr(publish.urllib.request, "urlopen", broken)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit, match="certificate"):
        publish.wait_for_pages([f"https://{STAGING_PUBLISH_DOMAIN}/"],
                               minutes=0.01,
                               allowed_domains=(STAGING_PUBLISH_DOMAIN,))


def test_publish_wait_timeout_github_io_default_message(monkeypatch):
    def broken(url, timeout=20):
        raise OSError("connection failed")

    monkeypatch.setattr(publish.urllib.request, "urlopen", broken)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit, match="Pages not serving after the wait"):
        publish.wait_for_pages(
            ["https://cristoslc.github.io/protect-south-portland-published/"],
            minutes=0.01)


def test_publish_stickiness_default_keeps_the_existing_domain():
    """Auto-keep (2026-10-14): without --domain a publish re-stages and
    re-verifies the custom domain the target already carries; it never
    silently drops one. An empty/absent Pages state keeps nothing."""
    state = {"cname": STAGING_PUBLISH_DOMAIN,
             "protected_domain_state": "verified"}
    assert publish.domain_stickiness_violation(state, None, False) is None
    assert publish.domain_stickiness_violation({}, None, False) is None
    assert publish.domain_stickiness_violation(
        {"protected_domain_state": "unverified"}, None, False) is None
    assert publish.resolve_publish_domain(state, None, False) == \
        (STAGING_PUBLISH_DOMAIN, None)
    assert publish.resolve_publish_domain({}, None, False) == (None, None)
    # A verified custom domain with no cname value to read still refuses
    # a domainless run: nothing to keep, staging blind would be worse.
    no_cname = {"protected_domain_state": "verified"}
    resolved = publish.resolve_publish_domain(no_cname, None, False)
    assert resolved[0] is None and resolved[1]
    assert "--domain" in resolved[1] and "--allow-domain-drop" in resolved[1]


def test_publish_stickiness_guard_escape_hatches():
    state = {"cname": STAGING_PUBLISH_DOMAIN}
    assert publish.domain_stickiness_violation(
        state, STAGING_PUBLISH_DOMAIN, False) is None
    assert publish.domain_stickiness_violation(state, None, True) is None
    conflict = publish.domain_stickiness_violation(
        state, STAGING_PUBLISH_DOMAIN, True)
    assert conflict and "conflicts" in conflict
    # --domain replaces what the target carries; --allow-domain-drop
    # clears it; the bare default keeps it (auto-keep).
    assert publish.resolve_publish_domain(
        state, "other.example.org", False) == ("other.example.org", None)
    assert publish.resolve_publish_domain(state, None, True) == (None, None)
    assert publish.resolve_publish_domain(state, None, False) == \
        (STAGING_PUBLISH_DOMAIN, None)


def test_publish_check_domain_stickiness_resolves_and_aborts(monkeypatch):
    monkeypatch.setattr(
        publish, "pages_api",
        lambda repo: {"cname": STAGING_PUBLISH_DOMAIN})
    assert publish.check_domain_stickiness(
        "cristoslc/protect-south-portland-staging", None, False) == \
        STAGING_PUBLISH_DOMAIN
    with pytest.raises(SystemExit, match="conflicts"):
        publish.check_domain_stickiness(
            "cristoslc/protect-south-portland-staging",
            STAGING_PUBLISH_DOMAIN, True)
    monkeypatch.setattr(publish, "pages_api", lambda repo: None)
    assert publish.check_domain_stickiness(
        "cristoslc/protect-south-portland-staging", None, False) is None


def test_publish_index_matches_built(tmp_path):
    # Operator ruling 2026-11-24: strict, after the strip. There is no
    # banner-line branch any more, so a served text that merely contains the
    # banner is not the built file and does not pass.
    index = tmp_path / "index.html"
    index.write_text(f"<p>{BANNER_TEXT}</p>", encoding="utf-8")
    assert publish.index_matches_built(f"<p>{BANNER_TEXT}</p>", str(index))
    assert not publish.index_matches_built(f"prose {BANNER_TEXT} prose", str(index))
    assert not publish.index_matches_built(BANNER_TEXT, str(index))
    assert not publish.index_matches_built("<p>different text only</p>",
                                           str(index))
    assert not publish.index_matches_built(f"<p>{BANNER_TEXT}</p>",
                                           str(index) + "-gone")
    # the one thing that may differ is the two publish-time injections, and
    # only when both are complete and ours
    gate = (publish.injected_block_open(publish.GATE_MARKER) + "\n<p>gate</p>\n"
            + publish.injected_block_close(publish.GATE_MARKER))
    stamp = (publish.injected_block_open(publish.STAMP_MARKER) + "\n<p>stamp</p>\n"
             + publish.injected_block_close(publish.STAMP_MARKER))
    served = f"<head>{stamp}{gate}</head><p>{BANNER_TEXT}</p>"
    assert not publish.index_matches_built(served, str(index))
    index.write_text(f"<head></head><p>{BANNER_TEXT}</p>", encoding="utf-8")
    assert publish.index_matches_built(served, str(index))
    # a difference OUTSIDE the injections is a real difference and still fails
    assert not publish.index_matches_built(
        served.replace(f"<p>{BANNER_TEXT}</p>", "<p>edited</p>"), str(index))


def test_publish_enforce_https_polls_then_enforces(monkeypatch):
    sequence = iter([
        {"https_enforced": False, "https_certificate":
            {"state": "pending_issuance"}},
        {"https_enforced": False, "https_certificate": {"state": "approved"}},
        {"https_enforced": False, "https_certificate": {"state": "approved"}},
        {"https_enforced": True},
    ])
    monkeypatch.setattr(publish, "pages_api", lambda repo: next(sequence))
    puts = []
    monkeypatch.setattr(publish, "put_https_enforced",
                        lambda repo: puts.append(repo))
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    assert publish.enforce_https("cristoslc/protect-south-portland-staging",
                                 clock=lambda: 0)["https_enforced"] is True
    assert puts == ["cristoslc/protect-south-portland-staging"]


def test_publish_enforce_https_timeout_names_the_manual_step(monkeypatch):
    monkeypatch.setattr(
        publish, "pages_api",
        lambda repo: {"https_enforced": False, "https_certificate": None})
    monkeypatch.setattr(publish, "put_https_enforced", lambda repo: None)
    ticks = iter(range(0, 1000, 30))
    with pytest.raises(SystemExit, match="Enforce HTTPS"):
        publish.enforce_https("cristoslc/protect-south-portland-staging",
                              minutes=1,
                              clock=lambda: next(ticks), pause=lambda s: None)


def test_publish_wait_flags_reject_a_domainless_run():
    with pytest.raises(SystemExit, match="custom-domain"):
        publish.assert_flag_agreement(None, True)
    with pytest.raises(SystemExit, match="custom-domain"):
        publish.assert_flag_agreement(None, False)
    publish.assert_flag_agreement(STAGING_PUBLISH_DOMAIN, None)
    publish.assert_flag_agreement(STAGING_PUBLISH_DOMAIN, True)


def test_publish_parser_hardening_flags():
    parser = publish.build_parser()
    args = parser.parse_args(["--gate-report", "g"])
    assert args.allow_domain_drop is False
    assert args.wait_https is None
    args = parser.parse_args(
        ["--gate-report", "g", "--allow-domain-drop", "--wait-https"])
    assert args.allow_domain_drop is True
    assert args.wait_https is True
    args = parser.parse_args(["--gate-report", "g", "--no-wait-https"])
    assert args.wait_https is False


def test_typography_older_visitor_floor():
    # Older-visitor readability pass (2026-10-15): the root scale rides the
    # visitor's own browser font setting (112.5% of it = 18px at defaults),
    # and body reading copy sits at exactly 1rem so every paragraph that
    # inherits the body (prose, cards, placeholder notes — whose own
    # font-size lines were dropped for that) lands on 18px and scales
    # together with every rem-based secondary size. The old fixed 17px body
    # broke that chain, and a fixed body floor is exactly what made the site
    # read small to older visitors. The staging audit
    # (tools/staging_audit.py) re-checks this against whatever the mirror
    # actually serves.
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    assert "font-size: 112.5%" in css, "accessibility root scale (html)"
    assert "\n  font-size: 1rem;\n" in css, "body floor follows the root in rem"
    assert "font-size: 17px" not in css, "fixed px body defeats user scaling"


def test_footer_cta_contrast_wins_over_footer_link_color():
    # Lighthouse color-contrast, 2026-10-15 staging audit: `.footer a`
    # (0,1,1) out-specifies `.btn--cta` (0,1,0), so the footer DONATE
    # button rendered #bfeaf4 on --orange-dark (4.30:1, below AA for its
    # 17px bold) instead of white (5.55:1). The CTA keeps its own white
    # on the orange fill; the hover path goes darker (white on
    # #9c3615, 7.11:1).
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    assert re.search(r"\.footer \.btn--cta\s*\{[^}]*color:\s*#fff", css), \
        "footer .btn--cta must re-pin white text on the orange fill"


# ---- header contrast (2026-11-23): the Act now pill keeps one passing pair --
# Measured in headless Chrome at 412 (menu open) and 1440: the pill rendered
# #b8401a on #de5021 (1.39:1) on the phone, because the 1120px block repainted
# only the label, and #fff on #de5021 (3.98:1) on desktop. Its text is 16.2px
# at weight 800 — under the 18.66px/700 large-text threshold — so AA wants
# 4.5:1, not 3:1. These helpers read the stylesheet the way the cascade would:
# every rule that touches the pill is resolved against the base rule when it
# declares only one of the pair, so a color-only mobile override fails here.

def _css_rules(css, media_max_width=None):
    """Yield (media_max_width, selector, declarations) for every style rule.

    Recurses into at-rules so a max-width override is reported with its own
    bound instead of vanishing into the outer text.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i, prelude = 0, ""
    while i < len(css):
        ch = css[i]
        if ch == "{":
            depth, j = 1, i + 1
            while j < len(css) and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            body, head = css[i + 1:j - 1], prelude.strip()
            prelude, i = "", j
            if head.startswith("@"):
                bound = media_max_width
                m = re.search(r"max-width:\s*([\d.]+)px", head)
                if m:
                    bound = float(m.group(1))
                yield from _css_rules(body, bound)
            else:
                yield media_max_width, head, body
        elif ch == "}":
            prelude, i = "", i + 1
        else:
            prelude += ch
            i += 1


def _css_declarations(body):
    decls = {}
    for part in body.split(";"):
        if ":" not in part:
            continue
        prop, value = part.split(":", 1)
        decls[prop.strip().lower()] = value.strip()
    return decls


def _css_variables(css):
    variables = {}
    for _media, _selector, body in _css_rules(css):
        for prop, value in _css_declarations(body).items():
            if prop.startswith("--"):
                variables[prop] = value
    return variables


def _css_color(value, variables, seen=()):
    """Resolve a CSS color value (var(), hex, or rgb()) to (r, g, b)."""
    value = re.sub(r"!important\s*$", "", value.strip()).strip()
    m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", value)
    if m:
        assert m.group(1) in variables, f"{m.group(1)} is not defined"
        assert m.group(1) not in seen, f"circular var() chain at {m.group(1)}"
        return _css_color(variables[m.group(1)], variables, seen + (m.group(1),))
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value)
    if m:
        digits = m.group(1)
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[k:k + 2], 16) for k in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+[\d.]+)?\s*\)", value)
    if m:
        return tuple(int(g) for g in m.groups())
    raise AssertionError(
        f"cannot resolve CSS color {value!r}; this test only understands "
        "hex, rgb() and var() so that a new color form is never waved through")


def _contrast_ratio(fg, bg):
    def luminance(rgb):
        channels = []
        for channel in rgb:
            c = channel / 255
            channels.append(c / 12.92 if c <= 0.03928
                            else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_nav_cta_pill_contrast_passes_at_every_width():
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    variables = _css_variables(css)
    rules = [(media, selector, _css_declarations(body))
             for media, selector, body in _css_rules(css)
             if "nav-cta" in selector]
    base = next(((selector, decls) for media, selector, decls in rules
                 if media is None and selector.strip() == ".main-nav .nav-cta > a"),
                None)
    assert base, "the Act now pill needs its own base rule to declare its pair"
    assert "background" in base[1], "the pill's fill must be declared, not inherited"
    assert "color" in base[1], "the pill's text color must be declared"
    base_bg = _css_color(base[1]["background"], variables)
    base_fg = _css_color(base[1]["color"], variables)

    for media, selector, decls in rules:
        fg = _css_color(decls["color"], variables) if "color" in decls else base_fg
        fill = decls.get("background", decls.get("background-color"))
        bg = _css_color(fill, variables) if fill else base_bg
        where = "all widths" if media is None else f"max-width {media:g}px"
        ratio = _contrast_ratio(fg, bg)
        assert ratio >= 4.5, (
            f"{selector.strip()} ({where}): the pill label renders "
            f"#{fg[0]:02x}{fg[1]:02x}{fg[2]:02x} on "
            f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x} = {ratio:.2f}:1; the nav "
            "text is 16.2px at weight 800, so WCAG AA normal text wants 4.5:1")


# ---- button-family focus ring (2026-11-24, ledger row 95) -------------------
# The Act now pair removal at `b88ec06` took the only :focus-visible ring any
# `.btn` family member had (it lived inside `.link-row--buttons`), so every
# button on the site fell back to the browser default or nothing. The pins
# below walk the BUILT pages for the census of rendered variants and their
# ancestor surfaces, then resolve the winning focus declaration from the
# stylesheet, so neither a new variant nor a new dark band can ship ringless
# and no page is hand-listed. The shape is compared against the two
# :focus-visible rules the site already ships (the signup input on paper, the
# MENU toggle on the masthead), because a third shape would be a new treatment.

FOCUS_RING_MIN_CONTRAST = 3.0  # WCAG 2.1 SC 1.4.11, non-text UI


def _is_btn_class(token):
    return re.fullmatch(r"btn(?:--[\w-]+)?", token) is not None


class _ButtonSurfaceWalker(HTMLParser):
    """Every element carrying a `.btn` member, with its ancestor chain.

    The chain is (tag, classes-in-document-order) from the outermost ancestor
    inward, so a surface is the nearest ancestor that declares a background in
    the stylesheet rather than a guess about where a page put its button.
    """

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._stack = []
        self.found = []  # (tag, classes tuple, ancestor tuple)

    def _record(self, tag, attrs):
        classes = tuple((dict(attrs).get("class") or "").split())
        if any(_is_btn_class(c) for c in classes):
            self.found.append((tag, classes, tuple(self._stack)))
        return classes

    def handle_starttag(self, tag, attrs):
        classes = self._record(tag, attrs)
        if tag not in self.VOID:
            self._stack.append((tag, classes))

    def handle_startendtag(self, tag, attrs):
        self._record(tag, attrs)

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return


def _parse_compound(compound):
    """Split one compound selector into (kind, name) pairs.

    Only tag names, `.class` and `:focus-visible` are understood. Anything
    else fails loud instead of being silently treated as a match, so a future
    selector form cannot ride through the census unnoticed.
    """
    parts, i = [], 0
    while i < len(compound):
        rest = compound[i:]
        if compound[i] == ".":
            m = re.match(r"\.([\w-]+)", rest)
            assert m, f"cannot parse selector compound {compound!r}"
            parts.append(("class", m.group(1)))
            i += m.end()
        elif compound[i] == ":":
            m = re.match(r"::?([\w-]+)(\([^)]*\))?", rest)
            assert m, f"cannot parse selector compound {compound!r}"
            assert m.group(1) == "focus-visible" and not m.group(2), (
                f"the focus census cannot evaluate the pseudo-class "
                f"{rest[:m.end()]!r}; teach this helper before shipping it")
            parts.append(("focus", None))
            i += m.end()
        else:
            m = re.match(r"[\w-]+", rest)
            assert m, f"cannot parse selector compound {compound!r}"
            parts.append(("tag", m.group(0)))
            i += m.end()
    return parts


def _focus_rules(css):
    """(order, media, selector, declarations) for every focus rule shipped.

    NOTHING is skipped here, including a selector shape the census cannot
    *match* and a rule inside a media query: a shape reader needs the whole
    set, and the matcher that cannot decide one raises instead of dropping it
    (see `_matching_focus_rules`). Skipping here is what hid the MENU toggle's
    focus rule from this census, so the coverage a docstring claimed was never
    what the code did.

    `media` is the max-width bound the rule sits under, or None when the rule
    is width-independent. It is reported rather than discarded so a reader can
    reason about it; a rule declares the same outline at every width, so it
    does not change a shape comparison, and only matching cares (there it
    fails loud instead of guessing).

    Understood exactly, not implied: element tags, `.class`, descendant
    combinators (plain whitespace) and the single pseudo-class
    `:focus-visible`. Anything else in a compound fails loud in
    `_parse_compound`; the sibling and child combinators (`+`, `~`, `>`)
    fail loud in `_matches_focus`.
    """
    rules = []
    for order, (media, selector, body) in enumerate(_css_rules(css)):
        if ":focus-visible" not in selector:
            continue
        for part in selector.split(","):
            part = " ".join(part.split())
            if part:
                rules.append((order, media, part, _css_declarations(body)))
    return rules


def _selector_specificity(selector):
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+|:[\w-]+(?:\([^)]*\))?", selector))
    tags = len(re.findall(r"(?:^|\s)[a-z][\w-]*", selector))
    return (ids, classes, tags)


def _matches_focus(selector, tag, classes, ancestors):
    """Does a focus selector reach this element inside its ancestor chain?

    Descendant combinators only, and deliberately so: the walker records a
    button's ancestor chain and nothing about its siblings, or about a child's
    own nesting, so `+`, `~` and `>` cannot be decided here. A selector
    carrying one raises rather than being guessed at or skipped, because a
    silently skipped focus rule is reported as "no ring" while the browser may
    well be painting one — the exact failure this census must never have.
    """
    for combinator in ("+", "~", ">"):
        if combinator in selector:
            raise AssertionError(
                f"the focus census cannot evaluate the selector {selector!r}: "
                f"it carries the {combinator!r} combinator and the button walker "
                "records an ancestor chain only. Teach _ButtonSurfaceWalker, "
                "_matches_focus and _button_census to see sibling/child "
                "structure before shipping a ring written that way, or express "
                "it with a descendant selector")
    parsed = [_parse_compound(compound) for compound in selector.split()]

    def compound_matches(compound, element_tag, element_classes):
        for kind, name in compound:
            if kind == "class" and name not in element_classes:
                return False
            if kind == "tag" and name != element_tag:
                return False
        return True

    if not compound_matches(parsed[-1], tag, classes):
        return False
    cursor = 0
    for compound in parsed[:-1]:
        while cursor < len(ancestors):
            ancestor_tag, ancestor_classes = ancestors[cursor]
            cursor += 1
            if compound_matches(compound, ancestor_tag, ancestor_classes):
                break
        else:
            return False
    return True


def _subject_could_match(selector, tag, classes):
    """Can the selector's last compound name this element at all?

    The subject is decided without touching a combinator, so a rule written
    against a different element — the MENU toggle's label, say — is filtered
    out before the matcher is asked, and the matcher's refusal only fires for
    a shape that could actually paint this element's ring. That is a sound
    filter, not a silent skip: a rule whose subject is another element cannot
    reach this one whatever combinator it carries.
    """
    for kind, name in _parse_compound(selector.split()[-1]):
        if kind == "class" and name not in classes:
            return False
        if kind == "tag" and name != tag:
            return False
    return True


def _matching_focus_rules(rules, tag, classes, ancestors):
    """[(specificity, order, selector, declarations)] reaching this element.

    Returned in CASCADE order: specificity first, source order second, which
    is what a browser does. The declarations are consumed in that order by
    `_resolve_outline`, so a shorthand and its longhand keep their real order
    too. Source order alone was right only by luck — every higher-specificity
    rule happened to come later — and a synthetic sheet proves the difference.

    Two shapes this census cannot decide are refused rather than skipped: a
    sibling or child combinator, and a rule under a media query that would
    otherwise reach the element (one ring per element cannot be a function of
    the viewport). Today the one media-scoped focus rule targets the MENU
    label, so the filter above keeps the census honest and a future
    width-scoped button ring fails here by name.
    """
    matched = []
    for order, media, selector, declarations in rules:
        if not _subject_could_match(selector, tag, classes):
            continue
        if not _matches_focus(selector, tag, classes, ancestors):
            continue
        if media is not None:
            raise AssertionError(
                f"the focus census cannot evaluate the selector {selector!r}: it "
                f"sits under @media (max-width: {media:g}px) and the census "
                "resolves one ring per element per surface, so a width-"
                "conditional ring would be reported as if it always applied. "
                "Teach this helper to evaluate media context, or scope the ring "
                "with a selector instead of a breakpoint")
        matched.append((_selector_specificity(selector), order, selector,
                        declarations))
    return sorted(matched, key=lambda rule: (rule[0], rule[1]))


def _resolve_outline(declarations):
    """(width, style, colour, offset) resolved in declaration order.

    Accepts a mapping (one rule block) or a sequence of (property, value)
    pairs (a cascade-ordered run across blocks). Components are applied in the
    order given and the last one to set a component wins, which is what a
    browser does: a shorthand and its longhand are NOT order-free, so
    `outline-color` declared before `outline` loses to the shorthand's colour
    and the same longhand declared after it wins. The old merge read the two
    out of a dict without regard to order and always let the longhand win.
    """
    if hasattr(declarations, "items"):
        declarations = declarations.items()
    width = style = colour = offset = None
    for prop, value in declarations:
        if prop == "outline":
            # a shorthand resets every component it does not name
            width = style = colour = None
            for token in value.split():
                if token in ("solid", "dashed", "dotted", "double", "none"):
                    style = token
                elif re.fullmatch(r"[\d.]+px", token):
                    width = token
                else:
                    colour = token
        elif prop == "outline-width":
            width = value
        elif prop == "outline-style":
            style = value
        elif prop == "outline-color":
            colour = value
        elif prop == "outline-offset":
            offset = value
    return width, style, colour, offset


def _class_backgrounds(css):
    """Background each single-class rule declares, plus the body's own.

    Alongside the fills this records each class's rule position in the
    stylesheet (source order), because one element can carry several of these
    classes at once — `class="callout callout--ask"` — and the surface the
    browser paints is the same-specificity rule that comes LAST, not the
    first class in the attribute.
    """
    backgrounds = {}
    order = {}
    counter = 0
    for _media, selector, body in _css_rules(css):
        counter += 1
        if ":" in selector:
            continue
        declarations = _css_declarations(body)
        fill = declarations.get("background-color") or declarations.get("background")
        if not fill or fill.startswith("url(") or fill in ("none", "transparent"):
            continue
        for part in selector.split(","):
            part = part.strip()
            m = re.fullmatch(r"\.([\w-]+)", part)
            if m:
                backgrounds[m.group(1)] = fill
                order[m.group(1)] = counter
            elif part == "body":
                backgrounds["body"] = fill
                order["body"] = counter
    return backgrounds, order


def _surface_behind(ancestors, backgrounds, background_order, variables):
    """(label, rgb) for the nearest ancestor that paints a surface.

    When one ancestor carries several background-declaring classes, the
    winner is the rule latest in the stylesheet — the same-specificity
    cascade, which is what the browser renders. This is what lets
    `.callout--ask` (teal-900, declared later) beat the base `.callout`
    (cyan-soft) as the true surface behind the panel's controls.
    """
    for _tag, classes in reversed(ancestors):
        candidates = [(background_order[name], name)
                      for name in classes
                      if name in backgrounds
                      and not backgrounds[name].startswith("rgba")]
        if candidates:
            _order, name = max(candidates)
            return f".{name}", _css_color(backgrounds[name], variables)
    assert "body" in backgrounds, (
        "the stylesheet must declare body's background: it is the surface "
        "every unbanded button is read against")
    return "body", _css_color(backgrounds["body"], variables)


def _button_census(docs):
    """{(variant tuple, surface label): ring ratio} for every rendered button."""
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    variables = _css_variables(css)
    backgrounds, background_order = _class_backgrounds(css)
    rules = _focus_rules(css)
    census = {}
    for dirpath, _dirnames, filenames in os.walk(docs):
        for name in sorted(filenames):
            if not name.endswith(".html"):
                continue
            walker = _ButtonSurfaceWalker()
            walker.feed(open(os.path.join(dirpath, name), encoding="utf-8").read())
            for tag, classes, ancestors in walker.found:
                variant = tuple(c for c in classes if _is_btn_class(c))
                surface, surface_rgb = _surface_behind(
                    ancestors, backgrounds, background_order, variables)
                applicable = _matching_focus_rules(rules, tag, classes, ancestors)
                winner = applicable[-1][2] if applicable else None
                width, style, colour, offset = _resolve_outline(
                    [pair
                     for _specificity, _order, _selector, declarations in applicable
                     for pair in declarations.items()])
                assert colour, (
                    f"{name}: {tag} {' '.join(variant)} on {surface} has no "
                    f"reachable :focus-visible colour (winning rule: {winner})")
                ring = _css_color(colour, variables)
                census[(variant, surface)] = (
                    _contrast_ratio(ring, surface_rgb), width, style, offset,
                    winner, name)
    return census


def test_issue8_alerts_line_reads_clean(docs):
    """Board issue staging-website-feedback#8 (the copy reviewer's finding on
    PR #109): the alerts sentence carried the page's own name mid-sentence —
    "Follow our alerts to Act now and attend City Council meetings" — and the
    capitalized "Act now" reads oddly there. The wording choice under Brand
    Voice keeps the filer's phrase lowercase and ties it to a concrete verb:
    "Follow our alerts and act now: come to City Council meetings and
    workshops." The alerts path itself is the workshop-alerts mailto in the
    preceding paragraph; it stays byte-identical.
    """
    act = read(docs, "act-now.html")
    assert "Follow our alerts and act now: come to City Council meetings and workshops." in act
    assert "to Act now and attend" not in act, (
        "the mid-sentence page-name capitalization the reviewer flagged must not return")
    # the alerts link facts stay untouched
    assert 'href="mailto:protectsouthportland@gmail.com?subject=Workshop%20alerts"' in act
    assert "with &ldquo;Workshop alerts&rdquo; in the subject line" in act


def test_act_now_secondary_cards_center_both_axes():
    """Experiment leg, operator directive (ledger row 140), verbatim in
    substance: "try making all these white asks centered horizontally and
    vertically" on the three secondary ask cards of act-now's card grid.
    "Try" makes this an experiment: one contiguous scoped CSS block, shipped
    alone, that the operator can revert in one commit if the look fails on
    their mobile read. The screenshot's card grid marked WHICH cards, never
    geometry, so the alignment is built from the grid's own flex column and
    carries no new colour and no contrast change. The row-129 span rule
    stands untouched: the story card's content centers within the spanned
    width. Scoped to .card-grid--act so no other page's cards move: no
    unscoped .card or .card__body rule may carry the alignment.
    """
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    # both axes, inside the single experiment scope
    assert re.search(
        r"\.card-grid--act \.card \{[^}]*justify-content: center", css, re.S), (
        "the cards' flex column must center content vertically within the card")
    assert re.search(
        r"\.card-grid--act \.card__body \{[^}]*text-align: center", css, re.S), (
        "heading, paragraph and action link must center horizontally")
    # (the row-129/130 span rule for the story card keeps its own pin; the
    # experiment must not touch it, and the scoped-stripped check below
    # proves this block adds nothing outside .card-grid--act)
    # scope isolation: no other page's cards pick the alignment up
    for sel in (r"(?:^|\n)\.card \{[^}]*text-align: center", r"\.card__body \{[^}]*text-align: center",
                r"(?:^|\n)\.card \{[^}]*justify-content: center", r"\.card__body \{[^}]*justify-content: center"):
        bare = re.search(sel, css)
        # remove the scoped experiment hits before judging the bare ones
        scoped_stripped = re.sub(r"\.card-grid--act [^{]*\{[^}]*\}", "", css)
        assert not re.search(sel, scoped_stripped), (
            f"the alignment leaked out of the .card-grid--act scope: {sel}")


def test_every_button_variant_keeps_a_visible_focus_ring_on_its_surface(docs):
    """Ledger row 95: the family keeps a visible ring wherever it renders.

    Census walked from the built pages (not a page list): each rendered
    variant on each surface it actually sits on must resolve a focus ring that
    clears the 3:1 non-text floor against the surface behind it. The
    combinations the family renders today are `.btn.btn--cta` (on light pages,
    on the dark teal featured panel since the row-109 swap, and on the dark
    bands) and `.btn.btn--ghost`; `.btn--light` stays declared for a page that
    adopts it. The assertions below name the rendered combinations so a build
    that loses all buttons fails instead of shrinking the census to an empty
    pass.
    """
    census = _button_census(docs)
    rendered = {variant for variant, _surface in census}
    assert ("btn", "btn--cta") in rendered, "the CTA variant must be in the census"
    assert ("btn", "btn--ghost") in rendered, "the ghost variant must be in the census"
    surfaces = {surface for _variant, surface in census}
    assert ".hero" in surfaces, "the dark hero card surface must be exercised"
    assert ".footer" in surfaces, "the dark footer surface must be exercised"
    assert any(surface not in (".hero", ".footer", ".section--teal")
               for surface in surfaces), "a light surface must be exercised too"

    for (variant, surface), (ratio, width, style, offset, winner, name) in sorted(census.items()):
        label = " ".join(variant)
        assert width == "3px" and style == "solid", (
            f"{name}: {label} on {surface} renders outline {width} {style} "
            f"(rule {winner}); the site's focus convention is 3px solid")
        assert offset == "2px", (
            f"{name}: {label} on {surface} renders outline-offset {offset} "
            f"(rule {winner}); the site's focus convention is 2px")
        assert ratio >= FOCUS_RING_MIN_CONTRAST, (
            f"{name}: {label} on {surface} gets a {ratio:.2f}:1 focus ring "
            f"(rule {winner}); WCAG 2.1 SC 1.4.11 wants 3:1 against the "
            "surface the ring sits on")


def test_button_focus_ring_colour_is_a_palette_token_and_keeps_the_shape():
    """Ledger row 95: the ring is a token, and its shape is the site's own.

    No new colour enters the palette: every `.btn` focus rule paints with a
    `var(--token)` that already exists in `:root`, and no literal hex or rgb()
    value appears anywhere in those rules. The shape is compared against the
    two focus rules the site already ships, so a third treatment fails here.
    """
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    variables = _css_variables(css)
    rules = _focus_rules(css)
    family = [(selector, declarations)
              for _order, _media, selector, declarations in rules
              if any(_is_btn_class(token.lstrip("."))
                     for compound in selector.split()
                     for token in re.findall(r"\.[\w-]+", compound))]
    assert family, (
        "the .btn family has no :focus-visible rule at all; that is the defect "
        "ledger row 95 exists to close")
    assert any(selector.strip() == ".btn:focus-visible"
               for selector, _declarations in family), (
        "a bare `.btn:focus-visible` rule must cover the whole family, "
        "including variants no page renders yet (.btn--light)")

    for selector, declarations in family:
        _width, _style, colour, _offset = _resolve_outline(declarations)
        assert colour, f"{selector} declares no outline colour"
        assert re.fullmatch(r"var\(\s*--[\w-]+\s*\)", colour), (
            f"{selector} paints its ring with {colour!r}; the palette is the "
            "single source of truth, so the ring must be a token")
        token = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", colour).group(1)
        assert token in variables, f"{selector} uses undefined token {token}"
        for value in declarations.values():
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", value), (
                f"{selector} introduces a literal colour ({value!r}); "
                "no new colour enters the palette")

    established = {}
    for _order, _media, selector, declarations in rules:
        width, style, _colour, offset = _resolve_outline(declarations)
        if width is None:
            continue  # a recolour-only override: the dark-band rules
        established[selector] = (width, style, offset)
    # The two rules the site already shipped before the family gained one are
    # named rather than counted: the reader used to skip every selector with a
    # combinator in it, so the MENU toggle's rule never reached this set and
    # "the two focus rules the site already ships" was really the signup input
    # alone. Naming both makes the claim the docstring makes testable.
    prior = (".signup input:focus-visible",
             ".nav-toggle:focus-visible + .nav-toggle-label")
    for selector in prior:
        assert selector in established, (
            f"the site's pre-existing focus rule {selector!r} is missing from "
            "the stylesheet or no longer declares a full outline; the family's "
            "shape is set by those rules, so one vanishing is a change of "
            "convention rather than a refactor")
    assert set(established.values()) == {("3px", "solid", "2px")}, (
        f"the site's existing focus convention moved: {established}")
    for selector, declarations in family:
        width, style, _colour, offset = _resolve_outline(declarations)
        if width is None:
            # a surface override may legitimately recolour only (the dark-band
            # rules do), inheriting width/style/offset from the family base;
            # the resolved per-element shape is pinned by the census test above
            continue
        assert (width, style, offset) in set(established.values()), (
            f"{selector} renders {width} {style} offset {offset}, not the "
            f"site's own {established} convention")


def _focus_ring_comment(css):
    """The `.btn` ring's explanatory comment, from its banner to its `*/`."""
    start = css.index("the family's keyboard ring")
    return css[start:css.index("*/", start)]


def test_focus_ring_comment_figures_reproduce_from_the_shipped_tokens():
    """Ledger row 99: the ring comment's contrast figures are recomputed.

    The full-class review of PR #79 caught the rejected-pair line claiming the
    teal ring measures "1.97:1 against `--teal-900` and 2.09:1 against
    `--teal-950`". Neither reproduces: teal-900 on teal-900 is 1.00:1 and on
    teal-950 is 1.30:1. 1.97 is teal-900 on `--teal-700` and 2.09 is teal-900
    on `--orange-dark`, so two numbers were copied off other rows and
    relabelled. This pin recomputes every pair the comment states from the
    palette in the same file, so a figure cannot drift from the token it
    claims to measure. A comment is not read by a browser, which is exactly
    why a wrong figure in one survived a review round and a published build.
    """
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    variables = _css_variables(css)
    comment = _focus_ring_comment(css)

    for fg, bg in (
            ("--teal-900", "--paper"),
            ("--teal-900", "--mist"),
            ("--teal-900", "--teal-100"),
            ("--teal-900", "--cyan-soft"),
            ("--teal-900", "--teal-900"),
            ("--teal-900", "--teal-950"),
            ("--cyan-soft", "--teal-900"),
            ("--cyan-soft", "--teal-950"),
    ):
        ratio = _contrast_ratio(_css_color(variables[fg], variables),
                                _css_color(variables[bg], variables))
        figure = f"{ratio:.2f}:1"
        assert re.search(rf"(?<![\d.]){re.escape(figure)}", comment), (
            f"the ring comment no longer states {figure} for {fg} on {bg}; "
            "recompute the figure from the tokens rather than retyping one")
    for wrong in ("1.97:1", "2.09:1"):
        assert wrong not in comment, (
            f"the ring comment carries {wrong}, which the review of ledger row "
            "95 found mislabelled: that figure measures teal-900 on --teal-700 "
            "(1.97:1) and on --orange-dark (2.09:1), not on the dark bands")


def test_focus_cascade_ranks_specificity_before_source_order():
    """Ledger row 99: specificity first, source order only as the tie-break.

    The census used to merge every applicable rule in source order, so a
    later, LOWER-specificity rule overrode an earlier, higher-specificity one.
    That is correct on the shipped stylesheet only because every
    higher-specificity rule also happens to come later, and the shape helper
    that ranks them (`_selector_specificity`) was defined and never called.
    This synthetic sheet is the case the real one does not contain.
    """
    css = (" .band .btn:focus-visible { outline: 3px solid var(--teal-900); "
           "outline-offset: 2px; }"
           " .btn:focus-visible { outline: 1px dotted var(--orange); "
           "outline-offset: 0px; }")
    matched = _matching_focus_rules(
        _focus_rules(css), "a", ("btn", "btn--cta"), (("section", ("band",)),))
    assert [selector for _s, _o, selector, _d in matched] == [
        ".btn:focus-visible", ".band .btn:focus-visible"], (
        "the resolver must apply rules in ascending specificity order, so the "
        "most specific rule lands last")
    resolved = _resolve_outline(
        [pair for _s, _o, _selector, declarations in matched
         for pair in declarations.items()])
    assert resolved == ("3px", "solid", "var(--teal-900)", "2px"), (
        "the later, lower-specificity `.btn:focus-visible` overrode the "
        f"earlier `.band .btn:focus-visible`: {resolved}")

    tie = (" .btn:focus-visible { outline: 3px solid var(--teal-900); }"
           " .btn:focus-visible { outline: 4px solid var(--cyan-soft); }")
    assert [declarations["outline"] for _s, _o, _sel, declarations
            in _matching_focus_rules(_focus_rules(tie), "a", ("btn",), ())] == [
        "3px solid var(--teal-900)", "4px solid var(--cyan-soft)"], (
        "equal specificity must fall back to source order")


def test_focus_outline_shorthand_and_longhand_keep_their_declaration_order():
    """Ledger row 99: `outline` and `outline-color` are not order-free.

    `_resolve_outline` used to parse the shorthand first and then prefer any
    longhand out of a dict, whatever order the two were declared in. CSS does
    the opposite: the LAST declaration of a property wins, so a longhand
    declared before the shorthand is overwritten by it. The site's own dark
    override declares only `outline-color`, from a later rule block, which the
    old code got right by accident; this pins both directions so the accident
    becomes a rule.
    """
    longhand_first = _css_declarations(
        "outline-color: var(--orange); outline: 3px solid var(--teal-900)")
    assert _resolve_outline(longhand_first) == (
        "3px", "solid", "var(--teal-900)", None), (
        "a shorthand declared after a longhand must win, exactly as in CSS")

    shorthand_first = _css_declarations(
        "outline: 3px solid var(--teal-900); outline-color: var(--cyan-soft)")
    assert _resolve_outline(shorthand_first) == (
        "3px", "solid", "var(--cyan-soft)", None), (
        "a longhand declared after the shorthand must win")


def test_focus_census_reads_every_rule_and_refuses_an_unknown_shape():
    """Ledger row 99: no focus rule is skipped, and an unhandled shape is loud.

    The reader used to drop every selector carrying `+`, `>` or `~`, and it
    dropped each rule's media context with it. That silently removed the MENU
    toggle's rule (`.nav-toggle:focus-visible + .nav-toggle-label`, the site's
    second pre-existing focus rule) from the census, so a docstring claiming
    the shape was compared against "the two focus rules the site already
    ships" was comparing one. Nothing is skipped now: every selector part is
    reported, the media bound travels with it, and a shape the matcher cannot
    decide raises instead of vanishing. A skipped rule reads as "no ring"
    while the browser may well be painting one.
    """
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    rules = _focus_rules(css)
    selectors = [selector for _order, _media, selector, _decl in rules]
    assert ".nav-toggle:focus-visible + .nav-toggle-label" in selectors, (
        "the MENU toggle's focus rule must be reported, not skipped for its "
        "sibling combinator")
    expected = sum(len([part for part in selector.split(",")
                        if ":focus-visible" in part])
                   for _media, selector, _body in _css_rules(css))
    assert len(selectors) == expected, (
        f"the reader reported {len(selectors)} of {expected} focus rules; a "
        "rule this census cannot see reads as no ring at all")
    toggle = next(rule for rule in rules
                  if rule[2] == ".nav-toggle:focus-visible + .nav-toggle-label")
    assert toggle[1] == 1120.0, (
        "the MENU toggle's focus rule sits under a media query and the reader "
        f"must report that bound rather than discard it: {toggle[1]}")

    for selector in (".band + .btn:focus-visible",
                     ".band > .btn:focus-visible"):
        with pytest.raises(AssertionError, match="combinator"):
            _matching_focus_rules(
                _focus_rules(f"{selector} {{ outline: 3px solid var(--teal-900); }}"),
                "a", ("btn",), ())
    with pytest.raises(AssertionError, match="@media"):
        _matching_focus_rules(
            _focus_rules("@media (max-width: 700px) { .btn:focus-visible "
                         "{ outline: 3px solid var(--teal-900); } }"),
            "a", ("btn",), ())


def test_heading_order_is_sequential(docs):
    # Staging audit digest #4 (2026-10-15): tank-farms.html and
    # our-campaigns.html opened their outline with an h3 directly under the
    # h1. Structure pin only — heading TEXT is unchanged; a retagged heading
    # keeps its visual h3 look via the .h3-look class in styles.css.
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue  # stubs have no headings; Lighthouse audits their target
        levels = [int(m.group(1)) for m in re.finditer(r"<h([1-6])\b", read(docs, name))]
        assert levels, f"{name}: no headings"
        assert levels[0] == 1, f"{name}: outline must open at h1, opens at h{levels[0]}"
        for prev, cur in zip(levels, levels[1:]):
            assert cur <= prev + 1, (
                f"{name}: heading level jumps h{prev} -> h{cur}; outline not sequential")


# ---- gate report hardening (2026-11-04): content-addressed verdicts -------
# The release gate used to validate coverage only: every page present, outcome
# pass, rounds in range. A report whose own scope_note said it covered one
# fixup therefore satisfied the gate for all sixteen pages, and any non-empty
# review_model passed, including a flash variant. Two invariants now hold:
# a page publishes only when the sha256 of its source file matches the reviewed
# hash, and the report must state a full-class reviewer that is not a flash
# model. These tests are the red-first record of both.


def gate_source_pages():
    pages_dir = os.path.join(ROOT, "site", "pages")
    return sorted(n for n in os.listdir(pages_dir) if n.endswith(".html"))


def gate_page_sha256(docs, name):
    return hashlib.sha256(open(os.path.join(docs, name), "rb").read()).hexdigest()


def gate_pages(docs):
    return {
        name: {"rounds": 1, "outcome": "pass", "sha256": gate_page_sha256(docs, name)}
        for name in gate_source_pages()
    }


def write_gate_report(tmp_path, docs, pages=None, drop=(), name="gate.json",
                      **overrides):
    report = {
        "date": "2026-11-04-test",
        "review_model": "synthetic/hf:zai-org/GLM-5.3",
        "review_class": "full",
        "pages": gate_pages(docs) if pages is None else pages,
        "scope_note": "test fixture",
    }
    for key in drop:
        report.pop(key, None)
    report.update(overrides)
    path = tmp_path / name
    path.write_text(json.dumps(report))
    return path


def test_gate_report_current_hashes_publish(tmp_path, docs):
    # The legitimate case: every page carries the hash of the file as it
    # stands now, so the verdict travels with the content it reviewed.
    path = write_gate_report(tmp_path, docs)
    model, review_class, per_page = publish.load_gate_report(str(path))
    assert "GLM-5.3" in model
    assert review_class == "full"
    assert per_page.count("r1") == len(gate_source_pages())


def test_gate_report_refuses_page_hash_mismatch(tmp_path, docs):
    # A page edited after review must be refused by name, with both hashes.
    pages = gate_pages(docs)
    pages["index.html"]["sha256"] = "0" * 64
    path = write_gate_report(tmp_path, docs, pages=pages)
    with pytest.raises(SystemExit) as exc:
        publish.load_gate_report(str(path))
    message = str(exc.value)
    assert "index.html" in message, message
    assert "0" * 64 in message, message
    assert gate_page_sha256(docs, "index.html") in message, message


def test_gate_report_refuses_legacy_entry_without_hash(tmp_path, docs):
    # Legacy decision (option a): a missing hash is refused outright, never
    # trusted by default. Nothing can prove what was reviewed otherwise.
    pages = gate_pages(docs)
    del pages["about.html"]["sha256"]
    path = write_gate_report(tmp_path, docs, pages=pages)
    with pytest.raises(SystemExit) as exc:
        publish.load_gate_report(str(path))
    message = str(exc.value)
    assert "about.html" in message, message
    assert "sha256" in message, message


def test_gate_report_refuses_flash_model(tmp_path, docs):
    path = write_gate_report(tmp_path, docs, review_model="vendor/some-model-flash")
    with pytest.raises(SystemExit) as exc:
        publish.load_gate_report(str(path))
    message = str(exc.value)
    assert "vendor/some-model-flash" in message, message
    assert "flash" in message.lower(), message


def test_gate_report_requires_review_class(tmp_path, docs):
    path = write_gate_report(tmp_path, docs, drop=("review_class",))
    with pytest.raises(SystemExit) as exc:
        publish.load_gate_report(str(path))
    message = str(exc.value)
    assert "review_class" in message, message
    assert "full" in message, message


def test_gate_report_refuses_non_full_class(tmp_path, docs):
    path = write_gate_report(tmp_path, docs, review_class="flash")
    with pytest.raises(SystemExit) as exc:
        publish.load_gate_report(str(path))
    message = str(exc.value)
    assert "flash" in message, message
    assert "full" in message, message


def gate_pages_with_pending(docs, page="act-now.html"):
    pages = gate_pages(docs)
    pages[page] = {
        "rounds": 0,
        "outcome": "pending",
        "sha256": gate_page_sha256(docs, page),
    }
    return pages


def test_gate_report_pending_entry_publishes_to_the_staging_leg(tmp_path, docs):
    """Ledger row 93: the operator's 2026-11-24 policy says a staging publish
    does not wait for review, so a page whose verdict is still in flight needs
    a state of its own to travel in. `pending` with rounds 0 is that state and
    means exactly one thing: no reviewer verdict for this page yet. The staging
    leg accepts it, and nothing on the way upgrades it to a pass."""
    page = "act-now.html"
    path = write_gate_report(
        tmp_path, docs, pages=gate_pages_with_pending(docs, page))
    model, review_class, per_page = publish.load_gate_report(
        str(path), target=publish.STAGING_REPO)
    assert "GLM-5.3" in model
    assert review_class == "full"
    assert f"{page} r0 PENDING" in per_page, per_page


def test_gate_report_pending_entry_refused_on_a_production_leg(tmp_path, docs):
    """The same report is a release credential nowhere. A production-targeted
    leg refuses it, and the refusal names the page and says production needs a
    real verdict rather than a borrowed pass. An unstated target is refused
    too: the staging allowance is stated by naming the staging mirror, never
    inferred by silence."""
    page = "act-now.html"
    path = write_gate_report(
        tmp_path, docs, pages=gate_pages_with_pending(docs, page))
    for target in (publish.PROD_REPO, None):
        with pytest.raises(SystemExit) as exc:
            publish.load_gate_report(str(path), target=target)
        message = str(exc.value)
        assert page in message, message
        assert "pending" in message.lower(), message
        assert "production" in message.lower(), message
        assert "verdict" in message.lower(), message


def test_gate_report_amend_refuses_a_page_whose_hash_moved(tmp_path, docs):
    """The amend path exists for one case: a verdict lands for a page that
    published as pending. It refuses the case content addressing exists to
    prevent, a verdict amended onto bytes the reviewer did not see, and a
    refused amendment leaves the report byte-identical."""
    page = "act-now.html"
    pages = gate_pages_with_pending(docs, page)
    pages[page]["sha256"] = "0" * 64
    path = write_gate_report(tmp_path, docs, pages=pages)
    before = path.read_text()
    with pytest.raises(SystemExit) as exc:
        gate_report.amend_gate_report(
            str(path), page, {"rounds": 2, "outcome": "pass"})
    message = str(exc.value)
    assert page in message, message
    assert "0" * 64 in message, message
    assert publish.page_sha256(page) in message, message
    assert path.read_text() == before, "a refused amendment must not rewrite it"


def test_gate_report_amended_pending_entry_publishes_on_both_legs(tmp_path, docs):
    """The landings: the reviewer's verdict replaces the pending entry, the
    report records who was amended and what it was before, and the amended
    report is accepted by both legs because it now carries a real verdict."""
    page = "act-now.html"
    path = write_gate_report(
        tmp_path, docs, pages=gate_pages_with_pending(docs, page))
    amended = gate_report.amend_gate_report(
        str(path), page, {"rounds": 2, "outcome": "pass"})
    entry = amended["pages"][page]
    assert entry["outcome"] == "pass", entry
    assert entry["rounds"] == 2, entry
    assert entry["sha256"] == publish.page_sha256(page), entry
    assert amended["pages"]["index.html"]["outcome"] == "pass"
    record = amended["amendments"][-1]
    assert record["page"] == page, record
    assert record["old_outcome"] == "pending", record
    assert record["old_rounds"] == 0, record
    assert record["new_outcome"] == "pass", record
    assert record["new_rounds"] == 2, record
    assert record["date"], record
    for target in (publish.STAGING_REPO, publish.PROD_REPO):
        publish.load_gate_report(str(path), target=target)


def test_gate_report_all_pass_behaviour_unchanged_on_both_legs(tmp_path, docs):
    """The pre-2026-11-24 rule set is not loosened by the pending allowance:
    all-pass stays accepted on either leg, and a missing page or a hash that
    no longer matches is refused on either leg. A pending page keeps its
    content address, so pending is a state of the verdict, never of the
    bytes."""
    path = write_gate_report(tmp_path, docs)
    for target in (publish.STAGING_REPO, publish.PROD_REPO, None):
        model, _, per_page = publish.load_gate_report(str(path), target=target)
        assert "GLM-5.3" in model
        assert per_page.count("r1") == len(gate_source_pages())
        assert "PENDING" not in per_page

    pages = gate_pages(docs)
    del pages["contact.html"]
    missing = write_gate_report(
        tmp_path, docs, pages=pages, name="missing.json")
    moved_pages = gate_pages(docs)
    moved_pages["index.html"]["sha256"] = "0" * 64
    moved = write_gate_report(
        tmp_path, docs, pages=moved_pages, name="moved.json")
    for target in (publish.STAGING_REPO, publish.PROD_REPO):
        with pytest.raises(SystemExit) as exc:
            publish.load_gate_report(str(missing), target=target)
        assert "contact.html" in str(exc.value), str(exc.value)
        with pytest.raises(SystemExit) as exc:
            publish.load_gate_report(str(moved), target=target)
        message = str(exc.value)
        assert "index.html" in message, message
        assert "0" * 64 in message, message

    pending_moved_pages = gate_pages_with_pending(docs)
    pending_moved_pages["act-now.html"]["sha256"] = "0" * 64
    pending_moved = write_gate_report(
        tmp_path, docs, pages=pending_moved_pages, name="pending-moved.json")
    with pytest.raises(SystemExit) as exc:
        publish.load_gate_report(str(pending_moved), target=publish.STAGING_REPO)
    assert "act-now.html" in str(exc.value), str(exc.value)


def run_gate_report_writer(tmp_path, verdicts, name):
    verdicts_path = tmp_path / f"{name}-verdicts.json"
    verdicts_path.write_text(json.dumps(verdicts))
    out = tmp_path / name
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "gate_report.py"),
         "--date", "2026-11-24-93",
         "--review-model", "synthetic/hf:zai-org/GLM-5.3",
         "--review-class", "full",
         "--verdicts", str(verdicts_path),
         "--scope-note", "ledger row 93 pending writer pin",
         "--out", str(out)],
        capture_output=True, text=True), out


def test_gate_report_writer_stamps_pending_without_upgrading_it(tmp_path):
    """The writer takes a pending verdict as it is: outcome pending, rounds 0,
    the page's own hash. It never writes a pass the reviewer did not give, and
    it leaves every other entry alone."""
    page = "act-now.html"
    verdicts = {
        name: {"rounds": 1, "outcome": "pass"}
        for name in gate_source_pages()
    }
    verdicts[page] = {"rounds": 0, "outcome": "pending"}
    proc, out = run_gate_report_writer(tmp_path, verdicts, "pending.json")
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text())
    assert report["pages"][page]["outcome"] == "pending", report["pages"][page]
    assert report["pages"][page]["rounds"] == 0, report["pages"][page]
    assert report["pages"][page]["sha256"] == publish.page_sha256(page)
    assert report["pages"]["index.html"]["outcome"] == "pass"
    assert "amendments" not in report, "the writer never amends by itself"
    publish.load_gate_report(str(out), target=publish.STAGING_REPO)


def test_gate_report_writer_refuses_pending_with_a_round_count(tmp_path):
    """A pending page has no round count yet, so a verdict that says pending
    and rounds 2 contradicts itself. It is refused loud with the page named,
    never quietly coerced to 0."""
    page = "act-now.html"
    verdicts = {
        name: {"rounds": 1, "outcome": "pass"}
        for name in gate_source_pages()
    }
    verdicts[page] = {"rounds": 2, "outcome": "pending"}
    proc, out = run_gate_report_writer(tmp_path, verdicts, "pending-rounds.json")
    assert proc.returncode != 0, proc.stdout
    assert page in proc.stderr, proc.stderr
    assert "rounds" in proc.stderr, proc.stderr
    assert not out.exists(), "a refused report must not be written"


def test_gate_report_writer_emits_publishable_report(tmp_path, docs):
    # The writer (tools/gate_report.py) is the only sanctioned way to make a
    # report now: it stamps current hashes and the class, and the publisher
    # accepts what it writes.
    verdicts = {
        name: {"rounds": 1, "outcome": "pass"}
        for name in gate_source_pages()
    }
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(json.dumps(verdicts))
    out = tmp_path / "report.json"
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "gate_report.py"),
         "--date", "2026-11-04-1",
         "--review-model", "synthetic/hf:zai-org/GLM-5.3",
         "--review-class", "full",
         "--verdicts", str(verdicts_path),
         "--scope-note", "writer round trip",
         "--out", str(out)],
        check=True, capture_output=True, text=True)
    report = json.loads(out.read_text())
    assert report["review_class"] == "full"
    assert report["pages"]["index.html"]["sha256"] == publish.page_sha256("index.html")
    publish.load_gate_report(str(out))


def test_gate_report_writer_refuses_incomplete_verdicts(tmp_path, docs):
    verdicts = {
        name: {"rounds": 1, "outcome": "pass"}
        for name in gate_source_pages()
        if name != "contact.html"
    }
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(json.dumps(verdicts))
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "gate_report.py"),
         "--date", "2026-11-04-1",
         "--review-model", "synthetic/hf:zai-org/GLM-5.3",
         "--review-class", "full",
         "--verdicts", str(verdicts_path),
         "--scope-note", "incomplete",
         "--out", str(tmp_path / "report.json")],
        capture_output=True, text=True)
    assert proc.returncode != 0, proc.stdout
    assert "contact.html" in proc.stderr, proc.stderr


def test_staging_gate_injects_static_stylesheet(tmp_path):
    # 2026-11-04: the gate built its <style> element in JavaScript, filled it,
    # and never appended it. The served head carried no stylesheet at all, so
    # the curtain rendered as a static block at the end of the document, the
    # body stayed readable, and the prompt's focused input scrolled the page
    # to the footer. The rules must arrive as a real <style> tag in the served
    # head, before any script runs.
    tree = tmp_path / "gated"
    tree.mkdir()
    (tree / "index.html").write_text(
        '<!DOCTYPE html><html lang="en"><head><title>x</title></head>'
        "<body><p>hi</p></body></html>", encoding="utf-8")
    assert publish.apply_staging_gate(str(tree), "phrase") == 1
    text = (tree / "index.html").read_text(encoding="utf-8")
    assert "<style>" in text, "served head must carry the gate rules as a real <style> tag"
    assert ".staging-gate body{visibility:hidden!important}" in text
    assert ".staging-gate .staging-bar{visibility:visible" in text, (
        "the staging preview bar stays visible while the gate is locked "
        "(row 128's interplay decision)")
    assert ".staging-gate-overlay{" in text
    assert ".staging-gate-input{" in text
    # the embedded map iframe can take focus as it loads; the gate must take
    # it back so a visitor can type the phrase without clicking
    assert 'window.addEventListener("load"' in text


DATE_TOKEN = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b", re.I)
INVITE_VERB = re.compile(
    # ledger row 125, review round 1: "show up" and "arrive" escaped this list
    # in the petition card's dated summons sentence, so the gate closed the
    # hole - the rule bans the shape, not a verb list, and a new verb cannot
    # slip past
    r"\b(join|come|attend|make plans|be there|rsvp|meet us|gather|show up|arrive)\b",
    re.I)
PAST_MARKER = re.compile(
    r"\b(met|was held|were held|took no vote|has not set|no date|happened|held on|took place)\b",
    re.I)


def past_event_invitations(page, carried=()):
    """Sentences that invite attendance at an event that already happened.

    Rule-based, not a phrase list. Two shapes flag: any past-dated event that
    carries an imperative to attend, and a specific workshop that carries an
    invitation or a deadline. A sentence with a past or open marker
    ("met", "was held", "took no vote", "has not set", "no date") reports the
    record and never flags. The rule fails toward catching too much.

    `carried` names sentences the page copies from a campaign document rather
    than writes; each entry is matched as a lowercase substring of the
    sentence, so an edit to the sentence stops the exemption and the rule
    applies again. Callers pass only what a page actually carries.
    """
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"\s+", " ", text)
    hits = []
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text):
        low = sentence.lower()
        if any(fragment in low for fragment in carried):
            continue
        dated = DATE_TOKEN.search(low)
        invite = INVITE_VERB.search(low)
        past = PAST_MARKER.search(low)
        if dated and invite and not past:
            hits.append(sentence.strip()[:180])
            continue
        if "workshop" in low and not past:
            specific = (dated or re.search(r"\bthe\s+(city council\s+)?workshop\b", low)
                        or "before the workshop" in low or "at the workshop" in low)
            if specific and invite:
                hits.append(sentence.strip()[:180])
    return hits


# 2026-11-24 (toolkit reference page): one invitation on the page is carried,
# not written. The campaign document's letter guidance tells residents what
# they can do — "Read the Tank Farms Toolkit, attend the Dec. 1 workshop and
# other public meetings, submit public comments, and share your own story" —
# and the workshop is still ahead of the page (Dec. 1, after a Nov. 24 build).
# The exemption names the sentence's opening, so a rewrite stops matching and
# the rule applies to it again.
CARRIED_INVITATIONS = {
    "toolkit.html": ("what residents can do: read the tank farms toolkit",),
}


def test_no_past_event_invitations(docs):
    # No page may invite anyone to an event that already happened. Rule-based
    # so a new verb, a new event name or a date-first phrasing cannot slip past
    # an exact-string list; past-tense reports are allowed.
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        hits = past_event_invitations(
            read(docs, name), CARRIED_INVITATIONS.get(name, ()))
        assert not hits, f"{name}: past-event invitation: {hits}"


def test_act_now_action_links_are_the_cards(docs):
    """The two action links are the card grid's now; the button pair is gone.

    The rulings on these two links, in the order they were made.

    2026-11-24 (row 88, the consolidation): the operator said "act-now.html has
    too many button variants, it's visually confusing", so Donate and Report an
    odor stopped carrying their own border, fill, colour, padding, type and
    underline reset and became members of the standard .btn family, keeping
    only the local layout, the square corners the operator asked for on row 82,
    the shared 14rem width floor and the focus ring. Consolidation was that
    leg's whole ground, and no card existed on this page when it merged, so it
    neither created nor endorsed any pair-plus-cards split: it moved the pair
    into the family and left it where it stood.

    2026-11-24 (row 92, the cards): the operator then asked for the card
    template used elsewhere on the site, "I want the underlying template for
    the card format used in multiple places on the site. The actual content on
    Our Work is fine, I just want similar cards on Act Now for Donate and
    Report an Odor." That leg added the cards BELOW the pair rather than
    replacing it, and row 92's own ledger record is where the split is first
    stated: the upgrade keeps the pair "so the same two destinations get a
    quick button and a fuller description rather than the buttons being
    replaced". The quick action in the pair and the richer description in the
    cards are row 92's grounds, not row 88's.

    # 2026-11-24 (row 106, the restructure): the operator's sketch moved the
    # Email the Council ask into the teal callout and turned the grid's top
    # row into two CTA tiles (Tell your story, Sign the petition), with Report
    # an odor and Donate as the bottom row. The Sign now pill stopped being a
    # free-standing control and moved into the petition tile; .btn--ghost
    # keeps its class because five other pages still render it (index,
    # our-campaigns, tank-farms, report-an-odor, share-your-story) — audited
    # the way link-row--buttons was, and kept because its users are named.
    #
    # 2026-11-24 (row 109, the swap): the featured block inverts to the green
    # panel (the island is gone), the grid's four cards share one white card
    # style, and the two CTA tiles lose their .btn--light actions for the
    # cards' own .card__more grammar, distinguished only by the glow. This
    # page now renders exactly one family member: the panel's .btn--cta.
    """
    act = read(docs, "act-now.html")
    css = read(docs, "styles.css")

    # the pair is gone: its markup and both of its anchors
    assert '<ul class="link-row link-row--buttons">' not in act
    assert '<a class="btn btn--ghost" href="donate.html">Donate</a>' not in act
    assert '<a class="btn btn--ghost" href="report-an-odor.html">Report an odor</a>' not in act

    # all four destinations survive, exactly once each in the page body,
    # through the card grid's own calls to action
    body = act[act.index('<div class="prose">'):act.index("</section>")]
    for href in ("donate.html", "report-an-odor.html", "share-your-story.html"):
        assert body.count(f'href="{href}"') == 1, (
            f"{href} must have exactly one way through the page body now")
    # recorded correction (2026-11-25, ledger row 125): the delivered
    # petition's form is offered nowhere; the forward card links to the page's
    # own workshop facts instead
    assert body.count('href="https://docs.google.com/forms/d/e/1FAIpQLSfPIeWgfe7GGgNqhxVatcPAEffmqo5jJJ-iGYcCh4ltcQsZcA/viewform"') == 0
    # row 129: the card's act-now self-link went with the removed block
    assert body.count('href="act-now.html"') == 0
    assert '<a class="card__more" href="donate.html">DONATE →</a>' in body
    assert '<a class="card__more" href="report-an-odor.html">REPORT AN ODOR →</a>' in body

    # the cards sit directly under the featured panel now, so the grid
    # opens the prose column the panel closes (row 106: the grid carries
    # the restructure's modifier, and the glowing cards are its first children)
    assert '<div class="prose">\n      <div class="card-grid card-grid--act">' in act
    assert body.index('class="card card--glow"') < body.index('href="report-an-odor.html"')

    # the pair's stylesheet scope had Act now as its only user, so it went with
    # the pair instead of being left dead: no rule and no modifier anywhere
    assert "link-row--buttons" not in css
    users = [name for name in html_files(docs)
             if "link-row--buttons" in read(docs, name)]
    assert users == [], f"the removed button modifier is still on {users}"

    # the retired petition-strip modifier got the same audit (row 106): it had
    # no rules of its own anywhere, act-now.html was its only user, and the
    # petition it named moved out of the callout into its own tile
    assert "petition-strip" not in css
    strip_users = [name for name in html_files(docs)
                   if "petition-strip" in read(docs, name)]
    assert strip_users == [], f"the retired petition-strip modifier is still on {strip_users}"

    # the family is still declared: this page renders the panel's .btn--cta;
    # .btn--ghost's five users are other pages; .btn--light is declared but no
    # page renders it today, and the family carries it ready (the row-95
    # ring comment's position). The retarget that removed the pair dropped
    # the suite's only existence check on these blocks (ledger row 94
    # follow-up), so it lands back here rather than nowhere: a page that
    # renders a family member with no family rule behind it is a broken
    # button, and nothing else would go red.
    for cls in (".btn {", ".btn--cta {", ".btn--light {", ".btn--ghost {"):
        assert cls in css, f"the standard family must declare {cls}"


def test_act_now_featured_panel_is_the_green_field(docs):
    """Row 109, instruction 1: the featured block inverts to white-on-green.
    The campaign teal field (the .section--teal precedent) carries the ask
    paragraph, the Email the Council line and the CTA as white text on
    --teal-900; the white island from the row-106 sketch is gone, and the
    featured block IS the green panel itself, not a panel inside it. The
    hear-your-voice and petition copy stay out in their cards."""
    act = read(docs, "act-now.html")
    css = read(docs, "styles.css")
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "site", "pages", "act-now.html"), encoding="utf-8").read()
    start = act.index('<div class="callout callout--ask">')
    end = act.index('<div class="prose">')
    panel = act[start:end]
    assert "ask-island" not in act and "ask-island" not in css, (
        "the white island is gone; the panel IS the green field")
    # recorded correction (2026-11-25, ledger row 130): the bold "Current
    # ask:" label dropped with the lead rewrite - the green box opens on the
    # ask sentence itself and the two ask-steps carry their own bold labels
    assert "Current ask:" not in panel
    assert "<strong>Email the Council</strong>" in panel
    assert "<strong>Wear green</strong>" in panel
    # the source page opts the CTA into the build's blockquote fill, and the
    # built page carries the populated body, so the mechanism found its
    # blockquote after the inversion
    assert 'data-mailto-body="blockquote"' in src
    assert "body=" in panel
    # the copy that lives in the cards stays out of the panel
    assert "We want to hear your voice" not in panel
    assert "Climate Resilience Petition" not in panel
    # the panel is the teal field with white ink, the section--teal precedent,
    # and it keeps the gap acceptance item: more space below the panel than
    # the base callout's 1.2em, so the grid visibly separates from it
    assert re.search(r"\.callout--ask \{[^}]*background: var\(--teal-900\)", css, re.S)
    assert re.search(r"\.callout--ask \{[^}]*color: #fff", css, re.S)
    assert re.search(r"\.callout--ask \{[^}]*margin-bottom: 2\.4em", css, re.S)
    assert re.search(r"\.callout \{[^}]*margin: 1\.2em 0", css, re.S), (
        "the base callout's 1.2em margin is the 'before' the gap is measured against")
    # the CTA's ring follows the family's dark-surface convention on the panel
    assert ".callout--ask .btn:focus-visible { outline-color: var(--cyan-soft); }" in css


def test_act_now_primary_cta_holds_two_equal_steps(docs):
    """Row 109, instruction 1: the primary CTA holds two steps of equal
    weight — (1) Email the Council, (2) Wear green and come to the City
    Council meeting — laid out side by side above 720px and stacked below,
    both steps in the same lede type. The show-up step's copy is composed
    from the banner facts and is agent-composed, flagged in the pull request."""
    act = read(docs, "act-now.html")
    css = read(docs, "styles.css")
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "site", "pages", "act-now.html"), encoding="utf-8").read()
    start = act.index('<div class="ask-steps">')
    end = act.index("</div>", act.index("ask-step", start + 20))
    steps = act[start:act.index('<div class="prose">')]
    assert steps.count('class="ask-step"') == 2
    # step one keeps its copy and its lede weight; since the operator's
    # send-back (see the per-column pin below) its button sits in its own
    # ask-step again, so the blockquote-fill mechanism is asserted in the
    # per-column pin
    assert "<strong>Email the Council</strong>" in steps
    # step two: the show-up ask, composed from the banner facts
    assert "<strong>Wear green</strong>" in steps
    assert "come to the City Council meeting" in steps
    assert "Tuesday, Dec. 1 at 6:30 p.m. in City Hall Council Chambers, 25 Cottage Road" in steps
    # equal weight: the two-column grid at 720px and above, one column below
    assert re.search(r"\.ask-steps \{[^}]*grid-template-columns: 1fr", css, re.S)
    assert re.search(r"@media \(min-width: 720px\) \{\s*\.ask-steps \{ grid-template-columns: 1fr 1fr; \}", css, re.S)


def test_act_now_each_ask_centers_its_own_control(docs):
    """Operator send-back, 2026-11-25 (ledger row 129 amendment), verbatim in
    substance: "I want each button centered below the paragraph that makes
    the ask." The shared centered .ask-actions row this file pinned earlier
    came apart in practice, so it is gone: each ask column carries its own
    control centered beneath that column's paragraph — the Email button under
    the Email-the-Council column, the Add to Calendar dropdown under the
    Wear-green column — and on mobile each button stays centered under its
    own ask as the columns stack, in order. The screenshot's red arrows and
    overlay rectangles mark intent only (which button belongs to which ask,
    roughly where); geometry and colour still come from the design system.
    """
    act = read(docs, "act-now.html")
    css = read(docs, "styles.css")
    steps = act[act.index('<div class="ask-steps">'):act.index('<div class="prose">')]
    assert steps.count('class="ask-step"') == 2
    # the shared row is gone from the page and the stylesheet
    assert 'class="ask-actions"' not in act
    first = steps[steps.index("<strong>Email the Council</strong>"):]
    first = first[:first.index("<strong>Wear green</strong>")]
    second = steps[steps.index("<strong>Wear green</strong>"):]
    # each column carries exactly one control, centered beneath its paragraph
    assert first.count('class="btn btn--cta"') == 1
    assert '<details class="cal-add">' in second
    assert steps.count('class="ask-step__action"') == 2
    # the action line follows its column's ask paragraph in document flow
    assert first.index("<strong>Email the Council</strong>") < first.index('class="ask-step__action"')
    assert second.index("<strong>Wear green</strong>") < second.index('class="ask-step__action"')
    # the CTA keeps its blockquote-fill mechanism in its column: the source
    # page opts in with the marker and the built page ships the populated body
    assert 'data-mailto-body="blockquote"' in _act_now_source()
    assert "body=" in first
    # centered: the action line centers its control; the paragraph above
    # keeps its own alignment, and the shared-row rules are gone (the
    # stylesheet may name the history in prose, but no .ask-actions rule
    # selector may remain)
    assert re.search(r"\.ask-step__action \{[^}]*text-align: center", css, re.S)
    assert not re.search(r"\.ask-actions[\s{,]", css)


def test_act_now_calendar_dropdown_is_native_details(docs):
    """Operator directive, 2026-11-25 (ledger row 129): an Add to Calendar
    dropdown with three entries and NO third-party widget or external
    calendar service script. The mechanism is the native <details>/<summary>
    element: its keyboard toggle (Enter/Space on the focused summary) and its
    screen-reader labeling (the summary is a native button-role toggle whose
    accessible name is its text) are the element's own semantics, so no
    script and no ARIA repair ships here. Entries are plain verbs.
    """
    act = read(docs, "act-now.html")
    start = act.index('<details class="cal-add">')
    end = act.index("</details>", start)
    dropdown = act[start:end]
    # the native toggle, labeled for screen readers by its own text
    assert '<summary class="btn btn--light">Add to Calendar</summary>' in dropdown
    # three entries, plain verbs
    assert ">Google Calendar</a>" in dropdown
    assert ">Apple / download .ics</a>" in dropdown
    assert "Other" in dropdown and "copy link" in dropdown
    # the Google entry opens in a new tab and cannot leak window references
    google = re.search(r'<a [^>]*href="https://calendar\.google\.com/[^"]*"[^>]*>', dropdown).group(0)
    assert 'target="_blank"' in google
    assert 'rel="noopener"' in google
    # the .ics entry points at the static asset built into the tree
    assert 'href="assets/calendar/city-council-workshop-2026-12-01.ics"' in dropdown
    # the copy-link entry shows the absolute ICS URL as selectable text
    assert "https://www.protectsouthportland.org/assets/calendar/city-council-workshop-2026-12-01.ics" in dropdown
    assert "Copy this link into your calendar app." in dropdown
    # no third-party widget and no external calendar service script: the
    # page's only script is the staging bar the build stamps on every page,
    # and no add-to-calendar widget vendor appears anywhere
    for script in re.findall(r"<script[^>]*src=\"([^\"]+)\"", act):
        assert script == "assets/js/staging-bar.js", script
    for vendor in ("addtocalendar", "calendly", "eventbrite", "calendarlabs",
                   "addevent.com", "script.addthis"):
        assert vendor not in act.lower(), vendor
    # the page shows only the recorded start time; the 6:30-8:30 block is the
    # named duration assumption and lives in the calendar entry alone
    assert "8:30" not in act
    assert "6:30 p.m." in act


def test_act_now_google_calendar_url_carries_the_right_utc_dates(docs):
    """Operator directive, 2026-11-25 (ledger row 129): the Google Calendar
    entry uses the standard no-auth template URL for the fixed event —
    Tuesday, Dec. 1, 6:30 p.m., City Hall Council Chambers, 25 Cottage Road,
    timezone America/New_York. December is EST (UTC-5), so 6:30 p.m. local is
    23:30Z and the two-hour block runs to 01:30Z on Dec. 2.
    """
    act = read(docs, "act-now.html")
    start = act.index('<details class="cal-add">')
    end = act.index("</details>", start)
    dropdown = act[start:end]
    href = re.search(r'href="(https://calendar\.google\.com/[^"]+)"', dropdown).group(1)
    url = html.unescape(href)
    assert url.startswith("https://calendar.google.com/render?action=TEMPLATE&")
    params = dict(part.partition("=")[::2] for part in url.split("?", 1)[1].split("&"))
    assert params["action"] == "TEMPLATE"
    assert params["dates"] == "20261201T233000Z/20261202T013000Z"
    assert "City%20Council%20Workshop" in params["text"]
    assert "25%20Cottage%20Road" in params["location"]
    # the invite carries the ask, not stage guidance
    assert "{{" not in url and "}}" not in url


def _act_now_source():
    return open(os.path.join(ROOT, "site", "pages", "act-now.html"),
                encoding="utf-8").read()


def test_calendar_ics_asset_parses_with_the_right_event(docs):
    """Operator directive, 2026-11-25 (ledger row 129): the Apple/other-clients
    entry downloads a static .ics asset shipped in the built tree, TZID
    America/New_York, carrying SUMMARY, LOCATION, DTSTART and DTEND for the
    Dec. 1 workshop. Pages serves .ics as text/calendar; the served
    content-type is verified by the orchestrator's serve turn and is stated
    as pending in this leg's pull request.
    """
    path = os.path.join(docs, "assets", "calendar",
                        "city-council-workshop-2026-12-01.ics")
    raw = open(path, "rb").read()
    text = raw.decode("utf-8")
    # RFC 5545 wants CRLF
    assert "\r\n" in text and "\n\n" not in text.replace("\r\n", "")
    lines = text.replace("\r\n", "\n").splitlines()
    unfolded = []
    for line in lines:
        if line[:1] in (" ", "\t") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    joined = "\n".join(unfolded)
    assert "BEGIN:VCALENDAR" in joined and "END:VCALENDAR" in joined
    assert "BEGIN:VTIMEZONE" in joined and "TZID:America/New_York" in joined
    event = joined[joined.index("BEGIN:VEVENT"):joined.index("END:VEVENT")]
    assert event.count("DTSTART;TZID=America/New_York:20261201T183000") == 1
    assert event.count("DTEND;TZID=America/New_York:20261201T203000") == 1
    assert "SUMMARY:City Council workshop (Protect South Portland)" in event
    # text values escape their commas per RFC 5545; unescape before comparing
    unescaped = event.replace("\\,", ",")
    assert "LOCATION:City Hall Council Chambers, 25 Cottage Road, South Portland, ME" in unescaped
    assert "UID:" in event and "DTSTAMP:" in event


def test_act_now_cta_tiles_lead_the_grid(docs):
    """Row 109, instruction 1: the two CTA tiles become the SAME card style
    as Report an odor and Donate — white cards, same geometry, same
    head/body/action grammar — distinguished only by a faint blue glow built
    from palette tokens, no fill, no dark teal. The bottom row is the
    existing Report an odor and Donate text cards, unchanged in content."""
    act = read(docs, "act-now.html")
    css = read(docs, "styles.css")
    body = act[act.index('<div class="prose">'):act.index("</section>")]

    story = body[body.index('class="card card--glow"'):body.index("SHARE YOUR STORY →</a>")]
    assert "Tell your story" in story
    assert "We want to hear your voice" in story
    assert 'href="share-your-story.html"' in story

    # recorded corrections: the petition card left (row 125) and its
    # replacement removed with the operator's redundancy ruling (row 129) -
    # the green box carries the ask once, and the grid carries three cards
    assert "Dec. 1: the council weighs what to require" not in body
    assert "WORKSHOP DETAILS" not in body
    assert body.count('class="card card--glow"') == 1
    assert body.index("Tell your story</h2>") < body.index("Report an odor</h2>") < body.index("Donate</h2>")
    # the grid-hole closure: the first card spans the full row (row 129)
    css = read(docs, "styles.css")
    assert ".card-grid--act .card:first-child { grid-column: 1 / -1; }" in css
    # the tile actions are the cards' own card__more grammar, not buttons.
    # Recorded correction (2026-11-25, ledger row 129), the operator's
    # directive: the page gains an Add to Calendar dropdown, and its trigger
    # renders the previously unrendered `.btn--light` family member on the
    # panel. The pin's intent is unchanged and still asserted below: the four
    # cards' actions stay card__more links; the only btn--light on the page is
    # the calendar summary, never a card action.
    assert act.count("btn--light") == 1
    assert '<summary class="btn btn--light">Add to Calendar</summary>' in act
    assert '<a class="card__more" href="share-your-story.html">SHARE YOUR STORY →</a>' in body
    assert "WORKSHOP DETAILS" not in body
    # the glow is the only difference, and it is built from palette tokens
    assert ".card--glow { box-shadow: 0 0 0 4px var(--cyan-soft), var(--shadow); }" in css
    assert not re.search(r"\.card--glow \{[^}]*background", css, re.S), (
        "the glow variant must not fill the card; the four cards share one style")


def test_the_wear_green_ask_agrees_between_banner_and_act_now(docs):
    """Row 109, consistency rule: the wearing-green ask and the banner are the
    same fact in two places, so the wording stays consistent. The homepage
    hero meta line (the block the operator calls the banner; renamed
    hero__meta when the banner became the hero) and the featured panel's
    show-up step must agree on the ask's verbs and every fact: the date, the
    time and the venue (City Hall Council Chambers, 25 Cottage Road, ruling
    dec_huccqekz7fjt). Any divergence is a named finding, not a style choice.

    2026-11-24 (ledger row 117), retargeted as a recorded correction: the
    operator directed the homepage's first text to the feedback-board filer's
    rewrite, nearly verbatim, so the hero's own ask sentence is now the
    filer's "Wear green!" line rather than the verb-pair sentence the strip
    and the featured block carry. The pin's intent is unchanged and still
    asserted: the homepage carries the wear-green ask and every fact, and the
    facts agree everywhere. The wording divergence is operator-directed (the
    filer's paragraph is the instruction) and named in the PR.
    """
    act = read(docs, "act-now.html")
    idx = read(docs, "index.html")
    # the filer's lead under the headline, with its wear-green ask
    assert "We know more than ever about how the tank farms are affecting" in idx
    assert "Wear green!" in idx
    # the featured panel's show-up step carries the same verbs and all facts
    assert "Wear green" in act and "come to the City Council meeting" in act
    for fact in ("Tuesday, Dec. 1", "6:30 p.m.", "City Hall Council Chambers, 25 Cottage Road"):
        assert fact in idx, fact
        assert fact in act, fact
    # the alert strip carries the same facts on every page, so nothing contradicts
    assert "Tuesday, Dec. 1 at 6:30 p.m. in City Hall Council Chambers, 25 Cottage Road" in act
    # act-now's own detailed paragraph keeps the same facts, so nothing on
    # the page contradicts the ask
    assert act.count("City Hall Council Chambers") >= 2


def test_no_double_brace_stage_guidance_ships_anywhere(docs):
    """AGENTS.md hard constraint 5 (operator ruling, 2026-11-24): text inside
    {{...}} in the campaign copy documents is stage guidance addressed to the
    agent, never copy. The built tree carries neither the braces nor their
    words, so the marker class is scanned for directly."""
    for name in html_files(docs):
        page = read(docs, name)
        assert "{{" not in page and "}}" not in page, (
            f"{name}: double-brace stage guidance reached the built page")


def test_act_now_past_tense_and_one_email_action(docs):
    # Ruling B (2026-11-05): the page asks for the outcome, not an instrument.
    # Retargeted 2026-11-24 (ledger row 121) as a recorded correction: the
    # operator ruled "specifically, I meant that we should be forward-looking,
    # not referencing the Oct 27 meeting. Don't repeat homepage text that's not
    # directly relevant to that goal." The past-tense opener retired; the pin
    # now follows the forward opener it became. The substance is unchanged and
    # still asserted: the page carries one real email-the-Council action, the
    # Dec. 1 workshop, and the special-counsel ask, with no invitation to a
    # past event.
    act = read(docs, "act-now.html")
    # 2026-11-24: read the tag-stripped text, so emphasis markup can move
    # inside the sentence without the ruling pin breaking on a <strong>.
    assert "The City Council is considering what — if any — action to take with the tank farms" in reading_text(act)
    assert "Staff and special counsel will be delivering a report at an upcoming workshop." in reading_text(act)
    assert "Oct. 27" not in act
    assert "Dec. 1" in act
    assert "no date has been set" not in act
    assert "require better technology at the tank farms" in act
    assert "make public what special counsel advises" in act
    assert "legal opinion the city is waiting on" not in act
    assert "special counsel" in act
    # the invitation class: gone
    assert "Make plans to come to the City Council workshop" not in act
    assert "before the workshop" not in act
    assert "637 Highland Ave" not in act
    # the rejected instrument: not named, not implied
    assert "municipal license" not in act
    assert "license the tank farms" not in act
    assert "pressure the DEP to use the existing licensing process" not in act
    # one real action: general address plus the seven councilors, prefilled subject
    m = re.search(r'href="(mailto:citycouncil@southportland\.gov\?cc=[^"]+subject=[^"]+)"', act)
    assert m, "act-now.html must carry one prefilled email-the-Council mailto action"
    # The cc list is the current council: every roster alias, and nothing
    # else. In particular no unverified alias for an incoming member.
    for _, _, alias, in_cc in ROW47_COUNCILORS:
        assert f"{alias}%40southportland.gov" in m.group(1), alias
    assert "eclancy%40southportland.gov" not in m.group(1), (
        "the cc list must reach the current council, and an incoming "
        "member's unverified alias must not ride along")
    # the ready-to-send message and the roster still ship
    assert "Dear Councilors," in act
    assert "citycouncil@southportland.gov" in act


def test_homepage_and_tank_farms_lead_with_the_next_workshop(docs):
    # Operator ruling 2026-11-05: the banner and the duplicated callout bullets
    # lead with the live fact and keep the ruling-B ask. The Oct. 27 date stays
    # only where the copy describes the past workshop.
    # 2026-11-20: the live fact changed from "no date set" to the Dec. 1
    # workshop, so the pinned banner text moves with it. The rule is unchanged:
    # lead with what is true now, keep the ask, never an invitation to the past.
    # 2026-11-24 (ledger row 117), retargeted as a recorded correction: the
    # operator directed the hero's first text to the feedback-board filer's
    # rewrite, so the live date and the ask now lead as the filer's paragraph.
    # 2026-11-24 (ledger row 121), retargeted again as a recorded correction:
    # the operator ruled "specifically, I meant that we should be
    # forward-looking, not referencing the Oct 27 meeting. Don't repeat
    # homepage text that's not directly relevant to that goal." The callout's
    # no-vote bullet retired; past_state now reads the forward campaign line
    # the operator's example named. The ruling is unchanged: a live date, a
    # real ask, no invitation to a past event.
    hero_lead = ("We know more than ever about how the tank farms are "
                 "affecting this community.")
    hero_ask = ("Email the Council and ask it to require better technology at "
                "the tank farms.")
    bullet_state = ("The Council plans its next workshop for Tuesday, Dec. 1 "
                    "at 6:30 p.m.")
    past_state = ("The Council is weighing what to require at the tank farms")
    idx = read(docs, "index.html")
    tank = read(docs, "tank-farms.html")
    # 2026-11-24: copy pins read tag-stripped text, so the bold pass can move
    # emphasis inside these sentences without weakening the ruling they pin.
    idx_text = reading_text(idx)
    tank_text = reading_text(tank)
    assert hero_lead in idx_text
    assert hero_ask in idx_text
    assert bullet_state in idx_text
    assert past_state in idx_text
    # the filer's workshop sentence carries the facts without inviting a past
    # event, and the two bold facility names survive in the readings paragraph
    assert ("Write to the city council today and attend the next city council "
            "workshop") in idx_text
    assert "Wear green!" in idx_text
    assert idx_text.count("South Portland Terminal") >= 1 and "Citgo on Mechanic Street" in idx_text
    assert "require better technology at the tank farms" in idx
    assert "make public what special counsel advises" in idx
    assert "637 Highland Ave" not in idx
    assert bullet_state in tank_text
    assert "require better technology at the tank farms" in tank
    assert "make public what special counsel advises" in tank
    assert "637 Highland Ave" not in tank
    assert "email the Council now" in tank


def test_about_workshop_is_past_tense(docs):
    # The reviewer caught this variant on 2026-11-05: "Come to the ... workshop
    # on Tuesday, Oct. 27 ... and email the Council before it." Same retired
    # invitation class, different verb, so the sitewide guard was widened.
    # Retargeted 2026-11-24 (ledger row 123): the operator superseded the scope
    # ruling, verbatim: "no, the homepage should already have been edited to
    # not include the Oct 27 explicit reference -- ALL CTA and ask-adjacent
    # copy should be forward looking, as in the new voice guide", so the
    # about page's current-focus paragraph no longer retells the Oct. 27
    # no-vote; it reads "The council is weighing what to require at the tank
    # farms, and its next workshop is Tuesday, Dec. 1".
    about = read(docs, "about.html")
    assert "The council is weighing what to require at the tank farms" in about
    assert "Oct. 27" not in about
    assert "took no vote" not in about
    assert "Come to the City Council workshop" not in about
    assert "637 Highland Ave" not in about


def test_act_now_lead_is_the_row130_rewrite(docs):
    # ledger row 130 (2026-11-25), write phase: the operator's target text
    # verbatim with two mandated corrections - (1) grammar, the directive's
    # typo ships as "is considering"; (2) typography, the double-hyphen
    # dashes ship as the page's own spaced em-dash entity convention (the
    # councilor list and the calendar menu use "Name &mdash; District"), with
    # the site's em-dash allowance on page copy only; and (3) the fact check
    # it mandated: the lead's date, time, venue and the email instruction
    # survive elsewhere on this page, asserted below
    act = read(docs, "act-now.html")
    # the corrected target text, verbatim
    assert "The City Council is considering what &mdash; if any &mdash; action to take with the tank farms. Staff and special counsel will be delivering a report at an upcoming workshop." in act
    # the directive typo guard: the uncorrected "is consider" never ships
    assert "City Council is consider " not in act
    # the lead label decision: the bold "Current ask:" label is dropped, the
    # box opens on the ask itself (named in the PR)
    assert "Current ask:" not in act
    # survival (a): the date, time and venue live in the wear-green step
    assert "The meeting is Tuesday, Dec. 1 at 6:30 p.m. in City Hall Council Chambers, 25 Cottage Road." in act
    # survival (b): the email instruction lives in the ask-step lede and the
    # ready-to-send flow
    assert "<strong>Email the Council</strong> and ask it to require better technology" in act
    assert "Start with the ready-to-send message above, then send to the addresses below." in act


def test_punchlist_a5_campaign_card_is_current(docs):
    # Nov. 5 meeting, A5: the tank card described the Oct. 27 workshop in the
    # present tense. The campaign page now points at the standing status.
    page = read(docs, "our-campaigns.html")
    assert "where the campaign stands" in page
    assert "Oct. 27 City Council workshop" not in page



def test_buttons_keep_breathing_room(docs):
    """Recurring failure mode, fixed at source 2026-11-23.

    A call-to-action wrapped in a <p> whose margins were zeroed sat flush
    against the text above and below it, which read as a spacing bug rather
    than a button. Two guards: no paragraph that wraps a button may zero its
    own margins, and the .btn rule must carry its own vertical margin and
    padding so no ancestor can squash it.
    """
    import re as _re
    flush = _re.compile(
        r'<p[^>]*style="[^"]*margin[^"]*0[^"]*"[^>]*>\s*<a class="btn', _re.I)
    for name in html_files(docs):
        m = flush.search(read(docs, name))
        assert not m, (
            f"{name}: a button wrapped in a zero-margin paragraph: "
            f"{m.group(0)[:120] if m else ''}")
    css = open(os.path.join(ROOT, "site", "styles.css"), encoding="utf-8").read()
    rule = _re.search(r"\.btn \{(.*?)\}", css, _re.S)
    assert rule, ".btn rule missing from styles.css"
    body = rule.group(1)
    margin = _re.search(r"margin:\s*([0-9.]+)(rem|px)\s+0", body)
    assert margin, ".btn must declare its own vertical margin"
    assert float(margin.group(1)) > 0, ".btn vertical margin must be non-zero"
    padding = _re.search(r"padding:\s*([0-9.]+)px", body)
    assert padding and int(padding.group(1)) >= 8, (
        ".btn needs at least 8px of vertical padding")


# ---- callout layout guard ------------------------------------------------

_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})


class _ElementScanner(HTMLParser):
    """A tiny element tree: enough of one to ask which elements are siblings.

    Each element records its parent, the siblings that precede it, and whether
    anything but whitespace sat between this element and the one before it.
    Callout elements also collect their text, so a failure can quote them.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {
            "tag": "(document)", "class": "", "classes": [], "children": [],
            "text": [], "pending_text": False,
        }
        self.elements = []
        self._open = [self.root]

    def _parent(self):
        return self._open[-1]

    def handle_starttag(self, tag, attrs):
        parent = self._parent()
        classes = ""
        for key, value in attrs:
            if key == "class":
                classes = value or ""
        element = {
            "tag": tag,
            "class": classes,
            "classes": classes.split(),
            "children": [],
            "text": [],
            # non-whitespace text between the previous sibling and this one
            "detached": parent["pending_text"],
            "pending_text": False,
        }
        parent["children"].append(element)
        parent["pending_text"] = False
        self.elements.append(element)
        # a void tag is still a child: an <img> or <br> between two callouts
        # breaks their adjacency, so it gets recorded and never opened
        if tag not in _VOID_TAGS:
            self._open.append(element)
        self._mark_word_break()

    def _mark_word_break(self):
        # text on either side of a tag is separate words to a reader, so an
        # element boundary becomes a space in a callout's quoted preview
        for element in self._open:
            if "callout" in element["classes"]:
                element["text"].append(" ")

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth]["tag"] == tag:
                del self._open[depth:]
                self._mark_word_break()
                return

    def handle_data(self, data):
        if not data.strip():
            return
        self._parent()["pending_text"] = True
        for element in self._open:
            if "callout" in element["classes"]:
                element["text"].append(data)


def _callout_preview(element):
    text = " ".join("".join(element["text"]).split())
    # a tag boundary becomes a space, but punctuation glued to its own tag
    # (<a>...</a>: like this) keeps its colon attached
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text[:60]


def _stacked_callouts(scan):
    """Pairs of callout elements that are adjacent siblings in one container."""
    pairs = []
    for element in [scan.root] + scan.elements:
        children = element["children"]
        for first, second in zip(children, children[1:]):
            if ("callout" in first["classes"] and "callout" in second["classes"]
                    and not second["detached"]):
                pairs.append((element, first, second))
    return pairs


def test_no_stacked_callouts(docs):
    """Design UAT guard (operator report, 2026-11-23): callouts exist to give
    one thing emphasis, so two of them stacked directly on top of each other
    cancel each other out and neither reads as highlighted.

    A stack here is two `.callout` elements that are adjacent siblings inside
    the same container, with nothing but whitespace between the closing tag of
    the first and the opening tag of the second. A callout nested inside
    another callout is a different shape (it reads as one box, not two) and is
    not what this catches. Neither is a callout separated from the next by
    another element or by text, because then the reader gets a break.

    Cheap by design: html.parser only, no browser, so a pytest-only CI runner
    can carry it.
    """
    violations = []
    for name in html_files(docs):
        scan = _ElementScanner()
        scan.feed(read(docs, name))
        scan.close()
        for container, first, second in _stacked_callouts(scan):
            where = '<{} class="{}">'.format(container["tag"], container["class"])
            violations.append(
                '{}: stacked callouts inside {}: "{}" then "{}"'.format(
                    name, where, _callout_preview(first), _callout_preview(second)))
    assert not violations, (
        "adjacent callouts split the emphasis they are meant to give; merge "
        "them into one box or demote one to plain prose\n" + "\n".join(violations))


# ---- bold emphasis guard -------------------------------------------------

_BOLD_BLOCK_TAGS = frozenset({"p", "li"})
_BOLD_TAGS = frozenset({"strong", "b"})
# A nested box starts its own reading unit, so its words never count toward
# the enclosing paragraph or list item (a sub-list inside an <li>, say).
_BOLD_NESTED_BOXES = frozenset({
    "p", "li", "ul", "ol", "div", "section", "article", "aside", "header",
    "footer", "main", "nav", "figure", "figcaption", "blockquote", "table",
    "tr", "td", "th", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
})

BOLD_BLOCK_MIN_WORDS = 10
BOLD_RUN_MAX_WORDS = 8
BOLD_SHARE_MAX = 0.25
# Run count, added 2026-11-24 after the share and length limits passed a
# paragraph that still read heavy: five short runs in a long paragraph clear
# both thresholds and still read as a wall of emphasis. A paragraph carries at
# most two runs; a callout, list item or heading carries one.
BOLD_RUNS_PARAGRAPH_MAX = 2
BOLD_RUNS_TIGHT_MAX = 1
_BOLD_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


class _BoldTree(HTMLParser):
    """An element tree with text leaves: enough to measure bold in a block."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "(document)", "children": []}
        self._open = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "children": [], "attrs": dict(attrs)}
        self._open[-1]["children"].append(node)
        if tag not in _VOID_TAGS:
            self._open.append(node)

    def handle_startendtag(self, tag, attrs):
        self._open[-1]["children"].append(
            {"tag": tag, "children": [], "attrs": dict(attrs)})

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth]["tag"] == tag:
                del self._open[depth:]
                return

    def handle_data(self, data):
        self._open[-1]["children"].append(data)


def _bold_text(node, stop_at_box=False):
    """Text under a node; with stop_at_box, a nested block's words are skipped."""
    pieces = []
    for child in node["children"]:
        if isinstance(child, str):
            pieces.append(child)
        elif child["tag"] == "br":
            pieces.append(" ")
        elif stop_at_box and child["tag"] in _BOLD_NESTED_BOXES:
            continue
        else:
            pieces.append(_bold_text(child, stop_at_box))
    return "".join(pieces)


def _bold_words(text):
    """Whitespace-separated tokens that carry a letter or digit (not a dash)."""
    return [token for token in re.split(r"\s+", html.unescape(text))
            if re.search(r"[0-9A-Za-z]", token)]


def _bold_runs(node):
    """One entry per <strong>/<b> element: a run is an element, not its pieces."""
    runs = []

    def walk(current):
        for child in current["children"]:
            if isinstance(child, str):
                continue
            if child["tag"] in _BOLD_TAGS:
                runs.append(_bold_words(_bold_text(child, stop_at_box=True)))
            else:
                walk(child)

    walk(node)
    return runs


def _bold_blocks(node):
    """Every <p>/<li>, with whether it sits inside a callout box."""
    blocks = []

    def walk(current, in_callout):
        for child in current["children"]:
            if isinstance(child, str):
                continue
            callout = in_callout or "callout" in (
                child.get("attrs", {}).get("class") or "")
            if child["tag"] in _BOLD_BLOCK_TAGS:
                blocks.append({"tag": child["tag"], "node": child,
                               "in_callout": callout})
            walk(child, callout)

    walk(node, False)
    return blocks


def _bold_headings(node):
    found = []

    def walk(current):
        for child in current["children"]:
            if isinstance(child, str):
                continue
            if child["tag"] in _BOLD_HEADING_TAGS:
                found.append(child)
            walk(child)

    walk(node)
    return found


def test_bold_marks_a_phrase_not_a_sentence(docs):
    """Bold marks a phrase, not a sentence (2026-11-24).

    The operator raised this with a screenshot of the tank-farms callout, where
    bold covered most of the paragraph across five separate runs. Bold that
    wide no longer points at anything: the reader sees a wall of black and the
    emphasis is gone.

    So, for every built page and every <p>/<li> of at least 10 words:

    - no single <strong>/<b> run may hold 8 words or more, because that is a
      sentence wearing emphasis, and
    - bold may not cover more than 25 percent of the block's own words, and
    - a block that is 100 percent bold is a heading written as bold text, which
      must become a real heading with the page's heading classes.

    Run count (2026-11-24, after the share limit passed a paragraph that still
    read heavy): a paragraph carries at most two bold runs, and a callout, list
    item or heading carries one. Share and run length cannot see the case this
    catches, because five short runs in a long paragraph clear both and still
    read as a wall of emphasis.

    The failure names the page, the block's word count, its bold share, its
    longest run, its run count and the text, so the sentence to fix is visible
    in the report.
    """
    violations = []
    for name in html_files(docs):
        tree = _BoldTree()
        tree.feed(read(docs, name))
        tree.close()
        for block in _bold_blocks(tree.root):
            node = block["node"]
            text = " ".join(html.unescape(
                _bold_text(node, stop_at_box=True)).split())
            words = _bold_words(text)
            runs = _bold_runs(node)
            limit = (BOLD_RUNS_TIGHT_MAX
                     if block["in_callout"] or block["tag"] == "li"
                     else BOLD_RUNS_PARAGRAPH_MAX)
            if len(runs) > limit:
                violations.append(
                    '{}: <{}>{} {} bold runs, limit {}: "{}"'.format(
                        name, block["tag"],
                        " in a callout" if block["in_callout"] else "",
                        len(runs), limit, text))
            if len(words) < BOLD_BLOCK_MIN_WORDS:
                continue
            bold_count = sum(len(run) for run in runs)
            longest = max(runs, key=len, default=[])
            share = bold_count / len(words)
            all_bold = bold_count == len(words)
            if (len(longest) >= BOLD_RUN_MAX_WORDS
                    or share > BOLD_SHARE_MAX or all_bold):
                violations.append(
                    '{}: <{}> {} words, {} bold ({:.0%}), longest run {} words{}: '
                    '"{}"'.format(
                        name, block["tag"], len(words), bold_count, share,
                        len(longest), ", all bold" if all_bold else "", text))
        for heading in _bold_headings(tree.root):
            runs = _bold_runs(heading)
            if len(runs) > BOLD_RUNS_TIGHT_MAX:
                violations.append(
                    '{}: <{}> {} bold runs, limit {}: "{}"'.format(
                        name, heading["tag"], len(runs),
                        BOLD_RUNS_TIGHT_MAX,
                        " ".join(html.unescape(_bold_text(heading)).split())))
    assert not violations, (
        "bold must mark a phrase, not a sentence: keep 2-5 words of the point "
        "and unbold the rest, or make a bold line a real heading. For any "
        "<p>/<li> of 10+ words: no <strong>/<b> run may reach "
        f"{BOLD_RUN_MAX_WORDS} words, bold may cover at most "
        f"{BOLD_SHARE_MAX:.0%} of the block, and an all-bold block is a heading "
        "written as text. Run count: at most "
        f"{BOLD_RUNS_PARAGRAPH_MAX} runs in a paragraph and "
        f"{BOLD_RUNS_TIGHT_MAX} in a callout, list item or heading\n"
        + "\n".join(violations))

def test_index_benzene_paragraph_keeps_two_bold_runs(docs):
    """The homepage benzene paragraph keeps two bold runs: the facility names.

    Operator, 2026-11-24: the paragraph still read heavy at five runs even
    though it cleared the share and run-length limits. The two facility names
    are what the sentence is about, and "worst readings in Maine are here" only
    lands if the reader can find the places, so those keep the emphasis and the
    other three runs come off. A later pass that puts one back fails here by
    name.
    """
    page = read(docs, "index.html")
    start = page.index("Concerning readings were collected near all the tanks")
    paragraph = page[start:page.index("</p>", start)]
    runs = re.findall(r"<strong>(.*?)</strong>", paragraph, re.S)
    assert len(runs) == 2, (
        "the benzene paragraph carries exactly two bold runs, the two facility "
        f"names; found {len(runs)}: {runs}")
    assert runs == ["South Portland Terminal", "Citgo on Mechanic Street"], (
        f"bold belongs on the facility names only, found {runs}")


def test_row86_brace_blocks_are_guidance_not_copy(docs):
    """Ledger row 86, operator ruling 2026-11-24, verbatim: "You should read
    content inside {{}} as stage instructions/agent guidance from [the copy
    document, tab t.9ye2jj2z90j8], not as literal text."

    The Act Now tab carries three brace blocks. Two of them shipped as
    reader-facing prose because a hand transcription dropped only the braces,
    which put agent-addressed "please verify" notes in front of visitors on
    act-now.html. This pin holds the ruling on the built page: no brace block's
    words reach a reader, the one reader-useful sentence beside a block
    survives, and the legislator list keeps a lead-in so a removal cannot leave
    it opening on a bare heading.
    """
    page = read(docs, "act-now.html")
    act = reading_text(page)
    # Agent-addressed instruction: never copy, never on a page.
    assert "please verify" not in act, "an agent-addressed verify note shipped"
    assert "Councilors as listed on the City" not in act, (
        "the councilor block's instruction reached the page")
    assert "Legislators listed here" not in act, (
        "the legislator block's instruction reached the page")
    assert "when you write" not in act, "instruction addressed to a writer"
    # The reader-useful half of the councilor block survives: where else to
    # find the addresses. (reading_text drops tags to spaces, so the link text
    # and the closing period are asserted apart.)
    assert "The addresses are also on" in act
    assert "southportland.gov/411/City-Council" in act
    # The legislator list keeps a lead-in between its heading and the list.
    start = page.index("Write to Maine state legislators")
    lead_in = reading_text(page[start:page.index("<ul", start)])
    assert lead_in.endswith("Their email addresses are below."), lead_in
    # No built page carries the brace syntax in either direction.
    for name in html_files(docs):
        markup = read(docs, name)
        assert "{{" not in markup and "}}" not in markup, (
            f"{name}: a brace block's delimiters reached the built tree")


def test_docs_serve_tree_shape_pins_the_pages_serve_config():
    """docs/ is the tree GitHub Pages will serve from main (fork model).

    Two shape facts pin the serving config (2026-11-24 migration): .nojekyll
    must be committed, because Pages must serve the built files verbatim with
    no build step; and docs/CNAME must NOT be tracked, because a tracked
    CNAME file is authoritative for branch deploys and would make Pages
    claim its hostname the moment it starts serving main, at a moment nobody
    chose. The domain file is committed deliberately at the cutover instead.
    """
    import subprocess
    tracked = subprocess.run(
        ["git", "ls-files", "docs/CNAME", "docs/.nojekyll"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert "docs/.nojekyll" in tracked, (
        "docs/.nojekyll must be committed: Pages serves the built tree "
        "verbatim, with no Jekyll pass over it")
    assert "docs/CNAME" not in tracked, (
        "docs/CNAME tracked: a branch deployment reads it as the custom "
        "domain, so Pages would claim its hostname the instant it serves "
        "main — the domain is set deliberately at cutover, never by a file "
        "that rides along in the tree")


# --- Ledger row 97: sendable copy must be the payload its action sends ------
#
# Operator instruction, 2026-11-24, verbatim: "add auto UAT rule to catch this,
# even though we're not running auto UAT now". The defect, caught by the
# operator's eye and by nothing else: `act-now.html` displayed a written-out
# letter under an "Example message" heading beside an orange "Email the
# Council" CTA whose mailto carried a subject and an EMPTY body, so the click
# opened a blank draft while the page asked the reader to copy the letter by
# hand. The rule lives once, in tools/uat_payload.py, and runs as the UAT
# ladder's payload rung (tools/uat_snapshots.py); the pins below are the
# always-on guard that runs with every suite run.

_UAT_MESSAGE = (
    "Dear Councilors,\n\n"
    "New state fence-line data shows benzene above Maine\u2019s ambient air "
    "guideline at ten of the eleven terminals.\n\n"
    "Sincerely,\n[Your name and street or neighborhood]"
)


def _sendable_fixture(href, heading="Example message", message=_UAT_MESSAGE):
    """A minimal page carrying the defect's shape: a CTA above a labelled
    blockquote of sendable copy. `href` is the control's link, so a caller
    decides whether the payload is blank, truncated or whole."""
    paragraphs = "".join(
        f"<p>{chunk}</p>" for chunk in html.escape(message).split("\n\n"))
    return f"""<!doctype html><html><body>
<p><a class="btn btn--cta" href="{href}">Email the Council</a></p>
<h2>{heading}</h2>
<blockquote>{paragraphs}</blockquote>
</body></html>"""


def test_act_now_cta_mailto_body_carries_the_example_message(docs):
    """The operator's 2026-11-24 catch, pinned on the built page.

    `act-now.html` displays a letter under "Example message" beside the
    "Email the Council" CTA. The CTA's decoded mailto body MUST be that
    letter, byte for byte after decoding: a subject with an empty body opens
    a blank draft and asks the reader to paste the whole letter by hand,
    which is exactly what the operator saw. Whitespace runs collapse on both
    sides (tools/uat_payload.canonical), so a paragraph separator cannot fail
    the pin while any word, punctuation mark or missing tail still does.

    WHAT THIS PIN CAN AND CANNOT PROVE, stated so no reader over-reads it:
    both sides of the comparison come from ONE authored source. The source
    anchor carries `data-mailto-body="blockquote"`, and the row-96 build step
    composes the mailto body from that same blockquote, so the pin guards the
    COMPOSER — that the letter reaches the draft whole, with no truncation, no
    dropped tail and nothing left blank. It cannot catch AUTHOR DRIFT: an
    author who pastes a different letter into the page's own copy would move
    both sides together. That case is held instead by the build refusing a
    marked CTA that already declares its own body, and by the review gate on
    the copy itself.
    """
    markup = read(docs, "act-now.html")
    pairs = [pair for pair in uat_payload.copy_payload_pairs(markup)
             if pair["control"] == "Email the Council"]
    assert len(pairs) == 1, (
        f"expected exactly one 'Email the Council' sendable pair on "
        f"act-now.html, found {pairs}")
    pair = pairs[0]
    assert pair["copy"].startswith("Dear Councilors,"), pair["copy"][:80]
    assert pair["copy_label"].lower().find("message") != -1, (
        f"the displayed copy's label changed: {pair['copy_label']!r}")
    assert pair["payload"], (
        "act-now.html: the 'Email the Council' mailto carries no body while "
        f"the page displays {len(pair['copy'])} characters of sendable copy "
        f"under {pair['copy_label']!r} — the click opens a blank draft")
    assert pair["payload"] == pair["copy"], (
        "act-now.html: the 'Email the Council' mailto body diverges from the "
        f"displayed copy: {uat_payload.divergence(pair['copy'], pair['payload'])}")


def test_uat_payload_rule_is_clean_across_every_built_page(docs):
    """The rule over the whole tree, through the same fetched-HTML path the
    UAT ladder uses, so this pin also proves the sweep works by URL.

    It walks `docs/` recursively, the same discovery the standalone tool
    defaults to (tools/uat_payload.discovered_pages), so the nested map pages
    are swept whenever the build produced them rather than skipped by a flat
    listing while this pin's title claims every page. A build with no map
    source carries no nested page, and then there is nothing extra to sweep.

    It must come back with zero findings, and it must not be vacuous: the
    Act now CTA is compared and carries a real payload. Every other page in
    the tree carries contact addresses, subject-only newsletter and workshop
    links, and mailing-address blockquotes, and none of those may fail.
    """
    pages = uat_payload.discovered_pages(str(docs))
    base = "file:" + os.path.join(str(docs), "index.html")
    findings, reports = uat_payload.sweep(base, pages)
    assert findings == [], "\n".join(findings)
    assert set(reports) == set(pages)
    if psp_public.find_map_source_docs() is not None:
        nested = [page for page in pages if "/" in page]
        assert nested, (
            "the build shipped map pages but the sweep read none of them: "
            f"{pages}")
    act = reports["act-now.html"]
    assert [pair["control"] for pair in act["pairs"]] == ["Email the Council"]
    assert len(act["pairs"][0]["payload"]) == len(act["pairs"][0]["copy"])
    # No other built page displays sendable copy today, so no other page is
    # inspected at all — a new sendable block on a new page shows up here as
    # a pair, and its payload must then match or this pin fails.
    others = {name: report["pairs"] for name, report in reports.items()
              if name != "act-now.html" and report["pairs"]}
    assert others == {}, f"unexpected sendable-copy pairs: {others}"


def test_uat_payload_rule_catches_blank_and_mismatched_payloads():
    """The two failures the rule exists for, on the defect's own shape.

    Red first: these assertions were written against the rule and are what
    make a blank or truncated payload a named failure rather than silence.
    """
    blank = _sendable_fixture(
        "mailto:citycouncil@example.org?subject=Require%20better%20technology")
    findings = uat_payload.check_page(blank, "act-now.html")
    assert len(findings) == 1
    assert findings[0].startswith(
        "sendable-payload:missing-payload act-now.html: control "
        "'Email the Council'"), findings[0]
    assert "empty payload" in findings[0]
    assert f"{len(uat_payload.canonical(_UAT_MESSAGE))} characters" in findings[0]

    truncated = uat_payload.canonical(_UAT_MESSAGE).split(" Sincerely")[0]
    href = ("mailto:citycouncil@example.org?subject=Ask&body="
            + urllib.parse.quote(truncated))
    findings = uat_payload.check_page(
        _sendable_fixture(href), "act-now.html")
    assert len(findings) == 1
    assert findings[0].startswith(
        "sendable-payload:payload-mismatch act-now.html"), findings[0]
    assert "payload stops after" in findings[0], findings[0]

    whole = ("mailto:citycouncil@example.org?subject=Ask&body="
             + urllib.parse.quote(uat_payload.canonical(_UAT_MESSAGE)))
    assert uat_payload.check_page(_sendable_fixture(whole), "act-now.html") == []


def test_uat_payload_rule_leaves_contact_and_unpaired_controls_alone():
    """The false-positive sweep, one case per shape the live site carries.

    A bare contact address, a subject-only alert link with no displayed copy,
    a mailing-address blockquote, a subject-only control several headings away
    from the copy, and a CTA whose page displays no copy must all pass.
    """
    contact_only = """<html><body>
<p>Write to <a href="mailto:protectsouthportland@gmail.com">protectsouthportland@gmail.com</a>.</p>
</body></html>"""
    assert uat_payload.check_page(contact_only, "contact.html") == []

    subject_only = """<html><body>
<p><a href="mailto:hello@example.org?subject=Subscribe%20to%20the%20newsletter">hello@example.org</a></p>
</body></html>"""
    assert uat_payload.check_page(subject_only, "newsletter.html") == []

    mailing_address = """<html><body>
<h2>Mailing address</h2>
<blockquote><p>Protect South Portland
15 Cottage Road, Suite 2154
South Portland, ME 04116</p></blockquote>
</body></html>"""
    assert uat_payload.check_page(mailing_address, "donate.html") == []

    far_control = """<html><body>
<h2>Example message</h2>
<blockquote><p>Dear Councilors,</p><p>Please require better technology at the
tank farms and make the special counsel advice public.</p></blockquote>
<h2>Write to City Councilors</h2>
<p>Addresses are below.</p>
<h2>Workshop alerts</h2>
<p>Write to <a href="mailto:hello@example.org?subject=Workshop%20alerts">hello@example.org</a>.</p>
</body></html>"""
    report = uat_payload.inspect_page(far_control, "act-now.html")
    assert report["findings"] == [], report["findings"]
    assert report["notes"], "the unpaired copy should be noted, not failed"

    no_copy = """<html><body>
<p><a class="btn btn--cta" href="mailto:hello@example.org?subject=Workshop%20alerts">Email us</a></p>
<p>Email us to get plugged into local efforts.</p>
</body></html>"""
    assert uat_payload.check_page(no_copy, "act-now.html") == []


def test_uat_ladder_payload_rung_stops_a_blank_payload_page(tmp_path, capsys):
    """The rule is wired into the UAT ladder, not only importable.

    `tools/uat_snapshots.py` runs the payload sweep before it opens a browser
    or files a single capture. A blank payload stops the ladder with exit 1
    and the finding printed; a whole payload lets the ladder through. No
    browser is opened on either run because `--payload-check-only` returns
    before the session, so this pin is cheap and headless.
    """
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"start_pages": ["act-now.html"]}))

    blank = tmp_path / "blank" / "act-now.html"
    blank.parent.mkdir()
    blank.write_text(_sendable_fixture(
        "mailto:citycouncil@example.org?subject=Require%20better%20technology"))
    code = uat_snapshots.main([
        "--target", "local", "--suite", str(suite), "--payload-check-only",
        "--url", "file:" + str(blank)])
    printed = capsys.readouterr().out
    assert code == 1
    assert "FAIL: sendable-payload:missing-payload act-now.html" in printed

    whole = tmp_path / "whole" / "act-now.html"
    whole.parent.mkdir()
    whole.write_text(_sendable_fixture(
        "mailto:citycouncil@example.org?subject=Ask&body="
        + urllib.parse.quote(uat_payload.canonical(_UAT_MESSAGE))))
    code = uat_snapshots.main([
        "--target", "local", "--suite", str(suite), "--payload-check-only",
        "--url", "file:" + str(whole)])
    printed = capsys.readouterr().out
    assert code == 0
    assert "0 findings" in printed


# ---------------------------------------------------------------------------
# Heading margin direction (2026-11-24, ledger row 104).
#
# The operator's principle, verbatim: "margin is also inverted here --
# headers should be closer to the content they belong with than to the
# prior section." Ruled on dec_f9zp4ryi7mdj, option "Space above larger
# than space below": a heading's top margin is strictly greater than its
# bottom margin, so more air sits before a heading than after it.
#
# The pin walks the stylesheet rather than hand-listing rules: a rule is a
# base heading rule when a selector in its group targets a bare heading
# element, optionally with its own classes, and carries no ancestor
# combinator. Boxed headings (.card h3, .action-band h2.h3-look, ...) are
# excluded by that same construction, not by a list: inside a box the
# heading belongs to the sentence under it and the box's own boundary
# separates it from the prior section, which is the ruling's implied note.

_ROOT_PX = 18.0  # html { font-size: 112.5% } of the 16px browser default

_BASE_HEADING_SELECTOR = re.compile(r"^h[1-6](?:\.[A-Za-z0-9_-]+)*$")


def _length_px(value, font_px, where):
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|rem|em)", value.strip())
    if not m:
        raise AssertionError(
            f"{where}: cannot resolve length {value!r}; this pin only "
            "understands px, rem and em so an unresolvable unit is never "
            "waved through")
    number, unit = float(m.group(1)), m.group(2)
    if unit == "px":
        return number
    if unit == "rem":
        return number * _ROOT_PX
    return number * font_px


def _heading_font_px(decls, where):
    """The font size em margins resolve against, in px.

    A rule without its own font-size keeps whatever scale the browser gives
    the heading; top and bottom em values share that one font factor, so the
    direction comparison is exact whatever the rendered size is.
    """
    if "font-size" not in decls:
        return _ROOT_PX
    value = decls["font-size"]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(px|rem|em|%)", value.strip())
    if not m:
        raise AssertionError(
            f"{where}: cannot resolve font-size {value!r} for em margins; "
            "declare the heading's size in px, rem or em")
    number, unit = float(m.group(1)), m.group(2)
    factor = {"px": 1.0, "rem": _ROOT_PX, "em": _ROOT_PX,
              "%": _ROOT_PX / 100.0}[unit]
    return number * factor


def _vertical_margin_pair(decls, where):
    """(top_raw, bottom_raw) from a rule's own margin declarations, or None
    when the rule leaves the vertical margins alone."""
    if "margin" in decls:
        parts = decls["margin"].split()
        if not 1 <= len(parts) <= 4:
            raise AssertionError(
                f"{where}: unreadable margin shorthand {decls['margin']!r}")
        if len(parts) == 1:
            top = bottom = parts[0]
        elif len(parts) == 2:
            top = bottom = parts[0]
        elif len(parts) == 3:
            top, bottom = parts[0], parts[2]
        else:
            top, bottom = parts[0], parts[3]
        return top, bottom
    if "margin-top" in decls or "margin-bottom" in decls:
        if "margin-top" not in decls or "margin-bottom" not in decls:
            raise AssertionError(
                f"{where}: declares only one of margin-top/margin-bottom; "
                "declare both (or the shorthand) so the direction stays "
                "checkable")
        return decls["margin-top"], decls["margin-bottom"]
    return None


def test_base_heading_margins_are_top_heavy(docs):
    """Every base heading rule declares more margin above than below.

    Ledger row 104 (2026-11-24). The operator's principle: "headers should
    be closer to the content they belong with than to the prior section."
    Ruling dec_f9zp4ryi7mdj, option "Space above larger than space below".
    The walk discovers the rules from the selectors themselves, so a future
    base heading rule cannot ship inverted and a future scoped box head
    (.anything h2) is out of the pin by construction.
    """
    css = read(docs, "styles.css")
    checked = []
    for media, selector, body in _css_rules(css):
        parts = [p.strip() for p in selector.split(",")]
        if not any(_BASE_HEADING_SELECTOR.match(p) for p in parts):
            continue
        decls = _css_declarations(body)
        pair = _vertical_margin_pair(decls, f"styles.css `{selector}`")
        if pair is None:
            continue
        where = f"styles.css `{selector}`"
        pair = _vertical_margin_pair(decls, where)
        if pair is None:
            continue
        needs_font = any(v.endswith("em") for v in pair)
        font_px = (_heading_font_px(decls, where) if needs_font else _ROOT_PX)
        top = _length_px(pair[0], font_px, where)
        bottom = _length_px(pair[1], font_px, where)
        checked.append(selector)
        assert top > bottom, (
            f"{where}: margin resolves to {top:g}px above but {bottom:g}px "
            "below — the inversion the operator named on 2026-11-24. A "
            "heading must sit closer to the content it introduces than to "
            "the prior section (ruling dec_f9zp4ryi7mdj)")
    covered = {re.match(r"h[1-6]", s).group(0) for s in checked}
    missing = {"h1", "h2", "h3"} - covered
    assert not missing, (
        f"the walk found no margin-bearing base rule for {sorted(missing)}; "
        "the pin is blind if the base heading margin rules disappear")
# --- Ledger row 101: the six findings on the row-97 rule's own review --------
#
# Full-class review of PR #82, six findings (four medium, two low), fixed here
# rather than filed. Each pin below was written against the pre-fix tool and
# failed there; the red proof is in the pull request body.

_LETTER = (
    "Dear Councilors,\n\n"
    "New state fence-line data shows benzene above Maine\u2019s ambient air "
    "guideline at ten of the eleven terminals.\n\n"
    "Sincerely,\n[Your name and street or neighborhood]"
)


def _cta_with_letter(heading="Example message"):
    """The clean shape: a CTA that carries the whole letter, above it."""
    body = urllib.parse.quote(uat_payload.canonical(_LETTER))
    return (f'<p><a class="btn btn--cta" '
            f'href="mailto:citycouncil@example.org?subject=Ask&body={body}">'
            f'Email the Council</a></p>\n'
            f'<h2>{heading}</h2>\n'
            f'<blockquote><p>{html.escape(_LETTER)}</p></blockquote>')


def test_uat_payload_rule_ignores_a_subject_link_inside_a_letter():
    """Finding 1, medium: a subject-carrying "email us" link inside a letter's
    own region is not a promise to send the letter.

    The reviewer's probe, verbatim in shape: a "Questions? email us" link after
    the displayed letter with no heading between them paired with the letter and
    fired `missing-payload`, because a subject-only control was transmitting by
    definition. The real tree swept clean only because a heading happened to sit
    between every subject link and every letter.
    """
    page = (f"<html><body>\n{_cta_with_letter()}\n"
            '<p>Questions? <a href="mailto:hello@example.org?'
            'subject=Question%20about%20the%20example%20message">email us</a>.'
            "</p>\n</body></html>")
    report = uat_payload.inspect_page(page, "act-now.html")
    assert report["findings"] == [], report["findings"]
    assert [pair["control"] for pair in report["pairs"]] == ["Email the Council"]

    # The opt-in is the way back in: a page that designates the copy as what
    # its control sends gets the blank payload reported, whatever the control's
    # label looks like.
    opted_in = page.replace("<blockquote>", "<blockquote data-sendable-copy>")
    findings = uat_payload.check_page(opted_in, "act-now.html")
    assert len(findings) == 1, findings
    assert "control 'email us'" in findings[0], findings[0]
    assert findings[0].startswith("sendable-payload:missing-payload"), findings[0]


def test_uat_payload_rule_notes_an_orphan_beside_a_paired_block():
    """Finding 2, medium: an unpaired sendable block is noted even when the
    page has a pair somewhere else.

    The module doc and the row-97 pull request both promise displayed copy with
    no control is noted rather than failed, but the note was emitted only under
    `if not pairs`, so a page with one paired letter and one orphan said nothing
    about the orphan.
    """
    page = (f"<html><body>\n{_cta_with_letter()}\n"
            '<h2>Sample comment</h2>\n'
            "<blockquote><p>I support the fence-line monitoring rule because "
            "the readings are the whole argument.</p></blockquote>\n"
            "</body></html>")
    report = uat_payload.inspect_page(page, "act-now.html")
    assert report["findings"] == [], report["findings"]
    assert len(report["pairs"]) == 1, report["pairs"]
    assert len(report["notes"]) == 1, report["notes"]
    assert "'Sample comment'" in report["notes"][0], report["notes"][0]
    assert "no transmitting control" in report["notes"][0], report["notes"][0]


def test_uat_payload_pin_states_its_shared_source_scope():
    """Finding 3, medium: the unit pin says what it can and cannot prove.

    The pin compares the built page's mailto body with the blockquote beside
    it, but the row-96 build step writes that body from that very blockquote, so
    both sides of the comparison come from one authored source. The pin guards
    the composer — that the letter is copied whole, with no truncation and no
    dropped tail — and it cannot catch an author who pastes a different letter
    into a hand-written body. That limit belongs on the record, not in a
    reader's assumption.
    """
    doc = test_act_now_cta_mailto_body_carries_the_example_message.__doc__
    assert doc, "the pin lost its docstring"
    doc = doc.lower()
    assert "composer" in doc, doc
    assert "author drift" in doc, doc
    assert "data-mailto-body" in doc, doc


def test_uat_payload_default_discovery_walks_nested_pages(tmp_path, capsys):
    """Finding 4, medium: nested pages are swept, not silently skipped.

    The default discovery used a flat `os.listdir`, so `map/embed.html` and
    `map/map.html` were never read, while the tree-wide pin's title said every
    built page. A blank payload on a nested page must stop the tool and be named
    by its relative path.
    """
    root = tmp_path / "built"
    (root / "map").mkdir(parents=True)
    (root / "index.html").write_text(
        "<html><body><p>Home</p></body></html>", encoding="utf-8")
    (root / "map" / "inner.html").write_text(
        _sendable_fixture("mailto:citycouncil@example.org?subject=Ask"),
        encoding="utf-8")

    code = uat_payload.main(["--url", "file:" + str(root / "index.html")])
    printed = capsys.readouterr().out
    assert code == 1, printed
    assert "FAIL: sendable-payload:missing-payload map/inner.html" in printed, \
        printed
    assert "payload sweep: 2 pages" in printed, printed

    assert uat_payload.discovered_pages(str(root)) == [
        "index.html", "map/inner.html"]


def test_uat_payload_rule_notes_cue_headed_prose_it_declines():
    """Finding 5, low: a letter restyled into paragraphs says so.

    Only a blockquote or a `data-sendable-copy` element counts as sendable copy,
    so a letter written out as ordinary paragraphs under "Example message" was
    neither checked nor noted — the silent decline the reviewer named. It is now
    noted by name, and the note carries the fix.
    """
    page = ("<html><body>\n<h2>Example message</h2>\n"
            + "".join(f"<p>{chunk}</p>"
                      for chunk in html.escape(_LETTER).split("\n\n"))
            + "\n</body></html>")
    report = uat_payload.inspect_page(page, "act-now.html")
    assert report["findings"] == [], report["findings"]
    assert report["pairs"] == [], report["pairs"]
    assert len(report["notes"]) == 1, report["notes"]
    note = report["notes"][0]
    assert "'Example message'" in note, note
    assert "not a <blockquote>" in note, note
    assert "data-sendable-copy" in note, note
    assert "(not a failure)" in note, note

    # Precision: a guidance section that merely mentions letters, with no
    # salutation and no sample cue in its heading, stays quiet. This is the
    # shape toolkit.html carries on the real tree.
    guidance = ("<html><body>\n<h2>Letter to the editor guidance</h2>\n<p>"
                + "Points for writing, one hundred and fifty words maximum, "
                "the council plans a workshop on options like licensing fees. "
                * 3 + "</p>\n</body></html>")
    assert uat_payload.inspect_page(guidance, "toolkit.html")["notes"] == []


def test_uat_payload_divergence_names_a_payload_that_runs_past_the_copy():
    """Finding 6, low: a payload longer than the displayed copy said nothing.

    `divergence()` sliced both strings at the same index, so when the payload
    merely continued past the copy it printed "the page displays ''", which
    reads like a broken message rather than a finding. The payload's extra
    characters are what the reader needs named.
    """
    detail = uat_payload.divergence("Dear Councilors, please act.",
                                    "Dear Councilors, please act. Also, now.")
    assert "runs 11 characters past the displayed copy" in detail, detail
    assert "' Also, now.'" in detail, detail
    assert "the page displays ''" not in detail, detail

    # End to end: the extra-text payload is a payload-mismatch finding, worded
    # the same way.
    copy = uat_payload.canonical(_LETTER)
    extra = " And one more demand."
    href = ("mailto:citycouncil@example.org?subject=Ask&body="
            + urllib.parse.quote(copy + extra))
    findings = uat_payload.check_page(_sendable_fixture(href), "act-now.html")
    assert len(findings) == 1, findings
    assert findings[0].startswith("sendable-payload:payload-mismatch"), findings[0]
    assert f"runs {len(extra)} characters past the displayed copy" in findings[0], \
        findings[0]

