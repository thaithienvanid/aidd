"""Work items: Specs, Intents, proposals, and explorations, and the fields a team tracks them by: the stored
status, triage, typed relations, labels, the why chain, and the handoff note.

A tracker (Jira, Linear, Plane) is optional: the files in git are the record, and backlog, triage, and handoff_notes read
the few fields that make them a backlog.

- **Status**: stored in the front matter (`status`, with `approved_by` and `approved_at` once approved); never derived.
- **Triage**: a Spec an agent suggested (`suggested_by`) stays a draft until a person records `triage`.
- **Relations**: `blocked_by` and the other typed links; `aidd validate` checks targets and cycles, `aidd status` shows blocks.
- **Handoff note**: an ```aidd-handoff YAML block an agent writes when it stops; `aidd status` reads it.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "ADR_FOLDER",
    "AGENT",
    "CAN_WAIT",
    "CHANGE_ORDERS",
    "DEFAULT_COMMITS",
    "DIRECTION_HEADING",
    "DOC_TEMPLATES",
    "DOC_TYPES_NEW",
    "EXPLORATION_FILE",
    "EXPLORATION_HOME",
    "FOLDED_FIX",
    "FOLDED_TYPES",
    "HANDOFF_FENCE",
    "ID_PREFIXES",
    "LANDED_STATUSES",
    "LIVING_DOCS",
    "MAX_COMMITS",
    "MAX_RETRIES",
    "NOTE",
    "OPS_DIRS",
    "PAST_APPROVAL",
    "PERSON",
    "PRIORITIES",
    "REPO_DOCS",
    "ROUNDS_DIR",
    "SECTION_MANIFESTS",
    "SPEC",
    "STEP_CODES",
    "STEP_MEANINGS",
    "STEP_WORDS",
    "THREAT_MODELS",
    "UNBLOCKS",
    "UNLINKED_DOCS",
    "UNLINKED_NEXT",
    "WARNING",
    "WORK_ID",
    "WORK_TYPES",
    "NewDoc",
    "NewObject",
    "Shown",
    "acceptance_ids",
    "add_branch_facts",
    "all_branches_work",
    "assisted_by_spelling",
    "assisted_by_values",
    "blocked_reasons",
    "body_sections",
    "branch_item",
    "check_repo",
    "command_path_literals",
    "comment_id_direction",
    "config_at",
    "deprecation_calendar",
    "deprecation_removal",
    "design_paths",
    "exploration_directions",
    "exploration_misplaced",
    "exploration_rounds",
    "files_matching",
    "find_slice",
    "find_spec_by_id",
    "find_specs_in_diff",
    "finished",
    "flag_cleanup",
    "folder_scope",
    "frozen_docs",
    "frozen_files",
    "frozen_paths",
    "frozen_section",
    "group",
    "handoff_blocks",
    "has_front_matter",
    "history_text",
    "holder_of",
    "id_order",
    "in_delivery_team",
    "index_path",
    "intent_statuses",
    "is_duplicate",
    "is_error",
    "is_id",
    "is_object",
    "item_priority",
    "link_doc",
    "load_exploration",
    "load_object",
    "new_contract",
    "new_doc",
    "new_exploration",
    "new_object",
    "new_repo_doc",
    "next_id",
    "object_files",
    "open_work",
    "outcome_due",
    "overdue_deprecations",
    "overdue_flags",
    "pending_removals",
    "phase_heading",
    "phase_line",
    "phases_of",
    "proposal_hash",
    "proposal_status",
    "raw_emergencies",
    "required_docs",
    "retries_used",
    "role_ids",
    "round_comment_files",
    "round_screenshots",
    "scope_over_acceptance_tests",
    "slice_ids",
    "slice_lines",
    "spec_stage",
    "spec_status",
    "spec_step",
    "spec_template",
    "status_text",
    "status_unblocks",
    "statuses",
    "step_words",
    "stored_status",
    "task_states",
    "team_names",
    "template_text",
    "templates_dir",
    "test_sections_in",
    "tests_files",
    "threat_models",
    "trace",
    "trace_text",
    "validate_file",
    "validate_next_step",
    "waiting_on",
    "why",
    "work_ids_in",
    "work_item_history",
    "work_items_history",
]

if TYPE_CHECKING:
    from aidd.workitems.all_branches import all_branches_work as all_branches_work
    from aidd.workitems.all_branches import index_path as index_path
    from aidd.workitems.authoring import ADR_FOLDER as ADR_FOLDER
    from aidd.workitems.authoring import CHANGE_ORDERS as CHANGE_ORDERS
    from aidd.workitems.authoring import DOC_TEMPLATES as DOC_TEMPLATES
    from aidd.workitems.authoring import DOC_TYPES_NEW as DOC_TYPES_NEW
    from aidd.workitems.authoring import LIVING_DOCS as LIVING_DOCS
    from aidd.workitems.authoring import REPO_DOCS as REPO_DOCS
    from aidd.workitems.authoring import UNLINKED_DOCS as UNLINKED_DOCS
    from aidd.workitems.authoring import UNLINKED_NEXT as UNLINKED_NEXT
    from aidd.workitems.authoring import NewDoc as NewDoc
    from aidd.workitems.authoring import NewObject as NewObject
    from aidd.workitems.authoring import folder_scope as folder_scope
    from aidd.workitems.authoring import link_doc as link_doc
    from aidd.workitems.authoring import new_contract as new_contract
    from aidd.workitems.authoring import new_doc as new_doc
    from aidd.workitems.authoring import new_object as new_object
    from aidd.workitems.authoring import new_repo_doc as new_repo_doc
    from aidd.workitems.authoring import required_docs as required_docs
    from aidd.workitems.authoring import scope_over_acceptance_tests as scope_over_acceptance_tests
    from aidd.workitems.authoring import spec_template as spec_template
    from aidd.workitems.authoring import template_text as template_text
    from aidd.workitems.authoring import templates_dir as templates_dir
    from aidd.workitems.backlog import WORK_TYPES as WORK_TYPES
    from aidd.workitems.backlog import group as group
    from aidd.workitems.backlog import is_duplicate as is_duplicate
    from aidd.workitems.backlog import waiting_on as waiting_on
    from aidd.workitems.backlog import why as why
    from aidd.workitems.commit_text import assisted_by_spelling as assisted_by_spelling
    from aidd.workitems.commit_text import assisted_by_values as assisted_by_values
    from aidd.workitems.commit_text import work_ids_in as work_ids_in
    from aidd.workitems.current_work import add_branch_facts as add_branch_facts
    from aidd.workitems.current_work import branch_item as branch_item
    from aidd.workitems.current_work import open_work as open_work
    from aidd.workitems.due_dates import deprecation_calendar as deprecation_calendar
    from aidd.workitems.due_dates import deprecation_removal as deprecation_removal
    from aidd.workitems.due_dates import flag_cleanup as flag_cleanup
    from aidd.workitems.due_dates import overdue_deprecations as overdue_deprecations
    from aidd.workitems.due_dates import overdue_flags as overdue_flags
    from aidd.workitems.due_dates import pending_removals as pending_removals
    from aidd.workitems.explorations import DIRECTION_HEADING as DIRECTION_HEADING
    from aidd.workitems.explorations import EXPLORATION_FILE as EXPLORATION_FILE
    from aidd.workitems.explorations import EXPLORATION_HOME as EXPLORATION_HOME
    from aidd.workitems.explorations import ROUNDS_DIR as ROUNDS_DIR
    from aidd.workitems.explorations import body_sections as body_sections
    from aidd.workitems.explorations import comment_id_direction as comment_id_direction
    from aidd.workitems.explorations import exploration_directions as exploration_directions
    from aidd.workitems.explorations import exploration_misplaced as exploration_misplaced
    from aidd.workitems.explorations import exploration_rounds as exploration_rounds
    from aidd.workitems.explorations import load_exploration as load_exploration
    from aidd.workitems.explorations import new_exploration as new_exploration
    from aidd.workitems.explorations import round_comment_files as round_comment_files
    from aidd.workitems.explorations import round_screenshots as round_screenshots
    from aidd.workitems.handoff_notes import HANDOFF_FENCE as HANDOFF_FENCE
    from aidd.workitems.handoff_notes import handoff_blocks as handoff_blocks
    from aidd.workitems.handoff_notes import role_ids as role_ids
    from aidd.workitems.history import history_text as history_text
    from aidd.workitems.history import work_item_history as work_item_history
    from aidd.workitems.history import work_items_history as work_items_history
    from aidd.workitems.ids import id_order as id_order
    from aidd.workitems.ids import is_id as is_id
    from aidd.workitems.intents import holder_of as holder_of
    from aidd.workitems.intents import intent_statuses as intent_statuses
    from aidd.workitems.intents import phase_heading as phase_heading
    from aidd.workitems.intents import phase_line as phase_line
    from aidd.workitems.intents import phases_of as phases_of
    from aidd.workitems.intents import slice_ids as slice_ids
    from aidd.workitems.intents import slice_lines as slice_lines
    from aidd.workitems.intents import spec_stage as spec_stage
    from aidd.workitems.manifest_sections import SECTION_MANIFESTS as SECTION_MANIFESTS
    from aidd.workitems.manifest_sections import frozen_section as frozen_section
    from aidd.workitems.manifest_sections import test_sections_in as test_sections_in
    from aidd.workitems.objects import FOLDED_TYPES as FOLDED_TYPES
    from aidd.workitems.objects import OPS_DIRS as OPS_DIRS
    from aidd.workitems.objects import files_matching as files_matching
    from aidd.workitems.objects import find_spec_by_id as find_spec_by_id
    from aidd.workitems.objects import has_front_matter as has_front_matter
    from aidd.workitems.objects import is_object as is_object
    from aidd.workitems.objects import object_files as object_files
    from aidd.workitems.repo_reads import config_at as config_at
    from aidd.workitems.slice_start import find_slice as find_slice
    from aidd.workitems.spec_file import FOLDED_FIX as FOLDED_FIX
    from aidd.workitems.spec_file import ID_PREFIXES as ID_PREFIXES
    from aidd.workitems.spec_file import THREAT_MODELS as THREAT_MODELS
    from aidd.workitems.spec_file import WORK_ID as WORK_ID
    from aidd.workitems.spec_file import acceptance_ids as acceptance_ids
    from aidd.workitems.spec_file import command_path_literals as command_path_literals
    from aidd.workitems.spec_file import design_paths as design_paths
    from aidd.workitems.spec_file import find_specs_in_diff as find_specs_in_diff
    from aidd.workitems.spec_file import frozen_docs as frozen_docs
    from aidd.workitems.spec_file import frozen_files as frozen_files
    from aidd.workitems.spec_file import frozen_paths as frozen_paths
    from aidd.workitems.spec_file import load_object as load_object
    from aidd.workitems.spec_file import next_id as next_id
    from aidd.workitems.spec_file import proposal_hash as proposal_hash
    from aidd.workitems.spec_file import proposal_status as proposal_status
    from aidd.workitems.spec_file import tests_files as tests_files
    from aidd.workitems.spec_file import threat_models as threat_models
    from aidd.workitems.spec_warnings import statuses as statuses
    from aidd.workitems.status import CAN_WAIT as CAN_WAIT
    from aidd.workitems.status import LANDED_STATUSES as LANDED_STATUSES
    from aidd.workitems.status import MAX_RETRIES as MAX_RETRIES
    from aidd.workitems.status import PAST_APPROVAL as PAST_APPROVAL
    from aidd.workitems.status import PRIORITIES as PRIORITIES
    from aidd.workitems.status import SPEC as SPEC
    from aidd.workitems.status import UNBLOCKS as UNBLOCKS
    from aidd.workitems.status import blocked_reasons as blocked_reasons
    from aidd.workitems.status import finished as finished
    from aidd.workitems.status import item_priority as item_priority
    from aidd.workitems.status import outcome_due as outcome_due
    from aidd.workitems.status import retries_used as retries_used
    from aidd.workitems.status import spec_status as spec_status
    from aidd.workitems.status import status_unblocks as status_unblocks
    from aidd.workitems.status import stored_status as stored_status
    from aidd.workitems.status import task_states as task_states
    from aidd.workitems.steps import AGENT as AGENT
    from aidd.workitems.steps import PERSON as PERSON
    from aidd.workitems.steps import STEP_CODES as STEP_CODES
    from aidd.workitems.steps import STEP_MEANINGS as STEP_MEANINGS
    from aidd.workitems.steps import STEP_WORDS as STEP_WORDS
    from aidd.workitems.steps import step_words as step_words
    from aidd.workitems.tracing import DEFAULT_COMMITS as DEFAULT_COMMITS
    from aidd.workitems.tracing import MAX_COMMITS as MAX_COMMITS
    from aidd.workitems.tracing import trace as trace
    from aidd.workitems.tracing import trace_text as trace_text
    from aidd.workitems.validation import NOTE as NOTE
    from aidd.workitems.validation import WARNING as WARNING
    from aidd.workitems.validation import check_repo as check_repo
    from aidd.workitems.validation import is_error as is_error
    from aidd.workitems.validation import validate_file as validate_file
    from aidd.workitems.validation import validate_next_step as validate_next_step
    from aidd.workitems.work_list import Shown as Shown
    from aidd.workitems.work_list import in_delivery_team as in_delivery_team
    from aidd.workitems.work_list import raw_emergencies as raw_emergencies
    from aidd.workitems.work_list import spec_step as spec_step
    from aidd.workitems.work_list import status_text as status_text
    from aidd.workitems.work_list import team_names as team_names
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "ADR_FOLDER": "authoring",
            "AGENT": "steps",
            "CAN_WAIT": "status",
            "CHANGE_ORDERS": "authoring",
            "DEFAULT_COMMITS": "tracing",
            "DIRECTION_HEADING": "explorations",
            "DOC_TEMPLATES": "authoring",
            "DOC_TYPES_NEW": "authoring",
            "EXPLORATION_FILE": "explorations",
            "EXPLORATION_HOME": "explorations",
            "FOLDED_FIX": "spec_file",
            "FOLDED_TYPES": "objects",
            "HANDOFF_FENCE": "handoff_notes",
            "ID_PREFIXES": "spec_file",
            "LANDED_STATUSES": "status",
            "LIVING_DOCS": "authoring",
            "MAX_COMMITS": "tracing",
            "MAX_RETRIES": "status",
            "NOTE": "validation",
            "OPS_DIRS": "objects",
            "PAST_APPROVAL": "status",
            "PERSON": "steps",
            "PRIORITIES": "status",
            "REPO_DOCS": "authoring",
            "ROUNDS_DIR": "explorations",
            "SECTION_MANIFESTS": "manifest_sections",
            "SPEC": "status",
            "STEP_CODES": "steps",
            "STEP_MEANINGS": "steps",
            "STEP_WORDS": "steps",
            "THREAT_MODELS": "spec_file",
            "UNBLOCKS": "status",
            "UNLINKED_DOCS": "authoring",
            "UNLINKED_NEXT": "authoring",
            "WARNING": "validation",
            "WORK_ID": "spec_file",
            "WORK_TYPES": "backlog",
            "NewDoc": "authoring",
            "NewObject": "authoring",
            "Shown": "work_list",
            "acceptance_ids": "spec_file",
            "add_branch_facts": "current_work",
            "all_branches_work": "all_branches",
            "assisted_by_spelling": "commit_text",
            "assisted_by_values": "commit_text",
            "blocked_reasons": "status",
            "body_sections": "explorations",
            "branch_item": "current_work",
            "check_repo": "validation",
            "command_path_literals": "spec_file",
            "comment_id_direction": "explorations",
            "config_at": "repo_reads",
            "deprecation_calendar": "due_dates",
            "deprecation_removal": "due_dates",
            "design_paths": "spec_file",
            "exploration_directions": "explorations",
            "exploration_misplaced": "explorations",
            "exploration_rounds": "explorations",
            "files_matching": "objects",
            "find_slice": "slice_start",
            "find_spec_by_id": "objects",
            "find_specs_in_diff": "spec_file",
            "finished": "status",
            "flag_cleanup": "due_dates",
            "folder_scope": "authoring",
            "frozen_docs": "spec_file",
            "frozen_files": "spec_file",
            "frozen_paths": "spec_file",
            "frozen_section": "manifest_sections",
            "group": "backlog",
            "handoff_blocks": "handoff_notes",
            "has_front_matter": "objects",
            "history_text": "history",
            "holder_of": "intents",
            "id_order": "ids",
            "in_delivery_team": "work_list",
            "index_path": "all_branches",
            "intent_statuses": "intents",
            "is_duplicate": "backlog",
            "is_error": "validation",
            "is_id": "ids",
            "is_object": "objects",
            "item_priority": "status",
            "link_doc": "authoring",
            "load_exploration": "explorations",
            "load_object": "spec_file",
            "new_contract": "authoring",
            "new_doc": "authoring",
            "new_exploration": "explorations",
            "new_object": "authoring",
            "new_repo_doc": "authoring",
            "next_id": "spec_file",
            "object_files": "objects",
            "open_work": "current_work",
            "outcome_due": "status",
            "overdue_deprecations": "due_dates",
            "overdue_flags": "due_dates",
            "pending_removals": "due_dates",
            "phase_heading": "intents",
            "phase_line": "intents",
            "phases_of": "intents",
            "proposal_hash": "spec_file",
            "proposal_status": "spec_file",
            "raw_emergencies": "work_list",
            "required_docs": "authoring",
            "retries_used": "status",
            "role_ids": "handoff_notes",
            "round_comment_files": "explorations",
            "round_screenshots": "explorations",
            "scope_over_acceptance_tests": "authoring",
            "slice_ids": "intents",
            "slice_lines": "intents",
            "spec_stage": "intents",
            "spec_status": "status",
            "spec_step": "work_list",
            "spec_template": "authoring",
            "status_text": "work_list",
            "status_unblocks": "status",
            "statuses": "spec_warnings",
            "step_words": "steps",
            "stored_status": "status",
            "task_states": "status",
            "team_names": "work_list",
            "template_text": "authoring",
            "templates_dir": "authoring",
            "test_sections_in": "manifest_sections",
            "tests_files": "spec_file",
            "threat_models": "spec_file",
            "trace": "tracing",
            "trace_text": "tracing",
            "validate_file": "validation",
            "validate_next_step": "validation",
            "waiting_on": "backlog",
            "why": "backlog",
            "work_ids_in": "commit_text",
            "work_item_history": "history",
            "work_items_history": "history",
        },
    )
