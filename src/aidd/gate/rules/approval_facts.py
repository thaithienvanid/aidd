"""The approval facts both approval rules read: which comments and reviews count, from whom, and whether an approval
of an earlier head carries to this one.
"""

from __future__ import annotations

import datetime as dt

from aidd import config
from aidd.gate.rules import gate_run
from aidd.kernel.timestamps import EPOCH, parse_time


def _signed_local_approvals(run: gate_run.GateRun, comments: list[dict], reviews: list[dict]) -> tuple[list[dict], list[dict]]:
    """Under `gates.local_approvals: signed`, a local approval counts only when the adapter verified its git signature
    (`verified: true`); the rest are dropped here, in the gate, so the rule holds for any context, not only aidd's own."""
    kept_c = [c for c in comments if c.get("verified") is True]
    kept_r = [r for r in reviews if r.get("verified") is True]
    dropped_spec = [c for c in comments if c.get("verified") is not True and gate_run.APPROVE_SPEC.search(gate_run.comment_commands(c["body"]))]
    dropped_merge = [r for r in reviews if r.get("verified") is not True and r["state"] == "approved"]
    dropped_merge += [c for c in comments if c.get("verified") is not True and gate_run.APPROVE.search(gate_run.comment_commands(c["body"]))]
    fix = "the approver records it again with git commit signing set up (`aidd approve`), with a key git trusts"
    if dropped_spec:
        who = ", ".join(sorted({config.normalize_identity(c["user"]) for c in dropped_spec}))
        run.add(
            "spec_approval",
            "warn",
            f'gates.local_approvals: "signed": Spec approvals without a verified signature do not count ({who})',
            fix,
            code="spec_approval.unsigned",
        )
    if dropped_merge:
        who = ", ".join(sorted({config.normalize_identity(x["user"]) for x in dropped_merge}))
        run.add(
            "merge_approval",
            "warn",
            f'gates.local_approvals: "signed": approvals without a verified signature do not count ({who})',
            fix,
            code="merge_approval.unsigned",
        )
    return kept_c, kept_r


def _app_posted_approvals(run: gate_run.GateRun, comments: list[dict]) -> list[dict]:
    """An approval line an App posted for a person (`via_app`: GitHub's performed_via_github_app) never counts: whoever
    holds the App's user token, an agent included, can post it in the person's name. The other comments stay."""
    posted = [c for c in comments if c.get("via_app") is True]
    fix = "the approver posts the line themselves, on the platform's web page or with its CLI, never through an App"
    spec_who = sorted({config.normalize_identity(c["user"]) for c in posted if gate_run.APPROVE_SPEC.search(gate_run.comment_commands(c["body"]))})
    merge_who = sorted({config.normalize_identity(c["user"]) for c in posted if gate_run.APPROVE.search(gate_run.comment_commands(c["body"]))})
    if spec_who:
        run.add(
            "spec_approval",
            "warn",
            f"Spec approvals an App posted on someone's behalf do not count ({', '.join(spec_who)})",
            fix,
            code="spec_approval.via_app",
        )
    if merge_who:
        run.add(
            "merge_approval",
            "warn",
            f"approvals an App posted on someone's behalf do not count ({', '.join(merge_who)})",
            fix,
            code="merge_approval.via_app",
        )
    return [c for c in comments if c.get("via_app") is not True]


def _tenant_scoped(run: gate_run.GateRun, comments: list[dict], reviews: list[dict]) -> tuple[list[dict], list[dict]]:
    """With a tenant, every comment and review under its identity as the config names it; one by an identity another
    tenant qualifies is dropped here, so its approval never counts, whatever pool or platform account it resembles."""
    tenant = run.tenant
    if not tenant:
        return comments, reviews
    kept_c: list[dict] = []
    kept_r: list[dict] = []
    foreign_spec: set[str] = set()
    foreign_merge: set[str] = set()
    for c in comments:
        local = config.scoped(c["user"], tenant)
        if local is None:
            body = gate_run.comment_commands(c["body"])
            if gate_run.APPROVE_SPEC.search(body):
                foreign_spec.add(config.normalize_identity(c["user"]))
            if gate_run.APPROVE.search(body):
                foreign_merge.add(config.normalize_identity(c["user"]))
            continue
        kept_c.append({**c, "user": local})
    for r in reviews:
        local = config.scoped(r["user"], tenant)
        if local is None:
            if r["state"] == "approved":
                foreign_merge.add(config.normalize_identity(r["user"]))
            continue
        kept_r.append({**r, "user": local})
    fix = f"an Approver of tenant {tenant!r} approves; an identity qualified with another tenant never approves here"
    if foreign_spec:
        run.add(
            "spec_approval",
            "warn",
            f"Spec approvals by identities of another tenant do not count ({', '.join(sorted(foreign_spec))})",
            fix,
            code="spec_approval.other_tenant",
        )
    if foreign_merge:
        run.add(
            "merge_approval",
            "warn",
            f"approvals by identities of another tenant do not count ({', '.join(sorted(foreign_merge))})",
            fix,
            code="merge_approval.other_tenant",
        )
    return kept_c, kept_r


