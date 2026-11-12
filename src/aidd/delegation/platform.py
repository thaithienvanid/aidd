"""The platform's facts a delegated merge or push needs, read only, through `gh api` reads of github.com: the default
branch and its tip, the branch rules, the pull request, the `tests` check run on the head, and the Pages source.
SECURITY.md lists them. The check stops before any of them under `AIDD_OFFLINE=1`, and never falls back to local
evidence."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
from typing import Protocol

from aidd.kernel import documents

# How long one read may take: the check's platform path is about seven reads, inside the hook's budget.
READ_TIMEOUT_SECONDS = 15
# The variables that would point `gh` at another host or repository than the one the check read.
_STEERING = ("GH_HOST", "GH_REPO", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
# The GitHub App whose check runs count: GitHub Actions. A commit status, or another app's check, never does.
ACTIONS_APP = "github-actions"


class PlatformError(RuntimeError):
    """A platform read that failed: the check defers."""


class Reader(Protocol):
    """What the check reads from the platform. Each read raises PlatformError when it cannot answer."""

    def default_branch(self) -> str: ...

    def branch_tip(self, branch: str) -> str: ...

    def rules(self, branch: str) -> dict: ...

    def pull(self, number: int) -> dict: ...

    def open_pull_for(self, branch: str) -> dict | None: ...

    def tests_run(self, head: str, workflow: str, number: int | None, default: str) -> dict | None: ...

    def pages_branch(self) -> str | None: ...


class NotFound(PlatformError):
    """The platform answered 404: the thing does not exist, or the token cannot see it."""


class GitHub:
    """`gh api` reads of one repository on github.com."""

    def __init__(self, slug: str, cwd: str, env: dict[str, str]):
        self.slug, self.cwd = slug, cwd
        self.env = {k: v for k, v in env.items() if k not in _STEERING}

    def get(self, path: str) -> object:
        """One read: `gh api <path>`, as JSON."""
        argv = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", path]
        try:
            done = subprocess.run(argv, cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=READ_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            raise PlatformError("the GitHub CLI, gh, is not installed") from None
        except subprocess.TimeoutExpired:
            raise PlatformError(f"gh api {path} took more than {READ_TIMEOUT_SECONDS} s") from None
        if done.returncode != 0:
            why = documents.one_line(done.stderr.strip() or done.stdout.strip(), 200)
            raise (NotFound if "HTTP 404" in why else PlatformError)(f"gh api {path}: {why}")
        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError:
            raise PlatformError(f"gh api {path} gave no JSON") from None

    def repo(self, rest: str = "") -> object:
        return self.get(f"repos/{self.slug}{rest}")

    def default_branch(self) -> str:
        data = self.repo()
        return str(data["default_branch"]) if isinstance(data, dict) and data.get("default_branch") else _bad("the repository has no default branch")

    def branch_tip(self, branch: str) -> str:
        data = self.repo(f"/branches/{urllib.parse.quote(branch, safe='')}")
        sha = (data.get("commit") or {}).get("sha") if isinstance(data, dict) else None
        return str(sha) if sha else _bad(f"{branch} has no tip")

    def rules(self, branch: str) -> dict:
        """What the default branch's rulesets and classic protection hold: the required checks, an up-to-date branch,
        and whether force pushes and deletion are blocked. `readable` is False when classic protection is hidden, and
        `bypass` is True when this session's token can pass them by: a ruleset's bypass, or an admin where classic
        protection does not bind admins."""
        quoted = urllib.parse.quote(branch, safe="")
        out: dict = {"required_checks": [], "strict": False, "blocks_force_push": False, "blocks_deletion": False, "readable": True, "bypass": False}
        found = _items(self.repo(f"/rules/branches/{quoted}"))
        for ruleset in sorted({str(r["ruleset_id"]) for r in found if r.get("ruleset_id")}):
            detail = self.repo(f"/rulesets/{int(ruleset)}")
            out["bypass"] = out["bypass"] or (isinstance(detail, dict) and detail.get("current_user_can_bypass", "never") != "never")
        for rule in found:
            kind, params = rule.get("type"), rule.get("parameters") or {}
            if kind == "required_status_checks":
                out["required_checks"] += [str(c.get("context")) for c in params.get("required_status_checks") or []]
                out["strict"] = out["strict"] or bool(params.get("strict_required_status_checks_policy"))
            out["blocks_force_push"] = out["blocks_force_push"] or kind == "non_fast_forward"
            out["blocks_deletion"] = out["blocks_deletion"] or kind == "deletion"
        try:
            classic = self.repo(f"/branches/{quoted}/protection")
        except NotFound:
            return out
        except PlatformError:
            return {**out, "readable": bool(out["required_checks"])}
        if isinstance(classic, dict):
            checks = classic.get("required_status_checks") or {}
            out["required_checks"] += list(checks.get("contexts") or []) + [str(c.get("context")) for c in checks.get("checks") or []]
            out["strict"] = out["strict"] or bool(checks.get("strict"))
            out["blocks_force_push"] = out["blocks_force_push"] or not (classic.get("allow_force_pushes") or {}).get("enabled", True)
            out["blocks_deletion"] = out["blocks_deletion"] or not (classic.get("allow_deletions") or {}).get("enabled", True)
            if not (classic.get("enforce_admins") or {}).get("enabled", False):
                me = self.repo()
                out["bypass"] = out["bypass"] or bool(isinstance(me, dict) and (me.get("permissions") or {}).get("admin"))
        return out

    def pull(self, number: int) -> dict:
        return _pull(self.repo(f"/pulls/{int(number)}"))

    def open_pull_for(self, branch: str) -> dict | None:
        """The open pull request whose head is `branch` in this repository, never a fork's."""
        owner = self.slug.split("/", 1)[0]
        found = _items(self.repo(f"/pulls?state=open&head={urllib.parse.quote(owner + ':' + branch, safe='')}&per_page=10"))
        same = [_pull(p) for p in found if ((p.get("head") or {}).get("repo") or {}).get("full_name") == self.slug]
        return same[0] if same else None

    def tests_run(self, head: str, workflow: str, number: int | None, default: str) -> dict | None:
        """The `tests` check run from GitHub Actions on `head`, from the latest run of `workflow` that belongs here: a
        pull request run of pull request `number` into `default`, or a push run on `default`. None when there is none,
        so an older pass, another pull request's run, or a run on another branch never counts."""
        flows = self.repo(f"/actions/runs?head_sha={head}&per_page=100")
        ours = [r for r in _items((flows or {}).get("workflow_runs") if isinstance(flows, dict) else []) if _belongs(r, workflow, number, default)]
        if not ours:
            return None
        latest = max(ours, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))
        runs = self.repo(f"/commits/{head}/check-runs?check_name=tests&per_page=100")
        checks = [
            c
            for c in _items((runs or {}).get("check_runs") if isinstance(runs, dict) else [])
            if (c.get("app") or {}).get("slug") == ACTIONS_APP
            and c.get("head_sha") == head
            and (c.get("check_suite") or {}).get("id") == latest.get("check_suite_id")
        ]
        if not checks:
            return None
        check = max(checks, key=lambda c: int(c.get("id") or 0))
        return {"id": check.get("id"), "workflow": workflow, "event": latest.get("event"), "conclusion": check.get("conclusion")}

    def pages_branch(self) -> str | None:
        try:
            data = self.repo("/pages")
        except NotFound:
            return None
        branch = ((data.get("source") or {}).get("branch")) if isinstance(data, dict) else None
        return str(branch) if branch else None


