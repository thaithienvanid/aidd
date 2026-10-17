"""GitHub adapter: gather a trusted context for a pull request and post `aidd/gate`.

Run it from a workflow whose definition comes from the default branch
(pull_request_target, issue_comment, workflow_run). It checks out nothing
from the PR: the head is fetched as git objects and never executed, and the
Policy command runs in a clean worktree of the PR's base branch.

Post with a dedicated GitHub App token and pin the required `aidd/gate`
check to that App: a commit status is a per-commit fact that any account
with push access can write, so the App identity is what makes it trusted.

Merge queues: the gate never runs on `merge_group` itself (that event runs the
workflow file from the merge-group commit, which holds the pull request's
changes). It runs on the `workflow_run` of the aidd-tests run the queue
started, judges the pull request as usual (approvals bound to its head), and
requires the tests to have re-run on the merge-group commit, whose tree must be
exactly the approved head merged into the commit the entry was built on.
"""

from __future__ import annotations

import base64
import datetime as dt
import fnmatch
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass

from aidd import config, views
from aidd import gate as aidd_gate
from aidd.kernel import documents, git, http
from aidd.kernel.processes import require_env
from aidd.kernel.timestamps import EPOCH, parse_time

STATUS_CONTEXT = "aidd/gate"
TESTS_WORKFLOW_PATH = ".github/workflows/aidd-tests.yml"
MAX_COMMITS = 250  # the pulls/{n}/commits API returns at most this many
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
MAX_TEAM_LOOKUPS = 50
_GITHUB_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$")
_REVIEW_STATE = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes_requested", "COMMENTED": "commented", "DISMISSED": "dismissed"}
_WHERE = "aidd gate github runs inside GitHub Actions"
_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


class Client(http.JsonClient):
    headers = _HEADERS

    def post(self, path: str, data: dict):
        _, _, body = self._request("POST", self.api + path, auth=self._auth(), data=data, headers=_HEADERS, max_bytes=http.MAX_API_BYTES)
        return json.loads(body or b"null")


# GitHub names each queue entry's branch gh-readonly-queue/<base>/pr-<number>-<sha of the commit it was built on>.
_QUEUE_BRANCH = re.compile(r"^(?:refs/heads/)?(?P<branch>gh-readonly-queue/(?P<base>.+)/pr-(?P<number>[1-9][0-9]{0,9})-(?P<sha>[0-9a-f]{40}))$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class MergeGroup:
    """One merge-queue entry: its commit, its branch, the base branch it targets, its pull request, and the SHA its branch names."""

    sha: str
    branch: str
    base_ref: str
    number: int
    named_parent: str


def merge_group_of(event: dict) -> MergeGroup | None:
    """The merge-queue entry an event concerns (a `merge_group` event, or the `workflow_run` of a run it started), else None.

    Nothing here is trusted on its own: the entry's commit is bound to the approved head by its tree (`merged_tree`),
    so a wrong pull request number or parent only makes the gate fail."""
    mg = event.get("merge_group")
    run = event.get("workflow_run")
    if isinstance(mg, dict):
        sha, ref = mg.get("head_sha"), mg.get("head_ref")
    elif isinstance(run, dict) and run.get("event") == "merge_group":
        sha, ref = run.get("head_sha"), run.get("head_branch")
    else:
        return None
    m = _QUEUE_BRANCH.match(ref or "")
    if not m or not isinstance(sha, str) or not _SHA.match(sha):
        raise ValueError(f"a merge queue event with an unexpected branch {ref!r} or commit {sha!r}; the gate cannot bind it to a pull request")
    return MergeGroup(sha=sha, branch=m["branch"], base_ref=m["base"], number=int(m["number"]), named_parent=m["sha"])


def queue_parent(cwd: str, sha: str, named_parent: str, base_tip: str) -> tuple[str, bool]:
    """The commit a queue entry was built on, and whether that is a previous entry (stacked) rather than the base.

    The branch names it; the name counts only when git agrees: the base is its ancestor and it is the entry's.
    Otherwise the entry was built on the base itself. The aidd-tests job and the gate both call this, so the
    evidence's base and the gate's expectation are computed the same way."""
    base = git.merge_base(base_tip, sha, cwd)
    if (
        named_parent != base
        and git.ok(["cat-file", "-e", f"{named_parent}^{{commit}}"], cwd)
        and git.ok(["merge-base", "--is-ancestor", base, named_parent], cwd)
        and git.ok(["merge-base", "--is-ancestor", named_parent, sha], cwd)
    ):
        return named_parent, True
    return base, False


def merged_tree(cwd: str, parent: str, head: str) -> str | None:
    """The tree of `head` merged into `parent` (git merge-tree, 2.38 or later), or None when the merge conflicts."""
    p = git._git(["merge-tree", "--write-tree", "--no-messages", parent, head], cwd)
    out = p.stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
    if p.returncode == 0 and _SHA.match(out):
        return out
    if p.returncode == 1:
        return None
    raise git.GitError(f"git merge-tree {parent[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")


def _queue_all_green(client: Client, repo: str, base_ref: str) -> bool | None:
    """Whether every merge queue rule on the base merges a group only when all its entries passed (ALLGREEN); None when unknown."""
    try:
        found = client.get(f"/repos/{repo}/rules/branches/{urllib.parse.quote(base_ref, safe='')}") or []
    except http.HttpError:
        return None
    queues = [r for r in found if isinstance(r, dict) and r.get("type") == "merge_queue"]
    if not queues:
        return None
    return all((r.get("parameters") or {}).get("grouping_strategy") == "ALLGREEN" for r in queues)


def pr_numbers(event: dict, client: Client, repo: str) -> list[int]:
    """Every open pull request an event concerns. Fork PRs are found by head repo and branch; a queue entry by its branch."""
    group = merge_group_of(event)
    if group:
        return [group.number]
    if isinstance(event.get("pull_request"), dict):
        return [int(event["pull_request"]["number"])]
    issue = event.get("issue")
    if issue and "pull_request" in issue:
        return [int(issue["number"])]
    run = event.get("workflow_run")
    if not run:
        return []
    found = {int(p["number"]) for p in run.get("pull_requests") or []}
    if not found:
        owner = ((run.get("head_repository") or {}).get("owner") or {}).get("login")
        if owner and run.get("head_branch"):
            pulls = client.paginate(f"/repos/{repo}/pulls", {"state": "open", "head": f"{owner}:{run['head_branch']}"})
            found = {int(p["number"]) for p in pulls if p.get("head", {}).get("sha") == run.get("head_sha")}
    if not found:
        sha = urllib.parse.quote(run["head_sha"], safe="")
        pulls = client.get(f"/repos/{repo}/commits/{sha}/pulls") or []
        found = {int(p["number"]) for p in pulls if p.get("state") == "open"}
    return sorted(found)


def _team_members(client: Client, entries: list[str]) -> dict[str, list[str]]:
    """Members of each `@org/team` pool entry. An entry that fails to resolve stays missing, which holds the gate pending.

    Pool entries can come from the change's own Spec (`approvers`), so each name is checked
    against GitHub's naming rules and quoted before it reaches a URL, and the lookups are capped.
    """
    out: dict[str, list[str]] = {}
    # A tenant-qualified entry (`acme:@org/team`) is looked up without its tenant and kept under the entry as written.
    teams = [(e, config.split_tenant(e)[1]) for e in entries]
    teams = [(e, name) for e, name in teams if "/" in name and not name.startswith("email:")]
    for e, name in teams[:MAX_TEAM_LOOKUPS]:
        org, slug = name.split("/", 1)
        if not (_GITHUB_NAME.match(org) and _GITHUB_NAME.match(slug)):
            continue
        path = f"/orgs/{urllib.parse.quote(org, safe='')}/teams/{urllib.parse.quote(slug, safe='')}/members"
        try:
            out[e] = [m["login"] for m in client.paginate(path)]
        except http.HttpError:
            pass
    return out


def _branch_conflicts(client: Client, repo: str, *, number: int, head_owner: str | None, head_ref: str | None, head_sha: str, base_ref: str) -> list[int]:
    """Other pull requests, open or closed, from the same branch at the same commit into another base.

    A test run belongs to a commit, and GitHub builds a pull_request run from
    the merge with its base, so a second pull request into a branch whose
    aidd-tests.yml writes forged evidence would produce a run this pull request
    cannot tell apart. Evidence is taken only when no such pull request exists.
    """
    if not head_owner or not head_ref:
        return []
    pulls = client.paginate(f"/repos/{repo}/pulls", {"state": "all", "head": f"{head_owner}:{head_ref}"}, limit=300, strict=True)
    return sorted(
        int(p["number"])
        for p in pulls
        if int(p["number"]) != number and (p.get("head") or {}).get("sha") == head_sha and (p.get("base") or {}).get("ref") != base_ref
    )


def verify_attestation(blob: bytes, repo: str, signer_workflow: str, token: str) -> str | None:
    """None when `gh attestation verify` accepts the evidence as signed by signer_workflow; otherwise why not."""
    gh = shutil.which("gh")
    if not gh:
        return "evidence.signer_workflow is set, but the gh CLI is not on the runner"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "evidence.json")
        with open(path, "wb") as fh:
            fh.write(blob)
        argv = [gh, "attestation", "verify", path, "--repo", repo, "--signer-workflow", signer_workflow, "--format", "json"]
        env = {**os.environ, "GH_TOKEN": token}
        try:
            p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=120, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"no valid attestation from {signer_workflow}: gh attestation verify did not finish: {type(exc).__name__}"
    return None if p.returncode == 0 else f"no valid attestation from {signer_workflow}: {(p.stderr or p.stdout).strip()[:200]}"


