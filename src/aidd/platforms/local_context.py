"""Build a gate context from a local git checkout.

Local contexts are untrusted (`trusted: False`): the machine that builds one is the machine the agent runs on.
They serve two uses. Before a PR/MR, an agent or a developer preflights a branch; that decision is advisory, and
the platform's gate decides. Local-first, with no platform, the local gate is the gate: it reads the approvals a
person recorded with `aidd approve` (workitems/approval_ledger.py), counting only signed ones when the base branch's config sets
`gates.local_approvals: signed`, and `aidd ship` merges only when it passes.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from aidd import config, gate, workitems
from aidd.kernel import documents, git, repo_paths, strict_yaml

# At most this many added lines per file go into the context, for the secrets rule.
MAX_ADDED_LINES = 5000
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


def added_lines(repo: str, base_sha: str, head_sha: str) -> dict[str, list[str]]:
    """path -> the lines the diff adds to it (text files; at most MAX_ADDED_LINES each), for the secrets rule."""
    out: dict[str, list[str]] = {}
    path: str | None = None
    diff = git.run(["-c", "core.quotePath=false", "diff", "-U0", "--no-color", "--no-ext-diff", base_sha, head_sha], repo, check=False)
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            path = target[2:] if target.startswith("b/") else None  # /dev/null, or a quoted name this reader skips
        elif line.startswith("+") and path is not None:
            lines = out.setdefault(path, [])
            if len(lines) < MAX_ADDED_LINES:
                lines.append(line[1:])
        elif line.startswith("diff --git "):
            path = None
    return out


def this_branchs_approvals(repo: str, reviews: list[dict], base_tip: str, head_sha: str) -> list[dict]:
    """The local Merge approvals that belong to this branch: of its head, of a commit in its history, or recorded on this
    branch (an earlier head a rebase replaced). An approval of a commit already on the base branch (shipped work), or one
    recorded on another branch, is another change's. The branch the record names is dropped: it is not context."""
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip()
    kept = []
    for r in reviews:
        recorded_on = r.pop("branch", None)
        sha = r.get("commit_sha") or ""
        if sha and sha != head_sha:
            if git.ok(["merge-base", "--is-ancestor", sha, base_tip], repo):
                continue
            if recorded_on is not None and recorded_on != branch and not git.ok(["merge-base", "--is-ancestor", sha, head_sha], repo):
                continue
        kept.append(r)
    return kept


def local_author(repo: str, cfg) -> str:
    """The change's author as the gate names it: `email:<user.email>`, or the login a person's git `user.name` is, when it
    is a login the config's approvers name (a preflight's approvals come as platform logins, and the author's own must
    not count)."""
    email = git.config_value("user.email", repo)
    name = git.config_value("user.name", repo).strip().lstrip("@")
    if cfg is not None and _LOGIN.fullmatch(name):
        named = {config.normalize_identity(a) for a in cfg.approvers} | {
            config.normalize_identity(a) for e in cfg.get("owners", "paths", default=[]) or [] for a in e.get("approvers", [])
        }
        if config.normalize_identity(name) in named:
            return config.normalize_identity(name)
    return f"email:{email}" if email else "local"


def spec_block(spec: str) -> str:
    return f"```yaml aidd\nspec: {strict_yaml.scalar(repo_paths.repo_path(spec))}\n```\n"


def specs_block(specs: list[str]) -> str:
    """A goal's Change Request block: the Spec paths its goal branch carries."""
    return "```yaml aidd\n" + strict_yaml.dump({"specs": [repo_paths.repo_path(s) for s in specs]}) + "```\n"


def _head_ref(repo: str, head: str) -> str:
    """The branch the local change comes from: `head` when it names a local branch, else the branch checked out when
    `head` is its commit. A bare commit (or a detached HEAD) is named by an explore branch whose tip it is, so a change
    from one never passes for a branchless one; else ""."""
    name = head.removeprefix("refs/heads/")
    if head != "HEAD" and git.ok(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], repo):
        return name
    sha = git.rev_parse(head, repo)
    if sha == git.rev_parse("HEAD", repo) and (checked_out := git.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip()):
        return checked_out
    tips = git.run(["for-each-ref", "--format=%(refname:short)", "--points-at", sha, "refs/heads/explore"], repo, check=False).split()
    return next((t for t in tips if workitems.is_explore(t)), "")


