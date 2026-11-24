#!/usr/bin/env python3
"""Per-page visual snapshots for a Protect South Portland UAT cycle (row 43).

Captures every real page from the UAT suite's start_pages at the five
standing evidence widths (412/768/1024/1100/1440 — the visual_check set),
full-page, into tests/evidence/uat-snapshots/<date>/<page>-<width>.png plus
a manifest the content judge reads. The browser is bb browser-automation
headless Chrome — the same mechanism tools/visual_check.sh uses ("playwright"
in the commission maps to this engine; the binding requirements are headless
render + viewport sizes + cookie injection, all covered).

Staging (the default target) sits behind the row-42 cookie gate: the tool
injects the psp_staging cookie like a human visitor would carry it,
computing the value from publish.staging_passphrase() — the SHARED
credential source (row-42 r2 precedent; no duplicated credential logic) —
and re-verifies the gate opened on EVERY snapshot (probe: no
.staging-gate-overlay in the live DOM + the page's main content present). A
page captured behind the overlay aborts the run loud.

Non-staging targets run cookieless. Fail loud everywhere: dead base
preflight, session failure, missing screenshot bytes, gate not opened,
blank capture. Redirect stubs (oil-tank-emissions.html, vocs.html) and
robots.txt are excluded from capture and recorded in the manifest: stubs
navigate away on load (their capture would be a duplicate of their target).

Before any capture the ladder runs the payload-fidelity rule
(tools/uat_payload.py, ledger row 97): where a page displays sendable copy
beside an action that transmits it, the payload MUST match the copy. It
fetches every page by URL through the same base, so it works identically
against a live host and a local build; a finding is printed with the page,
the control's label and what diverged, and the ladder stops before it files
snapshots. `--payload-check-only` runs just that rule.

Usage:
  python3 tools/uat_snapshots.py                                  # staging
  python3 tools/uat_snapshots.py --target local --date 2026-10-15 # local docs
  python3 tools/uat_snapshots.py --url <base>                     # override
  python3 tools/uat_snapshots.py --target local --payload-check-only
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish
import uat_payload
from staging_audit import AuditInfraError

SITE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SUITE = os.path.join(
    os.path.dirname(SITE_ROOT), ".bb", "skills", "uat", "suites", "uat-suite.json")
DEFAULT_TARGETS = {  # mirrors the UAT suite's own target registry
    "mirror": "https://cristoslc.github.io/protect-south-portland-published/",
    "staging": "https://staging.protectsouthportland.org/",
    "apex": "https://protectsouthportland.org/",
    "local": "file:" + os.path.join(SITE_ROOT, "docs", "index.html"),
}

WIDTHS = (412, 768, 1024, 1100, 1440)
EXCLUDED_START_PAGES = ("robots.txt", "oil-tank-emissions.html", "vocs.html")
HOST_STAGING = "staging.protectsouthportland.org"

# runtime probe: the gate overlay must be ABSENT (the cookie took) and the
# page's main content present (a real render, not a broken document). The
# map pages (#map) have no <main> shell: the marker accepts either.
GATE_EVAL_JS = """await p.evaluate(() => ({
  overlay: !!document.querySelector('.staging-gate-overlay'),
  main: !!((document.querySelector('main#content') &&
            document.querySelector('main#content').children.length) ||
           (document.querySelector('#map') &&
            document.querySelector('#map').children.length)),
}))"""


def snapshot_pages(suite_text):
    """The capture plan: the suite's start_pages minus the redirect stubs and
    robots.txt, in suite order; the manifest records what was excluded."""
    plan = [page for page in json.loads(suite_text)["start_pages"]
            if page not in EXCLUDED_START_PAGES]
    return plan


def snapshot_relpath(page, width):
    return page.removesuffix(".html").replace("/", "-") + f"-{width}.png"


def gate_cookies(host):
    """The row-42 gate cookie list for the browser session — staging host
    only, computed from the shared passphrase source; nothing for any other
    host, loud refusal when the staging target's passphrase is missing."""
    if host != HOST_STAGING:
        return []
    try:
        value = publish.staging_passphrase()
    except SystemExit as exc:
        raise AuditInfraError(str(exc)) from exc
    return [{
        "name": publish.GATE_COOKIE,
        "value": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "domain": HOST_STAGING,
        "path": "/",
        "secure": True,
        "sameSite": "Lax",
    }]


