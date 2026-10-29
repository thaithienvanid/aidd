"""`aidd eval standards`: the registry checks beyond the review dates. A `checked` date is a check only with the
evidence that confirms it, and no date may be shared by many unconfirmed entries; no entry cites a control by an id
another entry says moved; each edition names its source; and each tool, plugin, and skill names its license and pin."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from aidd import knowledge
from aidd.kernel import resources

_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*$")


def confirms(s: dict) -> bool:
    """Whether an entry's `evidence` confirms its `checked` date on its own.

    The URL must name a page, by its path or its query (a homepage shows only that a site exists), and the quote must be one full
    sentence: eight words or more, ending in `.`, `!`, or `?`, and neither the page title (` | `), the entry's own
    name, nor a copyright line. A title, a fragment, or boilerplate every page of a publisher carries shows that a page
    loaded, not that the edition was read. An
    extension's quote may instead be the line that names its pinned release, commit, or endpoint.
    """
    ev = s.get("evidence") or {}
    url, quote = urlparse(str(ev.get("url", ""))), " ".join(str(ev.get("quote", "")).split())
    if not (url.path.strip("/") or url.query):
        return False
    pins = [t for t in re.split(r"[\s(),@]+|==", str(s.get("pin", ""))) if len(t) >= 5 and re.search(r"\d|://", t)]
    if any(t in quote for t in pins):
        return True
    return (
        len(quote.split()) >= 8
        and bool(_SENTENCE_END.search(quote))
        and " | " not in quote
        and quote.casefold().rstrip(".") != str(s.get("name", "")).casefold()
        and not quote.casefold().startswith(("copyright", "©", "(c)"))
    )


def bulk_checked_dates(threshold: int = 20) -> list[tuple[str, int]]:
    """`checked` dates shared by more than `threshold` unconfirmed entries, as (date, count), newest first.

    One date across ISO 42001, the EU AI Act, MITRE ATLAS, and 250 others is a bulk edit, not that
    many independent confirmations. The currency control is only as good as the dates are honest,
    so `eval standards` fails when they cluster. A `reviewed` date claims no source check, so it is
    not counted.
    """
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for s in knowledge.dated_entries():
        # One entry referenced by five roles is one check, not five; an entry whose `evidence` quotes a
        # sentence from a real page (`confirms`) is an individual confirmation, whatever its date.
        key = str(s.get("id") or s.get("name"))
        if key in seen or confirms(s):
            continue
        seen.add(key)
        d = str(s.get("checked") or "")
        if d:
            counts[d] = counts.get(d, 0) + 1
    return sorted(((d, n) for d, n in counts.items() if n > threshold), key=lambda x: x[0], reverse=True)


_RENUMBERED = re.compile(r"\brenumbered from (\d{4})\b(.*)", re.I | re.S)
_MOVE = re.compile(r"\b([A-Z]{2,}\d{2})\s+to\s+([A-Z]{2,}\d{2})\b")


def stale_id_citations() -> list[dict]:
    """Entries that still cite a control by an ID another entry says moved.

    An entry whose `notes` say `renumbered from 2025 (Excessive Agency LLM06 to LLM03; ...)` makes the
    2025 IDs stale: any other entry whose source or evidence URL still carries one (`llm062025`) points
    agents at the old number. Each result carries `old`, `new`, `token`, and `moved_by`.
    """
    table = resources.load_json("roles.json").get("standards", {})
    moves = []
    for sid, e in table.items():
        m = _RENUMBERED.search(str(e.get("notes", "")))
        if m:
            moves += [(sid, old, new, f"{old}{m.group(1)}".lower()) for old, new in _MOVE.findall(m.group(2))]
    out = []
    for sid, e in table.items():
        urls = " ".join((str(e.get("source", "")), str((e.get("evidence") or {}).get("url", "")))).lower()
        out += [dict(e, id=sid, old=old, new=new, token=token, moved_by=by) for by, old, new, token in moves if by != sid and token in urls]
    return out


def unsourced_standards() -> list[dict]:
    """Entries in the registry's standards table that name an edition but no source to check it against.

    Read from the raw table: the resolved view folds a practice's `notes` into its displayed edition.
    """
    table = resources.load_json("roles.json").get("standards", {})
    return [dict(e, id=k) for k, e in table.items() if e.get("edition") and not e.get("source")]


def unevidenced_standards() -> list[dict]:
    """Entries in the standards table dated `checked` without the `source` and `evidence` that make the date a check.

    A practice with nothing to check against carries `reviewed` instead, so a `checked` date always names what was read.
    """
    table = resources.load_json("roles.json").get("standards", {})
    return [dict(e, id=k) for k, e in table.items() if e.get("checked") and not (e.get("source") and e.get("evidence"))]


def unpinned_extensions() -> list[dict]:
    """Tools, plugins, and skills with no `license` or no `pin`: third-party code a role would run with its permissions,
    unreviewable until a team knows what it may do with it and which exact release it installs. Each carries `missing`."""
    out = []
    for key in knowledge.roles()["order"]:
        for x in knowledge.roles()["roles"][key].get("extends", []):
            missing = [f for f in ("license", "pin") if not str(x.get(f, "")).strip()]
            if x["kind"] in ("tool", "plugin", "skill") and missing:
                out.append(dict(x, where=f"extension {key}", missing=missing))
    return out
