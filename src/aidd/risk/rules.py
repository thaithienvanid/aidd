"""The risk rules in force in a repository, and the level of one action.

The rules come in layers, each replacing the one before where a rule has the same selector (action, area, branch,
role, environment): the built-in rules (schemas/risks.json), the profile's (schemas/profiles.json), then the config's `risks.rules`,
which its `extends` parents merged first (config.loading.merge_risks keeps a parent's `locked` rule). Areas and actions
merge by id the same way.

A rule a parent config locked wins over every rule it did not lock. Otherwise, of the rules that match an action, the most specific wins: an exact action over a prefix that ends in `.*`, a longer
prefix over a shorter one, and `*` last; then the one with more of area, branch, role, and environment set. Between rules equally
specific, the higher level. With no rule matching, the level is `allow`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from aidd import config
from aidd.config import Config
from aidd.kernel import globs, resources

LEVELS = ("allow", "report", "ask")
LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}
NARROWING = ("area", "branch", "role", "environment")


@dataclass(frozen=True)
class Rule:
    action: str
    level: str
    area: str | None = None
    branch: str | None = None
    role: str | None = None
    locked: bool = False
    reason: str = ""
    source: str = "built-in"  # built-in, profile <name>, config, preset <path or url>, or org preset
    environment: str | None = None  # a name in the config's `environments`, for `deploy.run` there

    @property
    def from_config(self) -> bool:
        """Whether a config set the rule: the repository's own, or a preset it extends."""
        return self.source == "config" or self.source == "org preset" or self.source.startswith("preset ")

    @property
    def selector(self) -> tuple:
        return (self.action, self.area, self.branch, self.role, self.environment)

    def label(self) -> str:
        """The rule as a person reads it: `code.edit in payments: ask`, or `deploy.run to production: ask`."""
        narrow = [
            f"in {self.area}" if self.area else "",
            f"on {self.branch} branch" if self.branch else "",
            f"to {self.environment}" if self.environment else "",
            f"for {self.role}" if self.role else "",
        ]
        return " ".join([self.action, *(n for n in narrow if n)]) + f": {self.level}"


@dataclass
class RuleSet:
    """The areas, actions, and rules in force, with where each rule came from."""

    areas: dict[str, dict]
    actions: dict[str, dict]
    rules: list[Rule]
    ignored: list[str] = field(default_factory=list)  # the config's changes a locked rule set aside, said once
    # The config's `environments`: each a name, and the branch and tag globs whose push deploys there.
    environments: list[dict] = field(default_factory=list)


def builtin() -> dict:
    """schemas/risks.json, as data."""
    return resources.load_json("risks.json")


def _rule(raw: dict, source: str) -> Rule:
    return Rule(
        action=str(raw["action"]),
        level=str(raw["level"]),
        area=raw.get("area"),
        branch=raw.get("branch"),
        role=raw.get("role"),
        locked=bool(raw.get("locked")),
        reason=str(raw.get("reason") or ""),
        source=source,
        environment=raw.get("environment"),
    )


def rule_set(cfg: Config | None) -> RuleSet:
    """The rules in force for `cfg` (the built-in ones alone without a config)."""
    data = builtin()
    areas = copy.deepcopy(data["areas"])
    actions = copy.deepcopy(data["actions"])
    layers: list[tuple[str, list[dict]]] = [("built-in", data["rules"])]
    sources: dict[tuple, str] = {}
    environments: list[dict] = []
    if cfg is not None:
        environments = copy.deepcopy(cfg.get("environments", default=[]) or [])
        profile = config.profiles()["profiles"].get(cfg.profile) or {}
        layers.append((f"profile {cfg.profile}", profile.get("rules", [])))
        risks = cfg.get("risks", default={}) or {}
        areas.update(copy.deepcopy(risks.get("areas") or {}))
        actions.update(copy.deepcopy(risks.get("actions") or {}))
        layers.append(("config", risks.get("rules") or []))
        sources = cfg.rule_sources
        if cfg.get("delegation"):
            # Under a delegation, what it never covers and an install or a local migration could reach rises to ask, so
            # the person decides it. A rise only narrows, so the working tree's config may set it.
            reason = "under a standing delegation, the person decides this"
            layers.append(("delegation", [{"action": a, "level": "ask", "reason": reason} for a in data["delegation"]["rises_to_ask"]]))
    by_selector: dict[tuple, Rule] = {}
    for source, raws in layers:
        for raw in raws:
            r = _rule(raw, sources.get(config.selector(raw), "config") if source == "config" else source)
            by_selector[r.selector] = r
    ignored = list(cfg.warnings) if cfg is not None else []
    return RuleSet(
        areas=areas,
        actions=actions,
        rules=list(by_selector.values()),
        ignored=[w for w in ignored if "risks.rules" in w],
        environments=environments,
    )


