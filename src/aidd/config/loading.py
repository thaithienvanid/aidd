"""Load `.aidd/config.yaml` and its `extends` parents into a `Config`, with the warnings of every setting the merge refused, and what `aidd doctor` and `aidd validate` advise about a valid config."""

from __future__ import annotations

import copy
import hashlib
import posixpath
import re
from collections.abc import Callable

from aidd.config import baseline, extends, extends_merge, identities, model
from aidd.kernel import documents, globs, json_schema

TENANT = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")  # common.schema.json#/$defs/tenant


Reader = Callable[[str], "str | None"]
Fetcher = Callable[[str], bytes]


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
    """Load a config and its parents. `root_preset` is an org preset the gate injects as the first parent. With
    `skip_unread` (the guard, the session hooks, doctor, upkeep: tools that run offline by design), a URL parent that
    cannot be fetched is skipped with a warning (UNREAD_PARENT) instead of failing the load; the gate never skips."""
    if _depth > 5:
        raise model.ConfigError(f"{where}: extends is nested more than 5 levels")
    raw = documents.parse_yaml(text, where)
    warnings: list[str] = []
    from aidd.config import standards_policy

    errors = json_schema.validate(raw, "config.schema.json")
    # An industry standard gets its own refusal (it is only waived per project), in place of the schema's error there.
    special = standards_policy.config_problems(raw)
    if special:
        explained = tuple(path for path, _ in special)
        errors = [m for _, m in special] + [e for e in errors if not e.startswith(explained)]
    if errors:
        raise model.ConfigError("\n".join(f"{where}: {e}" for e in errors))
    merged: dict = {}
    parent_gates: dict | None = None
    parent_limits: dict | None = None
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
                warnings.append(f"{where}: extends {parent['url']} {UNREAD_PARENT} ({exc}); its settings do not apply on this machine, and the gate reads it")
                continue
        if ptext is None:
            raise model.ConfigError(f"{where}: extends {key!r} not found")
        if "sha256" in parent and hashlib.sha256(ptext.encode("utf-8")).hexdigest() != parent["sha256"]:
            raise model.ConfigError(f"{where}: extends {key!r} does not match its sha256 pin")
        parents.append((key, ptext))
    loaded: list[tuple[str, model.Config]] = []
    for key, ptext in parents:
        if key == "org preset":
            # The preset lives outside the repository: its parents come by URL, never from repo files.
            by_url = {k: v for k, v in (prefetched or {}).items() if "://" in k}
            preset = load_text(ptext, read=None, fetch=fetch, prefetched=by_url, where=key, _depth=_depth + 1, skip_unread=skip_unread)
            preset.raw["locks"] = sorted(set(preset.raw.get("locks", [])) | set(extends.ORG_PRESET_LOCKS))
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
            if k in ("gates", "limits"):
                continue
            if k in all_locks and k not in own:
                warnings.append(f"{key}: {k} is locked by another parent config and is ignored")
                continue
            praw[k] = v
        merged = extends_merge.merge(merged, praw, key) if merged else praw  # raises when a later parent is weaker
        parent_gates = pcfg.gates if parent_gates is None else extends_merge.tighten(parent_gates, pcfg.gates, key, [])
        parent_limits = pcfg.limits if parent_limits is None else extends_merge.tighten_limits(parent_limits, pcfg.limits, key, [])
    merged = extends_merge.merge(merged, raw, where, warnings) if merged else copy.deepcopy(raw)
    profile = merged["profile"]
    defaults = baseline.profiles()["profiles"][profile]
    gates = {k: v for k, v in defaults.items() if k not in ("description", "mode", "limits")}
    if parent_gates is not None:
        gates = extends_merge.tighten(gates, parent_gates, "extends", [])
    gates = extends_merge.tighten(gates, raw.get("gates", {}), where, warnings)
    merged["gates"] = gates
    # The limits only tighten too, the same way: the profile's, then the parents', then this config's.
    limits = dict(defaults.get("limits") or {})
    if parent_limits is not None:
        limits = extends_merge.tighten_limits(limits, parent_limits, "extends", [])
    merged["limits"] = extends_merge.tighten_limits(limits, raw.get("limits", {}), where, warnings)
    # A folder at the repository's top would widen every role area and rule built from it to the whole repository.
    for label, value in (
        ("docs.dir", (merged.get("docs") or {}).get("dir")),
        ("specs_dir", merged.get("specs_dir")),
        ("proposals_dir", merged.get("proposals_dir")),
    ):
        if value is not None and globs.normal_dir(str(value)) == ".":
            raise model.ConfigError(f"{where}: {label} {value!r} names the repository's top; name a folder inside the repository")
    _bots_only(merged, where, warnings)
    _guard_grants_and_exemptions(merged, where, warnings)
    _content_patterns(merged, where)
    # As git names it in a diff: `shared//base.yaml` is `shared/base.yaml`.
    by_path = [posixpath.normpath(k.replace("\\", "/")).lstrip("/") for k, _ in parents if k != "org preset" and "://" not in k]
    parent_paths = by_path + [p for _, pcfg in loaded for p in pcfg.parent_paths]
    return model.Config(raw=merged, profile=profile, gates=gates, warnings=warnings, parent_paths=tuple(dict.fromkeys(parent_paths)))


