import hashlib
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
  with the first an ancestor of the second;
- a green serve stamps the served state with an annotated `staging-<sha>`
  review tag on the fork-main commit it was built from (ledger row 103,
  operator instruction 2026-11-24), a second serve on the same sha
  reuses the tag instead of duplicating it, and a failed tag push
  reports but never fails the serve, because the serve landed and the
  tag is bookkeeping.
"""

import datetime
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import publish
import staging_serve

# The same literal the landed gate pins use (row 128), so both suites prove
# the same digest math against the same phrase.
GATE_TEST_PASSPHRASE = "crawlers-keep-out"


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
        str(src), str(dst), "staging.protectsouthportland.org",
        passphrase="serve-tree-test")
    assert pages == 1
    assert (dst / "CNAME").read_text() == "staging.protectsouthportland.org\n"
    assert (dst / "robots.txt").read_text() == staging_serve.GATE_ROBOTS_TEXT
    assert "Disallow: /" in (dst / "robots.txt").read_text()
    assert (dst / ".nojekyll").exists()
    served = (dst / "index.html").read_text()
    # row 128: the noindex rides inside the gate block now (row 42 machinery)
    assert '<meta name="robots" content="noindex, nofollow">' in served
    assert served.index('<meta name="robots" content="noindex, nofollow">') < served.index("</head>")
    assert "some-other-host.example" not in served


def test_serve_tree_gates_every_page(tmp_path, monkeypatch):
    """Ledger row 128 (2026-11-25), the operator's directive verbatim: "we
    still need the crawler gate and passphrase, too. I don't know why they got
    removed, but I expect them to still be in place." The reversal corpus id
    is dl-20261125T142900-d080; the ruling it reverses is dec_63blvjzqob1t
    (dl-20261124T154549-c606). The fork-model serve re-implements the row-42
    gate as amended by row 60 by REUSING publish.apply_staging_gate, so both
    pipelines run the same block: every served page carries the gate (only
    the passphrase's sha256 embeds; the plaintext never reaches a page), the
    curtain ships as a real <style> tag hidden from first paint (row 60a),
    the phrase field refocuses on window load against the map iframe (row
    60b), and the wrong phrase errors and stays locked (the block's own
    branch)."""
    src = _fixture_docs(tmp_path / "src")
    dst = tmp_path / "serve"
    monkeypatch.setenv("PSP_STAGING_PASSPHRASE", "crawlers-keep-out")
    pages = staging_serve.prepare_serve_tree(
        str(src), str(dst), "staging.protectsouthportland.org",
        base_sha="a" * 40)
    assert pages == 1
    served = (dst / "index.html").read_text()
    assert staging_serve.GATE_MARKER in served, "the gate is on every served page"
    digest = hashlib.sha256(b"crawlers-keep-out").hexdigest()
    assert digest in served, "the gate embeds the passphrase's sha256"
    assert "crawlers-keep-out" not in served, "the plaintext never reaches a page"
    assert '<meta name="robots" content="noindex, nofollow">' in served
    assert ".staging-gate body{visibility:hidden!important}" in served, (
        "the curtain ships as a real <style> tag (row 60a)")
    assert 'window.addEventListener("load"' in served, (
        "the phrase field refocuses after load (row 60b)")
    assert '"psp_staging"' in served
    assert "staging-gate-wrong" in served, "a wrong phrase errors and stays locked"
    assert 'Max-Age=2592000' in served, "the cookie persists 30 days"
    # the robots.txt the serve writes is the staging Disallow-all variant
    assert (dst / "robots.txt").read_text() == staging_serve.GATE_ROBOTS_TEXT


def test_serve_refuses_loud_without_a_passphrase(tmp_path, monkeypatch):
    """Fail loud, per row 42 as amended: a serve run with no passphrase in the
    environment and none beside the checkout refuses entirely - no tree, no
    gate keyed to nothing."""
    src = _fixture_docs(tmp_path / "src")
    monkeypatch.delenv("PSP_STAGING_PASSPHRASE", raising=False)
    monkeypatch.setattr(publish, "STAGING_DOTENV", str(tmp_path / "missing.env"))
    with pytest.raises(SystemExit) as loud:
        staging_serve.prepare_serve_tree(
            str(src), str(tmp_path / "serve"), "staging.protectsouthportland.org")
    assert "PSP_STAGING_PASSPHRASE" in str(loud.value)


def test_serve_tree_writes_the_preview_manifest(tmp_path):
    """Ledger row 127 (2026-11-25), the operator's staging-bar directive: the
    bar's "last updated" fact comes from staging-manifest.json, written by
    prepare_serve_tree into the SERVE tree (not the repo build) at serve time
    with the serve time and the fork sha the tree was built from. The built
    docs/ bytes therefore carry no volatile timestamp, so production and
    staging serve byte-identical trees and release freshness stays
    idempotent."""
    src = _fixture_docs(tmp_path / "src")
    dst = tmp_path / "serve"
    staging_serve.prepare_serve_tree(
        str(src), str(dst), "staging.protectsouthportland.org",
        base_sha="abcdef1234567890", passphrase="serve-tree-test")
    manifest = json.loads((dst / "staging-manifest.json").read_text())
    assert manifest["head"] == "abcdef1234567890"
    # the serve time is a parseable UTC ISO instant, seconds precision
    datetime.datetime.fromisoformat(manifest["served"])
    assert manifest["served"].endswith("+00:00")
    # and the served PAGE is the manifest's only channel: the timestamp lives
    # in no page's markup
    assert "served" not in (dst / "index.html").read_text()


def test_a_headless_page_refuses_the_serve(tmp_path):
    src = _fixture_docs(tmp_path / "src", head=False)
    with pytest.raises(SystemExit) as loud:
        staging_serve.prepare_serve_tree(
            str(src), str(tmp_path / "serve"), "staging.example",
            passphrase="serve-tree-test")
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


def _repo_with_origin(path):
    """A repo with an `origin` remote, the CI shape.

    On the fork's runner the remote is the repository itself, configured
    by actions/checkout; in tests a bare repo stands in for it. The
    fixture sets its own identity because the runner carries none (a
    local git fabricates one silently, which masked this on dev
    machines while CI failed), and the seed commit gives the
    branch_exists fetch a main to hold and the push a fast-forward
    base.
    """
    origin = path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True, text=True)
    repo = path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    # a dev machine's global signing config (e.g. 1Password SSH signing
    # of annotated tags) must not reach the generated tag: the hermetic
    # world is unsigned, like a bare Actions runner.
    _git(repo, "config", "tag.gpgsign", "false")
    _git(repo, "config", "tag.forcesignannotated", "false")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "seed.txt").write_text("base")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "origin", "main")
    return repo


def test_the_push_lands_on_the_remote(tmp_path):
    """A green serve run must leave staging-pages on origin.

    The fork's second serve run (45436048653, 2026-11-24) committed the
    serve tree, printed success naming `staging-pages`, and left nothing
    on the remote: the tool never ran `git push`. The branch lived only
    in the runner's workspace and died with it, while the run's own
    summary line asserted a landing that did not happen.
    """
    repo = _repo_with_origin(tmp_path)
    tree = _serve_tree(tmp_path / "serve", "pushed serve")
    sha = staging_serve.push_serve_branch(
        str(tree), "staging-pages", str(repo), "0" * 40)
    remote = subprocess.run(
        ["git", "--git-dir", str(tmp_path / "origin.git"),
         "rev-parse", "refs/heads/staging-pages"],
        capture_output=True, text=True)
    assert remote.returncode == 0, "staging-pages must exist on origin"
    assert remote.stdout.strip() == sha


def test_pushes_append_and_never_force(tmp_path):
    repo = _repo_with_origin(tmp_path)

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
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an", "staging-pages"],
        cwd=repo, capture_output=True, text=True).stdout.strip()
    assert author == "test", "a configured identity must never be overridden"
    remote = subprocess.run(
        ["git", "--git-dir", str(tmp_path / "origin.git"),
         "rev-parse", "refs/heads/staging-pages"],
        capture_output=True, text=True)
    assert remote.stdout.strip() == sha_two, (
        "origin must hold the newest serve, fast-forwarded, never replaced")


def test_push_supplies_identity_on_a_bare_runner(tmp_path, monkeypatch):
    """A repo with no git identity still takes the serve commit.

    A clean Actions runner has no user.name, no user.email, no global
    config. The fork's first serve run (run 45431398640, 2026-11-24)
    died at "cannot commit the serve tree" for exactly this reason, so
    the tool must supply its own machine identity when none resolves —
    and never override one that does.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    repo = _repo_with_origin(tmp_path)
    _git(repo, "config", "--unset", "user.email")
    _git(repo, "config", "--unset", "user.name")
    # a bare runner cannot fall back to an auto-fabricated ident either
    _git(repo, "config", "user.useConfigOnly", "true")
    # identity-free from here, exactly like the runner
    tree = _serve_tree(tmp_path / "serve", "identity-free serve")
    sha = staging_serve.push_serve_branch(
        str(tree), "staging-pages", str(repo), "0" * 40)
    assert sha
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>", "staging-pages"],
        cwd=repo, capture_output=True, text=True).stdout.strip()
    assert author == staging_serve.SERVE_COMMITTER, author


