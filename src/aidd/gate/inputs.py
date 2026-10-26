"""Inputs every entry point gathers the same way.

The config and its `extends` chain come from the tip of the base branch (the
rules in force now); the Spec and head config come from the change's head.
Local preflight, the test runner, and both CI adapters share this code, so
they can never disagree about which config applies.
"""

from __future__ import annotations

import re

from aidd import config, workitems
from aidd.gate import codeowners, content_rules, policy, routing
from aidd.kernel import documents, egress, git, globs


def declared_inputs(cwd: str, base_tip: str, head_sha: str, body: str, *, fetch=egress.fetch_text, org_preset: str | None = None) -> dict:
    """What the change declares, and the config in force.

    `config` comes only from the base branch: it is what a gate job may execute or trust (the Policy command, the
    evidence source, status checks, owners). When the base has no config (bootstrap), `config` is None and the
    change's own config is returned as `bootstrap_config`, for display and for the change's own test run only:
    a change never brings the rules, commands, or trust it is judged by.
    """
    base_config = git.show(base_tip, config.CONFIG_PATH, cwd)
    head_config = git.show(head_sha, config.CONFIG_PATH, cwd)
    head_files: dict[str, str] = {}
    if head_config is not None:
        head_files[config.CONFIG_PATH] = head_config
    cr, _ = workitems.parse_change_block(body)
    spec_approvers: list[str] = []
    named = [p for p in [(cr or {}).get("backfill")] if isinstance(p, str)] + workitems.change_specs(cr)
    for path in named:
        text = git.show(head_sha, path, cwd)
        if text is None:
            continue
        head_files[path] = text
        if path != (cr or {}).get("backfill"):
            try:
                spec_approvers += list(documents.split_front_matter(text)[0].get("approvers", []) or [])
            except documents.DocumentError:
                pass
    extends_warnings: list[str] = []
    bootstrap = base_config is None
    source, ref = (head_config, head_sha) if bootstrap else (base_config, base_tip)
    extends_texts = config.collect_extends(source, lambda p: git.show(ref, p, cwd), fetch, warnings=extends_warnings) if source else {}
    if org_preset:
        # The preset lives outside the repository, so its parents are fetched by URL only.
        config.collect_extends(org_preset, None, fetch, extends_texts, warnings=extends_warnings)
    loaded = None
    if source:
        try:
            loaded = config.load_text(source, prefetched=extends_texts, root_preset=org_preset)
            loaded.warnings.extend(extends_warnings)
        except (config.ConfigError, documents.DocumentError):
            loaded = None
    effective = None if bootstrap else loaded
    in_force = effective or loaded
    specs_dir = in_force.specs_dir if in_force is not None else "specs"
    derived_spec = None
    if cr is None:
        # No block: the gate takes the one Spec the diff adds or changes, so it reads each candidate as the head has it.
        for path in _changed(cwd, base_tip, head_sha, globs.under(specs_dir, "**/*.md")):
            if path not in head_files and (text := git.show(head_sha, path, cwd)) is not None:
                head_files[path] = text
        found = workitems.find_specs_in_diff([{"path": p} for p in head_files], specs_dir, head_files.get)
        derived_spec = found[0] if len(found) == 1 else None
    if cr and "specs" in cr:
        # A goal's change carries its plan too: the gate reads each work item the diff adds beside the Specs.
        for path in _plan_items_changed(cwd, base_tip, head_sha, specs_dir):
            if path not in head_files and (text := git.show(head_sha, path, cwd)) is not None:
                head_files[path] = text
    codeowners_text = None
    if effective and effective.get("owners", "codeowners"):
        codeowners_text = next((t for t in (git.show(base_tip, loc, cwd) for loc in codeowners.LOCATIONS) if t is not None), None)
    pools: set[str] = set(spec_approvers) | set(codeowners.all_owners(codeowners_text))
    if effective:
        pools.update(effective.approvers)
        for members in effective.specialists.values():
            pools.update(members)
        for entry in effective.get("owners", "paths", default=[]):
            pools.update(entry["approvers"])
    return {
        "base_config": base_config,
        "head_files": head_files,
        "extends_texts": extends_texts,
        # Why a parent config is missing (a failed fetch, a refused address): the report shows them as notes, since a
        # config that needed the parent does not load and its own warnings are lost with it.
        "extends_warnings": extends_warnings,
        "config": effective,
        "bootstrap_config": loaded if bootstrap else None,
        "pools": sorted(pools),
        "codeowners": codeowners_text,
        # With no block, the one Spec the diff carries, which the gate takes as the change's (gate_change_request).
        "derived_spec": derived_spec,
    }


