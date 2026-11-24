// Focus-ring evidence capture (ledger row 95). Run through:
//   bb browser-automation run <session> --script-file <this> --script-host <host>
// with WIDTH and BASE substituted by capture_focus_rings.sh.
//
// Focus is reached with real Tab presses, never el.focus(), so the ring a
// keyboard reader actually gets is the ring in the picture. Each target is
// scrolled to the middle of the viewport and captured as a viewport shot, so
// the element rect the script reports maps 1:1 to image pixels for the pixel
// measurement in measure_focus_rings.py.
const p = await browser.getPage('main');
const out = [];
const WIDTH = WIDTH_PLACEHOLDER;
const BASE = 'BASE_PLACEHOLDER';
const OUT = 'OUT_PLACEHOLDER';

// The homepage's map iframe holds dozens of focusable markers, so forward
// tabbing into the footer lands inside the frame and never arrives. The
// iframes are taken out of the tab order (tabindex -1, no visual change: the
// map still paints) before tabbing, which keeps every capture a real Tab
// press — the thing that makes :focus-visible match.
async function tabTo(selector, maxPresses) {
  for (let i = 0; i < maxPresses; i++) {
    await p.keyboard.press('Tab');
    const hit = await p.evaluate(
      (sel) => document.activeElement && document.activeElement.matches(sel),
      selector);
    if (hit) return i + 1;
  }
  return 0;
}

async function capture(pageUrl, selector, path) {
  await p.goto(pageUrl + '?f=' + Date.now(), {waitUntil: 'load'});
  await new Promise((r) => setTimeout(r, 500));
  // HTTP and the headless cache would otherwise keep serving the stylesheet
  // from a previous capture run, which is how the first pass of this evidence
  // photographed the UA default ring. Re-request the same file under a fresh
  // URL so the pixels are always the stylesheet as committed.
  await p.evaluate(async () => {
    const link = document.querySelector('link[rel="stylesheet"]');
    const url = new URL(link.href, location.href);
    url.searchParams.set('v', String(Date.now()));
    await new Promise((resolve) => {
      link.addEventListener('load', resolve, {once: true});
      link.href = url.toString();
      setTimeout(resolve, 4000);
    });
  });
  await p.evaluate(() => {
    document.querySelectorAll('iframe').forEach((f) => f.setAttribute('tabindex', '-1'));
  });
  const presses = await tabTo(selector, 120);
  if (!presses) {
    throw new Error('never reached ' + selector + ' with Tab');
  }
  // `behavior: instant` because the stylesheet sets scroll-behavior: smooth;
  // an animated scroll left the rect read mid-flight and put the reported
  // coordinates above the pixels in the first measurement pass.
  await p.evaluate((sel) => {
    document.querySelector(sel).scrollIntoView({block: 'center', behavior: 'instant'});
  }, selector);
  await new Promise((r) => setTimeout(r, 500));
  const info = await p.evaluate((sel) => {
    const el = document.querySelector(sel);
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {
      selector: sel,
      text: (el.textContent || '').trim(),
      rect: {x: r.x, y: r.y, w: r.width, h: r.height},
      focused: document.activeElement === el,
      outline: cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor,
      outlineOffset: cs.outlineOffset,
      fill: cs.backgroundColor,
      ink: cs.color,
    };
  }, selector);
  await p.screenshot({path});
  out.push(Object.assign({presses, page: pageUrl, shot: path}, info));
}

await p.setViewport({width: WIDTH, height: 900});
await capture(BASE + 'act-now.html', 'main .btn--ghost', OUT + '/' + WIDTH + '-act-now-ghost-light.png');
await capture(BASE + 'act-now.html', 'main .btn--cta', OUT + '/' + WIDTH + '-act-now-cta-light.png');
await capture(BASE + 'index.html', '.banner .btn--cta', OUT + '/' + WIDTH + '-banner-cta-dark.png');
await capture(BASE + 'index.html', '.footer__donate .btn', OUT + '/' + WIDTH + '-footer-cta-dark.png');
return out;
