"""The route of this change and its forecast: the route as the gate will enforce it (the higher of what the diff needs
and what the change declares), the route of planned paths before any code exists (`aidd gate --paths`), and this
branch's steps and overlaps from next_steps.py, as data and as text."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config, gate, workitems
from aidd.kernel import git
from aidd.tracking import next_steps

# Lowest to highest: an emergency is its own lane, above every other route.
ROUTE_ORDER = ("standard", "minor", "normal", "major", "emergency")


def _declared(root: Path, specs: list[next_steps.Item]) -> tuple[str, str] | None:
    """(route, by): the highest route this change declares, in a Spec on the branch or in the Change Request block of the
    newest branch commit that holds one (`aidd describe --commit`); None when it declares none."""
    found = [(str(it.data.get("route")), it.id) for it in specs if it.data.get("route") in ROUTE_ORDER]
    if not found:
        cwd = str(root)
        try:
            fork = git.merge_base(git.rev_parse(git.default_base(cwd), cwd), git.rev_parse("HEAD", cwd), cwd)
            block, _ = workitems.parse_change_block(gate.commit_block(cwd, fork, "HEAD") or "")
        except (git.GitError, OSError, ValueError):
            block = None
        if block and block.get("route") in ROUTE_ORDER and not block.get("spec"):
            found = [(str(block["route"]), "the Change Request block")]
    if not found:
        return None
    return max(found, key=lambda x: ROUTE_ORDER.index(x[0]))


def route_of(root: Path, specs: list[next_steps.Item] | None = None, *, ctype: str = "feat") -> dict | None:
    """The route of this change: the higher of the minimum the branch's diff needs (`routing.assess_diff`) and the route
    the change declares (`_declared`), as the gate enforces it. The computed summary's fields, with `route` and `lane`
    the effective ones, plus `required` (the diff's minimum, or None), `declared` ({route, by}, or None), and `header`
    (one line). None when there is neither a diff nor a declaration."""
    computed = gate.assess_diff(root, ctype=ctype)
    declared = _declared(root, specs or [])
    if computed is None and declared is None:
        return None
    out: dict = dict(computed or {"reasons": [], "dimensions": [], "pools": [], "basis": "no diff yet", "paths": []})
    out["reasons"] = gate.reason_lines(out) if computed else []
    need = computed["route"] if computed else None
    route = max([r for r in (need, declared[0] if declared else None) if r], key=ROUTE_ORDER.index)
    out |= {"route": route, "lane": gate.LANES[route], "required": need, "declared": {"route": declared[0], "by": declared[1]} if declared else None}
    head = f"Route: {route} ({out['lane']} lane)"
    if declared and need is None:
        out["header"] = f"{head}, set by {declared[1]}; the branch has no diff yet"
    elif declared and ROUTE_ORDER.index(declared[0]) >= ROUTE_ORDER.index(str(need)):
        out["header"] = f"{head}, set by {declared[1]}; " + ("the diff needs the same" if declared[0] == need else f"the diff alone needs {need}")
    elif declared:
        out["header"] = f"{head}, needed by the diff; {declared[1]} declares {declared[0]}, and the gate enforces the higher"
    else:
        out["header"] = f"{head}, needed by {out['basis']}"
    return out


def forecast(
    root: Path,
    *,
    paths: list[str] | None = None,
    ctype: str | None = None,
    dimensions: list[str] | tuple[str, ...] = (),
    irreversible: bool = False,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """This change's forecast: {"route", "steps", "overlaps"}. With `paths`, the route those planned paths need before any code
    exists and the lane's first step; else the route of this branch's change (`route_of`), the steps for the Specs it
    changes, and the other branches whose Specs overlap them."""
    if paths:
        # The route of planned paths needs only the config: a check that fails on this machine (a missing launcher)
        # comes first among the steps, and the forecast still says the route.
        setup = next_steps.setup_step(root)
        if setup is not None and setup["code"] == "setup.missing":
            return {"route": None, "steps": [setup], "overlaps": []}
        cfg = config.load_file(config.CONFIG_PATH, str(root), skip_unread=True)  # a display: an unread URL parent warns
        tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
        a = gate.assess_paths(cfg, paths, ctype=ctype or "feat", dimensions=dimensions, irreversible=irreversible, tracked=tracked)
        n = len(paths)
        planned = gate.route_summary(a, f"the planned paths ({n} path{'s' if n != 1 else ''})") | {"paths": list(paths)}
        planned["reasons"] = gate.reason_lines(planned)
        if packs := gate.risk_packs(cfg, a.dimensions):
            planned["packs"] = packs
        planned |= {
            "required": planned["route"],
            "declared": None,
            "header": f"Route: {planned['route']} ({planned['lane']} lane), needed by {planned['basis']}",
        }
        step = gate.lane_step(root, has_spec=False, summary=planned)
        hint = gate.untested_feature_hint(paths, ctype=ctype or "feat", tracked=tracked) if step and step["lane"] == "fast" else None
        if step and hint:
            step["how"] += f". Also: {hint}"
        constraints = config.effective_project(cfg, list(paths), today)
        steps = [s for s in (setup, step) if s]
        return {"route": planned, "steps": steps, "overlaps": []} | ({"project": constraints} if constraints else {})
    steps, specs = next_steps.collect(root, next_steps.Filters(), today, now)
    route = route_of(root, specs, ctype=ctype or "feat") if not steps[0]["code"].startswith("setup.") else None
    overlaps = [s for s in steps if s["code"].startswith("overlap")]
    constraints = config.effective_project(workitems.config_at(root), (route or {}).get("paths") or None, today) if route else None
    answer = {"route": route, "steps": [s for s in steps if not s["code"].startswith("overlap")], "overlaps": overlaps}
    return answer | ({"project": constraints} if constraints else {})


def pack_lines(route: dict) -> list[str]:
    """The domain packs a route calls for, one line for its added dependencies and one for its risk; none when it calls
    for none."""
    out = []
    if added := [p for p in route.get("packs") or [] if p.get("dependency")]:
        out.append("Domain packs the added dependencies call for: " + ", ".join(f"`aidd-team:{p['pack']}` ({p['dependency']} in {p['file']})" for p in added))
    if risky := [p for p in route.get("packs") or [] if p.get("reason")]:
        out.append("Domain packs its risk calls for: " + ", ".join(f"`aidd-team:{p['pack']}` ({p['reason']})" for p in risky))
    return out


def forecast_markdown(answer: dict) -> str:
    """The forecast as text: the route header and its reasons, then this change's steps, then the overlaps."""
    route = answer.get("route")
    if route:
        out = [route["header"], *(f"  - {line}" for line in route["reasons"]), *pack_lines(route)]
    else:
        out = ["Route: none yet: this branch has no diff; `aidd gate --paths GLOB...` forecasts the route before any code"]
    if answer.get("steps"):
        out += ["", "Next for this change:", next_steps.next_steps_markdown(answer["steps"]).rstrip("\n")]
    if answer.get("overlaps"):
        out += ["", "Overlaps with other branches:", next_steps.next_steps_markdown(answer["overlaps"]).rstrip("\n")]
    if answer.get("project"):
        out += ["", *config.project_markdown(answer["project"])]
    return "\n".join(out) + "\n"
