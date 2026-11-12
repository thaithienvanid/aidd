"""The domain skills a repository installs as project skills without the aidd-team plugin, and the hints when one is missing.

Each skill in `.claude/skills/` puts its name and description in every session's context, so `aidd init --aidd-team` and
`aidd upgrade` write only the domain skills the repository calls for (`choose`). A domain skill is called for by a manifest's
dependencies (`detection`), by a risk area `aidd risk` matches on a tracked path (each domain skill's `areas` in
schemas/packs.json, so the risk rules own which paths are which area), by `project.compliance`, by
`agents.domain_skills`, or by a past install. The aidd-domains plugin carries every domain skill, and a person enables it in the projects
that call for one; with the aidd-team plugin on, the hint and the doctor's warning only name it (`domain_skill_reading`, `doctor_lines`).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path

from aidd import config, risk
from aidd.kernel import documents, git, regular_files, resources
from aidd.setup import detection

TEAM_PREFIX = "aidd-"  # installed names: an agent `aidd-developer`, a skill `aidd-code-review`, a command `/aidd-implement`
SKILLS_DIR = ".claude/skills"
NEXT_STEP = "name it in agents.domain_skills in .aidd/config.yaml, then run `aidd upgrade --yes`"
PACKS_COMMAND = f"run `claude plugin install {config.PACKS_PLUGIN}@{config.MARKETPLACE} --scope project`"  # the plugin's packs, for this project only


def packs() -> list[dict]:
    """schemas/packs.json: every domain skill, each named by its skill's folder (`slug`)."""
    return list(resources.load_json("packs.json"))


def pack_names() -> list[str]:
    """Every domain skill, by the name of its skill's folder. Every other team skill is a practice skill."""
    return sorted(str(p["slug"]) for p in packs())


def area_packs() -> dict[str, list[str]]:
    """Each risk area a domain skill names in its `areas`, with the domain skills it brings."""
    out: dict[str, list[str]] = {}
    for p in packs():
        for area in p.get("areas", []):
            out.setdefault(str(area), []).append(str(p["slug"]))
    return out


def installed(root: Path) -> list[str]:
    """The domain skills `.claude/skills/` holds."""
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
    `.gitignore` is no regular file, git is never asked to read it, so only the tracked paths are listed. A dry run adds the
    files it would write, so it chooses as the real run does."""
    flags = ["--cached", "--others", "--exclude-standard"] if _ignore_file_is_regular(root) else ["--cached"]
    out = git.run(["ls-files", "-z", *flags], str(root), check=False)
    return list(dict.fromkeys([*(p for p in out.split("\0") if p), *regular_files.held_paths()]))


@dataclass
class Choice:
    """The domain skills to install, why each one, and what was read to choose them."""

    packs: list[str]
    why: dict[str, list[str]] = field(default_factory=dict)
    manifests: int = 0
    paths: int = 0


def choose(root: Path, found: dict | None = None) -> Choice:
    """The domain skills `aidd init --aidd-team` and `aidd upgrade` write, with the reason for each. `found` is `detection.detect(root)`,
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
    for entry in (cfg.get("agents", "domain_skills", default=[]) if cfg else []) or []:  # a name, or a name with the globs that narrow it
        add(str(entry if isinstance(entry, str) else entry["name"]), "agents.domain_skills")
    for p in installed(root):
        add(p, "installed before")
    return Choice(sorted(why), why, len(found["stacks"]), len(paths))


def install_note(choice: Choice) -> str:
    """What `aidd init --aidd-team` says about the domain skills it wrote: each with its reason, or what it read when it found none."""
    if choice.packs:
        held = ", ".join(f"{p} ({'; '.join(choice.why[p])})" for p in choice.packs)
        return f"note     {SKILLS_DIR}/ holds the domain skills {held}; to add another, {NEXT_STEP}"
    manifests = "no manifest" if not choice.manifests else f"{choice.manifests} manifest{'s' if choice.manifests > 1 else ''}"
    return (
        f"note     {SKILLS_DIR}/ holds no domain skill: aidd read {manifests} and {choice.paths} files, and none names a domain skill's "
        f"dependency or a risk area a domain skill covers; to add one, {NEXT_STEP}"
    )


def team_plugin_enabled(root: Path) -> bool:
    """Whether Claude Code enables the aidd-team plugin here, which carries the roles, the commands, and the practice skills."""
    return f"aidd-team@{config.MARKETPLACE}" in config.plugins_enabled(root)


def packs_plugin_enabled(root: Path) -> bool:
    """Whether Claude Code enables the aidd-domains plugin here, which carries every domain skill."""
    return f"{config.PACKS_PLUGIN}@{config.MARKETPLACE}" in config.plugins_enabled(root)


def _team_files_here(root: Path) -> bool:
    """Whether `aidd init --aidd-team` wrote the team as project skills here (a practice skill is always among them)."""
    return any(p.parent.name not in pack_names() for p in (root / SKILLS_DIR).glob(f"{TEAM_PREFIX}*/SKILL.md"))


def domain_skill_reading(root: Path, skills: list[dict]) -> tuple[dict[str, str], list[str]]:
    """How `aidd risk --paths` reads the domain skills it names (`skills` of its answer), where the team is installed here (the aidd-team
    plugin, or project files): the name each loads by, so loading never depends on a skill listing that may hold no description, and one
    hint for the skills that are not installed, with the step that adds them. Without the team, no name and no hint: the caller names each
    by its plugin."""
    plugin = team_plugin_enabled(root)
    if not (plugin or _team_files_here(root)):
        return {}, []
    if plugin:
        have = set(pack_names()) if packs_plugin_enabled(root) else set()
        name = lambda p: f"{config.PACKS_PLUGIN}:{p}"  # noqa: E731
        add = PACKS_COMMAND
    else:
        have, name, add = set(installed(root)), lambda p: f"{TEAM_PREFIX}{p}", NEXT_STEP
    names = {s["name"]: name(s["name"]) for s in skills}
    lacking = [f"`{n}`" for s, n in zip(skills, names.values(), strict=True) if s["name"] not in have]
    if not lacking:
        return names, []
    one = len(lacking) == 1
    where = f"the domain skill {lacking[0]} is" if one else f"the domain skills {', '.join(lacking)} are"
    return names, [f"{where} not installed, so the roles work without {'it' if one else 'them'}; to add {'it' if one else 'them'}, {add}"]


def doctor_lines(root: Path) -> list[tuple[str, str]]:
    """`aidd doctor`'s warning when the repository calls for a domain skill that is not here: `.claude/skills/` lacks it, where the team is
    installed as project files, or the aidd-domains plugin is not enabled, where the aidd-team plugin is."""
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
    return [("warning", f"the repository calls for the domain skills {named}, {step}")]


def packs_table() -> str:
    """The roles reference's table of every domain skill, so a domain no area names is still findable."""
    rows = "".join(f"| `{p['slug']}` | {p['name']} | {p['signal']} |\n" for p in sorted(packs(), key=lambda p: p["slug"]))
    return (
        "\n## Domain skills\n\n"
        f"`{SKILLS_DIR}/` holds the domain skills this repository calls for. To add another, {NEXT_STEP}.\n\n"
        "| Domain skill | Covers | Signal |\n| --- | --- | --- |\n" + rows
    )
