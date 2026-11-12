"""The checks of each delegable action, after the ones every action passes (check.py). Each reads git objects, the tip's
config, and the platform, and defers on the first fact it cannot prove."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from aidd import records, risk, testing, workitems
from aidd.delegation import deploys, diff_signals, local_run, platform, policy
from aidd.delegation.check import Check
from aidd.delegation.text_checks import tripwire
from aidd.kernel import documents, git, globs

# What runs `aidd test` in a workflow: the aidd action, or the command itself.
RUNS_AIDD_TEST = re.compile(r"^\s*(?:-\s*)?(?:uses:\s*['\"]?thaithienvanid/aidd@|(?:run:\s*)?(?:[\w./-]*/)?(?:uvx\s+|python3?\s+-m\s+)?aidd\s+test\b)", re.M)


def specs_dir(check: Check) -> str:
    """The folder the config holds the Specs in."""
    return local_run.specs_dir(check.cfg)


def spec_at_head(check: Check, spec_id: str) -> tuple[str, dict, str] | None:
    """The Spec with `spec_id` in the head commit: its path, its front matter, and its text. None after a defer. Only a
    file whose type is spec counts, and never a saved request, whatever its text says."""
    read = local_run.spec_by_id if check.reads_old_shape else local_run.head_spec_by_id
    found = read(check.top, check.req.head, specs_dir(check), spec_id)
    if found is None:
        check.defer("spec_not_found", f"no Spec {spec_id} in {check.req.head[:12]}")
        return None
    path, data, text, errs = found
    if errs:
        check.defer("validate_errors", "; ".join(errs)[:300])
        return None
    return path, data, text


def route_check(check: Check, spec: dict | None) -> None:
    """The change is not on the emergency route."""
    if spec and spec.get("route") == "emergency":
        check.defer("emergency_route", f"{spec.get('id')} is on the emergency route")


def spec_approve(check: Check) -> None:
    """A ready, valid Spec, every Acceptance item tested, no open decision unanswered, no Task scope in a reserved area, solo
    on major, red on base."""
    if not check.req.spec:
        check.defer("spec_not_found", "name the Spec with --spec <ID>")
        return
    found = spec_at_head(check, check.req.spec)
    if found is None:
        return
    path, spec, text = found
    check.covers["spec"] = check.req.spec
    check.spec_path, check.spec_data = path, spec
    route_check(check, spec)
    tripwire(check, {f"{path}'s body": documents.split_front_matter(text, path)[1]})
    if workitems.spec_status(spec) not in workitems.ASKS_APPROVAL:
        check.defer("spec_not_ready", f"{check.req.spec} is {workitems.spec_status(spec)}")
    if spec.get("route") == "major" and check.cfg and check.cfg.profile == "team":
        check.defer("team_review", "a major Spec's approval stays a person's under the team profile")
    if check.req.checkout:
        checked_out(check, path)
    if check.req.checkout and not check.reasons:
        errors = [e for e in workitems.validate_file(Path(check.top) / path, path) if not e.startswith("warning: ")]
        if errors:
            check.defer("validate_errors", errors[0])
    untested(check, spec, text)
    decisions_check(check, {"the Spec": text})  # an architect's open choice is settled before the Spec it shapes is approved
    assert check.rs is not None and check.cfg is not None
    parents = check.cfg.parent_paths
    scopes = [s for t in spec.get("tasks") or [] for s in t.get("scope") or []]
    hits = diff_signals.reserved_scopes(check.rs, scopes, parents) + diff_signals.reserved_paths(
        check.rs, diff_signals.changed(check.tip, check.req.head, check.top), parents
    )
    if hits:
        check.defer("reserved_path", ", ".join(hits[:5]))
    if not check.reasons:
        evidence, why = local_run.run_on_head(check.top, check.req.head, check.tip, path, old_shape=check.reads_old_shape)
        problem = local_run.red_problem(evidence, why)
        if problem:
            check.defer("not_red_on_base", problem)


def checked_out(check: Check, spec_path: str) -> None:
    """For a Spec approval, the checkout is at the head, with the Spec as the head commit holds it."""
    here = git.run(["rev-parse", "HEAD"], check.top, check=False).strip()
    if here != check.req.head:
        check.defer("head_moved", f"the checkout is at {here[:12]}, not {check.req.head[:12]}")
    elif git.dirty(check.top, check=False) and spec_path in git.dirty(check.top, check=False):
        check.defer("head_moved", f"{spec_path} has changes the head commit does not hold")


def untested(check: Check, spec: dict, text: str) -> None:
    """Every Acceptance item has a test command whose `covers` names it, and one command tests new behavior."""
    ids = workitems.acceptance_ids(text)
    cmds = [c for c in (spec.get("tests") or {}).get("commands", []) if isinstance(c, dict)]
    covered = {i for c in cmds for i in c.get("covers") or []}
    missing = [i for i in ids if i not in covered]
    if not ids or missing or not any(c.get("new_behavior") for c in cmds):
        check.defer("untested_acceptance", f"no command covers {', '.join(missing[:5])}" if missing else "no new_behavior command covers the Acceptance")


def change_spec(check: Check, base: str, head: str) -> tuple[str, dict, dict] | None:
    """The one Spec that applies to the change, as (path, the Spec as the run decides by it, the head's own front matter):
    the one `aidd test` runs the tests of, so the check and the runner never disagree about which Spec the change answers to.
    Its status, route, scope, tests, and frozen files are the base's (`base_view`) where the base holds the Spec as approved
    or later. The head's front matter serves the comparison with the approval and the text shown to the delegate. None with
    no Spec, or after a defer: more than one Spec, or a Spec the head deleted or moved. A Spec the change only reaches by a
    Task's scope is a note, as in the run, and the change's own paths decide whether it may merge with no Spec."""
    merge_base = git.merge_base(base, head, check.top)
    files = git.numstat(merge_base, head, check.top)
    paths = sorted({f["path"] for f in files} | {f["previous_path"] for f in files if f.get("previous_path")})
    try:
        found, _ = testing.find_governing(check.top, specs_dir(check), head, testing.GoverningChange(files, paths, check.head_branch, None, merge_base))
    except documents.DocumentError as exc:
        check.defer("validate_errors", documents.one_line(str(exc), 300))
        return None
    for g in (g for g in found if not g.runs):
        sid = g.data.get("id")
        check.reached.append(str(sid))
        check.warnings.append(
            f"the change touches the Task scope of {sid} ({g.path}) without holding it, so its tests did not run. "
            f"If this is {sid}'s work, work on a branch named spec/{sid}; if not, nothing to do"
        )
    found = [g for g in found if g.runs]
    if len(found) > 1:
        check.defer(
            "no_spec",
            f"{len(found)} Specs apply to the change ({', '.join(g.path for g in found[:5])}), so it is no one Spec's change: "
            "split it into one change for each Spec, or ask the person",
        )
        return None
    if not found:
        return None
    if found[0].why == "base":
        check.defer("no_spec", f"the head deleted or moved {found[0].path}, which applies to this change at the base: restore it, or end it with its status")
        return None
    check.covers["spec"] = str(found[0].data.get("id", ""))
    head_data = found[0].head or found[0].data
    check.spec_path, check.spec_data, check.spec_view = found[0].path, head_data, found[0].data
    return found[0].path, found[0].data, head_data


def approvals(check: Check, spec_id: str) -> list[tuple[str, str]]:
    """Each accept of `spec_id`'s approval on record, newest first, as (when, head). Only the delegate's own answer counts,
    and only while the delegation decides `spec.approve`: a reserved action is never the delegate's to answer. A `decision`
    never counts, because any session can write one in a person's name, and aidd cannot tell a person's yes from a
    session's claim of it. A record is only a pointer to the head the approval covered; the Spec's checks, run again on
    that head, carry the trust. A pulled record is another's text, so it never counts."""
    if "spec.approve" not in policy.covered(check.delegation):
        return []
    found = []
    for rec in records.delegate_accepts(check.top, spec_id):
        covers = (rec.get("data") or {}).get("covers") or {}
        if covers.get("head"):
            found.append((str(rec.get("recorded_at", "")), str(covers["head"])))
    return sorted(found, reverse=True)


def approval_passes(check: Check, head: str, spec_id: str) -> str:
    """Why the Spec approval's checks fail on `head` now, or "": its readiness, its tests and their coverage, its scopes,
    and its red run on the base, with the delegate's defer on that tree. The tip, the delegation, and the platform are
    the merge's own."""
    again = Check(dataclasses.replace(check.req, action="spec.approve", command="", head=head, spec=spec_id, checkout=False))
    again.open_repository()
    again.reads_old_shape = True  # the approval's commit is not the head: it may be from before an upgrade
    for name in ("default", "tip", "cfg", "rs", "delegation", "slug", "gh", "remotes"):
        setattr(again, name, getattr(check, name))
    again.deferred_before()
    if not again.reasons:
        spec_approve(again)
    return again.reasons[0]["code"] if again.reasons else ""


def approval_of(check: Check, spec_id: str) -> tuple[str, str]:
    """The commit a Spec's approval covers, and "" or why there is none. A trailer in a commit never counts, since the
    author writes it, and neither does a `decision`. The delegate's recorded accept counts only while `spec.approve` is
    delegated and the Spec approval's checks pass again now, on the head it covers. With `spec.approve` reserved, no
    approval can stand behind a delegated merge: a person merges, or delegates `spec.approve`."""
    for _when, named in approvals(check, spec_id):
        full = git.run(["rev-parse", "-q", "--verify", f"{named}^{{commit}}"], check.top, check=False).strip()
        if not full or not git.ok(["merge-base", "--is-ancestor", full, check.req.head], check.top):
            continue
        failed = approval_passes(check, full, spec_id)
        return (full, "") if not failed else ("", f"the recorded approval of {spec_id} at {full[:12]} no longer passes the Spec's checks: {failed}")
    if "spec.approve" not in policy.covered(check.delegation):
        return "", (
            f"spec.approve is reserved in the delegation, so a person approves {spec_id} and no record of it can stand behind a delegated merge: "
            "a person merges this change, or adds spec.approve to delegation.decides in a reviewed change"
        )
    return "", f"no recorded approval of {spec_id} covers a commit the head holds"


def scope_check(check: Check, paths: list[str], spec_path: str, approval: str) -> None:
    """Every changed path outside the Spec and the files its approval froze lies in a Task scope of the Spec as approved."""
    approved = local_run.spec_by_id(check.top, approval, specs_dir(check), str(check.covers.get("spec", "")))
    data = approved[1] if approved and not approved[3] else {}
    frozen = [spec_path, *workitems.frozen_files(data)]
    scopes = [s + "**" if s.endswith("/") else s for t in data.get("tasks") or [] for s in t.get("scope") or []]
    outside = [p for p in paths if not globs.match_any(frozen, p) and not globs.match_any(scopes, p)]
    if outside:
        check.defer("out_of_scope", f"{', '.join(outside[:5])} lie outside every Task scope of the approved Spec")


def frozen_by_another(check: Check, base: str, head: str, paths: list[str], held: dict[str, dict | None]) -> None:
    """No file that a Spec past approval at the fork point froze differs at the head, unless the change holds that Spec and records
    a revision of it: the held Spec's own frozen check then decides for it. The same rule `aidd test --require-green` holds the
    change to."""
    problem, *_ = testing.base_frozen_problem(check.top, specs_dir(check), (git.merge_base(base, head, check.top), head), paths, held)
    if problem:
        check.defer("tests_changed", problem)


def merge_checks(check: Check, base: str, head: str) -> str | None:
    """Spec first: an approved Spec whose checks pass again, its frozen tests, `tests`, and Acceptance unchanged since
    approval, and every change inside a Task's scope. The Spec is the one that applies to the change, as `aidd test` reads it:
    the diff holds it, or touches a Task's scope of an approved one. No Spec: `minor`, and every test file the base holds
    unchanged. Then the emergency route, the reserved paths, and the quoted text. The Spec's path, or None with no Spec."""
    assert check.rs is not None
    paths = diff_signals.changed(base, head, check.top)
    change = change_spec(check, base, head)
    spec = change[1] if change else None
    head_spec = change[2] if change else None
    if not check.reasons and not testing.tests_apply(check.top, head, git.merge_base(base, head, check.top)):
        check.defer("untested", "no test command applies to the paths this change touches, so a green check proves nothing about it")
    if change:
        # The base decides (`base_view`), and the head can only make the check stricter: a status or route it lowers still defers.
        for held, whose in ((change[1], "the run"), (change[2], "the head")):
            if workitems.spec_status(held) not in workitems.PAST_APPROVAL:
                check.defer("no_spec", f"{change[1].get('id')} is {workitems.spec_status(held)} in {whose}, not approved")
                break
        approval, why = approval_of(check, str(change[1].get("id", "")))
        if not approval:
            check.defer("no_spec", why)
        elif problem := local_run.frozen_problem(check.top, head, specs_dir(check), (change[0], change[2]), approval):
            check.defer("tests_changed", problem)
        else:
            scope_check(check, paths, change[0], approval)
    elif not check.reasons:
        route = risk.route_for(check.rs, paths).route
        if route != "minor":
            says = (
                f"; it touches the Task scope of {', '.join(check.reached)}, so if this is that Spec's work, work on a branch named spec/<ID>"
                if check.reached
                else ""
            )
            check.defer("no_spec", f"the change's paths give the {route} route, and it has no Spec{says}")
        touched = diff_signals.changed_test_files(base, head, check.top)
        if touched:
            check.defer("tests_changed", f"{', '.join(touched[:5])} changed, and the base holds it")
    frozen_by_another(check, base, head, paths, {str(spec.get("id")): head_spec} if spec else {})
    route_check(check, spec)
    if head_spec is not None and head_spec.get("route") != (spec or {}).get("route"):
        route_check(check, head_spec)  # a route the head claims as emergency defers too, though the run decides by the base's
    hits = diff_signals.reserved_paths(check.rs, paths, check.cfg.parent_paths if check.cfg else ())
    if hits:
        check.defer("reserved_path", ", ".join(hits[:5]))
    subjects = {c["sha"][:12]: c["message"].splitlines()[0] if c["message"] else "" for c in git.commits(base, head, check.top)}
    tripwire(check, {f"commit {sha}'s subject": s for sha, s in subjects.items()})
    return change[0] if change else None


def names_the_head(check: Check, named: str, note_file: str | None) -> bool:
    """Whether a note's `head` is the head, or a commit the head follows with changes to the note's own file alone: a
    note cannot name the commit that holds it."""
    if check.req.head.startswith(named):
        return True
    full = git.run(["rev-parse", "-q", "--verify", f"{named}^{{commit}}"], check.top, check=False).strip()
    if not full or not git.ok(["merge-base", "--is-ancestor", full, check.req.head], check.top):
        return False
    later = [p for p in git.run(["diff", "--name-only", "-z", full, check.req.head], check.top, check=False).split("\0") if p]
    if any(p != note_file for p in later):
        return False
    # The note's own file may change only by its notes and its status, so no Spec edit rides behind the verified head.
    then, now = (_without_notes(git.show(ref, note_file, check.top) or "") for ref in (full, check.req.head)) if later and note_file else ("", "")
    return then == now


def _without_notes(text: str) -> str:
    """A Spec's text without its handoff notes and its `status` line: what a note on its head leaves unchanged."""
    text = workitems.HANDOFF_FENCE.sub("", text)
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith("status:")).strip()


