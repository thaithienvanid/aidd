"""The trace of a path or a work item: what stands behind it, read on demand from git and aidd's own files and never stored.

For a repository path: the Specs whose Task scope covers it, with their Intent; the open Specs whose scope overlaps it;
the tests, linked docs, and interfaces those Specs name; and the last commits on the path with their work item ids and
`Assisted-by` trailers. For a work item id: the same, over the paths its Tasks scope (an Intent's, over its
Specs'), and the commits that name the id. The route, areas, and levels come from `aidd risk --paths` (the `risk` layer is
above this package, so the command adds them). No model, no index: the same repository gives the same answer.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from aidd import config
from aidd.kernel import documents, git, globs, repo_paths
from aidd.workitems import commit_text, intents, interfaces, status, work_list
from aidd.workitems.backlog import WORK_TYPES
from aidd.workitems.spec_file import WORK_ID

# Bounds: the commits read (default and ceiling), the entries listed per section, and the ids searched for in commit messages.
DEFAULT_COMMITS = 20
MAX_COMMITS = 100
MAX_LISTED = 50
MAX_PATHS = 200
MAX_GREP_IDS = 30

_TYPE_ORDER = {"spec": 0, "intent": 1}


class _Graph:
    """The work items of a repository, by id, with their parents and children."""

    def __init__(self, root: Path, cfg: config.Config | None):
        found, self.unreadable = work_list.read_work(root, cfg)
        self.data = {str(d["id"]): (p, d) for p, d in found if d.get("type") in WORK_TYPES and WORK_ID.fullmatch(str(d.get("id") or ""))}
        items = [d for _, d in self.data.values()]
        self.specs = {i: status.spec_status(d) for i, (_, d) in self.data.items() if d.get("type") == "spec"}
        self.states = intents.intent_statuses(items, self.specs)[0]
        self.children: dict[str, list[str]] = {}
        for i, (_, d) in sorted(self.data.items()):
            if d.get("parent"):
                self.children.setdefault(str(d["parent"]), []).append(i)

    def item_type(self, oid: str) -> str:
        return str(self.data[oid][1]["type"])

    def state(self, oid: str) -> str:
        return self.states.get(oid, self.specs.get(oid, "draft"))

    def ancestors(self, oid: str) -> list[str]:
        out: list[str] = []
        parent = str(self.data[oid][1].get("parent") or "")
        while parent in self.data and parent not in out and parent != oid:
            out.append(parent)
            parent = str(self.data[parent][1].get("parent") or "")
        return out

    def descendants(self, oid: str) -> list[str]:
        out: list[str] = []
        todo = list(self.children.get(oid, []))
        while todo:
            child = todo.pop(0)
            if child not in out and child != oid:
                out.append(child)
                todo.extend(self.children.get(child, []))
        return out

    def tasks(self, oid: str) -> list[dict]:
        tasks = self.data[oid][1].get("tasks")
        return [t for t in tasks if isinstance(t, dict) and t.get("id")] if isinstance(tasks, list) else []

    def scopes(self, oid: str) -> list[str]:
        """A Spec's Task scopes, once each; an Intent's, over the Specs below it."""
        specs = [oid] if self.item_type(oid) == "spec" else [c for c in self.descendants(oid) if self.item_type(c) == "spec"]
        return list(dict.fromkeys(s for i in specs for t in self.tasks(i) for s in _strings(t.get("scope"))))


def _trace_id(data: dict) -> str:
    """What joins an item to the rest of its piece of work: its `trace_id`, else its id in lower case."""
    return str(data.get("trace_id") or str(data.get("id") or "").lower())


def _strings(value: object) -> list[str]:
    return [x for x in value if isinstance(x, str) and x] if isinstance(value, list) else []


def _overlaps(scope: str, subject: list[str]) -> bool:
    return any(globs.overlap(scope, s) for s in subject)


def _repo_path(root: Path, target: str) -> str:
    """The path as the repository writes it. A path outside the repository, by `..`, an absolute path, or a link, is refused."""
    given = Path(target)
    top = root.resolve()
    if given.is_absolute() and given.resolve().is_relative_to(top):
        given = given.resolve().relative_to(top)
    rel = repo_paths.repo_path(given.as_posix()).rstrip("/")
    pure = PurePosixPath(rel)
    try:
        through = (top / rel).resolve()
    except (OSError, RuntimeError):  # a link loop (RuntimeError before Python 3.13): read the path as its text says
        through = top / rel
    outside = pure.is_absolute() or ".." in pure.parts or re.match(r"[A-Za-z]:", rel) or not through.is_relative_to(top)
    if outside or rel in ("", "."):
        raise ValueError(f"{target} is not a path inside the repository: name a file or folder in it, or a work item id (`aidd status src/billing/charge.py`)")
    return rel


def _entry(g: _Graph, oid: str, tasks: list[str] | None = None) -> dict:
    path, d = g.data[oid]
    entry: dict = {"id": oid, "type": g.item_type(oid), "title": str(d.get("title") or ""), "path": path, "status": g.state(oid)}
    if tasks:
        entry["tasks"] = tasks
    return entry


def _ranked(g: _Graph, ids: list[str]) -> list[str]:
    return sorted(dict.fromkeys(ids), key=lambda i: (_TYPE_ORDER.get(g.item_type(i), 3), status.finished(g.state(i)), i))


def _covering(g: _Graph, subject: list[str]) -> dict[str, list[str]]:
    """Each Spec with a Task whose scope overlaps the subject, with those Tasks' ids."""
    out: dict[str, list[str]] = {}
    for oid in sorted(g.specs):
        tasks = [str(t["id"]) for t in g.tasks(oid) if any(_overlaps(s, subject) for s in _strings(t.get("scope")))]
        if tasks:
            out[oid] = tasks
    return out


