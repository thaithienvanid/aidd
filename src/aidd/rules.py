"""Route assessment from paths, declared risk, and configuration.

The gate can raise a route, never lower it. Protected paths always
require major and cannot be switched off.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import depdiff, globs, resources
from .config import Config

ROUTE_RANK = {"standard": 0, "minor": 1, "normal": 2, "major": 3}
LANES = {"standard": "fast", "minor": "fast", "normal": "spec", "major": "spec", "emergency": "emergency"}
MAJOR_DIMENSIONS = {"data", "security", "privacy", "financial", "compliance"}
MAJOR_TYPES = {"data", "security", "compliance"}
# Types that need at least normal whatever the paths: an infrastructure change reaches production outside the code
# paths a rule can name (a console, a pipeline variable, a deploy file in an unusual place).
NORMAL_TYPES = {"infra"}
NEW_BEHAVIOR_TYPES = {"feat", "fix"}
# The specialist pool that reviews each major dimension (and each major type, which shares its name).
POOL_OF = {"data": "data", "security": "security", "privacy": "privacy", "financial": "finance", "compliance": "compliance"}
# Binary document formats: prose, slides, sheets, and pictures that code does not read as config. In a proposal-only
# change, a LOGIC_RULES rule does not match one by path, and none counts as a binary. Elsewhere every rule matches as before.
DOCUMENT_EXTENSIONS = (".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".ods", ".odp", ".png", ".jpg", ".jpeg", ".gif", ".webp")
# The baseline rules about logic, config, or tooling whose paths can match a document. baseline:personal-data is not one:
# personal data in a document is still personal data, so it always matches.
LOGIC_RULES = frozenset(
    {
        "baseline:migrations",
        "baseline:auth",
        "baseline:secrets-crypto",
        "baseline:payments",
        "baseline:build-tooling",
        "baseline:test-config",
        "baseline:quality-config",
        "baseline:iac",
    }
)


# The baseline rule over the standards folder: an edited copy of a library standard, or a team's own standard, needs a
# person's Spec approval, never the fast lane.
STANDARDS_RULE = "baseline:standards"


@dataclass
class Hit:
    rule: str
    path: str
    route: str
    dimensions: list[str] = field(default_factory=list)
    pools: list[str] = field(default_factory=list)
    dependency: str | None = None  # the added dependency that matched; `path` is then its manifest


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
        dict(r, exclude=list(r.get("exclude", [])) + list(extra.get(r["name"], [])), skip_documents=r["name"] in LOGIC_RULES)
        for r in resources.baseline()["risk_rules"]
        if r["name"] not in disabled
    ]
    for r in base:
        # The standards folder is under the docs folder the config names (`[docs] dir`), wherever that is.
        if r["name"] == STANDARDS_RULE and cfg.docs_dir != "docs":
            r["paths"] = [*r["paths"], globs.under(cfg.docs_dir, "standards/**")]
    return base + list(cfg.get("risk_rules", default=[]))


def rule_pools(rule: dict) -> list[str]:
    """The specialist pools a rule names: its specialists, else the pools of its dimensions, else security when it forces major."""
    if rule.get("specialists"):
        return list(rule["specialists"])
    pools = sorted({POOL_OF[d] for d in rule.get("dimensions", []) if d in POOL_OF})
    return pools or (["security"] if rule.get("route") == "major" else [])


def scan(paths: list[str], cfg: Config, dependencies: list[dict] | None = None, binary_paths: list[str] | tuple[str, ...] = ()) -> list[Hit]:
    """Path hits, then dependency hits. Path matching ignores case: macOS and Windows checkouts treat `Migrations/` and
    `migrations/` alike. A rule's `dependencies` match each dependency the diff adds to a manifest ({file, name}, from
    `depdiff.added`), wherever the code that uses it sits; the rule's `exclude` applies to the manifest's path.
    In a proposal-only change, a `LOGIC_RULES` rule does not match a binary document by path: a file in `binary_paths`
    (binary to git) whose name has a `DOCUMENT_EXTENSIONS` extension. A text file with such a name matches as before."""
    hits: list[Hit] = []
    protected = protected_paths(cfg)
    rules = active_rules(cfg)
    proposal = bool(proposal_only(paths, cfg))
    binary = set(binary_paths)
    for path in paths:
        if globs.first_match(protected, path, fold_case=True):
            hits.append(Hit("protected", path, "major", [], ["security"]))
        document = proposal and path in binary and path.lower().endswith(DOCUMENT_EXTENSIONS)
        for rule in rules:
            if (
                not (document and rule.get("skip_documents"))
                and globs.match_any(rule.get("paths", []), path, fold_case=True)
                and not globs.match_any(rule.get("exclude", []), path, fold_case=True)
            ):
                hits.append(Hit(rule["name"], path, rule.get("route", "minor"), list(rule.get("dimensions", [])), rule_pools(rule)))
    for dep in dependencies or []:
        for rule in rules:
            if (
                rule.get("dependencies")
                and depdiff.match(dep["name"], rule["dependencies"])
                and not globs.match_any(rule.get("exclude", []), dep["file"], fold_case=True)
            ):
                hits.append(Hit(rule["name"], dep["file"], rule.get("route", "minor"), list(rule.get("dimensions", [])), rule_pools(rule), dep["name"]))
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


def spec_phase(paths: list[str], frozen: list[str], task_scopes: list[list[str]]) -> bool:
    """Whether a Spec-backed change is still in its Spec phase: every changed path is the Spec, a frozen test, design
    file, or doc, the backfill (`frozen`), and some Task's scope has no change yet. Its tests are expected to fail on head
    until Implement, so the gate and `aidd test` treat a failure there as early proof, not as a broken change."""
    if not paths or not all(globs.match_any(frozen, p) for p in paths):
        return False
    return any(not any(globs.match_any(scope, p) for p in paths) for scope in task_scopes)


def budget_lines(files: list[dict], cfg: Config, reviewed: list[str] | tuple[str, ...] = ()) -> int:
    """The changed lines the budget counts: every file's additions and deletions, except under `budget_exclude_paths`
    and in `reviewed`, the Spec with its tests.files, design.files, and frozen docs (reviewed at Spec approval, so the budget measures
    what is left to review at Merge approval) and an emergency backfill. The gate and `aidd assess` both count with this."""
    excluded = list(cfg.get("budget_exclude_paths", default=[])) + list(reviewed)
    return sum(f["additions"] + f["deletions"] for f in files if not globs.match_any(excluded, f["path"]))


def binary_paths(files: list[dict]) -> list[str]:
    """The paths git shows as binary in a diff (numstat `-`), for `scan` and `counted_binaries`."""
    return [f["path"] for f in files if f.get("binary")]


def counted_binaries(files: list[dict], cfg: Config, paths: list[str] | None = None) -> int:
    """The binary files the minor route counts, because a line budget cannot measure them. In a proposal-only change a
    binary document (`DOCUMENT_EXTENSIONS`) does not count: its line budget is lifted too. Any other binary counts, inside
    the proposals folder or out. `paths` are every path the change touches (default: the paths of `files`), the same
    ones `scan` reads, so the gate, `aidd assess`, and `aidd describe` decide "proposal-only" alike."""
    proposal = bool(proposal_only(changed_paths(files) if paths is None else paths, cfg))
    return sum(1 for f in files if f.get("binary") and not (proposal and f["path"].lower().endswith(DOCUMENT_EXTENSIONS)))


def proposal_only(paths: list[str], cfg: Config) -> list[str]:
    """Every path of a change that touches only the proposals folder, else none. A Proposal is decided by its own go/no-go
    and sign-off, and its prose by the person who signs it, so it needs no Spec and leaves nothing to count against the
    line budget; a change that also touches anything else counts in full."""
    folder = globs.under(cfg.proposals_dir, "")
    return list(paths) if paths and all(p.startswith(folder) for p in paths) else []


def required_tests(
    config_tests: list[dict], declared: list[dict], source: str, paths: list[str], route: str | None = None
) -> tuple[list[tuple[dict, str]], list[str]]:
    """The (command, source) pairs this diff must run, and any names declared twice.

    On the emergency route the repository suite is its `smoke = true` commands when it marks any (else all of it), and
    the change's own commands add to them. The runner and the gate both call this, so they can never disagree on
    which tests apply.
    """
    if route == "emergency" and any(c.get("smoke") for c in config_tests):
        config_tests = [c for c in config_tests if c.get("smoke")]
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
    dependencies: list[dict] | None = None,
    binary_paths: list[str] | tuple[str, ...] = (),
) -> Assessment:
    """The minimum route for a change, the dimensions it implies, and the specialist pools a major change needs.
    `dependencies` are the ones the diff adds to its manifests ({file, name}); a rule that names one fires on it."""
    hits = scan(paths, cfg, dependencies, binary_paths)
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
        what = f"dependency {h.dependency} added in {h.path}" if h.dependency else h.path
        reasons.append(f"{label} matched {what} -> at least {h.route}")
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
    elif ctype in NORMAL_TYPES and ROUTE_RANK[required] < ROUTE_RANK["normal"]:
        required = "normal"
        reasons.append(f"type {ctype} -> at least normal")
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


MAX_EXPANDED = 2000  # tracked files one planned glob may stand for, so a `**` over a monorepo stays quick


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
    tracked: list[str] | None = None,
    dependencies: list[dict] | None = None,
) -> Assessment:
    """The minimum route for planned paths or globs, before any code exists: what `aidd assess --paths`, `aidd new spec --paths`,
    the MCP `assess` tool, and the routing evals compute. Advisory: the gate recomputes it from the real diff and can only raise it.

    With `tracked` (the repository's files, `git ls-files`), a glob or a folder also stands for every tracked file it
    matches, so a protected or risky file inside it raises the route and the reason names that file, not a sample.
    `dependencies` ({file, name}) are the ones the plan adds to a manifest, as a routing scenario names them."""
    planned = [planned_path(p) for p in paths]
    for p in paths if tracked else []:
        if any(c in p for c in "*?") or p.endswith("/"):
            pattern = p.removeprefix("./") + ("**" if p.endswith("/") else "")
            planned += [t for t in tracked or [] if globs.match_any([pattern], t)][:MAX_EXPANDED]
    planned = list(dict.fromkeys(planned))
    return assess(
        paths=planned,
        cfg=cfg,
        ctype=ctype,
        risk={"dimensions": list(dimensions), "reversible": not irreversible},
        confidence="high",
        task_count=1,
        changed_lines=changed_lines,
        binary_files=binary_files,
        dependencies=dependencies,
        binary_paths=[p for p in planned if p.lower().endswith(DOCUMENT_EXTENSIONS)],  # a planned document; the gate checks git's view
    )


def risk_packs(cfg: Config, dimensions: set[str]) -> list[dict]:
    """The domain packs a change's risk calls for ({pack, reason}), whatever its dependencies: privacy-by-default on the
    privacy dimension or a `gdpr` compliance target (`[project.compliance].targets`, read defensively: absent or
    malformed means none)."""
    targets = cfg.get("project", "compliance", "targets", default=[])
    gdpr = isinstance(targets, list) and any(isinstance(t, str) and t.lower() == "gdpr" for t in targets)
    if "privacy" in dimensions:
        return [{"pack": "privacy-by-default", "reason": "the privacy dimension"}]
    if gdpr:
        return [{"pack": "privacy-by-default", "reason": "the gdpr compliance target"}]
    return []


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

    `aidd assess` shows it for the branch; the gate recomputes the route from the real diff and can only raise it."""
    from pathlib import Path

    from . import config as cfgmod
    from . import gitutil, inputs

    top = str(Path(root))
    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, top, skip_unread=True)  # a local view: an unread URL parent warns
        base_name = base or inputs.default_base(top)
        fork = gitutil.merge_base(gitutil.rev_parse(base_name, top), gitutil.rev_parse("HEAD", top), top)
        committed = gitutil.numstat(fork, "HEAD", top)
        changed = gitutil.run(["diff", "--name-only", "-z", fork], top, check=False).split("\0")
        changed += gitutil.run(["ls-files", "--others", "--exclude-standard", "-z"], top, check=False).split("\0")
        paths = sorted({p for p in changed if p} | set(changed_paths(committed)))
        if not paths:
            return None
        lines = budget_lines(committed, cfg, _reviewed_on_branch(top, cfg, paths) + proposal_only(paths, cfg))
        deps = depdiff.added(paths, lambda p: gitutil.show(fork, p, top), lambda p: _worktree_text(top, p))
        a = assess(
            paths=paths,
            cfg=cfg,
            ctype=ctype,
            risk={"dimensions": [], "reversible": True},
            confidence="high",
            task_count=1,
            changed_lines=lines,
            binary_files=counted_binaries(committed, cfg, paths),
            dependencies=deps,
            binary_paths=binary_paths(committed),
        )
    except Exception:  # noqa: BLE001  # advice, never a failure: `aidd assess` and the session hook must still answer
        return None
    out = summary(a, f"this branch's diff against {base_name} ({len(paths)} path{'s' if len(paths) != 1 else ''})")
    out["paths"] = paths
    out["changed_lines"] = lines
    from .detect import dependency_packs

    if packs := dependency_packs(deps) + risk_packs(cfg, a.dimensions):
        # The domain packs the added dependencies and the risk call for, so the team loads them wherever the code sits.
        out["packs"] = packs
    if proposal_only(paths, cfg):
        out["reasons"].append("a proposal-only change: a person decides it at its go/no-go and sign-off, so its lines and documents do not count")
    return out