def decisions_check(check: Check, texts: dict[str, str]) -> None:
    """Every role's `open_decisions` entry, in the notes of `texts` read in their order, is answered by a later note's
    `answered`, by its id and one of its own choices. An entry is an agent's text, so it can only defer: the field left out or
    empty asks nothing, an entry that does not read stays open, and one a later `needs` names waits for a person."""
    blocks = [block for text in texts.values() for block in workitems.handoff_blocks(text or "")]
    states, unreadable = workitems.decision_states(blocks)
    waiting = [s for s in states if s["status"] != "answered"]
    if not (waiting or unreadable):
        return
    said = [
        f"`{s['entry']['id']}` is open (its choices: {', '.join(repr(o.get('choice')) for o in s['entry']['options'] if isinstance(o, dict))})"
        for s in waiting
        if s["status"] == "open"
    ]
    said += [f"`{s['entry']['id']}` waits for a person's choice, which a later note's needs names" for s in waiting if s["status"] == "needs_person"]
    check.defer("note_open_decision", f"in the handoff notes of {', then '.join(texts)}: " + "; ".join(said + unreadable))


def notes_check(check: Check, texts: dict[str, str], note_file: str | None = None) -> None:
    """The latest handoff note names the head with `needs: none`, no note after it fails to read or names no head, and no
    `open_decisions` entry stands unanswered. A note can only defer, never make a yes, so a later note that does not read
    stops the check rather than leave an older `needs: none` as the latest."""
    latest: dict | None = None
    unreadable_after = 0  # the notes after the latest one that names a head, and read as none
    for text in texts.values():
        for _raw, note, _err in workitems.handoff_blocks(text or ""):
            if isinstance(note, dict) and note.get("head"):
                latest, unreadable_after = note, 0
            else:
                unreadable_after += 1
    if latest is None:
        check.defer("note_missing", "no handoff note in the Spec, the pull request, or the head commit names a head")
    elif not names_the_head(check, str(latest["head"]), note_file):
        check.defer("note_other_head", f"the latest handoff note names {latest['head']}")
    elif str(latest.get("needs", "")).strip().lower() != "none":
        check.defer("note_needs_decision", f"the latest handoff note needs: {documents.one_line(str(latest.get('needs')), 120)}")
    if latest is not None and unreadable_after:
        check.defer(
            "note_unreadable",
            f"{unreadable_after} handoff note{'s' if unreadable_after > 1 else ''} after the latest one that names a head does not parse as YAML or names no head, so aidd cannot read what it needs",
        )
    decisions_check(check, texts)


