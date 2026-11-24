# Header contrast fix, 2026-11-23

Evidence for the branch `fix/header-cta-contrast`: the Act now pill in the site header rendered below WCAG 2.2 AA at both breakpoints, and the fix keeps one passing pair at every width.

## Contract

The pill's label is 16.2px at weight 800 (0.9rem against the 112.5% root scale), which is under the 18.66px/700 large-text threshold. Normal text therefore needs 4.5:1, not 3:1.

## What was measured

`measure.js` drives headless Chrome through the local browser automation session. At 412 (menu closed then open), 768 (closed then open) and 1440 it reads the pill's computed `color` and `background-color`, composites the real backdrop by walking ancestors for non-transparent fills, and computes the WCAG contrast ratio. It also records the MENU label pair, so the pass on the rest of the band is on the record rather than assumed.

Placeholders in `measure.js` are substituted before a run: `__BASE__` is the local static server root over the freshly built `docs/`, and `__OUT__` is the directory the screenshots are written to. The hover pass used the same script with a mouse move onto the pill.

## Before

| Viewport | State | Label | Fill | Ratio |
| --- | --- | --- | --- | --- |
| 412 | menu open | #b8401a | #de5021 | 1.39:1 FAIL |
| 768 | menu open | #b8401a | #de5021 | 1.39:1 FAIL |
| 1440 | desktop row | #ffffff | #de5021 | 3.98:1 FAIL |
| 412 | menu open, hover | #ffffff | #b8401a | 5.55:1 |
| 1440 | desktop row, hover | #ffffff | #de5021 | 3.98:1 FAIL |
| all | MENU label | #ffffff | #1d3e40 | 11.57:1 |

`measurements-before.json` carries the raw reads. The phone failure came from the 1120px block repainting only the label dark orange while the fill stayed orange; the desktop failure and the desktop hover came from white on `--orange`.

## After

| Viewport | State | Label | Fill | Ratio |
| --- | --- | --- | --- | --- |
| 412 | menu closed and open | #ffffff | #b8401a | 5.55:1 PASS |
| 768 | menu closed and open | #ffffff | #b8401a | 5.55:1 PASS |
| 1440 | desktop row | #ffffff | #b8401a | 5.55:1 PASS |
| 412 | menu open, hover | #ffffff | #9c3615 | 7.11:1 PASS |
| 1440 | desktop row, hover | #ffffff | #9c3615 | 7.11:1 PASS |
| all | MENU label | #ffffff | #1d3e40 | 11.57:1 |

`measurements-after.json` carries the raw reads. The fill is the same `--orange-dark` that `.btn--cta` already uses, so the banner button and the header pill now share one passing pair.

## Captures

- `before/` — 412 closed, 412 open, 768 closed, 768 open, 1440, all taken against the pre-fix build.
- `after/` — the same five states against the fixed build.
- `after/visual-check/` — the guarded crops from `tools/visual_check.sh` (top band and footer region at 412, 768, 1024, 1100, 1440). The run reported 50 width/page geometric checks clean and all 20 crops above the blank-capture floor.

The open mobile menu is captured by `measure.js`, because `tools/visual_check.sh` only renders the closed state.
