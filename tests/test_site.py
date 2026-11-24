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
from html.parser import HTMLParser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "tools", "build.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import psp_public
import publish

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
    chapters the ruling left behind, the two places that reach the page, and
    the header staying at five items.

    Two carried-copy defects stay on the page by decision, taken in the gate
    review of 2026-11-24, and a later agent must not "fix" them silently:

    - "The lawsuits create a public outcry but ends in consent decrees" is the
      campaign document's own subject-verb slip. Correcting it would rewrite
      campaign prose, so the page keeps it and the campaign fixes the source.
    - Two FAQ answers name the Oct. 27 workshop and "this year's" council
      candidates. The chapter lede already dates every answer to the October 15
      meeting, so the dated answer is honest as the snapshot it is.

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

    # 3. no sixth navigation item: five items plus the Act now pill
    nav = re.search(r'<nav class="main-nav".*?</nav>',
                    read(docs, "index.html"), re.S).group(0)
    collector = _TopNavLinks()
    collector.feed(nav)
    assert collector.hrefs == [
        "our-campaigns.html", "about.html", "share-your-story.html",
        "newsletter.html", "contact.html", "act-now.html",
    ], collector.hrefs
    assert nav.count('class="nav-cta"') == 1, "one pill, the Act now link"
    assert "toolkit.html" not in nav, "the toolkit page is not a nav item"

    # 4. draft artifacts and unpublished answers never ship
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

    # 5. the chapters the ruling left in the live document
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
    """Ledger row 33 (2026-10-15) sanctioned this meeting bullet; the operator
    directed the past-tense conversion on 2026-11-05 (the meeting happened).
    It stays as history above the workshop bullet, without the event links."""
    idx = read(docs, "index.html")
    # 2026-11-24: the copy pin reads the tag-stripped text, because the bold
    # pass moved emphasis inside this bullet; what row 33 rules on is the
    # sentence, not where the <strong> sits.
    idx_text = reading_text(idx)
    bullet = ("Neighbors met on Thursday, Oct. 15 for a community meeting to "
              "share ideas, concerns, and stories: 5:30 p.m. food and "
              "community; 6-7 p.m. discussion, at First Congregational Church "
              "UCC, 301 Cottage Road. Kids were welcome.")
    assert bullet in idx_text, "the past-tense meeting bullet must ship"
    assert "Join neighbors on Thursday, Oct. 15" not in idx, "the invitation form is retired"
    assert 'href="assets/files/tank-talk-flyer.pdf"' not in idx, "the event-only flyer link is dropped"
    flyer = os.path.join(ROOT, "docs", "assets", "files", "tank-talk-flyer.pdf")
    assert os.path.exists(flyer), "the Tank Talk flyer stays archived in the built tree"
    # meeting bullet sits above the workshop bullet (operator placement)
    callout_pos = idx_text.index("Now is the time to act")
    assert idx_text.index("Neighbors met on Thursday, Oct. 15", callout_pos) < \
        idx_text.index("The City Council took no vote at its Oct. 27 workshop", callout_pos)
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
    cname = os.path.join(ROOT, "docs", "CNAME")
    assert os.path.exists(cname)
    assert open(cname).read().strip() == "protectsouthportland.org"


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


