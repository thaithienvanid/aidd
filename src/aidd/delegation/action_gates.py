"""The gates of each delegable action, after the ones every action passes (check.py). Each reads git objects, the tip's
config, and the platform, and defers on the first fact it cannot prove."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from aidd import records, risk, workitems
from aidd.delegation import diff_signals, local_run, platform, policy
from aidd.delegation.check import Check
from aidd.kernel import documents, git, globs

# What runs `aidd test` in a workflow: the aidd action, or the command itself.
RUNS_AIDD_TEST = re.compile(r"^\s*(?:-\s*)?(?:uses:\s*['\"]?thaithienvanid/aidd@|(?:run:\s*)?(?:[\w./-]*/)?(?:uvx\s+|python3?\s+-m\s+)?aidd\s+test\b)", re.M)


def spec_at_head(check: Check, spec_id: str) -> tuple[str, dict, str] | None:
    """The Spec with `spec_id` in the head commit: its path, its front matter, and its text. None after a defer."""
    specs_dir = check.cfg.specs_dir if check.cfg else "specs"
    paths = [f"{specs_dir}/{spec_id}.md"] + sorted(p for p in git.ls_tree(check.req.head, check.top, paths=[specs_dir]) if p.endswith(".md"))
    for path in dict.fromkeys(paths):
        text = git.show(check.req.head, path, check.top)
        if text is None:
            continue
        data, _, errs = workitems.load_object(text, path)
        if data.get("id") == spec_id:
            if errs:
                check.defer("validate-errors", "; ".join(errs)[:300])
                return None
            return path, data, text
    check.defer("spec-not-found", f"no Spec {spec_id} in {check.req.head[:12]}")
    return None


def tripwire(check: Check, texts: dict[str, str]) -> None:
    """No quoted text claims an approval or addresses an approver or a model."""
    words = policy.builtin()["tripwires"]
    for where, text in texts.items():
        low = " ".join((text or "").lower().split())
        hit = next((w for w in words if w in low), None)
        if hit:
            check.defer("text-claims-approval", f"{where} says {hit!r}")
            return


def route_gate(check: Check, spec: dict | None) -> None:
    """The change is not on the emergency route."""
    if spec and spec.get("route") == "emergency":
        check.defer("emergency-route", f"{spec.get('id')} is on the emergency route")


def spec_approve(check: Check) -> None:
    """A ready, valid Spec, every Acceptance item tested, no Task scope in a reserved area, solo on major, red on base."""
    if not check.req.spec:
        check.defer("spec-not-found", "name the Spec with --spec <ID>")
        return
    found = spec_at_head(check, check.req.spec)
    if found is None:
        return
    path, spec, text = found
    check.covers["spec"] = check.req.spec
    route_gate(check, spec)
    tripwire(check, {f"{path}'s body": documents.split_front_matter(text, path)[1]})
    if workitems.spec_status(spec) != "ready":
        check.defer("spec-not-ready", f"{check.req.spec} is {workitems.spec_status(spec)}")
    if spec.get("route") == "major" and check.cfg and check.cfg.profile == "team":
        check.defer("team-review", "a major Spec's approval stays a person's under the team profile")
    if check.req.checkout:
        checked_out(check, path)
    if check.req.checkout and not check.reasons:
        errors = [e for e in workitems.validate_file(Path(check.top) / path, path) if not e.startswith("warning: ")]
        if errors:
            check.defer("validate-errors", errors[0])
    untested(check, spec, text)
    assert check.rs is not None
    scopes = [s for t in spec.get("tasks") or [] for s in t.get("scope") or []]
    hits = diff_signals.reserved_scopes(check.rs, scopes) + diff_signals.reserved_paths(check.rs, diff_signals.changed(check.tip, check.req.head, check.top))
    if hits:
        check.defer("reserved-path", ", ".join(hits[:5]))
    if not check.reasons:
        evidence, why = local_run.run_on_head(check.top, check.req.head, check.tip, path)
        problem = local_run.red_problem(evidence, why)
        if problem:
            check.defer("not-red-on-base", problem)


def checked_out(check: Check, spec_path: str) -> None:
    """For a Spec approval, the checkout is at the head, with the Spec as the head commit holds it."""
    here = git.run(["rev-parse", "HEAD"], check.top, check=False).strip()
    if here != check.req.head:
        check.defer("head-moved", f"the checkout is at {here[:12]}, not {check.req.head[:12]}")
    elif git.dirty(check.top, check=False) and spec_path in git.dirty(check.top, check=False):
        check.defer("head-moved", f"{spec_path} has changes the head commit does not hold")


def untested(check: Check, spec: dict, text: str) -> None:
    """Every Acceptance item has a test command whose `covers` names it, and one command tests new behavior."""
    ids = workitems.acceptance_ids(text)
    cmds = [c for c in (spec.get("tests") or {}).get("commands", []) if isinstance(c, dict)]
    covered = {i for c in cmds for i in c.get("covers") or []}
    missing = [i for i in ids if i not in covered]
    if not ids or missing or not any(c.get("new_behavior") for c in cmds):
        check.defer("untested-acceptance", f"no command covers {', '.join(missing[:5])}" if missing else "no new_behavior command covers the Acceptance")


def change_lane(check: Check, base: str, head: str) -> tuple[str, dict] | None:
    """The one Spec the change adds or changes, as (path, front matter); None on the fast lane, or after a defer."""
    specs_dir = check.cfg.specs_dir if check.cfg else "specs"
    found = workitems.find_specs_in_diff(git.numstat(git.merge_base(base, head, check.top), head, check.top), specs_dir, lambda p: git.show(head, p, check.top))
    if len(found) > 1:
        check.defer("no-spec", f"the change holds {len(found)} Specs, so it is no one Spec's change")
        return None
    if not found:
        return None
    text = git.show(head, found[0], check.top) or ""
    data, _, errs = workitems.load_object(text, found[0])
    if errs:
        check.defer("validate-errors", errs[0])
        return None
    check.covers["spec"] = str(data.get("id", ""))
    return found[0], data


def approvals(check: Check, spec_id: str) -> list[tuple[str, str]]:
    """Each accept of `spec_id`'s approval on record, newest first, as (when, head): a `decision` from any writer, the
    command line or the MCP tool, or a `delegate_answer` under the delegate's own name. A record is only a pointer to the
    head the approval covered; the Spec's gates, run again on that head, carry the trust. A pulled record is another's
    text, so it never counts."""
    pulled = records.pulled_ids(check.top)
    found = []
    for kind in ("decision", "delegate_answer"):
        for rec in records.read_records(check.top, record_type=kind)[0]:
            data = rec.get("data") or {}
            covers = data.get("covers") or {}
            said = (data.get("answer") or {}).get("outcome") if kind == "decision" else data.get("outcome")
            if kind == "delegate_answer" and rec.get("by") != policy.DECIDED_BY:
                continue
            if (
                rec.get("id") not in pulled
                and data.get("action") == "spec.approve"
                and covers.get("spec") == spec_id
                and said == "accept"
                and covers.get("head")
            ):
                found.append((str(rec.get("at", "")), str(covers["head"])))
    return sorted(found, reverse=True)


def approval_passes(check: Check, head: str, spec_id: str) -> str:
    """Why the Spec approval's gates fail on `head` now, or "": its readiness, its tests and their coverage, its scopes,
    and its red run on the base, with the delegate's defer on that tree. The tip, the delegation, and the platform are
    the merge's own, so a Spec a person approved needs no delegation of `spec.approve`."""
    again = Check(dataclasses.replace(check.req, action="spec.approve", command="", head=head, spec=spec_id, checkout=False))
    again.open_repository()
    for name in ("default", "tip", "cfg", "rs", "delegation", "slug", "gh", "remotes"):
        setattr(again, name, getattr(check, name))
    again.deferred_before()
    if not again.reasons:
        spec_approve(again)
    return again.reasons[0]["code"] if again.reasons else ""


