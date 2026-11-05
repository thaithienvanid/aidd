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
import sys
import tomllib
from pathlib import Path

import aidd
from aidd import config
from aidd.kernel import repo_paths

USER_LAUNCHER = (".aidd", "bin", "aidd")
USER_LAUNCHER_SHOWN = "~/" + "/".join(USER_LAUNCHER)
SH_LAUNCHER = '"$HOME"/' + "/".join(USER_LAUNCHER)  # sh expands $HOME
MCP_LAUNCHER = "${HOME}/" + "/".join(USER_LAUNCHER)  # Claude Code expands ${HOME} in .mcp.json
LOADER = "import sys; sys.version_info < (3, 11) and sys.exit(3); sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = sys.argv.pop(1); from aidd.cli import main; sys.exit(main())"
MCP_FILE = ".mcp.json"
CODEX_CONFIG = ".codex/config.toml"
_BEGIN = "# >>> aidd: the aidd MCP server. `aidd init` writes this block, and `aidd uninstall` removes it."
_END = "# <<< aidd"
# aidd's own MCP tools, which `aidd init` lets run with no prompt (R327): `risk`, `status`, `validate`, and `recall` only
# read (`recall` refreshes its cache in `.git/aidd/`), and `record` writes only `.git/aidd/records/` and refuses a secret's
# shape; the ones that read fetch a parent config
# the repository's `extends` names by URL, as the CLI does. A headless run can approve nothing, so without this it
# records nothing. `records push`, which sends records away, is a CLI command, an ask of its own. A config with
# `mcp: {approve_own_tools: false}` keeps them asking: init and upgrade write no approval and take out the ones aidd wrote.
OWN_MCP_TOOLS = ("risk", "status", "validate", "recall", "record")  # written to the allow lists in this order
CLAUDE_TOOL_PREFIXES = ("mcp__aidd__", "mcp__plugin_aidd_aidd__")  # the server `.mcp.json` names, and the plugin's
_CODEX_TOOLS = "".join(f'[mcp_servers.aidd.tools.{t}]\napproval_mode = "approve"\n' for t in OWN_MCP_TOOLS)


def codex_block(approve: bool) -> str:
    """aidd's block in `.codex/config.toml`: the server, and its tools approved by name unless `approve` is false."""
    return f'{_BEGIN}\n[mcp_servers.aidd]\ncommand = "sh"\nargs = ["-c", {json.dumps(f"exec {SH_LAUNCHER} mcp")}]\n{_CODEX_TOOLS if approve else ""}{_END}\n'


CODEX_BLOCK = codex_block(True)
CLAUDE_SETTINGS = ".claude/settings.json"
# The tool names aidd itself added to Claude Code's `permissions.allow`, so uninstall takes out only those, never a name a
# person listed first.
APPROVALS_FILE = ".aidd/mcp-approvals.json"
OPTED_OUT = "`mcp.approve_own_tools` is false"


def _ledger(root: Path) -> tuple[set[str], set[str]]:
    """(the names aidd added to Claude Code's `permissions.allow` and that are still aidd's; the names aidd added that
    the person took out, which stay out). A name the person puts back by hand is theirs, so it is on neither list."""
    try:
        data = json.loads((root / APPROVALS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), set()

    # Only aidd's own tool names count, so a crafted ledger can never take out a person's own entry.
    own = {n for prefix in CLAUDE_TOOL_PREFIXES for n in claude_tool_names(prefix)}

    def names(key: str) -> set[str]:
        value = data.get(key) if isinstance(data, dict) else None
        return {str(n) for n in value} & own if isinstance(value, list) else set()

    return names("claude-code"), names("taken_out")


def _added(root: Path) -> list[str]:
    return sorted(_ledger(root)[0])


def _write_ledger(root: Path, added: set[str], taken_out: set[str] | None = None) -> None:
    """Record both lists; with both empty, the ledger goes."""
    ledger, taken_out = root / APPROVALS_FILE, taken_out if taken_out is not None else _ledger(root)[1]
    if not added and not taken_out:
        ledger.unlink(missing_ok=True)
        return
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({"claude-code": sorted(added), "taken_out": sorted(taken_out)}, indent=2) + "\n", encoding="utf-8")


