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
MAX_REVIEW_AGE_DAYS = 180
_LIST_MERGE = ("risk_rules", "protected_paths", "standard_changes", "disable_rules", "scope_exempt_paths", "budget_exclude_paths", "tests")


# What a user-facing surface looks like in a Task's scope: web and mobile screens, components, and styles.
UI_PATHS = [
    *(f"**/*.{ext}" for ext in ("tsx", "jsx", "vue", "svelte", "astro", "html", "css", "scss", "swift", "dart", "xib", "storyboard")),
    *(f"**/{d}/**" for d in ("components", "pages", "screens", "views", "ui", "web", "frontend", "layouts", "templates")),
    "**/res/layout/**",
]


# What a device or platform matrix looks like in a Task's scope: native iOS and Android code, and a mobile app folder.
DEVICE_PATHS = [
    *(f"**/*.{ext}" for ext in ("swift", "dart", "xib", "storyboard")),
    *(f"{d}/**" for d in ("ios", "android", "mobile")),
    *(f"**/{d}/**" for d in ("ios", "android", "mobile")),
    "**/res/layout/**",
]


# What an authentication or authorization change looks like in a Task's scope: the paths of the `baseline:auth` risk rule.
AUTH_PATHS: list[str] = next((r["paths"] for r in resources.load_json("baseline.json")["risk_rules"] if r["name"] == "baseline:auth"), [])


# What a change to secrets and cryptography looks like in a Task's scope: the paths of the `baseline:secrets-crypto` risk rule.
SECRETS_PATHS: list[str] = next((r["paths"] for r in resources.load_json("baseline.json")["risk_rules"] if r["name"] == "baseline:secrets-crypto"), [])


# The required-docs matrix by default (`[docs.required]` replaces a kind's rule): what `aidd validate` warns about on
# the routes in `routes`, and what `aidd new spec` only suggests on those in `suggest`. Never a gate rule. Testing lives
# in the Spec's Acceptance and the tech spec's Test strategy; a separate test plan only when a QA owner, a regulator, a
# device matrix, or a client's UAT needs one (`any_of`: one of these condition sets must hold).
DOCS_REQUIRED: dict[str, dict] = {
    "tech-spec": {"routes": ["major"]},
    "runbook": {"routes": ["major"]},
    "threat-model": {
        "routes": ["normal", "major"],
        "any_of": [{"dimensions": ["security", "privacy", "data"]}, {"compliance": True, "paths": AUTH_PATHS + SECRETS_PATHS}],
    },
    "authz": {"routes": ["normal", "major"], "paths": AUTH_PATHS, "any_of": [{"dimensions": ["security"]}, {"compliance": True}]},
    "design-spec": {"routes": ["major"], "suggest": ["normal"], "types": ["feat"], "paths": UI_PATHS},
    "test-plan": {
        "routes": ["major"],
        "suggest": ["normal"],
        "any_of": [
            {"dimensions": ["compliance"]},
            {"types": ["compliance"]},
            {"profiles": ["regulated"]},
            {"paths": DEVICE_PATHS},
            {"uat": True},
            {"min_acceptance": 10},
        ],
    },
    "migration": {"routes": ["major"], "suggest": ["normal"], "any_of": [{"dimensions": ["data"]}, {"types": ["data"]}, {"reversible": False}]},
    "analytics": {"routes": ["normal", "major"], "hypothesis": True},
    # Personal data: the compliance doc holds the DPIA (GDPR Art. 35) the compliance analyst plans, and the data map is
    # the living inventory and records of processing (Art. 30) it and the data engineer keep.
    "compliance": {"routes": ["normal", "major"], "dimensions": ["privacy"]},
    "data-map": {"routes": [], "suggest": ["normal", "major"], "dimensions": ["privacy"]},
}

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
    def specialists(self) -> dict[str, list[str]]:
        """Specialist Approver pools by name (`owners.specialists`)."""
        return dict(self.get("owners", "specialists", default={}) or {})

    @property
    def tenant(self) -> str | None:
        """The tenant this repository belongs to (`tenant`), or None: approvals and records are scoped to it."""
        value = self.get("tenant")
        return str(value) if value else None

    @property
    def specs_dir(self) -> str:
        """Where Specs live (`specs_dir`), in its normal form (globs.normal_dir), as `docs_dir`."""
        return globs.normal_dir(str(self.get("specs_dir", default="specs")))

    @property
    def proposals_dir(self) -> str:
        """Where proposals live (`proposals_dir`), in its normal form (globs.normal_dir), as `docs_dir`."""
        return globs.normal_dir(str(self.get("proposals_dir", default="proposals")))

    @property
    def docs_dir(self) -> str:
        """Where `aidd new` writes linked documents (`[docs] dir`), in its normal form (globs.normal_dir): `./custom/` is
        `custom`. The config refuses the repository's top. Build a path or a pattern inside it with globs.under."""
        return globs.normal_dir(str(self.get("docs", "dir", default="docs")))

    @property
    def docs_required(self) -> dict[str, dict]:
        """The required-docs matrix: the defaults, with each kind `[docs.required]` sets replaced."""
        return DOCS_REQUIRED | dict(self.get("docs", "required", default={}) or {})

    @property
    def standards(self) -> list[dict]:
        """`[[standards]]`: the team's own rules and its copies of library standards, each a document that agents in the
        named roles read before a step."""
        return list(self.get("standards", default=[]) or [])

    @property
    def standards_policy(self) -> dict:
        """`[standards_policy]`: the library standards a company requires, excludes, or replaces, and the stacks it allows."""
        return dict(self.get("standards_policy", default={}) or {})

    @property
    def runbook_max_age_days(self) -> int:
        return int(self.get("runbook_max_age_days", default=RUNBOOK_MAX_AGE_DAYS))

    @property
    def max_review_age_days(self) -> int:
        """`[docs] max_review_age_days`: how old a living doc's `reviewed_on` may be before `aidd doctor` warns."""
        return int(self.get("docs", "max_review_age_days", default=MAX_REVIEW_AGE_DAYS))

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
    "approval_carry": ["trivial_rebase", "none"],
}
# Queue limits `aidd list` reads, never the gate: 0 is off, and a child may only lower a non-zero limit.
_QUEUE_LIMITS = ("max_open_per_approver", "escalate_after_minutes", "max_in_progress_per_owner", "max_in_progress_days")


