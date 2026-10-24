"""GitHub from the person's side, at their own terminal or through their agent: their sign-in (`gh`, or GH_TOKEN), the
pull request a decision is posted on, their Spec approval line and their review, auto-merge, the branch protection
`aidd doctor` checks, and whether Spec approval holds there for autopilot. The gate's side is github.py."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass

from aidd import config
from aidd import gate as aidd_gate
from aidd.kernel import git, http
from aidd.platforms import github

_REMOTE = re.compile(r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
BOT_NOTE = (
    "aidd never counts an approval from an account in identities.bots, and counts any other bot only when owners.approvers names it. "
    "GitHub's own review count takes an approval from any account with write access, a GitHub App or an agent's token included. "
    "Copilot code review only comments, so it never approves"
)


def _person_token(login: str | None = None) -> str | None:
    """The person's token: GH_TOKEN or GITHUB_TOKEN when set, else `gh`'s, for `login` when named (one of its
    accounts), else for its active account."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    out = _gh(["auth", "token", "--user", login]) if login else None
    if out is None:  # no account named, or a gh too old for `--user`: its active account
        out = _gh(["auth", "token"])
    return (out.strip() or None) if out is not None else None


def _gh(argv: list[str]) -> str | None:
    """What `gh <argv>` prints, or None when gh is missing or fails."""
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        p = subprocess.run([gh, *argv], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def approver_login(pool: list[str]) -> str | None:
    """The first Approver login in `pool` that `gh` holds a token for (`gh auth token --user`, read from this machine
    only), or None: aidd acts as that account whichever is active, so a second account signed in on the same machine
    never stands in the way. None too when GH_TOKEN or GITHUB_TOKEN decides, or for a team entry (`@org/team`)."""
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return None
    logins = [n for a in pool if (n := config.normalize_identity(str(a))) and "/" not in n and ":" not in n]
    return next((login for login in logins if (_gh(["auth", "token", "--user", login]) or "").strip()), None)


def not_an_approver_problem(login: str, pool: list[str]) -> str:
    """Why @`login`, the account aidd signed in as, cannot approve here, and the one step that fixes it."""
    return (
        f"GitHub knows you as @{login}, who is not an Approver here ({', '.join(map(str, pool)) or 'nobody'}), and gh holds no "
        "token for one. Sign in as an Approver with `gh auth login` (gh keeps each account, and aidd uses the Approver "
        "whichever is active), then run this again"
    )


@dataclass(frozen=True)
class PullRequest:
    """Where a person's approval goes on GitHub: the branch's open pull request, its head, and who the token signs in as."""

    repo: str
    number: int
    url: str
    head_sha: str
    login: str


def _person_client(login: str | None = None) -> github.Client | str:
    """A client with the person's own token (GH_TOKEN, GITHUB_TOKEN, or `gh auth token`, for `login` when named), or
    why there is none."""
    if os.environ.get("AIDD_OFFLINE") == "1":
        return "offline (AIDD_OFFLINE=1): aidd cannot reach GitHub to post your approval"
    token = _person_token(login)
    if not token:
        return "no GitHub token: run `gh auth login` (or set GH_TOKEN), then approve again"
    return github.Client(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))


def approval_target(root: str, branch: str, pool: list[str], *, client: github.Client | None = None) -> tuple[PullRequest | None, str | None]:
    """The pull request a person's approval of `branch` goes on, or None and why it cannot. The gate on GitHub counts
    an Approver's comment or review there, never this machine's decision records; so the token's login must be in the pool (a
    team entry is left to the gate, which resolves it)."""
    repo = origin_repo(root)
    if not repo:
        return None, "`origin` is not a github.com repository, so aidd cannot post the approval: post the line on the PR/MR yourself"
    made = client or _person_client(approver_login(pool))
    if isinstance(made, str):
        return None, made
    try:
        login = str((made.get("/user") or {}).get("login") or "")
        pulls = made.get(f"/repos/{repo}/pulls", {"head": f"{repo.split('/')[0]}:{branch}", "state": "open"}) or []
    except http.HttpError as exc:
        return None, f"GitHub answered: {exc}"
    if not pulls:
        return None, (
            f"{branch} has no open pull request on {repo}. Publishing is the person's: they type `publish` (or run `aidd "
            "publish --pr`), which pushes the branch, opens it, and carries their recorded approvals there"
        )
    names = {config.normalize_identity(str(a)) for a in pool}
    if config.normalize_identity(login) not in names and not any("/" in n for n in names):
        return None, not_an_approver_problem(login, pool)
    pr = pulls[0]
    return PullRequest(repo, int(pr["number"]), str(pr.get("html_url") or ""), str((pr.get("head") or {}).get("sha") or ""), login), None


