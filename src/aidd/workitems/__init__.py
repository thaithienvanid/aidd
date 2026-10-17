"""Work items: Specs, Epics, Initiatives, proposals, and explorations, and the fields a team tracks them by: status
groups, triage, typed relations, labels, the why chain, and the handoff note.

A tracker (Jira, Linear, Plane) is optional: the Spec, Epic, and Initiative files in git are the record, and the
children backlog, triage, and handoff_notes read the few fields that turn them into a backlog a person can steer. None
of it is evidence. The gate never uses those three, and the Spec hash ignores every field they read
(`spec_file.VOLATILE_SPEC_KEYS`) and every handoff block (`spec_file.strip_handoffs`), so bookkeeping never voids an
approval.

- **Status group**: each status of every kind falls into one of five groups (backlog, unstarted, started, completed,
  cancelled), from `x-groups` in the schemas, so any board mirrors any object by its group. The status itself is
  derived (`derived_status.py`); these functions take it as given.
- **Triage**: a Spec an agent suggested (`suggested_by: agent:<role>`, a role in `agents.proactive_roles`) stays a
  draft until a person records `triage` (accepted, declined, or snoozed until a date). A duplicate is a relation.
- **Relations**: `relations: [{type: "blocked_by", id: "SPEC-12"}]` on a Spec, Epic, or Initiative. `aidd
  validate` checks the targets exist and that blocks form no cycle; `aidd list` shows blocked work as blocked.
- **Handoff note**: a fenced ```aidd-handoff block of YAML (done, next, needs, stopped_at, and optional spend and
  status) that an agent writes into the Spec or the PR/MR when it stops. `aidd list` and the session hooks read the latest one in the Spec:
  `next` names the role that takes the work, and `needs` asks a person, while the status it was written in holds.

The other children: spec_file (parsing and the Spec hash), objects, derived_status, approval_ledger, branch_specs,
repo_reads (the objects and the config at a git ref), authoring (`aidd new`), validation (`aidd validate`) with
doc_checks, spec_warnings, proposal_checks, and due_dates, spec_history, steps, proposal, explorations, and item_folder
(what a work item's folder, `specs/<ID>/`, holds).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "AGENT",
    "APPROVALS_REF",
    "APPROVER",
    "AUTHOR",
    "CAN_WAIT",
    "CHANGE_ORDERS",
    "COMMIT",
    "DEFAULT_ROUTES",
    "DIRECTION_HEADING",
    "DOC_KINDS_NEW",
    "DOC_TEMPLATES",
    "EXPLORATION_FILE",
    "Facts",
    "HANDOFF_FENCE",
    "LIVING_DOCS",
    "MAX_OBJECTS",
    "MERGE_TRAILER",
    "NewDoc",
    "NewObject",
    "BASE_PATTERN",
    "OPS_DIRS",
    "Observer",
    "PERSON",
    "PRIORITIES",
    "RELEASED",
    "REPO_DOCS",
    "ROUNDS_DIR",
    "STANDING_SCOPES",
    "STEP_CODES",
    "UNBLOCKS",
    "UNLINKED_DOCS",
    "WORK_KINDS",
    "acceptance_ids",
    "active_specs",
    "approval_holds",
    "approve_merge_line",
    "approve_spec_line",
    "carried_specs",
    "confirmed_in",
    "with_login",
    "parse_typed",
    "grants",
    "live_standing",
    "live_standing_for",
    "ship_decision",
    "ship_said",
    "ship_said_for",
    "ship_said_line",
    "since_text",
    "standing_covers",
    "standing_line",
    "day",
    "goal_of",
    "current_branch",
    "EXPLORE_PREFIX",
    "explore_note",
    "is_explore",
    "edits_held",
    "builds_on",
    "GOAL_PREFIX",
    "GOAL_TRAILER",
    "SHIPS",
    "goal_branch",
    "is_launch",
    "launches_at",
    "ships",
    "small_goal_checks",
    "INTEGRATE_TRAILER",
    "MAX_GOAL_DAYS",
    "goal_branches",
    "goal_facts",
    "independent_tips",
    "flow_warnings",
    "work_branches",
    "MAX_OPEN_BRANCHES",
    "MAX_BRANCH_DAYS",
    "goal_warnings",
    "goal_limit",
    "integrated",
    "UNDO_TRAILER",
    "undo_trailer",
    "integrations",
    "integrate_trailer",
    "worktree_states",
    "worktree_slug",
    "cleanable",
    "authors",
    "base_signers",
    "blocked_reasons",
    "body_sections",
    "bots_of",
    "build_spec_history",
    "check_repo",
    "config_at",
    "container_statuses",
    "convert_proposal",
    "design_paths",
    "EXPLORATION_HOME",
    "exploration_directions",
    "exploration_misplaced",
    "exploration_rounds",
    "files_matching",
    "find_spec_by_id",
    "find_spec_in_diff",
    "find_specs_in_diff",
    "change_specs",
    "goal_command",
    "tests_with",
    "add_revision",
    "revise_target",
    "threat_models",
    "THREAT_MODELS",
    "flag_cleanup",
    "frozen_docs",
    "frozen_paths",
    "plan_paths",
    "observes",
    "ID_PREFIXES",
    "WORK_ID",
    "next_id",
    "group",
    "handoff_counts",
    "team_decisions",
    "has_front_matter",
    "is_duplicate",
    "is_me",
    "is_object",
    "is_signing_configured",
    "item_priority",
    "knowledge_action_how",
    "latest_handoff",
    "item_files",
    "link_doc",
    "load_exploration",
    "load_local_approvals",
    "load_object",
    "load_proposal",
    "my_identities",
    "needs",
    "needs_spec_approval",
    "new_contract",
    "new_doc",
    "new_exploration",
    "new_object",
    "new_repo_doc",
    "object_files",
    "objects_at",
    "outcome_due",
    "overdue_flags",
    "parse_change_block",
    "proposal_hash",
    "proposal_matrix",
    "proposal_status",
    "read_at",
    "record_decision",
    "record_local_approval",
    "required_docs",
    "retries_used",
    "role_ids",
    "round_screenshots",
    "set_outcome",
    "signers_path",
    "spec_hash",
    "spec_history_markdown",
    "spec_status",
    "spec_template",
    "status_transitions",
    "status_unblocks",
    "stored_status",
    "strip_handoffs",
    "task_states",
    "tests_files",
    "triage_state",
    "unready_for_approval",
    "spec_approval_problems",
    "validate_file",
    "validate_next_step",
    "waiting_on",
    "why",
    "why_text",
    "with_defaults",
]

if TYPE_CHECKING:
    from aidd.workitems.approval_ledger import APPROVALS_REF as APPROVALS_REF
    from aidd.workitems.approval_ledger import MERGE_TRAILER as MERGE_TRAILER
    from aidd.workitems.approval_ledger import STANDING_SCOPES as STANDING_SCOPES
    from aidd.workitems.approval_ledger import approve_merge_line as approve_merge_line
    from aidd.workitems.approval_ledger import approve_spec_line as approve_spec_line
    from aidd.workitems.approval_ledger import base_signers as base_signers
    from aidd.workitems.approval_ledger import confirmed_in as confirmed_in
    from aidd.workitems.approval_ledger import day as day
    from aidd.workitems.approval_ledger import is_signing_configured as is_signing_configured
    from aidd.workitems.approval_ledger import live_standing as live_standing
    from aidd.workitems.approval_ledger import live_standing_for as live_standing_for
    from aidd.workitems.approval_ledger import load_local_approvals as load_local_approvals
    from aidd.workitems.approval_ledger import record_local_approval as record_local_approval
    from aidd.workitems.approval_ledger import ship_decision as ship_decision
    from aidd.workitems.approval_ledger import ship_said as ship_said
    from aidd.workitems.approval_ledger import ship_said_for as ship_said_for
    from aidd.workitems.approval_ledger import ship_said_line as ship_said_line
    from aidd.workitems.approval_ledger import signers_path as signers_path
    from aidd.workitems.approval_ledger import since_text as since_text
    from aidd.workitems.approval_ledger import standing_covers as standing_covers
    from aidd.workitems.approval_ledger import standing_line as standing_line
    from aidd.workitems.approval_ledger import with_login as with_login
    from aidd.workitems.authoring import BASE_PATTERN as BASE_PATTERN
    from aidd.workitems.authoring import CHANGE_ORDERS as CHANGE_ORDERS
    from aidd.workitems.authoring import DOC_KINDS_NEW as DOC_KINDS_NEW
    from aidd.workitems.authoring import DOC_TEMPLATES as DOC_TEMPLATES
    from aidd.workitems.authoring import LIVING_DOCS as LIVING_DOCS
    from aidd.workitems.authoring import REPO_DOCS as REPO_DOCS
    from aidd.workitems.authoring import UNLINKED_DOCS as UNLINKED_DOCS
    from aidd.workitems.authoring import NewDoc as NewDoc
    from aidd.workitems.authoring import NewObject as NewObject
    from aidd.workitems.authoring import link_doc as link_doc
    from aidd.workitems.authoring import new_contract as new_contract
    from aidd.workitems.authoring import new_doc as new_doc
    from aidd.workitems.authoring import new_object as new_object
    from aidd.workitems.authoring import new_repo_doc as new_repo_doc
    from aidd.workitems.authoring import required_docs as required_docs
    from aidd.workitems.authoring import spec_template as spec_template
    from aidd.workitems.backlog import WORK_KINDS as WORK_KINDS
    from aidd.workitems.backlog import group as group
    from aidd.workitems.backlog import is_duplicate as is_duplicate
    from aidd.workitems.backlog import waiting_on as waiting_on
    from aidd.workitems.backlog import why as why
    from aidd.workitems.backlog import why_text as why_text
    from aidd.workitems.branch_kinds import EXPLORE_PREFIX as EXPLORE_PREFIX
    from aidd.workitems.branch_kinds import GOAL_TRAILER as GOAL_TRAILER
    from aidd.workitems.branch_kinds import builds_on as builds_on
    from aidd.workitems.branch_kinds import current_branch as current_branch
    from aidd.workitems.branch_kinds import edits_held as edits_held
    from aidd.workitems.branch_kinds import explore_note as explore_note
    from aidd.workitems.branch_kinds import goal_of as goal_of
    from aidd.workitems.branch_kinds import is_explore as is_explore
    from aidd.workitems.branch_specs import active_specs as active_specs
    from aidd.workitems.branch_specs import carried_specs as carried_specs
    from aidd.workitems.branch_specs import change_specs as change_specs
    from aidd.workitems.branch_specs import find_spec_in_diff as find_spec_in_diff
    from aidd.workitems.branch_specs import find_specs_in_diff as find_specs_in_diff
    from aidd.workitems.derived_status import CAN_WAIT as CAN_WAIT
    from aidd.workitems.derived_status import DEFAULT_ROUTES as DEFAULT_ROUTES
    from aidd.workitems.derived_status import PRIORITIES as PRIORITIES
    from aidd.workitems.derived_status import RELEASED as RELEASED
    from aidd.workitems.derived_status import UNBLOCKS as UNBLOCKS
    from aidd.workitems.derived_status import Facts as Facts
    from aidd.workitems.derived_status import Observer as Observer
    from aidd.workitems.derived_status import approval_holds as approval_holds
    from aidd.workitems.derived_status import blocked_reasons as blocked_reasons
    from aidd.workitems.derived_status import container_statuses as container_statuses
    from aidd.workitems.derived_status import item_priority as item_priority
    from aidd.workitems.derived_status import needs_spec_approval as needs_spec_approval
    from aidd.workitems.derived_status import outcome_due as outcome_due
    from aidd.workitems.derived_status import retries_used as retries_used
    from aidd.workitems.derived_status import spec_status as spec_status
    from aidd.workitems.derived_status import status_unblocks as status_unblocks
    from aidd.workitems.derived_status import stored_status as stored_status
    from aidd.workitems.derived_status import task_states as task_states
    from aidd.workitems.due_dates import flag_cleanup as flag_cleanup
    from aidd.workitems.due_dates import knowledge_action_how as knowledge_action_how
    from aidd.workitems.due_dates import overdue_flags as overdue_flags
    from aidd.workitems.explorations import DIRECTION_HEADING as DIRECTION_HEADING
    from aidd.workitems.explorations import EXPLORATION_FILE as EXPLORATION_FILE
    from aidd.workitems.explorations import EXPLORATION_HOME as EXPLORATION_HOME
    from aidd.workitems.explorations import ROUNDS_DIR as ROUNDS_DIR
    from aidd.workitems.explorations import body_sections as body_sections
    from aidd.workitems.explorations import exploration_directions as exploration_directions
    from aidd.workitems.explorations import exploration_misplaced as exploration_misplaced
    from aidd.workitems.explorations import exploration_rounds as exploration_rounds
    from aidd.workitems.explorations import load_exploration as load_exploration
    from aidd.workitems.explorations import new_exploration as new_exploration
    from aidd.workitems.explorations import round_screenshots as round_screenshots
    from aidd.workitems.goal_history import INTEGRATE_TRAILER as INTEGRATE_TRAILER
    from aidd.workitems.goal_history import MAX_BRANCH_DAYS as MAX_BRANCH_DAYS
    from aidd.workitems.goal_history import MAX_GOAL_DAYS as MAX_GOAL_DAYS
    from aidd.workitems.goal_history import MAX_OPEN_BRANCHES as MAX_OPEN_BRANCHES
    from aidd.workitems.goal_history import UNDO_TRAILER as UNDO_TRAILER
    from aidd.workitems.goal_history import flow_warnings as flow_warnings
    from aidd.workitems.goal_history import goal_branches as goal_branches
    from aidd.workitems.goal_history import goal_facts as goal_facts
    from aidd.workitems.goal_history import goal_limit as goal_limit
    from aidd.workitems.goal_history import goal_warnings as goal_warnings
    from aidd.workitems.goal_history import independent_tips as independent_tips
    from aidd.workitems.goal_history import integrate_trailer as integrate_trailer
    from aidd.workitems.goal_history import integrated as integrated
    from aidd.workitems.goal_history import integrations as integrations
    from aidd.workitems.goal_history import undo_trailer as undo_trailer
    from aidd.workitems.goal_history import work_branches as work_branches
    from aidd.workitems.handoff_notes import HANDOFF_FENCE as HANDOFF_FENCE
    from aidd.workitems.handoff_notes import handoff_counts as handoff_counts
    from aidd.workitems.handoff_notes import latest_handoff as latest_handoff
    from aidd.workitems.handoff_notes import needs as needs
    from aidd.workitems.handoff_notes import role_ids as role_ids
    from aidd.workitems.handoff_notes import team_decisions as team_decisions
    from aidd.workitems.item_folder import item_files as item_files
    from aidd.workitems.objects import OPS_DIRS as OPS_DIRS
    from aidd.workitems.objects import files_matching as files_matching
    from aidd.workitems.objects import find_spec_by_id as find_spec_by_id
    from aidd.workitems.objects import has_front_matter as has_front_matter
    from aidd.workitems.objects import is_object as is_object
    from aidd.workitems.objects import object_files as object_files
    from aidd.workitems.proposal import convert_proposal as convert_proposal
    from aidd.workitems.proposal import load_proposal as load_proposal
    from aidd.workitems.proposal import proposal_matrix as proposal_matrix
    from aidd.workitems.proposal import record_decision as record_decision
    from aidd.workitems.repo_reads import MAX_OBJECTS as MAX_OBJECTS
    from aidd.workitems.repo_reads import authors as authors
    from aidd.workitems.repo_reads import config_at as config_at
    from aidd.workitems.repo_reads import objects_at as objects_at
    from aidd.workitems.repo_reads import read_at as read_at
    from aidd.workitems.small_goals import GOAL_PREFIX as GOAL_PREFIX
    from aidd.workitems.small_goals import SHIPS as SHIPS
    from aidd.workitems.small_goals import goal_branch as goal_branch
    from aidd.workitems.small_goals import is_launch as is_launch
    from aidd.workitems.small_goals import launches_at as launches_at
    from aidd.workitems.small_goals import ships as ships
    from aidd.workitems.small_goals import small_goal_checks as small_goal_checks
    from aidd.workitems.spec_file import ID_PREFIXES as ID_PREFIXES
    from aidd.workitems.spec_file import THREAT_MODELS as THREAT_MODELS
    from aidd.workitems.spec_file import WORK_ID as WORK_ID
    from aidd.workitems.spec_file import acceptance_ids as acceptance_ids
    from aidd.workitems.spec_file import add_revision as add_revision
    from aidd.workitems.spec_file import design_paths as design_paths
    from aidd.workitems.spec_file import frozen_docs as frozen_docs
    from aidd.workitems.spec_file import frozen_paths as frozen_paths
    from aidd.workitems.spec_file import goal_command as goal_command
    from aidd.workitems.spec_file import load_object as load_object
    from aidd.workitems.spec_file import next_id as next_id
    from aidd.workitems.spec_file import observes as observes
    from aidd.workitems.spec_file import parse_change_block as parse_change_block
    from aidd.workitems.spec_file import plan_paths as plan_paths
    from aidd.workitems.spec_file import proposal_hash as proposal_hash
    from aidd.workitems.spec_file import proposal_status as proposal_status
    from aidd.workitems.spec_file import revise_target as revise_target
    from aidd.workitems.spec_file import set_outcome as set_outcome
    from aidd.workitems.spec_file import spec_hash as spec_hash
    from aidd.workitems.spec_file import strip_handoffs as strip_handoffs
    from aidd.workitems.spec_file import tests_files as tests_files
    from aidd.workitems.spec_file import tests_with as tests_with
    from aidd.workitems.spec_file import threat_models as threat_models
    from aidd.workitems.spec_file import with_defaults as with_defaults
    from aidd.workitems.spec_history import build_spec_history as build_spec_history
    from aidd.workitems.spec_history import spec_history_markdown as spec_history_markdown
    from aidd.workitems.spec_history import status_transitions as status_transitions
    from aidd.workitems.steps import AGENT as AGENT
    from aidd.workitems.steps import APPROVER as APPROVER
    from aidd.workitems.steps import AUTHOR as AUTHOR
    from aidd.workitems.steps import COMMIT as COMMIT
    from aidd.workitems.steps import PERSON as PERSON
    from aidd.workitems.steps import STEP_CODES as STEP_CODES
    from aidd.workitems.triage import bots_of as bots_of
    from aidd.workitems.triage import is_me as is_me
    from aidd.workitems.triage import my_identities as my_identities
    from aidd.workitems.triage import triage_state as triage_state
    from aidd.workitems.typed_words import grants as grants
    from aidd.workitems.typed_words import parse_typed as parse_typed
    from aidd.workitems.validation import check_repo as check_repo
    from aidd.workitems.validation import spec_approval_problems as spec_approval_problems
    from aidd.workitems.validation import unready_for_approval as unready_for_approval
    from aidd.workitems.validation import validate_file as validate_file
    from aidd.workitems.validation import validate_next_step as validate_next_step
    from aidd.workitems.worktree_list import cleanable as cleanable
    from aidd.workitems.worktree_list import worktree_slug as worktree_slug
    from aidd.workitems.worktree_list import worktree_states as worktree_states
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "AGENT": "steps",
            "APPROVALS_REF": "approval_ledger",
            "APPROVER": "steps",
            "AUTHOR": "steps",
            "CAN_WAIT": "derived_status",
            "CHANGE_ORDERS": "authoring",
            "COMMIT": "steps",
            "DEFAULT_ROUTES": "derived_status",
            "DIRECTION_HEADING": "explorations",
            "DOC_KINDS_NEW": "authoring",
            "DOC_TEMPLATES": "authoring",
            "EXPLORATION_FILE": "explorations",
            "Facts": "derived_status",
            "HANDOFF_FENCE": "handoff_notes",
            "LIVING_DOCS": "authoring",
            "MAX_OBJECTS": "repo_reads",
            "MERGE_TRAILER": "approval_ledger",
            "NewDoc": "authoring",
            "NewObject": "authoring",
            "BASE_PATTERN": "authoring",
            "OPS_DIRS": "objects",
            "Observer": "derived_status",
            "PERSON": "steps",
            "PRIORITIES": "derived_status",
            "RELEASED": "derived_status",
            "REPO_DOCS": "authoring",
            "ROUNDS_DIR": "explorations",
            "STEP_CODES": "steps",
            "UNBLOCKS": "derived_status",
            "UNLINKED_DOCS": "authoring",
            "WORK_KINDS": "backlog",
            "acceptance_ids": "spec_file",
            "active_specs": "branch_specs",
            "carried_specs": "branch_specs",
            "approval_holds": "derived_status",
            "approve_merge_line": "approval_ledger",
            "STANDING_SCOPES": "approval_ledger",
            "live_standing": "approval_ledger",
            "live_standing_for": "approval_ledger",
            "ship_decision": "approval_ledger",
            "ship_said": "approval_ledger",
            "ship_said_for": "approval_ledger",
            "ship_said_line": "approval_ledger",
            "standing_covers": "approval_ledger",
            "standing_line": "approval_ledger",
            "day": "approval_ledger",
            "goal_of": "branch_kinds",
            "current_branch": "branch_kinds",
            "EXPLORE_PREFIX": "branch_kinds",
            "explore_note": "branch_kinds",
            "is_explore": "branch_kinds",
            "edits_held": "branch_kinds",
            "builds_on": "branch_kinds",
            "GOAL_PREFIX": "small_goals",
            "GOAL_TRAILER": "branch_kinds",
            "SHIPS": "small_goals",
            "goal_branch": "small_goals",
            "is_launch": "small_goals",
            "launches_at": "small_goals",
            "ships": "small_goals",
            "small_goal_checks": "small_goals",
            "INTEGRATE_TRAILER": "goal_history",
            "MAX_GOAL_DAYS": "goal_history",
            "goal_branches": "goal_history",
            "goal_facts": "goal_history",
            "independent_tips": "goal_history",
            "flow_warnings": "goal_history",
            "work_branches": "goal_history",
            "MAX_OPEN_BRANCHES": "goal_history",
            "MAX_BRANCH_DAYS": "goal_history",
            "goal_warnings": "goal_history",
            "goal_limit": "goal_history",
            "integrated": "goal_history",
            "UNDO_TRAILER": "goal_history",
            "undo_trailer": "goal_history",
            "integrations": "goal_history",
            "integrate_trailer": "goal_history",
            "worktree_states": "worktree_list",
            "worktree_slug": "worktree_list",
            "cleanable": "worktree_list",
            "approve_spec_line": "approval_ledger",
            "confirmed_in": "approval_ledger",
            "with_login": "approval_ledger",
            "parse_typed": "typed_words",
            "grants": "typed_words",
            "since_text": "approval_ledger",
            "authors": "repo_reads",
            "base_signers": "approval_ledger",
            "blocked_reasons": "derived_status",
            "body_sections": "explorations",
            "bots_of": "triage",
            "build_spec_history": "spec_history",
            "check_repo": "validation",
            "config_at": "repo_reads",
            "container_statuses": "derived_status",
            "convert_proposal": "proposal",
            "design_paths": "spec_file",
            "EXPLORATION_HOME": "explorations",
            "exploration_directions": "explorations",
            "exploration_misplaced": "explorations",
            "exploration_rounds": "explorations",
            "files_matching": "objects",
            "find_spec_by_id": "objects",
            "find_spec_in_diff": "branch_specs",
            "find_specs_in_diff": "branch_specs",
            "change_specs": "branch_specs",
            "goal_command": "spec_file",
            "tests_with": "spec_file",
            "add_revision": "spec_file",
            "revise_target": "spec_file",
            "threat_models": "spec_file",
            "THREAT_MODELS": "spec_file",
            "flag_cleanup": "due_dates",
            "frozen_docs": "spec_file",
            "frozen_paths": "spec_file",
            "plan_paths": "spec_file",
            "observes": "spec_file",
            "ID_PREFIXES": "spec_file",
            "WORK_ID": "spec_file",
            "next_id": "spec_file",
            "group": "backlog",
            "has_front_matter": "objects",
            "is_duplicate": "backlog",
            "is_me": "triage",
            "is_object": "objects",
            "is_signing_configured": "approval_ledger",
            "item_priority": "derived_status",
            "knowledge_action_how": "due_dates",
            "latest_handoff": "handoff_notes",
            "handoff_counts": "handoff_notes",
            "team_decisions": "handoff_notes",
            "item_files": "item_folder",
            "link_doc": "authoring",
            "load_exploration": "explorations",
            "load_local_approvals": "approval_ledger",
            "load_object": "spec_file",
            "load_proposal": "proposal",
            "my_identities": "triage",
            "needs": "handoff_notes",
            "needs_spec_approval": "derived_status",
            "new_contract": "authoring",
            "new_doc": "authoring",
            "new_exploration": "explorations",
            "new_object": "authoring",
            "new_repo_doc": "authoring",
            "object_files": "objects",
            "objects_at": "repo_reads",
            "outcome_due": "derived_status",
            "overdue_flags": "due_dates",
            "parse_change_block": "spec_file",
            "proposal_hash": "spec_file",
            "proposal_matrix": "proposal",
            "record_decision": "proposal",
            "proposal_status": "spec_file",
            "read_at": "repo_reads",
            "record_local_approval": "approval_ledger",
            "required_docs": "authoring",
            "retries_used": "derived_status",
            "role_ids": "handoff_notes",
            "round_screenshots": "explorations",
            "set_outcome": "spec_file",
            "signers_path": "approval_ledger",
            "spec_hash": "spec_file",
            "spec_history_markdown": "spec_history",
            "spec_status": "derived_status",
            "spec_template": "authoring",
            "status_transitions": "spec_history",
            "status_unblocks": "derived_status",
            "stored_status": "derived_status",
            "strip_handoffs": "spec_file",
            "task_states": "derived_status",
            "tests_files": "spec_file",
            "triage_state": "triage",
            "unready_for_approval": "validation",
            "spec_approval_problems": "validation",
            "validate_file": "validation",
            "validate_next_step": "validation",
            "waiting_on": "backlog",
            "why": "backlog",
            "why_text": "backlog",
            "with_defaults": "spec_file",
        },
    )
