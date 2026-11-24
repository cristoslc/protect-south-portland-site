#!/usr/bin/env python3
"""Publish the public mirror: tests -> build -> scan -> single-commit push.

One command builds the site into docs/, stages the exact publish tree
(campaign pages + local assets + the standalone map under map/), scans it
for everything private or draft-flavored, force-pushes ONE fresh commit
(no inherited history) to the mirror repo, and makes sure Pages serves the
mirror's main branch root. Tests run via the pytest binary on PATH when it
exists (uv-managed installs often lack it in the executing interpreter),
falling back to python3 -m pytest.

The mirror is the public face, so publication requires the reviewer's
per-page gate report (AGENTS.md "Public website release gate"):

    {"date": "2026-10-13",
     "review_model": "ollama-cloud/glm-5.3",
     "review_class": "full",
     "pages": {"index.html": {"rounds": 1, "outcome": "pass",
                              "sha256": "<sha256 of site/pages/index.html>"}}}

Every page under site/pages/ must appear with outcome "pass", a rounds count
in 0-3, and the sha256 of the file as it stands now; the report must state a
full-class reviewer and must not name a flash model. Anything else aborts
loudly and the copy escalates to the operator instead of being published.
Write reports with tools/gate_report.py, which stamps the hashes for you.

Usage:
  python3 tools/publish.py --gate-report ../gate-reports/<date>.json
      (staging leg — the DEFAULT target since the 2026-10-14 staging-first
       directive: pushes the rebuilt tree to the staging mirror, keeping
       and re-verifying its existing custom domain)
  python3 tools/publish.py --gate-report ... --mirror-dir /tmp/psp-mirror-check
      (local verification: same staging + scan + commit against a scratch
       git repo; never contacts GitHub)
  python3 tools/publish.py --gate-report ... \
      --repo cristoslc/protect-south-portland-published
      (production leg — explicit only; per AGENTS.md "Deployment policy"
       it runs only after the staging leg has operator sign-off)
  python3 tools/publish.py --gate-report ... --repo <owner/name> \
      --domain <hostname>
      (same pipeline against another public repo — orphan commit, gate
       report, marker scan, Pages enable with the custom domain; then
       https://<hostname> is verified over a hostname-valid TLS
       connection and https_enforced is set once the certificate is
       approved (--no-wait-https skips the wait))

A publish never silently clears a custom domain its target repo already
carries: without --domain the existing hostname is auto-kept (re-staged
as the tree's CNAME and re-verified), --domain replaces it, and
--allow-domain-drop clears it explicitly. Legacy "branch" builds read
the domain from the CNAME file, so a CNAME-less staged tree would drop
it on the next Pages build.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zoneinfo

import psp_public

ROOT = psp_public.SITE_REPO_ROOT
# Publish targets (operator directive 2026-10-14, staging first): the
# DEFAULT target is the staging mirror; the production mirror is reached
# ONLY with an explicit --repo, and that leg runs only after staging
# sign-off (../docs/runbooks/psp-staging-first-deployment.md).
STAGING_REPO = "cristoslc/protect-south-portland-staging"
PROD_REPO = "cristoslc/protect-south-portland-published"
DEFAULT_REPO = STAGING_REPO

# Ledger row 42 (operator directive, 2026-10-15): staging obscurity + cookie
# gate. The staging leg (and ONLY the leg that targets STAGING_REPO) applies
# three layers to the tree right before the orphan commit: a Disallow-all
# robots.txt, a noindex/nofollow meta on every staged page, and a JS cookie
# gate whose embedded value is ONLY the passphrase's SHA-256 — the passphrase
# itself arrives at publish time (PSP_STAGING_PASSPHRASE env or the
# gitignored .env beside the checkout) and a missing value refuses the leg
# loud. Honest threat model: robots/noindex are real crawl protection; the
# cookie gate is DETERRENCE (Pages serves the full HTML regardless of JS).
# Production carries none of it: the gate marker is a private-surface marker
# in psp_public, so a gated tree fails any prod leg's scan loud.
STAGING_GATE = True
ENV_NAME = "PSP_STAGING_PASSPHRASE"
STAGING_DOTENV = os.path.join(os.path.dirname(ROOT), ".env")
GATE_COOKIE = "psp_staging"
GATE_MARKER = "staging-gate"

# Row 57 (2026-11-04): content-addressed gate reports. A page entry carries
# the sha256 of the source file it reviewed, so a verdict cannot outlive its
# content; and the report states the reviewer class explicitly, so the flash
# rule (AGENTS.md release gate) is enforced rather than trusted. The marker
# list is open-ended on purpose: a model rename must not defeat the class
# rule, and the class field is what actually gates.
REVIEW_CLASSES = ("full",)
FLASH_MARKERS = ("flash",)

GATE_ROBOTS_TEXT = (
    "# Staging mirror variant — not the production site.\n"
    "User-agent: *\n"
    "Disallow: /\n"
)

# Ledger row 79 (2026-11-24): the staging preview's publish-time stamp. The
# staging mirror carries a small masthead line saying when it was last
# published, so whoever opens a preview URL knows which build they are looking
# at. It rides the SAME boundary as the row-42 gate: injected into the staged
# tree, on the staging leg only, after the mirror scan and before the orphan
# commit. Its marker joins psp_public's private-surface set, so a tree that
# somehow carries the stamp fails a production leg's scan loud. The time is the
# PUBLISH clock, not a content date: no page says it, the leg computes it from
# the moment it runs, and the same clock is recorded in the publish commit.
STAMP_MARKER = "staging-updated"
STAMP_ZONE = "America/New_York"  # South Portland, Maine
STAMP_PREFIX = "Staging preview, updated "
# build.py's masthead opening tag. The stamp anchors on it, so a masthead
# rewrite refuses the leg loudly instead of quietly stamping nothing.
STAMP_ANCHOR = '<header class="masthead">'

# The stamp's rules travel with the stamp, never in site/styles.css: the
# stylesheet is production's as well. The background repeats as a literal first
# so the strip stays legible if the palette variable is missing (white text on
# white would not be). Contrast: #e6f1f1 on #122a2c is 13.1:1, well past AA.
STAMP_CSS = """<style>
/* Row 79, staging leg only: the publish-time strip above the masthead's inner
   row. It must never exist in site/styles.css, which production serves too. */
