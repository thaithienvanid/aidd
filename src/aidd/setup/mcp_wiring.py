"""How a coding agent starts aidd's MCP server.

The MCP server starts through this user's launcher, `~/.aidd/bin/aidd`, which `aidd init` writes: the interpreter
aidd is installed with, by its absolute path and isolated (`-I`), so a project's PYTHONPATH or a module in the working
folder cannot replace aidd's code. `.mcp.json` and `.codex/config.toml` then name the launcher through the home folder
and hold no machine's path. A launcher whose aidd sits inside the repository is never written: every repository on the
machine starts aidd through it, so one repository would steer them all.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import site
import sys
import tomllib
from pathlib import Path
from typing import Any

import aidd
from aidd import config
from aidd.kernel import processes, regular_files, repo_paths
from aidd.setup import files, pins, self_updating

USER_LAUNCHER = (".aidd", "bin", "aidd")
USER_LAUNCHER_SHOWN = "~/" + "/".join(USER_LAUNCHER)
SH_LAUNCHER = '"$HOME"/' + "/".join(USER_LAUNCHER)  # sh expands $HOME
INSTALL_COMMAND = f"uv tool install git+{pins.RELEASE_REPO_URL}"
MCP_LAUNCHER = "${HOME}/" + "/".join(USER_LAUNCHER)  # Claude Code expands ${HOME} in .mcp.json
LOADER = "import sys; sys.version_info < (3, 11) and sys.exit(3); sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = sys.argv.pop(1); from aidd.cli import main; sys.exit(main())"
MCP_FILE = ".mcp.json"
CODEX_CONFIG = ".codex/config.toml"
_BEGIN = "# >>> aidd: the aidd MCP server. `aidd init` writes this block, and `aidd uninstall` removes it."
_END = "# <<< aidd"
# aidd's own MCP tools, which `aidd init` lets run with no prompt: `risk`, `status`, `validate`, and `recall` only
# read (`recall` refreshes its cache in `.git/aidd/`), and `record` writes only `.git/aidd/records/` and refuses a secret's
# shape; the ones that read fetch a parent config
# the repository's `extends` names by URL, as the CLI does. A headless run can approve nothing, so without this it
# records nothing. `records push`, which sends records away, is a CLI command, an ask of its own. A config with
# `mcp: {allow_own_tools: false}` keeps them asking: init and upgrade allow none and take out the ones aidd allowed.
OWN_MCP_TOOLS = ("risk", "status", "validate", "recall", "record")  # written to the allow lists in this order
_CODEX_TOOLS = "".join(f'[mcp_servers.aidd.tools.{t}]\napproval_mode = "approve"\n' for t in OWN_MCP_TOOLS)


def codex_block(allow: bool) -> str:
    """aidd's block in `.codex/config.toml`: the server, and its tools allowed by name unless `allow` is false."""
    return f'{_BEGIN}\n[mcp_servers.aidd]\ncommand = "sh"\nargs = ["-c", {json.dumps(f"exec {SH_LAUNCHER} mcp")}]\n{_CODEX_TOOLS if allow else ""}{_END}\n'


CLAUDE_SETTINGS = ".claude/settings.json"
# The tool names aidd itself added to Claude Code's `permissions.allow`, and the ones a person took out, in
# `.aidd/harness-rules.json` beside the ask rules, so uninstall takes out only the first, never a name a person listed first.
ALLOWED_KEY, TAKEN_OUT_KEY = "claude-code-mcp-allowed", "claude-code-mcp-taken-out"
LEDGER = config.HARNESS_RULES_FILE
OPTED_OUT = "`mcp.allow_own_tools` is false"


def _ledger(root: Path) -> tuple[set[str], set[str]]:
    """(the names aidd added to Claude Code's `permissions.allow` and that are still aidd's; the names aidd added that
    the person took out, which stay out). A name the person puts back by hand is theirs, so it is on neither list."""
    try:
        data = json.loads(regular_files.repository_text(root, LEDGER) or "")
    except (OSError, ValueError):
        return set(), set()

    # Only aidd's own tool names count, so a crafted ledger can never take out a person's own entry.
    own = {n for prefix in config.CLAUDE_TOOL_PREFIXES for n in claude_tool_names(prefix)}

    def names(key: str) -> set[str]:
        value = data.get(key) if isinstance(data, dict) else None
        return {str(n) for n in value} & own if isinstance(value, list) else set()

    return names(ALLOWED_KEY), names(TAKEN_OUT_KEY)


