"""`aidd doctor`'s checks of the coding agents' ask rules: whether they are on disk and current, what they cannot hold, and
the trust step of each agent. Split from `doctor_checks` to keep each module short."""

from __future__ import annotations

from pathlib import Path

from aidd import config, risk
from aidd.kernel import documents, git, text
from aidd.setup import ask_rules, doctor_team, upgrading


def _config_quiet(root: Path) -> config.Config | None:
    """The config, or None when there is none or it does not load: another check reports why."""
    try:
        return config.load_file(config.CONFIG_PATH, str(root)) if (root / config.CONFIG_PATH).is_file() else None
    except (config.ConfigError, documents.DocumentError, OSError):
        return None


def no_ask_rules_problem(running: str | None, detected: list[str]) -> str:
    """The warning when aidd wrote no ask rules here, so no agent stops at an ask by itself. It names the detected
    agents that take none, where the skill and branch protection are the stops, and the command that writes the rules
    for the agent of this session, else for each agent aidd writes them for, if the person also uses one."""
    keys = text.series([h.key for h in config.ask_rule_harnesses()], "or")
    none_take = [config.HARNESSES[h].label for h in detected if not config.HARNESSES[h].ask_rules]
    if none_take:
        why = f"{text.series(none_take, 'and')} take{'s' if len(none_take) == 1 else ''} no ask rules"
    else:
        why = "no coding agent this repository wires takes them"
    stops = "so the skill and the default branch's protection are the stops here"
    if running and config.HARNESSES[running].ask_rules:
        how = f"`aidd init --harness {running}` writes them for {config.HARNESSES[running].label}, which runs this session"
    elif none_take:
        how = f"if you also use {keys}, `aidd init --harness <key>` writes its ask rules"
    else:
        how = f"`aidd init --harness <key>` writes them for {keys}"
    return f"no ask rules: {why}, {stops}. {how[0].upper() + how[1:]}"


def current_rule_formats(root: Path) -> list[str]:
    """The harness formats whose ask rules are on disk and current: listed in `.aidd/harness-rules.json`, and with
    nothing `apply_harness_rules` would still write. A ledger whose file a person removed counts for nothing."""
    patterns = risk.harness_patterns(risk.rule_set(_config_quiet(root)), ask_rules.push_rule_branches(root))
    out = []
    for fmt in risk.written_formats(root):
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, write=False)
        except (ValueError, OSError):
            continue
        if not any(d.startswith("would") for d in done):
            out.append(fmt)
    return out


def _stale_rules_warning(root: Path, label: str, change: str) -> str:
    """Why an agent's ask rules lag the risk rules, with what the next write changes (`change`, by action), and the command
    that writes them. When git cannot tell the default branch, each new local branch makes them stale again, so the way to
    name it comes first."""
    # In aidd's own source an upgrade runs from its code, as `aidd upgrade` itself says there.
    command = upgrading.SOURCE_UPGRADE if upgrading.aidd_source(root) else "aidd upgrade --yes"
    if git.default_branches(str(root))[1]:
        return f"{label}: its ask rules are not current with the risk rules ({change}): `{command}` writes them"
    return (
        f"{label}: its ask rules are not current with the risk rules ({change}), and git cannot tell the default branch, so each new branch makes them "
        f"stale again. Run `git config init.defaultBranch <branch>`, then `{command}`"
    )


