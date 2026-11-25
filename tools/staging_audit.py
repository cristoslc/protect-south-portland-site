#!/usr/bin/env python3
"""Staging accessibility audit — non-blocking by contract (findings exit 0).

Audits the staging mirror with zero extra dependencies (stdlib only;
Lighthouse arrives through npx, GitHub through the gh CLI):

1. HTTP 200 check for every public page.
2. Lighthouse accessibility (desktop preset) on every page plus a mobile
   pass on index.
3. The typography floor re-checked against the styles.css staging SERVES
   (root 112.5% + body 1rem — the contract tests/test_site.py pins on the
   source file).
4. A delta against the previous run's digest, read from the machine block
   inside the last GitHub issue labeled staging-audit.
5. One digest issue per run on the site repo, labeled staging-audit +
   accessibility.

Non-blocking contract: a site-shaped problem (404, Lighthouse findings, a
floor miss) records a FINDING and still exits 0 — the audit must never be
able to block a deploy pipeline through its own exit code. It exits
non-zero ONLY when the environment is broken (staging unreachable,
Lighthouse crash, gh failure): those fail loud.

Usage:
  python3 tools/staging_audit.py                       # audit staging, file the digest
  python3 tools/staging_audit.py --base-url http://127.0.0.1:8813 --skip-issue
                                                       # local ad-hoc pass
  python3 tools/staging_audit.py --repo <owner/name>   # digest to another repo
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import publish

SITE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BASE_URL = "https://staging.protectsouthportland.org"
DEFAULT_REPO = "cristoslc/protect-south-portland-site"

LABELS = (
    ("staging-audit", "1d76db", "Automated staging audit digest (one per run)"),
    ("accessibility", "d4c5f9", "Accessibility work and a11y findings"),
)

LIGHTHOUSE_PIN = "12"
MAP_EMBED = "map/embed.html"

# The typography floor contract. The source file is pinned by
# tests/test_site.py::test_typography_older_visitor_floor; here it is
# re-verified against what staging SERVES, so a deploy regression cannot
# quietly drop it.
FLOOR_ROOT = "font-size: 112.5%"
FLOOR_BODY = "font-size: 1rem;"
BANNED_BODY = re.compile(r"font-size:\s*17px")

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class AuditInfraError(Exception):
    """The environment is broken (network, Lighthouse, gh) — findings would
    be meaningless. Distinct from site-shaped problems, which are findings."""


class Finding:
    __slots__ = ("id", "title", "detail")

    def __init__(self, id, title, detail=""):
        self.id = id
        self.title = title
        self.detail = detail

    def as_machine(self):
        return {"id": self.id, "title": self.title, "detail": self.detail}

    def __repr__(self):
        return f"Finding({self.id!r})"


# ---------- pure logic (unit-tested; no network) ----------

def _rule_block(css, selector):
    """The top-level `{ selector { ... } }` block, or None."""
    match = re.search(rf"(?m)^{selector}\s*\{{[^}}]*\}}", css)
    return match.group(0) if match else None


def check_typography_floor(css):
    """Findings for the served stylesheet's typography floor, in id order."""
    findings = []
    root = _rule_block(css, "html")
    if not root or FLOOR_ROOT not in root:
        findings.append(Finding(
            "typography:root-scale",
            "html font-size 112.5% missing on the SERVED stylesheet",
            "The older-visitor root scale is a pinned contract; on the source "
            "file check test_typography_older_visitor_floor."))
    body = _rule_block(css, "body")
    if not body or FLOOR_BODY not in body:
        findings.append(Finding(
            "typography:body-floor",
            "body font-size 1rem missing on the SERVED stylesheet",
            "Reading copy must ride the root scale at exactly 1rem."))
    if BANNED_BODY.search(css):
        findings.append(Finding(
            "typography:fixed-px-body",
            "served body font-size uses a fixed px override (17px)",
            "A fixed-px body breaks the browser-settings scale contract; "
            "body must be 1rem against the 112.5% root."))
    return sorted(findings, key=lambda f: f.id)


def delta(previous, current):
    """Classify current Findings against a previous {id: title}; None when
    no previous digest exists."""
    if previous is None:
        return None
    current_ids = {f.id for f in current}
    return {
        "added": sorted(current_ids - set(previous)),
        "resolved": sorted(set(previous) - current_ids),
        "persisting": sorted(current_ids & set(previous)),
    }


def extract_previous_findings(body):
    """(map id->title, readable) from the LAST parseable ```json machine
    block in a previous digest body; ({}, False) when absent or garbled."""
    for block in re.findall(r"```json\n(.*?)```", body or "", re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data.get("findings"), list):
            return {f["id"]: f.get("title", "") for f in data["findings"]}, True
    return {}, False


