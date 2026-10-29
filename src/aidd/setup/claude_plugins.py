"""The aidd plugins for Claude Code: installing them for this user, or the repository files that carry the same parts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from aidd import config
from aidd.setup import hook_wiring, team_install

MARKETPLACE_REPO = "thaithienvanid/aidd"
PLUGIN_RUNNER = subprocess.run
# The optional aidd-mods plugin is a mod: Claude Code loads one from this version on (the oldest its tests ran on).
# What `claude plugin marketplace add` says when the settings name a marketplace of that name from another source
# (Claude Code 2.1.301): the marketplace is there, so the installs go on from it.
EXISTING_MARKETPLACE = "extraKnownMarketplaces"
MODS = "aidd-mods"
MODS_MIN = (2, 1, 295)


def share_with_project(root: Path, actions: list[str], *, team: bool) -> bool:
    """Enable the aidd plugins in the project's `.claude/settings.json` (`extraKnownMarketplaces` and `enabledPlugins`),
    so Claude Code offers them to everyone who trusts this folder, in place of the hooks and the MCP server init would
    copy into the repository. aidd-team, turned off there (`false`), stays off; the file is merged, never replaced.
    False when it cannot, so init wires the hooks instead: project settings (shared or local) it cannot read, that turn
    the aidd plugin off, or that name another source for the `aidd` marketplace, which would hand teammates someone
    else's plugin."""
    settings = root / ".claude" / "settings.json"
    source = {"source": {"source": "github", "repo": MARKETPLACE_REPO}}
    data: dict = {}
    # Claude Code merges settings.local.json over settings.json, so a repository could hold either: each is checked.
    for path in (settings, root / ".claude" / "settings.local.json"):
        try:
            read = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            read = None
        shown = path.relative_to(root).as_posix()
        if not isinstance(read, dict) or not isinstance(read.get("enabledPlugins", {}), dict) or not isinstance(read.get("extraKnownMarketplaces", {}), dict):
            actions.append(f"kept     {shown} (not valid settings JSON; wiring the hooks instead)")
            return False
        if read.get("extraKnownMarketplaces", {}).get(config.MARKETPLACE, source) != source:
            actions.append(
                f"warn     {shown} names another source for the `{config.MARKETPLACE}` marketplace; not enabling the plugin "
                f"from it, so init wires the hooks instead. Check that entry: aidd's is {MARKETPLACE_REPO} on GitHub"
            )
            return False
        if read.get("enabledPlugins", {}).get(f"aidd@{config.MARKETPLACE}", True) is not True:
            actions.append(f"kept     {shown} (it turns the aidd plugin off here; wiring the hooks instead)")
            return False
        data = read if path == settings else data
    plugins = [f"aidd@{config.MARKETPLACE}", *([f"aidd-team@{config.MARKETPLACE}"] if team else [])]
    known = data.setdefault("extraKnownMarketplaces", {})
    enabled = data.setdefault("enabledPlugins", {})
    added = [p for p in plugins if p not in enabled]
    new_marketplace = config.MARKETPLACE not in known
    known.setdefault(config.MARKETPLACE, source)
    enabled.update({p: True for p in added})
    shown = settings.relative_to(root).as_posix()
    if not added and not new_marketplace:
        actions.append(f"kept     {shown} (it enables the aidd plugin, which carries the guard, the session hooks, and the MCP server)")
        return True
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    actions.append(
        f"updated  {shown} (enables {', '.join(plugins)}: Claude Code offers {'them' if len(plugins) > 1 else 'it'} to everyone "
        "who trusts this folder, with the guard, the session hooks, and the MCP server)"
    )
    return True


def install_claude_plugins(root: Path, actions: list[str], *, team: bool, mods: bool = False) -> tuple[str, list[str]]:
    """Install the aidd plugins for this user through the Claude Code CLI (user scope), instead of repository files:
    why not ("" when every install ran, else "missing" or "failed"), so init can fall back to repository wiring, and
    the plugins this run installed or found already installed (`claude` exits 0 for both), which the fallback note
    names to uninstall: with the repository files, they would load twice. With `mods`, the optional aidd-mods plugin
    follows (`install_mods`); it never makes init fall back."""
    claude = shutil.which("claude")
    installed: list[str] = []
    if claude is None:
        actions.append("skipped  Claude Code plugins: no `claude` on PATH; wiring the repository instead")
        return "missing", installed
    commands = [[claude, "plugin", "marketplace", "add", MARKETPLACE_REPO], [claude, "plugin", "install", f"aidd@{config.MARKETPLACE}"]]
    if team:
        commands.append([claude, "plugin", "install", f"aidd-team@{config.MARKETPLACE}"])
    for cmd in commands:
        shown = " ".join(["claude", *cmd[1:]])
        try:
            r = PLUGIN_RUNNER(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=str(root))
        except (OSError, subprocess.TimeoutExpired) as exc:
            actions.append(f"failed   {shown}: {exc}; wiring the repository instead")
            return "failed", installed
        output = (r.stderr or r.stdout or "").strip()
        if r.returncode != 0 and cmd[2] == "marketplace" and EXISTING_MARKETPLACE in output:
            # The user's settings already name an `aidd` marketplace from another source, such as a local folder: use it.
            actions.append(f"kept     the {config.MARKETPLACE} marketplace your Claude Code settings already name; installing from it")
            continue
        if r.returncode != 0 and not (cmd[2] == "marketplace" and "already" in output.lower()):
            actions.append(f"failed   {shown}: {output.splitlines()[-1] if output else 'exit ' + str(r.returncode)}; wiring the repository instead")
            return "failed", installed
        actions.append(f"ran      {shown}")
        if cmd[2] == "install":
            installed.append(cmd[-1])
    if mods and install_mods(claude, root, actions):
        installed.append(f"{MODS}@{config.MARKETPLACE}")
    return "", installed


