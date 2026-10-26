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
        if data.get("kind") == "spec" and data.get("id") == spec_id:
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


# Documents that live in a work item's folder (`specs/<ID>/`, see item_folder) and name a `kind` of their own: never a work item.
DOCUMENT_KINDS = ("exploration",)


def object_files(root: Path, specs_dir: str) -> list[Path]:
    """aidd objects: Markdown files whose `---` front matter names a `kind`. A work item's own documents in its folder
    (`specs/<ID>/`), such as a decision card (DOCUMENT_KINDS), and other tools' files (Spec Kit's specs/NNN-*/, or
    notes with their own front matter) are left alone."""
    d = root / specs_dir
    found = (p for p in d.rglob("*.md") if p.name.lower() != "readme.md" and is_object(p)) if d.is_dir() else ()
    return sorted(p for p in found if front_kind(p) not in DOCUMENT_KINDS)


# How far into a file aidd looks for the `kind:` line of its front matter.
OBJECT_PROBE_LINES = 400


def _probe(p: Path) -> str:
    """`object` when the file opens with `---` front matter that has a top-level `kind:` line, `front` when it opens
    with front matter that closes without one, and empty otherwise."""
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as fh:
            if fh.readline().rstrip("\r\n").rstrip(" \t") != "---":
                return ""
            for _, line in zip(range(OBJECT_PROBE_LINES), fh, strict=False):
                if line.rstrip("\r\n").rstrip(" \t") == "---":
                    return "front"
                if line.startswith("kind:"):
                    return "object"
    except OSError:
        pass
    return ""


def is_object(p: Path) -> bool:
    """True when the file opens with `---` front matter that has a top-level `kind:` line."""
    return _probe(p) == "object"


def front_kind(path: Path) -> str:
    """The value of the top-level `kind:` line in a file's front matter, unquoted; empty when there is none."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            if fh.readline().rstrip("\r\n").rstrip(" \t") != "---":
                return ""
            for _, line in zip(range(OBJECT_PROBE_LINES), fh, strict=False):
                if line.rstrip("\r\n").rstrip(" \t") == "---":
                    return ""
                if line.startswith("kind:"):
                    return line[len("kind:") :].split("#", 1)[0].strip().strip("\"'")
    except OSError:
        pass
    return ""


def has_front_matter(p: Path) -> bool:
    """True when the file opens with `---` front matter, an aidd object's or a living doc's (`reviewed_on`)."""
    return _probe(p) != ""


# The one kind each work item's `parent` names: a Spec sits under an Epic, an Epic under an Initiative.
PARENT_KIND = {"spec": "epic", "epic": "initiative"}
KIND_NAMES = {
    "spec": "a Spec",
    "epic": "an Epic",
    "initiative": "an Initiative",
    "proposal": "a proposal",
    "runbook": "a runbook",
    "postmortem": "a postmortem",
}


def parent_kind_error(kind: str, parent: str, parent_kind: str) -> str:
    """Why `parent`, an object of `parent_kind`, cannot be the parent of a `kind`, or "" when it can."""
    if kind not in PARENT_KIND or parent_kind == PARENT_KIND[kind]:
        return ""
    return f"parent {parent} is {KIND_NAMES.get(parent_kind, parent_kind)}; {KIND_NAMES[kind]}'s parent is {KIND_NAMES[PARENT_KIND[kind]]}"


def kind_of(root: Path, oid: str, folders: tuple[str, ...]) -> str:
    """The kind of the object whose id is `oid` in `folders`, or "" when none has it (or it cannot be read)."""
    for path in (p for d in folders for p in object_files(root, d)):
        try:
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8", errors="replace"), str(path))
        except (documents.DocumentError, OSError):
            continue
        if str(data.get("id")) == oid:
            return str(data.get("kind"))
    return ""
