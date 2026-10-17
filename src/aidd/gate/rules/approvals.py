"""The approval rules: Spec approval, Merge approval, and the specialists a major change needs."""

from __future__ import annotations

from aidd import config, workitems
from aidd.gate.rules import gate_run
from aidd.kernel import globs


def gate_spec_approval(run: gate_run.GateRun) -> None:
    """Spec approval: an eligible Approver approved the exact Spec hash; every touched owner area too."""
    ctx, add, spec, record = run.ctx, run.add, run.spec, run.record
    if not spec:
        return
    if run.route not in run.g["spec_approval_routes"]:
        _recorded_spec_approval(run)
        return
    h = workitems.spec_hash(run.spec_text or "", ctx["head_tree"])
    record["spec_hash"] = h
    good: set[str] = set()
    given: dict[str, dict] = {}  # user -> when the counted approval was given, and the commit it named
    proofs: dict[str, bool] = {}  # user -> the approval named a commit holding only the Spec and its frozen files
    unrelated: list[str] = []  # named commits that are neither in head's history nor the approved Spec rebased
    late: list[str] = []  # named commits that are the approved Spec's, but whose own diff went beyond the frozen files
    stale_commits: list[str] = []  # commits named by approvals of an older hash: where the frozen files last were approved
    stale = False
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
            if m.group(2) != h:
                stale = True
                if m.group(3) and m.group(3) not in stale_commits:
                    stale_commits.append(m.group(3))
                continue
            user = config.normalize_identity(c["user"])
            sha = m.group(3) or ""
            if sha and sha == ctx.get("base_sha"):
                add("spec_approval", "warn", f"approval names the base commit {sha[:12]}, which proves no Spec commit", code="spec_approval.names_base")
            commit = (ctx.get("approval_commits") or {}).get(sha)
            if commit is not None:
                # A commit in head's history, or one a rebase replaced whose Spec hashes to the approved hash: its own
                # diff (from where it meets the base) must hold only the Spec and its frozen files.
                related = bool(commit["ancestor"]) or commit.get("spec_hash") == h
                only_frozen = bool(commit["paths"]) and sha != ctx.get("base_sha") and all(not_implementation(p) for p in commit["paths"])
                proven = related and only_frozen
                if not related:
                    unrelated.append(sha)
                elif not proven:
                    late.append(sha)
                proofs[user] = proofs.get(user, False) or proven
            if run.g["spec_approval_proof"] == "require" and not proofs.get(user):
                continue
            good.add(user)
            given.setdefault(user, {"identity": user, "at": c.get("created_at"), "commit": sha or None})
    if proofs:
        record["spec_approval_before_implementation"] = any(proofs.values())
        if not any(proofs.values()) and late:
            add(
                "spec_approval",
                "warn",
                f"the approved commit {late[0][:12]} already held changes beyond the Spec and its tests, so Spec approval came after implementation began",
                code="spec_approval.after_implementation",
            )
        if not any(proofs.values()) and unrelated:
            add(
                "spec_approval",
                "warn",
                f"the approval names commit {unrelated[0][:12]}, which is not in this branch's history and whose Spec does not hash to "
                f"{h}. So the approval proves nothing about when Spec approval came",
                f"approve again naming a commit on this branch that holds only the Spec and its tests: `aidd hash {run.cr['spec']} --line --ref <that commit>`",
                code="spec_approval.not_ancestor",
            )
    else:
        record["spec_approval_before_implementation"] = False
    # The approval line, exactly as `aidd hash <spec> --line` prints it: with the head commit when the head holds only
    # the Spec and its frozen files (it proves Spec approval came first), else with the commit that did.
    head_is_spec_only = bool(run.paths) and all(globs.match_any([*frozen, *run.threat_models], p) for p in run.paths)
    line = f"/aidd approve-spec {spec['id']} {h}" + (f" {run.head}" if head_is_spec_only else "")
    if run.g["spec_approval_proof"] == "require" and not head_is_spec_only:
        how = f"on the commit that holds only the Spec and its tests, `aidd hash {run.cr['spec']} --line --ref <that commit>` prints the line to post"
    else:
        how = line
    if run.g["spec_approval_proof"] == "require" and not good:
        add(
            "spec_approval",
            "pending",
            "profile requires the approval to name the commit it was given on, holding only the Spec and its tests",
            f"an eligible Approver posts {how}" if how == line else how,
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
                f"one of {', '.join(entry['approvers'])} posts: {how}",
                code="spec_approval.owner_area",
            )
    if not spec_ok:
        note = " (earlier approvals were for a different Spec or tests)" if stale else ""
        fix = f"an eligible Approver posts: {how}" + (
            " (on this machine: they type `approve <ID>` at their coding agent's prompt, or run `aidd approve spec` at their own terminal)"
            if run.ctx.get("platform") == "local"
            else ""
        )
        if stale_commits:
            # What changed in the frozen files since the last approval, for the Approver to read before approving again.
            fix += f"\nwhat changed since the last approval: git diff --stat {stale_commits[-1][:12]}..{run.head[:12]} -- {' '.join(frozen)}"
        add(
            "spec_approval",
            "pending",
            f"Spec {spec['id']} needs approval of hash {h}{note}",
            fix,
            code="spec_approval.missing",
        )
    if run.g["specialist_spec_approval"] and run.route == "major":
        for name in run.pools:
            spool, bound = run.specialist_pool(name)
            if spool is None or not [u for u in good if run.may_approve(u, spool)]:
                add(
                    "specialist_approval",
                    "pending",
                    f"Spec {spec['id']} needs an approval of hash {h} from the {name} pool",
                    f"a member of owners.specialists.{bound} posts: {how}",
                    code="specialist_approval.spec_missing",
                )