# The session hooks' level ([hooks] level), weakest first, and the level each profile starts at. A child config
# cannot lower the level its parent sets or starts at (see _merge), the way gates only tighten.
HOOK_LEVELS = ("minimal", "balanced", "strict")
HOOK_LEVEL_DEFAULTS = {"solo": "minimal", "team": "balanced", "org": "balanced", "regulated": "strict"}
HOOK_SWITCHES = ("session_start", "stop_check", "compact_note", "prompt_hint")

# `[agents] delegate`, weakest first, and the mode each profile starts at: whether the main session hands its
# edits of repository content to an aidd-team role (guard.delegate_check). A child config cannot loosen a parent's mode.
DELEGATE_MODES = ("never", "auto", "always")
DELEGATE_DEFAULTS = {"solo": "auto", "team": "auto", "org": "auto", "regulated": "always"}


def delegate_mode(raw: dict) -> str:
    """never, auto, or always: `[agents] delegate`, or the profile's default (DELEGATE_DEFAULTS)."""
    mode = (raw.get("agents") or {}).get("delegate")
    return mode if mode in DELEGATE_MODES else DELEGATE_DEFAULTS.get(str(raw.get("profile")), "auto")


def delegate_set(raw: dict) -> bool:
    """Whether a (merged) config sets `[agents] delegate` itself, or a parent's value binds it, rather than taking its
    profile's default."""
    return (raw.get("agents") or {}).get("delegate") in DELEGATE_MODES


def hook_level(raw: dict) -> str:
    """The session hooks' level a (merged) config sets, or its profile's default."""
    level = (raw.get("hooks") or {}).get("level")
    return level if level in HOOK_LEVELS else HOOK_LEVEL_DEFAULTS.get(str(raw.get("profile")), "balanced")


def _tighten(gates: dict, override: dict, where: str, warnings: list[str]) -> dict:
    out = copy.deepcopy(gates)
    for key, value in override.items():
        cur = out.get(key)
        if key in ("spec_approval_routes", "policy_required_routes", "observe_required_routes"):
            out[key] = sorted(set(cur or []) | set(value), key=ROUTE_KEYS.index)
        elif key == "approval_carry_routes":
            # Fewer routes on which an approval carries across a rebase is stricter: a child may only drop routes.
            wider = sorted(set(value) - set(cur or []), key=ROUTE_KEYS.index)
            if wider:
                warnings.append(f"{where}: gates.approval_carry_routes {wider} ignored; looser than {cur}")
            out[key] = sorted(set(cur or []) & set(value), key=ROUTE_KEYS.index)
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
        elif key == "local_signers":
            # Who may sign is the parent's to name: a child that points elsewhere could list its own keys.
            if cur and value != cur:
                warnings.append(f"{where}: gates.local_signers={value!r} ignored; the parent names {cur!r}")
            else:
                out[key] = value
        elif key in _QUEUE_LIMITS:
            # A queue limit: 0 is off, the loosest; any other number tightens by going lower.
            if not cur or (value and value <= cur):
                out[key] = value
            else:
                warnings.append(f"{where}: gates.{key}={value} ignored; looser than {cur}")
    return out


