"""Load `.aidd/config.yaml` and its `extends` parents into a `Config`, with a warning for every setting the merge set
aside.

How a child merges over its parents: it changes only what it names. A mapping merges member by member at every depth, and a
child never removes a parent's map entry, except to turn a disabled rule or default back on with `false`. A list of named
things merges by name, id, or selector (`standards`, `environments`, `risks.rules`, `project.rules`), and any other list or
a single value replaces the parent's. A parent holds what it must by locking it (`locks`, a key or one member), by a
library standard or company policy that binds (`standards`, `standards_policy`), or, in `risks`, by marking a rule `locked`,
which keeps the parent's level. A rule for every route also replaces the parent's rules for one route, unless the parent
locked them.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import posixpath
import re
import urllib.parse
from collections.abc import Callable, Iterable

from aidd import __version__
from aidd.config import development_teams, extends, limits, locks, model, old_shape, test_runners
from aidd.kernel import documents, findings, globs, json_schema, regular_files, resources, strict_yaml
from aidd.kernel.text import closest

Reader = Callable[[str], "str | None"]
Fetcher = Callable[[str], bytes]

# The words a warning carries for an `extends` URL parent that could not be read offline.
UNREAD_PARENT = "was not read"
# What a rule's selector is: two rules with the same one are the same rule, so a later one replaces an earlier one. The
# action comes first, and the rest are read in this order, as a rule prints its narrowing.
SELECTOR = ("action", "area", "branch", "role", "environment", "environment_shared", "route")


def selector(rule: dict) -> tuple:
    """A risk rule's selector: its action and the area, branch, role, environment, environment_shared, and route that narrow it."""
    return tuple(rule.get(k) for k in SELECTOR)


def route_rules_under(sel: tuple, selectors: Iterable[tuple]) -> list[tuple]:
    """Of `selectors`, those of the rules that name a route and differ from `sel` only by it, when `sel` names none: the
    rules a rule for every route replaces."""
    at = SELECTOR.index("route")
    bare = tuple(v for i, v in enumerate(sel) if i != at)
    return [s for s in selectors if sel[at] is None and s[at] is not None and tuple(v for i, v in enumerate(s) if i != at) == bare]


# A selector only one action takes: a rule that names it for an action that does not cover that action is refused. A prefix
# or `*` covers it, but the schema refuses the selector there too, so the way out is to name the action.
_ONLY_ON = (("route", "spec.approve"), ("environment", "deploy.run"), ("environment_shared", "deploy.run"))


def _selector_problems(raw: dict) -> list[tuple[str, str]]:
    """(schema path, message) for a rule that names a selector on an action other than the one that takes it (`_ONLY_ON`): a
    `route` not on `spec.approve`, or an `environment` not on `deploy.run`. A rule whose action is a prefix or `*` that covers
    that action is told only to name it, because removing the selector would widen the rule to every environment or route."""
    risks = raw.get("risks")
    rules = risks.get("rules") if isinstance(risks, dict) else None
    out = []
    for i, r in enumerate(rules if isinstance(rules, list) else []):
        for key, action in _ONLY_ON if isinstance(r, dict) else ():
            if r.get(key) is None or r.get("action") == action:
                continue
            covers = isinstance(r.get("action"), str) and action_matches(r["action"], action)
            way = f"set its action to `{action}`" if covers else f"remove `{key}` from it, or set its action to `{action}`"
            out.append(
                (
                    f"$.risks.rules[{i}].{key}",
                    f"risks.rules[{i}]: only `{action}` takes {'an' if key[0] in 'aeiou' else 'a'} `{key}`, and this rule is for {r.get('action')!r}; {way}",
                )
            )
    return out


_UNKNOWN_FIELD = re.compile(r"\$[^:]*: unknown field '(.*?)'(?:\. Did you mean `[^`]*`\?)?$")


def _error_path(error: str) -> str | None:
    """The document path a schema error names (`$.risks.rules[0].level`), and for an unknown field the path of that field."""
    if not error.startswith("$"):
        return None
    head = error.split(": ", 1)[0]
    found = _UNKNOWN_FIELD.match(error)
    return f"{head}.{found.group(1)}" if found else head


