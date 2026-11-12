"""What a standing delegation adds to Claude Code's project settings, the one harness that answers a delegated ask in
this version: a `PermissionRequest` hook and a `PreToolUse` hook that run `aidd delegate hook`, and three ask rules.
The ask rules keep every delegated command, and the delegate's answer tool, on the prompt path, so the hook answers
only a prompt they raise. Every other ask rule stays as it was. aidd lists what it wrote under `claude-code-delegation`
in `.aidd/harness-rules.json`, and changes only those entries, never a person's own."""

from __future__ import annotations

import datetime as dt
import json
import types
from pathlib import Path
from typing import Any

from aidd import config, delegation
from aidd.kernel import documents, git, globs, regular_files, resources, timestamps
from aidd.setup import mcp_wiring

SETTINGS = ".claude/settings.json"
LEDGER_KEY = "claude-code-delegation"
# The hook runs this user's pinned launcher, `~/.aidd/bin/aidd`, which `aidd init` writes (mcp_wiring), and never searches
# PATH, so no `aidd` a repository plants, on a relative entry such as `node_modules/.bin` or a link, can answer. A missing
# launcher exits 127 with no output: no decision, so the prompt stays.
HOOK_COMMAND = f"/bin/sh -c 'exec {mcp_wiring.SH_LAUNCHER} delegate hook'"
# The delegate's two tools, by both names Claude Code gives them: the one list `delegation` owns.
DELEGATE_TOOLS = "|".join(delegation.DELEGATE_TOOLS)
# The hook's own timeout: a local merge's check reruns the suite, so it keeps Claude Code's default of 600 s.
HOOKS = {
    "PermissionRequest": {"matcher": f"Bash|{DELEGATE_TOOLS}", "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 600}]},
    "PreToolUse": {"matcher": DELEGATE_TOOLS, "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 30}]},
}
# The delegated local merge's template has no harness rule of its own, and the answer tool must always prompt.
ASKS = ("Bash(git merge --no-ff *)", *delegation.DELEGATE_ANSWER_TOOLS)


def _read(root: Path, path: Path) -> dict:
    """A settings or ledger file as JSON, {} when there is none. One in the repository reads through the safe reader, and
    a link, a pipe, or a device there is an error, so aidd never writes through it; the person's own in their home reads
    as it is."""
    if Path(path).is_relative_to(root):
        text, why = regular_files.named_text(root, path.relative_to(root).as_posix())
        if text is None and why != regular_files.MISSING:  # never read, and so never written through
            raise ValueError(
                f"{path.relative_to(root).as_posix()} is {why}, which aidd never reads or writes through: replace it with the file, then run aidd again"
            )
    else:
        text = regular_files.text_at(root, path)
    if text is None:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return data


def _write(root: Path, path: Path, data: dict) -> None:
    """A settings or ledger file, through the safe writer: a link at it or on the way to it is WriteRefused."""
    regular_files.write_text_safely(root, path, json.dumps(data, indent=2) + "\n")


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
    settings, ledger = _read(root, path), _read(root, ledger_path)
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
        _write(root, path, settings)
        ledger[LEDGER_KEY] = ["hooks.PermissionRequest", "hooks.PreToolUse", *added] if wanted else []
        _write(root, ledger_path, {k: v for k, v in ledger.items() if v})
    return [f"{verb} the delegation's PermissionRequest and PreToolUse hooks and its {len(ASKS)} ask rules {'into' if wanted else 'from'} {SETTINGS}"]


# What `aidd init` and `aidd doctor` say once about a delegation, in this order: what still stops, what turns the hook
# off, and the one control that holds.
NOTES = (
    "Still asks you: every reserved action, such as a deploy, a migration, a new dependency, or a secret, and anything the check defers.",
    "If the hook fails or never loads (`claude --bare`, `disableAllHooks`), the prompt stays. A Claude Code mod that approves the call, a merge through another MCP server's tool, or an action no ask rule names passes the hook with no prompt.",
    "Branch protection is the one control that holds whatever the agents do: require the tests check, and block force pushes and deletion.",
)


def block(by: str, default_branch: str, today: dt.date) -> str:
    """The `delegation` block `aidd init --delegate` writes, with the moment it is written as `at`: every delegable action a
    person can undo, reviewed in 90 days."""
    review_due = (today + dt.timedelta(days=90)).isoformat()
    lines = [
        "# A standing delegation (docs/CONFIG.md, `delegation`): aidd-team:delegate answers these asks for you, on a passing",
        "# `aidd delegate check`. Only this file on the default branch sets it, and a reserved action is always yours.",
        "delegation:",
        f"  by: {json.dumps(by)}   # the address you commit with, or your no-reply one: it goes into each delegated commit",
        f'  at: "{timestamps.utc_stamp()}"',
        f"  decides: [{', '.join(delegation.undoable())}]",
        "  reserved: []",
        f"  default_branch: {json.dumps(default_branch)}",
        f'  review_due: "{review_due}"',
        "  digest: each_session",
    ]
    return "\n".join(lines) + "\n"


def deploy_files(root: Path) -> list[str]:
    """The files in the repository a host deploys from on a merge, such as `vercel.json`, for init's question."""
    pats = resources.load_json("risks.json")["areas"]["infra"].get("deploys_on_merge", [])
    tracked = git.run(["ls-files", "-z"], str(root), check=False).split("\0")
    return [documents.one_line(p, 160) for p in sorted(p for p in tracked if p and globs.match_any(pats, p, fold_case=True))[:5]]


def same_model_lines(root: Path, cfg: config.Config) -> list[tuple[str, str]]:
    """The delegate check's same-model warning for the branch checked out: the delegate runs on a model that an `Assisted-by`
    in the commits since the default branch names. None of those commits on the default branch itself, so none then."""
    try:
        name = git.default_branches(str(root))[0][0]
        run = types.SimpleNamespace(
            cfg=cfg, tip=git.rev_parse(f"refs/heads/{name}", str(root)), top=str(root), req=types.SimpleNamespace(head=git.rev_parse("HEAD", str(root)))
        )
    except (git.GitError, IndexError, OSError):
        return []
    note: Any = delegation.same_model_warning(run)  # type: ignore[arg-type]  # it reads only these four fields of a check
    return [("warning", note)] if note else []


def doctor_lines(root: Path, cfg: config.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """What `aidd doctor` says about a delegation: what it decides, which harness answers it, whether the hooks are in
    place and on, and what shadows the delegate. The warnings `aidd validate` prints (`config.delegation_warnings`) come next,
    then the same-model warning for the branch checked out."""
    block_ = (cfg.get("delegation") if cfg else None) or {}
    if not block_:
        return []
    out = [
        (
            "",
            f"delegation: decides {block_.get('decides')}, reserved {block_.get('reserved') or []}, review by {block_.get('review_due')}; the check reads it from the default branch's tip",
        )
    ]
    if note := delegation.not_yet_on_default_note(str(root), block_):
        out.append(("warning", note))
    out += [("warning", w) for w in config.delegation_warnings(block_, today or dt.date.today())]
    out += same_model_lines(root, cfg) if cfg else []
    recorded = str(block_.get("default_branch") or "")
    origin_head = git.run(["symbolic-ref", "-q", "refs/remotes/origin/HEAD"], str(root), check=False).strip().removeprefix("refs/remotes/origin/")
    if recorded and origin_head and origin_head != recorded:
        out.append(
            (
                "warning",
                f"delegation: origin/HEAD names `{origin_head}`, but the config records `{recorded}`, and `aidd upgrade` writes the push rules for "
                f"`{origin_head}`. If `{recorded}` is the default branch, run `git remote set-head origin --auto`. Otherwise fix delegation.default_branch",
            )
        )
    if not (root / ".claude").exists():
        out.append(
            ("warning", "delegation: only Claude Code answers a delegated ask in this version, and it is not set up here, so every ask still comes to you")
        )
        return out
    out.append(("", "delegation: Claude Code's hook answers it; every other harness keeps its ask rules and asks you, as with no delegation"))
    try:
        settings = _read(root, root / SETTINGS)
    except ValueError as exc:
        out.append(("warning", f"delegation: {exc}"))
        settings = {}
    groups = [g for e in HOOKS for g in (settings.get("hooks") or {}).get(e, []) if isinstance(g, dict)]
    if not any(h.get("command") == HOOK_COMMAND for g in groups for h in g.get("hooks") or [] if isinstance(h, dict)):
        out.append(("warning", f"delegation: no aidd hook in {SETTINGS}, so Claude Code keeps asking you; run `aidd upgrade --yes`"))
    for where in (root / SETTINGS, root / ".claude/settings.local.json", config.claude_config_dir() / "settings.json"):
        try:
            off = bool(_read(root, where).get("disableAllHooks"))
        except (ValueError, OSError):
            off = False
        if off:
            out.append(("warning", f"delegation: {where} sets disableAllHooks, so the hook never runs and every delegated ask comes back to you"))
    if (root / ".claude/agents/delegate.md").is_file():
        out.append(("warning", "delegation: .claude/agents/delegate.md shadows aidd-team:delegate, since Claude Code ranks a project's agent first; remove it"))
    out += [("", f"delegation: {note}") for note in NOTES]
    return out


def remove(root: Path, *, write: bool = True) -> list[str]:
    """`aidd uninstall`: take the delegation's hooks and ask rules out, whatever the config says."""
    return apply(root, None, write=write) if _read(root, root / config.HARNESS_RULES_FILE).get(LEDGER_KEY) else []