def test_cli_prepare_only_run_stands_up_end_to_end():
    """A bare CLI run over the real repo: freshness, scan, prepare, print.

    The default path prepares and verifies without pushing, which is what
    a local operator run looks like; only --push writes the branch.
    """
    env = dict(os.environ, PSP_STAGING_PASSPHRASE="cli-e2e-test")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "staging_serve.py")],
        cwd=ROOT, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert "pages prepared" in proc.stdout
    assert "staging.protectsouthportland.org" in proc.stdout
    assert "(not pushed)" in proc.stdout


def _base_commit(repo):
    """The seed commit, the fork-main sha a serve run is generated from."""
    proc = subprocess.run(["git", "rev-parse", "main"], cwd=repo,
                          capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _junk_fixture_docs(path):
    """A docs tree that carries bytecode junk, the shape a checkout has
    after pytest or any import ran inside it."""
    path.mkdir(parents=True)
    (path / "index.html").write_text("<html><head></head><body>page</body></html>")
    (path / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    cache = path / "tools" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "staging_serve.cpython-314.pyc").write_bytes(b"\x00junk")
    tests_cache = path / "tests" / "__pycache__"
    tests_cache.mkdir(parents=True)
    (tests_cache / "test_site.cpython-313-pytest-9.1.1.pyc").write_bytes(b"\x00junk")
    (path / ".DS_Store").write_bytes(b"\x00junk")
    return path


def test_the_prepared_serve_tree_carries_no_bytecode_junk(tmp_path):
    """Ledger row 136 (2026-11-25): the serve tree must never carry
    bytecode junk. prepare copies from the committed docs/ tree, so a
    docs tree that ever grows a cache cannot leak it into the serve."""
    src = _junk_fixture_docs(tmp_path / "src")
    dst = tmp_path / "serve"
    staging_serve.prepare_serve_tree(
        str(src), str(dst), "staging.example", passphrase=GATE_TEST_PASSPHRASE)
    junk = [os.path.join(dirpath, name)
            for dirpath, dirnames, filenames in os.walk(dst)
            for name in list(dirnames) + list(filenames)
            if name == "__pycache__" or name.endswith((".pyc", ".pyo", ".DS_Store"))]
    assert junk == [], f"the serve tree carries bytecode junk: {junk}"


def test_the_serve_tree_is_exactly_the_intended_set(tmp_path):
    """The serve tree's boundary is a fixed manifest: the docs tree (minus
    any CNAME, plus the files the serve owns) and nothing else — no
    sweeping of whatever else happens to sit beside it."""
    src = _fixture_docs(tmp_path / "src")
    dst = tmp_path / "serve"
    staging_serve.prepare_serve_tree(
        str(src), str(dst), "staging.example", passphrase=GATE_TEST_PASSPHRASE)
    served = {os.path.relpath(os.path.join(dirpath, name), dst)
              for dirpath, _, filenames in os.walk(dst)
              for name in filenames}
    assert served == {"index.html", "robots.txt", ".nojekyll", "CNAME",
                      "staging-manifest.json"}, served


def test_a_push_sweeps_untracked_bytecode_from_the_checkout(tmp_path):
    """The root cause (ledger row 136): the serve commit is built with
    `git rm` (tracked files only) followed by `git add -A`, so untracked
    bytecode that the serve process itself created — tools/__pycache__
    from the imports at startup (cpython-314 on the Actions runner), or
    tests/__pycache__ + tools/__pycache__ left by pytest in a local
    checkout — survives the rm and is staged into the serve commit. The
    push must sweep the checkout clean before staging the tree."""
    repo = _repo_with_origin(tmp_path)
    for rel in ("tools/__pycache__/staging_serve.cpython-314.pyc",
                "tests/__pycache__/test_site.cpython-313-pytest-9.1.1.pyc"):
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"\x00junk")
    base = _base_commit(repo)
    tree = _serve_tree(tmp_path / "serve", "clean serve")
    staging_serve.push_serve_branch(
        str(tree), "staging-pages", str(repo), base,
        cname="staging.protectsouthportland.org")
    listing = _remote_list(repo, "ls-tree", "-r", "--name-only",
                           "refs/heads/staging-pages")
    assert listing.returncode == 0
    junk = [line for line in listing.stdout.splitlines()
            if "__pycache__" in line or line.endswith((".pyc", ".pyo"))]
    assert junk == [], f"the serve commit carries bytecode junk: {junk}"


