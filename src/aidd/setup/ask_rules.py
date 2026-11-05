"""The coding agents' ask rules, written from the risk rules in force and the tests of the approved Specs. `aidd init` and
`aidd upgrade` write them, and `aidd doctor` compares them. Split from `adoption` to keep each module short."""

from __future__ import annotations

from pathlib import Path

from aidd import config, risk, workitems
from aidd.kernel import documents, git, regular_files


def push_rule_branches(root: Path) -> list[str]:
    """The branches the ask rules for a push to the default branch name: the default branch when the repository tells
    it, else every branch that could be it (`kernel.git.default_branches`), so a harness asks for more, never less. A
    local-only repository whose trunk has another name, adopted on a setup branch, keeps its trunk guarded."""
    return git.default_branches(str(root))[0]


def default_branch_note(branches: list[str]) -> str:
    """What init and doctor say when git cannot tell the default branch: a push to each branch that could be it asks,
    and how to name it."""
    return (
        "git cannot tell the default branch (no origin/HEAD, and no main or master), so a push to any branch that could "
        f"be it asks: {', '.join(branches)}. To name it, run `git remote set-head origin --auto` once there is a remote, "
        "or `git config init.defaultBranch <branch>`, then `aidd upgrade --yes`"
    )


def takes_edit_rules(harnesses: list[str]) -> bool:
    """Whether any of these coding agents has a file-edit ask rule, so an ask rule can guard the frozen tests of an approved Spec."""
    return any((f := config.HARNESSES[key].ask_rules) and risk.FORMATS[f].edits for key in harnesses)


def frozen_test_rules(root: Path, cfg: config.Config | None) -> tuple[list[str] | None, list[tuple[str, str]]]:
    """The path globs a harness's file-edit tool asks before: the tests of every approved Spec that is not done or revised
    (`workitems.frozen_test_files`), as `risk.harness_edit_paths` writes them, and what a person should hear, as (level, text).
    None in place of the globs while a Spec file does not parse: nothing is known of the Specs, so the rules stay as they are."""
    found = workitems.frozen_test_files(root, cfg)
    notes: list[tuple[str, str]] = []
    if found.unreadable:
        bad = found.unreadable[0]
        more = f" and {len(found.unreadable) - 1} more" if len(found.unreadable) > 1 else ""
        notes.append(
            (
                "warn",
                f"{documents.one_line(bad['path'])}{more} does not parse ({bad['error']}), so aidd cannot tell which Specs are approved and keeps the ask rules for "
                "their frozen tests as they were: fix the file, then run `aidd upgrade --yes`",
            )
        )
    if found.over_cap:
        notes.append(
            (
                "warn",
                f"the approved Specs list more test files than the {len(found.paths)} aidd guards with an ask rule, and {documents.one_line(found.over_cap)} lists "
                "the most, so aidd keeps the ask rules for their frozen tests as they were, and new ones have no ask rule at all: trim that Spec's `tests.files`, then run `aidd upgrade --yes`",
            )
        )
    return (None if found.unreadable or found.over_cap else risk.harness_edit_paths(found.paths)), notes


def aligned(line: str) -> str:
    """A line of `apply_harness_rules` as init and upgrade print it: its past-tense verb padded to the column the others use,
    and `would write` as it is, since it is two words."""
    verb, _, rest = line.partition(" ")
    return line if verb == "would" else f"{verb:<8} {rest}"


def write_ask_rules(root: Path, harnesses: list[str], actions: list[str], *, write: bool = True) -> None:
    """Each detected agent's ask rules, from the risk rules in force (`risk.apply_harness_rules`) and the tests of the
    approved Specs."""
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root)) if regular_files.is_file_or_held(root, config.CONFIG_PATH) else None
    except (config.ConfigError, OSError, ValueError) as exc:
        actions += [f"skipped  {risk.FORMATS[f].path} (config unreadable, ask rules kept: {exc})" for h in harnesses if (f := config.HARNESSES[h].ask_rules)]
        return
    rs = risk.rule_set(cfg)
    branches, known = git.default_branches(str(root))
    patterns, read_paths, labels = risk.harness_patterns(rs, branches), risk.harness_read_paths(rs), risk.pattern_actions(rs, branches)
    edit_paths, notes = frozen_test_rules(root, cfg)
    if takes_edit_rules(harnesses):
        actions += [f"note     {text}" for _level, text in notes]
    if not known and any(config.HARNESSES[key].ask_rules for key in harnesses):
        actions.append(f"hint     {default_branch_note(branches)}")
    for key in harnesses:
        fmt = config.HARNESSES[key].ask_rules
        if not fmt:
            continue
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, read_paths=read_paths, edit_paths=edit_paths, write=write, by_pattern=labels)
        except (ValueError, OSError) as exc:
            actions.append(f"kept     {config.HARNESSES[key].label}'s settings ({exc})")
            continue
        lines = [aligned(d) for d in done]
        actions += [x for x in lines if x not in actions] or [f"kept     {config.HARNESSES[key].label}'s ask rules (up to date)"]
    if "claude-code" in harnesses:
        from aidd.setup import delegation_wiring

        try:
            actions += [f"{d.split(' ', 1)[0]:<8} {d.split(' ', 1)[1]}" for d in delegation_wiring.apply(root, cfg, write=write)]
        except (ValueError, OSError) as exc:
            actions.append(f"kept     Claude Code's settings, with no delegation hooks ({exc})")
