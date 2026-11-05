"""The command line's grammar: every command with its arguments and flags, the grouped help, and the facts the
generated docs restate (`cli_facts`)."""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys

from aidd import __version__, config, docsgen, recall, workitems
from aidd.cli import arguments, mcp_protocol

DOCS = "Docs: https://github.com/thaithienvanid/aidd"
EPILOG = f"""The loop: Plan -> Specify (new spec) -> ask: Spec approval -> Implement and Verify, repeated until green (test)
  -> Review -> ask: Merge approval -> Merge -> Roll out -> Learn. Before the first edit, risk --paths gives the route, its lane,
  and the level of the edit; before a risky command, risk --command gives its level: allow, report, or ask.
Exit codes: 0 ok, 1 a check failed, 2 error.
{DOCS}"""

# Every command by what a person is doing, for `aidd help --all` and docs/CLI.md. Every command is in exactly one group.
COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Setup",
        (
            ("init", "adopt aidd in a repository"),
            ("upgrade", "bring the repository's aidd files up to this aidd (a dry run unless --yes)"),
            ("self-update", "update the aidd CLI to the latest release, or to main while there is none (--check)"),
            ("uninstall", "reverse `aidd init` (list what it would remove, or remove it with --yes)"),
            ("doctor", "check the wiring, the config, the risk rules, and each agent's ask rules"),
            ("standard", "list the open choices, aidd's library standards, and its stacks, or add a copy of one (add)"),
        ),
    ),
    (
        "Work",
        (
            ("status", "the open work: each Spec and work item, its status, and its next step"),
            ("risk", "the route for planned paths, or the level of a command or an action: allow, report, or ask"),
            ("records", "the history: each ask a person answered and each action the agent reported; add one, or share them (push, pull)"),
            ("trace", "what stands behind a path or a work item: its Specs, tests, docs, interfaces, route, and last commits"),
            ("recall", "search what the team already wrote: records, Specs, ADRs, the glossary, the product brief, the improvement log, and commits"),
            ("new", "create a Spec, Epic, Initiative, Proposal, exploration, runbook, postmortem, or a doc a Spec links"),
            ("test", "run the tests (green on head, red on base for new behavior) and write evidence"),
            ("validate", "validate the repository, or the files given"),
            ("explore", "one page comparing two or three directions, their trade-offs, and the rounds, for a person to pick one"),
            ("prototype", "the whole product as one clickable page, assembled from docs/design/app/ and checked"),
            ("help", "the everyday commands, every command (--all), or one command's arguments and flags"),
        ),
    ),
    (
        "Maintainers and harnesses",
        (
            ("eval", "run the agent evals, the standards check, or the pack check"),
            ("mcp", "serve aidd to agents as MCP tools over stdio"),
            ("gen-docs", "maintainers: regenerate the generated blocks in the docs and the skill"),
        ),
    ),
)
HIDDEN_GROUP = COMMAND_GROUPS[-1][0]
PLUMBING: tuple[tuple[str, str], ...] = ()

