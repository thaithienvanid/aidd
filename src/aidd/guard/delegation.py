"""`agents.delegate`: whether the main session must hand an edit to a role, to whom, and the note it gets
when it need not; and whether the guard holds an actor's writes at all.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from urllib.parse import unquote, urlparse

from aidd import config, workitems
from aidd.guard import edit_check, mcp_tools, path_location, repo_config, role_areas, verdicts
from aidd.kernel import git


def holds(root: str | None, event: dict) -> bool:
    """Whether the guard holds this actor's writes in the repository `root`: a role or a helper subagent where aidd is
    adopted, or a main session that `delegate` denies there. With the loop switched off in the config, no writer is
    held. On an explore branch a role and a helper still are: their edits are free there, but never the guard's own
    wiring or the git directory (edit_check.check_agent_edit, judge_write)."""
    if not root or not repo_config.is_adopted(root):
        return False
    cfg = repo_config.load_config(root)
    if cfg is not None and not config.component_on(cfg.raw, "loop"):
        return False
    if role_areas.role_of(event) or role_areas.is_helper(event):
        return True
    if cfg is not None and not workitems.edits_held(cfg, root):
        return False
    return cfg is not None and delegate_denies(root, event, cfg) is not None


HARD_LINK = (
    "{path} has {n} hard links, so a write to it changes the same file under every other name, and the guard cannot "
    "tell whether one of them is repository content. Write a new file instead, or leave it alone"
)


def hard_link_check(path: Path, roots: list[str | None], event: dict, cwd: Path | None = None) -> verdicts.Verdict | None:
    """("deny", reason) for a write to a regular file with more than one hard link, by an actor the guard holds in
    one of `roots` (the target's repository and the session's), or in the repository of `cwd`, read only for such a
    file; else None. Removing a name is not such a write."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_nlink < 2:
        return None
    if cwd is not None:
        roots = [*roots, path_location.session_root(cwd)]
    if not any(holds(r, event) for r in dict.fromkeys(r for r in roots if r)):
        return None
    return "deny", HARD_LINK.format(path=path, n=st.st_nlink)


def _lease_holder(root: str, event: dict) -> bool:
    """Whether the event's session holds a live autopilot lease. A lease aidd cannot read names no session here: `auto`
    never denies a session it cannot place, and `aidd autopilot next` refuses that file anyway."""
    from aidd import autopilot

    sid = event.get("session_id")
    if not isinstance(sid, str) or not autopilot.SESSION_ID.match(sid):
        return False
    try:
        return autopilot.lease_for_session(root, sid) is not None
    except (autopilot.LeaseError, OSError, git.GitError):
        return False


def delegate_in_force(root: str, cfg: config.Config) -> str:
    """The `delegate` mode the guard applies here. A profile's default of `always` (audited) applies only when the
    team is installed, since there is no role to hand an edit to without it; until then the guard acts as `auto`. A
    config that sets `always` itself keeps it, team or not: the guard then denies and says to install the team."""
    mode = config.delegate_mode(cfg.raw)
    if mode == "always" and not config.delegate_set(cfg.raw) and not config.team_installed(root):
        return "auto"
    return mode


def delegate_denies(root: str, event: dict, cfg: config.Config) -> str | None:
    """Why `delegate` denies this main session's edits of repository content (`always`, or `auto` in the session that
    holds the autopilot lease), or None when it does not. A subagent's event is never the main session's."""
    if event.get("agent_type"):
        return None
    mode = delegate_in_force(root, cfg)
    if mode == "always":
        return 'agents.delegate: "always": the main session never edits repository content'
    if mode == "auto" and _lease_holder(root, event):
        return 'agents.delegate: "auto" and this session runs autopilot: the lead never edits repository content'
    return None


MAX_NAMED_OWNERS = 3


def hand_to(root: str, cfg: config.Config, rel: str) -> str:
    """Whom to hand an edit of `rel` to, in a sentence the agent can act on."""
    owners = role_areas.owners_of(root, cfg, rel)
    if not owners:
        return (
            f"no role's area holds {rel}: a person edits it, or a Task's scope must cover it first "
            "(`/aidd-team:fix` for a small fix, `/aidd-team:specify` for a Spec)"
        )
    names = ", ".join(f"`aidd-team:{r}`" for r in owners[:MAX_NAMED_OWNERS])
    return f"hand the edit of {rel} to the role that owns it: {names} (a subagent of that type; `aidd-<role>` when `aidd init --team` installed the team)"


NO_TEAM = (
    "no aidd-team role is installed here to hand {rel} to. Install the team (`aidd init --team`, or the aidd-team "
    "plugin), or ask a person to change `agents.delegate`. Never route around this through a shell"
)


def delegate_check(root: str, rel: str, event: dict, cfg: config.Config) -> verdicts.Verdict | None:
    """("deny", reason) when `delegate` denies this main-session edit of `rel`, else None. Under `always` with no team
    installed, the reason says to install it rather than name a role that is not there."""
    why = delegate_denies(root, event, cfg)
    if why is None or not path_location.governed(root, rel):
        return None
    if config.delegate_mode(cfg.raw) == "always" and not config.team_installed(root):
        return "deny", f"{why}, and {NO_TEAM.format(rel=rel)}"
    return "deny", f"{why}; {hand_to(root, cfg, rel)}. Hand off instead, and never route around this through a shell"


