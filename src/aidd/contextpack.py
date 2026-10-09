"""`aidd context` (experimental): the minimal context pack for one step of one Spec.

A role reads by path, just in time: the pack names what to read, each with a one-line reason and a token estimate, and
never pastes a file's contents. In order: the Spec summary (`aidd hash --summary`), the Task (the role's Tasks with
`--role`), the docs the Spec links (`[[docs]]`, design files, ADRs in `decisions`), for the Specify step the exemplar
Specs a person named (`[docs] exemplars`), the latest handoff note, and the standards for the Task's paths as
`aidd owners --changed` lists them. The same repository gives the same pack.

Every path comes from a file an agent may have written, so each one is resolved first: an entry that is absolute, or
that resolves (through `..` or a symbolic link) outside the repository, is listed as outside it and is never read or
measured. A size is the regular file's byte count from `os.stat`, divided by four as `aidd eval packs` counts.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from . import config as cfgmod
from . import digest, gitutil, globs, model, owners, resources, workitems

SCHEMA_VERSION = "1"
CHARS_PER_TOKEN = 4
OUTSIDE = "outside the repository: not read"
DEFAULT_ROLE = "developer"  # the implementer for a Task whose assignee names no role (`agent:<harness>`)


def tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def inside(root: Path, rel: str) -> Path | None:
    """The file `rel` names, when it is a regular file inside the repository once every link is resolved; else None."""
    if not rel or Path(rel).is_absolute() or Path(rel).drive:
        return None
    top = root.resolve()
    try:
        target = (top / rel).resolve()
    except (OSError, RuntimeError):
        return None
    if not target.is_relative_to(top):
        return None
    try:
        return target if stat.S_ISREG(os.stat(target).st_mode) else None
    except OSError:
        return None


def _contained(root: Path, rel: str) -> bool:
    """Whether `rel` stays inside the repository (it need not exist)."""
    if not rel or Path(rel).is_absolute() or Path(rel).drive:
        return False
    top = root.resolve()
    try:
        return (top / rel).resolve().is_relative_to(top)
    except (OSError, RuntimeError):
        return False


def find_spec(root: Path, spec: str, specs_dir: str = "specs") -> Path:
    """The Spec file a path or an id names, inside the repository's working tree."""
    p = inside(root, spec) if ("/" in spec or "\\" in spec or spec.endswith(".md")) else None
    if p is not None:
        return p
    if "/" in spec or "\\" in spec or Path(spec).is_absolute():
        raise ValueError(f"{spec!r} is not a Spec file inside the repository")
    folder = root.resolve() / specs_dir
    for path in sorted(folder.rglob("*.md")) if _contained(root, specs_dir) and folder.is_dir() else []:
        found = inside(root, path.relative_to(root.resolve()).as_posix())
        if found is None:
            continue
        try:
            data, _ = model.split_front_matter(found.read_text(encoding="utf-8"), str(path))
        except (model.ModelError, OSError, UnicodeDecodeError):
            continue
        if data.get("kind") == "spec" and str(data.get("id")) == spec:
            return found
    raise ValueError(f"no Spec {spec!r}: give its path, such as specs/SPEC-1.md, or its id")


