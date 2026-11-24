#!/usr/bin/env python3
"""Write a content-addressed release-gate report (2026-11-04 hardening).

The publisher refuses a report whose page hashes do not match the source
files, and refuses a report that does not state a full-class reviewer. This
tool makes producing such a report the easy path: it takes the reviewer's
verdicts, stamps each page's built sha256 (docs/<page>.html, the content the
mirror ships), and validates exactly what publish.py will validate.

Usage:
  python3 tools/gate_report.py \
      --date 2026-11-04-1 \
      --review-model synthetic/hf:zai-org/GLM-5.3 \
      --review-class full \
      --verdicts /tmp/verdicts.json \
      --scope-note "Row 57: ... which commit the review saw ..." \
      --out ../gate-reports/2026-11-04-1.json

The verdicts file is a JSON object of page name -> {"rounds": N,
"outcome": "pass"}. Every file in site/pages/ must be present. Entries for
generated pages outside site/pages/ (the redirect stubs) are carried through
without a hash; the publisher ignores them.

PENDING VERDICTS (ledger row 93, 2026-11-24). The operator's policy publishes
to staging without waiting for review while review still gates production. A
page whose verdict is still in flight says so: {"rounds": 0, "outcome":
"pending"}. The writer stamps it through unchanged — it never upgrades pending
to pass — and the publisher accepts it on a staging leg only, refusing it by
name on every other target. A pending verdict that claims a round count
contradicts itself and is refused rather than coerced to 0.

AMENDING A LANDED VERDICT (ledger row 93). When the reviewer's verdict arrives
for a page that published as pending, replace the entry and record that it was
replaced:

  python3 tools/gate_report.py --amend ../gate-reports/<date>.json \
      --page act-now.html --verdict '{"rounds": 1, "outcome": "pass"}'

The amendment appends to the report's "amendments" list (page, date, old
outcome and rounds, new outcome and rounds, the sha256 both sides agree on).
It refuses, loudly and by page name: a page the report does not carry (it never
inserts an entry), a page with no content address, a verdict shape the gate
cannot use, an amendment that changes nothing, and a page whose stored sha256
no longer matches the built docs/<page>.html — amending a verdict onto changed
bytes is the exact failure content addressing exists to prevent. A refused
amendment leaves the report untouched, and nothing calls this automatically.

Refuses to overwrite an existing report unless --force is passed: gate
reports are evidence, not scratch files.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import publish

# The outcomes a written verdict may carry. "pending" is a marked in-flight
# state, not a verdict: it means no reviewer has ruled on the page yet, and it
# is only ever usable on a staging leg (publish.load_gate_report decides that
# from the leg's target).
WRITABLE_OUTCOMES = ("pass", publish.PENDING_OUTCOME)
# An amendment may also record a verdict that did not pass. Such an entry is
# refused by every leg, which is the honest outcome: a failed page does not
# publish, and the report says so instead of hiding it.
AMENDABLE_OUTCOMES = ("pass", publish.PENDING_OUTCOME, "fail")


def source_pages():
    pages_dir = os.path.join(publish.ROOT, "site", "pages")
    return sorted(n for n in os.listdir(pages_dir) if n.endswith(".html"))


def normalise_outcome(value):
    return str(value or "").strip().lower()


def check_verdict(page, entry, allowed=WRITABLE_OUTCOMES):
    """(outcome, rounds, problem) for one verdict entry; problem None if usable.

    Pending is the one outcome whose round count is fixed: a page with no
    verdict yet has no round count, so pending carries 0 and a pending verdict
    that claims rounds is refused rather than quietly coerced, because the two
    statements contradict each other.
    """
    if not isinstance(entry, dict):
        return None, None, f"{page}: verdict must be a JSON object of rounds and outcome"
    outcome = normalise_outcome(entry.get("outcome"))
    if outcome not in allowed:
        return None, None, (
            f"{page}: outcome {outcome!r} — the gate accepts "
            f"{', '.join(allowed)}")
    if outcome == publish.PENDING_OUTCOME:
        rounds = entry.get("rounds", publish.PENDING_ROUNDS)
        if rounds != publish.PENDING_ROUNDS:
            return None, None, (
                f"{page}: outcome 'pending' with rounds {rounds!r} — a page "
                f"with no reviewer verdict yet has no round count, so the "
                f"entry must say rounds 0; pending is never given a round "
                f"count it did not earn")
        return outcome, publish.PENDING_ROUNDS, None
    rounds = entry.get("rounds")
    if not isinstance(rounds, int) or not 0 <= rounds <= 3:
        return None, None, f"{page}: rounds {rounds!r} outside 0-3"
    return outcome, rounds, None


def amend_gate_report(path, page, verdict, today=None):
    """Replace one page's entry with a landed verdict, and record the change.

    The one case this serves (ledger row 93): a page published to staging as
    pending because staging does not wait for review, and the reviewer's
    verdict has now arrived. The entry is replaced with what the reviewer
    actually said, and the report gains an amendment record naming the page,
    the date, the outcome and rounds before and after, and the sha256 both
    sides agree on — so the report says what happened to it rather than looking
    as if it always carried the real verdict.

    Refusals, all loud and by page name: a page the report does not carry (an
    amendment replaces an entry, it never inserts one), a page outside
    site/pages/ (nothing content-addressed to amend), an entry with no sha256,
    a verdict the gate cannot use, a verdict that names different bytes, an
    amendment that changes nothing, and above all a page whose stored sha256 no
    longer matches the built docs/<page>.html. A refused amendment leaves the
    report byte-identical. Nothing calls this automatically.

    Returns the amended report dict.
    """
    path = os.path.abspath(path)
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        raise SystemExit(f"{path}: cannot read the gate report — {exc}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: is not JSON — {exc}")
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: expected a JSON object report")
    pages = raw.get("pages")
    if not isinstance(pages, dict) or not pages:
        raise SystemExit(f"{path}: carries no per-page entries to amend")
    if page not in pages:
        raise SystemExit(
            f"{page}: not in {path} — an amendment replaces an entry, it "
            f"never adds one; a page the report never carried has nothing to "
            f"amend")
    if page not in source_pages():
        raise SystemExit(
            f"{page}: not a page under site/pages/ — only a page with a "
            f"content address can be amended")
    entry = pages[page]
    stored = str(entry.get("sha256") or "").strip().lower() if isinstance(entry, dict) else ""
    if not stored:
        raise SystemExit(
            f"{page}: entry carries no sha256 — a verdict cannot be amended "
            f"onto content nobody pinned; re-review the page and write a new "
            f"report")
    current = publish.page_sha256(page)
    if isinstance(verdict, dict):
        named = str(verdict.get("sha256") or "").strip().lower()
        if named and named != current:
            raise SystemExit(
                f"{page}: the verdict names sha256 {named}, the built page is "
                f"{current} — the reviewer saw different bytes; re-review the "
                f"page")
    if stored != current:
        raise SystemExit(
            f"{page}: sha256 mismatch — the report pins {stored}, the built "
            f"page is {current}; the page changed after the verdict, so it "
            f"cannot be amended onto these bytes (re-review the page)")
    amendments = raw.get("amendments", [])
    if not isinstance(amendments, list):
        raise SystemExit(
            f"{path}: \"amendments\" is not a list — refusing to guess")
    outcome, rounds, problem = check_verdict(page, verdict, AMENDABLE_OUTCOMES)
    if problem:
        raise SystemExit(f"{path}: cannot amend: {problem}")
    old_outcome = normalise_outcome(entry.get("outcome"))
    old_rounds = entry.get("rounds")
    if old_outcome == outcome and old_rounds == rounds:
        raise SystemExit(
            f"{page}: already carries outcome {outcome!r} at rounds "
            f"{rounds!r} — an amendment that changes nothing is not recorded")
    pages[page] = {"rounds": rounds, "outcome": outcome, "sha256": current}
    amendments.append({
        "page": page,
        "date": today or datetime.date.today().isoformat(),
        "old_outcome": old_outcome,
        "old_rounds": old_rounds,
        "new_outcome": outcome,
        "new_rounds": rounds,
        "sha256": current,
    })
    raw["amendments"] = amendments
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2)
        fh.write("\n")
    return raw


def build_parser():
    parser = argparse.ArgumentParser(
        description="Write (or amend) a content-addressed release-gate report.")
    parser.add_argument("--date", default=None,
                        help="report label, normally YYYY-MM-DD-<n>")
    parser.add_argument("--review-model", default=None,
                        help="model that issued the verdicts")
    parser.add_argument("--review-class", default=None,
                        help='reviewer class, "full" for the release gate')
    parser.add_argument("--verdicts", default=None,
                        help="JSON: {page: {rounds, outcome}} from the reviewer")
    parser.add_argument("--scope-note", default=None,
                        help="what the review covered and which commit it saw; "
                             "this is the provenance record, not decoration")
    parser.add_argument("--out", default=None,
                        help="report path, normally ../gate-reports/<date>.json")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing report file")
    parser.add_argument("--amend", default=None, metavar="REPORT",
                        help="replace one page's verdict in an existing report "
                             "and record the amendment (needs --page and "
                             "--verdict); a page whose stored sha256 no longer "
                             "matches the built page is refused")
    parser.add_argument("--page", default=None,
                        help="the page to amend, e.g. act-now.html (with --amend)")
    parser.add_argument("--verdict", default=None,
                        help="the landed verdict as JSON, e.g. "
                             "'{\"rounds\": 1, \"outcome\": \"pass\"}' (with --amend)")
    return parser


def amend_main(args):
    if not args.page or not args.verdict:
        raise SystemExit(
            "--amend needs --page <page.html> and --verdict '<json>'")
    try:
        verdict = json.loads(args.verdict)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--verdict is not JSON — {exc}")
    report = amend_gate_report(args.amend, args.page, verdict)
    record = report["amendments"][-1]
    count = len(report["amendments"])
    print(f"amended {args.amend}: {record['page']} "
          f"{record['old_outcome']} r{record['old_rounds']} -> "
          f"{record['new_outcome']} r{record['new_rounds']} "
          f"({count} amendment{'' if count == 1 else 's'} recorded)")


def main():
    args = build_parser().parse_args()
    if args.amend:
        amend_main(args)
        return

    missing = [flag for flag, value in (
        ("--date", args.date),
        ("--review-model", args.review_model),
        ("--review-class", args.review_class),
        ("--verdicts", args.verdicts),
        ("--scope-note", args.scope_note),
        ("--out", args.out)) if not value]
    if missing:
        raise SystemExit("writing a report needs " + ", ".join(missing))
    if os.path.exists(args.out) and not args.force:
        raise SystemExit(
            f"{args.out}: already exists — gate reports are evidence; pass "
            "--force only to replace a report you wrote yourself")

    review_class = args.review_class.strip().lower()
    if review_class not in publish.REVIEW_CLASSES:
        raise SystemExit(
            f"--review-class {args.review_class!r} is not full — the release "
            f"gate accepts only {', '.join(publish.REVIEW_CLASSES)} "
            "(AGENTS.md \"Public website release gate\")")
    for marker in publish.FLASH_MARKERS:
        if marker in args.review_model.casefold():
            raise SystemExit(
                f"--review-model {args.review_model!r} carries the flash marker "
                f"{marker!r} — flash variants never issue the verdict")

    verdicts = json.load(open(args.verdicts, encoding="utf-8"))
    if not isinstance(verdicts, dict) or not verdicts:
        raise SystemExit(f"{args.verdicts}: expected a JSON object of page -> verdict")

    pages = source_pages()
    problems = []
    for page in pages:
        entry = verdicts.get(page)
        if not entry:
            problems.append(f"{page}: NOT REVIEWED — absent from the verdicts")
            continue
        _, _, problem = check_verdict(page, entry)
        if problem:
            problems.append(problem)
    if problems:
        raise SystemExit(
            "cannot write the report:\n  " + "\n  ".join(problems))

    report_pages = {}
    for name in sorted(verdicts):
        outcome, rounds, problem = check_verdict(name, verdicts[name])
        if problem:
            raise SystemExit(f"cannot write the report:\n  {problem}")
        stamped = {"rounds": rounds, "outcome": outcome}
        if name in pages:
            stamped["sha256"] = publish.page_sha256(name)
        report_pages[name] = stamped

    report = {
        "date": args.date,
        "review_model": args.review_model,
        "review_class": review_class,
        "pages": report_pages,
        "scope_note": args.scope_note,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    hashed = sum(1 for entry in report_pages.values() if "sha256" in entry)
    pending = sum(1 for entry in report_pages.values()
                  if entry["outcome"] == publish.PENDING_OUTCOME)
    pending_note = (
        f", {pending} pending (staging leg only — production will refuse "
        f"them until a verdict lands and the entry is amended)" if pending else "")
    print(f"wrote {args.out}: {hashed}/{len(pages)} source pages hashed, "
          f"{len(report_pages)} entries, model {args.review_model} "
          f"({review_class}){pending_note}")


if __name__ == "__main__":
    main()
