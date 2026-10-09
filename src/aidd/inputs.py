"""Inputs every entry point gathers the same way.

The config and its `extends` chain come from the tip of the base branch (the
rules in force now); the Spec and head config come from the change's head.
Local preflight, the test runner, and both CI adapters share this code, so
they can never disagree about which config applies.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

from . import codeowners, gitutil, http, model, policy, rules, schema
from . import config as cfgmod


def default_base(cwd: str = ".") -> str:
    """The base branch to compare against when --base is not given."""
    head = gitutil.run(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], cwd, check=False).strip()
    for ref in ([head] if head else []) + ["origin/main", "origin/master", "main", "master"]:
        if gitutil.run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd, check=False).strip():
            return ref
    raise gitutil.GitError("cannot find a base branch (tried origin/HEAD, origin/main, origin/master, main, master); pass --base <ref>")


def repo_path(path: str) -> str:
    """Normalize a user-supplied repo path: forward slashes, no leading ./"""
    s = path.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return PurePosixPath(s).as_posix()


def host_and_port(url: str) -> tuple[str, int]:
    """The host and port a URL names, even when its port is malformed (then the default)."""
    parsed = urllib.parse.urlsplit(url)
    try:
        return parsed.hostname or "", parsed.port or 443
    except ValueError:
        netloc = parsed.netloc.split("@")[-1]
        if netloc.startswith("["):  # an IPv6 literal: [addr]:port
            return netloc[1:].split("]", 1)[0], 443
        return netloc.split(":", 1)[0], 443


_SHARED = ipaddress.ip_network("100.64.0.0/10")  # carrier-grade NAT: not global, and not flagged private by Python
# Checked in order; the first match names the refusal.
_REFUSED = (
    ("loopback", lambda ip: ip.is_loopback),
    ("link-local", lambda ip: ip.is_link_local),
    ("shared (CGNAT)", lambda ip: ip.version == 4 and ip in _SHARED),
    ("private", lambda ip: ip.is_private),
    ("reserved", lambda ip: ip.is_reserved),
    ("unspecified", lambda ip: ip.is_unspecified),
    ("multicast", lambda ip: ip.is_multicast),
    ("non-global", lambda ip: not ip.is_global),
)


def check_public_address(host: str, port: int = 443) -> str:
    """The first address `host` resolves to, after checking that every one of them is public; otherwise HttpError."""
    try:
        addrs = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise http.HttpError(0, host, f"cannot resolve host {host!r}: {exc}") from exc
    vetted: list[str] = []
    for _family, _, _, _, sockaddr in addrs:
        ip_str = str(sockaddr[0])
        try:
            ip: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # ::ffff:10.0.0.1 is 10.0.0.1
        addr_class = next((name for name, refused in _REFUSED if refused(ip)), None)
        if addr_class:
            raise http.HttpError(0, host, f"refusing to reach {ip_str}: {addr_class} address class")
        vetted.append(ip_str)
    if not vetted:
        raise http.HttpError(0, host, f"host {host!r} resolves to no usable address")
    return vetted[0]


def fetch_text(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise http.HttpError(0, url, f"refusing scheme {parsed.scheme!r}; only https is permitted")
    host, port = host_and_port(url)
    ip = check_public_address(host, port)
    # The connection goes to the address just vetted, so a DNS answer that changes in between (rebinding) cannot
    # redirect it; no redirect is followed either. Behind a configured proxy the proxy picks the address. (The
    # sha256 pin on every extends URL is the real guarantee; this keeps the fetch from reaching internal hosts.)
    proxied = bool(urllib.request.getproxies().get("https")) and not urllib.request.proxy_bypass(host)
    return http.get_bytes(url, follow_redirects=False, pinned_ip=None if proxied else ip).decode("utf-8")


def org_preset_text() -> str | None:
    """An org preset the gate injects as the implicit root parent (AIDD_ORG_PRESET=path)."""
    path = os.environ.get("AIDD_ORG_PRESET")
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


MAX_EXTENDS_DEPTH = 5
ORG_PRESET_BY_URL = cfgmod.ORG_PRESET_BY_URL


def collect_extends(text: str, read, fetch=fetch_text, out: dict[str, str] | None = None, depth: int = 0, warnings: list[str] | None = None) -> dict[str, str]:
    """Every parent config in the extends chain, keyed by path or url. With `read` None (an org preset, which lives
    outside the repository), a parent named by path is not read, with a warning that says why."""
    out = {} if out is None else out
    warnings = [] if warnings is None else warnings
    if depth > MAX_EXTENDS_DEPTH:
        warnings.append(f"extends chain is deeper than {MAX_EXTENDS_DEPTH}; the parents beyond it are not read")
        return out
    try:
        raw = model.parse_toml(text, "config")
    except model.ModelError:
        return out
    for parent in raw.get("extends", []):
        if not isinstance(parent, dict):
            continue
        errs = schema.validate(parent, "config.schema.json#/$defs/extends")
        if errs:
            url = parent.get("url") or parent.get("path") or ""
            parsed = urllib.parse.urlsplit(url) if url else None
            if parsed and parsed.scheme and parsed.scheme.lower() != "https":
                msg = f"extends {url!r}: refused scheme {parsed.scheme!r}"
            else:
                msg = f"extends {url!r}: does not match schema: {'; '.join(errs)}"
            warnings.append(msg)
            continue
        key = parent.get("path") or parent.get("url")
        if not key or key in out:
            continue
        if "path" in parent and read is None:
            warnings.append(f"extends {parent['path']!r}: {ORG_PRESET_BY_URL}")
            continue
        if "url" in parent:
            try:
                check_public_address(*host_and_port(parent["url"]))
            except http.HttpError as exc:
                warnings.append(f"extends {parent['url']!r}: {exc.body}")
                continue
        try:
            t = read(parent["path"]) if "path" in parent else fetch(parent["url"])
        except http.HttpError as exc:
            # Every failure is named, with its cause: the config that needed this parent will not load without it.
            warnings.append(f"extends {parent.get('url', key)!r}: {exc.body if 'refusing' in str(exc) else exc}")
            t = None
        except Exception as exc:
            warnings.append(f"extends {parent.get('url', key)!r}: cannot fetch it: {type(exc).__name__}: {exc}")
            t = None
        if t is not None:
            out[key] = t
            collect_extends(t, read, fetch, out, depth + 1, warnings=warnings)
    return out


def declared_inputs(cwd: str, base_tip: str, head_sha: str, body: str, *, fetch=fetch_text, org_preset: str | None = None) -> dict:
    """What the change declares, and the config in force.

    `config` comes only from the base branch: it is what a gate job may execute or trust (the Policy command, the
    evidence source, status checks, owners). When the base has no config (bootstrap), `config` is None and the
    change's own config is returned as `bootstrap_config`, for display and for the change's own test run only:
    a change never brings the rules, commands, or trust it is judged by.
    """
    base_config = gitutil.show(base_tip, cfgmod.CONFIG_PATH, cwd)
    head_config = gitutil.show(head_sha, cfgmod.CONFIG_PATH, cwd)
    head_files: dict[str, str] = {}
    if head_config is not None:
        head_files[cfgmod.CONFIG_PATH] = head_config
    cr, _ = model.parse_change_block(body)
    spec_approvers: list[str] = []
    for key in ("backfill", "spec"):
        path = cr.get(key) if cr else None
        text = gitutil.show(head_sha, path, cwd) if isinstance(path, str) else None
        if path is None or text is None:
            continue
        head_files[path] = text
        if key == "spec":
            try:
                spec_approvers = model.split_front_matter(text)[0].get("approvers", [])
            except model.ModelError:
                pass
    extends_warnings: list[str] = []
    bootstrap = base_config is None
    source, ref = (head_config, head_sha) if bootstrap else (base_config, base_tip)
    extends_texts = collect_extends(source, lambda p: gitutil.show(ref, p, cwd), fetch, warnings=extends_warnings) if source else {}
    if org_preset:
        # The preset lives outside the repository, so its parents are fetched by URL only.
        collect_extends(org_preset, None, fetch, extends_texts, warnings=extends_warnings)
    loaded = None
    if source:
        try:
            loaded = cfgmod.load_text(source, prefetched=extends_texts, root_preset=org_preset)
            loaded.warnings.extend(extends_warnings)
        except (cfgmod.ConfigError, model.ModelError):
            loaded = None
    effective = None if bootstrap else loaded
    codeowners_text = None
    if effective and effective.get("owners", "codeowners"):
        codeowners_text = next((t for t in (gitutil.show(base_tip, loc, cwd) for loc in codeowners.LOCATIONS) if t is not None), None)
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
    }


def comment(user: str, c: dict) -> dict:
    """A platform comment as the context records it: edited when it changed after it was posted, and via_app when an
    App posted it for the person it names (GitHub's performed_via_github_app: a token an agent may hold)."""
    out = {
        "user": user,
        "body": c.get("body") or "",
        "created_at": c.get("created_at"),
        "edited": bool(c.get("updated_at")) and c.get("updated_at") != c.get("created_at"),
    }
    return out | ({"via_app": True} if c.get("performed_via_github_app") else {})


def adapter_fields(ctx: dict, cwd: str, decl: dict, base_tip: str, team_members: dict[str, list[str]], org_preset: str | None, *, pushed_at=None) -> dict:
    """The context fields both CI adapters compute alike from the rest of `ctx`: the declared inputs, the approval
    commits, the approvals' equivalent heads, and Policy, run from a clean worktree of the base tip with the base config's
    command. `pushed_at(sha)` says when an earlier head reached the platform, for a carried approval's cool-off."""
    cfg, base_sha, head_sha, files, body = decl["config"], ctx["base_sha"], ctx["head_sha"], ctx["files"], ctx["change"]["body"]
    extra: dict = {"dependency_updates": dependency_updates(cwd, base_sha, head_sha, files)} if cfg and cfg.get("standard_changes") else {}
    added = dependencies_added(cwd, base_sha, head_sha, files)
    if added:
        extra["dependencies_added"] = added
    reverted = revert_of(cwd, base_sha, head_sha, ctx["commits"], body)
    if reverted:
        extra["revert_of"] = reverted
    return extra | {
        "approval_commits": approval_commits(cwd, base_sha, head_sha, ctx["comments"], eligible=pool_members(decl["pools"], team_members), spec=spec_of(body)),
        "approval_equivalents": approval_equivalents(cwd, base_tip, base_sha, head_sha, approved_heads(ctx, head_sha), pushed_at=pushed_at),
        "head_tree": gitutil.ls_tree(head_sha, cwd),
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
            paths=rules.changed_paths(files),
            body=body,
            head_files=decl["head_files"],
            cfg=cfg,
            changed_lines=sum(f.get("additions", 0) + f.get("deletions", 0) for f in files),
            dependencies=added,
        ),
    }


