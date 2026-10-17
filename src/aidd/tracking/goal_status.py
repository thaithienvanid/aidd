"""Each goal branch's state for `aidd list` and `aidd doctor`: the Specs that ship into it, the ones it has integrated,
whether it is ready to release, and the warnings that keep it short and close to the default branch.

A goal is release-ready when every Spec that ships into it is integrated (or cancelled) and it holds every commit of
the default branch. Derived from git and the Specs each time, like every status.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config, workitems
from aidd.kernel import documents, git

_FINISHED = ("cancelled", "shipped", "done", "rolled_back")


def _epic_on(root: str, goal: str, specs_dir: str) -> dict:
    """The Epic a goal branch belongs to (`goal/<EPIC>`), as the goal branch holds it; {} when it holds none."""
    epic_id = goal.removeprefix(workitems.GOAL_PREFIX)
    text = git.show(f"refs/heads/{goal}", f"{specs_dir}/{epic_id}.md", root)
    try:
        data = documents.split_front_matter(text, f"{specs_dir}/{epic_id}.md")[0] if text else {}
    except documents.DocumentError:
        return {}
    return data if data.get("kind") == "epic" and str(data.get("id")) == epic_id else {}


def goals(root: Path | str, cfg: config.Config | None, steps: list[dict], now: dt.datetime | None = None) -> list[dict]:
    """One entry per local goal branch: {branch, head, epic, age_days, behind, specs, integrated, waiting,
    release_ready, warnings}. `steps` are `aidd list`'s, unfiltered: each Spec step names the goal it ships into
    (`goal`). The Epic's planned `specs` count too, started or not, so a goal is never ready with planned work missing."""
    limit = workitems.goal_limit(cfg)
    specs_dir = cfg.specs_dir if cfg is not None else "specs"
    out = []
    for g in workitems.goal_branches(str(root)):
        facts = workitems.goal_facts(str(root), g, now)
        held = workitems.integrated(str(root), g)
        epic = _epic_on(str(root), g, specs_dir)
        mine = {str(s["id"]): str(s.get("status") or "") for s in steps if s.get("goal") == g and s.get("id") and str(s.get("code")).startswith("spec.")}
        specs = list(dict.fromkeys([str(s) for s in epic.get("specs") or []] + sorted(set(mine) | set(held))))
        waiting = [s for s in specs if s not in held and mine.get(s) not in _FINISHED]
        out.append(
            facts
            | {
                "epic": str(epic["id"]) if epic else None,
                "specs": specs,
                "integrated": sorted(held),
                "waiting": waiting,
                "release_ready": bool(held) and not waiting and not facts["behind"],
                "warnings": workitems.goal_warnings(facts, limit),
            }
        )
    return out


def goal_steps(found: list[dict], standing: dict | None, majors: set[str]) -> list[dict]:
    """A step for each goal that is ready to release: the person's Merge approval of the goal's head (D3), or, while
    their standing approval covers every Spec in it (`majors`: the ids of major Specs), the agent's `aidd ship`."""
    out: list[dict] = []
    for g in found:
        if not g["release_ready"]:
            continue
        covered = standing is not None and (standing.get("scope") != "all-but-major" or not set(g["integrated"]) & majors)
        what = f"{g['branch']} is ready to release: {', '.join(g['integrated'])} integrated"
        if covered:
            how = f"on {g['branch']}: `aidd test`, then `aidd ship`, which tests the merge again and lands it once the gate passes"
            out.append(
                {"code": "goal.ship_ready", "where": g["branch"], "what": what + "; your standing approval covers it", "who": workitems.AGENT, "how": how}
            )
        else:
            how = f"on {g['branch']}: `aidd test`, then type `ship it` (or merge its pull request into the default branch)"
            out.append({"code": "goal.release", "where": g["branch"], "what": what, "who": workitems.APPROVER, "how": how})
        out[-1] |= {"id": g["branch"], "goal": g["branch"], "blocked": False}
    return out


def goals_markdown(found: list[dict]) -> str:
    """The lines `aidd list` starts with for its goals: one per goal that is ready to release or needs a step."""
    lines = []
    for g in found:
        if g["release_ready"]:
            lines.append(
                f"{g['branch']} is ready to release: {', '.join(g['integrated'])} integrated. On it, `aidd test`; the person's Merge approval "
                "releases it (they type `ship it`, or merge its pull request into the default branch)"
            )
        lines += g["warnings"]
    return "".join(f"{ln}\n" for ln in lines)