.masthead > .staging-updated{margin:0;padding:5px 20px;background:#122a2c;background:var(--teal-950);color:#e6f1f1;font-size:.8rem;line-height:1.45;font-weight:600;letter-spacing:.01em;text-align:center}
@media (max-width:520px){.masthead > .staging-updated{padding:4px 12px;font-size:.72rem}}
</style>"""

# The comparison boundary (operator, 2026-11-24). The production lane verifies
# a staging tree by fetching the HTML staging serves and comparing it against
# the page hashes in the gate report. Both publish-time injections (row 42's
# gate block, row 79's stamp) make a served page differ from the bytes the
# report hashed, so every injected region is wrapped in a paired comment
# carrying its marker. ONE function strips all of them, by marker, so the two
# can never drift apart into separate strips. A page that goes through
# strip_injected_blocks and then does not hash to the report's sha256 is a real
# difference, and the comparison must fail loudly on it rather than get waived.
INJECTED_BLOCK_MARKERS = (GATE_MARKER, STAMP_MARKER)


def injected_block_open(marker):
    return f"<!-- {marker}:injected -->"


def injected_block_close(marker):
    return f"<!-- /{marker}:injected -->"


def strip_injected_blocks(text):
    """Remove every publish-time injection from served HTML.

    The single strip at the comparison boundary, for both row 42's gate block
    and row 79's stamp. Each injection writes a paired marker comment around
    itself and nothing else, so removing both regions restores the page to the
    exact bytes the build produced and the gate report hashed. Deliberately one
    function: a second, parallel strip would drift the first time one of the
    two blocks changed shape.
    """
    for marker in INJECTED_BLOCK_MARKERS:
        pattern = re.compile(
            re.escape(injected_block_open(marker)) + r".*?"
            + re.escape(injected_block_close(marker)), re.DOTALL)
        text = pattern.sub("", text)
    return text


def repo_pages_base(repo):
    """GitHub Pages URL root for a repo: https://{owner}.github.io/{name}."""
    owner, _, name = repo.partition("/")
    return f"https://{owner}.github.io/{name}"


# Row-42 gate, injected as ONE block right after every staged page's <head>:
# the noindex meta, a static stylesheet that hides the page before any script
# runs, and the cookie-gate script. The stylesheet is a real <style> tag: the
# first version built it with createElement and never appended it, so the
# curtain rendered unstyled and the body stayed readable (fixed 2026-11-04).
# Placeholder @HASH@ becomes the passphrase's sha256 digest.
GATE_HEAD_BLOCK = r'''<meta name="robots" content="noindex, nofollow">
<style>
.staging-gate body{visibility:hidden!important}
.staging-gate-overlay{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;background:#122a2c;color:#e6f1f1;font:16px/1.5 'Segoe UI',system-ui,sans-serif}
.staging-gate-card{background:#fff;color:#26383a;padding:22px 26px;border-radius:14px;max-width:22rem;box-shadow:0 2px 14px rgba(0,0,0,.35)}
.staging-gate-title{margin:0 0 10px;font-weight:800;color:#1d3e40}
.staging-gate-label{display:block;margin-bottom:6px;font-size:.85rem;color:#5c6b6d}
.staging-gate-input{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid #dde8e8;border-radius:8px;font:inherit}
.staging-gate-submit{margin-top:10px;padding:9px 16px;border:0;border-radius:999px;background:#b8401a;color:#fff;font-weight:800;cursor:pointer}
.staging-gate-wrong{margin:8px 0 0;color:#b8401a;font-size:.85rem}
</style>
<script>
(function () {
  /* Staging review gate (row 42): deterrence-grade, staging mirror only. */
  var REQUIRED = "@HASH@";
  var COOKIE = "psp_staging";
  var docEl = document.documentElement;
  docEl.className += " staging-gate";
  function cookieValue() {
    var parts = document.cookie.split(/;\s*/);
    for (var i = 0; i < parts.length; i++) {
      var pair = parts[i].split("=");
      if (pair[0] === COOKIE) return pair[1];
    }
    return null;
  }
  function reveal() {
    docEl.className = docEl.className.replace(" staging-gate", "");
    var overlay = document.querySelector(".staging-gate-overlay");
    if (overlay && overlay.parentElement) overlay.parentElement.removeChild(overlay);
  }
  function hex(buffer) {
    var out = [], bytes = new Uint8Array(buffer);
    for (var i = 0; i < bytes.length; i++) out.push(("0" + bytes[i].toString(16)).slice(-2));
    return out.join("");
  }
  function boot() {
    if (cookieValue() === REQUIRED) { reveal(); return; }
    if (!window.crypto || !crypto.subtle) {
      // fail closed with a plain message: no digest API, no check, no page
      // (real staging serves over TLS or 127.0.0.1, where subtle exists)
      card = document.createElement("div");
      card.className = "staging-gate-card";
      card.textContent = "This browser cannot verify the access phrase.";
      var shell = document.createElement("div");
      shell.className = "staging-gate-overlay";
      shell.appendChild(card);
      docEl.appendChild(shell);
      return;
    }
    var overlay = document.createElement("div");
    overlay.className = "staging-gate-overlay";
    var card = document.createElement("div");
    card.className = "staging-gate-card";
    card.innerHTML = '<p class="staging-gate-title">Staging review</p>' +
      '<form><label class="staging-gate-label" for="staging-gate-phrase">Enter access phrase</label>' +
      '<input class="staging-gate-input" id="staging-gate-phrase" type="password" autocomplete="off">' +
      '<button class="staging-gate-submit" type="submit">Enter</button>' +
      '<p class="staging-gate-wrong" hidden>Access phrase not recognized.</p></form>';
    overlay.appendChild(card);
    docEl.appendChild(overlay);
    var input = card.querySelector(".staging-gate-input");
    card.querySelector("form").addEventListener("submit", function (event) {
      event.preventDefault();
      crypto.subtle.digest("SHA-256", new TextEncoder().encode(input.value))
        .then(function (digest) {
          if (hex(digest) === REQUIRED) {
            document.cookie = COOKIE + "=" + REQUIRED +
              "; Path=/; Secure; SameSite=Lax; Max-Age=2592000";
            reveal();
          } else {
            card.querySelector(".staging-gate-wrong").hidden = false;
            input.value = "";
            input.focus();
          }
        });
    });
    input.focus();
    window.addEventListener("load", function () {
      /* the embedded map iframe can take focus as it loads; take it back */
      if (document.querySelector(".staging-gate-overlay")) input.focus();
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
</script>'''


def dotenv_value(path, key):
    """The last KEY=VALUE hit for key in a minimal dotenv file (no deps)."""
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip()
    return None


def staging_passphrase():
    """The staging passphrase: PSP_STAGING_PASSPHRASE env first, then the
    gitignored .env beside the checkout. Missing = loud refusal, no
    placeholder, no default (row 42)."""
    value = os.environ.get(ENV_NAME, "").strip()
    if value:
        return value
    if os.path.exists(STAGING_DOTENV):
        found = dotenv_value(STAGING_DOTENV, ENV_NAME)
        if found:
            return found
    raise SystemExit(
        f"{ENV_NAME} missing: the staging gate needs the passphrase in the "
        f"environment or {STAGING_DOTENV} — refusing to publish a gate it "
        "cannot key properly")


def apply_staging_gate(tree, passphrase):
    """Row 42, staging leg only: write the Disallow-all robots.txt (staging
    variant) and inject the noindex meta + cookie-gate script after every
    staged page's <head>. Refuses louder variants: a tree that already
    carries robots.txt or the gate marker (double-gate), and any staged
    page without a <head> to protect. Returns the gated page count."""
    # docs/ ships a tracked Allow-all robots.txt that reaches every staged
    # tree; the staging variant REWRITES it (row 42)
    open(os.path.join(tree, "robots.txt"), "w", encoding="utf-8").write(GATE_ROBOTS_TEXT)
    digest = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
    block = GATE_HEAD_BLOCK.replace("@HASH@", digest)
    headless = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            text = open(path, encoding="utf-8").read()
            if GATE_MARKER in text:
                raise SystemExit(f"{path}: already gated — refusing a double gate")
            if "<head>" not in text:
                headless.append(os.path.relpath(path, tree))
                continue
            open(path, "w", encoding="utf-8").write(
                text.replace(
                    "<head>",
                    "<head>" + injected_block_open(GATE_MARKER) + "\n" + block
                    + "\n" + injected_block_close(GATE_MARKER), 1))
            count += 1
    if headless:
        raise SystemExit(
            "staged page(s) carry no <head> — the gate cannot protect them, "
            "refusing: " + ", ".join(headless))
    return count


def staging_leg_gated(repo):
    """True only for the staging mirror's leg.

    Row 42's gate and row 79's stamp both ride this one leg; a production leg
    (explicit --repo) carries neither, and the marker sets in psp_public turn a
    leaked one into a loud scan failure at the other end.
    """
    return repo == STAGING_REPO and STAGING_GATE


def stamp_label(when):
    """The staging stamp's line for one instant, in South Portland's zone.

    `when` is the publish clock, so it must carry a timezone: a naive datetime
    would silently mean whatever zone the publishing host runs in, which is a
    wrong label nobody would notice.
    """
    if when.tzinfo is None:
        raise SystemExit(
            "row 79 stamp: a naive datetime has no publish clock — pass an "
            "aware datetime (main() passes the UTC publish instant)")
    try:
        zone = zoneinfo.ZoneInfo(STAMP_ZONE)
    except zoneinfo.ZoneInfoNotFoundError as exc:
        raise SystemExit(
            f"row 79 stamp: time zone {STAMP_ZONE!r} is unavailable ({exc}); "
            "install tzdata so the stamp can name South Portland's local time "
            "instead of guessing one") from exc
    local = when.astimezone(zone)
    hour = local.strftime("%I").lstrip("0") or "12"
    return (f"{STAMP_PREFIX}{local.strftime('%b')} {local.day}, {local.year} "
            f"at {hour}:{local.strftime('%M %p')} {local.strftime('%Z')}")


def apply_staging_update_stamp(tree, when):
    """Row 79, staging leg only: write the publish-time line into every staged
    page's masthead and its rules into the head. Returns the stamped page count.

    The line is chrome, not copy: it sits inside <header class="masthead"> and
    above .masthead__inner, so the logo and the nav row keep their own layout.
    Pages without a masthead are only the redirect stubs (which navigate away)
    and the chrome-free map pages under map/; anything else refuses the leg
    loud, because a preview that says "updated" on some pages and not others is
    the bug this guard exists to prevent. Validated before anything is written,
    and a second pass is refused rather than stacked.
    """
    label = stamp_label(when)
    line = (injected_block_open(STAMP_MARKER)
            + f'\n  <p class="{STAMP_MARKER}">{label}</p>\n'
            + injected_block_close(STAMP_MARKER))
    stampable = []
    refused = []
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, tree)
            text = open(path, encoding="utf-8").read()
            if STAMP_MARKER in text:
                raise SystemExit(f"{path}: already stamped — refusing a second stamp")
            if STAMP_ANCHOR not in text:
                if rel.split(os.sep)[0] == psp_public.MAP_DIRNAME:
                    continue  # chrome-free standalone map page: no masthead
                if '<meta http-equiv="refresh"' in text:
                    continue  # redirect stub: no chrome, navigates away on load
            if STAMP_ANCHOR not in text or "<head>" not in text:
                refused.append(rel)
                continue
            stampable.append(path)
    if refused:
        raise SystemExit(
            "staged page(s) carry no masthead or no <head> to stamp — refusing "
            "to stamp some pages and not others: " + ", ".join(refused))
    for path in stampable:
        text = open(path, encoding="utf-8").read()
        text = text.replace(
            "<head>",
            "<head>" + injected_block_open(STAMP_MARKER) + "\n" + STAMP_CSS
            + "\n" + injected_block_close(STAMP_MARKER), 1)
        text = text.replace(STAMP_ANCHOR, STAMP_ANCHOR + line, 1)
        open(path, "w", encoding="utf-8").write(text)
    return len(stampable)


