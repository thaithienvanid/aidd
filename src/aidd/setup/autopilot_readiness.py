"""`aidd doctor --autopilot`: the settings an autopilot run needs, as far as aidd can see them.

aidd reads the repository's own files and this process's environment. It checks the hooks level, that the edit-time
guard is wired, that the deploy tooling it finds has held commands, that no variable named like a credential
reaches the agent (by name only: it never reads a value), and that Claude Code's permissions allow what the run runs
(aidd itself and aidd's read-only MCP tools) and never skip every check. What lives in the harness or the machine, such as the
sandbox and the permission mode, it cannot see, so it lists them for a person to check. It also says whether Claude Code's
advisor is configured (`advisorModel` in the settings files aidd can read), as information only: the advisor is
optional and experimental, and never a warning when it is absent.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from aidd import config
from aidd.kernel import git
from aidd.kernel.processes import CREDENTIAL_NAME
from aidd.setup import detection, hook_wiring

AUTOPILOT_CHECKLIST_TITLE = "What aidd cannot see; check these yourself before an autopilot run:"
AUTOPILOT_CHECKLIST: tuple[str, ...] = (
    "the sandbox is on wherever aidd cannot read the settings, such as managed settings",
    "the permission mode asks or denies what the settings do not allow (`dontAsk` for a run with nobody at the keyboard)",
    "the network reaches only what the work needs, from an allowlist",
    "for a team, managed settings hold these, so a project file cannot turn them off",
)
MAX_NAMES = 10
ADVISOR_KEY = "advisorModel"
ADVISOR_OFF_ENV = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"
ADVISOR_LIMITS = "optional and experimental, on the Anthropic API only"


def _guard_wired(root: Path) -> bool:
    """The guard runs: a PreToolUse hook runs `aidd hook pre-tool`, or the aidd plugin is on (its hooks carry it)."""
    if config.plugin_enabled(root):
        return True
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((root / ".claude" / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = (data.get("hooks") or {}).get("PreToolUse") or [] if isinstance(data, dict) else []
        if any(
            hook_wiring.aidd_hook(h.get("command")) == "pre-tool" for e in entries if isinstance(e, dict) for h in e.get("hooks") or [] if isinstance(h, dict)
        ):
            return True
    return False


# What an autopilot run calls on every step: under a permission mode that denies what the settings do not allow
# (`dontAsk`, as a run with nobody at the keyboard needs), each must be allowed, or the step stops on a denial. Found
# in real runs: reads and edits of the project's files (the guard still checks each edit's scope), aidd itself, aidd's
# read-only MCP tools, and the team plugin's flow files, outside the project. The decision tools (approve_*, ship,
# proposal_*) are left out: they ask the person in a dialog, which no rule replaces.
READ_ONLY_TOOLS = ("gate", "check_edit", "validate", "describe", "approval_line")
COMMAND_RULE = "Bash(aidd *)"
PROJECT_RULES = ("Read(/**)", "Edit(/**)")
SKIPS_EVERY_CHECK = "bypassPermissions"


def _settings(root: Path) -> list[dict]:
    """Every Claude Code settings file aidd can read, in the order a later one decides."""
    out = []
    for path in config.claude_settings_paths(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def sandbox_on(root: Path) -> bool:
    """Whether the settings aidd can read turn Claude Code's sandbox on (`sandbox.enabled`, a later file deciding)."""
    on = False
    for data in _settings(root):
        box = data.get("sandbox")
        if isinstance(box, dict) and isinstance(box.get("enabled"), bool):
            on = box["enabled"]
    return on


def _permissions(root: Path) -> tuple[set[str], str | None]:
    """The `permissions.allow` rules of every Claude Code settings file aidd can read, and the `defaultMode` the last
    of them sets (a later file decides)."""
    allowed: set[str] = set()
    mode: str | None = None
    for data in _settings(root):
        perms = data.get("permissions")
        if not isinstance(perms, dict):
            continue
        allowed |= {r for r in perms.get("allow") or [] if isinstance(r, str)}
        if isinstance(perms.get("defaultMode"), str):
            mode = perms["defaultMode"]
    return allowed, mode


def _mcp_server(root: Path) -> str | None:
    """How Claude Code names aidd's MCP tools here: `mcp__plugin_aidd_aidd` for the plugin, `mcp__aidd` for a project
    `.mcp.json` server named `aidd`, or None when neither is wired."""
    if config.plugin_enabled(root):
        return "mcp__plugin_aidd_aidd"
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError, AttributeError):
        return None
    return "mcp__aidd" if isinstance(servers, dict) and "aidd" in servers else None


def needed_rules(root: Path) -> list[str]:
    """The `permissions.allow` rules an autopilot run needs and the settings do not have yet, in the order to add them."""
    allowed, _ = _permissions(root)
    out = [r for r in PROJECT_RULES if r not in allowed and r.split("(", 1)[0] not in allowed]
    out += [] if allowed & {COMMAND_RULE, "Bash(aidd:*)", "Bash(aidd*)", "Bash"} else [COMMAND_RULE]
    if f"aidd-team@{config.MARKETPLACE}" in config.plugins_enabled(root) and (rule := _plugins_rule()) not in allowed and "Read" not in allowed:
        out.append(rule)
    if server := _mcp_server(root):
        whole = {server, f"{server}__*"}
        out += [f"{server}__{name}" for name in READ_ONLY_TOOLS if not allowed & (whole | {f"{server}__{name}"})]
    return out


