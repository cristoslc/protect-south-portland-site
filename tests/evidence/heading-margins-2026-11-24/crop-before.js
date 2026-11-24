const OUT = "/Users/cristos/Documents/projects/protect-south-portland/.worktrees/heading-margin-inversion/tests/evidence/heading-margins-2026-11-24/before";
const BASE = "http://127.0.0.1:8137/";
const WIDTHS = [412, 768, 1440];
const p = await browser.getPage("main");
for (const w of WIDTHS) {
  await p.setViewport({ width: w, height: 820 });
  await p.goto(BASE + "act-now.html?c=" + w, { waitUntil: "load" });
  await new Promise((r) => setTimeout(r, 500));
  await p.evaluate(() => {
    const h2 = [...document.querySelectorAll("h2")].find((h) => h.textContent.trim() === "Writing a letter to the editor");
    h2.scrollIntoView({ block: "center" });
  });
  await new Promise((r) => setTimeout(r, 300));
  await p.screenshot({ path: OUT + "/act-now-acceptance-" + w + ".png" });
}
return "ok";