def _located(where: str, text: str, problems: Iterable[tuple[str | None, str]]) -> str:
    """Each problem, in line order, as a line that names the file and, where the file's text holds the path, the line a person opens:
    `where: line 7: $.risks.rules[0].level: must be one of ...`. A problem with no path in this file, such as one found
    after the parents merged, names the file alone."""
    marks: dict[str, int] | None = None
    out: list[tuple[int, str]] = []
    for path, message in problems:
        if path is not None and marks is None:
            marks = strict_yaml.key_lines(text.replace("\r\n", "\n"))
        line = strict_yaml.line_of(marks, path) if path is not None and marks else None
        out.append((line or 0, f"{where}: line {line}: {message}" if line else f"{where}: {message}"))
    return "\n".join(m for _, m in sorted(out, key=lambda item: item[0]))  # in line order, however the checks found them


def unknown_actions(raw: dict, actions: Iterable[str]) -> list[tuple[str, str]]:
    """(document path, message) for each of `raw`'s `risks.rules` whose action is no action `actions` holds and covers none
    (`*`, or a prefix such as `spec.*`, covers every action that starts with it). A typo there would write a rule that
    governs nothing, so the load fails instead of letting the action read as `allow`."""
    known = set(actions)
    rules = (raw.get("risks") or {}).get("rules") if isinstance(raw.get("risks"), dict) else None
    out = []
    for i, rule in enumerate(rules if isinstance(rules, list) else []):
        action = rule.get("action") if isinstance(rule, dict) else None
        if isinstance(action, str) and not any(action_matches(action, a) for a in known):
            close = closest(action, known)
            guess = f"; did you mean `{close}`?" if close else "."
            out.append(
                (
                    f"$.risks.rules[{i}].action",
                    f"$.risks.rules[{i}].action: {action!r} is no action aidd knows{guess} `aidd risk --list` lists every action, and a config adds one under `risks.actions`",
                )
            )
    return out


def _noting_version_skew(load: Callable[..., model.Config]) -> Callable[..., model.Config]:
    """`load`, and for the config itself (not a parent) a load error that adds why a newer config fails here (`_version_skew`)."""

    @functools.wraps(load)
    def noting(text: str, **kwargs) -> model.Config:
        try:
            return load(text, **kwargs)
        except model.ConfigError as exc:
            if not kwargs.get("_depth") and (skew := _version_skew(text, kwargs.get("where", model.CONFIG_PATH))):
                raise model.ConfigError(f"{exc}\n{skew}") from None
            raise

    return noting