def harness_checks(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """Each detected agent's ask rules, against the risk rules in force."""
    out: list[tuple[str, str]] = []
    cfg = _config_quiet(root)
    rs = risk.rule_set(cfg)
    branches = ask_rules.push_rule_branches(root)
    patterns, read_paths, labels = risk.harness_patterns(rs, branches), risk.harness_read_paths(rs), risk.pattern_actions(rs, branches)
    edit_paths, edit_notes = ask_rules.frozen_test_rules(root, cfg)
    for h in detected:
        label, fmt = config.HARNESSES[h].label, config.HARNESSES[h].ask_rules
        if not fmt:
            continue
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, read_paths=read_paths, edit_paths=edit_paths, write=False, by_pattern=labels)
        except (ValueError, OSError) as exc:
            out.append(("warn", f"{label}: its ask rules cannot be checked ({exc}); fix what it names, then run `aidd doctor` again"))
            continue
        if would := [d.partition(": ")[2] for d in done if d.startswith("would")]:
            out.append(("warn", _stale_rules_warning(root, label, "; ".join(would))))
        else:
            out.append(("ok", f"{label}: its ask rules match the risk rules"))
        out += [("info", f"{label}: {d.removeprefix('kept').strip()}") for d in done if d.startswith("kept")]
        out += _frozen_test_notes(label, fmt, bool(edit_paths))
        out += [("warn", f"{label}: {w}") for w in (risk.opencode_shadow_warnings(root, patterns) if fmt == "opencode" else [])]
        gaps = risk.unwritten(fmt, patterns)
        # A `gh api` write has a pattern for each flag order, which a leading-words format cannot hold: one short line says so.
        api = [g for g in gaps if g.startswith("gh api")]
        # Intent agreement has no prompt there at all, which a person must know plainly: the skill alone asks for it.
        agreement = [g for g in gaps if g in (rs.actions.get("intent.agree") or {}).get("commands", [])]
        out += _agreement_notes(label, rs, bool(agreement))
        if api:
            out.append(
                (
                    "info",
                    f"{label}: `gh api` writes (a merge, a ref move, a release, a branch protection change) get no prompt from its rules, so the skill asks. "
                    "`gh pr merge` and `gh release create` keep their prompt.",
                )
            )
        wider = sorted(set(risk.widened(fmt, patterns).values()))
        if wider:
            out.append(
                (
                    "info",
                    f"{label}: its own rules hold no `*` inside a command, so they ask before every {text.series([f'`{w}`' for w in wider[:3]], 'and')}"
                    f"{f', and {len(wider) - 3} more' if len(wider) > 3 else ''} instead: more often than the risk rules, never less",
                )
            )
        out += hold_lines(config.HARNESSES[h], rs, branches)
    return out + (edit_notes if ask_rules.takes_edit_rules(detected) else []) + harness_closing_notes(root, detected) + doctor_team.team_lines(root, detected)


def _frozen_test_notes(label: str, fmt: str, has_frozen: bool) -> list[tuple[str, str]]:
    """Said for a harness whose ask rules hold no file-edit rule while an approved Spec has frozen tests: only a person's review and a delegated merge's check hold them."""
    if not has_frozen or risk.FORMATS[fmt].edits:
        return []
    return [
        (
            "info",
            f"{label}: no ask rule guards the frozen tests of an approved Spec, since its rules hold none for a file edit; "
            "a person's review of the pull request, and a delegated merge's check, are the controls",
        )
    ]


def _agreement_notes(label: str, rs, no_prompt: bool) -> list[tuple[str, str]]:
    """What a person must know about `intent.agree` in one agent: it has no prompt there (`no_prompt`), or its prompt reads the
    command text, which a heredoc, `-F <file>`, or `-m "$MSG"` hides the trailer from. The skill asks, and `aidd status` reads the trailer."""
    if no_prompt:
        return [("info", f"{label}: no prompt for `intent.agree`, so the skill asks first, and `aidd status` reads the `Agreed-by` trailer")]
    if not (rs.actions.get("intent.agree") or {}).get("commands"):
        return []
    hidden = 'a message written as a heredoc, with `-F <file>`, or as `-m "$MSG"`'
    return [
        (
            "info",
            f"{label}: its prompt for `intent.agree` reads the command text, so {hidden} hides the `Agreed-by` trailer from it: the skill asks first, and `aidd status` reads the trailer",
        )
    ]


