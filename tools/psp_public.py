#!/usr/bin/env python3
"""Publication-safety rules shared by build.py, publish.py and the tests.

The public mirror carries ONLY the campaign site plus the standalone
tank-farm map. Everything that belongs to the private research surface —
files, links, labels, the private repo's name and its github.io host — and
every internal working-draft artifact is banned from any published tree.
The rules live here once, and every entry point (site build, mirror
publish, CI) enforces the same sets, failing loudly instead of quietly
sanitizing.
"""
import os
import re

# Links, labels and names belonging to the private research surface. The
# private repo's NAME and its github.io host are banned too: once that repo
# goes private, any public reference to it is at best a dead link and at
# worst a disclosure.
PRIVATE_MARKERS = (
    "factcheck",
    "report.html",
    "data.html",
    "github.com/cristoslc",
    "cristoslc.github.io",
    "wixstatic",
    "PULL-PROVENANCE",
    "Research report",
    "Fact-check log",
    "Data files",
    "GitHub repo",
    # Ledger row 42 (2026-10-15): the staging cookie gate's marker. The gate
    # is a staging-leg feature only — production must never carry it, so the
    # marker sits in this list and any gated tree fails a prod leg's scan
    # loud. (The staging leg applies the gate AFTER its own scan, so the
    # intentional gate never trips the scanner that ships it.)
    "staging-gate",
    # Ledger row 79 (2026-11-24): the staging preview's publish-time line, the
    # small "Staging preview, updated <date and time>" strip in the masthead.
    # Same rule as the gate above and for the same reason: only the staging
    # leg's staged tree ever carries it, production never does, so a tree that
    # somehow arrives at a prod leg stamped fails the scan by name instead of
    # shipping a build time to the public site. (The staging leg stamps AFTER
    # its own scan, so the intentional stamp never trips the scanner that
    # ships it.)
    "staging-updated",
)

# Ledger row 9 (constraint): the Oct 15 assembly is never on the public site.
# REVERSED 2026-10-15 by ledger row 33 (operator directive; Mindy-sanctioned
# meeting copy ships today, meeting is tonight): the Oct-15 event-marker ban
# is retired so the sanctioned Action-Oriented bullet passes the scan. The
# private-surface markers above and the draft-artifact markers below are
# unchanged.
# The private research repo's NAME still trips the scan, but with slug
# boundaries: a bare "south-portland-tank-farms" token (spelled out, or
# inside the repo URL) is a private-surface reference, while a longer
# hyphen-joined URL slug that merely contains it is not — the Press Herald
# slugs the media-coverage leg shipped (2026-11-25,
# /2026/11/14/south-portland-tank-farms-require-.../) are public newspaper
# URLs, not research links. The host markers above stay literal, so the
# repo's URL trips whatever surrounds it.
PRIVATENAME_PATTERN = re.compile(
    r"(?<![\w-])south-portland-tank-farms(?![\w-])", re.IGNORECASE)

EVENT_MARKERS: tuple = ()

# AGENTS.md release gate, rule 4: scan for the draft-artifact pattern class,
# not a single exact string ("as now written", "most recent draft", TODO/FIXME
# labels, anything that reads like a note to self).
DRAFT_MARKERS = (
    "as now written",
    "most recent draft",
    "working draft",
    "TODO",
    "FIXME",
)

ALL_MARKERS = PRIVATE_MARKERS + EVENT_MARKERS + DRAFT_MARKERS

# Internal process references (2026-11-24). A footer script comment shipped
# the text `row-40 dropdown a11y — progressive enhancement only` into the HTML
# of every built page. Three reviewers flagged it independently, and it had
# been on staging and on production, because the marker sets above only match
# literal strings and nothing in them covered the project's own bookkeeping.
# These shapes belong to the private ledger, thread and decision records and
# to local checkouts; a campaign page never contains them.
#
# Literal substring matching cannot express "row 40" or "thr_abc123", so the
# rule needs patterns. Every scan_text/scan_file/scan_tree caller inherits
# these; the literal marker argument still works and still applies.
#
# The row forms are the deliberate part. The hyphenated id (`row-40`) and the
# spelled-out form ("ledger row 40") are unambiguous. A bare "row 40" is only
# a ledger reference when it opens a provenance note, so that pattern demands
# a following "(" or ":" — ordinary prose about a table row, and the
# stylesheet's own "nav row 909px", stay clean.
INTERNAL_REFERENCE_PATTERNS = (
    re.compile(r"\brow-\d+\b", re.IGNORECASE),          # row-40
    re.compile(r"\bledger rows? \d+\b", re.IGNORECASE),  # ledger row 40
    re.compile(r"\brow \d{1,3}\s*[:(]"),                 # row 40 (2026-10-15)
    re.compile(r"\bthr_[A-Za-z0-9]+"),                   # bb thread id
    re.compile(r"\bdec_[A-Za-z0-9]+"),                   # bb decision id
    re.compile(r"\bproj_[A-Za-z0-9]+"),                  # bb project id
    re.compile(r"gate-reports?/", re.IGNORECASE),        # gate-report dir
    re.compile(r"\b\d{4}-\d{2}-\d{2}-\d+\.json\b"),      # 2026-11-24-1.json
    re.compile(r"/Users/"),                              # absolute local path
    # 2026-11-24, second pass: the copied map pages carried audit-cycle
    # citations in their marker a11y comments ("staging audit issue #4") and
    # the stylesheet cited "page-structure review, fix N" and a "staging
    # audit, digest #4". The audit cycle is internal bookkeeping. The bare
    # "digest #"/"issue #" forms are deliberately NOT patterns: a newsletter
    # issue number is legitimate public copy, and both leaks sit inside the
    # "staging audit" phrase, which this entry covers whole.
    re.compile(r"staging audit", re.IGNORECASE),
)

