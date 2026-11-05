"""Work items: Specs, Intents, proposals, and explorations, and the fields a team tracks them by: the stored
status, triage, `blocked_by`, the why chain, and the handoff note.

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
    "AGENT",
    "ASKS_APPROVAL",
    "BEFORE_IMPLEMENT",
    "CAN_WAIT",
    "CHANGE_ORDERS",
    "DEFAULT_CHANGE_TYPE",
    "DEFAULT_COMMITS",
    "DIRECTION_HEADING",
    "DOC_TEMPLATES",
    "EXPLORATION_FILE",
    "EXPLORATION_HOME",
    "FROZEN_STATUSES",
    "HANDOFF_FENCE",
    "ID_PREFIXES",
    "IMPLEMENTING",
    "LIVING_DOCS",
    "MAX_COMMITS",
    "NOTE",
    "OPEN_GROUPS",
    "OPS_DIRS",
    "PAST_APPROVAL",
    "PERSON",
    "PLACEHOLDER",
    "REPO_DOCS",
    "ROUNDS_DIR",
    "SPEC_STATUSES",
    "STEP_CODES",
    "STEP_MEANINGS",
    "TEST_PLANS",
    "THREAT_MODELS",
    "UNLINKED_DOCS",
    "WARNING",
    "WORK_ID",
    "WORK_TYPES",
    "NewDoc",
    "NewObject",
    "Shown",
    "acceptance_ids",
    "add_branch_facts",
    "adr_folder",
    "all_branches_work",
    "apply_row",
    "assisted_by_spelling",
    "assisted_by_values",
    "body_sections",
    "branch_item",
    "change_type_of",
    "check_repo",
    "comment_id_direction",
    "config_at",
    "decision_states",
    "design_paths",
    "exploration_directions",
    "exploration_misplaced",
    "exploration_rounds",
    "find_slice",
    "find_spec_by_id",
    "find_specs_in_diff",
    "folder_scope",
    "frozen_change",
    "frozen_files",
    "frozen_test_files",
    "handoff_blocks",
    "has_front_matter",
    "hidden_characters",
    "history_text",
    "holder_of",
    "in_delivery_team",
    "index_path",
    "irreversible_of",
    "is_error",
    "is_id",
    "is_saved_request",
    "last_slice",
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
    "one_phase",
    "open_work",
    "phase_heading",
    "raw_emergencies",
    "read_document",
    "record_agreement",
    "required_docs",
    "role_identity",
    "round_comment_files",
    "round_screenshots",
    "running_roles",
    "running_roles_text",
    "scope_over_acceptance_tests",
    "slice_ids",
    "sort_intent_relations",
    "sort_relations",
    "spec_status",
    "spec_template",
    "stage_of_step",
    "stages",
    "status_findings",
    "status_text",
    "step_words",
    "stored_status",
    "team_names",
    "tests_files",
    "threat_models",
    "todays_shape",
    "trace",
    "trace_text",
    "validate_file",
    "validate_findings",
    "validate_next_step",
    "work_ids_in",
    "work_item_history",
    "work_items_history",
]

if TYPE_CHECKING:
    from aidd.workitems.agreement import record_agreement as record_agreement
    from aidd.workitems.all_branches import all_branches_work as all_branches_work
    from aidd.workitems.all_branches import index_path as index_path
    from aidd.workitems.authoring import CHANGE_ORDERS as CHANGE_ORDERS
    from aidd.workitems.authoring import DOC_TEMPLATES as DOC_TEMPLATES
    from aidd.workitems.authoring import LIVING_DOCS as LIVING_DOCS
    from aidd.workitems.authoring import REPO_DOCS as REPO_DOCS
    from aidd.workitems.authoring import UNLINKED_DOCS as UNLINKED_DOCS
    from aidd.workitems.authoring import NewDoc as NewDoc
    from aidd.workitems.authoring import NewObject as NewObject
    from aidd.workitems.authoring import adr_folder as adr_folder
    from aidd.workitems.authoring import folder_scope as folder_scope
    from aidd.workitems.authoring import link_doc as link_doc
    from aidd.workitems.authoring import new_contract as new_contract
    from aidd.workitems.authoring import new_doc as new_doc
    from aidd.workitems.authoring import new_object as new_object
    from aidd.workitems.authoring import new_repo_doc as new_repo_doc
    from aidd.workitems.authoring import required_docs as required_docs
    from aidd.workitems.authoring import scope_over_acceptance_tests as scope_over_acceptance_tests
    from aidd.workitems.authoring import spec_template as spec_template
    from aidd.workitems.backlog import WORK_TYPES as WORK_TYPES
    from aidd.workitems.commit_text import assisted_by_spelling as assisted_by_spelling
    from aidd.workitems.commit_text import assisted_by_values as assisted_by_values
    from aidd.workitems.commit_text import work_ids_in as work_ids_in
    from aidd.workitems.current_work import add_branch_facts as add_branch_facts
    from aidd.workitems.current_work import branch_item as branch_item
    from aidd.workitems.current_work import open_work as open_work
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
    from aidd.workitems.finding_lists import status_findings as status_findings
    from aidd.workitems.finding_lists import validate_findings as validate_findings
    from aidd.workitems.frozen_tests import FROZEN_STATUSES as FROZEN_STATUSES
    from aidd.workitems.frozen_tests import frozen_test_files as frozen_test_files
    from aidd.workitems.handoff_notes import HANDOFF_FENCE as HANDOFF_FENCE
    from aidd.workitems.handoff_notes import decision_states as decision_states
    from aidd.workitems.handoff_notes import handoff_blocks as handoff_blocks
    from aidd.workitems.handoff_notes import hidden_characters as hidden_characters
    from aidd.workitems.history import history_text as history_text
    from aidd.workitems.history import work_item_history as work_item_history
    from aidd.workitems.history import work_items_history as work_items_history
    from aidd.workitems.ids import is_id as is_id
    from aidd.workitems.intents import holder_of as holder_of
    from aidd.workitems.intents import phase_heading as phase_heading
    from aidd.workitems.intents import slice_ids as slice_ids
    from aidd.workitems.intents import stage_of_step as stage_of_step
    from aidd.workitems.intents import stages as stages
    from aidd.workitems.objects import OPS_DIRS as OPS_DIRS
    from aidd.workitems.objects import find_spec_by_id as find_spec_by_id
    from aidd.workitems.objects import has_front_matter as has_front_matter
    from aidd.workitems.objects import is_saved_request as is_saved_request
    from aidd.workitems.objects import object_files as object_files
    from aidd.workitems.objects import read_document as read_document
    from aidd.workitems.old_shape import DEFAULT_CHANGE_TYPE as DEFAULT_CHANGE_TYPE
    from aidd.workitems.old_shape import apply_row as apply_row
    from aidd.workitems.old_shape import change_type_of as change_type_of
    from aidd.workitems.old_shape import irreversible_of as irreversible_of
    from aidd.workitems.old_shape import last_slice as last_slice
    from aidd.workitems.old_shape import one_phase as one_phase
    from aidd.workitems.old_shape import role_identity as role_identity
    from aidd.workitems.old_shape import sort_intent_relations as sort_intent_relations
    from aidd.workitems.old_shape import sort_relations as sort_relations
    from aidd.workitems.old_shape import todays_shape as todays_shape
    from aidd.workitems.repo_reads import config_at as config_at
    from aidd.workitems.role_status import running_roles as running_roles
    from aidd.workitems.role_status import running_roles_text as running_roles_text
    from aidd.workitems.slice_start import find_slice as find_slice
    from aidd.workitems.spec_file import ID_PREFIXES as ID_PREFIXES
    from aidd.workitems.spec_file import TEST_PLANS as TEST_PLANS
    from aidd.workitems.spec_file import THREAT_MODELS as THREAT_MODELS
    from aidd.workitems.spec_file import WORK_ID as WORK_ID
    from aidd.workitems.spec_file import acceptance_ids as acceptance_ids
    from aidd.workitems.spec_file import design_paths as design_paths
    from aidd.workitems.spec_file import find_specs_in_diff as find_specs_in_diff
    from aidd.workitems.spec_file import frozen_change as frozen_change
    from aidd.workitems.spec_file import frozen_files as frozen_files
    from aidd.workitems.spec_file import load_object as load_object
    from aidd.workitems.spec_file import next_id as next_id
    from aidd.workitems.spec_file import tests_files as tests_files
    from aidd.workitems.spec_file import threat_models as threat_models
    from aidd.workitems.status import ASKS_APPROVAL as ASKS_APPROVAL
    from aidd.workitems.status import BEFORE_IMPLEMENT as BEFORE_IMPLEMENT
    from aidd.workitems.status import CAN_WAIT as CAN_WAIT
    from aidd.workitems.status import IMPLEMENTING as IMPLEMENTING
    from aidd.workitems.status import PAST_APPROVAL as PAST_APPROVAL
    from aidd.workitems.status import PLACEHOLDER as PLACEHOLDER
    from aidd.workitems.status import SPEC_STATUSES as SPEC_STATUSES
    from aidd.workitems.status import spec_status as spec_status
    from aidd.workitems.status import stored_status as stored_status
    from aidd.workitems.steps import AGENT as AGENT
    from aidd.workitems.steps import PERSON as PERSON
    from aidd.workitems.steps import STEP_CODES as STEP_CODES
    from aidd.workitems.steps import STEP_MEANINGS as STEP_MEANINGS
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
    from aidd.workitems.work_list import OPEN_GROUPS as OPEN_GROUPS
    from aidd.workitems.work_list import Shown as Shown
    from aidd.workitems.work_list import in_delivery_team as in_delivery_team
    from aidd.workitems.work_list import raw_emergencies as raw_emergencies
    from aidd.workitems.work_list import status_text as status_text
    from aidd.workitems.work_list import team_names as team_names
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "AGENT": "steps",
            "ASKS_APPROVAL": "status",
            "BEFORE_IMPLEMENT": "status",
            "CAN_WAIT": "status",
            "CHANGE_ORDERS": "authoring",
            "DEFAULT_CHANGE_TYPE": "old_shape",
            "DEFAULT_COMMITS": "tracing",
            "DIRECTION_HEADING": "explorations",
            "DOC_TEMPLATES": "authoring",
            "EXPLORATION_FILE": "explorations",
            "EXPLORATION_HOME": "explorations",
            "FROZEN_STATUSES": "frozen_tests",
            "HANDOFF_FENCE": "handoff_notes",
            "ID_PREFIXES": "spec_file",
            "IMPLEMENTING": "status",
            "LIVING_DOCS": "authoring",
            "MAX_COMMITS": "tracing",
            "NOTE": "validation",
            "OPEN_GROUPS": "work_list",
            "OPS_DIRS": "objects",
            "PAST_APPROVAL": "status",
            "PERSON": "steps",
            "PLACEHOLDER": "status",
            "REPO_DOCS": "authoring",
            "ROUNDS_DIR": "explorations",
            "SPEC_STATUSES": "status",
            "STEP_CODES": "steps",
            "STEP_MEANINGS": "steps",
            "TEST_PLANS": "spec_file",
            "THREAT_MODELS": "spec_file",
            "UNLINKED_DOCS": "authoring",
            "WARNING": "validation",
            "WORK_ID": "spec_file",
            "WORK_TYPES": "backlog",
            "NewDoc": "authoring",
            "NewObject": "authoring",
            "Shown": "work_list",
            "acceptance_ids": "spec_file",
            "add_branch_facts": "current_work",
            "adr_folder": "authoring",
            "all_branches_work": "all_branches",
            "apply_row": "old_shape",
            "assisted_by_spelling": "commit_text",
            "assisted_by_values": "commit_text",
            "body_sections": "explorations",
            "branch_item": "current_work",
            "change_type_of": "old_shape",
            "check_repo": "validation",
            "comment_id_direction": "explorations",
            "config_at": "repo_reads",
            "decision_states": "handoff_notes",
            "design_paths": "spec_file",
            "exploration_directions": "explorations",
            "exploration_misplaced": "explorations",
            "exploration_rounds": "explorations",
            "find_slice": "slice_start",
            "find_spec_by_id": "objects",
            "find_specs_in_diff": "spec_file",
            "folder_scope": "authoring",
            "frozen_change": "spec_file",
            "frozen_files": "spec_file",
            "frozen_test_files": "frozen_tests",
            "handoff_blocks": "handoff_notes",
            "has_front_matter": "objects",
            "hidden_characters": "handoff_notes",
            "history_text": "history",
            "holder_of": "intents",
            "in_delivery_team": "work_list",
            "index_path": "all_branches",
            "irreversible_of": "old_shape",
            "is_error": "validation",
            "is_id": "ids",
            "is_saved_request": "objects",
            "last_slice": "old_shape",
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
            "one_phase": "old_shape",
            "open_work": "current_work",
            "phase_heading": "intents",
            "raw_emergencies": "work_list",
            "read_document": "objects",
            "record_agreement": "agreement",
            "required_docs": "authoring",
            "role_identity": "old_shape",
            "round_comment_files": "explorations",
            "round_screenshots": "explorations",
            "running_roles": "role_status",
            "running_roles_text": "role_status",
            "scope_over_acceptance_tests": "authoring",
            "slice_ids": "intents",
            "sort_intent_relations": "old_shape",
            "sort_relations": "old_shape",
            "spec_status": "status",
            "spec_template": "authoring",
            "stage_of_step": "intents",
            "stages": "intents",
            "status_findings": "finding_lists",
            "status_text": "work_list",
            "step_words": "steps",
            "stored_status": "status",
            "team_names": "work_list",
            "tests_files": "spec_file",
            "threat_models": "spec_file",
            "todays_shape": "old_shape",
            "trace": "tracing",
            "trace_text": "tracing",
            "validate_file": "validation",
            "validate_findings": "finding_lists",
            "validate_next_step": "validation",
            "work_ids_in": "commit_text",
            "work_item_history": "history",
            "work_items_history": "history",
        },
    )
