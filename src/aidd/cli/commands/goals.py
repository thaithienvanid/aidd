"""The goal commands: `goal open` (the goal branch of a small goal that ships batched), integrate (a Spec's branch, or
a fast-lane fix, into its goal branch; `--undo` takes a Spec out again), and sync (the goal into a Spec's branch, or the
default branch into the goal).

A goal branch is the team's integration branch. Integrate is the team's own step: no person is asked, because nothing
it lands reaches the default branch unchecked. The release, the goal into the default branch, is a person's Merge
approval, and the goal gate proves each Spec in it again there.
"""

from __future__ import annotations

import sys

from aidd import gate, platforms, workitems
from aidd.cli import arguments, local_events
from aidd.cli.commands import operate
from aidd.kernel import documents, git

# What the gate may still wait for when a Spec integrates: the person's decisions at release, never anything else.
RELEASE_DECISIONS = ("merge_approval", "specialist_approval")


def _branch() -> str:
    return git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()


def _clean() -> bool:
    return not git.run(["status", "--porcelain", "--untracked-files=no"]).strip()


def _own_specs(cfg, goal: str) -> list[tuple[str, dict]]:
    """The Specs this branch adds or changes since it left `goal`: what a sync brought in from siblings is the goal's."""
    try:
        fork = git.merge_base(git.rev_parse(f"refs/heads/{goal}"), git.rev_parse("HEAD"))
    except git.GitError:
        return []
    changed = [p for p in git.run(["diff", "--name-only", "-z", fork, "HEAD", "--", cfg.specs_dir], check=False).split("\0") if p.endswith(".md")]
    out = []
    for path in changed:
        try:
            data = documents.split_front_matter(git.show("HEAD", path) or "", path)[0]
        except documents.DocumentError:
            continue
        if data.get("kind") == "spec":
            out.append((path, data))
    return out


def _goal_spec(specs: list[tuple[str, dict]], goal: str) -> tuple[str, dict] | None:
    """The one Spec among `specs` that ships into `goal`, or None when there is not exactly one."""
    found = [(r, d) for r, d in specs if str(d.get("base") or "") == goal]
    return found[0] if len(found) == 1 else None


def waits_only_for_release(d) -> bool:
    """Whether the gate passes but for the person's decisions at release: each finding that is not a warning is a
    pending Merge approval or specialist approval."""
    return d.decision == "pass" or all(f.rule in RELEASE_DECISIONS and f.level == "pending" for f in d.findings if f.level != "warn")


def _checks_on_head(sid: str, head: str) -> list[str]:
    """What autopilot's journal says against this head: a failed Verify or Review, or neither run on it. Empty when the
    journal holds no step for the Spec (the loop ran without autopilot, so its roles reported in the session)."""
    from aidd import autopilot

    try:
        mine = [e for e in autopilot.read_journal(".") if e.get("spec") == sid]
    except (OSError, ValueError):
        return []
    if not mine:
        return []
    problems = []
    for code, role in (("spec.verify", "the verifier"), ("spec.review", "the reviewer")):
        last = next((e for e in reversed(mine) if e.get("code") == code), None)
        if last is None or last.get("head") != head:
            problems.append(f"{role} has not reported on {head[:12]}: run {code.split('.')[1]} on this head first")
        elif last.get("result") != "ok":
            problems.append(f"{role} reported `{last.get('result')}` on {head[:12]}: fix it, then {code.split('.')[1]} again")
    return problems