def test_banner_homepage_only(docs):
    for name in html_files(docs):
        page = read(docs, name)
        has_banner = 'class="banner"' in page
        if name == "index.html":
            assert has_banner, "homepage must carry the banner"
        else:
            assert not has_banner, f"{name} must not carry the homepage banner"


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
    on the homepage — the mission folds into the banner as its sign-off and
    the About paragraph sits in a compact strip between the hero photo and
    the issue section (2026-10-14 single-hero design pass), with Our Story
    linking about.html and an Act now link to act-now.html (the doc's action
    section renamed page on 2026-11-24) — after
    the 2026-10-14 design round 2 both read as list items in a two-item link
    row (page-structure patch): prose, not buttons; the banner Act now is the
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
    assert "Read more: Our Story" in idx
    assert 'href="about.html"' in idx, "Our Story must link to about.html"
    # 2026-11-24 page-set revision: the doc renamed its action section Act Now,
    # so the link row names the destination the site now has.
    assert "Act now" in idx
    assert 'href="act-now.html"' in idx, "the action link must reach act-now.html"
    # design round 2 + page-structure patch: exactly one button idiom in the
    # first screen — the banner Act now — and the strip's links read as a
    # two-item link row after the paragraph (labels and hrefs char-for-char;
    # the paragraph ends at its own period), not a run-on, not stacked buttons.
    idx_top = idx[idx.index('class="banner"'):idx.index('<span class="kicker">Current campaign</span>')]
    assert idx_top.count('class="btn') == 1, "only the banner Act now is a button in the top flow"
    assert "intro-cta" not in idx and "btn--ghost" not in idx_top
    assert "meaningful actions.</p>" in idx and "Our Story</a> <a" not in idx, "strip ends at its own period"
    row_pos = idx.index('<ul class="link-row">')
    row = idx[row_pos:idx.index("</ul>", row_pos)]
    assert row.count('<li><a href="about.html">Read more: Our Story</a></li>') == 1
    assert row.count('<li><a href="act-now.html">Act now</a></li>') == 1
    # heading order (fix 3): the banner headline is the page's single h1
    assert idx.count("<h1") == 1 and '<h1 class="banner__headline">' in idx
    assert '<p class="banner__headline">' not in idx
    # final top-of-page order: banner (mission folded in as its sign-off, and
    # now the h1) -> hero photo band -> who-we-are strip -> link row (inside
    # the strip, after the paragraph) -> issue section
    banner_pos = idx.index('class="banner"')
    mission_pos = idx.index("We are a community-based")
    hero_pos = idx.index('class="hero-band')
    strip_pos = idx.index("For over a decade, we")
    issue_pos = idx.index('<span class="kicker">Current campaign</span>')
    assert banner_pos < mission_pos < hero_pos < strip_pos < row_pos < issue_pos
    # author working notes are not copy
    for leak in ("Something like this", "Something like that", "link to About Us"):
        assert leak not in idx, leak


def test_homepage_hero_band_shows_the_shoreline(docs):
    """Operator ask, 2026-11-24: the band under the banner showed petroleum
    tanks, so the photograph repeated the problem the headline complains
    about. It now shows what the campaign protects (Bug Light, a schooner
    under sail, the park lawn at dusk). The band is a CSS background with
    role="img", so the aria-label is the only description a screen reader
    gets, and the file it names has to exist in the built tree or the band
    ships as an empty grey strip with nothing to catch it.

    Gate finding 2026-11-24: the crop is no longer an inline style. The photo
    and its narrow-width crop live in the page-scoped `.hero-band--home`
    class, and a wide-viewport rule climbs the crop so the lawn and the
    people survive at desktop width, where the 260px band shows the thinnest
    slice of the frame."""
    idx = read(docs, "index.html")
    m = re.search(
        r'<div class="hero-band hero-band--low hero-band--home"\s+'
        r'role="img"\s+aria-label="([^"]+)"',
        idx,
    )
    assert m, 'the homepage band keeps its classes + role="img" + aria-label'
    label = m.group(1)
    assert "background-image" not in idx.split('class="banner"')[0], "no inline band style"
    css = read(docs, "styles.css")
    rule = re.search(r"\.hero-band--home\s*\{([^}]*)\}", css)
    assert rule, "the band's photo is declared in a page-scoped class, not an inline style"
    base_rule = rule.group(1)
    assert "assets/photos/hero-coast.jpg" in base_rule
    assert "background-position" in base_rule
    assert os.path.isfile(os.path.join(docs, "assets/photos/hero-coast.jpg")), \
        "hero-coast.jpg must exist in the built tree"
    wide = re.search(r"@media \(min-width: 901px\) \{(.*?)\n\}", css, re.S)
    assert wide, "a wide-viewport rule retunes this band's crop"
    assert ".hero-band--home" in wide.group(1) and "center 58%" in wide.group(1)
    assert "tank" not in label.lower(), "the band no longer describes tanks"
    for landmark in ("Bug Light", "schooner"):
        assert landmark in label, f"the description names the {landmark} the photo shows"
    assert len(label.split()) >= 8, "the description stays a real sentence, not a file name"


