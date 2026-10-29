"""The error catalog, docs/ERRORS.md: every code a person meets, each with its own anchor (kernel.text.code_anchor).

The finding codes come from the gate's rulebook, the step codes from the step-code contract and its meanings, and the
exit codes from the command line (`CliFacts.exit_codes`). The guard's reason codes are the codes its denial log
records (`aidd metrics --guard`), and the guard's GUARD_REASONS says what each means and what to do. A test keeps
GUARD_REASONS equal to the guard's REASON_CODES, so a new deny reason needs a row in both.
"""

from __future__ import annotations

from aidd import gate, guard
from aidd.docsgen import blocks, cli_reference, team_reference
from aidd.kernel import text as kernel_text

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
    rows = ([anchored(code, GUARD_PREFIX), kernel_text.md_cell(what), kernel_text.md_cell(fix)] for code, (what, fix) in sorted(guard.GUARD_REASONS.items()))
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