def _integration(cfg, named: str | None) -> tuple[str, str, tuple[str, dict] | None] | str:
    """(this branch, its goal, its one Spec that ships into the goal, or None for a fast-lane change), or why integrate
    cannot run here. `named` is `--goal`: a fast-lane fix, with no Spec, names the goal it was cut from."""
    branch = _branch()
    goal = named or workitems.goal_of(".", cfg)
    if not branch or branch.startswith(workitems.GOAL_PREFIX) or not goal:
        return (
            "integrate runs on a Spec's branch cut from its goal branch: the Spec's `base` names the goal "
            f"(`base: goal/<name>`) and the branch holds the goal's commits. A fast-lane fix names it: `--goal goal/<name>`. "
            f"This is {branch or 'a detached HEAD'}"
        )
    if workitems.is_explore(branch):
        return f"{branch} is an explore branch: nothing integrates from it as it is. {operate.KEEP_EXPLORE_WORK}"
    if named and not (named.startswith(workitems.GOAL_PREFIX) and workitems.builds_on(".", named)):
        return f"--goal {named}: name the goal branch this branch was cut from"
    if git.ok(["merge-base", "--is-ancestor", "HEAD", f"refs/heads/{goal}"]):
        return branch, goal, _goal_spec(workitems.active_specs(".", cfg), goal)  # already in: integrate says so
    specs = _own_specs(cfg, goal)
    found = _goal_spec(specs, goal)
    if found is None and (specs or not named):
        return f"integrate lands one Spec: this branch must carry exactly one active Spec whose `base` is {goal}, or none (a fast-lane fix)"
    return branch, goal, found


def _catch_up(goal: str) -> str | None:
    """Bring the local goal branch up to its upstream when the upstream is ahead (another machine integrated): why not,
    or None. A goal that went two ways is a person's to bring together."""
    upstream = platforms.fetch_upstream(goal)
    if upstream is None or git.ok(["merge-base", "--is-ancestor", upstream, f"refs/heads/{goal}"]):
        return None
    if not git.ok(["merge-base", "--is-ancestor", f"refs/heads/{goal}", upstream]):
        return f"{goal} and its upstream {upstream.removeprefix('refs/remotes/')} went two ways; a person merges them"
    platforms.move_branch(goal, git.rev_parse(upstream), git.rev_parse(f"refs/heads/{goal}"))
    print(f"{goal} caught up with its upstream at {git.rev_parse(upstream)[:12]}")
    return None


def _tested_merge(args, goal: str, goal_tip: str, head: str, message: str) -> tuple[tuple[str, str], dict] | None:
    """The merge of `head` into the goal tip, as a commit on no branch, and the evidence of its tests; None, with the
    reason printed, when the declaration fails, the merge conflicts, or the tests cannot run."""
    try:
        early = gate.decide(platforms.build_local_context(base=goal, head=head, run_policy=False))
        declared = [f for f in early.findings if f.level == "fail" and f.rule in operate.DECLARED_RULES]
        if declared:
            for f in declared:
                print(f"  [FAIL] {f.rule}: {f.message}" + (f"\n        fix: {f.fix}" if f.fix else ""))
            print("Not integrated: the change's declaration fails, so no test ran", file=sys.stderr)
            return None
        merged = platforms.merged_commit(goal_tip, head, message=message)
        ev, notes = platforms.run_in_worktree(merged[0], lambda tmp: gate.run_tests(repo=tmp, base=goal_tip, out_dir=args.out, pass_env=args.pass_env or ()))
    except (RuntimeError, git.GitError) as exc:
        print(f"Not integrated: {exc}. `aidd sync` merges the goal into this branch first", file=sys.stderr)
        return None
    for n in notes:
        print(f"note: {n}")
    return merged, ev