def repo_url(repo):
    """HTTPS clone URL for a publishes-to repo."""
    return f"https://github.com/{repo}.git"


def default_mirror_dir(repo):
    """Default checkout for a publish target: a sibling of the site repo
    named after the repo (protect-south-portland-published ->
    ../protect-south-portland-published)."""
    return os.path.join(os.path.dirname(ROOT), repo.partition("/")[2])

# Staged for the later DNS flip in the site repo; the mirror keeps its
# default github.io URL until the operator moves the domain over.
# .gitkeep is a repo artifact, not site content.
PUBLISH_EXCLUDES = ("CNAME", ".gitkeep")

# The mirror README is fixed public text, rebuilt fresh on every publish.
MIRROR_README_TEXT = """# Protect South Portland

Public snapshot of the Protect South Portland campaign website, maintained
by volunteers in South Portland, Maine.

- Start at `index.html`.
- The standalone interactive map lives at `map/map.html`; the homepage and
  the tank-farms page embed the chrome-free version at `map/embed.html`.

This repository is a generated snapshot, rebuilt in full on every publish.
"""

# Publish pushes what is committed; build output (docs/) is the only path
# allowed to differ, because publishing regenerates it.
REQUIRED_CLEAN_PATHS = (".github", "AGENTS.md", "README.md", "site", "tests", "tools")


