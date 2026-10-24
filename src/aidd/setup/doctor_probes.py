"""What `aidd doctor` runs and reads on this machine: the configured guard hook and MCP server, started once each,
Claude Code's wiring and managed settings, and a plugin loaded twice.
"""

from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from aidd import __version__, config
from aidd.setup import antigravity_wiring, claude_plugins, codex_wiring, grok_wiring, hook_wiring, hooks_file, opencode_wiring

RESTART_BEFORE_INIT = "A session started before `aidd init` must restart to load them."


def plugin_double_load(root: Path, label: str) -> list[tuple[str, str]]:
    """A warning for each aidd plugin enabled here whose part the repository files also carry: Claude Code loads both.
    A settings file it cannot read is a warning too, never a crash."""
    out: list[tuple[str, str]] = [
        ("warn", f"{label}: aidd cannot read {path}, so it cannot tell which plugins are enabled; check the file's permissions")
        for path in config.unreadable_claude_settings(root)
    ]
    on = config.plugins_enabled(root)
    skill, team = claude_plugins.claude_repo_files(root)
    fix = "Keep one: remove the repository files (`aidd uninstall` lists them), or turn the plugin off"
    if f"aidd@{config.MARKETPLACE}" in on and ".claude/skills/aidd" in skill:
        out.append(
            (
                "warn",
                f"{label}: the aidd plugin (aidd@{config.MARKETPLACE}) is enabled and {', '.join(skill)} also carry what the plugin carries (the skill, the guard hook, the MCP server), so it would load twice. {fix}",
            )
        )
    if f"aidd-team@{config.MARKETPLACE}" in on and team:
        out.append(
            (
                "warn",
                f"{label}: the aidd-team plugin (aidd-team@{config.MARKETPLACE}) is enabled and {', '.join(team)} also hold the roles, so they would load twice. {fix}",
            )
        )
    return out


# A harmless event for the guard hook: a Read, which the guard never decides on.
_PROBE_EVENT = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "README.md"}}
# The stdio probe a dual-era client sends first (https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio):
# `server/discover` at the 2026-07-28 revision, which `aidd mcp` answers with its name in the result's `_meta`.
_MCP_PROBE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "server/discover",
    "params": {
        "_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "aidd doctor", "version": __version__},
            "io.modelcontextprotocol/clientCapabilities": {},
        }
    },
}


