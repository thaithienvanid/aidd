"""The checks of the standards a repository copied in: what `aidd doctor` says about those copies (drift, edits, the company
policy's breaches, and deprecated or renamed ids), split from `standards` to keep each module short."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import command_names, documents, json_schema, retired_names
from aidd.knowledge import standards


def _expected(s_meta: dict, sid: str, path: str) -> tuple[dict, dict[str, dict]]:
    """The `standards` entry (without `from_library`) and the `tests` entries a copy of `sid` brings."""
    entry: dict = {"name": standards.entry_name(sid), "path": path, "fills": list(s_meta["fills"]), "roles": list(s_meta["roles"])}
    tests: dict[str, dict] = {}
    for e in s_meta.get("enforced_by", []):
        name = standards.test_name(sid, e["name"])
        test: dict = {"name": name, "command": list(e["command"])}
        if s_meta.get("when_changed"):
            test["when_changed"] = list(s_meta["when_changed"])
        tests[name] = test
    if s_meta.get("when_changed"):
        entry["when_changed"] = list(s_meta["when_changed"])
    if tests:
        entry["enforced_by"] = list(tests)
    return entry, tests


def weakened(copy_entry: dict, s_meta: dict, suite: list[dict]) -> list[str]:
    """What in a copy's config entry, or in the `tests` entries it brought, no longer matches the standard it copies."""
    sid = copy_entry["from_library"]["id"]
    entry, tests = _expected(s_meta, sid, copy_entry["path"])
    have = {k: v for k, v in copy_entry.items() if k != "from_library"}
    out = [f"the `standards` entry's {k}" for k in sorted(set(entry) | set(have)) if entry.get(k) != have.get(k)]
    by_name = {x.get("name"): x for x in suite}
    out += [f"the `tests` entry {name}" for name, want in tests.items() if by_name.get(name) != want]
    return out


def retired_keys(text: str | None, path: str) -> list[str]:
    """What a copy's front matter still holds under a name aidd retired, each as `old` is now `new`, in the file's order."""
    try:
        meta = documents.split_front_matter(text or "", path)[0]
    except documents.DocumentError:
        return []
    rows = (retired_names.row_for("standard", p) if (p := retired_names.error_path(e)) else None for e in json_schema.validate(meta, "standard.schema.json"))
    return [f"`{row['old']}` is now `{row['new']}`" for row in rows if row]