def run(cmd, cwd=ROOT):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    return proc.stdout.strip()


def page_sha256(name, docs_dir=None):
    """sha256 of a page's BUILT file — the content a verdict reviewed and the
    content the mirror ships. Hashing the source page alone missed shared
    chrome (the footer strip, injected by build.py), so a chrome-only change
    could publish against stale verdicts.

    docs_dir overrides the build tree (tests pass their own build; production
    leaves it None = the repo's docs/).
    """
    path = os.path.join(docs_dir or os.path.join(ROOT, "docs"), name)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def served_page_sha256(served_text):
    """sha256 of a page as a visitor's browser receives it, publish-time
    injections stripped. This is the hash the gate report can be compared to."""
    return hashlib.sha256(
        strip_injected_blocks(served_text).encode("utf-8")).hexdigest()


def served_page_matches(served_text, name, docs_dir=None):
    """True when the served page, minus the two publish-time injections, is
    byte-equal to the built page whose hash the gate report carries.

    This is the comparison the production lane runs against a staging tree.
    Anything that differs after the strip is a real difference and must be
    treated as one.
    """
    return served_page_sha256(served_text) == page_sha256(name, docs_dir=docs_dir)


def load_gate_report(path):
    """Validate the gate report and return (model, class, outcomes line).

    Two invariants since 2026-11-04 (row 57), both fail-loud:

    1. CONTENT-ADDRESSED VERDICTS. Every page entry carries the sha256 of the
       source file it reviewed. A page publishes only when that hash matches
       the file as it stands now, so a verdict cannot outlive its content. A
       fixup-scoped report can no longer cover untouched pages, and a page
       edited after review is refused by name. Legacy reports without hashes
       are refused outright, not trusted by default: nothing can prove what
       they reviewed.
    2. REVIEWER CLASS. The report states review_class explicitly and it must
       be "full"; a review_model carrying a flash marker is refused even when
       the class field claims full. The model string alone is never trusted.
    """
    raw = json.load(open(path, encoding="utf-8"))
    problems = []
    model = raw.get("review_model")
    model = model.strip() if isinstance(model, str) else ""
    if not model:
        problems.append(f"{path}: missing review_model")
    review_class = raw.get("review_class")
    review_class = review_class.strip().lower() if isinstance(review_class, str) else ""
    if not review_class:
        problems.append(
            f"{path}: review_class missing — the release gate requires a "
            f"full-class reviewer; add \"review_class\": \"full\"")
    elif review_class not in REVIEW_CLASSES:
        problems.append(
            f"{path}: review_class {review_class!r} is not full — the release "
            f"gate accepts only {', '.join(REVIEW_CLASSES)} (AGENTS.md "
            "\"Public website release gate\")")
    for marker in FLASH_MARKERS:
        if marker in model.casefold():
            problems.append(
                f"{path}: review_model {model!r} carries the flash marker "
                f"{marker!r} — flash variants never issue the verdict "
                "(AGENTS.md release gate)")
    pages = raw.get("pages")
    if not isinstance(pages, dict) or not pages:
        problems.append(f"{path}: missing per-page outcomes")
        pages = {}
    for page in sorted(os.listdir(os.path.join(ROOT, "site", "pages"))):
        if not page.endswith(".html"):
            continue
        entry = pages.get(page)
        if not entry:
            problems.append(f"{page}: NOT REVIEWED — absent from the gate report")
            continue
        outcome = str(entry.get("outcome", "")).strip().lower()
        rounds = entry.get("rounds")
        if outcome != "pass":
            problems.append(
                f"{page}: outcome {outcome!r} — not published, escalate to the operator")
            continue
        if not isinstance(rounds, int) or not 0 <= rounds <= 3:
            problems.append(f"{page}: rounds {rounds!r} outside 0-3")
            continue
        reviewed = entry.get("sha256")
        reviewed = reviewed.strip().lower() if isinstance(reviewed, str) else ""
        if not reviewed:
            problems.append(
                f"{page}: no sha256 in the gate report — a content-addressed "
                "verdict is required; re-review the page before publishing")
            continue
        current = page_sha256(page)
        if reviewed != current:
            problems.append(
                f"{page}: sha256 mismatch — reviewed {reviewed}, current "
                f"{current} (re-review the page or restore the reviewed content)")
    if problems:
        raise SystemExit(
            "gate failures — nothing is published:\n  " + "\n  ".join(problems))
    per_page = ", ".join(
        f"{p} r{pages.get(p, {}).get('rounds', '?')}"
        for p in sorted(k for k in pages if k.endswith(".html")))
    return model, review_class, per_page



