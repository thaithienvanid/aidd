"""A hooks file in Claude Code's shape, for a harness that reads one (Grok Build, Codex): written, checked, and removed.

The file holds a `hooks` object: `PreToolUse` groups of `{matcher, hooks}`, and the session events as handler groups.
aidd owns only its own handlers (each runs `aidd hook <name>`): init replaces those and keeps every other hook in the
file, and uninstall removes only them. A guard that cannot run writes nothing (an empty decision fails open), or a
`permissionDecision` deny where the project fails closed (`hook_wiring.fail_closed_test`). On Windows the commands are
sh, so init leaves the file alone there. This module imports neither `adoption` nor `doctor`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from aidd.kernel import repo_paths
from aidd.setup import hook_wiring

MATCHER = "*"
EVENTS = {"PreToolUse": "pre-tool", **hook_wiring.SESSION_EVENTS}
GUARD_TIMEOUT_SECONDS = 20
_FAIL_CLOSED_DENY = (
    '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",'
    '"permissionDecisionReason":"aidd: the guard could not run on this machine, and this project requires it"}}'
)


@dataclass(frozen=True)
class HooksFile:
    path: str  # the file, from the repository's top
    setup: str  # the command that writes it
    label: str  # the harness, for the messages
    from_subfolders: bool = False  # the harness may run a hook from a folder below the project's top (Codex: the session's)

    def hook_command(self, sub: str) -> str:
        """The command for one aidd hook: the user launcher, and nothing when it cannot run. The fallback reads
        `.aidd/config.yaml` in the folder the hook runs from, or, where the harness may run it from a subfolder, in the
        nearest folder above that holds one (shell builtins only, as `fail_closed_test` reads it)."""
        if sub == "pre-tool":
            config = ".aidd/config.yaml"
            find = ""
            if self.from_subfolders:
                config = '"$d/.aidd/config.yaml"'
                find = 'unset -f test 2>/dev/null; d=$PWD; while test -n "$d" && ! test -r "$d/.aidd/config.yaml"; do d=${d%/*}; done; '
            fallback = (
                f'echo "aidd: the guard could not run on this machine: run {self.setup}, and aidd doctor says why" >&2; '
                f"{find}if {hook_wiring.fail_closed_test(config)}; then echo '{_FAIL_CLOSED_DENY}'; fi"
            )
            return f"{hook_wiring.HOOK_LAUNCHER} hook pre-tool || {{ {fallback}; }}"
        return f"{hook_wiring.HOOK_LAUNCHER} hook {sub} || true"

    def _handler(self, sub: str) -> dict:
        timeout = GUARD_TIMEOUT_SECONDS if sub == "pre-tool" else hook_wiring.SESSION_HOOK_TIMEOUT_SECONDS
        return {"type": "command", "command": self.hook_command(sub), "timeout": timeout}

    def hook_spec(self) -> dict:
        """aidd's own entries, one per event."""
        spec: dict = {"PreToolUse": [{"matcher": MATCHER, "hooks": [self._handler("pre-tool")]}]}
        for event, sub in hook_wiring.SESSION_EVENTS.items():
            spec[event] = [{"hooks": [self._handler(sub)]}]
        return spec

    def _read(self, root: Path) -> dict | None:
        """The file as a JSON object; {} when there is none, None when it is not one."""
        path = root / self.path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def install(self, root: Path, actions: list[str]) -> None:
        """Write aidd's hooks into the file, and this user's launcher, keeping every other hook. Skipped on Windows."""
        path = root / self.path
        if os.name == "nt":
            actions.append(f"skipped  {self.path} (Windows has no sh hook; {self.label} would run these commands with sh)")
            return
        hook_wiring.install_user_launcher(root, hook_wiring.launcher(), actions)
        data = self._read(root)
        if data is None:
            actions.append(f"warn     {repo_paths.shown(path)} is not a JSON object; add the aidd hooks by hand (`aidd doctor` shows it)")
            return
        hooks: dict = data["hooks"] if isinstance(data.get("hooks"), dict) else {}
        merged = _without_aidd(hooks)
        for event, entries in self.hook_spec().items():
            merged[event] = merged.get(event, []) + entries
        if merged == hooks:
            actions.append(f"kept     {repo_paths.shown(path)} (the aidd hooks are there)")
            return
        verb = "updated " if path.exists() else "wrote   "
        data["hooks"] = merged
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        actions.append(f"{verb} {repo_paths.shown(path)} (the guard on every tool call, and {', '.join(hook_wiring.SESSION_EVENTS)})")

    def configured(self, root: Path) -> dict | None:
        """The `hooks` object in the file as it stands, or None when there is none."""
        spec = (self._read(root) or {}).get("hooks")
        return spec if isinstance(spec, dict) else None

    def wired(self, root: Path) -> dict[str, str]:
        """Each event the file wires to an aidd hook, with its command, whatever the commands are."""
        spec = self.configured(root)
        if spec is None:
            return {}
        out: dict[str, str] = {}
        for event, sub in EVENTS.items():
            command = next((h["command"] for h in _handlers(spec.get(event)) if hook_wiring.aidd_hook(h.get("command")) == sub), None)
            if command:
                out[event] = command
        return out

    def uninstall(self, root: Path, actions: list[str], *, yes: bool, verb: str, keep) -> None:
        """Remove aidd's hooks from the file, and the file when nothing else is left in it."""
        path = root / self.path
        if not path.is_file():
            return
        data = self._read(root)
        if data is None:
            keep(path, "not a JSON object; remove the aidd hooks by hand")
            return
        hooks = data.get("hooks")
        if not isinstance(hooks, dict) or not self.wired(root):
            return
        actions.append(f"{verb} the aidd hooks from {repo_paths.shown(path)}")
        if not yes:
            return
        rest = _without_aidd(hooks)
        if rest:
            data["hooks"] = rest
        else:
            data.pop("hooks", None)
        if data:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            path.unlink()


def _handlers(entries) -> list[dict]:
    groups = entries if isinstance(entries, list) else []
    return [h for g in groups if isinstance(g, dict) for h in (g.get("hooks") or []) if isinstance(h, dict)]


def _without_aidd(hooks: dict) -> dict:
    """`hooks` with every handler that runs an aidd hook taken out, and the groups and events it leaves empty."""
    out: dict = {}
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            out[event] = entries
            continue
        kept = []
        for group in entries:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept.append(group)
                continue
            rest = [h for h in group["hooks"] if not (isinstance(h, dict) and hook_wiring.aidd_hook(h.get("command")))]
            if rest:
                kept.append({**group, "hooks": rest})
        if kept:
            out[event] = kept
    return out
