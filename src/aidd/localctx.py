"""Build a verifier context from a local git checkout.

Local contexts are untrusted (`trusted: False`): the machine that builds one is the machine the agent runs on.
They serve two uses. Before a PR/MR, an agent or a developer preflights a branch; that decision is advisory, and
the platform's gate decides. Local-first, with no platform, the local gate is the gate: it reads the approvals a
person recorded with `aidd approve` (local.py), counting only signed ones when the base branch's config sets
`gates.local_approvals = "signed"`, and `aidd ship` merges only when it passes.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import gitutil, inputs, model, policy, rules


def find_spec_in_diff(files: list[dict], specs_dir: str, head_files_reader) -> str | None:
    specs = []
    for p in (f["path"] for f in files if f["path"].startswith(specs_dir.rstrip("/") + "/") and f["path"].endswith(".md")):
        text = head_files_reader(p)
        try:
            if text is not None and model.split_front_matter(text, p)[0].get("kind") == "spec":
                specs.append(p)
        except model.ModelError:
            continue
    return specs[0] if len(specs) == 1 else None


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
    if body is None:
        specs_dir = "specs"
        cfg_text = gitutil.show(base_tip, ".aidd/config.toml", repo) or gitutil.show(head_sha, ".aidd/config.toml", repo)
        if cfg_text:
            try:
                specs_dir = model.parse_toml(cfg_text, "config").get("specs_dir", "specs")
            except model.ModelError:
                pass
        spec = spec or find_spec_in_diff(files, specs_dir, lambda p: gitutil.show(head_sha, p, repo))
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
        # must be signed comes from the base branch's config, never from this machine's git config.
        from . import local

        signed = bool(cfg) and cfg.gates.get("local_approvals") == "signed"
        reviews, comments, notes = local.load(repo, require_signed=signed)
    ev = json.loads(Path(evidence).read_text(encoding="utf-8")) if evidence and Path(evidence).is_file() else None
    email = gitutil.config_value("user.email", repo)
    ctx = {
        "platform": "local",
        "trusted": False,
        "repo": str(Path(repo).resolve().name),
        "now": dt.datetime.now(dt.UTC).isoformat(),
        "change": {"id": head, "author": f"email:{email}" if email else "local", "body": body, "draft": False},
        "base_sha": base_sha,
        "head_sha": head_sha,
        # Nothing is pushed locally: the head commit's committer date is the best available start for the cool-off,
        # and the committer sets it (gates.Run.cooled).
        "head_pushed_at": gitutil.run(["log", "-1", "--format=%cI", head_sha], repo).strip() or None,
        "files": files,
        "commits": gitutil.commits(base_sha, head_sha, repo),
        "reviews": reviews,
        "comments": comments,
        "approval_commits": inputs.approval_commits(repo, base_sha, head_sha, comments, eligible=inputs.pool_members(decl["pools"], {})),
        "head_tree": gitutil.ls_tree(head_sha, repo),
        "head_files": decl["head_files"],
        "base_config": decl["base_config"],
        "extends_texts": decl["extends_texts"],
        "codeowners": decl["codeowners"],
        "org_preset": org,
        "team_members": {},
        "policy": {"result": "unbound"},
        "evidence": ev,
        "notes": notes,
    }
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
        )
    return ctx