def _worktree_text(root: str, rel: str) -> str | None:
    """A file as the working tree has it, or None when it is gone: the branch's head for `aidd assess`."""
    from pathlib import Path

    try:
        return (Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _reviewed_on_branch(root: str, cfg: Config, paths: list[str]) -> list[str]:
    """What the gate leaves out of the budget for this branch: each Spec (or emergency backfill) the diff adds or
    changes, with its tests.files, design.files, and frozen docs, as the working tree has them."""
    from pathlib import Path

    from . import model

    out: list[str] = []
    for rel in paths:
        if not (rel.startswith(globs.under(cfg.specs_dir, "")) and rel.endswith(".md")):
            continue
        try:
            data, _ = model.split_front_matter((Path(root) / rel).read_text(encoding="utf-8", errors="replace"), rel)
        except (OSError, model.ModelError):
            continue
        if data.get("kind") == "spec":
            out += [rel, *((data.get("tests") or {}).get("files") or []), *model.design_paths(data)]
    return [p for p in out if isinstance(p, str)]


def lane_step(root, *, has_spec: bool = False, summary: dict | None = None) -> dict | None:
    """`aidd assess`'s step for a change no Spec on the branch carries: what its lane asks for next, from `summary` (the
    route of planned paths) or else the branch's diff. None when there is no diff, or a Spec on the branch carries the
    change (its own steps say what is next). The same fields as every other step (`nextstep._step`), plus route and lane."""
    r = summary or (None if has_spec else assess_diff(root))
    if r is None or has_spec or LANES[r["route"]] == "emergency":
        return None
    if LANES[r["route"]] == "fast":
        from .localctx import platform_of

        what = "the fast lane: no Spec needed"
        if platform_of(str(root)) == "local":
            # `describe --commit` adds a commit, so the head moves: the tests run after it, on the head that ships.
            how = (
                "Implement and Verify, repeated until green. Then `aidd describe --commit` records the Change Request block in a new "
                "commit (the head moves). Then run `aidd test` on that head, and a person runs `aidd ship`"
            )
        else:
            how = (
                "Implement and Verify, repeated until green (`aidd test`); then `aidd describe` prints the Change Request block for the "
                "PR/MR (`aidd describe --commit` records it on the branch for a local ship)"
            )
    else:
        paths = r.get("paths") or []
        what = "the spec lane: this change needs a Spec, approved before any code"
        how = f'write the Spec and its tests first: `aidd new spec <ID> --title "..." --paths {" ".join(paths[:3])}{" ..." if len(paths) > 3 else ""}`'
    return {"code": "lane", "where": "", "what": what, "who": "agent", "how": how, "route": r["route"], "lane": r["lane"]}


SOURCE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".php", ".dart", ".swift", ".ex")


def untested_feature_hint(paths: list[str], *, ctype: str, tracked: list[str]) -> str | None:
    """Advice, never a route: a feat whose planned paths add new source files and no test file may want the spec lane,
    which writes the test before the code. None otherwise."""
    from .guard import looks_like_test

    if ctype != "feat" or any(looks_like_test(p) for p in paths):
        return None
    known = set(tracked)
    new = [p for p in paths if p not in known and p.endswith(SOURCE_EXT)]
    if not new:
        return None
    return (
        f"a new feature in new source files ({', '.join(new[:3])}) with no test file. The route stays as computed, but the spec "
        "lane writes the test first. `aidd new spec <ID> --force --paths ...` with a test path writes one"
    )


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