def _run_probe(root: Path, words: list[str], env: dict[str, str], stdin: str, timeout_seconds: int) -> subprocess.CompletedProcess[str] | str:
    """Run a launcher once with `stdin`: the finished process, or why it could not run."""
    if not hook_wiring.resolves(words[0]):
        return f"{words[0]} is not found on PATH"
    try:
        return subprocess.run(
            words,
            input=stdin,
            env={**os.environ, **env},
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


def run_hook_probe(root: Path, command: str, timeout_seconds: int = 20, shell: str | None = None) -> str | None:
    """Run the configured guard hook command once with a harmless event; None when it runs, else why not."""
    parsed = hook_wiring.parse_hook(command, "pre-tool")
    if parsed is None:
        return "it does not parse as an aidd hook command"
    words, env = parsed
    why = hook_wiring.launch_shape(root, words, env, words[-2:]) or (
        None if hook_wiring.written_by_init(command, "pre-tool", parsed, shell) else hook_wiring.NOT_INIT_WRITTEN
    )
    if why:
        return f"not run: {why}"
    r = _run_probe(root, words, env, json.dumps({**_PROBE_EVENT, "cwd": str(root)}), timeout_seconds)
    if isinstance(r, str):
        return r
    if r.returncode != 0:
        last = (r.stderr or r.stdout).strip().splitlines()
        return f"exit {r.returncode}" + (f": {last[-1]}" if last else "")
    return None


def mcp_server_name(stdout: str) -> str | None:
    """The server name in the first line a server wrote back to `_MCP_PROBE`, or None when it is no such answer."""
    try:
        name = json.loads(stdout.splitlines()[0])["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"]
    except (IndexError, ValueError, KeyError, TypeError):
        return None
    return name if isinstance(name, str) else None


def run_mcp_probe(root: Path, server: dict, timeout_seconds: int = 20) -> str | None:
    """Start the configured MCP server and send `server/discover`; None when aidd answers, else why not."""
    command, args, env = server.get("command"), server.get("args") or [], server.get("env") or {}
    if not isinstance(command, str) or not isinstance(args, list) or not isinstance(env, dict):
        return "the entry is not a command with args"
    words, env = [hook_wiring.expand_launcher(command), *map(str, args)], {str(k): str(v) for k, v in env.items()}
    why = hook_wiring.launch_shape(root, words, env, ["mcp"]) or (None if hook_wiring.mcp_written_by_init(server) else hook_wiring.NOT_INIT_WRITTEN)
    if why:
        return f"not run: {why}"
    r = _run_probe(root, words, env, json.dumps(_MCP_PROBE) + "\n", timeout_seconds)
    if isinstance(r, str):
        return r
    if mcp_server_name(r.stdout) == "aidd":
        return None
    last = (r.stderr or r.stdout).strip().splitlines()
    return f"exit {r.returncode}, no MCP answer" + (f": {last[-1]}" if last else "")


def settings_setting_home(root: Path) -> list[Path]:
    """The Claude Code settings files whose `env` sets HOME, which Claude Code passes to the hooks and the MCP servers."""
    out = []
    for path in config.claude_settings_paths(root):
        try:
            env = json.loads(path.read_text(encoding="utf-8")).get("env")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(env, dict) and "HOME" in env:
            out.append(path)
    return out


def claude_wiring_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Claude Code's repository wiring: the guard hook and the MCP server are configured, their launchers resolve on
    this machine, and, with `execute` (`aidd doctor`), each one actually starts. A wiring that cannot run is a failure:
    the guard would silently not guard."""
    label = config.HARNESSES["claude-code"].label
    fix = (
        "`aidd init --claude-hooks` repairs it on this machine (it runs this Python by its absolute path, isolated"
        + ("" if os.name == "nt" else f", from {hook_wiring.USER_LAUNCHER_SHOWN}")
        + ")"
    )
    out: list[tuple[str, str]] = []
    settings = root / ".claude" / "settings.json"
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {}) if settings.is_file() else {}
    except (OSError, ValueError, AttributeError):  # an unreadable file: `plugin_double_load` warns about it
        hooks = {}
    pre = [
        (h["command"], h.get("shell"))
        for e in (hooks.get("PreToolUse") or [] if isinstance(hooks, dict) else [])
        if isinstance(e, dict)
        for h in e.get("hooks", []) or []
        if isinstance(h, dict) and hook_wiring.aidd_hook(h.get("command")) == "pre-tool"
    ]
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {}) if (root / ".mcp.json").is_file() else {}
    except (ValueError, AttributeError):
        servers = {}
    server = servers.get("aidd") if isinstance(servers, dict) else None
    plugin = config.plugin_enabled(root)
    by_plugin = ("ok", f"{label}: the aidd plugin is enabled; it carries the guard hook, the session hooks, and the MCP server")
    if not pre and not isinstance(server, dict):
        unwired = f"{label} is in use, but the guard hook and the MCP server are not wired: `aidd init --claude-hooks`, or install the aidd plugin"
        return [by_plugin if plugin else ("warn", unwired)]
    broken, missing = [], []
    for command, shell in pre:
        parsed = hook_wiring.parse_hook(command, "pre-tool")
        # A launcher doctor will not run (one inside the repository) is refused before PATH is asked: whether it
        # resolves differs by OS (Windows finds no file without an extension), and the answer is the same either way.
        refused = parsed and (
            hook_wiring.launch_shape(root, *parsed, parsed[0][-2:])
            or (None if hook_wiring.written_by_init(command, "pre-tool", parsed, shell) else hook_wiring.NOT_INIT_WRITTEN)
        )
        if execute and refused:
            broken.append(f"the guard hook `{command}` does not run (not run: {refused})")
        elif not hook_wiring.resolves(hook_wiring.command_program(command)):
            broken.append(f"the guard hook `{command}` names a program not found here")
        elif execute and (why := run_hook_probe(root, command, shell=shell)):
            broken.append(f"the guard hook `{command}` does not run ({why})")
    if not isinstance(server, dict):
        missing.append("the MCP server is not in .mcp.json")
    elif not hook_wiring.resolves(server.get("command")):
        broken.append(f"the MCP server's command {server.get('command')!r} is not found here")
    elif execute and (why := run_mcp_probe(root, server)):
        broken.append(f"the MCP server does not start ({why})")
    if not pre:
        missing.insert(0, "the guard hook is not wired")
    if broken:
        out.append(("fail", f"{label}: " + "; ".join(broken) + f"; {fix}"))
    through_home = any(hook_wiring.HOOK_LAUNCHER in c for c, _ in pre) or (isinstance(server, dict) and server.get("command") == hook_wiring.MCP_LAUNCHER)
    if through_home and (homes := settings_setting_home(root)):
        broken.append("HOME")
        out.append(
            (
                "fail",
                f"{label}: {', '.join(str(p) for p in homes)} sets HOME in its `env`. The aidd hooks and MCP server find "
                f"{hook_wiring.USER_LAUNCHER_SHOWN} through HOME, so they could start another program: remove HOME from that `env`",
            )
        )
    if missing and not plugin:
        out.append(("warn", f"{label}: " + "; ".join(missing) + ": `aidd init --claude-hooks`, or install the aidd plugin"))
    if not broken and not missing:
        out.append(("ok", f"{label}: the guard hook and the MCP server are wired" + (", and both start" if execute else "") + f". {RESTART_BEFORE_INIT}"))
    elif not broken and plugin:
        out.append(by_plugin)
    return out


def antigravity_wiring_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Google Antigravity's wiring: the `aidd` hook in `.agents/hooks.json`, each command as init writes it, the user
    launcher, and (with `execute`) the guard answering a harmless tool call with no opinion."""
    label, shown = config.HARNESSES["antigravity"].label, antigravity_wiring.HOOKS_FILE
    if os.name == "nt":
        cmd = "Antigravity runs hooks with cmd on Windows, and aidd's hook commands are sh"
        return [("warn", f"{label}: the aidd hooks are not wired here ({cmd}); the skill and AGENTS.md still guide the agent, and the gate decides")]
    spec = antigravity_wiring.configured(root)
    if spec is not None and spec.get("enabled") is False:
        return [("warn", f'{label}: the `aidd` hook in {shown} is turned off (`"enabled": false`), so the guard does not run')]
    wired = antigravity_wiring.wired(root)
    if not wired:
        return [("warn", f"{label} is in use, but the guard hook is not wired in {shown}: `{antigravity_wiring.SETUP}`")]
    missing = [event for event in antigravity_wiring.EVENTS if event not in wired]
    broken = [
        f"its {event} command is not the one `aidd init` writes"
        for event, sub in antigravity_wiring.EVENTS.items()
        if event in wired and wired[event] != antigravity_wiring.hook_command(sub)
    ]
    if "PreToolUse" in wired and antigravity_wiring.matcher(root) != antigravity_wiring.MATCHER:
        broken.append("its PreToolUse matcher is not the one `aidd init` writes, so some tool calls skip the guard")
    argv, why = hook_wiring.read_user_launcher()
    if argv is None:
        broken.append(why or f"{hook_wiring.USER_LAUNCHER_SHOWN} cannot run")
    elif execute and not broken and (why := _antigravity_probe(root)):
        broken.append(f"the guard hook does not run ({why})")
    fix = f"`{antigravity_wiring.SETUP}` repairs it on this machine"
    out: list[tuple[str, str]] = []
    if broken:
        out.append(("fail", f"{label}: " + "; ".join(broken) + f"; {fix}"))
    if missing:
        out.append(("warn", f"{label}: {shown} does not wire {', '.join(missing)}: `{antigravity_wiring.SETUP}` adds them"))
    if not broken and not missing:
        started = ", and the guard starts" if execute else ""
        events = ", ".join(antigravity_wiring.SESSION_EVENTS)
        out.append(("ok", f"{label}: the guard hook and the session hooks ({events}) are wired in {shown}{started}. {RESTART_BEFORE_INIT}"))
    return out


def grok_wiring_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Grok Build's wiring: `.grok/hooks/aidd.json` (`hooks_file_checks`), probed with a Grok shell command."""
    event = {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command", "toolInput": {"command": "python3 -m unittest"}}
    return hooks_file_checks(root, "grok-build", grok_wiring.FILE, {**event, "workspaceRoot": str(root)}, execute=execute)


def codex_wiring_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Codex's wiring: `.codex/hooks.json` (`hooks_file_checks`), probed with a Codex shell command."""
    event: dict = {"hook_event_name": "PreToolUse", "turn_id": "aidd-doctor", "session_id": "aidd-doctor"}
    event |= {"tool_name": "Bash", "tool_input": {"command": "python3 -m unittest"}}
    checks = hooks_file_checks(root, "codex", codex_wiring.FILE, event, execute=execute)
    if checks and checks[-1][0] == "ok":
        checks.append(("ok", "Codex: it runs a project's hooks once you trust the project and review its hooks in `/hooks`"))
    return checks


def hooks_file_checks(root: Path, key: str, wiring: hooks_file.HooksFile, probe: dict, *, execute: bool) -> list[tuple[str, str]]:
    """A hooks file's wiring: each command as init writes it, the user launcher, and (with `execute`) the guard
    answering `probe`, a harmless tool call, with no opinion. A missing launcher is broken even then."""
    label, shown = config.HARNESSES[key].label, wiring.path
    if os.name == "nt":
        cmd = "Windows has no sh hook, and aidd's hook commands are sh"
        return [("warn", f"{label}: the aidd hooks are not wired here ({cmd}); the skill and AGENTS.md still guide the agent, and the gate decides")]
    wired = wiring.wired(root)
    if not wired:
        return [("warn", f"{label} is in use, but the guard hook is not wired in {shown}: `{wiring.setup}`")]
    missing = [event for event in hooks_file.EVENTS if event not in wired]
    broken = [
        f"its {event} command is not the one `aidd init` writes"
        for event, sub in hooks_file.EVENTS.items()
        if event in wired and wired[event] != wiring.hook_command(sub)
    ]
    argv, why = hook_wiring.read_user_launcher()
    if argv is None:
        broken.append(why or f"{hook_wiring.USER_LAUNCHER_SHOWN} cannot run")
    elif execute and not broken and (why := _guard_probe(root, {**probe, "cwd": str(root)})):
        broken.append(f"the guard hook does not run ({why})")
    fix = f"`{wiring.setup}` repairs it on this machine"
    out: list[tuple[str, str]] = []
    if broken:
        out.append(("fail", f"{label}: " + "; ".join(broken) + f"; {fix}"))
    if missing:
        out.append(("warn", f"{label}: {shown} does not wire {', '.join(missing)}: `{wiring.setup}` adds them"))
    if not broken and not missing:
        started = ", and the guard starts" if execute else ""
        events = ", ".join(hook_wiring.SESSION_EVENTS)
        out.append(("ok", f"{label}: the guard hook and the session hooks ({events}) are wired in {shown}{started}. {RESTART_BEFORE_INIT}"))
    return out


def opencode_wiring_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """OpenCode's guard: `.opencode/plugins/aidd.js` as init writes it, the user launcher, and (with `execute`) the
    guard answering a harmless OpenCode shell command with no opinion."""
    label, shown, tui = config.HARNESSES["opencode"].label, opencode_wiring.PLUGIN_FILE, opencode_wiring.TUI_DIR
    state = opencode_wiring.state(root)
    if state == "missing":
        return [("warn", f"{label} is in use, but the guard plugin {shown} and the terminal half {tui}/ are not there: `{opencode_wiring.SETUP}`")]
    broken = [f"{shown} or {tui}/ is an older aidd's"] if state == "stale" else []
    argv, why = hook_wiring.read_user_launcher()
    if argv is None:
        broken.append(why or f"{hook_wiring.USER_LAUNCHER_SHOWN} cannot run")
    elif execute and not broken:
        probe = {"harness": "opencode", "hook_event_name": "PreToolUse", "tool": "shell", "input": {"command": "python3 -m unittest"}, "cwd": str(root)}
        if why := _guard_probe(root, probe):
            broken.append(f"the guard does not run ({why})")
    if broken:
        fix = (
            "`aidd upgrade --yes` brings it up to date"
            if broken == [f"{shown} or {tui}/ is an older aidd's"]
            else f"`{opencode_wiring.SETUP}` repairs it on this machine"
        )
        return [("fail", f"{label}: " + "; ".join(broken) + f"; {fix} (aidd writes its own files, so an agent may run it)")]
    started = ", and the guard starts" if execute else ""
    return [
        ("ok", f"{label}: the guard plugin is in {shown}, and the terminal half in {tui}/{started}. Restart OpenCode after `aidd init`, so it loads the plugin")
    ]


def _guard_probe(root: Path, event: dict, timeout_seconds: int = 20) -> str | None:
    """Run the guard through the user launcher once with `event`; None when it writes nothing (no opinion)."""
    r = _run_probe(root, [hook_wiring.user_launcher_file(), "hook", "pre-tool"], {}, json.dumps(event), timeout_seconds)
    if isinstance(r, str):
        return r
    if r.returncode != 0 or r.stdout.strip():
        last = (r.stderr or r.stdout).strip().splitlines()
        return f"exit {r.returncode}" + (f": {last[-1]}" if last else "")
    return None


def _antigravity_probe(root: Path, timeout_seconds: int = 20) -> str | None:
    """Run the guard through the user launcher once, with an Antigravity file read in the workspace; None when it lets
    the read through (`allow`)."""
    read = {"name": "view_file", "args": {"AbsolutePath": str(root / "README.md")}}
    event = {"conversationId": "aidd-doctor", "workspacePaths": [str(root)], "toolCall": read}
    r = _run_probe(root, [hook_wiring.user_launcher_file(), "hook", "pre-tool"], {}, json.dumps(event), timeout_seconds)
    if isinstance(r, str):
        return r
    try:
        answer = json.loads(r.stdout)
    except ValueError:
        answer = None
    if r.returncode != 0 or answer != {"decision": "allow"}:
        last = (r.stderr or r.stdout).strip().splitlines()
        return f"exit {r.returncode}" + (f": {last[-1]}" if last else "")
    return None


def tree_diff(a: Path, b: Path) -> list[str]:
    cmp = filecmp.dircmp(a, b, ignore=filecmp.DEFAULT_IGNORES + [".DS_Store", "Thumbs.db"])
    out = [f"only in bundled: {x}" for x in cmp.left_only] + [f"only in repo: {x}" for x in cmp.right_only]
    out += [f"differs: {x}" for x in cmp.diff_files]
    for sub in cmp.common_dirs:
        out += [f"{sub}/{x}" for x in tree_diff(a / sub, b / sub)]
    return out


# Where Claude Code reads an organization's managed settings, from its "Deploy managed settings" page (checked
# 2026-09-28): the system directory holding managed-settings.json and managed-settings.d/, per OS. The macOS MDM
# profile lands in the managed preferences domain com.anthropic.claudecode, which macOS stores under
# /Library/Managed Preferences/ (an OS convention, not a path the page names). Windows also reads the HKLM
# registry value, and server-managed settings from the claude.ai console leave a cache in ~/.claude/.
MANAGED_SETTINGS_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "linux": "/etc/claude-code",
    "win32": r"C:\Program Files\ClaudeCode",
}
MANAGED_PLIST = "/Library/Managed Preferences/com.anthropic.claudecode.plist"
SERVER_MANAGED_CACHE = ".claude/remote-settings.json"
MANAGED_SETTINGS_TEMPLATE = "templates/claude/managed-settings.json"


def managed_settings_sources(platform: str | None = None, home: Path | None = None) -> list[str]:
    """The Claude Code managed settings this machine carries: a file, a drop-in, an MDM profile, the HKLM
    registry value, or the server-managed cache. Presence only: `/status` in Claude Code says which one applies."""
    platform = platform or sys.platform
    home = home if home is not None else Path.home()
    found: list[str] = []
    key = "linux" if platform.startswith("linux") else platform
    if base := MANAGED_SETTINGS_DIRS.get(key):
        d = Path(base)
        if (d / "managed-settings.json").is_file():
            found.append(str(d / "managed-settings.json"))
        if (d / "managed-settings.d").is_dir() and any((d / "managed-settings.d").glob("*.json")):
            found.append(str(d / "managed-settings.d"))
    if key == "darwin" and Path(MANAGED_PLIST).is_file():
        found.append(MANAGED_PLIST)
    if key == "win32":
        try:
            import winreg  # type: ignore[import-not-found,unused-ignore]

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\ClaudeCode") as k:  # type: ignore[attr-defined,unused-ignore]
                if winreg.QueryValueEx(k, "Settings")[0]:  # type: ignore[attr-defined,unused-ignore]
                    found.append(r"HKLM\SOFTWARE\Policies\ClaudeCode\Settings")
        except (ImportError, OSError):
            pass
    if (home / SERVER_MANAGED_CACHE).is_file():
        found.append(str(home / SERVER_MANAGED_CACHE))
    return found


def path_aidd_problem() -> str | None:
    """Why the `aidd` an agent's shell finds on PATH may answer otherwise than the aidd the hooks run (the user
    launcher): two installs, each from its own Python. None when they share one, or either cannot be read."""
    argv, _ = hook_wiring.read_user_launcher()
    found = shutil.which("aidd")
    if not argv or not found or os.name == "nt":
        return None
    try:
        first = Path(found).read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    words = first[2:].split()
    shell_python = words[0] if words else ""
    if not shell_python or Path(shell_python).name in ("sh", "bash", "env"):
        return None  # a wrapper script: its Python is not on its first line
    # Each install's own folder: two venvs' Pythons resolve to one base interpreter, but their bin folders differ.
    try:
        same = os.path.samefile(os.path.dirname(shell_python), os.path.dirname(argv[0]))
    except OSError:
        return None
    if same:
        return None
    return (
        f"the `aidd` on PATH ({found}) runs from {shell_python}, but the aidd hooks run {argv[0]} "
        f"({hook_wiring.USER_LAUNCHER_SHOWN}): an agent's shell and the guard may be two releases. Remove one install, "
        "then run `aidd init` from the one you keep, which points the launcher at it"
    )
