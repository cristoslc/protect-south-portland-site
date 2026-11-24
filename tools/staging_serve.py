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
  force push, so the branch's history is a readable serve log.

Usage:
  python3 tools/staging_serve.py            # prepare + verify, no push
  python3 tools/staging_serve.py --push     # the fork's CI path
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psp_public
import release_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAGING_HOST = "staging.protectsouthportland.org"  # ledger row 41
SERVE_BRANCH = "staging-pages"

# The staging variant of the crawl policy. docs/ ships the tracked
# Allow-all robots.txt that production serves; the serve branch rewrites
# it, exactly the way the row-42 staging leg always did.
STAGING_ROBOTS_TEXT = (
    "# Staging serve branch — not the production site.\n"
    "User-agent: *\n"
    "Disallow: /\n"
)

# Row 42's honest core, carried into the serve tree: search engines are
# told to stay out of the preview. Injected after <head> on every page.
NOINDEX_META = '<meta name="robots" content="noindex, nofollow">'


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


def prepare_serve_tree(src_docs, dst, cname):
    """Build the serve tree in dst from the committed docs/ tree.

    Copy (minus any CNAME file), scan the copy before injecting anything
    (the same order the publish staging leg used), then write the staging
    crawl protection, the noindex meta on every page, .nojekyll, and the
    CNAME that names the staging host. Returns the gated page count.
    """
    os.makedirs(dst, exist_ok=True)
    for entry in sorted(os.listdir(src_docs)):
        if entry == "CNAME":
            continue
        src = os.path.join(src_docs, entry)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, entry), dirs_exist_ok=True)
        else:
            shutil.copy2(src, os.path.join(dst, entry))
    open(os.path.join(dst, ".nojekyll"), "w").write("")
    psp_public.assert_clean(
        psp_public.scan_tree(dst), "staging serve tree (pre-injection)")
    open(os.path.join(dst, "robots.txt"), "w", encoding="utf-8").write(
        STAGING_ROBOTS_TEXT)
    headless = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(dst):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            text = open(path, encoding="utf-8").read()
            if "<head>" not in text:
                headless.append(os.path.relpath(path, dst))
                continue
            open(path, "w", encoding="utf-8").write(
                text.replace("<head>", "<head>\n" + NOINDEX_META, 1))
            count += 1
    if headless:
        raise SystemExit(
            "staging serve: page(s) carry no <head>, so the noindex meta "
            "cannot protect them, refusing: " + ", ".join(headless))
    open(os.path.join(dst, "CNAME"), "w", encoding="utf-8").write(cname + "\n")
    return count


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


def push_serve_branch(tree_dir, branch, cwd, base_sha):
    """Commit the prepared tree onto the serve branch and push.

    Append-only: an existing branch is checked out, cleared and rebuilt
    with a new commit on top, and the push is a plain fast-forward. The
    branch history is the serve log; nothing is ever force-pushed.
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
    return sha


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
        pages = prepare_serve_tree(args.src_docs, dst, args.cname)
        base_sha = _git("rev-parse", "HEAD", cwd=ROOT)[1]
        if args.push:
            sha = push_serve_branch(dst, args.branch, ROOT, base_sha)
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
