"""Triage: who runs this command, the person who must triage a Spec an agent suggested before it leaves draft, and the owners, who are people, never agents."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config
from aidd.kernel import git


def bots_of(cfg: config.Config | None) -> set[str]:
    return {str(b).lower().lstrip("@") for b in (cfg.get("identities", "bots", default=[]) if cfg else [])}


def my_identities(root: Path) -> set[str]:
    """Who runs this command, in every form a Spec may name them: git's user.email and user.name, and the GitHub login
    from `git config github.user` or gh's stored user. Local configuration only; a team (`@org/team`) is not resolved."""

    email = git.config_value("user.email", str(root)).lower()
    name = git.config_value("user.name", str(root)).lower()
    login = (config.operator_login(root) or "").lower()
    return {x for x in (email, email and f"email:{email}", name, login, login and f"@{login}") if x}


def is_me(identity: object, mine: set[str]) -> bool:
    s = str(identity or "").strip().lower()
    return bool(s) and (s in mine or s.lstrip("@") in mine)


def triage_errors(data: dict, bots: set[str] | frozenset[str] = frozenset(), proactive: list[str] | None = None) -> list[str]:
    """What `aidd validate` refuses: work an agent suggested moving past draft without a person's triage, a triage an
    agent recorded, a stored status a declined triage contradicts, and a proposal from an agent role outside
    `agents.proactive_roles` (`proactive`; None skips that check)."""
    if data.get("kind") != "spec":
        return []
    t = data.get("triage") or {}
    errs = []
    if t.get("by") and config.is_agent(t["by"], bots):
        errs.append(f"triage.by {t['by']} is an agent account; a person triages suggested work")
    suggester = str(data.get("suggested_by") or "")
    if proactive is not None and suggester.startswith("agent:") and suggester.split(":", 1)[1] not in proactive:
        allowed = ", ".join(proactive) or "none"
        errs.append(f"{suggester} may not suggest work: `agents.proactive_roles` names {allowed}; only those roles suggest work nobody asked for")
    raw = data.get("status")
    status = str(raw or "draft")
    if t.get("decision") == "declined" and raw is not None and raw not in ("cancelled", "draft"):
        errs.append(f'status {status} needs triage.decision: "accepted"; the recorded decision is declined, which cancels the work')
    elif t.get("decision") == "declined" and raw == "draft":
        errs.append('status draft contradicts triage.decision: "declined", which cancels the work: write status: "cancelled", or remove status')
    if not suggester or not config.is_agent(suggester, bots) or status in ("draft", "cancelled") or t.get("decision") == "declined":
        return errs
    if not t:
        errs.append(
            f"status {status} needs triage: {suggester} suggested this work, and a person decides whether it goes ahead "
            '(triage: {decision: "accepted", by: "@you", triaged_on: "YYYY-MM-DD"})'
        )
    elif t.get("decision") != "accepted":
        errs.append(f'status {status} needs triage.decision: "accepted"; the recorded decision is {t.get("decision")}')
    return errs


def owner_errors(data: dict, bots: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """An owner, and a feature flag's owner, is a person: never an agent or an agent account."""
    owner = data.get("owner")
    errs = [f"owner {owner} is an agent account; the owner is the person driving the work"] if owner and config.is_agent(owner, bots) else []
    for flag in (data.get("flags") or []) if data.get("kind") == "spec" else []:
        if isinstance(flag, dict) and flag.get("owner") and config.is_agent(flag["owner"], bots):
            errs.append(f"flag {flag.get('name')}: owner {flag['owner']} is an agent account; a person decides when a flag flips and sees it removed")
    return errs


def triage_state(data: dict, bots: set[str] | frozenset[str], today: dt.date) -> str | None:
    """`needed` when a person must triage the Spec now, `hidden` when it is out of `aidd list` (declined, or snoozed
    until a later date), and None otherwise."""
    t = data.get("triage") or {}
    decision = t.get("decision")
    if decision == "declined":
        return "hidden"
    if decision == "snoozed":
        return "hidden" if str(t.get("until") or "") > today.isoformat() else "needed"
    suggester = data.get("suggested_by")
    if not suggester or not config.is_agent(suggester, bots) or (decision == "accepted" and not config.is_agent(t.get("by"), bots)):
        return None
    return "needed"
