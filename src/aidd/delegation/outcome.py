"""The check's run and its output: the checks in order, then what an accept would cover (schemas/delegate-check.schema.json)."""

from __future__ import annotations

from aidd import config, records
from aidd.delegation import action_checks, commands, independence, policy, text_checks
from aidd.delegation.check import Check, Request, message_for
from aidd.kernel import git_reads

# The fields of a record's `covers` (schemas/records.json), in its order.
COVERS = ("command", "head", "tree", "base", "branch", "spec")


def evaluate(request: Request) -> Check:
    """One run of every check, in order, recomputed from nothing the asker wrote."""
    check = Check(request)
    check.open_repository()
    if check.passes_common():
        action_checks.CHECKS[request.action](check)
        text_checks.guard(check)
        if note := independence.same_model_warning(check):
            check.warnings.append(note)
    return check


@git_reads.shared_reads()
def run_check(request: Request) -> dict:
    """The check's answer (schemas/delegate-check.schema.json), with the `delegate_check` record it wrote as history."""
    check = evaluate(request)
    result = outcome(check)
    record_check(check, result)
    return result


def record_check(check: Check, result: dict) -> None:
    """Write the run as a `delegate_check` record, for history only; a clone whose git folder is read-only says so."""
    data = {
        "action": result["action"],
        "covers": {k: result["covers"][k] for k in COVERS if result["covers"].get(k)},
        "outcome": result["outcome"],
        "reasons": result["reasons"],
        "inputs": result["inputs"],
    }
    try:
        with records.written_by_delegation():
            record, _ = records.add_record("delegate_check", data, by=config.DECIDED_BY, subject=result["covers"].get("spec"), cwd=check.top)
        result["record"] = record["id"]
    except records.RecordError as exc:
        result["warnings"].append(f"the check's record was not written: {exc}")


def outcome(check: Check) -> dict:
    """The check's output, with the exact command an accept covers and the trailers when it is eligible."""
    eligible = not check.reasons
    covers = dict(check.covers)
    shape = policy.template(check.req.action)
    trailers = check.trailers() if eligible else []
    if eligible and shape is not None:
        covers["command"] = commands.canonical(shape, {**check.values, "message": message_for(check, trailers)})
    elif check.req.command:
        covers["command"] = check.req.command
    if check.req.spec:
        covers.setdefault("spec", check.req.spec)
    first = check.reasons[0] if check.reasons else None
    step = "Start aidd-team:delegate with this action, the command in covers, and the head." if eligible else policy.reasons()[first["code"]]["next"]["what"]  # type: ignore[index]
    return {
        "schema_version": "1",
        "outcome": "eligible" if eligible else "defer",
        "reserved": any(r["reserved"] for r in check.reasons),
        "action": check.req.action,
        "covers": covers,
        "reasons": check.reasons,
        "warnings": check.warnings,
        "inputs": check.inputs,
        "trailers": trailers,
        "next": {"what": step},
    }
