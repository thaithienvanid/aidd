"""The gate rules, one function each, run in order over a shared `Run`.

Each gate reads the context and what earlier gates derived, records facts,
and adds findings. A gate that makes the rest meaningless (no config, no
valid block, no Spec) calls `run.stop()`. To add a rule, write a function
that takes a Run and put it in GATES; org rules that should not live here
go through the Policy interface instead (see policy.py).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NoReturn

from . import __version__, codeowners, globs, model, resources, rules, schema
from . import config as cfgmod
from .util import EPOCH, agent_coauthors, extract_trailers, human_coauthors, is_agent, norm, parse_time, red_ok, scoped, split_tenant

# A command starts at column 0 of its own line (an optional head SHA follows the Spec hash).
APPROVE_SPEC = re.compile(r"^/aidd[ \t]+approve-spec[ \t]+(\S+)[ \t]+([0-9a-f]{32})(?:[ \t]+([0-9a-f]{40}|[0-9a-f]{64}))?[ \t]*$", re.M)
APPROVE = re.compile(r"^/aidd[ \t]+approve[ \t]+([0-9a-f]{40}|[0-9a-f]{64})[ \t]*$", re.M)
_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")

DEFAULT_SYSTEM_ACCOUNTS = ("web-flow",)
BLOCK_EXAMPLE = '```toml aidd\nspec = "specs/SPEC-123.md"\n```'


def bot_standard_change(cfg: cfgmod.Config, ctx: dict) -> dict | None:
    """A block for a bot PR that has none: every author must belong to one configured standard class."""
    system = {norm(x) for x in cfg.get("identities", "system_accounts", default=list(DEFAULT_SYSTEM_ACCOUNTS))}
    people = {norm(c[k]) for c in ctx["commits"] for k in ("author", "committer") if c.get(k)} - system
    people.add(norm(ctx["change"]["author"]))
    for entry in cfg.get("standard_changes", default=[]):
        if people <= {norm(a) for a in entry["authors"]}:
            return {
                "route": "standard",
                "standard_change": entry["name"],
                "type": entry.get("type", "deps"),
                "confidence": "high",
                "scope": list(entry["paths"]),
                "rollback": "Revert the change.",
                "assisted_by": [],
                "risk": {
                    "summary": f"Pre-approved standard change class {entry['name']}.",
                    "dimensions": list(entry.get("dimensions", ["third_party"])),
                    "reversible": True,
                },
            }
    return None


def commands(body: str) -> str:
    """Comment lines that can carry /aidd commands: not in fenced code (an unclosed fence runs to
    the end), not in an indented code block, not quoted, not inside an HTML comment."""
    out: list[str] = []
    fence: str | None = None
    prev_blank = True
    indented = False
    for line in model._HTML_COMMENT.sub("", body or "").splitlines():
        if fence:
            # CommonMark: the closing fence uses the same character, is at least as long, and has no info string.
            close = _FENCE_OPEN.match(line)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence) and not line.strip()[len(close.group(1)) :].strip():
                fence = None
            prev_blank = False
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = m.group(1)
            continue
        if line.startswith(("    ", "\t")) and line.strip() and (prev_blank or indented):
            indented = True
            continue
        indented = False
        if not line.lstrip().startswith(">"):
            out.append(line)
        prev_blank = not line.strip()
    return "\n".join(out)


def agent_account(user: str, bots: set[str] | frozenset[str] = frozenset()) -> bool:
    """An account that is an agent, whatever a pool says: listed in identities.bots, a login the baseline names as an
    agent (`agent_accounts`, such as Copilot's reviewer), or a `[bot]` account whose name carries a known agent name."""
    if user in bots or user in {norm(a) for a in resources.baseline().get("agent_accounts", [])}:
        return True
    if not user.endswith("[bot]"):
        return False
    names = {n.lower() for n in resources.baseline().get("agent_coauthors", {}).get("names", [])}
    return bool(names & set(re.split(r"[^a-z0-9]+", user[: -len("[bot]")])))


class _Pool:
    """Who may approve: users and @org/team entries, resolved through the context.

    With a tenant, an entry qualified with another tenant (`other:alice`) names nobody in this repository, and an entry
    qualified with this tenant (`acme:alice`) is the same as the bare one."""

    def __init__(self, entries: list[str], team_members: dict[str, list[str]], tenant: str | None = None):
        self.entries = list(entries)
        self.named: set[str] = set()
        self.users: set[str] = set()
        self.unresolved: list[str] = []
        for entry in self.entries:
            e = entry
            owner, _ = split_tenant(entry) if tenant else (None, "")
            if owner is not None and owner != tenant:
                continue  # another tenant's person or team never approves here
            if owner is not None:
                e = entry.strip().lstrip("@").split(":", 1)[1]
            n = norm(e)
            if "/" in n and not n.startswith("email:"):
                members = next((team_members[k] for k in (entry, e, "@" + n, n) if k in team_members), None)
                if members is None:
                    self.unresolved.append(e)
                else:
                    self.users.update(norm(m) for m in members)
            else:
                self.named.add(n)
                self.users.add(n)

    def __contains__(self, user: str) -> bool:
        # Bots approve only when named one by one, never through a team.
        return user in self.users and (not user.endswith("[bot]") or user in self.named)


class Stop(Exception):
    """Raised by a gate when the remaining gates cannot say anything useful."""


@dataclass
class Run:
    """What the gates share: the context, the record, and the facts earlier gates derived."""

    ctx: dict
    record: dict
    add: Callable[..., None]
    config: cfgmod.Config | None = None
    spec: dict | None = None
    spec_text: str | None = None
    cr: dict = field(default_factory=dict)
    declared: dict = field(default_factory=dict)
    route: str = ""
    tasks: list[dict] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    design_files: list[str] = field(default_factory=list)
    scope_declared: bool = True
    paths: list[str] = field(default_factory=list)
    changed_lines: int = 0
    binary_files: int = 0
    authors: set[str] = field(default_factory=set)
    bots: set[str] = field(default_factory=set)
    standard_ok: bool = False
    protected_hit: bool = False
    pools: list[str] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)
    latest: dict[str, dict] = field(default_factory=dict)
    approved_at: dict[str, dt.datetime | None] = field(default_factory=dict)
    stale_reviews: list[str] = field(default_factory=list)
    required: list[tuple[dict, str]] = field(default_factory=list)
    green: dict[str, dict] = field(default_factory=dict)
    red: dict[str, dict] = field(default_factory=dict)
    evidence_ok: bool = False

    def stop(self) -> NoReturn:
        raise Stop

    @property
    def cfg(self) -> cfgmod.Config:
        """The config in force; every gate after gate_config may rely on it."""
        assert self.config is not None, "gate_config runs first"
        return self.config

    @property
    def head(self) -> str:
        return self.ctx["head_sha"]

    @property
    def g(self) -> dict:
        return self.cfg.gates

    @property
    def solo(self) -> bool:
        return not self.cfg.gates["separation_of_duties"]

    @property
    def tenant(self) -> str | None:
        return self.config.tenant if self.config is not None else None

    def make_pool(self, entries: list[str]) -> _Pool:
        return _Pool(entries, self.ctx.get("team_members") or {}, self.tenant)

    def local(self, identity: str) -> str:
        """An identity as this repository's config names it: its own tenant's prefix dropped, another tenant's kept."""
        return scoped(identity, self.tenant) or norm(identity)

    @property
    def pool(self) -> _Pool:
        return self.make_pool(self.cfg.approvers)

    @property
    def spec_pool(self) -> _Pool | None:
        return self.make_pool(self.spec.get("approvers") or []) if self.spec and "approvers" in self.spec else None

    def reviewer_pool(self, name: str) -> tuple[_Pool | None, str]:
        """The members of a specialist pool and the pool's name; an unbound pool falls back to security."""
        reviewers = self.cfg.reviewers
        for candidate in (name, "security"):
            if reviewers.get(candidate):
                return self.make_pool(reviewers[candidate]), candidate
        return None, name

    def may_approve(self, user: str, pool: _Pool, narrow: _Pool | None = None) -> bool:
        """Only members of the pool approve; a bot only when the pool names it. Authors approve only under solo.

        Solo waives one rule, that an author cannot approve their own change. It never
        widens the pool: an outsider's pull request on a solo repository still needs an
        approval from someone in owners.approvers.
        """
        if user in self.bots or agent_account(user, self.bots) or (narrow is not None and user not in narrow) or user not in pool:
            return False
        return self.solo or user not in self.authors

    def cooled(self, user: str) -> bool:
        cooloff = self.g["cooloff_minutes"].get(self.route, 0)
        if not cooloff:
            return True
        # On a platform, head_pushed_at is when the head reached it. With platform "local" nothing is pushed, so the
        # local context sets it to the head commit's committer date: the best available locally, and set by the committer.
        pushed, t = parse_time(self.ctx.get("head_pushed_at")), self.approved_at.get(user)
        return bool(pushed and t and (t - pushed) >= dt.timedelta(minutes=cooloff))

    def owner_entries(self, candidates: list[str]) -> list[dict]:
        """Per-path owners the given paths touch: config owners.paths, plus CODEOWNERS when enabled."""
        found = [e for e in self.cfg.get("owners", "paths", default=[]) if any(globs.match_any(e["paths"], x, fold_case=True) for x in candidates)]
        if self.cfg.get("owners", "codeowners"):
            found += codeowners.entries(self.ctx.get("codeowners"), candidates)
        return found


