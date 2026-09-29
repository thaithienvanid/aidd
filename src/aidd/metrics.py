"""Summarize gate events (event.schema.json lines) into delivery and AI metrics."""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .util import EPOCH, parse_time

# The version of every `aidd metrics --json` object (schemas/metrics.schema.json). A new key keeps it; a renamed, removed,
# or retyped key bumps it.
SCHEMA_VERSION = "1"

# The pending rules a person clears: the human approvals, by rule id, with the name the output uses. The loop calls them
# approvals, never gates: the gate is the one check that decides whether a change may merge.
APPROVALS = {"spec_approval": "Spec approval", "merge_approval": "Merge approval", "specialist_review": "Specialist review"}


def load(paths: list[str], since: str | None = None) -> list[dict]:
    """Events from JSON-lines files, oldest first; with `since` (an ISO date or time), only those at or after it."""
    events = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    if since:
        since_t = _since(since)
        events = [e for e in events if (t := parse_time(e.get("ts"))) is not None and t >= since_t]
    return sorted(events, key=_when)


def _since(since: str) -> dt.datetime:
    since_t = parse_time(since)
    if since_t is None:
        raise ValueError(f"--since {since!r} is not an ISO date or time, such as 2026-09-01 or 2026-09-01T09:00:00Z")
    return since_t


def _key(e: dict) -> str:
    return f"{e.get('repo', '')}#{e.get('change', '?')}"


def _by_change(events: list[dict]) -> dict[str, list[dict]]:
    """Events grouped by change (repository and change id), in the order given."""
    out: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        out[_key(e)].append(e)
    return out


def _when(e: dict) -> dt.datetime:
    """An event's instant, for sorting: timestamps with different offsets or a `Z` compare as times, not as strings."""
    return parse_time(e.get("ts")) or EPOCH


def weeks_between(times: list[dt.datetime]) -> float | None:
    """The span of `times` in weeks, never less than one day (1/7 week), so a burst of events in one moment does not
    divide by zero. DORA's deployment frequency and the summary's throughput both divide by it, so they agree."""
    if not times:
        return None
    return max((max(times) - min(times)).total_seconds() / 604800, 1 / 7)


# Group keys for `aidd metrics --by`: a founder's projects (repo), an organization's or a company's
# repositories (owner, the part before the slash), the Spec's owner team, or a slice of the work.
GROUPS = {
    "repo": lambda e: e.get("repo") or "unknown",
    "owner": lambda e: (e.get("repo") or "unknown").split("/")[0],
    "team": lambda e: e.get("owner_team") or "no Spec",
    "profile": lambda e: e.get("profile") or "unknown",
    "route": lambda e: e.get("route") or "unknown",
    "author": lambda e: e.get("author") or "unknown",
}


def grouped(events: list[dict], by: str, target_wait: float | None = None, targets: dict | None = None) -> dict[str, dict]:
    """One summary per group. A change belongs to the group of its last event."""
    last = {k: GROUPS[by](evs[-1]) for k, evs in _by_change(events).items()}
    parts: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        parts[last[_key(e)]].append(e)
    return {g: summarize(evs, target_wait, targets) for g, evs in sorted(parts.items())}


def gate_waits(events: list[dict]) -> dict[str, list[float]]:
    """Minutes each pending rule held one change, from the first event that reported it pending to the first
    later event that did not. A rule still pending at the last event is not counted: its wait is not over."""
    waits: dict[str, list[float]] = defaultdict(list)
    open_since: dict[str, dt.datetime | None] = {}
    for e in sorted(events, key=_when):
        t = parse_time(e.get("ts"))
        pending = set(e.get("pending_rules", []))
        for rule in pending:
            open_since.setdefault(rule, t)
        for rule in [r for r in open_since if r not in pending]:
            start = open_since.pop(rule)
            if t and start:
                waits[rule].append((t - start).total_seconds() / 60)
    return dict(waits)


# A Merge approval on a major change that came within this many minutes of the gate first asking for it: too fast
# for a real review of a major change, so worth a second look. A signal for a retrospective, never a gate rule.
FAST_MERGE_APPROVAL_MINUTES = 10


def fast_major_merge_approvals(by_change: dict[str, list[dict]], limit: float = FAST_MERGE_APPROVAL_MINUTES) -> dict | None:
    """The rubber-stamp indicator: of the changes whose last event is on route major and whose Merge approval wait
    ended (`gate_waits`), how many ended within `limit` minutes, and which. The wait runs from the first event that
    reported merge_approval pending to the first later one that did not, so it measures the gate's view of the
    review, not the time a person spent reading. None when no such change is in the events."""
    measured, fast = 0, []
    for change, evs in by_change.items():
        if evs[-1].get("route") != "major":
            continue
        waits = gate_waits(evs).get("merge_approval")
        if not waits:
            continue
        measured += 1
        if waits[-1] < limit:
            fast.append(change)
    if not measured:
        return None
    return {"within_minutes": limit, "count": len(fast), "of": measured, "changes": sorted(fast)[:20]}