def cmd_integrate(args) -> int:
    """Land this Spec's branch (or a fast-lane fix) in its goal branch, as a merge commit, once its approval holds, its
    tests pass on the merged tree, and the gate against the goal waits for nothing but the release decisions. The team
    runs it. `--undo <ID>` takes an integrated Spec out of its goal again."""
    arguments.enter_repo(args, file_attrs=("out",))
    cfg = arguments.config_or_none()
    if args.undo:
        return _undo(args.undo, args.goal)
    where = _integration(cfg, args.goal) if cfg is not None else "no aidd config: `aidd init` first"
    if isinstance(where, str):
        print(f"error: {where}", file=sys.stderr)
        return 2
    branch, goal, found = where
    sid = str(found[1].get("id")) if found else None
    if not _clean():
        print("error: the working tree has uncommitted changes; commit them first", file=sys.stderr)
        return 1
    try:
        if why := _catch_up(goal):
            print(f"Not integrated: {why}", file=sys.stderr)
            return 1
    except (RuntimeError, git.GitError) as exc:
        print(f"Not integrated: {exc}", file=sys.stderr)
        return 1
    head, goal_tip = git.rev_parse("HEAD"), git.rev_parse(f"refs/heads/{goal}")
    if git.ok(["merge-base", "--is-ancestor", head, goal_tip]):
        undone = bool(sid) and sid not in workitems.integrated(".", goal)
        print(f"{sid or branch} at {head[:12]} is already in {goal}" + (" and was taken out with --undo: a person brings it back" if undone else ""))
        if pushed := platforms.push_branch(goal):
            print(pushed)
        return 0
    if sid and (problems := _checks_on_head(sid, head)):
        print(f"Not integrated: {'; '.join(problems)}", file=sys.stderr)
        return 1
    tested = _tested_merge(args, goal, goal_tip, head, _integrate_message(found, branch, head, goal_tip))
    if tested is None:
        return 1
    merged, ev = tested
    ctx = platforms.build_local_context(base=goal, head=head, run_policy=True)
    if git.rev_parse("HEAD") != head or git.rev_parse(f"refs/heads/{goal}") != goal_tip or ev["head_sha"] != merged[0]:
        print(f"Not integrated: {branch} or {goal} moved while the tests ran; run `aidd integrate` again", file=sys.stderr)
        return 1
    ctx["merge_group"] = {"sha": merged[0], "base_sha": goal_tip, "stacked": False, "tree": merged[1], "merged_tree": merged[1]}
    ctx["evidence"] = ev
    d = gate.decide(ctx)
    try:
        if not waits_only_for_release(d):
            print(gate.decision_text(d))
            print(f"Not integrated: the gate against {goal} waits for more than the release decisions (above)", file=sys.stderr)
            return 1
        platforms.move_branch(goal, merged[0], goal_tip)
        print(f"integrated {sid or 'the fix'} ({branch} at {head[:12]}) into {goal} at {merged[0][:12]}")
        if pushed := platforms.push_branch(goal):
            print(pushed)
        return 0
    except (RuntimeError, git.GitError) as exc:
        print(f"Not integrated: {exc}", file=sys.stderr)
        return 1
    finally:
        local_events.record(d, change=branch)


def _integrate_message(found: tuple[str, dict] | None, branch: str, head: str, goal_tip: str) -> str:
    """The merge commit's message: `<type>: <title> (<ID>)` with the Aidd-Integrate trailer for a Spec; for a
    fast-lane fix, its newest commit's subject."""
    if found is None:  # fixed words: a commit's own text never reaches the goal's record
        return f"Integrate the fast-lane change {branch}"
    data, sid = found[1], str(found[1].get("id"))
    kind = f"{data['type']}: " if data.get("type") in arguments.TYPES else ""
    return f"{kind}{data.get('title') or 'Integrate'} ({sid})\n\n{workitems.integrate_trailer(sid)}\n"


