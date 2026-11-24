# Release record — production returns to the 2026-10-18 build

Ruling: `dec_4ipo2y19ltxa`, option oct-18. Operator override, verbatim, dated 2026-11-24:
"override -- roll back with errors, then we'll fix just the minor errors".

**The release is a tag plus a pull request, and the operator approves and merges it.** No agent
publishes to production, creates the tag on the operator's behalf, or merges this request.

## What the release is

| item | value |
|---|---|
| source commit to tag | `ff39870` (the commit the 2026-10-18-1 gate report names) |
| staging mirror commit | `7930d62` |
| staging tree verified | yes, 18 of 18 pages, 2026-11-24 |
| gate report | `gate-reports/2026-11-24-6.json`, sha256 `67984f0d159bbc6a7f62d43dba70a6f9b78abb0ea45e764720b04f82a20127d3` |
| map source | tank-farms `c488631` (2026-10-15), the last source before the October build |
| staging URL | https://staging.protectsouthportland.org/ |

## Verification performed

The build of `ff39870` reproduces the 2026-10-18-1 page set exactly (18 of 18 names) and rebuilds
to identical hashes twice. Every page served by staging was fetched, the row-42 gate block was
removed with the exact bytes that tool injected, and the remainder hashed back to the report:

| page | sha256 | served |
|---|---|---|
| `404.html` | `ec13eaa94e13a60657bf09462811bd64a29dae4ad7fe743d731ff89c27e4f222` | match |
| `about.html` | `6c1e044bcf70f8de6aa46d5addd3c2c222b10aecd1fa8daf8c579f8ba89c3cf6` | match |
| `act-now.html` | `260841918412f2628e0ee6ea120e9800aa895f94af92abec0ad0b8ad0ce1cfdf` | match |
| `clear-skies.html` | `8d6ae1bb0b2d73a07087e9cdd0099acbbd2850c8f453db5bb3100e7943a1a83a` | match |
| `coastal-flooding.html` | `f65f582613964b63e8210fb760f6094f54f53e89871df5005f795e52697addb4` | match |
| `contact.html` | `e481ab4c2530b42440898dfbd5bc26edf2c45bacbfe2d266a4faf4d5e98b3b43` | match |
| `donate.html` | `7abf6649d544bb944517606eb0a6540160512e40da3fba9aba0d1e7b23e22641` | match |
| `fertilizer-ban.html` | `ed95677628f0c9251d61cd2f7a816a740bb020332115a851ab9b3954623f6bff` | match |
| `get-involved.html` | `63427be312e49aa1eb518cf1b885b9903002d771c96199a6ea02d06211c57d6e` | match |
| `index.html` | `982d3c1a7fc7860118d39e82286c46e857cb780b831c08d30c1753b06e278b32` | match |
| `newsletter.html` | `0031c2105321ca135d63a5567cef2136ac9775099585f7e2190d0ff4f86836e4` | match |
| `oil-tank-emissions.html` | `430a975043ed05393282d4f43d5ee6f555e38a95595d0f955f22946612899c67` | match |
| `our-campaigns.html` | `5db871ca674a64949e36a7dc42862e28674e910a326e9e3ace6aa230323e6633` | match |
| `past-work.html` | `ecc16858e58e42f8b1ba8a0ab11db1640fcf9d60d522ff0d8e9e6a1eadaab901` | match |
| `pesticides.html` | `921bfbc092cd9a4913ee492ecb15b603fef619dfe6ae577505037e618bf39fff` | match |
| `tank-farms.html` | `5a2d83f777f1000381273cf4b4f62f05e67f2f936ea472cde63a5e11eba1f398` | match |
| `vocs.html` | `08124f02f301a16ca22d67bc280cf7b11a65e0b62be2219d285c30097a96e86f` | match |
| `yard-south-proposal.html` | `9db5ab8a4bf4a306c4d43ac37b1ded1d034446ea02d1e3c947adaf21a99b7225` | match |

## The report's verdicts are transcribed, not new

`2026-10-18-1` carries no per-page hashes and no review class, because content addressing began on
2026-11-04. `2026-11-24-6` carries the same reviewer, rounds and outcomes transcribed from it, plus
freshly computed hashes, and its scope note says so. The operator overrode a fresh review cycle.

## Known-wrong facts this release publishes

1. P.O. Box 2154 on `contact.html`, `donate.html` and `get-involved.html` (address changed to 15 Cottage Road on 2026-11-23).
2. The October 27 workshop is still an invitation on the homepage and `act-now.html` (the workshop has passed).
3. The benzene claim corrected on 2026-11-24: "state standards" and "12 times" on `index.html`, `act-now.html`, `our-campaigns.html`, `tank-farms.html`; the corrected framing is Maine's ambient air guidelines and up to four and a half times the guideline.
4. `contact.html` says "Twitter" where the site has said X since 2026-11-23.

Correction to the brief rather than a repetition of it: this footer carries no "sign the petition"
line. Its stale item is the Get involved link, which still resolves on this build.

## Tag to cut

`release-2026-10-18` on `ff39870`, annotated, with the body naming the staging snapshot `7930d62`
and the gate report. The operator cuts it.
