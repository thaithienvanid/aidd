"""The safety rules: secrets on added lines, the Policy and freeze, an emergency's block, the observe window, and the
provenance of agent commits.
"""

from __future__ import annotations

import datetime as dt
import re

from aidd import config
from aidd.gate.rules import gate_run
from aidd.kernel.timestamps import parse_time

# The next step for a Policy finding that brings none of its own.
POLICY_FINDING_FIX = "change the PR/MR to meet this Policy rule, or ask the Policy's owner"


def gate_secrets(run: gate_run.GateRun) -> None:
    """An added line shaped like a secret warns, naming the file and the kind, never the value. The adapter passes the added
    lines (`files[].added_lines`): the local one does; a platform's secret scanning is the control where it does not."""
    hits = []
    for f in run.ctx["files"]:
        kinds: list[str] = []
        for line in f.get("added_lines") or []:
            kinds += [k for k in secret_kinds(line) if k not in kinds]
        if kinds:
            hits.append((f["path"], kinds))
    for path, kinds in hits[:MAX_SECRET_FINDINGS]:
        run.add(
            "secrets",
            "warn",
            f"{path} adds a line shaped like {', '.join(kinds)}",
            "if real, remove it from the change and its history, rotate it, and load it from the environment or a secret store. "
            "A placeholder or a documented example can stay",
            code="secrets.added",
        )


def gate_policy(run: gate_run.GateRun) -> None:
    """Policy and freeze. Unreachable is deny; org findings join as policy:<rule>."""
    ctx, cfg, add = run.ctx, run.cfg, run.add
    policy = (ctx.get("policy") or {}).get("result", "unbound")
    run.record["policy"] = policy
    if policy == "unbound":
        if run.route in run.g["policy_required_routes"]:
            add("policy", "fail", f"profile {cfg.profile} requires a bound Policy for {run.route}", "set policy.command in the config", code="policy.required")
    elif policy == "freeze":
        if run.route == "emergency":
            add("policy", "warn", "shipping under freeze through the emergency break-glass; the post-incident review must cover it", code="policy.break_glass")
        else:
            add(
                "policy",
                "fail",
                "a freeze is on; only the emergency route may ship",
                "wait for the freeze to end; if production is broken and this is the repair, use route emergency",
                code="policy.freeze",
            )
    elif policy == "deny":
        add(
            "policy",
            "fail",
            "Policy returned deny" + (f": {ctx['policy'].get('detail')}" if ctx["policy"].get("detail") else ""),
            "change the PR/MR so the Policy allows it, or ask the Policy's owner",
            code="policy.deny",
        )
    elif policy == "unreachable":
        add("policy", "fail", "the Policy command did not answer; unreachable is deny", "fix the Policy command or its runner", code="policy.unreachable")
    for f in (ctx.get("policy") or {}).get("findings", []):
        add(f"policy:{f['rule']}", f["level"], f["message"], f.get("fix") or POLICY_FINDING_FIX)


def gate_emergency(run: gate_run.GateRun) -> None:
    """A complete emergency block, a real review date, and a human commander who approved and did not author."""
    if run.route != "emergency":
        return
    add = run.add
    em = run.declared.get("emergency")
    if not em:
        add(
            "emergency",
            "fail",
            "route emergency needs an emergency block: severity, kind, commander, incident, review_due",
            "add an `emergency` block with those five keys to the Change Request block",
            code="emergency.no_block",
        )
        return
    if not str(em.get("incident") or "").strip():
        add(
            "emergency",
            "fail",
            "the emergency block names no incident: a production repair answers a real incident",
            'set incident: "<ticket or page id>" in `emergency`, the one the post-incident review and the backfill Spec will link',
            code="emergency.incident_missing",
        )
    # The window starts when the change opened or its head was last pushed, whichever is later: not at each
    # gate run, so a slow approval cannot expire it, and an old change turned into an emergency needs a fresh push.
    starts = [t for t in (parse_time((run.ctx["change"] or {}).get("created_at")), parse_time(run.ctx.get("head_pushed_at"))) if t]
    opened = max(starts) if starts else (parse_time(run.ctx.get("now")) or dt.datetime.now(dt.UTC))
    sla = run.cfg.get("emergency", "review_sla_days", default=2)
    try:
        due = dt.date.fromisoformat(str(em["review_due"]))
    except ValueError:
        due = None
        add(
            "emergency",
            "fail",
            f"review_due {em['review_due']!r} is not a calendar date",
            "set review_due to a date, such as 2026-10-14",
            code="emergency.review_due_invalid",
        )
    if due is not None and due > opened.date() + dt.timedelta(days=sla):
        add(
            "emergency",
            "fail",
            f"review_due {due} is more than {sla} day(s) after the change opened",
            f"set review_due within {sla} day(s)",
            code="emergency.review_due_late",
        )
    if due is not None and due < opened.date():
        add(
            "emergency",
            "fail",
            f"review_due {due} is before the change opened",
            "set a review date from the day the change opened",
            code="emergency.review_due_early",
        )
    commander = config.normalize_identity(em["commander"])
    if config.is_agent(commander, run.bots):
        add(
            "emergency",
            "fail",
            f"the incident commander {commander} is an agent or bot account",
            "name the human who runs the incident",
            code="emergency.commander_is_agent",
        )
    elif commander in run.authors and not run.solo:
        add(
            "emergency",
            "fail",
            f"the incident commander {commander} is also an author of this change",
            "name a commander who did not write it",
            code="emergency.commander_is_author",
        )
    elif not run.solo and not run.may_approve(commander, run.pool):
        add(
            "emergency",
            "fail",
            f"the incident commander {commander} is not an eligible Approver",
            "name a commander listed in owners.approvers",
            code="emergency.commander_not_approver",
        )
    elif not run.solo and commander not in run.approved_at:
        add(
            "emergency",
            "pending",
            f"the incident commander {commander} has not approved head {run.head[:12]}",
            "the commander approves the change",
            code="emergency.commander_pending",
        )


