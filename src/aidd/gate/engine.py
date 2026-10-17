"""The gate's decision: run every rule over a context (see context.schema.json) and fold the findings into pass, fail, or pending."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from aidd import __version__, workitems
from aidd import config as cfgmod
from aidd.gate import routing, rules
from aidd.gate.rules import gate_run
from aidd.kernel import json_schema


@dataclass
class Finding:
    rule: str
    level: str  # fail | pending | warn
    message: str
    fix: str = ""
    # Stable across rewording: which check fired and why (`tests.none`, `spec.not_at_head`).
    # The conformance suite asserts codes, so a rule firing for the wrong reason is caught.
    code: str = ""


@dataclass
class Decision:
    decision: str
    findings: list[Finding]
    record: dict
    trusted: bool = False
    config: cfgmod.Config | None = field(default=None, repr=False)
    # What the adapter that built the context wants a person to know (the context's `notes`), such as local approvals
    # that did not count. Shown in the report; never part of the decision.
    notes: list[str] = field(default_factory=list)
    # When the change was opened and when its head reached the platform, from the context, for the gate event's
    # loop-speed metrics (time to first feedback). Never part of the decision or the record.
    timing: dict[str, str] = field(default_factory=dict)

    def rules_at(self, level: str) -> list[str]:
        return sorted({f.rule for f in self.findings if f.level == level})

    def codes(self) -> list[str]:
        """Each finding as `level code`, sorted and unique: what the conformance suite pins."""
        return sorted({f"{f.level} {f.code}" for f in self.findings})


# The fix for a crash of the gate itself: a bug in aidd, which its maintainers fix.
REPORT_A_CRASH = "open a bug report for aidd's maintainers on aidd's repository with this context JSON attached, secrets removed"


def decide(ctx: dict) -> Decision:
    findings: list[Finding] = []
    record: dict = {"aidd_version": __version__}
    trusted = bool(ctx.get("trusted", False)) if isinstance(ctx, dict) else False
    raw_notes = ctx.get("notes") if isinstance(ctx, dict) else None
    notes = [n for n in raw_notes if isinstance(n, str)] if isinstance(raw_notes, list) else []
    timing = _timing(ctx)
    if isinstance(ctx, dict):
        # Known before validation, so even a malformed context yields a record a status can be posted for.
        # Only values of the right type: the record must stay valid even when the context is not.
        head, change = ctx.get("head_sha"), ctx.get("change")
        change_id = change.get("id") if isinstance(change, dict) else None
        record.update(head_sha=head if isinstance(head, str) else None, change=change_id if isinstance(change_id, str) else None)

    def add(rule: str, level: str, message: str, fix: str = "", code: str = "") -> None:
        findings.append(Finding(rule, level, message, fix, code or rule))

    def finish(cfg: cfgmod.Config | None = None) -> Decision:
        levels = {f.level for f in findings}
        decision = "fail" if "fail" in levels else "pending" if "pending" in levels else "pass"
        record["decision"] = decision
        record["failed_rules"] = sorted({f.rule for f in findings if f.level == "fail"})
        record["pending_rules"] = sorted({f.rule for f in findings if f.level == "pending"})
        record["findings"] = [{"rule": f.rule, "level": f.level, "code": f.code} for f in findings]
        return Decision(decision, findings, record, trusted, cfg, notes, timing)

    errors = json_schema.validate(ctx, "context.schema.json")
    if errors:
        for e in errors[:10]:
            add("context", "fail", f"context: {e}", "fix the platform adapter that built this context", code="context.invalid")
        return finish()
    members = _goal_specs(ctx)
    if members:
        cfg = _decide_goal(ctx, members, record, findings)
        return finish(cfg)
    return finish(_run_rules(gate_run.GateRun(ctx=ctx, record=record, add=add)))


def _run_rules(run: gate_run.GateRun) -> cfgmod.Config | None:
    """Every rule over one run, in order; the config in force, or None when the gate crashed (an internal.crash finding)."""
    try:
        for gate in rules.GATES:
            gate(run)
    except gate_run.Stop:
        pass
    except Exception as exc:  # fail closed: a crash must never leave an older status standing
        run.add("internal", "fail", f"gate error: {type(exc).__name__}: {exc}", REPORT_A_CRASH, code="internal.crash")
        return None
    return run.config


def _goal_specs(ctx: dict) -> list[str]:
    """A goal's Spec paths, when the change's one Change Request block names `specs` and holds no error; else none."""
    cr, errs = workitems.parse_change_block(str((ctx.get("change") or {}).get("body") or ""))
    return list(cr["specs"]) if cr and not errs and isinstance(cr.get("specs"), list) else []


def _decide_goal(ctx: dict, members: list[str], record: dict, findings: list[Finding]) -> cfgmod.Config | None:
    """A goal's change (`specs`): every rule runs once per Spec, as for a change of that one Spec, against the whole
    diff, where the other Specs' work and the goal's plan are in scope. A finding every run gives is reported once; one
    that only some runs give names their Specs. The record lists each Spec with its approval."""
    runs: list[tuple[str, list[Finding], dict]] = []
    cfg: cfgmod.Config | None = None
    for member in members:
        found: list[Finding] = []
        sub = dict(record, spec=member)
        ran = _run_rules(gate_run.GateRun(ctx=ctx, record=sub, add=_adder(found), member=member, members=list(members)))
        cfg = cfg or ran
        runs.append((str(sub.get("spec_id") or member), found, sub))
    seen: dict[tuple, list[str]] = {}
    for name, found, _ in runs:
        for f in found:
            seen.setdefault((f.rule, f.level, f.message, f.fix, f.code), []).append(name)
    for (rule, level, message, fix, code), names in seen.items():
        shown = message if len(set(names)) == len(runs) else f"{', '.join(dict.fromkeys(names))}: {message}"
        findings.append(Finding(rule, level, shown, fix, code))
    first = runs[0][2]
    keep = {k: v for k, v in first.items() if k not in _PER_SPEC}
    record.update(keep, spec=None, spec_id=None, trace_id=None)
    record["route"] = max((r.get("route") for _, _, r in runs if r.get("route")), key=_route_rank, default=first.get("route"))
    record["specs"] = [{k: r[k] for k in ("spec", "spec_id", *_PER_SPEC_SHOWN) if k in r} for _, _, r in runs]
    return cfg


def _adder(found: list[Finding]) -> Callable[..., None]:
    """The `add` of one Spec's run: its findings, kept apart until the goal's are merged."""

    def add(rule: str, level: str, message: str, fix: str = "", code: str = "") -> None:
        found.append(Finding(rule, level, message, fix, code or rule))

    return add


# What each Spec of a goal records on its own: in the goal's record, under `specs`.
_PER_SPEC = ("spec", "spec_id", "spec_hash", "spec_approved_by", "spec_approvals", "spec_approval_before_implementation", "trace_id", "owner_team", "plan")
_PER_SPEC_SHOWN = ("spec_hash", "spec_approved_by", "spec_approval_before_implementation")


def _route_rank(route: object) -> int:
    return routing.ROUTE_RANK.get(route, -1) if isinstance(route, str) else -1


def _timing(ctx) -> dict[str, str]:
    """`opened_at` and `head_pushed_at` from the context, when present as strings: facts for metrics, never for a rule."""
    if not isinstance(ctx, dict):
        return {}
    change = ctx.get("change")
    found = {"opened_at": change.get("created_at") if isinstance(change, dict) else None, "head_pushed_at": ctx.get("head_pushed_at")}
    return {k: v for k, v in found.items() if isinstance(v, str) and v}
