"""GitLab adapter: gather a context for one merge request in an MR pipeline, verify, and report.

GitLab runs the MR's own .gitlab-ci.yml, so enforce this job through a
pipeline execution policy (GitLab Ultimate) or a compliance pipeline, and keep
the platform's approval rules on ("Prevent approval by author", "Prevent
approvals by users who add commits", "Remove all approvals when commits are
added"). Fork MR pipelines fail closed.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse

from . import changerecord, config, gitutil, http, inputs, report
from .util import EPOCH, parse_time, require_env, split_tenant
from .verify import Decision, verify

STATUS_NAME = "aidd/gate"
COMMIT_LIMIT = 500


class Client(http.JsonClient):
    def _auth(self):
        return ("PRIVATE-TOKEN", self.token) if self.token else None

    def post(self, path: str, params: dict):
        _, _, body = self._request("POST", http.with_params(self.api + path, params), auth=self._auth())
        return json.loads(body or b"null")


MAX_GROUP_LOOKUPS = 50


def _group_members(client: Client, entries: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    # A tenant-qualified entry (`acme:@org/team`) is looked up without its tenant and kept under the entry as written.
    groups = [(e, split_tenant(e)[1]) for e in entries]
    groups = [(e, name) for e, name in groups if "/" in name and not name.startswith("email:")]
    for e, name in groups[:MAX_GROUP_LOOKUPS]:  # pool entries can come from the change's own Spec: cap the lookups
        try:
            out[e] = [m["username"] for m in client.paginate(f"/groups/{urllib.parse.quote(name, safe='')}/members/all")]
        except http.HttpError:
            pass
    return out


def _approvals(notes: list[dict], pushed_at: str | None, head_sha: str) -> list[dict]:
    """GitLab records approve and unapprove as system notes; the latest per user wins.

    An approval binds to head only when it came after this head's pipeline was created.
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
            state[user] = {"user": user, "state": "approved", "commit_sha": head_sha if bound else None, "submitted_at": n.get("created_at")}
        elif body.startswith("unapproved this merge request"):
            state[user] = {"user": user, "state": "dismissed", "commit_sha": None, "submitted_at": n.get("created_at")}
    return list(state.values())


def _committers_blocked(client: Client, project: str) -> bool:
    """Whether the project stops commit authors from approving, which covers commit emails the API cannot map."""
    try:
        settings = client.get(f"/projects/{project}/approvals") or {}
    except http.HttpError:
        return False
    return bool(settings.get("merge_requests_disable_committers_approval")) and not settings.get("merge_requests_author_approval")


def _commit_verified(client: Client, project: str, sha: str) -> bool:
    """Whether GitLab reports this commit's signature as verified. Unsigned commits 404."""
    try:
        sig = client.get(f"/projects/{project}/repository/commits/{sha}/signature") or {}
    except http.HttpError:
        return False
    return sig.get("verification_status") == "verified"


