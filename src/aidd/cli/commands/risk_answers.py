"""The parts of an `aidd risk` answer that are data or notes: every rule in force (`--list`), and what an answer says beside its level."""

from __future__ import annotations

from pathlib import Path

from aidd import risk
from aidd.kernel import git

NO_ACTION_NOTE = "no action's pattern matches this command, so no rule gave this allow: allow, unless an action's examples describe what it does"


def cap_area_paths(answer: dict, shown: int) -> dict:
    """`risk.advice`'s answer for a person or an agent to read: at most `shown` paths (`limits.max_paths_shown`) listed in each area, its full count in
    `path_count`, and a hint that says how many an area left out. Only a display reads this: the route, the edit level, and the scope of a new
    Spec come from `risk.advice` itself, with every path."""
    left = [f"{hit['area']} ({len(hit['paths']) - shown} of {len(hit['paths'])})" for hit in answer["areas"] if len(hit["paths"]) > shown]
    areas = [{**hit, "paths": hit["paths"][:shown], "path_count": len(hit["paths"])} for hit in answer["areas"]]
    hint = (
        f"the answer lists the first {shown} paths of an area and leaves out these: {', '.join(left)}. Every path still counts for the route and the edit level"
    )
    return answer | {"areas": areas, "hints": answer["hints"] + ([hint] if left else [])}


def trunk_note(answer: dict, where: str | None) -> list[str]:
    """Why a push asks as a push to the default branch when git cannot tell which branch that is, and how to name it. `answer`
    is `command_level`'s, `where` the folder it was read in (None: aidd cannot tell it)."""
    if where is None or not any(a["branch"] == "default" for a in answer["actions"]) or git.default_branches(where)[1]:
        return []
    return [
        "git cannot tell the default branch here (no origin/HEAD, and no main or master), so a push of any branch that could be it asks: "
        "run `git remote set-head origin --auto` once there is a remote, or `git config init.defaultBranch <branch>`"
    ]


def action_notes(rs, args, rule, level: str) -> list[str]:
    """What an `--action` answer does not say: the branch it is the highest level on, and the routes where the level is lower."""
    notes = [f"no --branch: its highest level on any branch (--branch {rule.branch} names one)"] if rule and rule.branch and not args.branch else []
    for named in [] if args.route else sorted({r.route for r in rs.rules if r.route and r.action == args.action}):
        there = risk.level_on_any_branch(rs, args.action, area=args.area, branch=args.branch, role=args.role, route=named)[0]
        notes += [f"no --route: the level above is for every route; on a {named} change it is {there} (`--route {named}`)"] if there != level else []
    return notes


def folder_note(folder: str) -> str:
    """What `--folder` did when no git checkout is there: the branch is unknown, so the answer reads the stricter way."""
    why = "is not a folder" if not Path(folder).is_dir() else "is not a git checkout"
    return f"--folder {folder} {why}, so the branch is unknown and the stricter reading holds"


def rules_list(rs: risk.RuleSet) -> tuple[dict, str]:
    """`aidd risk --list`: every rule in force with where it comes from, and the areas and actions, as data and as text."""
    answer: dict = {
        "rules": [
            {"action": r.action, "area": r.area, "branch": r.branch, "role": r.role, "level": r.level, "source": r.source, "locked": r.locked}
            | ({"environment": r.environment} if r.environment else {})
            | ({"environment_shared": r.environment_shared} if r.environment_shared is not None else {})
            | ({"route": r.route} if r.route else {})
            | ({"reason": r.reason} if r.reason else {})
            for r in rs.rules
        ],
        "areas": {k: {"glob_count": len(v.get("paths", [])), "route": v.get("route", "minor")} for k, v in rs.areas.items()},
        "actions": sorted(rs.actions),
        "api_endpoints": {k: list(v["api_endpoints"]) for k, v in sorted(rs.actions.items()) if v.get("api_endpoints")},
        "ignored": rs.ignored,
        "lock_effects": risk.lock_effects(rs),
    }
    text = "\n".join(f"{r.label()}  ({r.source}{', locked' if r.locked else ''})" for r in rs.rules) + "\n"
    text += "areas: " + ", ".join(f"{k} ({v['route']})" for k, v in answer["areas"].items()) + "\n"
    text += "".join(f"gh api endpoints, {k}: {', '.join(v)}\n" for k, v in answer["api_endpoints"].items())
    text += "".join(f"note: {w}\n" for w in rs.ignored)
    text += "".join(f"lock: {w}\n" for w in answer["lock_effects"])
    return answer, text
