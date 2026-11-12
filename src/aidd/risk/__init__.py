"""The risk rules: which actions an agent may take on its own, which it reports, and which it asks a person about; the
route a change needs, as advice; and the harness ask rules.

The children: rules (the rules in force and the level of one action), commands (which actions a shell command is),
routes (the route for planned paths), harness_rules (the ask rules as each coding agent's permission prompt),
opencode_rules (OpenCode's form of them), grok_rules (Grok Build's), holds (what each format holds of each action), settings_json (the JSON files they live in), and jsonc
(editing one that takes comments in place).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "FORMATS",
    "MATCHES",
    "UNHELD",
    "DeclaredRisk",
    "Hold",
    "Rule",
    "RuleSet",
    "actions_without_edits",
    "advice",
    "api_harness_names",
    "api_write_patterns",
    "apply_harness_rules",
    "areas_of",
    "builtin",
    "command_level",
    "command_notes",
    "deploys_to",
    "edit_level",
    "harness_edit_paths",
    "harness_patterns",
    "harness_read_paths",
    "held_by_none",
    "held_in_part",
    "hold_counts",
    "is_local_merge",
    "level_of",
    "level_on_any_branch",
    "lock_effects",
    "opencode_shadow_warnings",
    "pattern_actions",
    "planned_paths",
    "remove_harness_rules",
    "route_for",
    "routes_asking_for_spec_approval",
    "rule_files",
    "rule_set",
    "rule_suggestions",
    "shown_paths",
    "unknown_name",
    "unwritten",
    "widened",
    "written_formats",
]

if TYPE_CHECKING:
    from aidd.risk.commands import command_level as command_level
    from aidd.risk.commands import deploys_to as deploys_to
    from aidd.risk.commands import is_local_merge as is_local_merge
    from aidd.risk.edit_free_actions import actions_without_edits as actions_without_edits
    from aidd.risk.edit_paths import harness_edit_paths as harness_edit_paths
    from aidd.risk.harness_rules import FORMATS as FORMATS
    from aidd.risk.harness_rules import MATCHES as MATCHES
    from aidd.risk.harness_rules import api_harness_names as api_harness_names
    from aidd.risk.harness_rules import api_write_patterns as api_write_patterns
    from aidd.risk.harness_rules import apply_harness_rules as apply_harness_rules
    from aidd.risk.harness_rules import harness_patterns as harness_patterns
    from aidd.risk.harness_rules import harness_read_paths as harness_read_paths
    from aidd.risk.harness_rules import opencode_shadow_warnings as opencode_shadow_warnings
    from aidd.risk.harness_rules import pattern_actions as pattern_actions
    from aidd.risk.harness_rules import remove_harness_rules as remove_harness_rules
    from aidd.risk.harness_rules import rule_files as rule_files
    from aidd.risk.harness_rules import unwritten as unwritten
    from aidd.risk.harness_rules import widened as widened
    from aidd.risk.harness_rules import written_formats as written_formats
    from aidd.risk.holds import UNHELD as UNHELD
    from aidd.risk.holds import Hold as Hold
    from aidd.risk.holds import command_notes as command_notes
    from aidd.risk.holds import held_by_none as held_by_none
    from aidd.risk.holds import held_in_part as held_in_part
    from aidd.risk.holds import hold_counts as hold_counts
    from aidd.risk.routes import DeclaredRisk as DeclaredRisk
    from aidd.risk.routes import advice as advice
    from aidd.risk.routes import planned_paths as planned_paths
    from aidd.risk.routes import route_for as route_for
    from aidd.risk.routes import routes_asking_for_spec_approval as routes_asking_for_spec_approval
    from aidd.risk.routes import shown_paths as shown_paths
    from aidd.risk.rules import Rule as Rule
    from aidd.risk.rules import RuleSet as RuleSet
    from aidd.risk.rules import areas_of as areas_of
    from aidd.risk.rules import builtin as builtin
    from aidd.risk.rules import edit_level as edit_level
    from aidd.risk.rules import level_of as level_of
    from aidd.risk.rules import level_on_any_branch as level_on_any_branch
    from aidd.risk.rules import lock_effects as lock_effects
    from aidd.risk.rules import rule_set as rule_set
    from aidd.risk.rules import unknown_name as unknown_name
    from aidd.risk.suggestions import rule_suggestions as rule_suggestions
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "FORMATS": "harness_rules",
            "MATCHES": "harness_rules",
            "UNHELD": "holds",
            "DeclaredRisk": "routes",
            "Hold": "holds",
            "Rule": "rules",
            "RuleSet": "rules",
            "actions_without_edits": "edit_free_actions",
            "advice": "routes",
            "api_harness_names": "harness_rules",
            "api_write_patterns": "harness_rules",
            "apply_harness_rules": "harness_rules",
            "areas_of": "rules",
            "builtin": "rules",
            "command_level": "commands",
            "command_notes": "holds",
            "deploys_to": "commands",
            "edit_level": "rules",
            "harness_edit_paths": "edit_paths",
            "harness_patterns": "harness_rules",
            "harness_read_paths": "harness_rules",
            "held_by_none": "holds",
            "held_in_part": "holds",
            "hold_counts": "holds",
            "is_local_merge": "commands",
            "level_of": "rules",
            "level_on_any_branch": "rules",
            "lock_effects": "rules",
            "opencode_shadow_warnings": "harness_rules",
            "pattern_actions": "harness_rules",
            "planned_paths": "routes",
            "remove_harness_rules": "harness_rules",
            "route_for": "routes",
            "routes_asking_for_spec_approval": "routes",
            "rule_files": "harness_rules",
            "rule_set": "rules",
            "rule_suggestions": "suggestions",
            "shown_paths": "routes",
            "unknown_name": "rules",
            "unwritten": "harness_rules",
            "widened": "harness_rules",
            "written_formats": "harness_rules",
        },
    )