def _content_patterns(merged: dict, where: str) -> None:
    """A risk rule's `content` patterns compile, or the config is refused: a pattern that cannot run would leave the
    rule silently off."""
    for rule in merged.get("risk_rules", []):
        for pattern in rule.get("content", []) if isinstance(rule, dict) else []:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise model.ConfigError(f"{where}: risk_rules {rule.get('name')!r} content {pattern!r} is not a regular expression: {exc}") from exc


def _guard_grants_and_exemptions(merged: dict, where: str, warnings: list[str]) -> None:
    """A pattern matching every path would silently grant full exemption or merge rights; drop it and warn."""
    targets: list[tuple[dict, str, str]] = [(merged, key, key) for key in ("scope_exclude_paths", "changed_lines_exclude_paths")]
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


def advice(cfg: model.Config) -> list[str]:
    """What `aidd doctor` and `aidd validate` warn about in a valid config and the gate never reports: settings that are
    allowed, but looser than a person likely meant."""
    out = []
    for entry in cfg.get("standard_changes", default=[]):
        if "third_party" in entry.get("dimensions", ["third_party"]) and "major" in entry.get("update_types", []):
            out.append(
                f"standard_changes {entry['name']!r} takes major third-party updates with no human approval. A major version can "
                'break the API it offers. Keep update_types: ["patch", "minor"] unless your tests would catch that'
            )
    return out


def preset_tenant(text: str | None) -> str | None:
    """The tenant an org preset names, best effort, for an event about a run that failed before the config was read."""
    if not text:
        return None
    try:
        value = documents.parse_yaml(text, "org preset").get("tenant")
    except Exception:  # an unreadable preset is reported by the run itself; the event just has no tenant
        return None
    return value if isinstance(value, str) and TENANT.match(value) else None


def _bots_only(merged: dict, where: str, warnings: list[str]) -> None:
    """identities.system_accounts is for platform bookkeeping accounts; a person listed there would stop being an author."""
    accounts = merged.get("identities", {}).get("system_accounts")
    if accounts is None:
        return
    people = [x for x in accounts if not identities.is_bot(x)]
    if people:
        warnings.append(f"{where}: identities.system_accounts {people} ignored: only bot accounts (*[bot], web-flow, github-actions) may be exempt")
        merged["identities"]["system_accounts"] = [x for x in accounts if identities.is_bot(x)]


# The words a warning carries for an `extends` URL parent a tool that runs offline skipped (load_text's skip_unread).
UNREAD_PARENT = "was not read"


def load_file(path: str, root: str = ".", *, fetch: Fetcher | None = None, skip_unread: bool = False) -> model.Config:
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

        from aidd.kernel import http

        if "1" in (os.environ.get("AIDD_HOOK_OFFLINE"), os.environ.get("AIDD_OFFLINE")):

            def fetch(url: str) -> bytes:  # noqa: F811  # offline: never block on the network, nor reach it
                raise http.HttpError(0, url, "not fetched: offline (AIDD_OFFLINE=1, or a hook)")
        else:

            def fetch(url: str) -> bytes:  # noqa: F811
                # The gate's protected fetch: https only, a public address, and no redirect that would skip that check.
                from aidd.kernel import egress

                return egress.fetch_text(url).encode("utf-8")

    return load_text(text, read=read, fetch=fetch, where=path, root_preset=extends.org_preset_text(), skip_unread=skip_unread)