def approval_of(check: Check, spec_id: str) -> tuple[str, str]:
    """The commit a Spec's approval covers, and "" or why there is none. A trailer in a commit never counts, since the
    author writes it. A recorded accept, a person's or the delegate's, counts only when the Spec approval's gates pass
    again now, on the head it covers."""
    for _when, named in approvals(check, spec_id):
        full = git.run(["rev-parse", "-q", "--verify", f"{named}^{{commit}}"], check.top, check=False).strip()
        if not full or not git.ok(["merge-base", "--is-ancestor", full, check.req.head], check.top):
            continue
        failed = approval_passes(check, full, spec_id)
        return (full, "") if not failed else ("", f"the recorded approval of {spec_id} at {full[:12]} no longer passes the Spec's gates: {failed}")
    return "", f"no recorded approval of {spec_id} covers a commit the head holds"


def scope_gate(check: Check, paths: list[str], spec_path: str, approval: str) -> None:
    """Every changed path outside the Spec and the files its approval froze lies in a Task scope of the Spec as approved."""
    approved = local_run.spec_in(check.top, approval, spec_path.split("/")[0], str(check.covers.get("spec", "")))
    data = approved[1] if approved and approved[1] else {}
    frozen = [spec_path, *workitems.frozen_files(data)]
    scopes = [s + "**" if s.endswith("/") else s for t in data.get("tasks") or [] for s in t.get("scope") or []]
    outside = [p for p in paths if not globs.match_any(frozen, p) and not globs.match_any(scopes, p)]
    if outside:
        check.defer("out-of-scope", f"{', '.join(outside[:5])} lie outside every Task scope of the approved Spec")


