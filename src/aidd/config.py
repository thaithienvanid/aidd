"""Load .aidd/config.toml, merge `extends` parents, and compute effective gates.

Gates can only get stricter: a child config or a gate override that would
loosen the profile is ignored and reported as a warning.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from . import globs, model, resources, schema

CONFIG_PATH = ".aidd/config.toml"
ROUTE_KEYS = ("standard", "minor", "normal", "major", "emergency")
RUNBOOK_MAX_AGE_DAYS = 180
_LIST_MERGE = ("risk_rules", "protected_paths", "standard_changes", "disable_rules", "scope_exempt_paths", "budget_exclude_paths", "tests")


TENANT = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")  # common.schema.json#/$defs/tenant


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    raw: dict
    profile: str
    gates: dict
    warnings: list[str] = field(default_factory=list)

    def get(self, *keys, default=None):
        node = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def approvers(self) -> list[str]:
        return self.get("owners", "approvers", default=[])

    @property
    def reviewers(self) -> dict[str, list[str]]:
        """Specialist reviewer pools by name."""
        return dict(self.get("owners", "reviewers", default={}) or {})

    @property
    def tenant(self) -> str | None:
        """The tenant this repository belongs to (`tenant`), or None: approvals and records are scoped to it."""
        value = self.get("tenant")
        return str(value) if value else None

    @property
    def specs_dir(self) -> str:
        return self.get("specs_dir", default="specs")

    @property
    def proposals_dir(self) -> str:
        return self.get("proposals_dir", default="proposals")

    @property
    def standards(self) -> list[dict]:
        """House standards: the team's own rules, each a document that agents in the named roles read before a step."""
        return list(self.get("standards", default=[]) or [])

    @property
    def runbook_max_age_days(self) -> int:
        return int(self.get("runbook_max_age_days", default=RUNBOOK_MAX_AGE_DAYS))

    @property
    def policy_command(self) -> list[str] | None:
        return self.get("policy", "command")

    @property
    def observe_command(self) -> list[str] | None:
        return self.get("observe", "command")


def profile_rank(name: str) -> int:
    return resources.profiles()["order"].index(name)


_ORDERED = {
    "red_green": ["warn", "require"],
    "provenance": ["declare", "every_commit"],
    "unlinked_authors": ["warn", "fail"],
    "spec_approval_proof": ["optional", "require"],
    "local_approvals": ["any", "signed"],
}
# Queue limits `aidd next` reads, never the gate: 0 is off, and a child may only lower a non-zero limit.
_QUEUE_LIMITS = ("max_open_per_approver", "escalate_after_minutes")


# The session hooks' level ([hooks] level), weakest first, and the level each profile starts at. A child config
# cannot lower the level its parent sets or starts at (see _merge), the way gates only tighten.
HOOK_LEVELS = ("minimal", "standard", "strict")
HOOK_LEVEL_DEFAULTS = {"solo": "minimal", "team": "standard", "org": "standard", "regulated": "strict"}
HOOK_SWITCHES = ("session_start", "stop_check", "compact_note")


def hook_level(raw: dict) -> str:
    """The session hooks' level a (merged) config sets, or its profile's default."""
    level = (raw.get("hooks") or {}).get("level")
    return level if level in HOOK_LEVELS else HOOK_LEVEL_DEFAULTS.get(str(raw.get("profile")), "standard")


