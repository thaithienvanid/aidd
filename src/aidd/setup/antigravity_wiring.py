"""Google Antigravity's hooks: the guard and the session hooks in `.agents/hooks.json`, written, checked, and removed.

Antigravity's file maps a hook name to its events (https://antigravity.google/docs/hooks, and the copy `agy` ships):
`PreToolUse` takes `{matcher, hooks}` groups, and `SessionStart`, `PreInvocation`, and `Stop` take handler objects
directly. aidd writes one hook name, `aidd`, and never touches another. Each command runs through `sh -c` from the
`.agents/` folder; the hooks read the workspace from the event. A hook must answer with a JSON object: a guard that
cannot run answers `{"decision": "ask"}` (Antigravity asks the person; it denies an empty decision), or a deny where
the project fails closed (`hook_wiring.fail_closed_test`). Antigravity reads MCP servers only from the user's config or a plugin, so init writes none.
On Windows Antigravity runs a hook with `cmd /c`, and these commands are sh, so init leaves the file alone there.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from aidd.kernel import repo_paths
from aidd.setup import guard_message, hook_wiring

HOOKS_FILE = ".agents/hooks.json"
HOOK_NAME = "aidd"
# Every tool call, so a tool aidd does not know still reaches the guard (Antigravity's matcher is a Go regular
# expression, which cannot say "all but the reads"). The guard answers each: dialects.Antigravity.no_opinion.
MATCHER = "*"
SESSION_EVENTS = {"SessionStart": "session-start", "PreInvocation": "prompt-submit", "Stop": "stop"}
EVENTS = {"PreToolUse": "pre-tool", **SESSION_EVENTS}
GUARD_TIMEOUT_SECONDS = 20
SETUP = "aidd init --harness antigravity"
_NO_OPINION = '{"decision":"ask"}'
_FAIL_CLOSED_DENY = '{"decision":"deny","reason":"' + guard_message.guard_missing_message(SETUP) + '"}'


def hook_command(sub: str) -> str:
    """The `.agents/hooks.json` command for one aidd hook: the user launcher, and a JSON answer when it cannot run."""
    if sub == "pre-tool":
        fallback = (
            f'echo "{guard_message.guard_missing_message(SETUP)}" >&2; '
            f"if {hook_wiring.fail_closed_test('../.aidd/config.yaml')}; then echo '{_FAIL_CLOSED_DENY}'; else echo '{_NO_OPINION}'; fi"
        )
        return f"{hook_wiring.HOOK_LAUNCHER} hook pre-tool || {{ {fallback}; }}"
    return f"{hook_wiring.HOOK_LAUNCHER} hook {sub} || echo '{{}}'"


def _handler(sub: str) -> dict:
    timeout = GUARD_TIMEOUT_SECONDS if sub == "pre-tool" else hook_wiring.SESSION_HOOK_TIMEOUT_SECONDS
    return {"type": "command", "command": hook_command(sub), "timeout": timeout}


def hook_spec() -> dict:
    """The `aidd` entry init writes in `.agents/hooks.json`."""
    spec: dict = {"PreToolUse": [{"matcher": MATCHER, "hooks": [_handler("pre-tool")]}]}
    for event, sub in SESSION_EVENTS.items():
        spec[event] = [_handler(sub)]
    return spec


def _read(path: Path) -> dict | None:
    """The hooks file as a JSON object; {} when there is none, None when it is not one."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def install(root: Path, actions: list[str]) -> None:
    """Write the `aidd` hook in `.agents/hooks.json`, merged with the file's other hooks, and this user's launcher."""
    path = root / HOOKS_FILE
    if os.name == "nt":
        actions.append(f"skipped  {HOOKS_FILE} (Antigravity runs hooks with cmd on Windows, and aidd's hook commands are sh)")
        return
    hook_wiring.install_user_launcher(root, hook_wiring.launcher(), actions)
    data = _read(path)
    if data is None:
        actions.append(f"warn     {repo_paths.shown(path)} is not a JSON object; add the `{HOOK_NAME}` hook by hand (`aidd doctor` shows it)")
        return
    if data.get(HOOK_NAME) == hook_spec():
        actions.append(f"kept     {repo_paths.shown(path)} (the aidd hooks are there)")
        return
    verb = "updated " if path.exists() else "wrote   "
    data[HOOK_NAME] = hook_spec()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    actions.append(f"{verb} {repo_paths.shown(path)} (the guard on every tool call, and {', '.join(SESSION_EVENTS)})")


def configured(root: Path) -> dict | None:
    """The `aidd` entry in `.agents/hooks.json` as it stands, or None when there is none."""
    spec = (_read(root / HOOKS_FILE) or {}).get(HOOK_NAME)
    return spec if isinstance(spec, dict) else None


def matcher(root: Path) -> str | None:
    """The `aidd` hook's PreToolUse matcher in `.agents/hooks.json`, or None when it has none."""
    spec = configured(root) or {}
    groups = [g for g in (spec.get("PreToolUse") or []) if isinstance(g, dict)] if isinstance(spec.get("PreToolUse"), list) else []
    return next((g["matcher"] for g in groups if isinstance(g.get("matcher"), str)), None)


def wired(root: Path) -> dict[str, str]:
    """Each event the `aidd` hook in `.agents/hooks.json` wires, with its command, whatever the commands are; none when
    the hook is turned off (`"enabled": false`)."""
    spec = configured(root)
    if spec is None or spec.get("enabled") is False:
        return {}
    out: dict[str, str] = {}
    for event, sub in EVENTS.items():
        entries: list = spec[event] if isinstance(spec.get(event), list) else []
        groups = [e for e in entries if isinstance(e, dict)]
        handlers = [h for g in groups for h in ((g.get("hooks") or []) if event == "PreToolUse" else [g]) if isinstance(h, dict)]
        command = next((h["command"] for h in handlers if hook_wiring.aidd_hook(h.get("command")) == sub), None)
        if command:
            out[event] = command
    return out


def uninstall(root: Path, actions: list[str], *, yes: bool, verb: str, keep) -> None:
    """Remove the `aidd` hook from `.agents/hooks.json`, and the file when nothing else is in it."""
    path = root / HOOKS_FILE
    if not path.is_file():
        return
    data = _read(path)
    if data is None:
        keep(path, "not a JSON object; remove the aidd hook by hand")
        return
    if HOOK_NAME not in data:
        return
    actions.append(f"{verb} the aidd hooks from {repo_paths.shown(path)}")
    if yes:
        del data[HOOK_NAME]
        if data:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            path.unlink()
