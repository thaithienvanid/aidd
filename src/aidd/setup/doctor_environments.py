"""`aidd doctor` on where a push deploys: when what the workflows say and what the config's `environments` say disagree. The
delegate check already fails closed on a deploying workflow, so a warning here says why, and where to look."""

from __future__ import annotations

from pathlib import Path

from aidd import config, delegation, risk
from aidd.kernel import documents, git, globs


def _branches_that_exist(root: Path) -> list[str]:
    """The local branches, and origin's, by name."""
    refs = git.run(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin"], str(root), check=False).split()
    return [r.removeprefix("refs/heads/").removeprefix("refs/remotes/origin/") for r in refs if not r.endswith("/HEAD")]


def _exists(glob: str, branches: list[str]) -> bool:
    """Whether a branch is named like `glob`: a name with no wildcard names one branch."""
    return any(globs.match(glob, b) if globs.is_pattern(glob) else glob == b for b in branches)


def _says_nothing_deploys(root: Path, rs: risk.RuleSet) -> list[str]:
    """With `environments: []`, the `path:line` of each workflow that deploys on a push to the default branch."""
    names, _sure = git.default_branches(str(root))
    return list(dict.fromkeys(w for b in names for w in delegation.workflows_deploying_on(root, b, rs)))


def environment_checks(root: Path, cfg: config.Config | None) -> list[tuple[str, str]]:
    """A warning when `environments: []` says nothing deploys and a workflow deploys on a push to the default branch, and one
    for each environment none of whose branches exists any more."""
    if cfg is None:
        return []
    listed = cfg.get("environments")
    if not isinstance(listed, list):
        return []
    rs = risk.rule_set(cfg)
    out: list[tuple[str, str]] = []
    if not listed and (found := _says_nothing_deploys(root, rs)):
        out.append(
            (
                "warn",
                f"environments: [] says no push deploys, but {', '.join(found[:3])} deploys on a push to the default branch, so a delegated merge stays yours while it does. "
                "Name the environment it deploys to in `environments`, or take the deploy out of the workflow",
            )
        )
    existing = _branches_that_exist(root)
    for env in listed:
        wanted = [str(b) for b in env.get("branches") or []] if isinstance(env, dict) else []
        if wanted and existing and not any(_exists(b, existing) for b in wanted):
            out.append(
                (
                    "warn",
                    f"environments {documents.one_line(env.get('name'), 80)} lists {documents.one_line(', '.join(wanted), 200)}, and no branch like that exists here or on origin. "
                    "If it is gone, remove the environment from `environments`; if it is new, push it",
                )
            )
    return out