def _evidence(
    client: Client,
    repo: str,
    head_sha: str,
    workflow: str,
    artifact: str,
    head_repo: str | None = None,
    workflow_path: str = TESTS_WORKFLOW_PATH,
    *,
    head_ref: str | None = None,
    signer_workflow: str | None = None,
    event: str = "pull_request",
) -> tuple[dict | None, str]:
    """The evidence of the newest usable test run for this head: completed, not skipped or cancelled, with the artifact.

    `event` is pull_request for a pull request's head, merge_group for a queue entry's commit."""
    wf = workflow_path.rsplit("/", 1)[-1]
    runs = client.get(f"/repos/{repo}/actions/workflows/{wf}/runs", {"head_sha": head_sha, "event": event, "per_page": 30}).get("workflow_runs", [])
    runs = [
        r
        for r in runs
        if r.get("name") == workflow
        and r.get("path", workflow_path).split("@")[0] == workflow_path
        and r.get("event", event) == event
        and r.get("head_sha", head_sha) == head_sha
        and (head_ref is None or r.get("head_branch", head_ref) == head_ref)
        and (head_repo is None or (r.get("head_repository") or {}).get("full_name", head_repo) == head_repo)
    ]
    runs.sort(key=lambda r: parse_time(r.get("created_at")) or EPOCH, reverse=True)
    if not runs:
        return None, f"no {workflow} run from {workflow_path} for {head_sha[:12]}"
    missing = None
    for run in runs:
        if run.get("status") != "completed":
            return None, f"{workflow} run {run['id']} is {run.get('status')}"
        if run.get("conclusion") in ("skipped", "cancelled"):
            continue  # a title-only edit, or a run a newer one replaced
        arts = client.get(f"/repos/{repo}/actions/runs/{run['id']}/artifacts").get("artifacts", [])
        # A re-run keeps every attempt's artifacts: the newest one is the latest attempt's.
        named = [a for a in arts if a.get("name") == artifact and not a.get("expired")]
        art = max(named, key=lambda a: (parse_time(a.get("created_at")) or EPOCH, int(a.get("id") or 0)), default=None)
        if art is None:
            # A run that tested nothing (a description edit that left the Change Request block alone skips the tests job):
            # an earlier run of this same head holds the evidence, which is bound to its head and base like any other.
            missing = missing or f"{workflow} run {run['id']} uploaded no {artifact} artifact"
            continue
        blob = client.download(art["archive_download_url"], max_bytes=2 * MAX_EVIDENCE_BYTES)
        url = run.get("html_url", "")
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                if "evidence.json" not in zf.namelist():
                    return None, f"{artifact} has no evidence.json at its root"
                info = zf.getinfo("evidence.json")
                if info.file_size > MAX_EVIDENCE_BYTES or info.compress_size > MAX_EVIDENCE_BYTES:
                    return {"invalid": f"{artifact} of run {run['id']}: evidence.json size {info.file_size} exceeds {MAX_EVIDENCE_BYTES} byte cap"}, url
                raw = zf.read("evidence.json")
                data = json.loads(raw)
        except (zipfile.BadZipFile, ValueError) as exc:
            return {"invalid": f"{artifact} of run {run['id']} is unreadable: {type(exc).__name__}"}, url
        why = verify_attestation(raw, repo, signer_workflow, client.token) if signer_workflow else None
        return ({"invalid": why}, url) if why else (data, url)
    return None, missing or f"every {workflow} run for {head_sha[:12]} was skipped or cancelled"


