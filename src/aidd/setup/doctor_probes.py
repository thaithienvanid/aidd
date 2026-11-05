"""What `aidd doctor` runs and reads on this machine: the configured MCP server, started once, a plugin loaded twice,
and the installed OpenCode's version.
"""

from __future__ import annotations

import filecmp
import json
import os
import re
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
    """Run a launcher once with `stdin`, as the program `shutil.which` finds: the finished process, or why it could not run."""
    if not (program := shutil.which(words[0])):
        return f"{words[0]} is not found"
    try:
        return subprocess.run(
            [program, *words[1:]],
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


def run_mcp_probe(root: Path, timeout_seconds: int = 20) -> str | None:
    """Start the MCP server `aidd init` writes (`mcp_wiring.mcp_server`) and send `server/discover`; None when aidd
    answers, else why not. The program comes from aidd, never from the repository's `.mcp.json`, which a repository
    can track with any program in it."""
    server = mcp_wiring.mcp_server()
    program = str(mcp_wiring.user_launcher_path()) if server["command"] == mcp_wiring.MCP_LAUNCHER else server["command"]
    r = _run_probe(root, [program, *server["args"]], {}, json.dumps(_MCP_PROBE) + "\n", timeout_seconds)
    if isinstance(r, str):
        return r
    if mcp_server_name(r.stdout) == "aidd":
        return None
    last = (r.stderr or r.stdout).strip().splitlines()
    return f"exit {r.returncode}, no MCP answer" + (f": {last[-1]}" if last else "")


def opencode_version_problem(root: Path) -> str | None:
    """Why the installed OpenCode cannot read aidd's ask rules, or None: aidd writes them in OpenCode v2's `permissions`
    list, and OpenCode v1 refuses a file with a top-level key it does not know (packages/opencode/src/config/parse.ts:40-52,
    at v1.18.0). `opencode --version` answers offline and runs no project plugin. An `opencode` inside the repository
    never runs, as the MCP launcher takes no program from the project, and a `0.0.0-` build (a beta or dev one) reads
    as unknown."""
    program = shutil.which("opencode")
    if not program or Path(program).resolve().is_relative_to(Path(root).resolve()):
        return None
    r = _run_probe(root, [program, "--version"], {}, "", 10)
    found = None if isinstance(r, str) else re.search(r"(\d+)\.\d+\.\d+-?", r.stdout)
    if not found or found.group(0).startswith("0.0.0-") or int(found.group(1)) >= 2:
        return None
    return (
        f"OpenCode: this machine has OpenCode {found.group(0).rstrip('-')}, but aidd supports only v2 and later. aidd's ask rules "
        "are in `opencode.json`'s `permissions` list, which v1 refuses, and v1's `opencode upgrade` can stay on v1. Install v2, "
        "such as with `npm rm -g opencode-ai && npm i -g @opencode/cli@latest` or `brew install opencode` (docs/GUIDE.md, "
        '"Every coding agent", lists each way), then run `aidd doctor` again'
    )


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
    if execute and server != mcp_wiring.mcp_server():
        return [
            (
                "warn",
                f"{label}: the aidd MCP server was not started: the entry in {mcp_wiring.MCP_FILE} is not the one `aidd init` writes, and doctor starts no program a tracked file names. "
                "Run `aidd init` to write the entry, or run `aidd mcp` yourself to check the server",
            )
        ]
    if execute and (why := run_mcp_probe(root)):
        return [("fail", f"{label}: the aidd MCP server did not start: {why}")]
    return [("ok", f"{label}: the aidd MCP server is wired in {mcp_wiring.MCP_FILE}")]
