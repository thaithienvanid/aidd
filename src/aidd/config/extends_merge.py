"""How a config merges over its `extends` parents: gates only get stricter, settings a parent owns stay locked, and a child may only narrow an exemption. What a merge refuses becomes a warning."""

from __future__ import annotations

import copy

from aidd.config import baseline, model

_LIST_MERGE = ("risk_rules", "protected_paths", "standard_changes", "disable_rules", "scope_exempt_paths", "budget_exclude_paths", "tests")


def profile_rank(name: str) -> int:
    return baseline.profiles()["order"].index(name)


_ORDERED = {
    "red_green": ["warn", "require"],
    "provenance": ["declare", "every_commit"],
    "unlinked_authors": ["warn", "fail"],
    "spec_approval_proof": ["optional", "require"],
    "local_approvals": ["any", "signed"],
    "approval_carry": ["trivial_rebase", "none"],
}
# Queue limits `aidd list` reads, never the gate: 0 is off, and a child may only lower a non-zero limit.
_QUEUE_LIMITS = (
    "max_open_per_approver",
    "escalate_after_minutes",
    "max_in_progress_per_owner",
    "max_in_progress_days",
    "max_goal_days",
    "max_branch_days",
    "max_open_branches",
)


def tighten(gates: dict, override: dict, where: str, warnings: list[str]) -> dict:
    out = copy.deepcopy(gates)
    for key, value in override.items():
        cur = out.get(key)
        if key in ("spec_approval_routes", "policy_required_routes", "observe_required_routes"):
            out[key] = sorted(set(cur or []) | set(value), key=model.ROUTE_KEYS.index)
        elif key == "approval_carry_routes":
            # Fewer routes on which an approval carries across a rebase is stricter: a child may only drop routes.
            wider = sorted(set(value) - set(cur or []), key=model.ROUTE_KEYS.index)
            if wider:
                warnings.append(f"{where}: gates.approval_carry_routes {wider} ignored; looser than {cur}")
            out[key] = sorted(set(cur or []) & set(value), key=model.ROUTE_KEYS.index)
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


def merge(parent: dict, child: dict, where: str, warnings: list[str] | None = None) -> dict:
    warnings = warnings if warnings is not None else []
    out = copy.deepcopy(parent)
    if "profile" in parent and profile_rank(child["profile"]) < profile_rank(parent["profile"]):
        raise model.ConfigError(f"{where}: profile {child['profile']!r} is weaker than the parent profile {parent['profile']!r}")
    locked = set(parent.get("locks", []))
    for key, value in child.items():
        if key in ("extends", "gates"):
            continue
        if key == "project":
            # A locked `project` binds as a floor: the child adds and tightens (project.merge), never loosens.
            from aidd.config import project

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
            from aidd.config import standards_policy

            # A company's policy binds as a floor: a child adds and tightens, never loosens.
            out[key] = standards_policy.merge_policy(out.get(key) or {}, value, where, warnings)
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
                    floor = model.hook_level(parent)
                    if model.HOOK_LEVELS.index(v) < model.HOOK_LEVELS.index(floor):
                        warnings.append(f"{where}: hooks.level={v!r} ignored; looser than {floor!r}")
                        merged[sub] = floor
                    else:
                        merged[sub] = v
                elif (key, sub) == ("agents", "delegate") and "profile" in parent:
                    floor = model.delegate_mode(parent)
                    if model.DELEGATE_MODES.index(v) < model.DELEGATE_MODES.index(floor):
                        warnings.append(f"{where}: agents.delegate={v!r} ignored; looser than {floor!r}")
                        merged[sub] = floor
                    else:
                        merged[sub] = v
                elif key == "hooks" and sub in model.HOOK_SWITCHES and current.get(sub) is True and v is False:
                    warnings.append(f"{where}: hooks.{sub}=false ignored; a parent config turns it on")
                elif key == "components" and current.get(sub) is True and v is False:
                    warnings.append(f"{where}: components.{sub}=false ignored; a parent config turns it on")
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
        own = model.HOOK_LEVEL_DEFAULTS.get(str(child["profile"]), inherited)
        out["hooks"] = {**out["hooks"], "level": max(inherited, own, key=model.HOOK_LEVELS.index)}
    if "profile" in parent and "profile" in child and not (child.get("agents") or {}).get("delegate"):
        # A parent's mode, set or by its profile, binds as a floor, never below the child's own profile default.
        floor = max(model.delegate_mode(parent), model.DELEGATE_DEFAULTS.get(str(child["profile"]), "auto"), key=model.DELEGATE_MODES.index)
        if floor != model.DELEGATE_DEFAULTS.get(str(child["profile"]), "auto"):
            out["agents"] = {**(out.get("agents") or {}), "delegate": floor}
    return out


def _add_named(parents: list[dict], children: list[dict], label: str, warnings: list[str]) -> list[dict]:
    """The parent's entries plus the child's, where a child entry reusing a parent's `name` is dropped with a warning."""
    names = {e.get("name") for e in parents}
    warnings += [f"{label} {e.get('name')!r} is set by a parent config and cannot be replaced" for e in children if e.get("name") in names]
    return list(parents) + [e for e in children if e.get("name") not in names]