# When to use each command: the "Which command when" table in docs/CLI.md, and the everyday rows in README.md.
EVERYDAY: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("`aidd status`", ("status",), "to see the open work, and what waits on whom; `--mine` for what waits on you"),
    ("`aidd risk --paths`", ("risk",), "before the first edit: the route the planned paths need, its lane, and the level of the edit"),
    ("`aidd new spec`", ("new",), "when the route needs a Spec: start the Spec from its template"),
    (
        "`aidd test`",
        ("test",),
        "once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file",
    ),
)
README_FORMS: tuple[str, ...] = ("`aidd status`", "`aidd risk --paths`", "`aidd new spec`", "`aidd test`")
EVERYDAY_COMMANDS: tuple[str, ...] = tuple(dict.fromkeys(n for form, names, _ in EVERYDAY if form in README_FORMS for n in names))
README_ROWS: tuple[tuple[str, str, str], ...] = (
    ('"What\'s open?"', "`aidd status`", "all open work, and the next step of each"),
    ('"yes", to its question', "—", "a Spec approval, a merge, a force-push, or a deploy: the agent does it for you"),
    ('"Which risk rules are in force?"', "`aidd risk --list`", "every risk rule in force, and where it comes from"),
    ('"Which asks could stop?"', "`aidd risk --suggest`", "the ask rules you always said yes to, for actions you can undo"),
    ('"Update aidd."', "`aidd self-update`, then `aidd upgrade --yes`", "aidd and this repository's aidd files, brought up to date after one yes"),
)
WHEN: dict[str, str] = {
    "init": "once in each repository: write the config, the skill, the ask rules, and the CI workflow",
    "upgrade": "after you install a new aidd: bring the repository's aidd files up to it",
    "self-update": "to update the CLI now; it also checks once a day by itself, after a command you run at a terminal",
    "uninstall": "to remove aidd from a repository",
    "doctor": "after `init` or `upgrade`, or when something looks wrong: check the wiring",
    "standard": "to see the choices the packs leave open, or to adopt one of aidd's opinionated standards (`add`), or a stack of them (`add --stack python-cli`)",
    "records": "to see what was asked and answered, and what the agent did on its own; the agent writes each record (`add`); share them with `pull` and `push`",
    "recall": "before you decide or write: find what the team already wrote about it, then read the file each match names",
    "trace": "before you change code, or to see why it is as it is: the Specs, tests, docs, and commits behind a path or a work item, and what else is in flight there",
    "validate": "to check the whole repository, or the files you name",
    "explore": "when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it)",
    "prototype": "to click through the whole product: assemble the product prototype into one page and check it (`aidd new product-prototype` starts it)",
    "help": "to find a command: the everyday ones, every one (`--all`), or one command's arguments and flags (`aidd help <command>`)",
    "eval": "maintainers: run the agent evals, the standards check, or the pack check",
    "gen-docs": "maintainers: after a change to a schema or to the help, regenerate the generated blocks",
    "mcp": "harnesses: serve aidd to agents as MCP tools; `aidd init` wires it",
}