def _recorded_spec_approval(run: gate_run.GateRun) -> None:
    """On a route where the profile makes Spec approval optional, one an eligible Approver recorded anyway binds: its hash
    freezes the Spec and its tests, so an approval of another hash only fails, and red-then-green is required."""
    spec, pool, spec_pool = run.spec, run.pool, run.spec_pool
    assert spec is not None
    recorded = [
        (config.normalize_identity(c["user"]), m.group(2), c)
        for c in run.comments
        for m in gate_run.APPROVE_SPEC.finditer(gate_run.comment_commands(c["body"]))
        if m.group(1) == spec["id"] and run.may_approve(config.normalize_identity(c["user"]), pool, spec_pool)
    ]
    if not recorded:
        return
    h = workitems.spec_hash(run.spec_text or "", run.ctx["head_tree"])
    run.spec_bound = True
    run.record["spec_hash"] = h
    given = {u: {"identity": u, "at": c.get("created_at"), "commit": None} for u, x, c in recorded if x == h}
    if given:
        run.spec_approved = True
        run.record["spec_approved_by"] = sorted(given)
        run.record["spec_approvals"] = [given[u] for u in sorted(given)]
        return
    who = ", ".join(sorted({u for u, _, _ in recorded}))
    run.add(
        "spec_approval",
        "fail",
        f"Spec {spec['id']}'s recorded Spec approval ({who}) names another hash than {h}: the Spec or its tests changed after it. "
        f"A recorded approval binds the Spec and its tests even on route {run.route}, where Spec approval was optional",
        f"restore the approved Spec and tests, or have a person read the change and approve the new hash (locally `aidd approve spec {run.cr['spec']}`)",
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
            'turn on "Remove all approvals when commits are added" in the project\'s merge request approval settings',
            code="merge_approval.time_bound",
        )
    pool = run.pool
    approved = sorted(u for u in run.approved_at if run.may_approve(u, pool, run.spec_pool) and run.cooled(u))
    run.record["approved_by"] = approved
    run.record["merge_approvals"] = [_approval_entry(run, u) for u in approved]
    skipped = sorted(u for u in approved if u in run.cooloff_skipped) if g["cooloff_minutes"].get(run.route, 0) else []
    if skipped:
        run.record["cooloff_skipped_by"] = skipped
        add(
            "merge_approval",
            "warn",
            f"{', '.join(skipped)} skipped the {g['cooloff_minutes'][run.route]}-minute cool-off at their own terminal (`--skip-cooloff`). Locally "
            "the cool-off starts at a committer date the committer sets, so it is a reminder. The record keeps the skip",
            code="merge_approval.cooloff_skipped",
        )
    for u, (sha, why) in sorted(run.carried.items()):
        if u in approved:
            add("merge_approval", "warn", f"{u}'s approval of {sha[:12]} carried to head {head[:12]}: {why}", code="merge_approval.carried")
    for u, (sha, why) in sorted(run.not_carried.items()):
        if u not in run.approved_at:
            add(
                "merge_approval",
                "warn",
                f"{u}'s approval of {sha[:12]} does not carry to head {head[:12]}: {why}",
                f"{u} approves head {head[:12]} again",
                code="merge_approval.not_carried",
            )
    # An exact revert of a merged commit needs the incident commander's approval only (gate_emergency checks it is there).
    for entry in [] if run.exact_revert else run.owner_entries(run.paths):
        epool = run.make_pool(entry["approvers"])
        if not [u for u in run.approved_at if run.may_approve(u, epool) and run.cooled(u)]:
            add(
                "merge_approval",
                "pending",
                f"changes under {', '.join(entry['paths'])} need an approval from {', '.join(entry['approvers'])}",
                f"one of {', '.join(entry['approvers'])} approves head {head[:12]}",
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
            "answer the requested changes and push; the reviewer then approves, or dismisses the review",
            code="merge_approval.changes_requested",
        )
    if len(approved) < quorum:
        cooloff = g["cooloff_minutes"].get(run.route, 0)
        notes = []
        if run.stale_reviews:
            notes.append(f"approvals on an older commit, or given before the base branch changed, do not count ({', '.join(sorted(run.stale_reviews))})")
        if not run.solo and any(u in (run.authors | run.bots) for u in run.approved_at):
            notes.append("an author or an agent cannot approve")
        if cooloff and not all(run.cooled(u) for u in run.approved_at):
            since = "the head commit" if run.ctx.get("platform") == "local" else "the last push"
            notes.append(f"approvals must come at least {cooloff} min after {since}")
        if pool.unresolved:
            notes.append(f"could not resolve {', '.join(pool.unresolved)}")
        if run.ctx.get("platform") == "local":
            hint = (
                f"a person types `ship it` (or `approve merge`) at their coding agent's prompt, or runs `aidd approve merge` at their own "
                f"terminal, on head {head[:12]}"
            )
        else:
            hint = f"approve the PR/MR on head {head[:12]}" + (f", or comment /aidd approve-merge {head}" if run.solo else "")
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

    The emergency lane waives Specify, the budget, and red-then-green, never the specialist who
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
                f'bind the pool in the config: `owners.specialists` {name} = ["@org/{name}"]',
                code="specialist_approval.unbound",
            )
            continue
        users = sorted(u for u in run.approved_at if run.may_approve(u, spool) and run.cooled(u))
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
                f"ask a member of the {name} pool to review and approve this head",
                code="specialist_approval.missing",
            )
    run.record["specialist_approved_by"] = approved
