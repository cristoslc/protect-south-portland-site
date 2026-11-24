---
name: psp-changelog
description: "Use for Protect South Portland site releases. Covers the staging and production publish ladder for the Protect South Portland static site: the gate report, the reader-facing changelog section in psp-wiki, the changelog check, the handoff reference the publisher demands, and the capture set that follows a live staging build. Also use when asked to write or amend a section of the site changelog."
---

# Protect South Portland site releases: gate, changelog, handoff

This skill is the release sequence for the Protect South Portland static site. It exists because the publisher refuses a leg without a changelog handoff reference, and because a leg run out of order either reviews bytes that moved or ships a digest that disagrees with the site.

## Format authority

The changelog format lives in `psp-wiki/docs/changelog/CONVENTION.md`. Read that file before writing. It is the authority on section shape, status lines, bullet style, and what belongs in `EVIDENCE.md` instead of the digest. Do not restate or paraphrase the conventions here, and do not invent a second changelog.

## The ladder, in order

1. **Land the change on `main` through a pull request.** A merge is not a deploy: `.github/workflows/pages.yml` runs tests and a build smoke check with `contents: read` and publishes nothing. Nothing is reader-visible until step 6.
2. **Build and test on `main`.** `python3 tools/build.py`, then `.venv/bin/python -m pytest tests/ -q`.
3. **Write the ledger row first** in `south-portland-tank-farms/website-change-requests.md`. The ledger is the system of record; the changelog is the digest, and the two must not disagree.
4. **Run the release gate.** A page is not publishable until a full-class review passes it. The reviewer is GLM-5.3 class or above (`cove/text:ultra-heavy`), never a flash variant, and the review covers every page whose built bytes changed since the last published tree. Stamp the report with the repo tool:
   `python3 tools/gate_report.py --date <YYYY-MM-DD-n> --review-model "<reviewer>" --review-class full --verdicts <verdicts.json> --scope-note "<what the review covered and which commit it saw>" --out ../gate-reports/<date>.json`
   The tool hashes each built page. The publisher later refuses any page whose file hash differs from the reviewed one, and refuses a report with no hash or a flash reviewer.
5. **Write the changelog section in psp-wiki.** Newest first, one dated section per change day, a status line as its first content line. A section already open for the day gets extended, not duplicated. Commit it in `psp-wiki` and run `python3 tools/check_changelog.py` there. It must report zero findings.
6. **Publish the staging leg.** The bare command targets the staging mirror and keeps its custom domain:
   `python3 tools/publish.py --gate-report ../gate-reports/<date>.json --changelog-handoff "psp-wiki <sha> docs/changelog/CHANGELOG.md, section <YYYY-MM-DD>"`
   The handoff flag carries a reference to what was recorded, not a live person or thread. Production is reachable only with `--repo cristoslc/protect-south-portland-published`, and only on the operator's explicit word in the thread that asked. A staging-lane thread never runs that.
7. **Capture the changed pages on staging once that build is live**, and record the captures in `EVIDENCE.md`. The changelog section describes what a visitor sees; the evidence file carries the shas, report paths and capture refs.
8. **Flip the status line on release day.** The production lane changes `Status: staged, not yet published` to `Status: live since <date> (production <sha>)`. One line, not a rewrite. A section that was amended after a rejected publish says what actually happened.

## Hard rules that the tooling enforces, so do not try to route around them

- `tools/publish.py` refuses a run with neither `--changelog-handoff` nor `--changelog-waiver`. The waiver is worse than the handoff: it must name what was not captured and why, and the same text has to appear in the publish commit body and the ledger row. Use it only when the digest genuinely cannot describe the change.
- A gate report whose per-page hash does not match the current built page refuses by name. An edited page needs a re-review, not a re-run of the publisher.
- The staging-tree marker (`staging-gate`, a `Disallow` robots file, the per-page `noindex`) must never reach a production leg. The scanner fails a production push that carries it.
- A page absent from the gate report blocks the publish. Adding a page means reviewing it.

## Reporting the result

The leg is done when three things are true: the publish finished and printed the Pages settings it saw, the served staging pages carry the change, and the changelog commit and the gate report are named in the thread. Say which commit is on staging and which is on production, because those two are usually different.
