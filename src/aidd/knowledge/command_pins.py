"""The command pins: each exact tool version that a pack or a practice skill names in a command, such as
`uvx checkov==3.3.20` or `npx @lhci/cli@0.15.1`. A pack or a skill cannot assume a project's lock file, so it pins the
tool where it names it, and this reader is the one owner of that fact: the packs' data (schemas/roles.json's `domains`,
which schemas/packs.json holds) and the practice skills' text (SKILL.md and its references) are read, and nothing is
listed twice.

The registry comes from the command's form, never from a second list: `uvx`, `uv tool run`, and `pipx run` read PyPI,
`npx`, `npm exec`, and `pnpm dlx` read npm, and `go install` and `go run` read the Go module proxy. A package spec alone in
backticks reads the same way: `name==1.2.3` is PyPI and `name@1.2.3` is npm. A command with no exact version (`@latest`,
`<version>`, none) is not a pin. The online check (`aidd eval standards --online`) compares each pin with its registry's
newest release the way it does a library standard, through release_feeds. Versions of a binary with no such command form
(a GitHub release, a Docker image) are not read.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from aidd.kernel import resources
from aidd.knowledge import release_feeds, team_registry

PIN_PREFIX = "pin:"
_RUNNERS = {
    "uvx": "pypi",
    "uv tool run": "pypi",
    "pipx run": "pypi",
    "npx": "npm",
    "npm exec": "npm",
    "pnpm dlx": "npm",
    "go install": "goproxy",
    "go run": "goproxy",
}
# A runner word, then the rest of its command: up to a backtick, a line end, or a shell separator.
_COMMAND = re.compile(r"(?<![\w./-])(" + "|".join(re.escape(r) for r in sorted(_RUNNERS, key=len, reverse=True)) + r")(?![\w-])([^`\n;|&]*)")
_BARE_SPEC = re.compile(r"`([^`\s]{1,200}?(?:==|@)v?\d[^`\s]{0,60})`")
_SOURCE_OPTIONS = frozenset({"--from", "-p", "--package"})
_VALUE_OPTIONS = frozenset({"--with", "-w", "--python", "--registry"})
_VERSION = re.compile(r"v?\d[\w.+-]*")
_NAMES = {
    "pypi": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*"),
    "npm": re.compile(r"(?:@[a-z0-9~][a-z0-9._~-]*/)?[a-z0-9~][a-z0-9._~-]*"),
    "goproxy": re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*(?:/[A-Za-z0-9._~-]+)+"),
}
_CODE_HOSTS = frozenset({"github.com", "gitlab.com", "bitbucket.org", "golang.org"})


def _go_module(path: str) -> str:
    """The module that holds a package path, since the Go proxy answers for modules: up to a major-version segment
    (`/v2`), else the first three segments on a code host (`github.com/owner/repo`)."""
    parts = path.split("/")
    for i, part in enumerate(parts):
        if i >= 2 and re.fullmatch(r"v[2-9]\d*", part):
            return "/".join(parts[: i + 1])
    return "/".join(parts[:3]) if parts[0] in _CODE_HOSTS else path


def _pin(spec: str, registry: str) -> dict | None:
    """One package spec (`name==1.2.3`, `name@1.2.3`, `@scope/name@1.2.3`, `module/path@v1.2.3`) as a pin, or None when
    it carries no exact version or does not fit its registry."""
    spec = spec.strip("()\"'").rstrip(").,;:\"'")
    if registry == "pypi":
        spec = re.sub(r"\[[^\]]*\]", "", spec)
    name, _, version = spec.rpartition("==" if registry == "pypi" and "==" in spec else "@")
    if not (_VERSION.fullmatch(version) and _NAMES[registry].fullmatch(name)):
        return None
    if registry == "goproxy":
        name = _go_module(name)
        if not version.startswith("v"):
            return None
    return {"tool": name, "registry": registry, "version": version}


def _specs(command: str) -> list[str]:
    """The package specs a runner's command names: the value of each `--from`, `-p`, or `--package`, else its first
    word that is not an option (the one it runs)."""
    words = command.split()
    found: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if not word.startswith("-"):
            return found or [word]
        option, equals, value = word.partition("=")
        if option in _SOURCE_OPTIONS and equals:
            found.append(value)
        elif option in _SOURCE_OPTIONS and i < len(words):
            found.append(words[i])
            i += 1
        elif option in _VALUE_OPTIONS and not equals:
            i += 1
    return found


def read_pins(text: str) -> list[dict]:
    """The pins in a text, as {tool, registry, version}, in reading order."""
    found = []
    for m in _COMMAND.finditer(text):
        found += [p for spec in _specs(m.group(2)) if (p := _pin(spec, _RUNNERS[m.group(1)]))]
    found += [p for spec in _BARE_SPEC.findall(text) if (p := _pin(spec, "pypi" if "==" in spec else "npm"))]
    return found


def _strings(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _sources() -> Iterator[tuple[str, str]]:
    """Each place that may name a pin, as (where, text): a pack's data, and a practice skill's file. The team skill
    (`aidd-team`) is left out: its references are written from the extensions, which carry their own `pin`."""
    for pack in resources.load_json("roles.json").get("domains", []):  # a registry with no packs names no pin
        for text in _strings(pack):
            yield f"pack {pack.get('slug', '?')}", text
    for folder in team_registry.skill_folders():
        for path in sorted(folder.rglob("*.md")):
            rel = path.relative_to(folder.parent)
            if rel.parts[0] != "aidd-team":
                yield "skill " + (rel.parts[0] if path.name == "SKILL.md" else rel.as_posix()), path.read_text(encoding="utf-8")


def pinned_commands() -> list[dict]:
    """Every pin once, by registry, tool, and version, as {tool, registry, version, where}: `where` lists each pack and
    skill file that names it. In tool order."""
    found: dict[tuple[str, str, str], set[str]] = {}
    for where, text in _sources():
        for p in read_pins(text):
            found.setdefault((p["tool"], p["registry"], p["version"]), set()).add(where)
    return [{"tool": t, "registry": r, "version": v, "where": sorted(w)} for (t, r, v), w in sorted(found.items())]


def pinned_command_lines() -> list[str]:
    """What `aidd eval standards` prints, offline: the count, then each pin with its registry and where it is named."""
    pins = pinned_commands()
    lines = [f"{len(pins)} pinned commands in the packs and practice skills (`--online` compares each with its registry's newest release):"]
    lines += [f"- {p['tool']} {p['version']} ({release_feeds.FEED_NAMES[p['registry']]}); {', '.join(p['where'])}" for p in pins]
    return lines


def pinned_command_entries() -> list[dict]:
    """The pins as the release check reads them (release_feeds.check_releases): one entry each, its id led by `pin:`."""
    return [
        {
            "id": f"{PIN_PREFIX}{p['tool']}@{p['version']}",
            "tool": p["tool"],
            "registry": p["registry"],
            "url": release_feeds.feed_url(p["registry"], p["tool"]),
            "checked_version": p["version"],
            "version_policy": None,
            "package": p["tool"],
            "where": ", ".join(p["where"]),
        }
        for p in pinned_commands()
    ]
