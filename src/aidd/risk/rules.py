"""The risk rules in force in a repository, and the level of one action.

The rules come in layers, each replacing the one before where a rule has the same selector (action, area, branch,
role, environment, environment_shared, route): the built-in rules (schemas/risks.json), the profile's (schemas/profiles.json),
then the config's `risks.rules`, which its `extends` parents merged first (config.loading.merge_risks keeps a parent's
`locked` rule). Areas and actions merge by id the same way. A rule with no `route` also replaces the lower layers' rules
that differ from it only by route, so a config's `spec.approve: ask` asks on every route.

A rule a parent config locked is a floor, and it replaces no rule: it sits beside the rules below it, so a lock raises
a level and never lowers one, whatever it names. Of the rules that match an action, the most specific wins: an exact
action over a prefix that ends in `.*`, a longer prefix over a shorter one, and `*` last; then the one with more of
area, branch, role, environment, environment_shared, and route set. Between rules equally specific, the higher level.
The most specific locked rule and the most specific rule not locked each match, and the higher of the two levels
decides. With no rule matching, the level is `allow`. `environment_shared` comes from the config's `environments`: an
environment is shared unless it says `shared: false`.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from aidd import config
from aidd.config import Config
from aidd.kernel import globs, resources
from aidd.kernel.text import closest

# The levels of a rule, lowest first, and the branches a rule can name, from schemas/risks.json; with `None` first, every
# reading of "no branch named, then each one".
LEVELS: tuple[str, ...] = tuple(resources.load_json("risks.json")["levels"])
LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}
BRANCHES: tuple[str, ...] = tuple(resources.load_json("risks.json")["branches"])
ANY_BRANCH: tuple[str | None, ...] = (None, *BRANCHES)
NARROWING = config.SELECTOR[1:]
DELEGATION_REASON = "under a standing delegation, the person decides this"


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
    environment_shared: bool | None = None  # whether that environment is shared, as the config marks it
    route: str | None = None  # the route of the change, for `spec.approve`: normal or major

    @property
    def from_config(self) -> bool:
        """Whether a config set the rule: the repository's own, or a preset it extends."""
        return self.source == "config" or self.source == "org preset" or self.source.startswith("preset ")

    @property
    def selector(self) -> tuple:
        return tuple(getattr(self, k) for k in config.SELECTOR)

    def label(self) -> str:
        """The rule as a person reads it: `code.edit in payments: ask`, or `deploy.run to production: ask`."""
        narrow = [
            f"in {self.area}" if self.area else "",
            f"on {self.branch} branch" if self.branch else "",
            f"to {self.environment}" if self.environment else "",
            "to your own environment" if self.environment_shared is False else "to a shared environment" if self.environment_shared else "",
            f"for {self.role}" if self.role else "",
            f"on a {self.route} change" if self.route else "",
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
        environment_shared=raw.get("environment_shared"),
        route=raw.get("route"),
    )


def rule_set(cfg: Config | None) -> RuleSet:
    """The rules in force for `cfg`: the built-in ones, the profile's, and the config's. Without a config, the solo profile applies."""
    data = builtin()
    areas = copy.deepcopy(data["areas"])
    actions = copy.deepcopy(data["actions"])
    profile_name = (cfg or config.EMPTY).profile
    layers: list[tuple[str, list[dict]]] = [
        ("built-in", data["rules"]),
        (f"profile {profile_name}", (config.profiles()["profiles"].get(profile_name) or {}).get("rules", [])),
    ]
    sources: dict[tuple, str] = {}
    environments: list[dict] = []
    if cfg is not None:
        environments = copy.deepcopy(cfg.get("environments", default=[]) or [])
        risks = cfg.get("risks", default={}) or {}
        areas.update(copy.deepcopy(risks.get("areas") or {}))
        actions.update(copy.deepcopy(risks.get("actions") or {}))
        layers.append(("config", risks.get("rules") or []))
        sources = cfg.rule_sources
    delegated = cfg is not None and bool(cfg.get("delegation"))
    risen, exceptions = _rise(data["delegation"]["rises_to_ask"] if delegated else [])
    if exceptions:
        environments = [_shared_by_wildcard(e) for e in environments]
    # Under a delegation, what it never covers and an install, a local migration, or a deploy could reach rises to ask,
    # so the person decides it. A rise only raises, so the working tree's config may set it. It is locked, so it is a floor
    # over a parent's locked rule for a prefix or for every action, since it moves only toward the person deciding. The one cell it
    # leaves is the built-in rule an `except` selector names, such as the one for the developer's own environment, because
    # nobody else uses it. That rule outranks the rise by being narrower, so the rise is not locked for such an action, and
    # only while no config locks a rule for the action: a lock is a parent's word that it asks.
    open_cells = {
        a: sels
        for a, sels in exceptions.items()
        if not any(raw.get("locked") and config.action_matches(str(raw["action"]), a) for _, raws in layers for raw in raws)
    }
    layers.append(("delegation", [{"action": a, "level": "ask", "reason": DELEGATION_REASON, "locked": a not in open_cells} for a in risen]))
    kept = _layered(layers, sources)
    # Every rule of a risen action rises with it, whatever narrows it, so a narrower rule never keeps the level lower,
    # except the built-in rule for the developer's own environment of an open cell.
    for i, r in enumerate(kept):
        own_cell = r.source == "built-in" and any(all(getattr(r, k) == v for k, v in cell.items()) for cell in open_cells.get(r.action, []))
        if r.action in risen and r.level != "ask" and not own_cell:
            kept[i] = replace(r, level="ask", reason=DELEGATION_REASON, source="delegation")
    ignored = list(cfg.warnings) if cfg is not None else []
    return RuleSet(
        areas=areas,
        actions=actions,
        rules=kept,
        ignored=[w for w in ignored if "risks.rules" in w],
        environments=environments,
    )


