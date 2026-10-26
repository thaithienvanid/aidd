"""GitLab from the person's side, at their own terminal or through their agent: their sign-in (GITLAB_TOKEN, or
`glab`'s stored token for the host), the merge request `aidd publish` opens, and their Spec approval line on it. The
gate's side is gitlab.py. Merge approval stays the person's own approval of the merge request on GitLab.

Experimental: built against GitLab's REST API documentation and a faked API, not yet run against a production
instance."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass

from aidd import config
from aidd.kernel import git, http
from aidd.platforms import gitlab

# An `origin` on a GitLab host: https://host/group/sub/project(.git), git@host:group/project(.git), or
# ssh://git@host[:port]/group/project(.git). github.com is never a GitLab host.
_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?(?P<h1>[A-Za-z0-9.-]+)(?::(?P<port>[0-9]+))?/|git@(?P<h2>[A-Za-z0-9.-]+):|ssh://git@(?P<h3>[A-Za-z0-9.-]+)(?::[0-9]+)?/)"
    r"(?P<path>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)/?$"
)
TOKEN_ENV = ("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN")  # glab's names, in its order
HOST_ENV = ("GITLAB_HOST", "GL_HOST")
# What glab reads from the environment ahead of its stored config, for every host alike (docs.gitlab.com/cli/configuration):
# its tokens, its hosts (GITLAB_HOST, GITLAB_URI, GITLAB_API_HOST, GL_HOST, ...), and CI autologin with its job token.
# aidd runs glab without them, so glab answers only with the token it stored for the host aidd names.
_GLAB_ENV_PREFIXES = ("GITLAB_", "GL_")
_GLAB_ENV_NAMES = ("OAUTH_TOKEN", "CI_JOB_TOKEN", "GLAB_ENABLE_CI_AUTOLOGIN")


@dataclass(frozen=True)
class GitLabProject:
    """A GitLab project as `origin` names it: its host and its full path (group/subgroup/name)."""

    host: str
    path: str
    port: int | None = None  # an https `origin`'s port; an ssh port never says where the API is

    @property
    def netloc(self) -> str:
        """The host and, when `origin` names one, its port: what a token is given for."""
        return f"{self.host}:{self.port}" if self.port else self.host

    @property
    def api(self) -> str:
        return f"https://{self.netloc}/api/v4"

    @property
    def id(self) -> str:
        return urllib.parse.quote(self.path, safe="")


@dataclass(frozen=True)
class MergeRequest:
    """Where a person's Spec approval goes on GitLab: the branch's open merge request, its head, and who the token signs in as."""

    project: GitLabProject
    iid: int
    url: str
    head_sha: str
    username: str


def gitlab_project(root: str = ".") -> GitLabProject | None:
    """The GitLab project of the repository's `origin`, or None when `origin` is on github.com or is no URL aidd reads."""
    try:
        url = git.run(["remote", "get-url", "origin"], root, check=False).strip()
    except (git.GitError, OSError):
        return None
    m = _REMOTE.match(url)
    if not m:
        return None
    host = (m.group("h1") or m.group("h2") or m.group("h3") or "").lower()
    path = m.group("path").removesuffix(".git")
    port = int(m.group("port")) if m.group("port") and int(m.group("port")) != 443 else None
    return None if not host or host == "github.com" or "/" not in path else GitLabProject(host, path, port)


def _env_host() -> str:
    """The host GITLAB_HOST (or GL_HOST) names, lowercase, with its port when it names one other than 443; gitlab.com
    when neither is set. "" when it names no host aidd reads."""
    named = next((h for n in HOST_ENV if (h := os.environ.get(n, "").strip())), "gitlab.com")
    try:
        parts = urllib.parse.urlsplit(named if "://" in named else f"https://{named}")
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return ""
    return f"{host}:{port}" if host and port and port != 443 else host


def _person_token(netloc: str) -> str | None:
    """The person's token for `netloc` (a host, with its port when `origin` names one): GITLAB_TOKEN (or glab's other
    names) when the environment's host (GITLAB_HOST, else gitlab.com) is exactly `netloc`, else the token `glab` stored
    for `netloc`, asked with glab's environment tokens and hosts removed. A token never goes to a host it was not given
    for, since `origin` is local git config an agent can change."""
    token = next((t for n in TOKEN_ENV if (t := os.environ.get(n, "").strip())), None)
    if token and _env_host() == netloc:
        return token
    out = _glab(["config", "get", "token", "--host", netloc])
    return (out.strip() or None) if out is not None else None


