"""The team's knowledge: the team registry, role and practice text, the standards library and its evidence, owners,
and keeping all of it current.

The children: team_registry (roles, practices, packs, and flows from roles.json), role_text, agent_models, standards
(the library), standard_copy_checks (its doctor checks), standards_lists (its lists and tables), standards_evidence,
owners, upkeep (the review cadence, and the postmortem actions that target a pack or a skill), evidence_recheck (`aidd eval standards --online`), release_feeds (the release check),
command_pins (the exact versions packs and skills name in commands), recheck_report, bounded_fetch, and explanations
(`aidd explain`: what each of aidd's words means, from the data that owns it).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "CORE_PRELOAD",
    "CORE_SKILL",
    "EFFORT_BY_TIER",
    "EXPLAIN_TYPES",
    "INHERIT_MODEL",
    "LIBRARY_REVIEW_EVERY_DAYS",
    "MODELS_BY_HARNESS",
    "PLUGIN_HARNESS",
    "ROLE_REFERENCE",
    "TIER_MEANING",
    "RiskFacts",
    "add_standards",
    "areas_phrase",
    "catalog_choices",
    "catalog_library",
    "catalog_stacks",
    "check_online",
    "check_releases",
    "citation_entries",
    "contract_carried_for",
    "contract_for",
    "copy_edited",
    "dated_entries",
    "dated_on",
    "due_soon",
    "exit_code",
    "explain",
    "explain_words",
    "found_by",
    "harness_model",
    "library_problems",
    "lists_description",
    "markdown",
    "open_choices",
    "open_choices_table",
    "pinned_command_entries",
    "pinned_command_lines",
    "practice_front",
    "practice_names",
    "proactive_roles",
    "refresh_standards",
    "release_entries",
    "resolve_agent_effort",
    "resolve_agent_model",
    "resolve_agent_turns",
    "reviewed_rules_for",
    "role_area",
    "role_loop",
    "role_writes",
    "roles",
    "shared_rules_carried_for",
    "shared_rules_for",
    "skill_ref",
    "stack_rows",
    "stacks",
    "stale_standards",
    "standard_doctor_checks",
    "standard_ecosystem",
    "standard_rows",
    "standards_library",
    "target_problem",
    "tier_model",
    "unknown_key_warnings",
    "unsupported_note",
]

if TYPE_CHECKING:
    from aidd.knowledge.agent_models import INHERIT_MODEL as INHERIT_MODEL
    from aidd.knowledge.agent_models import harness_model as harness_model
    from aidd.knowledge.agent_models import resolve_agent_effort as resolve_agent_effort
    from aidd.knowledge.agent_models import resolve_agent_model as resolve_agent_model
    from aidd.knowledge.agent_models import resolve_agent_turns as resolve_agent_turns
    from aidd.knowledge.agent_models import unknown_key_warnings as unknown_key_warnings
    from aidd.knowledge.agent_models import unsupported_note as unsupported_note
    from aidd.knowledge.command_pins import pinned_command_entries as pinned_command_entries
    from aidd.knowledge.command_pins import pinned_command_lines as pinned_command_lines
    from aidd.knowledge.evidence_recheck import check_online as check_online
    from aidd.knowledge.evidence_recheck import citation_entries as citation_entries
    from aidd.knowledge.explanations import EXPLAIN_TYPES as EXPLAIN_TYPES
    from aidd.knowledge.explanations import RiskFacts as RiskFacts
    from aidd.knowledge.explanations import explain as explain
    from aidd.knowledge.explanations import explain_words as explain_words
    from aidd.knowledge.library_checks import library_problems as library_problems
    from aidd.knowledge.owners import proactive_roles as proactive_roles
    from aidd.knowledge.recheck_report import exit_code as exit_code
    from aidd.knowledge.recheck_report import markdown as markdown
    from aidd.knowledge.release_feeds import check_releases as check_releases
    from aidd.knowledge.release_feeds import release_entries as release_entries
    from aidd.knowledge.role_text import CORE_SKILL as CORE_SKILL
    from aidd.knowledge.role_text import ROLE_REFERENCE as ROLE_REFERENCE
    from aidd.knowledge.role_text import practice_front as practice_front
    from aidd.knowledge.role_text import practice_names as practice_names
    from aidd.knowledge.role_text import role_area as role_area
    from aidd.knowledge.role_text import role_loop as role_loop
    from aidd.knowledge.role_text import role_writes as role_writes
    from aidd.knowledge.standard_copy_checks import standard_doctor_checks as standard_doctor_checks
    from aidd.knowledge.standards import LIBRARY_REVIEW_EVERY_DAYS as LIBRARY_REVIEW_EVERY_DAYS
    from aidd.knowledge.standards import add_standards as add_standards
    from aidd.knowledge.standards import copy_edited as copy_edited
    from aidd.knowledge.standards import open_choices as open_choices
    from aidd.knowledge.standards import refresh_standards as refresh_standards
    from aidd.knowledge.standards import stacks as stacks
    from aidd.knowledge.standards import standard_ecosystem as standard_ecosystem
    from aidd.knowledge.standards import standards_library as standards_library
    from aidd.knowledge.standards_evidence import dated_entries as dated_entries
    from aidd.knowledge.standards_evidence import dated_on as dated_on
    from aidd.knowledge.standards_evidence import due_soon as due_soon
    from aidd.knowledge.standards_evidence import stale_standards as stale_standards
    from aidd.knowledge.standards_lists import catalog_choices as catalog_choices
    from aidd.knowledge.standards_lists import catalog_library as catalog_library
    from aidd.knowledge.standards_lists import catalog_stacks as catalog_stacks
    from aidd.knowledge.standards_lists import open_choices_table as open_choices_table
    from aidd.knowledge.standards_lists import stack_rows as stack_rows
    from aidd.knowledge.standards_lists import standard_rows as standard_rows
    from aidd.knowledge.team_registry import CORE_PRELOAD as CORE_PRELOAD
    from aidd.knowledge.team_registry import EFFORT_BY_TIER as EFFORT_BY_TIER
    from aidd.knowledge.team_registry import MODELS_BY_HARNESS as MODELS_BY_HARNESS
    from aidd.knowledge.team_registry import PLUGIN_HARNESS as PLUGIN_HARNESS
    from aidd.knowledge.team_registry import TIER_MEANING as TIER_MEANING
    from aidd.knowledge.team_registry import areas_phrase as areas_phrase
    from aidd.knowledge.team_registry import contract_carried_for as contract_carried_for
    from aidd.knowledge.team_registry import contract_for as contract_for
    from aidd.knowledge.team_registry import found_by as found_by
    from aidd.knowledge.team_registry import lists_description as lists_description
    from aidd.knowledge.team_registry import reviewed_rules_for as reviewed_rules_for
    from aidd.knowledge.team_registry import roles as roles
    from aidd.knowledge.team_registry import shared_rules_carried_for as shared_rules_carried_for
    from aidd.knowledge.team_registry import shared_rules_for as shared_rules_for
    from aidd.knowledge.team_registry import skill_ref as skill_ref
    from aidd.knowledge.team_registry import tier_model as tier_model
    from aidd.knowledge.upkeep import target_problem as target_problem
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "CORE_PRELOAD": "team_registry",
            "CORE_SKILL": "role_text",
            "EFFORT_BY_TIER": "team_registry",
            "EXPLAIN_TYPES": "explanations",
            "INHERIT_MODEL": "agent_models",
            "LIBRARY_REVIEW_EVERY_DAYS": "standards",
            "MODELS_BY_HARNESS": "team_registry",
            "PLUGIN_HARNESS": "team_registry",
            "ROLE_REFERENCE": "role_text",
            "TIER_MEANING": "team_registry",
            "RiskFacts": "explanations",
            "add_standards": "standards",
            "areas_phrase": "team_registry",
            "catalog_choices": "standards_lists",
            "catalog_library": "standards_lists",
            "catalog_stacks": "standards_lists",
            "check_online": "evidence_recheck",
            "check_releases": "release_feeds",
            "citation_entries": "evidence_recheck",
            "contract_carried_for": "team_registry",
            "contract_for": "team_registry",
            "copy_edited": "standards",
            "dated_entries": "standards_evidence",
            "dated_on": "standards_evidence",
            "due_soon": "standards_evidence",
            "exit_code": "recheck_report",
            "explain": "explanations",
            "explain_words": "explanations",
            "found_by": "team_registry",
            "harness_model": "agent_models",
            "library_problems": "library_checks",
            "lists_description": "team_registry",
            "markdown": "recheck_report",
            "open_choices": "standards",
            "open_choices_table": "standards_lists",
            "pinned_command_entries": "command_pins",
            "pinned_command_lines": "command_pins",
            "practice_front": "role_text",
            "practice_names": "role_text",
            "proactive_roles": "owners",
            "refresh_standards": "standards",
            "release_entries": "release_feeds",
            "resolve_agent_effort": "agent_models",
            "resolve_agent_model": "agent_models",
            "resolve_agent_turns": "agent_models",
            "reviewed_rules_for": "team_registry",
            "role_area": "role_text",
            "role_loop": "role_text",
            "role_writes": "role_text",
            "roles": "team_registry",
            "shared_rules_carried_for": "team_registry",
            "shared_rules_for": "team_registry",
            "skill_ref": "team_registry",
            "stack_rows": "standards_lists",
            "stacks": "standards",
            "stale_standards": "standards_evidence",
            "standard_doctor_checks": "standard_copy_checks",
            "standard_ecosystem": "standards",
            "standard_rows": "standards_lists",
            "standards_library": "standards",
            "target_problem": "upkeep",
            "tier_model": "team_registry",
            "unknown_key_warnings": "agent_models",
            "unsupported_note": "agent_models",
        },
    )
