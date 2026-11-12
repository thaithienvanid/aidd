"""The work-item files of a repository: which files are work items or typed documents, a Spec by id, a path or glob's files, and
which type of object may be the parent of which.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, globs, regular_files

# Operational documents: where `aidd new` writes each type, and where `aidd validate` and `aidd doctor` find them. The folder
# is the row's own (schemas/item-types.json): it never follows `docs.dir`, as a living document's `{docs}` path does.
OPS_DIRS = {t: config.item_type_rows()[t]["folder"] for t in config.types_in("operations")}

# The type of a Spec's `docs` entry that lists design files (spec.schema.json `$defs/doc`): the mockups, wireframes, and flows
# a person approves with the Spec. Spec approval always freezes them, so the entry's `frozen` is never read.
DESIGN_FILES = "design-files"


def find_spec_by_id(root: Path, specs_dir: str, spec_id: str) -> Path:
    """The Spec file whose id is `spec_id`: `<specs_dir>/<ID>.md`, else any Spec in the folder that says so. It reads each
    file as `read_document` does, so a link, a device, or a file past the size cap is never one, and a link at
    `<specs_dir>/<ID>.md` is an error that says so, since a write to the Spec would go through it."""
    rel = f"{specs_dir.rstrip('/')}/{spec_id}.md"
    direct = root / rel
    if regular_files.link_on_the_way(root, rel):
        raise ValueError(f"{rel}: {REFUSED[regular_files.LINK]}")
    for p in [direct] + [p for p in object_files(root, specs_dir) if p != direct]:
        text, _ = read_document(root, p.relative_to(root).as_posix())
        try:
            data, _ = documents.split_front_matter(text, p.as_posix()) if text is not None else ({}, "")
        except documents.DocumentError:
            continue
        if data.get("type") == "spec" and data.get("id") == spec_id:
            return p
    raise ValueError(
        f"no Spec {spec_id} in {specs_dir}/: write it first (`aidd new spec {command_names.quoted(spec_id) or '<ID>'} --title ...`), or name an existing one"
    )


# What a finding says of a repository file aidd reads no text from, by `regular_files.named_file_bytes`' reason.
REFUSED = {
    regular_files.LINK: "a link, which aidd never follows; replace it with the file",
    regular_files.NOT_REGULAR: "not a regular file (a device or a pipe, say), which aidd never opens; replace it with the file",
    regular_files.OUTSIDE: "a path outside the repository, which aidd never reads; name a file inside it",
    regular_files.TOO_LARGE: f"larger than {documents.MAX_DOCUMENT_BYTES} bytes, the most a document holds; split it, or link the detail",
}


def document_text(root: Path, rel: str) -> str:
    """`read_document`'s text, or "" when aidd reads none: for a check of a linked document that has nothing to say of
    one it cannot read."""
    return read_document(root, rel)[0] or ""


def read_document(root: Path, rel: str) -> tuple[str | None, str]:
    """The text of the document a repository names at `rel`, or None and why not, as a finding says it (REFUSED). It
    reads a regular file inside the repository only, never through a link or from a device, which a read could hang on,
    and at most a document's size cap, so another person's repository never sends a read elsewhere on the machine."""
    raw, why = regular_files.named_file_bytes(root, rel, documents.MAX_DOCUMENT_BYTES)
    if raw is None:
        return None, REFUSED.get(why, f"cannot be read ({why})")
    return raw.decode("utf-8", errors="replace"), ""


def files_matching(root: Path, pattern: str) -> list[str]:
    """The repository files a path or glob names, walking only below its literal prefix (never the whole tree). A path
    outside the repository, absolute, through `..`, or through a link that leads out, names no file, so nothing a Spec
    names is read from elsewhere on the machine."""
    parts = pattern.rstrip("/").split("/")
    if pattern.startswith(("/", "\\")) or ".." in parts:
        return []
    top = root.resolve()
    inside = lambda p: p.resolve().is_relative_to(top)  # noqa: E731
    fixed = list(itertools.takewhile(lambda s: not globs.is_pattern(s), parts))
    if len(fixed) == len(parts) and not pattern.endswith("/"):
        return [pattern] if (root / pattern).is_file() and inside(root / pattern) else []
    base = root.joinpath(*fixed)
    if not base.is_dir() or not inside(base):
        return []
    found = (p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file() and (not p.is_symlink() or inside(p)))
    return sorted(f for f in found if globs.match_any([pattern], f))


# The types a work item or a typed document has (schemas/item-types.json): a file is one when its front
# matter's top-level `type:` names one. Other tools write `type:` too (a blog post's `type: post`), so any other value
# leaves the file alone.
OBJECT_TYPES = config.types_of_form("work_item", "typed_document")
# The folder of the specs folder that holds each request saved from the chat, `specs/requests/<yyyy-mm-dd>-<slug>.md`: the
# person's own words, which an Intent's `request` names. It is never a work item, whatever its text holds.
REQUESTS = "requests"
# Documents that live in a work item's folder (`specs/<ID>/`, see item_folder) and have a type of their own: never a work item.
DOCUMENT_TYPES = config.types_with("inside_work_item")


def object_files(root: Path, specs_dir: str) -> list[Path]:
    """Objects: Markdown files whose `---` front matter names an aidd `type` (OBJECT_TYPES). A work item's own
    documents in its folder (`specs/<ID>/`), such as a decision card (DOCUMENT_TYPES), the saved requests (REQUESTS),
    and other tools' files (Spec Kit's specs/NNN-*/, or notes with their own front matter) are left alone."""
    return work_files(root, specs_dir)[0]


def work_files(root: Path, specs_dir: str) -> tuple[list[Path], list[tuple[Path, str]]]:
    """`object_files`, and each Markdown file of the folder that aidd reads no text from, with why (REFUSED): a link or
    a device, which could be a work item, so a Spec linked from elsewhere is never dropped without a word. A folder
    reached through a link is one such file, and nothing below it is walked."""
    folder = specs_dir.rstrip("/") or "."
    d = root / folder
    if regular_files.is_outside(folder) or not d.is_dir():
        return [], []
    if regular_files.link_on_the_way(root, folder):
        return [], [(d, REFUSED[regular_files.LINK])]
    found: list[Path] = []
    refused: list[tuple[Path, str]] = []
    for p in sorted(d.rglob("*.md")):
        if p.name.lower() == "readme.md" or is_saved_request(p, d):
            continue
        kind, why = _probe_file(p)
        if why:
            refused.append((p, REFUSED[why]))
        elif kind == "object" and front_type(p) not in DOCUMENT_TYPES:
            found.append(p)
    return found, refused


def is_saved_request(path: Path | str, specs: Path | str) -> bool:
    """Whether `path` lies in the REQUESTS folder right inside the specs folder `specs`: a person's own words, never a
    work item, whatever its text says. A `requests` folder deeper down, such as a work item's own, is not that folder."""
    return Path(path).is_relative_to(Path(specs) / REQUESTS)


