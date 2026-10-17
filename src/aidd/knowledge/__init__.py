"""The team's knowledge: the team registry, role and practice text, the standards library and its evidence, owners,
and keeping all of it current.

The children: team_registry (roles, practices, packs, and flows from roles.json), role_text, agent_models, standards
(the library), standards_evidence, owners, upkeep (the review cadence, and the postmortem actions that
target a pack or a skill), evidence_recheck (`aidd eval standards --online`), release_feeds (the release check),
recheck_report, and bounded_fetch.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "CORE_SKILL",
    "INHERIT_MODEL",
    "LIBRARY_REVIEW_EVERY_DAYS",
    "MODELS_BY_HARNESS",
    "PLUGIN_HARNESS",
    "ROLE_REFERENCE",
    "TIER_AGENT",
    "TIER_MEANING",
    "TIER_PERSON",
    "add_standards",
    "catalog_choices",
    "catalog_library",
    "catalog_stacks",
    "check_online",
    "check_releases",
    "config_standards",
    "contract_for",
    "dated_entries",
    "dated_on",
    "digest_for",
    "due_soon",
    "evidence_entries",
    "exit_code",
    "harness_model",
    "independent_review_warnings",
    "library_problems",
    "markdown",
    "open_actions",
    "open_choices",
    "open_choices_table",
    "owners_markdown",
    "owners_view",
    "practice_front",
    "practice_names",
    "proactive_roles",
    "refresh_standards",
    "release_entries",
    "resolve_agent_model",
    "role_area",
    "suggestions",
    "suggestions_text",
    "role_loop",
    "role_writes",
    "roles",
    "stack_rows",
    "stacks",
    "stale_standards",
    "standard_copies",
    "standard_doctor_checks",
    "standard_ecosystem",
    "standard_rows",
    "standards_for",
    "standards_library",
    "target_problem",
    "tier_model",
    "trust_counts",
    "trust_tier",
    "unknown_key_warnings",
    "unsupported_note",
]

if TYPE_CHECKING:
    from aidd.knowledge.agent_models import INHERIT_MODEL as INHERIT_MODEL
    from aidd.knowledge.agent_models import harness_model as harness_model
    from aidd.knowledge.agent_models import independent_review_warnings as independent_review_warnings
    from aidd.knowledge.agent_models import resolve_agent_model as resolve_agent_model
    from aidd.knowledge.agent_models import unknown_key_warnings as unknown_key_warnings
    from aidd.knowledge.agent_models import unsupported_note as unsupported_note
    from aidd.knowledge.evidence_recheck import check_online as check_online
    from aidd.knowledge.evidence_recheck import evidence_entries as evidence_entries
    from aidd.knowledge.extension_picks import suggestions as suggestions
    from aidd.knowledge.extension_picks import suggestions_text as suggestions_text
    from aidd.knowledge.owners import config_standards as config_standards
    from aidd.knowledge.owners import owners_markdown as owners_markdown
    from aidd.knowledge.owners import owners_view as owners_view
    from aidd.knowledge.owners import proactive_roles as proactive_roles
    from aidd.knowledge.owners import standards_for as standards_for
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
    from aidd.knowledge.standards import LIBRARY_REVIEW_EVERY_DAYS as LIBRARY_REVIEW_EVERY_DAYS
    from aidd.knowledge.standards import TIER_AGENT as TIER_AGENT
    from aidd.knowledge.standards import TIER_PERSON as TIER_PERSON
    from aidd.knowledge.standards import add_standards as add_standards
    from aidd.knowledge.standards import catalog_choices as catalog_choices
    from aidd.knowledge.standards import catalog_library as catalog_library
    from aidd.knowledge.standards import catalog_stacks as catalog_stacks
    from aidd.knowledge.standards import library_problems as library_problems
    from aidd.knowledge.standards import open_choices as open_choices
    from aidd.knowledge.standards import open_choices_table as open_choices_table
    from aidd.knowledge.standards import refresh_standards as refresh_standards
    from aidd.knowledge.standards import stack_rows as stack_rows
    from aidd.knowledge.standards import stacks as stacks
    from aidd.knowledge.standards import standard_copies as standard_copies
    from aidd.knowledge.standards import standard_doctor_checks as standard_doctor_checks
    from aidd.knowledge.standards import standard_ecosystem as standard_ecosystem
    from aidd.knowledge.standards import standard_rows as standard_rows
    from aidd.knowledge.standards import standards_library as standards_library
    from aidd.knowledge.standards import trust_counts as trust_counts
    from aidd.knowledge.standards import trust_tier as trust_tier
    from aidd.knowledge.standards_evidence import dated_entries as dated_entries
    from aidd.knowledge.standards_evidence import dated_on as dated_on
    from aidd.knowledge.standards_evidence import due_soon as due_soon
    from aidd.knowledge.standards_evidence import stale_standards as stale_standards
    from aidd.knowledge.team_registry import MODELS_BY_HARNESS as MODELS_BY_HARNESS
    from aidd.knowledge.team_registry import PLUGIN_HARNESS as PLUGIN_HARNESS
    from aidd.knowledge.team_registry import TIER_MEANING as TIER_MEANING
    from aidd.knowledge.team_registry import contract_for as contract_for
    from aidd.knowledge.team_registry import digest_for as digest_for
    from aidd.knowledge.team_registry import roles as roles
    from aidd.knowledge.team_registry import tier_model as tier_model
    from aidd.knowledge.upkeep import open_actions as open_actions
    from aidd.knowledge.upkeep import target_problem as target_problem
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "CORE_SKILL": "role_text",
            "INHERIT_MODEL": "agent_models",
            "LIBRARY_REVIEW_EVERY_DAYS": "standards",
            "MODELS_BY_HARNESS": "team_registry",
            "PLUGIN_HARNESS": "team_registry",
            "ROLE_REFERENCE": "role_text",
            "TIER_AGENT": "standards",
            "TIER_MEANING": "team_registry",
            "TIER_PERSON": "standards",
            "add_standards": "standards",
            "catalog_choices": "standards",
            "catalog_library": "standards",
            "catalog_stacks": "standards",
            "check_online": "evidence_recheck",
            "check_releases": "release_feeds",
            "config_standards": "owners",
            "contract_for": "team_registry",
            "dated_entries": "standards_evidence",
            "dated_on": "standards_evidence",
            "digest_for": "team_registry",
            "due_soon": "standards_evidence",
            "evidence_entries": "evidence_recheck",
            "exit_code": "recheck_report",
            "harness_model": "agent_models",
            "independent_review_warnings": "agent_models",
            "library_problems": "standards",
            "markdown": "recheck_report",
            "open_actions": "upkeep",
            "open_choices": "standards",
            "open_choices_table": "standards",
            "owners_markdown": "owners",
            "owners_view": "owners",
            "practice_front": "role_text",
            "practice_names": "role_text",
            "proactive_roles": "owners",
            "refresh_standards": "standards",
            "release_entries": "release_feeds",
            "resolve_agent_model": "agent_models",
            "role_area": "role_text",
            "suggestions": "extension_picks",
            "suggestions_text": "extension_picks",
            "role_loop": "role_text",
            "role_writes": "role_text",
            "roles": "team_registry",
            "stack_rows": "standards",
            "stacks": "standards",
            "stale_standards": "standards_evidence",
            "standard_copies": "standards",
            "standard_doctor_checks": "standards",
            "standard_ecosystem": "standards",
            "standard_rows": "standards",
            "standards_for": "owners",
            "standards_library": "standards",
            "target_problem": "upkeep",
            "tier_model": "team_registry",
            "trust_counts": "standards",
            "trust_tier": "standards",
            "unknown_key_warnings": "agent_models",
            "unsupported_note": "agent_models",
        },
    )