def _tighten(gates: dict, override: dict, where: str, warnings: list[str]) -> dict:
    out = copy.deepcopy(gates)
    for key, value in override.items():
        cur = out.get(key)
        if key in ("spec_approval_routes", "policy_required_routes", "observe_required_routes"):
            out[key] = sorted(set(cur or []) | set(value), key=ROUTE_KEYS.index)
        elif key in ("separation_of_duties", "specialist_spec_approval"):
            if value or not cur:
                out[key] = bool(value) or bool(cur)
            else:
                warnings.append(f"{where}: gates.{key}=false ignored; the profile requires true")
        elif key == "standard_changes":
            if value and not cur:
                warnings.append(f"{where}: gates.standard_changes=true ignored; the profile forbids standard changes")
            else:
                out[key] = bool(value) and bool(cur)
        elif key in _ORDERED:
            order = _ORDERED[key]
            if order.index(value) >= order.index(str(cur)):
                out[key] = value
            else:
                warnings.append(f"{where}: gates.{key}={value!r} ignored; looser than {cur!r}")
        elif key in ("approvals", "cooloff_minutes", "max_changed_lines"):
            # Per route: more approvals or a longer cool-off is stricter; a smaller changed-line budget is.
            merged = dict(cur or {})
            for route, n in value.items():
                old = merged.get(route)
                if (n >= (old or 0)) if key != "max_changed_lines" else (old is None or n <= old):
                    merged[route] = n
                else:
                    warnings.append(f"{where}: gates.{key}.{route}={n} ignored; looser than {old}")
            out[key] = merged
        elif key == "specialist_approvals":
            if value >= (cur or 0):
                out[key] = value
            else:
                warnings.append(f"{where}: gates.specialist_approvals={value} ignored; looser than {cur}")
        elif key in _QUEUE_LIMITS:
            # A queue limit: 0 is off, the loosest; any other number tightens by going lower.
            if not cur or (value and value <= cur):
                out[key] = value
            else:
                warnings.append(f"{where}: gates.{key}={value} ignored; looser than {cur}")
    return out


# Settings a parent config owns: a child cannot replace the org's Policy or evidence source once a
# parent sets them, nor a reviewer pool the parent bound (it may add other pools). Identity exemptions
# are locked even when the parent kept the default, because an exemption removes a person from the
# authors; a child may only narrow them.
_LOCKED = {
    ("policy", "command"),
    ("evidence", "workflow"),
    ("evidence", "artifact"),
    ("evidence", "workflow_path"),
    ("evidence", "signer_workflow"),
    ("evidence", "status_check_apps"),
}
_NARROW_ONLY = {("identities", "system_accounts"): ["web-flow"]}

# An org preset (AIDD_ORG_PRESET) is injected by the platform team, so a repository must not
# loosen it by adding entries: these keys are locked for it even when the preset does not list them.
# A parent the repository chose itself is covered by the repository's own review of its config.
ORG_PRESET_LOCKS = ("disable_rules", "rule_exclusions", "scope_exempt_paths")