def _glab_env() -> dict[str, str]:
    """This environment without what glab would read ahead of its stored config for every host."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(_GLAB_ENV_PREFIXES) and k.upper() not in _GLAB_ENV_NAMES}


def _glab(argv: list[str]) -> str | None:
    """What `glab <argv>` prints, or None when glab is missing or fails. It reads glab's own config, never a token or
    host from the environment; nothing leaves."""
    glab = shutil.which("glab")
    if not glab:
        return None
    try:
        p = subprocess.run([glab, *argv], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL, env=_glab_env())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def _person_client(project: GitLabProject) -> gitlab.Client | str:
    """A client with the person's own token for the project's host, or why there is none."""
    if os.environ.get("AIDD_OFFLINE") == "1":
        return "offline (AIDD_OFFLINE=1): aidd cannot reach GitLab"
    token = _person_token(project.netloc)
    if not token:
        return f"no GitLab token for {project.netloc}: run `glab auth login --hostname {project.netloc}` (or set GITLAB_TOKEN, and GITLAB_HOST for a host other than gitlab.com)"
    return gitlab.Client(token, project.api)


def _who(client: gitlab.Client) -> tuple[str, str | None]:
    """Who the token signs in as, and why aidd posts nothing as that account: a bot (a service account, or a project
    or group access token) is never a person, so an approval line it posts would never be the person's decision. Only
    `bot: false` makes the account a person."""
    me = client.get("/user") or {}
    username = str(me.get("username") or "") if isinstance(me, dict) else ""
    if not username:
        return "", "GitLab did not say who you are"
    if not isinstance(me, dict) or me.get("bot") is not False or gitlab.ACCESS_TOKEN_BOT.match(username):
        return username, (
            f"the GitLab token signs in as {username}, a bot account, so aidd posts nothing: use your own personal access "
            "token (`glab auth login`, or GITLAB_TOKEN)"
        )
    return username, None


def _open_merge_requests(client: gitlab.Client, project: GitLabProject, branch: str) -> list[dict]:
    """The open merge requests of `branch` within the project. GitLab lists a fork's merge request from a branch of the
    same name too, so only one whose source and target are the project itself, by its numeric id, is the branch's."""
    own = (client.get(f"/projects/{project.id}") or {}).get("id")
    if not isinstance(own, int) or isinstance(own, bool):
        raise LookupError(f"GitLab did not say which project {project.path} is")
    found = client.get(f"/projects/{project.id}/merge_requests", {"source_branch": branch, "state": "opened"}) or []
    mrs = [m for m in found if isinstance(m, dict)] if isinstance(found, list) else []
    return [m for m in mrs if m.get("source_project_id") == own and m.get("target_project_id") == own]


def open_merge_request(root: str, branch: str, base: str, *, client: gitlab.Client | None = None) -> tuple[str | None, str | None]:
    """Open the merge request of `branch` into `base` as the person (their own token), titled by the branch's newest
    commit, or name the one already open: (its URL, None), or (None, why not). `aidd publish` calls it once it has
    pushed the branch."""
    project = gitlab_project(root)
    if not project:
        return None, "`origin` is not a GitLab repository: open the merge request on your platform"
    made = client or _person_client(project)
    if isinstance(made, str):
        return None, made
    try:
        _, bot = _who(made)
        if bot:
            return None, bot
        open_now = _open_merge_requests(made, project, branch)
        if open_now:
            return str(open_now[0].get("web_url") or ""), None
        title = git.run(["log", "-1", "--format=%s", f"refs/heads/{branch}"], root, check=False).strip() or branch
        mr = made.post_json(
            f"/projects/{project.id}/merge_requests",
            {"source_branch": branch, "target_branch": base, "title": title, "description": "Published with `aidd publish`."},
        )
    except (http.HttpError, LookupError) as exc:
        return None, f"GitLab answered: {exc}"
    return str((mr or {}).get("web_url") or ""), None


def gitlab_approval_target(
    root: str, branch: str, pool: list[str], *, head: str, client: gitlab.Client | None = None
) -> tuple[MergeRequest | None, str | None]:
    """The merge request a person's Spec approval of `branch` goes on, or None and why it cannot. The gate on GitLab
    counts an Approver's note there, never this machine's decision records; so the token's user must be in the pool (a group
    entry is left to the gate, which resolves it), and never a bot. The merge request must name `head`, the commit
    `aidd publish` just pushed, so a line never goes on a merge request that holds other work."""
    project = gitlab_project(root)
    if not project:
        return None, "`origin` is not a GitLab repository, so aidd cannot post the approval: post the line on the merge request yourself"
    made = client or _person_client(project)
    if isinstance(made, str):
        return None, made
    try:
        username, bot = _who(made)
        if bot:
            return None, bot
        mrs = _open_merge_requests(made, project, branch)
    except (http.HttpError, LookupError) as exc:
        return None, f"GitLab answered: {exc}"
    if not mrs:
        return None, f"{branch} has no open merge request on {project.path}. Publishing is the person's: they type `publish` (or run `aidd publish`)"
    names = {config.normalize_identity(str(a)) for a in pool}
    if config.normalize_identity(username) not in names and not any("/" in n for n in names):
        return None, (
            f"GitLab knows you as @{username}, who is not an Approver here ({', '.join(map(str, pool)) or 'nobody'}). Sign in as an "
            "Approver with `glab auth login` (or set GITLAB_TOKEN to an Approver's token), then publish again"
        )
    mr = mrs[0]
    url, sha = str(mr.get("web_url") or ""), str(mr.get("sha") or "")
    if sha != head:
        return None, (
            f"the merge request {url} names head {sha[:12] or '(none yet)'}, not {head[:12]} that you just pushed, so aidd posts no "
            "Spec approval on it. GitLab may still be updating it: type `publish` again (or run `aidd publish`) in a minute"
        )
    return MergeRequest(project, int(mr["iid"]), url, sha, username), None


def post_gitlab_spec_approval(mr: MergeRequest, line: str, *, client: gitlab.Client | None = None) -> str:
    """Post the Spec approval line as a note on the merge request, as the person gitlab_approval_target named; the
    merge request's URL."""
    made = client or _person_client(mr.project)
    if isinstance(made, str):
        raise RuntimeError(made)
    made.post_json(f"/projects/{mr.project.id}/merge_requests/{mr.iid}/notes", {"body": line})
    return mr.url
