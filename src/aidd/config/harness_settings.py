"""Claude Code's settings as aidd reads them: the settings files, the plugins they enable, and whether the aidd-team
roles are installed."""

from __future__ import annotations

import json
import os
from pathlib import Path

MARKETPLACE = "aidd"


def claude_config_dir() -> Path:
    """Claude Code's user folder: CLAUDE_CONFIG_DIR when set, else ~/.claude."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def plugins_enabled(root: Path) -> set[str]:
    """The plugins Claude Code enables in this repository, from `enabledPlugins` in the user's settings, then the
    project's `.claude/settings.json`, then `.claude/settings.local.json`: a later file decides over an earlier one.
    Managed settings and a plugin installed but not named in any of them are not seen."""
    return _enabled_in(claude_settings_paths(root))


def user_plugins_enabled() -> set[str]:
    """The plugins this user's own Claude Code settings enable: never what a repository's `.claude/` files say, so a
    repository cannot claim the aidd plugin to keep `aidd init` from wiring the guard."""
    return _enabled_in([claude_config_dir() / "settings.json"])


def _enabled_in(paths: list[Path]) -> set[str]:
    on: dict[str, bool] = {}
    for path in paths:
        try:
            enabled = json.loads(path.read_text(encoding="utf-8")).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(enabled, dict):
            on.update({k: v is True for k, v in enabled.items()})
    return {k for k, v in on.items() if v}


def claude_settings_paths(root: Path) -> list[Path]:
    """The Claude Code settings files `plugins_enabled` reads, in the order a later one decides over an earlier one."""
    return [claude_config_dir() / "settings.json", root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]


def unreadable_claude_settings(root: Path) -> list[Path]:
    """The Claude Code settings files that exist but cannot be read, such as one without read permission."""
    out = []
    for path in claude_settings_paths(root):
        try:
            path.read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            out.append(path)
    return out


TEAM_PREFIX = "aidd-"  # `aidd init --team` installs each role as the project agent `aidd-<role>`

# The heading `aidd init --team` writes into AGENTS.md, for every harness: the short section that points to the roles.
TEAM_MARK = "<!-- aidd-team -->"


def team_installed(root: str | Path) -> bool:
    """The aidd-team roles are here: `aidd init --team` left them (its AGENTS.md section, or Claude Code's role files),
    or Claude Code enables the aidd-team plugin here, reading the user's, the project's, and the local settings in the
    order it does (`plugins_enabled`). The guard, `aidd doctor`, and the next steps all ask this one question."""
    root = Path(root)
    if any((root / ".claude" / "agents").glob(f"{TEAM_PREFIX}*.md")):
        return True
    try:
        if TEAM_MARK in (root / "AGENTS.md").read_text(encoding="utf-8", errors="replace"):
            return True
    except OSError:
        pass
    return f"aidd-team@{MARKETPLACE}" in plugins_enabled(root)


def plugin_enabled(root: Path) -> bool:
    """The aidd Claude Code plugin (`aidd@aidd`) is enabled for this project, read the way Claude Code reads it
    (`plugins_enabled`: the user's settings, then the project's, then the local ones, a later file deciding): its
    hooks/hooks.json then carries the session hooks itself."""
    return f"aidd@{MARKETPLACE}" in plugins_enabled(root)