def _hours_until(events: list[dict], reached) -> float | None:
    """Hours from a change's first event to the first one for which `reached(event)` holds."""
    first, hit = parse_time(events[0].get("ts")), next((e for e in events if reached(e)), None)
    t = parse_time(hit.get("ts")) if hit else None
    return (t - first).total_seconds() / 3600 if first and t else None


def _hours_to_pass(events: list[dict]) -> float | None:
    return _hours_until(events, lambda e: e.get("decision") == "pass")


def _reworked_after_g1(events: list[dict]) -> bool:
    """The Spec hash changed after an event in which the Spec approval held: the plan was reworked after Spec approval."""
    approved_hash = next((e.get("spec_hash") for e in events if e.get("spec_hash") and "spec_approval" not in e.get("pending_rules", [])), None)
    if approved_hash is None:
        return False
    after = events[next(i for i, e in enumerate(events) if e.get("spec_hash") == approved_hash) :]
    return any(e.get("spec_hash") and e["spec_hash"] != approved_hash for e in after)


def _first_pass(events: list[dict]) -> bool | None:
    """For a change that passed: did its passing head come from the first head the tests ran on (no fix-up push)?"""
    passed = next((e for e in events if e.get("decision") == "pass"), None)
    if passed is None:
        return None
    tested = next((e for e in events if "tests" not in e.get("pending_rules", [])), None)
    return tested is not None and tested.get("head_sha") == passed.get("head_sha")


def _minutes(start: dt.datetime | None, end: dt.datetime | None) -> float | None:
    return (end - start).total_seconds() / 60 if start and end and end >= start else None