def _stamp(t: dt.datetime | None) -> str | None:
    """A time as RFC 3339 UTC to the second, or None."""
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("-")[0].split("+")[0].split(".")[:3])
    except ValueError:
        return (0,)


def gate_config(run: Run) -> None:
    """Config comes from the base branch. A base without one never passes: an administrator merges the first config."""
    ctx, add = run.ctx, run.add
    run.record.update(
        change=ctx["change"]["id"], platform=ctx.get("platform"), head_sha=run.head, base_sha=ctx["base_sha"], trusted=bool(ctx.get("trusted", False))
    )
    cfg_text = ctx.get("base_config")
    bootstrap = False
    if cfg_text is None:
        cfg_text = ctx["head_files"].get(cfgmod.CONFIG_PATH)
        bootstrap = cfg_text is not None
    if cfg_text is None:
        add(
            "config",
            "fail",
            f"no {cfgmod.CONFIG_PATH} on the base branch or in this change",
            "run `aidd init` and merge the config first",
            code="config.missing",
        )
        run.stop()
    try:
        run.config = cfgmod.load_text(cfg_text, prefetched=ctx.get("extends_texts") or {}, root_preset=ctx.get("org_preset"))
    except (cfgmod.ConfigError, model.ModelError) as exc:
        add("config", "fail", str(exc), "fix .aidd/config.toml on the base branch", code="config.invalid")
        run.stop()
    cfg = run.cfg
    parts = [cfg_text, ctx.get("org_preset") or "", *(x for kv in sorted((ctx.get("extends_texts") or {}).items()) for x in kv)]
    run.record["config_sha256"] = hashlib.sha256("".join(f"{len(x)}:{x}" for x in parts).encode("utf-8")).hexdigest()
    if not bootstrap and cfg.get("mode"):
        run.record["config_mode"] = cfg.get("mode")  # a config the change itself adds never sets the mode
    if bootstrap:
        add(
            "config",
            "pending",
            "the base branch has no config, so this change cannot pass the gate",
            "a repository administrator merges the first config outside the gate; later changes are gated",
            code="config.bootstrap",
        )
    for w in cfg.warnings:
        add("config", "warn", w, code="config.warning")
    run.record.update(profile=cfg.profile, tenant=cfg.tenant)
    declared_version = str(cfg.get("aidd_version", default="") or "")
    if declared_version and _version_tuple(declared_version) > _version_tuple(__version__):
        add(
            "config",
            "warn",
            f"the config declares aidd_version {declared_version}, newer than this verifier ({__version__})",
            "upgrade the verifier pins (the workflow refs and the CLI) together with the config, as docs/INSTALL.md describes",
            code="config.newer_version",
        )
    if not cfg.approvers:
        add(
            "config",
            "fail",
            f"profile {cfg.profile} requires owners.approvers",
            'list approvers, for example approvers = ["@org/team"], or your own login under solo; an empty list means no change can merge (the gate fails closed)',
            code="config.no_approvers",
        )