def _added(root: Path) -> list[str]:
    return sorted(_ledger(root)[0])


def _ledger_problem(root: Path) -> tuple[str, bool]:
    """Why aidd refuses the ledger, and whether the file is there to fix: a link or a pipe, a file behind a link on the way,
    one that does not parse, one that is no JSON object, or one whose MCP keys are no lists. ("", False) when it is fine
    or missing."""
    text, why = regular_files.named_text(root, LEDGER)
    if text is None:
        return ("" if why == regular_files.MISSING else why), False
    try:
        data = json.loads(text)
    except ValueError:
        return "not valid JSON", True
    if not isinstance(data, dict):
        return "no JSON object", True
    bad = next((k for k in (ALLOWED_KEY, TAKEN_OUT_KEY) if k in data and not isinstance(data[k], list)), "")
    return (f"`{bad}` is no list" if bad else ""), True


def _ledger_refused(root: Path, actions: list[str]) -> bool:
    """Whether aidd refuses the ledger (`_ledger_problem`). Then it fails closed: the allowed tools stay as they are,
    since aidd cannot tell its own from a person's, and it says why."""
    why, there = _ledger_problem(root)
    if why:
        fix = "fix it" if there else "replace it with the file"
        actions.append(f"skipped  {CLAUDE_SETTINGS} (the MCP tools aidd allowed stay as they are: {LEDGER} is {why}; {fix}, then run aidd again)")
    return bool(why)


def _write_ledger(root: Path, added: set[str], taken_out: set[str], actions: list[str]) -> None:
    """Record both lists in the ledger beside the ask rules, keeping every other key as it is; with both empty, their keys
    go, and the file with them when nothing else is left. A link at the ledger or on the way to it is skipped and named."""
    ledger = root / LEDGER
    if refused := regular_files.write_refusal(root, ledger):
        actions.append(f"skipped  {LEDGER} ({refused})")
        return
    if why := _ledger_problem(root)[0]:  # the callers check first; this keeps a direct call from rewriting a file it cannot read
        actions.append(f"skipped  {LEDGER} (it is {why}: fix it, then run aidd again)")
        return
    data = json.loads(regular_files.repository_text(root, LEDGER) or "{}")
    mine = {ALLOWED_KEY: sorted(added), TAKEN_OUT_KEY: sorted(taken_out)}
    new = {k: v for k, v in data.items() if k not in mine} | {k: v for k, v in mine.items() if v}
    if not new:
        if regular_files.writes_held():  # a plan names the removal and leaves the file
            there = regular_files.hold_removal(root, ledger)
        else:
            there = ledger.is_file()
            ledger.unlink(missing_ok=True)
        actions += [f"removed  {LEDGER} (nothing of aidd's is left to record)"] if there else []
        return
    text = json.dumps(new, indent=2) + "\n"
    changed = regular_files.repository_text(root, LEDGER) != text
    if files.write_or_skip(root, ledger, text, actions) and changed:
        listed = "the MCP tools aidd allowed, so a later run takes out only those" if any(mine.values()) else "no MCP tool of aidd's is listed now"
        actions.append(f"updated  {LEDGER} ({listed})")


def _text(root: Path, rel: str, actions: list[str]) -> str | None:
    """The text of a file aidd wires, "" when there is none; None, with a `skipped` line, when aidd refuses it, such as a
    link, a pipe, or a file behind a link on the way, so aidd never writes over what it never read."""
    text, why = regular_files.named_text(root, rel)
    if text is None and why != regular_files.MISSING:
        actions.append(f"skipped  {rel} ({why}: aidd neither reads it nor writes through it; replace it with the file, then run aidd again)")
        return None
    return text or ""


def _json(text: str) -> Any:
    """`text` as JSON, {} when it is empty: a file not there yet."""
    return json.loads(text) if text else {}


def _reconcile(root: Path, allow: list) -> tuple[set[str], set[str]]:
    """Bring the ledger in line with what `permissions.allow` holds now: a name aidd added that is gone was taken out by
    the person, so it moves to `taken_out`; a taken-out name that is back was put back by hand, so it is the person's
    own and leaves the ledger, never to be removed by aidd."""
    added, taken_out = _ledger(root)
    present = {e for e in allow if isinstance(e, str)}
    return added & present, (taken_out | (added - present)) - present


