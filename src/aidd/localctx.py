"""Build a gate context from a local git checkout.

Local contexts are untrusted (`trusted: False`): the machine that builds one is the machine the agent runs on.
They serve two uses. Before a PR/MR, an agent or a developer preflights a branch; that decision is advisory, and
the platform's gate decides. Local-first, with no platform, the local gate is the gate: it reads the approvals a
person recorded with `aidd approve` (local.py), counting only signed ones when the base branch's config sets
`gates.local_approvals = "signed"`, and `aidd ship` merges only when it passes.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import gitutil, globs, inputs, model, policy, rules
from .util import norm

# At most this many added lines per file go into the context, for the secrets rule.
MAX_ADDED_LINES = 5000
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


def find_spec_in_diff(files: list[dict], specs_dir: str, head_files_reader) -> str | None:
    specs = []
    folder = globs.under(specs_dir, "")
    for p in (f["path"] for f in files if f["path"].startswith(folder) and f["path"].endswith(".md")):
        text = head_files_reader(p)
        try:
            if text is not None and model.split_front_matter(text, p)[0].get("kind") == "spec":
                specs.append(p)
        except model.ModelError:
            continue
    return specs[0] if len(specs) == 1 else None


CI_GATE_FILES = (".github/workflows/aidd-gate.yml", ".gitlab/aidd.gitlab-ci.yml")


def platform_of(repo: str) -> str:
    """`local` when this machine's gate is the gate (no remote, or no CI gate installed: `aidd init --ci none`), else
    `preflight`: the branch will go to a platform, whose `aidd/gate` decides, so the hints name the platform's steps."""
    remotes = gitutil.run(["remote"], repo, check=False).split()
    gated = any((Path(repo) / p).is_file() for p in CI_GATE_FILES)
    return "preflight" if remotes and gated else "local"


def added_lines(repo: str, base_sha: str, head_sha: str) -> dict[str, list[str]]:
    """path -> the lines the diff adds to it (text files; at most MAX_ADDED_LINES each), for the secrets rule."""
    out: dict[str, list[str]] = {}
    path: str | None = None
    diff = gitutil.run(["-c", "core.quotePath=false", "diff", "-U0", "--no-color", "--no-ext-diff", base_sha, head_sha], repo, check=False)
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


def this_branchs(repo: str, reviews: list[dict], base_tip: str, head_sha: str) -> list[dict]:
    """The local Merge approvals that belong to this branch: of its head, of a commit in its history, or recorded on this
    branch (an earlier head a rebase replaced). An approval of a commit already on the base branch (shipped work), or one
    recorded on another branch, is another change's. The branch the record names is dropped: it is not context."""
    branch = gitutil.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip()
    kept = []
    for r in reviews:
        recorded_on = r.pop("branch", None)
        sha = r.get("commit_sha") or ""
        if sha and sha != head_sha:
            if gitutil.ok(["merge-base", "--is-ancestor", sha, base_tip], repo):
                continue
            if recorded_on is not None and recorded_on != branch and not gitutil.ok(["merge-base", "--is-ancestor", sha, head_sha], repo):
                continue
        kept.append(r)
    return kept


def local_author(repo: str, cfg) -> str:
    """The change's author as the gate names it: `email:<user.email>`, or the login a person's git `user.name` is, when it
    is a login the config's approvers name (a preflight's approvals come as platform logins, and the author's own must
    not count)."""
    email = gitutil.config_value("user.email", repo)
    name = gitutil.config_value("user.name", repo).strip().lstrip("@")
    if cfg is not None and _LOGIN.fullmatch(name):
        named = {norm(a) for a in cfg.approvers} | {norm(a) for e in cfg.get("owners", "paths", default=[]) or [] for a in e.get("approvers", [])}
        if norm(name) in named:
            return norm(name)
    return f"email:{email}" if email else "local"


def spec_block(spec: str) -> str:
    return f"```toml aidd\nspec = {json.dumps(inputs.repo_path(spec))}\n```\n"