def _reconcile(root: Path, allow: list) -> tuple[set[str], set[str]]:
    """Bring the ledger in line with what `permissions.allow` holds now: a name aidd added that is gone was taken out by
    the person, so it moves to `taken_out`; a taken-out name that is back was put back by hand, so it is the person's
    own and leaves the ledger, never to be removed by aidd."""
    added, taken_out = _ledger(root)
    present = {e for e in allow if isinstance(e, str)}
    return added & present, (taken_out | (added - present)) - present


def approves_own_tools(root: Path) -> bool | None:
    """Whether aidd's own MCP tools run with no prompt: `mcp.approve_own_tools` in the config, true when unset; None
    when the config exists and does not load. Then aidd adds no approval and takes none out, so a broken file never
    turns a prompt off, and a config an upgrade has yet to bring up to this aidd changes nothing."""
    if not (root / config.CONFIG_PATH).is_file():
        return True
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (config.ConfigError, OSError, ValueError):
        return None
    return cfg.get("mcp", "approve_own_tools", default=True) is not False


def claude_tool_names(prefix: str) -> list[str]:
    return [f"{prefix}{t}" for t in OWN_MCP_TOOLS]


def withdraw_claude_tools(root: Path, actions: list[str], prefix: str, *, write: bool = True, reason: str = OPTED_OUT, quiet: bool = False) -> None:
    """Take out of `permissions.allow` the names of `prefix` that aidd added (APPROVALS_FILE), and only those, so a name a
    person listed or took out stays as they left it. `reason` says why. With `quiet`, nothing to take out says nothing."""
    path = root / CLAUDE_SETTINGS
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
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
        actions.append(f"kept     {repo_paths.shown(path)} ({why}; {OPTED_OUT}, and aidd wrote no approval there to take out)")
        return
    actions.append(f"{'removed ' if write else 'would remove'} aidd's MCP tool approvals from {repo_paths.shown(path)} ({reason})")
    if write:
        perms["allow"] = [e for e in allow if e not in gone]
        if not perms["allow"]:
            del perms["allow"]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        _write_ledger(root, added - set(gone), taken_out)


def allow_claude_tools(root: Path, actions: list[str], prefix: str, *, write: bool = True) -> None:
    """Let Claude Code run aidd's own MCP tools with no prompt: their names in the project's `permissions.allow`,
    keeping every other entry. Skipped, with the reason, when the settings file is not JSON aidd can read. Says what it
    would do and writes nothing unless `write`. With `mcp.approve_own_tools: false`, it takes aidd's names out instead."""
    path = root / CLAUDE_SETTINGS
    approve = approves_own_tools(root)
    if approve is None:
        actions.append(f"kept     {repo_paths.shown(path)} (the config does not load, so aidd's MCP tool approvals stay as they are)")
        return
    if not approve:
        withdraw_claude_tools(root, actions, prefix, write=write)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
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
        _write_ledger(root, added, taken_out)
    if not missing:
        left_out = [n for n in claude_tool_names(prefix) if n not in allow]
        if left_out:
            actions.append(
                f"kept     {repo_paths.shown(path)} (you took {', '.join(left_out)} out of `permissions.allow`, so it still asks; "
                f"add it back there, or delete {APPROVALS_FILE} and run `aidd init` again)"
            )
        else:
            actions.append(f"kept     {repo_paths.shown(path)} (aidd's MCP tools run with no prompt)")
        return
    actions.append(f"{'updated ' if write else 'would update'} {repo_paths.shown(path)} (aidd's MCP tools {', '.join(OWN_MCP_TOOLS)} run with no prompt)")
    if write:
        allow.extend(missing)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        _write_ledger(root, added | set(missing), taken_out)


def server_named(root: Path) -> bool | None:
    """Whether `.mcp.json` names a server called `aidd`; None when the file is not JSON aidd can read."""
    try:
        data = json.loads((root / MCP_FILE).read_text(encoding="utf-8")) if (root / MCP_FILE).is_file() else {}
    except (OSError, ValueError):
        return None
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return isinstance(servers, dict) and "aidd" in servers