def gate_result_ok(probe):
    """True only when the gate overlay is gone AND the page carries real
    content (a snapshot behind the overlay is never a valid capture)."""
    return bool(probe) and not probe.get("overlay") and bool(probe.get("main"))


def write_manifest(outdir, data):
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2) + "\n")


def bb_open(host_id="host_yat733yf8z"):
    proc = subprocess.run(
        ["bb", "browser-automation", "open", "--backend", "local", "--headless",
         "--machine", host_id, "--json"],
        capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)["id"]
    except (ValueError, KeyError) as exc:
        raise AuditInfraError(f"browser session open failed: {proc.stdout[:200]} {proc.stderr[:200]}") from exc


def bb_close(session):
    subprocess.run(["bb", "browser-automation", "close", session, "--json"],
                   capture_output=True, text=True)


def run_script(session, script, timeout_ms=60000):
    """One trusted dev-browser script; returns the parsed run output."""
    proc = subprocess.run(
        ["bb", "browser-automation", "run", session, "--script", script,
         f"--timeout-ms={timeout_ms}", "--json"],
        capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except ValueError as exc:
        raise AuditInfraError(f"browser run unreadable: {proc.stdout[:200]} {proc.stderr[:200]}") from exc
    if data.get("ok") is False or data.get("exitCode") != 0:
        raise AuditInfraError(
            f"browser run failed: {str(data.get('text') or data.get('error', {}).get('message', ''))[:300]}")
    return data


def set_gate_cookie(session, base, cookie):
    """Land on the origin first, then set the cookie the way the gate would
    read it (document.cookie carries the same name/value/attrs)."""
    script = (
        "const p = await browser.getPage('main');\n"
        f"await p.goto('{base}', {{waitUntil: 'load'}});\n"
        f"await p.evaluate(() => {{ document.cookie = '{cookie['name']}={cookie['value']}; "
        "Path=/; Secure; SameSite=Lax; Max-Age=2592000'; });\n"
        "return await p.evaluate(() => document.cookie.indexOf('psp_staging=') !== -1);\n"
    )
    return run_script(session, script)


def capture(session, base, page, width, path, settle_ms=700):
    """One full-page screenshot + the gate probe; returns (probe, path)."""
    script = f"""const p = await browser.getPage('main');
await p.setViewport({{width: {width}, height: 900}});
await p.goto('{base}{page}?vc=' + Date.now(), {{waitUntil: 'load'}});
if (typeof p.waitForNetworkIdle === 'function') {{
  await Promise.race([
    p.waitForNetworkIdle({{idleTime: 500, timeout: 8000}}).catch(() => {{}}),
    new Promise(r => setTimeout(r, 8000))
  ]);
}}
await new Promise(r => setTimeout(r, {settle_ms}));
const probe = {GATE_EVAL_JS};
await p.screenshot({{path: '{path}', fullPage: true}});
return probe;"""
    data = run_script(session, script, timeout_ms=90000)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise AuditInfraError(f"no screenshot bytes for {page} at {width}")
    try:
        probe = json.loads(data.get("text") or "{}")
    except ValueError as exc:
        raise AuditInfraError(f"gate probe unreadable for {page} at {width}: {exc}") from exc
    return probe


def resolve_outdir(args, today=None):
    """tests/evidence/uat-snapshots/<date>/ under the site repo."""
    date = args.date if args.date != "today" else (today or dt.date.today().isoformat())
    outdir = os.path.join(
        SITE_ROOT, "tests", "evidence", "uat-snapshots", date)
    return outdir, date


def build_parser():
    parser = argparse.ArgumentParser(
        description="Visual snapshot sweep for a UAT cycle (row 43).")
    parser.add_argument("--suite", default=DEFAULT_SUITE,
                        help="the uat-suite.json with start_pages")
    parser.add_argument("--target", choices=list(DEFAULT_TARGETS), default="staging")
    parser.add_argument("--url", help="explicit base URL override")
    parser.add_argument("--date", default="today",
                        help="manifest/capture date label (default: today)")
    parser.add_argument("--out", dest="outdir", default=None,
                        help="explicit output directory override")
    parser.add_argument("--skip-payload-check", action="store_true",
                        help="capture only; leave the sendable-copy payload "
                             "rule (ledger row 97) out of this run")
    parser.add_argument("--payload-check-only", action="store_true",
                        help="run the payload rule alone, no browser, no "
                             "snapshots")
    return parser


def run_payload_sweep(base, pages):
    """The ladder's payload-fidelity rung (ledger row 97), against `base`.

    Fetches each page by URL — http(s) or file: — so a live host and a local
    build run through the identical rule. A fetch fault is an environment
    failure and raises; a mismatch is returned as a finding, and the caller
    stops the ladder before filing snapshots.
    """
    try:
        findings, reports = uat_payload.sweep(base, pages)
    except uat_payload.PayloadFetchError as exc:
        raise AuditInfraError(str(exc)) from exc
    for report in reports.values():
        for note in report["notes"]:
            print(f"note: {note}")
    for finding in findings:
        print(f"FAIL: {finding}")
    pairs = sum(len(report["pairs"]) for report in reports.values())
    print(f"payload sweep: {len(reports)} pages, {pairs} copy/payload pairs "
          f"compared, {len(findings)} findings")
    return findings


def main(argv=None):
    args = build_parser().parse_args(argv)
    suite_text = open(args.suite, encoding="utf-8").read() if os.path.exists(
        args.suite or "") else None
    if suite_text is None:
        raise AuditInfraError(f"uat suite {args.suite!r} not readable")
    pages = snapshot_pages(suite_text)
    base = args.url or DEFAULT_TARGETS[args.target]
    if not base.endswith("/") and not base.startswith("file:"):
        base = base + "/"

    host = urlparse(base).hostname or "file"
    cookies = gate_cookies(host)
    http_base = base if not base.startswith("file:") else None
    if args.target != "local" or args.url:
        preflight = [base] if base.startswith("file:") else [base, f"{base}{pages[0]}"]
        for url in preflight:
            if url.startswith("file:"):
                continue
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as resp:
                    if resp.status != 200:
                        raise AuditInfraError(f"preflight: {url} returned {resp.status}")
            except urllib.error.HTTPError as exc:
                raise AuditInfraError(f"preflight: {url} returned {exc.code}") from exc
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                raise AuditInfraError(f"preflight: cannot reach {url}: {exc}") from exc

    if args.skip_payload_check and args.payload_check_only:
        raise AuditInfraError(
            "--skip-payload-check and --payload-check-only contradict each other")
    if not args.skip_payload_check:
        findings = run_payload_sweep(base, pages)
        if findings:
            print("payload sweep stopped the ladder: a page displays sendable "
                  "copy that its action does not send (ledger row 97)",
                  file=sys.stderr)
            return 1
        if args.payload_check_only:
            return 0

    outdir, date = (args.outdir, args.date) if args.outdir else resolve_outdir(args)
    os.makedirs(outdir, exist_ok=True)

    session = bb_open()
    samples = []
    try:
        if cookies:
            set_gate_cookie(session, base, cookies[0])
        excluded = [{"page": "vocs.html", "reason": "redirect stub"},
                    {"page": "oil-tank-emissions.html", "reason": "redirect stub"},
                    {"page": "robots.txt", "reason": "not a page"}]
        for page in pages:
            for width in WIDTHS:
                path = os.path.join(outdir, snapshot_relpath(page, width))
                probe = capture(session, http_base or base, page, width, path)
                if not gate_result_ok(probe):
                    raise AuditInfraError(
                        f"{page} at {width}: gate overlay did not clear or no "
                        "content marker — the psp_staging cookie did not take; "
                        "refusing to file a capture behind the gate")
                samples.append({"page": page, "width": width,
                                "path": os.path.relpath(path, outdir),
                                "bytes": os.path.getsize(path),
                                "gate_open": True})
    finally:
        bb_close(session)

    manifest = {
        "date": date,
        "target": args.target,
        "base": base,
        "gated": bool(cookies),
        "widths": list(WIDTHS),
        "pages": pages,
        "excluded": excluded,
        "samples": samples,
    }
    write_manifest(outdir, manifest)
    print(f"snapshots: {len(samples)} captures ({len(pages)} pages x "
          f"{len(WIDTHS)} widths) in {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())