#!/usr/bin/env python3
"""Build the fork's staging serve tree onto the staging-pages branch.

Under the fork model (migration plan 2026-11-24) staging is a fork whose
Pages must NOT serve main directly. A branch deployment reads the served
directory's CNAME file as its custom domain, and fork main is shared
verbatim with upstream through release pull requests, so the staging
hostname can never live in main. This tool writes the generated serve
branch instead:

- refuses unless the committed docs/ tree is a fresh build (release_check),
  because staging must preview exactly the bytes a release PR would carry;
- copies docs/ (minus any CNAME) and runs the psp_public scan over the
  copy, the same pre-injection order publish.py used;
- writes the staging robots.txt (Disallow-all) and a per-page noindex
  meta: the crawl protection that is ledger row 42's honest core. The
  cookie gate and the row-79 stamp are NOT carried — the operator ruling
  on their disposition is pending on the migration decision card, and
  this file is the place that ruling amends. The branch's own commit
  names what it serves, which is the stamp's question answered
  structurally;
- writes the CNAME naming the staging host, the one file that makes this
  branch differ from main and the reason it exists;
- commits the tree onto staging-pages and pushes, appending — never a
  force push, so the branch's history is a readable serve log. The push
  sweeps the checkout clean before staging (ledger row 136, 2026-11-25:
  `git rm` removes tracked files only, so untracked bytecode the serve
  process itself created survived to be swept into the serve commit by
  `git add -A`), and the copy into the serve tree excludes caches and OS
  droppings at the prepare boundary;
- after a successful push, stamps the served state with an annotated
  `staging-<serve sha>` review tag on the fork-main commit the serve
  was generated from (ledger row 103, operator instruction:
  "Staging should get a tag for editorial review checkouts, but
  merges/changes should always deploy to it"). The tag is bookkeeping
  for editorial review checkouts, never a deploy trigger: a missing
  tag never holds a staging update back, a sha whose tag exists is a
  no-op, and a failed tag push reports without failing the serve.

Usage:
  python3 tools/staging_serve.py            # prepare + verify, no push
  python3 tools/staging_serve.py --push     # the fork's CI path
"""
import argparse
import datetime
import os
import shutil
import json
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import publish
import psp_public
import release_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAGING_HOST = "staging.protectsouthportland.org"  # ledger row 41
SERVE_BRANCH = "staging-pages"

# the serve tree's robots variant and noindex injection come from
# publish.apply_staging_gate (row 42 as amended by row 60; ledger row 128)


def require_fresh(diffs):
    """Refuse to serve a committed tree that is not a fresh build.

    Staging previews the bytes a release PR would carry. If it silently
    rebuilt from source instead, it could serve content that fails the
    release gate, so a stale committed tree stops the serve loud.
    """
    if diffs:
        raise SystemExit(
            "staging serve: the committed docs/ tree is not a fresh "
            "build, refusing to serve it:\n  " + "\n  ".join(diffs))


GATE_MARKER = publish.GATE_MARKER
GATE_ROBOTS_TEXT = publish.GATE_ROBOTS_TEXT


