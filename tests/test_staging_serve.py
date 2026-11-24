"""Tests for tools/staging_serve.py, the fork's staging serve branch.

The fork model (migration plan 2026-11-24) serves staging from a generated
branch because the staging hostname can never live in main, which release
pull requests share verbatim with upstream. These tests pin the serve
tree's shape and the branch's append-only discipline with zero network:

- the serve tree rewrites robots.txt to the staging variant, injects the
  noindex meta after <head> on every page, writes .nojekyll and the
  CNAME naming the staging host, and drops any CNAME the source carried;
- a page without <head> refuses the serve (the meta cannot protect it);
- a tree that fails the psp_public scan refuses the serve, before any
  injection, the same pre-injection order publish.py used;
- a committed tree that is not a fresh build refuses the serve, because
  staging previews exactly what a release pull request would carry;
- pushes append commits, never force: two serves produce two commits
  with the first an ancestor of the second.
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import staging_serve


def _fixture_docs(path, head=True, marker=None):
    path.mkdir(parents=True)
    head_open, head_close = ("<head>", "</head>") if head else ("", "")
    body = "<html>" + head_open + head_close + "<body>page</body></html>"
    if marker:
        body = body.replace("page", f"see {marker}")
    (path / "index.html").write_text(body)
    (path / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    (path / "CNAME").write_text("some-other-host.example\n")
    return path


def test_serve_tree_swaps_domain_and_adds_crawl_protection(tmp_path):
    src = _fixture_docs(tmp_path / "src")
    dst = tmp_path / "serve"
    pages = staging_serve.prepare_serve_tree(
        str(src), str(dst), "staging.protectsouthportland.org")
    assert pages == 1
    assert (dst / "CNAME").read_text() == "staging.protectsouthportland.org\n"
    assert (dst / "robots.txt").read_text() == staging_serve.STAGING_ROBOTS_TEXT
    assert "Disallow: /" in (dst / "robots.txt").read_text()
    assert (dst / ".nojekyll").exists()
    served = (dst / "index.html").read_text()
    assert staging_serve.NOINDEX_META in served
    assert served.index(staging_serve.NOINDEX_META) < served.index("</head>")
    assert "some-other-host.example" not in served


def test_a_headless_page_refuses_the_serve(tmp_path):
    src = _fixture_docs(tmp_path / "src", head=False)
    with pytest.raises(SystemExit) as loud:
        staging_serve.prepare_serve_tree(
            str(src), str(tmp_path / "serve"), "staging.example")
    assert "no <head>" in str(loud.value)


def test_a_tree_failing_the_scan_refuses_the_serve(tmp_path):
    src = _fixture_docs(tmp_path / "src", marker="south-portland-tank-farms")
    with pytest.raises(SystemExit) as loud:
        staging_serve.prepare_serve_tree(
            str(src), str(tmp_path / "serve"), "staging.example")
    assert "publication-safety violation" in str(loud.value)
    assert "south-portland-tank-farms" in str(loud.value)


def test_a_stale_committed_tree_refuses_the_serve():
    with pytest.raises(SystemExit) as loud:
        staging_serve.require_fresh(["index.html: committed bytes differ"])
    assert "not a fresh build" in str(loud.value)
    assert "index.html" in str(loud.value)
    staging_serve.require_fresh([])  # the fresh path is silent


def _serve_tree(path, label):
    path.mkdir(parents=True)
    (path / "index.html").write_text(f"<html><head></head>{label}</html>")
    return path


def _git(repo, *cmd):
    subprocess.run(["git", *cmd], cwd=repo, check=True,
                   capture_output=True, text=True)


def test_pushes_append_and_never_force(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "seed.txt").write_text("base")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")

    tree_one = _serve_tree(tmp_path / "one", "first serve")
    sha_one = staging_serve.push_serve_branch(
        str(tree_one), "staging-pages", str(repo), "0" * 40)
    tree_two = _serve_tree(tmp_path / "two", "second serve")
    sha_two = staging_serve.push_serve_branch(
        str(tree_two), "staging-pages", str(repo), "0" * 40)
    assert sha_one != sha_two
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha_one, sha_two],
        cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, "the second serve must append, not replace"
    log = subprocess.run(
        ["git", "log", "--format=%s", "staging-pages"],
        cwd=repo, capture_output=True, text=True).stdout.splitlines()
    assert log[0].startswith("Serve 000000000000")
    assert (repo / "index.html").read_text() == "<html><head></head>second serve</html>"


def test_cli_prepare_only_run_stands_up_end_to_end():
    """A bare CLI run over the real repo: freshness, scan, prepare, print.

    The default path prepares and verifies without pushing, which is what
    a local operator run looks like; only --push writes the branch.
    """
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "staging_serve.py")],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "pages prepared" in proc.stdout
    assert "staging.protectsouthportland.org" in proc.stdout
    assert "(not pushed)" in proc.stdout
