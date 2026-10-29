"""The approval rules: Spec approval, Merge approval, and the specialists a major change needs."""

from __future__ import annotations

from aidd import config, workitems
from aidd.gate import rulebook
from aidd.gate.rules import gate_run
from aidd.kernel import globs

_NO_HASH = object()


def approved_hash(commit: dict | None, spec_id: str) -> object:
    """The Spec hash a commit named in an approval line held for `spec_id`: its goal entry, else its one Spec's; a
    marker when nothing says (an unknown commit, or one that holds no such Spec)."""
    if not commit:
        return _NO_HASH
    if "spec_hashes" in commit:
        return commit["spec_hashes"].get(spec_id, _NO_HASH)
    return commit.get("spec_hash", _NO_HASH)


def gate_spec_approval(run: gate_run.GateRun) -> None:
    """Spec approval: an eligible Approver approved the Spec at a commit where it, its tests, and its design read as they
    do at head (the same Spec hash); every touched owner area too."""
    ctx, add, spec, record = run.ctx, run.add, run.spec, run.record
    if not spec:
        return
    if run.route not in run.g["spec_approval_required_routes"]:
        _recorded_spec_approval(run)
        return
    h = workitems.spec_hash(run.spec_text or "", ctx["head_tree"], ctx["head_files"].get)
    record["spec_hash"] = h
    good: set[str] = set()
    given: dict[str, dict] = {}  # user -> when the counted approval was given, and the commit it named
    proofs: dict[str, bool] = {}  # user -> the approval named a commit holding only the Spec and its frozen files
    late: list[str] = []  # approved commits whose own diff went beyond the frozen files
    stale_commits: list[str] = []  # commits named by approvals of the Spec as it read before: where it was last approved
    unknown: list[str] = []  # commits git does not have here, so nothing says what was approved there
    frozen = [run.cr["spec"], *run.test_files, *run.design_files]
    # A commit that holds only the Spec, its frozen files, the components' threat models it links, and other work items
    # (the plan's Initiatives, Epics, and Specs) is still before implementation: planning is not implementation.
    before_code = [*frozen, *run.threat_models, *workitems.plan_paths(run.cfg.specs_dir)]
    own_scope = [s for task in run.tasks for s in task["scope"]]

    def not_implementation(path: str) -> bool:
        # In a goal's change, the goal's other work too: another Spec's code is never this Spec's implementation,
        # unless it also falls in this Spec's own Task scope.
        return globs.match_any(before_code, path) or (globs.match_any(run.goal_paths, path) and not globs.match_any(own_scope, path))

    for c in run.comments:
        for m in gate_run.APPROVE_SPEC.finditer(gate_run.comment_commands(c["body"])):
            if m.group(1) != spec["id"]:
                continue
            user, sha = config.normalize_identity(c["user"]), m.group(2)
            if sha == ctx.get("base_sha"):
                add("spec_approval", "warn", f"approval names the base commit {sha[:12]}, which proves no Spec commit", code="spec_approval.names_base")
                continue
            # What the person read at that commit, a commit in head's history or one a rebase replaced: it counts only
            # while the Spec and its frozen files read the same at head.
            commit = (ctx.get("approval_commits") or {}).get(sha)
            approved = approved_hash(commit, spec["id"])
            if approved is _NO_HASH:
                # The adapters look up commits for eligible identities only: another's line is no unknown commit.
                if run.may_approve(user, run.pool, run.spec_pool):
                    unknown.append(sha)
                continue
            assert commit is not None
            if approved != h:
                if sha not in stale_commits:
                    stale_commits.append(sha)
                continue
            proven = bool(commit["paths"]) and all(not_implementation(p) for p in commit["paths"])
            if not proven:
                late.append(sha)
            proofs[user] = proofs.get(user, False) or proven
            if run.g["spec_approval_proof"] == "require" and not proofs.get(user):
                continue
            good.add(user)
            given.setdefault(user, {"identity": user, "at": c.get("created_at"), "commit": sha})
    record["spec_approval_before_implementation"] = any(proofs.values())
    if proofs and not any(proofs.values()) and late:
        add(
            "spec_approval",
            "warn",
            f"the approved commit {late[0][:12]} already held changes beyond the Spec and its tests, so Spec approval came after implementation began",
            code="spec_approval.after_implementation",
        )
    # The approval line, exactly as `aidd approve spec` records it: the head commit when the head holds only the Spec and
    # its frozen files (it proves Spec approval came first), else the commit that did.
    head_is_spec_only = bool(run.paths) and all(globs.match_any([*frozen, *run.threat_models], p) for p in run.paths)
    at = "<the commit that holds only the Spec and its tests>" if run.g["spec_approval_proof"] == "require" and not head_is_spec_only else run.head
    line = f"the approval line is `/aidd approve-spec {spec['id']} {at}`"
    if run.g["spec_approval_proof"] == "require" and not good:
        add(
            "spec_approval",
            "pending",
            "profile requires the approval to name the commit it was given on, holding only the Spec and its tests",
            rulebook.finding_fix("spec_approval.commit_required", line),
            code="spec_approval.commit_required",
        )
    pool, spec_pool = run.pool, run.spec_pool
    spec_ok = sorted(u for u in good if run.may_approve(u, pool, spec_pool))
    run.spec_approved = bool(spec_ok)
    record["spec_approved_by"] = spec_ok
    record["spec_approvals"] = [given[u] for u in spec_ok]
    touched = [globs.sample_path(s) for task in spec["tasks"] for s in task["scope"]] + run.paths
    for entry in run.owner_entries(touched):
        epool = run.make_pool(entry["approvers"])
        if not [u for u in good if run.may_approve(u, epool)]:
            add(
                "spec_approval",
                "pending",
                f"Spec {spec['id']} touches {', '.join(entry['paths'])}: it needs a Spec approval from {', '.join(entry['approvers'])}",
                rulebook.finding_fix("spec_approval.owner_area", f"one of {', '.join(entry['approvers'])}; {line}"),
                code="spec_approval.owner_area",
            )
    if not spec_ok:
        note = " (earlier approvals were of the Spec or its tests as they read before)" if stale_commits else ""
        if unknown:
            note += f" (an approval names {unknown[0][:12]}, a commit this repository does not have, so it cannot count)"
        fix = rulebook.finding_fix(
            "spec_approval.missing",
            f"`approve {spec['id']}`, or `aidd approve spec {spec['id']}` at their own terminal" if run.ctx.get("platform") == "local" else line,
        )
        if stale_commits:
            # What changed in the frozen files since the last approval, for the Approver to read before approving again.
            fix += f"\nwhat changed since the last approval: git diff --stat {stale_commits[-1][:12]}..{run.head[:12]} -- {' '.join(frozen)}"
        add("spec_approval", "pending", f"Spec {spec['id']} needs a Spec approval of its text as it reads now{note}", fix, code="spec_approval.missing")
    if run.g["specialist_spec_approval"] and run.route == "major":
        for name in run.pools:
            spool, bound = run.specialist_pool(name)
            if spool is None or not [u for u in good if run.may_approve(u, spool)]:
                add(
                    "specialist_approval",
                    "pending",
                    f"Spec {spec['id']} needs a Spec approval from the {name} pool",
                    rulebook.finding_fix("specialist_approval.spec_missing", f"a member of `owners.specialists.{bound}`; {line}"),
                    code="specialist_approval.spec_missing",
                )