def _overlapping_specs(g: _Graph, subject: list[str], own: set[str]) -> list[dict]:
    out = []
    for oid in sorted(g.specs):
        if oid in own or status.finished(g.state(oid)):
            continue
        hit = [s for s in dict.fromkeys(s for t in g.tasks(oid) for s in _strings(t.get("scope"))) if _overlaps(s, subject)]
        if hit:
            out.append({k: v for k, v in _entry(g, oid).items() if k != "type"} | {"overlaps": hit})
    return out


def _map(d: dict, key: str) -> dict:
    """`d[key]` when it is a mapping, else an empty one: a Spec of the wrong shape is `aidd validate`'s finding, never a crash here."""
    v = d.get(key)
    return v if isinstance(v, dict) else {}


def _tests(cfg: config.Config | None, g: _Graph, specs: list[str], subject: list[str]) -> dict:
    def runs(when_changed: list[str]) -> bool:
        return not when_changed or any(globs.match_any([w], s, fold_case=True) or globs.overlap(w, s) for w in when_changed for s in subject)

    commands: list[dict] = []
    for source, tests in [("config", ((cfg or config.EMPTY).tests))] + [(i, _map(g.data[i][1], "tests").get("commands") or []) for i in specs]:
        for t in tests if isinstance(tests, list) else []:
            when = _strings(t.get("when_changed")) if isinstance(t, dict) else []
            if isinstance(t, dict) and isinstance(t.get("command"), list) and (source != "config" or runs(when)):
                commands.append({"source": source, "command": [str(a) for a in t["command"]], "when_changed": when})
    files = [{"spec": i, "files": f} for i in specs if (f := _strings(_map(g.data[i][1], "tests").get("files")))]
    return {"commands": commands, "files": files}