def gate_observe(run: gate_run.GateRun) -> None:
    observe = run.declared.get("observe")
    if run.route in run.g["observe_required_routes"] and not observe:
        run.add(
            "observe",
            "fail",
            f"route {run.route} under profile {run.cfg.profile} needs an observe block",
            "add window, rollback_trigger, and a command or signals; or, when nothing runs to watch, `not_applicable` with the reason",
            code="observe.missing",
        )
    elif isinstance(observe, dict) and observe.get("not_applicable"):
        # Nothing runs to watch (a library, a CLI, docs): the reason stands where the window would, for the Approver.
        run.add(
            "observe",
            "warn",
            f"observe is not applicable: {observe['not_applicable']}",
            "if something does run after release, replace it with window, rollback_trigger, and a command or signals",
            code="observe.not_applicable",
        )


def gate_provenance(run: gate_run.GateRun) -> None:
    """Every commit an agent wrote is declared: an `Assisted-by:` trailer naming an agent, a `Co-authored-by:` agent,
    or a bot author. `Assisted-by: none` declares a commit no agent wrote."""
    commits, add = run.ctx["commits"], run.add
    assisted = run.declared["assisted_by"]
    trailers = {c["sha"]: [t.strip().lower() for t in config.extract_trailers(c["message"])] for c in commits}
    named: dict[str, list[str]] = {}  # sha -> what names an agent
    for c in commits:
        who = [f"Assisted-by {t}" for t in trailers[c["sha"]] if t != "none"]
        who += [f"Co-authored-by {x}" for x in config.agent_coauthors(c["message"], run.bots)]
        who += [f"author {k}" for k in (c.get("author"), c.get("committer")) if k and config.normalize_identity(k) in run.bots]
        if who:
            named[c["sha"]] = who
    unmarked = [c["sha"] for c in commits if not c.get("merge") and not trailers[c["sha"]]]
    assisted_norm = {config.normalize_identity(a) for a in assisted}
    missing_from_assisted = [(c["sha"], t) for c in commits for t in trailers[c["sha"]] if t != "none" and config.normalize_identity(t) not in assisted_norm]
    if not assisted and named:
        sample = "; ".join(f"{sha[:10]}: {', '.join(w[:2])}" for sha, w in list(named.items())[:3])
        add(
            "provenance",
            "fail",
            f"{len(named)} commit(s) name an agent, but assisted_by is empty ({sample})",
            "list each harness/model in assisted_by",
            code="provenance.undeclared_agent",
        )
    elif missing_from_assisted:
        sample = "; ".join(f"{sha[:10]}: {t}" for sha, t in missing_from_assisted[:3])
        add(
            "provenance",
            "fail",
            f"commit trailer value not declared in assisted_by: {sample}",
            "list each harness/model in assisted_by",
            code="provenance.undeclared_trailer",
        )
    if unmarked and run.g["provenance"] == "every_commit":
        add(
            "provenance",
            "fail",
            f"{len(unmarked)} commit(s) lack an Assisted-by trailer: {', '.join(s[:10] for s in unmarked[:5])}",
            "amend each commit with `Assisted-by: <harness>/<model>`, or `Assisted-by: none` when no agent wrote it",
            code="provenance.missing_trailer",
        )
    if assisted and commits and not named:
        add(
            "provenance",
            "warn",
            "assisted_by is set but no commit names an agent (no Assisted-by trailer, Co-authored-by agent, or bot author)",
            code="provenance.no_agent_commit",
        )


# Secret-shaped strings. Each pattern starts at a fixed prefix and every repeat is bounded, and only the first
# MAX_SECRET_LINE characters of a line are read, so no input makes the scan slow. Shapes, not validity: a match is a warning.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("an AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a Stripe live key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,99}\b")),
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,255})\b")),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z0-9]{1,20} ){0,3}PRIVATE KEY-----")),
    ("a *_SECRET assignment", re.compile(r"\b[A-Za-z][A-Za-z0-9_]{0,60}_SECRET(?:_KEY)?[ \t]{0,4}[=:][ \t]{0,4}[\"']?(?![$<{%])[^\s\"'$]{8,200}")),
)
MAX_SECRET_LINE = 4096
MAX_SECRET_FINDINGS = 10


def secret_kinds(line: str) -> list[str]:
    """The kinds of secret `line` looks like it holds, in pattern order; [] for none."""
    text = line[:MAX_SECRET_LINE]
    return [kind for kind, rx in SECRET_PATTERNS if rx.search(text)]
