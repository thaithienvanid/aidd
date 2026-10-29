"""The Orca workspace card: inside Orca (github.com/stablyai/orca, a desktop app that runs coding agents in git
worktrees), session-start and stop put this change's first step on the worktree's card, with the work's state after
it (working, waiting on someone, stuck, or red: `card_state`), move the worktree to its board column (`board_status`),
and mark it unread while a person decides; `aidd publish` links the PR/MR it opened (`orca_link`). All through the CLI
Orca ships: `orca worktree show|set --worktree path:<root>` with `--comment`, `--workspace-status`, `--unread` or
`--read`, `--pr`, and `--gitlab-mr`, and `--json` (checked 2026-10-22 against Orca 1.4.237). The CLI talks to the Orca
app on this machine. The card is for people to glance at: it is never evidence and never an approval. Outside Orca, or
without its CLI, nothing happens; each update is time-boxed, silent on failure, and never changes what the hook prints.
`hooks.orca_status: false` turns it off.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from aidd import config
from aidd.guard import hook_settings
from aidd.kernel import git

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
    found = hook_settings.evidence_files(root, hook_settings.evidence_paths(cfg) if cfg else [f"{config.EVIDENCE_DIR}/{hook_settings.EVIDENCE_FILE}"])
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
    return card_view(root, cfg, stopping=stopping, now=now)[0]


# The board column each state puts the worktree in (`orca worktree set --workspace-status`, Orca's default ids,
# checked against Orca 1.4.237): no work yet, the agent's work (working, red, or stuck), a person's decision, and
# landed or merged.
BOARD_TODO, BOARD_IN_PROGRESS, BOARD_IN_REVIEW, BOARD_COMPLETED = "todo", "in-progress", "in-review", "completed"
_BOARD_DONE = frozenset({"spec.landed", "spec.done"})


def board_status(first_code: str | None, state: str | None) -> str:
    """The board column for the first step's code and the card's state (`card_state`)."""
    if first_code in _BOARD_DONE:
        return BOARD_COMPLETED
    if state is None:
        return BOARD_TODO
    return BOARD_IN_REVIEW if state.startswith("waiting on") else BOARD_IN_PROGRESS


def card_view(root: Path, cfg: config.Config | None = None, *, stopping: bool = False, now: float | None = None) -> tuple[str, str]:
    """(the card's line, its board column): `card_line`, and `board_status` for the same first step."""
    from aidd import tracking, workitems

    steps = tracking.plan(root)
    first = steps[0] if steps else {"what": "nothing is open on this branch", "who": workitems.AUTHOR}
    line = " ".join(f"{CARD_PREFIX}{first['what']} ({first['who']})".split())
    state = card_state(root, steps, cfg if cfg is not None else hook_settings.load_config(str(root)), stopping=stopping, now=now)
    tail = f"{CARD_STATE_SEP}{state}" if state else ""
    room = MAX_CARD_LINE - len(tail)
    if len(line) > room:
        line = line[: room - 3] + "..."
    return (line + tail)[:MAX_CARD_LINE], board_status(first.get("code") if steps else None, state)


def _was_waiting(comment: str) -> bool:
    """Whether aidd's own line on the card said the work waited on a person, which set the unread dot."""
    mine = next((x for x in comment.splitlines() if x.startswith(CARD_PREFIX)), "")
    return mine.rpartition(CARD_STATE_SEP)[2].startswith("waiting on") if CARD_STATE_SEP in mine else False


def merge_comment(current: str, line: str) -> str:
    """The card's comment with aidd's line in it. aidd's line replaces its own earlier one; every other line, which a
    person or another agent wrote, stays as it was."""
    lines = current.splitlines()
    for i, old in enumerate(lines):
        if old.startswith(CARD_PREFIX):
            return "\n".join(lines[:i] + [line] + [x for x in lines[i + 1 :] if not x.startswith(CARD_PREFIX)])
    return "\n".join([*lines, line]) if current.strip() else line


def _orca_cli(root: str, cfg: config.Config | None) -> tuple[str, str] | None:
    """(the Orca CLI, this worktree's selector) when the card may be updated here, else None: inside Orca, with its
    CLI, and with `hooks.orca_status` on."""
    if cfg is None or not hook_settings.enabled(cfg, "orca_status") or not any(os.environ.get(name) for name in ORCA_ENV):
        return None
    # The Orca CLI, found the way Orca's own skills find it: ORCA_CLI_COMMAND when Orca sets it (managed WSL
    # sessions), else `orca` on PATH; when that one is missing, never some other executable.
    exe = shutil.which(os.environ.get("ORCA_CLI_COMMAND") or "orca")
    # This worktree exactly; `active` would be whichever one the Orca window shows.
    return (exe, f"path:{root}") if exe else None


def _orca_runner(exe: str, root: str):
    """A runner of `orca <args> --json` whose calls share one time box of ORCA_TIMEOUT_SECONDS, started now."""
    deadline = time.monotonic() + ORCA_TIMEOUT_SECONDS

    def orca(*args: str) -> subprocess.CompletedProcess:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("the Orca card update ran out of time")
        return subprocess.run([exe, *args, "--json"], capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=root, timeout=left, check=False)

    return orca


def orca_card(root: str, cfg: config.Config, *, stopping: bool = False) -> None:
    """Best effort: show this change's first step on this worktree's Orca card, put the worktree in its board column
    (`board_status`), and mark it unread while the next step is a person's decision, read again once it is not. Display
    only, never evidence. It does nothing outside Orca, without the Orca CLI, or with `hooks.orca_status: false`; it
    never raises and never prints, and it writes only what changed."""
    found = _orca_cli(root, cfg)
    if found is None:
        return
    exe, target = found
    try:
        line, status = card_view(Path(root), cfg, stopping=stopping)
        orca = _orca_runner(exe, root)  # the time box is the CLI calls', never the plan's
        shown = orca("worktree", "show", "--worktree", target)
        if shown.returncode != 0:
            return
        worktree = (json.loads(shown.stdout).get("result") or {}).get("worktree") or {}
        current = str(worktree.get("comment") or "")
        comment = merge_comment(current, line)
        changes = ["--comment", comment] if comment != current else []
        changes += ["--workspace-status", status] if worktree.get("workspaceStatus") != status else []
        if status == BOARD_IN_REVIEW and worktree.get("isUnread") is not True:
            changes.append("--unread")
        elif status != BOARD_IN_REVIEW and _was_waiting(current) and worktree.get("isUnread") is True:
            changes.append("--read")  # only the dot aidd set: Orca's own unread marks stay
        if changes:
            orca("worktree", "set", "--worktree", target, *changes)
    except Exception:  # noqa: BLE001  # the card is a courtesy: it never breaks the hook or outlives its time box
        return


# A pull request's or a merge request's number in the URL `aidd publish` opened it at.
_CHANGE_URL = re.compile(r"/pull/(\d+)/?$|/-/merge_requests/(\d+)/?$|/merge_requests/(\d+)/?$")


def orca_link(root: str, cfg: config.Config | None, url: str) -> None:
    """Best effort, once `aidd publish` opened the change's PR/MR at `url`: link it on this worktree's Orca card
    (`--pr <number>` for a GitHub pull request, `--gitlab-mr <number>` for a GitLab merge request). The same
    conditions, time box, and silence as the card (`orca_card`); never evidence."""
    found = _orca_cli(root, cfg)
    match = _CHANGE_URL.search(url or "")
    if found is None or match is None:
        return
    exe, target = found
    link = ["--pr", match.group(1)] if match.group(1) else ["--gitlab-mr", match.group(2) or match.group(3)]
    try:
        _orca_runner(exe, root)("worktree", "set", "--worktree", target, *link)
    except Exception:  # noqa: BLE001  # a courtesy: a publish never fails for it
        return