# Nothing whose path smells like internal material is ever copied into a
# published tree, whatever it claims to contain. Casefolded substring match
# against every path component.
FORBIDDEN_PATH_PATTERNS = (
    "transcripts",
    "website-change-requests",
    "gap-analysis",
    "pull-provenance",
    "ledger",
    "chat-export",
)

BINARY_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".zip", ".mp3", ".mp4",
}

MAP_DIRNAME = "map"
MAP_FILES = ("embed.html", "map.html", "styles.css")

# The verbatim homepage banner (ledger row 5). The tests pin it from here so
# the banner has one source of truth. It is NOT a comparison fallback any more:
# the operator ruled on 2026-11-24 that publish.py's served-index check is
# strict after the strip, so a page that merely contains this line is not the
# built page and does not pass.
BANNER_TEXT = ("Tell our leaders to stop tank farms from dumping hazardous "
               "pollutants in our neighborhoods.")

SITE_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The standalone map pages are generated in the private tank-farms repo
# (docs/). By default the sibling checkout supplies them; PSP_MAP_DOCS_DIR
# overrides the location explicitly.
SIBLING_MAP_DOCS = os.path.join(
    os.path.dirname(SITE_REPO_ROOT), "south-portland-tank-farms", "docs")

# Research chrome on the standalone map page (tank-farms repo docs/map.html):
# the header nav links the research pages + private repo, and the sidebar
# carries the same four links. Both are cut; the brand header and the map
# sidebar prose stay. The post-strip marker scan is the hard gate.
HEADER_NAV_RE = re.compile(r"<nav>.*?</nav>", re.DOTALL)
SIDEBAR_LINKS_RE = re.compile(
    r'<p style="margin-top:8px">\s*<a class="side-link".*?</p>', re.DOTALL)

# Only the root README.md is published; any other .md in the tree is a leak.
PUBLISHED_MD_ALLOWLIST = ("README.md",)


# Internal provenance in the copied map pages (2026-11-24): the standalone
# map pages carried their audit-cycle citations in the marker a11y comments
# ("staging audit issue #4"). That is internal bookkeeping, not part of the
# page, so the copy step drops the citation and keeps the rest of the note.
# The sibling repo cleaned its own copies too, but this rail is what keeps a
# future copy from shipping one: the map pages are regenerated from that
# checkout, so editing docs/map/ alone would not survive the next build. The
# marker scan after the strip is the hard gate.
INTERNAL_PROVENANCE_RE = re.compile(
    r"\s*(?:PSP\s+)?staging audit(?:,?\s+(?:issue|digest)\s*#?\s*\d+)?[:,]?\s*",
    re.IGNORECASE)


def strip_internal_provenance(text):
    """Drop audit-cycle citations from a copied page, keep the note around it.

    Cutting only, never rewriting content: an unmatched shape stays put and
    the post-copy scan fails loud on it.
    """
    return INTERNAL_PROVENANCE_RE.sub("", text)


def strip_research_chrome(html):
    """Remove tank-farms research chrome from the standalone map page.

    Cutting only, never rewriting content. Callers must run the marker scan
    on the result — the scan, not the regexes, is the hard gate.
    """
    html = HEADER_NAV_RE.sub("", html, count=1)
    html = SIDEBAR_LINKS_RE.sub("", html, count=1)
    return html


def find_map_source_docs():
    """Directory holding the standalone map pages, or None if unavailable."""
    env_path = os.environ.get("PSP_MAP_DOCS_DIR")
    if env_path:
        if not os.path.isdir(env_path):
            raise SystemExit(f"PSP_MAP_DOCS_DIR={env_path!r}: not a directory")
        return env_path
    return SIBLING_MAP_DOCS if os.path.isdir(SIBLING_MAP_DOCS) else None


