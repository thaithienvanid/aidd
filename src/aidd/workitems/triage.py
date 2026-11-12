"""Triage: who runs this command, the person who must triage a Spec an agent suggested before it leaves draft, and the owners, who are people, never agents."""

from __future__ import annotations

from aidd import config
from aidd.workitems import status as status_of


def triage_errors(data: dict, proactive: list[str] | None = None) -> list[str]:
    """What `aidd validate` refuses: work an agent suggested moving past draft without a person's triage, a triage an
    agent recorded, a stored status a declined triage contradicts, and a proposal from an agent role outside
    `agents.proactive_roles` (`proactive`; None skips that check)."""
    if data.get("type") != "spec":
        return []
    t = data.get("triage") or {}
    errs = []
    if t.get("by") and config.is_agent(t["by"]):
        errs.append(f"triage.by {t['by']} is an agent account; a person triages suggested work")
    suggester = str(data.get("suggested_by") or "")
    kind, _ = config.typed_identity(suggester)
    # A role suggests as `role:<role>` written exactly. Any other spelling of an
    # agent's type (a case, a tenant, a lookalike) is refused, so it never stands for a role the list allows.
    named = {f"role:{role}" for role in proactive or []}
    if proactive is not None and config.identity_types().get(str(kind)) == "agent" and suggester not in named:
        allowed = ", ".join(proactive) or "none"
        errs.append(f"{suggester} may not suggest work: `agents.proactive_roles` names {allowed}; only those roles suggest work nobody asked for")
    raw = data.get("status")
    status = str(raw or "draft")
    if t.get("decision") == "declined" and raw is not None and raw not in status_of.WITHOUT_TRIAGE:
        errs.append(f'status {status} needs triage.decision: "accepted"; the recorded decision is declined, which cancels the work')
    elif t.get("decision") == "declined" and raw == "draft":
        errs.append('status draft contradicts triage.decision: "declined", which cancels the work: write status: "cancelled", or remove status')
    if not suggester or not config.is_agent(suggester) or status in status_of.WITHOUT_TRIAGE or t.get("decision") == "declined":
        return errs
    if not t:
        errs.append(
            f"status {status} needs triage: {suggester} suggested this work, and a person decides whether it goes ahead "
            '(triage: {decision: "accepted", by: "@you", decided_on: "YYYY-MM-DD"})'
        )
    elif t.get("decision") != "accepted":
        errs.append(f'status {status} needs triage.decision: "accepted"; the recorded decision is {t.get("decision")}')
    return errs


def owner_errors(data: dict) -> list[str]:
    """An owner, and a feature flag's owner, is a person: never an agent or an agent account."""
    owner = data.get("owner")
    errs = [f"owner {owner} is an agent account; the owner is the person driving the work"] if owner and config.is_agent(owner) else []
    for flag in (data.get("flags") or []) if data.get("type") == "spec" else []:
        if isinstance(flag, dict) and flag.get("owner") and config.is_agent(flag["owner"]):
            errs.append(f"flag {flag.get('name')}: owner {flag['owner']} is an agent account; a person decides when a flag flips and sees it removed")
    return errs
