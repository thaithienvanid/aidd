"""`aidd eval standards --online`: each registry entry's evidence URL fetched again, and whether the quoted sentence is
still on the page: `ok`, `moved` (the address no longer serves it), `missing` (the page no longer says it), or
`unreachable` (no answer to judge). It is bounded (a timeout per request, a time cap for the run, a byte limit per page,
at most two requests in flight and one per host), names itself in its user agent, and never edits the registry. The
offline check is the default.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import threading
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from aidd.knowledge import bounded_fetch

SCHEMA_VERSION = "1"
STATUSES = ("ok", "moved", "missing", "unreachable")
_TEXT_TYPES = ("text/", "application/xhtml", "application/xml", "application/json", "application/rss", "application/atom")


def evidence_entries() -> list[dict]:
    """Each entry with evidence to re-read, once, in registry order: `id`, `where` (the first owner), `url`, `quote`."""
    from aidd.knowledge import standards_evidence

    seen: set[str] = set()
    out = []
    for s in standards_evidence.dated_entries():
        key = str(s.get("id") or s.get("name"))
        ev = s.get("evidence") or {}
        if key in seen or not (ev.get("url") and ev.get("quote")):
            continue
        seen.add(key)
        out.append({"id": key, "name": s.get("name", key), "where": s.get("where", ""), "url": str(ev["url"]), "quote": str(ev["quote"])})
    return out


_TAG = re.compile(r"<[^>]*>")
_TYPOGRAPHY = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u202f": " ",
        "\u00ad": None,
        "\u200b": None,
        "*": None,
        "`": None,
    }
)


def normalize(text: str) -> str:
    """Text as the check compares it: entities decoded, typographic quotes and dashes plain, no emphasis marks, runs
    of whitespace one space, and case folded."""
    return " ".join(html.unescape(text).translate(_TYPOGRAPHY).split()).casefold()


def quote_on_page(quote: str, page: str) -> bool:
    """Whether the quoted sentence is on the page, with its markup removed (a tag as a space, or as nothing, for a
    word split by inline markup), or as written, for a quote of markup itself (an XML element of a POM or a feed).
    A JSON answer (an API's) is also read as indented JSON, the form a quote of one of its lines was copied from
    (`"sha": "...",`), whatever spacing the API sent."""
    want = normalize(quote)
    if not want:
        return False
    pages = [_TAG.sub(" ", page), _TAG.sub("", page), page]
    if page.lstrip()[:1] in ("{", "["):
        try:
            pages.append(json.dumps(json.loads(page), indent=2, ensure_ascii=False))
        except ValueError:
            pass
    return any(want in normalize(x) for x in pages)


def _same_address(a: str, b: str) -> bool:
    """Two addresses for one page: the scheme, a trailing slash, the host's case, and a fragment do not count."""

    def key(u: str) -> tuple[str, str, str]:
        p = urllib.parse.urlsplit(u)
        return p.netloc.lower().removeprefix("www."), p.path.rstrip("/") or "/", p.query

    return key(a) == key(b)


def judge(e: dict, fetcher: Callable[[str], bounded_fetch.Fetched]) -> dict:
    """One entry's row: its status, the HTTP status, the final address after a redirect, and why."""
    row = {"id": e["id"], "where": e.get("where", ""), "url": e["url"], "status": "unreachable", "http_status": None, "final_url": None, "reason": ""}
    try:
        got = fetcher(e["url"])
    except bounded_fetch.FetchError as exc:
        if exc.status in (404, 410):
            return row | {"status": "moved", "http_status": exc.status, "reason": f"HTTP {exc.status}: the page is no longer at this address"}
        return row | {"http_status": exc.status, "reason": str(exc)}
    moved = not _same_address(got.final_url, e["url"])
    row |= {"http_status": got.status, "final_url": got.final_url if moved else None}
    ctype = got.ctype.split(";", 1)[0].strip().lower()
    if ctype and not ctype.startswith(_TEXT_TYPES):
        return row | {"reason": f"cannot read {ctype} without a parser; check the quote by hand"}
    try:
        text = got.body.decode(bounded_fetch.charset(got.ctype), errors="replace")
    except LookupError:
        text = got.body.decode("utf-8", errors="replace")
    if quote_on_page(e["quote"], text):
        return row | {"status": "ok", "reason": f"redirected to {got.final_url}; update evidence.url" if moved else ""}
    if got.truncated:
        return row | {"reason": f"the quote is not in the first {len(got.body)} bytes, the most this run reads from a page"}
    if moved:
        return row | {"status": "moved", "reason": f"redirected to {got.final_url}, which does not carry the quote"}
    return row | {"status": "missing", "reason": "the page loads but no longer carries the quote; re-read the source"}


def check_online(
    entries: list[dict],
    *,
    timeout_seconds: float = bounded_fetch.TIMEOUT_SECONDS,
    max_seconds: float = bounded_fetch.MAX_SECONDS,
    max_bytes: int = bounded_fetch.MAX_BYTES,
    concurrency: int = bounded_fetch.CONCURRENCY,
    host_delay_seconds: float = bounded_fetch.HOST_DELAY_SECONDS,
    today: dt.date | None = None,
) -> dict:
    """Every entry's evidence re-read, within the bounds, as the `aidd eval standards --online --json` object."""
    concurrency = max(1, min(2, int(concurrency)))
    deadline = time.monotonic() + max(0.0, max_seconds)
    guard = threading.Lock()
    hosts: dict[str, threading.Lock] = {}
    last: dict[str, float] = {}

    def capped(url: str) -> bounded_fetch.Fetched:
        raise bounded_fetch.FetchError(f"not fetched: the run's time cap of {max_seconds:g} s was reached")

    def one(e: dict) -> dict:
        host = urllib.parse.urlsplit(e["url"]).netloc.lower()
        with guard:
            lock = hosts.setdefault(host, threading.Lock())
        with lock:  # one request at a time per host, `host_delay` apart
            wait = last.get(host, 0.0) + host_delay_seconds - time.monotonic()
            if wait > 0 and time.monotonic() + wait < deadline:
                time.sleep(wait)
            if time.monotonic() >= deadline:
                return judge(e, capped)
            try:
                return judge(e, lambda url: bounded_fetch.fetch(url, timeout_seconds, max_bytes, deadline))
            finally:
                last[host] = time.monotonic()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, entries))
    counts = {s: sum(1 for r in results if r["status"] == s) for s in STATUSES}
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_on": (today or dt.date.today()).isoformat(),
        "limits": {"timeout_seconds": timeout_seconds, "max_seconds": max_seconds, "max_bytes": max_bytes, "concurrency": concurrency},
        "counts": counts,
        "results": results,
    }