def withdraw_server_tools(root: Path, actions: list[str], *, write: bool = True) -> None:
    """When `.mcp.json` names no `aidd` server (the aidd plugin serves the tools now, under its own names), take out of
    `permissions.allow` the server's names (`mcp__aidd__*`) that aidd added: they approve tools no server has. A name a
    person listed stays."""
    if approves_own_tools(root) is None or server_named(root) is not False:
        return
    withdraw_claude_tools(root, actions, CLAUDE_TOOL_PREFIXES[0], write=write, reason="`.mcp.json` names no aidd server now", quiet=True)


def project_enables_plugin(root: Path) -> bool:
    """Whether the project's own `.claude/settings.json` enables the aidd plugin (`enabledPlugins`, set to true), the one
    file init and upgrade write. `config.plugin_enabled` reads every settings file Claude Code reads, for doctor."""
    try:
        settings = json.loads((root / CLAUDE_SETTINGS).read_text(encoding="utf-8")) if (root / CLAUDE_SETTINGS).is_file() else {}
    except ValueError:
        return False
    plugins = settings.get("enabledPlugins") if isinstance(settings, dict) else None
    return isinstance(plugins, dict) and plugins.get(f"aidd@{config.MARKETPLACE}") is True


def refresh_mcp(root: Path, actions: list[str], *, yes: bool) -> None:
    """`aidd upgrade`: bring the MCP wiring an earlier `aidd init` wrote up to this aidd, where that wiring is there: the
    Codex block, when it differs, and Claude Code's approval of aidd's tools, by the name the wiring gives them: the
    server `.mcp.json` names, or the plugin the project enables. It wires no server init did not. With
    `mcp.approve_own_tools: false`, it takes out the approvals aidd wrote instead."""
    approve = approves_own_tools(root)
    block = codex_block(bool(approve))
    cpath = root / CODEX_CONFIG
    text = cpath.read_text(encoding="utf-8", errors="replace") if cpath.is_file() else ""
    if approve is not None and (span := _block(text)) is not None and text[span[0] : span[1]] != block:
        new = text[: span[0]] + block + text[span[1] :]
        try:
            tomllib.loads(new)  # a person's own `[mcp_servers.aidd.tools.*]` outside the block would repeat a table
        except tomllib.TOMLDecodeError as exc:
            actions.append(f"kept     {repo_paths.shown(cpath)} (the new aidd block would not parse with the rest: {exc}); update it by hand")
        else:
            why = "and its tools run with no prompt" if approve else f"and its tools ask: {OPTED_OUT}"
            actions.append(f"{'updated ' if yes else 'would update'} {repo_paths.shown(cpath)} (the aidd MCP server, {why})")
            if yes:
                cpath.write_text(new, encoding="utf-8")
    try:
        mcp = json.loads((root / MCP_FILE).read_text(encoding="utf-8")) if (root / MCP_FILE).is_file() else {}
    except (OSError, ValueError):
        return
    served = isinstance(mcp, dict) and isinstance(mcp.get("mcpServers"), dict) and mcp["mcpServers"].get("aidd") == mcp_server()
    said: list[str] = []
    for prefix, wired in zip(CLAUDE_TOOL_PREFIXES, (served, project_enables_plugin(root)), strict=True):
        if wired:
            allow_claude_tools(root, said, prefix, write=yes)
    # Only once the plugin serves aidd: a server named `aidd` in Claude Code's local or user scope has the same names.
    if project_enables_plugin(root):
        withdraw_server_tools(root, said, write=yes)
    actions += [a for a in said if not a.startswith("kept ")]


