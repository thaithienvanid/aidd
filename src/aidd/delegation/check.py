"""`aidd delegate check`: whether a delegated ask may go to the delegate. Every run recomputes every gate from git, the
default branch's config, and, where a remote exists, the platform. It reads no record's claims, except a delegate's
defer, which only narrows. One failed gate defers.

The rule that shapes it: whatever widens what an agent may do comes from the default branch's tip, and whatever only
narrows it may come from anywhere.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config, records, risk
from aidd.delegation import commands, platform, policy
from aidd.kernel import documents, git

SHA = re.compile(r"^[0-9a-f]{40}$")


class UsageError(ValueError):
    """A check that cannot start: no repository, or a head that is no full commit id here. It exits 2."""


@dataclass
class Request:
    """What the asker passes, and nothing else: no prose, and no summary. `env` is the session's environment, read for
    the harness and `AIDD_OFFLINE`; `github` stands in for the platform's reads in a test."""

    action: str
    command: str = ""
    head: str = ""
    spec: str | None = None
    cwd: str = "."
    env: dict[str, str] = field(default_factory=dict)
    github: platform.Reader | None = None
    today: dt.date | None = None
    # False when a merge's check runs a Spec approval's gates again on an older head, which no checkout holds.
    checkout: bool = True


def _default_said(text: str | None) -> str:
    """The `delegation.default_branch` a config's text sets, or "" when it sets none or does not parse."""
    try:
        data = documents.parse_yaml(text, config.CONFIG_PATH) if text else {}
    except documents.DocumentError:
        return ""
    block = data.get("delegation") if isinstance(data, dict) else None
    return str(block.get("default_branch") or "") if isinstance(block, dict) else ""


def github_slug(url: str) -> str | None:
    """`owner/name` of a GitHub remote's URL, or None for any other host."""
    found = re.match(
        r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$", url.strip()
    )
    return found.group(1) if found else None


