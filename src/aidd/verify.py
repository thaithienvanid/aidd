"""The gate: a pure function from a context (see context.schema.json) to a decision.

The agent proposes; the gate decides. Nothing in the Change Request block
counts as evidence: diff paths, test results, approvals, identities, and the
Policy answer all come from the platform through the context. The rules live
in gates.py, one function each.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import __version__, gates, schema
from . import config as cfgmod


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


def verify(ctx: dict) -> Decision:
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

    errors = schema.validate(ctx, "context.schema.json")
    if errors:
        for e in errors[:10]:
            add("context", "fail", f"context: {e}", "fix the platform adapter that built this context", code="context.invalid")
        return finish()
    run = gates.Run(ctx=ctx, record=record, add=add)
    try:
        for gate in gates.GATES:
            gate(run)
    except gates.Stop:
        pass
    except Exception as exc:  # fail closed: a crash must never leave an older status standing
        add("internal", "fail", f"gate error: {type(exc).__name__}: {exc}", "report this with the context JSON", code="internal.crash")
        return finish()
    return finish(run.config)


def _timing(ctx) -> dict[str, str]:
    """`opened_at` and `head_pushed_at` from the context, when present as strings: facts for metrics, never for a rule."""
    if not isinstance(ctx, dict):
        return {}
    change = ctx.get("change")
    found = {"opened_at": change.get("created_at") if isinstance(change, dict) else None, "head_pushed_at": ctx.get("head_pushed_at")}
    return {k: v for k, v in found.items() if isinstance(v, str) and v}
