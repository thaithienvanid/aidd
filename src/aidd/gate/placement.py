"""Where the gate runs for a checkout: on a platform's CI, or on this machine (local-first)."""

from __future__ import annotations

from pathlib import Path

from aidd import config
from aidd.kernel import documents, git

CI_GATE_FILES = (".github/workflows/aidd-gate.yml", ".gitlab/aidd.gitlab-ci.yml")


def agents_publish(repo: str) -> bool:
    """Whether agents may take work off this machine: `publish: agents` in the config, as the working tree holds it
    (only a person changes the key: the guard denies an agent's edit of it). Unset, or unreadable, a person publishes."""
    try:
        data = documents.parse_yaml((Path(repo) / config.CONFIG_PATH).read_text(encoding="utf-8"), "config")
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return isinstance(data, dict) and data.get("publish") == "agents"


def published(repo: str) -> bool:
    """Whether the branch checked out is a piece of work someone published: a branch other than the base branch that
    a remote holds too. The base branch never counts, since every clone has it on the remote."""
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip()
    try:
        base = git.default_base(repo).removeprefix("origin/")
    except git.GitError:
        base = ""
    if not branch or branch == base:
        return False
    return any(git.ok(["rev-parse", "-q", "--verify", f"refs/remotes/{r}/{branch}"], repo) for r in git.run(["remote"], repo, check=False).split())


def trunk_on_platform(repo: str) -> bool:
    """Whether this repository's trunk lives on a platform: a remote runs the aidd gate workflow. Work then reaches the
    trunk through a pull or merge request (publish, then merge it there); else it lands on this machine's trunk."""
    return bool(git.run(["remote"], repo, check=False).split()) and any((Path(repo) / p).is_file() for p in CI_GATE_FILES)


def platform_of(repo: str) -> str:
    """`local` when this machine's gate is the gate, else `preflight`: the branch is on a platform, whose `aidd/gate`
    decides, so the hints name the platform's steps. The platform decides only where a remote runs the aidd gate
    workflow and the work is there: agents publish (`publish: agents`), or a person published this branch. Until a
    person publishes, the team works on this machine: the inner loop, and the local trunk `aidd land` lands on."""
    if not trunk_on_platform(repo):
        return "local"
    return "preflight" if agents_publish(repo) or published(repo) else "local"
