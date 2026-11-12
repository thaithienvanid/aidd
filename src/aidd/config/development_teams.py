"""`development_teams`: the development teams that share a repository, each with its approvers, its areas, its harness, its models,
and its effort. The schema checks each team's shape; this module checks what the schema cannot see, the harness and
area names, and finds one team by name."""

from __future__ import annotations

from aidd.config import harnesses, model
from aidd.kernel import resources


def problems(merged: dict) -> list[str]:
    """Each name a merged config's development teams give that names nothing: a harness aidd does not know, or an area
    neither the built-in rules nor `risks.areas` define. Empty when every name holds."""
    teams = merged.get("development_teams") or {}
    areas = set(resources.load_json("risks.json")["areas"]) | set((merged.get("risks") or {}).get("areas") or {})
    out = []
    for name in sorted(teams):
        team = teams[name]
        harness = team.get("harness")
        if harness is not None and harness not in harnesses.HARNESSES:
            out.append(f"development_teams.{name}.harness: {harness!r} is no harness aidd knows; name one `aidd init --harness` takes, such as claude-code")
        for area in team.get("areas") or []:
            if area not in areas:
                out.append(f"development_teams.{name}.areas: {area!r} is no area; name a built-in one (`aidd risk --list`) or add it under `risks.areas`")
    return out


def development_team(cfg: model.Config | None, name: str) -> dict:
    """The development team `name` in `cfg`'s `development_teams`; a ValueError that names the teams there when none has it."""
    if cfg is None:
        raise ValueError(f"--development-team reads {model.CONFIG_PATH}, which is missing or does not load: `aidd validate` names why")
    teams = cfg.get("development_teams", default={}) or {}
    if name not in teams:
        known = ", ".join(sorted(teams)) or "no team yet"
        raise ValueError(f"no development team {name!r} in {model.CONFIG_PATH}, whose `development_teams` names {known}: add it there, or name one of those")
    return dict(teams[name])
