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
- writes the staging robots.txt (Disallow-all) and injects the row-42
  cookie gate after every page's <head>: noindex meta, the curtain
  stylesheet and the passphrase-gate script (ledger row 128, 2026-11-25 —
  the operator reversed the cutover ruling dec_63blvjzqob1t, corpus
  dl-20261124T154549-c606, per corpus dl-20261125T142900-d080). The
  injection point is THIS serve tree, never the page sources: no built
  page carries the gate and a production tree cannot inherit it, and the
  gate marker is a production-forbidden marker in psp_public, so a leaked
  serve tree fails any production leg's scan loud. The passphrase arrives
  at serve time from PSP_STAGING_PASSPHRASE (env, then the workspace
  .env) and a serve run without it refuses loud — only the passphrase's
  SHA-256 embeds in the gate script. Row 60's two fixes are carried: the
  curtain ships as a real <style> tag hidden from first paint, and the
  phrase field refocuses on window load because the homepage map iframe
  steals focus. The row-79 stamp stays retired — the branch's own commit
  names what it serves, which is the stamp's question answered
  structurally;
- writes the CNAME naming the staging host, the one file that makes this
  branch differ from main and the reason it exists;
- commits the tree onto staging-pages and pushes, appending — never a
  force push, so the branch's history is a readable serve log;
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
import hashlib
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

# The staging variant of the crawl policy. docs/ ships the tracked
# Allow-all robots.txt that production serves; the serve branch rewrites
# it, exactly the way the row-42 staging leg always did.
STAGING_ROBOTS_TEXT = (
    "# Staging serve branch — not the production site.\n"
    "User-agent: *\n"
    "Disallow: /\n"
)

# Row 42's crawl core, carried into the serve tree: search engines are
# told to stay out of the preview. The meta is the first line of the
# injected gate block below.
NOINDEX_META = '<meta name="robots" content="noindex, nofollow">'


def gate_head_block(passphrase):
    """The row-42 gate block for one serve run, keyed by the passphrase.

    Only the passphrase's SHA-256 embeds (row 42); the block itself is
    publish.py's battle-tested GATE_HEAD_BLOCK — one source for the gate the
    retired publish staging leg and this serve step both inject, carrying
    row 60's fixes (a real <style> tag hidden from first paint, and the
    window-load refocus that beats the homepage map iframe) and row 128's
    interplay rule (the row-127 staging bar stays visible above the locked
    curtain).
    """
    digest = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
    return publish.GATE_HEAD_BLOCK.replace("@HASH@", digest)


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


def prepare_serve_tree(src_docs, dst, cname, base_sha=None, passphrase=None):
    """Build the serve tree in dst from the committed docs/ tree.

    Copy (minus any CNAME file), scan the copy before injecting anything
    (the same order the publish staging leg used), then write the staging
    crawl protection and inject the row-42 cookie gate after every page's
    <head> (ledger row 128: the operator's reversal of the cutover ruling —
    the gate lives here, at the serve step, never in the page sources).
    Writes .nojekyll, the CNAME that names the staging host, and
    staging-manifest.json (the staging preview bar's served time and the
    fork sha the tree was built from; ledger row 127). The passphrase comes
    from the `passphrase` argument or, at serve time, PSP_STAGING_PASSPHRASE
    (env, then the workspace .env) — a serve without it refuses loud.
    Returns the gated page count.
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
    manifest = {"served": datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")}
    if base_sha:
        manifest["head"] = base_sha
    open(os.path.join(dst, "staging-manifest.json"), "w",
         encoding="utf-8").write(json.dumps(manifest) + "\n")
    psp_public.assert_clean(
        psp_public.scan_tree(dst), "staging serve tree (pre-injection)")
    open(os.path.join(dst, "robots.txt"), "w", encoding="utf-8").write(
        STAGING_ROBOTS_TEXT)
    if passphrase is None:
        try:
            passphrase = publish.staging_passphrase()
        except SystemExit as exc:
            raise SystemExit(f"staging serve: {exc}") from exc
    block = gate_head_block(passphrase)
    injected = (publish.injected_block_open(publish.GATE_MARKER)
                + "\n" + block + "\n"
                + publish.injected_block_close(publish.GATE_MARKER))
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
                text.replace("<head>", "<head>" + injected, 1))
            count += 1
    if headless:
        raise SystemExit(
            "staging serve: page(s) carry no <head>, so the crawl gate "
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
