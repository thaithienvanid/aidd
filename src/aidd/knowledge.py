"""Keeping the team's knowledge current: the standards check, the review cadence, stewards, and Learn actions.

- `check_releases` reads the release feed of each library standard's tool (PyPI, npm, crates.io, Maven Central,
  NuGet, the Go module proxy, or GitHub releases; for a language toolchain, go.dev, nodejs.org, the .NET release
  index, Adoptium, or python.org) and flags a newer major stable release than its `checked_version`. A `latest_lts`
  standard is judged against the newest LTS release where the feed marks one.
- `check_online` fetches each registry entry's evidence URL again and reports whether the quoted sentence is still on
  the page: `ok`, `moved` (the address no longer serves it), `missing` (the page no longer says it), or `unreachable`
  (no answer to judge). It is bounded (a timeout per request, a time cap for the run, a byte limit per page, at most
  two requests in flight and one per host), names itself in its user agent, and never edits the registry.
  `aidd eval standards --online` runs it; the offline check is the default.
- The review cadence: an entry is due `review_every_days` after its date, else 90 days for an emerging entry and 365
  for an established one; a dated obligation also carries `review_due`.
- A steward per domain pack and practice skill: the person or team who keeps it current, never an agent.
- A postmortem action may `target` a pack or a skill (`pack:<slug>`, `skill:<name>`): the lesson belongs in the team's
  knowledge, and `aidd list` shows it until it is done.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from . import __version__, docs, resources
from . import http as aiddhttp

SCHEMA_VERSION = "1"
STATUSES = ("ok", "moved", "missing", "unreachable")
REVIEW_EVERY_DAYS = {"established": 365, "emerging": 90}
USER_AGENT = f"aidd/{__version__} (standards evidence check; +https://github.com/thaithienvanid/aidd)"
TIMEOUT_SECONDS = 15.0
MAX_SECONDS = 600.0
MAX_BYTES = 3_000_000
CONCURRENCY = 2
HOST_DELAY_SECONDS = 1.0
_TEXT_TYPES = ("text/", "application/xhtml", "application/xml", "application/json", "application/rss", "application/atom")


# ---- The review cadence ---------------------------------------------------------------------------------------------


def cadence_days(s: dict) -> int:
    """Days between reviews of an entry: its own `review_every_days`, else the default for its maturity."""
    own = s.get("review_every_days")
    return int(own) if own else REVIEW_EVERY_DAYS.get(str(s.get("maturity") or "established"), REVIEW_EVERY_DAYS["established"])


# ---- Stewards -------------------------------------------------------------------------------------------------------

_STEWARD = re.compile(r"^(@[A-Za-z0-9][A-Za-z0-9-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)?|email:[^@\s]+@[^@\s]+)$")


def steward_problem(value: object) -> str | None:
    """Why `value` cannot be a steward, or None: a steward is a person or a team (`@user`, `@org/team`,
    `email:<address>`), never an agent, a bot account, or a login the baseline names as an agent."""
    from . import config as cfgmod
    from . import gates

    text = str(value or "").strip()
    low = text.lower()
    if low.startswith("agent:") or low.endswith("[bot]") or cfgmod.is_bot(low.lstrip("@")) or gates.agent_account(low.lstrip("@")):
        return f"{text} is an agent or a bot account; a steward is a person or a team"
    if not _STEWARD.match(text):
        return f"{text or 'an empty value'} is not a person's or a team's handle (`@user`, `@org/team`, or `email:<address>`)"
    return None


def stewards() -> list[dict]:
    """Every domain pack and practice skill with its steward (None when none is named), packs first."""
    out = [{"kind": "pack", "id": d["slug"], "steward": d.get("steward")} for d in resources.roles()["domains"]]
    out += [{"kind": "skill", "id": n, "steward": docs.practice_steward(n)} for n in docs.practice_names()]
    return out


def steward_findings() -> tuple[list[str], list[dict]]:
    """(errors, unset): a named steward that is not a person or a team, and the packs and skills that name none."""
    errors, unset = [], []
    for s in stewards():
        if s["steward"] is None:
            unset.append(s)
        elif problem := steward_problem(s["steward"]):
            errors.append(f"{s['kind']} {s['id']}: steward {problem}")
    return errors, unset


# ---- Learn feeds knowledge ------------------------------------------------------------------------------------------


def target_problem(target: str) -> str | None:
    """Why a postmortem action's `target` names nothing the team knows, or None."""
    kind, _, name = str(target).partition(":")
    if kind == "pack":
        known = [d["slug"] for d in resources.roles()["domains"]]
        return None if name in known else f"target {target} names no pack; the packs are {', '.join(sorted(known))}"
    if kind == "skill":
        known = docs.practice_names()
        return None if name in known else f"target {target} names no practice skill; the skills are {', '.join(sorted(known))}"
    return f"target {target} is neither pack:<slug> nor skill:<name>"


