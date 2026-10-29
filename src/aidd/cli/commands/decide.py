"""The Decide commands: hash, approve, and explore."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aidd import config, gate, platforms, tracking, workitems
from aidd.cli import arguments
from aidd.cli.commands import standing
from aidd.cli.commands.confirmations import DECIDED_VIA as DECIDED_VIA
from aidd.cli.commands.confirmations import DECIDED_WHERE as DECIDED_WHERE
from aidd.cli.commands.confirmations import confirmation_problem as confirmation_problem
from aidd.cli.commands.confirmations import local_identity_problem as local_identity_problem
from aidd.cli.commands.confirmations import outside_shown
from aidd.cli.commands.standing import spec_route
from aidd.cli.commands.standing import standing_for as standing_for
from aidd.kernel import documents, git, globs


def cmd_hash(args) -> int:
    raw = args.spec
    arguments.enter_repo(args, "spec", file_attrs=("out",))
    if raw and "/" not in raw and "\\" not in raw and not Path(args.spec).is_file():
        args.spec = arguments.spec_by_id(raw, None if args.worktree else args.ref)
    if args.worktree:
        text = Path(args.spec).read_text(encoding="utf-8")
        data, _ = documents.split_front_matter(text, args.spec)
        if data.get("kind") == "proposal":
            return _proposal_hash(args, text)
        # Untracked files count too: the hash must match what the gate computes once they are committed.
        files = [
            p
            for p in git.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"]).split("\0")
            if p and globs.match_any(workitems.frozen_files(data), p) and Path(p).is_file()
        ]
        tree = git.hash_files(files)
        read = lambda p: Path(p).read_text(encoding="utf-8", errors="replace")  # noqa: E731
    else:
        shown = git.show(args.ref, args.spec)
        if shown is None:
            raise ValueError(f"{args.spec} is not in {args.ref}; commit it first, or pass --worktree")
        text = shown
        data, _ = documents.split_front_matter(text, args.spec)
        if data.get("kind") == "proposal":
            _proposal_flags(args)  # refuse a Spec-only flag before any warning
            if git.run(["status", "--porcelain", "--", args.spec], check=False).strip():
                print(f"warning: uncommitted changes to the proposal; this hash is for {args.ref}", file=sys.stderr)
            return _proposal_hash(args, text)
        tree = git.ls_tree(args.ref)
        dirty = git.run(["status", "--porcelain", "--", args.spec, *workitems.frozen_files(data)], check=False).strip()
        if dirty:
            print(f"warning: uncommitted changes to the Spec or its tests; this hash is for {args.ref}", file=sys.stderr)
        read = lambda p: git.show(args.ref, p) or ""  # noqa: E731
    # A file git cannot give is None to the hash, so the whole file counts, never an empty text's sections.
    h = workitems.spec_hash(text, tree, read if args.worktree else lambda p: git.show(args.ref, p))
    if args.summary:
        from aidd import views

        # What the Approver reads before approving, in at most 25 lines; the hash is the last.
        docs = workitems.frozen_docs(data)
        doc_texts = {p: read(p) for p in tree if globs.match_any(docs, p)}
        print(views.spec_summary(text, args.spec, h, files=doc_texts))
    else:
        print(h)
    if args.html or args.out:
        _spec_view(args, text, data, h, tree, read)
    return 0


def _proposal_flags(args) -> None:
    """Refuse the flags that show what a Spec approval covers: a proposal has none of it."""
    if args.summary or args.html or args.out:
        raise ValueError("--summary, --html, and --out show what a Spec approval covers; a proposal takes no flag")


def _proposal_hash(args, text: str) -> int:
    """`aidd hash` on a proposal: the hash a person records as `sign_off.hash`."""
    _proposal_flags(args)
    h = workitems.proposal_hash(text)
    print(h)
    return 0


def _spec_view(args, text: str, data: dict, h: str, tree: dict[str, str], read) -> None:
    """The Spec approval page: what `--summary` prints, and the frozen files, the route, and what changed since the last
    approval, as one HTML page for the Approver. The approval line on it is the one printed above."""
    from aidd import views

    line = "" if args.worktree else workitems.approve_spec_line(str(data.get("id")), git.rev_parse(args.ref))
    frozen = workitems.frozen_files(data)
    files = {p: read(p) for p in sorted(tree) if globs.match_any(frozen, p)}
    route = None
    cfg = arguments.config_or_none_quiet()
    scope = [s for task in data.get("tasks") or [] for s in task.get("scope") or []]
    if cfg is not None and scope:
        risk = data.get("risk") or {}
        tracked = [p for p in git.run(["ls-files", "-z"], check=False).split("\0") if p]
        a = gate.assess_paths(
            cfg,
            scope,
            ctype=str(data.get("type") or "feat"),
            dimensions=list(risk.get("dimensions") or []),
            irreversible=risk.get("reversible") is False,
            tracked=tracked,
        )
        route = gate.route_summary(a, "the Spec's scope")
    head = "" if args.worktree else git.rev_parse(args.ref)
    earlier = tracking.earlier_spec_approval(str(data.get("id")), h, args.spec)
    since = None
    if earlier:
        paths = [args.spec, *frozen]
        span = [earlier, head] if head else [earlier]
        since = {
            "commit": earlier,
            "stat": git.run(["diff", "--stat", *span, "--", *paths], check=False).rstrip(),
            "diff": git.run(["diff", "--no-color", "--no-ext-diff", *span, "--", *paths], check=False),
        }
    page = views.spec_page(text, args.spec, line, files=files, spec_hash=h, commit=head or "the working tree", route=route, since=since)
    out = views.write(args.out or views.default_path("spec", str(data.get("id") or Path(args.spec).stem)), page)
    print(f"wrote {arguments.repo_relative(out)}", file=sys.stderr)


def cmd_explore(args) -> int:
    """An exploration's comparison page (`aidd new exploration` writes the exploration)."""
    from aidd import views

    arguments.enter_repo(args, "folder", file_attrs=("out",))
    folder = Path(args.folder)
    # `specs/SPEC-9/explore/refund` is the page `explore-SPEC-9-refund`: two items' cards may share a slug.
    item = folder.parent.parent.name if folder.parent.name == "explore" else ""
    name = f"{item}-{folder.name}" if workitems.WORK_ID.fullmatch(item) else folder.name
    target = Path(args.out) if args.out else views.default_path("explore", name)
    views.write(target, views.comparison_page(folder))
    print(f"wrote {arguments.repo_relative(target)}")
    return 0


