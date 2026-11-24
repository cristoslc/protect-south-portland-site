// Heading-margin captures + acceptance-gap measurements (ledger row 104).
// BASE = server root over a built docs/ tree. OUT = evidence subfolder
// (before/ or after/). Writes full-page PNGs for act-now, index and
// tank-farms at 412 / 768 / 1440, and measures the acceptance case on
// act-now.html: the h2 "Writing a letter to the editor" against the
// legislator contact list above it and the Sentry h3 below it.
const BASE = 'http://127.0.0.1:8138/';
const OUT = '/Users/cristos/Documents/projects/protect-south-portland/.worktrees/heading-margin-inversion/tests/evidence/heading-margins-2026-11-24/after';
const PAGES = ['act-now.html', 'index.html', 'tank-farms.html'];
const WIDTHS = [412, 768, 1440];
const p = await browser.getPage('main');

function gaps() {
  const h2 = [...document.querySelectorAll('h2')]
    .find((h) => h.textContent.trim() === 'Writing a letter to the editor');
  if (!h2) return null;
  const list = h2.previousElementSibling;   // ul.contact-list, the legislators
  const sentry = h2.nextElementSibling;     // h3 "Sentry"
  const a = h2.getBoundingClientRect().top - list.getBoundingClientRect().bottom;
  const b = sentry.getBoundingClientRect().top - h2.getBoundingClientRect().bottom;
  const r = (n) => Math.round(n * 10) / 10;
  return {
    abovePx: r(a),   // legislator contact rows -> heading
    belowPx: r(b),   // heading -> the Sentry block it introduces
    listTag: list.tagName + '.' + list.className,
    sentryTag: sentry.tagName + ' ' + sentry.textContent.trim(),
  };
}

const results = {};
for (const w of WIDTHS) {
  await p.setViewport({ width: w, height: 900 });
  for (const page of PAGES) {
    await p.goto(BASE + page + '?w=' + w, { waitUntil: 'load' });
    await new Promise((r) => setTimeout(r, 600));
    await p.screenshot({ path: `${OUT}/${page.replace('.html', '')}-${w}.png`, fullPage: true });
    if (page === 'act-now.html') results[`${w}`] = await p.evaluate(gaps);
  }
}
return results;
// computed-style appendix for the after tree (root scale + winning margins)
const p2 = await browser.getPage('main');
await p2.setViewport({ width: 1440, height: 900 });
await p2.goto('http://127.0.0.1:8138/act-now.html?probe=1', { waitUntil: 'load' });
await new Promise((r) => setTimeout(r, 400));
return { rootFontPx: await p2.evaluate(() => getComputedStyle(document.documentElement).fontSize), margins: await p2.evaluate(() => {
  const h2 = [...document.querySelectorAll('h2')].find((h) => h.textContent.trim() === 'Writing a letter to the editor');
  const h3 = h2.nextElementSibling;
  const s2 = getComputedStyle(h2), s3 = getComputedStyle(h3), s1 = getComputedStyle(document.querySelector('h1'));
  return {
    h1: { marginTop: s1.marginTop, marginBottom: s1.marginBottom },
    h2: { marginTop: s2.marginTop, marginBottom: s2.marginBottom, fontPx: s2.fontSize },
    h3: { marginTop: s3.marginTop, fontPx: s3.fontSize },
  };
}) };
