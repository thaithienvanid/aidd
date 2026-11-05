"""Claude Code's settings as aidd reads them: the settings files, the plugins they enable, and whether the aidd-team
roles are installed."""

from __future__ import annotations

import json
import os
from pathlib import Path

from aidd.kernel import regular_files

MARKETPLACE = "aidd"
PACKS_PLUGIN = "aidd-packs"  # the plugin that carries the domain packs, as `aidd-packs:<pack>`; every other team skill is `aidd-team:<name>`


def claude_config_dir() -> Path:
    """Claude Code's user folder: CLAUDE_CONFIG_DIR when set, else ~/.claude."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def plugins_enabled(root: Path) -> set[str]:
    """The plugins Claude Code enables in this repository, from `enabledPlugins` in the user's settings, then the
    project's `.claude/settings.json`, then `.claude/settings.local.json`: a later file decides over an earlier one.
    Managed settings and a plugin installed but not named in any of them are not seen."""
    return _enabled_in(claude_settings_paths(root), root)


def user_plugins_enabled() -> set[str]:
    """The plugins this user's own Claude Code settings enable: never what a repository's `.claude/` files say, so a
    repository cannot claim the aidd plugin to keep `aidd init` from writing its own wiring."""
    return _enabled_in([claude_config_dir() / "settings.json"])


def _enabled_in(paths: list[Path], root: Path | None = None) -> set[str]:
    on: dict[str, bool] = {}
    for path in paths:
        try:
            enabled = (
                json.loads((regular_files.text_at(root, path) if root else regular_files.own_text(path)) or "").get("enabledPlugins") or {}
            )  # the person's own follows a link
        except (ValueError, AttributeError):
            continue
        if isinstance(enabled, dict):
            on.update({k: v is True for k, v in enabled.items()})
    return {k for k, v in on.items() if v}


def claude_settings_paths(root: Path) -> list[Path]:
    """The Claude Code settings files `plugins_enabled` reads, in the order a later one decides over an earlier one."""
    return [claude_config_dir() / "settings.json", root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]


def unreadable_claude_settings(root: Path) -> list[Path]:
    """The Claude Code settings files that exist but cannot be read, such as one without read permission, or, in the
    repository, a link, a pipe, or a device, which aidd never reads. Nothing is read to tell."""
    out = []
    for path in claude_settings_paths(root):
        if not os.path.lexists(path):
            continue
        if path.is_relative_to(root):
            raw, why = regular_files.named_file_bytes(root, path.relative_to(root).as_posix(), 0)
            if raw is None and why != regular_files.TOO_LARGE:
                out.append(path)
        elif not os.access(path, os.R_OK):
            out.append(path)
    return out


TEAM_PREFIX = "aidd-"  # `aidd init --aidd-team` installs each role as the project agent `aidd-<role>`

# The heading `aidd init --aidd-team` writes into AGENTS.md, for every harness: the short section that points to the roles.
TEAM_MARK = "<!-- aidd-team -->"


def plugin_enabled(root: Path) -> bool:
    """The aidd Claude Code plugin (`aidd@aidd`) is enabled for this project, read the way Claude Code reads it
    (`plugins_enabled`: the user's settings, then the project's, then the local ones, a later file deciding): its
    MCP server and skill then come from the plugin."""
    return f"aidd@{MARKETPLACE}" in plugins_enabled(root)
