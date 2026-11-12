"""The command line's parser: the help groups that list every command, the grouped help, and the facts the generated
docs restate (`cli_facts`). Each command's arguments and flags are in `grammar.py`, except `help`'s, which sit here beside `cmd_help`."""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys

from aidd import __version__, docsgen
from aidd.cli import arguments, grammar, mcp_protocol
from aidd.kernel import resources, retired_names
from aidd.kernel.text import did_you_mean

DOCS = "Docs: https://github.com/thaithienvanid/aidd"
# The two commands `aidd --help` shows under its description, each with what it tells you.
FIRST_COMMANDS = (
    ("aidd risk --paths app/payments/refund.py", "the route a change to these paths takes"),
    ("aidd init --dry-run", "what setup would write; nothing is written"),
)
EPILOG = f"""The loop: Plan -> Specify (new spec) -> ask: Spec approval -> Implement and Verify, repeated until green (test)
  -> Review -> ask: Merge approval -> Merge -> Roll out -> Learn. Before the first edit, risk --paths gives the route, whether a Spec comes first,
  and the level of the edit; before a risky command, risk --command gives its level: allow, report, or ask.
Exit codes: 0 ok, 1 a check failed, 2 error.
{DOCS}"""

# Every command by what a person is doing, for `aidd help --all` and docs/CLI.md. Every command is in exactly one group,
# or in MAINTAINER. Both print the groups, and the commands in each, in this order.
COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Setup",
        (
            ("init", "adopt aidd in a repository"),
            ("upgrade", "bring the repository's aidd files up to this aidd (a dry run unless --yes)"),
            ("self-update", "update the aidd CLI to the latest release, or to main while there is none (--dry-run)"),
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
            ("delegate", "a standing delegation: whether a delegated ask may go to the delegate (check), its packet, the hook, and stop"),
            ("recall", "search what the team already wrote: records, Specs, ADRs, the glossary, the product brief, the improvement log, and commits"),
            ("new", "create a Spec, Intent, Proposal, exploration, runbook, postmortem, release, or a doc a Spec links"),
            ("approve", "record your own approval of Intents, as your commit with your `Approved-by` and `Approves` lines"),
            ("test", "run the tests (green on head, red on base for new behavior) and write evidence"),
            ("validate", "validate the repository, or the files given"),
            ("explain", f"what one of aidd's words means and why: {arguments.EXPLAIN_TYPES_PHRASE}"),
            ("explore", "one page comparing two or three directions, their trade-offs, and the rounds, for a person to pick one"),
            ("prototype", "the whole product as one clickable page, assembled from docs/design/app/ and checked"),
            ("help", "the everyday commands, every command (--all), or one command's arguments and flags"),
        ),
    ),
    (
        "Agents and harnesses",
        (
            ("eval", "measure your agent setup on your own tasks and compare its runs (tasks, report, compare), or read how the work went (work)"),
            ("mcp", "serve aidd to agents as MCP tools over stdio"),
        ),
    ),
)
HIDDEN_GROUP = COMMAND_GROUPS[-1][0]
# aidd's own development: each runs and docs/CLI.md documents it, and `aidd help --all` never lists it, because no adopter
# needs it. The maintainer suites of `aidd eval` (MAINTAINER_SUITES) are the same.
MAINTAINER: tuple[tuple[str, str], ...] = (("gen-docs", "regenerate the generated blocks in the docs and the skill, after a change to a schema or the help"),)

