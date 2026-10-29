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
import shlex
from pathlib import Path

from aidd import config, knowledge, views, workitems
from aidd.kernel import documents, git, globs, repo_paths, resources

SCHEMA_VERSION = "1"
CHARS_PER_TOKEN = 4
OUTSIDE = "outside the repository: not read"
DEFAULT_ROLE = "developer"  # the builder for a Task whose assignee names no role (`agent:<harness>`)


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
    none at all, is the default builder's; a person's Task is no role's."""
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


def steps_for(role: str | None, step: str | None) -> list[str]:
    """The loop steps a pack serves, in loop order: the steps of every flow a step code starts, kept to the role's own
    with a role; with no step code, the role's own steps; none with neither. A step code no flow starts on is an error,
    since it decides what the pack holds."""
    data = knowledge.roles()
    order = list(data["loop"]["steps"])
    own = set((data["roles"].get(role) or {}).get("steps") or []) if role else None
    if step is None:
        return [s for s in order if own and s in own]
    codes = sorted({c for f in data["loop"]["flows"] for c in f.get("starts_on") or []})
    if step not in codes:
        raise ValueError(f"no step code {step!r}; name one the flows start on: {', '.join(codes)}")
    flow_steps = {s for f in data["loop"]["flows"] if step in (f.get("starts_on") or []) for s in f.get("steps") or []}
    return [s for s in order if s in flow_steps and (own is None or s in own)]


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


# At most this many files of one product-level kind go into a pack: a large body of work is read by path, as it needs.
LIVING_FILES = 8
# Files a pack never hands out as text to read.
_BINARY = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".zip")


def _entry_first(path: str) -> tuple[int, str]:
    """A kind's top-level files (its sitemap, its overview) before the pages under them."""
    return path.count("/"), path


def living_work(role: str | None, tracked: list[str], cfg, sid: str = "") -> list[tuple[str, str]]:
    """The product-level work a role keeps or reads (`loop.documents`: its owner, and `read_by`), as tracked files with
    their reason: the architecture overview for the architect, the developer, and the reviewer, and the product prototype
    for the designer and those who build and check against it. A reader gets the whole kind only when Spec `sid` changes
    a kind that feeds it (its design for the prototype, its tech spec for the overview); otherwise only the kind's
    top-level files, to read further by path. Top-level files come first, and no binary file is handed out. Nothing
    when no role is named."""
    if not role:
        return []
    docs_dir = cfg.docs_dir if cfg else "docs"
    specs_dir = cfg.specs_dir if cfg else "specs"
    documents = knowledge.roles()["loop"]["documents"]
    found: list[tuple[str, str]] = []
    for kind, doc in documents.items():
        if doc.get("scope") != "product" or not doc.get("files") or role not in [doc["owner"], *doc.get("read_by", [])]:
            continue
        patterns = [g.replace("{docs}", docs_dir) for g in doc["files"]]
        files = sorted((p for p in tracked if globs.match_any(patterns, p) and not p.lower().endswith(_BINARY)), key=_entry_first)
        feeders = [
            g.replace("{specs}", specs_dir).replace("{docs}", docs_dir).replace("<ID>", sid)
            for other in documents.values()
            if other.get("feeds") == kind
            for g in other.get("files") or []
        ]
        fed = bool(sid) and any(globs.match_any(feeders, p) for p in tracked)
        if role != doc["owner"] and not fed and files:
            files = [p for p in files if p.count("/") == files[0].count("/")]
        mine = "build and check against it"
        if role == doc["owner"]:
            mine = "a Task's scope changes it, after Spec approval" if doc.get("changed_only_in_a_task") else "keep it in line in the same change"
        found += [(p, f"the {kind.replace('-', ' ')}, the {doc['owner']}'s product-level work: {mine}") for p in files[:LIVING_FILES]]
    return found


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
    items.append(
        {
            "kind": "summary",
            "command": f"aidd hash {shlex.quote(rel)} --summary",
            "reason": "what Spec approval covers, on one screen",
            "tokens": tokens(summary),
        }
    )
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
    items += _step_items(root, (rel, data, body), steps_for(role, step), (tracked, seen, cfg))
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
    for p, why in living_work(role, tracked, cfg, sid):
        if p not in seen:
            seen.add(p)
            items.append(_item(root, "living", p, why))
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
    head = git.run(["rev-parse", "--verify", "-q", "HEAD"], str(root), check=False).strip() or None
    return {
        "schema_version": SCHEMA_VERSION,
        "spec": sid,
        "path": rel,
        "role": role,
        "step": step,
        "head": head,
        "spec_hash": _worktree_hash(root, text, data, cfg),
        "items": items,
        "tokens": sum(int(i["tokens"]) for i in items),
    }


