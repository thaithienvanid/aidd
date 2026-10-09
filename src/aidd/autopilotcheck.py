"""`aidd doctor --autopilot` (experimental): the settings an autopilot run needs, as far as aidd can see them.

aidd reads the repository's own files and this process's environment. It checks the hooks level, that the edit-time
guard is wired, that the deploy tooling it finds has held commands, and that no variable named like a credential
reaches the agent (by name only: it never reads a value). What lives in the harness or the machine, such as the
sandbox and the permission mode, it cannot see, so it lists them for a person to check. It also says whether Claude Code's
advisor is configured (`advisorModel` in the settings files aidd can read), as information only: the advisor is
optional and experimental, and never a warning when it is absent.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from . import config as cfgmod
from . import detect, gitutil, hooks, repo
from .util import CREDENTIAL_NAME

CHECKLIST_TITLE = "What aidd cannot see; check these yourself before an autopilot run:"
CHECKLIST = (
    "the harness runs the agent's commands in its sandbox",
    "the permission mode asks or denies what the settings do not allow; never a mode that skips every check",
    "the network reaches only what the work needs, from an allowlist",
    "for a team, managed settings hold these, so a project file cannot turn them off",
)
MAX_NAMES = 10
ADVISOR_KEY = "advisorModel"
ADVISOR_OFF_ENV = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"
ADVISOR_LIMITS = "optional and experimental, on the Anthropic API only"


def _guard_wired(root: Path) -> bool:
    """The guard runs: a PreToolUse hook runs `aidd hook pre-tool`, or the aidd plugin is on (its hooks carry it)."""
    if repo.plugin_enabled(root):
        return True
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((root / ".claude" / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = (data.get("hooks") or {}).get("PreToolUse") or [] if isinstance(data, dict) else []
        if any(repo.aidd_hook(h.get("command")) == "pre-tool" for e in entries if isinstance(e, dict) for h in e.get("hooks") or [] if isinstance(h, dict)):
            return True
    return False


def credential_names(env: dict[str, str] | None = None) -> list[str]:
    """The names of the variables that look like credentials (util.CREDENTIAL_NAME). Never their values."""
    return sorted(k for k in (os.environ if env is None else env) if CREDENTIAL_NAME.search(k))


def checks(root: Path, env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(level, message) for each check aidd can make: ok, warn, or fail."""
    out: list[tuple[str, str]] = []
    if not (root / cfgmod.CONFIG_PATH).is_file():
        return [("fail", "aidd is not set up here: run `aidd init` first")]
    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
    except (cfgmod.ConfigError, OSError, ValueError) as exc:
        return [("fail", f"the config does not load: {exc}")]
    level = hooks.level(cfg)
    if level == "minimal":
        out.append(("warn", 'the hooks level is minimal, so no stop reminder runs: set [hooks] level = "balanced" or "strict"'))
    else:
        out.append(("ok", f"the hooks level is {level}"))
    if _guard_wired(root):
        out.append(("ok", "the guard is wired (aidd hook pre-tool)"))
    else:
        out.append(("fail", "the guard is not wired: run `aidd init --agent-hooks`, or turn on the aidd plugin"))
    tracked = [p for p in gitutil.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    found, _ = detect.held_commands(root, tracked)
    held = cfg.get("guard", "held_commands", default=[]) or []
    if found and not held:
        names = ", ".join(e["name"] for e in found[:3])
        out.append(("warn", f"deploy tooling is here ({names}) but [[guard.held_commands]] holds nothing: `aidd init --dry-run` prints the entries"))
    elif found:
        out.append(("ok", f"{len(held)} held command{'s' if len(held) != 1 else ''} for the deploy tooling found"))
    else:
        out.append(("ok", "no deploy tooling found, so no held command is needed"))
    creds = credential_names(env)
    if creds:
        shown = ", ".join(creds[:MAX_NAMES]) + (f", and {len(creds) - MAX_NAMES} more" if len(creds) > MAX_NAMES else "")
        out.append(("warn", f"{len(creds)} variable{'s' if len(creds) != 1 else ''} named like a credential reach the agent: {shown}. Unset them for the run"))
    else:
        out.append(("ok", "no variable named like a credential (names only; aidd never reads a value)"))
    return out


def advisor_model(root: Path) -> str | None:
    """Claude Code's `advisorModel` from the user's, the project's, and the local settings (a later file decides), or
    None. Managed settings and the `--advisor` flag are not seen."""
    found: str | None = None
    for path in repo.claude_settings_paths(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = data.get(ADVISOR_KEY) if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            found = value.strip()
    return found


def advisor_line(root: Path, env: Mapping[str, str] | None = None) -> str:
    """One line of information about the advisor for an autopilot run; never a warning."""
    environ: Mapping[str, str] = os.environ if env is None else env
    model = advisor_model(root)
    if model and environ.get(ADVISOR_OFF_ENV):
        return f"{ADVISOR_KEY} = {model} is set, but {ADVISOR_OFF_ENV} turns it off for this environment"
    if model:
        return (
            f"an advisor is configured ({ADVISOR_KEY} = {model}), {ADVISOR_LIMITS}: a second opinion inside one session, never a "
            "substitute for the verifier, the reviewer, or independent review. Count its tokens in `aidd autopilot note --tokens`"
        )
    return f"no advisor is configured ({ADVISOR_KEY}): {ADVISOR_LIMITS}; the harness profile recommends one for an autopilot run"