evidence = _evidence


def _status_checks(client: Client, repo: str, head_sha: str, names: list[str], *, apps: list[str], head_ref: str | None) -> dict[str, str]:
    """The state of each named check run on head, from an allowed app and the PR's own branch.

    Within one check suite the newest run wins, so re-running a flaky job clears its failure.
    Across suites the worst state wins: a job with the same name in another workflow, run
    later, must not hide a failure. Commit statuses never count: anyone with push access can
    post one under any name.
    """
    if not names:
        return {}
    wanted = set(names)
    # One query per named check: a busy head with thousands of other check runs never pushes the named ones past the
    # page limit. Past it, for one name, the gate still errors rather than judge from a cut list.
    runs = [
        run
        for name in sorted(wanted)
        for run in client.paginate(
            f"/repos/{repo}/commits/{head_sha}/check-runs", {"check_name": name, "filter": "latest"}, key="check_runs", limit=1000, strict=True
        )
    ]
    runs.sort(key=lambda r: parse_time(r.get("started_at")) or parse_time(r.get("completed_at")) or EPOCH, reverse=True)
    newest: dict[tuple[str, object], str] = {}
    for run in runs:
        name = run.get("name")
        if name not in wanted or ((run.get("app") or {}).get("slug") or "") not in apps:
            continue
        suite = run.get("check_suite") or {}
        branch = suite.get("head_branch")
        if not branch or (head_ref and branch != head_ref):
            continue
        newest.setdefault((name, suite.get("id")), run.get("conclusion") or run.get("status") or "pending")
    states: dict[str, str] = {}
    for (name, _), state in newest.items():
        if name not in states or _check_rank(state) > _check_rank(states[name]):
            states[name] = state
    return states


def _check_rank(state: str) -> int:
    """How bad a check state is: a failure outranks waiting, and waiting outranks success."""
    return 0 if state in ("success", "neutral") else 1 if state in ("pending", "queued", "in_progress", "waiting", "requested", "skipped") else 2


def _base_changed_at(client: Client, repo: str, number: int) -> str | None:
    """When the pull request was last retargeted to another base branch, from its timeline."""
    events = client.paginate(f"/repos/{repo}/issues/{number}/timeline", limit=3000, strict=True)
    times = [(t, e["created_at"]) for e in events if e.get("event") == "base_ref_changed" and (t := parse_time(e.get("created_at"))) is not None]
    return max(times)[1] if times else None


def _pushed_at(client: Client, repo: str, head_sha: str, head_ref: str | None = None) -> str | None:
    """When this head first reached the pull request's branch: its earliest check suite there.

    Server time only (a committer date is the author's to set), and only suites on the pull
    request's own branch: pushing the same commit to a scratch branch earlier must not start
    the cool-off early. With no such suite the answer is None, so a cool-off never passes.
    """
    try:
        suites = client.get(f"/repos/{repo}/commits/{head_sha}/check-suites").get("check_suites", [])
    except http.HttpError:
        suites = []
    times = [
        (t, s["created_at"]) for s in suites if (head_ref is None or s.get("head_branch") == head_ref) and (t := parse_time(s.get("created_at"))) is not None
    ]
    return min(times)[1] if times else None


def _fetch(cwd: str, token: str, refspecs: list[str]) -> None:
    """Fetch with a one-off auth header, so the checkout never stores credentials a Policy command could read."""
    env = None
    if token:
        # The header travels in the environment, not on argv, so it never shows in `ps` or in a GitError message.
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"http.{server}/.extraheader", "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"}
    git.fetch(cwd, refspecs, env=env)


def _spec_approval_commits(comments: list[dict], limit: int = aidd_gate.MAX_APPROVAL_COMMITS) -> list[str]:
    """The commits `/aidd approve-spec` lines name, newest first."""

    out: list[str] = []
    for c in reversed(comments):
        for m in aidd_gate.APPROVE_SPEC.finditer(aidd_gate.comment_commands(c.get("body") or "")):
            if m.group(3) and m.group(3) not in out and len(out) < limit:
                out.append(m.group(3))
    return out


def _fetch_named(cwd: str, token: str, shas: list[str]) -> None:
    """Fetch the named commits git does not have yet, by id; best effort, since GitHub may no longer have one."""
    missing = [s for s in dict.fromkeys(shas) if _SHA.match(s) and not git.ok(["cat-file", "-e", f"{s}^{{commit}}"], cwd)]
    if not missing:
        return
    try:
        _fetch(cwd, token, missing)
    except git.GitError:
        for sha in missing:  # one unknown commit fails a batch; fetch the rest one by one
            try:
                _fetch(cwd, token, [sha])
            except git.GitError:
                continue