def _merge(parent: dict, child: dict, where: str, warnings: list[str] | None = None) -> dict:
    warnings = warnings if warnings is not None else []
    out = copy.deepcopy(parent)
    if "profile" in parent and profile_rank(child["profile"]) < profile_rank(parent["profile"]):
        raise ConfigError(f"{where}: profile {child['profile']!r} is weaker than the parent profile {parent['profile']!r}")
    locked = set(parent.get("locks", []))
    for key, value in child.items():
        if key in ("extends", "gates"):
            continue
        if key in locked:
            warnings.append(f"{where}: {key} is locked by a parent config and is ignored")
            continue
        if key == "locks":
            out[key] = sorted(locked | set(value))
            continue
        if key == "tenant" and parent.get("tenant") and value != parent["tenant"]:
            # A repository belongs to the tenant its parent names; it cannot move itself to another one.
            warnings.append(f"{where}: tenant {value!r} ignored; a parent config sets tenant {parent['tenant']!r}")
            continue
        if key == "mode" and parent.get("mode") == "enforce" and value != "enforce":
            warnings.append(f"{where}: mode {value!r} ignored; a parent config enforces the gate")
            continue
        if key == "standards":
            # A parent's house standard binds its children: they may add standards, never drop or redefine one.
            out[key] = _add_named(out.get(key, []), value, f"{where}: standards", warnings)
        elif key in _LIST_MERGE:
            out[key] = list(out.get(key, [])) + list(value)
        elif isinstance(value, dict) and isinstance(out.get(key, {}), dict):
            current = out.get(key, {})
            merged = dict(current)
            for sub, v in value.items():
                if (key, sub) in _NARROW_ONLY:
                    allowed = current.get(sub, _NARROW_ONLY[(key, sub)])
                    extra = sorted(set(v) - set(allowed))
                    if extra:
                        warnings.append(f"{where}: {key}.{sub} cannot add {extra}; a parent config owns identity exemptions")
                    merged[sub] = list(allowed) if extra else list(v)
                elif (key, sub) in _LOCKED and sub in current and current[sub] != v:
                    warnings.append(f"{where}: {key}.{sub} is set by a parent config and cannot be replaced")
                elif (key, sub) == ("owners", "approvers") and current.get(sub) and sorted(current[sub]) != sorted(v):
                    warnings.append(f"{where}: owners.approvers replaces the parent's approvers {current[sub]}")
                    merged[sub] = v
                elif (key, sub) == ("owners", "reviewers"):
                    pools = dict(current.get(sub) or {})
                    for pool, members in v.items():
                        if pool in pools and pools[pool] != members:
                            warnings.append(f"{where}: owners.reviewers.{pool} is set by a parent config and cannot be replaced")
                        else:
                            pools[pool] = list(members)
                    merged[sub] = pools
                elif (key, sub) == ("guard", "gated_commands"):
                    # A parent's deploy gate binds its children: they may add gates, never drop or redefine one.
                    merged[sub] = _add_named(current.get(sub, []), v, f"{where}: guard.gated_commands", warnings)
                elif (key, sub) == ("hooks", "level") and "profile" in parent:
                    floor = hook_level(parent)
                    if HOOK_LEVELS.index(v) < HOOK_LEVELS.index(floor):
                        warnings.append(f"{where}: hooks.level={v!r} ignored; looser than {floor!r}")
                        merged[sub] = floor
                    else:
                        merged[sub] = v
                elif key == "hooks" and sub in HOOK_SWITCHES and current.get(sub) is True and v is False:
                    warnings.append(f"{where}: hooks.{sub}=false ignored; a parent config turns it on")
                elif (key, sub) == ("owners", "paths"):
                    merged[sub] = list(current.get(sub, [])) + list(v)
                elif (key, sub) in (("identities", "bots"), ("evidence", "status_checks")):
                    merged[sub] = sorted(set(current.get(sub, [])) | set(v))
                elif (key, sub) == ("owners", "codeowners"):
                    merged[sub] = bool(current.get(sub)) or bool(v)
                elif (key, sub) == ("emergency", "review_sla_days") and sub in current:
                    merged[sub] = min(current[sub], v)
                else:
                    merged[sub] = v
            out[key] = merged
        else:
            out[key] = value
    inherited = (out.get("hooks") or {}).get("level")
    if inherited and "profile" in child and not (child.get("hooks") or {}).get("level"):
        # A parent's level binds as a floor, never below the child's own profile default.
        own = HOOK_LEVEL_DEFAULTS.get(str(child["profile"]), inherited)
        out["hooks"] = {**out["hooks"], "level": max(inherited, own, key=HOOK_LEVELS.index)}
    return out


def _add_named(parents: list[dict], children: list[dict], label: str, warnings: list[str]) -> list[dict]:
    """The parent's entries plus the child's, where a child entry reusing a parent's `name` is dropped with a warning."""
    names = {e.get("name") for e in parents}
    warnings += [f"{label} {e.get('name')!r} is set by a parent config and cannot be replaced" for e in children if e.get("name") in names]
    return list(parents) + [e for e in children if e.get("name") not in names]


Reader = Callable[[str], "str | None"]
Fetcher = Callable[[str], bytes]


