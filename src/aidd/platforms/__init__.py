"""The platform adapters: what feeds the gate its facts and acts on its decision on GitHub, on GitLab, and on one
machine with no platform (local-first)."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "MERGE_QUEUE_REF",
    "AGENT_ENV",
    "GITHUB_REPO_NAME",
    "NotAPerson",
    "PullRequest",
    "approval_target",
    "approve_pull_request",
    "disable_standing_auto_merges",
    "enable_auto_merge",
    "merge_review_body",
    "STANDING_REVIEW",
    "not_an_approver_problem",
    "open_pull_request",
    "person_login",
    "post_spec_approval",
    "build_local_context",
    "check_terminal",
    "github_gate",
    "gitlab_gate",
    "GitLabProject",
    "MergeRequest",
    "gitlab_approval_target",
    "gitlab_project",
    "open_merge_request",
    "post_gitlab_spec_approval",
    "train_parent",
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
    "land_locally",
    "spec_approval_holds",
    "spec_block",
    "this_branchs_approvals",
]

if TYPE_CHECKING:
    from aidd.platforms.github import github_gate as github_gate
    from aidd.platforms.github import merge_group_of as merge_group_of
    from aidd.platforms.github import queue_parent as queue_parent
    from aidd.platforms.github_person import GITHUB_REPO_NAME as GITHUB_REPO_NAME
    from aidd.platforms.github_person import STANDING_REVIEW as STANDING_REVIEW
    from aidd.platforms.github_person import PullRequest as PullRequest
    from aidd.platforms.github_person import approval_target as approval_target
    from aidd.platforms.github_person import approve_pull_request as approve_pull_request
    from aidd.platforms.github_person import disable_standing_auto_merges as disable_standing_auto_merges
    from aidd.platforms.github_person import enable_auto_merge as enable_auto_merge
    from aidd.platforms.github_person import merge_review_body as merge_review_body
    from aidd.platforms.github_person import not_an_approver_problem as not_an_approver_problem
    from aidd.platforms.github_person import open_pull_request as open_pull_request
    from aidd.platforms.github_person import origin_repo as origin_repo
    from aidd.platforms.github_person import person_login as person_login
    from aidd.platforms.github_person import post_spec_approval as post_spec_approval
    from aidd.platforms.github_person import protection_checks as protection_checks
    from aidd.platforms.github_person import spec_approval_holds as spec_approval_holds
    from aidd.platforms.gitlab import gitlab_gate as gitlab_gate
    from aidd.platforms.gitlab_person import GitLabProject as GitLabProject
    from aidd.platforms.gitlab_person import MergeRequest as MergeRequest
    from aidd.platforms.gitlab_person import gitlab_approval_target as gitlab_approval_target
    from aidd.platforms.gitlab_person import gitlab_project as gitlab_project
    from aidd.platforms.gitlab_person import open_merge_request as open_merge_request
    from aidd.platforms.gitlab_person import post_gitlab_spec_approval as post_gitlab_spec_approval
    from aidd.platforms.local_context import build_local_context as build_local_context
    from aidd.platforms.local_context import spec_block as spec_block
    from aidd.platforms.local_context import this_branchs_approvals as this_branchs_approvals
    from aidd.platforms.local_land import AGENT_ENV as AGENT_ENV
    from aidd.platforms.local_land import NotAPerson as NotAPerson
    from aidd.platforms.local_land import check_terminal as check_terminal
    from aidd.platforms.local_land import fetch_upstream as fetch_upstream
    from aidd.platforms.local_land import land_locally as land_locally
    from aidd.platforms.local_land import merged_commit as merged_commit
    from aidd.platforms.local_land import move_branch as move_branch
    from aidd.platforms.local_land import publish_branch as publish_branch
    from aidd.platforms.local_land import push_branch as push_branch
    from aidd.platforms.local_land import require_person as require_person
    from aidd.platforms.local_land import run_in_worktree as run_in_worktree
    from aidd.platforms.merge_results import MERGE_QUEUE_REF as MERGE_QUEUE_REF
    from aidd.platforms.merge_results import train_parent as train_parent
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "GITHUB_REPO_NAME": "github_person",
            "AGENT_ENV": "local_land",
            "NotAPerson": "local_land",
            "PullRequest": "github_person",
            "approval_target": "github_person",
            "approve_pull_request": "github_person",
            "disable_standing_auto_merges": "github_person",
            "enable_auto_merge": "github_person",
            "merge_review_body": "github_person",
            "STANDING_REVIEW": "github_person",
            "not_an_approver_problem": "github_person",
            "open_pull_request": "github_person",
            "person_login": "github_person",
            "post_spec_approval": "github_person",
            "build_local_context": "local_context",
            "check_terminal": "local_land",
            "github_gate": "github",
            "gitlab_gate": "gitlab",
            "GitLabProject": "gitlab_person",
            "MergeRequest": "gitlab_person",
            "gitlab_approval_target": "gitlab_person",
            "gitlab_project": "gitlab_person",
            "open_merge_request": "gitlab_person",
            "post_gitlab_spec_approval": "gitlab_person",
            "MERGE_QUEUE_REF": "merge_results",
            "train_parent": "merge_results",
            "merge_group_of": "github",
            "fetch_upstream": "local_land",
            "merged_commit": "local_land",
            "move_branch": "local_land",
            "origin_repo": "github_person",
            "protection_checks": "github_person",
            "queue_parent": "github",
            "require_person": "local_land",
            "run_in_worktree": "local_land",
            "publish_branch": "local_land",
            "push_branch": "local_land",
            "land_locally": "local_land",
            "spec_approval_holds": "github_person",
            "spec_block": "local_context",
            "this_branchs_approvals": "local_context",
        },
    )
