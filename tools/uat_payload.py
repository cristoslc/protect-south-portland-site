#!/usr/bin/env python3
"""UAT rule: displayed sendable copy must be the payload an action transmits.

The defect this exists to catch, found by the operator's eye on 2026-11-24:
`act-now.html` displayed a letter under an "Example message" heading beside an
orange "Email the Council" CTA whose `mailto:` carried a subject and an EMPTY
body, so the click opened a blank draft while the page asked the reader to copy
the letter by hand. Nothing looked for it.

THE RULE, stated generally: wherever a built page displays sendable copy (a
sample message, a petition text, a comment template) beside an action that
transmits it (a `mailto:` CTA, a form, a share link), the mechanism's payload
MUST match the displayed copy — same text, no truncation, and never an empty
payload under displayed message copy. A mismatch, a blank payload, or a
transmitting control with no payload where the page promises one is a named
failure that carries the page, the control's label, and what diverged.

WHAT COUNTS AS SENDABLE COPY (so an ordinary paragraph never does):
  * a `<blockquote>` whose governing label — the nearest heading before it —
    carries a send cue ("Example message", "A message you can send", "Sample
    comment", "Petition text", ...), or
  * any element carrying `data-sendable-copy` (the explicit opt-in: needs no
    cue, and is the precise way to designate new copy a page intends to send).
  An ordinary paragraph, a pull-quote and a mailing-address blockquote (headed
  "Mailing address" / "Give by mail") never qualify: their labels carry no cue.

WHAT COUNTS AS A TRANSMITTING CONTROL (so an address link never does):
  * a `mailto:`/`sms:`/share href whose query carries a payload parameter
    (`body=`, `text=`, `quote=`) — or, for the blank case, a `subject=`;
  * a button-styled `mailto:` (class contains `btn`) whose label carries a send
    cue ("Email ...", "Send ...", "Write ..."), even with NO query at all, so a
    CTA that promises to send the copy and sends nothing is caught;
  * a `<form>` carrying a message field (textarea, or a text input named for a
    message): the reader types the copy there, so its payload is the reader's
    and is not compared — it is recorded as a note, never a failure.
  A bare `mailto:someone@example.org` link, an address used as link text, and a
  subject-only newsletter or alert link are not transmitting controls.

PAIRING (so an unrelated control elsewhere on the page never fails a page): a
control pairs with a sendable block only when no heading other than the block's
own governing label sits between them and no other sendable block sits between
them. On `act-now.html` the CTA sits directly above "Example message", so it
pairs; the "Workshop alerts" mailto several headings further down does not.

WHAT THE RULE DOES NOT DO: it does not judge prose, does not require a page to
offer a send mechanism at all (displayed copy with no nearby control is
reported as an unpaired note, not a failure), and does not compare a subject
line. It reads FETCHED HTML (http, https or file:) so the same rule runs
against a live host by URL, which is the shape the UAT ladder checks.

Ledger row 97.
"""
from html.parser import HTMLParser
import html as html_mod
import os
import re
import urllib.parse
import urllib.request

USER_AGENT = "PSP-UAT-PayloadCheck/1.0 (acceptance testing)"

# A heading that labels displayed copy as something a reader would send. Whole
# words only, so "mailing" never matches "mail", and "email"/"mail" are absent
# on purpose: the site's mailing-address blockquotes are headed "Mailing
# address" and "Give by mail" and must never be read as sendable copy.
SEND_CUES = frozenset({
    "message", "messages", "letter", "letters", "petition", "template",
    "sample", "example", "script", "comment", "comments", "testimony",
    "copy", "send", "write", "text",
})

# A control's own label, when it is button-styled and has no payload at all.
CTA_SEND_CUES = frozenset({"email", "send", "write", "submit"})

PAYLOAD_PARAMS = ("body", "text", "quote")
SUBJECT_PARAMS = ("subject",)

HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
FORM_MESSAGE_TYPES = frozenset({"text", "search"})


class PayloadFetchError(RuntimeError):
    """A page could not be fetched for the sweep — an environment failure."""