def _plugins_rule() -> str:
    """Reading the installed plugins' files, where the team plugin keeps the flow each autopilot step runs."""
    folder = config.claude_config_dir() / "plugins"
    home = Path.home()
    return f"Read(~/{folder.relative_to(home).as_posix()}/**)" if folder.is_relative_to(home) else f"Read(/{folder.as_posix()}/**)"


def folder_trusted(root: Path) -> bool | None:
    """Whether Claude Code trusts the folder (`projects.<path>.hasTrustDialogAccepted` in its own `.claude.json`), read
    only: until it does, it ignores the project's `permissions.allow`. None when aidd cannot read the record."""
    home = Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser() if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home()
    try:
        projects = json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("projects") or {}
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(projects, dict):
        return None
    for key in {str(root), str(root.resolve())}:
        entry = projects.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("hasTrustDialogAccepted"), bool):
            return entry["hasTrustDialogAccepted"]
    return False


def permission_checks(root: Path) -> list[tuple[str, str]]:
    """(level, message) for Claude Code's permissions: never a mode that skips every check, and an allow rule for each
    thing an autopilot run calls (needed_rules), printed for a person to add: aidd never writes the settings."""
    _, mode = _permissions(root)
    out: list[tuple[str, str]] = []
    if sandbox_on(root):
        out.append(("ok", "the sandbox is on (`sandbox.enabled`): the agents' shell commands run inside it, with no one asked"))
    else:
        out.append(
            (
                "warn",
                "the sandbox is off in the settings aidd can read: set `sandbox.enabled: true`. Without it, a run with nobody to "
                "ask (`dontAsk`) is denied every shell command its allow rules do not match, such as a test piped to `tail`",
            )
        )
    if mode == SKIPS_EVERY_CHECK:
        out.append(("fail", f"`permissions.defaultMode` is `{SKIPS_EVERY_CHECK}`, which skips every check: use `dontAsk` or `default`"))
    missing = needed_rules(root)
    if missing:
        rules = ", ".join(json.dumps(r) for r in missing)
        out.append(
            (
                "warn",
                f"Claude Code's permissions do not allow what an autopilot run calls on every step, so a run with nobody to ask "
                f"(`dontAsk`) stops on a denial. Add to `permissions.allow` in .claude/settings.json: [{rules}]. Claude Code "
                "applies a project's allow rules once you trust the folder: run Claude Code there once and accept",
            )
        )
    else:
        out.append(("ok", "the permissions allow what an autopilot run calls on every step: the project's files, aidd, and its read-only tools"))
    trusted = folder_trusted(root)
    if trusted is False:
        out.append(
            (
                "warn",
                "Claude Code does not trust this folder yet, so it ignores the project's `permissions.allow`: run Claude Code here "
                "once and accept the trust dialog",
            )
        )
    elif trusted:
        out.append(("ok", "Claude Code trusts this folder, so it applies the project's permission rules"))
    return out


def credential_names(env: dict[str, str] | None = None) -> list[str]:
    """The names of the variables that look like credentials (processes.CREDENTIAL_NAME). Never their values."""
    return sorted(k for k in (os.environ if env is None else env) if CREDENTIAL_NAME.search(k))


def autopilot_checks(root: Path, env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(level, message) for each check aidd can make: ok, warn, or fail."""
    out: list[tuple[str, str]] = []
    if not (root / config.CONFIG_PATH).is_file():
        return [("fail", "aidd is not set up here: run `aidd init` first")]
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (config.ConfigError, OSError, ValueError) as exc:
        return [("fail", f"the config does not load: {exc}")]
    level = config.hook_level(cfg.raw)
    if level == "minimal":
        out.append(("warn", "the hooks level is minimal, so no stop reminder runs: set `hooks.level` to `balanced` or `strict`"))
    else:
        out.append(("ok", f"the hooks level is {level}"))
    if _guard_wired(root):
        out.append(("ok", "the guard is wired (aidd hook pre-tool)"))
    else:
        out.append(("fail", "the guard is not wired: run `aidd init --agent-hooks`, or turn on the aidd plugin"))
    tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    found, _ = detection.held_commands(root, tracked)
    held = cfg.get("guard", "held_commands", default=[]) or []
    if found and not held:
        names = ", ".join(e["name"] for e in found[:3])
        out.append(("warn", f"deploy tooling is here ({names}) but `guard.held_commands` holds nothing: `aidd init --dry-run` prints the entries"))
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
    return out + permission_checks(root)


def advisor_model(root: Path) -> str | None:
    """Claude Code's `advisorModel` from the user's, the project's, and the local settings (a later file decides), or
    None. Managed settings and the `--advisor` flag are not seen."""
    found: str | None = None
    for path in config.claude_settings_paths(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = data.get(ADVISOR_KEY) if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            found = value.strip()
    return found


def autopilot_advisor_line(root: Path, env: Mapping[str, str] | None = None) -> str:
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