def require_clean_worktree():
    for path in REQUIRED_CLEAN_PATHS:
        status = run(["git", "status", "--porcelain", "--", path])
        if status:
            raise SystemExit(
                f"{path}: uncommitted changes — the mirror snapshots what is "
                "committed, so commit first:\n" + status)


def build_site():
    pytest_bin = shutil.which("pytest")
    run([pytest_bin, "-q", "tests"] if pytest_bin
        else [sys.executable, "-m", "pytest", "-q", "tests"])
    run([sys.executable, "tools/build.py", "docs"])
    map_out = os.path.join(ROOT, "docs", psp_public.MAP_DIRNAME)
    missing = [name for name in psp_public.MAP_FILES
               if not os.path.exists(os.path.join(map_out, name))]
    if missing:
        raise SystemExit(
            "docs/map/ incomplete (missing: " + ", ".join(missing) + "): the "
            "standalone map pages come from the tank-farms checkout "
            "(../south-portland-tank-farms/docs) or PSP_MAP_DOCS_DIR; the "
            "site repo alone cannot publish the map.")


def stage_publish_tree(staging, cname=None, docs_dir=None):
    """Copy docs/ minus the CNAME/.gitkeep, add the fixed README, scan.

    With --domain the given hostname is staged as the tree's CNAME (the
    site repo's own docs/CNAME — the production flip — stays excluded
    unless the operator publishes with --domain that hostname).
    docs_dir overrides the source build tree (tests use the built fixture;
    production always leaves it None = the repo's docs/).
    """
    docs = docs_dir or os.path.join(ROOT, "docs")
    for entry in sorted(os.listdir(docs)):
        if entry in PUBLISH_EXCLUDES:
            continue
        src = os.path.join(docs, entry)
        dst = os.path.join(staging, entry)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    open(os.path.join(staging, "README.md"), "w", encoding="utf-8").write(MIRROR_README_TEXT)
    open(os.path.join(staging, ".nojekyll"), "w").write("")
    if cname:
        open(os.path.join(staging, "CNAME"), "w", encoding="utf-8").write(cname + "\n")
    psp_public.assert_clean(psp_public.scan_tree(staging), "staged publish tree")
    return sum(len(files) for _, _, files in os.walk(staging))


def ensure_git_repo(mirror_dir, is_remote_target, repo):
    if os.path.isdir(os.path.join(mirror_dir, ".git")):
        origin = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=mirror_dir, capture_output=True, text=True)
        if is_remote_target:
            if origin.returncode != 0 or repo not in origin.stdout:
                raise SystemExit(
                    f"{mirror_dir}: remote origin is {origin.stdout.strip()!r}, "
                    f"expected the {repo} clone")
        return
    if is_remote_target:
        view = subprocess.run(
            ["gh", "repo", "view", repo, "--json", "url"],
            capture_output=True, text=True)
        if view.returncode != 0:
            run(["gh", "repo", "create", repo, "--public", "--disable-wiki",
                 "--description",
                 "Protect South Portland - published campaign site and map (snapshot)"])
        run(["git", "clone", repo_url(repo), mirror_dir],
            cwd=os.path.dirname(mirror_dir))
    else:
        run(["git", "init", "-b", "main", mirror_dir])


def sync_tree(staging, mirror_dir):
    """Make the mirror worktree exactly equal the staged tree (except .git)."""
    for dirpath, dirnames, filenames in os.walk(staging):
        dirnames.sort()
        for name in dirnames:
            os.makedirs(os.path.join(mirror_dir, os.path.relpath(dirpath, staging), name),
                        exist_ok=True)
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), staging)
            dst = os.path.join(mirror_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(dirpath, name), dst)
    removed = []
    for dirpath, dirnames, filenames in os.walk(mirror_dir):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), mirror_dir)
            if not os.path.exists(os.path.join(staging, rel)):
                os.remove(os.path.join(dirpath, name))
                removed.append(rel)
    for dirpath, dirnames, filenames in os.walk(mirror_dir, topdown=False):
        if ".git" in dirnames:
            dirnames.remove(".git")
        rel = os.path.relpath(dirpath, mirror_dir)
        if rel == ".git" or rel.startswith(".git" + os.sep):
            continue  # empty-object/refs subdirs of a fresh clone are repo internals
        if dirpath != mirror_dir and not os.listdir(dirpath):
            os.rmdir(dirpath)
    return removed


def source_provenance():
    site_sha = run(["git", "rev-parse", "--short", "HEAD"])
    map_sha = ""
    if os.path.isdir(psp_public.SIBLING_MAP_DOCS):
        map_sha = run(["git", "rev-parse", "--short", "HEAD"],
                      cwd=os.path.dirname(psp_public.SIBLING_MAP_DOCS))
    return site_sha, map_sha


def single_commit(mirror_dir, message):
    """Replace the worktree's commit history with one fresh commit.

    Works on an unborn HEAD (fresh init/clone of an empty repo) and on a
    repo that already has a main: existing refs are only ever replaced,
    never extended, so every publish is exactly one commit.
    """
    unborn = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=mirror_dir, capture_output=True).returncode != 0
    if unborn:
        run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=mirror_dir)
    else:
        run(["git", "checkout", "--orphan", "publish-tmp"], cwd=mirror_dir)
    run(["git", "add", "-A"], cwd=mirror_dir)
    run(["git", "commit", "-m", message], cwd=mirror_dir)
    if not unborn:
        run(["git", "branch", "-M", "publish-tmp", "main"], cwd=mirror_dir)
    return run(["git", "rev-parse", "--short", "HEAD"], cwd=mirror_dir)


