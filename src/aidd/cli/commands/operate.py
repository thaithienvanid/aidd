"""The Operate commands: land, observe, and release-notes."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from aidd import config, gate, platforms, workitems
from aidd.cli import arguments, local_events
from aidd.cli.commands import decide
from aidd.kernel import documents, git


def cmd_release_notes(args) -> int:
    """Release notes from the Specs landed since a tag or date, grouped by Keep a Changelog, for users or developers."""
    from aidd import tracking

    arguments.enter_repo(args)
    if arguments.config_or_none() is None:
        raise ValueError(f"no {config.CONFIG_PATH}: `aidd init` first")
    d = tracking.release_notes(Path("."), args.since, audience=args.audience)
    print(json.dumps(d, indent=2) if args.json else tracking.release_notes_markdown(d), end="\n" if args.json else "")
    return 0


# What the change declares, which `aidd land` checks before it runs any test: a failure here stays a failure whatever the
# tests say, so the person learns it in seconds rather than after the suite.
DECLARED_RULES = ("config", "change_request", "spec", "confidence", "route", "scope", "changed_lines", "standard_change")


# What to do with an explore branch's work: the one step that brings it into the loop.
KEEP_EXPLORE_WORK = "To keep the work, rename the branch (`git branch -m <name>`): the gate then checks it as it checks any change"


def cmd_land(args) -> int:
    """Merge a branch that passes the gate into the base branch on this machine: Land, onto the local trunk.

    The declared inputs are checked first; then the tests run on exactly what will land (the head, or, when the base
    branch moved, the head merged into the base tip, in a temporary worktree); then the person confirms once, with one
    code, which also records their Merge approval when that is all the gate still waits for. Nobody is asked when the
    person already said so: a standing approval that covers the route, or their typed "land it" for this head."""

    arguments.enter_repo(args, file_attrs=("out", "body_file"))
    arguments.base_from_spec(args)  # a goal's Spec lands in its goal branch
    branch = git.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    base = args.base or git.default_base(".").removeprefix("origin/")
    if branch in (base, "HEAD"):
        print(f"error: switch to the branch to land; this is {branch}", file=sys.stderr)
        return 2
    if workitems.merges_nothing(branch):
        print(f"error: {branch} is an explore branch: nothing merges from it as it is. {KEEP_EXPLORE_WORK}", file=sys.stderr)
        return 1
    if git.run(["status", "--porcelain", "--untracked-files=no"]).strip():
        print("error: the working tree has uncommitted changes; commit or stash them first", file=sys.stderr)
        return 1
    head = git.rev_parse("HEAD")
    # Where a platform's gate decides, the pull request merges there: a local land would go around that gate.
    elsewhere = (
        f"this repository's gate runs on its platform, so {branch} merges there once `aidd/gate` passes. Type `merge it` at your "
        "coding agent's prompt: aidd posts your Merge approval on the pull request and turns on its auto-merge (or run "
        "`aidd approve merge`, then merge the pull request)"
        if gate.platform_of(".") == "preflight"
        else None
    )
    if args.show:
        shown = decide.merge_preview(args, head, reruns_tests=True) | {"base_branch": base, "squash": bool(args.squash)}
        if elsewhere:
            shown["problems"] = [elsewhere, *shown["problems"]]
            shown["merges_on_platform"] = True
        print(json.dumps(shown, indent=2))
        return 0
    if elsewhere:
        print(f"Not landed: {elsewhere}", file=sys.stderr)
        return 1
    if args.confirmed is not None and args.confirmed != head:
        print(f"error: you confirmed landing {branch} at {args.confirmed[:12]}, but its head is now {head[:12]}. Nothing was landed", file=sys.stderr)
        return 1
    if args.confirmed is not None and (problem := decide.confirmation_problem(args.decided_via)):
        print(f"error: not landed: {problem}", file=sys.stderr)
        return 2 if not decide.DECIDED_WHERE.fullmatch(args.decided_via) else 1
    body = arguments.body(args) if args.body_file else None
    early = gate.decide(platforms.build_local_context(base=base, head=head, body=body, run_policy=False))
    declared = [f for f in early.findings if f.level == "fail" and f.rule in DECLARED_RULES]
    if declared:
        for f in declared:
            print(f"  [FAIL] {f.code or f.rule}: {f.message}" + (f"\n        fix: {f.fix}" if f.fix else ""))
        print("Not landed: the change's declaration fails, so no test ran; fix it and run `aidd land` again", file=sys.stderr)
        return 1
    base_tip = git.rev_parse(base)
    merged: tuple[str, str] | None = None  # (the merge commit tested, its tree) when the base moved
    try:
        if git.ok(["merge-base", "--is-ancestor", base_tip, head]):
            # The tests run here, on this exact head: evidence on disk is a file an agent could have written.
            ev, notes = gate.run_tests(base=base, body=body, out_dir=args.out, pass_env=args.pass_env or ())
        else:
            merged = platforms.merged_commit(base_tip, head, message=args.message or _land_message(early.record, branch, head))
            print(f"{base} moved to {base_tip[:12]}: testing {head[:12]} merged into it ({merged[0][:12]}), which is what will land")
            ev, notes = platforms.run_in_worktree(
                merged[0], lambda tmp: gate.run_tests(repo=tmp, base=base_tip, body=body, out_dir=args.out, pass_env=args.pass_env or ())
            )
    except (RuntimeError, git.GitError) as exc:
        print(f"Not landed: {exc}", file=sys.stderr)
        return 1
    for n in notes:
        print(f"note: {n}")
    ctx = platforms.build_local_context(base=base, head=head, body=body, run_policy=True)
    if git.rev_parse("HEAD") != head or git.rev_parse(base) != base_tip or ev["head_sha"] != (merged[0] if merged else head):
        print(f"Not landed: {branch} or {base} moved while the tests ran; run `aidd land` again", file=sys.stderr)
        return 1
    if merged:
        # The tested commit is the head merged into the base tip: the gate checks it as it checks a merge-queue entry.
        ctx["merge_queue"] = {"sha": merged[0], "base_sha": base_tip, "stacked": False, "tree": merged[1], "merged_tree": merged[1]}
    ctx["evidence"] = ev
    d = gate.decide(ctx)
    try:
        approve = d.decision != "pass" and _only_merge_approval_missing(d) and gate.decide(_with_own_approval(ctx)).decision == "pass"
        if d.decision != "pass" and not approve:
            state = "fails" if d.decision == "fail" else "is pending"
            print(f"Not landed: the local gate {state} (details below)", file=sys.stderr, flush=True)
            print(gate.decision_text(d))
            if _only_merge_approval_missing(d) and (problem := decide.local_identity_problem()):
                print(f"note: {problem}")
            return 1
        if approve:
            # The one thing the gate waits for is the Merge approval this run records: never print it as a step for anyone.
            print(f"the gate passes on {head[:12]} but for its Merge approval, which landing records")
        else:
            print(gate.decision_text(d))
        # What lands, for the person to read before the code: the diffstat against the base.
        print(git.run(["diff", "--stat", ctx["base_sha"], head], check=False).rstrip())
        what = f"Land {branch} at {head[:12]} into {base}" + (" as one squashed commit" if args.squash else "")
        # Nobody is asked when the person already said so: their standing approval covers this route, or they typed
        # "land it" for exactly this head (aidd's prompt hook recorded it).
        asks = args.confirmed is None
        standing = decide.standing_for(str(d.record.get("route")), merge=True) if asks else None
        said = workitems.land_decision(d.config, ".", head) if asks and standing is None else None
        if standing is not None:
            print(f"your standing approval of {standing['since'][:16]} covers this {d.record.get('route')} change, so nobody is asked")
        elif said is not None:
            print(decide.land_it_note(said, head))
        try:
            if args.confirmed is None and standing is None and not said:
                platforms.require_person(
                    f"{what}, recording the Merge approval of {head[:12]}" if approve else what,
                    command="aidd land" + (" --squash" if args.squash else ""),
                    question=f"{what}{', with your Merge approval' if approve else ''}?",
                )
            if approve:
                line = workitems.approve_merge_line(head, branch=branch)
                where = args.decided_via if args.confirmed is not None else f"standing:{standing['sha'][:12]}" if standing else decide.land_it_decided_via(said)
                workitems.record_local_approval(line if where is None else workitems.decided_via(line, where))
                reviews, comments, notes = workitems.load_local_approvals(
                    ".",
                    require_signed=bool(d.config and d.config.gates.get("local_approvals") == "signed"),
                    signers=workitems.base_signers(d.config, base_tip),
                    signers_file=workitems.signers_path(d.config),
                )
                ctx.update(reviews=platforms.this_branchs_approvals(".", reviews, base_tip, head), comments=comments, notes=notes)
                d = gate.decide(ctx)
                if d.decision != "pass":
                    print(gate.decision_text(d))
                    print("Not landed: the Merge approval was recorded, but the gate still does not pass", file=sys.stderr)
                    return 1
            message = args.message or _land_message(ctx, branch, head)
            ran: list[str] = []
            new = platforms.land_locally(branch, base, squash=args.squash, message=message, head=head, merged=merged, base_tip=base_tip, notes=ran)
            for n in ran:
                print(f"note: {n}")
        except (platforms.NotAPerson, RuntimeError, git.GitError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"landed {branch} at {head[:12]} into {base} at {new[:12]}" + (" (the tested merge with the moved base)" if merged else ""))
        return 0
    finally:
        # The last decision this run made after the tests, once; the early check of the declaration is no gate run.
        local_events.record(d, change=branch)


def _only_merge_approval_missing(d) -> bool:
    """Whether the gate waits for nothing but Merge approval: every finding that is not a warning is merge_approval's."""
    blocking = [f for f in d.findings if f.level != "warn"]
    return bool(blocking) and all(f.rule == "merge_approval" and f.level == "pending" for f in blocking)


