"""Load `.aidd/config.yaml` and its `extends` parents into a `Config`, with a warning for every setting the merge set
aside.

How a child merges over its parents: a setting the child names replaces the parent's, except where a parent locks it
(`locks`), where a library standard or a company policy binds (`standards`, `standards_policy`), and in `risks`, where
areas and actions merge by id and rules by their selector, and a rule a parent marks `locked` keeps the parent's level.
"""

from __future__ import annotations

import copy
import hashlib
import posixpath
import urllib.parse
from collections.abc import Callable

from aidd.config import delivery_teams, extends, model
from aidd.kernel import documents, globs, json_schema

Reader = Callable[[str], "str | None"]
Fetcher = Callable[[str], bytes]

# The words a warning carries for an `extends` URL parent that could not be read offline.
UNREAD_PARENT = "was not read"
# What a rule's selector is: two rules with the same one are the same rule, so a later one replaces an earlier one.
SELECTOR = ("action", "area", "branch", "role", "environment")


def selector(rule: dict) -> tuple:
    """A risk rule's selector: its action and the area, branch, role, and environment that narrow it."""
    return tuple(rule.get(k) for k in SELECTOR)


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

    errors = json_schema.validate(raw, "config.schema.json")
    special = standards_policy.config_problems(raw)
    if special:
        explained = tuple(path for path, _ in special)
        errors = [m for _, m in special] + [e for e in errors if not e.startswith(explained)]
    if errors:
        raise model.ConfigError("\n".join(f"{where}: {e}" for e in errors))
    warnings: list[str] = []
    parents: list[tuple[str, str]] = [("org preset", root_preset)] if root_preset else []
    for parent in raw.get("extends", []):
        key = parent.get("path") or parent["url"]
        ptext = (prefetched or {}).get(key)
        if ptext is None and "path" in parent and where == "org preset":
            raise model.ConfigError(f"{where}: extends {key!r}: {extends.ORG_PRESET_BY_URL}")
        if ptext is None and "path" in parent and read:
            ptext = read(parent["path"])
        if ptext is None and "url" in parent:
            if fetch is None:
                raise model.ConfigError(f"{where}: cannot fetch {parent['url']} here; pass it pre-fetched")
            try:
                ptext = fetch(parent["url"]).decode("utf-8")
            except (OSError, RuntimeError, ValueError) as exc:  # HttpError is an OSError; an offline fetcher raises
                if not skip_unread:
                    raise
                warnings.append(f"{where}: extends {parent['url']} {UNREAD_PARENT} ({exc}); its settings do not apply on this machine")
                continue
        if ptext is None:
            raise model.ConfigError(f"{where}: extends {key!r} not found")
        if "sha256" in parent and hashlib.sha256(ptext.encode("utf-8")).hexdigest() != parent["sha256"]:
            raise model.ConfigError(f"{where}: extends {key!r} does not match its sha256 pin")
        parents.append((key, ptext))
    merged: dict = {}
    parent_paths: list[str] = []
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
        praw = _with_rule_sources(pcfg, "org preset" if root_preset and i == 0 else f"preset {_shown_parent(key)}")
        merged = merge(merged, praw, key, warnings) if merged else praw
    merged = merge(merged, raw, where, warnings) if merged else copy.deepcopy(raw)
    rule_sources = {selector(r): r.pop(_SOURCE) for r in (merged.get("risks") or {}).get("rules") or [] if _SOURCE in r}
    merged.setdefault("profile", "solo")
    for label, value in (
        ("docs.dir", (merged.get("docs") or {}).get("dir")),
        ("specs_dir", merged.get("specs_dir")),
        ("proposals_dir", merged.get("proposals_dir")),
    ):
        if value is not None and globs.normal_dir(str(value)) == ".":
            raise model.ConfigError(f"{where}: {label} {value!r} names the repository's top; name a folder inside the repository")
    # A team's harness and areas are names the schema cannot check, read once every parent has merged into the top one.
    unnamed = delivery_teams.problems(merged) if _depth == 0 else []
    if unnamed:
        raise model.ConfigError("\n".join(f"{where}: {e}" for e in unnamed))
    by_path = [posixpath.normpath(k.replace("\\", "/")).lstrip("/") for k, _ in parents if k != "org preset" and "://" not in k]
    return model.Config(
        raw=merged,
        profile=str(merged["profile"]),
        warnings=warnings,
        parent_paths=tuple(dict.fromkeys(by_path + parent_paths)),
        rule_sources=rule_sources,
    )


def _shown_parent(key: str) -> str:
    """A parent's path or URL as a rule's source shows it: one line, safe for a terminal, and a URL without its user,
    password, query, or fragment, which may hold a token."""
    if "://" in key:
        parts = urllib.parse.urlsplit(key)
        key = urllib.parse.urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))
    return documents.one_line(key, 200)


# The key a parent's rule carries through the merge, naming the preset it came from; taken off before the load returns.
_SOURCE = "_source"


def _with_rule_sources(pcfg: model.Config, label: str) -> dict:
    """A copy of a parent's config with each risk rule marked with the preset it came from: its own parent's, or
    `label` for a rule the parent sets itself."""
    out = copy.deepcopy(pcfg.raw)
    for rule in (out.get("risks") or {}).get("rules") or []:
        rule[_SOURCE] = pcfg.rule_sources.get(selector(rule), label)
    return out