def _plan_items_changed(cwd: str, base_tip: str, head_sha: str, specs_dir: str) -> list[str]:
    """The Markdown files directly in the specs folder that the change adds or changes (workitems.plan_paths)."""
    try:
        patterns = workitems.plan_paths(specs_dir)
    except ValueError:
        return []
    return _changed(cwd, base_tip, head_sha, *patterns)


def _changed(cwd: str, base_tip: str, head_sha: str, *patterns: str) -> list[str]:
    """The paths the change adds or changes since it left the base branch that match any of `patterns`."""
    changed = git.run(["diff", "--name-only", "-z", "--no-renames", f"{base_tip}...{head_sha}", "--"], cwd, check=False).split("\0")
    return sorted(p for p in changed if p and globs.match_any(list(patterns), p))


def recorded_comment(user: str, c: dict) -> dict:
    """A platform comment as the context records it: edited when it changed after it was posted, and via_app when an
    App posted it for the person it names (GitHub's performed_via_github_app: a token an agent may hold)."""
    out = {
        "user": user,
        "body": c.get("body") or "",
        "created_at": c.get("created_at"),
        "edited": bool(c.get("updated_at")) and c.get("updated_at") != c.get("created_at"),
    }
    return out | ({"via_app": True} if c.get("performed_via_github_app") else {})


def adapter_fields(ctx: dict, cwd: str, decl: dict, base_tip: str, team_members: dict[str, list[str]], org_preset: str | None) -> dict:
    """The context fields both CI adapters compute alike from the rest of `ctx`: the declared inputs, the dependencies
    and the content rules' matches the diff adds, the approval commits, the approvals' equivalent heads, and Policy, run from a clean worktree of the base tip with the base config's
    command."""
    cfg, base_sha, head_sha, files, body = decl["config"], ctx["base_sha"], ctx["head_sha"], ctx["files"], ctx["change"]["body"]
    extra: dict = {"dependency_updates": dependency_version_updates(cwd, base_sha, head_sha, files)} if cfg and cfg.get("standard_changes") else {}
    added = dependencies_added(cwd, base_sha, head_sha, files)
    if added:
        extra["dependencies_added"] = added
    if content := content_matches(cwd, cfg, base_sha, head_sha, files):
        extra["content_matches"] = content
    reverted = revert_of(cwd, base_sha, head_sha, ctx["commits"], body)
    if reverted:
        extra["revert_of"] = reverted
    return extra | {
        "approval_commits": approval_commits(
            cwd, base_sha, head_sha, ctx["comments"], eligible=pool_members(decl["pools"], team_members), spec=spec_of_change(body) or decl.get("derived_spec")
        ),
        "approval_equivalents": approval_equivalents(cwd, base_tip, base_sha, head_sha, approved_heads(ctx, head_sha)),
        "head_tree": git.ls_tree(head_sha, cwd),
        "head_files": decl["head_files"],
        "base_config": decl["base_config"],
        "extends_texts": decl["extends_texts"],
        "notes": list(decl.get("extends_warnings") or []),
        "codeowners": decl["codeowners"],
        "org_preset": org_preset,
        "team_members": team_members,
        "policy": policy.evaluate_in_base(
            cfg.policy_command if cfg else None,
            repo=cwd,
            base_ref=base_tip,
            change_id=ctx["change"]["id"],
            base_sha=base_sha,
            head_sha=head_sha,
            paths=routing.changed_paths(files),
            body=body,
            head_files=decl["head_files"],
            spec=decl.get("derived_spec"),
            cfg=cfg,
            changed_lines=sum(f.get("additions", 0) + f.get("deletions", 0) for f in files),
            dependencies=added,
            content=extra.get("content_matches"),
        ),
    }