# Settings a parent config owns: a child cannot replace the org's Policy or evidence source once a
# parent sets them, nor a specialist pool the parent bound (it may add other pools). Identity exemptions
# are locked even when the parent kept the default, because an exemption removes a person from the
# authors; a child may only narrow them.
_LOCKED = {
    ("policy", "command"),
    ("policy", "pass_env"),
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
# An org preset lives outside every repository, so no repository file can be its parent.
ORG_PRESET_BY_URL = "an org preset lives outside the repository, so it names its parents by url only (with a sha256 pin)"


def _merge(parent: dict, child: dict, where: str, warnings: list[str] | None = None) -> dict:
    warnings = warnings if warnings is not None else []
    out = copy.deepcopy(parent)
    if "profile" in parent and profile_rank(child["profile"]) < profile_rank(parent["profile"]):
        raise ConfigError(f"{where}: profile {child['profile']!r} is weaker than the parent profile {parent['profile']!r}")
    locked = set(parent.get("locks", []))
    for key, value in child.items():
        if key in ("extends", "gates"):
            continue
        if key == "project":
            # A locked [project] binds as a floor: the child adds and tightens (project.merge), never loosens.
            from . import project

            out[key] = project.merge(out.get(key), value, locked=key in locked, where=where, warnings=warnings)
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
            # A parent's standard binds its children: they may add standards, never drop or redefine one.
            out[key] = _add_named(out.get(key, []), value, f"{where}: standards", warnings)
        elif key == "standards_policy":
            from . import standards

            # A company's policy binds as a floor: a child adds and tightens, never loosens.
            out[key] = standards.merge_policy(out.get(key) or {}, value, where, warnings)
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
                elif (key, sub) == ("owners", "specialists"):
                    pools = dict(current.get(sub) or {})
                    for pool, members in v.items():
                        if pool in pools and pools[pool] != members:
                            warnings.append(f"{where}: owners.specialists.{pool} is set by a parent config and cannot be replaced")
                        else:
                            pools[pool] = list(members)
                    merged[sub] = pools
                elif (key, sub) == ("guard", "held_commands"):
                    # A parent's deploy gate binds its children: they may add gates, never drop or redefine one.
                    merged[sub] = _add_named(current.get(sub, []), v, f"{where}: guard.held_commands", warnings)
                elif (key, sub) == ("hooks", "level") and "profile" in parent:
                    floor = hook_level(parent)
                    if HOOK_LEVELS.index(v) < HOOK_LEVELS.index(floor):
                        warnings.append(f"{where}: hooks.level={v!r} ignored; looser than {floor!r}")
                        merged[sub] = floor
                    else:
                        merged[sub] = v
                elif (key, sub) == ("agents", "delegate") and "profile" in parent:
                    floor = delegate_mode(parent)
                    if DELEGATE_MODES.index(v) < DELEGATE_MODES.index(floor):
                        warnings.append(f"{where}: agents.delegate={v!r} ignored; looser than {floor!r}")
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
    if "profile" in parent and "profile" in child and not (child.get("agents") or {}).get("delegate"):
        # A parent's mode, set or by its profile, binds as a floor, never below the child's own profile default.
        floor = max(delegate_mode(parent), DELEGATE_DEFAULTS.get(str(child["profile"]), "auto"), key=DELEGATE_MODES.index)
        if floor != DELEGATE_DEFAULTS.get(str(child["profile"]), "auto"):
            out["agents"] = {**(out.get("agents") or {}), "delegate": floor}
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
    skip_unread: bool = False,
) -> Config:
    """Load a config and its parents. `root_preset` is an org preset the gate injects as the first parent. With
    `skip_unread` (the guard, the session hooks, doctor, upkeep: tools that run offline by design), a URL parent that
    cannot be fetched is skipped with a warning (UNREAD_PARENT) instead of failing the load; the gate never skips."""
    if _depth > 5:
        raise ConfigError(f"{where}: extends is nested more than 5 levels")
    raw = model.parse_toml(text, where)
    warnings: list[str] = []
    from . import standards

    errors = schema.validate(raw, "config.schema.json")
    # An industry standard gets its own refusal (it is only waived per project), in place of the schema's error there.
    special = standards.config_problems(raw)
    if special:
        explained = tuple(path for path, _ in special)
        errors = [m for _, m in special] + [e for e in errors if not e.startswith(explained)]
    if errors:
        raise ConfigError("\n".join(f"{where}: {e}" for e in errors))
    merged: dict = {}
    parent_gates: dict | None = None
    parents: list[tuple[str, str]] = [("org preset", root_preset)] if root_preset else []
    for parent in raw.get("extends", []):
        key = parent.get("path") or parent["url"]
        ptext = (prefetched or {}).get(key)
        if ptext is None and "path" in parent and where == "org preset":
            raise ConfigError(f"{where}: extends {key!r}: {ORG_PRESET_BY_URL}")
        if ptext is None and "path" in parent and read:
            ptext = read(parent["path"])
        if ptext is None and "url" in parent:
            if fetch is None:
                raise ConfigError(f"{where}: cannot fetch {parent['url']} here; pass it pre-fetched")
            try:
                ptext = fetch(parent["url"]).decode("utf-8")
            except (OSError, RuntimeError, ValueError) as exc:  # HttpError is an OSError; an offline fetcher raises
                if not skip_unread:
                    raise
                warnings.append(f"{where}: extends {parent['url']} {UNREAD_PARENT} ({exc}); its settings do not apply on this machine, and the gate reads it")
                continue
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
            preset = load_text(ptext, read=None, fetch=fetch, prefetched=by_url, where=key, _depth=_depth + 1, skip_unread=skip_unread)
            preset.raw["locks"] = sorted(set(preset.raw.get("locks", [])) | set(ORG_PRESET_LOCKS))
            loaded.append((key, preset))
        else:
            loaded.append((key, load_text(ptext, read=read, fetch=fetch, prefetched=prefetched, where=key, _depth=_depth + 1, skip_unread=skip_unread)))
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
    # A folder at the repository's top would widen every role area and rule built from it to the whole repository.
    for label, value in (
        ("docs.dir", (merged.get("docs") or {}).get("dir")),
        ("specs_dir", merged.get("specs_dir")),
        ("proposals_dir", merged.get("proposals_dir")),
    ):
        if value is not None and globs.normal_dir(str(value)) == ".":
            raise ConfigError(f"{where}: {label} {value!r} names the repository's top; name a folder inside the repository")
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


