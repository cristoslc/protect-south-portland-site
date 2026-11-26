/* Staging preview bar (operator directives 2026-11-25):
   first directive: "on the staging site ONLY, need the staging warning + last
   updated bar at top, above nav, non-dismissable. Maybe do it as a js
   injection feature toggled on the site url (match only root domain
   staging.protectsouthportland.*)"
   The second 2026-11-25 directive restyles the text and adds a feedback
   link; the operator's target format verbatim: "Staging preview. Live site:
   protectsouthportland.org. Last updated: {{US Eastern time}}
   ({{commit hash}}). Feedback >>"

   One script, shipped in the same built bytes as production: the toggle is
   the URL, not the build. The bar renders only when the host IS the staging
   root domain (any top-level domain variant), never on production, localhost
   previews, or review checkouts. Non-dismissable by design: no dismiss
   control, no state stored, nothing in localStorage and no cookies.

   The "Last updated" fact comes from the serve tree's staging-manifest.json
   (written at serve time by tools/staging_serve.py with the serve time and
   the fork sha it was built from); when the manifest is unreachable the bar
   shows the warning and the feedback link without the updated line. The
   serve time renders in US Eastern (America/New_York) as e.g.
   "Nov 25, 2026, 10:18 a.m. EST", and the fork sha shows in 12-char short
   form. The "Feedback >>" link opens the staging feedback board's guided
   issue form in a new tab.

   Sticky (2026-11-25 directive: "on staging, the staging preview bar should
   be STICKY - it must not disappear when scrolling"): the bar sticks at
   the viewport top (.staging-bar position sticky, top 0, z 60 above the
   masthead's 50 and the banner's 40, below the gated state's max-int
   layer), and the stack reseats from real rendered heights - the masthead
   sticks below the bar's own offsetHeight and the event banner sticks
   below bar + masthead - measured on load and on window resize (the
   banner leg's refine pattern, never magic numbers: at 412 the bar wraps
   to two lines and its height varies). The banner's own shell script seats
   it from the masthead alone; this script runs after it (deferred) and
   its resize listener registers after, so the corrected seat always
   wins on staging and the shell's behavior is untouched in production,
   where this code never runs (the matcher returns above). */
(function () {
  var STAGING_HOST = /^staging\.protectsouthportland\.[a-z]{2,}$/i;
  if (!STAGING_HOST.test(window.location.hostname)) return;

  var FEEDBACK_URL = 'https://github.com/Protect-South-Portland/staging-website-feedback/issues/new?template=website-feedback.yml';

  var EASTERN_TIME = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
  });

  function easternTime(iso) {
    var parts = {};
    EASTERN_TIME.formatToParts(new Date(iso)).forEach(function (part) {
      parts[part.type] = part.value;
    });
    var period = parts.dayPeriod === 'AM' ? 'a.m.' : 'p.m.';
    return parts.month + ' ' + parts.day + ', ' + parts.year + ', ' +
      parts.hour + ':' + parts.minute + ' ' + period + ' ' + parts.timeZoneName;
  }

  var bar = document.createElement('div');
  bar.className = 'staging-bar';
  bar.setAttribute('role', 'note');
  bar.textContent = 'Staging preview. Live site: protectsouthportland.org. ';

  var feedback = document.createElement('a');
  feedback.href = FEEDBACK_URL;
  feedback.target = '_blank';
  feedback.rel = 'noopener noreferrer';
  feedback.setAttribute('aria-label', 'Feedback — file a comment on the staging preview');
  feedback.textContent = 'Feedback >>';
  bar.appendChild(feedback);

  var masthead = document.querySelector('.masthead');
  if (masthead && masthead.parentNode) {
    masthead.parentNode.insertBefore(bar, masthead);
  } else {
    document.body.prepend(bar);
  }

  /* The sticky stack reseats from measured heights: the bar sticks at top
     0 (.staging-bar), the masthead sticks below the bar's real rendered
     height, and the event banner sticks below both. offsetHeight on load
     and on resize, never magic numbers - at 412 the bar wraps to two
     lines and its height varies. The banner's own shell script seats the
     banner from the masthead alone and registered its resize listener
     first; this deferred script corrects both seats and its listener
     fires after the shell's on every resize, so the corrected seats win
     wherever the bar exists. */
  var banner = document.getElementById('alert-strip');
  var seat = function () {
    var barHeight = bar.offsetHeight;
    if (masthead) masthead.style.top = barHeight + 'px';
    if (banner && masthead) banner.style.top = (barHeight + masthead.offsetHeight) + 'px';
  };
  seat();
  window.addEventListener('resize', seat);

  fetch('/staging-manifest.json').then(function (res) {
    return res.ok ? res.json() : null;
  }).then(function (manifest) {
    if (!manifest || !manifest.served) return;
    var note = document.createElement('span');
    note.className = 'staging-bar__updated';
    var updated = 'Last updated: ' + easternTime(manifest.served);
    if (manifest.head) {
      updated += ' (' + String(manifest.head).slice(0, 12) + '). ';
    }
    note.textContent = updated;
    bar.insertBefore(note, feedback);
  }).catch(function () { /* no manifest in this tree: the warning and the feedback link stay */ });
})();