def cmd_approve(args) -> int:
    """Record a person's approval on this machine, with no platform: a Spec approval or a Merge approval (workitems/decision_records.py)."""

    arguments.enter_repo(args, "spec", file_attrs=("evidence",))
    try:
        if args.what is None and (picked := _pick(args)) is not None:
            return picked
        if args.what == "spec" and getattr(args, "more", None):
            return _batch_spec_approvals(args)
        if args.what in ("all", "stop"):
            decided = standing.record(args)
        else:
            decided = _spec_approval(args) if args.what == "spec" else _merge_approval(args)
        if isinstance(decided, int):
            return decided
        line, done = decided
        sha, signed = workitems.record_local_approval(line)
    except platforms.NotAPerson as exc:
        print(f"Not approved: {exc}", file=sys.stderr)
        return 1
    print(f"{done}. Recorded {'signed' if signed else 'unsigned'} as {sha[:12]} (`aidd log` lists it).")
    if not signed and getattr(args, "confirmed", None) is None:
        print("Tip: sign approvals with a key that asks for your touch, so nothing can approve without you (docs/ADOPTION.md, Local-first).")
    return 0


def _pick(args) -> int | None:
    """`aidd approve` alone, at a person's terminal: what waits on their approval, numbered, and the one they pick.
    Sets `args` for that approval and returns None to go on, or an exit code to stop."""
    from aidd import tracking

    platforms.check_terminal("An approval", "aidd approve spec <ID>")
    waiting = [s for s in tracking.plan(Path("."), filters=tracking.Filters(all=True, waiting_on_me=True)) if s.get("code") in tracking.APPROVER_WAITS]
    if not waiting:
        print("Nothing waits on your approval. `aidd list` shows all open work.")
        return 0
    print("Waiting on your approval:")
    for i, s in enumerate(waiting, 1):
        what = "Spec approval" if s["code"] == "spec.spec_approval" else "Merge approval"
        print(f"  {i}. {s.get('id') or '':10} {what:15} {s.get('branch') or ''}")
    try:
        answer = input(f"Which one? [1{f'-{len(waiting)}' if len(waiting) > 1 else ''}, Enter for none] ").strip()
    except EOFError:
        answer = ""
    if not answer.isdigit() or not 1 <= int(answer) <= len(waiting):
        print("Nothing approved.")
        return 0
    s = waiting[int(answer) - 1]
    branch = str(s.get("branch") or "")
    if s["code"] == "spec.spec_approval":
        args.what, args.spec, args.ref = "spec", str(s.get("id")), branch or "HEAD"
        return None
    if branch and branch != _branch():
        print(f"{branch} is checked out elsewhere: Merge approval runs in its worktree, `aidd approve merge` there.", file=sys.stderr)
        return 1
    args.what = "merge"
    return None


