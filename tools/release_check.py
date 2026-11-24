#!/usr/bin/env python3
"""Release-gate checks for the fork model: freshness, scan, gate report.

tools/publish.py enforced three invariants at publish time: it built the
tree it pushed, scanned that tree with psp_public, and validated the gate
report against the built bytes. Under the fork model (migration plan
2026-11-24) the push is a pull request and Pages serves the committed
docs/ tree directly, so the same three invariants run here, in CI, on
every pull request and every push to main:

- FRESHNESS: a rebuild from site/pages/ must equal the committed docs/
  tree. A source edit without a rebuilt build cannot merge, on upstream
  or on the fork, which is what replaces the publish tool's
  build-at-publish trust.
- SCAN: the psp_public publication-safety scan over docs/, the served
  tree. The scan runs on every push rather than only at publish time.
  It scans docs/ only, never the repo root, because the marker literals
  the scan bans (the private repo's name, its github.io host) are what
  the scanner itself is made of.
- GATE REPORT: a report committed to a release pull request must carry
  the sha256 of every built page as it stands in that PR's committed
  docs/ tree, a full-class reviewer, and no flash marker. That is
  publish.load_gate_report's rule set, unchanged, so a verdict still
  cannot outlive the content it reviewed.

Usage:
  python3 tools/release_check.py            # freshness + scan
  python3 tools/release_check.py --freshness --scan   # same, explicit
  python3 tools/release_check.py --gate-report gate-reports/<date>.json

Exit status is non-zero on any finding; CI turns that into a red check.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build
import psp_public
import publish

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Committed files in docs/ that the build does not produce. Everything
# else in the committed tree must exist in a fresh build with identical
# bytes. robots.txt is authored, .nojekyll is serving config, CNAME is
# the deliberate cutover-time domain file (untracked until then).
NON_BUILT_ALLOWED = {"robots.txt", ".nojekyll", "CNAME"}


def file_sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def tree_hashes(tree_dir):
    out = {}
    for dirpath, dirnames, filenames in os.walk(tree_dir):
        dirnames.sort()
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), tree_dir)
            out[rel.replace(os.sep, "/")] = file_sha256(
                os.path.join(dirpath, name))
    return out


def tree_diffs(fresh_dir, committed_dir):
    """Differences between a fresh build and the committed docs/ tree.

    Pure comparison, no build: fresh_dir is a tree a fresh build produced
    (or a test fixture standing in for one), committed_dir is the tree
    Pages would serve. Returns human-readable differences, empty when the
    committed tree is fresh.
    """
    fresh = tree_hashes(fresh_dir)
    committed = tree_hashes(committed_dir)
    diffs = []
    for rel in sorted(fresh):
        if rel not in committed:
            diffs.append(f"{rel}: the build produces it, docs/ does not "
                         "carry it — rebuild and commit docs/")
        elif fresh[rel] != committed[rel]:
            diffs.append(f"{rel}: committed bytes differ from a fresh "
                         "build — rebuild and commit docs/")
    for rel in sorted(set(committed) - set(fresh)):
        if rel in NON_BUILT_ALLOWED:
            continue
        diffs.append(f"{rel}: docs/ carries it, a fresh build does not — "
                     "a stale file in the served tree; remove it or give "
                     "the page a redirect stub (build.py REDIRECTS)")
    return diffs


def fresh_tree_diffs(docs_dir):
    """tree_diffs between a fresh build and the committed docs/ tree.

    Builds site/pages into a scratch dir (copying the committed docs/map
    in first, which is exactly how a CI checkout builds: build.py keeps
    an existing map dir when no tank-farms sibling is present), then
    compares.

    The map itself cannot be freshness-checked here: its source lives in
    the private tank-farms checkout, which does not ride a public CI.
    Map updates land as deliberate commits, like any other content.
    """
    scratch = tempfile.mkdtemp(prefix="psp-fresh-")
    try:
        committed_map = os.path.join(docs_dir, psp_public.MAP_DIRNAME)
        if os.path.isdir(committed_map):
            shutil.copytree(
                committed_map,
                os.path.join(scratch, psp_public.MAP_DIRNAME))
        build.build(scratch)
        return tree_diffs(scratch, docs_dir)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def scan_docs(docs_dir=None):
    """psp_public violations for the served tree; empty list = clean."""
    return psp_public.scan_tree(docs_dir or os.path.join(ROOT, "docs"))


def validate_gate_report(path):
    """publish.load_gate_report's full rule set, against the current tree."""
    model, review_class, per_page = publish.load_gate_report(path)
    print(f"gate report {os.path.basename(path)}: model {model} "
          f"(class {review_class}), pages: {per_page}")


def main():
    parser = argparse.ArgumentParser(
        description="Release-gate checks: freshness, scan, gate report.")
    parser.add_argument("--freshness", action="store_true", default=False,
                        help="rebuild site/pages and compare against the "
                             "committed docs/ tree (default: on when no "
                             "other check is requested)")
    parser.add_argument("--scan", action="store_true", default=False,
                        help="run the psp_public scan over docs/")
    parser.add_argument("--gate-report", default=None, metavar="PATH",
                        help="validate one gate report against the current "
                             "committed docs/ tree")
    args = parser.parse_args()
    if not (args.freshness or args.scan or args.gate_report):
        args.freshness = True
        args.scan = True

    if args.freshness:
        diffs = fresh_tree_diffs(os.path.join(ROOT, "docs"))
        if diffs:
            raise SystemExit(
                "committed docs/ is not a fresh build — a source edit "
                "without a rebuilt docs/ cannot merge:\n  "
                + "\n  ".join(diffs))
        print("freshness: committed docs/ equals a fresh build")

    if args.scan:
        psp_public.assert_clean(scan_docs(), "committed docs/ tree")
        print("scan: committed docs/ tree is publication-clean")

    if args.gate_report:
        validate_gate_report(args.gate_report)


if __name__ == "__main__":
    main()