def _action_score(pattern: str, action: str) -> int | None:
    """How closely a rule's action matches `action`: the higher, the closer; None when it does not match."""
    if pattern == action:
        return 10_000
    if pattern == "*":
        return 0
    if pattern.endswith(".*") and action.startswith(pattern[:-1]):
        return len(pattern)
    return None


def winning_rule(
    rs: RuleSet, action: str, *, area: str | None = None, branch: str | None = None, role: str | None = None, environment: str | None = None
) -> Rule | None:
    """The rule that decides `action` narrowed by area, branch, role, and environment, or None when no rule matches."""
    best: tuple | None = None
    winner: Rule | None = None
    asked = {"area": area, "branch": branch, "role": role, "environment": environment}
    for r in rs.rules:
        score = _action_score(r.action, action)
        if score is None:
            continue
        if any(getattr(r, k) is not None and getattr(r, k) != asked[k] for k in NARROWING):
            continue
        # A rule a parent config locked wins over every rule it did not lock, however narrow (`aidd risk --list`).
        key = (r.locked, score, sum(getattr(r, k) is not None for k in NARROWING), LEVEL_RANK.get(r.level, 0))
        if best is None or key > best:
            best, winner = key, r
    return winner


def level_of(rs: RuleSet, action: str, **narrow) -> tuple[str, Rule | None]:
    """The level of `action` and the rule that decided it; `allow` with no rule when none matches."""
    r = winning_rule(rs, action, **narrow)
    return (r.level if r else "allow"), r


def level_on_any_branch(rs: RuleSet, action: str, **narrow) -> tuple[str, Rule | None]:
    """`level_of`, and when no branch is named, the highest level over every branch a rule can name, so an action whose
    rules all name a branch, such as `git.push`, never reads as `allow` for want of one. Unsure means the stricter level."""
    if narrow.get("branch") is not None:
        return level_of(rs, action, **narrow)
    found = [level_of(rs, action, **(narrow | {"branch": b})) for b in (None, "own", "default", "shared")]
    return max(found, key=lambda f: LEVEL_RANK[f[0]])


def areas_of(rs: RuleSet, path: str) -> list[str]:
    """The areas `path` is in, in the order the rule set lists them. Matching ignores case, as macOS and Windows do."""
    out = []
    for name, area in rs.areas.items():
        if globs.match_any(area.get("paths", []), path, fold_case=True) and not globs.match_any(area.get("exclude", []), path, fold_case=True):
            out.append(name)
    return out


def edit_level(rs: RuleSet, paths: list[str], *, role: str | None = None) -> tuple[str, Rule | None, dict[str, list[str]]]:
    """The level of `code.edit` over `paths`: the highest over every area they touch, the rule that decided it, and
    each area with the paths in it."""
    by_area: dict[str, list[str]] = {}
    for p in paths:
        for a in areas_of(rs, p):
            by_area.setdefault(a, []).append(p)
    level, rule = level_of(rs, "code.edit", role=role)
    for a in by_area:
        lv, r = level_of(rs, "code.edit", area=a, role=role)
        if LEVEL_RANK[lv] > LEVEL_RANK[level]:
            level, rule = lv, r
    return level, rule, by_area
