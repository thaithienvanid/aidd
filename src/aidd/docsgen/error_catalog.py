"""The error catalog, docs/ERRORS.md: every code a person meets, each with its own anchor (kernel.text.code_anchor).

The finding codes come from the gate's rulebook, the step codes from the step-code contract and its meanings, and the
exit codes from the command line (`CliFacts.exit_codes`). The guard's reason codes are the codes its denial log
records (`aidd metrics --guard`), and GUARD_REASONS below says what each means and what to do. A test keeps GUARD_REASONS
equal to the guard's REASON_CODES, so a new deny reason needs a row in both.
"""

from __future__ import annotations

from aidd import gate
from aidd.docsgen import blocks, cli_reference, team_reference
from aidd.kernel import text as kernel_text

# What each guard reason code means, and the next step that works: (what the guard denied, what to do).
GUARD_REASONS: dict[str, tuple[str, str]] = {
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
        "a test or design file, or a frozen doc, of a Spec whose approval holds: any edit voids the approval",
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
        "a subagent that is not an aidd-team role tried to write: a helper only reads",
        "spawn it as an `aidd-team:<role>` to write, or hand the edit back to the role or the author",
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

STEP_PREFIX, GUARD_PREFIX, EXIT_PREFIX = "step-", "guard-", "exit-"


def anchored(code: str, prefix: str = "") -> str:
    """A code as its table cell shows it: the anchor, then the code."""
    return f'<a id="{prefix}{kernel_text.code_anchor(code)}"></a>`{code}`'


def finding_codes() -> str:
    """Every finding code, under the question its rule answers: the code, its rule, what fires it, and its fix, which
    the rulebook owns (`Rule.fix_for`)."""
    rules = {r.name: r for r in gate.RULES}
    sections = []
    for question, names in gate.QUESTIONS:
        rows = (
            [anchored(code), f"`{name}`", kernel_text.md_cell(meaning), kernel_text.md_cell(rules[name].fix_for(code))]
            for name in names
            for code, meaning in rules[name].codes.items()
        )
        sections.append(f"### {question}\n\n" + blocks.markdown_table("Code | Rule | Fires when | What to do", rows))
    return "\n\n".join(sections)


def step_codes() -> str:
    """Every step code `aidd list` and `aidd autopilot next` show: who takes it, what it means, and what runs it."""
    from aidd import autopilot

    meanings = autopilot.step_meanings()
    rows = (
        [anchored(code, STEP_PREFIX), who, kernel_text.md_cell(meanings[code]), team_reference.step_runs(code)]
        for code, who in sorted(autopilot.contract().items())
    )
    return blocks.markdown_table("Code | Who takes it | What it means | What `aidd autopilot next` runs", rows)


def guard_codes() -> str:
    """Every reason code the guard logs for a deny: what it denied, and what to do instead."""
    rows = ([anchored(code, GUARD_PREFIX), kernel_text.md_cell(what), kernel_text.md_cell(fix)] for code, (what, fix) in sorted(GUARD_REASONS.items()))
    return blocks.markdown_table("Code | What the guard denied | What to do", rows)


def exit_codes(cli: cli_reference.CliFacts) -> str:
    """Each exit code, with what it means for each command that exits with it."""
    rows = (
        [anchored(str(n), EXIT_PREFIX), "; ".join(f"{command}: {kernel_text.md_cell(means[n])}" for command, means in cli.exit_codes if means[n])]
        for n in range(4)
    )
    return blocks.markdown_table("Code | What it means", rows)


def exit_table(cli: cli_reference.CliFacts) -> str:
    """The exit codes by command, for docs/CLI.md."""
    return blocks.markdown_table("Command | 0 | 1 | 2 | 3", ([command, *map(kernel_text.md_cell, means)] for command, means in cli.exit_codes))