def allows_own_tools(root: Path) -> bool | None:
    """Whether aidd's own MCP tools run with no prompt: `mcp.allow_own_tools` in the config, true when unset; None
    when the config exists and does not load. Then aidd allows no tool and takes none out, so a broken file never
    turns a prompt off, and a config an upgrade has yet to bring up to this aidd changes nothing."""
    if not regular_files.is_file_or_held(root, config.CONFIG_PATH):
        return True
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (config.ConfigError, OSError, ValueError):
        return None
    return cfg.get("mcp", "allow_own_tools", default=True) is not False


def claude_tool_names(prefix: str) -> list[str]:
    return [f"{prefix}{t}" for t in OWN_MCP_TOOLS]


def withdraw_claude_tools(root: Path, actions: list[str], prefix: str, *, write: bool = True, reason: str = OPTED_OUT, quiet: bool = False) -> None:
    """Take out of `permissions.allow` the names of `prefix` that aidd added (LEDGER), and only those, so a name a
    person listed or took out stays as they left it. `reason` says why. With `quiet`, nothing to take out says nothing."""
    path = root / CLAUDE_SETTINGS
    if (text := _text(root, CLAUDE_SETTINGS, actions)) is None or _ledger_refused(root, actions):
        return
    try:
        data = _json(text)
    except ValueError:
        data = None
    perms = data.get("permissions") if isinstance(data, dict) else None
    allow = perms.get("allow") if isinstance(perms, dict) else None
    added, taken_out = _reconcile(root, allow) if isinstance(allow, list) else (set(_added(root)), _ledger(root)[1])
    gone = [n for n in claude_tool_names(prefix) if n in added and isinstance(allow, list) and n in allow]
    if not gone or not isinstance(perms, dict) or not isinstance(allow, list):
        if quiet:
            return
        yours = [n for n in claude_tool_names(prefix) if isinstance(allow, list) and n in allow]
        why = f"{', '.join(yours)} stay allowed, since you listed them" if yours else "aidd's MCP tools ask"
        actions.append(f"kept     {repo_paths.shown(path)} ({why}; {OPTED_OUT}, and aidd allowed none there to take out)")
        return
    if write:
        perms["allow"] = [e for e in allow if e not in gone]
        if not perms["allow"]:
            del perms["allow"]
        if not files.write_or_skip(root, path, json.dumps(data, indent=2) + "\n", actions):
            return
        _write_ledger(root, added - set(gone), taken_out, actions)
    actions.append(f"{'removed ' if write else 'would remove'} the MCP tools aidd allowed from {repo_paths.shown(path)} ({reason})")


def allow_claude_tools(root: Path, actions: list[str], prefix: str, *, write: bool = True) -> None:
    """Let Claude Code run aidd's own MCP tools with no prompt: their names in the project's `permissions.allow`,
    keeping every other entry. Skipped, with the reason, when the settings file is not JSON aidd can read. Says what it
    would do and writes nothing unless `write`. With `mcp.allow_own_tools: false`, it takes aidd's names out instead."""
    path = root / CLAUDE_SETTINGS
    allow = allows_own_tools(root)
    if allow is None:
        actions.append(f"kept     {repo_paths.shown(path)} (the config does not load, so the MCP tools aidd allowed stay as they are)")
        return
    if not allow:
        withdraw_claude_tools(root, actions, prefix, write=write)
        return
    if (text := _text(root, CLAUDE_SETTINGS, actions)) is None or _ledger_refused(root, actions):
        return
    try:
        data = _json(text)
    except ValueError:
        actions.append(f"kept     {repo_paths.shown(path)} (not valid JSON; allow {', '.join(claude_tool_names(prefix))} by hand)")
        return
    perms = data.setdefault("permissions", {}) if isinstance(data, dict) else None
    if not isinstance(perms, dict) or not isinstance(perms.get("allow", []), list):
        actions.append(f"kept     {repo_paths.shown(path)} (its permissions are not the shape aidd reads; allow aidd's tools by hand)")
        return
    allow = perms.setdefault("allow", [])
    # A name aidd added once and the person took out stays out: their choice outlives every later init and upgrade.
    added, taken_out = _reconcile(root, allow)
    missing = [n for n in claude_tool_names(prefix) if n not in allow and n not in taken_out]
    if write and (added, taken_out) != _ledger(root):
        _write_ledger(root, added, taken_out, actions)
    if not missing:
        left_out = [n for n in claude_tool_names(prefix) if n not in allow]
        if left_out:
            actions.append(
                f"kept     {repo_paths.shown(path)} (you took {', '.join(left_out)} out of `permissions.allow`, so it still asks; "
                f"add it back there, or delete `{TAKEN_OUT_KEY}` from {LEDGER} and run `aidd init` again)"
            )
        else:
            actions.append(f"kept     {repo_paths.shown(path)} (aidd's MCP tools run with no prompt)")
        return
    if write:
        allow.extend(missing)
        if not files.write_or_skip(root, path, json.dumps(data, indent=2) + "\n", actions):
            return
        _write_ledger(root, added | set(missing), taken_out, actions)
    actions.append(f"{'updated ' if write else 'would update'} {repo_paths.shown(path)} (aidd's MCP tools {', '.join(OWN_MCP_TOOLS)} run with no prompt)")