def _with_own_approval(ctx: dict) -> dict:
    """The context as it would be once the person running `aidd land` approves the head: would their approval be enough?"""

    email = git.config_value("user.email")
    review = {
        "user": f"email:{email}" if email else "local",
        "state": "approved",
        "commit_sha": ctx["head_sha"],
        "submitted_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "verified": workitems.is_signing_configured("."),
    }
    return {**ctx, "reviews": [*ctx["reviews"], review]}


def _land_message(ctx_or_record: dict, branch: str, head: str | None = None) -> str:
    """The commit subject a land writes, in Conventional Commits form: `<type>: <title> (<ID>)` when the branch carries
    one Spec, `<type>: <goal> (<IDs>)` for a goal's Specs (feat when any of them is one), else the newest commit's
    subject that is not a Change Request block commit (commits are newest first)."""
    ctx = ctx_or_record
    body = (ctx.get("change") or {}).get("body") if isinstance(ctx.get("change"), dict) else None
    block = (workitems.parse_change_block(body or "")[0] or {}) if body is not None else {}
    spec = ctx.get("spec") if body is None else block.get("spec")
    head = head or ctx.get("head_sha")
    members = [s for s in ctx.get("specs") or [] if isinstance(s, dict)]
    goal = [str(s.get("spec_id") or s.get("spec")) for s in members]
    paths = [str(s["spec"]) for s in members if s.get("spec")] or (list(workitems.change_specs(block)) if head and "specs" in block else [])
    goal = goal or ([_spec_id(head, p) for p in paths] if head else [])
    if goal:
        types = [t for t in (_spec_field(head, p, "type") for p in paths) if t] if head else []
        kind = "feat" if "feat" in types else (types[0] if types else "feat")
        return f"{kind}: {branch.removeprefix(workitems.GOAL_PREFIX)} ({', '.join(goal)})"
    text = git.show(head, spec) if spec and head else None
    if text:
        try:
            data, _ = documents.split_front_matter(text, str(spec))
        except documents.DocumentError:
            data = {}
        if data.get("title"):
            kind = f"{data['type']}: " if data.get("type") in arguments.TYPES else ""
            return f"{kind}{data['title']} ({data.get('id', branch)})"
    commits = ctx.get("commits")
    if commits is None and head:
        base_sha = ctx.get("base_sha")
        commits = git.commits(base_sha, head) if base_sha else []
    plain = [c for c in commits or [] if c.get("message", "").strip() and workitems.parse_change_block(c["message"]) == (None, [])]
    subject = next((c["message"].splitlines()[0] for c in plain[:1]), "")
    return subject or f"Land {branch}"