def _worktree_hash(root: Path, text: str, data: dict, cfg: config.Config | None) -> str | None:
    """The Spec hash of the working tree, from its one owner (`workitems.Observer.hash_worktree`, as `aidd validate`
    reads it), or None when git cannot say."""
    try:
        return workitems.Observer(root, cfg).hash_worktree(text, data)
    except (git.GitError, OSError, ValueError):
        return None


def _step_items(root: Path, spec: tuple[str, dict, str], steps: list[str], state: tuple[list[str], set[str], config.Config | None]) -> list[dict]:
    """A loop step's own reads (`loop.step_reads`), for each step the pack serves, each once: the test files, the
    Acceptance, the evidence, the linked threat models, and the commands that show the rest (`aidd test`, `aidd gate`,
    the diff's stat). Every path an agent wrote is resolved as the rest are; a command is named, never run."""
    rel, data, body = spec
    tracked, seen, cfg = state
    reads = knowledge.roles()["loop"].get("step_reads") or {}
    items: list[dict] = []
    done: set[str] = set()
    for s in steps:
        for entry in reads.get(s) or []:
            read, why = entry["read"], entry["why"]
            if read in done:
                continue
            done.add(read)
            if read == "tests":
                for pattern in (data.get("tests") or {}).get("files") or []:
                    # `pyproject.toml#tool.pytest` freezes one section of a manifest: the file is read, for that section.
                    path, _, section = str(pattern).partition("#")
                    reason = f"{why}: its `{section}` section" if section else why
                    for p in sorted(x for x in tracked if globs.match_any([path], x)) or [path]:
                        if p not in seen:
                            seen.add(p)
                            items.append(_item(root, "test", p, reason))
            elif read == "acceptance" and (section := documents.raw_section(body, "Acceptance")).strip():
                items.append({"kind": "acceptance", "path": rel, "reason": f"the Acceptance section: {why}", "tokens": tokens(section)})
            elif read == "evidence":
                items.append(_item(root, "evidence", f"{config.EVIDENCE_DIR}/evidence.json", why))
            elif read == "threat_models":
                for p in workitems.threat_models(data, cfg.docs_dir if cfg else "docs"):
                    if p not in seen:
                        seen.add(p)
                        items.append(_item(root, "threat-model", p, why))
            elif read in ("test_command", "gate_command", "diff"):
                command = _step_command(root, read, rel)
                if command:
                    items.append({"kind": "command", "command": command, "reason": why, "tokens": 0})
    return items


def _step_command(root: Path, read: str, rel: str) -> str | None:
    """The command a step runs to see the rest: the tests, the gate, or the diff's stat against the branch's base. The
    Spec's path is an agent's file name, so it is quoted: an agent runs the command as written."""
    if read == "test_command":
        return f"aidd test --spec {shlex.quote(rel)}"
    if read == "gate_command":
        return f"aidd gate --spec {shlex.quote(rel)}"
    base = git.branch_base(str(root))
    return None if base == "HEAD" else f"git diff {base[:12]}...HEAD --stat"


def _one_line(text: object, most: int = 240) -> str:
    """A value from the repository as one line of plain text: no control character, at most `most` characters."""
    flat = " ".join("".join(c if c.isprintable() else " " for c in str(text)).split())
    return flat if len(flat) <= most else flat[: most - 1] + "…"


def context_pack_markdown(pack: dict) -> str:
    head = f"Context for {pack['spec']}" + (f", role {pack['role']}" if pack.get("role") else "") + (f", step {pack['step']}" if pack.get("step") else "")
    lines = [f"{head}: about {pack['tokens']} tokens. Read each by path, when the step needs it; run each command."]
    if pack.get("head"):
        lines.append(
            f"Made at {pack['head'][:12]}" + (f", Spec hash {pack['spec_hash'][:12]}" if pack.get("spec_hash") else "") + ": a later commit makes it stale."
        )
    lines.append("")
    for i in pack["items"]:
        where = f"`{i['command']}`" if i.get("command") else i["path"]
        lines.append(f"- {_one_line(where)} (~{i['tokens']} tokens): {_one_line(i['reason'])}")
    return "\n".join(lines) + "\n"
