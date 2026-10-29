"""`agents.delegate`: whether the main session must hand an edit to a role, to whom, and the note it gets
when it need not; and whether the guard holds an actor's writes at all.
"""

from __future__ import annotations

import os
import re
import site
import stat
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from aidd import config, workitems
from aidd.guard import dialects, edit_check, mcp_tools, path_location, repo_config, role_areas, verdicts
from aidd.kernel import git


def holds(root: str | None, event: dict) -> bool:
    """Whether the guard holds this actor's writes in the repository `root`: any subagent where aidd is adopted, or a main session that `delegate` denies there. With the loop switched off in the config, no writer is
    held. On an explore branch a role and a helper still are: their edits are free there, but never the guard's own
    wiring or the git directory (edit_check.check_agent_edit, judge_write)."""
    if not root or not repo_config.is_adopted(root):
        return False
    cfg = repo_config.load_config(root)
    if cfg is not None and not config.component_on(cfg.raw, "spec_steps"):
        return False
    if event.get("agent_type"):  # a role or a helper, also one that may write (agents.helpers)
        return True
    if cfg is not None and not workitems.edits_held(cfg, root):
        return False
    if cfg is not None and _plays_role(root, event):
        return True
    return cfg is not None and delegate_denies(root, event, cfg) is not None


def _plays_role(root: str, event: dict) -> bool:
    """Whether a main session plays a role (`aidd context --play --session <id>`), so the guard holds it as it holds a
    subagent with that role. A record aidd cannot read holds it too (fail closed)."""
    from aidd import autopilot

    if event.get("agent_type"):
        return False
    try:
        return autopilot.played_role(root, event.get("session_id")) is not None
    except Exception:
        return True


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
    """Whether the event's session holds a live autopilot lease whose run has not ended: a run that finished or hit a
    limit frees its lead's edits before it runs `stop`. A lease aidd cannot read names no session here: `auto`
    never denies a session it cannot place, and `aidd autopilot next` refuses that file anyway."""
    from aidd import autopilot

    sid = event.get("session_id")
    if not isinstance(sid, str) or not autopilot.SESSION_ID.match(sid):
        return False
    try:
        return autopilot.holds_lease(root, sid)
    except (autopilot.LeaseError, OSError, git.GitError):
        return False


def _lease_on_record(root: str, event: dict) -> bool:
    """Whether the event's session has an autopilot lease on record, live, ended, or stale, until `aidd autopilot stop`
    removes it. A lease file aidd cannot read counts for every session (fail closed): it may be anyone's."""
    from aidd import autopilot

    sid = event.get("session_id")
    try:
        found = autopilot.lease_for_session(root, sid if isinstance(sid, str) and autopilot.SESSION_ID.match(sid) else "no-session", include_stale=True)
    except (autopilot.LeaseError, OSError, ValueError, git.GitError):
        return True
    return found is not None and isinstance(sid, str)


def acts_alone(root: str, event: dict) -> bool:
    """Whether the agent in `event` works without the person: a subagent (a role or a helper), a main thread started as an
    aidd-team role (`--agent aidd-team:<role>`, as `holds` reads it), or a main session that has an autopilot lease on
    record or plays a role. The person's own session is none of these."""
    from aidd.guard import role_areas

    if event.get("agent_type") and (not role_areas.is_main_thread(event) or role_areas.role_of(event) is not None):
        return True
    return _lease_on_record(root, event) or _plays_role(root, event)


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


# A coding agent's own record of the conversation, which aidd reads for the person's typed words where the harness's
# hook event does not carry them (Antigravity's transcript, dialects._antigravity_prompt): no agent ever writes there.
HARNESS_RECORDS = dialects.HARNESS_RECORDS
HARNESS_RECORD_DENY = "{path} is the coding agent's own record of this conversation, which aidd reads for the person's typed words: an agent never writes it"


# A person's own settings of git, gh, and glab: an alias, a hook folder, an extension, or a program there runs for every
# repository, and gh's hosts file holds their token. Whole folders, wherever an environment variable moves them.
_PERSON_SETTINGS = re.compile(r"/(?:\.gitconfig$|\.config/(?:git|gh|glab-cli)(?:/|$)|\.local/share/gh(?:/|$))", re.I)
_SETTINGS_FOLDERS = ("GH_CONFIG_DIR", "GH_DATA_DIR", "GLAB_CONFIG_DIR", "GIT_CONFIG_GLOBAL")


