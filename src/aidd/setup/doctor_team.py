"""`aidd doctor` on the delivery team's files: whether the roles' files say what the config says, and whether the models
the config names deliver the independent review it asks for. Both ran only at `aidd init` before."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import regular_files
from aidd.setup import team_install, worktree_base


def team_lines(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """The warnings for the team files here, as (level, message): a role file that differs from what aidd writes for this
    config, `agents.models` or `agents.effort` set where the plugin carries the roles, and an `independent_review` that the
    models do not deliver on the wired harnesses."""
    out: list[tuple[str, str]] = []
    if plan := team_install.wanted_team_files(root):
        stale = [rel for rel, text in plan[0].items() if (regular_files.repository_text(root, rel) or "").replace("\r\n", "\n") != text]
        if stale:
            out.append(
                (
                    "warn",
                    f"delivery team: {'1 file is' if len(stale) == 1 else f'{len(stale)} files are'} missing or differs from what aidd writes for this config, such as {stale[0]}; "
                    "`aidd upgrade --yes` rewrites them, and replaces a hand edit, so set `agents.models` or `agents.effort` instead",
                )
            )
    if team_install.team_plugin_carries_roles(root) and (note := team_install.models_inert_note(root)):
        out.append(("warn", note))
    runs = tuple(h for h in ("claude-code", *team_install.NATIVE_AGENT_HARNESSES) if h in detected)
    if note := team_install.independent_review_note(root, runs):
        out.append(("warn", note.removeprefix("warn").strip()))
    return out + worktree_base.doctor_lines(root, detected)