MAX_APPROVAL_COMMITS = 50
MAX_EQUIVALENTS = 20
_HUNK = re.compile(rb"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


def approved_heads(ctx: dict, head_sha: str, limit: int = MAX_EQUIVALENTS) -> list[str]:
    """Earlier heads that approvals name, newest first: each `approved` review's commit, and each `/aidd approve-merge <sha>`
    comment's, other than the current head. Their diffs are compared with the head's (`approval_equivalents`)."""
    from aidd.gate.rules.gate_run import APPROVE, comment_commands
    from aidd.kernel.timestamps import EPOCH, parse_time

    named: list[tuple[object, str]] = [
        (parse_time(r.get("submitted_at")) or EPOCH, r["commit_sha"]) for r in ctx.get("reviews") or [] if r.get("state") == "approved" and r.get("commit_sha")
    ]
    for c in ctx.get("comments") or []:
        named += [(parse_time(c.get("created_at")) or EPOCH, m.group(1)) for m in APPROVE.finditer(comment_commands(c.get("body") or ""))]
    out: list[str] = []
    for _, sha in sorted(named, key=lambda t: t[0], reverse=True):  # type: ignore[arg-type, return-value]
        if sha != head_sha and sha not in out and len(out) < limit:
            out.append(sha)
    return out


def change_diff(cwd: str, base: str, head: str, exclude: list[str] | tuple[str, ...] = ()) -> bytes:
    """The change's diff, byte for byte, as a trivial rebase must keep it: every added, removed, and context line, every
    mode, and every binary patch, with only what a rebase moves left out, the blob ids on `index` lines and the line
    numbers on hunk headers. Whitespace counts (unlike `git patch-id` by default), and renames are not folded. `exclude`
    leaves literal paths out (an emergency's backfill Spec, next to the revert it documents)."""
    spec = ["--", ".", *(f":(exclude,literal){p}" for p in exclude)] if exclude else []
    p = git._git(
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "-U3",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            base,
            head,
            *spec,
        ],
        cwd,
    )
    if p.returncode != 0:
        raise git.GitError(f"git diff {base[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")
    out = []
    for line in p.stdout.split(b"\n"):
        if line.startswith(b"index "):
            continue
        out.append(_HUNK.sub(b"@@", line))
    return b"\n".join(out)


def approval_equivalents(cwd: str, base_tip: str, base_sha: str, head_sha: str, shas: list[str], *, limit: int = MAX_EQUIVALENTS) -> dict[str, dict]:
    """For each earlier head an approval names, what a trivial rebase onto the current head must show (the gate decides):

    - `base_sha`: where that head met the base branch (its merge-base with the base tip), or null when unknown;
    - `identical_diff`: its diff from there equals the head's diff from the head's base, byte for byte (`change_diff`);
    - `base_descends`: the head's base descends from that base on the base branch;
    - `new_committers`: who authored or committed the head's commits but none of that head's, as `email:<address>`.

    A commit git does not have (a head force-pushed away and not fetched) is unknown: nothing about it is equivalent."""
    out: dict[str, dict] = {}
    if not shas:
        return out
    head_diff: bytes | None = None
    head_people: set[str] | None = None
    for sha in shas[:limit]:
        entry: dict = {"base_sha": None, "identical_diff": False, "base_descends": False, "new_committers": []}
        out[sha] = entry
        if not git.ok(["cat-file", "-e", f"{sha}^{{commit}}"], cwd):
            continue
        try:
            old_base = git.merge_base(base_tip, sha, cwd)
        except git.GitError:
            continue
        entry["base_sha"] = old_base
        entry["base_descends"] = git.ok(["merge-base", "--is-ancestor", old_base, base_sha], cwd)
        if head_diff is None:
            head_diff = change_diff(cwd, base_sha, head_sha)
            head_people = _people(git.commits(base_sha, head_sha, cwd))
        entry["identical_diff"] = change_diff(cwd, old_base, sha) == head_diff
        entry["new_committers"] = sorted((head_people or set()) - _people(git.commits(old_base, sha, cwd)))
    return out


_REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{40})\b", re.M)