def _batch_spec_approvals(args) -> int:
    """`aidd approve spec SPEC-1 SPEC-2 ...` at a person's terminal: each Spec checked and shown as one approval is, then
    one question for all of them, and each recorded for its own hash. Any Spec that cannot be approved stops them all."""
    specs = [args.spec, *args.more]
    if args.show or args.confirmed is not None or gate.platform_of(".") == "preflight":
        print(
            "error: approve several Specs at once only at your own terminal, with no platform; with --show or --confirmed, "
            "or on a platform's pull requests, approve each Spec on its own",
            file=sys.stderr,
        )
        return 2
    decided: list[tuple[str, str]] = []
    for spec in specs:
        args.spec = spec
        one = _spec_approval(args, ask=False)
        if isinstance(one, int):
            print(f"Nothing was approved: {spec} cannot be approved now.", file=sys.stderr)
            return one
        decided.append(one)
    ids = [said.removeprefix("Approved ").split(" ", 1)[0] for _, said in decided]
    platforms.require_person(f"Spec approval for {', '.join(ids)}", command=f"aidd approve spec {' '.join(specs)}", question=f"Approve {', '.join(ids)}?")
    for line, said in decided:
        sha, signed = workitems.record_local_approval(line)
        print(f"{said}. Recorded {'signed' if signed else 'unsigned'} as {sha[:12]} (`aidd log` lists it).")
    return 0


def _spec_approval(args, ask: bool = True) -> tuple[str, str] | int:
    """The Spec approval record and what to say once it is recorded, or the exit code that stops it. `--show` prints
    the preview and stops; `--confirmed` takes the person's answer from Claude Code or an MCP client; else the terminal
    asks, unless `ask` is off for a batch that asks once for all."""
    if not args.spec:
        print("error: name the Spec: aidd approve spec specs/<ID>.md", file=sys.stderr)
        return 2
    args.spec = arguments.spec_by_id(args.spec, args.ref)
    text = git.show(args.ref, args.spec)
    if text is None and not Path(args.spec).is_file():
        print(f"error: no such Spec: {args.spec}", file=sys.stderr)
        return 2  # a usage error, like a missing argument
    if text is None:
        print(f"error: {args.spec} is not committed in {args.ref}; commit the Spec and its tests first", file=sys.stderr)
        return 1  # a failed check: the Spec exists, but not in the commit
    data, _ = documents.split_front_matter(text, args.spec)
    head = git.rev_parse(args.ref)
    h = workitems.spec_hash(text, git.ls_tree(head), lambda p: git.show(head, p))
    if args.show:
        print(json.dumps(_spec_preview(args, data, text, h, head), indent=2))
        return 0
    if args.ref == "HEAD" and git.run(["status", "--porcelain", "--", args.spec, *workitems.frozen_files(data)], check=False).strip():
        print("error: the Spec or its tests have uncommitted changes; approve what is committed", file=sys.stderr)
        return 1
    if unready := workitems.spec_approval_problems(text, args.spec):
        # An approval of a stub would freeze the stub: nobody approves a Spec that is not finished.
        print(f"error: {data.get('id')} is not ready for approval: {unready[0]}. Finish it, `aidd validate {args.spec}`, then approve", file=sys.stderr)
        return 1
    spec_id = str(data.get("id"))
    command = f"aidd approve spec {args.spec}" + (f" --ref {args.ref}" if args.ref != "HEAD" else "")
    standing = standing_for(spec_route(data)) if args.confirmed is None else None
    if standing is not None:
        if problem := local_identity_problem():
            print(f"error: {problem}", file=sys.stderr)
            return 1
    elif (stopped := _who_confirms(args, spec_id, h, head, command)) is not None:
        return stopped
    line = workitems.approve_spec_line(spec_id, head)
    on_platform = gate.platform_of(".") == "preflight"
    if args.confirmed is not None or standing is not None:
        if on_platform:
            return _post_spec(spec_id, line, head, _ref_branch(args), ask=None)
        where = args.decided_via if standing is None else f"standing:{standing['sha'][:12]}"
        said = f"Approved {spec_id}" + (f" under your standing approval of {standing['since'][:16]}" if standing else "")
        return workitems.decided_via(line, where), said
    _show_spec(args, data, text, h, head)
    if on_platform:
        return _post_spec(spec_id, line, head, _ref_branch(args), ask=command)
    if ask:
        platforms.require_person(f"Spec approval for {spec_id}", command=command, question=f"Approve {spec_id}?")
    return line, f"Approved {spec_id}"