def _line_offsets(markup):
    offsets, total = [], 0
    for line in markup.splitlines(keepends=True):
        offsets.append(total)
        total += len(line)
    offsets.append(total)
    return offsets


def _plain(fragment):
    """Tag-stripped, entity-decoded, whitespace-collapsed text."""
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def canonical(text):
    """The comparison form both sides of a payload check use.

    Whitespace runs collapse to one space and entities decode, so a paragraph
    separator (blank line vs space) can never fail the rule while a word,
    punctuation mark or missing tail still does.
    """
    return _plain(text)


def _words(text):
    return re.findall(r"[a-z0-9][a-z0-9'-]*", text.casefold())


def _has_cue(text, cues):
    return any(word in cues for word in _words(text))


class _Scan(HTMLParser):
    """Collect headings, blockquotes, anchors and forms with source offsets."""

    def __init__(self, markup):
        super().__init__(convert_charrefs=False)
        self.markup = markup
        self.offsets = _line_offsets(markup)
        self.headings = []
        self.blocks = []
        self.controls = []
        self._open = []

    def _offset(self):
        line, col = self.getpos()
        return self.offsets[line - 1] + col

    def handle_starttag(self, tag, attrs):
        attr = {k: (v or "") for k, v in attrs}
        start = self._offset()
        if tag in HEADING_TAGS:
            self._open.append({"kind": "heading", "tag": tag, "start": start,
                               "attrs": attr})
        elif tag == "blockquote" or "data-sendable-copy" in attr:
            self._open.append({"kind": "block", "tag": tag, "start": start,
                               "attrs": attr})
        elif tag in ("a", "area"):
            self._open.append({"kind": "control", "tag": tag, "start": start,
                               "attrs": attr})
        elif tag == "form":
            self._open.append({"kind": "form", "tag": tag, "start": start,
                               "attrs": attr, "fields": []})
        elif tag in ("textarea", "input") and self._open and \
                self._open[-1]["kind"] == "form":
            form = self._open[-1]
            itype = (attr.get("type") or "text").casefold()
            name = (attr.get("name") or attr.get("id") or "").casefold()
            if tag == "textarea" or itype in FORM_MESSAGE_TYPES or any(
                    hint in name for hint in ("message", "comment", "body",
                                              "story", "note", "text")):
                form["fields"].append(name or tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self._open and self._open[-1]["tag"] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index]["tag"] == tag:
                record = self._open.pop(index)
                record["end"] = self._offset() + len(tag) + 3
                self._record(record)
                return

    def _record(self, record):
        kind = record["kind"]
        if kind == "heading":
            record["level"] = int(record["tag"][1])
            record["text"] = _plain(self.markup[record["start"]:record["end"]])
            self.headings.append(record)
        elif kind == "block":
            record["text"] = _plain(self.markup[record["start"]:record["end"]])
            self.blocks.append(record)
        elif kind == "control":
            record["label"] = _plain(self.markup[record["start"]:record["end"]])
            self.controls.append(record)
        elif kind == "form":
            self.controls.append(record)

    def close(self):
        super().close()
        while self._open:  # an unclosed element still counts, oddly but loudly
            self._record(self._open.pop())


def _param_map(href):
    parts = urllib.parse.urlsplit(href)
    kept = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    return parts.scheme.casefold(), {k.casefold(): v[0] if v else ""
                                     for k, v in kept.items()}


def _control_payload(control):
    """(payload_text, has_payload_param, has_subject) for one anchor control."""
    href = control["attrs"].get("href", "")
    if not href:
        return "", False, False
    scheme, params = _param_map(href)
    for name in PAYLOAD_PARAMS:
        if name in params:
            return urllib.parse.unquote(params[name]), True, "subject" in params
    return "", False, "subject" in params


