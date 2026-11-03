"""The risk rules: which actions an agent may take on its own, which it reports, and which it asks a person about; the
route a change needs, as advice; and the harness ask rules.

The children: rules (the rules in force and the level of one action), commands (which actions a shell command is),
routes (the route for planned paths), and harness_rules (the ask rules as each coding agent's permission prompt).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "FORMATS",
    "MATCHES",
    "LANES",
    "LEVELS",
    "LEVEL_RANK",
    "MAJOR_DIMENSIONS",
    "Rule",
    "RuleSet",
    "advice",
    "apply_harness_rules",
    "areas_of",
    "builtin",
    "change_types",
    "command_level",
    "edit_level",
    "harness_patterns",
    "unwritten",
    "level_of",
    "matching_actions",
    "planned_paths",
    "remove_harness_rules",
    "route_for",
    "rule_set",
    "spec_approval_level",
]

if TYPE_CHECKING:
    from aidd.risk.commands import command_level as command_level
    from aidd.risk.commands import matching_actions as matching_actions
    from aidd.risk.harness_rules import FORMATS as FORMATS
    from aidd.risk.harness_rules import MATCHES as MATCHES
    from aidd.risk.harness_rules import apply_harness_rules as apply_harness_rules
    from aidd.risk.harness_rules import harness_patterns as harness_patterns
    from aidd.risk.harness_rules import remove_harness_rules as remove_harness_rules
    from aidd.risk.harness_rules import unwritten as unwritten
    from aidd.risk.routes import LANES as LANES
    from aidd.risk.routes import MAJOR_DIMENSIONS as MAJOR_DIMENSIONS
    from aidd.risk.routes import advice as advice
    from aidd.risk.routes import change_types as change_types
    from aidd.risk.routes import planned_paths as planned_paths
    from aidd.risk.routes import route_for as route_for
    from aidd.risk.routes import spec_approval_level as spec_approval_level
    from aidd.risk.rules import LEVEL_RANK as LEVEL_RANK
    from aidd.risk.rules import LEVELS as LEVELS
    from aidd.risk.rules import Rule as Rule
    from aidd.risk.rules import RuleSet as RuleSet
    from aidd.risk.rules import areas_of as areas_of
    from aidd.risk.rules import builtin as builtin
    from aidd.risk.rules import edit_level as edit_level
    from aidd.risk.rules import level_of as level_of
    from aidd.risk.rules import rule_set as rule_set
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "FORMATS": "harness_rules",
            "MATCHES": "harness_rules",
            "LANES": "routes",
            "LEVELS": "rules",
            "LEVEL_RANK": "rules",
            "MAJOR_DIMENSIONS": "routes",
            "Rule": "rules",
            "RuleSet": "rules",
            "advice": "routes",
            "apply_harness_rules": "harness_rules",
            "areas_of": "rules",
            "builtin": "rules",
            "change_types": "routes",
            "command_level": "commands",
            "edit_level": "rules",
            "harness_patterns": "harness_rules",
            "unwritten": "harness_rules",
            "level_of": "rules",
            "matching_actions": "commands",
            "planned_paths": "routes",
            "remove_harness_rules": "harness_rules",
            "route_for": "routes",
            "rule_set": "rules",
            "spec_approval_level": "routes",
        },
    )