def _undo(sid: str, named: str | None) -> int:
    """Take an integrated Spec out of its goal: one commit on the goal that reverts its integration, with the Aidd-Undo
    trailer. Its tests are not run here: nothing reaches users before the release, which judges the goal again."""
    goals = [named] if named else workitems.goal_branches(".")
    hits = [(g, workitems.integrations(".", g)[sid]) for g in goals if sid in workitems.integrations(".", g)]
    if len(hits) != 1:
        print(
            f"error: {sid} is integrated in {len(hits)} goal branches here; name one with --goal" if hits else f"error: no goal branch holds {sid}",
            file=sys.stderr,
        )
        return 2
    goal, (merge, _) = hits[0]
    tip = git.rev_parse(f"refs/heads/{goal}")
    p = git._git(["merge-tree", "--write-tree", "--no-messages", f"--merge-base={merge}", tip, f"{merge}^1"], ".")
    tree = p.stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
    if p.returncode != 0 or not tree:
        print(f"Not undone: later work in {goal} builds on {sid}'s changes, so its revert conflicts; a person takes it out", file=sys.stderr)
        return 1
    message = f"Take {sid} out of {goal}\n\nReverts {merge[:12]}.\n\n{workitems.undo_trailer(sid)}\n"
    new = git.run(["commit-tree", tree, "-p", tip, "-m", message]).strip()
    try:
        platforms.move_branch(goal, new, tip)
    except (RuntimeError, git.GitError) as exc:
        print(f"Not undone: {exc}", file=sys.stderr)
        return 1
    print(f"took {sid} out of {goal} at {new[:12]}; the release judges the goal without it")
    if pushed := platforms.push_branch(goal):
        print(pushed)
    return 0


def _goal_list(cfg, as_json: bool) -> int:
    """`aidd goal list`: the shape of the work for a person: each big goal and small goal with where each of their
    decisions stands (tracking.small_goal_ladders), each goal branch, and the trunk-based flow."""
    import json as jsonlib
    from pathlib import Path

    from aidd import tracking

    steps, specs = tracking.open_work(Path("."))
    goals = tracking.goals(".", cfg, steps)
    branches = workitems.work_branches(".")
    warnings = workitems.flow_warnings(branches, cfg)
    shown = {
        "schema_version": arguments.JSON_SCHEMA_VERSION,
        "goals": goals,
        "flow": {"branches": branches, "warnings": warnings},
    } | tracking.small_goal_ladders(".", cfg, steps, specs, goals)
    if as_json:
        print(jsonlib.dumps(shown, indent=2))
        return 0
    for g in goals:
        state = "ready to release" if g["release_ready"] else f"waits for {', '.join(g['waiting']) or 'its first Spec'}"
        print(f"{g['branch']}: {len(g['integrated'])} integrated, {state}; {g['age_days']} days old, {g['behind']} behind")
    print(
        f"{len(branches)} other branch(es) with unmerged work" + "".join(f"\n  {b['branch']}: {b['age_days']} days old, {b['behind']} behind" for b in branches)
    )
    for w in [w for g in goals for w in g["warnings"]] + warnings:
        print(f"warning: {w}")
    return 0