def _is_transmitting(control):
    """True when this element is a mechanism that sends the displayed copy."""
    if control["kind"] == "form":
        return bool(control["fields"])
    href = control["attrs"].get("href", "")
    if not href:
        return False
    scheme, params = _param_map(href)
    if scheme in ("mailto", "sms") or "text" in params or "body" in params \
            or "quote" in params or "subject" in params:
        if any(name in params for name in PAYLOAD_PARAMS):
            return True
        if "subject" in params:
            return True
        # A button-styled mailto with no query at all: the blank case.
        css = control["attrs"].get("class", "")
        return (scheme in ("mailto", "sms") and "btn" in css.split()
                and _has_cue(control["label"], CTA_SEND_CUES))
    return False


def _governing_heading(block, headings):
    before = [h for h in headings if h["end"] <= block["start"]]
    return before[-1] if before else None


def _is_sendable(block, headings):
    if "data-sendable-copy" in block["attrs"]:
        return True
    gov = _governing_heading(block, headings)
    return bool(gov) and _has_cue(gov["text"], SEND_CUES)


def _region_ok(block, control, governing, headings, blocks):
    """No heading but the block's own label, and no other sendable block,
    may sit between a control and the block it would send."""
    if control["end"] <= block["start"]:
        low, high = control["end"], block["start"]
    else:
        low, high = block["end"], control["start"]
    for heading in headings:
        if heading is governing:
            continue
        if low < heading["start"] < high:
            return False
    for other in blocks:
        if other is block:
            continue
        if low < other["start"] < high:
            return False
    return True


def sendable_blocks(markup):
    """Every block on the page the rule reads as copy a reader would send."""
    scan = _Scan(markup)
    scan.feed(markup)
    scan.close()
    found = []
    for block in scan.blocks:
        if not _is_sendable(block, scan.headings):
            continue
        gov = _governing_heading(block, scan.headings)
        block["label"] = (gov["text"] if gov else
                          block["attrs"].get("aria-label", ""))
        block["governing"] = gov
        found.append(block)
    return found


def divergence(expected, actual):
    if len(actual) < len(expected) and expected.startswith(actual):
        return (f"payload stops after {len(actual)} of {len(expected)} "
                "characters")
    index = 0
    for left, right in zip(expected, actual):
        if left != right:
            break
        index += 1
    return (f"first difference at character {index + 1}: the page displays "
            f"{expected[index:index + 40]!r}, the payload carries "
            f"{actual[index:index + 40]!r}")


def format_finding(page, kind, control_label, block_label, detail):
    return (f"sendable-payload:{kind} {page}: control {control_label!r} "
            f"beside displayed copy {block_label!r} — {detail}")


def copy_payload_pairs(markup):
    """Every displayed-copy/transmitting-control pair on a page, both sides.

    This is the raw material both the rule and the unit pin read: each dict
    carries the control's label, the label of the displayed copy, the
    mechanism, and the two canonical strings the rule compares (`copy` and
    `payload`). A form pair carries no `payload`: the reader types the copy.
    """
    scan = _Scan(markup)
    scan.feed(markup)
    scan.close()
    blocks = [block for block in scan.blocks if _is_sendable(block, scan.headings)]
    for block in blocks:
        gov = _governing_heading(block, scan.headings)
        block["label"] = (gov["text"] if gov else
                          block["attrs"].get("aria-label", ""))
        block["governing"] = gov
    controls = [control for control in scan.controls if _is_transmitting(control)]

    pairs = []
    for block in blocks:
        for control in controls:
            if not _region_ok(block, control, block["governing"],
                              scan.headings, blocks):
                continue
            label = (control.get("label") or control["attrs"].get("value")
                     or control["attrs"].get("action", ""))
            if control["kind"] == "form":
                pairs.append({"control": label, "copy_label": block["label"],
                              "mechanism": "form", "copy": canonical(block["text"]),
                              "payload": None, "has_payload_param": False})
                continue
            payload, has_param, _subject = _control_payload(control)
            mechanism = urllib.parse.urlsplit(
                control["attrs"].get("href", "")).scheme.casefold() or "link"
            pairs.append({"control": label, "copy_label": block["label"],
                          "mechanism": mechanism, "copy": canonical(block["text"]),
                          "payload": canonical(payload),
                          "has_payload_param": has_param})
    return pairs