def build_digest_body(stamp, base_url, page_results, findings, delta_info):
    """The digest markdown, ending with the machine block the next run
    reads its delta from."""
    lines = [f"# Staging audit — {stamp}", "", f"Base: {base_url}", ""]
    if findings:
        lines.append(f"**Verdict: {len(findings)} finding(s)** (non-blocking: "
                     "exit 0. The audit exits non-zero only on infrastructure errors.)")
    else:
        lines.append("**Verdict: clean run — no findings.**")
    lines += ["", "## Typography floor (served styles.css)"]
    floor = [f for f in findings if f.id.startswith("typography:")]
    if floor:
        lines.extend(f"- `{f.id}` {f.title}" for f in floor)
    else:
        lines.append("Passes: root `112.5%`, body `1rem` (18px at browser defaults).")
    lines += ["", "## Per-page results (Lighthouse accessibility)", "",
              "| Page | HTTP | Desktop score | Mobile score | Failed audits |",
              "|---|---|---|---|---|"]

    def fmt(entry, key):
        value = entry.get(key)
        return "—" if value is None else f"{value * 100:.0f}%"

    for page, entry in page_results.items():
        failed = entry.get("lighthouse") or entry.get("mobile_failed") or []
        lines.append(
            f"| {page} | {entry['status']} | {fmt(entry, 'lighthouse_score')} "
            f"| {fmt(entry, 'mobile_score')} | {', '.join(failed) if failed else '—'} |")
    lines.append("")
    if findings:
        lines += ["## Findings"]
        lines.extend(f"- `{f.id}` — {f.title}"
                     + (f" — {f.detail}" if f.detail else "") for f in findings)
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
        "page_results": {
            page: {key: value for key, value in entry.items() if value is not None}
            for page, entry in page_results.items()
        },
        "findings": [f.as_machine() for f in findings],
    }
    lines.append(json.dumps(machine, sort_keys=True))
    lines.append("```")
    return "\n".join(lines) + "\n"


def decide_exit(findings, infra):
    """Non-blocking contract: findings exit 0; an infrastructure failure is
    the only non-zero exit (and always is — loud)."""
    return 1 if infra else 0


# ---------- audit run over injected collaborators ----------

def public_pages():
    """Every public page URL path on the mirror: source pages sorted with
    index first, then the build.py redirect stubs, then the standalone map."""
    names = sorted(p for p in os.listdir(os.path.join(SITE_ROOT, "site", "pages"))
                   if p.endswith(".html"))
    names.remove("index.html")
    return ["index.html"] + names + sorted(build.REDIRECTS) + [MAP_EMBED]


def gate_expected(base_url):
    """True when the target is the gated staging host (row 128, 2026-11-25:
    the operator's reversal of the cutover ruling — the row-42 cookie gate
    is live on staging again). Compared on the host, not the byte-equal
    string: the payload sweep normalizes its base with a trailing slash, and
    that form is the same gated host, never an ungated override."""
    return base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")


def gate_extra_headers(base_url):
    """Row 42 r2: the psp_staging cookie as an extra-header, byte-compatible
    with what the gate sets, attached to BOTH the fetches (page HTTP-200 +
    the served-stylesheet floor check) and the Lighthouse runs so the audit
    measures the real pages instead of the gate overlay. The passphrase
    comes from publish's own loader (env / the same workspace .env) — there
    is no second copy of the credential logic. Missing value: loud
    (infrastructure error) when the target IS the gated staging host
    (gate_expected); no header when an overridden base names a non-gated
    target (e.g. a local serve)."""
    if not gate_expected(base_url):
        return None
    try:
        value = publish.staging_passphrase()
    except SystemExit as exc:
        raise AuditInfraError(str(exc)) from exc
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return {"Cookie": f"{publish.GATE_COOKIE}={digest}"}


