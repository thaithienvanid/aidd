"""Claude Code session hooks: what the agent should know when a session starts, and before it says it is done.

Each hook reads the event JSON Claude Code sends on stdin and prints the documented JSON answer, or nothing
(code.claude.com/docs/en/hooks, checked 2026-09-28):

- SessionStart: `hookSpecificOutput.additionalContext` adds text to the agent's context before the first prompt.
  `aidd hook session-start` adds a short summary of `aidd next`, led by the route and lane it computes for the branch's
  diff (level minimal and above), and, when the session starts again after a compaction (`source` = "compact"), the
  handoff note reminder (standard and above).
- Stop and SubagentStop: top-level `decision` = "block" with a `reason` keeps the agent working (strict), and
  `hookSpecificOutput.additionalContext` is non-error feedback that also continues it once (standard). The input's
  `stop_hook_active` is true when a stop hook already continued the agent; the hook then never continues it again.
- PreCompact: the documented output can only block the compaction (`decision` = "block" or exit 2); Claude Code
  discards its `systemMessage` and it takes no `additionalContext`. So `aidd hook pre-compact` is a no-op, and the
  handoff note reminder goes through SessionStart with source "compact", which does reach the agent.

Every hook is deterministic, uses no model and no network, reads only local state, and acts only in a repository
with .aidd/config.toml. It never breaks the agent's session: on an internal error it allows, prints nothing on
stdout, and writes one short note to stderr. `[hooks]` in the config sets the level and turns each hook off.

Inside Orca (github.com/stablyai/orca, a desktop app that runs coding agents in git worktrees), session-start and
stop also put the first step of `aidd next` on the worktree's Orca card, with the work's state after it (working,
waiting on someone, stuck, or red: `card_state`), through the CLI Orca ships:
`orca worktree show|set --worktree path:<root> --comment <text> --json` (checked 2026-09-28 against Orca 1.4.215).
The CLI talks to the Orca app on this machine. The card is for people to glance at: it is never evidence and never
an approval. Outside Orca, or without its CLI, nothing happens; the update is time-boxed, silent on failure, and
never changes what the hook prints. `[hooks] orca_status = false` turns it off.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config as cfgmod
from . import gitutil, globs, model, resources, rules

TEST_REMINDER = "Run `aidd test` and report the result before you say the work is done"
HANDOFF_REMINDER = (
    "write the handoff note now, as a ```aidd-handoff block (done, next, needs, stopped_at) in the Spec or the PR/MR, where `aidd next` reads it back"
)
MAX_SUMMARY_LINES = 15
EVIDENCE_FILE = "evidence.json"


def _event(stdin) -> dict:
    try:
        data = json.load(stdin)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _repo(event: dict) -> str | None:
    """The top of the repository the session works in, when it has adopted aidd; else None."""
    cwd = Path(event.get("cwd") or os.getcwd())
    if not cwd.is_dir():
        return None
    top = gitutil.toplevel(str(cwd))
    return top if top and (Path(top) / cfgmod.CONFIG_PATH).is_file() else None


def _config(root: str) -> cfgmod.Config | None:
    from .guard import _offline_fetch

    try:
        return cfgmod.load_file(cfgmod.CONFIG_PATH, root, fetch=_offline_fetch)
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError, ValueError):
        return None


def level(cfg: cfgmod.Config) -> str:
    """minimal, standard, or strict: `[hooks] level`, or the profile's default (config.HOOK_LEVEL_DEFAULTS)."""
    return cfgmod.hook_level(cfg.raw)


def at_least(cfg: cfgmod.Config, wanted: str) -> bool:
    return cfgmod.HOOK_LEVELS.index(level(cfg)) >= cfgmod.HOOK_LEVELS.index(wanted)


def enabled(cfg: cfgmod.Config, switch: str) -> bool:
    """Whether `[hooks] <switch>` leaves the hook on (the default)."""
    return cfg.get("hooks", switch, default=True) is not False


def _emit(stdout, payload: dict) -> int:
    json.dump(payload, stdout)
    stdout.write("\n")
    return 0


# ---- SessionStart ----------------------------------------------------------------------------------------