def _docs(g: _Graph, specs: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in specs:
        d = g.data[i][1]
        out += [{"type": "design", "path": p, "spec": i} for p in _strings(_map(d, "design").get("files"))]
        out += [{"type": "adr", "path": p, "spec": i} for p in _strings(d.get("adrs"))]
        linked = d.get("docs")
        out += [
            {"type": str(x.get("type") or "doc"), "path": x["path"], "spec": i}
            for x in (linked if isinstance(linked, list) else [])
            if isinstance(x, dict) and isinstance(x.get("path"), str)
        ]
    return [dict(t) for t in dict.fromkeys(tuple(e.items()) for e in out)]


def _interfaces(g: _Graph, specs: list[str]) -> list[dict]:
    named = sorted({n for i in specs for key in ("provides", "consumes") for n in interfaces.interface_names(g.data[i][1], key)})
    return [
        {"name": n, "provided_by": [i for i in sorted(g.specs) if n in interfaces.interface_names(g.data[i][1], "provides")]}
        | {"consumed_by": [i for i in sorted(g.specs) if n in interfaces.interface_names(g.data[i][1], "consumes")]}
        for n in named
    ]


def _commits(root: Path, args: list[str], limit: int, known: set[str]) -> tuple[list[dict], bool]:
    """The last `limit` commits `git log <args>` lists, each with the work item ids and `Assisted-by` values its message names."""
    records = git.log_fields(["-n", str(limit + 1), *args], ["%H", "%aI"], str(root), check=False)
    shas = [r[0] for r in records[:limit]]
    bodies = git.messages(shas, str(root)) if shas else {}
    out = []
    for sha, authored_at in records[:limit]:
        text = bodies.get(sha, "")
        out.append(
            {"sha": sha, "authored_at": authored_at, "work_ids": commit_text.work_ids_in(text, known), "assisted_by": commit_text.assisted_by_values(text)}
        )
    return out, len(records) > limit


def _pathspec(subject: list[str]) -> list[str]:
    return [f":(glob){s}" if globs.is_pattern(s) else f":(literal){s}" for s in subject]


def trace(root: Path, cfg: config.Config | None, target: str, *, commits: int = DEFAULT_COMMITS, route=None) -> dict:
    """What stands behind `target`, a repository path or a work item id (schemas/trace.schema.json, without its `risk` or its
    version field). `commits` is how many of the last commits to read, at most MAX_COMMITS. `route`, given the full
    subject, returns its `risk` before any section is cut, so the route never misses a path past MAX_PATHS."""
    if not 1 <= commits <= MAX_COMMITS:
        raise ValueError(f"--commits is a number from 1 to {MAX_COMMITS}, not {commits}")
    g = _Graph(root, cfg)
    is_item = target in g.data
    if not is_item and WORK_ID.fullmatch(target) and not (root / target).exists():
        raise ValueError(f"no Spec or Intent has the id {target}; `aidd status` lists the open work")
    own: set[str] = set()
    if is_item:
        subject = g.scopes(target)
        own = {target, *g.descendants(target)}
        covering = {i: [str(t["id"]) for t in g.tasks(i)] for i in sorted(own) if g.item_type(i) == "spec"}
        work_ids = [target, *g.ancestors(target), *sorted(own - {target})]
        tid = _trace_id(g.data[target][1])
        # The work items that share its trace_id are one piece of work with it, across Intents or repositories' Specs.
        work_ids += [i for i, (_, d) in sorted(g.data.items()) if tid and _trace_id(d) == tid and i not in own and i not in work_ids]
        named = [target, *(i for i in sorted(own) if g.item_type(i) == "spec")]
        ids = named[:MAX_GREP_IDS]
        log_args = ["--extended-regexp", *(f"--grep=(^|[^A-Za-z0-9-]){i}([^0-9]|$)" for i in ids)]
    else:
        subject = [_repo_path(root, target)]
        covering = _covering(g, subject)
        work_ids = [*covering, *(a for i in covering for a in g.ancestors(i))]
        log_args = ["--", *_pathspec(subject)]
    specs = sorted(covering)
    work = [_entry(g, i, covering.get(i)) for i in _ranked(g, work_ids)]
    answer: dict = {
        "subject": {"type": "work_item" if is_item else "path", "value": target},
        "paths": subject,
        "work": work,
        "overlapping_specs": _overlapping_specs(g, subject, own),
        "tests": _tests(cfg, g, specs, subject),
        "docs": _docs(g, specs),
        "interfaces": _interfaces(g, specs),
    }
    if route and subject:
        answer["risk"] = route(subject)
    answer["commits"], more = _commits(root, log_args, commits, set(g.data))
    cut = [k for k in ("work", "overlapping_specs", "docs", "interfaces") if len(answer[k]) > MAX_LISTED]
    for k in cut:
        answer[k] = answer[k][:MAX_LISTED]
    if len(subject) > MAX_PATHS:
        answer["paths"] = subject[:MAX_PATHS]
        cut.append("paths")
    for k in ("commands", "files"):
        if len(answer["tests"][k]) > MAX_LISTED:
            answer["tests"][k] = answer["tests"][k][:MAX_LISTED]
            cut.append(f"tests.{k}")
    if more or (is_item and len(named) > MAX_GREP_IDS):
        cut.append("commits")
    if cut:
        answer["truncated"] = sorted(cut)
    if g.unreadable:
        answer["unreadable"] = [u["path"] for u in g.unreadable]
    return answer


def _line(text: object) -> str:
    """A value from a file or a commit as one terminal line: no line break, control, or bidi character can forge a line."""
    return documents.one_line(text, 200)


def trace_text(answer: dict) -> str:
    """What stands behind a path or a work item, as a person reads it: one block per section that holds something."""
    sub = answer["subject"]
    lines = [f"{_line(sub['value'])} ({'work item' if sub['type'] == 'work_item' else 'path'})"]
    if sub["type"] == "work_item":
        lines.append("  scope: " + (_line(", ".join(answer["paths"])) or "no Task scope"))
    if not answer["work"]:
        lines.append("work: no Spec's Task scope covers it")
    for w in answer["work"]:
        tasks = f"  tasks {_line(', '.join(w['tasks']))}" if w.get("tasks") else ""
        lines.append(f"work: {w['id']} {_line(w['title'])} ({w['type']}): {w['status']}  {_line(w['path'])}{tasks}")
    lines += [f"overlapping: {f['id']} {_line(f['title'])}: {f['status']}  overlaps {_line(', '.join(f['overlaps']))}" for f in answer["overlapping_specs"]]
    lines += [
        f"test: {t['source']}: {_line(' '.join(t['command']))}" + (f"  when {_line(', '.join(t['when_changed']))}" if t["when_changed"] else "")
        for t in answer["tests"]["commands"]
    ]
    lines += [f"test files: {t['spec']}: {_line(', '.join(t['files']))}" for t in answer["tests"]["files"]]
    lines += [f"doc: {_line(d['type'])} {_line(d['path'])} ({d['spec']})" for d in answer["docs"]]
    lines += [
        f"interface: {_line(i['name'])}: provided by {_line(', '.join(i['provided_by'])) or 'no Spec here'}; "
        f"consumed by {_line(', '.join(i['consumed_by'])) or 'no Spec here'}"
        for i in answer["interfaces"]
    ]
    if answer.get("risk"):
        r = answer["risk"]
        areas = ", ".join(a["area"] for a in r["areas"]) or "no area"
        lines.append(
            f"risk: route {r['route']} ({config.lane_words().get(r['lane'], r['lane'])}), {areas}; edit: {r['edit']['level']}"
            + (f" ({r['edit']['rule']})" if r["edit"]["rule"] else "")
        )
    for c in answer["commits"]:
        lines.append(
            f"commit: {c['sha'][:10]} {c['authored_at'][:10]}"
            + "".join(f"  {x}" for x in c["work_ids"])
            + "".join(f"  Assisted-by: {_line(a)}" for a in c["assisted_by"])
        )
    if not answer["commits"]:
        lines.append("commits: none on it yet")
    if answer.get("truncated"):
        lines.append(
            f"cut at {MAX_LISTED} entries ({MAX_PATHS} paths) or the commit limit: {', '.join(answer['truncated'])}; name a narrower path or a smaller --commits"
        )
    lines += [f"unreadable: {_line(p)}; {work_list.fix_step(p)}" for p in answer.get("unreadable", [])]
    return "\n".join(lines) + "\n"
