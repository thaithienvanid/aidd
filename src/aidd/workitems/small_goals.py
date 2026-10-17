"""Small goals: how an Epic reaches users (`ships`), the goal branch a `batched` Epic gets, and the checks that keep
its Specs consistent with it.

- `incremental` (the default): each Spec merges to the default branch when it is done.
- `flagged`: each Spec merges to the default branch behind a feature flag that stays off; the `launch` Spec turns it on,
  and its Merge approval stays a person's.
- `batched`: the goal branch `goal/<id>`; the team integrates each Spec into it, and a person releases it once.

The goal branch's name comes from the Epic's id, so a Spec's `base` can be checked against its parent Epic.
"""

from __future__ import annotations

import re

GOAL_PREFIX = "goal/"
SHIPS = ("incremental", "flagged", "batched")


def ships(epic: dict | None) -> str:
    """How the Epic ships: its `ships`, else `incremental`."""
    value = str((epic or {}).get("ships") or "incremental")
    return value if value in SHIPS else "incremental"


def goal_branch(epic_id: str) -> str:
    """The goal branch of a `batched` Epic: `goal/<id>`, with any character git forbids in a branch name as `-`."""
    return GOAL_PREFIX + re.sub(r"[^A-Za-z0-9._-]", "-", epic_id)


def is_launch(spec: dict, idx: dict[str, dict]) -> bool:
    """Whether the Spec is its parent Epic's `launch`: the change that turns a flagged feature on for users."""
    epic = idx.get(str(spec.get("parent") or "")) or {}
    return epic.get("kind") == "epic" and bool(epic.get("launch")) and str(epic["launch"]) == str(spec.get("id") or "")


def launches_at(root: str, ref: str, specs_dir: str) -> dict[str, str]:
    """{launch Spec id: its Epic id} for each flagged Epic at `ref` (the default branch): the changes that turn a feature
    on for users, whose Merge approval a standing approval never covers."""
    from pathlib import Path

    from aidd.workitems import repo_reads

    found, _ = repo_reads.objects_at(Path(root), ref, specs_dir)
    return {str(d["launch"]): str(d.get("id")) for _, d, _, _ in found if d.get("kind") == "epic" and ships(d) == "flagged" and d.get("launch")}


def small_goal_checks(objects: list[tuple[str, dict]]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for each Spec against the Epic it belongs to, and for each Epic's own plan."""
    errors: list[str] = []
    warnings: list[str] = []
    epics = {str(d.get("id")): d for _, d in objects if d.get("kind") == "epic"}
    for p, d in objects:
        if d.get("kind") == "epic":
            mode, planned = ships(d), [str(s) for s in d.get("specs") or []]
            if mode == "batched" and 0 < len(planned) < 2:
                warnings.append(f"{p}: a small goal with one Spec needs no goal branch; make it `ships: incremental`")
            if d.get("launch") and mode != "flagged":
                errors.append(f"{p}: `launch` names the Spec that turns a flagged feature on; set `ships: flagged`, or drop `launch`")
            if mode == "flagged" and planned and d.get("launch") and str(d["launch"]) not in planned:
                warnings.append(f"{p}: the launch Spec {d['launch']} is not in `specs`; plan it last")
            continue
        if d.get("kind") != "spec":
            continue
        epic = epics.get(str(d.get("parent") or ""))
        if epic is None:
            continue
        mode, base, branch = ships(epic), str(d.get("base") or ""), goal_branch(str(epic.get("id")))
        if mode == "batched" and base != branch:
            errors.append(f"{p}: its Epic {epic.get('id')} ships batched, so it ships into {branch}: set `base: {branch}`")
        elif mode != "batched" and base.startswith(GOAL_PREFIX):
            errors.append(f"{p}: its Epic {epic.get('id')} ships {mode}, so it merges to the default branch: remove `base: {base}`")
        if mode == "flagged" and not d.get("flags") and str(epic.get("launch") or "") != str(d.get("id")):
            warnings.append(
                f"{p}: its Epic {epic.get('id')} ships flagged, so the Spec ships behind a feature flag that stays off until the launch; "
                "add it under `flags`, or users see half a feature"
            )
    return errors, warnings
