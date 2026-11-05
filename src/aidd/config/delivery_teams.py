"""`delivery_teams`: the delivery teams that share a repository, each with its people, its areas or Intents, its harness,
and its models. The schema checks each team's shape; this module checks what the schema cannot see, the harness and
area names, and finds one team by name."""

from __future__ import annotations

from aidd.config import harnesses, model
from aidd.kernel import resources


def problems(merged: dict) -> list[str]:
    """Each name a merged config's delivery teams give that names nothing: a harness aidd does not know, or an area
    neither the built-in rules nor `risks.areas` define. Empty when every name holds."""
    teams = merged.get("delivery_teams") or {}
    areas = set(resources.load_json("risks.json")["areas"]) | set((merged.get("risks") or {}).get("areas") or {})
    out = []
    for name in sorted(teams):
        team = teams[name]
        harness = team.get("harness")
        if harness is not None and harness not in harnesses.HARNESSES:
            out.append(f"delivery_teams.{name}.harness: {harness!r} is no harness aidd knows; name one `aidd init --harness` takes, such as claude-code")
        for area in team.get("areas") or []:
            if area not in areas:
                out.append(f"delivery_teams.{name}.areas: {area!r} is no area; name a built-in one (`aidd risk --list`) or add it under `risks.areas`")
    return out


def delivery_team(cfg: model.Config | None, name: str) -> dict:
    """The delivery team `name` in `cfg`'s `delivery_teams`; a ValueError that names the teams there when none has it."""
    if cfg is None:
        raise ValueError(f"--delivery-team reads {model.CONFIG_PATH}, which is missing or does not load: `aidd validate` names why")
    teams = cfg.get("delivery_teams", default={}) or {}
    if name not in teams:
        known = ", ".join(sorted(teams)) or "no team yet"
        raise ValueError(f"no delivery team {name!r} in {model.CONFIG_PATH}, whose `delivery_teams` names {known}: add it there, or name one of those")
    return dict(teams[name])
