"""What a standing delegation adds to Claude Code's project settings, the one harness that answers a delegated ask in
this version: a `PermissionRequest` hook and a `PreToolUse` hook that run `aidd delegate hook`, and three ask rules.
The ask rules keep every delegated command, and the delegate's answer tool, on the prompt path, so the hook answers
only a prompt they raise. Every other ask rule stays as it was. aidd lists what it wrote under `claude-code-delegation`
in `.aidd/harness-rules.json`, and changes only those entries, never a person's own."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from aidd import config
from aidd.kernel import git, globs, resources
from aidd.setup import mcp_wiring

SETTINGS = ".claude/settings.json"
LEDGER_KEY = "claude-code-delegation"
# The hook runs this user's pinned launcher, `~/.aidd/bin/aidd`, which `aidd init` writes (mcp_wiring), and never searches
# PATH, so no `aidd` a repository plants, on a relative entry such as `node_modules/.bin` or a link, can answer. A missing
# launcher exits 127 with no output: no decision, so the prompt stays.
HOOK_COMMAND = f"/bin/sh -c 'exec {mcp_wiring.SH_LAUNCHER} delegate hook'"
# The delegate's two tools, by both names Claude Code gives them.
DELEGATE_TOOLS = "mcp__plugin_aidd_aidd__delegate_answer|mcp__plugin_aidd_aidd__delegate_packet|mcp__aidd__delegate_answer|mcp__aidd__delegate_packet"
# The hook's own timeout: a local merge's check reruns the suite, so it keeps Claude Code's default of 600 s.
HOOKS = {
    "PermissionRequest": {"matcher": f"Bash|{DELEGATE_TOOLS}", "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 600}]},
    "PreToolUse": {"matcher": DELEGATE_TOOLS, "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 30}]},
}
# The delegated local merge's template has no harness rule of its own, and the answer tool must always prompt.
ASKS = ("Bash(git merge --no-ff *)", "mcp__aidd__delegate_answer", "mcp__plugin_aidd_aidd__delegate_answer")


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return data


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _take_out(settings: dict, claimed: list[str]) -> bool:
    """Take aidd's delegation hooks, and the ask rules it `claimed` (the ones it added), out of `settings`; whether
    anything changed. A person's own copy of one of those rules, there before aidd's, stays."""
    changed = False
    hooks: dict = settings["hooks"] if isinstance(settings.get("hooks"), dict) else {}
    for event in HOOKS:
        groups = hooks.get(event)
        if isinstance(groups, list):
            kept = [
                g for g in groups if not (isinstance(g, dict) and any(h.get("command") == HOOK_COMMAND for h in g.get("hooks") or [] if isinstance(h, dict)))
            ]
            if kept != groups:
                changed = True
                hooks[event] = kept
                if not kept:
                    hooks.pop(event)
    if "hooks" in settings and not hooks:
        settings.pop("hooks")
    perms: dict = settings["permissions"] if isinstance(settings.get("permissions"), dict) else {}
    ask = perms.get("ask")
    if isinstance(ask, list) and any(a in claimed for a in ask):
        perms["ask"] = [a for a in ask if a not in claimed]
        changed = True
    return changed


def apply(root: Path, cfg: config.Config | None, *, write: bool = True) -> list[str]:
    """Bring the delegation's hooks and ask rules in line with the config: there with a `delegation`, gone without one.
    What it did, one line each."""
    path, ledger_path = root / SETTINGS, root / config.HARNESS_RULES_FILE
    settings, ledger = _read(path), _read(ledger_path)
    before = json.dumps(settings, sort_keys=True)
    if ledger.get(LEDGER_KEY):
        _take_out(settings, [a for a in ledger[LEDGER_KEY] if a in ASKS])
    wanted = bool(cfg and cfg.get("delegation"))
    added: list[str] = []
    if wanted:
        hooks = settings.setdefault("hooks", {})
        for event, group in HOOKS.items():
            hooks.setdefault(event, []).append(json.loads(json.dumps(group)))
        perms = settings.setdefault("permissions", {})
        added = [a for a in ASKS if a not in perms.get("ask", [])]
        perms["ask"] = [*perms.get("ask", []), *added]
    if json.dumps(settings, sort_keys=True) == before:
        return []
    verb = ("wrote" if wanted else "removed") if write else ("would write" if wanted else "would remove")
    if write:
        _write(path, settings)
        ledger[LEDGER_KEY] = ["hooks.PermissionRequest", "hooks.PreToolUse", *added] if wanted else []
        _write(ledger_path, {k: v for k, v in ledger.items() if v})
    return [f"{verb} the delegation's PermissionRequest and PreToolUse hooks and its {len(ASKS)} ask rules {'into' if wanted else 'from'} {SETTINGS}"]


# What `aidd init` and `aidd doctor` say once about a delegation, in this order: what still stops, what turns the hook
# off, and the one control that holds.
NOTES = (
    "Still asks you: every reserved action, such as a deploy, a migration, a new dependency, or a secret, and anything the check defers.",
    "A Claude Code mod, `claude --bare`, or `disableAllHooks` turns the hook off, and then every delegated ask comes back to you.",
    "Branch protection is the one control that holds whatever the agents do: require the tests check, and block force pushes and deletion.",
)


def block(set_by: str, default_branch: str, deploys: bool | None, today: dt.date) -> str:
    """The `delegation` block `aidd init --delegate` writes: everything delegable, reviewed in 90 days, and the person's
    answer on whether a merge deploys, unset when they are not sure."""
    review_by = (today + dt.timedelta(days=90)).isoformat()
    lines = [
        "# A standing delegation (docs/CONFIG.md, `delegation`): aidd-team:delegate answers these asks for you, on a passing",
        "# `aidd delegate check`. Only this file on the default branch sets it, and a reserved action is always yours.",
        "delegation:",
        "  to: delegate",
        f"  set_by: {json.dumps(set_by)}   # the address you commit with, or your no-reply one: it goes into each delegated commit",
        "  decides: all",
        "  reserved: []",
        f"  default_branch: {json.dumps(default_branch)}",
        *(
            [f"  default_branch_deploys: {'true' if deploys else 'false'}"]
            if deploys is not None
            else ["  # default_branch_deploys: false   # unset: a merge may deploy, so it stays yours"]
        ),
        f'  review_by: "{review_by}"',
        "  digest: each_session",
    ]
    return "\n".join(lines) + "\n"


def deploy_files(root: Path) -> list[str]:
    """The files in the repository a host deploys from on a merge, such as `vercel.json`, for init's question."""
    pats = resources.load_json("risks.json")["areas"]["infra"].get("deploys_on_merge", [])
    tracked = git.run(["ls-files", "-z"], str(root), check=False).split("\0")
    return sorted(p for p in tracked if p and globs.match_any(pats, p, fold_case=True))[:5]