def test_embed_url_is_the_public_embedding(docs):
    """The map is self-hosted: both mapping pages iframe map/embed.html from
    this same published tree — no absolute cristoslc.github.io source."""
    for name in ("index.html", "tank-farms.html"):
        assert 'src="map/embed.html"' in read(docs, name), name


def test_docx_action_dates_are_on_the_homepage(docs):
    """The Oct. 27 date survives as a past fact; the venue address left with
    the invitation (operator ruling, 2026-11-05)."""
    idx = read(docs, "index.html")
    assert "Oct. 27" in idx
    assert "637 Highland Ave" not in idx


# ---- content-gap rewrite (Oct 13, 2026): homepage cut-down, archive page, ----
# ---- dated footer strip, dead-link sweep                                      ----

DATED_PHRASE = "Next: City Council workshop - Tuesday, Oct. 27, 6 p.m., South Portland High School."
# Ruling A (2026-11-05): the fallback call to action that replaces it in the
# shared footer strip on every page.
ACTION_PHRASE = "Report every odor. Sign the petition."
# the internal DATED marker lives only in tools/build.py as a Python comment;
# the served HTML must never carry it (release-gate rule 4, reviewer R1)
DATED_COMMENT = "DATED: remove after 2026-10-27 workshop"

PETITION_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSfPIeWgfe7GGgNqhxVatcPAEffmqo5jJJ-iGYcCh4ltcQsZcA/viewform"
)

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
    # branches into both odor paths and the petition. Since the 2026-11-24
    # page-set revision that page is act-now.html: it carries the petition and
    # offers the Report an odor child page, so the strip's target is never a
    # retired URL.
    for name in html_files(docs):
        if name in REDIRECT_PAGES:
            continue
        page = read(docs, name)
        assert DATED_PHRASE not in page, f"{name}: the retired Oct. 27 strip is still present"
        assert ACTION_PHRASE in page, name
        assert DATED_COMMENT not in page, f"{name}: internal DATED comment leaked into served HTML"
        assert 'class="action-strip"' in page, name
        assert re.search(
            r'<a href="act-now\.html">Report every odor\. Sign the petition\.</a>',
            page), name
    # and the target really is the branch page: the petition plus the way to
    # report an odor both live there
    act = read(docs, "act-now.html")
    assert PETITION_URL in act, "the strip promises the petition"
    assert 'href="report-an-odor.html"' in act, "the strip promises the odor path"


def test_no_public_todo_strings(docs):
    for name in html_files(docs):
        assert "TODO" not in read(docs, name), name


def test_act_now_current_ask_and_relocation(docs):
    """The current ask, the petition and the letter-to-the-editor guidance moved
    here from get-involved.html on 2026-11-24, when the copy document renamed
    its action section Act Now and gave the odor section its own page."""
    act = read(docs, "act-now.html")
    assert "Oct. 27" in act
    assert PETITION_URL in act
    assert "pressherald.com/contact/" in act


def test_act_now_workshop_is_past_tense(docs):
    # The Oct. 27 workshop happened. Both mentions state that it happened and
    # point at the email action, and the high-school address that served only
    # that night stays gone. 2026-11-20: the second mention now also carries the
    # next date, so it is pinned by its past-tense opener, not by a count of the
    # full retired sentence (which the live fact legitimately extends).
    # 2026-11-24: the two mentions are the current-ask callout and the More ways
    # to help paragraph, both of which moved here from get-involved.html.
    act = read(docs, "act-now.html")
    assert act.count("The City Council workshop was held on Oct. 27") == 2
    assert "Make plans to come to the City Council workshop" not in act
    assert "Attend the City Council workshop" not in act
    assert "637 Highland Ave" not in act


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


