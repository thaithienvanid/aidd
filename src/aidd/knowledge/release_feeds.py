"""The release check: the release feed of each library standard's tool (PyPI, npm, crates.io, Maven Central, NuGet, the
Go module proxy, or GitHub releases; for a language toolchain, go.dev, nodejs.org, the .NET release index, Adoptium, or
python.org), and a flag on a newer major stable release than its `checked_version`. A `latest_lts` standard is judged
against the newest LTS release where the feed marks one.

Each library standard with a `tool` names the feed its releases are published on. The weekly run reads the newest
release there and flags one whose major is newer than the standard's `checked_version`: a person then reads the
release notes and updates the standard. Before 1.0, a minor release counts as a major one (semantic versioning lets
0.y break). A pre-release never counts. A language toolchain has its own official feed, which marks its LTS releases
where it has them, so a `latest_lts` standard is not flagged by a newer release that is not LTS. The same bounds as
the evidence check apply, and the check edits nothing.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from collections.abc import Callable

from aidd.knowledge import bounded_fetch

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
    from aidd.knowledge import standards

    out = []
    for s in sorted(standards.standards_library().values(), key=lambda x: x.id):
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
    fetcher: Callable[[str], bounded_fetch.Fetched] | None = None,
    timeout_seconds: float = bounded_fetch.TIMEOUT_SECONDS,
    max_seconds: float = bounded_fetch.MAX_SECONDS,
    max_bytes: int = bounded_fetch.MAX_BYTES,
    host_delay_seconds: float = bounded_fetch.HOST_DELAY_SECONDS,
) -> list[dict]:
    """Each entry's row: `ok`, `newer_major` (with the newest release), or `unreachable` (no answer to judge)."""
    deadline = time.monotonic() + max(0.0, max_seconds)
    get = fetcher or (lambda url: bounded_fetch.fetch(url, timeout_seconds, max_bytes, deadline))
    last: dict[str, float] = {}
    rows = []
    for e in entries:
        row = {k: e[k] for k in ("id", "tool", "registry", "url", "checked_version")} | {"latest": None, "status": "unreachable", "reason": ""}
        host = urllib.parse.urlsplit(e["url"]).netloc.lower()
        wait = last.get(host, 0.0) + host_delay_seconds - time.monotonic()
        if fetcher is None and wait > 0 and time.monotonic() + wait < deadline:
            time.sleep(wait)
        if time.monotonic() >= deadline:
            rows.append(row | {"reason": f"not fetched: the run's time cap of {max_seconds:g} s was reached"})
            continue
        try:
            got = get(e["url"])
            body = got.body.decode(bounded_fetch.charset(got.ctype), errors="replace")
            latest = latest_version(e["registry"], body, e.get("version_policy"), e.get("package"))
        except bounded_fetch.FetchError as exc:
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