def build(
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
    base = base or inputs.default_base(repo)
    head_sha = gitutil.rev_parse(head, repo)
    base_tip = gitutil.rev_parse(base, repo)
    base_sha = gitutil.merge_base(base_tip, head_sha, repo)
    files = gitutil.numstat(base_sha, head_sha, repo)
    if body is None and spec is None:
        # No PR/MR description locally: the Change Request block the newest branch commit carries (`aidd describe --commit`).
        body = inputs.commit_block(repo, base_sha, head_sha)
    if body is None:
        specs_dir = "specs"
        cfg_text = gitutil.show(base_tip, ".aidd/config.toml", repo) or gitutil.show(head_sha, ".aidd/config.toml", repo)
        if cfg_text:
            try:
                specs_dir = str(model.parse_toml(cfg_text, "config").get("specs_dir", "specs"))
            except model.ModelError:
                pass
        try:
            spec = spec or find_spec_in_diff(files, specs_dir, lambda p: gitutil.show(head_sha, p, repo))
        except ValueError:  # specs_dir at the repository's top: the gate fails on the config itself (config.invalid)
            spec = None
        body = spec_block(spec) if spec else ""
    org = inputs.org_preset_text()
    decl = inputs.declared_inputs(repo, base_tip, head_sha, body, org_preset=org)
    cfg = decl["config"]
    notes: list[str] = []
    if approvals:
        data = json.loads(Path(approvals).read_text(encoding="utf-8"))
        reviews, comments = data.get("reviews", []), data.get("comments", [])
    else:
        # Local-first: the approvals people recorded on this machine with `aidd approve` (see local.py). Whether they
        # must be signed, and whose keys count, come from the base branch, never from this machine's git config.
        from . import local

        signed = bool(cfg) and cfg.gates.get("local_approvals") == "signed"
        reviews, comments, notes = local.load(
            repo, require_signed=signed, signers=local.base_signers(cfg, base_tip, repo), signers_file=local.signers_path(cfg)
        )
        reviews = this_branchs(repo, reviews, base_tip, head_sha)
    by_path = {f["path"]: f for f in files if not f.get("binary")}
    for path, lines in added_lines(repo, base_sha, head_sha).items() if files else ():
        entry = by_path.get(path)
        if entry is not None and lines:
            entry["added_lines"] = lines
    ev = json.loads(Path(evidence).read_text(encoding="utf-8")) if evidence and Path(evidence).is_file() else None
    ctx = {
        "platform": platform_of(repo),
        "trusted": False,
        "repo": str(Path(repo).resolve().name),
        "now": dt.datetime.now(dt.UTC).isoformat(),
        "change": {"id": head, "author": local_author(repo, cfg), "body": body, "draft": False},
        "base_sha": base_sha,
        "head_sha": head_sha,
        # Nothing is pushed locally: the head commit's committer date is the best available start for the cool-off,
        # and the committer sets it (gates.Run.cooled).
        "head_pushed_at": gitutil.run(["log", "-1", "--format=%cI", head_sha], repo).strip() or None,
        "files": files,
        "commits": gitutil.commits(base_sha, head_sha, repo),
        "reviews": reviews,
        "comments": comments,
        "approval_commits": inputs.approval_commits(
            repo, base_sha, head_sha, comments, eligible=inputs.pool_members(decl["pools"], {}), spec=inputs.spec_of(body)
        ),
        # An approval of an earlier head counts for this one only after a trivial rebase (the gate decides); locally an
        # earlier head "reached" the platform when it was committed, as for the head (head_pushed_at).
        "approval_equivalents": inputs.approval_equivalents(
            repo,
            base_tip,
            base_sha,
            head_sha,
            inputs.approved_heads({"reviews": reviews, "comments": comments}, head_sha),
            pushed_at=lambda sha: gitutil.run(["log", "-1", "--format=%cI", sha], repo, check=False).strip() or None,
        ),
        "head_tree": gitutil.ls_tree(head_sha, repo),
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
        ctx["dependency_updates"] = inputs.dependency_updates(repo, base_sha, head_sha, files)
    added = inputs.dependencies_added(repo, base_sha, head_sha, files)
    if added:
        ctx["dependencies_added"] = added
    reverted = inputs.revert_of(repo, base_sha, head_sha, ctx["commits"], body)
    if reverted:
        ctx["revert_of"] = reverted
    if run_policy and cfg and cfg.policy_command:
        ctx["policy"] = policy.evaluate_in_base(
            cfg.policy_command,
            repo=repo,
            base_ref=base_tip,
            change_id=head,
            base_sha=base_sha,
            head_sha=head_sha,
            paths=rules.changed_paths(files),
            body=body,
            head_files=decl["head_files"],
            cfg=cfg,
            changed_lines=sum(f.get("additions", 0) + f.get("deletions", 0) for f in files),
            dependencies=added,
        )
    return ctx
