"""The domain packs a repository installs as project skills without the aidd-team plugin, and the hints when one is missing.

Each skill in `.claude/skills/` puts its name and description in every session's context, so `aidd init --aidd-team` and
`aidd upgrade` write only the packs the repository calls for (`choose`). A pack is called for by a manifest's
dependencies (`detection`), by a risk area `aidd risk` matches on a tracked path (each pack's `areas` in
schemas/packs.json, so the risk rules own which paths are which area), by `project.compliance`, by
`agents.domain_packs`, or by a past install. The aidd-packs plugin carries every pack, and a person enables it in the projects
that call for one; with the aidd-team plugin on, the hints and the doctor's warning only name it (`pack_hint`, `doctor_lines`).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path

from aidd import config, risk
from aidd.kernel import documents, git, resources
from aidd.setup import detection

TEAM_PREFIX = "aidd-"  # installed names: an agent `aidd-developer`, a skill `aidd-code-review`, a command `/aidd-implement`
SKILLS_DIR = ".claude/skills"
NEXT_STEP = "name it in agents.domain_packs in .aidd/config.yaml, then run `aidd upgrade --yes`"
PACKS_COMMAND = f"run `claude plugin install {config.PACKS_PLUGIN}@{config.MARKETPLACE} --scope project`"  # the plugin's packs, for this project only


def packs() -> list[dict]:
    """schemas/packs.json: every domain pack, each named by its skill's folder (`slug`)."""
    return list(resources.load_json("packs.json"))


def pack_names() -> list[str]:
    """Every domain pack, by the name of its skill's folder. Every other team skill is a practice skill."""
    return sorted(str(p["slug"]) for p in packs())


def area_packs() -> dict[str, list[str]]:
    """Each risk area a pack names in its `areas`, with the packs it brings."""
    out: dict[str, list[str]] = {}
    for p in packs():
        for area in p.get("areas", []):
            out.setdefault(str(area), []).append(str(p["slug"]))
    return out


def installed(root: Path) -> list[str]:
    """The domain packs `.claude/skills/` holds."""
    return [p for p in pack_names() if (root / SKILLS_DIR / f"{TEAM_PREFIX}{p}" / "SKILL.md").is_file()]


def _config(root: Path) -> config.Config | None:
    try:
        return config.load_file(config.CONFIG_PATH, str(root))
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError):
        return None


def _ignore_file_is_regular(root: Path) -> bool:
    """Whether the repository's `.gitignore` is absent or a regular file: git opens it itself and blocks on a pipe."""
    try:
        return stat.S_ISREG(os.lstat(root / ".gitignore").st_mode)
    except FileNotFoundError:
        return True
    except OSError:
        return False


def _repo_paths(root: Path) -> list[str]:
    """Every path git tracks or would track (not ignored), at any depth, each once; none outside a repository. Where
    `.gitignore` is no regular file, git is never asked to read it, so only the tracked paths are listed."""
    flags = ["--cached", "--others", "--exclude-standard"] if _ignore_file_is_regular(root) else ["--cached"]
    out = git.run(["ls-files", "-z", *flags], str(root), check=False)
    return list(dict.fromkeys(p for p in out.split("\0") if p))


@dataclass
class Choice:
    """The packs to install, why each one, and what was read to choose them."""

    packs: list[str]
    why: dict[str, list[str]] = field(default_factory=dict)
    manifests: int = 0
    paths: int = 0


def choose(root: Path, found: dict | None = None) -> Choice:
    """The packs `aidd init --aidd-team` and `aidd upgrade` write, with the reason for each. `found` is `detection.detect(root)`,
    when the caller already has it, so detection runs once."""
    found = found if found is not None else detection.detect(root)
    cfg = _config(root)
    known = set(pack_names())
    why: dict[str, list[str]] = {}

    def add(pack: str, reason: str) -> None:
        if pack in known and reason not in why.setdefault(pack, []):
            why[pack].append(reason)

    for s in found["stacks"]:
        for p in s["packs"]:
            add(p, s["manifest"])
    rs, paths = risk.rule_set(cfg), _repo_paths(root)
    for area, brought in area_packs().items():
        if area not in rs.areas:
            continue
        one = replace(rs, areas={area: rs.areas[area]})  # `aidd risk`'s own matcher, for this area alone, up to its first path
        if first := next((p for p in paths if risk.areas_of(one, p)), None):
            for p in brought:
                add(p, f"the {area} area: {first}")
    if pack := ((config.effective_project(cfg) or {}).get("compliance") or {}).get("pack"):
        add(str(pack), "project.compliance")
    for p in (cfg.get("agents", "domain_packs", default=[]) if cfg else []) or []:
        add(str(p), "agents.domain_packs")
    for p in installed(root):
        add(p, "installed before")
    return Choice(sorted(why), why, len(found["stacks"]), len(paths))