def load_text(
    text: str,
    *,
    read: Reader | None = None,
    fetch: Fetcher | None = None,
    prefetched: dict[str, str] | None = None,
    where: str = CONFIG_PATH,
    _depth: int = 0,
    root_preset: str | None = None,
) -> Config:
    """Load a config and its parents. `root_preset` is an org preset the gate injects as the first parent."""
    if _depth > 5:
        raise ConfigError(f"{where}: extends is nested more than 5 levels")
    raw = model.parse_toml(text, where)
    errors = schema.validate(raw, "config.schema.json")
    if errors:
        raise ConfigError("\n".join(f"{where}: {e}" for e in errors))
    warnings: list[str] = []
    merged: dict = {}
    parent_gates: dict | None = None
    parents: list[tuple[str, str]] = [("org preset", root_preset)] if root_preset else []
    for parent in raw.get("extends", []):
        key = parent.get("path") or parent["url"]
        ptext = (prefetched or {}).get(key)
        if ptext is None and "path" in parent and read:
            ptext = read(parent["path"])
        if ptext is None and "url" in parent:
            if fetch is None:
                raise ConfigError(f"{where}: cannot fetch {parent['url']} here; pass it pre-fetched")
            ptext = fetch(parent["url"]).decode("utf-8")
        if ptext is None:
            raise ConfigError(f"{where}: extends {key!r} not found")
        if "sha256" in parent and hashlib.sha256(ptext.encode("utf-8")).hexdigest() != parent["sha256"]:
            raise ConfigError(f"{where}: extends {key!r} does not match its sha256 pin")
        parents.append((key, ptext))
    loaded: list[tuple[str, Config]] = []
    for key, ptext in parents:
        if key == "org preset":
            # The preset lives outside the repository: its parents come by URL, never from repo files.
            by_url = {k: v for k, v in (prefetched or {}).items() if "://" in k}
            preset = load_text(ptext, read=None, fetch=fetch, prefetched=by_url, where=key, _depth=_depth + 1)
            preset.raw["locks"] = sorted(set(preset.raw.get("locks", [])) | set(ORG_PRESET_LOCKS))
            loaded.append((key, preset))
        else:
            loaded.append((key, load_text(ptext, read=read, fetch=fetch, prefetched=prefetched, where=key, _depth=_depth + 1)))
    # A lock binds every other parent, whatever the order of extends: a sibling listed first cannot set a locked key.
    all_locks = {k for _, pcfg in loaded for k in pcfg.raw.get("locks", [])}
    for key, pcfg in loaded:
        warnings += pcfg.warnings
        own = set(pcfg.raw.get("locks", []))
        praw = {}
        for k, v in pcfg.raw.items():
            if k == "gates":
                continue
            if k in all_locks and k not in own:
                warnings.append(f"{key}: {k} is locked by another parent config and is ignored")
                continue
            praw[k] = v
        merged = _merge(merged, praw, key) if merged else praw  # raises when a later parent is weaker
        parent_gates = pcfg.gates if parent_gates is None else _tighten(parent_gates, pcfg.gates, key, [])
    merged = _merge(merged, raw, where, warnings) if merged else copy.deepcopy(raw)
    profile = merged["profile"]
    gates = {k: v for k, v in resources.profiles()["profiles"][profile].items() if k != "description"}
    if parent_gates is not None:
        gates = _tighten(gates, parent_gates, "extends", [])
    gates = _tighten(gates, raw.get("gates", {}), where, warnings)
    merged["gates"] = gates
    _bots_only(merged, where, warnings)
    _guard_grants_and_exemptions(merged, where, warnings)
    return Config(raw=merged, profile=profile, gates=gates, warnings=warnings)


