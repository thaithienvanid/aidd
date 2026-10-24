"""The gate: a pure function from a context (see context.schema.json) to a decision.

The agent proposes; the gate decides. Nothing in the Change Request block
counts as evidence: diff paths, test results, approvals, identities, and the
Policy answer all come from the platform through the context.

The children: engine (`decide`: every rule over a context, folded into pass, fail, or pending), rules (one function
each, run in order, with the secret patterns and the red-run test beside their rules), routing, inputs, policy,
codeowners, dependency_updates, placement, test_runner, change_record, decision_report, and rulebook.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "APPROVE_SPEC",
    "BUG_REPORT_URL",
    "Decision",
    "LANES",
    "MAX_APPROVAL_COMMITS",
    "ROUTE_RANK",
    "QUESTIONS",
    "RULES",
    "adapter_fields",
    "added_dependencies",
    "approval_commits",
    "approval_equivalents",
    "approved_heads",
    "content_matches",
    "assess_diff",
    "assess_paths",
    "assess_route",
    "binary_paths",
    "counted_changed_lines",
    "changed_paths",
    "check",
    "comment_commands",
    "commit_block",
    "counted_binaries",
    "decide",
    "decision_event",
    "decision_markdown",
    "decision_text",
    "declared_dependencies",
    "declared_inputs",
    "dependencies_added",
    "dependency_packs_for",
    "dependency_rules",
    "dependency_version_updates",
    "error_event",
    "evaluate_in_base",
    "event_header",
    "explain_rule",
    "find_change_record",
    "is_manifest",
    "lane_step",
    "CI_GATE_FILES",
    "agents_publish",
    "published",
    "trunk_on_platform",
    "platform_of",
    "pool_members",
    "proposal_only",
    "protected_paths",
    "config_controls_changed",
    "reason_lines",
    "recorded_comment",
    "red_ok",
    "required_tests",
    "revert_of",
    "reviewed_on_branch",
    "risk_packs",
    "route_summary",
    "run_test_command",
    "run_tests",
    "secret_kinds",
    "spec_of_change",
    "status_line",
    "untested_feature_hint",
    "verify_signature",
    "watch_tests",
    "worktree_text",
    "write_change_record",
    "write_records",
]

if TYPE_CHECKING:
    from aidd.gate.change_record import check as check
    from aidd.gate.change_record import find_change_record as find_change_record
    from aidd.gate.change_record import verify_signature as verify_signature
    from aidd.gate.change_record import write_change_record as write_change_record
    from aidd.gate.change_record import write_records as write_records
    from aidd.gate.decision_report import decision_event as decision_event
    from aidd.gate.decision_report import decision_markdown as decision_markdown
    from aidd.gate.decision_report import decision_text as decision_text
    from aidd.gate.decision_report import error_event as error_event
    from aidd.gate.decision_report import event_header as event_header
    from aidd.gate.decision_report import status_line as status_line
    from aidd.gate.dependency_updates import added_dependencies as added_dependencies
    from aidd.gate.dependency_updates import declared_dependencies as declared_dependencies
    from aidd.gate.dependency_updates import dependency_packs_for as dependency_packs_for
    from aidd.gate.dependency_updates import dependency_rules as dependency_rules
    from aidd.gate.dependency_updates import is_manifest as is_manifest
    from aidd.gate.engine import Decision as Decision
    from aidd.gate.engine import decide as decide
    from aidd.gate.inputs import MAX_APPROVAL_COMMITS as MAX_APPROVAL_COMMITS
    from aidd.gate.inputs import adapter_fields as adapter_fields
    from aidd.gate.inputs import approval_commits as approval_commits
    from aidd.gate.inputs import approval_equivalents as approval_equivalents
    from aidd.gate.inputs import approved_heads as approved_heads
    from aidd.gate.inputs import commit_block as commit_block
    from aidd.gate.inputs import content_matches as content_matches
    from aidd.gate.inputs import declared_inputs as declared_inputs
    from aidd.gate.inputs import dependencies_added as dependencies_added
    from aidd.gate.inputs import dependency_version_updates as dependency_version_updates
    from aidd.gate.inputs import pool_members as pool_members
    from aidd.gate.inputs import recorded_comment as recorded_comment
    from aidd.gate.inputs import revert_of as revert_of
    from aidd.gate.inputs import spec_of_change as spec_of_change
    from aidd.gate.placement import CI_GATE_FILES as CI_GATE_FILES
    from aidd.gate.placement import agents_publish as agents_publish
    from aidd.gate.placement import platform_of as platform_of
    from aidd.gate.placement import published as published
    from aidd.gate.placement import trunk_on_platform as trunk_on_platform
    from aidd.gate.policy import evaluate_in_base as evaluate_in_base
    from aidd.gate.routing import LANES as LANES
    from aidd.gate.routing import ROUTE_RANK as ROUTE_RANK
    from aidd.gate.routing import assess_diff as assess_diff
    from aidd.gate.routing import assess_paths as assess_paths
    from aidd.gate.routing import assess_route as assess_route
    from aidd.gate.routing import binary_paths as binary_paths
    from aidd.gate.routing import changed_paths as changed_paths
    from aidd.gate.routing import config_controls_changed as config_controls_changed
    from aidd.gate.routing import counted_binaries as counted_binaries
    from aidd.gate.routing import counted_changed_lines as counted_changed_lines
    from aidd.gate.routing import lane_step as lane_step
    from aidd.gate.routing import proposal_only as proposal_only
    from aidd.gate.routing import protected_paths as protected_paths
    from aidd.gate.routing import reason_lines as reason_lines
    from aidd.gate.routing import required_tests as required_tests
    from aidd.gate.routing import reviewed_on_branch as reviewed_on_branch
    from aidd.gate.routing import risk_packs as risk_packs
    from aidd.gate.routing import route_summary as route_summary
    from aidd.gate.routing import untested_feature_hint as untested_feature_hint
    from aidd.gate.routing import worktree_text as worktree_text
    from aidd.gate.rulebook import BUG_REPORT_URL as BUG_REPORT_URL
    from aidd.gate.rulebook import QUESTIONS as QUESTIONS
    from aidd.gate.rulebook import RULES as RULES
    from aidd.gate.rulebook import explain_rule as explain_rule
    from aidd.gate.rules.evidence import red_ok
    from aidd.gate.rules.gate_run import APPROVE_SPEC as APPROVE_SPEC
    from aidd.gate.rules.gate_run import comment_commands as comment_commands
    from aidd.gate.rules.safety import secret_kinds
    from aidd.gate.test_runner import run_test_command as run_test_command
    from aidd.gate.test_runner import run_tests as run_tests
    from aidd.gate.test_runner import watch_tests as watch_tests
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "APPROVE_SPEC": "rules.gate_run",
            "BUG_REPORT_URL": "rulebook",
            "Decision": "engine",
            "LANES": "routing",
            "MAX_APPROVAL_COMMITS": "inputs",
            "ROUTE_RANK": "routing",
            "QUESTIONS": "rulebook",
            "RULES": "rulebook",
            "adapter_fields": "inputs",
            "added_dependencies": "dependency_updates",
            "approval_commits": "inputs",
            "approval_equivalents": "inputs",
            "approved_heads": "inputs",
            "content_matches": "inputs",
            "assess_diff": "routing",
            "assess_paths": "routing",
            "assess_route": "routing",
            "binary_paths": "routing",
            "counted_changed_lines": "routing",
            "changed_paths": "routing",
            "check": "change_record",
            "comment_commands": "rules.gate_run",
            "commit_block": "inputs",
            "counted_binaries": "routing",
            "decide": "engine",
            "decision_event": "decision_report",
            "decision_markdown": "decision_report",
            "decision_text": "decision_report",
            "declared_dependencies": "dependency_updates",
            "declared_inputs": "inputs",
            "dependencies_added": "inputs",
            "dependency_packs_for": "dependency_updates",
            "dependency_rules": "dependency_updates",
            "dependency_version_updates": "inputs",
            "error_event": "decision_report",
            "evaluate_in_base": "policy",
            "event_header": "decision_report",
            "explain_rule": "rulebook",
            "find_change_record": "change_record",
            "is_manifest": "dependency_updates",
            "lane_step": "routing",
            "CI_GATE_FILES": "placement",
            "agents_publish": "placement",
            "published": "placement",
            "trunk_on_platform": "placement",
            "platform_of": "placement",
            "pool_members": "inputs",
            "proposal_only": "routing",
            "protected_paths": "routing",
            "config_controls_changed": "routing",
            "reason_lines": "routing",
            "recorded_comment": "inputs",
            "red_ok": "rules.evidence",
            "required_tests": "routing",
            "revert_of": "inputs",
            "reviewed_on_branch": "routing",
            "risk_packs": "routing",
            "route_summary": "routing",
            "run_test_command": "test_runner",
            "run_tests": "test_runner",
            "secret_kinds": "rules.safety",
            "spec_of_change": "inputs",
            "status_line": "decision_report",
            "untested_feature_hint": "routing",
            "verify_signature": "change_record",
            "watch_tests": "test_runner",
            "worktree_text": "routing",
            "write_change_record": "change_record",
            "write_records": "change_record",
        },
    )