def advice(cfg: Config) -> list[str]:
    """What `aidd doctor` and `aidd validate` warn about in a valid config and the gate never reports: settings that are
    allowed, but looser than a person likely meant."""
    out = []
    for entry in cfg.get("standard_changes", default=[]):
        if "third_party" in entry.get("dimensions", ["third_party"]) and "major" in entry.get("update_types", []):
            out.append(
                f"standard_changes {entry['name']!r} takes major third-party updates with no human approval. A major version can "
                'break the API it offers. Keep update_types = ["patch", "minor"] unless your tests would catch that'
            )
    return out


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


# The words a warning carries for an `extends` URL parent a tool that runs offline skipped (load_text's skip_unread).
UNREAD_PARENT = "was not read"


def load_file(path: str, root: str = ".", *, fetch: Fetcher | None = None, skip_unread: bool = False) -> Config:
    """Load a config from disk. `fetch` overrides how an `extends` URL parent is retrieved.

    The guard passes an offline fetcher: a 20-second hook must never block on the
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

        if "1" in (os.environ.get("AIDD_HOOK_OFFLINE"), os.environ.get("AIDD_OFFLINE")):

            def fetch(url: str) -> bytes:  # noqa: F811  # offline: never block on the network, nor reach it
                raise http.HttpError(0, url, "not fetched: offline (AIDD_OFFLINE=1, or a hook)")
        else:

            def fetch(url: str) -> bytes:  # noqa: F811
                # The gate's protected fetch: https only, a public address, and no redirect that would skip that check.
                from .inputs import fetch_text

                return fetch_text(url).encode("utf-8")

    from .inputs import org_preset_text

    return load_text(text, read=read, fetch=fetch, where=path, root_preset=org_preset_text(), skip_unread=skip_unread)


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