class Check:
    """One run of the check: the facts it read, and the reasons it defers."""

    def __init__(self, request: Request):
        self.req = request
        self.reasons: list[dict] = []
        self.inputs: dict = {}
        self.warnings: list[str] = []
        self.covers: dict = {"head": request.head}
        self.values: dict[str, str] = {}
        self.top = ""
        self.tree = ""
        self.default = ""
        self.tip = ""
        self.slug: str | None = None
        self.remotes: list[str] = []
        self.cfg: config.Config | None = None
        self.rs: risk.RuleSet | None = None
        self.delegation: dict = {}
        self.gh: platform.Reader | None = None

    def defer(self, code: str, detail: str) -> None:
        self.reasons.append(policy.reason(code, documents.one_line(detail, 400)))

    @property
    def offline(self) -> bool:
        return self.req.env.get("AIDD_OFFLINE") == "1"

    def open_repository(self) -> None:
        """The repository and the head, or UsageError: the head must be a full commit id this clone holds."""
        top = git.repository_top(self.req.cwd)
        if top is None:
            raise UsageError(git.no_repository_problem("delegate check"))
        if not SHA.match(self.req.head or ""):
            raise UsageError("--head takes the full 40-character commit id of the head, such as the one `git rev-parse HEAD` prints")
        if not git.ok(["cat-file", "-e", f"{self.req.head}^{{commit}}"], top):
            raise UsageError(f"this clone holds no commit {self.req.head}: fetch it, then run the check again")
        self.top = top
        self.tree = git.run(["rev-parse", f"{self.req.head}^{{tree}}"], top).strip()
        self.covers["tree"] = self.tree
        self.remotes = git.run(["remote"], top, check=False).split()

    def read_tip(self) -> bool:
        """The default branch and its tip: from the platform where a remote exists, else this clone. False on a defer."""
        if not self.remotes:
            name = self.local_default()
            if not name:
                return False
            self.default, self.tip = name, git.rev_parse(f"refs/heads/{name}", self.top)
            self.inputs["config_source"] = "local"
            return True
        url = git.run(["remote", "get-url", "origin" if "origin" in self.remotes else self.remotes[0]], self.top, check=False).strip()
        self.slug = github_slug(url)
        if self.slug is None:
            self.defer("platform-not-supported", "the remote is not on GitHub")
            return False
        if self.offline:
            self.defer("offline", "AIDD_OFFLINE=1 is set, and a repository with a remote reads its default branch from GitHub")
            return False
        return self.read_platform_tip()

    def local_default(self) -> str:
        """The default branch with no remote, from what a person set and never from a ref name alone. The candidates
        are `main`, `master`, and the branch the person's global `init.defaultBranch` names. Exactly one must name itself
        in its own tip's `delegation.default_branch`, and every other candidate must name that same one. "" after a
        defer, as when a remote's refs stand with no remote, since an agent can make a ref."""
        strays = git.run(["for-each-ref", "--format=%(refname)", "refs/remotes/", "refs/heads/origin/"], self.top, check=False).split()
        if strays:
            self.defer("default-branch-unknown", f"{strays[0]} stands with no remote configured")
            return ""
        named = git.run(["config", "--global", "--get", "init.defaultBranch"], self.top, check=False).strip()
        said = {
            name: _default_said(git.show(f"refs/heads/{name}", config.CONFIG_PATH, self.top))
            for name in dict.fromkeys(n for n in (named, "main", "master") if n)
            if git.ok(["rev-parse", "-q", "--verify", f"refs/heads/{name}^{{commit}}"], self.top)
        }
        selves = [n for n, s in said.items() if s == n]
        if len(selves) == 1 and all(s == selves[0] for s in said.values()):
            return selves[0]
        why = f"{', '.join(selves)} each name themselves" if len(selves) > 1 else "the candidates do not all name one branch in delegation.default_branch"
        each = ", ".join(f"{n}: {s or 'unset'}" for n, s in said.items()) or "no main or master"
        self.defer("default-branch-unknown", f"{why} ({each})")
        return ""

    def read_platform_tip(self) -> bool:
        """The default branch and its tip from GitHub. Its tip must be in this clone, so its files read from git objects."""
        self.gh = self.req.github or platform.connect(self.slug or "", self.top, self.req.env)
        try:
            self.default = self.gh.default_branch()
            self.tip = self.gh.branch_tip(self.default)
        except platform.PlatformError as exc:
            self.defer("platform-unreadable", str(exc))
            return False
        if not git.ok(["cat-file", "-e", f"{self.tip}^{{commit}}"], self.top):
            self.defer("tip-not-fetched", f"the tip of {self.default}, {self.tip[:12]}, is not in this clone")
            return False
        self.inputs["config_source"] = "platform"
        return True

    def read_delegation(self) -> bool:
        """The config at the tip, and its delegation. False on a defer."""
        tip, top = self.tip, self.top
        text = git.show(tip, config.CONFIG_PATH, top)
        if text is None:
            self.defer("not-delegated", f"the tip of {self.default} holds no {config.CONFIG_PATH}")
            return False
        try:
            self.cfg = config.load_text(text, read=lambda p: git.show(tip, p, top), root_preset=config.org_preset_text())
        except (config.ConfigError, documents.DocumentError, OSError, ValueError) as exc:
            self.defer("config-unreadable", str(exc))
            return False
        self.delegation = dict(self.cfg.get("delegation") or {})
        self.inputs["delegation"] = tip
        if not self.delegation:
            self.defer("not-delegated", f"the config at the tip of {self.default} sets no delegation")
            return False
        self.rs = risk.rule_set(self.cfg)
        self.covers["base"] = tip
        return True

    def covered(self) -> bool:
        """The tip's delegation covers the action, the delegation is on, and its review is not due."""
        action = self.req.action
        if action not in policy.delegable() or action in (self.delegation.get("reserved") or []):
            self.defer("reserved-action", f"{action} is reserved: it is always the person's")
            return False
        if action not in policy.covered(self.delegation, str(self.cfg.get("aidd_version") if self.cfg else "")):
            self.defer("not-delegated", f"the delegation at {self.tip[:12]} does not decide {action}")
        if Path(git.common_dir(self.top), *policy.STOP_FILE).exists():
            self.defer("delegation-stopped", "aidd delegate stop turned the delegation off in this clone")
        today = self.req.today or dt.datetime.now(dt.UTC).date()
        if str(self.delegation.get("review_by", "0000-00-00")) < today.isoformat():
            self.defer("delegation-review-due", f"review_by {self.delegation.get('review_by')} has passed")
        return not self.reasons

    def fits(self) -> bool:
        """The command fits the action's exact template, or the action runs none."""
        shape = policy.template(self.req.action)
        if shape is None:
            if self.req.command.strip():
                self.defer("command-not-canonical", f"{self.req.action} runs no command, so name none")
            return not self.reasons
        found, _ = commands.words(self.req.command)
        wide = commands.widening(found)
        values, why = commands.fit(shape, self.req.command)
        if wide:
            self.defer("admin-or-repo-flag", wide)
        elif values is None:
            self.defer("command-not-canonical", why)
        else:
            self.values = values
        return not self.reasons

    def deferred_before(self) -> None:
        """No delegate's defer covers this action on this tree, so an amend that keeps the tree never clears one."""
        found, _ = records.read_records(self.top, record_type="delegate_answer")
        for rec in found:
            data = rec.get("data") or {}
            if data.get("outcome") == "defer" and data.get("action") == self.req.action and (data.get("covers") or {}).get("tree") == self.tree:
                self.defer("deferred-before", f"the delegate deferred {self.req.action} on this tree in record {rec.get('id')}")
                return

    def message_matches(self) -> None:
        """A command that names its message names the check's own: the subject and the three trailers, exactly."""
        given = self.values.get("message")
        if given is not None and given != message_for(self, self.trailers()):
            self.defer("command-not-canonical", "its message is not the one the check gives: run the check without it, and run the command it gives")

    def passes_common(self) -> bool:
        """Every gate each action passes, in order: the harness, the tip and its delegation, the action, the command,
        its message, and the delegate's earlier defer. The repository must be open."""
        if config.session_harness(self.req.env) != policy.DELEGATING_HARNESS:
            self.defer("harness-not-delegated", "this session is not Claude Code, so its ask rules decide, with the person")
        elif self.read_tip() and self.read_delegation() and self.covered() and self.fits():
            self.message_matches()
            self.deferred_before()
        return not self.reasons

    def trailers(self) -> list[str]:
        """The three trailers a delegated yes writes, in place of `Approved-by`."""
        return [f"Decided-by: {policy.DECIDED_BY}", f"On-behalf-of: {self.delegation.get('set_by', '')}", f"Delegation: {self.tip}"]


def message_for(check: Check, trailers: list[str]) -> str:
    """The merge's message: the trailers alone for a pull request's body, after a subject for a local merge."""
    if check.req.action == "git.merge":
        return f"Merge {check.req.head[:12]} into {check.default}\n\n" + "\n".join(trailers)
    return "\n".join(trailers)