def _recorded_spec_approval(run: gate_run.GateRun) -> None:
    """On a route where the profile makes Spec approval optional, one an eligible Approver recorded anyway binds: it froze
    the Spec and its tests as they read at the approved commit, so an approval of them as they read before only fails,
    and red-then-green is required."""
    spec, pool, spec_pool = run.spec, run.pool, run.spec_pool
    assert spec is not None
    commits = run.ctx.get("approval_commits") or {}
    recorded = [
        (config.normalize_identity(c["user"]), m.group(2), c)
        for c in run.comments
        for m in gate_run.APPROVE_SPEC.finditer(gate_run.comment_commands(c["body"]))
        if m.group(1) == spec["id"] and run.may_approve(config.normalize_identity(c["user"]), pool, spec_pool)
    ]
    if not recorded:
        return
    h = workitems.spec_hash(run.spec_text or "", run.ctx["head_tree"], run.ctx["head_files"].get)
    base = run.ctx.get("base_sha")
    given = {
        u: {"identity": u, "at": c.get("created_at"), "commit": sha}
        for u, sha, c in recorded
        if sha != base and approved_hash(commits.get(sha), spec["id"]) == h
    }
    # An approval of the base commit proves no Spec commit; any other binds, a commit git does not have here included
    # (fail closed: nothing says what was approved there).
    bound = [(u, sha) for u, sha, _ in recorded if sha != base]
    if not given and not bound:
        run.add("spec_approval", "warn", "approval names the base commit, which proves no Spec commit", code="spec_approval.names_base")
        return
    run.spec_bound = True
    run.record["spec_hash"] = h
    if given:
        run.spec_approved = True
        run.record["spec_approved_by"] = sorted(given)
        run.record["spec_approvals"] = [given[u] for u in sorted(given)]
        return
    who = ", ".join(sorted({u for u, _ in bound}))
    unknown = [sha for _, sha in bound if approved_hash(commits.get(sha), spec["id"]) is _NO_HASH]
    why = (
        f"names {unknown[0][:12]}, a commit this repository does not have, so nothing says what it approved"
        if len(unknown) == len(bound)
        else "was of the Spec or its tests as they read before: they changed after it"
    )
    run.add(
        "spec_approval",
        "fail",
        f"Spec {spec['id']}'s recorded Spec approval ({who}) {why}. "
        f"A recorded approval binds the Spec and its tests even on route {run.route}, where Spec approval was optional",
        rulebook.finding_fix("spec_approval.voided", f"for this Spec, `approve {spec['id']}`"),
        code="spec_approval.voided",
    )


