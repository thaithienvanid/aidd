"""`aidd publish`: the person's step that takes work off this machine (ring 2 to ring 3 in METHOD.md, "Three rings").

Until then the team works here: the inner loop on each Spec's branch, and the local trunk `aidd land` lands on. Publish
pushes the branch checked out, with the person's decision records (`refs/aidd/decisions`), and opens its pull request
where a platform runs the gate. There it carries the person's own recorded Spec approvals onto the pull request, so the
platform's gate counts what they already decided. A person runs it at their own terminal, or an agent runs it once
the person typed `publish` for exactly this head (workitems.publish_said_for).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aidd import config, gate, guard, platforms, workitems
from aidd.cli import arguments
from aidd.cli.commands import confirmations
from aidd.kernel import git

RECORDS = workitems.DECISIONS_REF


def cmd_publish(args) -> int:
    """Push this branch (and the person's decision records), open its pull request where a platform runs the gate, and
    carry the person's recorded Spec approvals there."""
    arguments.enter_repo(args)
    cfg = arguments.config_or_none()
    if cfg is None:
        raise ValueError(f"no {config.CONFIG_PATH}: `aidd init` first")
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
    if not branch:
        print("error: HEAD is detached: switch to the branch to publish", file=sys.stderr)
        return 2
    if git.run(["status", "--porcelain", "--untracked-files=no"], check=False).strip():
        print("error: commit or set aside the changes first: publish takes only committed work", file=sys.stderr)
        return 1
    head = git.rev_parse("HEAD")
    remote = args.remote or _remote_of(branch)
    if not remote:
        print("error: this repository has no remote to publish to: add one (`git remote add origin <url>`)", file=sys.stderr)
        return 2
    base = _base()
    plan = _plan(branch, head, remote, base, args.pr)
    if args.show:
        outside, unread = confirmations.outside_shown()
        print(json.dumps(plan | outside | {"problems": [unread] if unread else []}, indent=2))
        return 0
    if args.confirmed is not None:
        stopped = _confirmed(args, plan)
    else:
        stopped = _who_publishes(cfg, head, plan)
    if stopped is not None:
        return stopped
    return _publish(cfg, plan, records=not args.no_records)


def _confirmed(args, plan: dict) -> int | None:
    """A person's "publish" answered in a dialog (`--confirmed HEAD`, from where `--decided-via` names): recorded on
    the decision records as their typed "publish" is, for exactly the head and the remote they saw, then published. None to
    go on, or the exit code that stops."""
    if args.confirmed != plan["head"]:
        print(
            f"error: you confirmed publishing {plan['branch']} at {args.confirmed[:12]}, but its head is now {plan['head'][:12]}. Nothing was published",
            file=sys.stderr,
        )
        return 1
    if problem := confirmations.confirmation_problem(args.decided_via):
        print(f"error: not published: {problem}", file=sys.stderr)
        return 2 if not confirmations.DECIDED_WHERE.fullmatch(args.decided_via) else 1
    if not args.decided_via.startswith("mcp:"):
        # Only aidd's MCP dialog asks for a publish; a typed `publish` is recorded by the prompt hook, never through here.
        print("error: not published: `--confirmed` counts for publish only from aidd's MCP dialog. Type `publish` at the prompt instead", file=sys.stderr)
        return 1
    login, problem = confirmations.standing_identity()
    if problem := problem or confirmations.local_identity_problem():
        print(f"error: not published: {problem}", file=sys.stderr)
        return 1
    line = workitems.publish_said_line(plan["head"], plan["branch"], plan["remote"], plan["urls"], args.decided_via)
    workitems.record_local_approval(workitems.with_login(line, login))
    return None


def _remote_of(branch: str) -> str:
    """The remote the branch tracks, else `origin`, else the only remote; "" with none. An agent's publish must still
    go where the person's decision named (_who_publishes), and the person sees each URL before they say yes."""
    tracked = git.run(["config", "--get", f"branch.{branch}.remote"], check=False).strip()
    remotes = git.run(["remote"], check=False).split()
    return tracked if tracked in remotes else "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else ""


def _base() -> str:
    try:
        return git.default_base(".").removeprefix("origin/")
    except git.GitError:
        return ""


def _on_a_platform() -> bool:
    """Whether a platform runs the aidd gate for this repository, so the pushed branch gets a pull request."""
    return any(Path(p).is_file() for p in gate.CI_GATE_FILES)


def _plan(branch: str, head: str, remote: str, base: str, pr: bool) -> dict:
    """What leaves this machine: the branch, its head, the remote branch it goes to (a new `publish/` branch when the
    base branch goes as a pull request, `--pr`), the commits the remote does not hold yet (newest first, at most ten
    shown), and whether a pull request opens (`--pr`, or a branch where a platform runs the gate)."""
    target = f"publish/{branch}-{head[:7]}" if pr and branch == base else branch
    pr = pr or (target != base and _on_a_platform())
    known = f"refs/remotes/{remote}/{target}"
    since = known if git.ok(["rev-parse", "-q", "--verify", known]) else (f"refs/remotes/{remote}/{base}" if base else "")
    span = f"{since}..{head}" if since and git.ok(["rev-parse", "-q", "--verify", since]) else head
    commits = [c for c in git.run(["log", "--format=%h %s", span], check=False).splitlines() if c]
    urls = workitems.remote_urls(".", remote)
    return {
        "branch": branch,
        "head": head,
        "remote": remote,
        "urls": urls,
        "to": target,
        "base": base,
        "commits": len(commits),
        "shown": commits[:10],
        "pull_request": pr,
    }


def _who_publishes(cfg, head: str, plan: dict) -> int | None:
    """A person at their own terminal says yes to what leaves; anyone else needs agents to publish here (`publish:
    agents`), or to stay inside the person's grant (workitems.publish_grant: their `publish`, or `approve all and
    publish`): this branch, to the remote they named. None to go on, or the exit code that stops."""
    try:
        platforms.check_terminal("Publishing", "aidd publish")
    except platforms.NotAPerson:
        if gate.agents_publish("."):
            return None
        grant = workitems.publish_grant(cfg, ".", head, plan["branch"])
        if grant and plan["remote"] == grant["remote"] and plan["to"] == grant["branch"] and plan["urls"] == grant["urls"]:
            return None  # inside what the person let the agent publish: this branch, to their remote
        print(
            f"error: not published: the person decides what leaves this machine. They type `publish` at the prompt for "
            f"{plan['branch']} at {head[:12]} (in Claude Code, aidd's MCP tool `publish` asks them in a dialog), or run `aidd publish` "
            "at their own terminal",
            file=sys.stderr,
        )
        return 1
    print(_summary(plan))
    try:
        platforms.require_person("Publishing", command="aidd publish", question=f"Publish {plan['branch']} to {plan['remote']}?")
    except platforms.NotAPerson as exc:
        print(f"Not published: {exc}", file=sys.stderr)
        return 1
    return None


def _summary(plan: dict) -> str:
    more = f"\n  ... and {plan['commits'] - len(plan['shown'])} more" if plan["commits"] > len(plan["shown"]) else ""
    opens = f", then a pull request into {plan['base']}" if plan["pull_request"] else ""
    lines = "\n".join(f"  {c}" for c in plan["shown"]) or "  (no commit the remote lacks)"
    where = ", ".join(plan["urls"]) or "no URL"
    return f"Leaves this machine: {plan['branch']} at {plan['head'][:12]} to {plan['remote']}/{plan['to']} ({where}){opens}\n{lines}{more}"


def _publish(cfg, plan: dict, *, records: bool) -> int:
    remote, target = plan["remote"], plan["to"]
    try:
        git.run(["push", remote, f"{plan['head']}:refs/heads/{target}"], ".", timeout_seconds=300)
    except git.GitError as exc:
        protected = target == plan["base"]
        hint = f" {remote} may protect {target}: publish it as a pull request instead, with `aidd publish --pr`." if protected else ""
        print(f"Not published: git push said: {exc}.{hint}", file=sys.stderr)
        return 1
    if target == plan["branch"]:
        git.run(["branch", f"--set-upstream-to={remote}/{target}", target], check=False)
    print(f"published {plan['branch']} at {plan['head'][:12]} to {remote}/{target}")
    if records and git.ok(["rev-parse", "-q", "--verify", RECORDS]):
        try:
            git.run(["push", remote, f"{RECORDS}:{RECORDS}"], ".", timeout_seconds=120)
            print(f"published your decision records ({RECORDS})")
        except git.GitError:
            print(
                f"note: {remote} holds decision records this machine lacks, so they were not published: fetch them with `git fetch {remote} {RECORDS}:{RECORDS}`"
            )
    if plan["pull_request"] and target != plan["base"]:
        return _open_and_carry(cfg, plan)
    return 0


def _on_gitlab() -> bool:
    """Whether the gate runs on GitLab for this repository: its GitLab CI file, and an `origin` that is not github.com."""
    return Path(gate.CI_GATE_FILES[1]).is_file() and platforms.origin_repo(".") is None and platforms.gitlab_project(".") is not None


def _open_and_carry(cfg, plan: dict) -> int:
    """Open the pull request (GitHub) or merge request (GitLab), then post the person's own recorded Spec approvals of
    this work there."""
    approvers = list(cfg.approvers)
    if plan["remote"] != "origin":
        print(f"note: no pull request opened: aidd opens it on origin's repository, and this went to {plan['remote']}. Open it on your platform")
        return 0
    on_gitlab = _on_gitlab()
    if on_gitlab:
        url, why = platforms.open_merge_request(".", plan["to"], plan["base"])
        if url is None:
            print(f"note: no merge request opened ({why}). Open it on GitLab: `glab mr create --fill`")
            return 0
        print(f"merge request: {url}")
    else:
        url, why = platforms.open_pull_request(".", plan["to"], plan["base"], approvers)
        if url is None:
            print(f"note: no pull request opened ({why}). Open it on your platform: `gh pr create --fill` or `glab mr create --fill`")
            return 0
        print(f"pull request: {url}")
    guard.orca_link(git.toplevel(".") or ".", cfg, url)  # inside Orca, the worktree's card links it; display only
    carried = _carry_spec_approvals(approvers, plan, gitlab=on_gitlab)
    if carried:
        print(f"carried your Spec approval of {', '.join(carried)} to it, so the gate there counts it")
    if on_gitlab:
        print("Next: `aidd/gate` runs in its pipeline. Approve the merge request on GitLab once it is ready: that is your Merge approval.")
    else:
        print("Next: `aidd/gate` runs there. Type `merge it` once it is ready: that is your Merge approval on the platform.")
    return 0


def _carry_spec_approvals(approvers: list[str], plan: dict, *, gitlab: bool = False) -> list[str]:
    """Post, on the branch's pull or merge request, each Spec approval this person recorded here for a Spec the work
    changes, at a commit the pushed head holds: the same line the platform's gate counts. Another person's record stays theirs."""
    email = config.operator_email(Path("."))
    if not email:
        return []
    base = f"refs/remotes/{plan['remote']}/{plan['base']}"
    changed = set(git.run(["diff", "--name-only", f"{base}...{plan['head']}"], check=False).split()) if git.ok(["rev-parse", "-q", "--verify", base]) else set()
    _, comments, _ = workitems.load_local_approvals(".")
    lines: dict[str, str] = {}
    for c in comments:
        words = str(c.get("body", "")).split()
        if c.get("user") != f"email:{email}" or words[:2] != ["/aidd", "approve-spec"] or len(words) != 4:
            continue
        spec_id, commit = words[2], words[3]
        if not any(Path(p).stem == spec_id for p in changed) or not git.ok(["merge-base", "--is-ancestor", commit, plan["head"]]):
            continue
        lines.setdefault(workitems.approve_spec_line(spec_id, commit), spec_id)
    if not lines:
        return []
    if gitlab:
        mr, why = platforms.gitlab_approval_target(".", plan["to"], approvers, head=plan["head"])
        if mr is None:
            print(f"note: aidd carried no Spec approval to the merge request: {why}")
            return []
        for line in lines:
            platforms.post_gitlab_spec_approval(mr, line)
    else:
        pr, _why = platforms.approval_target(".", plan["to"], approvers)
        if pr is None:
            return []
        for line in lines:
            platforms.post_spec_approval(pr, line)
    return list(dict.fromkeys(lines.values()))