def _show_spec(args, data: dict, text: str, h: str, head: str) -> None:
    """What a person reads before a Spec approval: the card, then whether it came late and what changed since."""
    ids = workitems.acceptance_ids(text)
    frozen = len(workitems.frozen_paths(data))
    rows = [
        ("Acceptance", ", ".join(ids) or "none listed"),
        ("Freezes", f"the Spec and {frozen} test or design pattern{'' if frozen == 1 else 's'}"),
        ("Commit", f"{head[:12]} ({args.ref if args.ref != 'HEAD' else _branch()})"),
        ("Risk", risk_line(data)),
        *([("Revised", revised)] if (revised := revision_line(data)) else []),
    ]
    print(card(f"Spec approval for {plain(str(data.get('id')), 40)}", plain(data.get("title")), [(k, plain(v, 240)) for k, v in rows]))
    _before_spec_approval(args, data, h, head)


def _who_confirms(args, spec_id: str, h: str, head: str, command: str) -> int | None:
    """Who may give this Spec approval: a person at a terminal no agent started, or a dialog's answer for exactly the
    commit they read (`--confirmed`), from an identity that can approve here. None to go on, or the exit code that stops."""
    if args.confirmed is None:
        platforms.check_terminal(f"Spec approval for {spec_id}", command)
    elif args.confirmed != head:
        print(
            f"error: you read {spec_id} at {args.confirmed[:12]}, but its branch is now at {head[:12]}. Nothing was recorded; review it again",
            file=sys.stderr,
        )
        return 1
    elif problem := confirmation_problem(args.decided_via):
        print(f"error: not approved: {problem}", file=sys.stderr)
        return 2 if not DECIDED_WHERE.fullmatch(args.decided_via) else 1
    if problem := local_identity_problem():
        print(f"error: {problem}", file=sys.stderr)
        return 1
    return None


def _ref_branch(args) -> str:
    """The branch an approval is for: `--ref` when it names one, else this checkout's."""
    ref = str(getattr(args, "ref", "HEAD") or "HEAD")
    return _branch() if ref == "HEAD" else ref.removeprefix("refs/heads/")


def _platform_target(branch: str, head: str) -> tuple[platforms.PullRequest | None, str | None]:
    """On a repository whose gate runs on GitHub: the branch's pull request, when a person's approval of `head` can go
    there as them, or why not. This machine's decision records never count there, so nothing is recorded locally."""
    cfg = arguments.config_or_none_quiet()
    pr, why = platforms.approval_target(".", branch, list(cfg.approvers) if cfg else [])
    if pr is None:
        return None, why
    if pr.head_sha != head and not git.ok(["merge-base", "--is-ancestor", head, pr.head_sha]):
        return None, f"{pr.repo}#{pr.number}'s head is {pr.head_sha[:12]}, not {head[:12]}: push {branch}, then approve"
    return pr, None


def _post_spec(spec_id: str, line: str, head: str, branch: str, *, ask: str | None) -> int:
    """Spec approval where a platform's gate decides: the approval line, posted on the branch's pull request as the
    person, after their yes at the terminal (`ask`, the command to copy) or their answer in a dialog (`ask` None)."""
    pr, why = _platform_target(branch, head)
    if pr is None:
        print(f"error: not approved: {why}. Or post this line on the PR/MR yourself, as an Approver:\n  {line}", file=sys.stderr)
        return 1
    if ask is not None:
        platforms.require_person(
            f"Spec approval for {spec_id}", command=ask, question=f"Post your approval of {spec_id} on {pr.repo}#{pr.number} as @{pr.login}?"
        )
    url = platforms.post_spec_approval(pr, line)
    print(f"Approved {spec_id}: posted on {url} as @{pr.login}. The gate on GitHub counts it.")
    return 0