def lane_gate(check: Check, base: str, head: str) -> str | None:
    """The spec lane: an approved Spec whose gates pass again, its frozen tests, `tests`, and Acceptance unchanged since
    approval, and every change inside a Task's scope. The fast lane: `minor`, and every test file the base holds
    unchanged. Then the emergency route, the reserved paths, and the quoted text. The Spec's path, or None on the fast lane."""
    assert check.rs is not None
    paths = diff_signals.changed(base, head, check.top)
    lane = change_lane(check, base, head)
    spec = lane[1] if lane else None
    if lane:
        if workitems.spec_status(lane[1]) not in workitems.PAST_APPROVAL:
            check.defer("no-spec", f"{lane[1].get('id')} is {workitems.spec_status(lane[1])}, not approved")
        approval, why = approval_of(check, str(lane[1].get("id", "")))
        if not approval:
            check.defer("no-spec", why)
        elif problem := local_run.frozen_problem(check.top, head, lane[0], lane[1], approval):
            check.defer("tests-changed", problem)
        else:
            scope_gate(check, paths, lane[0], approval)
    elif not check.reasons:
        route = risk.route_for(check.rs, paths).route
        if route != "minor":
            check.defer("no-spec", f"the change's paths give the {route} route, and it has no Spec")
        touched = diff_signals.changed_test_files(base, head, check.top)
        if touched:
            check.defer("tests-changed", f"{', '.join(touched[:5])} changed, and the base holds it")
    route_gate(check, spec)
    hits = diff_signals.reserved_paths(check.rs, paths)
    if hits:
        check.defer("reserved-path", ", ".join(hits[:5]))
    subjects = {c["sha"][:12]: c["message"].splitlines()[0] if c["message"] else "" for c in git.commits(base, head, check.top)}
    tripwire(check, {f"commit {sha}'s subject": s for sha, s in subjects.items()})
    return lane[0] if lane else None


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


def notes_gate(check: Check, texts: dict[str, str], note_file: str | None = None) -> None:
    """The latest handoff note names the head with `needs: none`. A note can only defer, never make a yes."""
    latest: dict | None = None
    for text in texts.values():
        for _raw, note, _err in workitems.handoff_blocks(text or ""):
            if isinstance(note, dict) and note.get("head"):
                latest = note
    if latest is None:
        check.defer("report-missing", "no handoff note in the Spec, the pull request, or the head commit names a head")
    elif not names_the_head(check, str(latest["head"]), note_file):
        check.defer("report-other-head", f"the latest handoff note names {latest['head']}")
    elif str(latest.get("needs", "")).strip().lower() != "none":
        check.defer("report-blocking", f"the latest handoff note needs: {documents.one_line(str(latest.get('needs')), 120)}")


