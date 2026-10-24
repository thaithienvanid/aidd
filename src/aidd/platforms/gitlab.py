"""GitLab adapter: gather a context for one merge request in an MR pipeline, verify, and report.

GitLab runs the MR's own .gitlab-ci.yml, so enforce this job through a
pipeline execution policy (GitLab Ultimate) or a compliance pipeline, and keep
the platform's approval rules on ("Prevent approval by author", "Prevent
approvals by users who add commits", "Remove all approvals when commits are
added"). Fork MR pipelines fail closed. A new target branch (a system note) voids
the approvals given before it.

Merge trains: in a train pipeline (CI_MERGE_REQUEST_EVENT_TYPE is merge_train) the
gate judges the merge request as usual, with approvals bound to its head, and the
car's commit, the train ref `refs/merge-requests/<iid>/train`, as GitHub's merge
queue judges a merge-group commit. The tests must have re-run on that commit, and
its tree must be exactly the approved head merged onto the commit the car was built
on: the target branch, or the car ahead (`merge_results.train_parent`).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
from pathlib import Path

from aidd import config
from aidd import gate as aidd_gate
from aidd.kernel import git, http
from aidd.kernel.processes import require_env
from aidd.kernel.timestamps import EPOCH, parse_time
from aidd.platforms.merge_results import COMMIT_SHA, MERGE_QUEUE_REF, merged_tree, train_parent

STATUS_NAME = "aidd/gate"
MAX_COMMITS = 500


class Client(http.JsonClient):
    def _auth(self):
        return ("PRIVATE-TOKEN", self.token) if self.token else None

    def post(self, path: str, params: dict):
        _, _, body = self._request("POST", http.with_params(self.api + path, params), auth=self._auth(), max_bytes=http.MAX_API_BYTES)
        return json.loads(body or b"null")

    def post_json(self, path: str, data: dict):
        """A POST whose fields go as a JSON body, for text such as a note's body that does not belong in a URL."""
        _, _, body = self._request("POST", self.api + path, auth=self._auth(), data=data, max_bytes=http.MAX_API_BYTES)
        return json.loads(body or b"null")


MAX_GROUP_LOOKUPS = 50
# Users whose `bot` flag one gate run reads (GET /users/:id), the approvers' and commenters' first, then group members.
MAX_USER_LOOKUPS = 250
# The bot user GitLab makes for a project or group access token: project_{id}_bot_{random} or group_{id}_bot_{random}.
# A group's bot is a member of the group, so a group in a pool would otherwise name it.
ACCESS_TOKEN_BOT = re.compile(r"^(?:project|group)_[0-9]+_bot(?:_[0-9a-z]+|[0-9]*)$", re.I)


class People:
    """Which GitLab accounts are people. Only GET /users/:id says whether an account is a bot (a service account, an
    access token's bot, or one of GitLab's own); a merge request's notes and a group's members never do. So an account
    is a person only when that lookup answers `bot: false`. A failed lookup, a missing field, or one past
    MAX_USER_LOOKUPS makes it no person (fail closed)."""

    def __init__(self, client: Client) -> None:
        self.client = client
        self.known: dict[int, bool] = {}

    def person(self, user: dict) -> bool:
        uid, name = user.get("id"), str(user.get("username") or "")
        if not isinstance(uid, int) or isinstance(uid, bool) or not name or ACCESS_TOKEN_BOT.match(name):
            return False
        if uid not in self.known:
            if len(self.known) >= MAX_USER_LOOKUPS:
                return False
            try:
                found = self.client.get(f"/users/{uid}") or {}
            except http.HttpError:
                found = {}
            self.known[uid] = isinstance(found, dict) and found.get("bot") is False
        return self.known[uid]

    def recorded(self, user: dict) -> str:
        """The username the context records: a bot's as GitHub names one, `<username>[bot]`, so the gate never counts
        its approval, or its approval line, unless a pool names it so."""
        name = str(user.get("username") or "")
        return name if self.person(user) else f"{name}[bot]"