def open_actions(data: dict) -> list[dict]:
    """A postmortem's actions that target a pack or a skill and are not done, once it is in review or published."""
    if data.get("kind") != "postmortem" or data.get("status") not in ("in_review", "published"):
        return []
    return [a for a in data.get("actions") or [] if isinstance(a, dict) and a.get("target") and not a.get("done")]


# ---- The standards check --------------------------------------------------------------------------------------


def evidence_entries() -> list[dict]:
    """Each entry with evidence to re-read, once, in registry order: `id`, `where` (the first owner), `url`, `quote`."""
    from . import evals

    seen: set[str] = set()
    out = []
    for s in evals.standards():
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
    word split by inline markup). A JSON answer (an API's) is also read as indented JSON, the form a quote of one of
    its lines was copied from (`"sha": "...",`), whatever spacing the API sent."""
    want = normalize(quote)
    if not want:
        return False
    pages = [_TAG.sub(" ", page), _TAG.sub("", page)]
    if page.lstrip()[:1] in ("{", "["):
        try:
            pages.append(json.dumps(json.loads(page), indent=2, ensure_ascii=False))
        except ValueError:
            pass
    return any(want in normalize(x) for x in pages)


class _Fetched:
    def __init__(self, status: int, final_url: str, ctype: str, body: bytes, truncated: bool):
        self.status, self.final_url, self.ctype, self.body, self.truncated = status, final_url, ctype, body, truncated


class FetchError(Exception):
    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.status = status


# Used explicitly, never installed: an https page never redirects to plain http.
_OPENER = urllib.request.build_opener(aiddhttp.SafeRedirectHandler())


def fetch(url: str, timeout: float, max_bytes: int, deadline: float) -> _Fetched:
    """One GET, read in chunks until `max_bytes`, the request's timeout, or the run's `deadline` (monotonic)."""
    if urllib.parse.urlsplit(url).scheme not in ("https", "http"):
        raise FetchError(f"not a web address: {url}")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Language": "en",
            "Accept-Encoding": "identity",
        },
    )
    # The GitHub API allows few unauthenticated reads; a token in the environment (read-only is enough) goes to that
    # host alone, and never follows a redirect.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and urllib.parse.urlsplit(url).netloc.lower() == "api.github.com" and urllib.parse.urlsplit(url).scheme == "https":
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    stop = min(time.monotonic() + timeout, deadline)
    try:
        with _OPENER.open(req, timeout=max(0.05, min(timeout, deadline - time.monotonic()))) as resp:
            body, truncated = b"", False
            while True:
                if time.monotonic() > stop:
                    raise FetchError(f"no complete answer within {timeout:g} s" if stop < deadline else "the run's time cap was reached")
                chunk = resp.read(65536)
                if not chunk:
                    break
                body += chunk
                if len(body) > max_bytes:
                    body, truncated = body[:max_bytes], True
                    break
            encoding = resp.headers.get("Content-Encoding", "")
            body, clipped = decode_body(body, encoding, max_bytes)
            return _Fetched(resp.status, resp.geturl(), resp.headers.get("Content-Type", ""), body, truncated or clipped)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise FetchError(f"HTTP {exc.code}", exc.code) from exc
    except aiddhttp.HttpError as exc:
        raise FetchError(str(exc), exc.status or None) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise FetchError(str(getattr(exc, "reason", exc)) or type(exc).__name__) from exc


def decode_body(body: bytes, encoding: str, max_bytes: int) -> tuple[bytes, bool]:
    """The body with its `Content-Encoding` undone, at most `max_bytes` of it, and whether that cut it short. Some hosts
    compress whatever the request asks for, so gzip and deflate (zlib-wrapped or raw) are decoded; the output is
    bounded, so a small compressed body cannot expand past the limit. Another encoding is a FetchError."""
    codings = [c.strip().lower() for c in encoding.split(",") if c.strip() and c.strip().lower() != "identity"]
    for coding in reversed(codings):  # applied in order, so undone last first
        if coding in ("gzip", "x-gzip"):
            tries = [zlib.MAX_WBITS | 16]
        elif coding == "deflate":
            tries = [zlib.MAX_WBITS, -zlib.MAX_WBITS]
        else:
            raise FetchError(f"cannot decode a body sent with Content-Encoding {coding}; check the quote by hand")
        for wbits in tries:
            try:
                d = zlib.decompressobj(wbits)
                out = d.decompress(body, max_bytes + 1)
                break
            except zlib.error:
                continue
        else:
            raise FetchError(f"the {coding} body does not decode")
        if len(out) > max_bytes:
            return out[:max_bytes], True
        body = out
    return body, False


def _same_address(a: str, b: str) -> bool:
    """Two addresses for one page: the scheme, a trailing slash, the host's case, and a fragment do not count."""

    def key(u: str) -> tuple[str, str, str]:
        p = urllib.parse.urlsplit(u)
        return p.netloc.lower().removeprefix("www."), p.path.rstrip("/") or "/", p.query

    return key(a) == key(b)


def _charset(ctype: str) -> str:
    m = re.search(r"charset=([\w.-]+)", ctype, re.I)
    return m.group(1) if m else "utf-8"


def judge(e: dict, fetcher: Callable[[str], _Fetched]) -> dict:
    """One entry's row: its status, the HTTP status, the final address after a redirect, and why."""
    row = {"id": e["id"], "where": e.get("where", ""), "url": e["url"], "status": "unreachable", "http_status": None, "final_url": None, "reason": ""}
    try:
        got = fetcher(e["url"])
    except FetchError as exc:
        if exc.status in (404, 410):
            return row | {"status": "moved", "http_status": exc.status, "reason": f"HTTP {exc.status}: the page is no longer at this address"}
        return row | {"http_status": exc.status, "reason": str(exc)}
    moved = not _same_address(got.final_url, e["url"])
    row |= {"http_status": got.status, "final_url": got.final_url if moved else None}
    ctype = got.ctype.split(";", 1)[0].strip().lower()
    if ctype and not ctype.startswith(_TEXT_TYPES):
        return row | {"reason": f"cannot read {ctype} without a parser; check the quote by hand"}
    try:
        text = got.body.decode(_charset(got.ctype), errors="replace")
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
    timeout: float = TIMEOUT_SECONDS,
    max_seconds: float = MAX_SECONDS,
    max_bytes: int = MAX_BYTES,
    concurrency: int = CONCURRENCY,
    host_delay: float = HOST_DELAY_SECONDS,
    today: dt.date | None = None,
) -> dict:
    """Every entry's evidence re-read, within the bounds, as the `aidd eval standards --online --json` object."""
    concurrency = max(1, min(2, int(concurrency)))
    deadline = time.monotonic() + max(0.0, max_seconds)
    guard = threading.Lock()
    hosts: dict[str, threading.Lock] = {}
    last: dict[str, float] = {}

    def capped(url: str) -> _Fetched:
        raise FetchError(f"not fetched: the run's time cap of {max_seconds:g} s was reached")

    def one(e: dict) -> dict:
        host = urllib.parse.urlsplit(e["url"]).netloc.lower()
        with guard:
            lock = hosts.setdefault(host, threading.Lock())
        with lock:  # one request at a time per host, `host_delay` apart
            wait = last.get(host, 0.0) + host_delay - time.monotonic()
            if wait > 0 and time.monotonic() + wait < deadline:
                time.sleep(wait)
            if time.monotonic() >= deadline:
                return judge(e, capped)
            try:
                return judge(e, lambda url: fetch(url, timeout, max_bytes, deadline))
            finally:
                last[host] = time.monotonic()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, entries))
    counts = {s: sum(1 for r in results if r["status"] == s) for s in STATUSES}
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_on": (today or dt.date.today()).isoformat(),
        "limits": {"timeout_seconds": timeout, "max_seconds": max_seconds, "max_bytes": max_bytes, "concurrency": concurrency},
        "counts": counts,
        "results": results,
    }


