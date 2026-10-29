"""`.aidd/config.yaml`: load it, merge its `extends` parents, and compute the effective gates, plus the baseline,
identities, harness settings, and the project block.

Gates can only get stricter: a child config or a gate override that would loosen the profile is ignored and reported
as a warning.

The children: model (`Config` and the values its keys take), loading (`load_file`, `load_text`), extends (the parents,
read from the repository or fetched by URL, and the org preset), extends_merge (how a child merges over them),
baseline, identities, harnesses, harness_settings, project, standards_policy, and layout (where aidd writes:
`.aidd/`'s output folders and the state in the git directory).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "AGENTS_MD",
    "COMPONENTS",
    "CONFIG_PATH",
    "EDITOR_SCHEMA",
    "SCHEMA_MODELINE",
    "schema_modeline",
    "Config",
    "ConfigError",
    "DELEGATE_MODES",
    "DOC_KINDS",
    "EMPTY_APPROVERS",
    "EVIDENCE_DIR",
    "EXISTING_STRUCTURE",
    "CRA_TARGET",
    "GUARD_LOG_FILE",
    "HARNESSES",
    "HOOK_LEVELS",
    "MARKETPLACE",
    "MAX_REVIEW_AGE_DAYS",
    "MAX_RUNBOOK_AGE_DAYS",
    "OUTPUT_IGNORE",
    "PLUGIN_NOTE",
    "FAIL_CLOSED_PROFILES",
    "FAIL_CLOSED_MODES",
    "POOL_OF",
    "PREVIEW_DIR",
    "PROJECT_DEFAULTS",
    "PROJECT_NO_UI",
    "ROUTE_KEYS",
    "STATE_DIR",
    "TEAM_MARK",
    "TEAM_PREFIX",
    "TRAILER",
    "UNREAD_PARENT",
    "VIEWS_DIR",
    "WATCHED_STATE_DIR",
    "advice",
    "agent_account",
    "agent_coauthors",
    "baseline_data",
    "baseline_json_text",
    "browser_hosts",
    "claude_config_dir",
    "claude_settings_paths",
    "collect_extends",
    "component_on",
    "cost_hint",
    "default_docs_required",
    "delegate_mode",
    "delegate_set",
    "HELPER_MODES",
    "helpers_mode",
    "effective_mode",
    "effective_project",
    "extract_trailers",
    "guard_log",
    "guarded_harnesses",
    "harnesses_table",
    "hold_hint",
    "hook_level",
    "human_coauthors",
    "is_agent",
    "is_bot",
    "load_file",
    "load_text",
    "major_conditions",
    "normalize_identity",
    "operator_email",
    "unlisted_local_approver",
    "operator_login",
    "gh_account_count",
    "org_preset_text",
    "plugin_enabled",
    "plugins_enabled",
    "user_plugins_enabled",
    "pointer_files",
    "preset_tenant",
    "profile_mode",
    "settings",
    "settings_text",
    "profiles",
    "project_compliance",
    "project_defaults",
    "project_findings",
    "project_block",
    "project_markdown",
    "registry_ids",
    "scoped",
    "split_tenant",
    "state_dir",
    "team_installed",
    "theme_hint",
    "unreadable_claude_settings",
]

if TYPE_CHECKING:
    from aidd.config.baseline import baseline_data as baseline_data
    from aidd.config.baseline import baseline_json_text as baseline_json_text
    from aidd.config.baseline import profile_mode as profile_mode
    from aidd.config.baseline import profiles as profiles
    from aidd.config.extends import collect_extends as collect_extends
    from aidd.config.extends import org_preset_text as org_preset_text
    from aidd.config.harness_settings import MARKETPLACE as MARKETPLACE
    from aidd.config.harness_settings import TEAM_MARK as TEAM_MARK
    from aidd.config.harness_settings import TEAM_PREFIX as TEAM_PREFIX
    from aidd.config.harness_settings import claude_config_dir as claude_config_dir
    from aidd.config.harness_settings import claude_settings_paths as claude_settings_paths
    from aidd.config.harness_settings import plugin_enabled as plugin_enabled
    from aidd.config.harness_settings import plugins_enabled as plugins_enabled
    from aidd.config.harness_settings import team_installed as team_installed
    from aidd.config.harness_settings import unreadable_claude_settings as unreadable_claude_settings
    from aidd.config.harness_settings import user_plugins_enabled as user_plugins_enabled
    from aidd.config.harnesses import AGENTS_MD as AGENTS_MD
    from aidd.config.harnesses import HARNESSES as HARNESSES
    from aidd.config.harnesses import PLUGIN_NOTE as PLUGIN_NOTE
    from aidd.config.harnesses import guarded_harnesses as guarded_harnesses
    from aidd.config.harnesses import harnesses_table as harnesses_table
    from aidd.config.harnesses import pointer_files as pointer_files
    from aidd.config.identities import TRAILER as TRAILER
    from aidd.config.identities import agent_account as agent_account
    from aidd.config.identities import agent_coauthors as agent_coauthors
    from aidd.config.identities import extract_trailers as extract_trailers
    from aidd.config.identities import gh_account_count as gh_account_count
    from aidd.config.identities import human_coauthors as human_coauthors
    from aidd.config.identities import is_agent as is_agent
    from aidd.config.identities import is_bot as is_bot
    from aidd.config.identities import normalize_identity as normalize_identity
    from aidd.config.identities import operator_email as operator_email
    from aidd.config.identities import operator_login as operator_login
    from aidd.config.identities import scoped as scoped
    from aidd.config.identities import split_tenant as split_tenant
    from aidd.config.identities import unlisted_local_approver as unlisted_local_approver
    from aidd.config.layout import EVIDENCE_DIR as EVIDENCE_DIR
    from aidd.config.layout import GUARD_LOG_FILE as GUARD_LOG_FILE
    from aidd.config.layout import OUTPUT_IGNORE as OUTPUT_IGNORE
    from aidd.config.layout import PREVIEW_DIR as PREVIEW_DIR
    from aidd.config.layout import STATE_DIR as STATE_DIR
    from aidd.config.layout import VIEWS_DIR as VIEWS_DIR
    from aidd.config.layout import WATCHED_STATE_DIR as WATCHED_STATE_DIR
    from aidd.config.layout import guard_log as guard_log
    from aidd.config.layout import state_dir as state_dir
    from aidd.config.loading import UNREAD_PARENT as UNREAD_PARENT
    from aidd.config.loading import advice as advice
    from aidd.config.loading import load_file as load_file
    from aidd.config.loading import load_text as load_text
    from aidd.config.loading import preset_tenant as preset_tenant
    from aidd.config.model import COMPONENTS as COMPONENTS
    from aidd.config.model import CONFIG_PATH as CONFIG_PATH
    from aidd.config.model import DELEGATE_MODES as DELEGATE_MODES
    from aidd.config.model import DOC_KINDS as DOC_KINDS
    from aidd.config.model import EDITOR_SCHEMA as EDITOR_SCHEMA
    from aidd.config.model import EMPTY_APPROVERS as EMPTY_APPROVERS
    from aidd.config.model import FAIL_CLOSED_MODES as FAIL_CLOSED_MODES
    from aidd.config.model import FAIL_CLOSED_PROFILES as FAIL_CLOSED_PROFILES
    from aidd.config.model import HELPER_MODES as HELPER_MODES
    from aidd.config.model import HOOK_LEVELS as HOOK_LEVELS
    from aidd.config.model import MAX_REVIEW_AGE_DAYS as MAX_REVIEW_AGE_DAYS
    from aidd.config.model import MAX_RUNBOOK_AGE_DAYS as MAX_RUNBOOK_AGE_DAYS
    from aidd.config.model import POOL_OF as POOL_OF
    from aidd.config.model import ROUTE_KEYS as ROUTE_KEYS
    from aidd.config.model import SCHEMA_MODELINE as SCHEMA_MODELINE
    from aidd.config.model import Config as Config
    from aidd.config.model import ConfigError as ConfigError
    from aidd.config.model import browser_hosts as browser_hosts
    from aidd.config.model import component_on as component_on
    from aidd.config.model import default_docs_required as default_docs_required
    from aidd.config.model import delegate_mode as delegate_mode
    from aidd.config.model import delegate_set as delegate_set
    from aidd.config.model import effective_mode as effective_mode
    from aidd.config.model import helpers_mode as helpers_mode
    from aidd.config.model import hook_level as hook_level
    from aidd.config.model import major_conditions as major_conditions
    from aidd.config.model import schema_modeline as schema_modeline
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
    from aidd.config.settings_view import settings as settings
    from aidd.config.settings_view import settings_text as settings_text
    from aidd.config.standards_policy import registry_ids as registry_ids
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "AGENTS_MD": "harnesses",
            "COMPONENTS": "model",
            "CONFIG_PATH": "model",
            "EDITOR_SCHEMA": "model",
            "SCHEMA_MODELINE": "model",
            "schema_modeline": "model",
            "Config": "model",
            "ConfigError": "model",
            "DELEGATE_MODES": "model",
            "DOC_KINDS": "model",
            "EMPTY_APPROVERS": "model",
            "EVIDENCE_DIR": "layout",
            "EXISTING_STRUCTURE": "project",
            "CRA_TARGET": "project",
            "GUARD_LOG_FILE": "layout",
            "HARNESSES": "harnesses",
            "HOOK_LEVELS": "model",
            "MARKETPLACE": "harness_settings",
            "MAX_REVIEW_AGE_DAYS": "model",
            "MAX_RUNBOOK_AGE_DAYS": "model",
            "OUTPUT_IGNORE": "layout",
            "PLUGIN_NOTE": "harnesses",
            "POOL_OF": "model",
            "PREVIEW_DIR": "layout",
            "PROJECT_DEFAULTS": "project",
            "PROJECT_NO_UI": "project",
            "ROUTE_KEYS": "model",
            "FAIL_CLOSED_PROFILES": "model",
            "FAIL_CLOSED_MODES": "model",
            "STATE_DIR": "layout",
            "TEAM_MARK": "harness_settings",
            "TEAM_PREFIX": "harness_settings",
            "TRAILER": "identities",
            "UNREAD_PARENT": "loading",
            "VIEWS_DIR": "layout",
            "WATCHED_STATE_DIR": "layout",
            "advice": "loading",
            "agent_account": "identities",
            "agent_coauthors": "identities",
            "baseline_data": "baseline",
            "baseline_json_text": "baseline",
            "claude_config_dir": "harness_settings",
            "claude_settings_paths": "harness_settings",
            "collect_extends": "extends",
            "browser_hosts": "model",
            "component_on": "model",
            "cost_hint": "project",
            "default_docs_required": "model",
            "major_conditions": "model",
            "delegate_mode": "model",
            "delegate_set": "model",
            "HELPER_MODES": "model",
            "helpers_mode": "model",
            "effective_mode": "model",
            "effective_project": "project",
            "extract_trailers": "identities",
            "guard_log": "layout",
            "guarded_harnesses": "harnesses",
            "harnesses_table": "harnesses",
            "hold_hint": "project",
            "hook_level": "model",
            "human_coauthors": "identities",
            "is_agent": "identities",
            "is_bot": "identities",
            "load_file": "loading",
            "load_text": "loading",
            "normalize_identity": "identities",
            "operator_email": "identities",
            "unlisted_local_approver": "identities",
            "operator_login": "identities",
            "gh_account_count": "identities",
            "org_preset_text": "extends",
            "plugin_enabled": "harness_settings",
            "plugins_enabled": "harness_settings",
            "user_plugins_enabled": "harness_settings",
            "pointer_files": "harnesses",
            "preset_tenant": "loading",
            "profile_mode": "baseline",
            "settings": "settings_view",
            "settings_text": "settings_view",
            "profiles": "baseline",
            "project_compliance": "project",
            "project_defaults": "project",
            "project_findings": "project",
            "project_block": "project",
            "project_markdown": "project",
            "registry_ids": "standards_policy",
            "scoped": "identities",
            "split_tenant": "identities",
            "state_dir": "layout",
            "team_installed": "harness_settings",
            "theme_hint": "project",
            "unreadable_claude_settings": "harness_settings",
        },
    )