def _approval_entry(run: gate_run.GateRun, user: str) -> dict:
    """A counted Merge approval for the record, bound to the head; when a trivial rebase carried it, also the head the
    person approved, where it was carried to, and why."""
    entry = {"identity": user, "at": gate_run._stamp(run.approved_at.get(user)), "commit": run.head}
    if user in run.carried:
        sha, why = run.carried[user]
        entry.update(approved_sha=sha, carried_to=run.head, carry_reason=why)
    return entry


def gate_merge_approval(run: gate_run.GateRun) -> None:
    """Merge approval: as many eligible Approvers as the route requires (`gates.approvals`) approved the head commit, owners of touched areas too, and nobody whose approval could be needed requested changes."""
    cfg, add, head, g = run.cfg, run.add, run.head, run.g
    if run.spec_phase:
        return  # nothing is built yet: Merge approval comes after Implement, and the report leads with Spec approval
    if run.ctx.get("approvals_reset_on_push") is False:
        # GitLab's approval names no commit: the gate binds it by time (after this head's pipeline began), and the
        # platform's own approval count, with the reset off, keeps approvals of heads nobody approved since.
        add(
            "merge_approval",
            "warn",
            "the project keeps approvals when commits are pushed, so the platform's approval count can include approvals of an older head. "
            "The gate counts an approval only when it came after this head's pipeline began",
            code="merge_approval.survives_push",
        )
    pool = run.pool
    approved = sorted(u for u in run.approved_at if run.may_approve(u, pool, run.spec_pool))
    run.record["approved_by"] = approved
    run.record["merge_approvals"] = [_approval_entry(run, u) for u in approved]
    for u, (sha, why) in sorted(run.carried.items()):
        if u in approved:
            add("merge_approval", "warn", f"{u}'s approval of {sha[:12]} carried to head {head[:12]}: {why}", code="merge_approval.carried")
    for u, (sha, why) in sorted(run.not_carried.items()):
        if u not in run.approved_at:
            add(
                "merge_approval",
                "warn",
                f"{u}'s approval of {sha[:12]} does not carry to head {head[:12]}: {why}",
                rulebook.finding_fix("merge_approval.not_carried", f"{u}, on head {head[:12]}"),
                code="merge_approval.not_carried",
            )
    # An exact revert of a merged commit needs the incident commander's approval only (gate_emergency checks it is there).
    for entry in [] if run.exact_revert else run.owner_entries(run.paths):
        epool = run.make_pool(entry["approvers"])
        if not [u for u in run.approved_at if run.may_approve(u, epool)]:
            add(
                "merge_approval",
                "pending",
                f"changes under {', '.join(entry['paths'])} need an approval from {', '.join(entry['approvers'])}",
                rulebook.finding_fix("merge_approval.owner_area", f"one of {', '.join(entry['approvers'])}, on head {head[:12]}"),
                code="merge_approval.owner_area",
            )
    quorum = g["approvals"].get("standard", 0) if run.standard_ok else g["approvals"].get(run.route, 1)
    if run.exact_revert:
        quorum = min(quorum, 1)
    # Anyone whose approval the change could need can block it: Approvers, specialist Approvers, and path owners.
    blockers = [pool] + [run.make_pool(members) for members in cfg.specialists.values()]
    blockers += [run.make_pool(e["approvers"]) for e in run.owner_entries(run.paths)]
    blocked_by = sorted(u for u, r in run.latest.items() if r["state"] == "changes_requested" and u not in run.authors and any(u in b for b in blockers))
    if blocked_by:
        add(
            "merge_approval",
            "pending",
            f"changes requested by {', '.join(blocked_by)}",
            code="merge_approval.changes_requested",
        )
    if len(approved) < quorum:
        notes = []
        if run.stale_reviews:
            notes.append(f"approvals on an older commit, or given before the base branch changed, do not count ({', '.join(sorted(run.stale_reviews))})")
        if not run.solo and any(u in (run.authors | run.bots) for u in run.approved_at):
            notes.append("an author or an agent cannot approve")
        if pool.unresolved:
            notes.append(f"could not resolve {', '.join(pool.unresolved)}")
        if run.ctx.get("platform") == "local":
            hint = f"head {head[:12]}; `merge it` on a pull request, `approve merge`, or `aidd approve merge` at their own terminal does the same"
        else:
            hint = f"head {head[:12]}" + (f", or a comment `/aidd approve-merge {head}`" if run.solo else "")
        hint = rulebook.finding_fix("merge_approval.missing", hint)
        add(
            "merge_approval",
            "pending",
            f"needs {quorum} approval(s) on head {head[:12]}, has {len(approved)}" + (f" ({'; '.join(notes)})" if notes else ""),
            hint,
            code="merge_approval.missing",
        )