def exit_code(result: dict, strict: bool) -> int:
    """1 only with `strict` and an entry moved or missing, or a library tool with a newer major release: an
    unreachable page or feed says nothing about the standard."""
    newer = any(r["status"] == "newer_major" for r in result.get("releases", []))
    return 1 if strict and (result["counts"]["moved"] or result["counts"]["missing"] or newer) else 0


# ---- The release-feed check -----------------------------------------------------------------------------------------
#
# Each library standard with a `tool` names the feed its releases are published on. The weekly run reads the newest
# release there and flags one whose major is newer than the standard's `checked_version`: a person then reads the
# release notes and updates the standard. Before 1.0, a minor release counts as a major one (semantic versioning lets
# 0.y break). A pre-release never counts. A language toolchain has its own official feed, which marks its LTS releases
# where it has them, so a `latest_lts` standard is not flagged by a newer release that is not LTS. The same bounds as
# the evidence check apply, and the check edits nothing.

# Each feed, by the name SECURITY.md's "Data handling" gives it.
FEED_NAMES = {
    "pypi": "PyPI",
    "npm": "npm",
    "crates": "crates.io",
    "maven": "Maven Central",
    "nuget": "NuGet",
    "go": "the Go module proxy",
    "github": "GitHub releases",
    "go.dev": "go.dev",
    "nodejs.org": "nodejs.org",
    "dotnet": "the .NET release index",
    "adoptium": "Adoptium",
    "python.org": "python.org",
}
FEEDS = tuple(FEED_NAMES)
# Go 1.x and Python 3.x name each major release by its minor number: Go 1.28, Python 3.15.
_MINOR_IS_MAJOR = frozenset({"go.dev", "python.org"})
LTS = "latest_lts"
RELEASE_STATUSES = ("ok", "newer_major", "unreachable")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*")


