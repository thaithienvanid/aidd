"""`standards_policy`: the library standards a company requires, excludes, or replaces, merged down the `extends`
chain as a floor a child only tightens, and the problems an entry can have."""

from __future__ import annotations

import re

from aidd.kernel import resources

LIBRARY_ID = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")


POLICY_LISTS = ("require", "exclude")


INDUSTRY_REFUSAL = (
    "{where}: {id!r} is an industry standard (the registry, schemas/roles.json); `standards_policy` takes opinionated library ids only. "
    "An industry standard applies everywhere and is only waived per project, with a reason and an expiry"
)


def registry_ids() -> set[str]:
    return set(resources.load_json("roles.json")["standards"])  # the registry table, as roles() keeps it


def config_problems(raw: dict) -> list[tuple[str, str]]:
    """(schema path, message) for what a config may never say about standards, in words the schema cannot give: an
    industry id in `standards_policy`, and `type: industry` in a `standards` entry. It reads only values of the
    right type, so a value of the wrong type is left to the schema's own error."""
    industry = registry_ids()
    out: list[tuple[str, str]] = []
    policy = raw.get("standards_policy")
    if isinstance(policy, dict):
        for key in POLICY_LISTS:
            values = policy.get(key)
            for i, sid in enumerate(values if isinstance(values, list) else []):
                if isinstance(sid, str) and sid in industry:
                    out.append((f"$.standards_policy.{key}[{i}]", INDUSTRY_REFUSAL.format(where=f"standards_policy.{key}", id=sid)))
        replace = policy.get("replace")
        for sid in replace if isinstance(replace, dict) else {}:
            if sid in industry:
                out.append(("$.standards_policy.replace", INDUSTRY_REFUSAL.format(where="standards_policy.replace", id=sid)))
            elif not LIBRARY_ID.match(sid):
                # The schema's checker reads no `propertyNames`, so the form of a key is checked here.
                out.append(("$.standards_policy.replace", f"standards_policy.replace: {sid!r} is no library id (`<group>/<topic>`)"))
    entries = raw.get("standards")
    for i, e in enumerate(entries if isinstance(entries, list) else []):
        if isinstance(e, dict) and e.get("type") == "industry":
            out.append(
                (
                    f"$.standards[{i}].type",
                    f"standards {e.get('name')!r}: an industry standard lives only in the registry (schemas/roles.json), and the packs apply it "
                    "everywhere; a project only waives one, with a reason and an expiry. Drop `type`, or propose the standard to aidd's registry",
                )
            )
    return out


def merge_policy(parent: dict, child: dict, where: str, warnings: list[str]) -> dict:
    """A child's policy on its parent's: it adds and tightens, never loosens."""
    out = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in parent.items()}
    require, exclude = list(parent.get("require", [])), list(parent.get("exclude", []))
    replace = dict(parent.get("replace", {}))
    for sid in child.get("require", []):
        if sid in exclude or sid in replace:
            warnings.append(f"{where}: standards_policy.require {sid!r} ignored; a parent config excludes or replaces it")
        elif sid not in require:
            require.append(sid)
    for sid in child.get("exclude", []):
        if sid in require:
            warnings.append(f"{where}: standards_policy.exclude {sid!r} ignored; a parent config requires it")
        elif sid not in exclude:
            exclude.append(sid)
    for sid, name in (child.get("replace") or {}).items():
        if sid in replace and replace[sid] != name:
            warnings.append(f"{where}: standards_policy.replace {sid!r} ignored; a parent config replaces it with {replace[sid]!r}")
        elif sid in require:
            warnings.append(f"{where}: standards_policy.replace {sid!r} ignored; a parent config requires it")
        else:
            replace[sid] = name
    if "allow_stacks" in child:
        if "allow_stacks" in parent:
            extra = [s for s in child["allow_stacks"] if s not in parent["allow_stacks"]]
            if extra:
                warnings.append(f"{where}: standards_policy.allow_stacks cannot add {extra}; a parent config allows only {parent['allow_stacks']}")
            out["allow_stacks"] = [s for s in child["allow_stacks"] if s in parent["allow_stacks"]]
        else:
            out["allow_stacks"] = list(child["allow_stacks"])
    for key, value in (("require", require), ("exclude", exclude)):
        if value or key in out:
            out[key] = value
    if replace or "replace" in out:
        out["replace"] = replace
    return out