# ---- row 141 (2026-11-25): the serve pushes to the FORK, never to origin ----
# The lane's note: --push hardcodes `origin`, so a hand-run serve scatters a
# staging-pages branch onto whatever origin names — tonight the site repo's
# own origin carries a stray staging-pages branch (9ee6914) as the evidence.
# The serve remote is now resolved explicitly and judged by host: a GitHub
# push URL must name the fork exactly, otherwise the serve refuses loud.

UPSTREAM_URL = "https://github.com/cristoslc/protect-south-portland-site.git"


def _point_origin_at_upstream(repo):
    subprocess.run(["git", "remote", "set-url", "origin", UPSTREAM_URL],
                   cwd=repo, check=True, capture_output=True, text=True)


def test_the_serve_refuses_an_origin_that_is_not_the_fork(tmp_path):
    # the real upstream URL: the guard fires before any fetch or push, so
    # the refusal is proven offline (red-first was demonstrated with an
    # unroutable host reaching "cannot push" instead of the refusal)
    repo = _repo_with_origin(tmp_path)
    _point_origin_at_upstream(repo)
    base = _base_commit(repo)
    with pytest.raises(SystemExit) as loud:
        staging_serve.push_serve_branch(
            str(_serve_tree(tmp_path / "serve", "guarded serve")),
            "staging-pages", str(repo), base,
            cname="staging.protectsouthportland.org")
    assert "protect-south-portland-staging" in str(loud.value)


