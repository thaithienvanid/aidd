"""The generated tables of what the harnesses' ask rules write and hold: `harnesses:ask-rules` (per harness: the file, what aidd
writes, how it matches, the mode it asks in, and where it does not hold) and `risks:holds` (per action: what asks besides the
skill, and what no harness rule can hold)."""

from __future__ import annotations

from aidd import config, risk
from aidd.docsgen import blocks as docsgen_blocks
from aidd.kernel import text as kernel_text


def leading_word_labels() -> list[str]:
    """The agents whose ask rules match only a command's leading words, so they hold fewer patterns."""
    return [h.label for h in config.ask_rule_harnesses() if risk.FORMATS[str(h.ask_rules)].match == "words"]


def limit_cell(harness: config.Harness) -> str:
    """Where a harness's ask rules do not hold, each with the page that says so and the date aidd read it."""
    parts = [f"{'Unconfirmed: ' if not x.confirmed else ''}{x.what} ([page]({x.source}), read {x.read})" for x in harness.limits]
    return "; ".join(parts) or "nothing documented"


def ask_rules_table() -> str:
    """Each harness `aidd init` writes the ask rules for: the file, what it writes there, how that harness matches a
    command (`risk.FORMATS`), the permission mode its rules hold in, and where they do not hold."""
    rows = []
    for h in config.ask_rule_harnesses():
        f = risk.FORMATS[str(h.ask_rules)]
        files = " or ".join(f"`{p}`" for p in risk.rule_files(str(h.ask_rules)))
        rows.append([h.reader or h.label, files, f.shape, risk.MATCHES[f.match], h.asks_in, limit_cell(h)])
    return docsgen_blocks.markdown_table("Harness | File | What aidd writes | How it matches a command | Asks in | Does not hold under", rows)


# What a branch protection holds of an `ask` action, when the default branch has the protection llms-install.md's
# hand-back asks a person to set: a pull request with a person's review and the test check, and no force push or deletion.
PLATFORM_HOLDS = {
    "git.push": "refused on the default branch, which takes only a PR/MR",
    "git.push.force": "refused on the default branch",
    "git.history.rewrite": "the force push that would publish it is refused on the default branch",
    "git.merge": "the push that would publish it is refused on the default branch, which takes only a PR/MR",
    "git.branch.delete": "deleting the default branch on the platform is refused",
    "pr.merge": "under `team`, the PR/MR review decides",
    "commit_status.post": "the `tests` check counts only from GitHub Actions (`integration_id`)",
}


def hold_gaps(rs, action: str) -> str:
    """What the formats cannot hold of an action: which harnesses hold fewer of its forms than it has, how many in full and how
    many by a narrower rule, and the form no format can hold at all."""
    by: dict[tuple[int, int, int], list[str]] = {}
    for h in config.ask_rule_harnesses():
        c = risk.hold_counts(rs, "main", str(h.ask_rules))[action]
        if c.full < c.forms:
            by.setdefault((c.forms, c.full, c.narrower), []).append(h.reader or h.label)
    parts = [
        f"{kernel_text.series(names, 'and')} hold {full} of its {forms} forms in full" + (f" and {narrower} more by a narrower rule" if narrower else "")
        for (forms, full, narrower), names in by.items()
    ]
    if action in risk.UNHELD:
        parts.append(f"no harness rule holds {risk.UNHELD[action]}, so the skill asks first")
    return "".join(f"; {p}" for p in parts)


def ask_holds_table() -> str:
    """Each built-in `ask` action and what holds it besides the skill (`risks:holds`): the commands a harness's own ask
    rules ask before, and the platform's branch protection."""
    rs = risk.rule_set(None)
    when: dict[str, list[str]] = {}
    for r in rs.rules:
        if r.level == "ask":
            part = f"in `{r.area}`" if r.area else f"to the {r.branch} branch" if r.branch else "always"
            when.setdefault(r.action, [])
            if part not in when[r.action]:
                when[r.action].append(part)
    rows = []
    for action, parts in when.items():
        if action == "git.push":
            cmds = [c for c in risk.harness_patterns(rs, "main") if c.startswith("git push") and "main" in c]
            parts = ["to the default or a shared branch"]
            harness = "asks before a push to the default branch, such as " + kernel_text.series([f"`{c}`" for c in cmds[:2]], "and") + ", and more"
        else:
            written = set(risk.harness_patterns(rs, "main"))
            cmds = [c for c in rs.actions.get(action, {}).get("commands", []) if c in written]
            listed = kernel_text.series([f"`{c}`" for c in cmds[:2]], "and") + (", and more" if len(cmds) > 2 else "")
            local = any(risk.is_local_merge(c) for c in rs.actions.get(action, {}).get("commands", []))
            harness = (
                f"asks before {listed}" if cmds else "nothing: a harness rule cannot see the branch checked out" if local else "nothing: no command marks it"
            )
            # An action that a rule allows on one's own branch asks everywhere else, a branch git cannot tell included.
            if parts == ["always"] and risk.level_of(rs, action, branch="own")[0] != "ask":
                parts = ["on any branch but your own"]
            # A deploy to an environment the config marks as the developer's own reports.
            if parts == ["always"] and any(r.action == action and r.environment_shared is False and r.level != "ask" for r in rs.rules):
                parts = ["to any environment but your own"]
            if rs.actions.get(action, {}).get("api_endpoints"):
                patterns = risk.api_write_patterns()  # the methods first, then the fields
                api = f"{risk.api_harness_names()} ask before any `gh api` write, such as `{patterns[0]}` and `{patterns[3]}`"
                harness = f"{harness}; {api}" if cmds else api
            if action == "intent.approve":  # a trailer's value varies, and a heredoc message hides it from a pattern
                words = kernel_text.series(leading_word_labels(), "and")
                harness += (
                    f"; {words} match leading words only, and Claude Code's pattern misses a message written as a heredoc, "
                    "so the skill asks, and `aidd status` counts an approval only with its `Approved-by` and `Approves` lines"
                )
            if reads := rs.actions.get(action, {}).get("file_reads"):
                names = kernel_text.series([h.label for h in config.ask_rule_harnesses() if risk.FORMATS[str(h.ask_rules)].reads], "and")
                path = reads["paths"][0]
                harness = f"{names} ask before their own file-read tool reads a file that holds secrets, such as `Read({path})`"
        if action not in ("intent.approve", "secret.use"):  # these two say it in their own words above
            harness += hold_gaps(rs, action)
        if parts[0].startswith("in "):
            parts = ["in " + kernel_text.series([x.removeprefix("in ") for x in parts], "and")]
        rows.append([f"`{action}`", parts[0], harness, PLATFORM_HOLDS.get(action, "—")])
    return docsgen_blocks.markdown_table("Action | Asks | A harness's own ask rules | Branch protection", rows)