def gate_change_request(run: Run) -> None:
    """The declared part: one toml aidd block, and the Spec it names."""
    ctx, add = run.ctx, run.add
    cr, errs = model.parse_change_block(ctx["change"]["body"])
    if cr is None and not errs:
        cr = bot_standard_change(run.cfg, ctx)
        if cr is None:
            add(
                "change_request",
                "fail",
                "the description has no ```toml aidd block",
                f"add one (`aidd change` prints a starting point), for example:\n{BLOCK_EXAMPLE}",
                code="change_request.no_block",
            )
            run.stop()
        add(
            "change_request",
            "warn",
            f"no toml aidd block: treated as standard change {cr['standard_change']!r}, because every author belongs to that class",
            code="change_request.standard_by_default",
        )
    for e in errs:
        add("change_request", "fail", e, code="change_request.invalid")
    if errs:
        run.stop()
    assert cr is not None  # no block and no errors was handled above
    run.cr = cr
    if "spec" in cr:
        spec_path = cr["spec"]
        run.spec_text = ctx["head_files"].get(spec_path)
        if run.spec_text is None:
            add("spec", "fail", f"{spec_path} is not in the head commit", "commit the Spec file at that path", code="spec.not_at_head")
            run.stop()
        try:
            loaded, _body, serrs = model.load_object(run.spec_text, spec_path)
        except model.ModelError as exc:
            add("spec", "fail", str(exc), code="spec.unparsable")
            run.stop()
        if loaded.get("kind") != "spec":
            serrs = serrs or [f"{spec_path}: kind must be spec"]
        for e in serrs:
            add("spec", "fail", e, code="spec.invalid")
        if serrs:
            run.stop()
        extra = sorted(set(cr) - {"spec", "trace_id"})
        if extra:
            add(
                "change_request", "fail", f"with spec set, the block holds only spec and trace_id; move {extra} into the Spec", code="change_request.extra_keys"
            )
        if cr.get("trace_id") and cr["trace_id"] != loaded.get("trace_id", loaded["id"]):
            add(
                "change_request",
                "fail",
                f"trace_id {cr['trace_id']!r} differs from the Spec trace_id {loaded.get('trace_id', loaded['id'])!r}",
                code="change_request.trace_id_mismatch",
            )
        run.spec = loaded
        run.declared = loaded
    else:
        if cr["route"] in ("normal", "major"):
            add(
                "spec", "fail", f"route {cr['route']} needs a Spec file", 'write specs/<ID>.md and set spec = "specs/<ID>.md" in the block', code="spec.missing"
            )
            run.stop()
        run.scope_declared = "scope" in cr
        run.declared = model.with_defaults(cr, rules.changed_paths(ctx["files"]))
    declared, spec = run.declared, run.spec
    run.route = declared["route"]
    run.tasks = spec["tasks"] if spec else [{"id": "inline", "title": "inline", "scope": list(declared["scope"])}]
    tests_decl = declared.get("tests")
    run.test_files = list(tests_decl["files"]) if tests_decl else []
    run.design_files = list(((spec or {}).get("design") or {}).get("files", []))
    run.record.update(
        spec=cr.get("spec"),
        spec_id=spec["id"] if spec else None,
        trace_id=declared.get("trace_id", spec["id"] if spec else None),
        owner_team=spec.get("owner_team") if spec else None,
        route=run.route,
        type=declared["type"],
        confidence=declared["confidence"],
        risk=declared["risk"],
        rollback=declared["rollback"],
        residual_risk=declared.get("residual_risk"),
        assisted_by=declared["assisted_by"],
        scope=sorted({s for task in run.tasks for s in task["scope"]}),
        scope_declared=run.scope_declared,
    )
    if declared["confidence"] == "low":
        add("confidence", "fail", "confidence is low", "answer the open_questions, then run `aidd next` again", code="confidence.low")
    if not spec and cr.get("route") == "emergency" and cr.get("backfill"):
        _check_backfill(run, cr)
    if not spec and run.scope_declared:
        # An inline block has no human before the diff, so its scope must be narrow and its tests separate.
        for pattern in list(declared["scope"]) + list(run.test_files):
            if globs.is_catch_all(pattern):
                add(
                    "scope",
                    "fail",
                    f"{pattern!r} matches every path, so it declares no scope",
                    "name the files or directories the change touches",
                    code="scope.catch_all",
                )
        for pattern in declared["scope"]:
            for tf in run.test_files:
                if globs.overlap(pattern, tf):
                    add("scope", "fail", f"scope {pattern!r} overlaps test file {tf!r}", "keep test files out of the scope", code="scope.overlaps_test")
    elif not spec:
        for tf in run.test_files:
            if globs.is_catch_all(tf):
                add("scope", "fail", f"{tf!r} matches every path, so it names no test file", "name the test files or directories", code="scope.test_catch_all")


def _check_backfill(run: Run, cr: dict) -> None:
    """An emergency commits its backfill Spec stub, so the review debt is visible to `aidd validate`."""
    path = cr["backfill"]
    text = run.ctx["head_files"].get(path)
    fix = f"commit the stub: aidd new spec <ID> --route emergency, at {path}, with the same review_due"
    if text is None:
        run.add("emergency", "fail", f"the backfill Spec {path} is not in the head commit", fix, code="emergency.backfill_missing")
        return
    try:
        data, _ = model.split_front_matter(text, path)
    except model.ModelError as exc:
        run.add("emergency", "fail", str(exc), fix, code="emergency.backfill_unparsable")
        return
    due = str((data.get("emergency") or {}).get("review_due", ""))
    if data.get("kind") != "spec" or data.get("route") != "emergency" or due != str(cr["emergency"]["review_due"]):
        run.add(
            "emergency",
            "fail",
            f"{path} must be a Spec with route emergency and review_due {cr['emergency']['review_due']}",
            fix,
            code="emergency.backfill_mismatch",
        )


def gate_facts(run: Run) -> None:
    """Facts from the platform: the diff, and who authored the change."""
    ctx, cfg, add = run.ctx, run.cfg, run.add
    files = ctx["files"]
    run.paths = rules.changed_paths(files)
    reviewed: list[str] = []
    if run.spec:
        # The Spec and its tests were reviewed at Spec approval; the budget measures what is left to review at Merge approval.
        reviewed += [run.cr["spec"], *run.test_files, *run.design_files]
    if run.cr.get("backfill"):
        reviewed.append(run.cr["backfill"])
    run.changed_lines = rules.budget_lines(files, cfg, reviewed)
    run.binary_files = sum(1 for f in files if f.get("binary"))
    run.record.update(changed_paths=run.paths, changed_files=len(files), changed_lines=run.changed_lines, binary_files=run.binary_files)
    if ctx.get("commits_truncated"):
        add(
            "authors",
            "fail",
            "the platform returned only part of the commit list, so authors cannot be verified",
            "split the change, or squash it below the platform's commit limit",
            code="authors.truncated",
        )
    system = {norm(x) for x in cfg.get("identities", "system_accounts", default=list(DEFAULT_SYSTEM_ACCOUNTS))}
    run.bots = {run.local(x) for x in cfg.get("identities", "bots", default=[])}
    authors = {run.local(c[k]) for c in ctx["commits"] for k in ("author", "committer") if c.get(k)}
    # A co-author wrote part of the change too, so they may not approve it.
    authors |= {norm(x) for c in ctx["commits"] for x in human_coauthors(c.get("message") or "", run.bots)}
    run.authors = (authors - system) | {run.local(ctx["change"]["author"])}
    run.record["authors"] = sorted(run.authors)
    # A commit email the platform cannot map to an account might belong to an Approver,
    # so separation of duties cannot be proven for it.
    unlinked = sorted(o for o in run.authors if o.startswith("email:") and o not in run.bots)
    if unlinked and not run.solo and not ctx.get("committer_approval_blocked"):
        level = "fail" if run.g["unlinked_authors"] == "fail" else "warn"
        add(
            "authors",
            level,
            f"commit author(s) {', '.join(unlinked[:5])} are not linked to a platform account, so an Approver may have written them",
            "link the email to its account, list agent emails in identities.bots, or rewrite the commits",
            code="authors.unlinked",
        )


def gate_standard_change(run: Run) -> None:
    if run.route != "standard":
        return
    cfg, add = run.cfg, run.add
    name = run.cr.get("standard_change")
    entry = next((e for e in cfg.get("standard_changes", default=[]) if e["name"] == name), None)
    if not run.g["standard_changes"]:
        add("standard_change", "fail", f"profile {cfg.profile} does not allow standard changes", code="standard_change.not_allowed")
    elif entry is None:
        add(
            "standard_change",
            "fail",
            f"no standard_changes entry named {name!r} in the config",
            "set standard_change to a configured class, or use another route",
            code="standard_change.unknown_class",
        )
    else:
        problems = rules.standard_match(entry, paths=run.paths, identities=run.authors, changed_lines=run.changed_lines)
        unsigned = [c["sha"][:10] for c in run.ctx["commits"] if c.get("verified") is not True]
        if unsigned:
            problems.append(f"commits without a platform-verified signature: {', '.join(unsigned[:5])}")
        for p in problems:
            add("standard_change", "fail", f"{name}: {p}", code="standard_change.mismatch")
        run.standard_ok = not problems