def test_the_serve_remote_flag_targets_the_fork_and_never_origin(tmp_path):
    # one bare stands in for the fork remote, origin carries the upstream
    # URL and must end the run untouched
    path = tmp_path / "git"
    origin = path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True, text=True)
    fork_remote = path / "staging-fork.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(fork_remote)],
                   check=True, capture_output=True, text=True)
    repo = path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "index.html").write_text("<html><head></head><body>seed</body></html>")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "origin", "main")
    _point_origin_at_upstream(repo)
    _git(repo, "remote", "add", "staging-fork", str(fork_remote))
    base = _base_commit(repo)
    sha = staging_serve.push_serve_branch(
        str(_serve_tree(tmp_path / "serve", "fork-targeted serve")),
        "staging-pages", str(repo), base, remote="staging-fork",
        cname="staging.protectsouthportland.org")
    landed = subprocess.run(
        ["git", "--git-dir", str(fork_remote), "rev-parse",
         "refs/heads/staging-pages"], capture_output=True, text=True)
    assert landed.returncode == 0, "the serve branch exists on the named remote"
    assert landed.stdout.strip() == sha, "the serve lands on the named remote"
    scattered = _remote_list(repo, "rev-parse", "refs/heads/staging-pages")
    assert scattered.returncode != 0 or not scattered.stdout.strip(), (
        "origin must never receive a serve push")


def test_serve_remote_judges_urls_by_host():
    judge = staging_serve.serve_remote_ok
    assert judge("https://github.com/Protect-South-Portland/"
                 "protect-south-portland-staging")
    assert judge("https://github.com/Protect-South-Portland/"
                 "protect-south-portland-staging.git")
    assert judge("git@github.com:Protect-South-Portland/"
                 "protect-south-portland-staging.git")
    # a local path is not a public scatter target: the test world and
    # approved local bare fixtures push by path
    assert judge("/tmp/psp-serve-origin.git")
    assert judge("../origin.git")
    # any other GitHub repo, upstream included, is refused
    assert not judge("https://github.com/cristoslc/"
                     "protect-south-portland-site.git")
    assert not judge("git@github.com:cristoslc/"
                     "protect-south-portland-site.git")