def scan_text(text, label, markers=ALL_MARKERS,
             patterns=INTERNAL_REFERENCE_PATTERNS + (PRIVATENAME_PATTERN,)):
    """Violations for one text blob (case-insensitive); empty list = clean.

    Checks the literal marker set and the internal-reference pattern set, so
    an internal ledger or thread reference fails the same gate as a research
    link. Callers that pass their own markers still get the patterns.
    """
    lines = text.splitlines()
    folded = text.casefold()
    violations = []
    for marker in markers:
        needle = marker.casefold()
        if needle not in folded:
            continue
        hit = next(
            ((i, line.strip()) for i, line in enumerate(lines, 1)
             if needle in line.casefold()),
            None,
        )
        if hit:
            line_no, snippet = hit
            if len(snippet) > 120:
                at = snippet.casefold().find(needle)
                snippet = "…" + snippet[max(0, at - 40):at + 70] + "…"
            violations.append(f'{label}: marker "{marker}" line {line_no}: {snippet}')
        else:
            violations.append(f'{label}: marker "{marker}" (spans lines)')
    for pattern in patterns:
        match = pattern.search(text)
        if match is None:
            continue
        line_no = text.count("\n", 0, match.start()) + 1
        line = lines[line_no - 1].strip() if line_no <= len(lines) else ""
        if len(line) > 120:
            at = max(0, match.start() - (text.rfind("\n", 0, match.start()) + 1))
            line = "…" + line[max(0, at - 40):at + 70] + "…"
        violations.append(
            f'{label}: internal reference "{match.group(0)}" line {line_no}: {line}')
    return violations


def scan_file(path, label, markers=ALL_MARKERS):
    """Violations for one file; binary formats are skipped, not suppressed."""
    ext = os.path.splitext(path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return []
    text = open(path, encoding="utf-8", errors="replace").read()
    return scan_text(text, label, markers=markers)


def scan_tree(tree_dir, markers=ALL_MARKERS):
    """Violations for a whole tree: marker strings, forbidden paths, .md rule.

    Every file is scanned as text unless it is a known-binary format, so an
    unknown file type containing private content still fails loudly.
    """
    violations = []
    for dirpath, dirnames, filenames in os.walk(tree_dir):
        dirnames.sort()
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fname in sorted(filenames):
            rel = os.path.relpath(
                os.path.join(dirpath, fname), tree_dir).replace(os.sep, "/")
            for part in rel.split("/"):
                folded = part.casefold()
                for pattern in FORBIDDEN_PATH_PATTERNS:
                    if pattern in folded:
                        violations.append(
                            f'{rel}: forbidden path component "{pattern}"')
            if rel.lower().endswith(".md"):
                if rel not in PUBLISHED_MD_ALLOWLIST:
                    violations.append(
                        f"{rel}: .md files are not published "
                        f"(allowed: {', '.join(PUBLISHED_MD_ALLOWLIST)})")
            violations.extend(scan_file(os.path.join(tree_dir, *rel.split("/")), rel, markers=markers))
    return violations


def assert_clean(violations, what):
    if violations:
        report = "\n".join(f"  - {v}" for v in violations)
        raise SystemExit(
            f"{what}: {len(violations)} publication-safety violation(s)\n"
            f"{report}\n"
            "Fix the source (or the copy step) and re-run. Nothing is "
            "published while violations remain.")


def copy_map_pages(out_dir, src_docs):
    """Copy the map pages into out_dir/map/, strip their research chrome and
    internal provenance, and fail loud if anything private survives.

    The copies are cut, never rewritten: research header/sidebar links come
    off map.html, audit-cycle citations come off every file's comments, and
    the marker scan on the result is the hard gate.
    """
    map_out = os.path.join(out_dir, MAP_DIRNAME)
    os.makedirs(map_out, exist_ok=True)
    written = []
    for name in ("embed.html", "styles.css"):
        text = open(os.path.join(src_docs, name), encoding="utf-8").read()
        open(os.path.join(map_out, name), "w", encoding="utf-8").write(
            strip_internal_provenance(text))
        written.append(f"map/{name}")
    stripped = strip_internal_provenance(strip_research_chrome(
        open(os.path.join(src_docs, "map.html"), encoding="utf-8").read()))
    open(os.path.join(map_out, "map.html"), "w", encoding="utf-8").write(stripped)
    written.append("map/map.html")
    assert_clean([violation for name in MAP_FILES
                  for violation in scan_file(os.path.join(map_out, name), f"map/{name}")],
                 "copied map pages")
    return written


def refresh_map_dir(out_dir):
    """Map pages into out_dir/map/ from the freshest available source.

    - Source checkout present (or PSP_MAP_DOCS_DIR set): copy + strip + scan.
    - No source, existing map dir (e.g. the committed copy a CI checkout
      rebuilds on): leave files untouched but scan them.
    - Neither: no-op; tools/publish.py fails loudly when publishing without
      a map, while plain site builds simply don't get one.
    Returns the copied list, or None when absent.
    """
    src = find_map_source_docs()
    map_out = os.path.join(out_dir, MAP_DIRNAME)
    if src:
        return copy_map_pages(out_dir, src)
    if os.path.isdir(map_out):
        assert_clean([violation for name in MAP_FILES
                      for violation in scan_file(os.path.join(map_out, name), f"map/{name}")],
                     "pre-existing map dir (no fresh source; scanned as-is)")
        return None
    return None