@_noting_version_skew
def load_text(
    text: str,
    *,
    read: Reader | None = None,
    fetch: Fetcher | None = None,
    prefetched: dict[str, str] | None = None,
    where: str = model.CONFIG_PATH,
    _depth: int = 0,
    root_preset: str | None = None,
    skip_unread: bool = False,
) -> model.Config:
    """Load a config and its parents. `root_preset` is an org preset (AIDD_ORG_PRESET) read as the first parent. A URL
    parent that cannot be fetched fails the load, so a preset's locked rules never drop away unseen. With `skip_unread`
    (the read-only views, which run offline by design), it is skipped with a warning (UNREAD_PARENT) instead."""
    if _depth > extends.MAX_EXTENDS_DEPTH:
        raise model.ConfigError(f"{where}: extends is nested more than {extends.MAX_EXTENDS_DEPTH} levels")
    raw = documents.parse_yaml(text, where)
    from aidd.config import standards_policy

    special = standards_policy.config_problems(raw) + _selector_problems(raw) + locks.problems(raw) + test_runners.related_tests_problems(raw)
    explained = tuple(path for path, _ in special)
    problems: list[tuple[str | None, str]] = [
        *special,
        *(
            (_error_path(e), limits.explain(e) or old_shape.explain(e, raw))
            for e in json_schema.validate(raw, "config.schema.json")
            if not e.startswith(explained)
        ),
    ]
    if problems:
        raise model.ConfigError(_located(where, text, problems))
    warnings: list[str] = _host_glob_warnings(raw, where)
    parents: list[tuple[str, str]] = [("org preset", root_preset)] if root_preset else []
    for n, parent in enumerate(raw.get("extends", [])):
        key = parent.get("path") or parent["url"]

        def refuse(message: str, at: int = n) -> model.ConfigError:
            return model.ConfigError(_located(where, text, [(f"$.extends[{at}]", message)]))

        if "url" in parent:
            try:
                urllib.parse.urlsplit(parent["url"])
            except ValueError as exc:  # such as "Invalid IPv6 URL": the file, the line, and the way out, never a bare ValueError
                raise refuse(f"extends url {documents.one_line(parent['url'], 120)!r} is not a URL ({exc}). Fix the url, or name a file with `path`") from None
        ptext = (prefetched or {}).get(key)
        if ptext is None and "path" in parent and where == "org preset":
            raise refuse(f"extends {key!r}: {extends.ORG_PRESET_BY_URL}")
        if ptext is None and "path" in parent and read:
            ptext = read(parent["path"])
        if ptext is None and "url" in parent:
            if fetch is None:
                raise refuse(f"cannot fetch {parent['url']} here; pass it pre-fetched")
            try:
                ptext = fetch(parent["url"]).decode("utf-8")
            except (OSError, RuntimeError, ValueError) as exc:  # HttpError is an OSError; an offline fetcher raises
                if not skip_unread:
                    if isinstance(exc, (OSError, RuntimeError, model.ConfigError)):
                        raise
                    raise refuse(
                        f"extends {_shown_parent(parent['url'])!r} cannot be read ({type(exc).__name__}: {exc}). Fix the url, or name a file with `path`"
                    ) from None
                warnings.append(f"{where}: extends {parent['url']} {UNREAD_PARENT} ({exc}); its settings do not apply on this machine")
                continue
        if ptext is None:
            raise refuse(f"extends {key!r} not found")
        if "sha256" in parent and hashlib.sha256(ptext.encode("utf-8")).hexdigest() != parent["sha256"]:
            raise refuse(f"extends {key!r} does not match its sha256 pin")
        parents.append((key, ptext))
    merged: dict = {}
    named: list[str] = []  # the parents merged so far, as a lock's warning names them
    parent_paths: list[str] = []
    defined_by: list[tuple[str, list]] = []  # each parent and the environments it holds, the nearest first
    declared: list[dict] = []  # every environment a parent defines, at any depth
    pool_homes: list[tuple[str, set]] = []  # each parent and the specialist pools it holds, the nearest first
    for i, (key, ptext) in enumerate(parents):
        by_url = {k: v for k, v in (prefetched or {}).items() if "://" in k}
        pcfg = load_text(
            ptext,
            read=None if key == "org preset" else read,
            fetch=fetch,
            prefetched=by_url if key == "org preset" else prefetched,
            where=key,
            _depth=_depth + 1,
            skip_unread=skip_unread,
        )
        warnings += pcfg.warnings
        parent_paths += pcfg.parent_paths
        declared += [*pcfg.parent_environments, *(e for e in pcfg.get("environments", default=[]) or [] if isinstance(e, dict))]
        defined_by.insert(0, (key, pcfg.get("environments", default=[]) or []))
        pool_homes.insert(0, (key, set(pcfg.get("owners", "specialists", default={}) or {})))
        praw = _with_rule_sources(pcfg, "org preset" if root_preset and i == 0 else f"preset {_shown_parent(key)}")
        merged = merge(merged, praw, key, warnings, by=", ".join(named)) if merged else praw
        named.append(_shown_parent(key))
    if _depth == 0 and merged:
        warnings += _empty_lock_warnings(merged, where)
    merged = merge(merged, raw, where, warnings, by=", ".join(named)) if merged else copy.deepcopy(raw)
    if _depth == 0 and "delegation" in merged and "delegation" not in raw:
        # A parent can narrow a delegation, never start one: only this repository's own config delegates.
        merged.pop("delegation")
        warnings.append(f"{where}: a parent config sets `delegation`, which only this repository's own config can set, so it is ignored")
    if _depth == 0:
        warnings += _own_wildcard_warnings(merged.get("environments") or [], [(where, raw.get("environments") or []), *defined_by])
        warnings += _pool_warnings(merged, [(where, set((raw.get("owners") or {}).get("specialists") or {})), *pool_homes])
    rule_sources = {selector(r): r.pop(_SOURCE) for r in (merged.get("risks") or {}).get("rules") or [] if _SOURCE in r}
    merged.setdefault("profile", "solo")
    for label, value in (
        ("docs.dir", (merged.get("docs") or {}).get("dir")),
        ("specs_dir", merged.get("specs_dir")),
        ("proposals_dir", merged.get("proposals_dir")),
        ("product_dir", merged.get("product_dir")),
    ):
        if value is not None and globs.normal_dir(str(value)) == ".":
            message = f"{label} {value!r} names the repository's top; name a folder inside the repository"
            raise model.ConfigError(_located(where, text, [("$." + label, message)]))
    if _depth == 0:
        # A team's harness and areas are names the schema cannot check, read once every parent has merged into the top one.
        unnamed = [("$." + e.split(":", 1)[0], e) for e in development_teams.problems(merged)]
        if unnamed:
            raise model.ConfigError(_located(where, text, unnamed))
        _refuse_unknown_actions(raw, merged, rule_sources, where, text)
    by_path = [posixpath.normpath(k.replace("\\", "/")).lstrip("/") for k, _ in parents if k != "org preset" and "://" not in k]
    return model.Config(
        raw=merged,
        profile=str(merged["profile"]),
        warnings=warnings,
        parent_paths=tuple(dict.fromkeys(by_path + parent_paths)),
        rule_sources=rule_sources,
        parent_environments=tuple(declared),
        sets_environments=isinstance(raw.get("environments"), list),
    )


