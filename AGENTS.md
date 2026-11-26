# Protect South Portland static site — agent notes

Static HTML/CSS site for Protect South Portland, generated into `docs/` by `tools/build.py`. GitHub Actions on this repo only runs the test suite, a build smoke check, and the non-blocking scheduled staging audit (issues only — nothing in this repo's CI deploys). The public staging site is the org fork `Protect-South-Portland/protect-south-portland-staging`, serving `staging.protectsouthportland.org` from its generated `staging-pages` branch; production is the Pages mirror `cristoslc/protect-south-portland-published`, updated only through `tools/publish.py` under the deployment policy below (the full fork-model rewrite lands with the phase-3 cutover PR).

## Hard constraint (operator approval, 2026-11-21): the site is the doc's page set

`protect_south_portland_website_copy` (with operator-added pages named in-thread, e.g. Share your story) is the sanctioned surface list. A page not in the doc does not get built, a meeting-notes wishlist item is not page authority, and no agent-authored "curation" copy (entry rules, taxonomies, start-here lists) ships anywhere. The library/press/history pages built 2026-11-05/06 against this rule were stripped 2026-11-21. Read `AGENTS-RETRO-agent-invented-pages.md` before creating any page.

## Commands

- Build: `python3 tools/build.py`
- Test: `.venv/bin/python -m pytest tests/` (see Test command)

## Test command

Declared project test command: `.venv/bin/python -m pytest tests/` — the repo venv at `.venv` carries pytest; the system `python3` does not. CI (`pages.yml`) installs pytest on the runner and runs `python -m pytest tests/ -q`.

## Deployment policy — fork model (operator directive, 2026-11-24; production cutover GO 2026-11-25)

**Topology.** Production is this repo's `main` branch, served by GitHub Pages from `/docs`; `www.protectsouthportland.org` and the apex answer it. Staging is the org fork `Protect-South-Portland/protect-south-portland-staging`, serving `staging.protectsouthportland.org` from its generated `staging-pages` branch. The crawl protection (Disallow-all robots, per-page noindex), the row-42 passphrase gate and the staging bar live in the fork's serve step and NEVER ship to production; a gated or bar-stamped tree fails the scanner by name if it ever reaches a production leg. Public feedback intake is `Protect-South-Portland/staging-website-feedback`.

**All work happens on the fork.** Pushes to fork `main` update staging within one CI run (merges and changes always deploy; `staging-<serve sha>` review tags stamp served states and never gate). A release is a pull request from a frozen fork release branch into upstream `main`, squash-merged **by the operator**; the merge is the deploy. No agent merges a release PR, pushes to upstream `main`, or touches either domain's Pages settings outside the cutover runbook's own steps. After each release, merge upstream `main` into fork `main` (plain merge, never force) so the next PR diffs cleanly.

**The release gate is unchanged:** the full-class review ladder, a content-addressed gate report committed in the PR under `gate-reports/`, release-gate CI green (tests, freshness, scanner, report hashes), and the psp-changelog handoff completed before the operator merges. The fork model strengthens the verification chain: Pages serves the committed `/docs` files verbatim (`.nojekyll` means no build step), so the reviewed bytes are the served bytes.

**Cutover record (2026-11-25).** The production GO ("After 141, ship it") authorizes the jump-forward cut: production day one serves the current `main` — the tree staging has served all day — superseding the plan's October-alignment default (`dec_4ipo2y19ltxa`) for this cut by fresh word. `tools/publish.py`'s mirror-publish pipeline retires with the cut, but the MODULE survives as the shared helper library (build, scanner, gate reports, and the serve step's gate helpers all import it); the plan's delete-the-file step is amended accordingly. The one-time Pages enable and cname flip commands live in `docs/runbooks/psp-fork-model-cutover.md` (workspace `docs/`), phase 3. The published mirror `cristoslc/protect-south-portland-published` stays un-archived as the rollback PUT target through the observation window.

## Orchestrator role (operator directive, 2026-11-24)

All redwork MUST [RFC 2119] be done by child threads, or handed off to another orchestrator or a top-level thread. The orchestrator ONLY [RFC 2119] does bluework and oversight. The exception: the orchestrator is permitted to evaluate pull requests and merge the low-risk ones.

Redwork means any execution that changes bytes or state: builds, publishes, worktree surgery, ledger rows, script writing, file edits, dry runs. If a command would create, change or push anything, it belongs to a child thread.

Bluework means rulings, review, planning, briefs, PR evaluation and the low-risk merges the exception allows.

## Reports must match the tree (operator directive, 2026-11-24)

**After any dispatch or merge an agent MUST [RFC 2119] either drive that work to its next surface — review, merge, publish — in the same turn, or state plainly in the report that the work is waiting and on what.** A report MUST NOT [RFC 2119] imply motion the tree does not show. Before reporting work as running or done, verify the tree itself: the branch, the commit, the PR state, the worktree. Intent is not evidence; a dispatched child is not a running child, and a follow-up queued to a stopped session is not a resume.

The operator's correction, verbatim (2026-11-24):

> **The stall pattern is now three for three tonight** — the cards sat unreviewed, the newsletter sat unmerged, and the phantom resume reported motion the tree did not show. The standing correction I gave the lane is the only real fix: after any dispatch or merge, either drive the work to publish in the same turn or state plainly in the report that it is waiting and on what. A report that implies motion while the tree stands still is worse than no report.

The three failures on the night of 2026-11-24, one line each:

- The cards leg: PR #72 sat open with no reviewer dispatched while a report implied it was in review; it merged later as `c08eda4`.
- The newsletter leg: PR #74 sat open and unmerged until the orchestrator merged it as `85e63aa`.
- The phantom resume: a follow-up sent to a stopped session was reported as running in parallel, while the worktree stayed at `f1314d4` with no commits, no PR and no active child.

A report that implies motion while the tree stands still is worse than no report.

## GitHub voice for agent-authored content (operator directive, 2026-11-24)

**Every issue, pull request body, review comment, and commit message an agent writes on GitHub MUST [RFC 2119] follow the ai-output-humanizer patterns: plain first person, no sycophancy, no em dashes, no rule-of-three, no invented emphasis, no "great catch" openers, and no summary-then-restate shape.** The operator's directive, verbatim (2026-11-24):

> in issues and PRs, you should be following guidance for agent-generated content

The audience is the operator and future readers, so the register is the reports-must-match-the-tree one: what was done, verified by what, nothing implied.

Authorship is stated where it matters. An agent-authored comment or PR body does not imply that a human reviewed, approved, or read anything it does not name. When a PR body describes a review, it names the reviewer thread and the verdict's sha, the way the gate reports do. When a comment carries a ruling, it quotes the ruling verbatim with its decision id.

A comment longer than about ten lines is shaped — a one-line lead, facts as short bullets, the evidence link and hash at the end — because a wall of text hides its own verification.

Scope: this applies to every issue, PR body, review comment, and commit message an agent writes on the site repo and the workspace repos, forward from the ruling's date (2026-11-24). Existing comments are not retroactively rewritten. A comment whose content a future reader would misread as human-verified gets a correction reply, not an edit.

## Issue and board checks (operator directive, 2026-11-24)

**The orchestrating thread (L0) and the lane lieutenant (L1) are each responsible for the checks below, and neither relies on the child that builds the work to self-report them.** L0 is the orchestrator that dispatches a leg; L1 is the lane lieutenant that runs it. The child threads that do the building stay outside the check loop: their reports are inputs, never verification. The reports-must-match-the-tree section above started this division; this section names who owns which half of it.

The operator's directive, verbatim (2026-11-24):

> you (as L0) and @thread:thr_g57ekquphp (as L1) are responsible for these checks. capture that in the project's agents.md/spokes

**Three checks are carried here, each earned by a failure that was caught once:**

- **Tree against report.** L0 MUST [RFC 2119] verify every status claim by call on its 15-minute cycle: open PRs, mirror and fork shas, worktree writes, issue-thread states. L1 MUST [RFC 2119] verify its own tree before every report it sends. A claim the tree contradicts is corrected in the same turn, with the difference between a lost message and a missed instruction stated when it matters.
- **Issue work.** An agent picking up a board issue MUST [RFC 2119] self-assign it and post a pickup comment (working on the fix, what will ship, where) before its first commit. It re-checks the issue thread at first commit, before publish, and at close. A mid-work comment is answered in the thread, folded into the leg with attribution, or filed as its own issue; it is never silently dropped. A premature close is reopened the moment the miss is seen.
- **Comment shape.** A comment longer than about ten lines is shaped: a one-line lead, the facts as short bullets, the evidence link and hash at the end. A fix is edited in place rather than stacked as a second comment.

**Each check exists because it was caught failing once, and the history is carried with the rule.** The failures are the stale board claims, the premature close on issue #3, and the wall-of-text comment. They are named in `AGENTS-RETRO-agent-invented-pages.md` and in the incident record's tradition: named, dated, and carried, so the next reader knows these are earned rules, not decoration.

## Brand voice (operator directive, 2026-11-24)

**Site copy is forward-looking.** Every copy leg SHOULD [RFC 2119] talk about what this community is doing next, not relitigate what already happened. History appears only in the past tense where it earns its place, and the page moves to the ask quickly. Written on the operator's line, verbatim:

> and we probably need a Brand Voice adjustment to talk about that forward-looking aspect, approaching the work with joy, etc.

**Approach the work with joy.** Copy SHOULD [RFC 2119] frame invitations rather than alarms: the meeting is a gathering ("come, wear green"), the archive is a shared record being built, the action is neighbors acting together, not doom and not blame-forward framing. Frightening facts are stated plainly and factually when they must be (the benzene readings, the fenceline data), but the voice a reader hears is hopeful and concrete.

**The verbs are concrete and active.** Copy SHOULD [RFC 2119] ask in second person where natural ("you're invited", "wear green and come") and use active verbs: write, come, call, sign, share, wear green. Campaign-as-subject abstractions stand in for no reader's action.

**Scope: every copy leg on every built page, forward from today.** This is the register the Dec. 1 ask already writes in; the homepage lead ("We know more than ever… join us… write… attend… wear green") is the reference example. The copy document could not carry this section (the service account is read-only there), so this section and its pull request are the record until the doc is next updated by human hands; a future update to the copy document SHOULD [RFC 2119] mirror this section's four paragraphs.

**Voice alignment with the comms doc (2026-11-25).** The PSP Comms Team doc's Content Guidelines tab opens with the tone line "Respectful, trustworthy, collaborative, optimistic" — the same register the paragraphs above pin for site copy, so the two documents agree rather than compete. The comms doc's mobilization toolkits tell speakers to "remind the city council of our demands"; that wording is channel register, not a content conflict: a toolkit addresses internal mobilization, while the site extends a public invitation ("write", "attend", "wear green"). No site copy leg imports "demands" wording from comms drafts. The doc's accessibility guidance ("Use plain language, high contrast colors, and easy-to-read fonts") is already binding here through the suite's contrast floor and the typography pins; the visual-brand experiment's token changes (section above) were measured against those floors, not beside them.

## Design input discipline: annotations, not mockups (operator directive, 2026-11-25)

**Screenshots and sketches are annotations of intent, never pixel-exact specs.** Any image routed to a leg as design input — the operator's, a child's, a filer's — answers "what should exist" and "roughly where", and nothing more. Legs MUST NOT [RFC 2119] sample an annotation's colors, geometry, or proportions as design tokens; implementation builds in the site's real design system (existing tokens, spacing, the suite's contrast floor). Written on the operator's line, verbatim:

> these are just annotations, not high-fidelity mockups.

Where an annotation conflicts with the suite's contrast, accessibility, or layout rules, the rules win and the PR names the divergence.

## Visual-brand experiment (staging only, operator directive 2026-11-25)

**This is an experiment the operator can end by reverting tokens.** The directive, verbatim in substance: "Let's experiment with closer compliance. Update our visual and voice guides and try Lato on the site (with appropriately contrasting typeface for headlines), the highlight hue, and the accent hue. Staging only, don't push to prod." It lives in `site/styles.css` tokens and `site/assets/fonts/` plus the pins in `tests/test_site.py`; no page markup changed. It is staging-scoped: no production action of any kind belongs to this leg, and the normal staging cycle (branch, PR, merge to main, fork serve) is its entire delivery surface.

**Type.** Lato carries the body (400 and 700, self-hosted woff2 in `site/assets/fonts/`, the OFL license files in-tree beside the files; no third-party font request anywhere — the font CDN hosts are banned by name in `test_visual_brand_experiment_no_external_font_host_in_sheet_or_pages`). Lato is the comms doc's council-packet face. The headline face is this leg's pick: **Bitter**, a slab serif (700, same self-hosting rule). Why Bitter: the directive asked for an "appropriately contrasting typeface for headlines", and a slab serif contrasts with Lato's humanist sans on structure rather than size alone; it keeps the sturdy civic-print feel of the council packet Lato comes from; and Bitter was drawn for screen text sizes, so it survives the site's 18px-root scale. The fallback stacks keep Avenir Next/system-ui on the body and Georgia/serif on headlines, so a visitor who never fetches the woff2 reads the same layout.

**Highlight.** `--highlight: #255e7c` — the council packet's R37 G94 B124 — takes the link/highlight roles from `--teal-700`: 7.07:1 on white, measured (6.72:1 on `--mist`, 6.11:1 on `--teal-100`, 6.17:1 on `--cyan-soft`; the `--teal-700` it replaced measured 5.88:1 on white).

**Accent.** A red-kite red replaces the orange family sitewide. The comms doc's Visual Brand tab describes a red kite as connected to Bug Light and the tanks, with "Red = South Portland/Red Riots but also can signal an alert in the air" — intent, not a spec (see the design-input rule above); the tokens are this leg's recorded mapping: `--red-kite: #c93a2e` for the decorative reds (the 4px masthead rule, the dashed placeholder border), `--red-kite-dark: #a02b23` for every text-bearing fill and link (CTA fills, the alert strip, the action-strip links), mirroring the old `--orange-dark` pattern, and `--red-kite-darker: #87211b` as the hover step. Every former `--orange-*` consumer was retargeted deliberately and named in the leg's pull request. Where intent met the suite's floors, the floors won and the PR names it: the old orange hover on the action strip measured 3.48:1 on `--cyan-soft`, under AA, and its red replacement measures 8.10:1.

**The teal masthead family stays** as the doc's "Greens/Blues = environment" primary: the masthead and nav fills, h1/h2 and the h3-look headings keep their teal tokens; only the link/highlight role moved off `--teal-700`.

## Staging audit — non-blocking, automated (2026-10-15)

`tools/staging_audit.py` audits the staging mirror on a schedule and files one digest issue per run on this repo, labeled `staging-audit` + `accessibility` (create-if-absent). Schedule: weekday mornings ~13:15 UTC plus manual `workflow_dispatch`, via `.github/workflows/staging-audit.yml`. Per run it checks every public page for HTTP 200, runs Lighthouse accessibility (desktop) on all pages plus a mobile pass on `index.html`, re-checks the typography floor against the `styles.css` staging actually serves (root `112.5%` + body `1rem` — the same contract `test_typography_older_visitor_floor` pins on the source file), and diffs its findings against the previous run's digest, read from the machine JSON block inside the last `staging-audit` issue.

The UAT cycle's visual sweep is `tools/uat_snapshots.py` (per-page full snapshots at the five evidence widths into `tests/evidence/uat-snapshots/`; gate-aware via the shared passphrase; manifest.json is the capture-of-record) and the judge's reading protocol — the layout hermeneutic — lives at `../docs/runbooks/psp-visual-uat.md`.

**Non-blocking contract:** a site-shaped problem (404, Lighthouse failure, floor miss) records a finding and still exits 0 — the audit must never block a deploy pipeline through its own exit code. It exits 1 only when the environment is broken (staging unreachable, Lighthouse crash, gh failure), and those failures are loud. Local ad-hoc pass: `python3 tools/staging_audit.py --base-url <url> --skip-issue` (stdlib only; Lighthouse arrives via npx). Since row 42 the audit passes through the staging cookie gate: it reads the passphrase like publish does and attaches the byte-compatible `psp_staging` cookie to every fetch and Lighthouse run (missing passphrase is loud only when the target is the default staging URL). The a11y contract this audit guards lives in `../psp/brand-guides/WCAG_COMPLIANCE.md` (verified contrast-pair table, typography floor, known deviations).

One operational fact from the first run day (2026-10-15): an audit racing a Pages rebuild can read a stale serve (the digest's typography findings then flag the OLD stylesheet). The deltas self-heal — the next run records the stale findings as resolved — so a run right after a publish should be read together with whatever follows it.

## Hard constraints (tests enforce; never bypass)

1. No links to the tank-farms research surfaces anywhere public: `report.html`, `factcheck.html`, `data.html`, `github.com/cristoslc/south-portland-tank-farms`, or their nav labels ("Research report", "Fact-check log", "Data files", "GitHub repo"). The map is self-hosted: index.html and tank-farms.html iframe the RELATIVE `map/embed.html` copy built into this repo's `docs/` (constraint text revised 2026-10-13 by orchestrator — the absolute github.io embed URL is superseded; the publish scanner also bans that host from the public tree).
2. No mention of the October 15 community assembly REVERSED 2026-10-15 by row 33 (Mindy-sanctioned meeting copy, operator publish-today directive; the meeting is tonight): the scanner's event-marker list is retired and the Action-Oriented meeting bullet ships with the flyer link. The original ban's shape is documented in the psp_public.py comment.
3. Text copied verbatim from PSP-authored pages is fine. Photography and graphics from the live Wix site ARE copied locally into `site/assets/photos/` (operator directive, 2026-10-13) and served from this repo; never hotlink `static.wixstatic.com`. Keep press-photo credits (Portland Press Herald photographers) in captions.
4. Change requests come from the ledger: `website-change-requests.md` in the PSP project workspace (this repo implements the open rows; row 4 and row 9 are constraints, not content).
5. Text inside `{{...}}` in the campaign copy documents is stage guidance addressed to the agent, never copy: obey it (layout direction, verify-before-publishing notes) and ship neither the braces nor the words inside them (operator ruling, 2026-11-24), because dropping only the braces is how an agent instruction reaches a reader as campaign voice. The documents are read through the `psp-gdrive` skill, which carries the same rule.

## Public website release gate (operator directive, 2026-10-13 — applies before ANY publish or republish)

1. **Scope:** every page whose copy changed (on the first run: all pages). A page is not publishable until it passes a full humanizer + style review.
2. **Reviewer:** the review round runs on a GLM-5.3-class model or higher, and flash variants do NOT qualify (operator clarification 2026-10-13): use `ollama-cloud/glm-5.3` (full GLM-5.3) or anything above it in the model ladder. A model below that class may implement revisions, but never performs the review verdict. Verbatim material copied from the historic Wix site is NOT exempt — it is legacy campaign copy and needs the review most.
3. **Rounds:** revise and re-review up to 3 rounds against the humanizer + style findings. Any page that still fails after 3 rounds is NOT published — escalate to the operator for a rewrite instead.
4. **Draft-artifact scan (part of every review):** no internal-draft language may reach the public surface. Known example (found live on `past-work.html` 2026-10-13): the header `THE #1 GOAL AS NOW WRITTEN IN THE MOST RECENT DRAFT:` — a working-draft label that must never be published. Scan for that pattern class: "as now written", "most recent draft", TODO/FIXME labels, template placeholders, anything that reads like a note to self rather than public copy.
5. **Recording the pass:** note per-page review outcome (round count, pass/fail) in the change log/commit message when publishing through the mirror pipeline.
6. **Content-addressed report, full-class reviewer (2026-11-04):** each page entry carries the `sha256` of the built `docs/<page>.html` as reviewed, and the report states `"review_class": "full"`. The publisher refuses a page whose current file hash differs from the reviewed one, refuses an entry with no hash (legacy reports do not publish; a missing hash cannot prove what was reviewed), and refuses a missing class or a `review_model` carrying a flash marker. A verdict therefore travels with the content it reviewed: an unchanged page legitimately keeps an older verdict, an edited page is refused by name. Write reports with `tools/gate_report.py`, which stamps the hashes and validates the class.
7. **The verdict names the commit it judged (2026-11-24):** a review verdict records the full sha of the head it reviewed, and if that head moves the verdict is void and the review runs again on the new head, so a merge is never made on a verdict for different bytes.
8. **A production release is a tagged pull request the operator merges (2026-11-24, RFC 2119):** the release MUST be tagged from the verified staging tree, MUST open as a pull request, and MUST be approved and merged by the operator. An agent MUST NOT publish to production or merge that pull request. See the deployment policy above; any publish that skips this is an incident.

## The retired mirror pipeline (record only)

The `publish.py` mirror pipeline (force-pushed single-commit publishes to `cristoslc/protect-south-portland-published`, the staging mirror leg, the Pages verification flags) is retired as of the 2026-11-25 cutover. The module itself remains in the tree because `tools/build.py`, `tools/psp_public.py`, `tools/gate_report.py`, `tools/staging_serve.py`, `tools/staging_audit.py`, `tools/payload_sweep.py` and `tools/uat_snapshots.py` import its helpers; nothing may invoke its publish pipeline any more, and its one-time Pages API commands live in the cutover runbook. The old tool's full behavior is in git history if a verification trick is ever needed again.

## Editing flow

Edit `site/pages/*.html` (each file carries its title/description in the first-line `<!-- meta: ... -->` comment), run `python3 tools/build.py`, run the tests, commit, push to `origin/main` (CI runs the tests and a build smoke check only — it deploys nothing), then follow the deployment policy above before anything reaches a public mirror. After any layout/nav change, run the multi-viewport pass (`tools/visual_check.sh`) before reporting — 412/768/1440 screenshots of homepage + campaign page (top band + footer region); the harness defaults to a local http server over fresh `docs/` (explicit baseUrl overrides), waits for network idle, and runs validity guards (200 preflight, differential checksums, non-uniform crops), so a blank capture can never exit 0. Old merged pages (`oil-tank-emissions.html`, `vocs.html`) live on as redirect stubs written by `tools/build.py` REDIRECTS.

## Operator edits in the shared checkout (standing instruction, 2026-11-24)

The operator edits pages by hand in the root checkout, in their own words: "I will continue also making edits to pages directly in /Users/cristos/Documents/projects/protect-south-portland/protect-south-portland-site/site/pages". An agent MUST NOT [RFC 2119] discard, stash, revert, `git clean`, or otherwise tidy away uncommitted changes in that checkout. A dirty root does not mean a mistake was made; it most likely means the operator is mid-edit, and their bytes are authoritative until they are captured. This outranks ordinary preflight hygiene. It does not weaken the read-only-root rule in `docs/incidents/2026-11-24-stale-rebase-shared-checkout.md`: an agent still MUST NOT write to the root checkout. That rule says where an agent's own edits go, this one says what an agent must never destroy.

When the operator says an edit is ready, or asks for a check, the edit is captured exactly as it stands:

1. Take the diff verbatim. Nothing is rewritten, reflowed, or adjusted to suit a test.
2. Commit it on a branch off `main`, with a message naming it the operator's manual edit.
3. Rebuild `docs/` in the same change.
4. Run the suite and the scanner.
5. Return the root checkout to clean by committing their bytes, never by discarding them.

If anything is red, stop and report rather than adjusting their copy. The gate report records that page as `rounds: 0`, operator-authored, with no review round and that fact stated in the scope note, the way `2026-11-24-9` did.

If a leg in flight holds the page the operator is editing, either capture their edit first and rebase the leg, or hold the capture, whichever loses less work, and say which order was chosen in the pull request so the order is on the record.

The changelog entry for such a page says the change was made by hand, not by an agent, so the digest never attributes the operator's words to an automated pass.