def _merge_approval(args) -> tuple[str, str] | int:
    """The Merge approval record of HEAD and what to say once it is recorded, or the exit code that stops it."""
    head = git.rev_parse("HEAD")
    branch = _branch()
    if args.show:
        print(json.dumps(merge_preview(args, head), indent=2))
        return 0
    standing = standing_for(str(merge_preview(args, head)["route"]), merge=True) if args.confirmed is None else None
    if standing is not None:
        return _merge_under_standing(args, standing, head, branch)
    said = workitems.land_decision(arguments.config_or_none_quiet(), ".", head) if args.confirmed is None else None
    if said is not None and workitems.covers_platform_merge(said, gate.platform_of(".")):
        return _merge_under_land_it(args, said, head, branch)
    if args.confirmed is None:
        platforms.check_terminal(f"Merge approval for the head commit {head[:12]}", "aidd approve merge")
    elif args.confirmed != head:
        print(
            f"error: you confirmed {branch} at {args.confirmed[:12]}, but its head is now {head[:12]}. Nothing was recorded; review it again", file=sys.stderr
        )
        return 1
    elif problem := confirmation_problem(args.decided_via):
        print(f"error: not approved: {problem}", file=sys.stderr)
        return 2 if not DECIDED_WHERE.fullmatch(args.decided_via) else 1
    if problem := local_identity_problem():
        print(f"error: {problem}", file=sys.stderr)
        return 1
    line = workitems.approve_merge_line(head, branch=branch)
    on_platform = gate.platform_of(".") == "preflight"
    if args.confirmed is not None:
        shown = merge_preview(args, head)
        if problems := shown["problems"]:
            print(f"error: not approved: {problems[0]}", file=sys.stderr)
            return 1
        if on_platform:
            return _approve_on_platform(branch, head, ask=False, auto_merge=args.auto_merge)
        return workitems.decided_via(line, args.decided_via), f"Approved merging {branch} at {head[:12]}" + _still_failing_note(shown["failing"])
    if not _before_merge_approval(args, head):
        return 1
    if on_platform:
        return _approve_on_platform(branch, head, ask=True, auto_merge=args.auto_merge)
    platforms.require_person(
        f"Merge approval for the head commit {head[:12]}", command="aidd approve merge", question=f"Approve merging {branch} at {head[:12]}?"
    )
    return line, f"Approved merging {branch} at {head[:12]}"


def _still_failing_note(failing: list[str]) -> str:
    """What the person's Merge approval leaves for the team, when the gate still fails on something else."""
    if not failing:
        return ""
    return f". The gate still fails on {', '.join(failing)}: the team fixes that, and the merge waits for it"


def _merge_under_standing(args, standing: dict, head: str, branch: str) -> tuple[str, str] | int:
    """Merge approval of `head` that the person's standing approval covers: recorded with nobody asked, citing it. Under
    a standing approval the agent records it, so only for a head whose gate fails on nothing else."""
    shown = merge_preview(args, head)
    if problems := shown["problems"] or ([f"the gate fails on {', '.join(shown['failing'])} for head {head[:12]}; fix that first"] if shown["failing"] else []):
        print(f"error: not approved: {problems[0]}", file=sys.stderr)
        return 1
    if gate.platform_of(".") == "preflight":
        # With auto-merge, as their "merge it" would, or nothing merges it; `stop approving` turns it off again.
        return _approve_on_platform(branch, head, ask=False, auto_merge=True, decided_via=f"standing:{standing['sha'][:12]}")
    line = workitems.approve_merge_line(head, branch=branch)
    said = f"Approved merging {branch} at {head[:12]} under your standing approval of {standing['since'][:16]}"
    return workitems.decided_via(line, f"standing:{standing['sha'][:12]}"), said