def prepare_serve_tree(src_docs, dst, cname, base_sha=None, passphrase=None):
    """... (gate note) ..."""
    """Build the serve tree in dst from the committed docs/ tree.

    Copy (minus any CNAME file), scan the copy before injecting anything
    (the same order the publish staging leg used), then write the staging
    crawl protection, the noindex meta on every page, .nojekyll, and the
    CNAME that names the staging host. Writes staging-manifest.json (the
    staging preview bar's served time and the fork sha the tree was built
    from; ledger row 127). Then the row-42 cookie gate rides this same tree:
    the passphrase resolves from the environment (workspace .env fallback),
    a serve run refuses loud without one, and publish.apply_staging_gate
    injects the noindex meta and the gate into every served page (row 128;
    ledger row 42 as amended by row 60). Returns the gated page count.
    """
    os.makedirs(dst, exist_ok=True)
    # Bytecode junk never rides the serve tree (ledger row 136, 2026-11-25):
    # caches and OS droppings are excluded at the copy boundary even if a
    # committed docs/ tree ever grows them.
    ignore_junk = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo",
                                         ".DS_Store")
    for entry in sorted(os.listdir(src_docs)):
        if entry == "CNAME" or entry == "__pycache__" or entry == ".DS_Store" \
                or entry.endswith((".pyc", ".pyo")):
            continue
        src = os.path.join(src_docs, entry)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, entry), dirs_exist_ok=True,
                            ignore=ignore_junk)
        else:
            shutil.copy2(src, os.path.join(dst, entry))
    open(os.path.join(dst, ".nojekyll"), "w").write("")
    manifest = {"served": datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")}
    if base_sha:
        manifest["head"] = base_sha
    open(os.path.join(dst, "staging-manifest.json"), "w",
         encoding="utf-8").write(json.dumps(manifest) + "\n")
    psp_public.assert_clean(
        psp_public.scan_tree(dst), "staging serve tree (pre-injection)")
    open(os.path.join(dst, "CNAME"), "w", encoding="utf-8").write(cname + "\n")
    if passphrase is None:
        passphrase = publish.staging_passphrase()
    gated = publish.apply_staging_gate(dst, passphrase)
    return gated


def _git(*cmd, cwd):
    proc = subprocess.run(["git", *cmd], cwd=cwd, capture_output=True,
                          text=True)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        err = proc.stderr.strip()
        if err:
            out = f"{out}\n{err}" if out else err
    return proc.returncode == 0, out


def branch_exists(branch, cwd):
    """True when the serve branch exists remotely or locally.

    The remote check comes first (the fork's CI world); a repo with no
    remote (tests) falls back to the local ref.
    """
    ok, _ = _git("fetch", "origin", branch, cwd=cwd)
    if ok:
        return True
    ok, _ = _git("show-ref", "--verify", f"refs/heads/{branch}", cwd=cwd)
    return ok


# The machine identity the serve commit carries when the environment
# has none. A bare Actions runner ships no user.name/user.email (the
# fork's first serve run, 45431398640, died at the commit step for
# exactly this reason), so a generated serve branch must be committable
# with zero pre-configuration. A configured identity always wins.
SERVE_COMMITTER_NAME = "psp staging serve"
SERVE_COMMITTER_EMAIL = "staging-serve@users.noreply.github.com"
SERVE_COMMITTER = f"{SERVE_COMMITTER_NAME} <{SERVE_COMMITTER_EMAIL}>"


def _commit_identity(cwd):
    """`-c` identity flags for the serve commit when none is configured."""
    ok, _ = _git("config", "user.email", cwd=cwd)
    if ok:
        return []
    return ["-c", f"user.name={SERVE_COMMITTER_NAME}",
            "-c", f"user.email={SERVE_COMMITTER_EMAIL}"]


def push_serve_branch(tree_dir, branch, cwd, base_sha, cname=STAGING_HOST):
    """Commit the prepared tree onto the serve branch and push.

    Append-only: an existing branch is checked out, cleared and rebuilt
    with a new commit on top, and the push is a plain fast-forward. The
    branch history is the serve log; nothing is ever force-pushed.

    After a successful branch push the served state is stamped with the
    `staging-<serve sha>` review tag (ledger row 103, operator
    instruction 2026-11-24). The tag is bookkeeping, never a gate: a
    failed tag push reports but does not fail the serve, because the
    serve landed.
    """
    if branch_exists(branch, cwd):
        ok, _ = _git("checkout", "-B", branch, f"origin/{branch}", cwd=cwd)
        if not ok:  # local-only branch (test world): no remote ref to -B onto
            ok, _ = _git("checkout", branch, cwd=cwd)
        if not ok:
            raise SystemExit(f"cannot check out the serve branch {branch}")
    else:
        ok, _ = _git("checkout", "--orphan", branch, cwd=cwd)
        if not ok:
            raise SystemExit(f"cannot create the orphan serve branch {branch}")
    _git("rm", "-rf", "--ignore-unmatch", ".", cwd=cwd)
    # `git rm` removes TRACKED files only. Untracked bytecode the serve
    # process itself created — tools/__pycache__ from the imports at startup
    # (cpython-314 on the Actions runner, row 136), or tests/__pycache__ and
    # tools/__pycache__ left by pytest in a local checkout — survives the rm,
    # and the `git add -A` below would sweep it into the serve commit (the
    # junk that reached staging-pages tonight). Sweep the checkout clean
    # before staging; only the prepared tree may enter the commit.
    ok, why = _git("clean", "-fdx", cwd=cwd)
    if not ok:
        raise SystemExit(
            f"cannot clear untracked files from the serve checkout: {why}")
    shutil.copytree(tree_dir, cwd, dirs_exist_ok=True)
    ok, _ = _git("add", "-A", cwd=cwd)
    if not ok:
        raise SystemExit("cannot stage the serve tree")
    when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ok, why = _git(
        *_commit_identity(cwd), "commit", "-m",
        f"Serve {base_sha[:12]} — {when}\n\n"
        f"Generated by tools/staging_serve.py from {base_sha}; "
        "staging-pages is a serve branch, do not edit by hand.",
        cwd=cwd)
    if not ok:
        raise SystemExit(f"cannot commit the serve tree: {why}")
    ok, sha = _git("rev-parse", "HEAD", cwd=cwd)
    if not ok:
        raise SystemExit("cannot read the serve commit")
    ok, why = _git("push", "origin", branch, cwd=cwd)
    if not ok:
        raise SystemExit(f"cannot push the serve branch {branch}: {why}")
    print("staging serve: " + tag_served_state(cwd, base_sha, cname=cname))
    return sha


# Ledger row 103 (operator instruction, 2026-11-24, verbatim: "Staging
# should get a tag for editorial review checkouts, but merges/changes
# should always deploy to it"). The tag names the same short sha the
# serve branch's subject names, so tag and branch agree on what was
# served; it points at the fork-main commit the serve was generated
# from, because that commit — source plus the built docs/ — is the
# reviewable tree an editorial reviewer wants to check out. Tags append
# for the life of the repo: a sha whose tag exists is a no-op, and a
# failed tag push never fails the serve run, whose outcome is the
# branch's, not the tag's.

TAG_PREFIX = "staging-"


def review_tag_name(base_sha):
    return f"{TAG_PREFIX}{base_sha[:12]}"


def _review_annotation(base_sha, cname, run_id):
    when = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"staging served {base_sha[:12]} on {cname}\n\n"
        f"served host: {cname}\n"
        f"serve run: {run_id}\n"
        f"at: {when}\n")