def revert_of(cwd: str, base_sha: str, head_sha: str, commits: list[dict], body: str = "") -> dict | None:
    """Whether the change is `git revert` of a commit already merged on the base branch: the commit a revert commit's
    message names ("This reverts commit <sha>."), whether it is on the base, and whether the change's whole diff, apart from
    the backfill Spec its block names, is exactly that commit's diff reversed (`change_diff`, byte for byte). None when no
    commit names a revert."""
    named = [sha for c in commits for sha in _REVERTS.findall(c.get("message") or "")]
    if not named:
        return None
    cr, _ = workitems.parse_change_block(body or "")
    backfill = [cr["backfill"]] if cr and isinstance(cr.get("backfill"), str) else []
    found = None
    for sha in dict.fromkeys(named):
        if not git.ok(["cat-file", "-e", f"{sha}^{{commit}}"], cwd):
            continue
        on_base = git.ok(["merge-base", "--is-ancestor", sha, base_sha], cwd)
        parent = git.run(["rev-parse", "--verify", "--quiet", f"{sha}^1"], cwd, check=False).strip()
        exact = bool(on_base and parent) and change_diff(cwd, sha, parent) == change_diff(cwd, base_sha, head_sha, backfill)
        found = {"sha": sha, "on_base": on_base, "exact": exact}
        if exact:
            break
    return found


def _people(commits: list[dict]) -> set[str]:
    return {c[k].lower() for c in commits for k in ("author", "committer") if c.get(k)}


def pool_members(pools: list[str], team_members: dict[str, list[str]]) -> set[str]:
    """Every identity a pool entry names, with `@org/team` entries resolved through `team_members` (as the gate does)."""

    out: set[str] = set()
    for e in pools:
        n = config.normalize_identity(e)
        if "/" in n and not n.startswith("email:"):
            out.update(config.normalize_identity(m) for m in team_members.get(e, team_members.get("@" + n, team_members.get(n, []))))
        else:
            out.add(n)
    return out


def approval_commits(
    cwd: str,
    base_sha: str,
    head_sha: str,
    comments: list[dict],
    *,
    eligible: set[str] | None = None,
    limit: int = MAX_APPROVAL_COMMITS,
    spec: str | list[str] | None = None,
) -> dict[str, dict]:
    """For every commit named in a Spec approval line, what that commit had changed since the base.

    It proves Spec approval came before implementation: an approval given on a commit that held only the Spec and its
    tests. The diff is the commit's own, from where it meets the base (`merge_base(base, sha)..sha`), so merging the
    base branch in later adds nothing, and a Spec commit rebased since keeps its proof. With `spec` (the change's Spec
    path) each entry also carries `spec_hash`, that Spec's Spec hash at the named commit: what the person approved,
    which the gate compares with the Spec hash at head. For a goal's Specs, `spec_hashes` holds one per Spec id the
    lines name, since one commit may be approved for several of them.

    Anyone can comment, so only comments from `eligible` identities (pool members, when given) are read, newest first,
    and at most `limit` commits are looked up; their existence is checked in one `git cat-file --batch-check`.
    """
    from aidd.gate.rules.gate_run import APPROVE_SPEC, comment_commands

    shas: list[str] = []
    named_ids: dict[str, list[str]] = {}  # sha -> the Spec ids its approval lines name
    for c in reversed(comments):
        if eligible is not None and config.normalize_identity(c.get("user") or "") not in eligible:
            continue
        for m in APPROVE_SPEC.finditer(comment_commands(c.get("body") or "")):
            sha = m.group(2)
            if sha not in shas and len(shas) < limit:
                shas.append(sha)
            if sha in shas and m.group(1) not in named_ids.setdefault(sha, []):
                named_ids[sha].append(m.group(1))
    if not shas:
        return {}
    listing = git.run(["cat-file", "--batch-check"], cwd, check=False, input="".join(f"{sha}^{{commit}}\n" for sha in shas)).splitlines()
    out: dict[str, dict] = {}
    for sha, line in zip(shas, listing + [""] * (len(shas) - len(listing)), strict=True):
        exists = line.split(" ")[1:2] == ["commit"]
        ancestor = exists and git.ok(["merge-base", "--is-ancestor", sha, head_sha], cwd)
        paths = [x for x in git.run(["diff", "--name-only", "-z", f"{base_sha}...{sha}"], cwd, check=False).split("\0") if x] if exists else []
        out[sha] = {"ancestor": ancestor, "paths": sorted(paths)}
        if not exists:
            continue
        if isinstance(spec, str):
            out[sha]["spec_hash"] = _spec_hash_at(cwd, sha, spec)
            continue
        named = {sid: path for sid in named_ids.get(sha, []) if (path := _spec_named(cwd, head_sha, spec or [], sid))}
        if named:
            out[sha]["spec_hashes"] = {sid: _spec_hash_at(cwd, sha, path) for sid, path in named.items()}
    return out