def open_pull_request(root: str, branch: str, base: str, pool: list[str], *, client: github.Client | None = None) -> tuple[str | None, str | None]:
    """Open the pull request of `branch` into `base` as the person (their own token), titled by the branch's newest
    commit, or name the one already open: (its URL, None), or (None, why not). `aidd publish` calls it once it has
    pushed the branch."""
    repo = origin_repo(root)
    if not repo:
        return None, "`origin` is not a github.com repository: open the pull or merge request on your platform"
    made = client or _person_client(approver_login(pool))
    if isinstance(made, str):
        return None, made
    try:
        open_now = made.get(f"/repos/{repo}/pulls", {"head": f"{repo.split('/')[0]}:{branch}", "state": "open"}) or []
        if open_now:
            return str(open_now[0].get("html_url") or ""), None
        title = git.run(["log", "-1", "--format=%s", f"refs/heads/{branch}"], root, check=False).strip() or branch
        made_pr = made.post(f"/repos/{repo}/pulls", {"title": title, "head": branch, "base": base, "body": "Published with `aidd publish`."})
    except http.HttpError as exc:
        return None, f"GitHub answered: {exc}"
    return str((made_pr or {}).get("html_url") or ""), None


def person_login(pool: list[str] | None = None, *, client: github.Client | None = None) -> tuple[str | None, str | None]:
    """The GitHub login of the person whose token this machine holds (`gh`): the account `pool` lists when gh holds
    one (approver_login), else the active one; or None and why it cannot be read."""
    made = client or _person_client(approver_login(pool or []))
    if isinstance(made, str):
        return None, made
    try:
        login = str((made.get("/user") or {}).get("login") or "")
    except http.HttpError as exc:
        return None, f"GitHub answered: {exc}"
    return (login, None) if login else (None, "GitHub did not say who you are")


def post_spec_approval(pr: PullRequest, line: str, *, client: github.Client | None = None) -> str:
    """Post the Spec approval line on the pull request as the person approval_target named; the comment's URL."""
    made = client or _person_client(pr.login)
    if isinstance(made, str):
        raise RuntimeError(made)
    return str((made.post(f"/repos/{pr.repo}/issues/{pr.number}/comments", {"body": line}) or {}).get("html_url") or pr.url)


def approve_pull_request(pr: PullRequest, head: str, body: str, *, client: github.Client | None = None) -> str:
    """Approve the pull request's `head` as the person approval_target named (a review that names the commit); the
    review's URL."""
    made = client or _person_client(pr.login)
    if isinstance(made, str):
        raise RuntimeError(made)
    review = made.post(f"/repos/{pr.repo}/pulls/{pr.number}/reviews", {"event": "APPROVE", "commit_id": head, "body": body})
    return str((review or {}).get("html_url") or pr.url)


AUTO_MERGE = "mutation($id: ID!) { enablePullRequestAutoMerge(input: {pullRequestId: $id}) { clientMutationId } }"


def enable_auto_merge(pr: PullRequest, *, client: github.Client | None = None) -> str | None:
    """Turn on the pull request's auto-merge as the person approval_target named, so GitHub merges it once every
    required check passes: None when it is on, else why not (`aidd/gate` is not required on the base branch, the
    repository allows no auto-merge, or GitHub said no). Only where the base branch requires `aidd/gate`: elsewhere
    auto-merge could merge a head the gate fails."""
    made = client or _person_client(pr.login)
    if isinstance(made, str):
        return made
    try:
        found = made.get(f"/repos/{pr.repo}/pulls/{pr.number}")
        found = found if isinstance(found, dict) else {}
        base = str((found.get("base") or {}).get("ref") or "")
        if not base or not _gate_required(made, pr.repo, base):
            return f"`{github.STATUS_CONTEXT}` is not a required check on {base or 'the base branch'}, so GitHub could merge before the gate passes; `aidd doctor` says how to require it"
        answer = made.post("/graphql", {"query": AUTO_MERGE, "variables": {"id": found.get("node_id")}}) or {}
    except (http.HttpError, OSError, ValueError, AttributeError, TypeError) as exc:  # an answer of another shape says no
        return f"GitHub answered: {exc}"
    errors = answer.get("errors") if isinstance(answer, dict) else None
    return "; ".join(str((e or {}).get("message") or e) for e in errors) if errors else None


