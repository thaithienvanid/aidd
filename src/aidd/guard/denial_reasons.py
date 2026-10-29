"""What each guard reason code means, and the next step that works: the error catalog (docs/ERRORS.md) prints them,
and the session-start note names the ones the guard keeps denying in a repository (repeated_denials_note)."""

from __future__ import annotations

import datetime as dt
import json
import os
import stat

from aidd import config

# What each guard reason code means, and the next step that works: (what the guard denied, what to do).
GUARD_REASONS: dict[str, tuple[str, str]] = {
    "browser_code": (
        "a browser tool (Playwright MCP's `browser_run_code_unsafe`) runs any code, so it can open any address",
        "use `browser_evaluate` to read the page instead; the guard holds the browser to reading and clicking local pages",
    ),
    "browser_page": (
        "a browser tool would open an address that is not a local page and not a host in `agents.browser_hosts`, or one the guard cannot read",
        "open a local preview (serve the page on `http://localhost:<port>`, or a `*.localhost` or `*.test` host), or ask the person to add the host to `agents.browser_hosts`",
    ),
    "approval_post": (
        "a command carries `/aidd approve`, and it does more than read",
        "leave the line out; the person types `approve <ID>` at the prompt, and aidd posts it as them",
    ),
    "decision_record": (
        "a command names `refs/aidd/decisions` or the `Aidd-Merge-Approval` trailer, where local approvals are recorded",
        "only read those approvals; the person types the decision, and aidd records it",
    ),
    "decision_typed": (
        "a command types an approval or a decision word into another terminal or program, where it would pass for the person's keyboard",
        "word the message without it; the person types the decision at the prompt, or answers aidd's dialog",
    ),
    "device_command": (
        "an `orca emulator exec` runs a device command its allowlist does not name, a word that is not plain, a word after `emulator exec` that is no flag's value, or a line with a newline or a backtick",
        "type text with `orca emulator type <text>`, run listed commands joined with `&&` inside one `--command`, or ask the person to run it in their own terminal",
    ),
    "approve_or_merge": (
        "an agent ran a command that approves or merges: `aidd approve`, `aidd land`, `gh pr review --approve`, `gh pr merge`, or an API call that does it",
        "stop and tell the person; they type `approve <ID>`, `land it`, or `merge it` at the prompt, or their standing approval covers it",
    ),
    "autopilot_session": (
        "the command starts or stops autopilot for another session",
        "start and stop autopilot only for this session, with the id the harness gives it",
    ),
    "base_branch": (
        "a git command lands work on the base branch, or moves it",
        "work reaches the base branch through `aidd land` once the person types `land it`, or through its PR/MR once they type `publish`",
    ),
    "config_invalid": (
        "`.aidd/config.yaml` does not parse or validate, so no role writes until it is fixed",
        "run `aidd validate`; the person fixes the config in their own session",
    ),
    "decision_unreadable": (
        "a shell write, or a tool with no new text, to a file that holds a person's decision, which the guard cannot read",
        "use the Edit or Write tool, and leave the decision itself to the person",
    ),
    "delegate": (
        "`agents.delegate` makes the main session hand this edit to an aidd-team role",
        "start the role the denial names, or ask the person to change `agents.delegate`",
    ),
    "exploration_decision": (
        "an edit adds or changes an exploration's `outcome`, which only a person records",
        "write the evidence, and leave the outcome to the person",
    ),
    "frozen_file": (
        "a test or design file, a frozen doc, or a frozen test section of a manifest, of a Spec whose approval holds, or went stale with no `aidd revise` since: any edit voids the approval",
        '`aidd revise <ID> "<what was wrong>"`, then the file\'s owner changes it, and the person approves the new hash',
    ),
    "git_dir": (
        "an edit or a shell write inside the git directory",
        "run the git or aidd command that changes it",
    ),
    "guard_failed": (
        "the guard could not run git, read the active Spec, or check the held commands, so it denies",
        "run `aidd doctor`, fix what it names, and try again",
    ),
    "hard_link": (
        "the file has more than one hard link, so a write changes it under every other name",
        "write a new file instead, or leave it alone",
    ),
    "held_command": (
        "the command matches a `guard.held_commands` entry, such as a production deploy",
        "ask the person to run it, or to start the session with the entry's `requires` variable set",
    ),
    "subagent_read_only": (
        "a subagent that is not an aidd-team role tried to write, or to run a program that is not on the guard's read list: a helper only reads",
        "hand the work back to the role or the lead; the lead starts an aidd-team role to write or run tests (`aidd-team:<role>` in Claude Code, `aidd-<role>` elsewhere)",
    ),
    "subagent_start": (
        "a role or a helper started another aidd-team role: only the lead does, and a role starts its own type or a read-only helper",
        "hand the step back to the lead, which starts the role itself",
    ),
    "initiative_decision": (
        "an edit adds or changes an Initiative's `go_no_go`, which only a person records",
        "write the rest, and leave the decision to the person",
    ),
    "no_active_spec": (
        "no active Spec, so the file has no approved scope",
        "start Specify with `aidd new spec` (or `/aidd-team:specify`); on a branch with several Specs, name it `spec/<ID>` or set `AIDD_SPEC`",
    ),
    "not_owner": (
        "a test, design, or doc file of the Spec, from a role that does not own it",
        "hand the change to the owner the denial names, such as the verifier for a test file",
    ),
    "other": (
        "a deny reason that no reason code names yet",
        "read the reason the guard printed: it names the next step",
    ),
    "out_of_scope": (
        "the file is outside every Task's scope in the active Spec",
        "add the file to a Task's scope in the Spec, and ask the person to approve it again; or leave the file alone",
    ),
    "proposal_decision": (
        "an edit adds or changes a proposal's `go_no_go`, `sign_off`, or `outcome`, or an agent ran the command that records one",
        "write the rest; the person types `decide <proposal> go` or `sign off <proposal>` at the prompt",
    ),
    "proposal_part": (
        "a role edits a part of a proposal that another role writes",
        "hand off to the role that writes that part",
    ),
    "protected_branch": (
        "a push rewrites or deletes main, master, trunk, or the default branch",
        "push your own branch without force; a person changes the protected branches",
    ),
    "protected_path": (
        "a protected path, such as the config, CI, or agent instructions, with no approved scope that covers it",
        "put it in a Task's scope, and ask the person to approve the Spec; or leave it alone",
    ),
    "review_dismissal": (
        "an edit adds, changes, or moves a dismissed finding in REVIEW.md",
        "report the finding, and leave its dismissal to the person who decides",
    ),
    "role_area": (
        "the file is outside the role's write area, or the role is read-only",
        "hand the file to the role the denial names, or to the person when no role writes it",
    ),
    "shell_opaque": (
        "a shell command runs code the guard cannot read: a command substitution, a shell fed from stdin or a here-document, `source`, `xargs`, or `find -exec`",
        "use the Write or Edit tool, or split it into plain commands",
    ),
    "shell_unknown_target": (
        "a shell write names its file through `$VAR`, a glob, or a patch the guard cannot read",
        "use Write or Edit with a literal path, or a plain command that names the file",
    ),
    "shell_unparsed": (
        "the shell check cannot parse the command, such as one with an unbalanced quote, and the profile fails closed",
        "balance the quotes, or put the text in a file",
    ),
    "signing_config": (
        "a `git config` command changes commit signing (`gpg.*`, `user.signingkey`)",
        "leave signing to the person; reading it is fine",
    ),
    "unknown_role": (
        "the hook names an aidd-team role the team does not have",
        "name a role from the team (`schemas/roles.json`)",
    ),
}


