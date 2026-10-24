"""OpenCode V2: the guard plugin `.opencode/plugins/aidd.js` and its terminal half `.opencode/plugins/aidd-tui/`,
written, checked, and removed.

OpenCode loads every plugin in `<project>/.opencode/plugins/` by itself. aidd's bare plugin (`templates/opencode/aidd.js`)
hooks `execute.before` on every tool call, `create.before` on every shell OpenCode creates, `prompt` on the person's
prompt, and `compaction` on a compaction, and reads the bus for a finished turn (`session.execution.succeeded`) and an
ended compaction, and sends each to `aidd hook` through this user's launcher: a deny throws, which blocks the call and
gives the agent the reason (`guard/dialects.OpenCode`); the stop reminder and the note after a compaction join the
session as synthetic messages. It fails open when aidd cannot run,
unless the project fails closed. The terminal half is a plugin directory beside it: `tui.tsx` puts `/aidd status`,
`/aidd approve`, `/aidd land`, `/aidd publish`, `/aidd merge`, `/aidd decide`, `/aidd sign-off`, `/aidd update`, and `/aidd init` in the
terminal, `status.js` holds the pure half the
tests run, and `index.ts` keeps the directory a plugin OpenCode discovers. This module imports neither `adoption` nor
`doctor`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from aidd import config
from aidd.kernel import repo_paths, resources
from aidd.setup import guard_message, hook_wiring

PLUGIN_FILE = ".opencode/plugins/aidd.js"
TUI_DIR = ".opencode/plugins/aidd-tui"
INDEX_FILE = f"{TUI_DIR}/index.ts"
TUI_FILE = f"{TUI_DIR}/tui.tsx"
STATUS_FILE = f"{TUI_DIR}/status.js"
SETUP = "aidd init --harness opencode"
# The OpenCode the plugin contract above was checked against (https://opencode.ai/v2/docs), for the docs and the runbook.
OPENCODE_VERSION = "2.1.0"
_MARK = "aidd's guard for OpenCode V2"


def _template(*parts: str) -> str:
    return resources.data_dir("templates").joinpath("opencode", *parts).read_text(encoding="utf-8")


def plugin_text() -> str:
    """The guard plugin as init writes it."""
    text = _template("aidd.js").replace("__FAIL_CLOSED_PROFILES__", "|".join(config.FAIL_CLOSED_PROFILES))
    text = text.replace("__FAIL_CLOSED_MODES__", "|".join(config.FAIL_CLOSED_MODES))
    return text.replace("__GUARD_MISSING__", guard_message.guard_missing_message(SETUP))


def index_text() -> str:
    """The server half of the terminal plugin: a no-op that keeps the directory discoverable."""
    return _template("aidd-tui", "index.ts")


def tui_text() -> str:
    """The terminal wiring, which only OpenCode's own TUI can load."""
    return _template("aidd-tui", "tui.tsx")


def status_text() -> str:
    """The pure half: the verbs, the argv each runs, and the lines the terminal draws."""
    return _template("aidd-tui", "status.js")


def files() -> dict[str, str]:
    """Every file `aidd init --harness opencode` writes here, as repo-relative path -> text."""
    return {PLUGIN_FILE: plugin_text(), INDEX_FILE: index_text(), TUI_FILE: tui_text(), STATUS_FILE: status_text()}


def _same(root: Path, rel: str, text: str) -> bool:
    path = root / rel
    return path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text


def install(root: Path, actions: list[str]) -> None:
    """Write the plugin, its terminal half, and this user's launcher (on Windows the `aidd.cmd` the plugin starts)."""
    hook_wiring.install_user_launcher(root, hook_wiring.launcher(), actions)
    for rel, text in files().items():
        path = root / rel
        if _same(root, rel, text):
            actions.append(f"kept     {repo_paths.shown(path)} (the aidd guard is there)")
            continue
        verb = "updated " if path.exists() else "wrote   "
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        why = "the guard on every tool call and every shell" if rel == PLUGIN_FILE else "`/aidd status` and the approvals, in the terminal"
        actions.append(f"{verb} {repo_paths.shown(path)} ({why})")


def state(root: Path) -> str:
    """`current` when every file is the one init writes, `stale` when the plugin is aidd's but any file is an older aidd's
    or gone (so `aidd upgrade` writes them all again, never leaving an old guard in place), `missing` when the plugin is
    gone or not aidd's at all."""
    written = files()
    if all(_same(root, rel, text) for rel, text in written.items()):
        return "current"
    plugin = root / PLUGIN_FILE
    if plugin.is_file() and _MARK in plugin.read_text(encoding="utf-8", errors="replace"):
        return "stale"  # aidd's plugin, older or with a file gone: `aidd upgrade` writes them all again
    return "missing"


def uninstall(root: Path, actions: list[str], *, yes: bool, verb: str, keep) -> None:
    """Remove the plugin when it is aidd's, and the terminal directory beside it."""
    path = root / PLUGIN_FILE
    if path.is_file():
        if _MARK not in path.read_text(encoding="utf-8", errors="replace"):
            keep(path, "not aidd's plugin")
        else:
            actions.append(f"{verb} {repo_paths.shown(path)}")
            if yes:
                path.unlink()
    tui = root / TUI_DIR
    if tui.is_dir():
        actions.append(f"{verb} {repo_paths.shown(tui)}")
        if yes:
            shutil.rmtree(tui)