# When to use each command: the "Which command when" table in docs/CLI.md, and the everyday rows in README.md, which list
# the rows in this order.
EVERYDAY: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "`aidd status`",
        ("status",),
        "to see the open work, and what waits on whom; `--who person` for what waits on you; with an id or a path, what stands behind it",
    ),
    ("`aidd risk --paths`", ("risk",), "before the first edit: the route the planned paths need, whether a Spec comes first, and the level of the edit"),
    ("`aidd new spec`", ("new",), "when the route needs a Spec: start the Spec from its template"),
    (
        "`aidd test`",
        ("test",),
        "once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file",
    ),
)
# The everyday commands the README shows, in its order.
README_FORMS: tuple[str, ...] = ("`aidd status`", "`aidd risk --paths`", "`aidd new spec`", "`aidd test`")
EVERYDAY_COMMANDS: tuple[str, ...] = tuple(dict.fromkeys(n for form, names, _ in EVERYDAY if form in README_FORMS for n in names))
# The README's table, row by row, in its order.
README_ROWS: tuple[tuple[str, str, str], ...] = (
    ('"What\'s open?"', "`aidd status`", "all open work, and the next step of each"),
    ('"yes", to its question', "—", "a Spec approval, a merge, a force-push, or a deploy: the agent does it for you"),
    ('"Which risk rules are in force?"', "`aidd risk --list`", "every risk rule in force, and where it comes from"),
    ('"Which asks could stop?"', "`aidd risk --suggest`", "the ask rules you always said yes to, for actions you can undo"),
    (
        '"Update aidd."',
        "`aidd self-update`, then `aidd upgrade --yes`",
        "aidd and this repository's aidd files, brought up to date after one yes; in Claude Code, also the plugins, as the guide's Update says",
    ),
)
WHEN: dict[str, str] = {
    "init": "once in each repository: write the config, the skill, the ask rules, and the CI workflow",
    "upgrade": "after you install a new aidd: bring the repository's aidd files up to it",
    "self-update": "to update the CLI now; it also checks once a day by itself, after a command you run at a terminal",
    "uninstall": "to remove aidd from a repository",
    "doctor": "after `init` or `upgrade`, or when something looks wrong: check the wiring",
    "standard": "to see the choices the packs leave open, or to adopt one of aidd's opinionated standards (`add`), or a stack of them (`add --stack python-cli`)",
    "records": "to see what was asked and answered, and what the agent did on its own; the agent writes each record (`add`); share them with `pull` and `push`",
    "delegate": "under a standing delegation, before a delegated ask: whether it may go to the delegate (`check`); `stop` turns it off",
    "recall": "before you decide or write: find what the team already wrote about it, then read the file each match names",
    "approve": "when `aidd status` offers it, after a run that could not ask: record your own approval of the Intents it names, as your commit",
    "validate": "to check the whole repository, or the files you name",
    "explain": "when a word or a step puzzles you: what it means and why, from the data that owns it (`aidd explain --list` lists them)",
    "explore": "when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it)",
    "prototype": "to click through the whole product: assemble the product prototype into one page and check it (`aidd new product-prototype` starts it)",
    "help": "to find a command: the everyday ones, every one (`--all`), or one command's arguments and flags (`aidd help <command>`)",
    "eval": "to measure your agent setup on your own tasks (`tasks`) and report or compare its runs (`report`, `compare`), or to read how the work went (`work`), as the retrospective does",
    "mcp": "harnesses: serve aidd to agents as MCP tools; `aidd init` wires it, and writes `~/.aidd/bin/aidd` only from an installed aidd",
    "gen-docs": "after a change to a schema or to the help, regenerate the generated blocks; `aidd help --all` leaves it out",
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
    "TYPE": "what to create (spec, intent, proposal, or a document; `aidd new --list` lists every type)",
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
        import re

        prog, lines = self.prog, [f"{self.prog}: {message}"]
        # Python 3.15's argparse adds its own guess (", maybe you meant 'x'?"); aidd gives its own, so it reads past it.
        if m := re.search(r"(?:argument ([^:]+): )?invalid choice: (?:'([^']*)'|([^\s(]+))(?:, maybe you meant '[^']*'\?)? \(choose from (.*)\)", message):
            # Quoted (`'a', 'b'`) up to 3.11, plain (`a, b`) from a later 3.12 patch on: read both.
            flag, word = m.group(1) or "", m.group(2) if m.group(2) is not None else m.group(3)
            choices = [c.strip().strip("'") for c in m.group(4).split(",") if c.strip()]
            guess = did_you_mean(word, choices, cutoff=0.75)  # a typo, never a guess ("next" is not "context")
            if prog == "aidd":
                lines = [f"aidd: '{word}' is not an aidd command. " + (did_you_mean(word, choices, 0.75, "aidd {}") or "`aidd help --all` lists them.")]
            elif row := next((r for r in retired_names.rows("cli_value") if r["old"] == f"{flag} {word}"), None):
                # A value aidd retired: what to type now, from schemas/retired-names.json, never only the list of choices.
                lines = [f"{prog} {flag}: '{word}' was retired in {row['retired_in']}: type `{row['new']}`. {row['note']}"]
            else:
                named = f"{prog} {flag}" if flag.startswith("-") else prog  # a flag's own name, so a person knows which value was wrong
                lines = [f"{named}: '{word}' is not a choice. " + (guess or f"The choices: {', '.join(choices)}.")]
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
            # A nested command (`aidd standard add`) is named by its last word that names a subcommand.
            sub, here = None, self
            for word in (w for w in self._words if not w.startswith("-")):
                nxt = next((a.choices.get(word) for a in here._actions if isinstance(a, argparse._SubParsersAction)), None)
                if nxt is None:
                    break
                sub = here = nxt
            if sub is not None:
                prog = sub.prog
                bad = message.split(": ", 1)[1].split()
                word = bad[0].split("=", 1)[0]
                if word.startswith("-"):
                    options = [o for a in sub._actions for o in a.option_strings]
                    verbs = [c for a in sub._actions if not a.option_strings for c in (a.choices or ())]  # `--list` for the word `list`
                    guess = did_you_mean(word, options, 0.75) or (f"Did you mean `{prog} {word[2:]}`?" if word[2:] in verbs else "")
                    wider = [o for o in options if word[2:] in o[2:].split("-")]  # `--team` for `--aidd-team`: one option holds the word
                    guess = guess or (f"Did you mean `{wider[0]}`?" if len(wider) == 1 else "")
                    lines = [f"{prog}: unknown option {' '.join(bad)}." + (f" {guess}" if guess else "")]
                else:
                    lines = [f"{prog}: unexpected {' '.join(repr(w) for w in bad)}." + arguments.stray_person_hint(bad[0], self._words)]
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
        lines = [self.format_usage().rstrip(), "", self.description or "", "", "Examples:"]
        pad = max(len(example) for example, _ in FIRST_COMMANDS)
        lines += [f"    {example.ljust(pad)}  {says}" for example, says in FIRST_COMMANDS]
        lines.append("")
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
        maintainer=MAINTAINER,
        everyday=EVERYDAY,
        readme_rows=README_ROWS,
        when=WHEN,
        mcp_supported=mcp_protocol.SUPPORTED,
        mcp_protocol=mcp_protocol.PROTOCOL,
        exit_codes=arguments.EXIT_CODES,
        mcp_tools=tuple(str(tool["name"]) for tool in mcp_tools.TOOLS),
    )


def cmd_help(args) -> int:
    """`aidd help`: what `aidd --help` prints, every command with --all, or one command's help."""
    argv = [*args.topic, "--help"] if args.topic else ["--help", *(["--all"] if args.all else [])]
    try:
        build_parser().parse_args(argv)
    except SystemExit as stop:  # argparse prints the help and stops, or prints the error and stops with 2
        return stop.code if isinstance(stop.code, int) else 0
    return 0


def _add_help(cmd, flag) -> None:
    s = cmd(
        "help",
        "the everyday commands, the same as `aidd --help`; with --all, every command by group; with a command, its arguments and flags",
        cmd_help,
    )
    s.add_argument("topic", nargs="*", metavar="COMMAND", help="a command, such as risk")
    flag(s, "--all", "every command, by group")


def build_parser() -> argparse.ArgumentParser:
    """The CLI."""
    p = _Parser(
        prog="aidd",
        description=resources.load_json("product.json")["short"],
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

    add_command = {**grammar.ADD_COMMAND, "help": _add_help}
    for _group, commands in (*COMMAND_GROUPS, ("", MAINTAINER)):
        for name, _summary in commands:
            add_command[name](cmd, flag)
    return p