# An MCP tool that writes a file (a filesystem server's `write_file`, a forge's `create_or_update_file` or `push_files`):
# under a `delegate` that denies, it is held to the same rule as an edit of each path its input names.
_MCP_FILE_VERBS = frozenset(
    {"write", "edit", "create", "update", "put", "move", "rename", "delete", "remove", "replace", "append", "patch", "apply", "save", "push"}
)
_MCP_FILE_NOUNS = frozenset({"file", "files"})


_MCP_PATH_KEYS = ("path", "file_path", "filename", "file", "destination", "target", "source", "src", "dest", "old_path", "new_path", "uri")


def _mcp_paths(tool_input: object) -> list[str]:
    """The file paths an MCP tool's input names (_MCP_PATH_KEYS, each of `paths`, and each of `files`); a `uri` counts
    only as a `file:` URI."""
    if not isinstance(tool_input, dict):
        return []

    def named(d: dict) -> list[str]:
        found = []
        for k in _MCP_PATH_KEYS:
            v = d.get(k)
            if isinstance(v, str) and v:
                if v.startswith("file:"):
                    v = unquote(urlparse(v).path)
                elif k == "uri" or "://" in v:
                    continue
                found.append(v)
        return found

    found = named(tool_input)
    for key in ("files", "paths"):
        for item in tool_input.get(key) or [] if isinstance(tool_input.get(key), list) else []:
            if isinstance(item, dict):
                found += named(item)
            elif isinstance(item, str):
                found.append(item)
    return found


def delegate_mcp(root: str | None, cwd: str, name: str, tool_input: object, event: dict) -> verdicts.Verdict | None:
    """("deny", reason) for an MCP tool that writes a file of a repository while `delegate` denies the main session's
    edits there. Each path is judged in the repository that holds it; a relative one is read from `root`, the
    session's repository, else from `cwd`."""
    words = mcp_tools.mcp_words(name.rsplit("__", 1)[-1])
    if not words or words[0] in mcp_tools.MCP_READ_VERBS:
        return None
    if not (_MCP_FILE_VERBS & set(words)) or not (_MCP_FILE_NOUNS & set(words)):
        return None
    # The main session meets `delegate`; a role or a helper meets the edit rules, as for a shell write.
    lead_only = not event.get("agent_type")
    for raw in _mcp_paths(tool_input):
        for path in path_location.readings(Path(raw) if os.path.isabs(raw) else Path(root or cwd) / raw.lstrip("/")):
            verdict = judge_write(path, root, event, lead_only=lead_only)
            if verdict is not None and verdict[0] == "deny":
                return "deny", f"MCP tool {name}: {verdict[1]}"
    return None


def judge_write(path: Path, root: str | None, event: dict, *, lead_only: bool = False, content: bool = True) -> verdicts.Verdict | None:
    """The verdict on a write to `path` by whoever `event` says writes, in the repository that holds the path (never the
    session's): a role or a helper meets the edit rules, a main session `delegate`. `root` is the session's own
    repository, which also holds a hard link's write. `lead_only` checks only `delegate` (an MCP tool), and `content`
    is false for a write that only removes or renames a name. None when nothing applies."""
    place = path_location.locate(path)
    failed = path_location.git_failed_reason(place.probe, place.why)
    if failed:
        return "deny", failed[0]
    verdict: verdicts.Verdict | None = None
    if place.top and repo_config.is_adopted(place.top):
        if not lead_only and (role_areas.role_of(event) or role_areas.is_helper(event)):
            if any(part.casefold() == ".git" for part in Path(place.rel).parts):
                # As for an edit tool: only git and aidd commands write there. A HEAD written by hand could name an
                # explore branch, where the guard holds no edit.
                return "deny", f"{place.rel} is inside the git directory: only git and aidd commands write there. Run the git or aidd command that changes it"
            verdict = edit_check.check_agent_edit(place.top, place.rel, event)
        elif not event.get("agent_type"):
            cfg = repo_config.load_config(place.top)
            verdict = delegate_check(place.top, place.rel, event, cfg) if cfg is not None else None
    if (verdict is None or verdict[0] == "allow") and content:
        verdict = hard_link_check(path, [place.top, root], event) or verdict
    return verdict


def delegate_steer(root: str, rel: str, event: dict, cfg: config.Config) -> str | None:
    """Under `auto`, outside the lease holder's session: a note to the agent, never a denial, naming the role that owns
    `rel`. Said once per session and role, only when the team is installed; None otherwise."""
    from aidd import autopilot

    sid = event.get("session_id")
    if event.get("agent_type") or delegate_in_force(root, cfg) != "auto" or not isinstance(sid, str) or not autopilot.SESSION_ID.match(sid):
        return None
    if not path_location.governed(root, rel) or not config.team_installed(root):
        return None
    owners = role_areas.owners_of(root, cfg, rel)
    if not autopilot.is_first_mention(root, sid, f"delegate {owners[0] if owners else '-'}"):
        return None
    if not owners:
        # Information only: this session may edit the file. It must never read as a reason to refuse a harmless edit.
        return (
            f"aidd: `agents.delegate: auto` (a note, not a denial): no aidd-team role's area holds {rel}, so there is no role "
            "to hand it to. This session may edit it. This note comes once per session and role."
        )
    return f"aidd: `agents.delegate: auto`: prefer the team over editing yourself; {hand_to(root, cfg, rel)}. This note comes once per session and role."
