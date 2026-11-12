"""The requests saved from the chat, `specs/requests/<yyyy-mm-dd>-<slug>.md`: a person's own words, which an Intent's
`request` names. The file is committed, so anyone who can read the repository reads it. The product manager leaves out
every secret and credential, and other people's personal data, and marks each place, such as `[left out: a credential]`.
`aidd validate` checks for a known secret's shape. No pattern finds personal data, so that stays the product manager's.
A saved request is never a work item, so a file there whose front matter names an aidd type is an error, never a Spec.
"""

from __future__ import annotations

import os
from pathlib import Path

from aidd import config
from aidd.kernel import regular_files, secret_patterns
from aidd.workitems import objects, repo_reads, spec_warnings


def credential_findings(root: Path, specs_dir: str, max_files: int) -> list[str]:
    """`request_findings` of each saved request, at most `max_files` of them. It walks the folder without following a
    link, and a link on the way to the folder is an error, so a tracked `specs/requests -> /` never walks the disk."""
    rel = f"{specs_dir.rstrip('/')}/{objects.REQUESTS}"
    folder = root / rel
    if regular_files.is_outside(specs_dir.rstrip("/") or ".") or not (folder.is_dir() or folder.is_symlink()):
        return []
    if regular_files.link_on_the_way(root, rel):
        return [f"{rel}: {objects.REFUSED[regular_files.LINK]}"]
    files: list[str] = []
    for here, dirs, names in os.walk(folder):
        dirs.sort()
        files += sorted(Path(here, n).relative_to(root).as_posix() for n in names if n.endswith(".md"))
        if len(files) > max_files:
            break
    out = [f for name in files[:max_files] for f in request_findings(root, name)]
    if len(files) > max_files:
        out.append(f"warning: {rel}: more than {max_files} saved requests, so only the first {max_files} were checked for a secret")
    return out


def request_findings(root: Path, rel: str) -> list[str]:
    """The findings for one saved request at `rel`: an error when aidd reads no text from it (a link, a device, or a
    file past a document's cap), or when its front matter names an aidd type; then one finding for each line that looks
    like it holds a secret: an error for a known token's shape (`secret_patterns.SECRET_PATTERNS`), and a warning for a
    looser one, such as a password assignment. It names the line and the shape, never the value, and reads each line to
    `secret_patterns.MAX_SECRET_LINE`, so a crafted line costs no more than a short one."""
    text, why = objects.read_document(root, rel)
    if text is None:
        return [f"{rel}: {why}"]
    out: list[str] = []
    found = objects.front_line_in(iter(text.lstrip("﻿").splitlines(keepends=True)))
    if found and found[0]:
        out.append(
            f"{rel}: its front matter names `type: {found[1]}`, but a saved request is never a work item; "
            f"move the work item out of {Path(rel).parent.as_posix()}/, or take out its `type:` line"
        )
    for n, line in enumerate(text.splitlines(), 1):
        line = line[: secret_patterns.MAX_SECRET_LINE]
        strict = secret_patterns.secret_types(line)
        if shapes := strict or secret_patterns.secret_types(line, loose=True):
            level = "" if strict else "warning: "
            out.append(
                f"{level}{rel}:{n}: looks like it holds {shapes[0]}. A saved request leaves out every secret and credential: "
                "replace it with `[left out: a credential]`, and rotate the credential if a commit ever held it"
            )
    return out


def saved_request_of(path: Path) -> tuple[Path, str] | None:
    """(the repository's root, the path from it) when `path` is a saved request of the repository that holds it, by
    the config's specs folder; None otherwise. The path is judged as written, so a link there is a saved request too."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return None
    cfg = repo_reads.config_at(root)
    full = Path(os.path.realpath(path.parent)) / path.name
    if not objects.is_saved_request(full, root / (cfg or config.EMPTY).specs_dir):
        return None
    return root, full.relative_to(root).as_posix()