def assessed_lane(root: str, cfg: cfgmod.Config) -> str | None:
    """One line: the route and lane `aidd next` computes for the branch's current diff (committed, staged, unstaged,
    and untracked, against the merge-base; `rules.assess_diff`), or None when there is no diff or it cannot tell. The
    entry rule, shown where the agent starts: it is advisory, from paths alone, and the gate re-checks the real diff."""
    try:
        r = rules.assess_diff(root)
    except Exception:  # noqa: BLE001  # a hint the agent can do without; the hook never fails on it
        return None
    if r is None:
        return None
    n = len(r["paths"])
    return (
        f"`aidd next` on this branch's diff ({n} path{'s' if n != 1 else ''}): "
        f"{r['route']} ({r['lane']} lane); `aidd next` gives the reasons, and the gate re-checks the real diff."
    )


def purpose(cfg: cfgmod.Config | None) -> str | None:
    """One line, "Mission: ... / Goal: ...", with whichever of the two the config sets; None when it sets neither."""
    parts = [f"{label}: {' '.join(str(cfg.get(key)).split())}" for key, label in (("mission", "Mission"), ("goal", "Goal")) if cfg and cfg.get(key)]
    return " / ".join(parts) or None


def summary(root: Path, lane: str | None = None, cfg: cfgmod.Config | None = None) -> str:
    """At most MAX_SUMMARY_LINES lines: what `aidd next` says for this repository, most urgent first, after the
    assessed lane for the branch's diff and the team's mission and goal, when there are any."""
    from . import nextstep

    # The route step is the lane line above, when there is one: never twice.
    steps = [s for s in nextstep.plan(root) if not (lane and s.get("code") == "route")]
    branch = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"], str(root), check=False).strip() or "unknown"
    lines = [f"aidd next on branch {branch} (`aidd next` has the full list):", *(x for x in (lane, purpose(cfg)) if x)]
    shown = 0
    for i, s in enumerate(steps, 1):
        if MAX_SUMMARY_LINES - len(lines) < 2 + (1 if i < len(steps) else 0):
            break
        lines += [f"{i}. {s['what']}", f"   {s['who']}: {s['how']}"]
        shown = i
    if shown < len(steps):
        lines.append(f"... and {len(steps) - shown} more")
    return "\n".join(lines[:MAX_SUMMARY_LINES])


def session_start(event: dict, stdout) -> int:
    root = _repo(event)
    cfg = _config(root) if root else None
    if cfg is None:
        return 0
    parts = []
    if enabled(cfg, "session_start"):
        parts.append(summary(Path(root), assessed_lane(root, cfg), cfg))  # type: ignore[arg-type]
    if event.get("source") == "compact" and at_least(cfg, "standard") and enabled(cfg, "compact_note"):
        parts.append(f"The context was just compacted. If the handoff note is not current, {HANDOFF_REMINDER}; then read it back and continue from Stopped at.")
    orca_card(root, cfg)  # type: ignore[arg-type]
    if not parts:
        return 0
    return _emit(stdout, {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(parts)}})


# ---- Stop and SubagentStop -------------------------------------------------------------------------------


def evidence_paths(cfg: cfgmod.Config) -> list[str]:
    """Where `aidd test` writes evidence: aidd-evidence/, and the configured artifact's folder when it differs."""
    dirs = ["aidd-evidence", str(cfg.get("evidence", "artifact", default="aidd-evidence") or "aidd-evidence")]
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


def missing_evidence(root: str, cfg: cfgmod.Config, specs: list[tuple[str, dict]], changed: list[str], in_scope: list[str]) -> str | None:
    """Why no evidence file proves the tests for this working tree, or None when one does.

    It proves them when its head_sha is HEAD, it is not partial (`aidd test --changed`, which the gate never accepts),
    every configured [[tests]] command that applies and every Spec's tests.commands passed on head (phase green), and
    no uncommitted in-scope file changed after it was written."""
    head = gitutil.rev_parse("HEAD", root)
    declared = [c for _, d in specs for c in (d.get("tests") or {}).get("commands", []) or [] if isinstance(c, dict) and c.get("name")]
    required, _ = rules.required_tests(list(cfg.get("tests", default=[]) or []), declared, "spec", changed)
    names = sorted({c["name"] for c, _ in required})
    dirty = set(gitutil.dirty(root, untracked=True, check=False))
    why = "no evidence from `aidd test` in " + " or ".join(evidence_paths(cfg))
    for rel, written, data in _evidence_files(Path(root), evidence_paths(cfg)):
        if not isinstance(data, dict) or data.get("head_sha") != head:
            why = f"{rel} is for another commit, not HEAD {head[:12]}"
            continue
        if data.get("partial"):
            why = f"{rel} is partial (`aidd test --changed`), and the gate needs a full `aidd test`"
            continue
        passed = {r.get("name") for r in data.get("results", []) if isinstance(r, dict) and r.get("phase", "green") == "green" and r.get("status") == "passed"}
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
    from .guard import role_of

    role = role_of(event)
    return bool(role) and "{scope}" in resources.roles()["roles"][role]["writes"]