def _merge_under_land_it(args, said: dict, head: str, branch: str) -> tuple[str, str] | int:
    """Merge approval of `head` under the person's "land it" or "merge it" (workitems.land_decision): recorded with nobody asked,
    citing it, as under a standing approval for this one change. The agent records it, so only for a head whose gate
    fails on nothing else; on a platform, the person's approving review of exactly `head`, with auto-merge."""
    shown = merge_preview(args, head)
    if problems := shown["problems"] or ([f"the gate fails on {', '.join(shown['failing'])} for head {head[:12]}; fix that first"] if shown["failing"] else []):
        print(f"error: not approved: {problems[0]}", file=sys.stderr)
        return 1
    print(land_it_note(said, head))
    if gate.platform_of(".") == "preflight":
        return _approve_on_platform(branch, head, ask=False, auto_merge=True, decided_via=land_it_decided_via(said))
    line = workitems.approve_merge_line(head, branch=branch)
    return workitems.decided_via(line, land_it_decided_via(said) or "prompt"), f'Approved merging {branch} at {head[:12]} under your "land it"'


def land_it_decided_via(said: dict | None) -> str | None:
    """Where a Merge approval under the person's "land it" or "merge it" was confirmed: `prompt` for the head they said it for, else
    the record it rests on (`land-it:<sha>`), so the record never claims they saw a head they did not."""
    if said is None:
        return None
    return "prompt" if said["exact"] else f"land-it:{said['sha'][:12]}"


def land_it_note(said: dict, head: str) -> str:
    """What the person reads when their "land it" or "merge it" covers `head`: for a later head, each commit they have not seen."""
    if said["exact"]:
        return f"you said to land {head[:12]}, so nobody is asked again"
    commits = git.run(["log", "--format=%h %s", f"{said['head']}..{head}"], check=False).splitlines()
    shown = "; ".join(commits[:5]) + (f"; and {len(commits) - 5} more" if len(commits) > 5 else "")
    return (
        f"you said to land {said['head'][:12]}, and this head adds {len(commits)} commit(s) inside the same work, with the Spec "
        f"and its tests as approved, so nobody is asked again: {shown}"
    )


def _approve_on_platform(branch: str, head: str, *, ask: bool, auto_merge: bool = False, decided_via: str | None = None) -> int:
    """Merge approval where a platform's gate decides: an approving review of exactly `head` on the branch's pull
    request, as the person, after their yes at the terminal (`ask`) or their answer in a dialog; with `auto_merge`
    (the person's "merge it", or their standing approval), its auto-merge too, so it merges once `aidd/gate` passes."""
    pr, why = _platform_target(branch, head)
    if pr is not None and pr.head_sha != head:
        why = f"{pr.repo}#{pr.number}'s head is {pr.head_sha[:12]}, not {head[:12]}: push {branch}, then approve"
    if pr is None or why:
        print(f"error: not approved: {why}", file=sys.stderr)
        return 1
    if ask:
        platforms.require_person(
            f"Merge approval for the head commit {head[:12]}",
            command="aidd approve merge",
            question=f"Approve {pr.repo}#{pr.number} at {head[:12]} as @{pr.login}?",
        )
    url = platforms.approve_pull_request(pr, head, platforms.merge_review_body(head, decided_via))
    print(f"Approved merging {branch} at {head[:12]}: an approving review on {url} as @{pr.login}. The gate on GitHub counts it.")
    if auto_merge:
        why = platforms.enable_auto_merge(pr)
        print(
            "Auto-merge is on: the pull request merges by itself once `aidd/gate` passes."
            if why is None
            else f"Auto-merge is not on ({why}): the pull request merges once `aidd/gate` passes and a person merges it on the platform."
        )
    return 0


def _merge_context(args, head: str):
    """The local gate's context and decision for `head`, with the evidence `aidd test` wrote here."""
    evidence = Path(getattr(args, "evidence", None) or ".aidd/evidence/evidence.json")
    arguments.base_from_spec(args)
    ctx = platforms.build_local_context(base=getattr(args, "base", None), head=head, evidence=str(evidence) if evidence.is_file() else None, run_policy=True)
    return ctx, gate.decide(ctx)