def _spec_field(head: str, path: str, key: str) -> str | None:
    """One front-matter field of the Spec at `path` in `head`, or None when it has none there."""
    try:
        value = documents.split_front_matter(git.show(head, path) or "", path)[0].get(key)
    except documents.DocumentError:
        return None
    return str(value) if value else None


def _spec_id(head: str, path: str) -> str:
    """The id of the Spec at `path` in `head`, or the path when it has none there."""
    try:
        return str(documents.split_front_matter(git.show(head, path) or "", path)[0].get("id") or path)
    except documents.DocumentError:
        return path


def conventional_type(subjects: list[str]) -> str | None:
    """The change type the newest Conventional Commit subject names (`fix(cart)!: ...` is fix), when it is one aidd knows."""
    return next(iter(workitems.commit_types(subjects, arguments.TYPES)), None)


def cmd_observe(args) -> int:
    """Run a Spec's observe command once, or poll it for the window (--window); --write records outcome.observe_result.
    Never rolls back. With --band METRIC, judge a metric series against its control band instead (`_observe_band`)."""
    if args.band:
        if args.window is not None:
            raise ValueError("--window polls a Spec's observe command; with --band, --baseline sets how many values make the baseline")
        return _observe_band(args, metric=args.band, series_arg=args.target, baseline=args.baseline)
    if args.baseline is not None or args.json:
        raise ValueError("--baseline and --json judge a metric: use them with --band METRIC")
    if args.write not in (None, "auto"):
        raise ValueError(f"--write {args.write}: a Spec id names the draft Spec a band breach writes; use it with --band METRIC")
    args.spec = args.target
    arguments.enter_repo(args, "spec")
    args.spec = arguments.spec_by_id(args.spec, None)
    path = Path(args.spec)
    text = path.read_text(encoding="utf-8")
    data, _ = documents.split_front_matter(text, args.spec)
    obs = data.get("observe")
    if not obs:
        raise ValueError(f"{args.spec} has no observe block")
    if obs.get("not_applicable"):
        print(f"{args.spec}: nothing to watch: observe is not applicable ({obs['not_applicable']})")
        return 0
    cfg = arguments.config_or_none()
    command = obs.get("command") or (cfg.observe_command if cfg else None)
    print(f"window: {obs['window']}  rollback trigger: {obs['rollback_trigger']}")
    if obs.get("signals"):
        print(f"signals: {obs['signals']}")
    if not command:
        print("no observe command: a human watches the signals for the window")
        if args.window:
            print("error: --window polls the observe command; set observe.command in the Spec or the config", file=sys.stderr)
            return 2
        return 0
    from aidd.kernel.processes import run_bounded, scrub_credentials

    # The command may come from the Spec, which the change wrote, and runs where release credentials
    # live: it sees none of them unless the operator passes one by name.
    env = {
        **scrub_credentials(dict(os.environ), keep=args.pass_env or ()),
        "AIDD_SPEC_ID": str(data.get("id")),
        "AIDD_WINDOW": obs["window"],
        "AIDD_ROLLBACK_TRIGGER": obs["rollback_trigger"],
    }

    def check() -> int | None:
        # A timeout kills the command's whole process group, so a watcher it started cannot linger.
        code, _, _ = run_bounded(command, env=env, timeout_seconds=args.timeout, capture=False)
        return code

    if args.window:
        from aidd import tracking

        length = obs["window"] if args.window == "spec" else args.window
        window_s, every_s = tracking.window_seconds(length), tracking.window_seconds(args.every)
        print(f"watching for {length}: the observe command every {args.every}; the trigger fires after {args.consecutive} failed check(s) in a row")
        # A check that timed out counts as unhealthy (124, as timeout(1) reports it).
        w = tracking.watch_window(lambda: 124 if (c := check()) is None else c, window_s=window_s, every_s=every_s, consecutive=args.consecutive)
        result = w.result
        if result == "pass":
            print(f"observe: pass: the {length} window ended after {w.checks} check(s), {w.failures} unhealthy; the rollback trigger never fired")
        else:
            print(f"observe: ROLLBACK TRIGGER FIRED after {w.checks} check(s): {obs['rollback_trigger']}")
            print("aidd never rolls back: run your rollback now, then record it (outcome.rolled_back) and go to Learn")
    else:
        code = check()
        result = "pass" if code == 0 else "fail"
        print(f"observe: {result} (exit {code})" + ("" if result == "pass" else f"; if this persists, roll back: {obs['rollback_trigger']}"))
    if args.write:
        path.write_text(workitems.set_outcome(text, "observe_result", result), encoding="utf-8")
        print(f"wrote outcome.observe_result = {result!r} to {path}")
    return 0 if result == "pass" else 1


