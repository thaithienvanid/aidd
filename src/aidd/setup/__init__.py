"""Adopt a repository and keep it adopted: `aidd init`, `upgrade`, `uninstall`, and `doctor`, the detection behind them,
importing a plan or issues as Specs, and keeping the CLI itself current (`aidd self-update`).

The children: adoption (init), config_template, team_install, harness_text, hook_wiring, claude_plugins, pins, files, upgrading,
self_updating, uninstalling, doctor_checks, doctor_probes, detection, plan_import, issue_import, and autopilot_readiness. Authoring and
validating work items (`aidd new`, `aidd validate`) live in aidd.workitems.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "AUTOPILOT_CHECKLIST",
    "AUTOPILOT_CHECKLIST_TITLE",
    "DEFAULT_ISSUE_LIMIT",
    "InitOptions",
    "MAX_ISSUE_LIMIT",
    "RESTART_NOTICE",
    "SMOKE_TEST",
    "autopilot_advisor_line",
    "autopilot_checks",
    "build_imported_spec",
    "default_held",
    "detect",
    "detect_harnesses",
    "detection_markdown",
    "installed_harnesses",
    "doctor",
    "found_to_fit",
    "init",
    "issues_from_file",
    "issues_from_github",
    "pin_workflow",
    "auto_update",
    "runbook_checks",
    "self_update",
    "stack_radar",
    "uninstall",
    "upgrade",
    "write_issue_specs",
    "wrote_claude_code_files",
]

if TYPE_CHECKING:
    from aidd.setup.adoption import RESTART_NOTICE as RESTART_NOTICE
    from aidd.setup.adoption import InitOptions as InitOptions
    from aidd.setup.adoption import detect_harnesses as detect_harnesses
    from aidd.setup.adoption import init as init
    from aidd.setup.adoption import installed_harnesses as installed_harnesses
    from aidd.setup.adoption import wrote_claude_code_files as wrote_claude_code_files
    from aidd.setup.autopilot_readiness import AUTOPILOT_CHECKLIST as AUTOPILOT_CHECKLIST
    from aidd.setup.autopilot_readiness import AUTOPILOT_CHECKLIST_TITLE as AUTOPILOT_CHECKLIST_TITLE
    from aidd.setup.autopilot_readiness import autopilot_advisor_line as autopilot_advisor_line
    from aidd.setup.autopilot_readiness import autopilot_checks as autopilot_checks
    from aidd.setup.config_template import SMOKE_TEST as SMOKE_TEST
    from aidd.setup.detection import default_held as default_held
    from aidd.setup.detection import detect as detect
    from aidd.setup.detection import detection_markdown as detection_markdown
    from aidd.setup.detection import found_to_fit as found_to_fit
    from aidd.setup.detection import stack_radar as stack_radar
    from aidd.setup.doctor_checks import doctor as doctor
    from aidd.setup.doctor_checks import runbook_checks as runbook_checks
    from aidd.setup.issue_import import DEFAULT_ISSUE_LIMIT as DEFAULT_ISSUE_LIMIT
    from aidd.setup.issue_import import MAX_ISSUE_LIMIT as MAX_ISSUE_LIMIT
    from aidd.setup.issue_import import issues_from_file as issues_from_file
    from aidd.setup.issue_import import issues_from_github as issues_from_github
    from aidd.setup.issue_import import write_issue_specs as write_issue_specs
    from aidd.setup.pins import pin_workflow as pin_workflow
    from aidd.setup.plan_import import build_imported_spec as build_imported_spec
    from aidd.setup.self_updating import auto_update as auto_update
    from aidd.setup.self_updating import self_update as self_update
    from aidd.setup.uninstalling import uninstall as uninstall
    from aidd.setup.upgrading import upgrade as upgrade
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "AUTOPILOT_CHECKLIST": "autopilot_readiness",
            "AUTOPILOT_CHECKLIST_TITLE": "autopilot_readiness",
            "DEFAULT_ISSUE_LIMIT": "issue_import",
            "MAX_ISSUE_LIMIT": "issue_import",
            "RESTART_NOTICE": "adoption",
            "SMOKE_TEST": "config_template",
            "autopilot_advisor_line": "autopilot_readiness",
            "autopilot_checks": "autopilot_readiness",
            "build_imported_spec": "plan_import",
            "default_held": "detection",
            "detect": "detection",
            "detect_harnesses": "adoption",
            "detection_markdown": "detection",
            "installed_harnesses": "adoption",
            "doctor": "doctor_checks",
            "found_to_fit": "detection",
            "InitOptions": "adoption",
            "init": "adoption",
            "issues_from_file": "issue_import",
            "issues_from_github": "issue_import",
            "pin_workflow": "pins",
            "auto_update": "self_updating",
            "runbook_checks": "doctor_checks",
            "self_update": "self_updating",
            "stack_radar": "detection",
            "uninstall": "uninstalling",
            "upgrade": "upgrading",
            "write_issue_specs": "issue_import",
            "wrote_claude_code_files": "adoption",
        },
    )
