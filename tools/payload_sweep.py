#!/usr/bin/env python3
"""Scheduled sendable-copy payload sweep — the row-97 rule on a clock.

Runs the UAT ladder's payload-fidelity rung (tools/uat_payload.py, ledger
row 97) against the staging host by URL — exactly the fetch-by-URL shape
tools/uat_snapshots.py's run_payload_sweep runs before any capture — on the
weekday-morning schedule beside the staging audit
(.github/workflows/payload-sweep.yml), and files one digest issue per run
the way tools/staging_audit.py files its digest: an issue whose body ends in
a ```json machine block the next run diffs against (delta: added, resolved,
persisting).

PAGES: every .html in the committed docs/ build except build.REDIRECTS'
stubs. The ladder reads its page plan from the workspace uat-suite.json,
which does not exist in CI; the committed build output is the repo's own
page set of record and a superset of the ladder's list (the suite predates
report-an-odor, share-your-story and toolkit). Redirect stubs are excluded
by build.REDIRECTS itself — never a hardcoded page list — so a future stub
is excluded here by the same line that makes it a stub.

NON-BLOCKING CONTRACT (the audit's, unchanged): a site-shaped problem — a
payload mismatch, a blank payload under displayed copy — is a FINDING,
filed as the digest report naming the page, the control and what diverged,
and still exits 0. It exits non-zero ONLY when the environment is broken:
host unreachable, non-200, or a tool crash. Those fail loud.

FAIL LOUD ON SHAPE (ledger row 111): the sweep reads fetched HTML blind, so
a staging fault that returns a 200 with the WRONG document — an error page,
an interstitial, the wrong site after a DNS/cutover mistake — would parse
clean and file a clean bill. Every fetched page must therefore carry the
shape its committed build has: a real HTML document containing the built
shell's `<main id="content">` or the map pages' `id="map"`. Anything else
is an infrastructure failure, not a pass.

Cookie attached (row 128, 2026-11-25): the operator reversed the cutover
ruling dec_63blvjzqob1t (corpus dl-20261124T154549-c606) per corpus
dl-20261125T142900-d080, so the row-42 cookie gate is live on staging again
and the sweep attaches the psp_staging cookie from PSP_STAGING_PASSPHRASE
(env, then the workspace .env — the audit's loader, no second copy of the
credential logic). On the gated staging host a missing passphrase is an
environment fault: the run refuses loud rather than sweeping unprotected.
ON A 200-WITH-CURTAIN RESPONSE, stated explicitly: the curtain is
browser-side — GitHub Pages serves the full HTML regardless, so the raw
200 body still carries the complete built shell and the payload rule keeps
reading real copy. The tripwires are therefore: (1) the gate MARKER check —
a 200 page with the built shell but no `staging-gate` marker means the gate
died or the host is not staging, an infrastructure failure, loud; and (2)
the row-111 unrecognised-document rule, which fires only if the host ever
served a document that is not one of the site's built pages (a curtain-only
stub would lack the built shell and fail there).

Usage:
  python3 tools/payload_sweep.py                       # sweep staging, file the digest
  python3 tools/payload_sweep.py --skip-issue          # sweep and print only
  python3 tools/payload_sweep.py --url file:docs/index.html --skip-issue
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import publish
import uat_payload
from staging_audit import (AuditInfraError, Finding, create_issue,
                           decide_exit, delta, ensure_labels,
                           extract_previous_findings, gate_expected,
                           gate_extra_headers, last_digest_issue)

SITE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BASE_URL = "https://staging.protectsouthportland.org/"
DEFAULT_REPO = "cristoslc/protect-south-portland-site"

SWEEP_LABELS = (
    ("payload-sweep", "0e8a16",
     "Automated sendable-copy payload sweep digest (one per run)"),
)

# The shape markers a fetched page must carry to be recognised as the site's
# own document: the built shell (build.py wraps every page body in it) or the
# standalone map pages' root element.
SHELL_MARKER = '<main id="content">'
MAP_MARKER = 'id="map"'


def sweep_pages(docs_root=None):
    """Every built page to sweep, redirect stubs excluded by build.REDIRECTS."""
    root = docs_root or os.path.join(SITE_ROOT, "docs")
    return [page for page in uat_payload.discovered_pages(root)
            if page not in build.REDIRECTS]


def shape_fault(page, markup):
    """A reason string when the fetched document is not a recognised site
    page, or None. The reason is an infrastructure failure, never a finding:
    a clean rule result over the wrong document would be a clean bill the
    page never earned."""
    if "<html" not in markup:
        return (f"unrecognised page shape for {page}: no <html> document — "
                "the host served something that is not the site's page")
    if SHELL_MARKER not in markup and MAP_MARKER not in markup:
        return (f"unrecognised page shape for {page}: no built-shell "
                f"{SHELL_MARKER!r} (or map {MAP_MARKER!r}) marker — the host "
                "served a document that is not one of the site's built pages")
    return None


def checked_fetch(page, base):
    """Fetch one page by URL with the row-42 gate cookie attached when the
    target is the gated staging host (row 128), refusing a wrong-document
    200 and a 200 that carries no gate marker (both loud; see module
    docstring). Raises PayloadFetchError / AuditInfraError — both loud."""
    headers = gate_extra_headers(base)
    markup = uat_payload.fetch_html(uat_payload.page_url(base, page),
                                    headers=headers)
    fault = shape_fault(page, markup)
    if fault:
        raise AuditInfraError(fault)
    if gate_expected(base) and publish.GATE_MARKER not in markup:
        raise AuditInfraError(
            f"unrecognised staging shape for {page}: the 200 document "
            f"carries no {publish.GATE_MARKER!r} gate marker — the row-42 "
            "crawl gate is not live on the served tree (row 128), so this "
            "is not the staging the sweep is contracted to read; refusing "
            "loud")
    return markup


def finding_row(finding_text):
    """One finding string -> a digest Finding with a stable id.

    The finding strings carry the page, the control's label and what
    diverged; the id is derived from the rule's kind, the page, and a short
    hash of the full text, so an identical divergence keeps its id across
    runs (the delta's `persisting`) while any change of page, control or
    divergence makes a new one."""
    match = re.match(r"sendable-payload:(\S+) (\S+):", finding_text)
    kind, page = (match.group(1), match.group(2)) if match else ("unknown", "unknown")
    digest = hashlib.sha256(finding_text.encode("utf-8")).hexdigest()[:8]
    return Finding(id=f"payload:{kind}:{page}:{digest}", title=finding_text)


def run_sweep(base, pages, fetcher=None):
    """The rung against `base`, shape-checked. Returns digest Findings and
    the per-page reports; any fetch/shape fault raises (loud). `fetcher`
    defaults to the real checked fetch and is injectable for tests."""
    if fetcher is None:
        fetcher = lambda page: checked_fetch(page, base)  # noqa: E731
    findings, reports = [], {}
    for page in pages:
        report = uat_payload.inspect_page(fetcher(page), page)
        reports[page] = report
        findings.extend(report["findings"])
    return [finding_row(text) for text in findings], reports


def build_digest_body(stamp, base_url, reports, findings, delta_info):
    """The digest markdown, ending with the machine block the next run
    reads its delta from — the audit digest's contract, one rung wide."""
    pairs = sum(len(report["pairs"]) for report in reports.values())
    lines = [f"# Payload sweep — {stamp}", "",
             f"Base: {base_url}",
             f"Pages swept: {len(reports)}; copy/payload pairs compared: {pairs}", ""]
    if findings:
        lines.append(f"**Verdict: {len(findings)} finding(s)** (non-blocking: "
                     "exit 0. The sweep exits non-zero only on infrastructure "
                     "errors.)")
    else:
        lines.append("**Verdict: clean run — no findings.**")
    lines += ["", "## Per-page results", "",
              "| Page | Pairs compared | Notes |", "|---|---|---|"]
    for page, report in reports.items():
        lines.append(f"| {page} | {len(report['pairs'])} | "
                     f"{len(report['notes'])} |")
    lines.append("")
    if findings:
        lines += ["## Findings — displayed copy its action does not send "
                  "(ledger row 97)"]
        lines.extend(f"- `{found.id}` — {found.title}" for found in findings)
        lines.append("")
    lines.append("## Delta vs previous digest")
    if delta_info is None:
        lines.append("First run — no previous digest to compare against.")
    else:
        lines.append(f"- Added: {', '.join('`%s`' % i for i in delta_info['added']) or 'none'}")
        lines.append(f"- Resolved: {', '.join('`%s`' % i for i in delta_info['resolved']) or 'none'}")
        lines.append(f"- Persisting: {', '.join('`%s`' % i for i in delta_info['persisting']) or 'none'}")
    lines += ["", "<!-- machine block: the next run reads its delta from this -->",
              "```json"]
    machine = {
        "version": 1,
        "date": stamp,
        "base_url": base_url,
        "pages": {page: {"pairs": len(report["pairs"])}
                  for page, report in reports.items()},
        "findings": [found.as_machine() for found in findings],
    }
    lines.append(json.dumps(machine, sort_keys=True))
    lines.append("```")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scheduled sendable-copy payload sweep (findings exit 0; "
                    "ledger row 97 rule, row 111 schedule).")
    parser.add_argument("--url", default=DEFAULT_BASE_URL,
                        help="base URL of the host to sweep "
                             "(default: the staging URL)")
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="owner/name of the repo that receives the digest issue")
    parser.add_argument("--skip-issue", action="store_true",
                        help="sweep and print, but do not file the digest issue")
    args = parser.parse_args(argv)
    base = args.url if args.url.endswith("/") or args.url.startswith("file:") \
        else args.url + "/"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pages = sweep_pages()

    try:
        findings, reports = run_sweep(base, pages)
    except (uat_payload.PayloadFetchError, AuditInfraError) as exc:
        print(f"INFRASTRUCTURE FAILURE — {exc}", file=sys.stderr)
        print("Findings are non-blocking by contract; a broken environment is "
              "not a finding. Exiting 1 so the failure is loud — the sweep "
              "must never file a clean bill over a host it could not read.",
              file=sys.stderr)
        return 1

    previous_body = None
    if not args.skip_issue:
        previous = last_digest_issue(args.repo, label="payload-sweep")
        previous_body = (previous or {}).get("body")
    previous_map = None
    if previous_body:
        previous_map, _ = extract_previous_findings(previous_body)
    delta_info = delta(previous_map, findings)
    body = build_digest_body(stamp, base, reports, findings, delta_info)

    if not args.skip_issue:
        ensure_labels(args.repo, SWEEP_LABELS)
        issue_url = create_issue(args.repo, f"Payload sweep {stamp}", body,
                                 labels=("payload-sweep",))
        print(f"digest issue: {issue_url}")
    verdict = "CLEAN" if not findings else f"{len(findings)} FINDING(S) (non-blocking)"
    print(f"payload sweep {stamp} — {base}: {verdict}")
    print(f"payload sweep: {len(reports)} pages, "
          f"{sum(len(report['pairs']) for report in reports.values())} "
          f"copy/payload pairs compared, {len(findings)} findings")
    for found in findings:
        print(f"  - {found.title}")
    return decide_exit(findings, infra=False)


if __name__ == "__main__":
    sys.exit(main())