def _version(text: str) -> tuple[int, ...]:
    """`2.1.300 (Claude Code)` -> (2, 1, 300); () when the text names no version."""
    head = text.strip().split(" ", 1)[0]
    parts = head.split(".")
    return tuple(int(p) for p in parts) if parts and all(p.isdigit() for p in parts) else ()


def install_mods(claude: str, root: Path, actions: list[str]) -> bool:
    """Install the optional aidd-mods plugin when this Claude Code loads mods (`MODS_MIN`). It is extra: a version too
    old, or a failed install, is a `skipped` or `failed` line, and the plugins installed before it stand."""
    shown = f"claude plugin install {MODS}@{config.MARKETPLACE}"
    want = ".".join(map(str, MODS_MIN))
    try:
        said = PLUGIN_RUNNER([claude, "--version"], capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(root))
        have = _version(said.stdout or "")
        if not have or have < MODS_MIN:
            found = ".".join(map(str, have)) or "an unknown version"
            actions.append(f"skipped  {MODS}: Claude Code {found} loads no mods; it needs {want} or later. Update it, then run `{shown}`")
            return False
        r = PLUGIN_RUNNER(
            [claude, "plugin", "install", f"{MODS}@{config.MARKETPLACE}"], capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=str(root)
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        actions.append(f"failed   {shown}: {exc}; the other plugins stand. Run it again later")
        return False
    if r.returncode != 0:
        output = (r.stderr or r.stdout or "").strip()
        actions.append(f"failed   {shown}: {output.splitlines()[-1] if output else 'exit ' + str(r.returncode)}; the other plugins stand. Run it again later")
        return False
    actions.append(f"ran      {shown}")
    return True


def claude_repo_files(root: Path) -> tuple[list[str], list[str]]:
    """The repository files that carry what the aidd plugins carry, for Claude Code: (the skill's part, the team's part).
    The skill's part is the `.claude/skills/aidd` link or copy, the aidd hook in `.claude/settings.json`, and the `aidd`
    server in `.mcp.json`; the team's part is the `aidd-*` agents, commands, and skills `aidd init --team` writes.
    A file that cannot be read counts as not carrying anything; `unreadable_claude_settings` names it. Only the names
    aidd ships count, so a team's own `.claude/skills/aidd-<name>` is never one of them."""
    skill: list[str] = []
    if (root / ".claude" / "skills" / "aidd").exists():
        skill.append(".claude/skills/aidd")
    try:
        if hook_wiring.HOOK_COMMAND in (root / ".claude" / "settings.json").read_text(encoding="utf-8", errors="replace"):
            skill.append(".claude/settings.json")
    except OSError:
        pass
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError, AttributeError):
        servers = {}
    if isinstance(servers, dict) and "aidd" in servers:
        skill.append(".mcp.json")
    shipped = [rel for rel in team_install.team_files([], True) if rel.startswith(".claude/")]
    team = [f".claude/{d}" for d in ("agents", "commands", "skills") if any(rel.startswith(f".claude/{d}/") and (root / rel).is_file() for rel in shipped)]
    return skill, team


def plugin_fallback_note(root: Path, installed: list[str], why: str = "missing") -> str:
    """What `aidd init --claude-plugins` says when it wired the repository instead of the plugins: what Claude Code now
    loads from the repository, that those files replace the plugins, and how to switch to the plugins later. It never
    says to install the plugins as well: the skill and the roles would load twice (`aidd doctor` warns)."""
    skill, team = claude_repo_files(root)
    files = [*skill, *(f"{d}/{team_install.TEAM_PREFIX}*" for d in team)]
    undo = (
        (" Uninstall the plugins this run installed or found already installed: " + ", ".join(f"`claude plugin uninstall {p}`" for p in installed) + ".")
        if installed
        else ""
    )
    cause = (
        "the `claude` CLI is missing, so install the `claude` CLI"
        if why == "missing"
        else "the install failed, so see the `failed` line above and fix its cause"
    )
    return (
        f"fallback Claude Code loads aidd from the repository files instead: {', '.join(files) or 'none'}. These files replace the plugins, "
        f"so do not also install the plugins: the skill and the roles would load twice.{undo} To use the plugins instead: {cause}, "
        "run `aidd uninstall --yes`, then run the same `aidd init` again with `--claude-plugins`. "
        f"Init then adds the marketplace, as /plugin marketplace add {MARKETPLACE_REPO} does in Claude Code, and installs the plugins"
    )
