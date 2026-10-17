"""Grok Build's hooks: the guard and the session hooks in `.grok/hooks/aidd.json`, written, checked, and removed.

Grok discovers `<project>/.grok/hooks/*.json` and reads Claude Code's shape (`hooks_file`). The matcher is `*`, because
Grok's `Write` matcher does not select the separate `write` tool. The hook is inert until the person trusts the folder.
"""

from __future__ import annotations

from aidd.setup import hooks_file

FILE = hooks_file.HooksFile(".grok/hooks/aidd.json", "aidd init --harness grok-build", "Grok Build")
HOOKS_FILE, SETUP, MATCHER, EVENTS = FILE.path, FILE.setup, hooks_file.MATCHER, hooks_file.EVENTS
GUARD_TIMEOUT_SECONDS = hooks_file.GUARD_TIMEOUT_SECONDS
hook_command, hook_spec, install, configured, wired, uninstall = (
    FILE.hook_command,
    FILE.hook_spec,
    FILE.install,
    FILE.configured,
    FILE.wired,
    FILE.uninstall,
)
