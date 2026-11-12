"""The route for planned paths: how much of the loop a change needs, as advice, before any code exists.

A change starts minor. Each area it touches raises it to the area's `route`; a risk dimension that can harm data,
people, money, or the law makes it major, as does an irreversible change. A dimension counts whether an area carries it or
the author declares it (`aidd risk --dimension`), and any dimension rules out minor. The change type never raises the route.
`aidd risk --paths` and the MCP `risk` tool give the route, whether a Spec comes first, why, the level of the first edit, and the step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aidd import config
from aidd.config import Config
from aidd.kernel import command_names, globs
from aidd.risk.rules import RuleSet, areas_in, edit_level_in, level_of, rule_set


@dataclass
class Route:
    route: str
    dimensions: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    areas: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class DeclaredRisk:
    """What the author declares of a change beyond its paths: its risk dimensions (`--dimension`), and whether a revert would
    not restore the prior state (`--irreversible`)."""

    dimensions: tuple[str, ...] = ()
    irreversible: bool = False


NOTHING_DECLARED = DeclaredRisk()


def planned_paths(paths: list[str], tracked: list[str] | None = None) -> list[str]:
    """Planned paths as the areas see them: a glob or a folder becomes a sample path inside it, and with `tracked`
    (the repository's files) it also stands for every tracked file it matches, so a risky file inside it counts. The
    route is never lower than a file the glob matches, so no match is left out."""
    out = [globs.sample_path(p) if globs.is_pattern(p) or p.endswith("/") else p.removeprefix("./") for p in paths]
    for p in paths if tracked else []:
        if globs.is_pattern(p) or p.endswith("/"):
            out += globs.matching(p.removeprefix("./") + ("**" if p.endswith("/") else ""), tracked or [])
    return list(dict.fromkeys(out))


def route_for(rs: RuleSet, paths: list[str], declared: DeclaredRisk = NOTHING_DECLARED) -> Route:
    """The least route for a change to `paths` with the `declared` risk."""
    return route_in(rs, areas_in(rs, paths), declared)


def route_in(rs: RuleSet, by_area: dict[str, list[str]], declared: DeclaredRisk = NOTHING_DECLARED) -> Route:
    """The least route for a change that touches the areas `by_area` names, each with its paths, with the `declared` risk. A
    declared dimension raises the route as an area's does."""
    rank = config.ROUTE_RANK
    r = Route("minor", areas=by_area)
    for name, hit in by_area.items():
        area = rs.areas[name]
        need = area.get("route", "minor")
        r.dimensions.update(area.get("dimensions", []))
        if rank[need] > rank[r.route]:
            r.route = need
        r.reasons.append(f"area {name} ({hit[0]}{' and more' if len(hit) > 1 else ''}) -> at least {need}")
    if added := sorted(set(declared.dimensions) - r.dimensions):
        r.dimensions.update(added)
        r.reasons.append(f"declared dimensions {added}")
    major = r.dimensions.intersection(config.MAJOR_DIMENSIONS)
    if major and r.route != "major":
        r.route = "major"
        r.reasons.append(f"dimensions {sorted(major)} -> major")
    if declared.irreversible:
        r.route = "major"
        r.reasons.append("irreversible -> major")
    if r.route == "minor" and r.dimensions:
        r.route = "normal"
        r.reasons.append(f"dimensions {sorted(r.dimensions)} -> normal")
    return r


def spec_approval_level(cfg: Config | None, route: str) -> str:
    """Whether an agent asks for Spec approval on `route`: the level of the `spec.approve` rule for that route. A route
    without a Spec has nothing to approve, so it is `allow`."""
    if route not in config.SPEC_FIRST_ROUTES:
        return "allow"
    return level_of(rule_set(cfg), "spec.approve", route=route)[0]


def routes_asking_for_spec_approval(profile: str) -> list[str]:
    """The routes on which an agent asks for Spec approval under `profile`'s rules and the built-in ones, in route order."""
    cfg = config.Config({}, profile)
    return [r for r in config.ROUTES if spec_approval_level(cfg, r) == "ask"]


def specialists(cfg: Config | None, dimensions: set[str]) -> list[dict]:
    """The specialist pools a change's dimensions name, with the people `owners.specialists` binds to each."""
    pools = sorted({config.POOL_OF[d] for d in dimensions if d in config.POOL_OF})
    bound = cfg.specialists if cfg else {}
    return [{"pool": p, "people": list(bound.get(p, []))} for p in pools]


def untested_new_files(paths: list[str], *, change_type: str, tracked: list[str]) -> str | None:
    """The new source files a feat's planned paths add with no test file, named for the one next step of a change with no Spec, which
    then writes their test first. None otherwise."""
    if change_type != "feat" or any(config.looks_like_test(p) for p in paths):
        return None
    known = set(tracked)
    new = [p for p in paths if p not in known and p.endswith(config.source_extensions())]
    if not new:
        return None
    return ", ".join(new[:3]) + (", ..." if len(new) > 3 else "")


def shown_paths(paths: list[str]) -> str:
    """The paths a next step names, as command words: the first three, and "..." for more. A path is the repository's text, so it
    joins a command only as a plain name (kernel.command_names), else as `<path>`."""
    return " ".join(command_names.quoted(p) or "<path>" for p in paths[:3]) + (" ..." if len(paths) > 3 else "")


def advice(
    cfg: Config | None,
    paths: list[str],
    *,
    change_type: str = "feat",
    declared: DeclaredRisk = NOTHING_DECLARED,
    tracked: list[str] | None = None,
) -> dict:
    """Everything `aidd risk --paths` says, as data (schemas/risk.schema.json). The route reads the paths and the `declared`
    risk; the change type shapes only the next step."""
    rs = rule_set(cfg)
    planned = planned_paths(paths, tracked)
    by_area = areas_in(rs, planned)  # once: a glob over a large repository stands for many files
    r = route_in(rs, by_area, declared)
    level, rule = edit_level_in(rs, list(by_area))
    approval = spec_approval_level(cfg, r.route)
    # One next step: a new feature with no test gets its test first inside the step of a change with no Spec, never a second step.
    untested = untested_new_files(paths, change_type=change_type, tracked=tracked or []) if r.route == "minor" else None
    first = f"write a test for the new code ({untested}) first; then implement" if untested else "implement"
    if r.route == "minor":
        step = f"with no Spec, {first} and verify with `aidd test`, and ask before it reaches the default branch"
        if level == "ask":
            step = f"no Spec, in an ask area ({', '.join(a for a in by_area)}): ask before the first edit, naming the paths; then {first} and verify with `aidd test`"
    else:
        shown = shown_paths(paths)
        # The step carries what was declared, so the Spec it writes takes the route this answer gives.
        flags = "".join(f" --dimension {command_names.quoted(d) or '<dimension>'}" for d in sorted(set(declared.dimensions))) + (
            " --irreversible" if declared.irreversible else ""
        )
        asks = "ask for Spec approval" if approval == "ask" else "say the Spec is written, and go on"
        step = f'Spec first: write the Spec and its tests (`aidd new spec "<title>" --paths {shown}{flags}`), then {asks}'

    constraints = config.effective_project(cfg, planned)
    return {
        "paths": list(paths),
        "route": r.route,
        "reasons": r.reasons or ["no area or declared risk raised it: the least route is minor"],
        "dimensions": sorted(r.dimensions),
        "areas": [{"area": a, "paths": ps} for a, ps in by_area.items()],
        "edit": {"level": level, "rule": rule.label() if rule else None, "source": rule.source if rule else None},
        "spec_approval": approval,
        "specialists": specialists(cfg, r.dimensions),
        "next": {"what": step},
        "hints": [],
    } | ({"project": constraints} if constraints else {})
