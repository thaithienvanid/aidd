"""The work-item files of a repository: which files are aidd objects, a Spec by id, a path or glob's files, and which
kind of object may be the parent of which.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from aidd.kernel import documents, globs

# Operational documents: where `aidd new` writes each kind, and where `aidd validate` and `aidd doctor` find them.
OPS_DIRS = {"runbook": "docs/runbooks", "postmortem": "docs/postmortems"}


def find_spec_by_id(root: Path, specs_dir: str, spec_id: str) -> Path:
    """The Spec file whose id is `spec_id`: `<specs_dir>/<ID>.md`, else any Spec in the folder that says so."""
    direct = root / specs_dir / f"{spec_id}.md"
    for p in [direct] + [p for p in object_files(root, specs_dir) if p != direct]:
        if not p.is_file():
            continue
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8"), p.as_posix())
        except documents.DocumentError:
            continue
        if data.get("type") == "spec" and data.get("id") == spec_id:
            return p
    raise ValueError(f"no Spec {spec_id} in {specs_dir}/: write it first (`aidd new spec {spec_id} --title ...`), or name an existing one")


def files_matching(root: Path, pattern: str) -> list[str]:
    """The repository files a path or glob names, walking only below its literal prefix (never the whole tree)."""
    parts = pattern.rstrip("/").split("/")
    fixed = list(itertools.takewhile(lambda s: not any(c in s for c in "*?["), parts))
    if len(fixed) == len(parts) and not pattern.endswith("/"):
        return [pattern] if (root / pattern).is_file() else []
    base = root.joinpath(*fixed)
    if not base.is_dir():
        return []
    found = (p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
    return sorted(f for f in found if globs.match_any([pattern], f))


# The types of aidd object, each a work item or its record: a file is one when its front matter's top-level `type:` names
# one. Other tools write `type:` too (a blog post's `type: post`), so any other value leaves the file alone.
ITEM_TYPES = ("spec", "epic", "initiative", "proposal", "runbook", "postmortem", "exploration", "feedback")
# Documents that live in a work item's folder (`specs/<ID>/`, see item_folder) and have a type of their own: never a work item.
DOCUMENT_TYPES = ("exploration",)


def object_files(root: Path, specs_dir: str) -> list[Path]:
    """aidd objects: Markdown files whose `---` front matter names an aidd `type` (ITEM_TYPES). A work item's own
    documents in its folder (`specs/<ID>/`), such as a decision card (DOCUMENT_TYPES), and other tools' files (Spec
    Kit's specs/NNN-*/, or notes with their own front matter) are left alone. A file that still names its type with
    `kind:` counts, so `aidd validate` names the fix rather than skip it."""
    d = root / specs_dir
    found = (p for p in d.rglob("*.md") if p.name.lower() != "readme.md" and is_object(p)) if d.is_dir() else ()
    return sorted(p for p in found if front_type(p) not in DOCUMENT_TYPES)


# How far into a file aidd looks for the `type:` line of its front matter.
OBJECT_PROBE_LINES = 400


def _front_line(p: Path) -> tuple[str, str] | None:
    """(key, value) of the first top-level `type:` or `kind:` line in a file's front matter that names an aidd type,
    unquoted; ("", "") when the front matter closes without one; None when the file opens with none."""
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as fh:
            if fh.readline().rstrip("\r\n").rstrip(" \t") != "---":
                return None
            for _, line in zip(range(OBJECT_PROBE_LINES), fh, strict=False):
                if line.rstrip("\r\n").rstrip(" \t") == "---":
                    return "", ""
                key, colon, value = line.partition(":")
                value = value.split("#", 1)[0].strip().strip("\"'")
                if colon and key in ("type", "kind") and value in ITEM_TYPES:
                    return key, value
    except OSError:
        pass
    return None


def _probe(p: Path) -> str:
    """`object` when the file opens with `---` front matter whose top-level `type:` names an aidd type, `front` when it
    opens with front matter that closes without one, and empty otherwise."""
    found = _front_line(p)
    return "" if found is None else "object" if found[0] else "front"


def is_object(p: Path) -> bool:
    """True when the file opens with `---` front matter whose top-level `type:` names an aidd type (ITEM_TYPES)."""
    return _probe(p) == "object"


def front_type(path: Path) -> str:
    """The aidd type the top-level `type:` line of a file's front matter names, unquoted; empty when there is none."""
    found = _front_line(path)
    return found[1] if found else ""


def has_front_matter(p: Path) -> bool:
    """True when the file opens with `---` front matter, an aidd object's or a living doc's (`reviewed_on`)."""
    return _probe(p) != ""


# The one kind each work item's `parent` names: a Spec sits under an Epic, an Epic under an Initiative.
PARENT_TYPE = {"spec": "epic", "epic": "initiative"}
TYPE_NAMES = {
    "spec": "a Spec",
    "epic": "an Epic",
    "initiative": "an Initiative",
    "proposal": "a proposal",
    "runbook": "a runbook",
    "postmortem": "a postmortem",
}


def parent_type_error(kind: str, parent: str, parent_kind: str) -> str:
    """Why `parent`, an object of `parent_kind`, cannot be the parent of a `kind`, or "" when it can."""
    if kind not in PARENT_TYPE or parent_kind == PARENT_TYPE[kind]:
        return ""
    return f"parent {parent} is {TYPE_NAMES.get(parent_kind, parent_kind)}; {TYPE_NAMES[kind]}'s parent is {TYPE_NAMES[PARENT_TYPE[kind]]}"


def type_of(root: Path, oid: str, folders: tuple[str, ...]) -> str:
    """The kind of the object whose id is `oid` in `folders`, or "" when none has it (or it cannot be read)."""
    for path in (p for d in folders for p in object_files(root, d)):
        try:
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8", errors="replace"), str(path))
        except (documents.DocumentError, OSError):
            continue
        if str(data.get("id")) == oid:
            return str(data.get("type"))
    return ""
