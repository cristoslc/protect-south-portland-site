"""Tests for tools/release_check.py, the fork-model release gate.

The fork model (migration plan 2026-11-24) moves the publish tool's three
invariants into CI: the committed docs/ tree must be a fresh build, it must
pass the psp_public scan, and a gate report must match the built bytes it
claims to have reviewed. These tests pin all three with zero network:

- the real repo's committed docs/ is fresh (red the moment anyone commits
  a source edit without rebuilding);
- a doctored committed tree is flagged by name, in both directions
  (missing/different build output, and a stale file the build no longer
  produces);
- the scan is clean on the real tree and flags a planted marker;
- a report built from the real tree's hashes validates, and a tampered
  hash is refused by name (the content-addressed verdict rule).
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import publish
import release_check


def test_committed_docs_is_a_fresh_build():
    """The standing invariant: main's committed docs/ equals a rebuild.

    This is the test that goes red first: a source edit committed without
    rebuilding docs/ fails here before any release PR is opened.
    """
    assert release_check.fresh_tree_diffs(os.path.join(ROOT, "docs")) == []


def test_freshness_flags_a_doctored_committed_page(tmp_path):
    scratch = tmp_path / "scratch"
    committed = tmp_path / "docs"
    for tree in (scratch, committed):
        tree.mkdir()
        (tree / "index.html").write_text("<html>same bytes</html>")
        (tree / "styles.css").write_text("body{}")
    (committed / "index.html").write_text("<html>different bytes</html>")
    diffs = release_check.tree_diffs(str(scratch), str(committed))
    assert any("index.html" in d and "differ" in d for d in diffs), diffs


def test_freshness_flags_a_stale_file_the_build_stopped_making(tmp_path):
    scratch = tmp_path / "scratch"
    committed = tmp_path / "docs"
    scratch.mkdir()
    committed.mkdir()
    (scratch / "index.html").write_text("<html>x</html>")
    (committed / "index.html").write_text("<html>x</html>")
    (committed / "retired-page.html").write_text("stale in the served tree")
    diffs = release_check.tree_diffs(str(scratch), str(committed))
    assert any("retired-page.html" in d for d in diffs), diffs
    assert any("give the page a redirect stub" in d for d in diffs), diffs


def test_freshness_allows_the_authored_non_built_files(tmp_path):
    scratch = tmp_path / "scratch"
    committed = tmp_path / "docs"
    scratch.mkdir()
    committed.mkdir()
    (scratch / "index.html").write_text("<html>x</html>")
    (committed / "index.html").write_text("<html>x</html>")
    for name in ("robots.txt", ".nojekyll", "CNAME"):
        (committed / name).write_text("authored, not built")
    assert release_check.tree_diffs(str(scratch), str(committed)) == []


def test_scan_is_clean_on_the_real_tree():
    assert release_check.scan_docs() == []


def test_scan_flags_a_planted_marker(tmp_path):
    (tmp_path / "leak.html").write_text(
        "see github.com/cristoslc/south-portland-tank-farms for research")
    violations = release_check.scan_docs(str(tmp_path))
    assert any("south-portland-tank-farms" in v for v in violations), violations


def _report_for_current_tree(path, tamper=None):
    pages = {}
    for name in sorted(os.listdir(os.path.join(ROOT, "site", "pages"))):
        if not name.endswith(".html"):
            continue
        pages[name] = {"rounds": 1, "outcome": "pass",
                       "sha256": publish.page_sha256(name)}
    if tamper:
        entry = dict(pages[tamper])
        entry["sha256"] = "0" * 64
        pages[tamper] = entry
    report = {"date": "test", "review_model": "cove/text:ultra-heavy",
              "review_class": "full", "pages": pages,
              "scope_note": "test report over the current tree"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    return path


def test_gate_report_matching_the_tree_validates(tmp_path, capsys):
    path = _report_for_current_tree(str(tmp_path / "report.json"))
    release_check.validate_gate_report(path)
    out = capsys.readouterr().out
    assert "model cove/text:ultra-heavy" in out
    assert "class full" in out


def test_gate_report_with_a_tampered_hash_is_refused_by_name(tmp_path):
    pages = sorted(os.listdir(os.path.join(ROOT, "site", "pages")))
    page = next(p for p in pages if p.endswith(".html"))
    path = _report_for_current_tree(str(tmp_path / "report.json"), tamper=page)
    with pytest.raises(SystemExit) as loud:
        release_check.validate_gate_report(path)
    assert page in str(loud.value)
    assert "sha256 mismatch" in str(loud.value)
