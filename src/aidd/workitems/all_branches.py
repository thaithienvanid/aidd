"""The open work in all branches of the clone, for `aidd status --all-branches`: each worktree as its files stand
now, and each local and fetched branch with no worktree as its tip commit holds them. Each of these is a place:
`worktree:<path>`, `branch:<name>`, or `remote:<remote>/<name>`.

Each place becomes rows of the index (aidd.kernel.index) in the clone's git folder, `.git/aidd/index.sqlite`, so a
place is read again only when its stamp changes. A worktree's stamp is its work-item files' names, sizes, times, and
inodes; a branch's is its tip. Both also hold the folders the config names and ROW_FORMAT, so another config or
another aidd never reads rows it did not write. A fetched branch counts as of the person's last `git fetch`. The index
is a cache: without it, the places are read directly, with the same answer.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from aidd import config
from aidd.kernel import git, index
from aidd.workitems import objects, work_list

# The shape of a place's rows: a change to how rows are built raises it, so no index holds rows of the old shape.
ROW_FORMAT = 1


def _folders(cfg: config.Config | None) -> tuple[str, str]:
    return (cfg.specs_dir, cfg.proposals_dir) if cfg else ("specs", "proposals")


def _stamp(cfg: config.Config | None, what: str) -> str:
    return hashlib.sha256("\0".join((str(ROW_FORMAT), *_folders(cfg), what)).encode()).hexdigest()


def _is_work_file(rel: str, specs_dir: str, proposals_dir: str) -> bool:
    parts = rel.split("/")
    if rel.startswith(proposals_dir.rstrip("/") + "/") and len(parts) == len(proposals_dir.rstrip("/").split("/")) + 2:
        return parts[-1] == "proposal.md"
    return rel.startswith(specs_dir.rstrip("/") + "/") and rel.endswith(".md") and parts[-1].lower() != "readme.md"


def _rows(found: list[tuple[str, dict]], unreadable: list[dict]) -> list[index.Entry]:
    rows = [index.Entry(str(data.get("type")), rel, None, None, data) for rel, data in found]
    return rows + [index.Entry("unreadable", u["path"], None, None, {"error": u["error"]}) for u in unreadable]


def _worktree_place(top: Path, cfg: config.Config | None) -> tuple[str, Callable[[], list[index.Entry]]]:
    specs_dir, proposals_dir = _folders(cfg)
    stamp = hashlib.sha256()
    for folder in (top / specs_dir, top / proposals_dir):
        for p in sorted(folder.rglob("*.md")) if folder.is_dir() else ():
            rel = p.relative_to(top).as_posix()
            if _is_work_file(rel, specs_dir, proposals_dir):
                st = p.stat()
                stamp.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\0{st.st_ctime_ns}\0{st.st_ino}\n".encode())
    return _stamp(cfg, stamp.hexdigest()), lambda: _rows(*work_list.read_work(top, cfg))


def _branch_rows(root: str, commit: str, cfg: config.Config | None) -> list[index.Entry]:
    specs_dir, proposals_dir = _folders(cfg)
    listed = git.ls_tree(commit, root, paths=[specs_dir, proposals_dir])  # by the commit listed, so a prune between is harmless
    tree = {rel: sha for rel, sha in listed.items() if _is_work_file(rel, specs_dir, proposals_dir)}
    blobs = git.raw_objects(sorted(set(tree.values())), root)
    texts = []
    for rel, sha in sorted(tree.items()):
        text = blobs.get(sha, b"").decode("utf-8-sig", errors="replace")
        found = objects.front_line_in(iter(text.splitlines(keepends=True)))
        is_proposal = rel.endswith("/proposal.md") and rel.startswith(proposals_dir.rstrip("/") + "/")
        if is_proposal or (found and found[0] and found[1] not in objects.DOCUMENT_TYPES):
            texts.append((rel, text))
    return _rows(*work_list.parse_work(texts))


def places(root: Path, cfg: config.Config | None) -> dict[str, tuple[str, Callable[[], list[index.Entry]]]]:
    """Every place of the clone by name, with its stamp and its loader. A branch checked out in a worktree is read
    from the worktree's files; a worktree whose folder is gone counts as no worktree, so its branch is read from its tip."""
    out: dict[str, tuple[str, Callable[[], list[index.Entry]]]] = {}
    checked_out: set[str] = set()
    block: dict[str, str] = {}
    for line in git.run(["worktree", "list", "--porcelain"], str(root)).splitlines() + [""]:
        key, _, value = line.partition(" ")
        if line:
            block[key] = value
            continue
        path = block.get("worktree", "")
        if path and "bare" not in block and "prunable" not in block and Path(path).is_dir():
            out[f"worktree:{path}"] = _worktree_place(Path(path), cfg)
            if "branch" in block:
                checked_out.add(block["branch"])
        block = {}
    refs = git.run(["for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes"], str(root))
    for line in refs.splitlines():
        ref, _, sha = line.partition(" ")
        if ref in checked_out or ref.endswith("/HEAD"):
            continue
        name = f"branch:{ref.removeprefix('refs/heads/')}" if ref.startswith("refs/heads/") else f"remote:{ref.removeprefix('refs/remotes/')}"
        out[name] = (_stamp(cfg, sha), functools.partial(_branch_rows, str(root), sha, cfg))
    return out


def index_path(root: Path) -> Path:
    """The index of the clone `root` is in: `.git/aidd/index.sqlite`, which every worktree shares."""
    return Path(git.common_dir(str(root))) / "aidd" / "index.sqlite"


def all_branches_work(
    root: Path,
    cfg: config.Config | None,
    *,
    today: dt.date | None = None,
    include_done: bool = False,
    use_index: bool = True,
    keep: work_list.Keep | None = None,
) -> dict:
    """The open work of every place (schemas/status.schema.json, without its version field): one item for each version
    of a work item, with the places that hold it, so two places that differ show both, never a silent pick. With
    `keep`, only the items it keeps, as `work_list.open_items` reads it."""
    found = places(root, cfg)
    if use_index:
        by_place = index.read_through(index_path(root), found)
    else:
        by_place = {name: sorted(load(), key=lambda e: (e.id, e.type)) for name, (_, load) in found.items()}
    merged: dict[str, dict] = {}
    due: dict[str, dict] = {}
    unreadable: list[dict] = []
    for name in sorted(by_place):
        rows = by_place[name]
        items = [(e.id, e.data) for e in rows if e.type != "unreadable"]
        bad = [{"path": e.id, "error": e.data["error"]} for e in rows if e.type == "unreadable"]
        answer = work_list.open_items(items, bad, cfg, today=today, include_done=include_done, keep=keep)
        for item in answer["items"]:
            merged.setdefault(json.dumps(item, sort_keys=True), {**item, "places": []})["places"].append(name)
        due.update((json.dumps(d, sort_keys=True), d) for d in answer["due"])
        unreadable += [{**u, "place": name} for u in answer.get("unreadable", [])]
    out: dict = {"items": sorted(merged.values(), key=lambda i: (str(i["id"]), i["places"])), "due": [due[k] for k in sorted(due)]}
    if unreadable:
        out["unreadable"] = unreadable
    if not out["items"] and not out["due"] and not unreadable:
        out["next"] = work_list.open_items([], [], cfg)["next"]
    return out
