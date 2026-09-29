"""Inputs every entry point gathers the same way.

The config and its `extends` chain come from the tip of the base branch (the
rules in force now); the Spec and head config come from the change's head.
Local preflight, the test runner, and both CI adapters share this code, so
they can never disagree about which config applies.
"""

from __future__ import annotations

import ipaddress
import os
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


def collect_extends(text: str, read, fetch=fetch_text, out: dict[str, str] | None = None, depth: int = 0, warnings: list[str] | None = None) -> dict[str, str]:
    """Every parent config in the extends chain, keyed by path or url."""
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
        if "url" in parent:
            try:
                check_public_address(*host_and_port(parent["url"]))
            except http.HttpError as exc:
                warnings.append(f"extends {parent['url']!r}: {exc.body}")
                continue
        try:
            t = read(parent["path"]) if "path" in parent else fetch(parent["url"])
        except http.HttpError as exc:
            if "refusing" in str(exc):
                warnings.append(f"extends {parent.get('url', key)!r}: {exc.body}")
            t = None
        except Exception:
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
        collect_extends(org_preset, lambda p: None, fetch, extends_texts, warnings=extends_warnings)
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
        for members in effective.reviewers.values():
            pools.update(members)
        for entry in effective.get("owners", "paths", default=[]):
            pools.update(entry["approvers"])
    return {
        "base_config": base_config,
        "head_files": head_files,
        "extends_texts": extends_texts,
        "config": effective,
        "bootstrap_config": loaded if bootstrap else None,
        "pools": sorted(pools),
        "codeowners": codeowners_text,
    }


def comment(user: str, c: dict) -> dict:
    """A platform comment as the context records it: edited when it changed after it was posted."""
    return {
        "user": user,
        "body": c.get("body") or "",
        "created_at": c.get("created_at"),
        "edited": bool(c.get("updated_at")) and c.get("updated_at") != c.get("created_at"),
    }


def adapter_fields(ctx: dict, cwd: str, decl: dict, base_tip: str, team_members: dict[str, list[str]], org_preset: str | None) -> dict:
    """The context fields both CI adapters compute alike from the rest of `ctx`: the declared inputs, the approval
    commits, and Policy, run from a clean worktree of the base tip with the base config's command."""
    cfg, base_sha, head_sha, files, body = decl["config"], ctx["base_sha"], ctx["head_sha"], ctx["files"], ctx["change"]["body"]
    return {
        "approval_commits": approval_commits(cwd, base_sha, head_sha, ctx["comments"], eligible=pool_members(decl["pools"], team_members)),
        "head_tree": gitutil.ls_tree(head_sha, cwd),
        "head_files": decl["head_files"],
        "base_config": decl["base_config"],
        "extends_texts": decl["extends_texts"],
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
        ),
    }


MAX_APPROVAL_COMMITS = 50


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
    cwd: str, base_sha: str, head_sha: str, comments: list[dict], *, eligible: set[str] | None = None, limit: int = MAX_APPROVAL_COMMITS
) -> dict[str, dict]:
    """For every commit named in a Spec approval line, what that commit had changed since the base.

    It proves Spec approval came before implementation: an approval given on a commit that held only the Spec and its
    tests. The diff runs from the merge-base, so merging the base branch in later adds nothing. A commit that
    is not an ancestor of head proves nothing.

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
        paths = [x for x in gitutil.run(["diff", "--name-only", "-z", f"{base_sha}...{sha}"], cwd, check=False).split("\0") if x] if ancestor else []
        out[sha] = {"ancestor": ancestor, "paths": sorted(paths)}
    return out