def deploy_gate(check: Check) -> None:
    """For the default branch, the person said a merge deploys nothing, and no workflow at the tip deploys on it."""
    answer = check.delegation.get("default_branch_deploys")
    if answer is None:
        check.defer("deploys-unknown", "delegation.default_branch_deploys is unset")
    elif answer is True:
        check.defer("merge-deploys", "delegation.default_branch_deploys is true")
    assert check.rs is not None
    found = diff_signals.deploying_workflows(check.rs, check.tip, check.default, check.top)
    if found:
        check.defer("deploy-workflow-found", ", ".join(found[:3]))


def head_holds_tip(check: Check, strict: bool = False) -> None:
    """The head holds the default branch's tip, so the tree tested is the tree that merges."""
    if not strict and not git.ok(["merge-base", "--is-ancestor", check.tip, check.req.head], check.top):
        check.defer("base-moved", f"{check.req.head[:12]} does not hold the tip of {check.default}, {check.tip[:12]}")


def head_commit_text(check: Check) -> str:
    return git.messages([check.req.head], check.top).get(check.req.head, "")


def spec_text(check: Check, spec_path: str | None) -> str:
    """The Spec's text at the head, where its handoff notes live; "" on the fast lane."""
    return (git.show(check.req.head, spec_path, check.top) or "") if spec_path else ""


def git_merge(check: Check) -> None:
    """A local merge, under solo with no remote: the default branch checked out at its tip, the head holding it, the
    lane's gates, no deploy, a note on the head, and the check's own green run of `aidd test` on the head."""
    if check.values.get("sha") != check.req.head:
        check.defer("head-moved", "the command merges another commit than --head")
    if check.cfg and check.cfg.profile == "team":
        check.defer("team-review", "a merge stays a person's under the team profile")
    if check.remotes:
        check.defer("has-remote", f"the repository has a remote ({', '.join(check.remotes)})")
    branch = git.current_branch(check.top)
    here = git.run(["rev-parse", "HEAD"], check.top, check=False).strip()
    if branch != check.default or here != check.tip:
        check.defer("head-moved", f"the checkout must be {check.default} at {check.tip[:12]}, and it is {branch or 'detached'} at {here[:12]}")
    check.covers["branch"] = check.default
    head_holds_tip(check)
    if check.reasons:
        return
    spec = lane_gate(check, check.tip, check.req.head)
    deploy_gate(check)
    notes_gate(check, {"spec": spec_text(check, spec), "head commit": head_commit_text(check)}, spec)
    if not check.reasons:
        evidence, why = local_run.run_on_head(check.top, check.req.head, check.tip)
        problem = local_run.suite_problem(evidence, why)
        if problem:
            check.defer("suite-red", problem)


def tests_workflow(check: Check) -> str | None:
    """The workflow at the tip that runs `aidd test`, by its path."""
    for path in sorted(git.ls_tree(check.tip, check.top, paths=[diff_signals.WORKFLOWS[:-1]])):
        if path.endswith((".yml", ".yaml")) and RUNS_AIDD_TEST.search(git.show(check.tip, path, check.top) or ""):
            return path
    return None


