"""Adopt a repository and keep it adopted: `aidd init`, `upgrade`, `uninstall`, and `doctor`, the detection behind them,
and keeping the CLI itself current (`aidd self-update`).

The children: adoption (init), ask_rules (the coding agents' ask rules), init_plan (init --dry-run), config_keep (init --force), skill_files, config_template, team_install, domain_packs, harness_files, harness_text, mcp_wiring, claude_plugins, pins, files,
ignore_lines, manifests, migrating, migration_blocks, migration_specs, upgrading, self_updating, uninstalling, doctor_checks, doctor_harnesses, doctor_probes, and detection. Authoring and
validating work items (`aidd new`, `aidd validate`) live in aidd.workitems.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "SMOKE_TEST",
    "UPGRADE_PROBLEM",
    "InitOptions",
    "agents_to_restart",
    "auto_update",
    "detect",
    "detection_markdown",
    "doctor",
    "doctor_findings",
    "dry_run_lines",
    "found_to_fit",
    "full_ref",
    "init",
    "init_harnesses",
    "pack_hint",
    "pin_workflow",
    "plan_init",
    "restart_notice",
    "self_update",
    "stack_radar",
    "uninstall",
    "upgrade",
]

if TYPE_CHECKING:
    from aidd.setup.adoption import InitOptions as InitOptions
    from aidd.setup.adoption import agents_to_restart as agents_to_restart
    from aidd.setup.adoption import init as init
    from aidd.setup.adoption import init_harnesses as init_harnesses
    from aidd.setup.adoption import restart_notice as restart_notice
    from aidd.setup.config_template import SMOKE_TEST as SMOKE_TEST
    from aidd.setup.detection import detect as detect
    from aidd.setup.detection import detection_markdown as detection_markdown
    from aidd.setup.detection import found_to_fit as found_to_fit
    from aidd.setup.detection import stack_radar as stack_radar
    from aidd.setup.doctor_checks import doctor as doctor
    from aidd.setup.doctor_checks import doctor_findings as doctor_findings
    from aidd.setup.domain_packs import pack_hint as pack_hint
    from aidd.setup.init_plan import dry_run_lines as dry_run_lines
    from aidd.setup.init_plan import plan_init as plan_init
    from aidd.setup.pins import full_ref as full_ref
    from aidd.setup.pins import pin_workflow as pin_workflow
    from aidd.setup.self_updating import auto_update as auto_update
    from aidd.setup.self_updating import self_update as self_update
    from aidd.setup.uninstalling import uninstall as uninstall
    from aidd.setup.upgrading import UPGRADE_PROBLEM as UPGRADE_PROBLEM
    from aidd.setup.upgrading import upgrade as upgrade
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "SMOKE_TEST": "config_template",
            "UPGRADE_PROBLEM": "upgrading",
            "InitOptions": "adoption",
            "agents_to_restart": "adoption",
            "auto_update": "self_updating",
            "detect": "detection",
            "detection_markdown": "detection",
            "doctor": "doctor_checks",
            "doctor_findings": "doctor_checks",
            "dry_run_lines": "init_plan",
            "found_to_fit": "detection",
            "full_ref": "pins",
            "init": "adoption",
            "init_harnesses": "adoption",
            "pack_hint": "domain_packs",
            "pin_workflow": "pins",
            "plan_init": "init_plan",
            "restart_notice": "adoption",
            "self_update": "self_updating",
            "stack_radar": "detection",
            "uninstall": "uninstalling",
            "upgrade": "upgrading",
        },
    )
