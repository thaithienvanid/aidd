"""Work items as a team tracks them: status groups, triage, typed relations, labels, the why chain, and the handoff note.

A tracker (Jira, Linear, Plane) is optional: the Spec, Epic, and Initiative files in git are the record, and this
module reads the few fields that turn them into a backlog a person can steer. None of it is evidence. The gate never
imports this module, and the Spec hash ignores every field here (`model.VOLATILE_SPEC_KEYS`) and every
handoff block (`model.strip_handoffs`), so bookkeeping never voids an approval.

- **Status group**: each status of every kind falls into one of five groups (backlog, unstarted, started, completed,
  cancelled), from `x-groups` in the schemas, so any board mirrors any object by its group. The status itself is
  derived (`state.py`); these functions take it as given.
- **Triage**: a Spec an agent suggested (`suggested_by = "agent:<role>"`, a role in `[agents] proactive_roles`) stays a
  draft until a person records `triage` (accepted, declined, or snoozed until a date). A duplicate is a relation.
- **Relations**: `relations = [{ type = "blocked_by", id = "SPEC-12" }]` on a Spec, Epic, or Initiative. `aidd
  validate` checks the targets exist and that blocks form no cycle; `aidd assess` and `aidd list` show blocked work as blocked.
- **Handoff note**: a fenced ```aidd-handoff block of TOML (done, next, needs, stopped_at, and optional spend and
  status) that an agent writes into the Spec or the PR/MR when it stops. `aidd assess` and `aidd list` read the latest one in the Spec:
  `next` names the role that takes the work, and `needs` asks a person, while the status it was written in holds.
"""

from __future__ import annotations

import datetime as dt
import functools
import re
from collections.abc import Callable
from pathlib import Path

from . import config as cfgmod
from . import gitutil, model, resources

GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")
WORK_KINDS = ("spec", "epic", "initiative")
# Approvals that a handoff note must not name as its `next`. The Approver inbox follows the derived status, so a note
# names the role that takes the work, and `aidd validate` warns about one of these.
APPROVAL_STEPS = ("spec-approval", "merge-approval")
HANDOFF_KEYS = ("done", "next", "needs", "stopped_at")
HANDOFF_OPTIONAL = ("spend", "status")
HANDOFF_FENCE = re.compile(r"^```aidd-handoff[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)
MAX_OBJECTS = 5000  # objects read at a ref; a Specs folder larger than this is read in part, and says so


@functools.cache
def _groups() -> dict[str, dict[str, str]]:
    common = resources.load_json("common.schema.json")["$defs"]
    container = dict(common["container_status"]["x-groups"])
    return {
        "spec": dict(common["status"]["x-groups"]),
        "epic": container,
        "initiative": container,
        "proposal": dict(resources.load_json("proposal.schema.json")["properties"]["status"]["x-groups"]),
    }


def group(data: dict, status: str | None = None) -> str | None:
    """The status group of a Spec, Epic, Initiative, or proposal in `status` (its derived status; the stored one when
    not given); None for another kind or an unknown status."""
    kind = str(data.get("kind"))
    default = {"spec": "draft", "epic": "draft", "initiative": "draft"}.get(kind)
    return _groups().get(kind, {}).get(str(status or data.get("status") or default))


def is_duplicate(data: dict) -> bool:
    """This item repeats another (`duplicates`), which carries the work."""
    return any(r["type"] == "duplicates" for r in relations(data))


def bots_of(cfg: cfgmod.Config | None) -> set[str]:
    return {str(b).lower().lstrip("@") for b in (cfg.get("identities", "bots", default=[]) if cfg else [])}


def is_agent(identity: object, bots: set[str] | frozenset[str] = frozenset()) -> bool:
    """An agent (`agent:<role>`), a configured agent account, or a platform bot: never a person who decides."""
    s = str(identity or "").strip()
    return s.startswith("agent:") or s.lower().lstrip("@") in bots or cfgmod.is_bot(s)


def my_identities(root: Path) -> set[str]:
    """Who runs this command, in every form a Spec may name them: git's user.email and user.name, and the GitHub login
    from `git config github.user` or gh's stored user. Local configuration only; a team (`@org/team`) is not resolved."""
    from . import repo

    email = gitutil.config_value("user.email", str(root)).lower()
    name = gitutil.config_value("user.name", str(root)).lower()
    login = (repo.operator_login(root) or "").lower()
    return {x for x in (email, email and f"email:{email}", name, login, login and f"@{login}") if x}


def is_me(identity: object, mine: set[str]) -> bool:
    s = str(identity or "").strip().lower()
    return bool(s) and (s in mine or s.lstrip("@") in mine)


def triage_errors(data: dict, bots: set[str] | frozenset[str] = frozenset(), proactive: list[str] | None = None) -> list[str]:
    """What `aidd validate` refuses: work an agent suggested moving past draft without a person's triage, a triage an
    agent recorded, a stored status a declined triage contradicts, and a proposal from an agent role outside
    `[agents] proactive_roles` (`proactive`; None skips that check)."""
    if data.get("kind") != "spec":
        return []
    t = data.get("triage") or {}
    errs = []
    if t.get("by") and is_agent(t["by"], bots):
        errs.append(f"triage.by {t['by']} is an agent account; a person triages suggested work")
    suggester = str(data.get("suggested_by") or "")
    if proactive is not None and suggester.startswith("agent:") and suggester.split(":", 1)[1] not in proactive:
        allowed = ", ".join(proactive) or "none"
        errs.append(f"{suggester} may not suggest work: [agents] proactive_roles names {allowed}; only those roles suggest work nobody asked for")
    raw = data.get("status")
    status = str(raw or "draft")
    if t.get("decision") == "declined" and raw is not None and raw not in ("cancelled", "draft"):
        errs.append(f'status {status} needs triage.decision = "accepted"; the recorded decision is declined, which cancels the work')
    elif t.get("decision") == "declined" and raw == "draft":
        errs.append('status draft contradicts triage.decision = "declined", which cancels the work: write status = "cancelled", or remove status')
    if not suggester or not is_agent(suggester, bots) or status in ("draft", "cancelled") or t.get("decision") == "declined":
        return errs
    if not t:
        errs.append(
            f"status {status} needs triage: {suggester} suggested this work, and a person decides whether it goes ahead "
            '(triage = { decision = "accepted", by = "@you", on = "YYYY-MM-DD" })'
        )
    elif t.get("decision") != "accepted":
        errs.append(f'status {status} needs triage.decision = "accepted"; the recorded decision is {t.get("decision")}')
    return errs


def owner_errors(data: dict, bots: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """An owner, and a feature flag's owner, is a person: never an agent or an agent account."""
    owner = data.get("owner")
    errs = [f"owner {owner} is an agent account; the owner is the person driving the work"] if owner and is_agent(owner, bots) else []
    for flag in (data.get("flags") or []) if data.get("kind") == "spec" else []:
        if isinstance(flag, dict) and flag.get("owner") and is_agent(flag["owner"], bots):
            errs.append(f"flag {flag.get('name')}: owner {flag['owner']} is an agent account; a person decides when a flag flips and sees it removed")
    return errs


def triage_state(data: dict, bots: set[str] | frozenset[str], today: dt.date) -> str | None:
    """`needed` when a person must triage the Spec now, `hidden` when it is out of `aidd list` (declined, or snoozed
    until a later date), and None otherwise."""
    t = data.get("triage") or {}
    decision = t.get("decision")
    if decision == "declined":
        return "hidden"
    if decision == "snoozed":
        return "hidden" if str(t.get("until") or "") > today.isoformat() else "needed"
    suggester = data.get("suggested_by")
    if not suggester or not is_agent(suggester, bots) or (decision == "accepted" and not is_agent(t.get("by"), bots)):
        return None
    return "needed"


def relations(data: dict) -> list[dict]:
    return [r for r in data.get("relations") or [] if isinstance(r, dict) and r.get("type") and r.get("id")]


def index(objects: list[tuple[str, dict]]) -> dict[str, dict]:
    """Spec, Epic, and Initiative data by id."""
    return {str(d["id"]): d for _, d in objects if d.get("kind") in WORK_KINDS and d.get("id")}


def _cycle(edges: dict[str, set[str]]) -> list[str]:
    """One cycle in a directed graph, as the ids along it, or [] when there is none."""
    state: dict[str, int] = {}
    for start in sorted(edges):
        if state.get(start):
            continue
        stack: list[tuple[str, list[str]]] = [(start, sorted(edges.get(start, ())))]
        path = [start]
        state[start] = 1
        while stack:
            node, todo = stack[-1]
            if not todo:
                stack.pop()
                path.pop()
                state[node] = 2
                continue
            nxt = todo.pop(0)
            if state.get(nxt) == 1:
                return path[path.index(nxt) :]
            if not state.get(nxt):
                state[nxt] = 1
                path.append(nxt)
                stack.append((nxt, sorted(edges.get(nxt, ()))))
    return []


def relation_errors(objects: list[tuple[str, dict]]) -> list[str]:
    """Relations that point nowhere or at themselves, and blocks that form a cycle."""
    where = {str(d["id"]): p for p, d in objects if d.get("kind") in WORK_KINDS and d.get("id")}
    errs: list[str] = []
    edges: dict[str, set[str]] = {}
    for p, d in objects:
        if d.get("kind") not in WORK_KINDS:
            continue
        me = str(d.get("id"))
        for kind, other in [(r["type"], str(r["id"])) for r in relations(d)]:
            if other == me:
                errs.append(f"{p}: {kind} {other} points at itself")
            elif other not in where:
                errs.append(f"{p}: {kind} {other}: no Spec, Epic, or Initiative in the Specs folder has that id")
            elif kind == "blocks":
                edges.setdefault(me, set()).add(other)
            elif kind == "blocked_by":
                edges.setdefault(other, set()).add(me)
    cycle = _cycle(edges)
    if cycle:
        errs.append(f"{where[cycle[0]]}: blocks and blocked_by form a cycle ({' -> '.join([*cycle, cycle[0]])}); nothing in it can ever start")
    return errs


def waiting_on(data: dict, idx: dict[str, dict], lets_go: Callable[[str], bool]) -> list[str]:
    """The items this one still waits for: its own blocked_by, and every item that says it blocks this one, unless
    `lets_go(id)` (its derived status landed or ended the work) or it is a duplicate. An id not in the Specs folder
    counts as unfinished: nothing shows it finished."""
    me = str(data.get("id"))
    ids = [str(r["id"]) for r in relations(data) if r["type"] == "blocked_by"]
    ids += [oid for oid, other in idx.items() if oid != me and any(r["type"] == "blocks" and str(r["id"]) == me for r in relations(other))]
    return [i for i in dict.fromkeys(ids) if i not in idx or not (lets_go(i) or is_duplicate(idx[i]))]


def why(data: dict, idx: dict[str, dict], cfg: cfgmod.Config | None, progress: dict[str, tuple[int, int]] | None = None) -> list[dict]:
    """Why this Spec matters, widest first: the mission, the goal, its Initiative and Epic (with `progress`, their
    children finished of all, as "n/m"), and its own hypothesis (or, once measured, its outcome). Each link is
    {kind, id?, text, progress?}; a link with nothing written is left out."""
    chain: list[dict] = []
    for key in ("mission", "goal"):
        text = cfg.get(key) if cfg else None
        if text:
            chain.append({"kind": key, "text": str(text)})
    parents: list[dict] = []
    seen: set[str] = set()
    parent = data.get("parent")
    while parent and str(parent) not in seen and len(parents) < 8:
        seen.add(str(parent))
        found = idx.get(str(parent))
        if found is None:
            parents.append({"kind": "parent", "id": str(parent), "text": "not in the Specs folder"})
            break
        link = {"kind": found.get("kind"), "id": str(parent), "text": str(found.get("goal") or found.get("title") or "")}
        if progress and str(parent) in progress:
            link["progress"] = "{}/{}".format(*progress[str(parent)])
        parents.append(link)
        parent = found.get("parent")
    chain += reversed(parents)
    result = (data.get("outcome") or {}).get("result")
    if data.get("hypothesis") or result:
        text = str(data.get("hypothesis") or "")
        if result:
            text = f"{text} (outcome: {result})" if text else f"outcome: {result}"
        chain.append({"kind": "spec", "id": str(data.get("id")), "text": text})
    return chain


def why_text(chain: list[dict]) -> str:
    return " → ".join(f"{link.get('id') or link['kind']}{' (' + link['progress'] + ')' if link.get('progress') else ''}: {link['text']}" for link in chain)


@functools.cache
def role_ids() -> frozenset[str]:
    return frozenset(resources.load_json("roles.json")["roles"])


def handoff_blocks(text: str) -> list[tuple[dict | None, str]]:
    """Every ```aidd-handoff block in a document, in order: (its TOML as a dict, or None, and the parse error)."""
    out: list[tuple[dict | None, str]] = []
    for m in HANDOFF_FENCE.finditer(text):
        try:
            out.append((model.parse_toml(m.group(1), "aidd-handoff block"), ""))
        except model.ModelError as exc:
            out.append((None, str(exc)))
    return out


def latest_handoff(text: str) -> dict | None:
    """The last well-formed handoff note in the document, or None."""
    notes = [h for h, _ in handoff_blocks(text) if h is not None and isinstance(h.get("next"), str)]
    return notes[-1] if notes else None


def needs(note: dict | None, status: str | None = None) -> list[str]:
    """What the note asks a person for; "none" and blanks ask for nothing. A note that records the `status` it was
    written in asks only while the item is still in it: once the work moved on, the question is stale."""
    if note and status and isinstance(note.get("status"), str) and note["status"] != status:
        return []
    raw = (note or {}).get("needs")
    items = raw if isinstance(raw, list) else [raw]
    return [str(x).strip() for x in items if str(x or "").strip() and str(x).strip().lower() not in ("none", "nothing", "n/a", "-")]


def handoff_warnings(where: str, text: str) -> list[str]:
    """`aidd validate` warnings for handoff notes a reader cannot use: bad TOML, a missing key, a `next` that is not
    a role (an approval is not a role: the Approver inbox follows the derived status), or an unknown `status`."""
    from .state import SPEC

    out = []
    for i, (note, err) in enumerate(handoff_blocks(text), 1):
        if note is None:
            out.append(f"warning: {where}: handoff note {i} is not TOML ({err.split(': ', 1)[-1]})")
            continue
        missing = [k for k in HANDOFF_KEYS if k not in note]
        unknown = sorted(set(note) - set(HANDOFF_KEYS) - set(HANDOFF_OPTIONAL))
        if missing:
            out.append(f"warning: {where}: handoff note {i} has no {', '.join(missing)}")
        if unknown:
            out.append(f"warning: {where}: handoff note {i} has keys aidd does not read: {', '.join(unknown)}")
        nxt = note.get("next")
        if nxt in APPROVAL_STEPS:
            out.append(
                f"warning: {where}: handoff note {i}: next {nxt!r} is an approval, not a role. aidd puts the Spec in the Approver "
                "inbox from its derived status. Name the role that takes the work next"
            )
        elif "next" in note and (not isinstance(nxt, str) or nxt not in role_ids()):
            out.append(f"warning: {where}: handoff note {i}: next {nxt!r} is not a role")
        if "status" in note and note["status"] not in SPEC:
            out.append(f"warning: {where}: handoff note {i}: status {note['status']!r} is not a Spec status ({', '.join(SPEC)})")
    return out


def config_at(root: Path | None) -> cfgmod.Config | None:
    """The repository's config, read offline; None when it is missing or unreadable."""
    if root is None or not (root / cfgmod.CONFIG_PATH).is_file():
        return None

    def offline(url: str) -> bytes:
        raise cfgmod.ConfigError(f"not fetched: {url}")

    try:
        return cfgmod.load_file(cfgmod.CONFIG_PATH, str(root), fetch=offline)
    except Exception:  # noqa: BLE001  # an unreadable config is `aidd validate`'s own finding; agent: ids still count
        return None


def validate(path: Path, text: str, data: dict, root: Path | None) -> list[str]:
    """One work item's triage and owner errors and handoff warnings, for `aidd validate`."""
    from .owners import proactive_roles

    errs: list[str] = []
    cfg = config_at(root)
    bots = bots_of(cfg)
    if data.get("kind") == "spec" and (data.get("suggested_by") or data.get("triage")):
        proactive = proactive_roles(cfg) if cfg is not None or root is not None else None
        errs += [f"{path}: {e}" for e in triage_errors(data, bots, proactive)]
        t = data.get("triage")
        if isinstance(t, dict) and t.get("decision") == "declined" and not t.get("reason"):
            errs.append(f"warning: {path}: triage declined with no triage.reason; say why in one sentence, so a later triage of the same idea reads it first")
    errs += [f"{path}: {e}" for e in owner_errors(data, bots)]
    return errs + handoff_warnings(str(path), text)


def objects_at(root: Path, ref: str, specs_dir: str) -> tuple[list[tuple[str, dict, str, str]], bool]:
    """Every aidd object under `specs_dir` at `ref` (not only this branch's): (path, front matter, body, text), and
    whether the read stopped at MAX_OBJECTS. One `git cat-file --batch` reads them all."""
    listed = gitutil.run(["ls-tree", "-r", "-z", "--name-only", ref, "--", specs_dir], str(root), check=False).split("\0")
    paths = [p for p in listed if p.endswith(".md") and Path(p).name.lower() != "readme.md"]
    capped = len(paths) > MAX_OBJECTS
    return read_at(root, ref, paths[:MAX_OBJECTS]), capped


def read_at(root: Path, ref: str, paths: list[str]) -> list[tuple[str, dict, str, str]]:
    """The aidd objects among `paths` as `ref` holds them: (path, front matter, body, text). One `git cat-file`."""
    if not paths:
        return []
    proc = gitutil._git(["cat-file", "--batch"], str(root), input="".join(f"{ref}:{p}\n" for p in paths))
    raw, pos, out = proc.stdout, 0, []
    for p in paths:
        nl = raw.find(b"\n", pos)
        if nl < 0:
            break
        header = raw[pos:nl].split()
        pos = nl + 1
        if len(header) != 3 or header[1] != b"blob":
            continue
        size = int(header[2])
        text = raw[pos : pos + size].decode("utf-8", errors="replace")
        pos += size + 1
        if not text.lstrip("﻿").startswith("+++"):
            continue
        try:
            data, body = model.split_front_matter(text, p)
        except model.ModelError:
            continue
        out.append((p, data, body, text))
    return out


def authors(root: Path, ref: str, specs_dir: str) -> dict[str, set[str]]:
    """Who added each file under `specs_dir`, as of `ref`: its first commit's author email and name, lowercased."""
    # Each commit is NUL, then its id, author email, and author name each ended by NUL, then the file names. Neither
    # field can hold a NUL, so an author name cannot add a commit or claim another's files.
    log = gitutil.run(["log", "--diff-filter=A", "--format=%x00%H%x00%ae%x00%an%x00", "--name-only", ref, "--", specs_dir], str(root), check=False)
    out: dict[str, set[str]] = {}
    tokens = log.split("\0")[1:]
    for i in range(0, len(tokens) - 3, 4):
        sha, email, name, names = tokens[i : i + 4]
        if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", sha):
            break
        for p in names.split("\n"):
            if p.strip():
                out[p.strip()] = {x for x in (email.lower(), f"email:{email.lower()}", name.lower()) if x and x != "email:"}
    return out