def standard_doctor_checks(root: Path, cfg) -> list[tuple[str, str]]:
    """The copies' drift, edits, and deprecated or renamed ids; the policy's breaches; and `fills` that name no choice."""
    out: list[tuple[str, str]] = []
    lib, moved, policy = standards.standards_library(), standards.renames(), standards.company_policy(cfg)
    choices = standards.open_choices()
    entries = list(cfg.standards)
    for e in entries:
        for ref in e.get("fills", []):
            if ref not in choices:
                out.append(("warn", f"standards {e['name']!r}: fills {ref}, which no pack or practice skill declares (`aidd standard list` names them)"))
    seen: dict[tuple[str, str], str] = {}
    clean = 0
    picks = standards.defaults(lib)
    for e in standards.standard_copies(entries):
        v, name = e["from_library"], e["name"]
        sid = v["id"]
        where = f"standards {name!r}"
        for ref in e.get("fills", []):
            slot = (ref, standards.standard_ecosystem(sid))
            if slot in seen:
                hint = f" (aidd's default: {picks[slot]})" if slot in picks else ""
                out.append(("warn", f"{where}: {seen[slot]} already fills {ref} for {standards.standard_ecosystem(sid)}; keep one standard per choice{hint}"))
            seen[slot] = name
        text = standards.read_copy(root, str(e["path"]))
        edited = standards.copy_edited(text, v, lib.get(sid))
        required = sid in policy.get("require", [])
        # The entry and its tests must still say what the standard says: compare them with the copy (or the library's text).
        source = lib[sid].meta if (edited or text is None) and sid in lib else None
        if source is None and text is not None:
            try:
                source = documents.split_front_matter(text, e["path"])[0]
            except documents.DocumentError:
                source = lib[sid].meta if sid in lib else None
        if isinstance(source, dict) and json_schema.validate(source, "standard.schema.json"):
            source = lib[sid].meta if sid in lib else None
        weak = weakened(e, source, list(cfg.get("tests", default=[]) or [])) if isinstance(source, dict) else []
        if weak and required:
            out.append(
                (
                    "fail",
                    f"standards policy: {name}: its config entry no longer matches {sid} ({', '.join(weak)}), which the company requires as it is; restore it",
                )
            )
        elif weak:
            out.append(
                (
                    "warn",
                    f"{where}: its config entry no longer matches {sid} ({', '.join(weak)}); restore it between its `# aidd:standard` markers, "
                    "or remove the entry and run `aidd standard add` again",
                )
            )
        if edited and (old := retired_keys(text, str(e["path"]))):
            out.append(("warn", f"{where}: the copy holds names aidd retired ({'; '.join(old)}); `aidd upgrade --yes` moves them"))
        if edited and required:
            out.append(("fail", f"standards policy: {name} is an edited copy of {sid}, which the company requires as it is; restore the copy"))
        elif edited:
            out.append(
                (
                    "warn",
                    f"{where}: the copy of {sid} was edited; never edit a copy: restore it, or write your own standard and name it in `standards_policy.replace`",
                )
            )
        if sid in moved:
            out.append(("warn", f"{where}: {sid} was renamed to {moved[sid]}; `aidd upgrade --yes` moves the copy"))
        elif sid not in lib:
            out.append(("warn", f"{where}: {sid} is no longer in aidd's library; keep it as your own standard, or remove it"))
        elif not lib[sid].active:
            new = lib[sid].meta.get("replaced_by")
            out.append(
                (
                    "warn",
                    f"{where}: {sid} is deprecated, replaced by {new}; `aidd standard add {command_names.quoted(str(new)) or '<id>'}`, then remove this one",
                )
            )
        elif lib[sid].sha256 != v["sha256"] and not edited:
            out.append(("warn", f"{where}: aidd {standards.__version__} ships a newer {sid}; `aidd upgrade --yes` refreshes the copy"))
        elif not edited and not weak and text is not None:
            clean += 1
        if sid in policy.get("exclude", []):
            out.append(("fail", f"standards policy: {name} copies {sid}, which the company excludes; remove it"))
        if sid in (policy.get("replace") or {}):
            out.append(("fail", f"standards policy: {name} copies {sid}, which the company replaces with its own standard {policy['replace'][sid]}"))
        allowed = policy.get("allow_stacks")
        if v.get("stack") and allowed is not None and v["stack"] not in allowed:
            out.append(
                (
                    "fail",
                    f"standards policy: {name} came with the stack {v['stack']}, which the company does not allow (allow_stacks: {', '.join(allowed) or 'none'})",
                )
            )
    present = {e["from_library"]["id"] for e in standards.standard_copies(entries)}
    for sid in policy.get("require", []):
        if sid not in present:
            out.append(("fail", f"standards policy: the company requires {sid}; `aidd standard add {command_names.quoted(sid) or '<id>'}`"))
    named = {e["name"] for e in entries}
    for sid, name in sorted((policy.get("replace") or {}).items()):
        if name not in named:
            out.append(("warn", f"standards policy: {sid} is replaced by {name}, which is no `standards` entry here"))
    for key in ("require", "exclude"):
        for sid in policy.get(key, []):
            if sid not in lib and sid not in moved:
                out.append(("warn", f"standards policy: {key} names {sid}, which is no library standard of aidd {standards.__version__}"))
    if clean and not any(level != "ok" for level, _ in out):
        out.append(("ok", f"library standards: {clean} copies match aidd {standards.__version__}"))
    return out