def _guard_grants_and_exemptions(merged: dict, where: str, warnings: list[str]) -> None:
    """A pattern matching every path would silently grant full exemption or merge rights; drop it and warn."""
    targets: list[tuple[dict, str, str]] = [(merged, key, key) for key in ("scope_exempt_paths", "budget_exclude_paths")]
    rules = merged.get("rule_exclusions")
    targets += [(rules, r, f"rule_exclusions {r!r}") for r, pats in rules.items() if isinstance(pats, list)] if isinstance(rules, dict) else []
    targets += [(e, "paths", f"standard_changes {e.get('name', 'standard_change')!r} paths") for e in merged.get("standard_changes", []) if isinstance(e, dict)]
    owners_paths = (merged.get("owners") or {}).get("paths", [])
    targets += [(e, "paths", "owners.paths") for e in (owners_paths if isinstance(owners_paths, list) else []) if isinstance(e, dict)]
    targets += [(e, "exclude", "risk_rules exclude") for e in merged.get("risk_rules", []) if isinstance(e, dict)]
    for node, key, label in targets:
        wide = [p for p in node.get(key, []) if globs.is_catch_all(p)]
        if wide:
            warnings.append(f"{where}: {label} {wide} ignored: a pattern that matches every path would switch the rule off")
            node[key] = [p for p in node[key] if p not in wide]


def preset_tenant(text: str | None) -> str | None:
    """The tenant an org preset names, best effort, for an event about a run that failed before the config was read."""
    if not text:
        return None
    try:
        value = model.parse_toml(text, "org preset").get("tenant")
    except Exception:  # an unreadable preset is reported by the run itself; the event just has no tenant
        return None
    return value if isinstance(value, str) and TENANT.match(value) else None


BOT_ACCOUNTS = ("web-flow", "github-actions", "ghost")


def is_bot(identity: str) -> bool:
    s = identity.strip().lower().lstrip("@")
    return s.endswith("[bot]") or s in BOT_ACCOUNTS


def _bots_only(merged: dict, where: str, warnings: list[str]) -> None:
    """identities.system_accounts is for platform bookkeeping accounts; a person listed there would stop being an author."""
    accounts = merged.get("identities", {}).get("system_accounts")
    if accounts is None:
        return
    people = [x for x in accounts if not is_bot(x)]
    if people:
        warnings.append(f"{where}: identities.system_accounts {people} ignored: only bot accounts (*[bot], web-flow, github-actions) may be exempt")
        merged["identities"]["system_accounts"] = [x for x in accounts if is_bot(x)]


def load_file(path: str, root: str = ".", *, fetch: Fetcher | None = None) -> Config:
    """Load a config from disk. `fetch` overrides how an `extends` URL parent is retrieved.

    The edit-time guard passes an offline fetcher: a 20-second hook must never block on the
    network, and a repo-controlled URL must not beacon from a developer's machine on every edit.
    """
    from pathlib import Path

    rootp = Path(root)
    text = (rootp / path).read_text(encoding="utf-8")

    def read(rel: str) -> str | None:
        p = rootp / rel
        return p.read_text(encoding="utf-8") if p.is_file() else None

    if fetch is None:
        import os

        from . import http

        if os.environ.get("AIDD_HOOK_OFFLINE") == "1":

            def fetch(url: str) -> bytes:  # noqa: F811  # offline: skip the parent, never block on the network
                raise http.HttpError(0, url, "not fetched: the edit-time guard does not use the network")
        else:

            def fetch(url: str) -> bytes:  # noqa: F811
                # The gate's protected fetch: https only, a public address, and no redirect that would skip that check.
                from .inputs import fetch_text

                return fetch_text(url).encode("utf-8")

    from .inputs import org_preset_text

    return load_text(text, read=read, fetch=fetch, where=path, root_preset=org_preset_text())


def effective_mode(configured: str | None, requested: str | None, *, input_trusted: bool) -> str:
    """The gate's mode: the base branch's config wins; else the CI setting, if the CI setting is trusted.

    GitHub's mode comes from the reusable workflow's input, which runs from the base branch. GitLab's
    comes from a variable anyone allowed to run a pipeline can override, so it may not relax the gate.
    """
    if configured in ("enforce", "advisory"):
        return configured
    if input_trusted and requested in ("enforce", "advisory"):
        return requested
    return "enforce"
