"""What `aidd doctor` runs and reads on this machine: the configured MCP server, started once, and a plugin loaded
twice.
"""

from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
from pathlib import Path

from aidd import __version__, config
from aidd.setup import claude_plugins, mcp_wiring


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
                f"{label}: the aidd plugin (aidd@{config.MARKETPLACE}) is enabled and {', '.join(skill)} also carry what the plugin carries (the skill and the MCP server), so it would load twice. {fix}",
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


# The first message a client sends an MCP server: it only asks the server who it is.
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
    if not shutil.which(words[0]):
        return f"{words[0]} is not found"
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
    program = str(mcp_wiring.user_launcher_path()) if command == mcp_wiring.MCP_LAUNCHER else command
    words, env = [program, *map(str, args)], {str(k): str(v) for k, v in env.items()}
    r = _run_probe(root, words, env, json.dumps(_MCP_PROBE) + "\n", timeout_seconds)
    if isinstance(r, str):
        return r
    if mcp_server_name(r.stdout) == "aidd":
        return None
    last = (r.stderr or r.stdout).strip().splitlines()
    return f"exit {r.returncode}, no MCP answer" + (f": {last[-1]}" if last else "")


def tree_diff(a: Path, b: Path) -> list[str]:
    cmp = filecmp.dircmp(a, b, ignore=filecmp.DEFAULT_IGNORES + [".DS_Store", "Thumbs.db"])
    out = [f"only in bundled: {x}" for x in cmp.left_only] + [f"only in repo: {x}" for x in cmp.right_only]
    out += [f"differs: {x}" for x in cmp.diff_files]
    for sub in cmp.common_dirs:
        out += [f"{sub}/{x}" for x in tree_diff(a / sub, b / sub)]
    return out


def claude_mcp_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Claude Code's `aidd` MCP server, as `.mcp.json` or the aidd plugin carries it; with `execute`, started once."""
    label = "Claude Code"
    if config.plugin_enabled(root):
        return [("ok", f"{label}: the aidd plugin carries the skill and the MCP server")]
    try:
        server = (json.loads((root / mcp_wiring.MCP_FILE).read_text(encoding="utf-8")).get("mcpServers") or {}).get("aidd")
    except (OSError, ValueError, AttributeError):
        server = None
    if not isinstance(server, dict):
        return [("warn", f"{label}: no aidd MCP server in {mcp_wiring.MCP_FILE}; `aidd init` adds it (the skill works without it)")]
    if server.get("command") == mcp_wiring.MCP_LAUNCHER and not mcp_wiring.user_launcher_path().is_file():
        return [("warn", f"{label}: {mcp_wiring.MCP_FILE} starts {mcp_wiring.USER_LAUNCHER_SHOWN}, which this machine lacks; `aidd init` writes it")]
    if execute and (why := run_mcp_probe(root, server)):
        return [("fail", f"{label}: the aidd MCP server did not start: {why}")]
    return [("ok", f"{label}: the aidd MCP server is wired in {mcp_wiring.MCP_FILE}")]