def ensure_pages_enabled(repo, cname=None):
    proc = subprocess.run(
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages",
         "-f", "build_type=legacy",
         "-f", "source[branch]=main",
         "-f", "source[path]=/"],
        capture_output=True, text=True)
    already = "409" in proc.stderr or "already" in proc.stderr.lower()
    if proc.returncode != 0 and not already:
        raise SystemExit(f"enabling Pages failed:\n{proc.stderr}")
    if cname:
        proc = subprocess.run(
            ["gh", "api", "-X", "PUT", f"repos/{repo}/pages",
             "-f", f"cname={cname}"],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(
                f"setting the Pages custom domain {cname} failed:\n{proc.stderr}")
        check = subprocess.run(
            ["gh", "api", f"repos/{repo}/pages"],
            capture_output=True, text=True)
        if check.returncode != 0:
            raise SystemExit(f"reading back Pages settings failed:\n{check.stderr}")
        state = json.loads(check.stdout)
        if state.get("cname") != cname:
            raise SystemExit(
                f"Pages custom domain is {state.get('cname')!r}, "
                f"expected {cname!r}")


def wait_for_pages(urls, minutes=8, allowed_domains=None):
    """Wait for the URLs to serve 200, asserting the redirect chain stays
    under the allowed set.

    allowed_domains=None (the github.io verification pass) requires the
    FINAL URL to stay under *.github.io: when it lands elsewhere (the
    custom domain after the flip, or NetSol's forward to Wix), fail loud
    immediately instead of timing out or worse, "verifying" over the
    wrong site's bytes. With --domain the allowed set is exactly that
    hostname.
    """
    pending = list(urls)
    deadline = time.time() + minutes * 60
    while pending and time.time() < deadline:
        still = []
        for url in pending:
            try:
                with urllib.request.urlopen(url, timeout=20) as resp:
                    status, final_url = resp.status, resp.geturl()
            except Exception:
                still.append(url)
                continue
            host = urllib.request.urlsplit(final_url).hostname or ""
            ok = (host in allowed_domains if allowed_domains
                  else host.endswith(".github.io"))
            if not ok:
                raise SystemExit(
                    f"{url}\n  final URL is {final_url!r} (host {host!r})\n"
                    "  custom DNS already live — verify the custom domain "
                    "instead, or DNS not yet moved")
            if status != 200:
                still.append(url)
        pending = still
        if pending:
            time.sleep(15)
    if pending:
        raise SystemExit(
            "Pages not serving after the wait: " + ", ".join(pending) +
            ("\n  (DNS record or TLS certificate for the custom domain may "
             "still be provisioning — cert issuance can take up to 24 hours)"
             if allowed_domains else ""))


def pages_api(repo):
    """GET the repo's Pages settings, or None when Pages is not enabled."""
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/pages"], capture_output=True, text=True)
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    if "404" in proc.stderr or "Not Found" in proc.stderr:
        return None
    raise SystemExit(f"reading Pages settings failed:\n{proc.stderr}")


def cert_state(pages_state):
    """The HTTP-certificate status from a Pages API body, whatever shape
    the API shows today (none so far / dict with .state / plain string)."""
    cert = (pages_state or {}).get("https_certificate")
    if isinstance(cert, dict):
        return cert.get("state")
    return cert


def resolve_publish_domain(state, requested_cname, allow_drop):
    """The publish's effective custom domain, from the target repo's live
    Pages state (None when Pages is not enabled), the explicit --domain
    request, and --allow-domain-drop.

    Staging-first hardening (2026-10-14): a publish never silently clears
    or rewrites a custom domain the target already carries. --domain wins
    and is staged; without --domain the existing hostname is auto-kept
    (the staged tree re-carries its CNAME and the publish re-verifies that
    hostname); --allow-domain-drop alone explicitly clears the domain.
    Legacy "branch" builds read the domain from the CNAME file, so a
    CNAME-less staged tree would drop it on the next Pages build. The
    only hard refusals are the flag-combination conflict and a verified
    custom domain whose cname value cannot be read.

    Returns (effective_cname, violation_reason_or_None).
    """
    current = (state or {}).get("cname")
    protected = (state or {}).get("protected_domain_state") == "verified"
    if requested_cname and allow_drop:
        return None, ("--allow-domain-drop conflicts with --domain: pass "
                      "one or the other, never both")
    if current:
        if allow_drop:
            return None, None
        return (requested_cname or current), None
    if protected and not requested_cname and not allow_drop:
        return None, (
            "this repo's Pages state shows a verified custom domain but "
            "no cname value to keep; a tree staged without --domain would "
            "risk clearing it on the next Pages build. Re-run with "
            "--domain <hostname> to keep publishing against it, or pass "
            "--allow-domain-drop explicitly to drop the custom domain.")
    return requested_cname, None


def domain_stickiness_violation(state, requested_cname, allow_drop):
    """Abort reason, if any, for these flags against this Pages state;
    resolve_publish_domain carries the effective domain."""
    return resolve_publish_domain(state, requested_cname, allow_drop)[1]


def check_domain_stickiness(repo, requested_cname, allow_drop):
    """Pages state + flags -> the effective custom domain for a remote
    target, failing loud on a violation."""
    cname, violation = resolve_publish_domain(
        pages_api(repo), requested_cname, allow_drop)
    if violation:
        raise SystemExit(violation)
    return cname


def tls_cert_subject(host, timeout=20):
    """Peer certificate from a hostname-verified (SNI + SAN matched) TLS
    handshake; a name mismatch or invalid chain raises."""
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    common = next(
        (value for rdn in cert.get("subject", ()) for key, value in rdn
         if key == "commonName"), None)
    return common, cert.get("notAfter")


def index_matches_built(text, index_path):
    """The served index equals the freshly built one once the publish-time
    injections come off. Strict: equal, or the leg stops.

    A staging index serves the row-42 gate block and the row-79 stamp, so a
    raw byte comparison would fail every time, and a check that fails every
    time gets waived. Stripping both regions first makes the comparison pass
    because the bytes match, not because the comparison was loosened.

    There is deliberately NO fallback, and this is a decision rather than an
    omission. Until 2026-11-24 this function also passed when the served page
    merely carried the banner line (ledger row 5). That branch is how a
    stamped page came to look verified: strict equality failed, the fallback
    turned the failure into a pass, and the leg printed success. With the
    strip in place the fallback has no legitimate caller left, and any future
    injection or template tweak would fail equality again with the fallback
    waiting to hide it. A served index that differs from the build after the
    strip is a wrong tree, and the leg must stop.

    BEHAVIOUR CHANGE, named here so nobody is surprised: a `--domain` publish
    whose host serves a page that is not byte-identical to this build (an
    older cached build, for instance) now stops instead of passing on the
    banner line. Re-run the leg when the host is serving the current build.
    """
    if not os.path.exists(index_path):
        return False
    built = open(index_path, encoding="utf-8").read()
    return strip_injected_blocks(text) == strip_injected_blocks(built)


def verify_custom_domain(domain, index_path, minutes=8):
    """Blocking gate: the custom domain must serve the staged tree over a
    hostname-valid TLS connection before the publish claims success."""
    wait_for_pages([f"https://{domain}/",
                    f"https://{domain}/map/embed.html",
                    f"https://{domain}/map/map.html"],
                   minutes=minutes, allowed_domains=(domain,))
    common, not_after = tls_cert_subject(domain)
    with urllib.request.urlopen(f"https://{domain}/", timeout=20) as resp:
        if resp.status != 200:
            raise SystemExit(f"https://{domain}/ returned {resp.status}")
        text = resp.read().decode("utf-8", errors="replace")
    if not index_matches_built(text, index_path):
        raise SystemExit(
            f"https://{domain}/: the served index does not match the "
            f"built index ({index_path}) once the publish-time injections "
            f"are stripped; the tree being served is not the tree that "
            f"was built")
    return f"TLS commonName {common!r} (notAfter {not_after})"


def put_https_enforced(repo):
    proc = subprocess.run(
        ["gh", "api", "-X", "PUT", f"repos/{repo}/pages",
         "-F", "https_enforced=true"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"PUT https_enforced=true failed:\n{proc.stderr}")


def assert_flag_agreement(domain, wait_https):
    """--wait-https/--no-wait-https have no meaning without a custom domain."""
    if wait_https is not None and not domain:
        raise SystemExit(
            "--wait-https/--no-wait-https apply only to custom-domain "
            "publishes: pass --domain as well")


def enforce_https(repo, minutes=60, clock=time.time, pause=time.sleep):
    """Poll the Pages API until the HTTPS certificate is approved, then
    set https_enforced=true. On timeout, fail loud with the manual step —
    never silently continue without encryption."""
    MANUAL = (f"{repo}: HTTPS certificate not approved after {minutes} "
              "minutes. Manual step: repo Pages settings → Enforce HTTPS "
              "once the certificate shows available, then re-run the "
              "verification.")
    deadline = clock() + minutes * 60
    while True:
        state = pages_api(repo) or {}
        if state.get("https_enforced"):
            return state
        if cert_state(state) == "approved":
            put_https_enforced(repo)
            if (pages_api(repo) or {}).get("https_enforced"):
                return pages_api(repo)
        if clock() >= deadline:
            raise SystemExit(MANUAL)
        pause(30)


CHANGELOG_LT = "thr_6sf5hk9f4m"


def resolve_changelog_handoff(handoff, waiver):
    """Rung 2b: a publish cannot proceed on a silent skip; it can proceed on a
    recorded one. Returns the line that goes into the publish commit.

    The handoff is required by default (runbook rung 2b). A waiver is a written
    statement naming what was not captured, and the same text belongs in the
    ledger row for the publish. Refusing here is deliberate: the ladder says the
    changelog is what a reader sees, so skipping it has to leave a trace.
    """
    handoff = (handoff or "").strip()
    waiver = (waiver or "").strip()
    if handoff and waiver:
        raise SystemExit(
            "publish: give either --changelog-handoff or --changelog-waiver, "
            "not both — the commit would record two contradictory statements")
    if handoff:
        return f"Changelog handoff (rung 2b): {handoff}"
    if waiver:
        if len(waiver.split()) < 4:
            raise SystemExit(
                "publish: a changelog waiver must name what was not captured; "
                f"{waiver!r} does not. Say which pages or captures are missing "
                "and why, and put the same text in the ledger row.")
        return f"Changelog handoff waived (rung 2b): {waiver}"
    raise SystemExit(
        "publish: rung 2b — the changelog handoff is required by default.\n"
        f"  Notify the changelog lieutenant ({CHANGELOG_LT}) with the commit, "
        "the changed pages and the gate report, then pass\n"
        "    --changelog-handoff <what it recorded>\n"
        "  If the handoff cannot happen, pass\n"
        "    --changelog-waiver \"<what was not captured, and why>\"\n"
        "  and put the same text in the ledger row for this publish. A publish "
        "may skip the handoff in writing, never silently.")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Publish the public mirror (gate report mandatory).")
    parser.add_argument("--gate-report", required=True,
                        help="JSON file with the reviewer's per-page outcomes")
    parser.add_argument("--changelog-handoff", default=None, metavar="REF",
                        help="what the changelog lieutenant recorded for this "
                             "cycle (entry, capture set or artifact ref); "
                             "required by default — see rung 2b in the runbook")
    parser.add_argument("--changelog-waiver", default=None, metavar="TEXT",
                        help="written waiver for publishing without the "
                             "handoff; must name what was not captured, and the "
                             "same text belongs in the ledger row")
    parser.add_argument("--subject", default=None,
                        help="commit subject override (default: 'Publish <today>'; "
                             "a same-day republish keeps the original subject)")
    parser.add_argument("--note", default="",
                        help="extra commit-message body line recording what "
                             "this publish cycle changed")
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="push target as owner/name (default: the staging "
                             "mirror per the 2026-10-14 staging-first directive; "
                             "production requires the explicit --repo "
                             f"{PROD_REPO} and runs only after staging sign-off)")
    parser.add_argument("--domain", default=None,
                        help="custom hostname: staged as the tree's CNAME and set "
                             "as the target repo's Pages custom domain (default: "
                             "auto-keep — a target that already carries a custom "
                             "domain keeps it, one without keeps its github.io URL)")
    parser.add_argument("--allow-domain-drop", action="store_true",
                        help="explicit override that clears the target repo's "
                             "Pages custom domain: the staged CNAME-less tree "
                             "drops it on the next Pages build")
    wait = parser.add_mutually_exclusive_group()
    wait.add_argument("--wait-https", dest="wait_https",
                      action="store_true", default=None,
                      help="wait for the HTTPS certificate and set https_enforced "
                           "(default behavior for --domain publishes)")
    wait.add_argument("--no-wait-https", dest="wait_https",
                      action="store_false", default=None,
                      help="skip the HTTPS wait/enforcement step (leave it manual)")
    parser.add_argument("--mirror-dir", default=None,
                        help="target checkout (default: the clone of --repo; "
                             "any other path = local verification only)")
    return parser


def main():
    args = build_parser().parse_args()
    # Row 79: one publish clock for the whole leg — the stamp, the print line
    # and the commit message all name the same instant.
    publish_clock = datetime.datetime.now(datetime.timezone.utc)
    # Rung 2b runs before any real work, so a silent skip cannot get as far as
    # a build or a push.
    changelog_line = resolve_changelog_handoff(
        args.changelog_handoff, args.changelog_waiver)
    mirror_dir = args.mirror_dir or default_mirror_dir(args.repo)
    is_remote_target = os.path.abspath(
        mirror_dir) == os.path.abspath(default_mirror_dir(args.repo))
    pages_base = repo_pages_base(args.repo)
    # Row 42: the gate rides the leg that targets the staging mirror — the
    # prod leg (explicit --repo) never carries it. The passphrase reads
    # FIRST so a missing value fails loud before any real work happens.
    # Row 79's stamp rides the same leg.
    staging_gate_on = staging_leg_gated(args.repo)
    gate_passphrase = staging_passphrase() if staging_gate_on else None

    require_clean_worktree()
    domain = args.domain
    if is_remote_target:
        # Before anything is pushed or built: resolve the custom domain —
        # explicit --domain, or auto-keep of what the target already
        # carries — so a publish can never silently clear it.
        domain = check_domain_stickiness(
            args.repo, args.domain, args.allow_domain_drop)
    assert_flag_agreement(domain, args.wait_https)
    # Build BEFORE validating the gate report: the hashes cover the built
    # pages, and the build is reproducible, so a stale report is refused by
    # name instead of publishing content nobody reviewed.
    build_site()
    review_model, review_class, per_page = load_gate_report(args.gate_report)

    staging = tempfile.mkdtemp(prefix="psp-publish-")
    gated = 0
    stamped = 0
    try:
        file_count = stage_publish_tree(staging, cname=domain)
        ensure_git_repo(mirror_dir, is_remote_target, args.repo)
        removed = sync_tree(staging, mirror_dir)
        psp_public.assert_clean(
            psp_public.scan_tree(mirror_dir), "mirror worktree")
        if staging_gate_on:
            # Row 42: gate AFTER the mirror scan — the intentional gate must
            # never trip the scanner that ships it (the marker stays a
            # forbidden private-surface string for every OTHER leg).
            # Row 79's stamp goes after the gate, at the same boundary: it is
            # staging chrome too, and its marker is in the same forbidden set.
            gated = apply_staging_gate(mirror_dir, gate_passphrase)
            stamped = apply_staging_update_stamp(mirror_dir, publish_clock)
            print(f"staging gate (row 42): {gated} pages + robots.txt — "
                  "deterrence-grade; prod legs never carry the marker")
            print(f"staging stamp (row 79): {stamped} pages — "
                  f"{stamp_label(publish_clock)}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    today = datetime.date.today().isoformat()
    site_sha, map_sha = source_provenance()
    snapshot = f"site {site_sha}" + (f", tank-farms map {map_sha}" if map_sha else "")
    subject = args.subject or f"Publish {today}"
    message = (
        f"{subject}\n\n"
        f"Release gate (AGENTS.md): all pages passed the humanizer + style "
        f"review on model {review_model} (reviewer class {review_class}, "
        f"content-addressed). Rounds to pass: {per_page}.\n"
        f"Snapshot: {snapshot}."
        + (f"\nStaging gate (row 42): {gated} pages gated; staging preview "
           f"stamp (row 79): {stamp_label(publish_clock)}." if staging_gate_on else "")
        + f"\n{changelog_line}"
        + (f"\n{args.note}" if args.note else ""))

    if is_remote_target:
        sha = single_commit(mirror_dir, message)
        run(["git", "push", "--force", "origin", "main"], cwd=mirror_dir)
        ensure_pages_enabled(args.repo, cname=domain)
        if domain:
            cert_note = verify_custom_domain(
                domain, os.path.join(ROOT, "docs", "index.html"))
            wait_https = args.wait_https if args.wait_https is not None else True
            if wait_https:
                final_state = enforce_https(args.repo)
            print(f"published commit {sha} ({file_count} files) to {args.repo}")
            print(f"site: https://{domain}/")
            print(f"map: https://{domain}/map/map.html")
            print(f"tls: {cert_note}")
            print("index: the served index matches the built index once "
                  "the publish-time injections are stripped")
            if wait_https:
                print("https: enforced — polled the Pages API for the "
                      "certificate, then set https_enforced=true")
        else:
            wait_for_pages([pages_base + "/",
                            pages_base + "/map/embed.html",
                            pages_base + "/map/map.html"])
            print(f"published commit {sha} ({file_count} files) to {args.repo}")
            print(f"site: {pages_base}/")
            print(f"map: {pages_base}/map/map.html")
        state = pages_api(args.repo) or {}
        print(f"pages: status {state.get('status')}, "
              f"cname {state.get('cname')!r}, "
              f"cert {cert_state(state)!r}, "
              f"protected {state.get('protected_domain_state')!r}, "
              f"https_enforced {state.get('https_enforced')}")
        if domain and args.wait_https is False:
            print("HTTPS enforcement left off (--no-wait-https): manual "
                  "step — repo Pages settings → Enforce HTTPS once the "
                  "certificate shows available")
    else:
        sha = single_commit(mirror_dir, message)
        print(f"LOCAL verification only — nothing pushed ({file_count} files, "
              f"removed stale: {sorted(removed) or 'none'})")
        print(f"commit {sha} in {mirror_dir}")
        print(f"gate: {review_model} ({review_class}), pages: {per_page}")
        print(f"snapshot: {snapshot}")


if __name__ == "__main__":
    main()