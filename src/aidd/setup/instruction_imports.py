"""Claude Code reads a project's `CLAUDE.md` in place of `AGENTS.md`, and a `CLAUDE.md` can import the file with one line,
`@AGENTS.md` (code.claude.com/docs/en/memory, read 2026-11-11). So aidd's section in `CLAUDE.md` is that line, and the
block, the project's guide, and the team's roles reach Claude Code once, from the file that owns them.

The section sits between aidd's marks. Everything else in the person's `CLAUDE.md` stays as it is, and aidd never writes
`CLAUDE.local.md`, which is the person's own.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from aidd import config
from aidd.kernel import regular_files, repo_paths
from aidd.setup import files, marked_sections

HEADING = "## Change control"
MAX_LINE = 2000  # a longer line of a person's file is no import, and is not scanned
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_IMPORT = re.compile(r"(?<![\w`@/.-])@(\S+)")


def import_line(rel: str) -> str:
    """The line that imports `AGENTS.md` from the instruction file at `rel`, a path inside the repository."""
    return "@" + posixpath.relpath(config.AGENTS_MD, posixpath.dirname(rel) or ".")


def import_section(rel: str) -> str:
    """aidd's section for the instruction file at `rel`: a heading and the import, between its marks."""
    note = "<!-- Claude Code reads this file in place of AGENTS.md, so this line imports it. -->"
    return f"{marked_sections.AGENTS_MARK}\n{HEADING}\n\n{note}\n{import_line(rel)}\n{marked_sections.end_mark(marked_sections.AGENTS_MARK)}\n"


def imports_agents_md(text: str, rel: str) -> bool:
    """Whether `text`, the instruction file at `rel`, imports `AGENTS.md` the way Claude Code reads an import: a word that
    starts with `@` outside a code span and a code fence, whose path from this file names the root `AGENTS.md`."""
    fence = False
    for line in text.splitlines():
        if line.strip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence or len(line) > MAX_LINE:
            continue
        for found in _IMPORT.finditer(_CODE_SPAN.sub("", line)):
            if posixpath.normpath(posixpath.join(posixpath.dirname(rel), found.group(1))) == config.AGENTS_MD:
                return True
    return False


def person_imports(text: str, rel: str) -> bool:
    """Whether the person's own lines, outside aidd's section, import `AGENTS.md`."""
    found = marked_sections.sections(text, marked_sections.AGENTS_MARK)
    outside = text[: found[0].start] + text[found[0].end :] if found and found[0].closed else text
    return imports_agents_md(outside, rel)


def links_to_agents_md(root: Path, rel: str) -> bool:
    """Whether the file at `rel` is a link to the root `AGENTS.md`, which Claude Code's page offers in place of an import."""
    path = root / rel
    return path.is_symlink() and path.resolve() == (root / config.AGENTS_MD).resolve()


def hiders_present(root: Path, harness: config.Harness) -> list[str]:
    """The files in `root` that make `harness` skip `AGENTS.md`."""
    return [rel for rel in harness.hiders if regular_files.is_file_or_held(root, rel) or (root / rel).is_symlink()]


def pointer_target(root: Path, harness: config.Harness) -> str | None:
    """The instruction file aidd writes for `harness`: the first of its files that exists. When none does, and a file that hides
    `AGENTS.md` does, the pointer file is made, so the guide reaches the agent. None when `AGENTS.md` is read already."""
    for rel in harness.pointer_names:
        if regular_files.is_file_or_held(root, rel) or (root / rel).is_symlink():
            return rel
    if harness.pointer and (not harness.only_if_present or hiders_present(root, harness)):
        return harness.pointer
    return None


def reaches_agents_md(root: Path, harness: config.Harness) -> bool:
    """Whether `harness` reads `AGENTS.md`: nothing hides it, or one of its project files imports it or links to it."""
    if not hiders_present(root, harness):
        return True
    for rel in harness.pointer_names:
        if links_to_agents_md(root, rel) or imports_agents_md(regular_files.repository_text(root, rel) or "", rel):
            return True
    return False


def problem(root: Path, harness: config.Harness) -> str | None:
    """The doctor warning for `harness` when a file hides `AGENTS.md` from it and no project file imports it, else None."""
    if reaches_agents_md(root, harness):
        return None
    hiding = ", ".join(hiders_present(root, harness))
    holds_mark = any(marked_sections.AGENTS_MARK in (regular_files.repository_text(root, rel) or "") for rel in harness.pointer_names)
    fix = (
        "`aidd upgrade --yes` replaces the copy there with the import" if holds_mark else f"`aidd init` adds the import to {harness.pointer}, keeping your text"
    )
    return (
        f"{harness.label} reads {hiding} in place of {config.AGENTS_MD}, and no {harness.pointer} imports it, so it misses the project's guide "
        f"and the team's roles; {fix}, or write `{import_line(harness.pointer or '')}` in {harness.pointer} yourself"
    )


def appended(current: str, section: str) -> str:
    """`section` as it is added to the end of `current`: after one blank line, in the line endings `current` uses."""
    plain = current.replace("\r\n", "\n")
    gap = "" if plain.endswith("\n\n") or not plain else "\n" if plain.endswith("\n") else "\n\n"
    text = gap + section
    return text.replace("\n", "\r\n") if "\r\n" in current else text


def write_import(root: Path, rel: str, actions: list[str]) -> None:
    """Claude Code's instruction file: aidd's section is the line that imports AGENTS.md, added to the end of the person's file.
    A file that links to AGENTS.md, or imports it already, or holds aidd's section, is kept as it is."""
    path = root / rel
    current, why = regular_files.named_text(root, rel)
    section, line = import_section(rel), import_line(rel)
    if links_to_agents_md(root, rel):
        actions.append(f"kept     {repo_paths.shown(path)} (a link to AGENTS.md: Claude Code reads AGENTS.md through it)")
    elif current is None and why != regular_files.MISSING:
        actions.append(f"skipped  {repo_paths.shown(path)} ({why}: aidd neither reads it nor writes through it; replace it with the file)")
    elif current is None:
        if files.write_or_skip(root, path, section, actions):
            actions.append(
                f"wrote    {repo_paths.shown(path)} (Claude Code reads it in place of AGENTS.md, so it holds the line `{line}` that imports AGENTS.md)"
            )
    elif marked_sections.AGENTS_MARK in current:
        actions.append(f"kept     {repo_paths.shown(path)} (already holds aidd's section; `aidd upgrade --yes` refreshes it)")
    elif imports_agents_md(current, rel):
        actions.append(f"kept     {repo_paths.shown(path)} (already imports AGENTS.md)")
    elif files.write_or_skip(root, path, appended(current, section), actions, append=True):
        actions.append(
            f"appended {repo_paths.shown(path)} (the line `{line}`, which imports AGENTS.md so Claude Code reads the project's guide too; your text stays)"
        )
