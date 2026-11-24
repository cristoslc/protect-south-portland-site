"""Tests for tools/uat_snapshots.py — the visual-snapshot UAT capture tool.

Row 43 (2026-10-15): a UAT cycle captures every real page from the UAT
suite's start_pages at the five standing evidence widths into
tests/evidence/uat-snapshots/<date>/ plus a manifest for the judge. The
browser mechanism is bb browser-automation (the same headless Chrome
tools/visual_check.sh uses). Tests pin the pure logic with zero browser or
network calls: the page plan, the snapshot naming contract, the row-42 gate
cookie build over the shared credential source, the gate-opened runtime
check, the manifest contract, and the CLI defaults.
"""

import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import publish
import uat_snapshots as us

SUITE = json.dumps({"start_pages": [
    "index.html", "about.html", "act-now.html", "tank-farms.html",
    "our-campaigns.html", "past-work.html", "report-an-odor.html",
    "contact.html", "donate.html", "newsletter.html",
    "coastal-flooding.html", "clear-skies.html", "fertilizer-ban.html",
    "pesticides.html", "yard-south-proposal.html", "404.html",
    "oil-tank-emissions.html", "vocs.html",          # redirect stubs
    "map/map.html", "map/embed.html",                # standalone map pages
    "robots.txt",
]})


def test_snapshot_plan_covers_the_real_pages_only():
    plan = us.snapshot_pages(SUITE)
    assert "index.html" in plan and "tank-farms.html" in plan
    assert "map/map.html" in plan and "map/embed.html" in plan
    # redirect stubs navigate away on load (a capture would be a duplicate of
    # their target) and robots.txt is not a page: both stay out, recorded
    for excluded in ("oil-tank-emissions.html", "vocs.html", "robots.txt"):
        assert excluded not in plan
    assert len(plan) == 18


def test_snapshot_plan_keeps_suite_order():
    ordered = json.loads(SUITE)["start_pages"]
    expected = [p for p in ordered if p not in us.EXCLUDED_START_PAGES]
    assert us.snapshot_pages(SUITE) == expected


def test_widths_are_the_five_standing_evidence_widths():
    assert us.WIDTHS == (412, 768, 1024, 1100, 1440)


def test_snapshot_name_contract():
    assert us.snapshot_relpath("index.html", 412) == "index-412.png"
    assert us.snapshot_relpath("map/embed.html", 768) == "map-embed-768.png"


def test_gate_cookie_builds_from_the_shared_credential(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "STAGING_DOTENV", os.path.join(str(tmp_path), "env"))
    monkeypatch.delenv(publish.ENV_NAME, raising=False)
    open(os.path.join(str(tmp_path), "env"), "w", encoding="utf-8").write(
        publish.ENV_NAME + "=shibboleth\n")
    assert us.gate_cookies("staging.protectsouthportland.org") == [{
        "name": publish.GATE_COOKIE,
        "value": hashlib.sha256(b"shibboleth").hexdigest(),
        "domain": "staging.protectsouthportland.org",
        "path": "/",
        "secure": True,
        "sameSite": "Lax",
    }]


def test_gate_cookie_missing_passphrase_is_loud_on_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "STAGING_DOTENV", os.path.join(str(tmp_path), "absent"))
    monkeypatch.delenv(publish.ENV_NAME, raising=False)
    with pytest.raises(us.AuditInfraError) as loud:
        us.gate_cookies("staging.protectsouthportland.org")
    assert publish.ENV_NAME in str(loud.value)


def test_non_staging_hosts_run_cookieless():
    assert us.gate_cookies("cristoslc.github.io") == []
    assert us.gate_cookies("127.0.0.1") == []


def test_gate_result_ok_requires_no_overlay_and_content():
    assert us.gate_result_ok({"overlay": False, "main": True}) is True
    assert us.gate_result_ok({"overlay": True, "main": True}) is False, \
        "a page captured behind the gate overlay is not a valid capture"
    assert us.gate_result_ok({"overlay": False, "main": False}) is False, \
        "no content marker means a broken page, not a capture"
    assert us.gate_result_ok({}) is False


def test_gate_eval_checks_the_overlay_and_the_content_marker():
    assert ".staging-gate-overlay" in us.GATE_EVAL_JS
    # the map pages carry no <main>: their #map shell counts as content too
    assert "#map" in us.GATE_EVAL_JS
    assert "main#content" in us.GATE_EVAL_JS


def test_manifest_contract(tmp_path):
    data = {
        "date": "2026-10-15", "target": "staging",
        "base": "https://staging.protectsouthportland.org/",
        "gated": True, "widths": list(us.WIDTHS),
        "pages": ["index.html"],
        "excluded": [{"page": "vocs.html", "reason": "redirect stub"}],
        "samples": [{"page": "index.html", "width": 412,
                     "path": "index-412.png", "bytes": 12345, "gate_open": True}],
    }
    us.write_manifest(tmp_path, data)
    loaded = json.loads((tmp_path / "manifest.json").read_text())
    assert loaded == data


def test_cli_defaults_match_the_commission():
    parser = us.build_parser()
    args = parser.parse_args([])
    assert args.target == "staging"
    assert args.date == "today"
    outdir, date = us.resolve_outdir(args, today="2026-10-15")
    assert os.path.basename(outdir) == "2026-10-15"
    assert os.path.basename(os.path.dirname(outdir)) == "uat-snapshots"