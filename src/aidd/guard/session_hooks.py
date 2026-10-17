"""Claude Code session hooks: what the agent should know when a session starts, and before it says it is done.

Each hook reads the event JSON Claude Code sends on stdin and prints the documented JSON answer, or nothing
(code.claude.com/docs/en/hooks, checked 2026-09-28):

- SessionStart: `hookSpecificOutput.additionalContext` adds text to the agent's context before the first prompt.
  `aidd hook session-start` adds a short summary of this change, led by its route and lane (level minimal and
  above), and, when the session starts again after a compaction (`source` = "compact"), the handoff note reminder
  (default and above).
- Stop and SubagentStop: top-level `decision` = "block" with a `reason` keeps the agent working (strict), and
  `hookSpecificOutput.additionalContext` is non-error feedback that also continues it once (default). The input's
  `stop_hook_active` is true when a stop hook already continued the agent; the hook then never continues it again.
  `aidd hook stop` reminds the agent to run `aidd test` when its Spec's scope changed without evidence for it, and,
  once Spec approval holds, names each change on the branch the guard would deny (`edit_check.forbidden_changes`): a
  frozen test, design file, or doc, a path outside the scope, or a protected path, written where the edit hook could
  not see it.
- UserPromptSubmit: `hookSpecificOutput.additionalContext` adds text to the agent's context with the prompt.
  `aidd hook prompt-submit` adds one line, this change's first step and its command, under the team and org
  profiles at level balanced and above. It never blocks a prompt.
- PreCompact: the documented output can only block the compaction (`decision` = "block" or exit 2); Claude Code
  discards its `systemMessage` and it takes no `additionalContext`. So `aidd hook pre-compact` prints nothing: it saves
  the state of the work (the summary of this change, the latest handoff note's `stopped_at`, and this session's autopilot
  lease and last steps) in the git directory (`lease.save_snapshot`), and SessionStart with source "compact" or
  "resume" reads it back to the agent with the handoff note reminder (default and above).

Every hook is deterministic, uses no model and no network, reads only local state, writes no tracked file (the
snapshot goes to the git directory), masks secret-looking values in what it prints or saves, and acts only in a
repository with .aidd/config.yaml. It never breaks the agent's session: on an internal error it allows, prints nothing on
stdout, and writes one short note to stderr. `hooks` in the config sets the level and turns each hook off.

Inside Orca (github.com/stablyai/orca, a desktop app that runs coding agents in git worktrees), session-start and
stop also put this change's first step on the worktree's Orca card, with the work's state after it (working,
waiting on someone, stuck, or red: `card_state`), through the CLI Orca ships:
`orca worktree show|set --worktree path:<root> --comment <text> --json` (checked 2026-09-28 against Orca 1.4.215).
The CLI talks to the Orca app on this machine. The card is for people to glance at: it is never evidence and never
an approval. Outside Orca, or without its CLI, nothing happens; the update is time-boxed, silent on failure, and
never changes what the hook prints. `hooks.orca_status: false` turns it off.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from aidd import config, gate, knowledge
from aidd.guard import dialects
from aidd.kernel import documents, git, globs

TEST_REMINDER = "Run `aidd test` and report the result before you say the work is done"
HANDOFF_REMINDER = "write the handoff note now, as a ```aidd-handoff block (done, next, needs, stopped_at) in the Spec or the PR/MR, where aidd reads it back"
MAX_SUMMARY_LINES = 15
EVIDENCE_FILE = "evidence.json"


def _event(stdin) -> dict:
    try:
        data = json.load(stdin)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def session_note(event: dict, cfg: config.Config) -> str | None:
    """Under autopilot, in a harness that gives a command no variable for the session (Antigravity), the line that
    names the session's id to the agent: the guard allows `aidd autopilot start|stop` only with the id its event names."""
    from aidd import autopilot

    sid = event.get("session_id")
    if dialects.of(event).names_its_session or not config.component_on(cfg.raw, "autopilot") or not isinstance(sid, str) or not autopilot.SESSION_ID.match(sid):
        return None
    return f"aidd: this conversation's session id is `{sid}`. Pass `--session {sid}` to every `aidd autopilot` command."


