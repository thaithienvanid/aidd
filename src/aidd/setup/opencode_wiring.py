"""OpenCode V2's guard: the plugin `.opencode/plugins/aidd.js`, written, checked, and removed.

OpenCode loads every plugin in `<project>/.opencode/plugins/` by itself. aidd's plugin (`templates/opencode/aidd.js`)
hooks `execute.before` on every tool call, sends the call to `aidd hook pre-tool` through this user's launcher, and
throws on a deny, which blocks the call and gives the agent the reason (`guard/dialects.OpenCode`). It fails open when
aidd cannot run, unless the project fails closed. On Windows the launcher is an sh script, so init leaves the plugin
out there. This module imports neither `adoption` nor `doctor`.
"""

from __future__ import annotations

import os
from pathlib import Path

from aidd import config
from aidd.kernel import repo_paths, resources
from aidd.setup import hook_wiring

PLUGIN_FILE = ".opencode/plugins/aidd.js"
SETUP = "aidd init --harness opencode"
_MARK = "aidd's guard for OpenCode V2"


def plugin_text() -> str:
    """The plugin as init writes it."""
    text = (resources.data_dir("templates") / "opencode" / "aidd.js").read_text(encoding="utf-8")
    return text.replace("__FAIL_CLOSED_PROFILES__", "|".join(config.FAIL_CLOSED_PROFILES))


def install(root: Path, actions: list[str]) -> None:
    """Write the plugin, and this user's launcher. Skipped on Windows."""
    path = root / PLUGIN_FILE
    if os.name == "nt":
        actions.append(f"skipped  {PLUGIN_FILE} (on Windows the aidd launcher is an sh script, which the plugin cannot start)")
        return
    hook_wiring.install_user_launcher(root, hook_wiring.launcher(), actions)
    text = plugin_text()
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        actions.append(f"kept     {repo_paths.shown(path)} (the aidd guard is there)")
        return
    verb = "updated " if path.exists() else "wrote   "
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    actions.append(f"{verb} {repo_paths.shown(path)} (the guard on every tool call)")


def state(root: Path) -> str:
    """`current` when the plugin is the one init writes, `stale` when it is an older aidd's, `missing` otherwise."""
    path = root / PLUGIN_FILE
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    if text == plugin_text():
        return "current"
    return "stale" if _MARK in text else "missing"


def uninstall(root: Path, actions: list[str], *, yes: bool, verb: str, keep) -> None:
    """Remove the plugin when it is aidd's."""
    path = root / PLUGIN_FILE
    if not path.is_file():
        return
    if _MARK not in path.read_text(encoding="utf-8", errors="replace"):
        keep(path, "not aidd's plugin")
        return
    actions.append(f"{verb} {repo_paths.shown(path)}")
    if yes:
        path.unlink()
