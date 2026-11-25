"""Tests for tools/payload_sweep.py — the scheduled payload-fidelity sweep.

Row 111 (2026-11-24): the operator ruled to "schedule the payload sweep" —
the row-97 rule (tools/uat_payload.py), which until now ran only inside the
UAT ladder, runs on a weekday-morning GitHub Actions schedule against the
staging host by URL and files one digest issue per run the way the staging
audit files its digest. Tests pin the pure logic with zero network calls:
the page plan (built pages, redirect stubs excluded by build.REDIRECTS),
the fail-loud shape check (a 200 with the wrong document is an environment
failure, never a clean bill), the stable finding ids the delta mechanism
diffs against, the digest body's round-tripping machine block, and the
non-blocking exit contract (findings exit 0; a broken environment is the
only non-zero exit).
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import uat_payload
import payload_sweep as ps
from staging_audit import AuditInfraError, extract_previous_findings

# A page the rule reads: cue heading, blockquote letter, paired mailto whose
# payload differs — one divergence, the shape a finding is made of.
MISMATCH_PAGE = """
<html><head><title>Act now</title></head><body>
<main id="content">
<h2>Example message</h2>
<blockquote>Dear Councilor, please require better technology at the tank
farm. Sincerely, A Neighbor</blockquote>
<a class="btn" href="mailto:council@example.org?body=Different%20words">Email
the Council</a>
</main>
</body></html>
"""


# ---------- page plan ----------

def test_sweep_pages_excludes_every_redirect_stub():
    pages = ps.sweep_pages()
    for stub in __import__("build").REDIRECTS:
        assert stub not in pages, f"redirect stub {stub} must not be swept"


def test_sweep_pages_covers_the_real_built_pages():
    # Pinned by name so adding or removing a page is a deliberate test edit,
    # never a silent change to what the schedule reads (row 111's rule).
    assert ps.sweep_pages() == [
        "404.html", "about.html", "act-now.html", "clear-skies.html",
        "coastal-flooding.html", "contact.html", "donate.html",
        "fertilizer-ban.html", "index.html", "map/embed.html", "map/map.html",
        "newsletter.html", "our-campaigns.html", "past-work.html",
        "pesticides.html", "report-an-odor.html", "share-your-story.html",
        "tank-farms.html", "toolkit.html", "yard-south-proposal.html",
    ]


def test_sweep_pages_reads_a_given_docs_root(tmp_path):
    (tmp_path / "map").mkdir()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "map" / "map.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "vocs.html").write_text("<html></html>", encoding="utf-8")
    assert ps.sweep_pages(str(tmp_path)) == ["index.html", "map/map.html"]


# ---------- fail-loud shape check ----------

def test_shape_accepts_the_built_shell():
    assert ps.shape_fault("index.html", MISMATCH_PAGE) is None


def test_shape_accepts_the_map_pages():
    map_page = "<html><body><div id=\"map\"></div></body></html>"
    assert ps.shape_fault("map/map.html", map_page) is None


def test_shape_refuses_a_non_html_document():
    fault = ps.shape_fault("index.html", '{"error": "not found"}')
    assert fault and "unrecognised page shape" in fault and "index.html" in fault


def test_shape_refuses_html_without_the_built_shell():
    # An interstitial, an error page or the wrong site can come back as a
    # 200 HTML document that parses clean and would file a clean bill; the
    # missing shell marker makes it loud instead.
    fault = ps.shape_fault("index.html",
                           "<html><body><h1>Maintenance</h1></body></html>")
    assert fault and "no built-shell" in fault


def test_checked_fetch_raises_loud_on_a_wrong_document(monkeypatch):
    monkeypatch.setattr(uat_payload, "fetch_html",
                        lambda url, extra_headers=None: "<html><body>wrong site</body></html>")
    with pytest.raises(AuditInfraError, match="index.html"):
        ps.checked_fetch("index.html", "https://staging.example.org/")


# ---------- findings and their stable ids ----------

def test_finding_row_id_is_stable_and_names_kind_and_page():
    text = ("sendable-payload:payload-mismatch act-now.html: control "
            "'Email the Council' beside displayed copy 'Example message' — "
            "first difference at character 1")
    first, second = ps.finding_row(text), ps.finding_row(text)
    assert first.id == second.id
    assert first.id.startswith("payload:payload-mismatch:act-now.html:")
    assert first.title == text


def test_finding_row_distinguishes_divergences():
    base = ("sendable-payload:missing-payload act-now.html: control {label!r} "
            "beside displayed copy 'Example message' — the mailto sends an "
            "empty payload")
    assert ps.finding_row(base.format(label="A")).id != \
        ps.finding_row(base.format(label="B")).id


def test_finding_row_survives_an_unparseable_finding_shape():
    row = ps.finding_row("something unexpected")
    assert row.id.startswith("payload:unknown:unknown:") and row.title


def test_run_sweep_returns_findings_over_a_mismatched_payload():
    reports = {}

    def fetcher(page):
        reports[page] = MISMATCH_PAGE
        return MISMATCH_PAGE

    findings, reports = ps.run_sweep("https://staging.example.org/",
                                     ["act-now.html"], fetcher)
    assert len(findings) == 1
    assert "payload-mismatch" in findings[0].id
    assert "Email" in findings[0].title and "divergence" not in findings[0].id
    assert reports["act-now.html"]["pairs"]


def test_run_sweep_propagates_a_fetch_fault():
    def fetcher(page):
        raise uat_payload.PayloadFetchError(f"cannot fetch {page}: status 503")

    with pytest.raises(uat_payload.PayloadFetchError):
        ps.run_sweep("https://staging.example.org/", ["index.html"], fetcher)


# ---------- digest body ----------

def test_digest_body_ends_in_a_round_tripping_machine_block():
    findings, reports = ps.run_sweep("https://staging.example.org/",
                                     ["act-now.html"],
                                     lambda page: MISMATCH_PAGE)
    body = ps.build_digest_body("2026-11-24 09:45 UTC",
                                "https://staging.example.org/",
                                reports, findings, None)
    block = body.rstrip().split("```json\n", 1)[1].removesuffix("```")
    data = json.loads(block)
    assert data["base_url"] == "https://staging.example.org/"
    previous_map, readable = extract_previous_findings(body)
    assert readable
    assert set(previous_map) == {found.id for found in findings}


def test_digest_body_renders_verdict_table_and_delta():
    findings, reports = ps.run_sweep("https://staging.example.org/",
                                     ["act-now.html"],
                                     lambda page: MISMATCH_PAGE)
    body = ps.build_digest_body("stamp", "https://staging.example.org/",
                                reports, findings,
                                {"added": [findings[0].id],
                                 "resolved": [], "persisting": []})
    assert "**Verdict: 1 finding(s)**" in body
    assert "| act-now.html |" in body
    assert findings[0].title in body
    assert "- Added: `%s`" % findings[0].id in body
    clean = ps.build_digest_body("stamp", "https://staging.example.org/",
                                 reports, [], None)
    assert "**Verdict: clean run — no findings.**" in clean
    assert "First run — no previous digest to compare against." in clean


# ---------- exit contract (non-blocking) ----------

def test_findings_exit_zero_and_file_a_report(monkeypatch):
    findings, _ = ps.run_sweep("https://staging.example.org/",
                               ["act-now.html"], lambda page, extra_headers=None: MISMATCH_PAGE)
    monkeypatch.setattr(ps, "run_sweep",
                        lambda base, pages, fetcher=None, extra_headers=None: (findings, {}))
    monkeypatch.setattr(ps, "sweep_pages", lambda: ["act-now.html"])
    assert ps.main(["--skip-issue", "--url", "https://staging.example.org/"]) == 0


def test_infra_failure_is_the_only_nonzero_exit(monkeypatch):
    for fault in (uat_payload.PayloadFetchError("cannot fetch index.html: "
                                                "status 503"),
                  AuditInfraError("unrecognised page shape for index.html")):
        def broken(base, pages, fault=fault, extra_headers=None):
            raise fault

        monkeypatch.setattr(ps, "run_sweep", broken)
        monkeypatch.setattr(ps, "sweep_pages", lambda: ["index.html"])
        assert ps.main(["--skip-issue"]) == 1


# ---------- the schedule itself ----------

def test_workflow_sweeps_on_a_weekday_morning_and_files_issues():
    text = open(os.path.join(ROOT, ".github", "workflows",
                             "payload-sweep.yml"), encoding="utf-8").read()
    assert "cron: \"45 13 * * 1-5\"" in text
    assert "issues: write" in text
    assert "workflow_dispatch:" in text
    assert "concurrency:" in text and "group: payload-sweep" in text
    assert "python3 tools/payload_sweep.py" in text
    # recorded correction (row 128): the sweep attaches the gate cookie, so
    # the workflow names the psp_staging passphrase secret (as the audit's
    # workflow has since row 46)
    assert "PSP_STAGING_PASSPHRASE: ${{ secrets.PSP_STAGING_PASSPHRASE }}" in text