def inspect_page(markup, page):
    """Inspect one page's HTML. Returns {"findings", "pairs", "notes"}.

    A finding is a formatted string naming the page, the control, and what
    diverged; a pair is one comparison the rule actually made, so a test can
    prove the rule was not vacuous on a page.
    """
    pairs = copy_payload_pairs(markup)
    findings, notes = [], []
    for pair in pairs:
        label, copy_label = pair["control"], pair["copy_label"]
        if pair["mechanism"] == "form":
            notes.append(f"{page}: control {label!r} is a form carrying a "
                         "message field — the reader supplies the copy")
            continue
        if not pair["has_payload_param"] or not pair["payload"]:
            findings.append(format_finding(
                page, "missing-payload", label, copy_label,
                f"the {pair['mechanism']} sends an empty payload while the "
                f"page displays {len(pair['copy'])} characters of sendable "
                "copy — the reader would have to paste it by hand"))
            continue
        if pair["payload"] != pair["copy"]:
            findings.append(format_finding(
                page, "payload-mismatch", label, copy_label,
                divergence(pair["copy"], pair["payload"])))
    if not pairs:
        for block in sendable_blocks(markup):
            notes.append(f"{page}: displayed copy {block['label']!r} has no "
                         "transmitting control in its region (not a failure)")
    return {"findings": findings, "pairs": pairs, "notes": notes}


def check_page(markup, page):
    """The findings for one page, in the UAT ladder's failure shape."""
    return inspect_page(markup, page)["findings"]


def page_url(base, page):
    """Resolve one page against a base that may be http(s) or a file: path."""
    if base.startswith("file:"):
        root = base[len("file:"):]
        if root.endswith(".html") or root.endswith(".htm"):
            root = os.path.dirname(root)
        return "file:" + os.path.join(root, page)
    return urllib.parse.urljoin(base if base.endswith("/") else base + "/", page)


def fetch_html(url, timeout=20.0):
    """GET one page as text. Raises PayloadFetchError — an environment fault,
    never a site finding."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            body = response.read()
    except Exception as exc:  # noqa: BLE001 — surface the URL and the reason
        raise PayloadFetchError(f"cannot fetch {url}: {exc}") from exc
    if status is None and url.startswith("file:"):
        status = 200  # file: URLs carry no status line, which is a 200 here
    if status != 200:
        raise PayloadFetchError(f"cannot fetch {url}: status {status}")
    return body.decode("utf-8", errors="replace")


def sweep(base, pages, fetcher=fetch_html):
    """Run the rule over each page fetched from `base`.

    Works identically against a live host and a local build, because both go
    through the same fetch. Returns (findings, reports) where reports maps each
    page to its inspect_page() result; a fetch fault raises loudly.
    """
    findings, reports = [], {}
    for page in pages:
        report = inspect_page(fetcher(page_url(base, page)), page)
        reports[page] = report
        findings.extend(report["findings"])
    return findings, reports


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="UAT rule: displayed sendable copy must match the payload "
                    "its action transmits (ledger row 97).")
    parser.add_argument("--url", required=True,
                        help="base URL or file: path of the built index")
    parser.add_argument("--pages", nargs="+", default=None,
                        help="page names (default: every .html in the base)")
    args = parser.parse_args(argv)
    if args.pages:
        pages = args.pages
    elif args.url.startswith("file:"):
        root = args.url[len("file:"):]
        root = os.path.dirname(root) if root.endswith(".html") else root
        pages = sorted(name for name in os.listdir(root)
                       if name.endswith(".html"))
    else:
        parser.error("--pages is required for an http(s) base")
    findings, reports = sweep(args.url, pages)
    for report in reports.values():
        for note in report["notes"]:
            print(f"note: {note}")
    for finding in findings:
        print(f"FAIL: {finding}")
    pairs = sum(len(report["pairs"]) for report in reports.values())
    print(f"payload sweep: {len(reports)} pages, {pairs} copy/payload pairs "
          f"compared, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