def stop_check(root: str, cfg: cfgmod.Config) -> str | None:
    """The reminder the agent should get before it stops, or None when there is nothing to remind it of."""
    from .guard import _specs, branch_base, changed_since

    specs = _specs(root, cfg)
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


def stop(event: dict, stdout) -> int:
    if event.get("stop_hook_active") is True:
        return 0  # a stop hook already continued the agent: never loop
    root = _repo(event)
    cfg = _config(root) if root else None
    if cfg is None:
        return 0
    if event.get("hook_event_name") != "SubagentStop":  # the session's own stop; a subagent's stop never waits on Orca
        orca_card(root, cfg, stopping=True)  # type: ignore[arg-type]
    if not enabled(cfg, "stop_check") or not at_least(cfg, "standard") or not _ships_code(event):
        return 0
    reminder = stop_check(root, cfg)  # type: ignore[arg-type]
    if reminder is None:
        return 0
    if at_least(cfg, "strict"):
        return _emit(stdout, {"decision": "block", "reason": reminder})
    name = "SubagentStop" if event.get("hook_event_name") == "SubagentStop" else "Stop"
    return _emit(stdout, {"hookSpecificOutput": {"hookEventName": name, "additionalContext": reminder}})


# ---- The Orca workspace card -----------------------------------------------------------------------------

# Orca sets these in every terminal it manages (src/main/ipc/pty/ipc/spawn-env.ts in stablyai/orca, and the
# agent-hook environment). Any one of them means the hook runs inside Orca.
ORCA_ENV = ("ORCA_PANE_KEY", "ORCA_WORKTREE_ID", "ORCA_AGENT_HOOK_PORT")
ORCA_TIMEOUT = 2.0  # seconds for the whole card update, both CLI calls together
CARD_PREFIX = "aidd next: "
MAX_CARD_LINE = 160


# The state at the end of the card line. `stuck` is judged only when the agent stops: an agent that stops with no
# commit and no handoff note for this long has probably lost its way, and a person should look.
STUCK_MINUTES = 60
CARD_STATE_SEP = " | "
MAX_CARD_NAMES = 2  # approvers named in "waiting on ...", then "+N"
_FAILED = ("failed", "timeout", "not_started")


def failed_evidence(root: Path, cfg: cfgmod.Config | None) -> list[str]:
    """The commands the evidence for HEAD records as failed on the head (phase green), from the newest evidence file
    `aidd test` wrote; [] when there is none for HEAD or it passed. A red-phase failure on the base is expected."""
    head = gitutil.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    found = _evidence_files(root, evidence_paths(cfg) if cfg else ["aidd-evidence/" + EVIDENCE_FILE])
    for _, _, data in sorted(found, key=lambda x: x[1], reverse=True):
        if isinstance(data, dict) and head and data.get("head_sha") == head:
            results = [r for r in data.get("results", []) if isinstance(r, dict) and r.get("phase", "green") == "green"]
            return [str(r.get("name")) for r in results if r.get("status") in _FAILED]
    return []


def last_activity(root: Path, steps: list[dict]) -> float | None:
    """When the work last moved, as a Unix time: the newer of the HEAD commit's committer time and the modification
    time of an open Spec holding an ```aidd-handoff block (the file is where the agent writes its latest note)."""
    times = []
    head = gitutil.run(["log", "-1", "--format=%ct", "HEAD"], str(root), check=False).strip()
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