# How far into a file aidd looks for the `type:` line of its front matter.
OBJECT_PROBE_LINES = 400


def _front_line(p: Path) -> tuple[str, str] | None:
    """(key, value) of the first top-level `type:` line in a file's front matter that names an aidd type,
    unquoted; ("", "") when the front matter closes without one; None when the file opens with none or is not read."""
    return _read_front_line(p)[0]


def _read_front_line(p: Path) -> tuple[tuple[str, str] | None, str]:
    """`_front_line`, and why the file was not read: LINK or NOT_REGULAR (`regular_files`), else empty. It reads a
    regular file only, never through a link or from a device, which a read could hang on. It reads no more than a
    document's cap and finds the type in that, so a file past the cap is still an object, which its reader then
    refuses by name as too large."""
    root = regular_files.working_root(p)
    rel = regular_files.relative(root, p)
    raw, why = regular_files.regular_file_bytes(root, rel, documents.MAX_DOCUMENT_BYTES)  # inside `root`, through no link out
    if raw is None:
        if why != regular_files.NOT_REGULAR:
            return None, ""
        return None, regular_files.LINK if p.is_symlink() or regular_files.link_on_the_way(root, rel) else regular_files.NOT_REGULAR
    return front_line_in(iter(raw.decode("utf-8-sig", errors="replace").splitlines(keepends=True))), ""


def front_line_in(lines: Iterator[str]) -> tuple[str, str] | None:
    """`_front_line` of a file's lines, such as a file read from a branch."""
    if next(lines, "").rstrip("\r\n").rstrip(" \t") != "---":
        return None
    for _, line in zip(range(OBJECT_PROBE_LINES), lines, strict=False):
        if line.rstrip("\r\n").rstrip(" \t") == "---":
            return "", ""
        key, colon, value = line.partition(":")
        value = value.split("#", 1)[0].strip().strip("\"'")
        if colon and key == "type" and value in OBJECT_TYPES:
            return key, value
    return None


def _probe(p: Path) -> str:
    """`object` when the file opens with `---` front matter whose top-level `type:` names an aidd type, `front` when it
    opens with front matter that closes without one, and empty otherwise."""
    return _probe_file(p)[0]


def _probe_file(p: Path) -> tuple[str, str]:
    """`_probe`, and why the file was not read (`_read_front_line`)."""
    found, why = _read_front_line(p)
    return ("" if found is None else "object" if found[0] else "front"), why


def is_object(path: Path) -> bool:
    """True when the file opens with `---` front matter whose top-level `type:` names an aidd type (OBJECT_TYPES)."""
    return _probe(path) == "object"


def front_type(path: Path) -> str:
    """The aidd type the top-level `type:` line of a file's front matter names, unquoted; empty when there is none."""
    found = _front_line(path)
    return found[1] if found else ""


def has_front_matter(path: Path) -> bool:
    """True when the file opens with `---` front matter, a work item's, a typed document's, or a living doc's (`reviewed_on`)."""
    return _probe(path) != ""


# The one type each work item's `parent` names: a Spec sits under an Intent, and an Intent under nothing.
PARENT_TYPE = {t: row["parent"] for t, row in config.item_type_rows().items() if "parent" in row}
TYPE_NAMES = {t: row["noun"] for t, row in config.item_type_rows().items() if "noun" in row}


def parent_type_error(item_type: str, parent: str, parent_type: str) -> str:
    """Why `parent`, an object of `parent_type`, cannot be the parent of an `item_type`, or "" when it can."""
    if item_type not in PARENT_TYPE or parent_type == PARENT_TYPE[item_type]:
        return ""
    return f"parent {parent} is {TYPE_NAMES.get(parent_type, parent_type)}; {TYPE_NAMES[item_type]}'s parent is {TYPE_NAMES[PARENT_TYPE[item_type]]}"


def type_of(root: Path, oid: str, folders: tuple[str, ...]) -> str:
    """The type of the object whose id is `oid` in `folders`, or "" when none has it (or it cannot be read)."""
    for path in (p for d in folders for p in object_files(root, d)):
        text, _ = read_document(root, path.relative_to(root).as_posix())
        try:
            data, _ = documents.split_front_matter(text, str(path)) if text is not None else ({}, "")
        except documents.DocumentError:
            continue
        if str(data.get("id")) == oid:
            return str(data.get("type"))
    return ""