def _size(path: Path) -> int:
    """Tokens from the byte count of a verified, in-repository regular file; never read."""
    return (os.stat(path).st_size + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def role_of(task: dict) -> str | None:
    """The role a Task is for: `agent:<role>` names it; an agent assignee that names no role (`agent:claude-code`), or
    none at all, is the default implementer's; a person's Task is no role's."""
    assignee = str(task.get("assignee") or "")
    if not assignee:
        return DEFAULT_ROLE
    if not assignee.startswith("agent:"):
        return None
    name = assignee.split(":", 1)[1]
    return name if name in workitems.role_ids() else DEFAULT_ROLE


def reads_exemplars(role: str | None, step: str | None) -> bool:
    """Whether the pack lists the exemplar Specs: on a step the specify flow starts on (roles.json), or with no step
    for every role or a role that writes the Spec."""
    if step is not None:
        return any(f.get("command") == "specify" and step in (f.get("starts_on") or []) for f in resources.roles()["loop"]["flows"])
    writes = set((resources.roles()["roles"].get(role) or {}).get("writes") or []) if role else {"{spec}"}
    return bool({"{spec}", "{specs_dir}"} & writes)


def _item(root: Path, kind: str, rel: str, why: str) -> dict:
    found = inside(root, rel)
    if found is None:
        return {"kind": kind, "path": rel, "reason": f"{why} ({OUTSIDE})" if not _contained(root, rel) else f"{why} (missing)", "tokens": 0}
    return {"kind": kind, "path": found.relative_to(root.resolve()).as_posix(), "reason": why, "tokens": _size(found)}


def build(root: Path, spec: str, *, role: str | None = None, step: str | None = None) -> dict:
    """The pack (schemas/context-pack.schema.json): {schema_version, spec, path, role, step, items, tokens}."""
    cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root)) if (root / cfgmod.CONFIG_PATH).is_file() else None
    path = find_spec(root, spec, cfg.specs_dir if cfg else "specs")
    rel = path.relative_to(root.resolve()).as_posix()
    text = path.read_text(encoding="utf-8")
    data, body = model.split_front_matter(text, rel)
    sid = str(data.get("id") or rel)
    items: list[dict] = []
    summary = digest.spec_digest(text, rel, f"/aidd approve-spec {sid} <hash>")
    items.append({"kind": "summary", "command": f"aidd hash {rel} --summary", "reason": "what Spec approval covers, on one screen", "tokens": tokens(summary)})
    every = [t for t in data.get("tasks") or [] if isinstance(t, dict)]
    tasks = [t for t in every if role_of(t) == role] if role else every
    for t in tasks:
        scope = ", ".join(t.get("scope") or [])
        items.append(
            {
                "kind": "task",
                "path": rel,
                "reason": f"Task {t.get('id')}: {t.get('title')} (scope {scope}), in the front matter",
                "tokens": tokens(json.dumps(t, sort_keys=True)),
            }
        )
    tracked = [p for p in gitutil.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    seen: set[str] = {rel}
    linked = [(str(d.get("path")), f"{d.get('kind', 'doc')} doc the Spec links") for d in data.get("docs") or [] if isinstance(d, dict) and d.get("path")]
    linked += [(str(p), "design file approved with the Spec") for p in (data.get("design") or {}).get("files") or []]
    linked += [(str(p), "ADR the Spec depends on") for p in data.get("decisions") or [] if "://" not in str(p)]
    for pattern, why in linked:
        if not _contained(root, pattern):
            if pattern not in seen:
                seen.add(pattern)
                items.append({"kind": "doc", "path": pattern, "reason": f"{why} ({OUTSIDE})", "tokens": 0})
            continue
        matches = sorted(p for p in tracked if globs.match_any([pattern], p)) or [pattern]
        for p in matches:
            if p not in seen:
                seen.add(p)
                items.append(_item(root, "doc", p, why))
    if cfg is not None and reads_exemplars(role, step):
        for p in cfg.get("docs", "exemplars", default=[]) or []:
            if str(p) not in seen:
                seen.add(str(p))
                items.append(_item(root, "exemplar", str(p), "an exemplar a person chose"))
    note = workitems.latest_handoff(body)
    if note:
        blocks = workitems.HANDOFF_FENCE.findall(body)
        items.append(
            {
                "kind": "handoff",
                "path": rel,
                "reason": f"the latest handoff note (next: {note.get('next')}" + (f"; stopped at {note['stopped_at']}" if note.get("stopped_at") else "") + ")",
                "tokens": tokens(blocks[-1] if blocks else ""),
            }
        )
    scopes = [str(g) for t in tasks for g in t.get("scope") or []]
    changed = sorted({p for p in tracked if globs.match_any(scopes, p)} | set(scopes))
    standards = owners.config_standards(cfg)
    if role:
        chosen = owners.standards_for(standards, role, changed)
    else:
        chosen = [s for s in standards if not s["when_changed"] or any(globs.match_any(s["when_changed"], p) for p in changed)]
    for s in chosen:
        if s["path"] not in seen:
            seen.add(s["path"])
            items.append(_item(root, "standard", s["path"], f"standard {s['name']} ({s['enforcement']}) for {', '.join(s['roles'])}"))
    return {
        "schema_version": SCHEMA_VERSION,
        "spec": sid,
        "path": rel,
        "role": role,
        "step": step,
        "items": items,
        "tokens": sum(int(i["tokens"]) for i in items),
    }


def markdown(pack: dict) -> str:
    head = f"Context for {pack['spec']}" + (f", role {pack['role']}" if pack.get("role") else "") + (f", step {pack['step']}" if pack.get("step") else "")
    lines = [f"{head}: about {pack['tokens']} tokens. Read each by path, when the step needs it.", ""]
    for i in pack["items"]:
        where = f"`{i['command']}`" if i.get("command") else i["path"]
        lines.append(f"- {where} (~{i['tokens']} tokens): {i['reason']}")
    return "\n".join(lines) + "\n"
