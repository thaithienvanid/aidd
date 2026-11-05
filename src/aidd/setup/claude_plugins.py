"""The aidd plugins for Claude Code: installing them for this user, or the repository files that carry the same parts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from aidd import config
from aidd.kernel import regular_files
from aidd.kernel.regular_files import open_for_write, write_refusal
from aidd.setup import pins, team_install

MARKETPLACE_REPO = "thaithienvanid/aidd"
PLUGIN_RUNNER = subprocess.run
# What `claude plugin marketplace add` says when the settings name a marketplace of that name from another source
# (Claude Code 2.1.301): the marketplace is there, so the installs go on from it.
EXISTING_MARKETPLACE = "extraKnownMarketplaces"
STABLE_NOTE = f"the aidd marketplace follows `{pins.STABLE_BRANCH}`, the branch each release moves, instead of main"
UNTIL_RELEASE = (
    f"the aidd marketplace follows main, so the plugins carry each commit on main, released or not, until aidd has a release "
    f"and `aidd upgrade --yes` moves it to `{pins.STABLE_BRANCH}`"
)


def marketplace_source() -> dict:
    """The aidd marketplace's source for Claude Code: the `stable` branch, which only a release moves, once the first
    release has made it; before that, or when GitHub cannot say, no `ref`, so Claude Code follows the default branch."""
    source = {"source": "github", "repo": MARKETPLACE_REPO}
    return {**source, "ref": pins.STABLE_BRANCH} if pins.stable_exists() else source


# The refs of aidd's marketplace a person may choose: the release channel, the default branch, or one release's tag.
OWN_REFS = re.compile(rf"{pins.STABLE_BRANCH}|main|v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


def is_aidd_marketplace(entry: object) -> bool:
    """Whether an `extraKnownMarketplaces` entry is aidd's own marketplace: this repository on GitHub, at its default
    branch or at a `ref` of aidd's own (`OWN_REFS`). Any other ref is another source, which may be anyone's branch."""
    source = entry.get("source") if isinstance(entry, dict) and set(entry) == {"source"} else None
    if not isinstance(source, dict) or not set(source) <= {"source", "repo", "ref"}:
        return False
    ref = source.get("ref")
    return (
        source.get("source") == "github"
        and source.get("repo") == MARKETPLACE_REPO
        and (ref is None or (isinstance(ref, str) and bool(OWN_REFS.fullmatch(ref))))
    )


def write_settings(root: Path, path: Path, data: dict, actions: list[str]) -> bool:
    """Write Claude Code settings to `path`, never through a link: a link at the file or on the way to it could send the
    write outside the repository. False, with a line that says so, when there is one."""
    shown = path.relative_to(root).as_posix()
    if refused := write_refusal(root, path):
        actions.append(f"kept     {shown} ({refused})")
        return False
    if not regular_files.writes_held():  # a plan holds the write and makes no folder
        path.parent.mkdir(parents=True, exist_ok=True)
    with open_for_write(path, text=True, root=root) as out:
        out.write(json.dumps(data, indent=2) + "\n")
    return True


def moves_to_stable(entry: dict, source: dict) -> bool:
    """Set aidd's own entry, with no `ref`, to the `stable` ref `source` names, and say whether it moved. A `ref` a person
    chose stays as it is."""
    if not is_aidd_marketplace(entry) or "ref" in entry["source"] or "ref" not in source:
        return False
    entry["source"] = dict(source)
    return True


def share_with_project(root: Path, actions: list[str], *, aidd_team: bool, packs: bool = False) -> bool:
    """Enable the aidd plugins in the project's `.claude/settings.json` (`extraKnownMarketplaces` and `enabledPlugins`),
    so Claude Code offers them to everyone who trusts this folder, in place of the MCP server and the skill link init would
    copy into the repository. aidd-packs, with the team, only where the repository calls for a domain pack (`packs`), since
    its descriptions share the skill listing budget. aidd-team, turned off there (`false`), stays off; the file is merged, never replaced.
    False when it cannot, so init wires the repository instead: project settings (shared or local) it cannot read, that turn
    the aidd plugin off, or that name another source for the `aidd` marketplace, which would hand teammates someone
    else's plugin. aidd's entry follows `stable` once a release has made it (`marketplace_source`)."""
    settings = root / ".claude" / "settings.json"
    source = marketplace_source()
    data: dict = {}
    # Claude Code merges settings.local.json over settings.json, so a repository could hold either: each is checked.
    for path in (settings, root / ".claude" / "settings.local.json"):
        try:
            read = json.loads(regular_files.repository_text(root, path.relative_to(root).as_posix()) or "{}")
        except (OSError, ValueError):
            read = None
        shown = path.relative_to(root).as_posix()
        if not isinstance(read, dict) or not isinstance(read.get("enabledPlugins", {}), dict) or not isinstance(read.get("extraKnownMarketplaces", {}), dict):
            actions.append(f"kept     {shown} (not valid settings JSON; wiring the repository instead)")
            return False
        if not is_aidd_marketplace(read.get("extraKnownMarketplaces", {}).get(config.MARKETPLACE, {"source": source})):
            actions.append(
                f"warn     {shown} names another source for the `{config.MARKETPLACE}` marketplace; not enabling the plugin "
                f"from it, so init wires the repository instead. Check that entry: aidd's is {MARKETPLACE_REPO} on GitHub"
            )
            return False
        if read.get("enabledPlugins", {}).get(f"aidd@{config.MARKETPLACE}", True) is not True:
            actions.append(f"kept     {shown} (it turns the aidd plugin off here; wiring the repository instead)")
            return False
        data = read if path == settings else data
    plugins = [
        f"aidd@{config.MARKETPLACE}",
        *([f"aidd-team@{config.MARKETPLACE}"] if aidd_team else []),
        *([f"{config.PACKS_PLUGIN}@{config.MARKETPLACE}"] if aidd_team and packs else []),
    ]
    known = data.setdefault("extraKnownMarketplaces", {})
    enabled = data.setdefault("enabledPlugins", {})
    added = [p for p in plugins if p not in enabled]
    new_marketplace = config.MARKETPLACE not in known
    moved = not new_marketplace and moves_to_stable(known[config.MARKETPLACE], source)
    entry = known.setdefault(config.MARKETPLACE, {"source": source})
    enabled.update({p: True for p in added})
    shown = settings.relative_to(root).as_posix()
    main = "" if "ref" in entry["source"] else f"; {UNTIL_RELEASE}"
    if not added and not new_marketplace and not moved:
        actions.append(f"kept     {shown} (it enables the aidd plugin, which carries the skill and the MCP server{main})")
        return True
    if not write_settings(root, settings, data, actions):
        return False  # init wires the repository instead
    them = "them" if len(plugins) > 1 else "it"
    what = f"enables {', '.join(plugins)}: Claude Code offers {them} to everyone who trusts this folder, with the skill and the MCP server"
    actions.append(f"updated  {shown} ({'; '.join([*([what] if added or new_marketplace else []), *([STABLE_NOTE] if moved else [])])}{main})")
    return True


def _aidd_entries(root: Path, path: Path) -> tuple[dict, dict] | None:
    """(the settings, aidd's marketplace entry in them) from a Claude Code settings file, or None when it names none."""
    try:
        data = json.loads(regular_files.text_at(root, path) or "")
    except (OSError, ValueError):
        return None
    known = data.get("extraKnownMarketplaces") if isinstance(data, dict) else None
    entry = known.get(config.MARKETPLACE) if isinstance(known, dict) else None
    return (data, entry) if isinstance(entry, dict) and is_aidd_marketplace(entry) else None


def follow_stable(root: Path, actions: list[str], *, yes: bool) -> None:
    """`aidd upgrade`: move the aidd marketplace that init wrote into `.claude/settings.json` with no `ref` to `stable`,
    once a release has made that branch. It asks GitHub only when there is such an entry; a `ref` a person chose stays."""
    settings = root / ".claude" / "settings.json"
    found = _aidd_entries(root, settings)
    if found is None or "ref" in found[1]["source"] or not moves_to_stable(found[1], marketplace_source()):
        return
    if yes and not write_settings(root, settings, found[0], actions):
        return
    actions.append(f"{'updated ' if yes else 'would update'} .claude/settings.json ({STABLE_NOTE})")


def channel_checks(root: Path) -> list[tuple[str, str]]:
    """`aidd doctor`: which branch each Claude Code settings file adds the aidd marketplace at. With no `ref` it follows
    main, so aidd asks GitHub whether a release has made `stable` yet, and says what to do when it has."""
    out: list[tuple[str, str]] = []
    asked: list[bool | None] = []  # GitHub's answer, asked once
    for path in config.claude_settings_paths(root):
        found = _aidd_entries(root, path)
        if found is None:
            continue
        shown = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        ref = found[1]["source"].get("ref")
        if ref == pins.STABLE_BRANCH:
            out.append(("ok", f"Claude Code: {shown} adds the aidd marketplace at `{ref}`, which moves only when aidd releases"))
            continue
        if ref:
            continue  # a branch or tag a person chose
        asked = asked or [pins.stable_exists()]
        stable = asked[0]
        fix = "`aidd upgrade --yes` moves it" if path == root / ".claude" / "settings.json" else f'add `"ref": "{pins.STABLE_BRANCH}"` to its source'
        if stable:
            out.append(
                (
                    "warn",
                    f"Claude Code: {shown} adds the aidd marketplace at main, which carries unreleased commits, while aidd has a release: {fix} to `{pins.STABLE_BRANCH}`",
                )
            )
        else:
            why = "aidd has no release yet" if stable is False else "aidd could not ask GitHub whether it has a release"
            out.append(
                (
                    "info",
                    f"Claude Code: {shown} adds the aidd marketplace at main, because {why}. So the plugins carry each commit on main; once a release makes `{pins.STABLE_BRANCH}`, {fix} there",
                )
            )
    return out


def install_claude_plugins(root: Path, actions: list[str], *, aidd_team: bool) -> tuple[str, list[str]]:
    """Install the aidd plugins for this user through the Claude Code CLI (user scope), instead of repository files:
    why not ("" when every install ran, else "offline", "missing", or "failed"), so init can fall back to repository wiring, and
    the plugins this run installed or found already installed (`claude` exits 0 for both), which the fallback note
    names to uninstall: with the repository files, they would load twice."""
    installed: list[str] = []
    if os.environ.get("AIDD_OFFLINE") == "1":
        # `claude plugin marketplace add` and `install` fetch the plugins from github.com, an optional call offline stops.
        actions.append("skipped  Claude Code plugins: offline (AIDD_OFFLINE=1), and installing them fetches from github.com; wiring the repository instead")
        return "offline", installed
    claude = shutil.which("claude")
    if claude is None:
        actions.append("skipped  Claude Code plugins: no `claude` on PATH; wiring the repository instead")
        return "missing", installed
    # `owner/repo#ref` adds the marketplace at that branch, as Claude Code's docs say; before the first release, at main.
    add = MARKETPLACE_REPO + (f"#{pins.STABLE_BRANCH}" if "ref" in marketplace_source() else "")
    commands = [[claude, "plugin", "marketplace", "add", add], [claude, "plugin", "install", f"aidd@{config.MARKETPLACE}"]]
    if aidd_team:
        commands.append([claude, "plugin", "install", f"aidd-team@{config.MARKETPLACE}"])
    for cmd in commands:
        shown = " ".join(["claude", *cmd[1:]])
        if regular_files.writes_held():  # a plan runs nothing, and takes the installs as they would go
            actions.append(f"ran      {shown}")
            installed += [cmd[-1]] if cmd[2] == "install" else []
            continue
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
    return "", installed


def claude_repo_files(root: Path) -> tuple[list[str], list[str]]:
    """The repository files that carry what the aidd plugins carry, for Claude Code: (the skill's part, the team's part).
    The skill's part is the `.claude/skills/aidd` link or copy and the `aidd` server in `.mcp.json`; the team's part is the `aidd-*` agents, commands, and skills `aidd init --aidd-team` writes.
    A file that cannot be read counts as not carrying anything; `unreadable_claude_settings` names it. Only the names
    aidd ships count, so a team's own `.claude/skills/aidd-<name>` is never one of them."""
    skill: list[str] = []
    if (root / ".claude" / "skills" / "aidd").exists():
        skill.append(".claude/skills/aidd")
    try:
        servers = json.loads(regular_files.repository_text(root, ".mcp.json") or "").get("mcpServers") or {}
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
    causes = {
        "missing": "the `claude` CLI is missing, so install the `claude` CLI",
        "offline": "AIDD_OFFLINE=1 stopped the install, so unset it",
    }
    cause = causes.get(why, "the install failed, so see the `failed` line above and fix its cause")
    return (
        f"fallback Claude Code loads aidd from the repository files instead: {', '.join(files) or 'none'}. These files replace the plugins, "
        f"so do not also install the plugins: the skill and the roles would load twice.{undo} To use the plugins instead: {cause}, "
        "run `aidd uninstall --yes`, then run the same `aidd init` again with `--claude-plugins`. "
        f"Init then adds the marketplace, as /plugin marketplace add {MARKETPLACE_REPO} does in Claude Code, and installs the plugins"
    )