def _repo(event: dict) -> str | None:
    """The top of the repository the session works in, when it has adopted aidd; else None."""
    cwd = Path(event.get("cwd") or os.getcwd())
    if not cwd.is_dir():
        return None
    top = git.toplevel(str(cwd))
    return top if top and (Path(top) / config.CONFIG_PATH).is_file() else None


def _config(root: str) -> config.Config | None:
    from aidd.guard.repo_config import offline_fetch

    try:
        return config.load_file(config.CONFIG_PATH, root, fetch=offline_fetch, skip_unread=True)
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError):
        return None


def level(cfg: config.Config) -> str:
    """minimal, balanced, or strict: `hooks.level`, or the profile's default (config.HOOK_LEVEL_DEFAULTS)."""
    return config.hook_level(cfg.raw)


def hook_level_at_least(cfg: config.Config, wanted: str) -> bool:
    return config.HOOK_LEVELS.index(level(cfg)) >= config.HOOK_LEVELS.index(wanted)


def enabled(cfg: config.Config, switch: str) -> bool:
    """Whether `hooks.<switch>` leaves the hook on (the default). Every session hook speaks for the loop, so it is
    silent when `components.hooks` or `components.loop` is off."""
    if not (config.component_on(cfg.raw, "hooks") and config.component_on(cfg.raw, "loop")):
        return False
    return cfg.get("hooks", switch, default=True) is not False


def _emit(stdout, payload: dict) -> int:
    json.dump(payload, stdout)
    stdout.write("\n")
    return 0


def _emit_context(stdout, event: dict, hook_name: str, text: str) -> int:
    """Context for the agent, in the format of the harness that sent `event` (`dialects`)."""
    return _emit(stdout, dialects.of(event).context(hook_name, text))


def _emit_idle(stdout, event: dict) -> int:
    """Nothing to add: no output, or what the harness reads instead (an empty object for Antigravity)."""
    answer = dialects.of(event).idle()
    return 0 if answer is None else _emit(stdout, answer)


# ---- SessionStart ----------------------------------------------------------------------------------------


def change_lane(root: str, cfg: config.Config, answer: dict | None = None) -> str | None:
    """One line: the route header of this change's forecast (the higher of what the branch's current diff
    needs, committed, staged, unstaged, and untracked, and what its Spec or Change Request block declares), or None when there is
    neither a diff nor a declaration, or it cannot tell. The route, shown where the agent starts: it is advisory,
    and the gate re-checks the real diff. `answer` is `next_steps.forecast`'s, when the caller has it."""
    try:
        from aidd import tracking

        route = (answer if answer is not None else tracking.forecast(Path(root))).get("route")
    except Exception:  # noqa: BLE001  # a hint the agent can do without; the hook never fails on it
        return None
    if not route:
        return None
    return f"{route['header']}; `aidd gate` gives the reasons, and checks the real diff again."


def purpose(cfg: config.Config | None) -> str | None:
    """One line, "Mission: ... / Goal: ...", with whichever of the two the config sets; None when it sets neither."""
    parts = [f"{label}: {' '.join(str(cfg.get(key)).split())}" for key, label in (("mission", "Mission"), ("goal", "Goal")) if cfg and cfg.get(key)]
    return " / ".join(parts) or None


def summary(root: Path, lane: str | None = None, cfg: config.Config | None = None) -> str:
    """At most MAX_SUMMARY_LINES lines: what the forecast says for this change, most urgent first, after its route
    (`lane`, else `change_lane`) and the team's mission and goal, when there are any."""
    from aidd import tracking

    answer = tracking.forecast(root)
    lane = lane if lane is not None else change_lane(str(root), cfg, answer) if cfg is not None else None
    steps = [*answer["steps"], *answer["overlaps"]]
    branch = git.run(["rev-parse", "--abbrev-ref", "HEAD"], str(root), check=False).strip() or "unknown"
    lines = [f"aidd: this change, on branch {branch} (`aidd list` shows all open work):", *(x for x in (lane, purpose(cfg)) if x)]
    shown = 0
    for i, s in enumerate(steps, 1):
        if MAX_SUMMARY_LINES - len(lines) < 2 + (1 if i < len(steps) else 0):
            break
        lines += [f"{i}. {s['what']}", f"   {s['who']}: {s['how']}"]
        shown = i
    if shown < len(steps):
        lines.append(f"... and {len(steps) - shown} more")
    return "\n".join(lines[:MAX_SUMMARY_LINES])