def harness_closing_notes(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """The notes after each agent's own lines: the branches the push rules guard when git cannot tell the default branch,
    and the agents aidd writes no ask rules for."""
    out: list[tuple[str, str]] = []
    if any(config.HARNESSES[h].ask_rules for h in detected) and not git.default_branches(str(root))[1]:
        out.append(("info", ask_rules.default_branch_note(ask_rules.push_rule_branches(root))))
    others = [config.HARNESSES[h].label for h in detected if not config.HARNESSES[h].ask_rules]
    if others:
        out.append(("info", f"{', '.join(others)}: no ask-rule format aidd writes, so the skill alone says when to ask"))
    return out


def _forms(hold: risk.Hold) -> str:
    """How a format holds the forms of one action: in full, by a narrower rule, and by none."""
    parts = [f"{hold.full} of {hold.forms} forms in full"]
    parts += [f"{hold.narrower} by a narrower rule"] * bool(hold.narrower)
    parts += [f"{hold.none} by none"] * bool(hold.none and (hold.full or hold.narrower))
    return ", ".join(parts)


def limit_text(limit: config.Limit) -> str:
    """One place an agent's ask rules do not hold, with the page that says so and the date aidd read it."""
    return f"{'unconfirmed: ' if not limit.confirmed else ''}{limit.what} ({limit.source}, read {limit.read})"


def hold_lines(harness: config.Harness, rs, branches: list[str]) -> list[tuple[str, str]]:
    """What an agent's ask rules do not hold, so no `ask` action rests on a prompt that never comes: each action no rule of its
    own holds (the skill alone asks), each one held in part, the form no rule can hold, and the modes where the rules do not
    hold at all. `aidd explain <action>` says what each action does."""
    label, holds = harness.label, risk.hold_counts(rs, branches, str(harness.ask_rules))
    out: list[tuple[str, str]] = []
    if none := risk.held_by_none(holds):
        out.append(
            (
                "info",
                f"{label}: no rule of its own holds {text.series([f'`{a}`' for a in none], 'and')}, so the skill alone asks for them (`aidd explain <action>` says what each does)",
            )
        )
    if part := risk.held_in_part(holds):
        listed = text.series([f"`{a}` ({_forms(x)})" for a, x in part.items()], "and")
        out.append(("info", f"{label}: its rules hold only part of {listed}, so the skill asks for the rest"))
    out += [("info", f"{label}: no rule holds {why}, so the skill asks first") for action, why in risk.UNHELD.items() if action in holds]
    modes = f"; they do not hold under {'; '.join(limit_text(x) for x in harness.limits)}" if harness.limits else ""
    out.append(("info", f"{label}: its ask rules hold in {harness.asks_in}{f', read by {harness.reader} only' if harness.reader else ''}{modes}"))
    return out


def repeats_trust_step(how: str, check: str) -> bool:
    """Whether the way to check the trust starts as the trust step does, so saying it again adds nothing."""
    return check.split(",", 1)[0].strip() == how.split(" and ", 1)[0].strip()


def trust_checks(detected: list[str]) -> list[tuple[str, str]]:
    """For each detected agent with a trust step (`config.Trust`): whether its ask rules wait for the person to trust the
    folder, what else it holds back until then, how to check, and the words to type. The trust lives in the person's own
    files outside the repository, which aidd never reads, so each line says aidd cannot see it."""
    out: list[tuple[str, str]] = []
    for h in detected:
        label, trust = config.HARNESSES[h].label, config.HARNESSES[h].trust
        if trust is None:
            continue
        when = f"{trust.when}, " if trust.when else ""
        check = "" if repeats_trust_step(trust.how, trust.check) else f"; {trust.check}"
        asks = f"{when}its ask rules hold only once you trust this folder" if trust.holds_ask_rules else "its ask rules hold here now"
        line = f"{label}: {asks}. Until you trust the folder, it holds back {trust.holds}. To trust it, {trust.how}. aidd cannot see whether you have{check}"
        out.append(("info", line))
    return out