def _person_setting(reading: str) -> bool:
    """Whether a resolved path is in a person's settings of git, gh, or glab (_PERSON_SETTINGS), also at the folder or
    file GH_CONFIG_DIR, GH_DATA_DIR, GLAB_CONFIG_DIR, GIT_CONFIG_GLOBAL, XDG_CONFIG_HOME, or XDG_DATA_HOME names, as
    written and as it resolves."""
    named = [os.environ.get(k, "") for k in _SETTINGS_FOLDERS]
    named += [os.path.join(os.environ[k], tool) for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME") if os.environ.get(k) for tool in ("git", "gh", "glab-cli")]
    places = {p.casefold() for f in named if f for p in (os.path.abspath(f), os.path.realpath(f))}
    folded = reading.casefold()
    return bool(_PERSON_SETTINGS.search(reading)) or any(folded == p or folded.startswith(p + "/") for p in places)


# The folder of the aidd package this guard runs from.
_PACKAGE = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _runtime_folders() -> list[str]:
    """The folders the guard runs from on this machine: `~/.aidd` (whose `bin/aidd` every repository's hooks start
    from), and, for an installed aidd, its package and the interpreter running it (its prefix, its site-packages,
    and the folder of its executable). A package in a source checkout is that repository's own work."""
    installed = any(part in ("site-packages", "dist-packages") for part in Path(_PACKAGE).parts)
    found = [os.path.join(os.path.expanduser("~"), ".aidd")]
    if installed:
        found += [_PACKAGE, sys.prefix, sys.exec_prefix, os.path.dirname(os.path.realpath(sys.executable)), *site.getsitepackages()]
    return list(dict.fromkeys(q.replace("\\", "/").casefold() for p in found for q in (os.path.abspath(p), os.path.realpath(p))))


def _aidd_install(reading: str) -> bool:
    """Whether a resolved path is in a folder the guard runs from (_runtime_folders), or holds one, as a folder that
    is moved or removed does: a write there could switch the guard off for every repository."""
    folded = reading.replace("\\", "/").rstrip("/").casefold()
    return any(folded == p or folded.startswith(p + "/") or p.startswith(folded + "/") for p in _runtime_folders())


def _plugin_folders() -> list[str]:
    """Claude Code's plugins folder on this machine: `~/.claude/plugins`, `plugins` under CLAUDE_CONFIG_DIR when it
    moves the config, and CLAUDE_CODE_PLUGIN_CACHE_DIR when it moves the plugins, as written and as each resolves."""
    home = os.path.expanduser("~")
    found = [os.path.join(home, ".claude", "plugins"), os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude"), "plugins")]
    found += [os.environ["CLAUDE_CODE_PLUGIN_CACHE_DIR"]] if os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR") else []
    return list(dict.fromkeys(q.replace("\\", "/").rstrip("/").casefold() for p in found for q in (os.path.abspath(p), os.path.realpath(p))))


def _claude_plugins(reading: str) -> bool:
    """Whether a resolved path is in Claude Code's plugins folder (_plugin_folders) or a seed folder, or holds one. aidd's hooks, its MCP
    server, and the aidd-cli plugin's `aidd` run from its copies, and its records say which copy loads, so a write
    there could switch the guard off. Each plugin's own `data/` folder, where a plugin keeps its state, stays open."""
    folded = reading.replace("\\", "/").rstrip("/").casefold()
    for p in _plugin_folders():
        if folded == p or p.startswith(folded + "/"):
            return True
        if folded.startswith(p + "/") and not (folded + "/").startswith(p + "/data/"):
            return True
    # The folders CLAUDE_CODE_PLUGIN_SEED_DIR names hold plugins installed ahead of time, in containers and CI, whole.
    seeds = [s for s in os.environ.get("CLAUDE_CODE_PLUGIN_SEED_DIR", "").split(os.pathsep) if s]
    seen = {q.replace("\\", "/").rstrip("/").casefold() for s in seeds for q in (os.path.abspath(s), os.path.realpath(s))}
    return any(folded == p or folded.startswith(p + "/") or p.startswith(folded + "/") for p in seen)


def harness_record(path: Path) -> str | None:
    """The denial for a write to aidd's own launcher or installed code, to Claude Code's installed plugins, to a coding
    agent's record of the conversation, or to a person's own settings of git, gh, or glab (_PERSON_SETTINGS), or None."""
    shown = os.path.abspath(os.path.expanduser(str(path)))
    # As written and as it resolves (a symlink into the folder, or one the folder is reached through), in any case.
    readings = {shown, os.path.realpath(shown)}
    if any(_aidd_install(r.replace("\\", "/")) for r in readings):
        return f"{shown} is in, or holds, aidd's own launcher or installed code, which every repository's guard runs from: only `aidd init`, `aidd upgrade`, or `aidd self-update` writes it"
    if any(_claude_plugins(r.replace("\\", "/")) for r in readings):
        return (
            f"{shown} is in, or holds, Claude Code's installed plugins, which aidd's hooks and its `aidd` command run from: "
            "only `claude plugin`, `/plugin`, or `/aidd update` changes it"
        )
    if any(_person_setting(r.replace("\\", "/")) for r in readings):
        return f"{shown} holds a person's own settings of git, gh, or glab, which apply in every repository: leave it to them"
    hit = any(HARNESS_RECORDS.search(r.replace("\\", "/") + "/") for r in readings)
    return HARNESS_RECORD_DENY.format(path=shown) if hit else None


def judge_write(path: Path, root: str | None, event: dict, *, lead_only: bool = False, content: bool = True) -> verdicts.Verdict | None:
    """The verdict on a write to `path` by whoever `event` says writes, in the repository that holds the path (never the
    session's): a role or a helper meets the edit rules, a main session `delegate`. `root` is the session's own
    repository, which also holds a hard link's write. `lead_only` checks only `delegate` (an MCP tool), and `content`
    is false for a write that only removes or renames a name. None when nothing applies."""
    if record := harness_record(path):
        return "deny", record
    place = path_location.locate(path)
    if path_location.in_git_dir(path, [root, place.top]):
        # Every writer, for every git directory, also one kept outside the work tree (the part check below sees `.git` only).
        return "deny", f"{path} is inside the git directory: only git and aidd commands write there. Run the git or aidd command that changes it"
    failed = path_location.git_failed_reason(place.probe, place.why)
    if failed:
        return "deny", failed[0]
    verdict: verdicts.Verdict | None = None
    if place.top and repo_config.is_adopted(place.top):
        if any(part.casefold() == ".git" for part in Path(place.rel).parts):
            # Every writer, as for an edit tool: only git and aidd commands write there. A HEAD written by hand could name
            # an explore branch, where the guard holds no edit, and a hook or a config line runs at the next git command.
            return "deny", f"{place.rel} is inside the git directory: only git and aidd commands write there. Run the git or aidd command that changes it"
        if not lead_only and event.get("agent_type"):  # a role, a helper, or a helper that may write: the edit rules alike
            verdict = edit_check.check_agent_edit(place.top, place.rel, event)
        elif not event.get("agent_type"):
            cfg = repo_config.load_config(place.top)
            if cfg is None and (kept := repo_config.kept_unreadable(place.top)):
                return "deny", f"shell write to {place.rel}: {kept}. Until then no write goes through here"
            # The always-on rules first: the session's shell write is held to it as its edit tools are, with no text to read. An
            # MCP tool's write too (`lead_only`): the always-on rules bind every writer, and hold while the config is broken.
            verdict = edit_check.person_only_check(place.top, cfg, place.rel, event)
            if verdict is None:
                verdict = delegate_check(place.top, place.rel, event, cfg) if cfg is not None else None
            if verdict is None or verdict[0] == "allow":  # an edit tool's, a shell's, or an MCP tool's write alike
                verdict = edit_check.played_check(place.top, place.rel, event) or verdict
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
    if not autopilot.claim_first_mention(root, sid, f"delegate {owners[0] if owners else '-'}"):
        return None
    if not owners:
        # Information only: this session may edit the file. It must never read as a reason to refuse a harmless edit.
        return (
            f"aidd: `agents.delegate: auto` (a note, not a denial): no aidd-team role's area holds {rel}, so there is no role "
            "to hand it to. This session may edit it. This note comes once per session and role."
        )
    return (
        f"aidd: `agents.delegate: auto`: place the role as the lead rule says: {hand_to(root, cfg, rel)}, or play it yourself only for a "
        "small step that adds a view to your own work. This note comes once per session and role."
    )