def deploy_check(check: Check, pages: str | None = None) -> None:
    """For the default branch, nothing deploys on a merge: the config declares its `environments`, none names the default
    branch or it is not the Pages source, and no workflow or host file at the tip deploys on it. `pages` is the platform's
    Pages source branch; a repository with no platform has none."""
    found = deploys.of_branch(check, check.default, pages)
    if found.unknown:
        check.defer(
            "environments_unset",
            f"this repository's config sets no `environments` of its own, so aidd cannot tell whether a merge into {check.default} deploys",
        )
    if found.why():
        check.defer("merge_deploys", f"a merge into {check.default} deploys: " + ", ".join([*found.declared()[:3], *found.workflows[:3]]))


def head_holds_tip(check: Check, strict: bool = False) -> None:
    """The head holds the default branch's tip, so the tree tested is the tree that merges."""
    if not strict and not git.ok(["merge-base", "--is-ancestor", check.tip, check.req.head], check.top):
        check.defer("base_moved", f"{check.req.head[:12]} does not hold the tip of {check.default}, {check.tip[:12]}")


def head_commit_text(check: Check) -> str:
    return git.messages([check.req.head], check.top).get(check.req.head, "")


def spec_text(check: Check, spec_path: str | None) -> str:
    """The Spec's text at the head, where its handoff notes live; "" with no Spec."""
    return (git.show(check.req.head, spec_path, check.top) or "") if spec_path else ""


