"""Where the gate runs for a checkout: on a platform's CI, or on this machine (local-first)."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import git

CI_GATE_FILES = (".github/workflows/aidd-gate.yml", ".gitlab/aidd.gitlab-ci.yml")


def platform_of(repo: str) -> str:
    """`local` when this machine's gate is the gate (no remote, or no CI gate installed: `aidd init --ci none`), else
    `preflight`: the branch will go to a platform, whose `aidd/gate` decides, so the hints name the platform's steps."""
    remotes = git.run(["remote"], repo, check=False).split()
    gated = any((Path(repo) / p).is_file() for p in CI_GATE_FILES)
    return "preflight" if remotes and gated else "local"