def build_context(client: Client, repo: str, number: int, *, cwd: str = ".", org_preset: str | None = None, group: MergeGroup | None = None) -> dict:
    """The trusted context for a pull request; with `group`, for its merge-queue entry (approvals still bind to the PR head)."""
    pr = client.get(f"/repos/{repo}/pulls/{number}")
    head_sha = pr["head"]["sha"]
    base_ref = pr["base"]["ref"]
    if group and group.base_ref != base_ref:
        raise RuntimeError(f"the queue entry {group.branch} targets {group.base_ref}, but pull request #{number} targets {base_ref}")
    refspecs = [f"+refs/pull/{number}/head:refs/aidd/pr-head", f"+refs/heads/{base_ref}:refs/aidd/base"]
    if group:
        refspecs.append(f"+refs/heads/{group.branch}:refs/aidd/merge-group")
    _fetch(cwd, client.token, refspecs)
    base_tip = git.rev_parse("refs/aidd/base", cwd)
    git.rev_parse(head_sha, cwd)
    merge_group = None
    if group:
        if git.rev_parse("refs/aidd/merge-group", cwd) != group.sha:
            raise RuntimeError(f"the queue branch {group.branch} no longer points at {group.sha[:12]}; the queue rebuilt it")
        parent, stacked = queue_parent(cwd, group.sha, group.named_parent, base_tip)
        # The pull request's diff as it enters the queue: from where it meets the entry's parent.
        base_sha = git.merge_base(parent, head_sha, cwd)
        merge_group = {
            "sha": group.sha,
            "ref": group.branch,
            "base_sha": parent,
            "stacked": stacked,
            "tree": git.run(["rev-parse", "--verify", f"{group.sha}^{{tree}}"], cwd).strip(),
            "merged_tree": merged_tree(cwd, parent, head_sha),
            "all_green": _queue_all_green(client, repo, base_ref) if stacked else None,
        }
    else:
        base_sha = git.merge_base(base_tip, head_sha, cwd)
    body = pr.get("body") or ""
    files = git.numstat(base_sha, head_sha, cwd)
    decl = aidd_gate.declared_inputs(cwd, base_tip, head_sha, body, org_preset=org_preset)
    cfg = decl["config"]
    commits = [
        {
            "sha": c["sha"],
            "author": (c.get("author") or {}).get("login") or f"email:{c['commit']['author']['email']}",
            "committer": (c.get("committer") or {}).get("login") or f"email:{c['commit']['committer']['email']}",
            "message": c["commit"]["message"],
            "merge": len(c.get("parents", [])) > 1,
            "verified": bool(((c.get("commit") or {}).get("verification") or {}).get("verified")),
        }
        for c in client.paginate(f"/repos/{repo}/pulls/{number}/commits", limit=MAX_COMMITS)
    ]
    base_changed_at = _base_changed_at(client, repo, number)
    reviews = [
        {
            "user": r["user"]["login"],
            "state": _REVIEW_STATE.get(r["state"], "commented"),
            "commit_sha": r.get("commit_id"),
            "submitted_at": r.get("submitted_at"),
        }
        for r in client.paginate(f"/repos/{repo}/pulls/{number}/reviews", strict=True)
        if r.get("user")
    ]
    comments = [
        aidd_gate.recorded_comment(c["user"]["login"], c) for c in client.paginate(f"/repos/{repo}/issues/{number}/comments", strict=True) if c.get("user")
    ]
    team_members = _team_members(client, decl["pools"])

    def ev(key: str, default=None):
        return cfg.get("evidence", key, default=default) if cfg else default

    head = pr.get("head") or {}
    # A queue entry's commit is its own: its runs are on the queue branch of this repository, and no other pull request shares it.
    tested_sha, tested_ref, tested_repo = (group.sha, group.branch, repo) if group else (head_sha, head.get("ref"), (head.get("repo") or {}).get("full_name"))
    conflicts: list[int] = []
    if not group:
        owner = ((head.get("repo") or {}).get("owner") or {}).get("login")
        conflicts = _branch_conflicts(client, repo, number=number, head_owner=owner, head_ref=head.get("ref"), head_sha=head_sha, base_ref=base_ref)
    if conflicts:
        evidence, evidence_note = (
            None,
            (
                f"pull request(s) {', '.join(f'#{n}' for n in conflicts)} from this branch at this commit "
                "target another base, so their test runs are indistinguishable. Close them and push a new commit"
            ),
        )
    else:
        evidence, evidence_note = _evidence(
            client,
            repo,
            tested_sha,
            ev("workflow", "aidd-tests"),
            ev("artifact", "aidd-evidence"),
            tested_repo,
            ev("workflow_path", TESTS_WORKFLOW_PATH),
            head_ref=tested_ref,
            signer_workflow=ev("signer_workflow"),
            event="merge_group" if group else "pull_request",
        )
    pushed_at = _pushed_at(client, repo, head_sha, head.get("ref"))
    checks = {}
    if not conflicts:
        checks = _status_checks(client, repo, tested_sha, ev("status_checks", []), apps=ev("status_check_apps", ["github-actions"]), head_ref=tested_ref)
    ctx = {
        "platform": "github",
        "trusted": True,
        "repo": repo,
        "now": dt.datetime.now(dt.UTC).isoformat(),
        "change": {
            "id": str(number),
            "url": pr.get("html_url", ""),
            "author": pr["user"]["login"],
            "body": body,
            "head_ref": str((pr.get("head") or {}).get("ref") or ""),
            "draft": bool(pr.get("draft")),
            "created_at": pr.get("created_at"),
        },
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_pushed_at": pushed_at,
        "base_changed_at": base_changed_at,
        "files": files,
        "commits": commits,
        "commits_truncated": int(pr.get("commits", 0)) > MAX_COMMITS,
        "reviews": reviews,
        "comments": comments,
        "status_checks": checks,
        "evidence": evidence,
    }
    # Commits approvals name that a force-push took off the branch (an earlier head, a Spec commit rebased away) are
    # fetched by id, so the approvals' equivalence and the Spec proof can be computed; one GitHub no longer has stays unknown.
    _fetch_named(cwd, client.token, aidd_gate.approved_heads(ctx, head_sha) + _spec_approval_commits(comments))
    ctx |= aidd_gate.adapter_fields(ctx, cwd, decl, base_tip, team_members, org_preset, pushed_at=lambda sha: _pushed_at(client, repo, sha, head.get("ref")))
    if merge_group:
        ctx["merge_group"] = merge_group
    return ctx | {"_evidence_note": evidence_note, "_base_ref": base_ref}


def status_context(base_ref: str, protected: list[str], mode: str = "enforce") -> str:
    """`aidd/gate` only for protected bases in enforce mode, so no other run can satisfy the required check."""
    if mode == "advisory":
        return f"{STATUS_CONTEXT} (advisory)"
    return STATUS_CONTEXT if any(fnmatch.fnmatchcase(base_ref, p) for p in protected) else f"{STATUS_CONTEXT} ({base_ref})"


def post_status(client: Client, repo: str, d: aidd_gate.Decision, target_url: str, context: str = STATUS_CONTEXT, *, sha: str | None = None) -> None:
    """Post the decision on the head, or on `sha` (a merge-queue entry's commit)."""
    state = {"pass": "success", "fail": "failure", "pending": "pending"}[d.decision]
    head_sha = urllib.parse.quote(sha or d.record["head_sha"] or "", safe="")
    client.post(f"/repos/{repo}/statuses/{head_sha}", {"state": state, "context": context, "description": aidd_gate.status_line(d), "target_url": target_url})


def protected_branches(client: Client, repo: str) -> list[str]:
    """The default branch, plus AIDD_PROTECTED_BRANCHES (comma-separated names or globs such as release/*)."""
    extra = [b.strip() for b in os.environ.get("AIDD_PROTECTED_BRANCHES", "").split(",") if b.strip()]
    return [client.get(f"/repos/{repo}")["default_branch"], *extra]