def write_gate_report(tmp_path, docs, pages=None, drop=(), **overrides):
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
    path = tmp_path / "gate.json"
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
    assert ".staging-gate-overlay{" in text
    assert ".staging-gate-input{" in text
    # the embedded map iframe can take focus as it loads; the gate must take
    # it back so a visitor can type the phrase without clicking
    assert 'window.addEventListener("load"' in text


DATE_TOKEN = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b", re.I)
INVITE_VERB = re.compile(
    r"\b(join|come|attend|make plans|be there|rsvp|meet us|gather)\b", re.I)
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


def test_act_now_past_tense_and_one_email_action(docs):
    # Ruling B (2026-11-05): the page asks for the outcome, not an instrument.
    # The Oct. 27 workshop happened, so the opener states it and the page
    # carries one real email-the-Council action. "Oct. 27" itself stays: the
    # date describes a past event. What must be gone is every invitation to
    # attend it. Never pin the date string's absence.
    act = read(docs, "act-now.html")
    # 2026-11-24: read the tag-stripped text, so emphasis markup can move
    # inside the sentence without the ruling pin breaking on a <strong>.
    assert "The City Council workshop was held on Oct. 27" in reading_text(act)
    assert "took no vote" in act
    # 2026-11-20: a date now exists, so the opener states the outcome: the
    # options the Council asked for return at the planned Dec. 1 workshop.
    # "another workshop" was retired by the reviewer as a doubled sentence.
    assert "the options it asked for return" in act
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
    banner = ("The Council plans its next workshop on tank emissions for "
              "Tuesday, Dec. 1 at 6:30 p.m. Ask it to require better technology "
              "at the tank farms.")
    bullet_state = ("The Council plans its next workshop for Tuesday, Dec. 1 "
                    "at 6:30 p.m.")
    past_state = ("The City Council took no vote at its Oct. 27 workshop")
    idx = read(docs, "index.html")
    tank = read(docs, "tank-farms.html")
    # 2026-11-24: copy pins read tag-stripped text, so the bold pass can move
    # emphasis inside these sentences without weakening the ruling they pin.
    idx_text = reading_text(idx)
    tank_text = reading_text(tank)
    assert banner in idx_text
    assert bullet_state in idx_text
    assert past_state in idx_text
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
    about = read(docs, "about.html")
    assert "The Council took no vote at its Oct. 27 workshop" in about
    assert "Come to the City Council workshop" not in about
    assert "637 Highland Ave" not in about


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


class _BoldTree(HTMLParser):
    """An element tree with text leaves: enough to measure bold in a block."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "(document)", "children": []}
        self._open = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "children": []}
        self._open[-1]["children"].append(node)
        if tag not in _VOID_TAGS:
            self._open.append(node)

    def handle_startendtag(self, tag, attrs):
        self._open[-1]["children"].append({"tag": tag, "children": []})

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
    blocks = []

    def walk(current):
        for child in current["children"]:
            if isinstance(child, str):
                continue
            if child["tag"] in _BOLD_BLOCK_TAGS:
                blocks.append(child)
            walk(child)

    walk(node)
    return blocks


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

    The failure names the page, the block's word count, its bold share, its
    longest run and the text, so the sentence to fix is visible in the report.
    """
    violations = []
    for name in html_files(docs):
        tree = _BoldTree()
        tree.feed(read(docs, name))
        tree.close()
        for block in _bold_blocks(tree.root):
            text = " ".join(html.unescape(
                _bold_text(block, stop_at_box=True)).split())
            words = _bold_words(text)
            if len(words) < BOLD_BLOCK_MIN_WORDS:
                continue
            runs = _bold_runs(block)
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
    assert not violations, (
        "bold must mark a phrase, not a sentence: keep 2-5 words of the point "
        "and unbold the rest, or make a bold line a real heading. For any "
        "<p>/<li> of 10+ words: no <strong>/<b> run may reach "
        f"{BOLD_RUN_MAX_WORDS} words, bold may cover at most "
        f"{BOLD_SHARE_MAX:.0%} of the block, and an all-bold block is a heading "
        "written as text\n" + "\n".join(violations))