def _observe_band(args, *, metric: str, series_arg: str, baseline: int | None) -> int:
    """Judge a metric series against its control band; with --write, turn a breach into a draft Spec to triage."""
    from aidd import tracking

    series = Path(series_arg).resolve()
    arguments.enter_repo(args)
    band = tracking.band_from_config(arguments.config_or_none(), metric)
    # The thresholds come from `observe.bands`, the one place they are set; --baseline only sizes the window.
    band = tracking.Band(band.metric, baseline or band.window, band.diagnose_sigma, band.propose_sigma)
    reading = tracking.judge_band(tracking.load_series(series), band)
    breach = reading.tier in ("diagnose", "propose")
    written = None
    if breach and args.write:
        cfg = arguments.config_or_none()
        spec_id = args.write if args.write not in ("auto", True) else f"OBS-{metric}-{dt.date.today():%Y%m%d}".replace("_", "-")
        written = workitems.new_object(
            Path("."),
            workitems.NewObject(
                kind="spec",
                id=spec_id,
                title=f"{metric} breached its control band ({reading.tier})",
                route="normal",
                ctype="fix",
                owner_team=cfg.get("owners", "default_owner_team", default="") if cfg else "",
                specs_dir=cfg.specs_dir if cfg else "specs",
            ),
        )
        # A breach is work nobody asked for: an agent suggests it (the SRE when it may), and a person triages it.
        from aidd import knowledge

        may = knowledge.proactive_roles(cfg)
        role = "sre" if "sre" in may or not may else may[0]
        text = written.read_text(encoding="utf-8").replace("kind: spec\n", f"kind: spec\nsuggested_by: agent:{role}\n", 1)
        head, sep, body = text.partition("\n---\n")
        written.write_text(head + sep + "\n" + tracking.band_intent_text(reading, series.name, cfg.get("goal") if cfg else None) + body, encoding="utf-8")
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | reading.as_dict() | {"spec": str(written) if written else None}, indent=2))
    else:
        print(f"{reading.metric}: {reading.tier}" + (f" ({reading.note})" if reading.note else f", {reading.sigma} sigma"))
        for rule in reading.rules:
            print(f"  rule {rule}")
        if written:
            print(f"wrote {written}: a draft Spec for the service owner to triage")
    return 1 if breach else 0
