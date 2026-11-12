"""Whether a push to a branch deploys, and why: the one place the delegate check decides it, for a push to the change's own
branch and for a merge into the default branch. It reads the config's `environments`, the Pages source, the workflows
at the tip that deploy on the push, and, for the default branch, the tracked files a host deploys from on a merge."""

from __future__ import annotations

import dataclasses

from aidd import risk
from aidd.delegation import deploy_evidence, diff_signals
from aidd.delegation.check import Check
from aidd.kernel import git, globs


@dataclasses.dataclass
class Deploys:
    """Why a push to a branch deploys. Every field empty and `unknown` false is the one case where it deploys nothing."""

    unknown: bool = False  # the default branch, and no `environments` of this repository's own: aidd cannot tell
    environments: list[str] = dataclasses.field(default_factory=list)  # the names of the environments that list the branch
    pages: bool = False  # the branch is the Pages source
    workflows: list[str] = dataclasses.field(default_factory=list)  # `path:line` of each workflow that deploys on the push
    host_files: list[str] = dataclasses.field(default_factory=list)  # the default branch's tracked host deploy files, when no environment names it

    def declared(self) -> list[str]:
        """What makes the push deploy by what the config, the platform, and the tracked files say, apart from workflows."""
        return [*(["it is the Pages source"] if self.pages else []), *(f"environment {n}" for n in self.environments), *self.host_files]

    def why(self) -> list[str]:
        """Everything that makes the push deploy."""
        return [*self.declared(), *self.workflows]


def host_files(check: Check) -> list[str]:
    """The tracked files at the tip a host deploys from on a merge, such as `vercel.json`."""
    assert check.rs is not None
    patterns = diff_signals.host_deploy_globs(check.rs)
    return sorted(p for p in git.ls_tree(check.tip, check.top) if globs.match_any(patterns, p, fold_case=True))


def _gitlab_jobs(check: Check, branch: str) -> list[str]:
    """Each job of the tip's `.gitlab-ci.yml` that deploys on a push to `branch`, or that this cannot read: a repository on
    one platform may still track another's file, and doctor reads it too."""
    entry = git.run(["ls-tree", "-z", "--full-tree", check.tip, "--", deploy_evidence.GITLAB_FILE], check.top).split()
    if not entry:
        return []
    text = git.show(check.tip, deploy_evidence.GITLAB_FILE, check.top) if entry[0] in ("100644", "100755") else None  # not a symlink
    if text is None:
        return [f"{deploy_evidence.GITLAB_FILE} (unreadable)"]
    return deploy_evidence.gitlab_deploying_on(text, branch, [check.default])


def of_branch(check: Check, branch: str, pages: str | None) -> Deploys:
    """What deploys on a push to `branch`, with `pages` the platform's Pages source branch (None: it has none, or the
    repository has no platform). An environment from any layer, the config's own or a parent's, counts, because the delegate
    only ever reads a "yes" from a layer. For the default branch it also fails closed on `environments` that nothing here
    sets, and on a host's deploy file that no environment names, because a merge there is a push."""
    assert check.rs is not None and check.cfg is not None
    # An environment any layer lists counts, as the rules read a push: a name with no wildcard lists only itself.
    listed = risk.deploys_to([*check.rs.environments, *check.cfg.parent_environments], "branches", branch)
    out = Deploys(
        environments=list(dict.fromkeys(listed)),
        pages=pages == branch,
        workflows=[*diff_signals.deploying_workflows(check.rs, check.tip, branch, check.top), *_gitlab_jobs(check, branch)],
    )
    if branch == check.default:
        # The repository's own list says a merge deploys nowhere, and so does a lock on `environments`, set by a parent or by this
        # repository (its own lock is the person's own file, so it loosens nothing against them). An unlocked parent's list cannot say it.
        said = check.cfg.sets_environments or "environments" in (check.cfg.get("locks") or [])
        out.unknown = check.cfg.get("environments") is None or not said
        out.host_files = [] if out.environments else host_files(check)
    return out