def git_merge(check: Check) -> None:
    """A local merge, under solo with no remote: the default branch checked out at its tip, the head holding it, the
    merge checks, no deploy, a note on the head, and the check's own green run of `aidd test` on the head."""
    if check.values.get("sha") != check.req.head:
        check.defer("head_moved", "the command merges another commit than --head")
    if check.cfg and check.cfg.profile == "team":
        check.defer("team_review", "a merge stays a person's under the team profile")
    if check.remotes:
        check.defer("has_remote", f"the repository has a remote ({', '.join(check.remotes)})")
    branch = git.current_branch(check.top)
    here = git.run(["rev-parse", "HEAD"], check.top, check=False).strip()
    if branch != check.default or here != check.tip:
        check.defer("head_moved", f"the checkout must be {check.default} at {check.tip[:12]}, and it is {branch or 'detached'} at {here[:12]}")
    check.covers["branch"] = check.default
    head_holds_tip(check)
    if check.reasons:
        return
    spec = merge_checks(check, check.tip, check.req.head)
    deploy_check(check)
    notes_check(check, {"the Spec": spec_text(check, spec), "the head commit's message": head_commit_text(check)}, spec)
    if not check.reasons:
        evidence, why = local_run.run_on_head(check.top, check.req.head, check.tip)
        problem = local_run.suite_problem(evidence, why)
        if problem:
            check.defer("suite_red", problem)