def github_gate(
    *,
    dry_run: bool = False,
    cwd: str = ".",
    events_out: str | None = None,
    record_out: str | None = None,
    resolve_only: bool = False,
    mode: str | None = None,
    html_out: str | None = None,
) -> int:
    repo = require_env("GITHUB_REPOSITORY", _WHERE)
    client = Client(os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    with open(require_env("GITHUB_EVENT_PATH", _WHERE), encoding="utf-8") as fh:
        event = json.load(fh)
    group = merge_group_of(event)
    numbers = pr_numbers(event, client, repo)
    if resolve_only:
        # `head` keys the reusable workflow's concurrency group: one queue per commit, since a commit status belongs to
        # the commit, whichever pull request or queue entry a run judges. The queue entry's own commit, else the pull
        # request's current head as GitHub reports it now (an event's copy may be older).
        head = group.sha if group else (str((client.get(f"/repos/{repo}/pulls/{numbers[0]}").get("head") or {}).get("sha") or "") if numbers else "")
        line = f"prs={json.dumps(numbers)}\npr={numbers[0] if numbers else ''}\nhead={head if _SHA.match(head) else ''}\n"
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(line)
        print(line, end="")
        return 0
    if not numbers:
        print("aidd gate: this event is not about an open pull request; nothing to do")
        return 0
    # The mode comes from the base config, else from `--mode`, which the reusable workflow passes from its `mode` input
    # (a workflow definition on the default branch). AIDD_MODE is only an environment variable: a job's env, a
    # composite action, or another workflow can set it, so, as on GitLab, it can never relax the gate.
    requested, trusted = (mode, True) if mode else (os.environ.get("AIDD_MODE") or None, False)
    if requested == "advisory" and not trusted:
        print(
            'aidd gate: AIDD_MODE=advisory is ignored; pass --mode advisory (the reusable workflow\'s `mode` input) or set mode: "advisory" in the base config'
        )
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    try:
        org = config.org_preset_text()
        protected = protected_branches(client, repo)
    except Exception as exc:  # fail closed here too: an older success on these heads must not stand
        print(f"aidd gate: setup error: {type(exc).__name__}: {exc}")
        # The platform failed, not git: the config committed at the checkout (the default branch's, or the base's)
        # still says whether this repository asked for advisory mode.
        mode = config.effective_mode(_checkout_mode(cwd), requested, input_trusted=trusted)
        if not dry_run:
            for number in numbers:
                # The protected branch list is unknown, so post on the required context for every base.
                _post_error(client, repo, number, exc, run_url, ["*"], mode, group)
        return 2 if mode == "enforce" else 0
    worst = 0
    for number in numbers:
        mode = config.effective_mode(None, requested, input_trusted=trusted)  # for an error before the base config is read
        try:
            worst = max(
                worst,
                _gate_one(client, repo, number, numbers, cwd, org, (requested, trusted), protected, run_url, dry_run, events_out, record_out, group, html_out),
            )
        except Exception as exc:  # fail closed: a crash must never leave an older success standing
            print(f"PR #{number}: gate error: {type(exc).__name__}: {exc}")
            if events_out:
                _append_line(events_out, aidd_gate.error_event(repo, str(number), exc, mode=mode, run_url=run_url, tenant=config.preset_tenant(org)))
            if not dry_run:
                _post_error(client, repo, number, exc, run_url, protected, mode, group)
            worst = max(worst, 2 if mode == "enforce" else 0)
    return worst


def _gate_one(
    client: Client,
    repo: str,
    number: int,
    numbers: list[int],
    cwd: str,
    org: str | None,
    requested: tuple[str | None, bool],
    protected: list[str],
    run_url: str,
    dry_run: bool,
    events_out: str | None,
    record_out: str | None,
    group: MergeGroup | None,
    html_out: str | None = None,
) -> int:
    """Evaluate, report, and post for one pull request, or its merge-queue entry. Any exception here posts `error`."""
    ctx, d, base_ref = _evaluate(client, repo, number, cwd=cwd, org_preset=org, group=group)
    # A mode in the base config wins; else `--mode` (the reusable workflow's input), and never AIDD_MODE alone.
    mode = config.effective_mode(d.record.get("config_mode"), requested[0], input_trusted=requested[1])
    print(f"PR #{number} -> {base_ref} ({mode})" + (f", merge-queue entry {group.sha[:12]}" if group else ""))
    print(aidd_gate.decision_text(d))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            try:
                extra = views.merge_digest(ctx, cwd=cwd)
            except Exception as exc:  # a summary for people; it must never turn a decision into an error
                extra = f"\n_The Merge approval digest is unavailable: {type(exc).__name__}._\n"
            fh.write(f"#### PR #{number}{' (advisory)' if mode == 'advisory' else ''}\n\n" + aidd_gate.decision_markdown(d) + extra)
    if events_out:
        _append_line(events_out, aidd_gate.decision_event(d, repo, author=ctx["change"]["author"], base_ref=base_ref, mode=mode, run_url=run_url))
    if record_out:
        aidd_gate.write_records(d, ctx, record_out, number=None if len(numbers) == 1 else number, run_url=run_url)
    if html_out is not None:
        views.write_merge_page(ctx, d, html_out, cwd=cwd, number=None if len(numbers) == 1 else number)
    if not dry_run and group:
        # The status goes on the queue entry's commit, which is immutable and belongs to this entry alone. Its tree
        # binds it to the head the approvals name, so a head that moved since only makes the decision fail.
        post_status(client, repo, d, run_url, status_context(group.base_ref, protected, mode), sha=group.sha)
    elif not dry_run:
        # A newer push makes this decision stale; the run for the new head posts instead.
        if client.get(f"/repos/{repo}/pulls/{number}")["head"]["sha"] != d.record.get("head_sha"):
            print(f"PR #{number}: head moved while verifying; not posting")
            return 0
        posted = _shared_head_decision(client, repo, number, d, protected, cwd=cwd, org_preset=org)
        post_status(client, repo, posted, run_url, status_context(base_ref, protected, mode))
    return 1 if d.decision == "fail" and mode == "enforce" else 0


def _checkout_mode(cwd: str) -> str | None:
    """The `mode` the config committed at the checkout's HEAD sets, or None. Read from git, never the working tree."""
    text = git.show("HEAD", config.CONFIG_PATH, cwd)
    if text is None:
        return None
    try:
        # With no fetcher: a parent by URL (which may enforce) makes this fail, and so does an org preset that cannot
        # be read, and the gate stays closed.
        preset = config.org_preset_text()
        mode = config.load_text(text, read=lambda p: git.show("HEAD", p, cwd), root_preset=preset).get("mode")
    except (OSError, config.ConfigError, documents.DocumentError):
        return None
    return mode if isinstance(mode, str) else None


def _evaluate(
    client: Client, repo: str, number: int, *, cwd: str, org_preset: str | None, group: MergeGroup | None = None
) -> tuple[dict, aidd_gate.Decision, str]:
    ctx = build_context(client, repo, number, cwd=cwd, org_preset=org_preset, group=group)
    note = ctx.pop("_evidence_note", "")
    base_ref = ctx.pop("_base_ref")
    d = aidd_gate.decide(ctx)
    if note and ctx.get("evidence") is None:
        for f in d.findings:
            if f.rule == "tests" and f.level == "pending":
                f.message += f" ({note})"
    return ctx, d, base_ref


_RANK = {"pass": 0, "pending": 1, "fail": 2}


def _shared_head_decision(
    client: Client, repo: str, number: int, d: aidd_gate.Decision, protected: list[str], *, cwd: str, org_preset: str | None
) -> aidd_gate.Decision:
    """A commit status belongs to the commit, so a head shared by pull requests into several protected
    bases gets the worst of their decisions; otherwise a pass into a laxer base would unlock the others."""
    head_sha = d.record["head_sha"]
    siblings = [
        int(p["number"])
        for p in client.get(f"/repos/{repo}/commits/{head_sha}/pulls") or []
        if p.get("state") == "open"
        and int(p["number"]) != number
        and (p.get("head") or {}).get("sha") == head_sha
        and any(fnmatch.fnmatchcase((p.get("base") or {}).get("ref", ""), b) for b in protected)
    ]
    worst = d
    for other in siblings:
        _, od, obase = _evaluate(client, repo, other, cwd=cwd, org_preset=org_preset)
        if _RANK[od.decision] > _RANK[worst.decision]:
            od.record["shared_with"] = f"#{other} -> {obase}"
            worst = od
    return worst


def _post_error(client: Client, repo: str, number: int, exc: Exception, run_url: str, protected: list[str], mode: str, group: MergeGroup | None = None) -> None:
    try:
        if group:
            sha, base_ref = group.sha, group.base_ref
        else:
            pr = client.get(f"/repos/{repo}/pulls/{number}")
            sha, base_ref = pr["head"]["sha"], pr["base"]["ref"]
        status = {"state": "error", "context": status_context(base_ref, protected, mode), "description": f"aidd gate error: {type(exc).__name__}"[:140]}
        client.post(f"/repos/{repo}/statuses/{urllib.parse.quote(sha, safe='')}", status | {"target_url": run_url})
    except Exception as again:  # the run itself fails, which a required check also blocks on
        print(f"PR #{number}: could not post the error status: {again}")


_REMOTE = re.compile(r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
BOT_NOTE = (
    "aidd never counts an approval from an account in identities.bots, and counts any other bot only when owners.approvers names it. "
    "GitHub's own review count takes an approval from any account with write access, a GitHub App or an agent's token included. "
    "Copilot code review only comments, so it never approves"
)


def _person_token(login: str | None = None) -> str | None:
    """The person's token: GH_TOKEN or GITHUB_TOKEN when set, else `gh`'s, for `login` when named (one of its
    accounts), else for its active account."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    out = _gh(["auth", "token", "--user", login]) if login else None
    if out is None:  # no account named, or a gh too old for `--user`: its active account
        out = _gh(["auth", "token"])
    return (out.strip() or None) if out is not None else None


def _gh(argv: list[str]) -> str | None:
    """What `gh <argv>` prints, or None when gh is missing or fails."""
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        p = subprocess.run([gh, *argv], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def approver_login(pool: list[str]) -> str | None:
    """The first Approver login in `pool` that `gh` holds a token for (`gh auth token --user`, read from this machine
    only), or None: aidd acts as that account whichever is active, so a second account signed in on the same machine
    never stands in the way. None too when GH_TOKEN or GITHUB_TOKEN decides, or for a team entry (`@org/team`)."""
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return None
    logins = [n for a in pool if (n := config.normalize_identity(str(a))) and "/" not in n and ":" not in n]
    return next((login for login in logins if (_gh(["auth", "token", "--user", login]) or "").strip()), None)


def not_an_approver_problem(login: str, pool: list[str]) -> str:
    """Why @`login`, the account aidd signed in as, cannot approve here, and the one step that fixes it."""
    return (
        f"GitHub knows you as @{login}, who is not an Approver here ({', '.join(map(str, pool)) or 'nobody'}), and gh holds no "
        "token for one. Sign in as an Approver with `gh auth login` (gh keeps each account, and aidd uses the Approver "
        "whichever is active), then run this again"
    )


@dataclass(frozen=True)
class PullRequest:
    """Where a person's approval goes on GitHub: the branch's open pull request, its head, and who the token signs in as."""

    repo: str
    number: int
    url: str
    head_sha: str
    login: str


def _person_client(login: str | None = None) -> Client | str:
    """A client with the person's own token (GH_TOKEN, GITHUB_TOKEN, or `gh auth token`, for `login` when named), or
    why there is none."""
    if os.environ.get("AIDD_OFFLINE") == "1":
        return "offline (AIDD_OFFLINE=1): aidd cannot reach GitHub to post your approval"
    token = _person_token(login)
    if not token:
        return "no GitHub token: run `gh auth login` (or set GH_TOKEN), then approve again"
    return Client(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))


def approval_target(root: str, branch: str, pool: list[str], *, client: Client | None = None) -> tuple[PullRequest | None, str | None]:
    """The pull request a person's approval of `branch` goes on, or None and why it cannot. The gate on GitHub counts
    an Approver's comment or review there, never this machine's ledger; so the token's login must be in the pool (a
    team entry is left to the gate, which resolves it)."""
    repo = origin_repo(root)
    if not repo:
        return None, "`origin` is not a github.com repository, so aidd cannot post the approval: post the line on the PR/MR yourself"
    made = client or _person_client(approver_login(pool))
    if isinstance(made, str):
        return None, made
    try:
        login = str((made.get("/user") or {}).get("login") or "")
        pulls = made.get(f"/repos/{repo}/pulls", {"head": f"{repo.split('/')[0]}:{branch}", "state": "open"}) or []
    except http.HttpError as exc:
        return None, f"GitHub answered: {exc}"
    if not pulls:
        return None, f"{branch} has no open pull request on {repo}: open one (`gh pr create`), then approve"
    names = {config.normalize_identity(str(a)) for a in pool}
    if config.normalize_identity(login) not in names and not any("/" in n for n in names):
        return None, not_an_approver_problem(login, pool)
    pr = pulls[0]
    return PullRequest(repo, int(pr["number"]), str(pr.get("html_url") or ""), str((pr.get("head") or {}).get("sha") or ""), login), None


def person_login(pool: list[str] | None = None, *, client: Client | None = None) -> tuple[str | None, str | None]:
    """The GitHub login of the person whose token this machine holds (`gh`): the account `pool` lists when gh holds
    one (approver_login), else the active one; or None and why it cannot be read."""
    made = client or _person_client(approver_login(pool or []))
    if isinstance(made, str):
        return None, made
    try:
        login = str((made.get("/user") or {}).get("login") or "")
    except http.HttpError as exc:
        return None, f"GitHub answered: {exc}"
    return (login, None) if login else (None, "GitHub did not say who you are")


def post_spec_approval(pr: PullRequest, line: str, *, client: Client | None = None) -> str:
    """Post the Spec approval line on the pull request as the person approval_target named; the comment's URL."""
    made = client or _person_client(pr.login)
    if isinstance(made, str):
        raise RuntimeError(made)
    return str((made.post(f"/repos/{pr.repo}/issues/{pr.number}/comments", {"body": line}) or {}).get("html_url") or pr.url)


def approve_pull_request(pr: PullRequest, head: str, body: str, *, client: Client | None = None) -> str:
    """Approve the pull request's `head` as the person approval_target named (a review that names the commit); the
    review's URL."""
    made = client or _person_client(pr.login)
    if isinstance(made, str):
        raise RuntimeError(made)
    review = made.post(f"/repos/{pr.repo}/pulls/{pr.number}/reviews", {"event": "APPROVE", "commit_id": head, "body": body})
    return str((review or {}).get("html_url") or pr.url)


AUTO_MERGE = "mutation($id: ID!) { enablePullRequestAutoMerge(input: {pullRequestId: $id}) { clientMutationId } }"


def enable_auto_merge(pr: PullRequest, *, client: Client | None = None) -> str | None:
    """Turn on the pull request's auto-merge as the person approval_target named, so GitHub merges it once every
    required check passes: None when it is on, else why not (`aidd/gate` is not required on the base branch, the
    repository allows no auto-merge, or GitHub said no). Only where the base branch requires `aidd/gate`: elsewhere
    auto-merge could merge a head the gate fails."""
    made = client or _person_client(pr.login)
    if isinstance(made, str):
        return made
    try:
        found = made.get(f"/repos/{pr.repo}/pulls/{pr.number}")
        found = found if isinstance(found, dict) else {}
        base = str((found.get("base") or {}).get("ref") or "")
        if not base or not _gate_required(made, pr.repo, base):
            return f"`{STATUS_CONTEXT}` is not a required check on {base or 'the base branch'}, so GitHub could merge before the gate passes; `aidd doctor` says how to require it"
        answer = made.post("/graphql", {"query": AUTO_MERGE, "variables": {"id": found.get("node_id")}}) or {}
    except (http.HttpError, OSError, ValueError, AttributeError, TypeError) as exc:  # an answer of another shape says no
        return f"GitHub answered: {exc}"
    errors = answer.get("errors") if isinstance(answer, dict) else None
    return "; ".join(str((e or {}).get("message") or e) for e in errors) if errors else None


def _gate_required(client: Client, repo: str, branch: str) -> bool:
    """Whether `branch` requires the `aidd/gate` status, by a ruleset or by classic branch protection."""
    name = urllib.parse.quote(branch, safe="")
    rules = client.get(f"/repos/{repo}/rules/branches/{name}") or []
    checks = [c for r in rules if r.get("type") == "required_status_checks" for c in (r.get("parameters") or {}).get("required_status_checks") or []]
    if any(c.get("context") == STATUS_CONTEXT for c in checks):
        return True
    required = ((client.get(f"/repos/{repo}/branches/{name}") or {}).get("protection") or {}).get("required_status_checks") or {}
    return STATUS_CONTEXT in (required.get("contexts") or []) or any(c.get("context") == STATUS_CONTEXT for c in required.get("checks") or [])


def origin_repo(root: str = ".") -> str | None:
    """The `owner/name` of the repository's `origin` remote on github.com, or None."""
    try:
        url = git.run(["remote", "get-url", "origin"], root, check=False).strip()
    except (git.GitError, OSError):
        return None
    m = _REMOTE.match(url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def protection_checks(root: str, *, client: Client | None = None) -> list[tuple[str, str]]:
    """`aidd doctor`, best effort: does the default branch's protection let the gate decide?

    Only for an `origin` on github.com, with a token (GH_TOKEN, GITHUB_TOKEN, or `gh auth token`); offline or
    without one it says it skipped. AIDD_OFFLINE=1, and AIDD_HOOK_OFFLINE=1 inside a hook, skip it before any request. Warns when the rules do not require `aidd/gate` (so GitHub's review count, which
    takes a bot's approval, decides alone), when `aidd/gate` is not pinned to an App, when an App may bypass the
    rules, and when a merge queue merges groups whose every entry did not pass."""
    repo = origin_repo(root)
    if not repo:
        return []
    if client is None:
        token = _person_token()
        if not token:
            return [("ok", f"GitHub protection of {repo} not checked: no token (set GH_TOKEN, or `gh auth login`)")]
        if "1" in (os.environ.get("AIDD_OFFLINE"), os.environ.get("AIDD_HOOK_OFFLINE")):
            return [("ok", f"GitHub protection of {repo} not checked: offline (AIDD_OFFLINE=1 or a hook)")]
        client = Client(token, "https://api.github.com")
    try:
        branch = client.get(f"/repos/{repo}")["default_branch"]
        found = client.get(f"/repos/{repo}/rules/branches/{urllib.parse.quote(branch, safe='')}") or []
    except (http.HttpError, OSError, KeyError, ValueError) as exc:
        why = f"HTTP {exc.status}" if isinstance(exc, http.HttpError) and exc.status else type(exc).__name__
        return [("ok", f"GitHub protection of {repo} not checked: {why} (offline, or the token cannot read the repository's rules)")]
    checks = [c for r in found if r.get("type") == "required_status_checks" for c in (r.get("parameters") or {}).get("required_status_checks") or []]
    reviews = [r.get("parameters") or {} for r in found if r.get("type") == "pull_request"]
    counted = max((int(p.get("required_approving_review_count") or 0) for p in reviews), default=0)
    out: list[tuple[str, str]] = []
    gate = [c for c in checks if c.get("context") == STATUS_CONTEXT]
    if not gate:
        why = f"; its rules require {counted} approval(s). {BOT_NOTE}" if counted else ""
        out.append(("warn", f"{repo}: the rules on {branch} do not require the `{STATUS_CONTEXT}` status, so the gate decides nothing{why}"))
    elif not all(c.get("integration_id") for c in gate):
        out.append(
            ("warn", f"{repo}: `{STATUS_CONTEXT}` is required on {branch} from any source; pin it to your aidd App, or anyone with write access can post it")
        )
    else:
        out.append(
            ("ok", f"{repo}: {branch} requires `{STATUS_CONTEXT}` from a pinned App" + (f"; GitHub's review count is extra. {BOT_NOTE}" if counted else ""))
        )
    if reviews and not any(p.get("require_last_push_approval") for p in reviews):
        out.append(("warn", f'{repo}: turn on "Require approval of the most recent reviewable push" on {branch}, so whoever pushed last cannot approve'))
    for r in found:
        if r.get("type") == "merge_queue" and (r.get("parameters") or {}).get("grouping_strategy") != "ALLGREEN":
            out.append(("warn", f'{repo}: the merge queue on {branch} can merge an entry that failed; turn on "Only merge non-failing pull requests"'))
    for rid in sorted({r["ruleset_id"] for r in found if isinstance(r.get("ruleset_id"), int)}):
        try:
            actors = client.get(f"/repos/{repo}/rulesets/{rid}").get("bypass_actors") or []
        except (http.HttpError, OSError, ValueError):
            continue  # bypass actors are visible to admins only
        if any(a.get("actor_type") == "Integration" for a in actors):
            out.append(("warn", f"{repo}: ruleset {rid} lets a GitHub App bypass it, so an agent's App could merge past `{STATUS_CONTEXT}`"))
    return out + _goal_protection(root, repo, client)


# What a goal branch's rules must block: a goal holds integrated Specs, which nobody may rewrite or delete.
GOAL_RULES = {"non_fast_forward": "force pushes", "deletion": "deletion"}


def _goal_protection(root: str, repo: str, client: Client) -> list[tuple[str, str]]:
    """A warning when a goal branch this clone has is not protected on GitHub against force pushes and deletion
    (templates/github/rulesets/goal.json); nothing when there is no goal branch, or the rules cannot be read."""
    from aidd import workitems

    goals = workitems.goal_branches(root)
    if not goals:
        return []
    try:
        found = client.get(f"/repos/{repo}/rules/branches/{urllib.parse.quote(goals[0], safe='')}") or []
    except (http.HttpError, OSError, ValueError):
        return []
    missing = [what for kind, what in GOAL_RULES.items() if not any(r.get("type") == kind for r in found)]
    if not missing:
        return [("ok", f"{repo}: {goals[0]} blocks force pushes and deletion")]
    return [
        (
            "warn",
            f"{repo}: the rules on {goals[0]} allow {' and '.join(missing)}, so a goal's integrated Specs could be rewritten or lost. "
            "Import templates/github/rulesets/goal.json (Settings → Rules → Rulesets → Import a ruleset)",
        )
    ]


def _append_line(path: str, event: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


# A GitHub `owner/name`: the owner's letters, digits, and inner hyphens; the name's letters, digits, `.`, `_`, and `-`,
# never `.` or `..` alone. `project.repo` pins it on the base branch (config.schema.json).
GITHUB_REPO_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$")


def spec_approval_holds(root: str, spec_id: str, *, pinned: str | None, spec_hash: str | None, client: Client | None = None) -> bool:
    """Autopilot: whether Spec approval holds for `spec_id` as the gate decides it on this branch's open
    pull request, from the platform's own approval lines and reviews (`build_context`, then `gate.decide`, as CI runs them).

    It trusts only the repository a person pinned on the base branch (`pinned`, `project.repo`): `origin` is local
    git config, which an agent can change. True only when `origin` is that repository, the pull request's head is this
    working tree's HEAD, the gate judged this Spec at this Spec hash (`spec_hash`, the local one), and found no Spec
    approval pending or failing. `build_context` fetches the pull request's head and base into `refs/aidd/*`. False
    without a pinned repository or a token, offline (AIDD_OFFLINE=1, or AIDD_HOOK_OFFLINE=1 in a hook), with no open pull
    request, on any mismatch, or on any error: autopilot then asks a person."""
    repo = origin_repo(root)
    if not repo or not pinned or not spec_hash or not GITHUB_REPO_NAME.match(pinned) or repo.lower() != pinned.lower():
        return False
    if client is None:
        if "1" in (os.environ.get("AIDD_OFFLINE"), os.environ.get("AIDD_HOOK_OFFLINE")):
            return False
        token = _person_token()
        if not token:
            return False
        client = Client(token, "https://api.github.com")
    branch = git.run(["rev-parse", "--abbrev-ref", "HEAD"], root, check=False).strip()
    head = git.run(["rev-parse", "HEAD"], root, check=False).strip()
    if not branch or branch == "HEAD" or not _SHA.match(head):
        return False
    try:
        prs = client.get(f"/repos/{pinned}/pulls", {"head": f"{pinned.split('/')[0]}:{branch}", "state": "open"})
        if not isinstance(prs, list) or len(prs) != 1 or not isinstance(prs[0], dict):
            return False
        if (prs[0].get("head") or {}).get("sha") != head:
            return False  # the pull request holds another head: what was approved is not what is here
        d = aidd_gate.decide(build_context(client, pinned, int(prs[0]["number"]), cwd=root))
        record = d.record if isinstance(d.record, dict) else {}
        findings = record.get("findings")
        if not isinstance(findings, list):
            return False
        return (
            str(record.get("spec_id") or "") == spec_id
            and record.get("head_sha") == head
            and record.get("spec_hash") == spec_hash
            and not any(not isinstance(f, dict) or (f.get("rule") == "spec_approval" and f.get("level") in ("fail", "pending")) for f in findings)
        )
    except Exception:  # noqa: BLE001  # any doubt is a person's decision, never a cleared Spec
        return False