def tag_served_state(cwd, base_sha, cname=STAGING_HOST, run_id=None):
    """Stamp the served state with the review tag, failing soft.

    Returns a one-line report either way. Nothing here raises and
    nothing here can: the serve branch has already landed when this
    runs, so tag bookkeeping must never turn a good serve red.
    """
    run_id = run_id or os.environ.get("GITHUB_RUN_ID") or "local"
    name = review_tag_name(base_sha)
    # ls-remote exits 0 whether or not the ref matched, so existence is
    # read from its output, not its status code.
    ok, out = _git("ls-remote", "origin", f"refs/tags/{name}", cwd=cwd)
    if not (ok and out):  # no remote (test world): fall back to local ref
        ok, _ = _git("show-ref", "--verify", f"refs/tags/{name}", cwd=cwd)
    if ok:
        return f"review tag {name} already exists on the served sha (no-op)"
    ok, why = _git(
        *_commit_identity(cwd), "tag", "-a", name, base_sha,
        "-m", _review_annotation(base_sha, cname, run_id), cwd=cwd)
    if not ok:
        return (f"review tag not created, serve unaffected "
                f"(bookkeeping): {why}")
    ok, why = _git("push", "origin", f"refs/tags/{name}", cwd=cwd)
    if not ok:
        return (f"review tag {name} exists locally but origin refused "
                f"it, serve unaffected (bookkeeping): {why}")
    return (f"review tag {name} pushed, pointing at the fork-main "
            f"commit the serve was generated from")


def main():
    parser = argparse.ArgumentParser(
        description="Prepare (and optionally push) the staging serve branch.")
    parser.add_argument("--cname", default=STAGING_HOST,
                        help="hostname the serve branch claims")
    parser.add_argument("--src-docs", default=os.path.join(ROOT, "docs"),
                        help="the committed docs/ tree to serve")
    parser.add_argument("--branch", default=SERVE_BRANCH,
                        help="generated serve branch name")
    parser.add_argument("--push", action="store_true", default=False,
                        help="commit the tree onto the serve branch and "
                             "push (default: prepare and verify only)")
    args = parser.parse_args()

    require_fresh(release_check.fresh_tree_diffs(args.src_docs))
    dst = tempfile.mkdtemp(prefix="psp-serve-")
    try:
        base_sha = _git("rev-parse", "HEAD", cwd=ROOT)[1]
        pages = prepare_serve_tree(args.src_docs, dst, args.cname,
                                   base_sha=base_sha)
        if args.push:
            sha = push_serve_branch(dst, args.branch, ROOT, base_sha,
                                    cname=args.cname)
            print(f"staging serve: {pages} pages on {args.branch} "
                  f"({sha[:12]}) claiming {args.cname}, built from "
                  f"{base_sha[:12]}")
        else:
            print(f"staging serve: {pages} pages prepared in {dst} "
                  f"claiming {args.cname}, built from {base_sha[:12]} "
                  "(not pushed)")
    finally:
        shutil.rmtree(dst, ignore_errors=True)


if __name__ == "__main__":
    main()
