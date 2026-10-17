"""Codex's hooks: the guard and the session hooks in `.codex/hooks.json`, written, checked, and removed.

Codex reads `<project>/.codex/hooks.json` in Claude Code's shape (`hooks_file`; https://learn.chatgpt.com/docs/hooks),
and runs each command from the session's folder, which may sit below the project's top. The file may hold the person's own hooks too: init keeps them. Codex
loads a project's hooks only once the person trusts the project, and runs each new or changed hook only once they
review it in `/hooks`.
"""

from __future__ import annotations

from aidd.setup import hooks_file

FILE = hooks_file.HooksFile(".codex/hooks.json", "aidd init --harness codex", "Codex", from_subfolders=True)
HOOKS_FILE, SETUP, EVENTS = FILE.path, FILE.setup, hooks_file.EVENTS
hook_command, install, wired, uninstall = FILE.hook_command, FILE.install, FILE.wired, FILE.uninstall