def run_audit(base_url, pages=None, fetch=None, lh=None, extra_headers=None):
    """Audit {base}: per-page HTTP status, Lighthouse (desktop everywhere +
    mobile on index), and the typography floor of the SERVED stylesheet.

    A 404 is a finding and skips that page's Lighthouse run (auditing an
    error page is noise). Network/lighthouse failures raise AuditInfraError
    and are never swallowed into findings.
    """
    fetch = fetch or http_fetch
    lh = lh or lighthouse_run
    base = base_url.rstrip("/")
    findings = []
    page_results = {}

    try:
        css_status, css_text = fetch(f"{base}/styles.css", extra_headers=extra_headers)
    except AuditInfraError:
        raise
    css_fetched = css_status == 200
    if not css_fetched:
        findings.append(Finding("http:styles.css",
                                f"HTTP {css_status}",
                                f"{base}/styles.css — the audit runs the floor "
                                "check on the served stylesheet"))
    else:
        findings.extend(check_typography_floor(css_text))

    for page in (pages or public_pages()):
        url = f"{base}/{page}"
        entry = {"status": None, "lighthouse_score": None,
                 "lighthouse": None, "mobile_score": None, "mobile_failed": None}
        try:
            status, text = fetch(url, extra_headers=extra_headers)
        except AuditInfraError:
            raise
        entry["status"] = status
        if status != 200:
            findings.append(Finding(f"http:{page}", f"HTTP {status}",
                                    f"{url} answered {status}"))
            page_results[page] = entry
            continue
        if gate_expected(base_url) and publish.GATE_MARKER not in text:
            # Row 128: once the cookie gate is the served contract, a 200
            # page whose bytes carry no gate marker means the gate died or
            # the host is not staging. An environment fault, loud — the
            # audit must never file a clean bill over an unprotected host.
            raise AuditInfraError(
                f"{page}: the staging host answered 200 without the "
                f"{publish.GATE_MARKER!r} gate marker — the row-42 crawl "
                "gate is not live on the served tree, so this is not the "
                "staging the audit is contracted to measure")
        try:
            score, failed = lh(url, "desktop", extra_headers=extra_headers)
            entry["lighthouse_score"], entry["lighthouse"] = score, failed
            if score is not None and score < 1.0:
                findings.append(Finding(
                    f"lighthouse:{page}", f"Lighthouse accessibility {score * 100:.0f}%",
                    "failed audits: " + (", ".join(failed) or "none listed")))
            if page == "index.html":
                mobile_score, mobile_failed = lh(url, "mobile", extra_headers=extra_headers)
                entry["mobile_score"], entry["mobile_failed"] = mobile_score, mobile_failed
                if mobile_score is not None and mobile_score < 1.0:
                    findings.append(Finding(
                        "lighthouse:mobile:index.html",
                        f"Lighthouse mobile accessibility {mobile_score * 100:.0f}%",
                        "failed audits: " + (", ".join(mobile_failed) or "none listed")))
        except AuditInfraError:
            raise
        page_results[page] = entry

    return {"findings": findings, "page_results": page_results}


# ---------- real collaborators ----------