def server_named(root: Path) -> bool | None:
    """Whether `.mcp.json` names a server called `aidd`; None when the file is not JSON aidd can read."""
    try:
        data = json.loads(regular_files.repository_text(root, MCP_FILE) or "") if regular_files.is_file_or_held(root, MCP_FILE) else {}
    except (OSError, ValueError):
        return None
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return isinstance(servers, dict) and "aidd" in servers


def withdraw_server_tools(root: Path, actions: list[str], *, write: bool = True) -> None:
    """When `.mcp.json` names no `aidd` server (the aidd plugin serves the tools now, under its own names), take out of
    `permissions.allow` the server's names (`mcp__aidd__*`) that aidd added: they approve tools no server has. A name a
    person listed stays."""
    if allows_own_tools(root) is None or server_named(root) is not False:
        return
    withdraw_claude_tools(root, actions, config.CLAUDE_TOOL_PREFIXES[0], write=write, reason="`.mcp.json` names no aidd server now", quiet=True)


def project_enables_plugin(root: Path) -> bool:
    """Whether the project's own `.claude/settings.json` enables the aidd plugin (`enabledPlugins`, set to true), the one
    file init and upgrade write. `config.plugin_enabled` reads every settings file Claude Code reads, for doctor."""
    try:
        settings = json.loads(regular_files.repository_text(root, CLAUDE_SETTINGS) or "") if regular_files.is_file_or_held(root, CLAUDE_SETTINGS) else {}
    except ValueError:
        return False
    plugins = settings.get("enabledPlugins") if isinstance(settings, dict) else None
    return isinstance(plugins, dict) and plugins.get(f"aidd@{config.MARKETPLACE}") is True


def refresh_mcp(root: Path, actions: list[str], *, yes: bool) -> None:
    """`aidd upgrade`: bring the MCP wiring an earlier `aidd init` wrote up to this aidd, where that wiring is there: the
    Codex block, when it differs, and Claude Code's allowing of aidd's tools, by the name the wiring gives them: the
    server `.mcp.json` names, or the plugin the project enables. It wires no server init did not. With
    `mcp.allow_own_tools: false`, it takes out the names aidd allowed instead."""
    allow = allows_own_tools(root)
    block = codex_block(bool(allow))
    cpath = root / CODEX_CONFIG
    text = _text(root, CODEX_CONFIG, actions)
    if text is not None and allow is not None and (span := _block(text)) is not None and text[span[0] : span[1]] != block:
        new = text[: span[0]] + block + text[span[1] :]
        try:
            tomllib.loads(new)  # a person's own `[mcp_servers.aidd.tools.*]` outside the block would repeat a table
        except tomllib.TOMLDecodeError as exc:
            actions.append(f"kept     {repo_paths.shown(cpath)} (the new aidd block would not parse with the rest: {exc}); update it by hand")
        else:
            why = "and its tools run with no prompt" if allow else f"and its tools ask: {OPTED_OUT}"
            if not yes or files.write_or_skip(root, cpath, new, actions):
                actions.append(f"{'updated ' if yes else 'would update'} {repo_paths.shown(cpath)} (the aidd MCP server, {why})")
    if (mcp_text := _text(root, MCP_FILE, actions)) is None:
        return
    try:
        mcp = _json(mcp_text)
    except ValueError:
        return
    served = isinstance(mcp, dict) and isinstance(mcp.get("mcpServers"), dict) and mcp["mcpServers"].get("aidd") == mcp_server()
    said: list[str] = []
    for prefix, wired in zip(config.CLAUDE_TOOL_PREFIXES, (served, project_enables_plugin(root)), strict=True):
        if wired:
            allow_claude_tools(root, said, prefix, write=yes)
    # Only once the plugin serves aidd: a server named `aidd` in Claude Code's local or user scope has the same names.
    if project_enables_plugin(root):
        withdraw_server_tools(root, said, write=yes)
    # A file skipped twice is said once. A "kept" line stays out unless the opt-out is on, where it says which names stayed.
    actions += list(dict.fromkeys(a for a in said if allow is False or not a.startswith("kept ")))