def gate_route(run: Run) -> None:
    """Assess the real diff. A Spec-backed normal change is raised to major; anything else below the minimum fails."""
    add, declared, spec = run.add, run.declared, run.spec
    risk = declared["risk"]
    cls = rules.assess(
        paths=run.paths,
        cfg=run.cfg,
        ctype=declared["type"],
        risk=risk,
        confidence=declared["confidence"],
        task_count=len(run.tasks),
        changed_lines=run.changed_lines,
        standard_ok=run.standard_ok,
        binary_files=run.binary_files,
    )
    run.protected_hit = any(h.rule == "protected" for h in cls.hits)
    run.pools = sorted(cls.pools)
    run.record.update(required_route=cls.required_route, route_reasons=cls.reasons, required_pools=run.pools)
    undeclared = sorted(cls.dimensions - set(risk["dimensions"]))
    if undeclared:
        # A Spec-backed change gets the implied gates anyway (the overlay below); an inline block must declare them.
        add(
            "route",
            "warn" if spec else "fail",
            f"risk.dimensions must include {undeclared}, which the changed paths imply",
            "add them to risk.dimensions" + (" (the gate already applies them)" if spec else " and run `aidd next` again"),
            code="route.undeclared_dimensions",
        )
    if run.route == "emergency":
        if cls.required_route == "major":
            add(
                "emergency",
                "warn",
                f"outside an emergency this repair would be major: the {', '.join(run.pools)} review still applies, and the post-incident review must cover it",
                code="emergency.would_be_major",
            )
    elif spec is not None and run.route == "normal" and cls.required_route == "major":
        # major is an overlay the gate computes, not a route an author must guess: a Spec-backed
        # change is raised, and the major gates (specialist review, observe, cool-off) apply.
        run.route = "major"
        run.record.update(route=run.route, declared_route="normal")
        add(
            "route",
            "warn",
            "raised to major: " + "; ".join(cls.reasons),
            f"major gates now apply: an approval from the {', '.join(run.pools)} pool(s) and an observe block",
            code="route.raised_to_major",
        )
    elif run.route == "standard" and not run.standard_ok:
        pass  # the standard_change rule already says why; a second route failure is noise
    elif rules.ROUTE_RANK[run.route] < rules.ROUTE_RANK[cls.required_route]:
        need_spec = " and write a Spec" if cls.required_route in ("normal", "major") and spec is None else ""
        add(
            "route",
            "fail",
            f"declared {run.route}, but the change requires {cls.required_route}: " + "; ".join(cls.reasons),
            f'set route = "{cls.required_route}"{need_spec}',
            code="route.too_low",
        )


def gate_scope(run: Run) -> None:
    """Every changed path sits inside some Task's scope, a test or design file, the Spec, or scope_exempt_paths."""
    allowed = [s for task in run.tasks for s in task["scope"]] + run.test_files + run.design_files + run.cfg.get("scope_exempt_paths", default=[])
    allowed += [run.cr[key] for key in ("spec", "backfill") if run.cr.get(key)]
    outside = [p for p in run.paths if not globs.match_any(allowed, p)]
    if outside:
        shown = ", ".join(outside[:10]) + (" ..." if len(outside) > 10 else "")
        run.add(
            "scope",
            "fail",
            f"{len(outside)} changed path(s) outside the scope: {shown}",
            "add a Task or widen the scope in the Spec (the Spec needs approval again), or drop those edits",
            code="scope.outside",
        )
    # Plan adherence: a Task whose scope no changed path touches was not delivered, or the plan was wrong.
    # Either way the Approver should know before Merge approval; it warns rather than fails, because a Task can
    # legitimately end up needing no change.
    if run.spec:
        untouched = [t["id"] for t in run.tasks if not any(globs.match_any(t["scope"], p) for p in run.paths)]
        run.record["plan"] = {"tasks": len(run.tasks), "untouched_tasks": untouched}
        if untouched:
            run.add(
                "scope",
                "warn",
                f"Task(s) {', '.join(untouched)} changed nothing in their scope: the plan and the diff disagree",
                "finish the Task, or remove it from the Spec if it turned out to need no change (the Spec needs approval again)",
                code="scope.untouched_task",
            )


def gate_budget(run: Run) -> None:
    budget = None if run.route in ("standard", "emergency") else run.g["max_changed_lines"].get(run.route)
    if budget is not None and run.changed_lines > budget:
        run.add(
            "budget",
            "fail",
            f"{run.changed_lines} changed lines exceed the {run.route} budget of {budget}",
            "split into smaller Specs or Tasks, or exclude generated files with budget_exclude_paths",
            code="budget.exceeded",
        )


def gate_merge_queue(run: Run) -> None:
    """A merge-queue entry ships exactly the approved head merged into the commit it was built on, and nothing else.

    Approvals stay bound to `head_sha`, so the merge-group commit's tree must be what merging that head into
    `merge_group.base_sha` gives. A stacked entry also carries earlier entries' changes, which only their own gate
    runs judged, so it passes only when the platform merges a group once every entry in it passed.
    """
    group = run.ctx.get("merge_group")
    if not group:
        return
    run.record["merge_group_sha"] = group["sha"]
    if group["merged_tree"] is None:
        run.add(
            "merge_queue",
            "fail",
            f"the approved head {run.head[:12]} does not merge cleanly into {group['base_sha'][:12]}, the commit the queue entry was built on",
            "update the pull request from its base, get it approved on the new head, and queue it again",
            code="merge_queue.conflict",
        )
    elif group["tree"] != group["merged_tree"]:
        run.add(
            "merge_queue",
            "fail",
            f"the merge-group commit {group['sha'][:12]} is not the approved head {run.head[:12]} merged into {group['base_sha'][:12]}: "
            "it holds changes nobody approved, or lacks approved ones",
            "remove the entry and queue the pull request again from its approved head",
            code="merge_queue.diff_mismatch",
        )
    if group["stacked"] and group.get("all_green") is not True:
        run.add(
            "merge_queue",
            "fail",
            f"the entry is built on another queue entry ({group['base_sha'][:12]}), and the queue is not confirmed to merge only groups whose "
            "every entry passed, so a failing entry ahead could merge with this one",
            'turn on "Only merge non-failing pull requests" in the merge queue rule (grouping strategy ALLGREEN), or build one entry at a time',
            code="merge_queue.stacked_unverified",
        )


NO_OP = {"true", ":", "exit", "echo", "/bin/true", "/usr/bin/true"}
_NO_OP_ARGS = {"true", ":", "pass", "exit 0", "exit 0;", "; true", "noop"}
_NO_OP_WRAPPERS = {"sh", "bash", "zsh", "/bin/sh", "/bin/bash", "env", "nohup", "time", "nice", "python", "python3", "make"}


def is_no_op_command(cmd: list[str]) -> bool:
    if not cmd or cmd[0].strip() in NO_OP:
        return True
    return (cmd[0].strip() in _NO_OP_WRAPPERS or len(cmd) == 1) and any(arg.strip() in _NO_OP_ARGS for arg in cmd[1:])