MAX_APPROVAL_COMMITS = 50
MAX_EQUIVALENTS = 20
_HUNK = re.compile(rb"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


def approved_heads(ctx: dict, head_sha: str, limit: int = MAX_EQUIVALENTS) -> list[str]:
    """Earlier heads that approvals name, newest first: each `approved` review's commit, and each `/aidd approve-merge <sha>` (or `/aidd approve <sha>`)
    comment's, other than the current head. Their diffs are compared with the head's (`approval_equivalents`)."""
    from .gates import APPROVE, commands
    from .util import EPOCH, parse_time

    named: list[tuple[object, str]] = [
        (parse_time(r.get("submitted_at")) or EPOCH, r["commit_sha"]) for r in ctx.get("reviews") or [] if r.get("state") == "approved" and r.get("commit_sha")
    ]
    for c in ctx.get("comments") or []:
        named += [(parse_time(c.get("created_at")) or EPOCH, m.group(1)) for m in APPROVE.finditer(commands(c.get("body") or ""))]
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
    p = gitutil._git(
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
        raise gitutil.GitError(f"git diff {base[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")
    out = []
    for line in p.stdout.split(b"\n"):
        if line.startswith(b"index "):
            continue
        out.append(_HUNK.sub(b"@@", line))
    return b"\n".join(out)


def approval_equivalents(
    cwd: str, base_tip: str, base_sha: str, head_sha: str, shas: list[str], *, pushed_at=None, limit: int = MAX_EQUIVALENTS
) -> dict[str, dict]:
    """For each earlier head an approval names, what a trivial rebase onto the current head must show (the gate decides):

    - `base_sha`: where that head met the base branch (its merge-base with the base tip), or null when unknown;
    - `identical_diff`: its diff from there equals the head's diff from the head's base, byte for byte (`change_diff`);
    - `base_descends`: the head's base descends from that base on the base branch;
    - `new_committers`: who authored or committed the head's commits but none of that head's, as `email:<address>`;
    - `pushed_at`: when that head reached the platform, if the adapter knows (its cool-off counts from there).

    A commit git does not have (a head force-pushed away and not fetched) is unknown: nothing about it is equivalent."""
    out: dict[str, dict] = {}
    if not shas:
        return out
    head_diff: bytes | None = None
    head_people: set[str] | None = None
    for sha in shas[:limit]:
        entry: dict = {"base_sha": None, "identical_diff": False, "base_descends": False, "new_committers": []}
        out[sha] = entry
        if not gitutil.ok(["cat-file", "-e", f"{sha}^{{commit}}"], cwd):
            continue
        try:
            old_base = gitutil.merge_base(base_tip, sha, cwd)
        except gitutil.GitError:
            continue
        entry["base_sha"] = old_base
        entry["base_descends"] = gitutil.ok(["merge-base", "--is-ancestor", old_base, base_sha], cwd)
        if head_diff is None:
            head_diff = change_diff(cwd, base_sha, head_sha)
            head_people = _people(gitutil.commits(base_sha, head_sha, cwd))
        entry["identical_diff"] = change_diff(cwd, old_base, sha) == head_diff
        entry["new_committers"] = sorted((head_people or set()) - _people(gitutil.commits(old_base, sha, cwd)))
        if pushed_at is not None:
            entry["pushed_at"] = pushed_at(sha)
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
    cr, _ = model.parse_change_block(body or "")
    backfill = [cr["backfill"]] if cr and isinstance(cr.get("backfill"), str) else []
    found = None
    for sha in dict.fromkeys(named):
        if not gitutil.ok(["cat-file", "-e", f"{sha}^{{commit}}"], cwd):
            continue
        on_base = gitutil.ok(["merge-base", "--is-ancestor", sha, base_sha], cwd)
        parent = gitutil.run(["rev-parse", "--verify", "--quiet", f"{sha}^1"], cwd, check=False).strip()
        exact = bool(on_base and parent) and change_diff(cwd, sha, parent) == change_diff(cwd, base_sha, head_sha, backfill)
        found = {"sha": sha, "on_base": on_base, "exact": exact}
        if exact:
            break
    return found


def _people(commits: list[dict]) -> set[str]:
    return {c[k].lower() for c in commits for k in ("author", "committer") if c.get(k)}


def pool_members(pools: list[str], team_members: dict[str, list[str]]) -> set[str]:
    """Every identity a pool entry names, with `@org/team` entries resolved through `team_members` (as the gate does)."""
    from .util import norm

    out: set[str] = set()
    for e in pools:
        n = norm(e)
        if "/" in n and not n.startswith("email:"):
            out.update(norm(m) for m in team_members.get(e, team_members.get("@" + n, team_members.get(n, []))))
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
    spec: str | None = None,
) -> dict[str, dict]:
    """For every commit named in a Spec approval line, what that commit had changed since the base.

    It proves Spec approval came before implementation: an approval given on a commit that held only the Spec and its
    tests. The diff is the commit's own, from where it meets the base (`merge_base(base, sha)..sha`), so merging the
    base branch in later adds nothing, and a Spec commit rebased since keeps its proof: with `spec` (the change's Spec
    path) each entry also carries `spec_hash`, that Spec's Spec hash at the named commit, which the gate
    matches against the approved hash when the commit is no longer an ancestor of head.

    Anyone can comment, so only comments from `eligible` identities (pool members, when given) are read, newest first,
    and at most `limit` commits are looked up; their existence is checked in one `git cat-file --batch-check`.
    """
    from .gates import APPROVE_SPEC, commands
    from .util import norm

    shas: list[str] = []
    for c in reversed(comments):
        if eligible is not None and norm(c.get("user") or "") not in eligible:
            continue
        for m in APPROVE_SPEC.finditer(commands(c.get("body") or "")):
            sha = m.group(3)
            if sha and sha not in shas and len(shas) < limit:
                shas.append(sha)
    if not shas:
        return {}
    listing = gitutil.run(["cat-file", "--batch-check"], cwd, check=False, input="".join(f"{sha}^{{commit}}\n" for sha in shas)).splitlines()
    out: dict[str, dict] = {}
    for sha, line in zip(shas, listing + [""] * (len(shas) - len(listing)), strict=True):
        exists = line.split(" ")[1:2] == ["commit"]
        ancestor = exists and gitutil.ok(["merge-base", "--is-ancestor", sha, head_sha], cwd)
        paths = [x for x in gitutil.run(["diff", "--name-only", "-z", f"{base_sha}...{sha}"], cwd, check=False).split("\0") if x] if exists else []
        out[sha] = {"ancestor": ancestor, "paths": sorted(paths)}
        if spec and exists:
            out[sha]["spec_hash"] = _spec_hash_at(cwd, sha, spec)
    return out


def _spec_hash_at(cwd: str, sha: str, spec: str) -> str | None:
    """The Spec hash of the Spec at `spec` as commit `sha` holds it, or None when it has none there."""
    text = gitutil.show(sha, spec, cwd)
    if text is None:
        return None
    try:
        return model.spec_hash(text, gitutil.ls_tree(sha, cwd))
    except model.ModelError:
        return None


def dependency_updates(cwd: str, base_sha: str, head_sha: str, files: list[dict]) -> list[dict]:
    """The dependency versions the diff's manifests and lockfiles move (depdiff), for a standard change's update types."""
    from . import depdiff

    paths = [f["path"] for f in files] + [f["previous_path"] for f in files if f.get("previous_path")]
    return depdiff.updates(sorted(set(paths)), lambda p: gitutil.show(base_sha, p, cwd), lambda p: gitutil.show(head_sha, p, cwd))


def dependencies_added(cwd: str, base_sha: str, head_sha: str, files: list[dict]) -> list[dict]:
    """The dependencies the diff's manifests add ({file, name}, depdiff), for the risk rules that name a dependency."""
    from . import depdiff

    return depdiff.added([f["path"] for f in files], lambda p: gitutil.show(base_sha, p, cwd), lambda p: gitutil.show(head_sha, p, cwd))


def commit_block(cwd: str, base_sha: str, head_sha: str) -> str | None:
    """Locally, where no PR/MR description exists: the message of the newest commit on the branch (`base_sha..head_sha`)
    that holds a Change Request block (`aidd describe --commit` writes one), read as the description; None when none does.
    A malformed block is returned too, so the gate reports it instead of ignoring it."""
    for c in gitutil.commits(base_sha, head_sha, cwd):  # newest first
        cr, errs = model.parse_change_block(c.get("message") or "")
        if cr is not None or errs:
            return c["message"]
    return None


def spec_of(body: str) -> str | None:
    """The Spec path a change's Change Request block names, if any."""
    cr, _ = model.parse_change_block(body or "")
    spec = (cr or {}).get("spec")
    return spec if isinstance(spec, str) else None