def _group_members(client: Client, entries: list[str], people: People | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """Each group entry's members who are people, and the entries a member was left out of because GitLab did not say
    they are a person: that pool is smaller than the group, so an approval from one never counts."""
    people = people or People(client)
    out: dict[str, list[str]] = {}
    shrunk: list[str] = []
    # A tenant-qualified entry (`acme:@org/team`) is looked up without its tenant and kept under the entry as written.
    groups = [(e, config.split_tenant(e)[1]) for e in entries]
    groups = [(e, name) for e, name in groups if "/" in name and not name.startswith("email:")]
    for e, name in groups[:MAX_GROUP_LOOKUPS]:  # pool entries can come from the change's own Spec: cap the lookups
        try:
            members = [m for m in client.paginate(f"/groups/{urllib.parse.quote(name, safe='')}/members/all") if isinstance(m, dict)]
        except http.HttpError:
            continue
        # Those already looked up (the approvers and commenters) first, so the cap never drops one who approved.
        members.sort(key=lambda m: m.get("id") not in people.known)
        out[e] = [str(m["username"]) for m in members if people.person(m)]
        if len(out[e]) < len(members):
            shrunk.append(e)
    return out, shrunk


def _head_at(versions: list[dict], when) -> str | None:
    """The merge request's head at a moment: the newest diff version created at or before it."""
    best = None
    for v in versions:
        t = parse_time(v.get("created_at"))
        if t is not None and when is not None and t <= when and (best is None or t >= best[0]):
            best = (t, v.get("head_commit_sha"))
    return best[1] if best else None


def _approvals(notes: list[dict], pushed_at: str | None, head_sha: str, versions: list[dict] | None = None) -> list[dict]:
    """GitLab records approve and unapprove as system notes; the latest per user wins.

    An approval binds to head only when it came after this head's pipeline was created. An earlier approval names the
    head the merge request had then (its diff versions), so the gate can decide whether a trivial rebase carries it.
    Times are compared as instants, never as strings (GitLab mixes `.123Z` and offsets).
    """
    pushed = parse_time(pushed_at)
    state: dict[str, dict] = {}
    for n in sorted(notes, key=lambda n: parse_time(n.get("created_at")) or EPOCH):
        if not n.get("system"):
            continue
        body = (n.get("body") or "").strip().lower()
        user = n["author"]["username"]
        if body.startswith("approved this merge request"):
            created = parse_time(n.get("created_at"))
            bound = pushed is not None and created is not None and created >= pushed
            earlier = None if bound else _head_at(versions or [], created)
            sha = head_sha if bound else (earlier if earlier and earlier != head_sha else None)
            state[user] = {"user": user, "state": "approved", "commit_sha": sha, "submitted_at": n.get("created_at")}
        elif body.startswith("unapproved this merge request"):
            state[user] = {"user": user, "state": "dismissed", "commit_sha": None, "submitted_at": n.get("created_at")}
    return list(state.values())


# GitLab's system notes for a new target branch: set by a person ("changed target branch from `a` to `b`"), or by
# GitLab when the old target was merged or deleted ("changed automatically target branch to `b` because ...").
_RETARGET = re.compile(r"^(?:changed (?:automatically )?target branch\b|.*\bnow targets the\b)", re.I)


def _by_whom_matters(note: dict) -> bool:
    """A note whose author the gate weighs: a comment, which can carry an approval line, or an approval system note."""
    body = (note.get("body") or "").strip().lower()
    return not note.get("system") or body.startswith(("approved this merge request", "unapproved this merge request"))


def _base_changed_at(notes: list[dict]) -> str | None:
    """When the merge request was last retargeted to another branch, from its system notes; None if never."""
    found = [
        (t, n.get("created_at"))
        for n in notes
        if n.get("system") and _RETARGET.match((n.get("body") or "").strip())
        for t in [parse_time(n.get("created_at"))]
        if t
    ]
    return max(found)[1] if found else None


def _approval_settings(client: Client, project: str) -> dict:
    """The project's approval settings, or {} when they cannot be read."""
    try:
        settings = client.get(f"/projects/{project}/approvals") or {}
    except http.HttpError:
        return {}
    return settings if isinstance(settings, dict) else {}


def _committers_blocked(settings: dict) -> bool:
    """Whether the project stops commit authors from approving, which covers commit emails the API cannot map."""
    return bool(settings.get("merge_requests_disable_committers_approval")) and not settings.get("merge_requests_author_approval")


def _reset_on_push(settings: dict) -> bool | None:
    """Whether the project removes approvals when commits are pushed; None when the setting is not reported."""
    value = settings.get("reset_approvals_on_push")
    return value if isinstance(value, bool) else None


def _commit_verified(client: Client, project: str, sha: str) -> bool:
    """Whether GitLab reports this commit's signature as verified. Unsigned commits 404."""
    try:
        sig = client.get(f"/projects/{project}/repository/commits/{sha}/signature") or {}
    except http.HttpError:
        return False
    return sig.get("verification_status") == "verified"


def _commits(
    client: Client, project: str, iid: int, *, signatures: bool = False, local: dict | None = None, limit: int = MAX_COMMITS
) -> tuple[list[dict], bool]:
    """Every merge-request commit, or ([], True) when the list exceeds `limit`. Signature lookups run only
    when `signatures` is set (a config with standard_changes), because they cost one request per commit."""
    try:
        raw = client.paginate(f"/projects/{project}/merge_requests/{iid}/commits", limit=limit, strict=True)
    except http.PageLimitError:
        return [], True
    local = local or {}
    return [
        {
            "sha": c["id"],
            "author": f"email:{c.get('author_email', '')}",
            "committer": f"email:{c.get('committer_email', '')}",
            "message": c.get("message") or c.get("title", ""),
            "merge": local.get(c["id"], {}).get("merge", False),
            "verified": _commit_verified(client, project, c["id"]) if signatures else False,
        }
        for c in raw
    ], False


def _versions(client: Client, project: str, iid: int) -> list[dict]:
    """The merge request's diff versions, which name the head an earlier approval saw. All of them or none: a cut list
    could map an approval to the wrong head, and without them an earlier approval names no head, so it never carries."""
    try:
        found = client.paginate(f"/projects/{project}/merge_requests/{iid}/versions", limit=500, strict=True)
    except (http.HttpError, http.PageLimitError):
        return []
    return [v for v in found if isinstance(v, dict)] if isinstance(found, list) else []


def _pushed_at(versions: list[dict], head_sha: str) -> str | None:
    """When the merge request last got this head: the first of the newest diff versions that all name it. None when
    the newest version names another head, or any version has no time: their order is then unknown, so no approval
    binds. A head pushed, replaced, and pushed again counts from its last push, so an approval of the head between
    never binds to it."""
    timed = [(parse_time(v.get("created_at")), v) for v in versions]
    if any(t is None for t, _ in timed):
        return None
    dated = sorted(timed, key=lambda tv: tv[0] or EPOCH)
    since = None
    for _, v in reversed(dated):
        if v.get("head_commit_sha") != head_sha:
            break
        since = v.get("created_at")
    return since


def _train_car(cwd: str, iid: int, train_sha: str, head_sha: str, base_tip: str) -> dict:
    """The merge-train car this pipeline tests, as the gate's `merge_queue` entry: its commit, which must still be what the
    train ref names, the commit it was built on, and both trees. GitLab merges a car only once its own pipeline
    passed and every car ahead merged, and a car ahead that fails leaves the train and restarts the cars behind it,
    so a failing car never merges with this one (`all_green`)."""
    if git.rev_parse(MERGE_QUEUE_REF, cwd) != train_sha:
        raise RuntimeError(f"the merge train ref of MR !{iid} no longer points at {train_sha[:12]}; GitLab rebuilt the train, and the new pipeline decides")
    parent, stacked = train_parent(cwd, train_sha, head_sha, base_tip)
    return {
        "sha": train_sha,
        "ref": f"refs/merge-requests/{iid}/train",
        "base_sha": parent,
        "stacked": stacked,
        "tree": git.run(["rev-parse", "--verify", f"{train_sha}^{{tree}}"], cwd).strip(),
        "merged_tree": merged_tree(cwd, parent, head_sha),
        "all_green": True,
    }


def build_context(
    client: Client,
    project: str,
    iid: int,
    *,
    cwd: str = ".",
    evidence_path: str | None = None,
    org_preset: str | None = None,
    train_sha: str | None = None,
    left_out: list[str] | None = None,
) -> dict:
    """The trusted context for a merge request; with `train_sha`, for its merge-train car (approvals still bind to the
    head). `left_out` gets each group pool entry a member was left out of, because GitLab did not say they are a person."""
    mr = client.get(f"/projects/{project}/merge_requests/{iid}")
    head_sha = mr["sha"]
    target = mr["target_branch"]
    refspecs = [f"+refs/heads/{target}:refs/aidd/base", f"+refs/merge-requests/{iid}/head:refs/aidd/mr-head"]
    if train_sha:
        refspecs.append(f"+refs/merge-requests/{iid}/train:{MERGE_QUEUE_REF}")
    git.fetch(cwd, refspecs)
    base_tip = git.rev_parse("refs/aidd/base", cwd)
    entry = _train_car(cwd, iid, train_sha, head_sha, base_tip) if train_sha else None
    # A car's diff is the merge request's as it enters the train: from where it meets the car's parent.
    base_sha = git.merge_base(entry["base_sha"] if entry else base_tip, head_sha, cwd)
    body = mr.get("description") or ""
    files = git.numstat(base_sha, head_sha, cwd)
    decl = aidd_gate.declared_inputs(cwd, base_tip, head_sha, body, org_preset=org_preset)
    cfg = decl["config"]
    versions = _versions(client, project, iid)
    # A train pipeline starts when the car joins the train, after the approvals: the head's own diff version says when
    # the merge request got it. Any other pipeline is the head's own, created when it was pushed.
    pushed_at = _pushed_at(versions, head_sha) if train_sha else os.environ.get("CI_PIPELINE_CREATED_AT")
    local = {c["sha"]: c for c in git.commits(base_sha, head_sha, cwd)}
    need_signatures = bool(cfg.get("standard_changes", default=[]) if cfg else [])
    commits, commits_truncated = _commits(client, project, iid, signatures=need_signatures, local=local)
    raw_notes = client.paginate(f"/projects/{project}/merge_requests/{iid}/notes", {"sort": "asc", "order_by": "created_at"}, strict=True)
    # A bot's note is recorded under `<username>[bot]`: its approval and its approval lines never count as a person's.
    people = People(client)
    notes = [n | {"author": {**n["author"], "username": people.recorded(n["author"])}} if _by_whom_matters(n) else n for n in raw_notes]
    comments = [aidd_gate.recorded_comment(n["author"]["username"], n) for n in notes if not n.get("system")]
    team_members, shrunk = _group_members(client, decl["pools"], people)
    if left_out is not None:
        left_out.extend(shrunk)
    settings = _approval_settings(client, project)
    evidence = None
    if evidence_path and os.path.isfile(evidence_path):
        with open(evidence_path, encoding="utf-8") as fh:
            evidence = json.load(fh)
    ctx = {
        "platform": "gitlab",
        "trusted": True,
        "repo": os.environ.get("CI_PROJECT_PATH", str(project)),
        "now": dt.datetime.now(dt.UTC).isoformat(),
        "change": {
            "id": str(iid),
            "url": mr.get("web_url", ""),
            "author": mr["author"]["username"],
            "body": body,
            "head_ref": str(mr.get("source_branch") or ""),
            "draft": bool(mr.get("draft") or mr.get("work_in_progress")),
            "created_at": mr.get("created_at"),
        },
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_pushed_at": pushed_at,
        "base_changed_at": _base_changed_at(notes),
        "files": files,
        "commits": commits,
        "commits_truncated": commits_truncated,
        "reviews": _approvals(notes, pushed_at, head_sha, versions),
        "comments": comments,
        "evidence": evidence,
        "committer_approval_blocked": _committers_blocked(settings),
        "approvals_reset_on_push": _reset_on_push(settings),
    }
    for earlier in aidd_gate.approved_heads(ctx, head_sha):  # an earlier head a force-push replaced: fetch it by id, best effort
        if not git.ok(["cat-file", "-e", f"{earlier}^{{commit}}"], cwd):
            try:
                git.fetch(cwd, [earlier])
            except git.GitError:
                pass
    ctx |= aidd_gate.adapter_fields(ctx, cwd, decl, base_tip, team_members, org_preset)
    if entry:
        ctx["merge_queue"] = entry
    return ctx


def post_status(client: Client, project: str, d: aidd_gate.Decision, target_url: str, name: str = STATUS_NAME) -> None:
    """Post the decision on the head, or on the merge-train car's commit the decision judged."""
    state = {"pass": "success", "fail": "failed", "pending": "pending"}[d.decision]
    head_sha = urllib.parse.quote(d.record.get("merge_queue_sha") or d.record["head_sha"] or "", safe="")
    client.post(f"/projects/{project}/statuses/{head_sha}", {"state": state, "name": name, "description": aidd_gate.status_line(d), "target_url": target_url})


def gitlab_gate(
    *,
    dry_run: bool = False,
    cwd: str = ".",
    evidence_path: str = f"{config.EVIDENCE_DIR}/evidence.json",
    events_out: str | None = None,
    record_out: str | None = None,
    pending_fails: bool = True,
    post: bool = False,
    mode: str | None = None,
    html_out: str | None = None,
) -> int:
    iid = os.environ.get("CI_MERGE_REQUEST_IID")
    if not iid:
        print("aidd gate: not a merge request pipeline; nothing to do")
        return 0
    train_sha = None
    if os.environ.get("CI_MERGE_REQUEST_EVENT_TYPE") == "merge_train":
        # A train pipeline tests the car's commit: the MR's head merged onto the cars ahead of it, or the target.
        train_sha = os.environ.get("CI_COMMIT_SHA") or ""
        if not COMMIT_SHA.match(train_sha) or not COMMIT_SHA.match(os.environ.get("CI_MERGE_REQUEST_SOURCE_BRANCH_SHA") or ""):
            print(
                f"aidd gate: MR !{iid} runs in a merge train, but the pipeline names no train commit (CI_COMMIT_SHA) or MR head "
                "(CI_MERGE_REQUEST_SOURCE_BRANCH_SHA); failing closed. Remove the MR from the train and add it again."
            )
            return 1
    if train_sha:
        try:
            checked_out = git.rev_parse("HEAD", cwd)
        except git.GitError:
            checked_out = ""
        if checked_out != train_sha:
            print(
                f"aidd gate: MR !{iid} runs in a merge train, but the checkout is {checked_out[:12] or '(none)'}, not the train's commit "
                f"{train_sha[:12]} (CI_COMMIT_SHA); failing closed. Run the gate job on the pipeline's own checkout of the train's commit, then retry the job."
            )
            return 1
    this_project = require_env("CI_PROJECT_ID", "aidd gate gitlab runs inside a GitLab merge request pipeline")
    target = os.environ.get("CI_MERGE_REQUEST_PROJECT_ID", this_project)
    if target != this_project:
        # A fork's pipeline runs the fork's CI config and branches; nothing it reports is trustworthy.
        print("aidd gate: this pipeline runs in a fork, where the gate cannot be enforced; failing closed. Run merge request pipelines in the parent project.")
        return 1
    # A pipeline variable is untrusted: anyone who may run a pipeline can set AIDD_MODE. Until the
    # base branch's config is read, the gate enforces; only that config can make it advisory.
    requested = mode or os.environ.get("AIDD_MODE")
    mode = config.effective_mode(None, requested, input_trusted=False)
    project = urllib.parse.quote(target, safe="")
    client = Client(os.environ.get("AIDD_GITLAB_TOKEN", ""), os.environ.get("CI_API_V4_URL", "https://gitlab.com/api/v4"))
    left_out: list[str] = []
    ctx = build_context(
        client, project, int(iid), cwd=cwd, evidence_path=evidence_path, org_preset=config.org_preset_text(), train_sha=train_sha, left_out=left_out
    )
    # Approvals bind to this pipeline's creation time, so only the pipeline for the MR's current head may decide.
    pipeline_head = os.environ.get("CI_MERGE_REQUEST_SOURCE_BRANCH_SHA") or os.environ.get("CI_COMMIT_SHA")
    if pipeline_head and pipeline_head != ctx["head_sha"]:
        print(f"aidd gate: MR !{iid} head is {ctx['head_sha'][:12]}, this pipeline ran for {pipeline_head[:12]}; the pipeline for the current head decides")
        return 0 if mode == "advisory" else 1
    d = aidd_gate.decide(ctx)
    mode = config.effective_mode(d.record.get("config_mode"), requested, input_trusted=False, fallback=config.profile_mode(d.record.get("profile")))
    if requested == "advisory" and mode == "enforce":
        print('aidd gate: AIDD_MODE=advisory is ignored; set mode: "advisory" in the base branch\'s .aidd/config.yaml instead')
    print(f"MR !{iid} ({mode})" + (f", merge train entry {train_sha[:12]}" if train_sha else ""))
    print(aidd_gate.decision_text(d))
    if left_out:
        print(
            f"note: the pools {', '.join(left_out)} leave out members GitLab did not say are people (GET /users/:id answered no `bot: false`, "
            f"or past {MAX_USER_LOOKUPS} lookups), so an approval from one does not count, and the gate may wait. A person in the "
            "group approves instead, or, when GitLab did not answer, retry the job"
        )
    run_url = os.environ.get("CI_JOB_URL")
    if events_out:
        event = aidd_gate.decision_event(
            d, ctx["repo"], author=ctx["change"]["author"], mode=mode, base_ref=os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME"), run_url=run_url
        )
        with open(events_out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    if record_out:
        aidd_gate.write_records(d, ctx, record_out, run_url=run_url)
    if html_out is not None:
        from aidd import views

        views.write_merge_page(ctx, d, html_out, cwd=cwd, evidence_dir=Path(evidence_path).parent if Path(evidence_path).is_file() else None)
    if post and not dry_run and client.token:
        # In a train, the status goes on the car's commit, which belongs to this car alone; its tree binds it to the head.
        post_status(client, project, d, os.environ.get("CI_JOB_URL", ""), STATUS_NAME if mode == "enforce" else f"{STATUS_NAME} (advisory)")
    return 1 if mode != "advisory" and (d.decision == "fail" or (d.decision == "pending" and pending_fails)) else 0
