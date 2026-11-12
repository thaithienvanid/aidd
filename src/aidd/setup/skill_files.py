"""The vendored skill and the links to it that `aidd init` makes. Inside a plan (`regular_files.holding_writes`) they say
what they would do, hold the files in the plan, and change nothing."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from aidd import __version__
from aidd.kernel import regular_files, repo_paths, resources
from aidd.setup import files

SKILL_REL = ".agents/skills/aidd"
DEFAULT_LINKS = (".claude/skills",)


def vendor_skill(root: Path, force: bool, actions: list[str]) -> None:
    src = resources.data_dir("skill")
    dest = root / SKILL_REL
    if dest.resolve() == src.resolve():
        actions.append(f"kept     {repo_paths.shown(dest)} (this is the source)")
        return
    if dest.exists() and not force:
        actions.append(f"kept     {repo_paths.shown(dest)} (exists; `aidd upgrade --yes` upgrades it)")
        return
    if files.refuses_link_on_the_way(root, dest, actions):
        return
    if regular_files.writes_held():
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            text = path.read_text(encoding="utf-8", errors="replace")  # aidd's own: the bundled skill, which the plan lists
            regular_files.hold_write(root, Path(SKILL_REL) / path.relative_to(src), text)
    else:
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    actions.append(f"vendored {repo_paths.shown(dest)} (aidd {__version__})")


def link_skill(root: Path, link_dir: str, actions: list[str], force: bool = False) -> None:
    link = root / link_dir / "aidd"
    target = os.path.relpath(root / SKILL_REL, link.parent)
    if link.is_symlink() and os.readlink(link) == target:
        actions.append(f"kept     {repo_paths.shown(link)} -> {repo_paths.shown(target)}")
        return
    if files.refuses_link_on_the_way(root, link, actions):
        return
    if link.is_symlink() or link.exists():
        if not force:
            why = "a link elsewhere; --force replaces it" if link.is_symlink() else "a real directory; --force refreshes it"
            actions.append(f"kept     {repo_paths.shown(link)} ({why})")
            return
        if not regular_files.writes_held():
            if link.is_symlink():
                link.unlink()
            else:
                shutil.rmtree(link)
    if regular_files.writes_held():
        regular_files.hold_write(root, Path(link_dir) / "aidd", f"-> {target}")  # a link, listed as the one path it is
        actions.append(f"linked   {repo_paths.shown(link)} -> {repo_paths.shown(target)}")
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
        actions.append(f"linked   {repo_paths.shown(link)} -> {repo_paths.shown(target)}")
    except OSError:
        shutil.copytree(root / SKILL_REL, link, symlinks=True)  # a link inside is copied as a link, never followed
        actions.append(f"copied   {repo_paths.shown(link)} (symlinks unavailable; `aidd doctor` checks it stays equal)")