def gate_tests_declared(run: Run) -> None:
    """Which tests apply to this diff, and whether the repository has any at all."""
    cfg, add, spec = run.cfg, run.add, run.spec
    config_cmds = cfg.get("tests", default=[])
    declared_cmds = (run.declared.get("tests") or {}).get("commands", [])
    run.required, dupes = rules.required_tests(config_cmds, declared_cmds, "spec" if spec else "change_request", run.paths)
    for dup in dupes:
        add("tests", "fail", f"test name {dup!r} is declared twice (config and Spec)", "give every test command a unique name", code="tests.duplicate_name")
    status_names = cfg.get("evidence", "status_checks", default=[])
    if not config_cmds and not declared_cmds and not status_names:
        add(
            "tests",
            "fail",
            "no tests: the config has no [[tests]] or evidence.status_checks, and the change declares none",
            "characterization: name one command that proves today's behavior, in the config or the Spec",
            code="tests.none",
        )
    elif not run.required and not status_names:
        add("tests", "warn", "no test applies to this diff: every command's when_changed misses the changed paths", code="tests.none_applies")
    if not spec and run.route == "minor" and not config_cmds and not status_names and declared_cmds:
        # Nobody reviews an inline block before the diff, so its own commands cannot stand in for a suite.
        add(
            "tests",
            "fail",
            "a minor change needs the repository suite ([[tests]]) or evidence.status_checks; inline tests only add to it",
            "bind the repository suite in the config, or write a Spec (its tests are reviewed at Spec approval)",
            code="tests.minor_without_suite",
        )
    for c in declared_cmds:
        if is_no_op_command(c.get("command", [])):
            add("tests", "fail", f"{c['name']}: {c['command']} proves nothing", "run a command that fails when the behavior is wrong", code="tests.no_op")


def gate_status_checks(run: Run) -> None:
    """Existing CI as evidence: named check runs must succeed on this head."""
    names = run.cfg.get("evidence", "status_checks", default=[])
    if not names:
        return
    states = run.ctx.get("status_checks") or {}
    run.record["status_checks"] = {name: states.get(name, "missing") for name in names}
    for name in names:
        state = states.get(name, "missing")
        if state in ("success", "neutral"):
            continue
        if state == "skipped":
            run.add(
                "tests", "pending", f"check run {name!r} is skipped on head {run.head[:12]}", "the check did not run on this head", code="tests.check_skipped"
            )
        elif state in ("pending", "queued", "in_progress", "missing"):
            run.add("tests", "pending", f"check run {name!r} is {state} on head {run.head[:12]}", "wait for your CI", code="tests.check_waiting")
        else:
            run.add("tests", "fail", f"check run {name!r} is {state} on head {run.head[:12]}", "fix the change until your CI passes", code="tests.check_failed")


def gate_evidence(run: Run) -> None:
    """Every applicable command has a green result on this exact head and base."""
    ctx, add, head, record = run.ctx, run.add, run.head, run.record
    record["tests"] = []
    if not run.required:
        return
    ev = ctx.get("evidence")
    if ev is None:
        add("tests", "pending", f"no test evidence for head {head[:12]} yet", "wait for aidd-tests, or run `aidd test`", code="tests.no_evidence")
        return
    if ev.get("invalid"):
        add(
            "tests",
            "fail",
            f"evidence: {ev['invalid']}",
            "re-run aidd-tests; if it repeats, the test job is writing a corrupt artifact",
            code="tests.evidence_invalid",
        )
        return
    everrs = schema.validate(ev, "evidence.schema.json")
    if everrs:
        for e in everrs:
            add("tests", "fail", f"evidence: {e}", code="tests.evidence_schema")
        return
    if ev.get("partial"):
        add(
            "tests",
            "pending",
            "the evidence is partial: `aidd test --changed` ran only the commands the working-tree diff selects",
            "run `aidd test` without --changed; in CI, wait for aidd-tests",
            code="tests.evidence_partial",
        )
        return
    # In a merge queue the tests re-run on the merge-group commit, against the commit the entry was built on.
    group = ctx.get("merge_group")
    want_head, want_base = (group["sha"], group["base_sha"]) if group else (head, ctx["base_sha"])
    what = "merge-group commit" if group else "head"
    if ev["head_sha"] != want_head:
        add(
            "tests",
            "pending",
            f"evidence is for {ev['head_sha'][:12]}, the {what} is {want_head[:12]}",
            f"wait for a run on the current {what}",
            code="tests.evidence_other_head",
        )
        return
    if ev["base_sha"] != want_base:
        add(
            "tests",
            "pending",
            f"evidence ran against base {ev['base_sha'][:12]}, the change's base is {want_base[:12]}",
            "re-run aidd-tests for this pull request" + (" in the merge queue" if group else ""),
            code="tests.evidence_other_base",
        )
        return
    rank: dict[str | None, int] = {"failed": 2, "timeout": 2, "not_started": 1, "passed": 0}

    def badness(r: dict) -> tuple[int, bool]:
        return rank.get(r.get("status"), 0), r.get("exit") != 0

    seen_results: set[tuple[str, str]] = set()
    run.green, run.red = {}, {}
    for r in ev["results"]:
        name, phase = r["name"], r["phase"]
        if (name, phase) in seen_results:
            add(
                "tests",
                "fail",
                f"duplicate test result {name!r} in phase {phase!r}",
                "each test command must have at most one result per phase",
                code="tests.duplicate_result",
            )
        seen_results.add((name, phase))
        target = run.green if phase == "green" else run.red if phase == "red" else None
        if target is not None and (name not in target or badness(r) > badness(target[name])):
            target[name] = r
    run.evidence_ok = True
    if ev.get("runner"):
        record["evidence_runner"] = dict(ev["runner"])
    for c, src in run.required:
        r = run.green.get(c["name"])
        if r is None:
            add("tests", "fail", f"{c['name']}: no result on head", "re-run aidd-tests", code="tests.no_result")
            continue
        entry = {"name": c["name"], "source": src, "command": r["command"], "exit": r.get("exit"), "status": r["status"], "duration_s": r.get("duration_s")}
        red = run.red.get(c["name"])
        if red is not None:
            entry.update(red_exit=red.get("exit"), red_status=red["status"])
        record["tests"].append(entry)
        if r["command"] != c["command"]:
            add("tests", "fail", f"{c['name']}: the runner ran {r['command']}, the declaration says {c['command']}", code="tests.command_mismatch")
        elif r["status"] != "passed" or r.get("exit") != 0:
            add(
                "tests",
                "fail",
                f"{c['name']}: {r['status']} (exit {r.get('exit')})",
                "an implementation error or a flake retries in Implement (at most 3); a wrong Spec returns to Specify",
                code="tests.failed",
            )


def gate_red_green(run: Run) -> None:
    """New behavior failed on the base commit, for the right reason, with the declared command."""
    if not run.evidence_ok:
        return
    add = run.add
    level = "fail" if run.g["red_green"] == "require" else "warn"
    new_behavior = [c for c, _ in run.required if c.get("new_behavior")]
    ctype = run.declared["type"]
    if run.spec and run.route in ("normal", "major") and ctype in rules.NEW_BEHAVIOR_TYPES and not new_behavior:
        add(
            "red_green",
            level,
            f"a {ctype} change needs at least one test command with new_behavior = true",
            "write a test that fails on the base commit and passes with the change",
            code="red_green.no_new_behavior",
        )
    for c in new_behavior:
        r = run.red.get(c["name"])
        if r is None:
            add("red_green", level, f"{c['name']}: no red run against the base commit", "run `aidd test` without --no-red", code="red_green.no_red_run")
        elif r["command"] != c["command"]:
            add("red_green", level, f"{c['name']}: the red run used {r['command']}, the declaration says {c['command']}", code="red_green.red_command_mismatch")
        elif r["status"] == "passed":
            add(
                "red_green",
                level,
                f"{c['name']}: passes on the base commit, so it does not prove new behavior",
                "tighten the test",
                code="red_green.passes_on_base",
            )
        elif not red_ok(r):
            add(
                "red_green",
                level,
                f"{c['name']}: red run was {r['status']} (exit {r.get('exit')}); it must fail by assertion",
                "make the test fail fast on base",
                code="red_green.red_not_assertion",
            )