def _layered(layers: list[tuple[str, list[dict]]], sources: dict[tuple, str]) -> list[Rule]:
    """The rules of every layer, a rule replacing the layers' before it at its selector. A rule a parent config locked
    replaces none: it is a floor beside the rules below, so a lock never lowers a level (`winning_rule`)."""
    by_selector: dict[tuple, Rule] = {}
    locks: dict[tuple, Rule] = {}
    for source, raws in layers:
        found = [_rule(raw, sources.get(config.selector(raw), "config") if source == "config" else source) for raw in raws]
        # A rule for every route replaces the lower layers' rules that differ from it only by route, so a config's
        # `spec.approve: ask` is never set aside by the profile's rule for the normal route.
        for r in found:
            if not r.locked:
                for sel in config.route_rules_under(r.selector, by_selector):
                    del by_selector[sel]
        for r in found:
            (locks if r.locked else by_selector)[r.selector] = r
    return [*by_selector.values(), *locks.values()]


def _rise(items: list) -> tuple[list[str], dict[str, list[dict]]]:
    """The actions that rise to `ask` under a delegation, and for each action with an `except`, the selectors of its one
    exception: the built-in rules that match one keep their level. An item is an action id or `{action, except}`, and a
    selector holds `environment_shared` alone, as the schema says."""
    risen = [i if isinstance(i, str) else i["action"] for i in items]
    cells = {i["action"]: i["except"] for i in items if isinstance(i, dict) and i.get("except")}
    for action, selectors in cells.items():
        for cell in selectors:
            if not isinstance(cell, dict) or set(cell) != {"environment_shared"}:
                raise ValueError(
                    f"schemas/risks.json delegation.rises_to_ask: the `except` of {action} holds {cell!r}, but a selector is `{{environment_shared: true|false}}` alone"
                )
    return risen, cells


def _shared_by_wildcard(env: dict) -> dict:
    """The environment as a delegation reads it: one marked `shared: false` that a wildcard glob names reads as shared,
    because such a glob can match other people's branches and tags, so only an environment named with no wildcard stays the
    developer's own."""
    if env.get("shared") is False and any(globs.is_pattern(str(g)) for g in [*(env.get("branches") or []), *(env.get("tags") or [])]):
        return {k: v for k, v in env.items() if k != "shared"}
    return env


def _action_score(pattern: str, action: str) -> int | None:
    """How closely a rule's action matches `action`: the higher, the closer; None when it does not match."""
    if not config.action_matches(pattern, action):
        return None
    return 10_000 if pattern == action else 0 if pattern == "*" else len(pattern)


def winning_rule(
    rs: RuleSet,
    action: str,
    *,
    area: str | None = None,
    branch: str | None = None,
    role: str | None = None,
    environment: str | None = None,
    route: str | None = None,
) -> Rule | None:
    """The rule that decides `action` narrowed by area, branch, role, environment, and route, or None when no rule
    matches. Whether the environment is shared comes from the config's `environments`, never from the caller. With no
    `route`, a rule that names one never matches, so an unsure caller reads the rule for every route."""
    best: dict[bool, tuple[tuple, Rule]] = {}  # by whether a parent locked the rule: its key and the most specific rule
    shared = None if environment is None else environment_is_shared(rs, environment)
    asked = {"area": area, "branch": branch, "role": role, "environment": environment, "environment_shared": shared, "route": route}
    for r in rs.rules:
        score = _action_score(r.action, action)
        if score is None:
            continue
        if any(getattr(r, k) is not None and getattr(r, k) != asked[k] for k in NARROWING):
            continue
        key = (score, sum(getattr(r, k) is not None for k in NARROWING), LEVEL_RANK.get(r.level, 0))
        if r.locked not in best or key > best[r.locked][0]:
            best[r.locked] = (key, r)
    # A lock is a floor: the level of the most specific rule not locked, raised to the lock's when the lock is higher. On a
    # tie the lock is named, since it is the organization's word (`aidd risk --list`).
    found = [best[k][1] for k in (True, False) if k in best]
    return max(found, key=lambda r: LEVEL_RANK.get(r.level, 0), default=None)