class _Help(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Show a default only when it says something and the help text does not already explain it."""

    def _get_help_string(self, action):
        text = action.help or ""
        if "default" in text or action.default in (None, "", False, [], argparse.SUPPRESS):
            return text
        return super()._get_help_string(action)


# One example for a command run without what it needs, shown in place of argparse's usage dump.
EXAMPLES: dict[str, str] = {
    "aidd new": 'aidd new spec "Add a percentage discount"',
    "aidd explore": "aidd explore specs/SPEC-12/explore/split-bill",
}
# What a missing positional argument is, in words, for the error (argparse names it by its dest).
MISSING: dict[str, str] = {
    "type": "what to create (spec, epic, initiative, proposal, or a document)",
    "folder": "the folder",
}


class _Parser(argparse.ArgumentParser):
    """The top-level parser: its help lists the everyday commands (EVERYDAY_COMMANDS), each with its one-line help, and
    with `--all` every command by COMMAND_GROUPS, so a person reads what they need first; every command works either way.
    An error is one or two lines that say what to type (clig.dev): a close match for a mistyped word, an example for a
    missing argument."""

    show_all = False
    _words: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        # No aidd command takes an abbreviated long option, so `--conf` is never `--confirmed`. argparse makes each
        # command's parser of this class, so the rule binds every command, not only the top level.
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message: str):
        import difflib
        import re

        prog, lines = self.prog, [f"{self.prog}: {message}"]
        # Python 3.15's argparse adds its own guess (", maybe you meant 'x'?"); aidd gives its own, so it reads past it.
        if m := re.search(r"invalid choice: '([^']*)'(?:, maybe you meant '[^']*'\?)? \(choose from (.*)\)", message):
            # Quoted (`'a', 'b'`) up to 3.11, plain (`a, b`) from a later 3.12 patch on: read both.
            choices = [c.strip().strip("'") for c in m.group(2).split(",") if c.strip()]
            close = difflib.get_close_matches(m.group(1), choices, n=1, cutoff=0.75)  # a typo, never a guess ("next" is not "context")
            if prog == "aidd":
                lines = [f"aidd: '{m.group(1)}' is not an aidd command." + (f" Did you mean `aidd {close[0]}`?" if close else " `aidd help --all` lists them.")]
            else:
                lines = [
                    f"{prog}: '{m.group(1)}' is not one of its choices." + (f" Did you mean `{close[0]}`?" if close else f" The choices: {', '.join(choices)}.")
                ]
        elif message.startswith("the following arguments are required: "):
            if prog == "aidd" and "COMMAND" in message:
                self.print_help(sys.stderr)
                self.exit(2)
            missing = ", ".join(MISSING.get(n.strip(), n.strip()) for n in message.split(": ", 1)[1].split(","))
            lines = [f"{prog}: missing {missing}."]
            if example := EXAMPLES.get(prog):
                lines.append(f"For example: {example}")
        elif message.startswith("unrecognized arguments: ") and prog == "aidd" and self._words:
            # The top-level parser reports a subcommand's unknown option: name that command, and its closest option.
            # A nested command (`aidd autopilot note`) is named by its last word that names a subcommand.
            sub, here = None, self
            for word in (w for w in self._words if not w.startswith("-")):
                nxt = next((a.choices.get(word) for a in here._actions if isinstance(a, argparse._SubParsersAction)), None)
                if nxt is None:
                    break
                sub = here = nxt
            if sub is not None:
                prog = sub.prog
                options = [o for a in sub._actions for o in a.option_strings]
                bad = message.split(": ", 1)[1].split()
                close = difflib.get_close_matches(bad[0].split("=", 1)[0], options, n=1, cutoff=0.75)
                lines = [f"{prog}: unknown option {' '.join(bad)}." + (f" Did you mean `{close[0]}`?" if close else "")]
        if "--help" not in lines[0] and "help --all" not in lines[0]:
            lines.append(f"`{prog} --help` shows every option.")
        self.exit(2, "\n".join(lines) + "\n")

    def parse_known_args(self, args=None, namespace=None):
        if self.prog == "aidd":
            # `--help` prints as soon as argparse reads it, so look for `--all` among the options before the command first.
            words = list(sys.argv[1:] if args is None else args)
            self._words = words
            lead = words[: next((i for i, w in enumerate(words) if not w.startswith("-")), len(words))]
            # An unknown option there (`--al`) is an error even with `--help`, never a help that hides the commands.
            unknown = [w for w in lead if w != "--" and w.split("=", 1)[0] not in self._option_string_actions]
            if unknown:
                self.error("unrecognized arguments: " + " ".join(unknown))
            self.show_all = "--all" in lead
        known, rest = super().parse_known_args(args, namespace)
        if self.prog == "aidd":
            known.words = self._words  # the command's words as given, for a handler whose ask rule matches them (`records push`)
        return known, rest

    def format_help(self) -> str:
        action = next((a for a in self._actions if isinstance(a, argparse._SubParsersAction)), None)
        if action is None or self.prog != "aidd":
            return super().format_help()
        import textwrap

        purpose = {n: text for _, rows in COMMAND_GROUPS for n, text in rows}
        if self.show_all:
            shown = COMMAND_GROUPS
        else:
            shown = (("Everyday commands", tuple((n, purpose[n]) for n in EVERYDAY_COMMANDS)),)
        width = max(len(n) for _, rows in shown for n, _ in rows) + 2
        wrap = max(shutil.get_terminal_size((100, 24)).columns, 60) - width - 4
        lines = [self.format_usage().rstrip(), "", self.description or "", ""]
        for title, rows in shown:
            lines.append(f"{title}:")
            for name, text in rows:
                chunks = textwrap.wrap(text, wrap) or [""]
                lines.append(f"  {name.ljust(width)}{chunks[0]}")
                lines += [f"  {' ' * width}{c}" for c in chunks[1:]]
            lines.append("")
        if not self.show_all:
            more = ["More commands, such as `aidd init`: `aidd help --all`.", "One command in full: `aidd help <command>`."]
            return "\n".join([*lines, *more, DOCS]) + "\n"
        lines += [
            "options:",
            "  -h, --help  show this help message and exit",
            "  --all       with --help: list every command, by group",
            "  --version   show the version and exit",
            "",
            self.epilog or "",
        ]
        return "\n".join(lines) + "\n"


class Handler:
    """A command's handler, named "group:cmd_name" in aidd.cli.commands and imported only when the command runs: building
    the parser loads no command's code, and running a command loads its own group alone."""

    def __init__(self, where: str) -> None:
        self.group, _, self.__name__ = where.partition(":")

    def __call__(self, args: argparse.Namespace) -> int:
        return getattr(importlib.import_module(f"aidd.cli.commands.{self.group}"), self.__name__)(args)


def cli_facts() -> docsgen.CliFacts:
    """The command line's facts the generated docs restate: the parser `aidd` runs, its help groups, and the MCP
    revisions `aidd mcp` speaks and the tools it lists."""
    from aidd.cli import mcp_tools  # only gen-docs reads the tools, so building the parser never loads them

    return docsgen.CliFacts(
        parser=build_parser(),
        command_groups=COMMAND_GROUPS,
        hidden_group=HIDDEN_GROUP,
        plumbing=PLUMBING,
        everyday=EVERYDAY,
        readme_rows=README_ROWS,
        when=WHEN,
        mcp_supported=mcp_protocol.SUPPORTED,
        mcp_protocol=mcp_protocol.PROTOCOL,
        exit_codes=arguments.EXIT_CODES,
        mcp_tools=tuple(str(tool["name"]) for tool in mcp_tools.TOOLS),
    )


def _setup(cmd, flag) -> None:
    s = cmd("init", "adopt aidd in a repository", "setup:cmd_init")
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--dry-run", "print what init finds (stacks, tests, sensitive areas, CI) and the config it proposes; write nothing")
    s.add_argument("--profile", choices=list(config.PROFILES), help="solo (one person decides) or team (default: the config init keeps, else asked, else solo)")
    s.add_argument("--ci", choices=["github", "gitlab", "none"], default="github", help="CI templates to install")
    s.add_argument("--ref", metavar="SHA_OR_TAG", help="pin the CI files' aidd action to this commit SHA or release tag")
    s.add_argument("--approvers", nargs="+", metavar="WHO", help="owners.approvers: the people agents ask, such as @you")
    s.add_argument(
        "--specialist", action="append", metavar="POOL=WHO", help="a specialist pool (owners.specialists), such as security=@org/security (repeatable)"
    )
    s.add_argument("--test", metavar="COMMAND", help='the repository suite, such as "npm test"')
    flag(s, "--team", "also install the delivery team (optional): an agent for each role, with the team commands and domain packs")
    s.add_argument(
        "--harness",
        action="append",
        choices=[*config.HARNESSES, "none"],
        metavar="AGENT",
        help="the coding agents to wire instead of detecting them: " + ", ".join(config.HARNESSES) + ", or none (repeatable)",
    )
    flag(s, "--claude-plugins", "install the aidd plugins for this user through the `claude` CLI instead of repository files for Claude Code")
    flag(s, "--devcontainer", "also write .devcontainer/: a dev container that denies outbound traffic except to an allow-list (a starting point)")
    s.add_argument(
        "--compliance-target",
        action="append",
        choices=["soc2", "iso27001", "gdpr", "hipaa", "pci-dss", "fedramp", "cra", "other"],
        help="a framework or law the product answers to, for `project.compliance.targets` (repeatable)",
    )
    flag(s, "--security-ci", "also write the security CI when compliance is off")
    s.add_argument("--link", action="append", metavar="DIR", help="extra agent skill directory to link, besides .claude/skills (repeatable)")
    flag(s, "--no-skill", "do not vendor the skill (agents load the plugin instead)")
    flag(s, "--force", "overwrite existing files and upgrade the vendored skill")

    s = cmd(
        "upgrade",
        "bring a repository's aidd files up to this aidd: the skill, the team files, each agent's ask rules, the CI pins, and aidd_version; "
        "a dry run unless --yes",
        "setup:cmd_upgrade",
    )
    s.add_argument("path", nargs="?", default=".", help="repository root")
    s.add_argument("--ref", metavar="SHA_OR_TAG", help="pin the CI files to this aidd commit or release; default: this aidd's")
    flag(s, "--yes", "make the changes")

    s = cmd(
        "self-update",
        "update the aidd CLI to the latest release of thaithienvanid/aidd, the way it was installed (uv, pipx, or the one-line installer), "
        "from the release's wheel once it matches the release's SHA256SUMS; AIDD_NO_UPDATE_CHECK=1 turns the daily check off",
        "setup:cmd_self_update",
    )
    flag(s, "--check", "say what it would update to; change nothing")
    flag(s, "--main", "update to the tip of main instead: unreleased code, with no release to verify it against")

    s = cmd("uninstall", "reverse `aidd init`: list what it would remove, or remove it with --yes", "setup:cmd_uninstall")
    s.add_argument("path", nargs="?", default=".", help="the repository (default: the current directory)")
    flag(s, "--yes", "remove the files; without it, only list them")
    s.add_argument("--link", action="append", metavar="DIR", help="extra skill link directories given to `aidd init --link` (repeatable)")

    s = cmd("doctor", "check that a repository is wired correctly", "setup:cmd_doctor")
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--json", "print each check as JSON (schemas/doctor.schema.json)")

    s = cmd(
        "standard",
        "the choices the domain packs and practice skills leave open, each with aidd's default, and aidd's library of opinionated standards "
        "that fill them, and its stacks; `add` copies standards or a stack into docs/standards/ with their `standards` entries and their `tests`",
        "setup:cmd_standard",
    )
    s.add_argument(
        "standard_command",
        nargs="?",
        choices=["list", "add"],
        metavar="list|add",
        help="list (the default) the choices and the library, or add a copy of library standards or a stack",
    )
    s.add_argument("ids", nargs="*", metavar="ID", help="add: library ids, such as python/ruff-lint-format")
    s.add_argument("--stack", metavar="NAME", help="add: a stack, such as python-cli")
    flag(s, "--stacks", "list the stacks instead: opinionated standards that go together")
    flag(s, "--json", "print JSON (schemas/standard-list.schema.json, or with --stacks schemas/stack-list.schema.json)")


def _work(cmd, flag) -> None:
    s = cmd("status", "the open work: each Spec, Epic, Initiative, and proposal with its status and its next step, and who takes it", "work:cmd_status")
    s.add_argument("id", nargs="?", help="one work item, such as SPEC-3, including a finished one")
    flag(s, "--mine", "only what waits on a person")
    flag(s, "--all-branches", "the open work in every worktree and in every local and fetched branch, each item with the places that hold it")
    s.add_argument(
        "--delivery-team",
        metavar="NAME",
        help="only one delivery team's work (`delivery_teams` in the config): its Epics, their Specs, and the Specs whose Task scope touches its areas",
    )
    flag(s, "--json", "print it as JSON (schemas/status.schema.json)")
    flag(s, "--html", "write it as one page to .aidd/views/status-work.html: a board by status, the tree, what waits on a person, and the words to type")

    s = cmd(
        "risk",
        "advice before an action: the route for planned paths (--paths), the level of a shell command (--command) or an action (--action), "
        "or every risk rule in force (--list); a level is allow, report, or ask",
        "work:cmd_risk",
    )
    s.add_argument("--paths", nargs="+", metavar="PATH", help="planned paths or globs: the route, the lane, the edit's level, and the first step")
    s.add_argument("--command", dest="command_line", metavar="LINE", help='a shell command line, such as "git push --force origin main"')
    s.add_argument("--action", metavar="ID", help="an action, such as pr.merge (`aidd risk --list` lists them)")
    flag(s, "--list", "every rule in force, the areas, and the actions, with where each rule comes from")
    flag(s, "--suggest", "the ask rules that got a yes every time, at least 10 times in the records, for actions a person can undo: rules to consider lowering")
    s.add_argument("--change-type", default="feat", choices=arguments.CHANGE_TYPES, help="with --paths: the change type")
    flag(s, "--irreversible", "with --paths: a revert would not restore the prior state (makes the route major)")
    s.add_argument("--area", help="with --action: the area it touches, such as payments")
    s.add_argument("--branch", choices=["own", "default", "shared"], help="with --command or --action: the branch it reaches (default: read from git)")
    s.add_argument("--role", help="with --command or --action: the aidd-team role that acts")
    flag(s, "--json", "print it as JSON (schemas/risk.schema.json)")

    s = cmd(
        "records",
        "the history in .git/aidd/records/, newest first: each ask a person answered (decision) and each action the agent reported (report); "
        "`add` writes one, checked against schemas/records.json. A record is the agent's account, never a yes and never evidence",
        "work:cmd_records",
    )
    s.add_argument(
        "records_command",
        nargs="?",
        choices=["list", "add", "push", "pull"],
        metavar="list|add|push|pull",
        help="list (the default) the records, add one, or share them through the remote's refs/aidd/records: pull adds the ones you lack, push sends yours",
    )
    s.add_argument("remote", nargs="?", help="push and pull: the remote, one this clone names (default origin); they take no other option")
    s.add_argument("--type", dest="record_type", metavar="TYPE", help="list: only this type; add: the record's type, decision or report")
    s.add_argument("--subject", metavar="ID", help="list: only this work item's; add: the work item it belongs to, such as SPEC-4")
    s.add_argument("--by", metavar="HARNESS/MODEL", help="add: the agent that writes it, as a commit's Assisted-by, such as claude-code/claude-opus-5-5")
    s.add_argument("--data", metavar="JSON", help="add: the record's data as a JSON object, or - to read it from stdin")
    flag(s, "--json", "list: print the records as JSON (schemas/records.schema.json, $defs/list)")

    s = cmd(
        "trace",
        "what stands behind a repository path or a Spec, Epic, or Initiative: the Specs whose Task scope covers it, the open Specs in flight there, "
        "their tests, docs, and interfaces, the route, and the last commits, read from git and the work items' files",
        "work:cmd_trace",
    )
    s.add_argument("target", metavar="PATH|ID", help="a file or folder in the repository, or a work item id such as SPEC-3")
    s.add_argument("--commits", type=int, default=workitems.DEFAULT_COMMITS, metavar="N", help=f"the most commits to read, from 1 to {workitems.MAX_COMMITS}")
    flag(s, "--json", "print it as JSON (schemas/trace.schema.json)")

    s = cmd(
        "recall",
        "search what the team already wrote: the records, the Specs and their documents, the ADRs, the glossary, the product brief, the improvement log, "
        "and the commit subjects. Each match has its file and line, a record's id, or a commit's short sha, newest first where it has a date. "
        "It reads through the index in .git/aidd/, a cache of the files: never a source of truth, never evidence, never a yes",
        "work:cmd_recall",
    )
    s.add_argument("recall_words", nargs="+", metavar="WORD", help="the words to find, all in one line, such as: retry budget")
    s.add_argument("--limit", type=int, default=recall.DEFAULT_MATCHES, metavar="N", help=f"the most matches to show, from 1 to {recall.MAX_MATCHES}")
    flag(s, "--json", "print it as JSON (schemas/recall.schema.json)")

    s = cmd(
        "new",
        "create a Spec, Epic, Initiative, Proposal, runbook, postmortem, or feedback log from the template; or a document a Spec links, "
        "written from its template and added to the Spec's `docs`; or the repository's one design-system, product-prototype, architecture "
        "overview, data-map, vendors register, glossary, or vulnerability-policy; or a proposal's contract; or an exploration",
        "work:cmd_new",
    )
    s.add_argument(
        "type",
        choices=[
            "spec",
            "epic",
            "initiative",
            "proposal",
            "runbook",
            "postmortem",
            *(k for k in workitems.DOC_TYPES_NEW if k != "runbook"),
            "product-prototype",
        ],
    )
    s.add_argument(
        "id",
        nargs="?",
        help='such as SPEC-42, or for a Spec, Epic, Initiative, or Proposal its title (`aidd new spec "Add a discount"`), which takes the next '
        "free id; for a linked document, its topic, such as rate-limits; a contract's proposal id; an exploration's folder; none for a repository document",
    )
    s.add_argument(
        "--title",
        help="a Spec's, Epic's, Initiative's, Proposal's, runbook's, or postmortem's title (or give it in place of the id); an exploration's question; a document's default is its topic",
    )
    s.add_argument(
        "--route",
        choices=["normal", "major", "emergency"],
        help="a Spec is normal (the default), major, or an emergency backfill; with --paths, the route the paths need wins when it is higher",
    )
    s.add_argument("--change-type", default="feat", choices=arguments.CHANGE_TYPES, help="the change type")
    s.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        help="spec: the paths or globs the change will touch; computes the route (as `aidd risk --paths` does) and writes them as the Task's scope",
    )
    s.add_argument("--dimension", action="append", choices=arguments.DIMENSIONS, help="spec: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "spec: a revert would not restore the prior state (forces major)")
    flag(s, "--force", "product-prototype: refused; a linked document: write it again")
    flag(
        s,
        "--full",
        "spec: every section (adds Problem, Goals, Non-goals, and Learn); by default a normal Spec is the short one (Intent, "
        "Context, Acceptance, Design, Policy conflicts, Rollback), and a major Spec is full; alternatives and the pre-mortem "
        "live in the tech spec it links",
    )
    s.add_argument("--owner-team", default="", help="default: owners.default_owner_team from the config")
    s.add_argument("--parent", default="", help="the parent's id: an Epic for a Spec, an Initiative for an Epic")
    s.add_argument("--audience", default="client", choices=["client", "internal"], help="a proposal's audience: a client, or the company's own decision makers")
    s.add_argument("--addressee", default="", help='who receives a proposal and decides, such as "Acme Corp" or "the executive committee"')
    s.add_argument(
        "--spec",
        default="",
        help="the Spec id: a linked document's Spec (required), a runbook's (linked as a living doc), or a postmortem's (the Spec that carries the fix)",
    )
    s.add_argument(
        "--area",
        default="",
        help="a linked document's folder under the specs folder, such as checkout, shared by several Specs (default: the Spec id); for --prototype, a second flow's folder in the Spec's design/",
    )
    flag(s, "--no-link", "a linked document: write it and print its `docs` entry, leaving the Spec to its writer to link it")
    flag(
        s,
        "--prototype",
        "ui: write the HTML prototype instead of the design spec, as prototype.html in the design folder: every screen of the flow, "
        "its states, themes, and frames, deep links, and notes, shown by `aidd prototype`",
    )
    s.add_argument("--owner", default="", help="exploration: the role that owns it (default product-designer; architect for an architecture question)")
    s.add_argument(
        "--timebox",
        default="45 minutes",
        help="exploration: minutes or a cost, or a spike's end date (YYYY-MM-DD); when it runs out, the owner stops and presents",
    )

    s = cmd("test", "run the tests (green on head, red on base) and write evidence", "work:cmd_test")
    s.add_argument("--base", help="the base branch to compare with (default: the default branch)")
    s.add_argument("--spec", help="the Spec whose tests to run, by path or id (default: the one Spec in the diff)")
    s.add_argument("--out", default=config.EVIDENCE_DIR, help="where evidence.json and logs go")
    flag(s, "--no-red", "skip red runs (the final run on the head should include them)")
    flag(s, "--red-in-place", "CI only: run red in this checkout, keeping installed dependencies")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=arguments.PASS_ENV_HELP)
    flag(s, "--changed", "run only the commands the working tree's changes select, green only; the evidence is marked partial")
    flag(s, "--watch", "run --changed now and again whenever a file changes, until Ctrl-C (exit 0)")

    s = cmd("validate", "validate the repository, or the files given", "work:cmd_validate")
    s.add_argument("paths", nargs="*", metavar="PATH", help="files or folders (default: the whole repository)")
    flag(s, "--json", "print the errors and warnings as JSON (schemas/validate.schema.json)")

    s = cmd(
        "explore",
        "render an exploration's one comparison page: two or three divergent directions side by side, the trade-offs under each, and "
        "each round's screenshots; the owning role writes the pick and its reason in the Spec, DESIGN.md, or an ADR",
        "work:cmd_explore",
    )
    s.add_argument("folder", help="the exploration's folder, such as specs/SPEC-12/explore/split-bill")
    s.add_argument("--out", metavar="PATH", help="where to write the page (default: .aidd/views/explore-<folder>.html)")

    s = cmd(
        "prototype",
        "assemble the whole-product prototype from docs/design/app/ (sitemap.json, shell.html, and flows/) into aidd's prototype viewer, "
        ".aidd/views/prototype.html, and check it: every link and navigation item opens a screen, no flow draws its own navigation, "
        "and every flow is reachable",
        "work:cmd_prototype",
    )
    s.add_argument(
        "file",
        nargs="?",
        help="a Spec's or a flow's prototype file, such as specs/SPEC-12/design/prototype.html, to open in the current viewer; "
        "the file is never changed, so a frozen prototype gets every fix to the viewer",
    )
    flag(s, "--check", "only check the sources: report every problem, with its line in a prototype file, exit 1 on any, and write nothing")
    flag(s, "--example", "write the prototype tool's showcase, a complete design to learn the format from, to .aidd/views/")
    flag(s, "--open", "open the written page in your browser, after printing its address")
    flag(s, "--serve", "serve the page on 127.0.0.1 until Ctrl-C, built again on each reload, with the files of the design's folder; off under AIDD_OFFLINE=1")
    flag(s, "--lan", "with --serve: listen on the local network too, so a phone on it opens the page")
    s.add_argument("--port", type=int, default=8765, help="with --serve: the port (default: 8765)")
    flag(s, "--components", "print the design's component contract as JSON: each data-component, its variants, screens, and test ids")
    flag(s, "--screens", "print the design's screens as JSON: each one's id, title, parent, first state, and states in order")
    s.add_argument("--new-design", metavar="FILE", help="write a design file from the starting design, such as an exploration's sketch (directions/a.html)")
    s.add_argument("--title", default="A direction", help="with --new-design: what the design shows")
    s.add_argument(
        "--stories", metavar="INDEX", help="check Storybook's index.json (from `storybook build`) against the component contract: exit 1 on a missing story"
    )

    s = cmd(
        "help",
        "the everyday commands, the same as `aidd --help`; with --all, every command by group; with a command, its arguments and flags",
        cmd_help,
    )
    s.add_argument("topic", nargs="*", metavar="COMMAND", help="a command, such as risk")
    flag(s, "--all", "every command, by group")