def _remove_claude_tools(root: Path, actions: list[str], verb: str, yes: bool) -> None:
    """Take out of Claude Code's `permissions.allow` only the names aidd added (LEDGER), then their keys in that file."""
    path, ledger = root / CLAUDE_SETTINGS, root / LEDGER
    if _ledger_refused(root, actions):
        return
    ours = set(_added(root))
    try:
        data = _json(_text(root, CLAUDE_SETTINGS, actions) or "")  # one aidd refuses is skipped, and named
    except ValueError:
        data = None
    perms = data.get("permissions") if isinstance(data, dict) else None
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if isinstance(perms, dict) and isinstance(allow, list) and ours & set(allow):
        perms["allow"] = [e for e in allow if e not in ours]
        if not perms["allow"]:
            del perms["allow"]
        if not yes or files.write_or_skip(root, path, json.dumps(data, indent=2) + "\n", actions):
            actions.append(f"{verb} aidd's MCP tools from {repo_paths.shown(path)} `permissions.allow`")
    if _holds_keys(root) and not files.refuses_link_on_the_way(root, ledger, actions):
        actions.append(f"{verb} the MCP tools aidd allowed from {LEDGER}")
        if yes:
            _write_ledger(root, set(), set(), [])


def _holds_keys(root: Path) -> bool:
    """Whether the ledger file still holds a list of MCP tool names, even one with no name of aidd's in it."""
    try:
        data = json.loads(regular_files.repository_text(root, LEDGER) or "")
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and any(k in data for k in (ALLOWED_KEY, TAKEN_OUT_KEY))


def user_launcher_path() -> Path:
    return Path(os.path.join(os.path.expanduser("~"), *USER_LAUNCHER))