# The words aidd's approving review carries when the person's standing approval gave it: how `stop approving` finds
# the auto-merges that approval turned on, among the person's own.
STANDING_REVIEW = "under your standing approval"
_OPEN_AUTO_MERGES = (
    "query($owner: String!, $name: String!, $after: String) { repository(owner: $owner, name: $name) { pullRequests(states: OPEN, "
    "first: 100, after: $after) { pageInfo { hasNextPage endCursor } nodes { id url autoMergeRequest { enabledBy { login } } "
    "reviews(last: 20, states: APPROVED) { nodes { author { login } body } } } } } }"
)
_MAX_PAGES = 50  # 5,000 open pull requests; past that, say so rather than stop short in silence


def merge_review_body(head: str, decided_via: str | None) -> str:
    """The approving review's text: which commit, and where the person gave the approval. One their standing approval
    gave says so (STANDING_REVIEW), which is how `stop approving` finds the auto-merge it turned on."""
    if decided_via and decided_via.startswith("standing:"):
        given = f"{STANDING_REVIEW} ({decided_via})"
    elif decided_via and decided_via != "prompt":
        given = f'under your "merge it" ({decided_via})'
    else:
        given = "given with `aidd approve merge`"
    return f"Merge approval of {head[:12]}, {given}."


DISABLE_AUTO_MERGE = "mutation($id: ID!) { disablePullRequestAutoMerge(input: {pullRequestId: $id}) { clientMutationId } }"


def disable_standing_auto_merges(root: str, pool: list[str], *, client: github.Client | None = None) -> tuple[list[str], str | None]:
    """Turn off the auto-merge of each open pull request on `origin` that the person's standing approval turned on: the
    person enabled it, and their latest approving review there says it came from the standing approval
    (STANDING_REVIEW). A pull request they approved with their own "merge it" keeps its auto-merge. The person is the
    account the approval went out as (approver_login of `pool`, as approval_target picks it). (The URLs turned off, and
    why not all could be, or None.) Both facts come from GitHub, never from a file on this machine; every page of open
    pull requests is read, and one the standing approval approved whose auto-merge another account turned on is named."""
    repo = origin_repo(root)
    if not repo:
        return [], None
    made = client or _person_client(approver_login(pool))
    if isinstance(made, str):
        return [], made
    owner, name = repo.split("/", 1)
    off: list[str] = []
    left: list[str] = []
    try:
        login = str((made.get("/user") or {}).get("login") or "")
        if not login:
            return [], "GitHub did not say who you are"
        after = None
        for _ in range(_MAX_PAGES):
            answer = made.post("/graphql", {"query": _OPEN_AUTO_MERGES, "variables": {"owner": owner, "name": name, "after": after}}) or {}
            if errors := (answer.get("errors") if isinstance(answer, dict) else None):
                return off, "GitHub answered: " + "; ".join(str((e or {}).get("message") or e) for e in errors)
            repository = (answer.get("data") or {}).get("repository")
            if not repository:
                return off, f"GitHub did not return {repo}"
            page = repository.get("pullRequests") or {}
            for pr in page.get("nodes") or []:
                enabled_by = (((pr.get("autoMergeRequest") or {}).get("enabledBy")) or {}).get("login")
                mine = [r for r in ((pr.get("reviews") or {}).get("nodes") or []) if ((r.get("author") or {}).get("login")) == login]
                if not enabled_by or not mine or STANDING_REVIEW not in str(mine[-1].get("body") or ""):
                    continue
                if enabled_by != login:
                    left.append(f"{pr.get('url')} (auto-merge turned on by @{enabled_by})")
                    continue
                done = made.post("/graphql", {"query": DISABLE_AUTO_MERGE, "variables": {"id": pr.get("id")}}) or {}
                if errors := (done.get("errors") if isinstance(done, dict) else None):
                    return off, "; ".join(str((e or {}).get("message") or e) for e in errors)
                off.append(str(pr.get("url") or ""))
            info = page.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                break
            after = info.get("endCursor")
        else:
            return off, f"more than {_MAX_PAGES * 100} open pull requests: check the rest on GitHub"
    except (http.HttpError, OSError, ValueError, AttributeError, TypeError) as exc:  # an answer of another shape says no
        return off, f"GitHub answered: {exc}"
    return off, (f"still on: {', '.join(left)}" if left else None)