def _signed_local_approvals(run: Run, comments: list[dict], reviews: list[dict]) -> tuple[list[dict], list[dict]]:
    """Under `gates.local_approvals = "signed"`, a local approval counts only when the adapter verified its git signature
    (`verified: true`); the rest are dropped here, in the verifier, so the rule holds for any context, not only aidd's own."""
    kept_c = [c for c in comments if c.get("verified") is True]
    kept_r = [r for r in reviews if r.get("verified") is True]
    dropped_spec = [c for c in comments if c.get("verified") is not True and APPROVE_SPEC.search(commands(c["body"]))]
    dropped_merge = [r for r in reviews if r.get("verified") is not True and r["state"] == "approved"]
    dropped_merge += [c for c in comments if c.get("verified") is not True and APPROVE.search(commands(c["body"]))]
    fix = "the approver records it again with git commit signing set up (`aidd approve`), with a key git trusts"
    if dropped_spec:
        who = ", ".join(sorted({norm(c["user"]) for c in dropped_spec}))
        run.add(
            "spec_approval",
            "warn",
            f'gates.local_approvals = "signed": Spec approvals without a verified signature do not count ({who})',
            fix,
            code="spec_approval.unsigned",
        )
    if dropped_merge:
        who = ", ".join(sorted({norm(x["user"]) for x in dropped_merge}))
        run.add(
            "merge_approval",
            "warn",
            f'gates.local_approvals = "signed": approvals without a verified signature do not count ({who})',
            fix,
            code="merge_approval.unsigned",
        )
    return kept_c, kept_r


def _tenant_scoped(run: Run, comments: list[dict], reviews: list[dict]) -> tuple[list[dict], list[dict]]:
    """With a tenant, every comment and review under its identity as the config names it; one by an identity another
    tenant qualifies is dropped here, so its approval never counts, whatever pool or platform account it resembles."""
    tenant = run.tenant
    if not tenant:
        return comments, reviews
    kept_c: list[dict] = []
    kept_r: list[dict] = []
    foreign_spec: set[str] = set()
    foreign_merge: set[str] = set()
    for c in comments:
        local = scoped(c["user"], tenant)
        if local is None:
            body = commands(c["body"])
            if APPROVE_SPEC.search(body):
                foreign_spec.add(norm(c["user"]))
            if APPROVE.search(body):
                foreign_merge.add(norm(c["user"]))
            continue
        kept_c.append({**c, "user": local})
    for r in reviews:
        local = scoped(r["user"], tenant)
        if local is None:
            if r["state"] == "approved":
                foreign_merge.add(norm(r["user"]))
            continue
        kept_r.append({**r, "user": local})
    fix = f"an Approver of tenant {tenant!r} approves; an identity qualified with another tenant never approves here"
    if foreign_spec:
        run.add(
            "spec_approval",
            "warn",
            f"Spec approvals by identities of another tenant do not count ({', '.join(sorted(foreign_spec))})",
            fix,
            code="spec_approval.other_tenant",
        )
    if foreign_merge:
        run.add(
            "merge_approval",
            "warn",
            f"approvals by identities of another tenant do not count ({', '.join(sorted(foreign_merge))})",
            fix,
            code="merge_approval.other_tenant",
        )
    return kept_c, kept_r


def _agent_approvals(run: Run, reviews: list[dict]) -> None:
    """An approval review from an agent, or from a bot no pool names, never counts here; a platform's own review count
    may still take it, so say so."""
    named = run.pool.named
    users = {norm(r["user"]) for r in reviews if r["state"] == "approved"}
    who = {u for u in users if agent_account(u, run.bots) or (cfgmod.is_bot(u) and u not in named)}
    if who:
        run.add(
            "merge_approval",
            "warn",
            f"an agent or bot approved on the platform ({', '.join(sorted(who))}); it never counts toward Merge approval, and your "
            "branch rules may be counting it",
            "require the aidd/gate status in the branch rules (docs/PLATFORMS.md, GitHub rulesets and aidd), and have a person approve",
            code="merge_approval.agent_approval",
        )


def derive_approvals(run: Run) -> None:
    """Facts both approval gates read: unedited comments, each reviewer's latest review, and approvals on head."""
    ctx, head = run.ctx, run.head
    run.record["separation_of_duties"] = "waived_solo" if run.solo else "enforced"
    comments, reviews = _tenant_scoped(run, ctx["comments"], ctx["reviews"])
    _agent_approvals(run, reviews)
    if ctx.get("platform") == "local" and run.g.get("local_approvals") == "signed":
        comments, reviews = _signed_local_approvals(run, comments, reviews)
    run.comments = [c for c in comments if not c.get("edited")]
    if any(c.get("edited") for c in comments):
        run.add("edited_comments", "warn", "edited comments are ignored; post a new comment to approve", code="edited_comments.ignored")
    for r in sorted(reviews, key=lambda r: parse_time(r.get("submitted_at")) or EPOCH):
        if r["state"] != "commented":  # a comment does not clear an approval or a change request
            run.latest[norm(r["user"])] = r
    # Retargeting the change to another base changes its diff, so an earlier approval approved something else.
    rebased = parse_time(ctx.get("base_changed_at"))
    for u, r in run.latest.items():
        if r["state"] == "approved":
            at = parse_time(r.get("submitted_at"))
            if (r.get("commit_sha") or "") == head and not (rebased and (at is None or at < rebased)):
                run.approved_at[u] = at
            else:
                run.stale_reviews.append(u)
    if run.solo:
        for c in run.comments:
            for m in APPROVE.finditer(commands(c["body"])):
                at = parse_time(c.get("created_at"))
                if m.group(1) == head and not (rebased and (at is None or at < rebased)):
                    run.approved_at.setdefault(norm(c["user"]), at)


