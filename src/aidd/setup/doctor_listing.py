"""`aidd doctor`'s report of the skill descriptions a session lists here. Claude Code lists every skill's name and, within 1% of
the model's context window, every description, and past it drops the descriptions of the least-used skills (config.SIZES). A
skill or command that sets `disable-model-invocation: true` puts no description in the listing (config.LISTING_FACTS). It is a
report, not a warning: the person's window and their other plugins decide whether it bites, and aidd cannot see them. aidd says
it only where the team's files, or the aidd-team plugin, are installed here."""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config, knowledge
from aidd.kernel import documents, resources
from aidd.setup import domain_packs, team_install

LISTED = re.compile(r"^\.claude/(skills/[^/]+/SKILL\.md|commands/[^/]+\.md)$")


def description(text: str) -> str:
    """The `description` of a skill's or command's front matter; empty when it has none or the front matter does not parse."""
    try:
        value = documents.split_front_matter(text)[0].get("description")
    except documents.DocumentError:
        return ""
    return value if isinstance(value, str) else ""


def _listed(files: dict[str, str]) -> list[tuple[str, int]]:
    """Each listed description in `files` as (the skill's name, its length): a command that sets `disable-model-invocation: true`
    lists none. A project skill `aidd-<name>` is the team skill `<name>`."""
    return [
        (Path(rel).parent.name.removeprefix(team_install.TEAM_PREFIX), len(description(text)))
        for rel, text in files.items()
        if LISTED.match(rel) and knowledge.lists_description(text)
    ]


def listing_lines(root: Path) -> list[tuple[str, str]]:
    """The report line for the descriptions the team puts in a session here: those of the project files `aidd init --aidd-team`
    wrote, or, with the aidd-team plugin on, its router and practice skills, and the packs when the aidd-packs plugin is on too.
    Nothing when the team is not installed here."""
    plugin = domain_packs.team_plugin_enabled(root)
    if plugin:
        packs_on = domain_packs.packs_plugin_enabled(root)
        files = team_install.team_files([], True, packs=None if packs_on else [])
        where = "The aidd-team and aidd-packs plugins list" if packs_on else "The aidd-team plugin lists"
        step = "To keep every description in a small window, raise the `skillListingBudgetFraction` setting of Claude Code, for example to 0.02."
        if packs_on:
            step += " A role loads a domain pack by name, so a pack needs no description: enable the aidd-packs plugin only in a project that calls for a pack."
    elif (wanted := team_install.wanted_team_files(root)) is not None:
        files, where = wanted[0], "The team files here list"
        step = "To list fewer, name the packs the project calls for in `agents.domain_packs`, then run `aidd upgrade --yes`."
    else:
        return []
    listed = _listed(files)
    if plugin:  # the plugin carries the router skill too, which no project file does
        router = (resources.data_dir("team") / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8")  # aidd's own: the bundled team files
        listed.append(("aidd-team", len(description(router))))
    chars = sum(n for _, n in listed)
    return [("", config.listing_note(chars, where, step, sum(n for name, n in listed if knowledge.found_by(name) == "name")))]
