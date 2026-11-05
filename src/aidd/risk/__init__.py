"""The risk rules: which actions an agent may take on its own, which it reports, and which it asks a person about; the
route a change needs, as advice; and the harness ask rules.

The children: rules (the rules in force and the level of one action), commands (which actions a shell command is),
routes (the route for planned paths), harness_rules (the ask rules as each coding agent's permission prompt), and
opencode_rules (OpenCode's form of them).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "FORMATS",
    "LANES",
    "LEVELS",
    "LEVEL_RANK",
    "MAJOR_DIMENSIONS",
    "MATCHES",
    "Rule",
    "RuleSet",
    "advice",
    "api_harness_names",
    "api_write_patterns",
    "apply_harness_rules",
    "areas_of",
    "builtin",
    "call_actions",
    "change_types",
    "command_level",
    "command_notes",
    "edit_level",
    "harness_patterns",
    "harness_read_paths",
    "is_local_merge",
    "level_of",
    "level_on_any_branch",
    "opencode_shadow_warnings",
    "planned_paths",
    "remove_harness_rules",
    "route_for",
    "rule_set",
    "rule_suggestions",
    "shown_paths",
    "spec_approval_level",
    "unwritten",
    "widened",
    "written_formats",
]

if TYPE_CHECKING:
    from aidd.risk.commands import call_actions as call_actions
    from aidd.risk.commands import command_level as command_level
    from aidd.risk.commands import is_local_merge as is_local_merge
    from aidd.risk.harness_rules import FORMATS as FORMATS
    from aidd.risk.harness_rules import MATCHES as MATCHES
    from aidd.risk.harness_rules import api_harness_names as api_harness_names
    from aidd.risk.harness_rules import api_write_patterns as api_write_patterns
    from aidd.risk.harness_rules import apply_harness_rules as apply_harness_rules
    from aidd.risk.harness_rules import command_notes as command_notes
    from aidd.risk.harness_rules import harness_patterns as harness_patterns
    from aidd.risk.harness_rules import harness_read_paths as harness_read_paths
    from aidd.risk.harness_rules import opencode_shadow_warnings as opencode_shadow_warnings
    from aidd.risk.harness_rules import remove_harness_rules as remove_harness_rules
    from aidd.risk.harness_rules import unwritten as unwritten
    from aidd.risk.harness_rules import widened as widened
    from aidd.risk.harness_rules import written_formats as written_formats
    from aidd.risk.routes import LANES as LANES
    from aidd.risk.routes import MAJOR_DIMENSIONS as MAJOR_DIMENSIONS
    from aidd.risk.routes import advice as advice
    from aidd.risk.routes import change_types as change_types
    from aidd.risk.routes import planned_paths as planned_paths
    from aidd.risk.routes import route_for as route_for
    from aidd.risk.routes import shown_paths as shown_paths
    from aidd.risk.routes import spec_approval_level as spec_approval_level
    from aidd.risk.rules import LEVEL_RANK as LEVEL_RANK
    from aidd.risk.rules import LEVELS as LEVELS
    from aidd.risk.rules import Rule as Rule
    from aidd.risk.rules import RuleSet as RuleSet
    from aidd.risk.rules import areas_of as areas_of
    from aidd.risk.rules import builtin as builtin
    from aidd.risk.rules import edit_level as edit_level
    from aidd.risk.rules import level_of as level_of
    from aidd.risk.rules import level_on_any_branch as level_on_any_branch
    from aidd.risk.rules import rule_set as rule_set
    from aidd.risk.suggestions import rule_suggestions as rule_suggestions
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "FORMATS": "harness_rules",
            "LANES": "routes",
            "LEVELS": "rules",
            "LEVEL_RANK": "rules",
            "MAJOR_DIMENSIONS": "routes",
            "MATCHES": "harness_rules",
            "Rule": "rules",
            "RuleSet": "rules",
            "advice": "routes",
            "api_harness_names": "harness_rules",
            "api_write_patterns": "harness_rules",
            "apply_harness_rules": "harness_rules",
            "areas_of": "rules",
            "builtin": "rules",
            "call_actions": "commands",
            "change_types": "routes",
            "command_level": "commands",
            "command_notes": "harness_rules",
            "edit_level": "rules",
            "harness_patterns": "harness_rules",
            "harness_read_paths": "harness_rules",
            "is_local_merge": "commands",
            "level_of": "rules",
            "level_on_any_branch": "rules",
            "opencode_shadow_warnings": "harness_rules",
            "planned_paths": "routes",
            "remove_harness_rules": "harness_rules",
            "route_for": "routes",
            "rule_set": "rules",
            "rule_suggestions": "suggestions",
            "shown_paths": "routes",
            "spec_approval_level": "routes",
            "unwritten": "harness_rules",
            "widened": "harness_rules",
            "written_formats": "harness_rules",
        },
    )