def _on_default_path(directory: str) -> bool:
    """Whether a folder is on this interpreter's sys.path with `-I` (its site-packages), so `-m aidd` finds aidd there."""
    import site
    import sysconfig

    paths = {os.path.realpath(p) for p in (*site.getsitepackages(), sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"]) if p}
    return os.path.realpath(directory) in paths


def launcher() -> list[str]:
    """How the MCP server starts this aidd: this interpreter by its absolute path, isolated, with `-m aidd` when aidd is
    installed in its site-packages, else LOADER and the source it runs from."""
    src = str(Path(aidd.__file__).resolve().parent.parent)
    python = os.path.normpath(os.path.abspath(sys.executable))
    return [python, "-I", "-m", "aidd"] if _on_default_path(src) else [python, "-I", "-c", LOADER, src, "aidd"]


def installed(argv: list[str]) -> bool:
    """Whether `argv`, as `launcher()` gives it, starts an installed aidd: one in the interpreter's site-packages (uv, pipx, the
    one-line installer), the user's site-packages (`pip install --user`), the zipapp, or a Claude Code plugin's copy. A source
    tree on `sys.path`, an editable install included, is not, and neither is a path that is none of them."""
    if len(argv) <= 4:
        return True
    src = Path(argv[4])
    return src.is_file() or self_updating.in_plugin_cache(src.parent) or os.path.realpath(src) == os.path.realpath(site.getusersitepackages())


def launcher_problem(path: Path | None = None) -> str | None:
    """Why the launcher in the home folder starts no installed aidd, or None: it is not aidd's, or starts one. A launcher that
    names a Python or a source that is gone, or a source tree that is no install, is the problem. The step is `aidd init`."""
    path = path or user_launcher_path()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()  # aidd's own: the launcher in the person's home
        argv = processes.split_words(next(line for line in lines if line.startswith("exec "))[5:])
    except (OSError, StopIteration, ValueError):
        return None
    if argv[-1:] == ["$@"]:
        argv.pop()
    if len(argv) < 4 or argv[1] != "-I":
        return None  # not the form aidd writes: the person's own
    fix = f"install aidd with `{INSTALL_COMMAND}`, then run `aidd init` to write it again"
    if not (os.path.isabs(argv[0]) and os.path.exists(argv[0]) or shutil.which(argv[0])):
        return f"{USER_LAUNCHER_SHOWN} starts {argv[0]}, which no longer exists: {fix}"
    if len(argv) > 4 and not os.path.exists(argv[4]):
        return f"{USER_LAUNCHER_SHOWN} starts {argv[4]}, which no longer exists: {fix}"
    if not installed(argv):
        return f"{USER_LAUNCHER_SHOWN} starts {argv[4]}, a source checkout and no install, so every repository here runs that code: {fix}"
    return None


def launcher_script(argv: list[str]) -> str:
    return (
        "#!/bin/sh\n"
        "# Written by `aidd init`. The aidd MCP server of every repository on this machine starts here:\n"
        "# aidd, isolated (-I), from the Python it is installed with. `aidd doctor` checks it; init rewrites it.\n"
        f'exec {" ".join(shlex.quote(a) for a in argv)} "$@"\n'
    )


def install_user_launcher(root: Path, actions: list[str]) -> None:
    """Write this user's launcher for this aidd, unless it is that one already, aidd sits inside `root`, or this aidd is no install."""
    argv = launcher()
    if not installed(argv):  # a checkout is a branch's unfinished code, and the launcher is every repository's here
        path = user_launcher_path()
        what = (
            f"so it stays as it is; install aidd with `{INSTALL_COMMAND}` to update it"
            if path.is_file()
            else f"so it writes none; install aidd with `{INSTALL_COMMAND}`, then run `aidd init`"
        )
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (this aidd runs from a source checkout, {what})")
        return
    src = Path(argv[4] if len(argv) > 4 else aidd.__file__).resolve()
    if src.is_relative_to(Path(root).resolve()):
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (not rewritten: the aidd it would start sits inside this repository)")
        return
    path, text = user_launcher_path(), launcher_script(argv)
    owned = path.parent.parent  # ~/.aidd, the folder aidd owns in the home: no write leaves it through a link
    if link := regular_files.link_on_the_way(owned, path.relative_to(owned)):
        actions.append(
            f"warn     could not write {USER_LAUNCHER_SHOWN} (~/.aidd/{link} is a link, and aidd writes nothing through a link: remove the link, then run aidd again)"
        )
        return
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:  # aidd's own: the launcher in the person's home
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (it starts this aidd)")
        return
    if regular_files.writes_held():  # a plan: the launcher is outside the repository, so it is named and not written
        actions.append(f"wrote    {USER_LAUNCHER_SHOWN} (the aidd MCP server of every repository here starts {argv[0]} -I)")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}")
        with regular_files.open_for_write(tmp, text=True, root=owned) as out:
            out.write(text)
        tmp.chmod(0o755)
        os.replace(tmp, path)
    except OSError as exc:
        actions.append(f"warn     could not write {USER_LAUNCHER_SHOWN} ({exc.strerror or exc}); the aidd MCP server cannot start until it exists")
        return
    actions.append(f"wrote    {USER_LAUNCHER_SHOWN} (the aidd MCP server of every repository here starts {argv[0]} -I)")


def mcp_server() -> dict:
    """The .mcp.json entry that starts `aidd mcp`: the user launcher, except on Windows, where it is this interpreter."""
    if os.name != "nt":
        return {"command": MCP_LAUNCHER, "args": ["mcp"]}
    argv = launcher()
    return {"command": argv[0], "args": [*argv[1:], "mcp"]}


def install_claude_mcp(root: Path, actions: list[str]) -> None:
    """The `aidd` server in `.mcp.json`, keeping every other server."""
    path = root / MCP_FILE
    if (text := _text(root, MCP_FILE, actions)) is None:
        return
    try:
        data = _json(text)
    except ValueError:
        actions.append(f"kept     {repo_paths.shown(path)} (not valid JSON; add the aidd server by hand: `aidd mcp`)")
        return
    servers = data.setdefault("mcpServers", {})
    if servers.get("aidd") == mcp_server():
        actions.append(f"kept     {repo_paths.shown(path)} (the aidd MCP server is there)")
        return
    servers["aidd"] = mcp_server()
    if files.write_or_skip(root, path, json.dumps(data, indent=2) + "\n", actions):
        actions.append(f"updated  {repo_paths.shown(path)} (the aidd MCP server)")


def _block(text: str) -> tuple[int, int] | None:
    start = text.find(_BEGIN)
    end = text.find(_END, start) if start >= 0 else -1
    if start < 0 or end < 0:
        return None
    end += len(_END)
    return start, end + (1 if text[end : end + 1] == "\n" else 0)


def install_codex_mcp(root: Path, actions: list[str]) -> None:
    """Add the `aidd` MCP server to `.codex/config.toml`, keeping every other line. Skipped on Windows."""
    path = root / CODEX_CONFIG
    if os.name == "nt":
        actions.append(f"skipped  {CODEX_CONFIG} (Windows has no sh; add the server with `codex mcp add aidd -- aidd mcp`)")
        return
    if (text := _text(root, CODEX_CONFIG, actions)) is None:
        return
    allow = allows_own_tools(root)
    block = codex_block(bool(allow))
    if (span := _block(text)) is not None:
        if text[span[0] : span[1]] == block or allow is None:
            actions.append(f"kept     {repo_paths.shown(path)} (the aidd MCP server is there)")
            return
        new = text[: span[0]] + block + text[span[1] :]
        try:
            tomllib.loads(new)  # a person's own `[mcp_servers.aidd.tools.*]` outside the block would repeat a table
        except tomllib.TOMLDecodeError as exc:
            actions.append(f"kept     {repo_paths.shown(path)} (the new aidd block would not parse with the rest: {exc}); update it by hand")
            return
        if files.write_or_skip(root, path, new, actions):
            actions.append(f"updated  {repo_paths.shown(path)} (the aidd MCP server)")
        return
    try:
        servers = tomllib.loads(text).get("mcp_servers")
    except tomllib.TOMLDecodeError:
        actions.append(f"kept     {repo_paths.shown(path)} (not TOML that aidd can read; add the server with `codex mcp add aidd -- aidd mcp`)")
        return
    if isinstance(servers, dict) and "aidd" in servers:
        actions.append(f"kept     {repo_paths.shown(path)} (it already names an aidd MCP server)")
        return
    lead = "" if not text else "\n" if text.endswith("\n") else "\n\n"
    if files.write_or_skip(root, path, text + lead + block, actions):
        actions.append(f"{'updated ' if text else 'wrote   '} {repo_paths.shown(path)} (the aidd MCP server, which Codex starts in a trusted project)")


def remove_mcp(root: Path, actions: list[str], *, yes: bool) -> None:
    """Take aidd's MCP server out of `.mcp.json` and `.codex/config.toml` (`aidd uninstall`)."""
    verb = "removed" if yes else "would remove"
    path = root / MCP_FILE
    try:
        data = _json(_text(root, MCP_FILE, actions) or "")  # one aidd refuses is skipped, and named
    except ValueError:
        data = {}
    if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) and data["mcpServers"].get("aidd") == mcp_server():
        actions.append(f"{verb} the aidd MCP server from {repo_paths.shown(path)}")
        if yes:
            del data["mcpServers"]["aidd"]
            if not data["mcpServers"] and len(data) == 1:
                path.unlink()
            else:
                files.write_or_skip(root, path, json.dumps(data, indent=2) + "\n", actions)
    _remove_claude_tools(root, actions, verb, yes)
    cpath = root / CODEX_CONFIG
    text = _text(root, CODEX_CONFIG, actions) or ""
    if (span := _block(text)) is not None:
        actions.append(f"{verb} the aidd MCP server from {repo_paths.shown(cpath)}")
        if yes:
            rest = text[: span[0]].rstrip("\n") + ("\n" if text[: span[0]].strip() else "") + text[span[1] :]
            if rest.strip():
                files.write_or_skip(root, cpath, rest, actions)
            else:
                cpath.unlink()