def percentile(values: list[float], q: float) -> float | None:
    """The nearest-rank percentile (q in 0..1): the smallest value with at least q of the values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(math.ceil(q * len(ordered)), 1) - 1]


def spread(values: list[float], digits: int = 1) -> dict | None:
    """The median (p50), the 90th percentile (nearest rank), and how many samples: the typical case and the tail."""
    if not values:
        return None
    p90 = percentile(values, 0.9)
    return {"p50": round(statistics.median(values), digits), "p90": round(p90, digits) if p90 is not None else None, "samples": len(values)}


def first_feedback(events: list[dict]) -> list[float]:
    """Minutes from each head reaching the platform to the first gate decision on it that holds test evidence.

    One sample per head of one change. The start is the event's `head_pushed_at`; for the change's first head without
    one, its `opened_at`. A head with neither, or whose tests never reported, gives no sample: the events cannot say."""
    out: list[float] = []
    opened = next((parse_time(e.get("opened_at")) for e in events if e.get("opened_at")), None)
    heads: dict[str, list[dict]] = {}
    for e in events:
        if e.get("head_sha") and e.get("decision") != "error":
            heads.setdefault(e["head_sha"], []).append(e)
    for i, evs in enumerate(heads.values()):
        pushed = next((parse_time(e.get("head_pushed_at")) for e in evs if e.get("head_pushed_at")), None)
        start = pushed or (opened if i == 0 else None)
        answered = next((e for e in evs if "tests" not in e.get("pending_rules", [])), None)
        m = _minutes(start, parse_time(answered.get("ts"))) if answered else None
        if m is not None:
            out.append(m)
    return out


def flow(events: list[dict]) -> tuple[float, float] | None:
    """(lead, active) minutes for a change that passed, or None.

    Lead time runs from the change's `opened_at` (or, without one, its first gate run) to its first passing decision.
    Waiting is the time a human approval was pending: from each event that reported one pending to the next event.
    Active is lead minus waiting: the time the change moved without waiting on a person (agents, CI, fix-ups)."""
    ordered = [e for e in events if parse_time(e.get("ts"))]
    end_at = next((i for i, e in enumerate(ordered) if e.get("decision") == "pass"), None)
    if end_at is None:
        return None
    opened = next((parse_time(e.get("opened_at")) for e in ordered if e.get("opened_at")), None)
    first = parse_time(ordered[0].get("ts"))
    start = min(t for t in (opened, first) if t is not None)
    lead = _minutes(start, parse_time(ordered[end_at].get("ts")))
    if not lead:
        return None
    waiting = 0.0
    for a, b in zip(ordered[:end_at], ordered[1 : end_at + 1], strict=True):
        if set(a.get("pending_rules", [])) & set(APPROVALS):
            waiting += _minutes(parse_time(a.get("ts")), parse_time(b.get("ts"))) or 0.0
    return lead, max(lead - waiting, 0.0)


def delivery_outcomes(specs_dir: Path) -> dict:
    """DORA's stability measures from Specs' `outcome`: the change failure rate, and the median days to restore.

    A released Spec failed when it was rolled back or failed its observe window. Gate events cannot
    see this, because it happens after the merge; the Spec's outcome records it.
    """
    from . import model

    released = failed = 0
    restore_days: list[float] = []
    for path in sorted(specs_dir.rglob("*.md")):
        try:
            data, _ = model.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        except (model.ModelError, OSError, UnicodeDecodeError):
            continue
        out = data.get("outcome") or {}
        if data.get("kind") != "spec" or not out.get("released_at"):
            continue
        released += 1
        if out.get("rolled_back") or out.get("observe_result") == "fail" or data.get("status") == "rolled_back":
            failed += 1
            if out.get("restored_at"):
                start, end = dt.date.fromisoformat(str(out["released_at"])), dt.date.fromisoformat(str(out["restored_at"]))
                restore_days.append((end - start).days)
    return {
        "released_specs": released,
        "change_failure_rate": round(failed / released, 3) if released else None,
        "median_days_to_restore": statistics.median(restore_days) if restore_days else None,
    }


# DORA's five software delivery metrics (dora.dev/guides/dora-metrics), each as close as aidd's own records allow, with
# what it actually measures said plainly. DORA advises comparing a service with its own past and its own targets, not
# with other teams, so the report takes targets from the config instead of printing another team's thresholds.
DORA = (
    ("deployments_per_week", "Deployment frequency", "changes that passed the gate, per week; a deployment each when every merge deploys", "higher"),
    (
        "lead_time_hours",
        "Change lead time",
        "median hours from a change's first gate run to its first pass; the platform's merge and the deploy come after",
        "lower",
    ),
    ("change_fail_rate", "Change fail rate", "share of released Specs rolled back or failing their observe window (needs --specs)", "lower"),
    ("recovery_days", "Failed deployment recovery time", "median days from release to restore for failed Specs (needs --specs)", "lower"),
    ("rework_rate", "Deployment rework rate", "share of passed changes on the emergency route: unplanned, made because of an incident", "lower"),
)


def dora(events: list[dict], specs_dir: Path | None = None, targets: dict | None = None) -> list[dict]:
    """The five DORA metrics from gate events (and the Specs' outcomes), each against the team's target when one is set."""
    by_change = _by_change(sorted(events, key=_when))
    passed = {k: evs for k, evs in by_change.items() if any(e.get("decision") == "pass" for e in evs)}
    times = [t for e in events if (t := parse_time(e.get("ts")))]
    weeks = weeks_between(times)
    leads = [h for evs in passed.values() if (h := _hours_to_pass(evs)) is not None]
    emergency = sum(1 for evs in passed.values() if any(e.get("route") == "emergency" for e in evs))
    outcomes = delivery_outcomes(specs_dir) if specs_dir else {}
    value = {
        "deployments_per_week": round(len(passed) / weeks, 2) if weeks else None,
        "lead_time_hours": round(statistics.median(leads), 1) if leads else None,
        "change_fail_rate": outcomes.get("change_failure_rate"),
        "recovery_days": outcomes.get("median_days_to_restore"),
        "rework_rate": round(emergency / len(passed), 3) if passed else None,
    }
    return [_judged(key, name, measures, better, value[key], targets) for key, name, measures, better in DORA]


def _judged(key: str, name: str, measures: str, better: str, v, targets: dict | None) -> dict:
    """A metric's row, judged against its `[targets]` key when one is set."""
    target = (targets or {}).get(key)
    met = None if v is None or target is None else (v >= target if better == "higher" else v <= target)
    return {"metric": key, "name": name, "value": v, "target": target, "met": met, "better": better, "measures": measures}


def _met_target(r: dict) -> tuple[str, str]:
    """A judged row's Met and Target cells."""
    met = "" if r["met"] is None else ("yes" if r["met"] else "**no**")
    return met, "" if r["target"] is None else f"{'≥' if r['better'] == 'higher' else '≤'} {r['target']}"


def _na(v: object) -> object:
    return "n/a" if v is None else v


def dora_markdown(rows: list[dict]) -> str:
    lines = ["| DORA metric | Value | Target | Met | What aidd measures |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        met, target = _met_target(r)
        lines.append(f"| {r['name']} | {_na(r['value'])} | {target} | {met} | {r['measures']} |")
    lines += ["", "Set targets in `[targets]` in .aidd/config.toml. Compare a service with its own past, not with other teams (dora.dev)."]
    return "\n".join(lines) + "\n"


# Gradual release: autonomy is earned per agent and per kind of change, from evidence, never granted up front.
AUTONOMY_STAGES = (
    ("review every change", "humans review each change in full; the default for a new agent or a new kind of work"),
    ("review the trade-offs", "a human still approves, but reads the agent's surfaced trade-offs and the tests first"),
    ("candidate standard change", "enough clean history to consider a pre-approved standard change class for this work"),
)


def autonomy(
    events: list[dict], min_changes: int = 10, min_first_pass: float = 0.8, standard_min_changes: int = 25, standard_min_first_pass: float = 0.9
) -> list[dict]:
    """Per agent and change type: how its changes fared, and the stage of autonomy the evidence supports.

    The stage is only a suggestion for a human to act on. One change that failed at its end, or a Spec
    reworked after approval, holds the agent at the first stage for that kind of work.
    """
    by_change = _by_change(events)
    rows: dict[tuple[str, str], dict] = {}
    for evs in by_change.values():
        final = evs[-1]
        for agent in final.get("assisted_by") or []:
            row = rows.setdefault((agent, final.get("type") or "unknown"), {"changes": 0, "passed": 0, "first_pass": 0, "failed": 0, "reworked": 0})
            row["changes"] += 1
            row["passed"] += final.get("decision") == "pass"
            row["first_pass"] += bool(_first_pass(evs))
            row["failed"] += final.get("decision") == "fail"
            row["reworked"] += _reworked_after_g1(evs)
    out = []
    for (agent, ctype), r in sorted(rows.items()):
        share = r["first_pass"] / r["passed"] if r["passed"] else 0.0
        clean = r["failed"] == 0 and r["reworked"] == 0
        stage = 0
        if clean and r["changes"] >= min_changes and share >= min_first_pass:
            stage = 2 if r["changes"] >= standard_min_changes and share >= standard_min_first_pass else 1
        out.append({"agent": agent, "type": ctype, **r, "first_pass_share": round(share, 3), "stage": AUTONOMY_STAGES[stage][0]})
    return out


def autonomy_markdown(rows: list[dict]) -> str:
    head = "| Agent | Type | Changes | First-pass share | Failed | Reworked after Spec approval | Stage the evidence supports |\n| --- | --- | --- | --- | --- | --- | --- |\n"
    body = "\n".join(
        f"| {r['agent']} | {r['type']} | {r['changes']} | {r['first_pass_share']} | {r['failed']} | {r['reworked']} | {r['stage']} |" for r in rows
    )
    legend = "\n\n" + "\n".join(f"- **{name}**: {what}." for name, what in AUTONOMY_STAGES)
    return head + (body or "| _no agent-assisted changes yet_ | | | | | | |") + legend + "\n"


def summarize(events: list[dict], target_wait: float | None = None, targets: dict | None = None) -> dict:
    """The delivery and AI metrics of a set of events; `target_wait` (minutes) names the pending rules whose median wait is
    above it, and `targets` (the config's `[targets]`) judges the loop-speed metrics."""
    by_change = _by_change(events)
    finals = [evs[-1] for evs in by_change.values()]
    waits: dict[str, list[float]] = defaultdict(list)
    for evs in by_change.values():
        for rule, minutes in gate_waits(evs).items():
            waits[rule].extend(minutes)
    to_pass = [h for h in (_hours_to_pass(evs) for evs in by_change.values()) if h is not None]
    to_approval = [h for h in (_hours_until(evs, lambda e: e.get("approvals", 0) > 0) for evs in by_change.values()) if h is not None]
    first_pass = [fp for fp in (_first_pass(evs) for evs in by_change.values()) if fp is not None]
    with_spec = [evs for evs in by_change.values() if any(e.get("spec") for e in evs)]
    reworked = sum(1 for evs in with_spec if _reworked_after_g1(evs))
    approved_specs = [evs for evs in with_spec if any(e.get("spec_hash") and "spec_approval" not in e.get("pending_rules", []) for e in evs)]
    feedback = [m for evs in by_change.values() for m in first_feedback(evs)]
    flows = [f for f in (flow(evs) for evs in by_change.values()) if f is not None]
    lead_total = sum(lead for lead, _ in flows)
    planned = [e for e in finals if e.get("spec")]
    heads: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in events:
        heads[(_key(e), e.get("head_sha", ""))].append(e)
    # Per head: once evidence exists, did its tests pass on the first evaluation that saw them?
    first_green = checked_heads = 0
    for evs in heads.values():
        seen = [e for e in evs if "tests" not in e.get("pending_rules", [])]
        if seen:
            checked_heads += 1
            first_green += "tests" not in seen[0].get("failed_rules", [])
    upgraded = 0
    for evs in by_change.values():
        if any(e.get("required_route") and e.get("route") and e["required_route"] != e["route"] and "route" in e.get("failed_rules", []) for e in evs):
            upgraded += 1
    failed = Counter(r for e in events for r in e.get("failed_rules", []))
    advisory = [e for e in finals if e.get("mode") == "advisory"]
    lines = [e.get("changed_lines", 0) for e in finals]
    # Flow: the human queue (changes whose last decision is pending, by the gate they wait on) and throughput.
    waiting = [e for e in finals if e.get("decision") == "pending"]
    waiting_by_rule = Counter(r for e in waiting for r in e.get("pending_rules", []))
    times = [t for t in (parse_time(e.get("ts")) for e in events) if t]
    weeks = weeks_between(times)
    passes = sum(1 for e in finals if e.get("decision") == "pass")
    medians = {rule: round(statistics.median(m), 1) for rule, m in sorted(waits.items())}
    out = {
        "schema_version": SCHEMA_VERSION,
        "events": len(events),
        "changes": len(by_change),
        "final_decisions": dict(Counter(e.get("decision", "unknown") for e in finals)),
        "routes": dict(Counter(e.get("route") or "unknown" for e in finals)),
        "first_pass_tests_rate": round(first_green / checked_heads, 3) if checked_heads else None,
        "route_corrections": upgraded,
        "top_failed_rules": failed.most_common(8),
        "median_changed_lines": statistics.median(lines) if lines else None,
        "ai_assisted_share": round(sum(1 for e in finals if e.get("assisted_by")) / len(finals), 3) if finals else None,
        "raised_to_major": sum(1 for e in finals if e.get("declared_route")),
        # Where changes wait: the constraint a retrospective should improve first.
        "median_wait_minutes": medians,
        "wait_above_target": {rule: m for rule, m in medians.items() if target_wait is not None and m > target_wait},
        "median_hours_to_pass": round(statistics.median(to_pass), 2) if to_pass else None,
        # Stage speed and plan quality, from the same events.
        "median_hours_to_first_approval": round(statistics.median(to_approval), 2) if to_approval else None,
        "first_pass_share": round(sum(first_pass) / len(first_pass), 3) if first_pass else None,
        "spec_reworked_after_g1": reworked,
        "plan_adherence_share": round(sum(1 for e in planned if not e.get("untouched_tasks")) / len(planned), 3) if planned else None,
        "open_waiting": len(waiting),
        "open_waiting_by_rule": dict(sorted(waiting_by_rule.items())),
        "throughput_per_week": round(passes / weeks, 2) if weeks else None,
        # Observe first: how often the gate would have blocked, while it only reports.
        "advisory_would_block_share": round(sum(1 for e in advisory if e.get("decision") == "fail") / len(advisory), 3) if advisory else None,
        # Loop speed, each paired with a quality measure in `loop_speed`.
        "first_feedback_minutes": spread(feedback),
        "approval_wait_minutes": {rule: {"name": APPROVALS[rule]} | (spread(waits[rule]) or {}) for rule in APPROVALS if rule in waits and waits[rule]},
        "flow_efficiency": round(sum(active for _, active in flows) / lead_total, 3) if lead_total else None,
        "spec_rework_rate": round(reworked / len(approved_specs), 3) if approved_specs else None,
        # A signal for people, never a gate: major changes whose Merge approval came very fast.
        "fast_major_merge_approvals": fast_major_merge_approvals(by_change),
    }
    out["loop_speed"] = loop_speed(out, targets)
    return out


# The loop-speed metrics and the quality metric each is paired with, so the loop cannot get faster by getting worse
# (METHOD §12.1). A target key in `[targets]` judges the speed metric; `aidd metrics` exits 1 when one is missed.
LOOP_SPEED = (
    (
        "first_feedback_minutes",
        "Time to first feedback (p50, minutes)",
        "from a head's push (or the change's opening) to the first gate decision holding its test results",
        "lower",
        ("first_pass_tests_rate", "First-pass test rate"),
    ),
    (
        "approval_wait_p90_minutes",
        "Approval wait (p90 of the slowest approval, minutes)",
        "how long Spec approval, Merge approval, and specialist review were pending, at the 90th percentile",
        "lower",
        ("spec_rework_rate", "Specs reworked after Spec approval (share)"),
    ),
    (
        "flow_efficiency_min",
        "Flow efficiency",
        "share of lead time (opened to first pass) not spent waiting on a human approval",
        "higher",
        ("first_pass_share", "First-pass share (passed on the first tested head)"),
    ),
)


def loop_speed(s: dict, targets: dict | None = None) -> list[dict]:
    """The loop-speed rows of a summary, each against its `[targets]` key and beside its paired quality metric."""
    waits = [w["p90"] for w in s["approval_wait_minutes"].values() if w.get("p90") is not None]
    value = {
        "first_feedback_minutes": (s["first_feedback_minutes"] or {}).get("p50"),
        "approval_wait_p90_minutes": max(waits) if waits else None,
        "flow_efficiency_min": s["flow_efficiency"],
    }
    return [
        _judged(key, name, measures, better, value[key], targets) | {"paired_with": {"metric": quality, "name": quality_name, "value": s[quality]}}
        for key, name, measures, better, (quality, quality_name) in LOOP_SPEED
    ]


def loop_speed_markdown(rows: list[dict]) -> str:
    lines = ["| Loop speed | Value | Target | Met | Paired quality metric | Value |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        met, target = _met_target(r)
        q = r["paired_with"]
        lines.append(f"| {r['name']} | {_na(r['value'])} | {target} | {met} | {q['name']} | {_na(q['value'])} |")
    return "\n".join(lines) + "\n"


def _fast_text(fast: dict | None) -> str | None:
    if not fast:
        return None
    names = f": {', '.join(fast['changes'])}" if fast["count"] else ""
    return f"{fast['count']} of {fast['of']}{names}"


def _approval_name(rule: str) -> str:
    return APPROVALS.get(rule, rule)


def markdown(s: dict) -> str:
    rows = [
        ("Gate events", s["events"]),
        ("Changes", s["changes"]),
        ("Final decisions", ", ".join(f"{k} {v}" for k, v in s["final_decisions"].items()) or "none"),
        ("Routes", ", ".join(f"{k} {v}" for k, v in s["routes"].items()) or "none"),
        ("First-pass test rate", s["first_pass_tests_rate"]),
        ("Changes whose route was corrected", s["route_corrections"]),
        ("Median changed lines", s["median_changed_lines"]),
        ("AI-assisted share", s["ai_assisted_share"]),
        ("Raised to major by the gate", s["raised_to_major"]),
        ("Median hours to pass", s["median_hours_to_pass"]),
        ("Median hours to first approval", s["median_hours_to_first_approval"]),
        ("First-pass share (passed on the first tested head)", s["first_pass_share"]),
        ("Specs reworked after Spec approval", s["spec_reworked_after_g1"]),
        ("Plan adherence (Specs with no idle Task)", s["plan_adherence_share"]),
        ("Median wait per approval (minutes)", ", ".join(f"{_approval_name(r)} {m}" for r, m in s["median_wait_minutes"].items() if r in APPROVALS) or "none"),
        ("Approval wait p50 / p90 (minutes)", ", ".join(f"{w['name']} {w['p50']} / {w['p90']}" for w in s["approval_wait_minutes"].values()) or "none"),
        ("Median wait for evidence and checks (minutes)", ", ".join(f"{r} {m}" for r, m in s["median_wait_minutes"].items() if r not in APPROVALS) or "none"),
        ("Waits above the wait target", ", ".join(f"{_approval_name(r)} {m}" for r, m in s["wait_above_target"].items()) or "none"),
        (
            "Open changes waiting (per approval or check)",
            f"{s['open_waiting']}"
            + (": " + ", ".join(f"{_approval_name(r)} {n}" for r, n in s["open_waiting_by_rule"].items()) if s["open_waiting_by_rule"] else ""),
        ),
        ("Time to first feedback p50 / p90 (minutes)", _p50_p90(s["first_feedback_minutes"])),
        ("Flow efficiency (active share of lead time)", s["flow_efficiency"]),
        ("Spec rework rate after Spec approval", s["spec_rework_rate"]),
        (f"Major changes merge-approved within {FAST_MERGE_APPROVAL_MINUTES} minutes (look again)", _fast_text(s.get("fast_major_merge_approvals"))),
        ("Throughput (passing changes per week)", s["throughput_per_week"]),
        ("Advisory: share that would have been blocked", s["advisory_would_block_share"]),
        ("Top failed rules", ", ".join(f"{r} {n}" for r, n in s["top_failed_rules"]) or "none"),
    ]
    if "change_failure_rate" in s:
        rows += [
            ("Released Specs", s["released_specs"]),
            ("Change failure rate (rolled back or failed observe)", s["change_failure_rate"]),
            ("Median days to restore", s["median_days_to_restore"]),
        ]
    table = "| Metric | Value |\n| --- | --- |\n" + "\n".join(f"| {k} | {_na(v)} |" for k, v in rows) + "\n"
    out = table + "\n" + loop_speed_markdown(s["loop_speed"])
    if s.get("cost"):
        out += "\n" + cost_markdown(s["cost"])
    return out


def _p50_p90(x: dict | None) -> str | None:
    return f"{x['p50']} / {x['p90']} ({x['samples']} heads)" if x else None


def markdown_grouped(groups: dict[str, dict], by: str) -> str:
    return "\n".join(f"## {by}: {g}\n\n{markdown(s)}" for g, s in groups.items())


def _ranked(counter: Counter) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def guard_denials(entries: list[dict]) -> dict:
    """Counts of the edit-time guard's denials (the lines of .aidd/work/guard.jsonl) by reason code, role, and tool.

    A denial of the session itself, with no aidd-team role, counts under the role "session"."""
    denials = [e for e in entries if e.get("decision", "deny") == "deny"]
    return {
        "schema_version": SCHEMA_VERSION,
        "denials": len(denials),
        "by_reason": _ranked(Counter(str(e.get("reason") or "other") for e in denials)),
        "by_role": _ranked(Counter(str(e.get("role") or "session") for e in denials)),
        "by_tool": _ranked(Counter(str(e.get("tool") or "unknown") for e in denials)),
    }


def guard_markdown(counts: dict, source: str) -> str:
    if not counts["denials"]:
        return f"No guard denials in {source}.\n"
    lines = [f"Guard denials in {source}: {counts['denials']}", ""]
    for title, key in (("Reason", "by_reason"), ("Role", "by_role"), ("Tool", "by_tool")):
        lines += [f"| {title} | Denials |", "| --- | ---: |"]
        lines += [f"| {name} | {n} |" for name, n in counts[key].items()]
        lines.append("")
    return "\n".join(lines)


# Cost visibility: a ledger the host exports (a harness's usage export, an orchestrator's cost API), joined to changes.
# Display only: cost never affects aidd/gate, never pauses work, and a missed `cost_per_change` target never sets the exit code.
LEDGER_FIELDS = ("ts", "amount", "currency", "agent", "spec", "branch", "sha")


def load_ledger(path: str, since: str | None = None) -> list[dict]:
    """Ledger entries, one JSON object per line: {ts, amount, currency, agent?, spec?, branch?, sha?}. A malformed line
    is an error naming its line, never a silent skip: a cost report that drops entries understates the cost."""
    since_t = _since(since) if since else None
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{n}: not JSON: {exc.msg}") from None
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{n}: a ledger line is a JSON object")
        amount = item.get("amount")
        if (
            parse_time(item.get("ts")) is None
            or isinstance(amount, bool)
            or not isinstance(amount, int | float)
            or not math.isfinite(amount)
            or not isinstance(item.get("currency"), str)
            or not item["currency"]
        ):
            raise ValueError(f"{path}:{n}: a ledger line needs ts (an ISO time), amount (a number), and currency (such as USD)")
        for key in ("agent", "spec", "branch", "sha"):
            if item.get(key) is not None and not isinstance(item[key], str):
                raise ValueError(f"{path}:{n}: {key} must be a string")
        if since_t is None or (parse_time(item["ts"]) or EPOCH) >= since_t:
            out.append({k: item.get(k) for k in LEDGER_FIELDS})
    return out


def _keys(evs: list[dict]) -> dict[str, set[str]]:
    specs = {str(e["spec_id"]) for e in evs if e.get("spec_id")} | {Path(str(e["spec"])).stem for e in evs if e.get("spec")}
    return {"spec": specs, "branch": {str(e.get("change")) for e in evs if e.get("change")}, "sha": {e["head_sha"] for e in evs if e.get("head_sha")}}


def _joins(entry: dict, keys: dict[str, set[str]], how: str) -> bool:
    if how == "spec":
        return bool(entry.get("spec")) and entry["spec"] in keys["spec"]
    if how == "sha":
        sha = (entry.get("sha") or "").lower()
        return len(sha) >= 7 and any(h.startswith(sha) or sha.startswith(h) for h in keys["sha"])
    return bool(entry.get("branch")) and entry["branch"] in keys["branch"]


def cost(events: list[dict], ledger: list[dict], targets: dict | None = None, quality: float | None = None) -> dict:
    """Cost per change, per currency, from a ledger joined to the changes in `events`.

    An entry joins by its Spec id, else by a commit sha (7 or more hex digits, matching any head the gate judged), else by
    its branch (the change id, which is the branch for local and `--context` runs). An entry that matches several changes
    (one Spec with several PRs) is split evenly among them; one that matches none is reported as not joined."""
    by_change = _by_change(events)
    keys = {k: _keys(evs) for k, evs in by_change.items()}
    per_change: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    unattributed: dict[str, float] = defaultdict(float)
    joined_by: Counter = Counter()
    for entry in ledger:
        cur, amount = entry["currency"], float(entry["amount"])
        by_agent[entry.get("agent") or "unknown"][cur] += amount
        how, matches = "none", []
        for how in ("spec", "sha", "branch"):
            matches = [k for k, ks in keys.items() if _joins(entry, ks, how)]
            if matches:
                break
        if not matches:
            unattributed[cur] += amount
            joined_by["none"] += 1
            continue
        joined_by[how] += 1
        for k in matches:
            per_change[k][cur] += amount / len(matches)
    currencies: dict[str, dict] = {}
    for cur in sorted({c for costs in per_change.values() for c in costs}):
        amounts = [costs[cur] for costs in per_change.values() if cur in costs]
        currencies[cur] = {
            "total": round(sum(amounts), 4),
            "changes": len(amounts),
            "per_change": round(sum(amounts) / len(amounts), 4),
            "median_per_change": round(statistics.median(amounts), 4),
        }
    target = (targets or {}).get("cost_per_change")
    only = next(iter(currencies.values())) if len(currencies) == 1 else None
    return {
        "entries": len(ledger),
        "joined_by": dict(sorted(joined_by.items())),
        "currencies": currencies,
        "unattributed": {c: round(v, 4) for c, v in sorted(unattributed.items())},
        "by_agent": {a: {c: round(v, 4) for c, v in sorted(cs.items())} for a, cs in sorted(by_agent.items())},
        "target": target,
        # Judged only with one currency: aidd converts nothing.
        "met": None if target is None or only is None else only["per_change"] <= target,
        "paired_with": {"metric": "first_pass_share", "name": "First-pass share (passed on the first tested head)", "value": quality},
        "display_only": True,
    }


def cost_markdown(c: dict) -> str:
    lines = ["| Cost (display only) | Value |", "| --- | --- |"]
    joined = ", ".join(f"{how} {n}" for how, n in c["joined_by"].items())
    lines.append(f"| Ledger entries | {c['entries']}" + (f" (joined by {joined})" if joined else "") + " |")
    for cur, x in c["currencies"].items():
        lines.append(f"| Cost per change ({cur}) | {x['per_change']} over {x['changes']} changes (median {x['median_per_change']}, total {x['total']}) |")
    if c["target"] is not None:
        met = "n/a: several currencies" if c["met"] is None else ("yes" if c["met"] else "**no**")
        lines.append(f"| Target cost per change | ≤ {c['target']}: {met} |")
    if c["unattributed"]:
        lines.append("| Not joined to a change | " + ", ".join(f"{v} {cur}" for cur, v in c["unattributed"].items()) + " |")
    for agent, cs in c["by_agent"].items():
        lines.append(f"| By agent: {agent} | " + ", ".join(f"{v} {cur}" for cur, v in cs.items()) + " |")
    lines.append(f"| Paired quality: {c['paired_with']['name']} | {_na(c['paired_with']['value'])} |")
    lines += ["", "Cost is shown, never enforced: it decides no gate, pauses no agent, and a missed target does not change the exit code."]
    return "\n".join(lines) + "\n"


def _slug(text: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def propose_standard_changes(events: list[dict], rows: list[dict], types: list[str] | None = None) -> list[dict]:
    """For each agent and change type the evidence puts at the candidate-standard-change stage, a `[[standard_changes]]`
    entry to start from, with the metrics that justify it.

    A proposal only: .aidd/** is protected, so a person merges it as a major change. `paths` stays empty, because gate
    events do not record paths, so the entry fails `aidd validate` until a person fills it."""
    by_change = _by_change(events)
    out = []
    for r in rows:
        if r["stage"] != AUTONOMY_STAGES[2][0]:
            continue
        finals = [evs[-1] for evs in by_change.values() if r["agent"] in (evs[-1].get("assisted_by") or []) and (evs[-1].get("type") or "unknown") == r["type"]]
        authors = sorted({str(e["author"]) for e in finals if e.get("author") and not any(c.isspace() for c in str(e["author"]))})
        max_lines = max((int(e.get("changed_lines") or 0) for e in finals), default=0)
        evidence = {k: r[k] for k in ("changes", "passed", "first_pass_share", "failed", "reworked")}
        lines = [
            f"# Proposed by `aidd metrics --autonomy --propose` for {r['agent']} on {r['type']} changes.",
            f"# Evidence: {r['changes']} changes, {r['passed']} passed, first-pass share {r['first_pass_share']}, "
            f"{r['failed']} failed, {r['reworked']} Specs reworked after Spec approval.",
            "# A person merges this, never an agent: .aidd/** is a protected path, so it is a major change with its approvals.",
            "# Fill `paths` with the globs this class may touch: gate events do not record paths, and an empty list fails `aidd validate`.",
            "[[standard_changes]]",
            f"name = {json.dumps(_slug(r['type'] + ' ' + r['agent']))}",
            "paths = []",
            "authors = [" + ", ".join(json.dumps(a) for a in authors) + "]" + ("" if authors else "  # the accounts that open these changes"),
        ]
        if max_lines:
            lines.append(f"max_changed_lines = {max_lines}")
        if types is None or r["type"] in types:
            lines.append(f"type = {json.dumps(r['type'])}")
        out.append({"agent": r["agent"], "type": r["type"], "evidence": evidence, "toml": "\n".join(lines) + "\n"})
    return out


def proposals_text(proposals: list[dict]) -> str:
    if not proposals:
        return "No agent and change type meets the candidate-standard-change thresholds ([agents.autonomy]); nothing to propose.\n"
    return "\n".join(p["toml"] for p in proposals)