def doctor_lines(root: Path, cfg: config.Config | None) -> list[tuple[str, str]]:
    """What `aidd doctor` says about a delegation: what it decides, which harness answers it, whether the hooks are in
    place and on, and what shadows the delegate."""
    block_ = (cfg.get("delegation") if cfg else None) or {}
    if not block_:
        return []
    out = [
        (
            "ok",
            f"delegation: decides {block_.get('decides')}, reserved {block_.get('reserved') or []}, review by {block_.get('review_by')}; the check reads it from the default branch's tip",
        )
    ]
    if not (root / ".claude").exists():
        out.append(("warn", "delegation: only Claude Code answers a delegated ask in this version, and it is not set up here, so every ask still comes to you"))
        return out
    out.append(("ok", "delegation: Claude Code's hook answers it; every other harness keeps its ask rules and asks you, as with no delegation"))
    settings = _read(root / SETTINGS) if (root / SETTINGS).is_file() else {}
    groups = [g for e in HOOKS for g in (settings.get("hooks") or {}).get(e, []) if isinstance(g, dict)]
    if not any(h.get("command") == HOOK_COMMAND for g in groups for h in g.get("hooks") or [] if isinstance(h, dict)):
        out.append(("warn", f"delegation: no aidd hook in {SETTINGS}, so Claude Code keeps asking you; run `aidd upgrade --yes`"))
    for where in (root / SETTINGS, root / ".claude/settings.local.json", Path.home() / ".claude" / "settings.json"):
        try:
            off = where.is_file() and bool(_read(where).get("disableAllHooks"))
        except (ValueError, OSError):
            off = False
        if off:
            out.append(("warn", f"delegation: {where} sets disableAllHooks, so the hook never runs and every delegated ask comes back to you"))
    if (root / ".claude/agents/delegate.md").is_file():
        out.append(("warn", "delegation: .claude/agents/delegate.md shadows aidd-team:delegate, since Claude Code ranks a project's agent first; remove it"))
    out += [("ok", f"delegation: {note}") for note in NOTES]
    return out


def remove(root: Path, *, write: bool = True) -> list[str]:
    """`aidd uninstall`: take the delegation's hooks and ask rules out, whatever the config says."""
    return apply(root, None, write=write) if _read(root / config.HARNESS_RULES_FILE).get(LEDGER_KEY) else []