def gate_spec_approval(run: Run) -> None:
    """Spec approval: an eligible Approver approved the exact Spec hash; every touched owner area too."""
    ctx, add, spec, record = run.ctx, run.add, run.spec, run.record
    if not (spec and run.route in run.g["spec_approval_routes"]):
        return
    h = model.spec_hash(run.spec_text or "", ctx["head_tree"])
    record["spec_hash"] = h
    good: set[str] = set()
    given: dict[str, dict] = {}  # user -> when the counted approval was given, and the commit it named
    proofs: dict[str, bool] = {}  # user -> the approval named a commit holding only the Spec and its frozen files
    stale = False
    frozen = [run.cr["spec"], *run.test_files, *run.design_files]
    for c in run.comments:
        for m in APPROVE_SPEC.finditer(commands(c["body"])):
            if m.group(1) != spec["id"]:
                continue
            if m.group(2) != h:
                stale = True
                continue
            user = norm(c["user"])
            sha = m.group(3) or ""
            if sha and sha == ctx.get("base_sha"):
                add("spec_approval", "warn", f"approval names the base commit {sha[:12]}, which proves no Spec commit", code="spec_approval.names_base")
            commit = (ctx.get("approval_commits") or {}).get(sha)
            if commit is not None:
                proven = (
                    bool(commit["ancestor"] and commit["paths"]) and sha != ctx.get("base_sha") and all(globs.match_any(frozen, p) for p in commit["paths"])
                )
                proofs[user] = proofs.get(user, False) or proven
            if run.g["spec_approval_proof"] == "require" and not proofs.get(user):
                continue
            good.add(user)
            given.setdefault(user, {"identity": user, "at": c.get("created_at"), "commit": sha or None})
    if proofs:
        record["spec_approval_before_implementation"] = any(proofs.values())
        if not any(proofs.values()):
            add(
                "spec_approval",
                "warn",
                "the approved commit already held changes beyond the Spec and its tests, so Spec approval came after implementation began",
                code="spec_approval.after_implementation",
            )
    else:
        record["spec_approval_before_implementation"] = False
    if run.g["spec_approval_proof"] == "require" and not good:
        add(
            "spec_approval",
            "pending",
            "profile requires the approval to name the commit it was given on, holding only the Spec and its tests",
            f"approve with the line `aidd hash {run.cr['spec']} --comment` prints on that commit",
            code="spec_approval.commit_required",
        )
    pool, spec_pool = run.pool, run.spec_pool
    spec_ok = sorted(u for u in good if run.may_approve(u, pool, spec_pool))
    record["spec_approved_by"] = spec_ok
    record["spec_approvals"] = [given[u] for u in spec_ok]
    touched = [globs.sample_path(s) for task in spec["tasks"] for s in task["scope"]] + run.paths
    for entry in run.owner_entries(touched):
        epool = run.make_pool(entry["approvers"])
        if not [u for u in good if run.may_approve(u, epool)]:
            add(
                "spec_approval",
                "pending",
                f"Spec {spec['id']} touches {', '.join(entry['paths'])}: it needs a Spec approval from {', '.join(entry['approvers'])}",
                f"one of {', '.join(entry['approvers'])} comments: /aidd approve-spec {spec['id']} {h}",
                code="spec_approval.owner_area",
            )
    if not spec_ok:
        note = " (earlier approvals were for a different Spec or tests)" if stale else ""
        add(
            "spec_approval",
            "pending",
            f"Spec {spec['id']} needs approval of hash {h}{note}",
            f"an eligible Approver comments: /aidd approve-spec {spec['id']} {h}"
            + (" (on this machine: `aidd approve spec` at their own terminal)" if run.ctx.get("platform") == "local" else ""),
            code="spec_approval.missing",
        )
    if run.g["specialist_spec_approval"] and run.route == "major":
        for name in run.pools:
            spool, bound = run.reviewer_pool(name)
            if spool is None or not [u for u in good if run.may_approve(u, spool)]:
                add(
                    "specialist_review",
                    "pending",
                    f"Spec {spec['id']} needs an approval of hash {h} from the {name} pool",
                    f"a member of owners.reviewers.{bound} comments: /aidd approve-spec {spec['id']} {h}",
                    code="specialist_review.spec_missing",
                )


def gate_merge_approval(run: Run) -> None:
    """Merge approval: as many eligible Approvers as the route requires (`gates.approvals`) approved the head commit, owners of touched areas too, and nobody whose approval could be needed requested changes."""
    cfg, add, head, g = run.cfg, run.add, run.head, run.g
    pool = run.pool
    approved = sorted(u for u in run.approved_at if run.may_approve(u, pool, run.spec_pool) and run.cooled(u))
    run.record["approved_by"] = approved
    run.record["merge_approvals"] = [{"identity": u, "at": _stamp(run.approved_at.get(u)), "commit": head} for u in approved]
    for entry in run.owner_entries(run.paths):
        epool = run.make_pool(entry["approvers"])
        if not [u for u in run.approved_at if run.may_approve(u, epool) and run.cooled(u)]:
            add(
                "merge_approval",
                "pending",
                f"changes under {', '.join(entry['paths'])} need an approval from {', '.join(entry['approvers'])}",
                f"one of {', '.join(entry['approvers'])} approves head {head[:12]}",
                code="merge_approval.owner_area",
            )
    quorum = g["approvals"].get("standard", 0) if run.standard_ok else g["approvals"].get(run.route, 1)
    # Anyone whose approval the change could need can block it: Approvers, specialist reviewers, and path owners.
    blockers = [pool] + [run.make_pool(members) for members in cfg.reviewers.values()]
    blockers += [run.make_pool(e["approvers"]) for e in run.owner_entries(run.paths)]
    blocked_by = sorted(u for u, r in run.latest.items() if r["state"] == "changes_requested" and u not in run.authors and any(u in b for b in blockers))
    if blocked_by:
        add("merge_approval", "pending", f"changes requested by {', '.join(blocked_by)}", code="merge_approval.changes_requested")
    if len(approved) < quorum:
        cooloff = g["cooloff_minutes"].get(run.route, 0)
        notes = []
        if run.stale_reviews:
            notes.append(f"approvals on an older commit, or given before the base branch changed, do not count ({', '.join(sorted(run.stale_reviews))})")
        if not run.solo and any(u in (run.authors | run.bots) for u in run.approved_at):
            notes.append("an author or an agent cannot approve")
        if cooloff and not all(run.cooled(u) for u in run.approved_at):
            since = "the head commit" if run.ctx.get("platform") == "local" else "the last push"
            notes.append(f"approvals must come at least {cooloff} min after {since}")
        if pool.unresolved:
            notes.append(f"could not resolve {', '.join(pool.unresolved)}")
        if run.ctx.get("platform") == "local":
            hint = f"a person runs `aidd approve merge` at their own terminal on head {head[:12]}"
        else:
            hint = f"approve the PR/MR on head {head[:12]}" + (f", or comment /aidd approve {head}" if run.solo else "")
        add(
            "merge_approval",
            "pending",
            f"needs {quorum} approval(s) on head {head[:12]}, has {len(approved)}" + (f" ({'; '.join(notes)})" if notes else ""),
            hint,
            code="merge_approval.missing",
        )


def gate_specialist_review(run: Run) -> None:
    """Major, and an emergency repair that would be major: each required specialist pool approved the head.

    The emergency lane waives Specify, the budget, and red-then-green, never the specialist who
    would have reviewed the same change outside an emergency.
    """
    g, route = run.g, run.route
    major_repair = route == "emergency" and (run.protected_hit or run.record.get("required_route") == "major")
    if not (route == "major" or major_repair) or g["specialist_approvals"] <= 0:
        return
    approved: dict[str, list[str]] = {}
    for name in run.pools or ["security"]:
        spool, bound = run.reviewer_pool(name)
        if spool is None:
            run.add(
                "specialist_review",
                "fail",
                f"{route} needs owners.reviewers.{name} (or owners.reviewers.security) under profile {run.cfg.profile}",
                f'bind the pool in the config: [owners.reviewers] {name} = ["@org/{name}"]',
                code="specialist_review.unbound",
            )
            continue
        users = sorted(u for u in run.approved_at if run.may_approve(u, spool) and run.cooled(u))
        approved[name] = users
        if len(users) < g["specialist_approvals"]:
            stand_in = f" (owners.reviewers.{bound} stands in)" if bound != name else ""
            why = "" if route == "major" else "; an emergency repair that would be major keeps its specialist review"
            run.add(
                "specialist_review",
                "pending",
                f"needs {g['specialist_approvals']} approval(s) from the {name} pool{stand_in} on head, has {len(users)}{why}",
                code="specialist_review.missing",
            )
    run.record["specialist_approved_by"] = approved