def _agent_approvals(run: gate_run.GateRun, reviews: list[dict]) -> None:
    """An approval review from an agent, or from a bot no pool names, never counts here; a platform's own review count
    may still take it, so say so."""
    named = run.pool.named
    users = {config.normalize_identity(r["user"]) for r in reviews if r["state"] == "approved"}
    who = {u for u in users if config.agent_account(u, run.bots) or (config.is_bot(u) and u not in named)}
    if who:
        run.add(
            "merge_approval",
            "warn",
            f"an agent or bot approved on the platform ({', '.join(sorted(who))}); it never counts toward Merge approval, and your "
            "branch rules may be counting it",
            "require the aidd/gate status in the branch rules (docs/PLATFORMS.md, GitHub rulesets and aidd), and have a person approve",
            code="merge_approval.agent_approval",
        )


def derive_approvals(run: gate_run.GateRun) -> None:
    """Facts both approval gates read: unedited comments, each reviewer's latest review, and approvals on head."""
    ctx, head = run.ctx, run.head
    run.record["separation_of_duties"] = "waived_solo" if run.solo else "enforced"
    comments, reviews = _tenant_scoped(run, ctx["comments"], ctx["reviews"])
    _agent_approvals(run, reviews)
    comments = _app_posted_approvals(run, comments)
    if ctx.get("platform") in ("local", "preflight") and run.g.get("local_approvals") == "signed":
        comments, reviews = _signed_local_approvals(run, comments, reviews)
    run.comments = [c for c in comments if not c.get("edited")]
    if any(c.get("edited") for c in comments):
        run.add("edited_comments", "warn", "edited comments are ignored; post a new comment to approve", code="edited_comments.ignored")
    for r in sorted(reviews, key=lambda r: parse_time(r.get("submitted_at")) or EPOCH):
        if r["state"] != "commented":  # a comment does not clear an approval or a change request
            run.latest[config.normalize_identity(r["user"])] = r
    # Retargeting the change to another base changes its diff, so an earlier approval approved something else.
    rebased = parse_time(ctx.get("base_changed_at"))
    for u, r in run.latest.items():
        if r["state"] == "approved":
            at = parse_time(r.get("submitted_at"))
            sha = r.get("commit_sha") or ""
            if sha == head and not (rebased and (at is None or at < rebased)):
                run.approved_at[u] = at
            elif _carries(run, u, sha, at, rebased):
                run.approved_at[u] = at
            else:
                run.stale_reviews.append(u)
    if ctx.get("platform") == "local":
        # Locally the cool-off starts at a committer date the committer sets: a person may skip it on record.
        run.cooloff_skipped = {u for u, r in run.latest.items() if r["state"] == "approved" and r.get("cooloff_skipped") is True}
    if run.solo:
        for c in run.comments:
            for m in gate_run.APPROVE.finditer(gate_run.comment_commands(c["body"])):
                at = parse_time(c.get("created_at"))
                user = config.normalize_identity(c["user"])
                if m.group(1) == head and not (rebased and (at is None or at < rebased)):
                    run.approved_at.setdefault(user, at)
                elif user not in run.approved_at and _carries(run, user, m.group(1), at, rebased):
                    run.approved_at[user] = at


def carry_blocker(run: gate_run.GateRun) -> str | None:
    """Why no approval of an earlier head carries to this one on this change, or None when a trivial rebase may carry one."""
    if run.g.get("approval_carry", "none") != "trivial_rebase":
        return "gates.approval_carry is none"
    if run.route == "emergency":
        return "an emergency never carries an approval"
    if run.route not in run.g.get("approval_carry_routes", []):
        return f"route {run.route} does not carry approvals under profile {run.cfg.profile}"
    if run.protected_hit:
        return "the change touches a protected path"
    return None


def _carries(run: gate_run.GateRun, user: str, sha: str, at: dt.datetime | None, rebased: dt.datetime | None) -> bool:
    """Whether `user`'s approval of the earlier head `sha` counts for this head: a trivial rebase (Gerrit's TRIVIAL_REBASE).

    The change's diff is identical onto a base that descends from the approved one on the protected branch, and nobody
    new committed; the evidence re-runs on this head by the usual rules, and separation of duties is checked against this
    head's authors and committers when the approval is counted. Records why it did or did not carry."""
    eq = (run.ctx.get("approval_equivalents") or {}).get(sha)
    if not sha or sha == run.head or eq is None or carry_blocker(run) is not None:
        return False  # the head itself (made stale by a retarget), or an earlier head the adapter did not compare
    why = None
    if eq.get("base_sha") is None:
        why = f"the approved head {sha[:12]} is not available to compare"
    elif rebased and (at is None or at < rebased):
        why = "the change was retargeted to another base branch since"
    elif not eq.get("identical_diff"):
        why = f"the diff on head {run.head[:12]} differs from the approved head {sha[:12]}'s"
    elif not eq.get("base_descends"):
        why = f"the new base does not descend from {eq['base_sha'][:12]}, the approved head's base"
    elif eq.get("new_committers"):
        why = f"{', '.join(eq['new_committers'][:3])} committed since, and did not commit the approved head"
    if why is not None:
        run.not_carried[user] = (sha, why)
        return False
    run.carried[user] = (
        sha,
        f"trivial rebase: the diff approved on {sha[:12]} is identical on {run.head[:12]}, onto a base that descends from {eq['base_sha'][:12]}",
    )
    return True