# Every working way to spell this repository's own URL, canonical or not.
# The first two are the shapes row 142's fence recognized; the rest are the
# six forms that passed it (issue #140). A scheme, a port, a host case or
# an embedded credential does not change which repo a URL names.
UPSTREAM_URL_FORMS = [
    "https://github.com/cristoslc/protect-south-portland-site.git",
    "git@github.com:cristoslc/protect-south-portland-site.git",
    "ssh://git@github.com/cristoslc/protect-south-portland-site.git",
    "ssh://git@ssh.github.com:443/cristoslc/protect-south-portland-site.git",
    "https://user@github.com/cristoslc/protect-south-portland-site.git",
    "https://user:s3cret@github.com/cristoslc/protect-south-portland-site.git",
    "http://github.com/cristoslc/protect-south-portland-site.git",
    "https://GitHub.com/cristoslc/protect-south-portland-site.git",
]


def test_serve_remote_refuses_upstream_in_every_working_url_form():
    """No spelling of upstream's URL gets past the judge (issue #140).

    The first fence read the two canonical spellings only, so an ssh URL,
    an ssh.github.com URL on port 443, an embedded credential, an http
    scheme or a case-variant host named upstream and still passed. The
    judge now resolves the host and the repo path, so scheme, port, host
    case and credentials cannot disguise the target.
    """
    judge = staging_serve.serve_remote_ok
    for url in UPSTREAM_URL_FORMS:
        assert not judge(url), f"upstream must be refused in the form {url!r}"


def test_serve_remote_accepts_the_fork_in_every_working_url_form():
    """The widened fence still passes the fork wherever git can push it.

    A fence that refuses the fork's own URLs would break the serve it
    guards, so each accepted spelling is pinned: the canonical https and
    scp forms, the ssh scheme, ssh.github.com on its port, an embedded
    credential, a case-variant host, a trailing slash, the scp form with
    no user, and the repo spelled in a different case the way GitHub
    compares it.
    """
    judge = staging_serve.serve_remote_ok
    fork_forms = [
        "https://github.com/Protect-South-Portland/"
        "protect-south-portland-staging",
        "https://github.com/Protect-South-Portland/"
        "protect-south-portland-staging.git",
        "https://github.com/Protect-South-Portland/"
        "protect-south-portland-staging.git/",
        "git@github.com:Protect-South-Portland/"
        "protect-south-portland-staging.git",
        "github.com:Protect-South-Portland/protect-south-portland-staging.git",
        "ssh://git@github.com/Protect-South-Portland/"
        "protect-south-portland-staging.git",
        "ssh://git@ssh.github.com:443/Protect-South-Portland/"
        "protect-south-portland-staging.git",
        "https://user:token@github.com/Protect-South-Portland/"
        "protect-south-portland-staging.git",
        "https://GitHub.com/Protect-South-Portland/"
        "protect-south-portland-staging.git",
        "https://github.com/protect-south-portland/"
        "PROTECT-SOUTH-PORTLAND-STAGING.git",
    ]
    for url in fork_forms:
        assert judge(url), f"the fork must still serve in the form {url!r}"


def test_serve_remote_still_allows_shapes_that_name_no_github_repo():
    """A local path or a non-GitHub host is not a GitHub scatter target.

    The fence's job is upstream's URL, not every remote: the test world and
    approved bare fixtures push by path, and a non-GitHub host is outside
    the rows this fence covers. A GitHub host with no repo path names
    nothing and is refused rather than waved through.
    """
    judge = staging_serve.serve_remote_ok
    assert judge("/tmp/psp-serve-origin.git")
    assert judge("../origin.git")
    assert judge("file:///tmp/psp-serve-origin.git")
    assert judge("https://gitlab.com/someone/else.git")
    assert not judge("https://github.com/")
    assert not judge("git@github.com:")


def _remote_list(repo, *git_args):
    origin_dir = os.path.abspath(os.path.join(repo, "..", "origin.git"))
    return subprocess.run(
        ["git", "--git-dir", origin_dir, *git_args],
        capture_output=True, text=True)