def feed_url(registry: str, package: str) -> str:
    """The one address that answers with the newest release of `package` on `registry`. Each path segment is encoded
    whole, so a name can never reach another path on the feed's host (the schema also limits each name's form)."""

    def seg(x: str) -> str:
        return urllib.parse.quote(x, safe="")

    if registry == "pypi":
        return f"https://pypi.org/pypi/{seg(package)}/json"
    if registry == "npm":
        # A scoped package keeps its `@`, as the registry expects: `@scope%2Fname`.
        scope, _, name = package.rpartition("/")
        prefix = f"@{seg(scope.removeprefix('@'))}%2F" if scope else ""
        return f"https://registry.npmjs.org/{prefix}{seg(name)}/latest"
    if registry == "crates":
        return f"https://crates.io/api/v1/crates/{seg(package)}"
    if registry == "maven":
        group, _, artifact = package.partition(":")
        return f"https://repo1.maven.org/maven2/{'/'.join(seg(g) for g in group.split('.'))}/{seg(artifact)}/maven-metadata.xml"
    if registry == "nuget":
        return f"https://api.nuget.org/v3-flatcontainer/{seg(package.lower())}/index.json"
    if registry == "go":
        # The module proxy's case encoding: each capital letter becomes `!` and its lower case.
        parts = [re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), seg(p)) for p in package.split("/")]
        return f"https://proxy.golang.org/{'/'.join(parts)}/@latest"
    if registry == "github":
        owner, _, repo = package.partition("/")
        return f"https://api.github.com/repos/{seg(owner)}/{seg(repo)}/releases/latest"
    # The official toolchain feeds: one fixed address each, whatever the package names.
    if registry == "go.dev":
        return "https://go.dev/dl/?mode=json"
    if registry == "nodejs.org":
        return "https://nodejs.org/dist/index.json"
    if registry == "dotnet":
        return "https://builds.dotnet.microsoft.com/dotnet/release-metadata/releases-index.json"
    if registry == "adoptium":
        return "https://api.adoptium.net/v3/info/available_releases"
    if registry == "python.org":
        return "https://www.python.org/api/v2/downloads/release/?is_published=true"
    raise ValueError(f"unknown release feed {registry!r}; the feeds are {', '.join(FEEDS)}")


