"""`aidd context` (experimental): the minimal context pack for one step of one Spec.

A role reads by path, just in time: the pack names what to read, each with a one-line reason and a token estimate, and
never pastes a file's contents. In order: the Spec summary (`aidd hash --summary`), the Task (the role's Tasks with
`--role`), the docs the Spec links (`docs`, design files, ADRs in `adrs`), for the Specify step the exemplar
Specs a person named (`docs.exemplars`), the latest handoff note, and the standards for the Task's paths as
`aidd owners --changed` lists them. The same repository gives the same pack.

Every path comes from a file an agent may have written, so each one is resolved first: an entry that is absolute, or
that resolves (through `..` or a symbolic link) outside the repository, is listed as outside it and is never read or
measured. A size is the regular file's byte count from `os.stat`, divided by four as `aidd eval packs` counts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from aidd import config, knowledge, views, workitems
from aidd.kernel import documents, git, globs, repo_paths, resources

SCHEMA_VERSION = "1"
CHARS_PER_TOKEN = 4
OUTSIDE = "outside the repository: not read"
DEFAULT_ROLE = "developer"  # the implementer for a Task whose assignee names no role (`agent:<harness>`)


def tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _contained(root: Path, rel: str) -> bool:
    """Whether `rel` stays inside the repository (it need not exist)."""
    if not rel or Path(rel).is_absolute() or Path(rel).drive:
        return False
    top = root.resolve()
    try:
        return (top / rel).resolve().is_relative_to(top)
    except (OSError, RuntimeError):
        return False


def find_spec_file(root: Path, spec: str, specs_dir: str = "specs") -> Path:
    """The Spec file a path or an id names, inside the repository's working tree."""
    p = repo_paths.inside(root, spec) if ("/" in spec or "\\" in spec or spec.endswith(".md")) else None
    if p is not None:
        return p
    if "/" in spec or "\\" in spec or Path(spec).is_absolute():
        raise ValueError(f"{spec!r} is not a Spec file inside the repository")
    folder = root.resolve() / specs_dir
    for path in sorted(folder.rglob("*.md")) if _contained(root, specs_dir) and folder.is_dir() else []:
        found = repo_paths.inside(root, path.relative_to(root.resolve()).as_posix())
        if found is None:
            continue
        try:
            data, _ = documents.split_front_matter(found.read_text(encoding="utf-8"), str(path))
        except (documents.DocumentError, OSError, UnicodeDecodeError):
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
        return any(f.get("command") == "specify" and step in (f.get("starts_on") or []) for f in knowledge.roles()["loop"]["flows"])
    writes = set((knowledge.roles()["roles"].get(role) or {}).get("writes") or []) if role else {"{spec}"}
    return bool({"{spec}", "{specs_dir}"} & writes)


def _item(root: Path, kind: str, rel: str, why: str) -> dict:
    found = repo_paths.inside(root, rel)
    if found is None:
        return {"kind": kind, "path": rel, "reason": f"{why} ({OUTSIDE})" if not _contained(root, rel) else f"{why} (missing)", "tokens": 0}
    return {"kind": kind, "path": found.relative_to(root.resolve()).as_posix(), "reason": why, "tokens": _size(found)}


def playbook_item(root: Path, role: str) -> dict:
    """The role's playbook, to play it in the lead's own session (role placement `lead`): the agent file this aidd
    ships, with its hard rules, its done-when, and the practice skills it names. The one item from outside the
    repository: aidd's own package, which is trusted, so it is measured. Named by path, never pasted."""
    if role not in workitems.role_ids():
        raise ValueError(f"no role {role!r}; `aidd owners` lists every role")
    found = resources.data_dir("team") / "agents" / f"{role}.md"
    shown = found.resolve()
    inside = shown.is_relative_to(root.resolve())
    return {
        "kind": "playbook",
        "path": shown.relative_to(root.resolve()).as_posix() if inside else str(shown),
        "reason": f"the {role}'s playbook, to play the role in your own session: its rules, its done-when, and the practice skills to load",
        "tokens": _size(found),
    }


def build_context_pack(root: Path, spec: str, *, role: str | None = None, step: str | None = None, play: bool = False) -> dict:
    """The pack (schemas/context-pack.schema.json): {schema_version, spec, path, role, step, items, tokens}. With
    `play`, the pack is for the lead to play `role` itself, so it starts with that role's playbook."""
    if play and not role:
        raise ValueError("--play needs --role: the role you play in your own session")
    cfg = config.load_file(config.CONFIG_PATH, str(root)) if (root / config.CONFIG_PATH).is_file() else None
    path = find_spec_file(root, spec, cfg.specs_dir if cfg else "specs")
    rel = path.relative_to(root.resolve()).as_posix()
    text = path.read_text(encoding="utf-8")
    data, body = documents.split_front_matter(text, rel)
    sid = str(data.get("id") or rel)
    items: list[dict] = [playbook_item(root, role)] if play and role else []
    summary = views.spec_summary(text, rel, f"/aidd approve-spec {sid} <commit>")
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
    tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    seen: set[str] = {rel}
    linked = [(str(d.get("path")), f"{d.get('kind', 'doc')} doc the Spec links") for d in data.get("docs") or [] if isinstance(d, dict) and d.get("path")]
    linked += [(str(p), "design file approved with the Spec") for p in (data.get("design") or {}).get("files") or []]
    linked += [(str(p), "ADR the Spec depends on") for p in data.get("adrs") or [] if "://" not in str(p)]
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
    standards = knowledge.config_standards(cfg)
    if role:
        chosen = knowledge.standards_for(standards, role, changed)
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


def context_pack_markdown(pack: dict) -> str:
    head = f"Context for {pack['spec']}" + (f", role {pack['role']}" if pack.get("role") else "") + (f", step {pack['step']}" if pack.get("step") else "")
    lines = [f"{head}: about {pack['tokens']} tokens. Read each by path, when the step needs it.", ""]
    for i in pack["items"]:
        where = f"`{i['command']}`" if i.get("command") else i["path"]
        lines.append(f"- {where} (~{i['tokens']} tokens): {i['reason']}")
    return "\n".join(lines) + "\n"