def tests_workflow(check: Check) -> str | None:
    """The workflow at the tip that runs `aidd test`, by its path."""
    for path in sorted(git.ls_tree(check.tip, check.top, paths=[diff_signals.WORKFLOWS[:-1]])):
        if path.endswith((".yml", ".yaml")) and RUNS_AIDD_TEST.search(git.show(check.tip, path, check.top) or ""):
            return path
    return None


def pr_merge(check: Check) -> None:
    """A merge on GitHub: not team, the branch rules hold, the pull request is this head into the default branch, the
    tip's test workflow passed on the head, the merge checks, no deploy, and a note on the head."""
    if check.values.get("repo") != check.slug:
        check.defer("bypass_flag", f"--repo names {check.values.get('repo')}, not {check.slug}")
    if check.values.get("sha") != check.req.head:
        check.defer("head_moved", "the command's --match-head-commit is not --head")
    if check.cfg and check.cfg.profile == "team":
        check.defer("team_review", "a merge stays a person's under the team profile")
    if check.reasons:
        return
    assert check.gh is not None
    try:
        rules = check.gh.rules(check.default)
        pull = check.gh.pull(int(check.values["number"]))
    except platform.PlatformError as exc:
        check.defer("platform_unreadable", str(exc))
        return
    if not rules.get("readable", True):
        check.defer("protection_unreadable", f"the rules of {check.default} could not be read")
    elif rules.get("bypass"):
        check.defer("no_protection", f"this session's token can bypass the rules of {check.default}, so they prove nothing here")
    elif "tests" not in rules.get("required_checks", []) or not rules.get("blocks_force_push") or not rules.get("blocks_deletion"):
        check.defer("no_protection", f"{check.default} must require the tests check and block force pushes and deletion")
    if pull.get("base") != check.default or pull.get("head_sha") != check.req.head or pull.get("state") != "open":
        check.defer("head_moved", f"pull request #{check.values['number']} is not open from {check.req.head[:12]} into {check.default}")
    check.covers["branch"] = check.default
    check.head_branch = str(pull.get("head_ref") or "")
    head_holds_tip(check, strict=bool(rules.get("strict")))
    ci_check(check)
    spec = merge_checks(check, check.tip, check.req.head)
    try:
        pages = check.gh.pages_branch()
    except platform.PlatformError as exc:
        check.defer("platform_unreadable", str(exc))
        pages = None
    deploy_check(check, pages)
    tripwire(check, {"the pull request's title": pull.get("title", ""), "the pull request's body": pull.get("body", "")}, hidden=False)
    texts = {"the Spec": spec_text(check, spec), "the pull request's body": pull.get("body", ""), "the head commit's message": head_commit_text(check)}
    notes_check(check, texts, spec)