def _spec_named(cwd: str, head_sha: str, specs: list[str], spec_id: str) -> str | None:
    """Of a goal's Specs, the one whose id at head is `spec_id`, so an approval's commit is matched against that Spec."""
    for path in specs:
        try:
            if spec_id and documents.split_front_matter(git.show(head_sha, path, cwd) or "")[0].get("id") == spec_id:
                return path
        except documents.DocumentError:
            continue
    return None


def _spec_hash_at(cwd: str, sha: str, spec: str) -> str | None:
    """The Spec hash of the Spec at `spec` as commit `sha` holds it, or None when it has none there."""
    text = git.show(sha, spec, cwd)
    if text is None:
        return None
    try:
        return workitems.spec_hash(text, git.ls_tree(sha, cwd))
    except documents.DocumentError:
        return None


def dependency_version_updates(cwd: str, base_sha: str, head_sha: str, files: list[dict]) -> list[dict]:
    """The dependency versions the diff's manifests and lockfiles move (dependency_updates), for a standard change's update types."""
    from aidd.gate import dependency_updates as depdiff

    paths = [f["path"] for f in files] + [f["previous_path"] for f in files if f.get("previous_path")]
    return depdiff.updates(sorted(set(paths)), lambda p: git.show(base_sha, p, cwd), lambda p: git.show(head_sha, p, cwd))


def content_matches(cwd: str, cfg: config.Config | None, base_sha: str, head_sha: str | None, files: list[dict]) -> list[dict]:
    """The context's `content_matches`: each content rule of the config that a line the diff adds matches, from
    `base_sha` to `head_sha` (None: the working tree), as each CI adapter and the local gate compute it."""
    active = content_rules.rules(routing.active_rules(cfg)) if cfg is not None else []
    if not active:
        return []
    paths = [f["path"] for f in files if f.get("additions") and not f.get("binary")]

    def added(path: str) -> list[str] | None:
        # A file git counts additions in, but whose diff gave no added line, was not read: it counts as a match.
        return content_rules.added_lines(cwd, base_sha, head_sha, path) or None

    return content_rules.matches(active, paths, added)


def dependencies_added(cwd: str, base_sha: str, head_sha: str, files: list[dict]) -> list[dict]:
    """The dependencies the diff's manifests add ({file, name}, dependency_updates), for the risk rules that name a dependency."""
    from aidd.gate import dependency_updates as depdiff

    return depdiff.added_dependencies([f["path"] for f in files], lambda p: git.show(base_sha, p, cwd), lambda p: git.show(head_sha, p, cwd))


def commit_block(cwd: str, base_sha: str, head_sha: str) -> str | None:
    """Locally, where no PR/MR description exists: the message of the newest commit on the branch (`base_sha..head_sha`)
    that holds a Change Request block (`aidd describe --commit` writes one), read as the description; None when none does.
    A malformed block is returned too, so the gate reports it instead of ignoring it."""
    for c in git.commits(base_sha, head_sha, cwd):  # newest first
        cr, errs = workitems.parse_change_block(c.get("message") or "")
        if cr is not None or errs:
            return c["message"]
    return None


def spec_of_change(body: str) -> str | list[str] | None:
    """The Spec path a change's Change Request block names, or a goal's Spec paths, if any."""
    cr, _ = workitems.parse_change_block(body or "")
    spec = (cr or {}).get("spec")
    if isinstance(spec, str):
        return spec
    return workitems.change_specs(cr) or None