def _remove_claude_tools(root: Path, actions: list[str], verb: str, yes: bool) -> None:
    """Take out of Claude Code's `permissions.allow` only the names aidd added (APPROVALS_FILE), then that file."""
    path, ledger = root / CLAUDE_SETTINGS, root / APPROVALS_FILE
    ours = set(_added(root))
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        data = None
    perms = data.get("permissions") if isinstance(data, dict) else None
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if isinstance(perms, dict) and isinstance(allow, list) and ours & set(allow):
        actions.append(f"{verb} aidd's MCP tools from {repo_paths.shown(path)} `permissions.allow`")
        if yes:
            perms["allow"] = [e for e in allow if e not in ours]
            if not perms["allow"]:
                del perms["allow"]
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if ledger.is_file():
        actions.append(f"{verb} {APPROVALS_FILE}")
        if yes:
            ledger.unlink()


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


def launcher_script(argv: list[str]) -> str:
    return (
        "#!/bin/sh\n"
        "# Written by `aidd init`. The aidd MCP server of every repository on this machine starts here:\n"
        "# aidd, isolated (-I), from the Python it is installed with. `aidd doctor` checks it; init rewrites it.\n"
        f'exec {" ".join(shlex.quote(a) for a in argv)} "$@"\n'
    )


def install_user_launcher(root: Path, actions: list[str]) -> None:
    """Write this user's launcher for this aidd, unless it is that one already, or aidd sits inside `root`."""
    argv = launcher()
    src = Path(argv[4] if len(argv) > 4 else aidd.__file__).resolve()
    if src.is_relative_to(Path(root).resolve()):
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (not rewritten: the aidd it would start sits inside this repository)")
        return
    path, text = user_launcher_path(), launcher_script(argv)
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (it starts this aidd)")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
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
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        actions.append(f"kept     {repo_paths.shown(path)} (not valid JSON; add the aidd server by hand: `aidd mcp`)")
        return
    servers = data.setdefault("mcpServers", {})
    if servers.get("aidd") == mcp_server():
        actions.append(f"kept     {repo_paths.shown(path)} (the aidd MCP server is there)")
        return
    servers["aidd"] = mcp_server()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
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
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    approve = approves_own_tools(root)
    block = codex_block(bool(approve))
    if (span := _block(text)) is not None:
        if text[span[0] : span[1]] == block or approve is None:
            actions.append(f"kept     {repo_paths.shown(path)} (the aidd MCP server is there)")
            return
        new = text[: span[0]] + block + text[span[1] :]
        try:
            tomllib.loads(new)  # a person's own `[mcp_servers.aidd.tools.*]` outside the block would repeat a table
        except tomllib.TOMLDecodeError as exc:
            actions.append(f"kept     {repo_paths.shown(path)} (the new aidd block would not parse with the rest: {exc}); update it by hand")
            return
        path.write_text(new, encoding="utf-8")
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
    path.parent.mkdir(parents=True, exist_ok=True)
    lead = "" if not text else "\n" if text.endswith("\n") else "\n\n"
    path.write_text(text + lead + block, encoding="utf-8")
    actions.append(f"{'updated ' if text else 'wrote   '} {repo_paths.shown(path)} (the aidd MCP server, which Codex starts in a trusted project)")


def remove_mcp(root: Path, actions: list[str], *, yes: bool) -> None:
    """Take aidd's MCP server out of `.mcp.json` and `.codex/config.toml` (`aidd uninstall`)."""
    verb = "removed" if yes else "would remove"
    path = root / MCP_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        data = {}
    if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) and data["mcpServers"].get("aidd") == mcp_server():
        actions.append(f"{verb} the aidd MCP server from {repo_paths.shown(path)}")
        if yes:
            del data["mcpServers"]["aidd"]
            if not data["mcpServers"] and len(data) == 1:
                path.unlink()
            else:
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _remove_claude_tools(root, actions, verb, yes)
    cpath = root / CODEX_CONFIG
    text = cpath.read_text(encoding="utf-8", errors="replace") if cpath.is_file() else ""
    if (span := _block(text)) is not None:
        actions.append(f"{verb} the aidd MCP server from {repo_paths.shown(cpath)}")
        if yes:
            rest = text[: span[0]].rstrip("\n") + ("\n" if text[: span[0]].strip() else "") + text[span[1] :]
            if rest.strip():
                cpath.write_text(rest, encoding="utf-8")
            else:
                cpath.unlink()