def gate_specialist_approval(run: gate_run.GateRun) -> None:
    """Major, an emergency repair that would be major, and any change a risk rule asks a pool for by name: each
    required specialist pool approved the head.

    The emergency lane waives Specify, the changed-line limit, and red-then-green, never the specialist who
    would have reviewed the same change outside an emergency. An exact revert needs none.
    """
    g, route = run.g, run.route
    major_repair = route == "emergency" and (run.protected_hit or run.record.get("required_route") == "major") and not run.exact_revert
    asked = bool(run.asked_pools) and not run.exact_revert
    if not (route == "major" or major_repair or asked) or g["specialist_approvals"] <= 0 or run.spec_phase:
        return
    approved: dict[str, list[str]] = {}
    for name in run.pools or ["security"]:
        spool, bound = run.specialist_pool(name)
        if spool is None:
            run.add(
                "specialist_approval",
                "fail",
                f"{route} needs owners.specialists.{name}"
                + ("" if name == "security" else " (or owners.specialists.security)")
                + f" under profile {run.cfg.profile}",
                rulebook.finding_fix("specialist_approval.unbound", f'here, `{name}: ["@org/{name}"]`'),
                code="specialist_approval.unbound",
            )
            continue
        users = sorted(u for u in run.approved_at if run.may_approve(u, spool))
        approved[name] = users
        if len(users) < g["specialist_approvals"]:
            stand_in = f" (owners.specialists.{bound} stands in)" if bound != name else ""
            why = ""
            if route != "major":
                asks = name in run.asked_pools
                why = (
                    "; a risk rule asks this pool for what the change does"
                    if asks
                    else "; an emergency repair that would be major keeps its specialist approval"
                )
            run.add(
                "specialist_approval",
                "pending",
                f"needs {g['specialist_approvals']} approval(s) from the {name} pool{stand_in} on head, has {len(users)}{why}",
                rulebook.finding_fix("specialist_approval.missing", f"here, the {name} pool, on head {run.head[:12]}"),
                code="specialist_approval.missing",
            )
    run.record["specialist_approved_by"] = approved
