"""A work item's folder: everything about an Initiative, an Epic, or a Spec lives beside its file, in `specs/<ID>/`.

`specs/SPEC-12.md` is the work item. `specs/SPEC-12/` holds what it links and what was decided for it: its linked
documents (`<kind>-<topic>.md`, such as `tech-spec-checkout.md`), its design files (`design/`, frozen by Spec
approval when `design.files` names them), and its explorations (`explore/<slug>/`, each with `exploration.md`).
`docs/` holds the project's official docs: the ADRs, the architecture overview, the runbooks, the glossary.

`item_files` lists a folder for `aidd list --json`, so a reader such as the aidd-mods pane shows what an item holds
without knowing where the folder is.
"""

from __future__ import annotations

from pathlib import Path

from aidd import config
from aidd.kernel import documents

DESIGN_FOLDER = "design"
EXPLORE_FOLDER = "explore"
EXPLORATION_FILE = "exploration.md"
MAX_FILES = 20  # enough for one item; a longer folder ends with a count


def doc_kind(name: str) -> str:
    """A linked document's kind from its file name (`tech-spec-checkout.md` is a `tech-spec`); `doc` when it names none."""
    return next((k for k in sorted(config.DOC_KINDS, key=len, reverse=True) if name.startswith(f"{k}-")), "doc")


def _exploration(folder: Path, rel: str) -> dict:
    entry: dict = {"path": rel, "kind": "exploration"}
    try:
        data, _ = documents.split_front_matter((folder / EXPLORATION_FILE).read_text(encoding="utf-8"), rel)
    except (OSError, documents.DocumentError):
        return entry
    for key in ("question", "status", "owner"):
        if isinstance(data.get(key), str) and data[key]:
            entry[key] = data[key]
    return entry


def item_files(root: Path, specs_dir: str, item_id: str) -> list[dict]:
    """What the work item's folder holds, as `{path, kind}` entries: each linked document (its kind), the design folder,
    each exploration (with its question, its status, open or decided, and its owner), and any other folder. At most
    MAX_FILES entries; then one `{kind: "more", count}`."""
    folder = root / specs_dir / item_id
    if not item_id or not folder.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(folder.iterdir(), key=lambda q: (q.is_dir(), q.name)):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not p.name.startswith("."):
            out.append({"path": rel, "kind": doc_kind(p.name)})
        elif p.is_dir() and p.name == DESIGN_FOLDER:
            out.append({"path": rel, "kind": "design"})
        elif p.is_dir() and p.name == EXPLORE_FOLDER:
            out += [_exploration(e, e.relative_to(root).as_posix()) for e in sorted(p.iterdir()) if e.is_dir()]
        elif p.is_dir() and not p.name.startswith("."):
            out.append({"path": rel, "kind": "folder"})
    if len(out) > MAX_FILES:
        return [*out[:MAX_FILES], {"kind": "more", "count": len(out) - MAX_FILES}]
    return out
