"""The guard for agents: is this path inside the active Spec's scope, and may this agent write it?

The gate decides at merge; this catches the same mistakes while the agent
works, where they are cheapest to fix. It runs locally, so it is a guide, not
a control: it allows when it cannot tell (no config, no git repository, no active Spec),
and the gate re-checks everything. A config that exists but is invalid or cannot be read never turns it off: every
session meets the deploy and infrastructure commands `aidd init` detects (setup.default_held), a role or a helper
writes nothing, the person's own session may edit (to fix the config), and session-start names the problem. The hook runs git only from a system path, with the repository's fsmonitor,
hooks, and driver programs off (`git.system_only`). In a repository that has adopted aidd, a git that cannot run or
read it is a deny. That defends against the repository's committed content, not against a local writer of
`.git/config`, HOME, or the git programs.

The guard answers allow or deny, never "ask": an approval prompt during the build would put a person back on
the critical path of every session running in parallel. Each deny names the route that fixes it; humans
approve at Spec approval and Merge approval, and a deploy waits for its held-command approval.

Decisions for an edit (Edit, Write, MultiEdit, NotebookEdit):
- deny: outside every Task's `scope` of the active Spec; outside an aidd-team role's write area;
  from a subagent that is not an aidd-team role (the loop contract's helper rule: a helper of another type only reads);
  a protected path outside every approved scope, or with no active Spec; a test or design file or a frozen doc
  once the Spec's approval holds (an approval of its current hash, or a stored status at or past ready where nothing local
  records approvals), or, before that, by a role that does not own it
- allow: everything else, including a protected path inside a Task's scope (the gate makes the change major)

Decisions for a shell command (Bash, or PowerShell, checked the same way), in a repository that has adopted aidd:
- deny: approving or merging a PR/MR (`gh pr review --approve`, `gh pr merge`, `gh api` review and merge
  calls, `glab mr approve|merge`), `aidd approve` and `aidd land` through any wrapper (`uvx`, `uv run`, `pipx run`,
  `python -m`, `xargs`), a force push to or a deletion of main, master, trunk, or the repository's default branch
  (a push with no refspec counts as the current branch), and any command whose text carries `/aidd approve`,
  `/aidd approve-spec`, the decision records' ref (`refs/aidd/decisions`, or `refs/aidd/approvals` before 1.0), or
  `Aidd-Merge-Approval` unless it only reads: agents never
  approve, merge, or post an approval. The denial names the dialog tool where a person approves after a yes in the chat.
  What `xargs`, `parallel`, and `find -exec|-execdir|-ok|-okdir` run is read as the agent's own command, each word they
  fill in as a name only the shell resolves (indirect_runs), so a git ref or branch, or a `git`, `gh`, `glab`, or
  `aidd` command, that only their input names is denied
- allow: `aidd approve spec|merge` and `aidd land` while the person's standing approval holds, `aidd land` after they
  typed "land it" or "merge it" for this head, `aidd publish` after they typed "publish" for it, and `aidd approve stop` always; never `aidd approve all` or `--confirmed`
- deny: sending text that approves (`aidd approve`, `aidd land`, `/aidd approve`, a decision record) into another
  terminal or program, or starting a program there with it, where it would run as if a person typed it: `orca terminal
  send|create|split`, `orca orchestration send|ask|reply|dispatch`, `orca computer type-text|paste-text|press-key|hotkey`,
  `orca emulator type|exec`, `orca agent launch|worktree create --prompt` and `orca orchestration task-create|worker-start
  --spec` (judged whole),
  `tmux send-keys` (and `new-window`, `new-session`, `split-window`, `respawn-pane|window`), `screen`, `zellij run` and
  `zellij action write-chars|write|new-pane`, `open -a <terminal>`, `osascript`, `xdotool type|key`, `wtype`,
  `ydotool type`, `expect`, `kitty`, `wezterm`, a terminal emulator's command, or a write to /dev/tty* or /dev/pts/*.
  The text is matched as written, and again as the program receives it: unquoted, with tmux key names (`Space`,
  `Enter`) as the keys they send, and with the words run together, so quoting or escaping does not hide it. It would
  defeat the check that a person runs `aidd approve` in a terminal an agent did not start
- deny: a `git config` that sets, unsets, or edits commit signing (`gpg.*`, `user.signingkey`, their sections, or the
  whole file with `--edit`): which key signs and which signatures count are a person's settings. Reading them is fine
- deny: for a role, a proposal part that is not its own, and an edit that adds or changes a proposal's `go_no_go`,
  `sign_off`, or `outcome`, an Initiative's `go_no_go`, an exploration's `outcome`, or a line of REVIEW.md that looks
  like a dismissed finding in any shape, or an edit that moves one under its heading (compared on the hook's Edit and
  Write input), which only a person records; and any other write to REVIEW.md (a shell write, a tool with no new text),
  which the dismissal check cannot read
- deny: a command that matches a `guard.held_commands` entry (a production deploy, say) unless the
  environment Claude Code started with carries that entry's `requires` variable, which a person sets
- deny: for a role or a helper subagent, an obvious shell write (a `>` or `>>` redirect, also after a subshell group
  or a command substitution, `tee`, `sed -i`, `cp`, `mv`, `rm`, `touch`, `dd of=`, `git apply`, `patch`, and the
  source of a hard link: `ln` without `-s`, `link`, `cp -l`) whose target the edit rules above deny, or whose target
  the check cannot read (a patch from a pipe, an unexpanded `$VAR` or glob); for the main session, the same writes
  that `agents.delegate` denies
- deny: for a writer the guard holds (a role, a helper, or a main session that `delegate` denies), a command that runs
  code the parser cannot read (OPAQUE), a closed list: a command substitution or backticks where a command starts; a
  shell fed by stdin (a here-string, a here-document, an input file, or a pipe); `trap` with a command, `source`, `.`;
  `xargs`, `parallel`, `find -exec|-execdir|-ok|-okdir`, except `xargs` or `find -exec|-execdir` that runs only a literal
  reader (`wc`, `grep`, `head`, `tail`, `cat`, `basename`, `dirname`, `ls`, `stat`; `sort` and `file` after a literal
  `--`) with literal words (indirect_runs). `exec`, `command`, and `builtin` are followed as wrappers, and
  a write target with a brace expansion (`src/{a,b}.py`) is unreadable like a glob. A program that writes by itself
  (an interpreter, a build tool, a package manager) stays the documented limit; what one changes that the
  always-on rules stand on, `aidd land`, `aidd approve`, and `aidd publish` show at the next decision (outside_changes.py)
- deny: for a helper subagent, which only reads, every command but a read on helper_runs' list (git and aidd only
  by their listed reads), and each option of one that writes a file or starts a program the command names; PowerShell,
  a program named by its path or through a wrapper, a variable the line sets, and a shell that runs anything but a
  `-c` line of reads are denied too
- deny: a write to a file with more than one hard link, by a writer the guard holds (a role, a helper, or a main
  session that `delegate` denies): the guard cannot tell whether another name of it is repository content
- deny: `aidd autopilot start|stop` with a `--session` that is not the hook event's own `session_id`, so an agent never
  binds the lease to another session, such as the person's (anywhere, even outside an adopted repository)
- allow: everything else

Each write a tool names (an Edit's path, a shell write's target, an MCP tool's path) is judged in the repository
that holds it, found from the path itself (`locate`), never from the session's cwd: a sibling or nested worktree,
or a session started outside the repository, meets the same rules. The path follows symbolic links and takes the
case it has on disk, and a file git tracks is repository content even in an ignored folder. An edit tool never
writes inside a `.git` folder. The known limits are in SECURITY.md (the trust model).

Decisions for an MCP tool (`mcp__<server>__<tool>`), in a repository that has adopted aidd:
- deny: a tool that merges or approves (`merge_pull_request`, `approve_merge_request`, `enable_auto_merge`, and the
  same words in camelCase or kebab-case, `mergePullRequest`, `complete-pull-request`), sets a commit status, submits a
  review whose input says APPROVE, or carries a `/aidd approve` line; a name that starts with a read verb (get, list,
  search, read, check, is, can, view, describe) only reads
- deny: for a main session that `agents.delegate` denies, a tool that writes a file of a repository: each path
  under `path`, `file_path`, `filename`, `file`, `source`, `destination`, `target`, `src`, `dest`, `old_path`,
  `new_path`, a `file:` `uri`, and in `files` or `paths`
- allow: every other MCP tool

The shell check follows a subshell group, a command substitution, and a `case` pattern's `)`, reads `cd` as bash
does (logical, `-P`, `cd -`), and reads a command with a here-document twice, with and without the bodies. It
follows `sh -c` and `eval` MAX_NESTING levels deep; deeper, or when parsing fails, a writer the guard holds is denied.
tests/test_guard_oracle.py checks its decisions against what real bash writes.

The shell check tokenizes with shlex and follows `&&`, `;`, `|`, `cd`, and `sh -c`, but it does not run the shell.
So a program that writes by itself (an interpreter such as `python -c`, a build tool, a package manager) is not seen,
nor is a write the parser reads differently from bash, nor, for a writer the guard does not hold, a target it cannot
read (`$VAR`, a glob). That is why it guides and the gate's scope rule, on the real diff, decides. Program names compare as
Windows names too (`gh.exe`, `GH.EXE`, `aidd.cmd`), and a PowerShell command loses its backtick escapes first. A command
shlex cannot read is read again with its ANSI-C strings (`$'it\\'s'`) rewritten and its here-document bodies set aside
(a body a shell reads is checked as commands); one it still cannot read is denied when its raw text approves, merges,
or force-pushes, and denied outright under AIDD_HOOK_FAIL_CLOSED=1.

Each deny of the hook appends one JSON line to guard.jsonl in the git directory (config.guard_log), which every
worktree shares and git never commits: when, the role, the tool, the path or command (at most 200 characters, never a
file's contents), and the reason code (REASON_CODES).
Secret-looking values in a logged command (an Authorization header, a bearer token, `*_TOKEN=`, `*_KEY=`,
`*SECRET*=`, `--password X`, a URL's `user:password@`) are replaced with `***` first. `aidd metrics --guard` counts them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "Answer",
    "DECISION_KINDS",
    "check_decision",
    "check_edit",
    "check_typed",
    "counted_note",
    "changes_since_decision",
    "pre_tool_hook",
    "record_checked",
    "keep_state_at_decision",
    "repo_relative",
    "orca_link",
    "run_session_hook",
    "shown_outside",
]

if TYPE_CHECKING:
    from aidd.guard.edit_check import check_edit as check_edit
    from aidd.guard.outside_changes import DECISION_KINDS as DECISION_KINDS
    from aidd.guard.outside_changes import Answer as Answer
    from aidd.guard.outside_changes import changes_since_decision as changes_since_decision
    from aidd.guard.outside_changes import check_decision as check_decision
    from aidd.guard.outside_changes import check_typed as check_typed
    from aidd.guard.outside_changes import counted_note as counted_note
    from aidd.guard.outside_changes import keep_state_at_decision as keep_state_at_decision
    from aidd.guard.outside_changes import record_checked as record_checked
    from aidd.guard.outside_changes import shown_outside as shown_outside
    from aidd.guard.pre_tool import pre_tool_hook as pre_tool_hook
    from aidd.guard.repo_config import repo_relative as repo_relative
    from aidd.guard.session_hooks import run_session_hook as run_session_hook
    from aidd.guard.workspace_card import orca_link as orca_link
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "Answer": "outside_changes",
            "DECISION_KINDS": "outside_changes",
            "check_decision": "outside_changes",
            "check_edit": "edit_check",
            "check_typed": "outside_changes",
            "counted_note": "outside_changes",
            "changes_since_decision": "outside_changes",
            "pre_tool_hook": "pre_tool",
            "record_checked": "outside_changes",
            "keep_state_at_decision": "outside_changes",
            "repo_relative": "repo_config",
            "orca_link": "workspace_card",
            "run_session_hook": "session_hooks",
            "shown_outside": "outside_changes",
        },
    )
