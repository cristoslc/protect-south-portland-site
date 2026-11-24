// Header contrast measurement for the Act now pill (2026-11-23).
// Run through `bb browser-automation run <session> --script ...` with the
// placeholders substituted: __BASE__ = local static server root over the built
// docs/, __OUT__ = directory the screenshots are written to. See README.md in
// this folder for the contract and the numbers it produced.
const BASE = __BASE__;
const OUT = '__OUT__';
const p = await browser.getPage('main');

function js() {
  const hex = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((s) => parseFloat(s.trim()));
    const [r, g, b, a = 1] = parts;
    return { r, g, b, a };
  };
  const lum = ({ r, g, b }) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  const composite = (el) => {
    // walk up, collecting fills; blend translucent layers onto an opaque base
    const layers = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const st = getComputedStyle(node);
      const bg = hex(st.backgroundColor);
      if (bg && bg.a > 0) layers.push(bg);
      if (bg && bg.a >= 1) break;
      node = node.parentElement;
    }
    let base = { r: 255, g: 255, b: 255 };
    for (let i = layers.length - 1; i >= 0; i--) {
      const l = layers[i];
      base = {
        r: l.r * l.a + base.r * (1 - l.a),
        g: l.g * l.a + base.g * (1 - l.a),
        b: l.b * l.a + base.b * (1 - l.a),
      };
    }
    return base;
  };
  const round = (n) => Math.round(n * 100) / 100;
  const fmt = (c) => '#' + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
  const pill = document.querySelector('nav.main-nav > ul > li.nav-cta > a');
  const label = document.querySelector('.nav-toggle-label');
  const out = { pill: null, label: null, menuVisible: null };
  if (pill) {
    const st = getComputedStyle(pill);
    const fg = hex(st.color);
    const bg = composite(pill);
    out.pill = {
      selector: 'nav.main-nav > ul > li.nav-cta > a',
      text: pill.textContent.trim(),
      color: st.color,
      colorHex: fmt(fg),
      backgroundColorDeclared: st.backgroundColor,
      backgroundHex: fmt(bg),
      fontSize: st.fontSize,
      fontWeight: st.fontWeight,
      ratio: round(ratio(fg, bg)),
    };
    const rect = pill.getBoundingClientRect();
    out.pillRect = { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) };
  }
  if (label) {
    const st = getComputedStyle(label);
    const fg = hex(st.color);
    const bg = composite(label);
    out.label = {
      selector: '.nav-toggle-label',
      text: label.textContent.trim(),
      colorHex: fmt(fg),
      backgroundHex: fmt(bg),
      fontSize: st.fontSize,
      fontWeight: st.fontWeight,
      ratio: round(ratio(fg, bg)),
    };
  }
  const nav = document.querySelector('nav.main-nav');
  out.menuVisible = !!(nav && getComputedStyle(nav).display !== 'none');
  return out;
}

const results = {};

async function shot(name) {
  await p.screenshot({ path: OUT + '/' + name });
}

// 412 — mobile, menu closed then open
await p.setViewport({ width: 412, height: 900 });
await p.goto(BASE + 'index.html?m=' + Date.now(), { waitUntil: 'load' });
await new Promise((r) => setTimeout(r, 700));
await shot('412-menu-closed.png');
results['412-menu-closed'] = await p.evaluate(js);
await p.evaluate(() => {
  const t = document.querySelector('.nav-toggle');
  t.checked = true;
  t.dispatchEvent(new Event('change', { bubbles: true }));
});
await new Promise((r) => setTimeout(r, 400));
await shot('412-menu-open.png');
results['412-menu-open'] = await p.evaluate(js);

// 768 — mobile/tablet, closed then open
await p.setViewport({ width: 768, height: 900 });
await p.goto(BASE + 'index.html?m=' + Date.now(), { waitUntil: 'load' });
await new Promise((r) => setTimeout(r, 700));
await shot('768-menu-closed.png');
results['768-menu-closed'] = await p.evaluate(js);
await p.evaluate(() => {
  const t = document.querySelector('.nav-toggle');
  t.checked = true;
  t.dispatchEvent(new Event('change', { bubbles: true }));
});
await new Promise((r) => setTimeout(r, 400));
await shot('768-menu-open.png');
results['768-menu-open'] = await p.evaluate(js);

// 1440 — desktop row
await p.setViewport({ width: 1440, height: 900 });
await p.goto(BASE + 'index.html?m=' + Date.now(), { waitUntil: 'load' });
await new Promise((r) => setTimeout(r, 700));
await shot('1440-menu-closed.png');
results['1440-menu-closed'] = await p.evaluate(js);

return results;