def ci_check(check: Check) -> None:
    """The `tests` check run from GitHub Actions, on the head, from the tip's test workflow, on a pull request or a push,
    concluded success. A commit status never counts."""
    workflow = tests_workflow(check)
    if workflow is None:
        check.defer("ci_not_green", f"no workflow at the tip of {check.default} runs aidd test")
        return
    assert check.gh is not None
    try:
        run = check.gh.tests_run(check.req.head, workflow, int(check.values["number"]) if check.values.get("number") else None, check.default)
    except platform.PlatformError as exc:
        check.defer("platform_unreadable", str(exc))
        return
    if not run or run.get("conclusion") != "success" or run.get("event") not in ("pull_request", "push"):
        check.defer("ci_not_green", f"the tests check run from {workflow} on {check.req.head[:12]} is {(run or {}).get('conclusion') or 'missing'}")
        return
    check.inputs["evidence"] = {"source": "check_run", **{k: run.get(k) for k in ("id", "workflow", "event", "conclusion")}}


def git_push(check: Check) -> None:
    """A push of the change's own branch: the head branch of its open pull request into the default branch, never the
    default branch, a branch that deploys, or the Pages source, and no reserved path in what it pushes."""
    branch = check.values.get("branch", "")
    check.covers["branch"] = branch
    if check.values.get("sha") != check.req.head:
        check.defer("head_moved", "the command pushes another commit than --head")
    if branch == check.default:
        check.defer("reserved_branch", f"{branch} is the default branch")
    if check.reasons:
        return
    assert check.gh is not None
    try:
        pull = check.gh.open_pull_for(branch)
        pages = check.gh.pages_branch()
    except platform.PlatformError as exc:
        check.defer("platform_unreadable", str(exc))
        return
    if not pull or pull.get("base") != check.default:
        check.defer("reserved_branch", f"{branch} is the head of no open pull request into {check.default}")
    assert check.rs is not None
    found = deploys.of_branch(check, branch, pages)
    if found.why():
        check.defer("branch_deploys", f"{branch} deploys: " + ", ".join(found.why()[:3]))
    hits = diff_signals.reserved_paths(check.rs, diff_signals.changed(check.tip, check.req.head, check.top), check.cfg.parent_paths if check.cfg else ())
    if hits:
        check.defer("reserved_path", ", ".join(hits[:5]))


CHECKS = {"spec.approve": spec_approve, "git.push": git_push, "pr.merge": pr_merge, "git.merge": git_merge}