def gate_policy(run: Run) -> None:
    """Policy and freeze. Unreachable is deny; org findings join as policy:<rule>."""
    ctx, cfg, add = run.ctx, run.cfg, run.add
    policy = (ctx.get("policy") or {}).get("result", "unbound")
    run.record["policy"] = policy
    if policy == "unbound":
        if run.route in run.g["policy_required_routes"]:
            add("policy", "fail", f"profile {cfg.profile} requires a bound Policy for {run.route}", "set policy.command in the config", code="policy.required")
    elif policy == "freeze":
        if run.route == "emergency":
            add("policy", "warn", "shipping under freeze through the emergency break-glass; the post-incident review must cover it", code="policy.break_glass")
        else:
            add(
                "policy",
                "fail",
                "a freeze is on; only the emergency route may ship",
                "wait for the freeze to end; if production is broken and this is the repair, use route emergency",
                code="policy.freeze",
            )
    elif policy == "deny":
        add("policy", "fail", "Policy returned deny" + (f": {ctx['policy'].get('detail')}" if ctx["policy"].get("detail") else ""), code="policy.deny")
    elif policy == "unreachable":
        add("policy", "fail", "the Policy command did not answer; unreachable is deny", "fix the Policy command or its runner", code="policy.unreachable")
    for f in (ctx.get("policy") or {}).get("findings", []):
        add(f"policy:{f['rule']}", f["level"], f["message"], f.get("fix", ""))


def gate_emergency(run: Run) -> None:
    """A complete emergency block, a real review date, and a human commander who approved and did not author."""
    if run.route != "emergency":
        return
    add = run.add
    em = run.declared.get("emergency")
    if not em:
        add("emergency", "fail", "route emergency needs an emergency block: severity, kind, commander, review_due", code="emergency.no_block")
        return
    # The window starts when the change opened or its head was last pushed, whichever is later: not at each
    # gate run, so a slow approval cannot expire it, and an old change turned into an emergency needs a fresh push.
    starts = [t for t in (parse_time((run.ctx["change"] or {}).get("created_at")), parse_time(run.ctx.get("head_pushed_at"))) if t]
    opened = max(starts) if starts else (parse_time(run.ctx.get("now")) or dt.datetime.now(dt.UTC))
    sla = run.cfg.get("emergency", "review_sla_days", default=2)
    try:
        due = dt.date.fromisoformat(str(em["review_due"]))
    except ValueError:
        due = None
        add("emergency", "fail", f"review_due {em['review_due']!r} is not a calendar date", code="emergency.review_due_invalid")
    if due is not None and due > opened.date() + dt.timedelta(days=sla):
        add(
            "emergency",
            "fail",
            f"review_due {due} is more than {sla} day(s) after the change opened",
            f"set review_due within {sla} day(s)",
            code="emergency.review_due_late",
        )
    if due is not None and due < opened.date():
        add(
            "emergency",
            "fail",
            f"review_due {due} is before the change opened",
            "set a review date from the day the change opened",
            code="emergency.review_due_early",
        )
    commander = norm(em["commander"])
    if is_agent(commander, run.bots):
        add(
            "emergency",
            "fail",
            f"the incident commander {commander} is an agent or bot account",
            "name the human who runs the incident",
            code="emergency.commander_is_agent",
        )
    elif commander in run.authors and not run.solo:
        add(
            "emergency",
            "fail",
            f"the incident commander {commander} is also an author of this change",
            "name a commander who did not write it",
            code="emergency.commander_is_author",
        )
    elif not run.solo and not run.may_approve(commander, run.pool):
        add(
            "emergency",
            "fail",
            f"the incident commander {commander} is not an eligible Approver",
            "name a commander listed in owners.approvers",
            code="emergency.commander_not_approver",
        )
    elif not run.solo and commander not in run.approved_at:
        add(
            "emergency",
            "pending",
            f"the incident commander {commander} has not approved head {run.head[:12]}",
            "the commander approves the change",
            code="emergency.commander_pending",
        )


def gate_observe(run: Run) -> None:
    if run.route in run.g["observe_required_routes"] and not run.declared.get("observe"):
        run.add(
            "observe",
            "fail",
            f"route {run.route} under profile {run.cfg.profile} needs an observe block",
            "add window, rollback_trigger, and a command or signals",
            code="observe.missing",
        )


def gate_provenance(run: Run) -> None:
    """Every commit an agent wrote is declared: an `Assisted-by:` trailer naming an agent, a `Co-authored-by:` agent,
    or a bot author. `Assisted-by: none` declares a commit no agent wrote."""
    commits, add = run.ctx["commits"], run.add
    assisted = run.declared["assisted_by"]
    trailers = {c["sha"]: [t.strip().lower() for t in extract_trailers(c["message"])] for c in commits}
    named: dict[str, list[str]] = {}  # sha -> what names an agent
    for c in commits:
        who = [f"Assisted-by {t}" for t in trailers[c["sha"]] if t != "none"]
        who += [f"Co-authored-by {x}" for x in agent_coauthors(c["message"], run.bots)]
        who += [f"author {k}" for k in (c.get("author"), c.get("committer")) if k and norm(k) in run.bots]
        if who:
            named[c["sha"]] = who
    unmarked = [c["sha"] for c in commits if not c.get("merge") and not trailers[c["sha"]]]
    assisted_norm = {norm(a) for a in assisted}
    missing_from_assisted = [(c["sha"], t) for c in commits for t in trailers[c["sha"]] if t != "none" and norm(t) not in assisted_norm]
    if not assisted and named:
        sample = "; ".join(f"{sha[:10]}: {', '.join(w[:2])}" for sha, w in list(named.items())[:3])
        add(
            "provenance",
            "fail",
            f"{len(named)} commit(s) name an agent, but assisted_by is empty ({sample})",
            "list each harness/model in assisted_by",
            code="provenance.undeclared_agent",
        )
    elif missing_from_assisted:
        sample = "; ".join(f"{sha[:10]}: {t}" for sha, t in missing_from_assisted[:3])
        add(
            "provenance",
            "fail",
            f"commit trailer value not declared in assisted_by: {sample}",
            "list each harness/model in assisted_by",
            code="provenance.undeclared_trailer",
        )
    if unmarked and run.g["provenance"] == "every_commit":
        add(
            "provenance",
            "fail",
            f"{len(unmarked)} commit(s) lack an Assisted-by trailer: {', '.join(s[:10] for s in unmarked[:5])}",
            "amend each commit with `Assisted-by: <harness>/<model>`, or `Assisted-by: none` when no agent wrote it",
            code="provenance.missing_trailer",
        )
    if assisted and commits and not named:
        add(
            "provenance",
            "warn",
            "assisted_by is set but no commit names an agent (no Assisted-by trailer, Co-authored-by agent, or bot author)",
            code="provenance.no_agent_commit",
        )


def gate_draft(run: Run) -> None:
    if run.ctx["change"].get("draft"):
        run.add("draft", "pending", "the change is a draft", code="draft.draft")


# Order matters only where a step derives facts later ones read: gate_config, gate_change_request, gate_facts,
# gate_standard_change and gate_route set up the declaration, the diff, and the route; derive_approvals builds
# the approval facts every approval gate reads. The remaining gates only read.
GATES: list[Callable[[Run], None]] = [
    gate_config,
    gate_change_request,
    gate_facts,
    gate_standard_change,
    gate_route,
    gate_scope,
    gate_budget,
    gate_merge_queue,
    gate_tests_declared,
    gate_status_checks,
    gate_evidence,
    gate_red_green,
    derive_approvals,
    gate_spec_approval,
    gate_merge_approval,
    gate_specialist_review,
    gate_policy,
    gate_emergency,
    gate_observe,
    gate_provenance,
    gate_draft,
]