def http_fetch(url, extra_headers=None):
    """(status, text) for a URL; a non-2xx is a normal return, an
    unreachable host is infrastructure. extra_headers carries the row-42
    staging-gate cookie (byte-compatible with the gate's own Set-Cookie)."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "psp-staging-audit/1", **(extra_headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise AuditInfraError(f"cannot reach {url}: {exc}") from exc


def find_chrome():
    for candidate in (os.environ.get("CHROME_PATH"), shutil.which("google-chrome"),
                      shutil.which("chromium"), shutil.which("chromium-browser"),
                      MAC_CHROME if os.path.exists(MAC_CHROME) else None):
        if candidate and os.path.exists(candidate) or candidate and shutil.which(candidate):
            return candidate
    return None


def parse_lighthouse(data):
    """(score, failed-audit ids) from a Lighthouse JSON report. Only audits
    that carry scoring weight count; scoreless (informative/manual) audits
    are treated as passing so the digest records reportable failures only."""
    try:
        category = data["categories"]["accessibility"]
        audits = data["audits"]
        score = category["score"]
        failed = sorted(
            audit_ref["id"] for audit_ref in category["auditRefs"]
            if audit_ref.get("weight", 0) > 0
            and (audits.get(audit_ref["id"]) or {}).get("score") is not None
            and (audits.get(audit_ref["id"]) or {}).get("score") < 0.9)
        return score, failed
    except (KeyError, TypeError) as exc:
        raise AuditInfraError(f"unexpected Lighthouse JSON shape: {exc}") from exc


def lighthouse_run(url, form_factor, extra_headers=None):
    """(score, failed ids) for one Lighthouse run; a crash is infra.
    extra_headers carries the row-42 staging-gate cookie so the measured
    page is the real one, not the gate overlay."""
    chrome = find_chrome()
    if not chrome:
        raise AuditInfraError("no Chrome for Lighthouse — set CHROME_PATH")
    npx = shutil.which("npx")
    if not npx:
        raise AuditInfraError("npx not found — node is required for the audit")
    with tempfile.TemporaryDirectory(prefix="psp-lh-") as tmp:
        out = os.path.join(tmp, "lh.json")
        cmd = [npx, "--yes", f"lighthouse@{LIGHTHOUSE_PIN}", url, "--quiet",
               "--only-categories=accessibility", "--output=json",
               f"--output-path={out}",
               "--chrome-flags=--headless=new --no-sandbox --disable-gpu"]
        if form_factor == "desktop":
            cmd.append("--preset=desktop")
        if extra_headers:
            cmd.append("--extra-headers=" + json.dumps(extra_headers))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired as exc:
            raise AuditInfraError(f"lighthouse timed out on {url}") from exc
        if proc.returncode != 0 or not os.path.exists(out):
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            raise AuditInfraError(
                f"lighthouse failed (rc {proc.returncode}) on {url}: {' | '.join(tail)}")
        try:
            with open(out, encoding="utf-8") as handle:
                return parse_lighthouse(json.load(handle))
        except ValueError as exc:
            raise AuditInfraError(f"lighthouse wrote unparseable JSON: {exc}") from exc


# ---------- GitHub digest helpers (gh CLI) ----------

def _gh(args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def ensure_labels(repo, labels=LABELS):
    """Create any missing label. `labels` is a (name, color, blurb) tuple
    sequence, LABELS by default; the payload sweep passes its own (the digest
    issue surface is shared, the label streams are not)."""
    for name, color, description in labels:
        probe = _gh(["api", f"repos/{repo}/labels/{name}"])
        if probe.returncode == 0:
            continue
        if "404" not in probe.stderr:
            raise AuditInfraError(f"gh label check failed for {name}:\n{probe.stderr}")
        created = _gh(["api", "-X", "POST", f"repos/{repo}/labels",
                       "-f", f"name={name}", "-f", f"color={color}",
                       "-f", f"description={description}"])
        if created.returncode != 0 and "422" not in created.stderr:
            raise AuditInfraError(f"gh label create failed for {name}:\n{created.stderr}")


def last_digest_issue(repo, label="staging-audit"):
    """The most recent digest issue carrying `label`, or None."""
    proc = _gh(["issue", "list", "-R", repo, "--label", label,
                "--state", "all", "--limit", "1", "--json", "number,title,body"])
    if proc.returncode != 0:
        raise AuditInfraError(f"gh issue list failed:\n{proc.stderr}")
    items = json.loads(proc.stdout or "[]")
    return items[0] if items else None


def create_issue(repo, title, body, labels=("staging-audit", "accessibility")):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
        handle.write(body)
        path = handle.name
    try:
        proc = _gh(["issue", "create", "-R", repo, "--title", title,
                    "--body-file", path] +
                   [flag for label in labels for flag in ("--label", label)])
    finally:
        os.unlink(path)
    if proc.returncode != 0:
        raise AuditInfraError(f"gh issue create failed:\n{proc.stderr}")
    return proc.stdout.strip().splitlines()[-1]


# ---------- entry point ----------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Non-blocking staging accessibility audit (findings exit 0).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="mirror root to audit (default: the staging URL)")
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="owner/name of the repo that receives the digest issue")
    parser.add_argument("--skip-issue", action="store_true",
                        help="audit and print, but do not file the digest issue")
    args = parser.parse_args(argv)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        result = run_audit(args.base_url,
                           extra_headers=gate_extra_headers(args.base_url))
    except AuditInfraError as exc:
        print(f"INFRASTRUCTURE FAILURE — {exc}", file=sys.stderr)
        print("Findings are non-blocking by contract; a broken environment is not a "
              "finding. Exiting 1 so the failure is loud.", file=sys.stderr)
        return 1

    findings = result["findings"]
    previous_body = None
    if not args.skip_issue:
        previous = last_digest_issue(args.repo)
        previous_body = (previous or {}).get("body")
    previous_map = None
    if previous_body:
        previous_map, _ = extract_previous_findings(previous_body)
        if previous_map:
            previous_map = {fid: title for fid, title in previous_map.items()}
        else:
            previous_map = None
    delta_info = delta(previous_map, findings)
    body = build_digest_body(stamp, args.base_url, result["page_results"],
                             findings, delta_info)

    if not args.skip_issue:
        ensure_labels(args.repo)
        issue_url = create_issue(args.repo, f"Staging audit {stamp}", body)
        print(f"digest issue: {issue_url}")
    verdict = "CLEAN" if not findings else f"{len(findings)} FINDING(S) (non-blocking)"
    print(f"staging audit {stamp}: {verdict}")
    for found in findings:
        print(f"  - {found.id}: {found.title}")
    return decide_exit(findings, infra=False)


if __name__ == "__main__":
    sys.exit(main())