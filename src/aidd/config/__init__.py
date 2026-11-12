"""`.aidd/config.yaml`: load it and merge its `extends` parents, the profiles, the coding agents aidd knows, Claude
Code's settings as aidd reads them, and the project block.

The children: model (`Config` and the values its keys take), loading (`load_file`, `load_text`, and the merge), extends
(the parents, read from the repository or fetched by URL, and the org preset), old_shape (a config in an earlier shape, read as today's), harnesses, harness_settings, harness_sizes (the sizes a vendor documents), project,
standards_policy, languages, test_runners, and item_types (what aidd knows of each language, each test runner, and each type of thing it tracks or writes, from the tables in schemas/), and layout (where aidd writes).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "AGENTS_MD",
    "AGENT_ENV",
    "BASE_COMMIT",
    "CHANGED_PATHS",
    "CLAUDE_TOOL_PREFIXES",
    "CONFIG_PATH",
    "CRA_TARGET",
    "DECIDED_BY",
    "DELEGATE_AGENT",
    "DELEGATING_HARNESS",
    "DOC_TYPES",
    "EDITOR_SCHEMA",
    "EMPTY",
    "EVIDENCE_DIR",
    "EXISTING_STRUCTURE",
    "HARNESSES",
    "HARNESS_RULES_FILE",
    "LISTING_FACTS",
    "MAJOR_DIMENSIONS",
    "MARKETPLACE",
    "OUTPUT_IGNORE",
    "PACKS_PLUGIN",
    "PLUGIN_NOTE",
    "POOL_OF",
    "PROFILES",
    "PROJECT_DEFAULTS",
    "PROJECT_NO_UI",
    "ROLES_HOME",
    "ROUTES",
    "ROUTE_RANK",
    "SCHEMA_MODELINE",
    "SELECTOR",
    "SESSION_ENV",
    "SESSION_SIGNALS",
    "SIZES",
    "SPEC_FIRST_ROUTES",
    "TEAM_FILES_FILE",
    "TEAM_MARK",
    "VIEWS_DIR",
    "Config",
    "ConfigError",
    "ConfigUnreadable",
    "Harness",
    "Limit",
    "action_matches",
    "apply_row",
    "approved_by_kind",
    "approved_by_problem",
    "approver_is_agent",
    "ask_rule_harnesses",
    "claude_config_dir",
    "claude_settings_paths",
    "common_documents",
    "config_load_problem",
    "config_unreadable_finding",
    "cost_hint",
    "default_docs_required",
    "delegation_review_warning",
    "delegation_warnings",
    "development_team",
    "display_name",
    "effective_project",
    "harnesses_table",
    "hold_hint",
    "identity_types",
    "in_todays_shape",
    "initial_status",
    "is_agent",
    "item_type_groups",
    "item_type_rows",
    "language_gitignore",
    "listing_budget",
    "listing_note",
    "load_file",
    "load_or_stop",
    "load_text",
    "looks_like_test",
    "manifest_languages",
    "manifest_names",
    "no_ask_rule_harnesses",
    "no_test_failed_exit",
    "normalize_identity",
    "org_preset_text",
    "plugin_enabled",
    "plugins_enabled",
    "pointer_files",
    "profiles",
    "project_block",
    "project_compliance",
    "project_defaults",
    "project_findings",
    "project_markdown",
    "registry_ids",
    "related_tests_suggestion",
    "route_of_risk",
    "route_rules_under",
    "route_words",
    "schema_modeline",
    "selector",
    "session_harness",
    "setting_default",
    "source_extensions",
    "status_set",
    "status_table",
    "status_transitions",
    "test_runner_names",
    "theme_hint",
    "todays_shape",
    "typed_identity",
    "types_in",
    "types_of_form",
    "types_with",
    "types_with_field",
    "unreadable_claude_settings",
    "user_plugins_enabled",
    "what_you_do",
]

if TYPE_CHECKING:
    from aidd.config.development_teams import development_team as development_team
    from aidd.config.extends import org_preset_text as org_preset_text
    from aidd.config.harness_settings import MARKETPLACE as MARKETPLACE
    from aidd.config.harness_settings import PACKS_PLUGIN as PACKS_PLUGIN
    from aidd.config.harness_settings import TEAM_MARK as TEAM_MARK
    from aidd.config.harness_settings import claude_config_dir as claude_config_dir
    from aidd.config.harness_settings import claude_settings_paths as claude_settings_paths
    from aidd.config.harness_settings import plugin_enabled as plugin_enabled
    from aidd.config.harness_settings import plugins_enabled as plugins_enabled
    from aidd.config.harness_settings import unreadable_claude_settings as unreadable_claude_settings
    from aidd.config.harness_settings import user_plugins_enabled as user_plugins_enabled
    from aidd.config.harness_sizes import LISTING_FACTS as LISTING_FACTS
    from aidd.config.harness_sizes import SIZES as SIZES
    from aidd.config.harness_sizes import listing_budget as listing_budget
    from aidd.config.harness_sizes import listing_note as listing_note
    from aidd.config.harnesses import AGENT_ENV as AGENT_ENV
    from aidd.config.harnesses import AGENTS_MD as AGENTS_MD
    from aidd.config.harnesses import CLAUDE_TOOL_PREFIXES as CLAUDE_TOOL_PREFIXES
    from aidd.config.harnesses import DECIDED_BY as DECIDED_BY
    from aidd.config.harnesses import DELEGATE_AGENT as DELEGATE_AGENT
    from aidd.config.harnesses import DELEGATING_HARNESS as DELEGATING_HARNESS
    from aidd.config.harnesses import HARNESSES as HARNESSES
    from aidd.config.harnesses import PLUGIN_NOTE as PLUGIN_NOTE
    from aidd.config.harnesses import SESSION_ENV as SESSION_ENV
    from aidd.config.harnesses import SESSION_SIGNALS as SESSION_SIGNALS
    from aidd.config.harnesses import Harness as Harness
    from aidd.config.harnesses import Limit as Limit
    from aidd.config.harnesses import ask_rule_harnesses as ask_rule_harnesses
    from aidd.config.harnesses import harnesses_table as harnesses_table
    from aidd.config.harnesses import no_ask_rule_harnesses as no_ask_rule_harnesses
    from aidd.config.harnesses import pointer_files as pointer_files
    from aidd.config.harnesses import session_harness as session_harness
    from aidd.config.harnesses import what_you_do as what_you_do
    from aidd.config.identities import approved_by_kind as approved_by_kind
    from aidd.config.identities import approved_by_problem as approved_by_problem
    from aidd.config.identities import approver_is_agent as approver_is_agent
    from aidd.config.identities import display_name as display_name
    from aidd.config.identities import identity_types as identity_types
    from aidd.config.identities import is_agent as is_agent
    from aidd.config.identities import normalize_identity as normalize_identity
    from aidd.config.identities import typed_identity as typed_identity
    from aidd.config.item_types import ROLES_HOME as ROLES_HOME
    from aidd.config.item_types import common_documents as common_documents
    from aidd.config.item_types import initial_status as initial_status
    from aidd.config.item_types import item_type_groups as item_type_groups
    from aidd.config.item_types import item_type_rows as item_type_rows
    from aidd.config.item_types import status_set as status_set
    from aidd.config.item_types import status_table as status_table
    from aidd.config.item_types import status_transitions as status_transitions
    from aidd.config.item_types import types_in as types_in
    from aidd.config.item_types import types_of_form as types_of_form
    from aidd.config.item_types import types_with as types_with
    from aidd.config.item_types import types_with_field as types_with_field
    from aidd.config.languages import language_gitignore as language_gitignore
    from aidd.config.languages import manifest_languages as manifest_languages
    from aidd.config.languages import manifest_names as manifest_names
    from aidd.config.languages import source_extensions as source_extensions
    from aidd.config.layout import EVIDENCE_DIR as EVIDENCE_DIR
    from aidd.config.layout import HARNESS_RULES_FILE as HARNESS_RULES_FILE
    from aidd.config.layout import OUTPUT_IGNORE as OUTPUT_IGNORE
    from aidd.config.layout import TEAM_FILES_FILE as TEAM_FILES_FILE
    from aidd.config.layout import VIEWS_DIR as VIEWS_DIR
    from aidd.config.limits import setting_default as setting_default
    from aidd.config.loading import SELECTOR as SELECTOR
    from aidd.config.loading import action_matches as action_matches
    from aidd.config.loading import config_load_problem as config_load_problem
    from aidd.config.loading import config_unreadable_finding as config_unreadable_finding
    from aidd.config.loading import load_file as load_file
    from aidd.config.loading import load_or_stop as load_or_stop
    from aidd.config.loading import load_text as load_text
    from aidd.config.loading import route_rules_under as route_rules_under
    from aidd.config.loading import selector as selector
    from aidd.config.model import CONFIG_PATH as CONFIG_PATH
    from aidd.config.model import DOC_TYPES as DOC_TYPES
    from aidd.config.model import EDITOR_SCHEMA as EDITOR_SCHEMA
    from aidd.config.model import EMPTY as EMPTY
    from aidd.config.model import MAJOR_DIMENSIONS as MAJOR_DIMENSIONS
    from aidd.config.model import POOL_OF as POOL_OF
    from aidd.config.model import PROFILES as PROFILES
    from aidd.config.model import ROUTE_RANK as ROUTE_RANK
    from aidd.config.model import ROUTES as ROUTES
    from aidd.config.model import SCHEMA_MODELINE as SCHEMA_MODELINE
    from aidd.config.model import SPEC_FIRST_ROUTES as SPEC_FIRST_ROUTES
    from aidd.config.model import Config as Config
    from aidd.config.model import ConfigError as ConfigError
    from aidd.config.model import ConfigUnreadable as ConfigUnreadable
    from aidd.config.model import default_docs_required as default_docs_required
    from aidd.config.model import looks_like_test as looks_like_test
    from aidd.config.model import route_of_risk as route_of_risk
    from aidd.config.model import route_words as route_words
    from aidd.config.model import schema_modeline as schema_modeline
    from aidd.config.old_shape import apply_row as apply_row
    from aidd.config.old_shape import in_todays_shape as in_todays_shape
    from aidd.config.old_shape import todays_shape as todays_shape
    from aidd.config.profile_data import profiles as profiles
    from aidd.config.project import CRA_TARGET as CRA_TARGET
    from aidd.config.project import EXISTING_STRUCTURE as EXISTING_STRUCTURE
    from aidd.config.project import PROJECT_DEFAULTS as PROJECT_DEFAULTS
    from aidd.config.project import PROJECT_NO_UI as PROJECT_NO_UI
    from aidd.config.project import cost_hint as cost_hint
    from aidd.config.project import delegation_review_warning as delegation_review_warning
    from aidd.config.project import delegation_warnings as delegation_warnings
    from aidd.config.project import effective_project as effective_project
    from aidd.config.project import hold_hint as hold_hint
    from aidd.config.project import project_block as project_block
    from aidd.config.project import project_compliance as project_compliance
    from aidd.config.project import project_defaults as project_defaults
    from aidd.config.project import project_findings as project_findings
    from aidd.config.project import project_markdown as project_markdown
    from aidd.config.project import theme_hint as theme_hint
    from aidd.config.standards_policy import registry_ids as registry_ids
    from aidd.config.test_runners import BASE_COMMIT as BASE_COMMIT
    from aidd.config.test_runners import CHANGED_PATHS as CHANGED_PATHS
    from aidd.config.test_runners import no_test_failed_exit as no_test_failed_exit
    from aidd.config.test_runners import related_tests_suggestion as related_tests_suggestion
    from aidd.config.test_runners import test_runner_names as test_runner_names
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "AGENTS_MD": "harnesses",
            "AGENT_ENV": "harnesses",
            "BASE_COMMIT": "test_runners",
            "CHANGED_PATHS": "test_runners",
            "CLAUDE_TOOL_PREFIXES": "harnesses",
            "CONFIG_PATH": "model",
            "CRA_TARGET": "project",
            "DECIDED_BY": "harnesses",
            "DELEGATE_AGENT": "harnesses",
            "DELEGATING_HARNESS": "harnesses",
            "DOC_TYPES": "model",
            "EDITOR_SCHEMA": "model",
            "EMPTY": "model",
            "EVIDENCE_DIR": "layout",
            "EXISTING_STRUCTURE": "project",
            "HARNESSES": "harnesses",
            "HARNESS_RULES_FILE": "layout",
            "LISTING_FACTS": "harness_sizes",
            "MAJOR_DIMENSIONS": "model",
            "MARKETPLACE": "harness_settings",
            "OUTPUT_IGNORE": "layout",
            "PACKS_PLUGIN": "harness_settings",
            "PLUGIN_NOTE": "harnesses",
            "POOL_OF": "model",
            "PROFILES": "model",
            "PROJECT_DEFAULTS": "project",
            "PROJECT_NO_UI": "project",
            "ROLES_HOME": "item_types",
            "ROUTES": "model",
            "ROUTE_RANK": "model",
            "SCHEMA_MODELINE": "model",
            "SELECTOR": "loading",
            "SESSION_ENV": "harnesses",
            "SESSION_SIGNALS": "harnesses",
            "SIZES": "harness_sizes",
            "SPEC_FIRST_ROUTES": "model",
            "TEAM_FILES_FILE": "layout",
            "TEAM_MARK": "harness_settings",
            "VIEWS_DIR": "layout",
            "Config": "model",
            "ConfigError": "model",
            "ConfigUnreadable": "model",
            "Harness": "harnesses",
            "Limit": "harnesses",
            "action_matches": "loading",
            "apply_row": "old_shape",
            "approved_by_kind": "identities",
            "approved_by_problem": "identities",
            "approver_is_agent": "identities",
            "ask_rule_harnesses": "harnesses",
            "claude_config_dir": "harness_settings",
            "claude_settings_paths": "harness_settings",
            "common_documents": "item_types",
            "config_load_problem": "loading",
            "config_unreadable_finding": "loading",
            "cost_hint": "project",
            "default_docs_required": "model",
            "delegation_review_warning": "project",
            "delegation_warnings": "project",
            "development_team": "development_teams",
            "display_name": "identities",
            "effective_project": "project",
            "harnesses_table": "harnesses",
            "hold_hint": "project",
            "identity_types": "identities",
            "in_todays_shape": "old_shape",
            "initial_status": "item_types",
            "is_agent": "identities",
            "item_type_groups": "item_types",
            "item_type_rows": "item_types",
            "language_gitignore": "languages",
            "listing_budget": "harness_sizes",
            "listing_note": "harness_sizes",
            "load_file": "loading",
            "load_or_stop": "loading",
            "load_text": "loading",
            "looks_like_test": "model",
            "manifest_languages": "languages",
            "manifest_names": "languages",
            "no_ask_rule_harnesses": "harnesses",
            "no_test_failed_exit": "test_runners",
            "normalize_identity": "identities",
            "org_preset_text": "extends",
            "plugin_enabled": "harness_settings",
            "plugins_enabled": "harness_settings",
            "pointer_files": "harnesses",
            "profiles": "profile_data",
            "project_block": "project",
            "project_compliance": "project",
            "project_defaults": "project",
            "project_findings": "project",
            "project_markdown": "project",
            "registry_ids": "standards_policy",
            "related_tests_suggestion": "test_runners",
            "route_of_risk": "model",
            "route_rules_under": "loading",
            "route_words": "model",
            "schema_modeline": "model",
            "selector": "loading",
            "session_harness": "harnesses",
            "setting_default": "limits",
            "source_extensions": "languages",
            "status_set": "item_types",
            "status_table": "item_types",
            "status_transitions": "item_types",
            "test_runner_names": "test_runners",
            "theme_hint": "project",
            "todays_shape": "old_shape",
            "typed_identity": "identities",
            "types_in": "item_types",
            "types_of_form": "item_types",
            "types_with": "item_types",
            "types_with_field": "item_types",
            "unreadable_claude_settings": "harness_settings",
            "user_plugins_enabled": "harness_settings",
            "what_you_do": "harnesses",
        },
    )