def worktree_notes(root: str, cfg: config.Config) -> list[str]:
    """At session start: this worktree's name in the shared dev stack, when the project has one, so the agent never
    starts a second stack; and worktrees a person may clean, once."""
    from aidd import workitems

    out = []
    services = cfg.get("project", "dev_services") or {}
    if services:
        up = " ".join(services["up"]) if services.get("up") else "the project's dev stack"
        out.append(
            f"aidd: the dev services are shared by every worktree ({up}, once per machine): never start a second stack. Name what this "
            f"worktree makes in it (its database, bucket, ports) by AIDD_WORKTREE={workitems.worktree_slug(root)}, which `aidd test` sets."
        )
    try:
        gone = workitems.cleanable(workitems.worktree_states(root), root)
    except Exception:  # noqa: BLE001  # a courtesy line: never the session's failure
        gone = []
    if gone:
        out.append(f"aidd: {len(gone)} worktree(s) are merged or missing: tell the person once that `aidd worktrees clean` removes them.")
    return out


def session_start(event: dict, stdout) -> int:
    root = _repo(event)
    cfg = _config(root) if root else None
    if cfg is None:
        from aidd.guard.path_location import config_problem

        problem = config_problem(root)
        if not problem:
            return _emit_idle(stdout, event)
        held = "the guard holds the deploy and infrastructure commands `aidd init` detects, and no aidd-team role writes, until it is fixed"
        return _emit_context(stdout, event, "SessionStart", f"aidd: {problem}. Until then {held}.")
    # A URL parent the hook did not fetch (it runs offline): say so, whatever else is on.
    parts = [f"aidd: {w}" for w in cfg.warnings if config.UNREAD_PARENT in w]
    if enabled(cfg, "session_start"):
        parts.append(summary(Path(root), cfg=cfg))  # type: ignore[arg-type]
    if session_line := session_note(event, cfg):
        parts.append(session_line)
    from aidd import workitems

    if workitems.is_explore(branch := workitems.current_branch(root)):  # type: ignore[arg-type]
        parts.append(f"aidd: {workitems.explore_note(branch)}")
    parts += worktree_notes(root, cfg)  # type: ignore[arg-type]
    if standing := workitems.live_standing_for(cfg, root):  # type: ignore[arg-type]
        but = " except on major changes" if standing["scope"] == "all-but-major" else ""
        parts.append(
            f"aidd: the person's standing approval is on{but}, since {standing['since'][:16]}: run the `aidd approve spec`, "
            "`aidd approve merge`, or `aidd ship` that `aidd list` names, and never ask them for it."
        )
    if event.get("source") == "compact" and hook_level_at_least(cfg, "balanced") and enabled(cfg, "compact_note"):
        parts.append(
            f"The context was just compacted. If the handoff note is not current, {HANDOFF_REMINDER}; then read it back and continue from its `stopped_at`."
        )
    if event.get("source") in ("compact", "resume") and hook_level_at_least(cfg, "balanced") and enabled(cfg, "compact_note"):
        saved = saved_state(root, event)  # type: ignore[arg-type]
        if saved:
            parts.append(saved)
    orca_card(root, cfg)  # type: ignore[arg-type]
    if not parts:
        return _emit_idle(stdout, event)
    from aidd.guard.denial_log import redact  # the branch name and every step's words are masked, as the module docstring says

    return _emit_context(stdout, event, "SessionStart", redact("\n\n".join(parts)))


