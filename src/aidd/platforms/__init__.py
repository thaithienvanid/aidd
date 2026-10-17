"""The platform adapters: what feeds the gate its facts and acts on its decision on GitHub, on GitLab, and on one
machine with no platform (local-first)."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "AGENT_ENV",
    "GITHUB_REPO_NAME",
    "NotAPerson",
    "PullRequest",
    "approval_target",
    "approve_pull_request",
    "enable_auto_merge",
    "not_an_approver_problem",
    "person_login",
    "post_spec_approval",
    "build_local_context",
    "check_terminal",
    "github_gate",
    "gitlab_gate",
    "merge_group_of",
    "fetch_upstream",
    "merged_commit",
    "move_branch",
    "origin_repo",
    "protection_checks",
    "queue_parent",
    "require_person",
    "run_in_worktree",
    "publish_branch",
    "push_branch",
    "ship_locally",
    "spec_approval_holds",
    "spec_block",
    "this_branchs_approvals",
]

if TYPE_CHECKING:
    from aidd.platforms.github import GITHUB_REPO_NAME as GITHUB_REPO_NAME
    from aidd.platforms.github import PullRequest as PullRequest
    from aidd.platforms.github import approval_target as approval_target
    from aidd.platforms.github import approve_pull_request as approve_pull_request
    from aidd.platforms.github import enable_auto_merge as enable_auto_merge
    from aidd.platforms.github import github_gate as github_gate
    from aidd.platforms.github import merge_group_of as merge_group_of
    from aidd.platforms.github import not_an_approver_problem as not_an_approver_problem
    from aidd.platforms.github import origin_repo as origin_repo
    from aidd.platforms.github import person_login as person_login
    from aidd.platforms.github import post_spec_approval as post_spec_approval
    from aidd.platforms.github import protection_checks as protection_checks
    from aidd.platforms.github import queue_parent as queue_parent
    from aidd.platforms.github import spec_approval_holds as spec_approval_holds
    from aidd.platforms.gitlab import gitlab_gate as gitlab_gate
    from aidd.platforms.local_context import build_local_context as build_local_context
    from aidd.platforms.local_context import spec_block as spec_block
    from aidd.platforms.local_context import this_branchs_approvals as this_branchs_approvals
    from aidd.platforms.local_ship import AGENT_ENV as AGENT_ENV
    from aidd.platforms.local_ship import NotAPerson as NotAPerson
    from aidd.platforms.local_ship import check_terminal as check_terminal
    from aidd.platforms.local_ship import fetch_upstream as fetch_upstream
    from aidd.platforms.local_ship import merged_commit as merged_commit
    from aidd.platforms.local_ship import move_branch as move_branch
    from aidd.platforms.local_ship import publish_branch as publish_branch
    from aidd.platforms.local_ship import push_branch as push_branch
    from aidd.platforms.local_ship import require_person as require_person
    from aidd.platforms.local_ship import run_in_worktree as run_in_worktree
    from aidd.platforms.local_ship import ship_locally as ship_locally
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "GITHUB_REPO_NAME": "github",
            "AGENT_ENV": "local_ship",
            "NotAPerson": "local_ship",
            "PullRequest": "github",
            "approval_target": "github",
            "approve_pull_request": "github",
            "enable_auto_merge": "github",
            "not_an_approver_problem": "github",
            "person_login": "github",
            "post_spec_approval": "github",
            "build_local_context": "local_context",
            "check_terminal": "local_ship",
            "github_gate": "github",
            "gitlab_gate": "gitlab",
            "merge_group_of": "github",
            "fetch_upstream": "local_ship",
            "merged_commit": "local_ship",
            "move_branch": "local_ship",
            "origin_repo": "github",
            "protection_checks": "github",
            "queue_parent": "github",
            "require_person": "local_ship",
            "run_in_worktree": "local_ship",
            "publish_branch": "local_ship",
            "push_branch": "local_ship",
            "ship_locally": "local_ship",
            "spec_approval_holds": "github",
            "spec_block": "local_context",
            "this_branchs_approvals": "local_context",
        },
    )