def pr_merge(check: Check) -> None:
    """A merge on GitHub: not team, the branch rules hold, the pull request is this head into the default branch, the
    tip's test workflow passed on the head, the lane's gates, no deploy, and a note on the head."""
    if check.values.get("repo") != check.slug:
        check.defer("admin-or-repo-flag", f"--repo names {check.values.get('repo')}, not {check.slug}")
    if check.values.get("sha") != check.req.head:
        check.defer("head-moved", "the command's --match-head-commit is not --head")
    if check.cfg and check.cfg.profile == "team":
        check.defer("team-review", "a merge stays a person's under the team profile")
    if check.reasons:
        return
    assert check.gh is not None
    try:
        rules = check.gh.rules(check.default)
        pull = check.gh.pull(int(check.values["number"]))
    except platform.PlatformError as exc:
        check.defer("platform-unreadable", str(exc))
        return
    if not rules.get("readable", True):
        check.defer("protection-unreadable", f"the rules of {check.default} could not be read")
    elif rules.get("bypass"):
        check.defer("no-protection", f"this session's token can bypass the rules of {check.default}, so they prove nothing here")
    elif "tests" not in rules.get("required_checks", []) or not rules.get("blocks_force_push") or not rules.get("blocks_deletion"):
        check.defer("no-protection", f"{check.default} must require the tests check and block force pushes and deletion")
    if pull.get("base") != check.default or pull.get("head_sha") != check.req.head or pull.get("state") != "open":
        check.defer("head-moved", f"pull request #{check.values['number']} is not open from {check.req.head[:12]} into {check.default}")
    check.covers["branch"] = check.default
    head_holds_tip(check, strict=bool(rules.get("strict")))
    ci_gate(check)
    spec = lane_gate(check, check.tip, check.req.head)
    deploy_gate(check)
    tripwire(check, {"the pull request's title": pull.get("title", ""), "the pull request's body": pull.get("body", "")})
    notes_gate(check, {"spec": spec_text(check, spec), "pull request": pull.get("body", ""), "head commit": head_commit_text(check)}, spec)


def ci_gate(check: Check) -> None:
    """The `tests` check run from GitHub Actions, on the head, from the tip's test workflow, on a pull request or a push,
    concluded success. A commit status never counts."""
    workflow = tests_workflow(check)
    if workflow is None:
        check.defer("ci-not-green", f"no workflow at the tip of {check.default} runs aidd test")
        return
    assert check.gh is not None
    try:
        run = check.gh.tests_run(check.req.head, workflow, int(check.values["number"]) if check.values.get("number") else None, check.default)
    except platform.PlatformError as exc:
        check.defer("platform-unreadable", str(exc))
        return
    if not run or run.get("conclusion") != "success" or run.get("event") not in ("pull_request", "push"):
        check.defer("ci-not-green", f"the tests check run from {workflow} on {check.req.head[:12]} is {(run or {}).get('conclusion') or 'missing'}")
        return
    check.inputs["evidence"] = {"source": "check_run", **{k: run.get(k) for k in ("id", "workflow", "event", "conclusion")}}


def git_push(check: Check) -> None:
    """A push of the change's own branch: the head branch of its open pull request into the default branch, never the
    default branch, a branch that deploys, or the Pages source, and no reserved path in what it pushes."""
    branch = check.values.get("branch", "")
    check.covers["branch"] = branch
    if check.values.get("sha") != check.req.head:
        check.defer("head-moved", "the command pushes another commit than --head")
    if branch == check.default:
        check.defer("reserved-branch", f"{branch} is the default branch")
    if check.reasons:
        return
    assert check.gh is not None
    try:
        pull = check.gh.open_pull_for(branch)
        pages = check.gh.pages_branch()
    except platform.PlatformError as exc:
        check.defer("platform-unreadable", str(exc))
        return
    if not pull or pull.get("base") != check.default:
        check.defer("reserved-branch", f"{branch} is the head of no open pull request into {check.default}")
    assert check.rs is not None
    named = [e.get("name") for e in check.rs.environments if globs.match_any(e.get("branches") or [], branch)]
    found = diff_signals.deploying_workflows(check.rs, check.tip, branch, check.top)
    if pages == branch or named or found:
        check.defer(
            "deploy-branch", f"{branch} deploys: " + ", ".join([*(["it is the Pages source"] if pages == branch else []), *map(str, named), *found][:3])
        )
    hits = diff_signals.reserved_paths(check.rs, diff_signals.changed(check.tip, check.req.head, check.top))
    if hits:
        check.defer("reserved-path", ", ".join(hits[:5]))


GATES = {"spec.approve": spec_approve, "git.push": git_push, "pr.merge": pr_merge, "git.merge": git_merge}
