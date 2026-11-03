"""Adopt a repository and keep it adopted: `aidd init`, `upgrade`, `uninstall`, and `doctor`, the detection behind them,
and keeping the CLI itself current (`aidd self-update`).

The children: adoption (init), config_template, team_install, harness_text, hook_wiring, claude_plugins, pins, files, upgrading,
self_updating, uninstalling, launcher_location, doctor_checks, doctor_probes, detection, and autopilot_readiness. Authoring and
validating work items (`aidd new`, `aidd validate`) live in aidd.workitems.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "InitOptions",
    "SMOKE_TEST",
    "agents_to_restart",
    "auto_update",
    "detect",
    "detect_harnesses",
    "detection_markdown",
    "doctor",
    "found_to_fit",
    "full_ref",
    "init",
    "installed_harnesses",
    "pin_workflow",
    "restart_notice",
    "runbook_checks",
    "self_update",
    "stack_radar",
    "uninstall",
    "upgrade",
]

if TYPE_CHECKING:
    from aidd.setup.adoption import InitOptions as InitOptions
    from aidd.setup.adoption import agents_to_restart as agents_to_restart
    from aidd.setup.adoption import detect_harnesses as detect_harnesses
    from aidd.setup.adoption import init as init
    from aidd.setup.adoption import installed_harnesses as installed_harnesses
    from aidd.setup.adoption import restart_notice as restart_notice
    from aidd.setup.config_template import SMOKE_TEST as SMOKE_TEST
    from aidd.setup.detection import detect as detect
    from aidd.setup.detection import detection_markdown as detection_markdown
    from aidd.setup.detection import found_to_fit as found_to_fit
    from aidd.setup.detection import stack_radar as stack_radar
    from aidd.setup.doctor_checks import doctor as doctor
    from aidd.setup.doctor_checks import runbook_checks as runbook_checks
    from aidd.setup.pins import full_ref as full_ref
    from aidd.setup.pins import pin_workflow as pin_workflow
    from aidd.setup.self_updating import auto_update as auto_update
    from aidd.setup.self_updating import self_update as self_update
    from aidd.setup.uninstalling import uninstall as uninstall
    from aidd.setup.upgrading import upgrade as upgrade
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "InitOptions": "adoption",
            "SMOKE_TEST": "config_template",
            "agents_to_restart": "adoption",
            "auto_update": "self_updating",
            "detect": "detection",
            "detect_harnesses": "adoption",
            "detection_markdown": "detection",
            "doctor": "doctor_checks",
            "found_to_fit": "detection",
            "full_ref": "pins",
            "init": "adoption",
            "installed_harnesses": "adoption",
            "pin_workflow": "pins",
            "restart_notice": "adoption",
            "runbook_checks": "doctor_checks",
            "self_update": "self_updating",
            "stack_radar": "detection",
            "uninstall": "uninstalling",
            "upgrade": "upgrading",
        },
    )
