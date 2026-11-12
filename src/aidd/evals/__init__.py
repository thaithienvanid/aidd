"""Evaluations.

routing: ask any agent CLI to route each scenario in evals/routing/*.yaml and score it.
roles: send each aidd-team role a task with a seeded defect (evals/roles/*.yaml) and score the answer.
standards: list the team's standards registry and the entries past their review cadence (emerging 90 days, established
    365, or the entry's own) or their review_due.
tasks: send your own agent configuration real tasks (a project's own `evals/tasks/*.yaml`; aidd ships none), each in a scratch worktree, and grade it by commands that must pass.

The agent suites are measurements, not fixtures: `measure` runs a suite K times and reports each
scenario's pass@1 (the share of trials that passed) and pass^K (every trial passed); a control run
without the aidd material gives the baseline the material is measured against (the lift); and
`record` appends one JSON line per run, so scores are compared over time, not remembered. Each line names the
commit that holds its material and a hash of its material (`material_sha256`), so `report` marks a row stale once the material changed.

transcripts: read a recorded Claude Code event stream (stream-json, or the hook captures) as the files the run opened, its
    tool calls, and its usage, with no model.

compare: two recorded runs of one suite, their difference in mean pass@1 with a 95% interval, and a plain verdict.
role_coverage: the role eval cases counted per role operation (a role at one loop step), from schemas/roles.json.
work: read a repository's own history (commits, Assisted-by trailers, Specs, records, handoff notes) as baselines
    and signals about how the work went, with no model.

The children: claims (what each case proves, and the claims with no case), claim_registry (who owns each kind of claim), held_out (the held-out cases and their lock), shapes (the kind of project each case shows, and the
pairs no case shows), worlds (the language and domain a live case's project is set in, and the shares no one world may pass), suites (routing, roles, tasks, and `measure`), scoring (a role or task answer as a decision, a handoff note,
whole words, and a diff), run_log (the recorded runs and `report`), compare, role_coverage, standards_audit, transcripts,
and work_history.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "MIN_COMPARE_CASES",
    "MeasuredMaterial",
    "append_run",
    "bulk_checked_dates",
    "case_problems",
    "case_shapes",
    "case_worlds",
    "cases_path",
    "claim_coverage_table",
    "claims_file",
    "compare_runs",
    "cost_summary",
    "fixture_problems",
    "held_out_ids",
    "load_scenarios",
    "mark_held_out_read",
    "material_files",
    "material_sha256",
    "measure",
    "output_cap",
    "read_transcript",
    "read_work_history",
    "record_blockers",
    "repo_state",
    "report",
    "role_case_problems",
    "role_coverage_table",
    "run_line",
    "run_roles",
    "run_routing",
    "run_tasks",
    "shape_coverage_table",
    "shape_problems",
    "shapes_file",
    "split_summary",
    "stale_id_citations",
    "suite_cases",
    "summary",
    "unevidenced_standards",
    "unpinned_extensions",
    "unsourced_standards",
    "work_history_text",
    "world_coverage_table",
    "world_problems",
    "worlds_file",
]

if TYPE_CHECKING:
    from aidd.evals.claims import case_problems as case_problems
    from aidd.evals.claims import claim_coverage_table as claim_coverage_table
    from aidd.evals.claims import claims_file as claims_file
    from aidd.evals.claims import suite_cases as suite_cases
    from aidd.evals.compare import MIN_COMPARE_CASES as MIN_COMPARE_CASES
    from aidd.evals.compare import compare_runs as compare_runs
    from aidd.evals.held_out import mark_held_out_read as mark_held_out_read
    from aidd.evals.held_out import record_blockers as record_blockers
    from aidd.evals.role_coverage import role_case_problems as role_case_problems
    from aidd.evals.role_coverage import role_coverage_table as role_coverage_table
    from aidd.evals.run_log import MeasuredMaterial as MeasuredMaterial
    from aidd.evals.run_log import append_run as append_run
    from aidd.evals.run_log import cases_path as cases_path
    from aidd.evals.run_log import material_files as material_files
    from aidd.evals.run_log import material_sha256 as material_sha256
    from aidd.evals.run_log import repo_state as repo_state
    from aidd.evals.run_log import report as report
    from aidd.evals.run_log import run_line as run_line
    from aidd.evals.shapes import case_shapes as case_shapes
    from aidd.evals.shapes import fixture_problems as fixture_problems
    from aidd.evals.shapes import shape_coverage_table as shape_coverage_table
    from aidd.evals.shapes import shape_problems as shape_problems
    from aidd.evals.shapes import shapes_file as shapes_file
    from aidd.evals.standards_audit import bulk_checked_dates as bulk_checked_dates
    from aidd.evals.standards_audit import stale_id_citations as stale_id_citations
    from aidd.evals.standards_audit import unevidenced_standards as unevidenced_standards
    from aidd.evals.standards_audit import unpinned_extensions as unpinned_extensions
    from aidd.evals.standards_audit import unsourced_standards as unsourced_standards
    from aidd.evals.suites import cost_summary as cost_summary
    from aidd.evals.suites import held_out_ids as held_out_ids
    from aidd.evals.suites import load_scenarios as load_scenarios
    from aidd.evals.suites import measure as measure
    from aidd.evals.suites import output_cap as output_cap
    from aidd.evals.suites import run_roles as run_roles
    from aidd.evals.suites import run_routing as run_routing
    from aidd.evals.suites import run_tasks as run_tasks
    from aidd.evals.suites import split_summary as split_summary
    from aidd.evals.suites import summary as summary
    from aidd.evals.transcripts import read_transcript as read_transcript
    from aidd.evals.work_history import read_work_history as read_work_history
    from aidd.evals.work_history import work_history_text as work_history_text
    from aidd.evals.worlds import case_worlds as case_worlds
    from aidd.evals.worlds import world_coverage_table as world_coverage_table
    from aidd.evals.worlds import world_problems as world_problems
    from aidd.evals.worlds import worlds_file as worlds_file
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "MIN_COMPARE_CASES": "compare",
            "MeasuredMaterial": "run_log",
            "append_run": "run_log",
            "bulk_checked_dates": "standards_audit",
            "case_problems": "claims",
            "case_shapes": "shapes",
            "case_worlds": "worlds",
            "cases_path": "run_log",
            "claim_coverage_table": "claims",
            "claims_file": "claims",
            "compare_runs": "compare",
            "cost_summary": "suites",
            "fixture_problems": "shapes",
            "held_out_ids": "suites",
            "load_scenarios": "suites",
            "mark_held_out_read": "held_out",
            "material_files": "run_log",
            "material_sha256": "run_log",
            "measure": "suites",
            "output_cap": "suites",
            "read_transcript": "transcripts",
            "read_work_history": "work_history",
            "record_blockers": "held_out",
            "repo_state": "run_log",
            "report": "run_log",
            "role_case_problems": "role_coverage",
            "role_coverage_table": "role_coverage",
            "run_line": "run_log",
            "run_roles": "suites",
            "run_routing": "suites",
            "run_tasks": "suites",
            "shape_coverage_table": "shapes",
            "shape_problems": "shapes",
            "shapes_file": "shapes",
            "split_summary": "suites",
            "stale_id_citations": "standards_audit",
            "suite_cases": "claims",
            "summary": "suites",
            "unevidenced_standards": "standards_audit",
            "unpinned_extensions": "standards_audit",
            "unsourced_standards": "standards_audit",
            "work_history_text": "work_history",
            "world_coverage_table": "worlds",
            "world_problems": "worlds",
            "worlds_file": "worlds",
        },
    )
