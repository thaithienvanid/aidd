"""Write what init and the team install write: a file, unless it exists and --force is off, noted in the actions. Every
write goes through the one safe writer, so a link at a file or on the way to it is skipped and named, never followed,
and the command goes on with the other files."""

from __future__ import annotations

import shutil
from pathlib import Path

from aidd.kernel import regular_files, repo_paths


def write_or_skip(root: Path, path: Path, text: str, actions: list[str], *, append: bool = False) -> bool:
    """Write (or with `append`, add) `text` at `path` in the repository `root`, never through a link; whether it did. A
    refusal adds a `skipped` line that names the link or the file and the next step."""
    try:
        regular_files.write_text_safely(root, path, text, append=append)
    except regular_files.WriteRefused as exc:
        actions.append(f"skipped  {repo_paths.shown(path)} ({exc})")
        return False
    return True


def write_file(root: Path, path: Path, text: str, force: bool, actions: list[str]) -> None:
    held = regular_files.is_file_or_held(root, path)  # also a file an earlier step of the same plan wrote
    if (path.exists() or held) and not force:
        actions.append(f"kept     {repo_paths.shown(path)} (exists; --force replaces it)")
        return
    before = regular_files.repository_text(root, path.relative_to(root).as_posix()) if held or path.is_file() else None
    if write_or_skip(root, path, text, actions):
        edited = force and before is not None and before.replace("\r\n", "\n") != text
        actions.append(f"wrote    {repo_paths.shown(path)}" + (" (--force replaced a file whose text differed)" if edited else ""))


def remove_safely(root: Path, path: Path, line: str, yes: bool, actions: list[str]) -> None:
    """Say `line`, and with `yes` remove the file or the folder at `path`, never through a link on the way to it: a link
    at `path` itself goes, never what it points to. A link on the way is skipped and named instead."""
    if refuses_link_on_the_way(root, path, actions):
        return
    actions.append(line)
    if yes and (path.is_symlink() or path.is_file()):
        path.unlink()
    elif yes and path.is_dir():
        shutil.rmtree(path)


def refuses_link_on_the_way(root: Path, path: Path, actions: list[str]) -> bool:
    """Whether a link lies between `root` and the folder of `path`, which a copy, a removal, or a new link at `path` would
    go through; a `skipped` line names it. A link at `path` itself is the caller's to replace."""
    if link := regular_files.link_on_the_way(root, path.parent):
        actions.append(f"skipped  {repo_paths.shown(path)} ({link} is a link, and aidd writes nothing through a link: remove the link, then run aidd again)")
        return True
    return False
