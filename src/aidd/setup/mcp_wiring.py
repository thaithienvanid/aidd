"""How a coding agent starts aidd's MCP server, and how `aidd upgrade` removes the wiring an older aidd wrote.

The MCP server starts through this user's launcher, `~/.aidd/bin/aidd`, which `aidd init` writes: the interpreter
aidd is installed with, by its absolute path and isolated (`-I`), so a project's PYTHONPATH or a module in the working
folder cannot replace aidd's code. `.mcp.json` and `.codex/config.toml` then name the launcher through the home folder
and hold no machine's path. A launcher whose aidd sits inside the repository is never written: every repository on the
machine starts aidd through it, so one repository would steer them all.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
import tomllib
from pathlib import Path

import aidd
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
CODEX_BLOCK = f'{_BEGIN}\n[mcp_servers.aidd]\ncommand = "sh"\nargs = ["-c", {json.dumps(f"exec {SH_LAUNCHER} mcp")}]\n{_END}\n'


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
    if (span := _block(text)) is not None:
        if text[span[0] : span[1]] == CODEX_BLOCK:
            actions.append(f"kept     {repo_paths.shown(path)} (the aidd MCP server is there)")
            return
        path.write_text(text[: span[0]] + CODEX_BLOCK + text[span[1] :], encoding="utf-8")
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
    path.write_text(text + lead + CODEX_BLOCK, encoding="utf-8")
    actions.append(f"{'updated ' if text else 'wrote   '} {repo_paths.shown(path)} (the aidd MCP server, which Codex starts in a trusted project)")


def remove_mcp(root: Path, actions: list[str], *, yes: bool) -> None:
    """Take aidd's MCP server out of `.mcp.json` and `.codex/config.toml` (`aidd uninstall`)."""
    verb = "removed" if yes else "would remove"
    path = root / MCP_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        data = {}
    if isinstance(data.get("mcpServers"), dict) and data["mcpServers"].get("aidd") == mcp_server():
        actions.append(f"{verb} the aidd MCP server from {repo_paths.shown(path)}")
        if yes:
            del data["mcpServers"]["aidd"]
            if not data["mcpServers"] and len(data) == 1:
                path.unlink()
            else:
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
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


# What an older aidd wrote to run its guard and session hooks, and the gate's CI: `aidd upgrade` removes each one.
_OLD_HOOK = re.compile(r"(?<![\w-])aidd(?:\.cmd)?\"?\s+hook\s+(pre-tool|session-start|prompt-submit|stop|pre-compact|subagent-start|post-tool)\b")
OLD_FILES = (
    ".grok/hooks/aidd.json",
    ".opencode/plugins/aidd.js",
    ".github/workflows/aidd-gate.yml",
    ".github/workflows/aidd-relay.yml",
    ".github/rulesets/goal.json",
)
OLD_FOLDERS = (".opencode/plugins/aidd-tui",)
OLD_HOOK_FILES = (".claude/settings.json", ".claude/settings.local.json", ".codex/hooks.json", ".agents/hooks.json")


def _drop_hooks(data: dict) -> int:
    """Remove every aidd hook handler from a Claude Code shaped `hooks` block, and Antigravity's named `aidd` hook
    (`{"aidd": {"PreToolUse": [...]}}` in `.agents/hooks.json`); how many it removed."""
    removed = 0
    named = data.get("aidd")
    if isinstance(named, dict) and _OLD_HOOK.search(json.dumps(named)):
        removed += sum(len(v) if isinstance(v, list) else 1 for v in named.values())
        del data["aidd"]
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return removed
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue  # not a list of groups, so nothing of aidd's: the person's own, kept as it is
        groups = hooks[event]
        kept_groups = []
        for g in groups:
            if isinstance(g, dict) and "hooks" not in g:  # a handler on its own, as Antigravity's events hold them
                if _OLD_HOOK.search(str(g.get("command", ""))):
                    removed += 1
                else:
                    kept_groups.append(g)
                continue
            if not (isinstance(g, dict) and isinstance(g["hooks"], list)):
                kept_groups.append(g)  # not a group of handlers: the person's own, as it is
                continue
            handlers = g["hooks"]
            kept = [h for h in handlers if not (isinstance(h, dict) and _OLD_HOOK.search(str(h.get("command", ""))))]
            removed += len(handlers) - len(kept)
            if kept:
                kept_groups.append({**g, "hooks": kept})
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks")
    return removed


def remove_old_wiring(root: Path, actions: list[str], *, yes: bool) -> None:
    """Remove what an older aidd wrote for its guard, its session hooks, its terminal pane, and its gate's CI, keeping
    everything a person wrote beside it."""
    verb = "removed" if yes else "would remove"
    for rel in OLD_HOOK_FILES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict) or not (n := _drop_hooks(data)):
            continue
        actions.append(f"{verb} {n} aidd hook{'s' if n > 1 else ''} from {rel} (aidd runs no hooks now)")
        if yes:
            if data:
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            else:
                path.unlink()
    for rel in OLD_FILES:
        if (root / rel).is_file():
            actions.append(f"{verb} {rel} (an older aidd's guard or gate)")
            if yes:
                (root / rel).unlink()
    for rel in OLD_FOLDERS:
        if (root / rel).is_dir():
            actions.append(f"{verb} {rel}/ (an older aidd's terminal pane)")
            if yes:
                shutil.rmtree(root / rel)