def merge_preview(args, head: str, *, reruns_tests: bool = False) -> dict:
    """What `aidd approve merge --show` prints: what a person approves (the branch, its head, what changed, the gate's
    state) and why it cannot be approved yet, before anyone confirms. `aidd land --show` (`reruns_tests`) leaves out
    the test rules, since land runs the tests again on what lands."""
    ctx, d = _merge_context(args, head)
    skip = {"merge_approval", *(("tests", "red_green") if reruns_tests else ())}
    failing = sorted({f.rule for f in d.findings if f.level == "fail" and f.rule not in skip})
    pending = sorted({f.rule for f in d.findings if f.level == "pending" and f.rule not in skip})
    # A person's Merge approval is theirs to give whatever else fails: the gate still holds the merge until the rest is
    # fixed. Only landing (`reruns_tests`) cannot go on while the gate fails.
    problems = [f"the gate fails on {', '.join(failing)} for head {head[:12]}; fix that first"] if failing and reruns_tests else []
    if problem := local_identity_problem():
        problems.append(problem)
    outside, unread = outside_shown()
    problems += [unread] if unread else []
    # `aidd land` (reruns_tests) is local-first: on a platform the pull request merges there, so there is nothing to post.
    posts_to, why = _platform_preview(_branch(), head, exact=True) if not problems and not reruns_tests else (None, None)
    if why:
        problems.append(why)
    return {
        "posts_to": posts_to,
        "branch": _branch(),
        "head": head,
        "base": ctx["base_sha"],
        "spec": str(d.record.get("spec") or ""),
        "route": str(d.record.get("route") or ""),
        "changed": git.run(["diff", "--shortstat", ctx["base_sha"], head], check=False).strip(),
        "decision": d.decision,
        "failing": failing,
        "pending": pending,
        "warnings": [plain(m, 300) for m in [*_left_branch(head), *sorted({f.message for f in d.findings if f.level == "warn"})[:5]]],
        **outside,
        "problems": problems,
    }


def _left_branch(head: str) -> list[str]:
    """What changed in the files a Spec froze that was approved on this branch and then left it (tracking.left_branch_changes)."""
    try:
        return tracking.left_branch_changes(head, config.load_file(config.CONFIG_PATH))
    except (OSError, ValueError, git.GitError):
        return []


def _branch() -> str:
    return git.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()


def revision_line(data: dict) -> str | None:
    """The Spec's latest revision as the Approver reads it (`aidd revise`): what was wrong, and the hash it reopened."""
    revisions = [r for r in data.get("revisions") or [] if isinstance(r, dict)]
    if not revisions:
        return None
    last = revisions[-1]
    return plain(f"{last.get('why')} (reopened {last.get('on')}; it was approved as {str(last.get('was'))[:12]})", 300)


def card(title: str, subtitle: str, rows: list[tuple[str, str]]) -> str:
    """A short block a person reads at a glance: the title, the subtitle, then aligned label and value rows."""
    width = max(len(k) for k, _ in rows) + 2
    lines = [title, f"  {subtitle}" if subtitle else "", *(f"  {k.ljust(width)}{v}" for k, v in rows)]
    return "\n".join(line for line in lines if line) + "\n"


def _before_spec_approval(args, data: dict, h: str, head: str) -> None:
    """What the person should see before a Spec approval: whether HEAD already holds implementation (then the approval
    proves it came late), and what changed in the frozen files since the last approval of another hash, led by a changed
    test, as the preview's warnings are."""
    since = tracking.changed_since(args.spec, data, h, head)
    if tests := tracking.tests_changed(args.spec, data, since, head):
        print(f"{plain(tests, 300)}\n", flush=True)
    if late := _implementation_at(args, data, head):
        print(f"warning: {plain(late, 300)}\n", file=sys.stderr, flush=True)
    if since:
        print(workitems.since_text(since, f"git diff {since['commit'][:12]} {head[:12]} -- {args.spec}"))


def _implementation_at(args, data: dict, head: str) -> str | None:
    """Why an approval on `head` would prove Spec approval came after implementation began, as the gate decides it
    (spec_approval.after_implementation), or None. The Spec, its frozen files, the components' threat models it links,
    and the plan's other work items are not implementation."""
    base_sha = arguments.base_sha(args, head)
    if not base_sha:
        return None
    cfg = arguments.config_or_none_quiet()
    allowed = [args.spec, *workitems.frozen_paths(data), *workitems.plan_paths(cfg.specs_dir if cfg else "specs")]
    allowed += workitems.threat_models(data, cfg.docs_dir if cfg else "docs")
    changed = [p for p in git.run(["diff", "--name-only", "-z", base_sha, head]).split("\0") if p]
    beyond = [p for p in changed if not globs.match_any(allowed, p)]
    if not beyond:
        return None
    return (
        f"{head[:12]} already holds implementation ({', '.join(beyond[:3])}{f' and {len(beyond) - 3} more' if len(beyond) > 3 else ''}), "
        "so this approval records that Spec approval came after implementation began. Approve on the commit that holds only the Spec and its tests"
    )


