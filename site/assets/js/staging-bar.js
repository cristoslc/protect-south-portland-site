/* Staging preview bar (operator directive 2026-11-25):
   "on the staging site ONLY, need the staging warning + last updated bar at
   top, above nav, non-dismissable. Maybe do it as a js injection feature
   toggled on the site url (match only root domain staging.protectsouthportland.*)"

   One script, shipped in the same built bytes as production: the toggle is
   the URL, not the build. The bar renders only when the host IS the staging
   root domain (any top-level domain variant), never on production, localhost
   previews, or review checkouts. Non-dismissable by design: no dismiss
   control, no state stored, nothing in localStorage and no cookies. The
   "last updated" fact comes from the serve tree's staging-manifest.json
   (written at serve time by tools/staging_serve.py with the serve time and
   the fork sha it was built from); when the manifest is unreachable the bar
   shows the warning without the updated line. In document flow at the top
   (not sticky): it scrolls away with the page. */
(function () {
  var STAGING_HOST = /^staging\.protectsouthportland\.[a-z]{2,}$/i;
  if (!STAGING_HOST.test(window.location.hostname)) return;

  var bar = document.createElement('div');
  bar.className = 'staging-bar';
  bar.setAttribute('role', 'note');
  bar.textContent = 'Staging preview. This is not the live site; the live site is protectsouthportland.org.';
  var masthead = document.querySelector('.masthead');
  if (masthead && masthead.parentNode) {
    masthead.parentNode.insertBefore(bar, masthead);
  } else {
    document.body.prepend(bar);
  }

  fetch('/staging-manifest.json').then(function (res) {
    return res.ok ? res.json() : null;
  }).then(function (manifest) {
    if (!manifest || !manifest.served) return;
    var note = document.createElement('span');
    note.className = 'staging-bar__updated';
    note.textContent = ' Last updated: ' + manifest.served +
      (manifest.head ? ' (serve ' + String(manifest.head).slice(0, 12) + ')' : '');
    bar.appendChild(note);
  }).catch(function () { /* no manifest in this tree: the warning alone stays */ });
})();