# A pre-release marker after the version's numbers: `1.0.0-M1`, `4.0.0.RC1`, `2.0.0a1`, `1.0.dev3`, `6.0.0-preview.1`,
# `25-ea`. A marker is a whole word, so `33.0.0-jre`, `1.0.post1`, and `5.3.0.Final` are stable.
_PRE_RELEASE = re.compile(r"(?i)(?:^|[^a-z])(?:a|b|c|alpha|beta|rc|cr|m|milestone|pre|preview|dev|snapshot|ea|canary|nightly|next|insiders)(?=[^a-z]|$)")


def is_prerelease(version: object) -> bool:
    """Whether a version names a pre-release (a milestone, a release candidate, an alpha, a beta, a preview, a dev or
    nightly build, a snapshot, or an early-access build). The check never takes one as the newest release."""
    text = re.sub(r"^(?:v|go)(?=[0-9])", "", str(version or "").strip(), flags=re.I)
    m = _VERSION.match(text)
    return bool(_PRE_RELEASE.search(text[m.end() :] if m else text))


def _plain(version: object) -> str | None:
    m = _VERSION.search(str(version or ""))
    return m.group(0) if m else None


def _stable(version: object) -> str | None:
    """A version's plain numbers, or None for a pre-release."""
    return None if is_prerelease(version) else _plain(version)


def _newest(versions: list) -> str | None:
    found = [v for v in (_stable(x) for x in versions if isinstance(x, str)) if v]
    return max(found, key=_version_key, default=None)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def latest_version(registry: str, body: str, policy: str | None = None, package: str | None = None) -> str | None:
    """The newest stable release in a feed's answer, as plain numbers (`1.2.3`), or None. A pre-release never counts:
    where the feed lists every release, the newest stable one is read; where it names one, a pre-release reads as none.
    A toolchain feed that marks its LTS releases gives the newest LTS one for a `latest_lts` policy."""
    if registry in _TOOLCHAINS:
        return _TOOLCHAINS[registry](json.loads(body), policy == LTS, package)
    if registry == "maven":
        listed = _newest(re.findall(r"<version>\s*([^<\s]+)\s*</version>", body))
        m = re.search(r"<release>\s*([^<\s]+)\s*</release>", body)
        return listed or (_stable(m.group(1)) if m else None)
    if registry == "pypi":
        # PyPI's answer lists every release after `info` and can pass the byte limit: `info` comes first, so read it there.
        m = re.search(r'"info"\s*:\s*\{.*?"version"\s*:\s*"([^"]+)"', body, re.S)
        if m and not is_prerelease(m.group(1)):
            return _plain(m.group(1))
        try:
            releases = json.loads(body).get("releases")
        except (ValueError, AttributeError):
            return None
        return _newest(list(releases)) if isinstance(releases, dict) else None
    data = json.loads(body)
    if not isinstance(data, dict):
        return None
    if registry == "npm":
        return _stable(data.get("version"))
    if registry == "crates":
        return _stable((data.get("crate") or {}).get("max_stable_version"))
    if registry == "nuget":
        versions = data.get("versions")
        return _newest(versions) if isinstance(versions, list) else None
    if registry == "go":
        return _stable(data.get("Version"))
    if registry == "github":
        return _stable(data.get("tag_name"))
    raise ValueError(f"unknown release feed {registry!r}")