def cmd_goal(args) -> int:
    """`aidd goal open <EPIC>`: the goal branch of a small goal that ships batched, cut from the default branch once
    the plan holding the Epic is there (the person agreed to it). Nothing changes when the branch exists. `aidd goal
    list`: each goal and the trunk-based flow."""
    arguments.enter_repo(args)
    cfg = arguments.config_or_none()
    if args.action == "list":
        return _goal_list(cfg, args.json)
    if not args.epic:
        print("error: name the Epic: aidd goal open EPIC-3", file=sys.stderr)
        return 2
    specs_dir = cfg.specs_dir if cfg else "specs"
    base = git.default_base(".")
    text = git.show(base, f"{specs_dir}/{args.epic}.md")
    try:
        epic = documents.split_front_matter(text, f"{specs_dir}/{args.epic}.md")[0] if text else {}
    except documents.DocumentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if epic.get("kind") != "epic":
        print(f"error: {args.epic} is no Epic on {base}: a goal branch opens once the plan that holds it is merged (the person agreed to it)", file=sys.stderr)
        return 2
    if workitems.ships(epic) != "batched":
        print(f"error: {args.epic} ships {workitems.ships(epic)}: its Specs merge to the default branch, with no goal branch", file=sys.stderr)
        return 2
    branch = workitems.goal_branch(args.epic)
    if git.ok(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"]):
        print(f"{branch} is open at {git.rev_parse(branch)[:12]}")
        return 0
    # Its first commit, empty, says what the goal is for: work cut from the goal then builds on it (workitems.builds_on),
    # and the goal's age counts from it.
    message = f"Open {branch} for {args.epic}: {epic.get('title') or ''}".rstrip(": ") + f"\n\n{workitems.GOAL_TRAILER}: {branch}\n"
    tip = git.run(["commit-tree", f"{base}^{{tree}}", "-p", git.rev_parse(base), "-m", message]).strip()
    git.run(["branch", branch, tip])
    print(f"opened {branch} at {tip[:12]}. Each Spec: `git switch -c spec/<ID> {branch}`, then `aidd new spec <ID> --parent {args.epic}`")
    if published := platforms.publish_branch(branch):
        print(published)
    return 0


def cmd_sync(args) -> int:
    """Merge newer work in, never rebasing: on a Spec's branch, its goal branch; on a goal branch, the default branch.
    A conflict stops it with nothing merged, and lists the files."""
    arguments.enter_repo(args)
    cfg = arguments.config_or_none()
    branch = _branch()
    if branch.startswith(workitems.GOAL_PREFIX):
        source = args.source or git.default_base(".")
    else:
        # A Spec's branch cut from its goal takes the goal; any other branch takes the default branch, daily.
        source = args.source or (workitems.goal_of(".", cfg) if cfg else None) or git.default_base(".")
    if not branch or not source:
        print("error: sync runs on a branch: switch to one first; name what to merge in with --from", file=sys.stderr)
        return 2
    if not _clean():
        print("error: the working tree has uncommitted changes; commit them first", file=sys.stderr)
        return 1
    if branch.startswith(workitems.GOAL_PREFIX) and (why := _catch_up(branch)):
        print(f"Not synced: {why}", file=sys.stderr)
        return 1
    try:
        tip = git.rev_parse(source)
    except git.GitError:
        print(f"error: no branch or commit {source}", file=sys.stderr)
        return 2
    if branch.startswith(workitems.GOAL_PREFIX) and not git.ok(["merge-base", "--is-ancestor", tip, git.default_base(".")]):
        # Anything else reaches a goal only through `aidd integrate`, which checks it first.
        print(
            f"error: on a goal branch, sync merges in only what the default branch holds; {source} holds more. A Spec lands with `aidd integrate`",
            file=sys.stderr,
        )
        return 2
    if git.ok(["merge-base", "--is-ancestor", tip, "HEAD"]):
        print(f"{branch} already holds {source} at {tip[:12]}")
        return 0
    p = git._git(["merge", "--no-ff", "--no-edit", "-m", f"Sync {source} into {branch}", tip], ".")
    if p.returncode != 0:
        conflicts = [c for c in git.run(["diff", "--name-only", "--diff-filter=U", "-z"], check=False).split("\0") if c]
        git.run(["merge", "--abort"], check=False)
        if not conflicts:
            print(
                f"Not synced: git could not merge {source} into {branch}, so nothing was merged: {p.stderr.decode('utf-8', errors='replace').strip()}",
                file=sys.stderr,
            )
            return 1
        listed = ", ".join(conflicts[:20]) + (f" and {len(conflicts) - 20} more" if len(conflicts) > 20 else "")
        print(
            f"Not synced: {source} conflicts with {branch} (files: {listed}); nothing was merged.\n"
            f"Needs: the owner of each file's scope resolves it with `git merge {source}` on {branch}"
            + (", or a person does it on the goal branch, where only aidd moves it" if branch.startswith(workitems.GOAL_PREFIX) else ""),
            file=sys.stderr,
        )
        return 1
    print(f"synced {source} at {tip[:12]} into {branch} at {git.rev_parse('HEAD')[:12]}")
    return 0