def _spec_preview(args, data: dict, text: str, h: str, head: str) -> dict:
    """What `aidd approve spec --show` prints: what a person approves, and why it could not be recorded, before anyone confirms."""
    ids = workitems.acceptance_ids(text)
    problems = [
        f"it is not ready: {e}; finish it (`aidd validate {args.spec}`) before anyone approves it" for e in workitems.spec_approval_problems(text, args.spec)
    ]
    if args.ref == "HEAD" and git.run(["status", "--porcelain", "--", args.spec, *workitems.frozen_files(data)], check=False).strip():
        problems.append("the Spec or its tests have uncommitted changes; commit them first")
    if head == arguments.base_sha(args, head):
        problems.append(f"{head[:12]} is the base branch's own commit; commit the Spec and its tests on this branch first")
    posts_to, why = _platform_preview(_ref_branch(args), head) if not problems else (None, None)
    if why:
        problems.append(why)
    if problem := local_identity_problem():
        problems.append(problem)
    outside, unread = outside_shown()
    problems += [unread] if unread else []
    since = tracking.changed_since(args.spec, data, h, head)
    return {
        "id": plain(data.get("id"), 40),
        "title": plain(data.get("title")),
        "spec": args.spec,
        "acceptance": [plain(i, 20) for i in ids],
        "commit": head,
        "ref": args.ref,
        "since": since,
        "risk": risk_line(data),
        "revised": revision_line(data),
        "posts_to": posts_to,
        "warnings": [plain(w, 300) for w in [tracking.tests_changed(args.spec, data, since, head), _implementation_at(args, data, head)] if w],
        **outside,
        "problems": problems,
    }


def plain(text: object, limit: int = 200) -> str:
    """Agent-written text as an approval surface may show it (documents.one_line). A Spec's title, rollback, or changed
    lines could otherwise fake a hash or a second question in the card or the dialog a person reads before saying yes."""
    return documents.one_line(text, limit)


def risk_line(data: dict) -> str:
    """What a person weighs before saying go, in one line: the route, the declared risk dimensions, whether a revert
    restores the prior state, and the rollback."""
    risk = data.get("risk") or {}
    parts = [f"route {plain(data.get('route') or '?', 20)}"]
    if dims := risk.get("dimensions"):
        parts.append("touches " + plain(", ".join(map(str, dims)), 120))
    if risk.get("reversible") is False:
        parts.append("NOT reversible: a revert does not restore the prior state")
    rollback = str(data.get("rollback") or "").strip()
    if rollback and "TODO" not in rollback:
        parts.append(f"rollback: {plain(rollback, 160)}")
    return "; ".join(parts)


def _platform_preview(branch: str, head: str, *, exact: bool = False) -> tuple[dict | None, str | None]:
    """Where a platform repository's approval would go, for a dialog to show (`posts_to`), or why it cannot; (None,
    None) where this machine's gate decides. `exact`: a Merge approval names the pull request's head itself."""
    if gate.platform_of(".") != "preflight":
        return None, None
    pr, why = _platform_target(branch, head)
    if pr is not None and exact and pr.head_sha != head:
        why = f"{pr.repo}#{pr.number}'s head is {pr.head_sha[:12]}, not {head[:12]}: push {branch}, then approve"
    if pr is None or why:
        return None, why
    return {"repo": pr.repo, "number": pr.number, "url": pr.url, "as": pr.login}, None


def _before_merge_approval(args, head: str) -> bool:
    """What the person reads before a Merge approval: the approval summary, the diffstat, and the gate's state, with what still
    fails besides their approval. Their decision is theirs whatever fails: the gate holds the merge until it is fixed."""
    from aidd import views

    ctx, d = _merge_context(args, head)
    for line in _left_branch(head):
        print(f"warning: {plain(line, 300)}", flush=True)
    print(views.merge_summary(ctx, cwd=".").strip())
    print(git.run(["diff", "--stat", ctx["base_sha"], head], check=False).rstrip())
    print(gate.decision_text(d))
    failing = sorted({f.rule for f in d.findings if f.level == "fail" and f.rule != "merge_approval"})
    if failing:
        print(f"note: the gate still fails on {', '.join(failing)} for head {head[:12]}: your approval is recorded, and the merge waits for the fix")
    return True
