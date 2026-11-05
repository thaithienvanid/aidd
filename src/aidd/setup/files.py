"""Write what init and the team install write: a file, unless it exists and --force is off, noted in the actions."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import repo_paths


def write_file(path: Path, text: str, force: bool, actions: list[str]) -> None:
    if path.exists() and not force:
        actions.append(f"kept     {repo_paths.shown(path)} (exists; --force replaces it)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    actions.append(f"wrote    {repo_paths.shown(path)}")
