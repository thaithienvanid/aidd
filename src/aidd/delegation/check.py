"""`aidd delegate check`: whether a delegated ask may go to the delegate. Every run recomputes every check from git, the
default branch's config, and, where a remote exists, the platform. It reads no record's claims, except a delegate's
defer, which only narrows. One failed check defers.

The rule that shapes it: whatever widens what an agent may do comes from the default branch's tip, and whatever only
narrows it may come from anywhere.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config, records, risk
from aidd.delegation import commands, platform, policy
from aidd.kernel import documents, git, remote_urls, retired_names

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
    # False when a merge's check runs a Spec approval's checks again on an older head, which no checkout holds.
    checkout: bool = True


def _default_said(text: str | None) -> str | None:
    """The `delegation.default_branch` a config's text sets, or "" when there is no text or it sets none. None when it does not
    parse, or holds a name the upgrade leaves for a person (`retired_names.Refused`), which no check reads either."""
    try:
        data = config.todays_shape(documents.parse_yaml(text, config.CONFIG_PATH)) if text else {}
    except (documents.DocumentError, retired_names.Refused):
        return None
    block = data.get("delegation") if isinstance(data, dict) else None
    return str(block.get("default_branch") or "") if isinstance(block, dict) else ""


def tip_text(tip: str, path: str, top: str) -> str | None:
    """A config file at the tip, in today's shape; None when the tip holds none."""
    text = git.show(tip, path, top)
    return None if text is None else config.in_todays_shape(text)


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
        self.reads_old_shape = False  # the commit named as the head is one the change does not control, so it reads in today's shape
        self.head_branch = ""  # the change's branch, when the platform names it: a pull request's head
        self.slug: str | None = None
        self.remotes: list[str] = []
        self.cfg: config.Config | None = None
        self.rs: risk.RuleSet | None = None
        self.delegation: dict = {}
        self.gh: platform.Reader | None = None
        # The Spec the change answers to, once a check found it: the one file the delegate reads (parts.py), by its path.
        self.spec_path: str | None = None
        self.spec_data: dict = {}
        self.spec_view: dict = {}  # the Spec as the run decides by it (`base_view`); spec_data is the head's own text
        self.reached: list[str] = []  # the open Specs whose Task scope the change touches without holding them
        self.scanned: set[str] = set()  # the labels of the texts the tripwire already read, so no text is read twice

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
        self.slug = remote_urls.github_slug(url)
        if self.slug is None:
            self.defer("platform_not_supported", "the remote is not on GitHub")
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
            self.defer("default_branch_unknown", f"{strays[0]} stands with no remote configured")
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
        if broken := [n for n, s in said.items() if s is None]:  # the cause a person fixes, where the branch question would mislead
            self.defer("config_unreadable", f"the {config.CONFIG_PATH} on {broken[0]} does not load, so the check cannot tell which branch is the default")
            return ""
        why = f"{', '.join(selves)} each name themselves" if len(selves) > 1 else "the candidates do not all name one branch in delegation.default_branch"
        each = ", ".join(f"{n}: {s or 'unset'}" for n, s in said.items()) or "no main or master"
        self.defer("default_branch_unknown", f"{why} ({each})")
        return ""

    def read_platform_tip(self) -> bool:
        """The default branch and its tip from GitHub. Its tip must be in this clone, so its files read from git objects."""
        self.gh = self.req.github or platform.connect(self.slug or "", self.top, self.req.env)
        try:
            self.default = self.gh.default_branch()
            self.tip = self.gh.branch_tip(self.default)
        except platform.PlatformError as exc:
            self.defer("platform_unreadable", str(exc))
            return False
        if not git.ok(["cat-file", "-e", f"{self.tip}^{{commit}}"], self.top):
            self.defer("tip_not_fetched", f"the tip of {self.default}, {self.tip[:12]}, is not in this clone")
            return False
        self.inputs["config_source"] = "platform"
        return True

    def read_delegation(self) -> bool:
        """The config at the tip, and its delegation. False on a defer."""
        tip, top = self.tip, self.top
        text = git.show(tip, config.CONFIG_PATH, top)
        if text is None:
            self.defer("not_delegated", f"the tip of {self.default} holds no {config.CONFIG_PATH}")
            return False
        try:
            # the tip is not the head: a config from before an upgrade reads as today's, so the upgrade alone changes no answer
            self.cfg = config.load_text(config.in_todays_shape(text), read=lambda p: tip_text(tip, p, top), root_preset=config.org_preset_text())
        except (config.ConfigError, documents.DocumentError, OSError, ValueError) as exc:
            self.defer("config_unreadable", str(exc))
            return False
        self.delegation = dict(self.cfg.get("delegation") or {})
        self.inputs["delegation_commit"] = tip
        if not self.delegation:
            self.defer("not_delegated", f"the config at the tip of {self.default} sets no delegation")
            return False
        said = self.delegation.get("default_branch")
        if self.inputs.get("config_source") == "platform" and said and said != self.default:
            self.defer("default_branch_unknown", f"delegation.default_branch is {said}, and the platform's default branch is {self.default}")
            return False
        self.rs = risk.rule_set(self.cfg)
        self.covers["base"] = tip
        return True

    def delegation_holds(self) -> bool:
        """The tip's delegation decides the action, the stop file is absent, and its review is not due."""
        action = self.req.action
        if action not in policy.delegable() or action in (self.delegation.get("reserved") or []):
            self.defer("reserved_action", f"{action} is reserved: it is always the person's")
            return False
        if action not in policy.covered(self.delegation):
            self.defer("not_delegated", f"the delegation at {self.tip[:12]} does not decide {action}")
        if os.path.lexists(Path(git.common_dir(self.top), *policy.STOP_FILE)):  # any entry there narrows, a link or a pipe too
            self.defer("delegation_stopped", "aidd delegate stop turned the delegation off in this clone")
        today = self.req.today or dt.datetime.now(dt.UTC).date()
        if str(self.delegation.get("review_due", "0000-00-00")) < today.isoformat():
            self.defer("delegation_review_due", f"review_due {self.delegation.get('review_due')} has passed")
        elif far := config.delegation_review_warning(self.delegation, today):
            self.warnings.append(far)
        return not self.reasons

    def fits(self) -> bool:
        """The command fits the action's exact template, or the action runs none."""
        shape = policy.template(self.req.action)
        if shape is None:
            if self.req.command.strip():
                self.defer("command_not_canonical", f"{self.req.action} runs no command, so name none")
            return not self.reasons
        found, _ = commands.words(self.req.command)
        wide = commands.widening(found)
        values, why = commands.fit(shape, self.req.command)
        if wide:
            self.defer("bypass_flag", wide)
        elif values is None:
            self.defer("command_not_canonical", why)
        else:
            self.values = values
        return not self.reasons

    def deferred_before(self) -> None:
        """No delegate's defer covers this action on this tree, so an amend that keeps the tree never clears one. A record
        file that does not read could be one, and a defer only narrows, so it defers too, until the file reads."""
        # Every defer counts, a pulled or another writer's too: a defer only narrows, so a forged one can only stop a merge.
        found, unreadable = records.read_records(self.top, record_type="delegate_answer")
        for rec in found:
            data = rec.get("data") or {}
            if data.get("outcome") == "defer" and data.get("action") == self.req.action and (data.get("covers") or {}).get("tree") == self.tree:
                self.defer("deferred_before", f"the delegate deferred {self.req.action} on this tree in record {rec.get('id')}")
                return
        if unreadable:
            more = f" and {len(unreadable) - 1} more" if len(unreadable) > 1 else ""
            first = unreadable[0].split("/aidd/records/", 1)[-1]  # the file from the records folder, so a long path never hides its name
            self.defer("records_unreadable", f"{documents.one_line(first, 160)}{more} does not read as a record")

    def message_matches(self) -> None:
        """A command that names its message names the check's own: the subject and the three trailers, exactly."""
        given = self.values.get("message")
        if given is not None and given != message_for(self, self.trailers()):
            self.defer("command_not_canonical", "its message is not the one the check gives: run the check without it, and run the command it gives")

    def passes_common(self) -> bool:
        """Every check each action passes, in order: the harness, the tip and its delegation, the action, the command,
        its message, and the delegate's earlier defer. The repository must be open."""
        if config.session_harness(self.req.env) != config.DELEGATING_HARNESS:
            self.defer("harness_not_supported", "this session is not Claude Code, so its ask rules decide, with the person")
        elif self.read_tip() and self.read_delegation() and self.delegation_holds() and self.fits():
            self.message_matches()
            self.deferred_before()
        return not self.reasons

    def trailers(self) -> list[str]:
        """The three trailers a delegated yes writes, in place of `Approved-by`."""
        return [f"Decided-by: {config.DECIDED_BY}", f"On-behalf-of: {self.delegation.get('set_by', '')}", f"Delegation: {self.tip}"]


def message_for(check: Check, trailers: list[str]) -> str:
    """The merge's message: the trailers alone for a pull request's body, after a subject for a local merge."""
    if check.req.action == "git.merge":
        return f"Merge {check.req.head[:12]} into {check.default}\n\n" + "\n".join(trailers)
    return "\n".join(trailers)
