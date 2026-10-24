"""`aidd init --orca`: the `orca.yaml` that docs/ORCA.md documents. It checks the setup in each new Orca worktree and shows the next step.
An existing orca.yaml is never replaced, not even by --force, because it runs commands on a person's machine."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import repo_paths

ORCA_YAML = """\
scripts:
  setup: |
    aidd doctor
setupAgentStartupPolicy: wait-for-setup
defaultTabs:
  - title: aidd list --branch
    command: aidd list --branch
"""

_PROTECTED = "orca.yaml is a protected path, so the gate treats any change to it as major, and Orca asks you before it runs its scripts."


def orca_actions(root: Path, actions: list[str]) -> None:
    """Write orca.yaml at the repository root, or keep the one that exists and show what aidd would add."""
    path = root / "orca.yaml"
    if path.exists():
        shown = "".join(f"  {line}\n" for line in ORCA_YAML.splitlines())
        actions.append(f"kept     {repo_paths.shown(path)} (exists; aidd never replaces it). Add this to it by hand:\n{shown}{_PROTECTED}")
        return
    path.write_text(ORCA_YAML, encoding="utf-8")
    actions.append(f"wrote    {repo_paths.shown(path)}\n{_PROTECTED}")
