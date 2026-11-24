// Heading-margin captures + acceptance-gap measurements (ledger row 104).
// BASE = server root over a built docs/ tree. OUT = evidence subfolder
// (before/ or after/). Writes full-page PNGs for act-now, index and
// tank-farms at 412 / 768 / 1440, and measures the acceptance case on
// act-now.html: the h2 "Writing a letter to the editor" against the
// legislator contact list above it and the Sentry h3 below it.
const BASE = 'http://127.0.0.1:8137/';
const OUT = '/Users/cristos/Documents/projects/protect-south-portland/.worktrees/heading-margin-inversion/tests/evidence/heading-margins-2026-11-24/before';
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