# ---- Stop and SubagentStop -------------------------------------------------------------------------------


def evidence_paths(cfg: config.Config) -> list[str]:
    """Where `aidd test` writes evidence: .aidd/evidence/, and the folder `evidence.artifact` names when it is set."""
    dirs = [config.EVIDENCE_DIR, *([str(cfg.get("evidence", "artifact"))] if cfg.get("evidence", "artifact") else [])]
    return [f"{d.rstrip('/')}/{EVIDENCE_FILE}" for d in dict.fromkeys(dirs)]


def _evidence_files(root: Path, rels: list[str]) -> list[tuple[str, float, object]]:
    """(path, modification time, parsed JSON) of each evidence file that reads."""
    found = []
    for rel in rels:
        try:
            found.append((rel, (root / rel).stat().st_mtime, json.loads((root / rel).read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return found


def missing_evidence(root: str, cfg: config.Config, specs: list[tuple[str, dict]], changed: list[str], in_scope: list[str]) -> str | None:
    """Why no evidence file proves the tests for this working tree, or None when one does.

    It proves them when its head_sha is HEAD, it is not partial (`aidd test --changed`, which the gate never accepts),
    every configured `tests` command that applies and every Spec's tests.commands passed on head (phase green), and
    no uncommitted in-scope file changed after it was written."""
    head = git.rev_parse("HEAD", root)
    declared = [c for _, d in specs for c in (d.get("tests") or {}).get("commands", []) or [] if isinstance(c, dict) and c.get("name")]
    required, _ = gate.required_tests(list(cfg.get("tests", default=[]) or []), declared, "spec", changed)
    names = sorted({c["name"] for c, _ in required})
    dirty = set(git.dirty(root, untracked=True, check=False))
    why = "no evidence from `aidd test` in " + " or ".join(evidence_paths(cfg))
    for rel, written, data in _evidence_files(Path(root), evidence_paths(cfg)):
        if not isinstance(data, dict) or data.get("head_sha") != head:
            why = f"{rel} is for another commit, not HEAD {head[:12]}"
            continue
        if data.get("partial"):
            why = f"{rel} is partial (`aidd test --changed`), and the gate needs a full `aidd test`"
            continue
        passed = {
            r.get("name") for r in data.get("results", []) if isinstance(r, dict) and r.get("red_green", "green") == "green" and r.get("status") == "passed"
        }
        failing = [n for n in names if n not in passed]
        if failing:
            why = f"{rel} does not record {', '.join(failing)} as passed"
            continue
        newer = [p for p in in_scope if p in dirty and (Path(root) / p).is_file() and (Path(root) / p).stat().st_mtime > written]
        if newer:
            why = f"{', '.join(newer[:3])} changed after {rel} was written"
            continue
        return None
    return why


def _ships_code(event: dict) -> bool:
    """Stop is the session's own; SubagentStop counts only for a role that writes code in a Task's scope. A helper
    subagent only reads, and the other roles do not run the tests."""
    if event.get("hook_event_name") != "SubagentStop":
        return True
    from aidd.guard.role_areas import role_of

    role = role_of(event)
    return bool(role) and "{scope}" in knowledge.roles()["roles"][role]["writes"]


def stop_check(root: str, cfg: config.Config) -> str | None:
    """The reminder the agent should get before it stops, or None when there is nothing to remind it of."""
    from aidd import workitems
    from aidd.kernel.git import branch_base, changed_since

    specs = workitems.active_specs(root, cfg)
    scopes = [s for _, d in specs for t in d.get("tasks", []) or [] if isinstance(t, dict) for s in t.get("scope", []) or []]
    if not scopes:
        return None
    changed = changed_since(root, branch_base(root))
    in_scope = [p for p in changed if globs.match_any(scopes, p)]
    if not in_scope:
        return None
    why = missing_evidence(root, cfg, specs, changed, in_scope)
    if why is None:
        return None
    ids = ", ".join(str(d.get("id")) for _, d in specs)
    return f"{TEST_REMINDER}. aidd: {ids} has changes in its scope ({', '.join(in_scope[:3])}{', ...' if len(in_scope) > 3 else ''}), and {why}."


MAX_NAMED_CHANGES = 5  # forbidden changes listed in the stop reminder, then "and N more"


def guard_check(root: str, cfg: config.Config) -> str | None:
    """The changes the guard would have denied, named, or None when there are none (`edit_check.forbidden_changes`)."""
    from aidd.guard.edit_check import forbidden_changes

    found = forbidden_changes(root, cfg)
    if not found:
        return None
    lines = [f"- {rel}: {reason}" for rel, reason in found[:MAX_NAMED_CHANGES]]
    if len(found) > MAX_NAMED_CHANGES:
        lines.append(f"- and {len(found) - MAX_NAMED_CHANGES} more")
    return (
        "aidd: this branch changed files the guard would have denied (a write it did not see, such as a script or a "
        "shell command). Undo each change, or take the route the reason names, before you say the work is done:\n" + "\n".join(lines)
    )


def stop(event: dict, stdout) -> int:
    dialect = dialects.of(event)
    if dialect.stop_held(event):
        return _emit_idle(stdout, event)  # a stop hook already continued the agent: never loop
    root = _repo(event)
    cfg = _config(root) if root else None
    if cfg is None:
        return _emit_idle(stdout, event)
    if event.get("hook_event_name") != "SubagentStop":  # the session's own stop; a subagent's stop never waits on Orca
        orca_card(root, cfg, stopping=True)  # type: ignore[arg-type]
    if not enabled(cfg, "stop_check") or not hook_level_at_least(cfg, "balanced") or not _ships_code(event):
        return _emit_idle(stdout, event)
    parts = [x for x in (stop_check(root, cfg), guard_check(root, cfg)) if x]  # type: ignore[arg-type]
    if not parts:
        return _emit_idle(stdout, event)
    return _emit(stdout, dialect.stop(event, "\n\n".join(parts), strict=hook_level_at_least(cfg, "strict")))


# ---- The Orca workspace card -----------------------------------------------------------------------------

# Orca sets these in every terminal it manages (src/main/ipc/pty/ipc/spawn-env.ts in stablyai/orca, and the
# agent-hook environment). Any one of them means the hook runs inside Orca.
ORCA_ENV = ("ORCA_PANE_KEY", "ORCA_WORKTREE_ID", "ORCA_AGENT_HOOK_PORT")
ORCA_TIMEOUT_SECONDS = 2.0  # seconds for the whole card update, both CLI calls together
CARD_PREFIX = "aidd: "
MAX_CARD_LINE = 160


# The state at the end of the card line. `stuck` is judged only when the agent stops: an agent that stops with no
# commit and no handoff note for this long has probably lost its way, and a person should look.
STUCK_MINUTES = 60
CARD_STATE_SEP = " | "
MAX_CARD_NAMES = 2  # approvers named in "waiting on ...", then "+N"
_FAILED = ("failed", "timeout", "not_started")


def failed_evidence(root: Path, cfg: config.Config | None) -> list[str]:
    """The commands the evidence for HEAD records as failed on the head (phase green), from the newest evidence file
    `aidd test` wrote; [] when there is none for HEAD or it passed. A red-phase failure on the base is expected."""
    head = git.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    found = _evidence_files(root, evidence_paths(cfg) if cfg else [f"{config.EVIDENCE_DIR}/{EVIDENCE_FILE}"])
    for _, _, data in sorted(found, key=lambda x: x[1], reverse=True):
        if isinstance(data, dict) and head and data.get("head_sha") == head:
            results = [r for r in data.get("results", []) if isinstance(r, dict) and r.get("red_green", "green") == "green"]
            return [str(r.get("name")) for r in results if r.get("status") in _FAILED]
    return []


def last_activity(root: Path, steps: list[dict]) -> float | None:
    """When the work last moved, as a Unix time: the newer of the HEAD commit's committer time and the modification
    time of an open Spec holding an ```aidd-handoff block (the file is where the agent writes its latest note)."""
    times = []
    head = git.run(["log", "-1", "--format=%ct", "HEAD"], str(root), check=False).strip()
    if head.isdigit():
        times.append(float(head))
    for s in steps:
        where = root / str(s.get("where") or "")
        if not s.get("where") or not where.is_file():
            continue
        try:
            if "```aidd-handoff" in where.read_text(encoding="utf-8"):
                times.append(where.stat().st_mtime)
        except (OSError, UnicodeDecodeError):
            continue
    return max(times) if times else None


def _names(who: list[str]) -> str:
    shown = ", ".join(who[:MAX_CARD_NAMES])
    return shown + (f" +{len(who) - MAX_CARD_NAMES}" if len(who) > MAX_CARD_NAMES else "")


def card_state(root: Path, steps: list[dict], cfg: config.Config | None, *, stopping: bool = False, now: float | None = None) -> str | None:
    """The work's state in a few words, the first rule that holds winning:

    - `red: <commands> failed`: the evidence `aidd test` wrote for HEAD records a head test as failed
    - `waiting on <who>`: the first step is a person's (an approval names its eligible approvers)
    - `stuck: no commit or handoff note for <age>`: only when the agent stops, with its work still its own, and nothing
      moved (`last_activity`) for STUCK_MINUTES or more
    - `working`: the first step is the agent's
    None when nothing is open."""
    from aidd import tracking, workitems

    first = steps[0] if steps else None
    if first is None or first.get("code") in ("nothing_open", "nothing_matches"):
        return None
    failed = failed_evidence(root, cfg)
    if failed:
        return f"red: {_names(failed)} failed on HEAD"
    who = str(first.get("who") or "")
    if not who.startswith(workitems.AGENT):
        return f"waiting on {_names(first['approvers'])}" if first.get("approvers") else f"waiting on {who}"
    if stopping:
        moved = last_activity(root, steps)
        idle = int(((now if now is not None else time.time()) - moved) // 60) if moved is not None else 0
        if idle >= STUCK_MINUTES:
            return f"stuck: no commit or handoff note for {tracking.age_text(idle)}"
    return "working"


def card_line(root: Path, cfg: config.Config | None = None, *, stopping: bool = False, now: float | None = None) -> str:
    """One short line for the card: this change's first step and who takes it, then the state (`card_state`)
    after CARD_STATE_SEP. The step is shortened, never the state, so the line stays within MAX_CARD_LINE."""
    from aidd import tracking, workitems

    steps = tracking.plan(root)
    first = steps[0] if steps else {"what": "nothing is open on this branch", "who": workitems.AUTHOR}
    line = " ".join(f"{CARD_PREFIX}{first['what']} ({first['who']})".split())
    state = card_state(root, steps, cfg if cfg is not None else _config(str(root)), stopping=stopping, now=now)
    tail = f"{CARD_STATE_SEP}{state}" if state else ""
    room = MAX_CARD_LINE - len(tail)
    if len(line) > room:
        line = line[: room - 3] + "..."
    return (line + tail)[:MAX_CARD_LINE]


def merge_comment(current: str, line: str) -> str:
    """The card's comment with aidd's line in it. aidd's line replaces its own earlier one; every other line, which a
    person or another agent wrote, stays as it was."""
    lines = current.splitlines()
    for i, old in enumerate(lines):
        if old.startswith(CARD_PREFIX):
            return "\n".join(lines[:i] + [line] + [x for x in lines[i + 1 :] if not x.startswith(CARD_PREFIX)])
    return "\n".join([*lines, line]) if current.strip() else line


def orca_card(root: str, cfg: config.Config, *, stopping: bool = False) -> None:
    """Best effort: show this change's first step on this worktree's Orca card. Display only, never evidence. It does nothing
    outside Orca, without the Orca CLI, or with `hooks.orca_status: false`; it never raises and never prints."""
    if not enabled(cfg, "orca_status") or not any(os.environ.get(name) for name in ORCA_ENV):
        return
    # The Orca CLI, found the way Orca's own skills find it: ORCA_CLI_COMMAND when Orca sets it (managed WSL
    # sessions), else `orca` on PATH; when that one is missing, never some other executable.
    exe = shutil.which(os.environ.get("ORCA_CLI_COMMAND") or "orca")
    if exe is None:
        return
    target = f"path:{root}"  # this worktree exactly; `active` would be whichever one the Orca window shows
    deadline = 0.0  # set once the line is computed: the time box is the two CLI calls', never the plan's

    def orca(*args: str) -> subprocess.CompletedProcess:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("the Orca card update ran out of time")
        return subprocess.run([exe, *args, "--json"], capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=root, timeout=left, check=False)

    try:
        line = card_line(Path(root), cfg, stopping=stopping)
        deadline = time.monotonic() + ORCA_TIMEOUT_SECONDS
        shown = orca("worktree", "show", "--worktree", target)
        if shown.returncode != 0:
            return
        current = str(((json.loads(shown.stdout).get("result") or {}).get("worktree") or {}).get("comment") or "")
        comment = merge_comment(current, line)
        if comment != current:
            orca("worktree", "set", "--worktree", target, "--comment", comment)
    except Exception:  # noqa: BLE001  # the card is a courtesy: it never breaks the hook or outlives its time box
        return


# ---- UserPromptSubmit: the prompt hint -------------------------------------------------------------------

MAX_HINT_CHARS = 200  # characters: a few tokens a prompt
HINT_PROFILES = ("team", "org")


def hint_line(root: Path) -> str | None:
    """One line: this change's first step, who takes it, and its command; None when nothing is open."""
    from aidd import tracking
    from aidd.guard.denial_log import redact

    answer = tracking.forecast(root)
    steps = [s for s in answer["steps"] if s.get("code") not in ("nothing_open", "nothing_matches")]
    if not steps:
        return None
    s = steps[0]
    line = redact(" ".join(f"aidd: next step: {s['what']} ({s['who']}): {s['how']}".split()))
    return line if len(line) <= MAX_HINT_CHARS else line[: MAX_HINT_CHARS - 3] + "..."


def prompt_submit(event: dict, stdout, on_prompt=None) -> int:
    """With each prompt, one line of context for the agent (never the person): the current step and its command. Only
    under the team and org profiles, at level balanced or strict; it never blocks the prompt. Antigravity runs the hook
    before each model call (PreInvocation), so there the line comes only before a turn's first (`invocationNum` 0).

    First, `on_prompt(text, root)` (the CLI's typed decisions) may record what the person typed when it is a decision,
    such as `approve SPEC-1`, in this hook's own process before the model reads it; its line then tells the session
    what was recorded, in place of the hint."""
    root = _repo(event)
    text = event.get("prompt")
    if on_prompt is not None and root and isinstance(text, str):
        try:
            said = on_prompt(text, root)
        except Exception:  # noqa: BLE001  # a decision that cannot be recorded is an ordinary prompt
            said = None
        if said:
            return _emit_context(stdout, event, "UserPromptSubmit", said)
    if not dialects.of(event).prompt_hint_due(event):
        return _emit_idle(stdout, event)
    cfg = _config(root) if root else None
    if cfg is None or str(cfg.get("profile")) not in HINT_PROFILES or not hook_level_at_least(cfg, "balanced") or not enabled(cfg, "prompt_hint"):
        return _emit_idle(stdout, event)
    try:
        line = hint_line(Path(root))  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001  # a hint the agent can do without: quiet, and the prompt goes on
        return _emit_idle(stdout, event)
    if not line:
        return _emit_idle(stdout, event)
    return _emit_context(stdout, event, "UserPromptSubmit", line)


# ---- PreCompact: the snapshot ----------------------------------------------------------------------------

SNAPSHOT_JOURNAL = 5  # the session's last autopilot steps in the snapshot
SNAPSHOT_HEADER = "Before the compaction, aidd saved this state of the work"


def snapshot_text(root: Path, cfg: config.Config, session_id: str) -> str:
    """The state a compaction must not lose: the summary of this change, the active Specs' latest handoff note
    (`stopped_at` and `next`), and this session's autopilot lease and last steps. Secret-looking values are masked."""
    from aidd import autopilot, workitems
    from aidd.guard.denial_log import redact

    lines = [summary(root, cfg=cfg)]
    for rel, _ in workitems.active_specs(str(root), cfg):
        try:
            note = workitems.latest_handoff((root / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            note = None
        if note:
            lines.append(f"Latest handoff note in {rel}: stopped_at {note.get('stopped_at') or '-'}; next {note.get('next')}")
    try:
        held = autopilot.lease_for_session(root, session_id)
        steps = [e for e in autopilot.read_journal(root, tail=autopilot.JOURNAL_TAIL_BYTES) if e.get("session_id") == session_id][-SNAPSHOT_JOURNAL:]
    except (autopilot.LeaseError, OSError):
        held, steps = None, []
    if held:
        lines.append(
            f"This session runs autopilot on {held['work']} until {held['expires_at']}: go on with `aidd autopilot next --session {session_id} --json`."
        )
        lines += [f"- {e.get('spec') or e.get('work')}: {e.get('code')} {e.get('result')}" for e in steps]
    return redact("\n".join(lines))


def pre_compact(event: dict, stdout) -> int:
    """Save the state of the work in the git directory (lease.save_snapshot), never in a tracked file, and print
    nothing: PreCompact output can block a compaction but cannot add context, and blocking would stop a session at its
    context limit. session-start reads the snapshot back after the compaction, or when the session resumes."""
    from aidd import autopilot

    root = _repo(event)
    cfg = _config(root) if root else None
    sid = event.get("session_id")
    if cfg is None or not hook_level_at_least(cfg, "balanced") or not enabled(cfg, "compact_note"):
        return 0
    if not isinstance(sid, str) or not autopilot.SESSION_ID.match(sid):
        return 0
    try:
        autopilot.save_snapshot(root, sid, snapshot_text(Path(root), cfg, sid))  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001  # a snapshot is a convenience: the compaction goes on without it
        return 0
    return 0


def saved_state(root: str, event: dict) -> str | None:
    """The snapshot this session saved before a compaction, as context; None when there is none."""
    from aidd import autopilot

    sid = event.get("session_id")
    if not isinstance(sid, str) or not autopilot.SESSION_ID.match(sid):
        return None
    try:
        saved = autopilot.saved_snapshot(root, sid)
    except (autopilot.LeaseError, OSError):
        return None
    return f"{SNAPSHOT_HEADER} (at {saved['at']}):\n{saved['text']}" if saved else None


HANDLERS = {"session-start": session_start, "prompt-submit": prompt_submit, "stop": stop, "pre-compact": pre_compact}


def run_session_hook(name: str, stdin=None, stdout=None, stderr=None, on_prompt=None) -> int:
    """Run one hook. Any failure of its own allows: exit 0, nothing on stdout (an empty object for Antigravity, which
    reads one from every hook), and a short note on stderr. `on_prompt` goes to the prompt hook (prompt_submit)."""
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    offline = os.environ.get("AIDD_HOOK_OFFLINE")
    os.environ["AIDD_HOOK_OFFLINE"] = "1"  # every config load in the hook skips an `extends` URL: never the network
    event: dict = {}
    try:
        event = _event(stdin)
        event = dialects.of(event).normalize(event)  # the harness's fields in Claude Code's: `cwd`, `session_id`
        if name == "prompt-submit":
            return prompt_submit(event, stdout, on_prompt)
        return HANDLERS[name](event, stdout)
    except Exception as exc:  # noqa: BLE001  # a helper hook must never break the agent's session
        print(f"aidd hook {name}: skipped after an internal error ({type(exc).__name__}); allowing", file=stderr)
        return _emit_idle(stdout, event)
    finally:
        if offline is None:
            os.environ.pop("AIDD_HOOK_OFFLINE", None)
        else:
            os.environ["AIDD_HOOK_OFFLINE"] = offline