def install_note(choice: Choice) -> str:
    """What `aidd init --aidd-team` says about the packs it wrote: each with its reason, or what it read when it found none."""
    if choice.packs:
        held = ", ".join(f"{p} ({'; '.join(choice.why[p])})" for p in choice.packs)
        return f"note     {SKILLS_DIR}/ holds the domain packs {held}; to add another, {NEXT_STEP}"
    manifests = "no manifest" if not choice.manifests else f"{choice.manifests} manifest{'s' if choice.manifests > 1 else ''}"
    return (
        f"note     {SKILLS_DIR}/ holds no domain pack: aidd read {manifests} and {choice.paths} files, and none names a pack's "
        f"dependency or a risk area a pack covers; to add one, {NEXT_STEP}"
    )


def team_plugin_enabled(root: Path) -> bool:
    """Whether Claude Code enables the aidd-team plugin here, which carries the roles, the commands, and the practice skills."""
    return f"aidd-team@{config.MARKETPLACE}" in config.plugins_enabled(root)


def packs_plugin_enabled(root: Path) -> bool:
    """Whether Claude Code enables the aidd-packs plugin here, which carries every pack."""
    return f"{config.PACKS_PLUGIN}@{config.MARKETPLACE}" in config.plugins_enabled(root)


def _team_files_here(root: Path) -> bool:
    """Whether `aidd init --aidd-team` wrote the team as project skills here (a practice skill is always among them)."""
    return any(p.parent.name not in pack_names() for p in (root / SKILLS_DIR).glob(f"{TEAM_PREFIX}*/SKILL.md"))


def pack_hint(root: Path, areas: list[str]) -> list[str]:
    """`aidd risk --paths`'s hints for the packs the areas it matched bring, where the team is installed here (the aidd-team plugin,
    or project files): the pack to load by name, so loading never depends on a skill listing that may hold no description, and
    a pack that is not installed, with the step that adds it. Nothing without the team, or when no matched area brings a pack."""
    plugin = team_plugin_enabled(root)
    if not (plugin or _team_files_here(root)):
        return []
    by_area = area_packs()
    called = {p: a for a in reversed(areas) for p in by_area.get(a, [])}
    if plugin:
        have = set(pack_names()) if packs_plugin_enabled(root) else set()
        name = lambda p: f"{config.PACKS_PLUGIN}:{p}"  # noqa: E731
        add = PACKS_COMMAND
    else:
        have, name, add = set(installed(root)), lambda p: f"{TEAM_PREFIX}{p}", NEXT_STEP
    out = []
    for found, text in (
        (True, "load the domain pack {} with the Skill tool before you edit it"),
        (False, "the domain pack {} is not installed, so the roles work without it; to add it, " + add),
    ):
        named = ", ".join(f"`{name(p)}` (the {a} area)" for p, a in sorted(called.items()) if (p in have) is found)
        out += [text.format(named)] if named else []
    return out


def doctor_lines(root: Path) -> list[tuple[str, str]]:
    """`aidd doctor`'s warning when the repository calls for a pack that is not here: `.claude/skills/` lacks it, where the team is
    installed as project files, or the aidd-packs plugin is not enabled, where the aidd-team plugin is."""
    plugin = team_plugin_enabled(root)
    if (plugin and packs_plugin_enabled(root)) or not (plugin or _team_files_here(root)):
        return []
    choice = choose(root)
    missing = [p for p in choice.packs if plugin or p not in set(installed(root))]
    if not missing:
        return []
    named = ", ".join(f"{p} ({'; '.join(choice.why[p])})" for p in missing)
    if plugin:
        step = f"which the {config.PACKS_PLUGIN} plugin carries and is not enabled here: {PACKS_COMMAND}"
    else:
        step = f"which {SKILLS_DIR}/ lacks: run `aidd upgrade --yes`"
    return [("warning", f"the repository calls for the domain packs {named}, {step}")]


def packs_table() -> str:
    """The roles reference's table of every domain pack, so a domain no area names is still findable."""
    rows = "".join(f"| `{p['slug']}` | {p['name']} | {p['signal']} |\n" for p in sorted(packs(), key=lambda p: p["slug"]))
    return (
        "\n## Domain packs\n\n"
        f"`{SKILLS_DIR}/` holds the packs this repository calls for. To add another, {NEXT_STEP}.\n\n"
        "| Pack | Covers | Signal |\n| --- | --- | --- |\n" + rows
    )