def _refuse_unknown_actions(raw: dict, merged: dict, rule_sources: dict[tuple, str], where: str, text: str) -> None:
    """Fail the load for a rule that names an action no layer defines: the built-in actions and the `risks.actions` of this
    config and its parents. This file's own rules name their line; a parent's rule names the parent it came from."""
    known = set(resources.load_json("risks.json")["actions"]) | set((merged.get("risks") or {}).get("actions") or {})
    problems = unknown_actions(raw, known)
    own = {selector(r) for r in (raw.get("risks") or {}).get("rules") or [] if isinstance(r, dict)}
    parents = {s: src for s, src in rule_sources.items() if s not in own}
    foreign = [
        f"{src}: {m.split(': ', 1)[1]}"
        for rule in (merged.get("risks") or {}).get("rules") or []
        if (src := parents.get(selector(rule))) is not None
        for _, m in unknown_actions({"risks": {"rules": [rule]}}, known)
    ]
    if problems or foreign:
        raise model.ConfigError("\n".join([*([_located(where, text, problems)] if problems else []), *foreign]))


def _shown_parent(key: str) -> str:
    """A parent's path or URL as a rule's source shows it: one line, safe for a terminal, and a URL without its user,
    password, query, or fragment, which may hold a token."""
    if "://" in key:
        parts = urllib.parse.urlsplit(key)
        key = urllib.parse.urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))
    return documents.one_line(key, 200)


# The key a parent's rule carries through the merge, naming the preset it came from; taken off before the load returns.
_SOURCE = "_source"


@functools.cache
def _level_rank() -> dict[str, int]:
    """The levels of a risk rule by their place in schemas/risks.json, lowest first, as `risk.rules.LEVELS` reads them; read
    when first asked, so importing the config reads no data file."""
    return {level: i for i, level in enumerate(resources.load_json("risks.json")["levels"])}


def _with_rule_sources(pcfg: model.Config, label: str) -> dict:
    """A copy of a parent's config with each risk rule marked with the preset it came from: its own parent's, or
    `label` for a rule the parent sets itself."""
    out = copy.deepcopy(pcfg.raw)
    for rule in (out.get("risks") or {}).get("rules") or []:
        rule[_SOURCE] = pcfg.rule_sources.get(selector(rule), label)
    return out


