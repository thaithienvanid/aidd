"""Codex's hooks and MCP server: the guard and the session hooks in `.codex/hooks.json`, and the `aidd` MCP server in
`.codex/config.toml`, written, checked, and removed.

Codex reads `<project>/.codex/hooks.json` in Claude Code's shape (`hooks_file`; https://learn.chatgpt.com/docs/hooks),
and runs each command from the session's folder, which may sit below the project's top. The file may hold the person's own hooks too: init keeps them. Codex
loads a project's hooks only once the person trusts the project, and runs each new or changed hook only once they
review it in `/hooks`.

Codex also reads a trusted project's `.codex/config.toml`, its `[mcp_servers]` among the rest (codex 0.156 lists a server
there in `codex mcp list`). Init appends one marked block that starts `aidd mcp` through this user's launcher, the way the
hooks do, and keeps every other line; uninstall removes only that block. A file that already names an `aidd` server, or
that is not TOML, is left as it is.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

from aidd.kernel import repo_paths
from aidd.setup import hook_wiring, hooks_file

FILE = hooks_file.HooksFile(".codex/hooks.json", "aidd init --harness codex", "Codex", from_subfolders=True)
HOOKS_FILE, SETUP, EVENTS = FILE.path, FILE.setup, hooks_file.EVENTS
hook_command, wired = FILE.hook_command, FILE.wired

CONFIG_FILE = ".codex/config.toml"
_BEGIN = "# >>> aidd: the aidd MCP server. `aidd init` writes this block, and `aidd uninstall` removes it."
_END = "# <<< aidd"
# sh expands $HOME when Codex starts the server, so the file holds no machine's path, as the hooks hold none.
MCP_BLOCK = f'{_BEGIN}\n[mcp_servers.aidd]\ncommand = "sh"\nargs = ["-c", {json.dumps(f"exec {hook_wiring.HOOK_LAUNCHER} mcp")}]\n{_END}\n'


def _block(text: str) -> tuple[int, int] | None:
    """Where aidd's block sits in the file's text, from its first line to the end of its last; None when it is not there."""
    start = text.find(_BEGIN)
    end = text.find(_END, start) if start >= 0 else -1
    if start < 0 or end < 0:
        return None
    end += len(_END)
    return start, end + (1 if text[end : end + 1] == "\n" else 0)


def install_mcp(root: Path, actions: list[str]) -> None:
    """Add the `aidd` MCP server to `.codex/config.toml`, keeping every other line. Skipped on Windows, as the hooks are."""
    path = root / CONFIG_FILE
    if os.name == "nt":
        actions.append(f"skipped  {CONFIG_FILE} (Windows has no sh; add the server with `codex mcp add aidd -- aidd mcp`)")
        return
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if (span := _block(text)) is not None:
        if text[span[0] : span[1]] == MCP_BLOCK:
            actions.append(f"kept     {repo_paths.shown(path)} (the aidd MCP server is there)")
            return
        path.write_text(text[: span[0]] + MCP_BLOCK + text[span[1] :], encoding="utf-8")
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
    path.write_text(text + lead + MCP_BLOCK, encoding="utf-8")
    actions.append(f"{'updated ' if text else 'wrote   '} {repo_paths.shown(path)} (the aidd MCP server, which Codex starts in a trusted project)")


def install(root: Path, actions: list[str]) -> None:
    """The hooks, then the MCP server."""
    FILE.install(root, actions)
    install_mcp(root, actions)


def uninstall(root: Path, actions: list[str], *, yes: bool, verb: str, keep) -> None:
    """Remove aidd's hooks, and aidd's block from `.codex/config.toml`: the file goes too when nothing else is in it."""
    FILE.uninstall(root, actions, yes=yes, verb=verb, keep=keep)
    path = root / CONFIG_FILE
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if (span := _block(text)) is None:
        return
    actions.append(f"{verb} the aidd MCP server from {repo_paths.shown(path)}")
    if yes:
        rest = text[: span[0]].rstrip("\n") + ("\n" if text[: span[0]].strip() else "") + text[span[1] :]
        if rest.strip():
            path.write_text(rest, encoding="utf-8")
        else:
            path.unlink()
