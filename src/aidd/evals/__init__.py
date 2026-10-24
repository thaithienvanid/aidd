"""Evaluations.

examples: run every examples/<case>/ through the gate and compare with expected.json.
routing: ask any agent CLI to route each scenario in evals/routing/*.yaml and score it.
roles: send each aidd-team role a task with a seeded defect (evals/roles/*.yaml) and score the answer.
standards: list the team's standards registry and the entries past their review cadence (emerging 90 days, established
    365, or the entry's own) or their review_due.
tasks: send your own agent configuration real tasks (evals/tasks/*.yaml), each in a scratch worktree, and grade it by commands that must pass.

The agent suites are measurements, not fixtures: `measure` runs a suite K times and reports each
scenario's pass@1 (the share of trials that passed) and pass^K (every trial passed); a control run
without the aidd material gives the baseline the material is measured against (the lift); and
`record` appends one JSON line per run, so scores are compared over time, not remembered. Each line names the
commit that holds its material and a hash of its material (`material_sha256`), so `report` marks a row stale once the material changed.

The children: examples, suites (routing, roles, tasks, and `measure`), records (the recorded runs and `report`), and
standards_audit.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "append_record",
    "bulk_checked_dates",
    "cases_path",
    "load_scenarios",
    "material_files",
    "material_sha256",
    "materialize",
    "measure",
    "record_line",
    "repo_state",
    "report",
    "run_examples",
    "run_roles",
    "run_routing",
    "run_tasks",
    "stale_id_citations",
    "summary",
    "unevidenced_standards",
    "unpinned_extensions",
    "unsourced_standards",
]

if TYPE_CHECKING:
    from aidd.evals.examples import materialize as materialize
    from aidd.evals.examples import run_examples as run_examples
    from aidd.evals.records import append_record as append_record
    from aidd.evals.records import cases_path as cases_path
    from aidd.evals.records import material_files as material_files
    from aidd.evals.records import material_sha256 as material_sha256
    from aidd.evals.records import record_line as record_line
    from aidd.evals.records import repo_state as repo_state
    from aidd.evals.records import report as report
    from aidd.evals.standards_audit import bulk_checked_dates as bulk_checked_dates
    from aidd.evals.standards_audit import stale_id_citations as stale_id_citations
    from aidd.evals.standards_audit import unevidenced_standards as unevidenced_standards
    from aidd.evals.standards_audit import unpinned_extensions as unpinned_extensions
    from aidd.evals.standards_audit import unsourced_standards as unsourced_standards
    from aidd.evals.suites import load_scenarios as load_scenarios
    from aidd.evals.suites import measure as measure
    from aidd.evals.suites import run_roles as run_roles
    from aidd.evals.suites import run_routing as run_routing
    from aidd.evals.suites import run_tasks as run_tasks
    from aidd.evals.suites import summary as summary
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "append_record": "records",
            "bulk_checked_dates": "standards_audit",
            "cases_path": "records",
            "load_scenarios": "suites",
            "material_files": "records",
            "material_sha256": "records",
            "materialize": "examples",
            "measure": "suites",
            "record_line": "records",
            "repo_state": "records",
            "report": "records",
            "run_examples": "examples",
            "run_roles": "suites",
            "run_routing": "suites",
            "run_tasks": "suites",
            "stale_id_citations": "standards_audit",
            "summary": "suites",
            "unevidenced_standards": "standards_audit",
            "unpinned_extensions": "standards_audit",
            "unsourced_standards": "standards_audit",
        },
    )