# How far back the note looks, how often a reason must repeat to count, how many it names, and how much of the log's end
# it reads, so the hook stays fast on a long log.
REPEATED_DENIAL_DAYS = 7
REPEATED_DENIAL_MIN = 3
REPEATED_DENIALS_SHOWN = 3
_LOG_TAIL_BYTES = 256 * 1024


def repeated_denials(root: str, now: dt.datetime | None = None) -> list[tuple[str, int]]:
    """(reason code, count) for the reasons the guard denied at least REPEATED_DENIAL_MIN times in the last REPEATED_DENIAL_DAYS days, most
    first, at most REPEATED_DENIALS_SHOWN, from the end of the guard log; [] when there is none or the log cannot be read."""
    since = (now or dt.datetime.now(dt.UTC)) - dt.timedelta(days=REPEATED_DENIAL_DAYS)
    try:
        fd = os.open(config.guard_log(root), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                return []
            fh.seek(0, 2)
            start = max(0, fh.tell() - _LOG_TAIL_BYTES)
            fh.seek(start)
            lines = fh.read().decode("utf-8", errors="replace").splitlines()[1 if start else 0 :]
    except OSError:
        return []
    counts: dict[str, int] = {}
    for line in lines:
        try:
            entry = json.loads(line)
            at = dt.datetime.fromisoformat(str(entry["ts"]).replace("Z", "+00:00"))
            recent = at.tzinfo is not None and at >= since
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
            continue
        code = entry.get("reason")
        if recent and isinstance(code, str) and code in GUARD_REASONS and code != "other":  # "other" names no step
            counts[code] = counts.get(code, 0) + 1
    ranked = sorted(((c, n) for c, n in counts.items() if n >= REPEATED_DENIAL_MIN), key=lambda cn: (-cn[1], cn[0]))
    return ranked[:REPEATED_DENIALS_SHOWN]


def repeated_denials_note(root: str, now: dt.datetime | None = None) -> str | None:
    """The session-start lines on what the guard keeps denying here, one a reason, each with the step that works
    instead; None when nothing repeats."""
    found = repeated_denials(root, now)
    if not found:
        return None
    lines = [f"- {GUARD_REASONS[code][0]} ({n} times). Instead: {GUARD_REASONS[code][1]}." for code, n in found]
    return f"aidd: what the guard denied most here in the last {REPEATED_DENIAL_DAYS} days:\n" + "\n".join(lines)