def environment_is_shared(rs: RuleSet, name: str) -> bool:
    """Whether other people use the environment `name`: True unless the config marks it `shared: false`. A name the
    config does not hold, or holds twice with one entry shared, reads as shared, so unsure means it asks."""
    found = [e for e in rs.environments if e.get("name") == name]
    return not found or any(e.get("shared") is not False for e in found)


def unknown_name(kind: str, name: str, valid: Iterable[str], next_step: str) -> str:
    """The message for a `name` that is no `kind` aidd knows, or "" when it is one of `valid`. An action, area, or role
    that no rule names would read as `allow`, the lowest level, so a typo asks for a fix instead of an answer. The
    message names the closest of `valid` and `next_step`, where the full list is."""
    choices = sorted(set(valid))
    if name in choices:
        return ""
    close = closest(name, choices)
    return f"{name!r} is not {'an' if kind[0] in 'aeiou' else 'a'} {kind} aidd knows" + (f"; did you mean `{close}`?" if close else ".") + f" {next_step}"


def level_of(rs: RuleSet, action: str, **narrow) -> tuple[str, Rule | None]:
    """The level of `action` and the rule that decided it; `allow` with no rule when none matches."""
    r = winning_rule(rs, action, **narrow)
    return (r.level if r else "allow"), r


def level_on_any_branch(rs: RuleSet, action: str, **narrow) -> tuple[str, Rule | None]:
    """`level_of`, and when no branch is named, the highest level over every branch a rule can name, so an action whose
    rules all name a branch, such as `git.push`, never reads as `allow` for want of one. Unsure means the stricter level."""
    if narrow.get("branch") is not None:
        return level_of(rs, action, **narrow)
    found = [level_of(rs, action, **(narrow | {"branch": b})) for b in ANY_BRANCH]
    return max(found, key=lambda f: LEVEL_RANK[f[0]])


def lock_effects(rs: RuleSet) -> list[str]:
    """One line for each rule a parent config locked: the narrower rules it raises to its level, and that it lowers none.
    A lock is a floor (`winning_rule`), so a rule it covers that sits below its level reads at the lock's level in the
    places the two both match, and a rule at or above its level is unchanged. The rises a standing delegation makes are
    left out: they say so in the rule's own source."""
    out = []
    for lock in (r for r in rs.rules if r.locked and r.source != "delegation"):
        covered = [
            r
            for r in rs.rules
            if not r.locked
            and config.action_matches(lock.action, r.action)
            and all(getattr(r, k) == getattr(lock, k) for k in NARROWING if getattr(lock, k) is not None)
        ]
        raised = [r.label() for r in covered if LEVEL_RANK.get(r.level, 0) < LEVEL_RANK.get(lock.level, 0)]
        out.append(f"{lock.label()} is locked ({lock.source}): it raises {', '.join(raised) if raised else 'no rule'} to {lock.level}, and lowers none")
    return out


def areas_of(rs: RuleSet, path: str) -> list[str]:
    """The areas `path` is in, in the order the rule set lists them. Matching ignores case, as macOS and Windows do."""
    out = []
    for name, area in rs.areas.items():
        if globs.match_any(area.get("paths", []), path, fold_case=True) and not globs.match_any(area.get("exclude", []), path, fold_case=True):
            out.append(name)
    return out


def areas_in(rs: RuleSet, paths: list[str]) -> dict[str, list[str]]:
    """Each area that any of `paths` is in, with those paths: `areas_of` for a whole list at once, so a planned glob that
    stands for every tracked file under it costs a pass per area pattern. The areas come in the order their first path
    does, and the rule set's order within one path."""
    path_keys = globs.keys(paths, fold_case=True)
    found: list[tuple[int, int, str, list[str]]] = []
    for place, (name, area) in enumerate(rs.areas.items()):
        hit = globs.match_in(area.get("paths", []), path_keys, fold_case=True)
        if hit and area.get("exclude"):
            hit -= globs.match_in(area["exclude"], path_keys, fold_case=True, within=hit)
        if hit:
            found.append((min(hit), place, name, [paths[i] for i in sorted(hit)]))
    return {name: files for _, _, name, files in sorted(found)}


def edit_level(rs: RuleSet, paths: list[str], *, role: str | None = None) -> tuple[str, Rule | None, dict[str, list[str]]]:
    """The level of `code.edit` over `paths`: the highest over every area they touch, the rule that decided it, and
    each area with the paths in it."""
    by_area = areas_in(rs, paths)
    return *edit_level_in(rs, list(by_area), role=role), by_area


def edit_level_in(rs: RuleSet, areas: list[str], *, role: str | None = None) -> tuple[str, Rule | None]:
    """The level of `code.edit` over the `areas` a change touches, and the rule that decided it."""
    level, rule = level_of(rs, "code.edit", role=role)
    for a in areas:
        lv, r = level_of(rs, "code.edit", area=a, role=role)
        if LEVEL_RANK[lv] > LEVEL_RANK[level]:
            level, rule = lv, r
    return level, rule