def _go(data: object, lts: bool, package: str | None) -> str | None:
    """go.dev/dl: the supported releases, newest first, each marked `stable`. Go has no LTS line."""
    rows = data if isinstance(data, list) else []
    return _newest([r.get("version") for r in rows if isinstance(r, dict) and r.get("stable") is True])


def _node(data: object, lts: bool, package: str | None) -> str | None:
    """nodejs.org/dist/index.json: every release, each with `lts` false or its line's code name."""
    rows = [r for r in (data if isinstance(data, list) else []) if isinstance(r, dict)]
    return _newest([r.get("version") for r in rows if r.get("lts") or not lts])


def _dotnet(data: object, lts: bool, package: str | None) -> str | None:
    """The .NET release index: one row per channel, with its release type (`lts` or `sts`) and support phase. A
    channel in `preview` or `go-live` has shipped no stable release."""
    field = "latest-sdk" if package == "sdk" else "latest-runtime"
    rows = (data.get("releases-index") if isinstance(data, dict) else None) or []
    rows = [r for r in rows if isinstance(r, dict) and r.get("support-phase") not in ("preview", "go-live")]
    return _newest([r.get(field) for r in rows if r.get("release-type") == "lts" or not lts])


def _adoptium(data: object, lts: bool, package: str | None) -> str | None:
    """Adoptium's available releases: the newest feature release and the newest LTS release, as numbers."""
    value = data.get("most_recent_lts" if lts else "most_recent_feature_release") if isinstance(data, dict) else None
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _python(data: object, lts: bool, package: str | None) -> str | None:
    """python.org's release list: each one named `Python X.Y.Z` and marked `pre_release`. CPython has no LTS line."""
    rows = [r for r in (data if isinstance(data, list) else []) if isinstance(r, dict) and r.get("is_published") and not r.get("pre_release")]
    names = [re.fullmatch(r"Python ([0-9][^\s]*)", str(r.get("name") or "")) for r in rows if r.get("version") == 3]
    return _newest([m.group(1) for m in names if m])


_TOOLCHAINS: dict[str, Callable[[object, bool, str | None], str | None]] = {
    "go.dev": _go,
    "nodejs.org": _node,
    "dotnet": _dotnet,
    "adoptium": _adoptium,
    "python.org": _python,
}


def _major(version: str, depth: int = 1) -> tuple[int, ...]:
    parts = (*_version_key(version), 0, 0)
    return parts[: depth + 1] if not parts[0] else parts[:depth]


def newer_major(checked: str, latest: str, registry: str | None = None) -> bool:
    """Whether `latest` is a newer major release than `checked` (before 1.0, a newer minor). On go.dev and python.org a
    major release is a new minor number, such as Go 1.28 or Python 3.15."""
    a, b = _plain(checked), _plain(latest)
    depth = 2 if registry in _MINOR_IS_MAJOR else 1
    return bool(a and b) and _major(str(b), depth) > _major(str(a), depth)


def release_entries() -> list[dict]:
    """Each active library standard whose tool has a release feed, with the version it was checked at."""
    from . import standards

    out = []
    for s in sorted(standards.library().values(), key=lambda x: x.id):
        tool = s.meta.get("tool")
        if not tool or not s.active:
            continue
        out.append(
            {
                "id": s.id,
                "tool": tool["name"],
                "registry": tool["registry"],
                "url": feed_url(tool["registry"], tool["package"]),
                "checked_version": s.meta["checked_version"],
                "version_policy": s.meta.get("version_policy"),
                "package": tool["package"],
            }
        )
    return out