def test_a_serve_run_stamps_a_review_tag_for_the_served_sha(tmp_path, monkeypatch):
    """A green serve run stamps the served state for review checkouts.

    The operator's instruction (ledger row 103, 2026-11-24): staging gets
    a tag for editorial review checkouts while merges always deploy. The
    tag names the serve sha the branch's subject names, so tag and branch
    agree on what was served, and its annotation carries the run id, the
    UTC time and the served hostname. The reviewable checkout is the
    fork-main commit the serve was generated from, not the serve branch.
    """
    monkeypatch.setenv("GITHUB_RUN_ID", "45444343117")
    repo = _repo_with_origin(tmp_path)
    base = _base_commit(repo)
    tree = _serve_tree(tmp_path / "serve", "tagged serve")
    staging_serve.push_serve_branch(
        str(tree), "staging-pages", str(repo), base,
        cname="staging.protectsouthportland.org")
    tag = staging_serve.review_tag_name(base)
    listing = _remote_list(repo, "tag", "--list")
    assert listing.returncode == 0
    assert tag in listing.stdout.splitlines(), (
        "the serve run must leave the review tag on origin")
    target = _remote_list(repo, "rev-parse", f"{tag}^{{commit}}")
    assert target.stdout.strip() == base, (
        "the review tag must point at the fork-main commit the serve "
        "was generated from, the reviewable checkout")
    contents = _remote_list(repo, "tag", "--list", "-n99", tag).stdout
    assert "staging.protectsouthportland.org" in contents
    assert "45444343117" in contents, "the annotation carries the run id"


def test_a_second_serve_on_the_same_sha_reuses_the_same_tag(tmp_path, monkeypatch):
    """A re-serve of the same fork-main sha must not duplicate or error.

    Tags append for the life of the repo: once a sha's review tag
    exists, later serves of that sha leave it alone. The serve branch
    still lands (merges always deploy); only the tag bookkeeping is
    idempotent.
    """
    monkeypatch.setenv("GITHUB_RUN_ID", "45444343117")
    repo = _repo_with_origin(tmp_path)
    base = _base_commit(repo)
    staging_serve.push_serve_branch(
        str(_serve_tree(tmp_path / "one", "first serve of the sha")),
        "staging-pages", str(repo), base,
        cname="staging.protectsouthportland.org")
    staging_serve.push_serve_branch(
        str(_serve_tree(tmp_path / "two", "second serve of the sha")),
        "staging-pages", str(repo), base,
        cname="staging.protectsouthportland.org")
    tag = staging_serve.review_tag_name(base)
    listing = _remote_list(repo, "tag", "--list")
    assert listing.stdout.splitlines().count(tag) == 1, (
        "the second serve on the same sha must keep exactly one review tag")
    target = _remote_list(repo, "rev-parse", f"{tag}^{{commit}}")
    assert target.stdout.strip() == base


def test_a_failed_tag_push_reports_but_never_fails_the_serve(tmp_path, monkeypatch):
    """The tag is bookkeeping, the branch is the deploy.

    The origin's pre-receive hook rejects tag refs only. The branch must
    still land and the push must still return: a failed tag push never
    holds a staging update back, and the serve run's outcome is the
    branch's, not the tag's.
    """
    monkeypatch.setenv("GITHUB_RUN_ID", "45444343117")
    repo = _repo_with_origin(tmp_path)
    hook = os.path.join(tmp_path, "origin.git", "hooks", "pre-receive")
    with open(hook, "w") as fh:
        fh.write("#!/bin/sh\nwhile read -r _ _ ref; do\n"
                 "  case \"$ref\" in refs/tags/*) exit 1;; esac\n"
                 "done\nexit 0\n")
    os.chmod(hook, 0o755)
    # a machine's global core.hooksPath would bypass the repo's hooks;
    # the bare origin anchors its hooks dir in its own config.
    subprocess.run(
        ["git", "--git-dir", os.path.join(tmp_path, "origin.git"),
         "config", "core.hooksPath", "hooks"],
        check=True, capture_output=True, text=True)
    base = _base_commit(repo)
    tree = _serve_tree(tmp_path / "serve", "tagless serve")
    sha = staging_serve.push_serve_branch(
        str(tree), "staging-pages", str(repo), base,
        cname="staging.protectsouthportland.org")  # must not raise
    remote = _remote_list(repo, "rev-parse", "refs/heads/staging-pages")
    assert remote.returncode == 0, (
        "the serve branch lands even when the tag push is refused")
    assert remote.stdout.strip() == sha
    listing = _remote_list(repo, "tag", "--list")
    assert listing.stdout.splitlines() == [], "no tag reached origin"