# Spec statuses at or past Spec approval (workitems' derived status), and those that reached the default branch.
_APPROVED = ("ready", "in_progress", "in_review", "shipped", "done", "rolled_back")
_LANDED = ("shipped", "done")


def _rung(done: int, total: int, waits: list[str]) -> dict:
    return {"done": done, "total": total, "waits": waits}


def _release(building: list[str], state: dict[str, str], branch: str | None, ready: set[str], waiting: dict[str, str]) -> dict:
    """D3 for one small goal: its goal released once (together, `branch`), or each Spec on the default branch."""
    if branch:
        released = bool(building) and all(state[s] in _LANDED for s in building)
        return _rung(int(released), 1, [branch] if branch in ready else [])
    return _rung(sum(state[s] in _LANDED for s in building), len(building), [s for s in building if waiting.get(s) == "spec.in_review"])


def small_goal_ladders(root: Path | str, cfg: config.Config | None, steps: list[dict], specs: list, goals: list[dict]) -> dict:
    """The shape of the work as a person decides it: each big goal (Initiative) with its small goals (Epics on the
    default branch, the plans a person agreed to), and for each small goal how it ships and where each of the person's
    decisions stands. `specs` are `open_work`'s Items, each with its derived status; `goals` are `goals`' entries.

    Each small goal: {id, title, parent, ships, branch, specs: [{id, status}], plan, spec_approval, release, launch}, where
    a rung is {done, total, waits} (`waits`: the Spec ids, or the goal branch, waiting on a person now), `plan` is
    "agreed" (the Epic is on the default branch), and `launch` is None unless it ships flagged."""
    specs_dir = cfg.specs_dir if cfg is not None else "specs"
    try:
        found, _ = workitems.objects_at(Path(root), git.default_base(str(root)), specs_dir)
    except git.GitError:
        found = []
    status = {it.id: it.status for it in specs}
    parent_of = {it.id: str(it.data.get("parent") or "") for it in specs}
    waiting = {str(s.get("id")): str(s.get("code")) for s in steps if s.get("who") in (workitems.APPROVER, workitems.PERSON, workitems.AUTHOR)}
    held = {s for g in goals for s in g["integrated"]}
    ready = {g["branch"] for g in goals if g["release_ready"]}
    out: list[dict] = []
    initiatives: dict[str, dict] = {}
    for _, d, _, _ in found:
        if d.get("kind") == "initiative":
            initiatives[str(d.get("id"))] = {"id": str(d.get("id")), "title": str(d.get("title") or ""), "small_goals": []}
    for _, d, _, _ in found:
        if d.get("kind") != "epic" or d.get("status") in ("done", "cancelled"):
            continue
        eid, mode = str(d.get("id")), workitems.ships(d)
        planned = [str(s) for s in d.get("specs") or []] or sorted(i for i, p in parent_of.items() if p == eid)
        launch = str(d.get("launch") or "") if mode == "flagged" else ""
        building = [s for s in planned if s != launch]
        state = {s: ("integrated" if s in held and status.get(s) not in _LANDED else status.get(s, "planned")) for s in planned}
        branch = workitems.goal_branch(eid) if mode == "batched" else None
        release = _release(building, state, branch, ready, waiting)
        entry = {
            "id": eid,
            "title": str(d.get("title") or ""),
            "parent": str(d.get("parent") or "") or None,
            "ships": mode,
            "branch": branch,
            "specs": [{"id": s, "status": state[s]} for s in planned],
            "plan": "agreed",
            "spec_approval": _rung(
                sum(state[s] in _APPROVED or state[s] == "integrated" for s in planned),
                len(planned),
                [s for s in planned if waiting.get(s) == "spec.spec_approval"],
            ),
            "release": release,
            "launch": (
                {"spec": launch, "state": "done" if state.get(launch) in _LANDED else "waits" if waiting.get(launch) == "spec.in_review" else "todo"}
                if mode == "flagged"
                else None
            ),
        }
        out.append(entry)
        if entry["parent"] in initiatives:
            initiatives[entry["parent"]]["small_goals"].append(eid)
    return {"initiatives": list(initiatives.values()), "small_goals": out}