def _maintain(cmd, flag) -> None:
    s = cmd(
        "eval",
        "run an agent routing eval, the role evals, the standards check, the pack and practice template check, or your own agent tasks; report recorded runs",
        "maintain:cmd_eval",
    )
    s.add_argument("suite", choices=["routing", "roles", "standards", "packs", "tasks", "report", "transcript"])
    s.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="report: JSON-lines files written with --record, printed as one markdown table; transcript: one recorded event stream, read as JSON",
    )
    s.add_argument("--root", help="routing, roles: the aidd source checkout (default: this installation's source, if any); tasks: your repository (default: .)")
    s.add_argument("--scenarios", help="directory of scenario .yaml files")
    s.add_argument("--agent-command", help='agent command that reads a prompt on stdin, such as "claude -p"')
    flag(s, "--no-embed", "routing: ask the agent to load the skill by name instead of embedding its text")
    s.add_argument(
        "--min-accuracy", type=float, default=0.9, help="fail below this mean pass@1: the share of correct routes, passed role scenarios, or passed tasks"
    )
    s.add_argument("--repeat", type=int, default=1, metavar="K", help="routing, roles, tasks: run each scenario K times; report pass@1 and pass^K")
    flag(
        s,
        "--without-aidd",
        "routing, roles: also run every scenario without the aidd material (the skill reference, the role playbook) and report the lift; never gates",
    )
    s.add_argument("--record", metavar="PATH", help="routing, roles, tasks: append this run to a JSON-lines file (read it with `aidd eval report`)")
    s.add_argument("--model-label", metavar="TEXT", help="the model name to record with the run, as you name it (aidd never infers it)")
    flag(
        s,
        "--online",
        "standards: fetch each evidence URL again and report whether its quote is still there (ok, moved, missing, unreachable); never edits the registry",
    )
    flag(s, "--strict", "standards --online: exit 1 when an entry is moved or missing (never for unreachable)")
    s.add_argument("--due", type=int, metavar="DAYS", help="standards: list each entry that comes due for review within DAYS days, soonest first")
    flag(
        s,
        "--json",
        "standards --online: print the report as JSON (schemas/knowledge.schema.json); "
        "packs: print each pack's and practice skill's estimated size, and the problems, as JSON",
    )
    s.add_argument("--timeout", type=float, default=15.0, metavar="SECONDS", help="standards --online: each request's timeout")
    s.add_argument("--max-seconds", type=float, default=600.0, metavar="SECONDS", help="standards --online: the whole run's time cap")
    s.add_argument("--max-bytes", type=int, default=3_000_000, metavar="N", help="standards --online: the most bytes read from one page")
    s.add_argument("--concurrency", type=int, default=2, choices=[1, 2], help="standards --online: requests in flight (one per host)")
    cmd(
        "mcp",
        "serve aidd to agents as MCP tools over stdio: the risk level of an action, the open work, validation, records, and a search of what the team wrote",
        "maintain:cmd_mcp",
    )
    s = cmd("gen-docs", "maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills", "maintain:cmd_gen_docs")
    flag(s, "--check", "fail when any generated block is stale")


def cmd_help(args) -> int:
    """`aidd help`: what `aidd --help` prints, every command with --all, or one command's help."""
    argv = [*args.topic, "--help"] if args.topic else ["--help", *(["--all"] if args.all else [])]
    try:
        build_parser().parse_args(argv)
    except SystemExit as stop:  # argparse prints the help and stops, or prints the error and stops with 2
        return stop.code if isinstance(stop.code, int) else 0
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The CLI."""
    p = _Parser(
        prog="aidd",
        description="aidd: the AI-Driven Development toolkit. Agents do the work, and you decide the risky steps.",
        epilog=EPILOG,
        formatter_class=_Help,
    )
    p.add_argument("--version", action="version", version=f"aidd {__version__}")
    p.add_argument("--all", action="store_true", help="with --help: list every command, by group")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def cmd(name: str, help_text: str, func) -> argparse.ArgumentParser:
        s = sub.add_parser(name, description=help_text, formatter_class=_Help)
        s.set_defaults(func=Handler(func) if isinstance(func, str) else func)
        return s

    def flag(parser, name: str, help_text: str) -> None:
        parser.add_argument(name, action="store_true", help=help_text)

    for register in (_setup, _work, _maintain):
        register(cmd, flag)
    return p
