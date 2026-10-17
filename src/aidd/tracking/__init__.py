"""What is open and how the work goes: the next steps (this change's forecast, `aidd list`), upkeep, the status rollup
(`aidd digest`, release notes), metrics and their export, the observe window, and control bands."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "APPROVER_WAITS",
    "Band",
    "Filters",
    "METRICS_SCHEMA_VERSION",
    "METRIC_GROUPS",
    "EXPORT_FORMATS",
    "ROLLUP_EVENTS_FILE",
    "ROUTE_ORDER",
    "age_text",
    "goals",
    "small_goal_ladders",
    "goals_markdown",
    "autonomy",
    "autonomy_markdown",
    "autopilot_run_measures",
    "band_from_config",
    "band_intent_text",
    "collect_records",
    "cost_per_change",
    "default_since",
    "delivery_outcomes",
    "digest_markdown",
    "digest_page",
    "dora",
    "dora_markdown",
    "flaky",
    "flaky_markdown",
    "forecast",
    "forecast_markdown",
    "gate_events",
    "grouped_metrics",
    "guard_denials",
    "guard_markdown",
    "handoff_health",
    "judge_band",
    "load_events",
    "load_ledger",
    "load_series",
    "markdown_grouped",
    "metrics_markdown",
    "new_step",
    "next_steps_markdown",
    "open_work",
    "pack_lines",
    "plan",
    "proposals_text",
    "propose_standard_changes",
    "records_by_control",
    "release_notes",
    "release_notes_markdown",
    "render_export",
    "rollup_window",
    "runs_markdown",
    "status_digest",
    "suite_runs",
    "summarize_events",
    "upkeep_items",
    "upkeep_markdown",
    "watch_window",
    "window_seconds",
]

if TYPE_CHECKING:
    from aidd.tracking.control_bands import Band as Band
    from aidd.tracking.control_bands import band_from_config as band_from_config
    from aidd.tracking.control_bands import band_intent_text as band_intent_text
    from aidd.tracking.control_bands import judge_band as judge_band
    from aidd.tracking.control_bands import load_series as load_series
    from aidd.tracking.goal_status import goals as goals
    from aidd.tracking.goal_status import goals_markdown as goals_markdown
    from aidd.tracking.goal_status import small_goal_ladders as small_goal_ladders
    from aidd.tracking.metrics import METRIC_GROUPS as METRIC_GROUPS
    from aidd.tracking.metrics import METRICS_SCHEMA_VERSION as METRICS_SCHEMA_VERSION
    from aidd.tracking.metrics import autonomy as autonomy
    from aidd.tracking.metrics import autonomy_markdown as autonomy_markdown
    from aidd.tracking.metrics import autopilot_run_measures as autopilot_run_measures
    from aidd.tracking.metrics import cost_per_change as cost_per_change
    from aidd.tracking.metrics import delivery_outcomes as delivery_outcomes
    from aidd.tracking.metrics import dora as dora
    from aidd.tracking.metrics import dora_markdown as dora_markdown
    from aidd.tracking.metrics import flaky as flaky
    from aidd.tracking.metrics import flaky_markdown as flaky_markdown
    from aidd.tracking.metrics import gate_events as gate_events
    from aidd.tracking.metrics import grouped_metrics as grouped_metrics
    from aidd.tracking.metrics import guard_denials as guard_denials
    from aidd.tracking.metrics import guard_markdown as guard_markdown
    from aidd.tracking.metrics import handoff_health as handoff_health
    from aidd.tracking.metrics import load_events as load_events
    from aidd.tracking.metrics import load_ledger as load_ledger
    from aidd.tracking.metrics import markdown_grouped as markdown_grouped
    from aidd.tracking.metrics import metrics_markdown as metrics_markdown
    from aidd.tracking.metrics import proposals_text as proposals_text
    from aidd.tracking.metrics import propose_standard_changes as propose_standard_changes
    from aidd.tracking.metrics import runs_markdown as runs_markdown
    from aidd.tracking.metrics import suite_runs as suite_runs
    from aidd.tracking.metrics import summarize_events as summarize_events
    from aidd.tracking.next_steps import APPROVER_WAITS as APPROVER_WAITS
    from aidd.tracking.next_steps import ROUTE_ORDER as ROUTE_ORDER
    from aidd.tracking.next_steps import Filters as Filters
    from aidd.tracking.next_steps import age_text as age_text
    from aidd.tracking.next_steps import forecast as forecast
    from aidd.tracking.next_steps import forecast_markdown as forecast_markdown
    from aidd.tracking.next_steps import new_step as new_step
    from aidd.tracking.next_steps import next_steps_markdown as next_steps_markdown
    from aidd.tracking.next_steps import open_work as open_work
    from aidd.tracking.next_steps import pack_lines as pack_lines
    from aidd.tracking.next_steps import plan as plan
    from aidd.tracking.observe import watch_window as watch_window
    from aidd.tracking.observe import window_seconds as window_seconds
    from aidd.tracking.record_export import EXPORT_FORMATS as EXPORT_FORMATS
    from aidd.tracking.record_export import collect_records as collect_records
    from aidd.tracking.record_export import records_by_control as records_by_control
    from aidd.tracking.record_export import render_export as render_export
    from aidd.tracking.status_rollup import ROLLUP_EVENTS_FILE as ROLLUP_EVENTS_FILE
    from aidd.tracking.status_rollup import default_since as default_since
    from aidd.tracking.status_rollup import digest_markdown as digest_markdown
    from aidd.tracking.status_rollup import digest_page as digest_page
    from aidd.tracking.status_rollup import release_notes as release_notes
    from aidd.tracking.status_rollup import release_notes_markdown as release_notes_markdown
    from aidd.tracking.status_rollup import rollup_window as rollup_window
    from aidd.tracking.status_rollup import status_digest as status_digest
    from aidd.tracking.upkeep import upkeep_items as upkeep_items
    from aidd.tracking.upkeep import upkeep_markdown as upkeep_markdown
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "APPROVER_WAITS": "next_steps",
            "Band": "control_bands",
            "Filters": "next_steps",
            "METRICS_SCHEMA_VERSION": "metrics",
            "METRIC_GROUPS": "metrics",
            "EXPORT_FORMATS": "record_export",
            "ROLLUP_EVENTS_FILE": "status_rollup",
            "ROUTE_ORDER": "next_steps",
            "age_text": "next_steps",
            "goals": "goal_status",
            "small_goal_ladders": "goal_status",
            "goals_markdown": "goal_status",
            "autonomy": "metrics",
            "autonomy_markdown": "metrics",
            "autopilot_run_measures": "metrics",
            "band_from_config": "control_bands",
            "band_intent_text": "control_bands",
            "collect_records": "record_export",
            "cost_per_change": "metrics",
            "delivery_outcomes": "metrics",
            "digest_markdown": "status_rollup",
            "digest_page": "status_rollup",
            "dora": "metrics",
            "dora_markdown": "metrics",
            "flaky": "metrics",
            "flaky_markdown": "metrics",
            "forecast": "next_steps",
            "forecast_markdown": "next_steps",
            "gate_events": "metrics",
            "handoff_health": "metrics",
            "suite_runs": "metrics",
            "grouped_metrics": "metrics",
            "guard_denials": "metrics",
            "guard_markdown": "metrics",
            "judge_band": "control_bands",
            "load_events": "metrics",
            "load_ledger": "metrics",
            "load_series": "control_bands",
            "markdown_grouped": "metrics",
            "metrics_markdown": "metrics",
            "new_step": "next_steps",
            "next_steps_markdown": "next_steps",
            "open_work": "next_steps",
            "pack_lines": "next_steps",
            "plan": "next_steps",
            "proposals_text": "metrics",
            "propose_standard_changes": "metrics",
            "records_by_control": "record_export",
            "release_notes": "status_rollup",
            "release_notes_markdown": "status_rollup",
            "render_export": "record_export",
            "rollup_window": "status_rollup",
            "default_since": "status_rollup",
            "runs_markdown": "metrics",
            "status_digest": "status_rollup",
            "summarize_events": "metrics",
            "upkeep_items": "upkeep",
            "upkeep_markdown": "upkeep",
            "watch_window": "observe",
            "window_seconds": "observe",
        },
    )