def _commits(
    client: Client, project: str, iid: int, *, signatures: bool = False, local: dict | None = None, limit: int = COMMIT_LIMIT
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


def build_context(client: Client, project: str, iid: int, *, cwd: str = ".", evidence_path: str | None = None, org_preset: str | None = None) -> dict:
    mr = client.get(f"/projects/{project}/merge_requests/{iid}")
    head_sha = mr["sha"]
    target = mr["target_branch"]
    gitutil.fetch(cwd, [f"+refs/heads/{target}:refs/aidd/base", f"+refs/merge-requests/{iid}/head:refs/aidd/mr-head"])
    base_tip = gitutil.rev_parse("refs/aidd/base", cwd)
    base_sha = gitutil.merge_base(base_tip, head_sha, cwd)
    body = mr.get("description") or ""
    files = gitutil.numstat(base_sha, head_sha, cwd)
    decl = inputs.declared_inputs(cwd, base_tip, head_sha, body, org_preset=org_preset)
    cfg = decl["config"]
    pushed_at = os.environ.get("CI_PIPELINE_CREATED_AT")
    local = {c["sha"]: c for c in gitutil.commits(base_sha, head_sha, cwd)}
    need_signatures = bool(cfg.get("standard_changes", default=[]) if cfg else [])
    commits, commits_truncated = _commits(client, project, iid, signatures=need_signatures, local=local)
    notes = client.paginate(f"/projects/{project}/merge_requests/{iid}/notes", {"sort": "asc", "order_by": "created_at"}, strict=True)
    comments = [inputs.comment(n["author"]["username"], n) for n in notes if not n.get("system")]
    team_members = _group_members(client, decl["pools"])
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
            "draft": bool(mr.get("draft") or mr.get("work_in_progress")),
            "created_at": mr.get("created_at"),
        },
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_pushed_at": pushed_at,
        "files": files,
        "commits": commits,
        "commits_truncated": commits_truncated,
        "reviews": _approvals(notes, pushed_at, head_sha),
        "comments": comments,
        "evidence": evidence,
        "committer_approval_blocked": _committers_blocked(client, project),
    }
    return ctx | inputs.adapter_fields(ctx, cwd, decl, base_tip, team_members, org_preset)


def post_status(client: Client, project: str, d: Decision, target_url: str, name: str = STATUS_NAME) -> None:
    state = {"pass": "success", "fail": "failed", "pending": "pending"}[d.decision]
    head_sha = urllib.parse.quote(d.record["head_sha"] or "", safe="")
    client.post(f"/projects/{project}/statuses/{head_sha}", {"state": state, "name": name, "description": report.status_line(d), "target_url": target_url})


def gate(
    *,
    dry_run: bool = False,
    cwd: str = ".",
    evidence_path: str = "aidd-evidence/evidence.json",
    events_out: str | None = None,
    record_out: str | None = None,
    pending_fails: bool = True,
    post: bool = False,
    mode: str | None = None,
) -> int:
    iid = os.environ.get("CI_MERGE_REQUEST_IID")
    if not iid:
        print("aidd gate: not a merge request pipeline; nothing to do")
        return 0
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
    ctx = build_context(client, project, int(iid), cwd=cwd, evidence_path=evidence_path, org_preset=inputs.org_preset_text())
    # Approvals bind to this pipeline's creation time, so only the pipeline for the MR's current head may decide.
    pipeline_head = os.environ.get("CI_MERGE_REQUEST_SOURCE_BRANCH_SHA") or os.environ.get("CI_COMMIT_SHA")
    if pipeline_head and pipeline_head != ctx["head_sha"]:
        print(f"aidd gate: MR !{iid} head is {ctx['head_sha'][:12]}, this pipeline ran for {pipeline_head[:12]}; the pipeline for the current head decides")
        return 0 if mode == "advisory" else 1
    d = verify(ctx)
    mode = config.effective_mode(d.record.get("config_mode"), requested, input_trusted=False)
    if requested == "advisory" and mode == "enforce":
        print('aidd gate: AIDD_MODE=advisory is ignored; set mode = "advisory" in the base branch\'s .aidd/config.toml instead')
    print(f"MR !{iid} ({mode})")
    print(report.text(d))
    run_url = os.environ.get("CI_JOB_URL")
    if events_out:
        event = report.event(
            d, ctx["repo"], author=ctx["change"]["author"], mode=mode, base_ref=os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME"), run_url=run_url
        )
        with open(events_out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    if record_out:
        changerecord.write_records(d, ctx, record_out, run_url=run_url)
    if post and not dry_run and client.token:
        post_status(client, project, d, os.environ.get("CI_JOB_URL", ""), STATUS_NAME if mode == "enforce" else f"{STATUS_NAME} (advisory)")
    return 1 if mode != "advisory" and (d.decision == "fail" or (d.decision == "pending" and pending_fails)) else 0
