"""`aidd doctor` on the development team's files: whether the roles' files say what the config says, and whether the models
the config names deliver the independent review it asks for. Both ran only at `aidd init` before."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import regular_files
from aidd.setup import team_install, worktree_base


def team_lines(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """The warnings for the team files here, as (result, message): a role file that differs from what aidd writes for this
    config, `agents.models` or `agents.effort` set where the plugin carries the roles, and an `independent_review` that the
    models do not deliver on the wired harnesses."""
    out: list[tuple[str, str]] = []
    plan = team_install.wanted_team_files(root)
    if plan:
        stale = [rel for rel, text in plan[0].items() if (regular_files.repository_text(root, rel) or "").replace("\r\n", "\n") != text]
        if stale:
            count = "1 file is missing or differs" if len(stale) == 1 else f"{len(stale)} files are missing or differ"
            out.append(
                (
                    "warning",
                    f"development team: {count} from what aidd writes for this config, such as {stale[0]}. "
                    "`aidd upgrade --yes` adds missing files and updates unedited ones while keeping files you edited, "
                    "so remove a kept file and run `aidd upgrade --yes` to take the latest, or set `agents.models` or `agents.effort` instead",
                )
            )
    if team_install.team_plugin_carries_roles(root) and (note := team_install.models_inert_note(root)):
        out.append(("warning", note))
    runs = team_install.role_running_harnesses(root, detected, plan[1] if plan else (), claude_files=plan[2] if plan else False)
    if runs and (note := team_install.independent_review_note(root, runs)):
        out.append(("warning", note.removeprefix("warn").strip()))
    return out + worktree_base.doctor_lines(root, detected)