def build_local_context(
    *,
    repo: str = ".",
    base: str | None = None,
    head: str = "HEAD",
    body: str | None = None,
    spec: str | None = None,
    approvals: str | None = None,
    evidence: str | None = None,
    run_policy: bool = True,
) -> dict:
    base = base or git.default_base(repo)
    head_sha = git.rev_parse(head, repo)
    base_tip = git.rev_parse(base, repo)
    base_sha = git.merge_base(base_tip, head_sha, repo)
    files = git.numstat(base_sha, head_sha, repo)
    if body is None and spec is None:
        # No PR/MR description locally: the Change Request block the newest branch commit carries (`aidd describe --commit`).
        body = gate.commit_block(repo, base_sha, head_sha)
    if body is None:
        specs_dir = "specs"
        cfg_text = git.show(base_tip, ".aidd/config.yaml", repo) or git.show(head_sha, ".aidd/config.yaml", repo)
        if cfg_text:
            try:
                specs_dir = str(documents.parse_yaml(cfg_text, "config").get("specs_dir", "specs"))
            except documents.DocumentError:
                pass
        try:
            found = [spec] if spec else workitems.find_specs_in_diff(files, specs_dir, lambda p: git.show(head_sha, p, repo))
        except ValueError:  # specs_dir at the repository's top: the gate fails on the config itself (config.invalid)
            found = []
        # A goal branch carries its Specs together, one or more, with its plan; anywhere else, several Specs need a Change
        # Request block that says so.
        on_goal = git.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip().startswith(workitems.GOAL_PREFIX)
        spec = found[0] if len(found) == 1 and not on_goal else None
        body = spec_block(spec) if spec else specs_block(found) if found and on_goal else ""
    org = config.org_preset_text()
    decl = gate.declared_inputs(repo, base_tip, head_sha, body, org_preset=org)
    cfg = decl["config"]
    notes: list[str] = []
    if approvals:
        data = json.loads(Path(approvals).read_text(encoding="utf-8"))
        reviews, comments = data.get("reviews", []), data.get("comments", [])
    else:
        # Local-first: the approvals people recorded on this machine with `aidd approve` (see workitems/approval_ledger.py). Whether they
        # must be signed, and whose keys count, come from the base branch, never from this machine's git config.

        signed = bool(cfg) and cfg.gates.get("local_approvals") == "signed"
        reviews, comments, notes = workitems.load_local_approvals(
            repo, require_signed=signed, signers=workitems.base_signers(cfg, base_tip, repo), signers_file=workitems.signers_path(cfg)
        )
        reviews = this_branchs_approvals(repo, reviews, base_tip, head_sha)
    by_path = {f["path"]: f for f in files if not f.get("binary")}
    for path, lines in added_lines(repo, base_sha, head_sha).items() if files else ():
        entry = by_path.get(path)
        if entry is not None and lines:
            entry["added_lines"] = lines
    ev = json.loads(Path(evidence).read_text(encoding="utf-8")) if evidence and Path(evidence).is_file() else None
    ctx = {
        "platform": gate.platform_of(repo),
        "trusted": False,
        "repo": str(Path(repo).resolve().name),
        "now": dt.datetime.now(dt.UTC).isoformat(),
        "change": {"id": head, "author": local_author(repo, cfg), "body": body, "head_ref": _head_ref(repo, head), "draft": False},
        "base_sha": base_sha,
        "head_sha": head_sha,
        # Nothing is pushed locally: the head commit's committer date is the best available start for the cool-off,
        # and the committer sets it (gate_run.GateRun.cooled).
        "head_pushed_at": git.run(["log", "-1", "--format=%cI", head_sha], repo).strip() or None,
        "files": files,
        "commits": git.commits(base_sha, head_sha, repo),
        "reviews": reviews,
        "comments": comments,
        "approval_commits": gate.approval_commits(
            repo, base_sha, head_sha, comments, eligible=gate.pool_members(decl["pools"], {}), spec=gate.spec_of_change(body)
        ),
        # An approval of an earlier head counts for this one only after a trivial rebase (the gate decides); locally an
        # earlier head "reached" the platform when it was committed, as for the head (head_pushed_at).
        "approval_equivalents": gate.approval_equivalents(
            repo,
            base_tip,
            base_sha,
            head_sha,
            gate.approved_heads({"reviews": reviews, "comments": comments}, head_sha),
            pushed_at=lambda sha: git.run(["log", "-1", "--format=%cI", sha], repo, check=False).strip() or None,
        ),
        "head_tree": git.ls_tree(head_sha, repo),
        "head_files": decl["head_files"],
        "base_config": decl["base_config"],
        "extends_texts": decl["extends_texts"],
        "codeowners": decl["codeowners"],
        "org_preset": org,
        "team_members": {},
        "policy": {"result": "unbound"},
        "evidence": ev,
        "notes": [*notes, *decl.get("extends_warnings", [])],
    }
    if cfg and cfg.get("standard_changes"):
        ctx["dependency_updates"] = gate.dependency_version_updates(repo, base_sha, head_sha, files)
    added = gate.dependencies_added(repo, base_sha, head_sha, files)
    if added:
        ctx["dependencies_added"] = added
    if content := gate.content_matches(repo, cfg, base_sha, head_sha, files):
        ctx["content_matches"] = content
    reverted = gate.revert_of(repo, base_sha, head_sha, ctx["commits"], body)
    if reverted:
        ctx["revert_of"] = reverted
    if run_policy and cfg and cfg.policy_command:
        ctx["policy"] = gate.evaluate_in_base(
            cfg.policy_command,
            repo=repo,
            base_ref=base_tip,
            change_id=head,
            base_sha=base_sha,
            head_sha=head_sha,
            paths=gate.changed_paths(files),
            body=body,
            head_files=decl["head_files"],
            cfg=cfg,
            changed_lines=sum(f.get("additions", 0) + f.get("deletions", 0) for f in files),
            dependencies=added,
            content=ctx.get("content_matches"),
        )
    return ctx
