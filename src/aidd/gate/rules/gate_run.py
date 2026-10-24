"""What the gate rules share: the run (the context, the record, and the facts earlier rules derived), the approver
pools, and the /aidd commands a comment carries.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NoReturn

from aidd import config as cfgmod
from aidd.gate import codeowners
from aidd.kernel import documents, globs

# A command starts at column 0 of its own line. A Spec approval names the Spec and the commit the person read it at
# (`/aidd approve-spec SPEC-1 <sha>`): git holds what they approved, and the gate compares it with the head. A Merge
# approval is `/aidd approve-merge <sha>`.
APPROVE_SPEC: re.Pattern[str] = re.compile(r"^/aidd[ \t]+approve-spec[ \t]+(\S+)[ \t]+([0-9a-f]{40}|[0-9a-f]{64})[ \t]*$", re.M)
APPROVE = re.compile(r"^/aidd[ \t]+approve-merge[ \t]+([0-9a-f]{40}|[0-9a-f]{64})[ \t]*$", re.M)
_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")

DEFAULT_SYSTEM_ACCOUNTS = ("web-flow",)


def comment_commands(body: str) -> str:
    """Comment lines that can carry /aidd commands: not in fenced code (an unclosed fence runs to
    the end), not in an indented code block, not quoted, not inside an HTML comment."""
    out: list[str] = []
    fence: str | None = None
    prev_blank = True
    indented = False
    for line in documents._HTML_COMMENT.sub("", body or "").splitlines():
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


class ApproverPool:
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
            owner, _ = cfgmod.split_tenant(entry) if tenant else (None, "")
            if owner is not None and owner != tenant:
                continue  # another tenant's person or team never approves here
            if owner is not None:
                e = entry.strip().lstrip("@").split(":", 1)[1]
            n = cfgmod.normalize_identity(e)
            if "/" in n and not n.startswith("email:"):
                members = next((team_members[k] for k in (entry, e, "@" + n, n) if k in team_members), None)
                if members is None:
                    self.unresolved.append(e)
                else:
                    self.users.update(cfgmod.normalize_identity(m) for m in members)
            else:
                self.named.add(n)
                self.users.add(n)

    def __contains__(self, user: str) -> bool:
        # Bots approve only when named one by one, never through a team.
        return user in self.users and (not user.endswith("[bot]") or user in self.named)


class Stop(Exception):
    """Raised by a gate when the remaining gates cannot say anything useful."""


@dataclass
class GateRun:
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
    # The components' living threat models the Spec links (workitems.threat_models): documentation, never frozen.
    threat_models: list[str] = field(default_factory=list)
    scope_declared: bool = True
    # No Change Request block and no Spec: the gate derived the declaration, and gate_route sets the computed route.
    derived: bool = False
    paths: list[str] = field(default_factory=list)
    changed_lines: int = 0
    binary_files: int = 0
    authors: set[str] = field(default_factory=set)
    bots: set[str] = field(default_factory=set)
    standard_ok: bool = False
    protected_hit: bool = False
    # The matched risk rules, other than a protected path, that ask for major themselves (gate_route).
    major_rules: list[str] = field(default_factory=list)
    pools: list[str] = field(default_factory=list)
    # The pools a matched risk rule names in `specialists`: asked on every route (routing.Assessment.asked).
    asked_pools: list[str] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)
    latest: dict[str, dict] = field(default_factory=dict)
    approved_at: dict[str, dt.datetime | None] = field(default_factory=dict)
    stale_reviews: list[str] = field(default_factory=list)
    # user -> (the earlier head they approved, why it carried / why not) for approvals a trivial rebase carried, or did not.
    carried: dict[str, tuple[str, str]] = field(default_factory=dict)
    not_carried: dict[str, tuple[str, str]] = field(default_factory=dict)
    required: list[tuple[dict, str]] = field(default_factory=list)
    green: dict[str, dict] = field(default_factory=dict)
    red: dict[str, dict] = field(default_factory=dict)
    evidence_ok: bool = False
    # Every changed path is the Spec or a file it freezes, and a Task has yet to change anything (rules.spec_phase).
    spec_phase: bool = False
    spec_failures: list[str] = field(default_factory=list)
    # An emergency whose whole diff reverts a commit merged on the base, exactly (the context's revert_of).
    exact_revert: bool = False
    # An eligible Approver recorded a Spec approval on a route where the profile makes it optional: it binds the hash,
    # and red-then-green is required for that Spec (gate_spec_approval, gate_red_green).
    spec_bound: bool = False
    # Spec approval holds for this change: counted on a route that needs it, or recorded where it is optional.
    spec_approved: bool = False
    # A goal's change (`specs`): the Spec this run judges, and every Spec the goal lands (engine._decide_goal).
    member: str | None = None
    members: list[str] = field(default_factory=list)
    # The paths that are the goal's other work, never this Spec's implementation: the other Specs, their Task scopes,
    # tests, and design files, and the goal's plan items (gate_change_request fills it).
    goal_paths: list[str] = field(default_factory=list)
    # The risk dimensions the changed paths imply, whatever the declaration says (gate_route).
    implied_dimensions: set[str] = field(default_factory=set)

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

    def make_pool(self, entries: list[str]) -> ApproverPool:
        return ApproverPool(entries, self.ctx.get("team_members") or {}, self.tenant)

    def local(self, identity: str) -> str:
        """An identity as this repository's config names it: its own tenant's prefix dropped, another tenant's kept."""
        return cfgmod.scoped(identity, self.tenant) or cfgmod.normalize_identity(identity)

    @property
    def pool(self) -> ApproverPool:
        return self.make_pool(self.cfg.approvers)

    @property
    def spec_pool(self) -> ApproverPool | None:
        return self.make_pool(self.spec.get("approvers") or []) if self.spec and "approvers" in self.spec else None

    def specialist_pool(self, name: str) -> tuple[ApproverPool | None, str]:
        """The members of a specialist pool and the pool's name; an unbound pool falls back to security."""
        pools = self.cfg.specialists
        for candidate in (name, "security"):
            if pools.get(candidate):
                return self.make_pool(pools[candidate]), candidate
        return None, name

    def may_approve(self, user: str, pool: ApproverPool, narrow: ApproverPool | None = None) -> bool:
        """Only members of the pool approve; a bot only when the pool names it. Authors approve only under solo.

        Solo waives one rule, that an author cannot approve their own change. It never
        widens the pool: an outsider's pull request on a solo repository still needs an
        approval from someone in owners.approvers.
        """
        if user in self.bots or cfgmod.agent_account(user, self.bots) or (narrow is not None and user not in narrow) or user not in pool:
            return False
        return self.solo or user not in self.authors

    def owner_entries(self, candidates: list[str]) -> list[dict]:
        """Per-path owners the given paths touch: config owners.paths, plus CODEOWNERS when enabled."""
        found = [e for e in self.cfg.get("owners", "paths", default=[]) if any(globs.match_any(e["paths"], x, fold_case=True) for x in candidates)]
        if self.cfg.get("owners", "codeowners"):
            found += codeowners.entries(self.ctx.get("codeowners"), candidates)
        return found


def _stamp(t: dt.datetime | None) -> str | None:
    """A time as RFC 3339 UTC to the second, or None."""
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None