def merge(parent: dict, child: dict, where: str, warnings: list[str] | None = None, by: str = "") -> dict:
    """A child config over its parent: see the module's note. `by` names the parents, for a lock's warning."""
    warnings = warnings if warnings is not None else []
    out = copy.deepcopy(parent)
    held = list(parent.get("locks", []))
    locked = {lock for lock in held if "." not in lock}
    for key, value in child.items():
        if key == "extends":
            continue
        if key == "docs" and isinstance(value, dict):
            value = _turn_back_on(out, value)  # before the locks: turning a rule back on only tightens, so no lock stops it
            if not value:
                continue
        value = locks.without_locked(key, value, held, where, warnings)
        if key == "project":
            from aidd.config import project

            out[key] = project.merge(out.get(key), value, locked=key in locked, where=where, warnings=warnings)
        elif key in locked:
            if value != out.get(key):  # a child that restates the locked value (every config names its `profile`) says nothing new
                warnings.append(_lock_warning(key, value, out.get(key), where, by))
        elif key == "locks":
            out[key] = sorted(set(held) | set(value))
        elif key == "standards":
            out[key] = _add_named(out.get(key, []), value, f"{where}: standards", warnings)
        elif key == "standards_policy":
            from aidd.config import standards_policy

            out[key] = standards_policy.merge_policy(out.get(key) or {}, value, where, warnings)
        elif key == "risks":
            out[key] = merge_risks(out.get(key) or {}, value, where, warnings)
        elif key == "limits" and isinstance(value, dict):
            out[key] = limits.merged(out.get(key), value)
        elif key == "delegation" and isinstance(value, dict):
            out[key] = narrow_delegation(out.get(key), value, where, warnings)
        elif key == "environments" and isinstance(value, list):
            out[key] = _merge_environments(parent, value, where, warnings)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = documents.merge_members(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _lock_warning(key: str, value: object, held: object, where: str, by: str) -> str:
    """Why a child's `key` is ignored. The profile's warning names the value in force and the parents."""
    if key != "profile":
        return f"{where}: {key} is locked by a parent config and is ignored"
    return f"{where}: profile is locked by a parent config ({by or 'a parent'}) at {held!r}, so {value!r} is ignored"


def _turn_back_on(out: dict, value: dict) -> dict:
    """The child's `docs` without the types it turns back on (`disabled: {type: false}`), which leave `out`'s `disabled`.
    Turning a rule back on only tightens, so no lock stops it."""
    flags = value.get("disabled")
    back = [k for k, v in flags.items() if v is False] if isinstance(flags, dict) else []
    group = out.get("docs")
    if isinstance(group, dict) and isinstance(group.get("disabled"), dict):
        for k in back:
            group["disabled"].pop(k, None)
    rest = copy.deepcopy(value)
    for k in back:
        del rest["disabled"][k]
    if back and not rest["disabled"]:
        del rest["disabled"]
    return rest


def narrow_delegation(parent: dict | None, child: dict, where: str, warnings: list[str]) -> dict:
    """A child's `delegation` under its parent's: the parent can only narrow it. The child decides at most what the parent
    decides, keeps every action either reserves, and reviews by the earlier date."""
    if not isinstance(parent, dict):
        return copy.deepcopy(child)
    out = copy.deepcopy(child)
    theirs, mine = parent.get("decides"), child.get("decides")
    if isinstance(theirs, list):
        kept = list(theirs) if not isinstance(mine, list) else [a for a in mine if a in theirs]
        dropped = [] if not isinstance(mine, list) else [a for a in mine if a not in theirs]
        if dropped:
            warnings.append(f"{where}: delegation.decides {', '.join(dropped)} is not delegated by a parent config, so it is left out")
        out["decides"] = kept
    out["reserved"] = sorted(set(parent.get("reserved") or []) | set(child.get("reserved") or []))
    if parent.get("review_due") and str(parent["review_due"]) < str(out.get("review_due") or "9999-12-31"):
        out["review_due"] = parent["review_due"]
    return out


def _merge_environments(parent: dict, child: list, where: str, warnings: list[str]) -> list:
    """`environments` merge by `name`: a child adds an environment or overrides one by name, and each environment of the
    parent's that it does not name stays. An environment a locked parent rule covers stays exactly as the parent set it, so
    a child cannot move the branches or tags the lock covers, or mark the environment its own. A locked `deploy.run` rule
    that narrows to whether an environment is shared covers every environment the parent defines. A parent that locks
    `environments` keeps the whole list."""
    rules = [r for r in (parent.get("risks") or {}).get("rules") or [] if r.get("locked")]
    theirs = [e for e in parent.get("environments") or [] if isinstance(e, dict)]
    names = {e.get("name") for e in theirs}
    every = any(r.get("environment_shared") is not None and action_matches(str(r.get("action")), "deploy.run") for r in rules)
    held = names if every else {r["environment"] for r in rules if r.get("environment") in names}
    mine: dict = {}
    for env in child:
        name = env.get("name") if isinstance(env, dict) else None
        if name in held:
            if env not in theirs:
                warnings.append(f"{where}: environments {name} is covered by a rule a parent config locked, so this redefinition is ignored")
            continue
        mine.setdefault(name, []).append(copy.deepcopy(env))
    out: list = []
    placed: set = set()
    for env in theirs:
        name = env.get("name")
        if name not in mine:
            out.append(copy.deepcopy(env))
        elif name not in placed:
            out += mine[name]
            placed.add(name)
    return out + [env for name, envs in mine.items() if name not in placed for env in envs]


def _own_wildcard_warnings(environments: list, defined_by: list[tuple[str, list]]) -> list[str]:
    """A warning for each wildcard glob of an environment marked `shared: false`, which `aidd validate` and `aidd doctor`
    show. A wildcard branch glob gives way only for the branch checked out, and a wildcard tag glob never does, so a push
    it matches still asks. Each warning names the nearest config file of `defined_by` (file, environments) that holds it."""
    out = []
    for env in environments:
        if not isinstance(env, dict) or env.get("shared") is not False:
            continue
        file = next((f for f, envs in defined_by if env in envs), defined_by[0][0])
        for ref_type, one, gives_way in (
            ("branches", "branch", "unless it pushes the branch checked out"),
            ("tags", "tag", "because a wildcard tag glob never gives way"),
        ):
            for glob in [g for g in env.get(ref_type) or [] if globs.is_pattern(str(g))]:
                out.append(
                    f"{file}: environments {env.get('name')} is your own (`shared: false`), but its {one} glob {glob!r} has a "
                    f"wildcard that can match other people's {ref_type}. So a push it matches still asks, {gives_way}. Name each of your "
                    f"own {ref_type} without a wildcard in {file}"
                )
    return out


def _pool_warnings(merged: dict, homes: list[tuple[str, set]]) -> list[str]:
    """A warning for each `owners.specialists` pool that no risk dimension asks for, as `--specialist` refuses it, and
    that no area is named for: an expert pool takes the name of the area that marks the code its people know, such as
    `clinical`. It names the file that holds the pool (`homes`: this config first, then each parent's pools) and the
    closest pool when the name is a typo."""
    pools = sorted(set(model.POOL_OF.values()))
    areas = set(resources.load_json("risks.json")["areas"]) | set((merged.get("risks") or {}).get("areas") or {})
    return [
        f"{next(f for f, names in homes if pool in names)}: owners.specialists {pool!r} is not a pool aidd asks for a risk dimension, and no area has its "
        "name, so no change names it. " + (f"Did you mean `{near}`?" if (near := closest(str(pool), pools)) else f"The pools: {', '.join(pools)}.")
        for pool in (merged.get("owners") or {}).get("specialists") or {}
        if pool not in pools and pool not in areas
    ]


def _host_glob_warnings(raw: dict, where: str) -> list[str]:
    """A warning for each `deploys_on_merge` glob of an area that starts with `/` or `..`: globs are repo-relative and never
    reach outside the repository, so such a glob matches nothing and the file it names does not defer a delegated merge."""
    areas = (raw.get("risks") or {}).get("areas") if isinstance(raw.get("risks"), dict) else None
    return [
        f"{where}: risks.areas {name} deploys_on_merge {glob!r} never matches, because a glob is relative to the repository's top; write it without a leading `/` or `..`"
        for name, area in (areas.items() if isinstance(areas, dict) else [])
        for glob in (area.get("deploys_on_merge") or [] if isinstance(area, dict) else [])
        if isinstance(glob, str) and glob.startswith(("/", ".."))
    ]


def _empty_lock_warnings(inherited: dict, where: str) -> list[str]:
    """A warning for each `deploy.run` rule the parent configs (`inherited`) lock that holds no environment of theirs: it
    names one they never define, or narrows by `environment_shared` while they define none. This config's own
    environments would then decide what the lock covers."""
    names = {e.get("name") for e in inherited.get("environments") or [] if isinstance(e, dict)}
    out = []
    for rule in (inherited.get("risks") or {}).get("rules") or []:
        if not rule.get("locked") or not action_matches(str(rule.get("action")), "deploy.run"):
            continue
        if rule.get("environment") and rule["environment"] not in names:
            missing = f"the environment {rule['environment']}"
        elif rule.get("environment_shared") is not None and not names:
            missing = "an environment"
        else:
            continue
        out.append(
            f"{where}: a parent config locks {_label(rule)}, but no parent config defines {missing}, so this config's own environments "
            "decide what the lock covers. Define the environments in the parent config that locks the rule"
        )
    return out


def action_matches(pattern: str, action: str) -> bool:
    """Whether a rule's action (`git.push`, a prefix such as `git.*`, or `*`) covers `action`."""
    return pattern in (action, "*") or (pattern.endswith(".*") and action.startswith(pattern[:-1]))


def merge_risks(parent: dict, child: dict, where: str, warnings: list[str]) -> dict:
    """A child's `risks` over its parent's: an area or action with a parent's id replaces it, and a rule with a
    parent's selector replaces it, unless the parent marks that rule `locked`. A locked rule stays locked when a child
    restates it, and a child cannot redefine an area or an action a locked rule names, so it cannot narrow what the
    rule covers."""
    out = {k: copy.deepcopy(v) for k, v in parent.items()}
    locked = [r for r in out.get("rules", []) if r.get("locked")]
    areas = {r["area"] for r in locked if r.get("area")}

    def is_named(section: str, key: str) -> bool:
        if section == "areas":
            return key in areas
        return any(action_matches(str(r.get("action")), key) for r in locked)

    for section in ("areas", "actions"):
        mine = {k: v for k, v in (child.get(section) or {}).items() if not is_named(section, k)}
        for k in sorted(set(child.get(section) or {}) - set(mine)):
            warnings.append(f"{where}: risks.{section} {k} is named by a rule a parent config locked, so this redefinition is ignored")
        if section in child:
            out[section] = documents.merge_members(out.get(section) or {}, mine)
    rules = {selector(r): r for r in out.get("rules", [])}
    # A child's rule for every route replaces the parent's rules for one route, unless the parent locked them. It runs
    # over the parent's rules before any child rule applies, so the result never depends on the order of the child's.
    for rule in child.get("rules", []):
        for old in route_rules_under(selector(rule), list(rules)):
            if not rules[old].get("locked"):
                del rules[old]
    for rule in child.get("rules", []):
        sel = selector(rule)
        was_locked = bool(rules.get(sel, {}).get("locked"))
        if was_locked and rules[sel].get("level") != rule.get("level"):
            warnings.append(f"{where}: risks.rules {_label(rule)} is locked by a parent config at {rules[sel]['level']!r}, so {rule.get('level')!r} is ignored")
            continue
        held = _held_by_lock(rule, locked) if not was_locked else None
        if held:
            warnings.append(f"{where}: risks.rules {_label(rule)} is set aside: a parent config locked {_label(held)} at {held['level']!r}")
        mine = copy.deepcopy(rule)
        if mine.get("locked") and not was_locked and any(action_matches(str(r.get("action")), str(mine.get("action"))) for r in locked):
            # A child's own lock never outranks a parent's on the same action: without this, a narrower child rule
            # marked `locked` would win over the parent's locked one.
            warnings.append(f"{where}: risks.rules {_label(rule)} cannot lock an action a parent config locked, so its `locked` is ignored")
            mine.pop("locked")
        if was_locked:
            # A locked rule a child restates still comes from the parent that locked it, where a person changes it.
            mine.pop(_SOURCE, None)
            mine |= {"locked": True} | ({_SOURCE: rules[sel][_SOURCE]} if _SOURCE in rules[sel] else {})
        rules[sel] = mine
    if rules or "rules" in out:
        out["rules"] = list(rules.values())
    return out


def _held_by_lock(rule: dict, locked: list[dict]) -> dict | None:
    """The parent's locked rule that decides a child's rule for one route instead; None when none does. A lock is a
    floor, so it decides only a child rule below its level."""
    if rule.get("route") is None:
        return None
    return next(
        (
            r
            for r in locked
            if action_matches(str(r.get("action")), str(rule.get("action")))
            and r.get("route") in (None, rule["route"])
            and _level_rank().get(str(r.get("level")), 0) > _level_rank().get(str(rule.get("level")), 0)
        ),
        None,
    )


def _label(rule: dict) -> str:
    """A rule as a person reads it: its action and what narrows it."""
    narrow = ", ".join(f"{k} {str(rule[k]).lower() if isinstance(rule[k], bool) else rule[k]}" for k in SELECTOR[1:] if rule.get(k) is not None)
    return f"{rule.get('action')}" + (f" ({narrow})" if narrow else "")


def _add_named(parents: list[dict], children: list[dict], label: str, warnings: list[str]) -> list[dict]:
    """The parent's entries plus the child's, where a child entry reusing a parent's `name` is dropped with a warning."""
    names = {e.get("name") for e in parents}
    warnings += [f"{label} {e.get('name')!r} is set by a parent config and cannot be replaced" for e in children if e.get("name") in names]
    return list(parents) + [e for e in children if e.get("name") not in names]


# Why a repository's config file is not read, by `regular_files.named_file_bytes`' reason.
_CONFIG_REFUSED = {
    regular_files.LINK: "a link, which aidd never follows; replace it with the file",
    regular_files.NOT_REGULAR: "not a regular file (a device or a pipe, say), which aidd never opens; replace it with the file",
    regular_files.OUTSIDE: "a path outside the repository, which aidd never reads",
    regular_files.TOO_LARGE: f"larger than {documents.MAX_DOCUMENT_BYTES} bytes, the most a config holds",
}


def repository_config_text(root, rel: str) -> str:
    """The text of the config file a repository holds at `rel`: a regular file inside it, never read through a link or
    from a device, which a read could hang on, and at most a document's size. Anything else is a ConfigError that says
    why, and a missing file is the OSError any read of it gives."""
    raw, why = regular_files.named_file_bytes(root, rel, documents.MAX_DOCUMENT_BYTES)
    if raw is None and why in _CONFIG_REFUSED:
        raise model.ConfigError(f"{rel}: {_CONFIG_REFUSED[why]}")
    if raw is None:
        raise FileNotFoundError(f"{rel}: {why}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise model.ConfigError(f"{rel}: not UTF-8 text") from None


def load_file(path: str, root: str = ".", *, fetch: Fetcher | None = None, skip_unread: bool = False, text: str | None = None) -> model.Config:
    """Load a config from disk, or from `text` in its place, such as a config a dry run has not written yet. `fetch`
    overrides how an `extends` URL parent is retrieved; with AIDD_OFFLINE=1 none is."""
    import os
    from pathlib import Path

    rootp = Path(root)
    text = repository_config_text(rootp, path) if text is None else text

    def read(rel: str) -> str | None:
        if not os.path.lexists(rootp / rel):
            return None
        return repository_config_text(rootp, rel)

    if fetch is None:
        from aidd.kernel import http

        if os.environ.get("AIDD_OFFLINE") == "1":

            def fetch(url: str) -> bytes:  # noqa: F811  # offline: never reach the network
                raise http.HttpError(0, url, "not fetched: offline (AIDD_OFFLINE=1)")
        else:

            def fetch(url: str) -> bytes:  # noqa: F811
                from aidd.kernel import egress

                return egress.fetch_text(url).encode("utf-8")

    cfg = load_text(text, read=read, fetch=fetch, where=path, root_preset=extends.org_preset_text(), skip_unread=skip_unread)
    for test in cfg.tests:  # a folder a test runs in is inside the repository and reached through no link, here and when it runs
        if (folder := test.get("runs_in")) and (bad := regular_files.link_on_the_way(rootp.absolute(), folder)):
            raise model.ConfigError(
                f"{path}: tests {test.get('name')}: `runs_in` {folder} is no folder inside the repository ({bad} is a link or lies outside it). "
                "Name a folder inside it that no link leads through, or remove `runs_in`, then run aidd again"
            )
    return cfg


def _version_skew(text: str, path: str) -> str:
    """When the config's `aidd_version` is newer than this aidd, why that may be the cause of a load error, and the two
    ways out; else "". An action or a setting only the newer aidd knows fails the load here, because aidd cannot tell it
    from a typo. This runs only after a load failed, so a newer config that loads says nothing."""
    try:
        raw = documents.parse_yaml(text, path)
    except documents.DocumentError:
        return ""
    wrote = raw.get("aidd_version") if isinstance(raw, dict) else None
    if not isinstance(wrote, str) or not re.fullmatch(r"\d+\.\d+\.\d+", wrote):
        return ""
    if tuple(map(int, wrote.split("."))) <= tuple(map(int, re.findall(r"\d+", __version__)[:3])):
        return ""
    return (
        f"note: {path} was written for aidd {wrote}, while this is aidd {__version__}, so a setting only aidd {wrote} knows may be what fails. "
        f"Upgrade aidd to {wrote} (`aidd self-update`), or, where aidd is pinned (CI), move the pin to {wrote} (`aidd upgrade --ref <tag or commit> --yes`)."
    )


def config_load_problem(exc: Exception, *, goes_on: bool = False, path: str = model.CONFIG_PATH) -> str:
    """Why `path` does not load, and what happens next. A command that decides stops (`goes_on` False), because rules it
    cannot read are no rules, and a guess could read an `ask` as an `allow`. A view that shows what it can (`goes_on`) says
    so in one line, and exits 1. Either way the next step is `aidd validate`."""
    if goes_on:
        reason = documents.one_line((str(exc).strip().splitlines() or [type(exc).__name__])[0], 160)
        return f"aidd: {path} does not load ({reason}), so this command shows what it can without it, and exits 1. Run `aidd validate` to see what to fix."
    detail = str(exc).strip() or type(exc).__name__
    return f"{detail}\naidd stopped: it cannot read the rules in {path}, and a guess could read an `ask` as an `allow`. Fix what is named above, then run `aidd validate`."


def config_unreadable_finding(exc: Exception, *, goes_on: bool = False, path: str = model.CONFIG_PATH) -> dict:
    """The finding for a config that does not load. A `ConfigUnreadable` that stopped a command already says why and the next
    step; any other error is worded as `config_load_problem` words it."""
    said = str(exc) if isinstance(exc, model.ConfigUnreadable) else config_load_problem(exc, goes_on=goes_on, path=path).removeprefix("aidd: ")
    return findings.finding("config.unreadable", said, path=path)


def load_or_stop(path: str, root: str = ".", **kwargs) -> model.Config:
    """`load_file`, for a command that decides: a config that does not load raises a ConfigError that says why and names
    the next step (`config_load_problem`), never a guess without it."""
    try:
        return load_file(path, root, **kwargs)
    except (model.ConfigError, documents.DocumentError, OSError) as exc:
        raise model.ConfigUnreadable(config_load_problem(exc, path=path)) from None