def card_state(root: Path, steps: list[dict], cfg: cfgmod.Config | None, *, stopping: bool = False, now: float | None = None) -> str | None:
    """The work's state in a few words, the first rule that holds winning:

    - `red: <commands> failed`: the evidence `aidd test` wrote for HEAD records a head test as failed
    - `waiting on <who>`: the first step is a person's (an approval names its eligible approvers)
    - `stuck: no commit or handoff note for <age>`: only when the agent stops, with its work still its own, and nothing
      moved (`last_activity`) for STUCK_MINUTES or more
    - `working`: the first step is the agent's
    None when nothing is open."""
    from . import nextstep

    first = steps[0] if steps else None
    if first is None or first.get("code") in ("nothing_open", "nothing_matches"):
        return None
    failed = failed_evidence(root, cfg)
    if failed:
        return f"red: {_names(failed)} failed on HEAD"
    who = str(first.get("who") or "")
    if not who.startswith(nextstep.AGENT):
        return f"waiting on {_names(first['approvers'])}" if first.get("approvers") else f"waiting on {who}"
    if stopping:
        moved = last_activity(root, steps)
        idle = int(((now if now is not None else time.time()) - moved) // 60) if moved is not None else 0
        if idle >= STUCK_MINUTES:
            return f"stuck: no commit or handoff note for {nextstep._age(idle)}"
    return "working"


def card_line(root: Path, cfg: cfgmod.Config | None = None, *, stopping: bool = False, now: float | None = None) -> str:
    """One short line for the card: the first step of `aidd next` and who takes it, then the state (`card_state`)
    after CARD_STATE_SEP. The step is shortened, never the state, so the line stays within MAX_CARD_LINE."""
    from . import nextstep

    steps = nextstep.plan(root)
    first = steps[0] if steps else {"what": "nothing is open on this branch", "who": nextstep.YOU}
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


def orca_card(root: str, cfg: cfgmod.Config, *, stopping: bool = False) -> None:
    """Best effort: show `aidd next` on this worktree's Orca card. Display only, never evidence. It does nothing
    outside Orca, without the Orca CLI, or with `[hooks] orca_status = false`; it never raises and never prints."""
    if not enabled(cfg, "orca_status") or not any(os.environ.get(name) for name in ORCA_ENV):
        return
    # The Orca CLI, found the way Orca's own skills find it: ORCA_CLI_COMMAND when Orca sets it (managed WSL
    # sessions), else `orca` on PATH; when that one is missing, never some other executable.
    exe = shutil.which(os.environ.get("ORCA_CLI_COMMAND") or "orca")
    if exe is None:
        return
    deadline = time.monotonic() + ORCA_TIMEOUT
    target = f"path:{root}"  # this worktree exactly; `active` would be whichever one the Orca window shows

    def orca(*args: str) -> subprocess.CompletedProcess:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("the Orca card update ran out of time")
        return subprocess.run([exe, *args, "--json"], capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=root, timeout=left, check=False)

    try:
        line = card_line(Path(root), cfg, stopping=stopping)
        shown = orca("worktree", "show", "--worktree", target)
        if shown.returncode != 0:
            return
        current = str(((json.loads(shown.stdout).get("result") or {}).get("worktree") or {}).get("comment") or "")
        comment = merge_comment(current, line)
        if comment != current:
            orca("worktree", "set", "--worktree", target, "--comment", comment)
    except Exception:  # noqa: BLE001  # the card is a courtesy: it never breaks the hook or outlives its time box
        return


# ---- PreCompact ------------------------------------------------------------------------------------------


def pre_compact(event: dict, stdout) -> int:
    """A no-op by design: PreCompact output can block a compaction but cannot add context (Claude Code discards its
    systemMessage and it takes no additionalContext), and blocking would stop a session at its context limit. The
    handoff reminder is added after the compaction instead, by session-start with source "compact"."""
    return 0


HANDLERS = {"session-start": session_start, "stop": stop, "pre-compact": pre_compact}


def run(name: str, stdin=None, stdout=None, stderr=None) -> int:
    """Run one hook. Any failure of its own allows: exit 0, nothing on stdout, a short note on stderr."""
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    offline = os.environ.get("AIDD_HOOK_OFFLINE")
    os.environ["AIDD_HOOK_OFFLINE"] = "1"  # every config load in the hook skips an `extends` URL: never the network
    try:
        return HANDLERS[name](_event(stdin), stdout)
    except Exception as exc:  # noqa: BLE001  # a helper hook must never break the agent's session
        print(f"aidd hook {name}: skipped after an internal error ({type(exc).__name__}); allowing", file=stderr)
        return 0
    finally:
        if offline is None:
            os.environ.pop("AIDD_HOOK_OFFLINE", None)
        else:
            os.environ["AIDD_HOOK_OFFLINE"] = offline