def merge(parent: dict, child: dict, where: str, warnings: list[str] | None = None) -> dict:
    """A child config over its parent: see the module's note."""
    warnings = warnings if warnings is not None else []
    out = copy.deepcopy(parent)
    locked = set(parent.get("locks", []))
    for key, value in child.items():
        if key == "extends":
            continue
        if key == "project":
            from aidd.config import project

            out[key] = project.merge(out.get(key), value, locked=key in locked, where=where, warnings=warnings)
        elif key in locked:
            warnings.append(f"{where}: {key} is locked by a parent config and is ignored")
        elif key == "locks":
            out[key] = sorted(locked | set(value))
        elif key == "standards":
            out[key] = _add_named(out.get(key, []), value, f"{where}: standards", warnings)
        elif key == "standards_policy":
            from aidd.config import standards_policy

            out[key] = standards_policy.merge_policy(out.get(key) or {}, value, where, warnings)
        elif key == "risks":
            out[key] = merge_risks(out.get(key) or {}, value, where, warnings)
        elif key == "environments" and isinstance(value, list):
            out[key] = _merge_environments(parent, value, where, warnings)
        elif key == "docs" and isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_docs(out[key], value, where, warnings)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **copy.deepcopy(value)}
        else:
            out[key] = copy.deepcopy(value)
    return out


def _merge_environments(parent: dict, child: list, where: str, warnings: list[str]) -> list:
    """A child's `environments` replaces its parent's, except an environment a locked parent rule names: the parent's
    definition stays, so a child cannot move the branches or tags the lock covers."""
    rules = (parent.get("risks") or {}).get("rules") or []
    theirs = {e.get("name"): e for e in parent.get("environments") or [] if isinstance(e, dict)}
    held = sorted({str(r["environment"]) for r in rules if r.get("locked") and r.get("environment") in theirs})
    mine = []
    for env in child:
        name = env.get("name") if isinstance(env, dict) else None
        if name in held:
            if env != theirs[name]:
                warnings.append(f"{where}: environments {name} is named by a rule a parent config locked, so this redefinition is ignored")
            continue
        mine.append(copy.deepcopy(env))
    return [copy.deepcopy(theirs[n]) for n in held] + mine


def _merge_docs(parent: dict, child: dict, where: str, warnings: list[str]) -> dict:
    """`docs` merges by type under `required`, and a child cannot set `off` for a type its parent sets to `warn`."""
    out = {**parent, **copy.deepcopy(child)}
    levels = parent.get("required")
    if isinstance(levels, dict) and isinstance(child.get("required"), dict):
        required = dict(levels)
        for doc_type, level in child["required"].items():
            if levels.get(doc_type) == "warn" and level == "off":
                warnings.append(f"{where}: docs.required.{doc_type}='off' ignored; a parent config sets it to 'warn'")
            else:
                required[doc_type] = level
        out["required"] = required
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
            out[section] = {**(out.get(section) or {}), **copy.deepcopy(mine)}
    rules = {selector(r): r for r in out.get("rules", [])}
    for rule in child.get("rules", []):
        sel = selector(rule)
        was_locked = bool(rules.get(sel, {}).get("locked"))
        if was_locked and rules[sel].get("level") != rule.get("level"):
            warnings.append(f"{where}: risks.rules {_label(rule)} is locked by a parent config at {rules[sel]['level']!r}, so {rule.get('level')!r} is ignored")
            continue
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


def _label(rule: dict) -> str:
    """A rule as a person reads it: its action and what narrows it."""
    narrow = ", ".join(f"{k} {rule[k]}" for k in SELECTOR[1:] if rule.get(k))
    return f"{rule.get('action')}" + (f" ({narrow})" if narrow else "")


def _add_named(parents: list[dict], children: list[dict], label: str, warnings: list[str]) -> list[dict]:
    """The parent's entries plus the child's, where a child entry reusing a parent's `name` is dropped with a warning."""
    names = {e.get("name") for e in parents}
    warnings += [f"{label} {e.get('name')!r} is set by a parent config and cannot be replaced" for e in children if e.get("name") in names]
    return list(parents) + [e for e in children if e.get("name") not in names]


def load_file(path: str, root: str = ".", *, fetch: Fetcher | None = None, skip_unread: bool = False) -> model.Config:
    """Load a config from disk. `fetch` overrides how an `extends` URL parent is retrieved; with AIDD_OFFLINE=1 none is."""
    import os
    from pathlib import Path

    rootp = Path(root)
    text = (rootp / path).read_text(encoding="utf-8")

    def read(rel: str) -> str | None:
        p = rootp / rel
        return p.read_text(encoding="utf-8") if p.is_file() else None

    if fetch is None:
        from aidd.kernel import http

        if os.environ.get("AIDD_OFFLINE") == "1":

            def fetch(url: str) -> bytes:  # noqa: F811  # offline: never reach the network
                raise http.HttpError(0, url, "not fetched: offline (AIDD_OFFLINE=1)")
        else:

            def fetch(url: str) -> bytes:  # noqa: F811
                from aidd.kernel import egress

                return egress.fetch_text(url).encode("utf-8")

    return load_text(text, read=read, fetch=fetch, where=path, root_preset=extends.org_preset_text(), skip_unread=skip_unread)