def _belongs(run: dict, workflow: str, number: int | None, default: str) -> bool:
    """Whether a workflow run is `workflow`'s for this change: on pull request `number` into `default`, or a push to `default`."""
    if str(run.get("path", "")).split("@")[0] != workflow:
        return False
    if run.get("event") == "push":
        return run.get("head_branch") == default
    prs = [p for p in run.get("pull_requests") or [] if isinstance(p, dict)]
    return run.get("event") == "pull_request" and any(p.get("number") == number and (p.get("base") or {}).get("ref") == default for p in prs)


def _bad(why: str) -> str:
    raise PlatformError(why)


def _items(data: object) -> list[dict]:
    """A list of objects from an answer, or [] for any other shape."""
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _pull(data: object) -> dict:
    """The facts of a pull request the check reads."""
    if not isinstance(data, dict):
        raise PlatformError("the pull request is no object")
    head, base = data.get("head") or {}, data.get("base") or {}
    return {
        "base": base.get("ref"),
        "head_ref": head.get("ref"),
        "head_sha": head.get("sha"),
        "state": data.get("state"),
        "title": str(data.get("title") or ""),
        "body": str(data.get("body") or ""),
    }


def connect(slug: str, cwd: str, env: dict[str, str]) -> Reader:
    """A reader of the repository `slug` on github.com, with the session's `gh` sign-in."""
    return GitHub(slug, cwd, env)
