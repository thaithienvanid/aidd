"""Google Antigravity's hooks and MCP server: the guard and the session hooks in `.agents/hooks.json`, and the `aidd`
MCP server as a workspace plugin in `.agents/plugins/aidd/`, written, checked, and removed.

Antigravity's file maps a hook name to its events (https://antigravity.google/docs/hooks, and the copy `agy` ships):
`PreToolUse` takes `{matcher, hooks}` groups, and `SessionStart`, `PreInvocation`, and `Stop` take handler objects
directly. aidd writes one hook name, `aidd`, and never touches another. Each command runs through `sh -c` from the
`.agents/` folder; the hooks read the workspace from the event. A hook must answer with a JSON object: a guard that
cannot run answers `{"decision": "ask"}` (Antigravity asks the person; it denies an empty decision), or a deny where
the project fails closed (`hook_wiring.fail_closed_test`). Antigravity reads MCP servers from the user's config or a
plugin (`.agents/plugins/<name>/mcp_config.json`), so init writes the `aidd` plugin there.
On Windows Antigravity runs a hook with `cmd /c`, and these commands are sh, so init leaves the files alone there.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from aidd.kernel import repo_paths
from aidd.setup import guard_message, hook_wiring

HOOKS_FILE = ".agents/hooks.json"
HOOK_NAME = "aidd"
PLUGIN_DIR = ".agents/plugins/aidd"
PLUGIN_MANIFEST = f"{PLUGIN_DIR}/plugin.json"
PLUGIN_MCP_FILE = f"{PLUGIN_DIR}/mcp_config.json"
PLUGIN_SPEC = {"name": HOOK_NAME}
MCP_SPEC = {"mcpServers": {HOOK_NAME: {"command": "sh", "args": ["-c", "exec ~/.aidd/bin/aidd mcp"]}}}
# Every tool call, so a tool aidd does not know still reaches the guard (Antigravity's matcher is a Go regular
# expression, which cannot say "all but the reads"). The guard answers each: dialects.Antigravity.no_opinion.
MATCHER = "*"
SESSION_EVENTS = {"SessionStart": "session-start", "PreInvocation": "prompt-submit", "Stop": "stop"}
EVENTS = {"PreToolUse": "pre-tool", **SESSION_EVENTS}
GUARD_TIMEOUT_SECONDS = 20
SETUP = "aidd init --harness antigravity"
_NO_OPINION = '{"decision":"ask"}'
_FAIL_CLOSED_DENY = '{"decision":"deny","reason":"' + guard_message.guard_missing_message(SETUP) + '"}'


def hook_command(sub: str) -> str:
    """The `.agents/hooks.json` command for one aidd hook: the user launcher, and a JSON answer when it cannot run."""
    if sub == "pre-tool":
        fallback = (
            f'echo "{guard_message.guard_missing_message(SETUP)}" >&2; '
            f"if {hook_wiring.fail_closed_test('../.aidd/config.yaml')}; then echo '{_FAIL_CLOSED_DENY}'; else echo '{_NO_OPINION}'; fi"
        )
        return f"{hook_wiring.HOOK_LAUNCHER} hook pre-tool || {{ {fallback}; }}"
    return f"{hook_wiring.HOOK_LAUNCHER} hook {sub} || echo '{{}}'"


def _handler(sub: str) -> dict:
    timeout = GUARD_TIMEOUT_SECONDS if sub == "pre-tool" else hook_wiring.SESSION_HOOK_TIMEOUT_SECONDS
    return {"type": "command", "command": hook_command(sub), "timeout": timeout}


def hook_spec() -> dict:
    """The `aidd` entry init writes in `.agents/hooks.json`."""
    spec: dict = {"PreToolUse": [{"matcher": MATCHER, "hooks": [_handler("pre-tool")]}]}
    for event, sub in SESSION_EVENTS.items():
        spec[event] = [_handler(sub)]
    return spec


def _read(path: Path) -> dict | None:
    """The hooks file as a JSON object; {} when there is none, None when it is not one."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def install_mcp(root: Path, actions: list[str]) -> None:
    """Write the `aidd` workspace plugin in `.agents/plugins/aidd/`, which registers the `aidd` MCP server."""
    manifest = root / PLUGIN_MANIFEST
    mcp = root / PLUGIN_MCP_FILE
    if _read(manifest) == PLUGIN_SPEC and _read(mcp) == MCP_SPEC:
        actions.append(f"kept     {repo_paths.shown(mcp)} (the aidd MCP server is there)")
        return
    verb = "updated " if mcp.exists() or manifest.exists() else "wrote   "
    mcp.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(PLUGIN_SPEC, indent=2) + "\n", encoding="utf-8")
    mcp.write_text(json.dumps(MCP_SPEC, indent=2) + "\n", encoding="utf-8")
    actions.append(f"{verb} {repo_paths.shown(mcp)} (the aidd MCP server, in `.agents/plugins/aidd/`)")


