"""Route assessment from paths, declared risk, and configuration.

The verifier can raise a route, never lower it. Protected paths always
require major and cannot be switched off.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import globs, resources
from .config import Config

ROUTE_RANK = {"standard": 0, "minor": 1, "normal": 2, "major": 3}
LANES = {"standard": "fast", "minor": "fast", "normal": "spec", "major": "spec", "emergency": "emergency"}
MAJOR_DIMENSIONS = {"data", "security", "privacy", "financial", "compliance"}
MAJOR_TYPES = {"data", "security", "compliance"}
NEW_BEHAVIOR_TYPES = {"feat", "fix"}
# The specialist pool that reviews each major dimension (and each major type, which shares its name).
POOL_OF = {"data": "data", "security": "security", "privacy": "privacy", "financial": "finance", "compliance": "compliance"}


@dataclass
class Hit:
    rule: str
    path: str
    route: str
    dimensions: list[str] = field(default_factory=list)
    pools: list[str] = field(default_factory=list)


@dataclass
class Assessment:
    required_route: str
    dimensions: set[str]
    pools: set[str]
    hits: list[Hit]
    reasons: list[str]

    @property
    def lane(self) -> str:
        return LANES[self.required_route]


def _command_paths(command: list[str] | None) -> list[str]:
    """What a bound command runs, such as ./scripts/aidd-policy: its whole directory, because a script
    reads its neighbours (a policy.rego, a helper). A script at the root protects only itself."""
    out = []
    for arg in command or []:
        s = arg.replace("\\", "/")
        if s.startswith("-") or s.startswith("/") or "://" in s or ("/" not in s and not s.startswith(".")):
            continue
        while s.startswith("./"):
            s = s[2:]
        if s and not s.startswith("../"):
            out.append(s.rsplit("/", 1)[0] + "/**" if "/" in s else s)
    return out


def protected_paths(cfg: Config) -> list[str]:
    commands = _command_paths(cfg.get("policy", "command")) + _command_paths(cfg.get("observe", "command"))
    return list(resources.baseline()["protected_paths"]) + list(cfg.get("protected_paths", default=[])) + commands


def active_rules(cfg: Config) -> list[dict]:
    disabled = set(cfg.get("disable_rules", default=[]))
    extra = cfg.get("rule_exclusions", default={})
    base = [
        dict(r, exclude=list(r.get("exclude", [])) + list(extra.get(r["name"], []))) for r in resources.baseline()["risk_rules"] if r["name"] not in disabled
    ]
    return base + list(cfg.get("risk_rules", default=[]))


def rule_pools(rule: dict) -> list[str]:
    """The specialist pools a rule names: its reviewers, else the pools of its dimensions, else security when it forces major."""
    if rule.get("reviewers"):
        return list(rule["reviewers"])
    pools = sorted({POOL_OF[d] for d in rule.get("dimensions", []) if d in POOL_OF})
    return pools or (["security"] if rule.get("route") == "major" else [])


def scan(paths: list[str], cfg: Config) -> list[Hit]:
    """Path hits. Matching ignores case: macOS and Windows checkouts treat `Migrations/` and `migrations/` alike."""
    hits: list[Hit] = []
    protected = protected_paths(cfg)
    rules = active_rules(cfg)
    for path in paths:
        if globs.first_match(protected, path, fold_case=True):
            hits.append(Hit("protected", path, "major", [], ["security"]))
        for rule in rules:
            if globs.match_any(rule["paths"], path, fold_case=True) and not globs.match_any(rule.get("exclude", []), path, fold_case=True):
                hits.append(Hit(rule["name"], path, rule.get("route", "minor"), list(rule.get("dimensions", [])), rule_pools(rule)))
    return hits


def select_tests(commands: list[dict], paths: list[str]) -> list[dict]:
    """Commands that apply to this diff: those without when_changed, and those whose globs match a changed path.

    Matching ignores case, like risk rules: a pattern that adds a requirement must not miss `DB/` for `db/`.
    Patterns that grant scope or exemptions (scope, scope_exempt_paths, budget_exclude_paths) stay exact.
    """
    return [c for c in commands if not c.get("when_changed") or any(globs.match_any(c["when_changed"], p, fold_case=True) for p in paths)]


def changed_paths(files: list[dict]) -> list[str]:
    """Every path a diff touches, including rename sources."""
    return sorted({f["path"] for f in files} | {f["previous_path"] for f in files if f.get("previous_path")})


def budget_lines(files: list[dict], cfg: Config, reviewed: list[str] | tuple[str, ...] = ()) -> int:
    """The changed lines the budget counts: every file's additions and deletions, except under `budget_exclude_paths`
    and in `reviewed`, the Spec with its tests.files and design.files (reviewed at Spec approval, so the budget measures
    what is left to review at Merge approval) and an emergency backfill. The gate and `aidd next` both count with this."""
    excluded = list(cfg.get("budget_exclude_paths", default=[])) + list(reviewed)
    return sum(f["additions"] + f["deletions"] for f in files if not globs.match_any(excluded, f["path"]))


def required_tests(config_tests: list[dict], declared: list[dict], source: str, paths: list[str]) -> tuple[list[tuple[dict, str]], list[str]]:
    """The (command, source) pairs this diff must run, and any names declared twice.

    The runner and the verifier both call this, so they can never disagree on which tests apply.
    """
    pairs = [(c, "config") for c in config_tests] + [(c, source) for c in declared]
    names = [c["name"] for c, _ in pairs]
    dupes = sorted({n for i, n in enumerate(names) if n in names[:i]})
    selected = select_tests([c for c, _ in pairs], paths)
    return [(c, src) for c, src in pairs if any(c is s for s in selected)], dupes


def assess(
    *,
    paths: list[str],
    cfg: Config,
    ctype: str,
    risk: dict,
    confidence: str,
    task_count: int,
    changed_lines: int,
    standard_ok: bool = False,
    binary_files: int = 0,
) -> Assessment:
    """The minimum route for a change, the dimensions it implies, and the specialist pools a major change needs."""
    hits = scan(paths, cfg)
    reasons: list[str] = []
    dims = set(risk.get("dimensions", []))
    pools: set[str] = set()
    required = "minor"
    first: dict[str, Hit] = {}  # the first hit of each rule, in order: one reason per rule
    for h in hits:
        dims.update(h.dimensions)
        if ROUTE_RANK[h.route] > ROUTE_RANK[required]:
            required = h.route
        if h.route == "major":
            pools.update(h.pools)
        first.setdefault(h.rule, h)
    for h in first.values():
        label = "protected path" if h.rule == "protected" else f"rule {h.rule}"
        reasons.append(f"{label} matched {h.path} -> at least {h.route}")
    major_dims = dims & MAJOR_DIMENSIONS
    if major_dims:
        required = "major"
        pools.update(POOL_OF[d] for d in major_dims)
        reasons.append(f"dimensions {sorted(major_dims)} -> major")
    if risk.get("reversible") is False:
        required = "major"
        reasons.append("not reversible -> major")
    if ctype in MAJOR_TYPES:
        required = "major"
        pools.add(POOL_OF[ctype])
        reasons.append(f"type {ctype} -> major")
    if required == "major" and not pools:
        pools.add("security")
    if standard_ok and required != "major":
        # A configured standard class is a pre-accepted risk up to normal; major never qualifies.
        return Assessment("standard", dims, set(), hits, reasons + ["matches a configured standard change -> standard"])
    if required == "minor":
        budget = cfg.gates["max_changed_lines"].get("minor")
        problems = []
        if confidence != "high":
            problems.append(f"confidence {confidence}")
        if task_count > 1:
            problems.append(f"{task_count} tasks")
        if dims:
            problems.append(f"dimensions {sorted(dims)}")
        if budget is not None and changed_lines > budget:
            problems.append(f"{changed_lines} changed lines > minor budget {budget}")
        if binary_files:
            problems.append(f"{binary_files} binary file(s), which a line budget cannot measure")
        if problems:
            required = "normal"
            reasons.append("not minor: " + ", ".join(problems) + " -> normal")
    return Assessment(required, dims, pools if required == "major" else set(), hits, reasons)


def planned_path(p: str) -> str:
    """A planned path as the rules see it: a glob or a folder becomes a sample path inside it."""
    return globs.sample_path(p) if any(c in p for c in "*?") or p.endswith("/") else p.removeprefix("./")


def assess_paths(
    cfg: Config,
    paths: list[str],
    *,
    ctype: str = "feat",
    dimensions: list[str] | tuple[str, ...] = (),
    irreversible: bool = False,
    changed_lines: int = 0,
    binary_files: int = 0,
) -> Assessment:
    """The minimum route for planned paths or globs, before any code exists: what `aidd new spec --paths`, the MCP
    `next` tool, and the routing evals compute. Advisory: the gate recomputes it from the real diff and can only raise it."""
    return assess(
        paths=[planned_path(p) for p in paths],
        cfg=cfg,
        ctype=ctype,
        risk={"dimensions": list(dimensions), "reversible": not irreversible},
        confidence="high",
        task_count=1,
        changed_lines=changed_lines,
        binary_files=binary_files,
    )


def summary(a: Assessment, basis: str) -> dict:
    """An assessment as data: the route, its lane, and why."""
    return {
        "route": a.required_route,
        "lane": a.lane,
        "reasons": list(a.reasons),
        "dimensions": sorted(a.dimensions),
        "pools": sorted(a.pools),
        "basis": basis,
    }


def reason_lines(a: Assessment | dict) -> list[str]:
    """The reasons as a person reads them; a change no rule raised says so, rather than printing nothing."""
    reasons = a["reasons"] if isinstance(a, dict) else a.reasons
    return list(reasons) or ["no risk rule, protected path, or declared risk raised it: the minimum is minor"]


def assess_diff(root, base: str | None = None, *, ctype: str = "feat") -> dict | None:
    """The route and lane for the current branch's diff against its merge-base with `base` (default: the repository's
    default branch): committed, staged, unstaged, and untracked paths. None when there is no diff or it cannot tell.

    `aidd next` shows it for the branch; the gate recomputes the route from the real diff and can only raise it."""
    from pathlib import Path

    from . import config as cfgmod
    from . import gitutil, inputs

    top = str(Path(root))
    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, top)
        base_name = base or inputs.default_base(top)
        fork = gitutil.merge_base(gitutil.rev_parse(base_name, top), gitutil.rev_parse("HEAD", top), top)
        committed = gitutil.numstat(fork, "HEAD", top)
        changed = gitutil.run(["diff", "--name-only", "-z", fork], top, check=False).split("\0")
        changed += gitutil.run(["ls-files", "--others", "--exclude-standard", "-z"], top, check=False).split("\0")
        paths = sorted({p for p in changed if p} | set(changed_paths(committed)))
        if not paths:
            return None
        lines = budget_lines(committed, cfg, _reviewed_on_branch(top, cfg, paths))
        a = assess(
            paths=paths,
            cfg=cfg,
            ctype=ctype,
            risk={"dimensions": [], "reversible": True},
            confidence="high",
            task_count=1,
            changed_lines=lines,
            binary_files=sum(1 for f in committed if f.get("binary")),
        )
    except Exception:  # noqa: BLE001  # advice, never a failure: `aidd next` and the session hook must still answer
        return None
    out = summary(a, f"this branch's diff against {base_name} ({len(paths)} path{'s' if len(paths) != 1 else ''})")
    out["paths"] = paths
    out["changed_lines"] = lines
    return out


def _reviewed_on_branch(root: str, cfg: Config, paths: list[str]) -> list[str]:
    """What the gate leaves out of the budget for this branch: each Spec (or emergency backfill) the diff adds or
    changes, with its tests.files and design.files, as the working tree has them."""
    from pathlib import Path

    from . import model

    out: list[str] = []
    for rel in paths:
        if not (rel.startswith(cfg.specs_dir.rstrip("/") + "/") and rel.endswith(".md")):
            continue
        try:
            data, _ = model.split_front_matter((Path(root) / rel).read_text(encoding="utf-8", errors="replace"), rel)
        except (OSError, model.ModelError):
            continue
        if data.get("kind") == "spec":
            out += [rel, *((data.get("tests") or {}).get("files") or []), *((data.get("design") or {}).get("files") or [])]
    return [p for p in out if isinstance(p, str)]


def route_step(root, *, has_spec: bool = False) -> dict | None:
    """`aidd next`'s step for the branch's diff (the entry rule): the computed route and lane, why, and what the lane
    asks for next. The same fields as every other step (`nextstep._step`), plus route, lane, and reasons."""
    r = assess_diff(root)
    if r is None:
        return None
    if LANES[r["route"]] == "fast":
        how = "the fast lane: implement ⟲ verify with `aidd test`, then `aidd change` prints the toml aidd block for the PR/MR"
    elif has_spec:
        how = "the spec lane: the Spec on this branch carries it; its route must be at least this, and the gate checks"
    else:
        how = f'the spec lane: write a Spec first, `aidd new spec <ID> --title "..." --paths {" ".join(r["paths"][:3])}{" ..." if len(r["paths"]) > 3 else ""}`'
    return {
        "code": "route",
        "where": "",
        "what": f"{r['basis']} needs route {r['route']} ({r['lane']} lane): " + "; ".join(reason_lines(r)),
        "who": "your agent",
        "how": how,
        "route": r["route"],
        "lane": r["lane"],
        "reasons": r["reasons"],
    }


def standard_match(entry: dict, *, paths: list[str], identities: set[str], changed_lines: int) -> list[str]:
    """Return the reasons a change does not qualify for this standard change; empty means it does."""
    problems = []
    # A class's paths grant merge rights, so they match exactly: case folding would widen the grant.
    outside = [p for p in paths if not globs.match_any(entry["paths"], p)]
    if outside:
        problems.append(f"paths outside the class: {', '.join(outside[:5])}")
    allowed = {a.lstrip("@").lower() for a in entry["authors"]}
    strangers = sorted(i for i in identities if i not in allowed)
    if strangers:
        problems.append(f"authors not in the class: {', '.join(strangers)}")
    limit = entry.get("max_changed_lines")
    if limit is not None and changed_lines > limit:
        problems.append(f"{changed_lines} changed lines > {limit}")
    return problems
