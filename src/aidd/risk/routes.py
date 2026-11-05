"""The route for planned paths: how much of the loop a change needs, as advice, before any code exists.

A change starts minor. Each area it touches raises it to the area's `route`; a risk dimension that can harm data,
people, money, or the law makes it major, as does an irreversible change or a change type that is one of those.
`aidd risk --paths` and the MCP `risk` tool give the route, its lane, why, the level of the first edit, and the step.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from aidd import config
from aidd.config import Config
from aidd.kernel import globs, resources
from aidd.risk.rules import RuleSet, edit_level, level_of, rule_set

MAJOR_DIMENSIONS = {"data", "security", "privacy", "financial", "compliance"}
MAJOR_TYPES = {"data", "security", "compliance"}
# A type that needs at least normal whatever the paths: an infrastructure change reaches production outside the code
# paths an area can name (a console, a pipeline variable, a deploy file in an unusual place).
NORMAL_TYPES = {"infra"}
LANES = {"minor": "fast", "normal": "spec", "major": "spec", "emergency": "emergency"}
MAX_EXPANDED = 2000  # tracked files one planned glob may stand for, so a `**` over a monorepo stays quick
SOURCE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".php", ".dart", ".swift", ".ex")


def change_types() -> tuple[str, ...]:
    """The change types a Spec or a commit subject may name (common.schema.json)."""
    return tuple(resources.load_json("common.schema.json")["$defs"]["change_type"]["enum"])


@dataclass
class Route:
    route: str
    dimensions: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    areas: dict[str, list[str]] = field(default_factory=dict)

    @property
    def lane(self) -> str:
        return LANES[self.route]


def planned_paths(paths: list[str], tracked: list[str] | None = None) -> list[str]:
    """Planned paths as the areas see them: a glob or a folder becomes a sample path inside it, and with `tracked`
    (the repository's files) it also stands for every tracked file it matches, so a risky file inside it counts."""
    out = [globs.sample_path(p) if any(c in p for c in "*?") or p.endswith("/") else p.removeprefix("./") for p in paths]
    for p in paths if tracked else []:
        if any(c in p for c in "*?") or p.endswith("/"):
            pattern = p.removeprefix("./") + ("**" if p.endswith("/") else "")
            out += itertools.islice((t for t in tracked or [] if globs.match(pattern, t)), MAX_EXPANDED)
    return list(dict.fromkeys(out))


def route_for(rs: RuleSet, paths: list[str], *, change_type: str = "feat", irreversible: bool = False) -> Route:
    """The least route for a change to `paths` of `change_type`."""
    _, _, by_area = edit_level(rs, paths)
    rank = config.ROUTE_RANK
    r = Route("minor", areas=by_area)
    for name, hit in by_area.items():
        area = rs.areas[name]
        need = area.get("route", "minor")
        r.dimensions.update(area.get("dimensions", []))
        if rank[need] > rank[r.route]:
            r.route = need
        r.reasons.append(f"area {name} ({hit[0]}{' and more' if len(hit) > 1 else ''}) -> at least {need}")
    major = r.dimensions & MAJOR_DIMENSIONS
    if major and r.route != "major":
        r.route = "major"
        r.reasons.append(f"dimensions {sorted(major)} -> major")
    if irreversible:
        r.route = "major"
        r.reasons.append("not reversible -> major")
    if change_type in MAJOR_TYPES:
        r.route = "major"
        r.reasons.append(f"type {change_type} -> major")
    elif change_type in NORMAL_TYPES and rank[r.route] < rank["normal"]:
        r.route = "normal"
        r.reasons.append(f"type {change_type} -> at least normal")
    if r.route == "minor" and r.dimensions:
        r.route = "normal"
        r.reasons.append(f"dimensions {sorted(r.dimensions)} -> normal")
    return r


def spec_approval_level(cfg: Config | None, route: str) -> str:
    """Whether an agent asks for Spec approval on `route`: `ask` on the profile's spec_approval_routes and on every
    route a config rule names for `spec.approve`, else `report` (it writes the Spec, says so, and goes on)."""
    profile = config.profiles()["profiles"].get(cfg.profile if cfg else "solo") or {}
    if route not in ("normal", "major"):
        return "allow"
    level, rule = level_of(rule_set(cfg), "spec.approve")
    if rule is not None and rule.from_config:
        return level
    return "ask" if route in profile.get("spec_approval_routes", []) else "report"


def specialists(cfg: Config | None, dimensions: set[str]) -> list[dict]:
    """The specialist pools a change's dimensions name, with the people `owners.specialists` binds to each."""
    pools = sorted({config.POOL_OF[d] for d in dimensions if d in config.POOL_OF})
    bound = cfg.specialists if cfg else {}
    return [{"pool": p, "people": list(bound.get(p, []))} for p in pools]


def untested_feature_hint(paths: list[str], *, change_type: str, tracked: list[str]) -> str | None:
    """Advice: a feat whose planned paths add new source files and no test file may want the spec lane, which writes
    the test before the code. None otherwise."""
    from aidd.kernel.repo_paths import looks_like_test

    if change_type != "feat" or any(looks_like_test(p) for p in paths):
        return None
    known = set(tracked)
    new = [p for p in paths if p not in known and p.endswith(SOURCE_EXT)]
    if not new:
        return None
    return (
        f"a new feature in new source files ({', '.join(new[:3])}) with no test file. The route stays as computed, but the spec "
        "lane writes the test first: `aidd new spec <ID> --paths ...` with a test path"
    )


def advice(cfg: Config | None, paths: list[str], *, change_type: str = "feat", irreversible: bool = False, tracked: list[str] | None = None) -> dict:
    """Everything `aidd risk --paths` says, as data (schemas/risk.schema.json)."""
    rs = rule_set(cfg)
    planned = planned_paths(paths, tracked)
    r = route_for(rs, planned, change_type=change_type, irreversible=irreversible)
    level, rule, by_area = edit_level(rs, planned)
    approval = spec_approval_level(cfg, r.route)
    if r.lane == "fast":
        step = "the fast lane: no Spec. Implement and verify with `aidd test`, then ask before it reaches the default branch"
        if level == "ask":
            step = f"the fast lane, in an ask area ({', '.join(a for a in by_area)}): ask before the first edit, naming the paths; then implement and verify with `aidd test`"
    else:
        shown = " ".join(paths[:3]) + (" ..." if len(paths) > 3 else "")
        asks = "ask for Spec approval" if approval == "ask" else "say the Spec is written, and go on"
        step = f'the spec lane: write the Spec and its tests first (`aidd new spec <ID> --title "..." --paths {shown}`), then {asks}'
    hint = untested_feature_hint(paths, change_type=change_type, tracked=tracked or [])
    constraints = config.effective_project(cfg, planned)
    return {
        "paths": list(paths),
        "route": r.route,
        "lane": r.lane,
        "reasons": r.reasons or ["no area or declared risk raised it: the least route is minor"],
        "dimensions": sorted(r.dimensions),
        "areas": [{"area": a, "paths": ps} for a, ps in by_area.items()],
        "edit": {"level": level, "rule": rule.label() if rule else None, "source": rule.source if rule else None},
        "spec_approval": approval,
        "specialists": specialists(cfg, r.dimensions),
        "step": step,
        "hints": [hint] if hint else [],
    } | ({"project": constraints} if constraints else {})
