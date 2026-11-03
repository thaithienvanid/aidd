"""`.aidd/config.yaml`: load it and merge its `extends` parents, the profiles, the coding agents aidd knows, Claude
Code's settings as aidd reads them, and the project block.

The children: model (`Config` and the values its keys take), loading (`load_file`, `load_text`, and the merge), extends
(the parents, read from the repository or fetched by URL, and the org preset), harnesses, harness_settings, project,
standards_policy, and layout (where aidd writes).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "AGENTS_MD",
    "CONFIG_PATH",
    "CRA_TARGET",
    "Config",
    "ConfigError",
    "DOC_KINDS",
    "EDITOR_SCHEMA",
    "EVIDENCE_DIR",
    "EXISTING_STRUCTURE",
    "HARNESSES",
    "HARNESS_RULES_FILE",
    "MARKETPLACE",
    "MAX_REVIEW_AGE_DAYS",
    "MAX_RUNBOOK_AGE_DAYS",
    "OUTPUT_IGNORE",
    "PLUGIN_NOTE",
    "POOL_OF",
    "PREVIEW_DIR",
    "PROFILES",
    "PROJECT_DEFAULTS",
    "PROJECT_NO_UI",
    "ROUTE_KEYS",
    "ROUTE_RANK",
    "SCHEMA_MODELINE",
    "SELECTOR",
    "TEAM_MARK",
    "TEAM_PREFIX",
    "UNREAD_PARENT",
    "VIEWS_DIR",
    "area_paths",
    "ask_rule_harnesses",
    "claude_config_dir",
    "claude_settings_paths",
    "collect_extends",
    "cost_hint",
    "default_docs_required",
    "harness_paths",
    "harnesses_table",
    "hold_hint",
    "is_agent",
    "is_bot",
    "load_file",
    "load_text",
    "major_conditions",
    "merge_risks",
    "names_an_agent",
    "normalize_identity",
    "org_preset_text",
    "plugin_enabled",
    "plugins_enabled",
    "pointer_files",
    "profiles",
    "project_block",
    "project_compliance",
    "project_defaults",
    "effective_project",
    "project_findings",
    "project_markdown",
    "registry_ids",
    "schema_modeline",
    "selector",
    "theme_hint",
    "unreadable_claude_settings",
    "user_plugins_enabled",
]

if TYPE_CHECKING:
    from aidd.config.extends import collect_extends as collect_extends
    from aidd.config.extends import org_preset_text as org_preset_text
    from aidd.config.harness_settings import MARKETPLACE as MARKETPLACE
    from aidd.config.harness_settings import TEAM_MARK as TEAM_MARK
    from aidd.config.harness_settings import TEAM_PREFIX as TEAM_PREFIX
    from aidd.config.harness_settings import claude_config_dir as claude_config_dir
    from aidd.config.harness_settings import claude_settings_paths as claude_settings_paths
    from aidd.config.harness_settings import plugin_enabled as plugin_enabled
    from aidd.config.harness_settings import plugins_enabled as plugins_enabled
    from aidd.config.harness_settings import unreadable_claude_settings as unreadable_claude_settings
    from aidd.config.harness_settings import user_plugins_enabled as user_plugins_enabled
    from aidd.config.harnesses import AGENTS_MD as AGENTS_MD
    from aidd.config.harnesses import HARNESSES as HARNESSES
    from aidd.config.harnesses import PLUGIN_NOTE as PLUGIN_NOTE
    from aidd.config.harnesses import ask_rule_harnesses as ask_rule_harnesses
    from aidd.config.harnesses import harness_paths as harness_paths
    from aidd.config.harnesses import harnesses_table as harnesses_table
    from aidd.config.harnesses import pointer_files as pointer_files
    from aidd.config.identities import is_agent as is_agent
    from aidd.config.identities import is_bot as is_bot
    from aidd.config.identities import names_an_agent as names_an_agent
    from aidd.config.identities import normalize_identity as normalize_identity
    from aidd.config.layout import EVIDENCE_DIR as EVIDENCE_DIR
    from aidd.config.layout import HARNESS_RULES_FILE as HARNESS_RULES_FILE
    from aidd.config.layout import OUTPUT_IGNORE as OUTPUT_IGNORE
    from aidd.config.layout import PREVIEW_DIR as PREVIEW_DIR
    from aidd.config.layout import VIEWS_DIR as VIEWS_DIR
    from aidd.config.loading import SELECTOR as SELECTOR
    from aidd.config.loading import UNREAD_PARENT as UNREAD_PARENT
    from aidd.config.loading import load_file as load_file
    from aidd.config.loading import load_text as load_text
    from aidd.config.loading import merge_risks as merge_risks
    from aidd.config.loading import selector as selector
    from aidd.config.model import CONFIG_PATH as CONFIG_PATH
    from aidd.config.model import DOC_KINDS as DOC_KINDS
    from aidd.config.model import EDITOR_SCHEMA as EDITOR_SCHEMA
    from aidd.config.model import MAX_REVIEW_AGE_DAYS as MAX_REVIEW_AGE_DAYS
    from aidd.config.model import MAX_RUNBOOK_AGE_DAYS as MAX_RUNBOOK_AGE_DAYS
    from aidd.config.model import POOL_OF as POOL_OF
    from aidd.config.model import PROFILES as PROFILES
    from aidd.config.model import ROUTE_KEYS as ROUTE_KEYS
    from aidd.config.model import ROUTE_RANK as ROUTE_RANK
    from aidd.config.model import SCHEMA_MODELINE as SCHEMA_MODELINE
    from aidd.config.model import Config as Config
    from aidd.config.model import ConfigError as ConfigError
    from aidd.config.model import area_paths as area_paths
    from aidd.config.model import default_docs_required as default_docs_required
    from aidd.config.model import major_conditions as major_conditions
    from aidd.config.model import schema_modeline as schema_modeline
    from aidd.config.profile_data import profiles as profiles
    from aidd.config.project import CRA_TARGET as CRA_TARGET
    from aidd.config.project import EXISTING_STRUCTURE as EXISTING_STRUCTURE
    from aidd.config.project import PROJECT_DEFAULTS as PROJECT_DEFAULTS
    from aidd.config.project import PROJECT_NO_UI as PROJECT_NO_UI
    from aidd.config.project import cost_hint as cost_hint
    from aidd.config.project import effective_project as effective_project
    from aidd.config.project import hold_hint as hold_hint
    from aidd.config.project import project_block as project_block
    from aidd.config.project import project_compliance as project_compliance
    from aidd.config.project import project_defaults as project_defaults
    from aidd.config.project import project_findings as project_findings
    from aidd.config.project import project_markdown as project_markdown
    from aidd.config.project import theme_hint as theme_hint
    from aidd.config.standards_policy import registry_ids as registry_ids
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "AGENTS_MD": "harnesses",
            "CONFIG_PATH": "model",
            "CRA_TARGET": "project",
            "Config": "model",
            "ConfigError": "model",
            "DOC_KINDS": "model",
            "EDITOR_SCHEMA": "model",
            "EVIDENCE_DIR": "layout",
            "EXISTING_STRUCTURE": "project",
            "HARNESSES": "harnesses",
            "HARNESS_RULES_FILE": "layout",
            "MARKETPLACE": "harness_settings",
            "MAX_REVIEW_AGE_DAYS": "model",
            "MAX_RUNBOOK_AGE_DAYS": "model",
            "OUTPUT_IGNORE": "layout",
            "PLUGIN_NOTE": "harnesses",
            "POOL_OF": "model",
            "PREVIEW_DIR": "layout",
            "PROFILES": "model",
            "PROJECT_DEFAULTS": "project",
            "PROJECT_NO_UI": "project",
            "ROUTE_KEYS": "model",
            "ROUTE_RANK": "model",
            "SCHEMA_MODELINE": "model",
            "SELECTOR": "loading",
            "TEAM_MARK": "harness_settings",
            "TEAM_PREFIX": "harness_settings",
            "UNREAD_PARENT": "loading",
            "VIEWS_DIR": "layout",
            "area_paths": "model",
            "ask_rule_harnesses": "harnesses",
            "claude_config_dir": "harness_settings",
            "claude_settings_paths": "harness_settings",
            "collect_extends": "extends",
            "cost_hint": "project",
            "default_docs_required": "model",
            "harness_paths": "harnesses",
            "harnesses_table": "harnesses",
            "hold_hint": "project",
            "is_agent": "identities",
            "is_bot": "identities",
            "load_file": "loading",
            "load_text": "loading",
            "major_conditions": "model",
            "merge_risks": "loading",
            "names_an_agent": "identities",
            "normalize_identity": "identities",
            "org_preset_text": "extends",
            "plugin_enabled": "harness_settings",
            "plugins_enabled": "harness_settings",
            "pointer_files": "harnesses",
            "profiles": "profile_data",
            "project_block": "project",
            "project_compliance": "project",
            "project_defaults": "project",
            "effective_project": "project",
            "project_findings": "project",
            "project_markdown": "project",
            "registry_ids": "standards_policy",
            "schema_modeline": "model",
            "selector": "loading",
            "theme_hint": "project",
            "unreadable_claude_settings": "harness_settings",
            "user_plugins_enabled": "harness_settings",
        },
    )