def check_releases(
    entries: list[dict],
    *,
    fetcher: Callable[[str], _Fetched] | None = None,
    timeout: float = TIMEOUT_SECONDS,
    max_seconds: float = MAX_SECONDS,
    max_bytes: int = MAX_BYTES,
    host_delay: float = HOST_DELAY_SECONDS,
) -> list[dict]:
    """Each entry's row: `ok`, `newer_major` (with the newest release), or `unreachable` (no answer to judge)."""
    deadline = time.monotonic() + max(0.0, max_seconds)
    get = fetcher or (lambda url: fetch(url, timeout, max_bytes, deadline))
    last: dict[str, float] = {}
    rows = []
    for e in entries:
        row = {k: e[k] for k in ("id", "tool", "registry", "url", "checked_version")} | {"latest": None, "status": "unreachable", "reason": ""}
        host = urllib.parse.urlsplit(e["url"]).netloc.lower()
        wait = last.get(host, 0.0) + host_delay - time.monotonic()
        if fetcher is None and wait > 0 and time.monotonic() + wait < deadline:
            time.sleep(wait)
        if time.monotonic() >= deadline:
            rows.append(row | {"reason": f"not fetched: the run's time cap of {max_seconds:g} s was reached"})
            continue
        try:
            got = get(e["url"])
            body = got.body.decode(_charset(got.ctype), errors="replace")
            latest = latest_version(e["registry"], body, e.get("version_policy"), e.get("package"))
        except FetchError as exc:
            rows.append(row | {"reason": str(exc)})
            continue
        except (ValueError, LookupError, AttributeError, TypeError, RecursionError) as exc:
            rows.append(row | {"reason": f"the feed's answer does not read: {exc}"})
            continue
        finally:
            last[host] = time.monotonic()
        if latest is None:
            rows.append(row | {"reason": "the feed names no stable release"})
        elif newer_major(e["checked_version"], latest, e["registry"]):
            rows.append(
                row | {"latest": latest, "status": "newer_major", "reason": f"{e['tool']} {latest} is out; the standard was checked at {e['checked_version']}"}
            )
        else:
            rows.append(row | {"latest": latest, "status": "ok"})
    return rows


def markdown(result: dict) -> str:
    """The report as Markdown (it reads as text too): what to fix, then the counts and what each status asks for."""
    c = result["counts"]
    lines = [f"# Standards evidence, re-read online on {result['checked_on']}", ""]
    rows = [r for r in result["results"] if r["status"] != "ok" or r["final_url"]]
    if rows:
        lines += ["| Status | Entry | Evidence | Why |", "| --- | --- | --- | --- |"]
        order = {s: i for i, s in enumerate(("moved", "missing", "ok", "unreachable"))}
        for r in sorted(rows, key=lambda r: order[r["status"]]):
            why = str(r["reason"]).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r['status']} | `{r['id']}` ({r['where']}) | <{r['url']}> | {why} |")
        lines.append("")
    total = len(result["results"])
    lines.append(f"{total} entries with evidence: {c['ok']} ok, {c['moved']} moved, {c['missing']} missing, {c['unreachable']} unreachable.")
    releases = result.get("releases") or []
    if releases:
        flagged = [r for r in releases if r["status"] != "ok"]
        if flagged:
            lines += ["", "| Release | Library standard | Tool | Checked | Latest | Why |", "| --- | --- | --- | --- | --- | --- |"]
            for r in sorted(flagged, key=lambda r: RELEASE_STATUSES.index(r["status"])):
                why = str(r["reason"]).replace("|", "\\|").replace("\n", " ")
                status = r["status"].replace("_", " ")
                lines.append(f"| {status} | `{r['id']}` | {r['tool']} | {r['checked_version']} | {r['latest'] or '—'} | {why} |")
        n = {s: sum(1 for r in releases if r["status"] == s) for s in RELEASE_STATUSES}
        lines += ["", f"{len(releases)} library tools on their release feeds: {n['ok']} ok, {n['newer_major']} newer major, {n['unreachable']} unreachable."]
    lines += [
        "",
        "moved: find the page's new address and update `evidence.url`. missing: re-read the source, since its edition may have changed, "
        "and update the entry with a new quote and date. Either is a change to schemas/roles.json that its steward reviews. "
        "unreachable: no answer to judge (a network error, a refusal, a type that is not text, or a limit of this run). It says nothing about the standard. "
        "newer major: read the tool's release notes, then update the library standard's `checked_version`, `pin`, and `checked` date. "
        "This check read the registry and the library and changed nothing.",
    ]
    return "\n".join(lines) + "\n"