def _gate_required(client: github.Client, repo: str, branch: str) -> bool:
    """Whether `branch` requires the `aidd/gate` status, by a ruleset or by classic branch protection."""
    name = urllib.parse.quote(branch, safe="")
    rules = client.get(f"/repos/{repo}/rules/branches/{name}") or []
    checks = [c for r in rules if r.get("type") == "required_status_checks" for c in (r.get("parameters") or {}).get("required_status_checks") or []]
    if any(c.get("context") == github.STATUS_CONTEXT for c in checks):
        return True
    required = ((client.get(f"/repos/{repo}/branches/{name}") or {}).get("protection") or {}).get("required_status_checks") or {}
    return github.STATUS_CONTEXT in (required.get("contexts") or []) or any(c.get("context") == github.STATUS_CONTEXT for c in required.get("checks") or [])


def origin_repo(root: str = ".") -> str | None:
    """The `owner/name` of the repository's `origin` remote on github.com, or None."""
    try:
        url = git.run(["remote", "get-url", "origin"], root, check=False).strip()
    except (git.GitError, OSError):
        return None
    m = _REMOTE.match(url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def protection_checks(root: str, *, client: github.Client | None = None) -> list[tuple[str, str]]:
    """`aidd doctor`, best effort: does the default branch's protection let the gate decide?

    Only for an `origin` on github.com, with a token (GH_TOKEN, GITHUB_TOKEN, or `gh auth token`); offline or
    without one it says it skipped. AIDD_OFFLINE=1, and AIDD_HOOK_OFFLINE=1 inside a hook, skip it before any request. Warns when the rules do not require `aidd/gate` (so GitHub's review count, which
    takes a bot's approval, decides alone), when `aidd/gate` is not pinned to an App, when an App may bypass the
    rules, and when a merge queue merges groups whose every entry did not pass."""
    repo = origin_repo(root)
    if not repo:
        return []
    if client is None:
        token = _person_token()
        if not token:
            return [("ok", f"GitHub protection of {repo} not checked: no token (set GH_TOKEN, or `gh auth login`)")]
        if "1" in (os.environ.get("AIDD_OFFLINE"), os.environ.get("AIDD_HOOK_OFFLINE")):
            return [("ok", f"GitHub protection of {repo} not checked: offline (AIDD_OFFLINE=1 or a hook)")]
        client = github.Client(token, "https://api.github.com")
    try:
        branch = client.get(f"/repos/{repo}")["default_branch"]
        found = client.get(f"/repos/{repo}/rules/branches/{urllib.parse.quote(branch, safe='')}") or []
    except (http.HttpError, OSError, KeyError, ValueError) as exc:
        why = f"HTTP {exc.status}" if isinstance(exc, http.HttpError) and exc.status else type(exc).__name__
        return [("ok", f"GitHub protection of {repo} not checked: {why} (offline, or the token cannot read the repository's rules)")]
    checks = [c for r in found if r.get("type") == "required_status_checks" for c in (r.get("parameters") or {}).get("required_status_checks") or []]
    reviews = [r.get("parameters") or {} for r in found if r.get("type") == "pull_request"]
    counted = max((int(p.get("required_approving_review_count") or 0) for p in reviews), default=0)
    out: list[tuple[str, str]] = []
    gate = [c for c in checks if c.get("context") == github.STATUS_CONTEXT]
    if not gate:
        why = f"; its rules require {counted} approval(s). {BOT_NOTE}" if counted else ""
        out.append(("warn", f"{repo}: the rules on {branch} do not require the `{github.STATUS_CONTEXT}` status, so the gate decides nothing{why}"))
    elif not all(c.get("integration_id") for c in gate):
        out.append(
            (
                "warn",
                f"{repo}: `{github.STATUS_CONTEXT}` is required on {branch} from any source; pin it to your aidd App, or anyone with write access can post it",
            )
        )
    else:
        out.append(
            (
                "ok",
                f"{repo}: {branch} requires `{github.STATUS_CONTEXT}` from a pinned App" + (f"; GitHub's review count is extra. {BOT_NOTE}" if counted else ""),
            )
        )
    if reviews and not any(p.get("require_last_push_approval") for p in reviews):
        out.append(("warn", f'{repo}: turn on "Require approval of the most recent reviewable push" on {branch}, so whoever pushed last cannot approve'))
    for r in found:
        if r.get("type") == "merge_queue" and (r.get("parameters") or {}).get("grouping_strategy") != "ALLGREEN":
            out.append(("warn", f'{repo}: the merge queue on {branch} can merge an entry that failed; turn on "Only merge non-failing pull requests"'))
    for rid in sorted({r["ruleset_id"] for r in found if isinstance(r.get("ruleset_id"), int)}):
        try:
            actors = client.get(f"/repos/{repo}/rulesets/{rid}").get("bypass_actors") or []
        except (http.HttpError, OSError, ValueError):
            continue  # bypass actors are visible to admins only
        if any(a.get("actor_type") == "Integration" for a in actors):
            out.append(("warn", f"{repo}: ruleset {rid} lets a GitHub App bypass it, so an agent's App could merge past `{github.STATUS_CONTEXT}`"))
    return out + _goal_protection(root, repo, client)


# What a goal branch's rules must block: a goal holds integrated Specs, which nobody may rewrite or delete.
GOAL_RULES = {"non_fast_forward": "force pushes", "deletion": "deletion"}


def _goal_protection(root: str, repo: str, client: github.Client) -> list[tuple[str, str]]:
    """A warning when a goal branch this clone has is not protected on GitHub against force pushes and deletion
    (templates/github/rulesets/goal.json); nothing when there is no goal branch, or the rules cannot be read."""
    from aidd import workitems

    goals = workitems.goal_branches(root)
    if not goals:
        return []
    try:
        found = client.get(f"/repos/{repo}/rules/branches/{urllib.parse.quote(goals[0], safe='')}") or []
    except (http.HttpError, OSError, ValueError):
        return []
    missing = [what for kind, what in GOAL_RULES.items() if not any(r.get("type") == kind for r in found)]
    if not missing:
        return [("ok", f"{repo}: {goals[0]} blocks force pushes and deletion")]
    return [
        (
            "warn",
            f"{repo}: the rules on {goals[0]} allow {' and '.join(missing)}, so a goal's integrated Specs could be rewritten or lost. "
            "Import templates/github/rulesets/goal.json (Settings → Rules → Rulesets → Import a ruleset)",
        )
    ]


# A GitHub `owner/name`: the owner's letters, digits, and inner hyphens; the name's letters, digits, `.`, `_`, and `-`,
# never `.` or `..` alone. `project.repo` pins it on the base branch (config.schema.json).
GITHUB_REPO_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$")


def spec_approval_holds(root: str, spec_id: str, *, pinned: str | None, spec_hash: str | None, client: github.Client | None = None) -> bool:
    """Autopilot: whether Spec approval holds for `spec_id` as the gate decides it on this branch's open
    pull request, from the platform's own approval lines and reviews (`build_context`, then `gate.decide`, as CI runs them).

    It trusts only the repository a person pinned on the base branch (`pinned`, `project.repo`): `origin` is local
    git config, which an agent can change. True only when `origin` is that repository, the pull request's head is this
    working tree's HEAD, the gate judged this Spec at this Spec hash (`spec_hash`, the local one), and found no Spec
    approval pending or failing. `build_context` fetches the pull request's head and base into `refs/aidd/*`. False
    without a pinned repository or a token, offline (AIDD_OFFLINE=1, or AIDD_HOOK_OFFLINE=1 in a hook), with no open pull
    request, on any mismatch, or on any error: autopilot then asks a person."""
    repo = origin_repo(root)
    if not repo or not pinned or not spec_hash or not GITHUB_REPO_NAME.match(pinned) or repo.lower() != pinned.lower():
        return False
    if client is None:
        if "1" in (os.environ.get("AIDD_OFFLINE"), os.environ.get("AIDD_HOOK_OFFLINE")):
            return False
        token = _person_token()
        if not token:
            return False
        client = github.Client(token, "https://api.github.com")
    branch = git.run(["rev-parse", "--abbrev-ref", "HEAD"], root, check=False).strip()
    head = git.run(["rev-parse", "HEAD"], root, check=False).strip()
    if not branch or branch == "HEAD" or not github.COMMIT_SHA.match(head):
        return False
    try:
        prs = client.get(f"/repos/{pinned}/pulls", {"head": f"{pinned.split('/')[0]}:{branch}", "state": "open"})
        if not isinstance(prs, list) or len(prs) != 1 or not isinstance(prs[0], dict):
            return False
        if (prs[0].get("head") or {}).get("sha") != head:
            return False  # the pull request holds another head: what was approved is not what is here
        d = aidd_gate.decide(github.build_context(client, pinned, int(prs[0]["number"]), cwd=root))
        record = d.record if isinstance(d.record, dict) else {}
        findings = record.get("findings")
        if not isinstance(findings, list):
            return False
        return (
            str(record.get("spec_id") or "") == spec_id
            and record.get("head_sha") == head
            and record.get("spec_hash") == spec_hash
            and not any(not isinstance(f, dict) or (f.get("rule") == "spec_approval" and f.get("level") in ("fail", "pending")) for f in findings)
        )
    except Exception:  # noqa: BLE001  # any doubt is a person's decision, never a cleared Spec
        return False
