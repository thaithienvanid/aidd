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
from aidd.kernel import documents, regular_files
from aidd.setup import claude_plugins, domain_packs, mcp_wiring, migrating
from aidd.setup.self_updating import version_key


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
    if f"{config.PACKS_PLUGIN}@{config.MARKETPLACE}" in on and (held := domain_packs.installed(root)):
        out.append(
            (
                "warn",
                f"{label}: the {config.PACKS_PLUGIN} plugin ({config.PACKS_PLUGIN}@{config.MARKETPLACE}) is enabled and .claude/skills/ also holds the packs {', '.join(held)}, so they would load twice. {fix}",
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


def tree_diff(bundled: Path, copy: Path) -> list[str]:
    """How the repository's `copy` differs from aidd's `bundled` tree: the names only in one, then the files that
    differ, then each folder in both. It reads `copy`'s files as regular files only, through the safe reader, so a link, a
    pipe, or a device there differs and is never read, and it never walks a linked folder."""
    ignore = {*filecmp.DEFAULT_IGNORES, ".DS_Store", "Thumbs.db"}

    def names(top: Path) -> set[str]:
        return {n for n in os.listdir(top) if n not in ignore} if top.is_dir() and not top.is_symlink() else set()

    left, right = names(bundled), names(copy)
    out = [f"only in bundled: {x}" for x in sorted(left - right)] + [f"only in repo: {x}" for x in sorted(right - left)]
    both = sorted(left & right)
    dirs = [n for n in both if (bundled / n).is_dir() and (copy / n).is_dir() and not (copy / n).is_symlink()]
    for n in (n for n in both if n not in dirs):
        theirs, _ = regular_files.file_bytes(regular_files.working_root(copy / n), copy / n, regular_files.MAX_REPOSITORY_FILE)
        if not (bundled / n).is_file() or theirs != (bundled / n).read_bytes():  # aidd's own: the bundled skill
            out.append(f"differs: {n}")
    for sub in dirs:
        out += [f"{sub}/{x}" for x in tree_diff(bundled / sub, copy / sub)]
    return out


def launcher_checks() -> list[tuple[str, str]]:
    """The user launcher every repository's MCP server and delegation hook start through: a warning when it starts a
    path that is no install, or that is gone. Silent when the launcher is missing (the checks of each wiring say so)."""
    why = mcp_wiring.launcher_problem()
    return [("warn", why)] if why else []


def claude_mcp_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Claude Code's `aidd` MCP server, as `.mcp.json` or the aidd plugin carries it; with `execute`, started once."""
    label = "Claude Code"
    if config.plugin_enabled(root):
        return [("ok", f"{label}: the aidd plugin carries the skill and the MCP server")]
    try:
        server = (json.loads(regular_files.repository_text(root, mcp_wiring.MCP_FILE) or "").get("mcpServers") or {}).get("aidd")
    except (OSError, ValueError, AttributeError):
        server = None
    if not isinstance(server, dict):
        return [("warn", f"{label}: no aidd MCP server in {mcp_wiring.MCP_FILE}; `aidd init` adds it (the skill works without it)")]
    if server.get("command") == mcp_wiring.MCP_LAUNCHER and not mcp_wiring.user_launcher_path().is_file():
        return [
            (
                "warn",
                f"{label}: {mcp_wiring.MCP_FILE} starts {mcp_wiring.USER_LAUNCHER_SHOWN}, which this machine lacks; `aidd init` from an installed aidd writes it",
            )
        ]
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


# A version as a doctor line may show it: three numbers, each short, and a short suffix. Any longer text is no version.
VERSION = re.compile(r"\d{1,6}\.\d{1,6}\.\d{1,6}(?:-[0-9A-Za-z.]{1,32})?")
SKILL_FILE = "SKILL.md"


def skill_version(text: str | None) -> str | None:
    """The version a skill file names in its front matter (`metadata.version`), or None when it names none that reads."""
    try:
        data, _ = documents.split_front_matter(text, SKILL_FILE) if text else ({}, "")
    except documents.DocumentError:
        return None
    meta = data.get("metadata")
    version = meta.get("version") if isinstance(meta, dict) else None
    return version if isinstance(version, str) and VERSION.fullmatch(version) else None


def plugin_version(root: Path) -> str | None:
    """The version of the aidd plugin enabled here: the skill's version in the folder Claude Code installed it to, found in
    its own record of installed plugins (`installed_plugins.json` in its plugins folder). No network call, and no program runs.
    None when the plugin is not enabled, or when no one version reads: a record that names folders of two versions, a record
    Claude Code keeps another way, or a folder with no skill. The plugin's manifest names no version, so its skill does."""
    key = f"aidd@{config.MARKETPLACE}"
    if key not in config.plugins_enabled(root):
        return None
    try:
        entries = json.loads(regular_files.own_text(config.claude_config_dir() / "plugins" / "installed_plugins.json") or "")["plugins"][key]
        folders = {Path(e["installPath"]) for e in entries}
    except (ValueError, KeyError, TypeError, RecursionError):  # a record nested too deep to read is no record
        return None
    found = {skill_version(regular_files.own_text(f / ".agents" / "skills" / "aidd" / SKILL_FILE)) for f in folders}
    return found.pop() if len(found) == 1 and None not in found else None


def version_lines(root: Path) -> list[tuple[str, str]]:
    """A warning when the plugin, or the skill in this repository, is of a newer aidd than the one that runs, and when the
    plugin is of an older one, each with the step that works where the person is. One `claude plugin update` moves every
    project on the machine at once, while the `aidd` command and each repository's files stay as they were, so the three can
    differ. Each version comes from a file; a version that cannot be read is not guessed, and says nothing."""
    plugin = plugin_version(root)
    skill = skill_version(regular_files.repository_text(root, ".agents/skills/aidd/SKILL.md"))
    ahead = [
        f"{what} {v}" for what, v in (("the aidd plugin", plugin), ("the skill in this repository", skill)) if v and version_key(v) > version_key(__version__)
    ]
    out = []
    if ahead:
        words = " and ".join(ahead)
        out.append(
            (
                "warn",
                f"{words} {'is' if len(ahead) == 1 else 'are'} newer than this aidd {__version__}, so the skill may ask for what this aidd does not do yet: run `aidd self-update`",
            )
        )
    if plugin and version_key(plugin) < version_key(__version__):
        out.append(
            (
                "warn",
                f"the aidd plugin {plugin} is older than this aidd {__version__}: in a terminal, run `claude plugin marketplace update aidd`, "
                "then `claude plugin update aidd@aidd` and `claude plugin update aidd-team@aidd`",
            )
        )
    return out


def retired_name_lines(root: Path) -> list[tuple[str, str]]:
    """A warning when a file aidd reads here holds a name aidd retired: how many names in how many files, and the step. The
    one plan `aidd upgrade` makes counts them, so doctor and the upgrade never disagree. A config that does not load already
    has its own failure, which names the same step, so the caller asks only when the config loads."""
    try:
        found = migrating.plan(root)
    except (ValueError, OSError):
        return []
    named = [words for kind, words in found.lines if kind in ("migrate", "manual")]
    if not named:
        return []
    files = {words.split(":", 1)[0] for words in named}
    left = sum(kind == "manual" for kind, _ in found.lines)
    rest = f", and names the {left} it leaves for you to change" if left else ""
    many = len(named) > 1
    return [
        (
            "warn",
            f"{len(named)} name{'s' if many else ''} aidd retired {'are' if many else 'is'} still in {len(files)} file{'s' if len(files) > 1 else ''} here "
            f"(the config, Specs, or another file aidd reads): `aidd upgrade --yes` moves them{rest}",
        )
    ]