def mcp_configured(root: Path) -> bool:
    """Whether `.agents/plugins/aidd/` holds the `aidd` plugin manifest and MCP server init writes."""
    return _read(root / PLUGIN_MANIFEST) == PLUGIN_SPEC and _read(root / PLUGIN_MCP_FILE) == MCP_SPEC


def install(root: Path, actions: list[str]) -> None:
    """Write the `aidd` hook in `.agents/hooks.json`, the `aidd` MCP plugin, and this user's launcher."""
    path = root / HOOKS_FILE
    if os.name == "nt":
        actions.append(f"skipped  {HOOKS_FILE} (Antigravity runs hooks with cmd on Windows, and aidd's hook commands are sh)")
        return
    hook_wiring.install_user_launcher(root, hook_wiring.launcher(), actions)
    data = _read(path)
    if data is None:
        actions.append(f"warn     {repo_paths.shown(path)} is not a JSON object; add the `{HOOK_NAME}` hook by hand (`aidd doctor` shows it)")
    elif data.get(HOOK_NAME) == hook_spec():
        actions.append(f"kept     {repo_paths.shown(path)} (the aidd hooks are there)")
    else:
        verb = "updated " if path.exists() else "wrote   "
        data[HOOK_NAME] = hook_spec()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        actions.append(f"{verb} {repo_paths.shown(path)} (the guard on every tool call, and {', '.join(SESSION_EVENTS)})")
    install_mcp(root, actions)


def configured(root: Path) -> dict | None:
    """The `aidd` entry in `.agents/hooks.json` as it stands, or None when there is none."""
    spec = (_read(root / HOOKS_FILE) or {}).get(HOOK_NAME)
    return spec if isinstance(spec, dict) else None


def matcher(root: Path) -> str | None:
    """The `aidd` hook's PreToolUse matcher in `.agents/hooks.json`, or None when it has none."""
    spec = configured(root) or {}
    groups = [g for g in (spec.get("PreToolUse") or []) if isinstance(g, dict)] if isinstance(spec.get("PreToolUse"), list) else []
    return next((g["matcher"] for g in groups if isinstance(g.get("matcher"), str)), None)


def wired(root: Path) -> dict[str, str]:
    """Each event the `aidd` hook in `.agents/hooks.json` wires, with its command, whatever the commands are; none when
    the hook is turned off (`"enabled": false`)."""
    spec = configured(root)
    if spec is None or spec.get("enabled") is False:
        return {}
    out: dict[str, str] = {}
    for event, sub in EVENTS.items():
        entries: list = spec[event] if isinstance(spec.get(event), list) else []
        groups = [e for e in entries if isinstance(e, dict)]
        handlers = [h for g in groups for h in ((g.get("hooks") or []) if event == "PreToolUse" else [g]) if isinstance(h, dict)]
        command = next((h["command"] for h in handlers if hook_wiring.aidd_hook(h.get("command")) == sub), None)
        if command:
            out[event] = command
    return out


def uninstall(root: Path, actions: list[str], *, yes: bool, verb: str, keep) -> None:
    """Remove the `aidd` hook from `.agents/hooks.json`, the file when nothing else is in it, and `.agents/plugins/aidd/`."""
    path = root / HOOKS_FILE
    if path.is_file():
        data = _read(path)
        if data is None:
            keep(path, "not a JSON object; remove the aidd hook by hand")
        elif HOOK_NAME in data:
            actions.append(f"{verb} the aidd hooks from {repo_paths.shown(path)}")
            if yes:
                del data[HOOK_NAME]
                if data:
                    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                else:
                    path.unlink()
    plugin = root / PLUGIN_DIR
    if plugin.is_dir():
        if mcp_configured(root) and {p.name for p in plugin.iterdir()} <= {"plugin.json", "mcp_config.json"}:
            actions.append(f"{verb} the aidd MCP plugin in {repo_paths.shown(plugin)}")
            if yes:
                shutil.rmtree(plugin)
                if plugin.parent.is_dir() and not any(plugin.parent.iterdir()):
                    plugin.parent.rmdir()
        else:
            keep(plugin, "changed since init")
