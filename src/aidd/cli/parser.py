"""The command line's grammar: the top-level parser and its grouped help, the groups' registrars
(aidd.cli.grammar), and the facts the generated docs restate.
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys

from aidd import __version__, docsgen
from aidd.cli import arguments, grammar, mcp_protocol
from aidd.kernel import extensions

DOCS = "Docs: https://github.com/thaithienvanid/aidd"
# The end of `aidd help --all`; `aidd --help` ends with DOCS alone.
EPILOG = f"""The loop: Plan -> Specify (new spec) -> Spec approval (approve spec) -> Implement and Verify, repeated
  until green (test) -> Review (gate) -> Merge approval (land) -> Publish (publish) -> Roll out (observe) -> Learn.
  Before the first edit, gate --paths gives the route and its lane. The fast lane skips Specify and Spec approval, and needs
  no Change Request block: describe prints one to raise the route or declare a risk. list shows all open work and who holds each step.
Exit codes: 0 pass or ok, 1 fail, 3 pending (a local gate; `gate github` exits 0 and `gate gitlab` exits 1 on pending unless --pending-ok), 2 error.
{DOCS}"""

# Every command by what a person is doing, for `aidd help --all` and docs/CLI.md. Every command is in exactly one group
# (docsgen._subcommands reads them), and the last group holds the maintainer and harness commands. `aidd --help` lists
# only EVERYDAY_COMMANDS.
COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Setup",
        (
            ("init", "adopt aidd in a repository"),
            ("upgrade", "bring the repository's aidd files up to this aidd (a dry run unless --yes)"),
            ("self-update", "update the aidd CLI to the latest release, or to main while there is none (--check)"),
            ("uninstall", "reverse `aidd init` (list what it would remove, or remove it with --yes)"),
            ("doctor", "check that the repository is wired correctly"),
            ("extensions", "the plugins from aidd's registry that fit this repository, and how a person installs each (suggest)"),
            ("standard", "list the open choices and aidd's library standards, or add a copy of one (add)"),
            ("stack", "list the stacks, or add one: its standards and its `project.stack` entries (add)"),
        ),
    ),
    (
        "Understand",
        (
            ("list", "all open work and who holds each step (--branch, --mine, --waiting-on-me, --agent, --blocked)"),
            ("log", "one Spec's history from git"),
            ("owners", "who decides and who does the work"),
            ("config", "the settings this repository sets, and the ones you may want to set (--all: every setting)"),
            ("help", "the everyday commands, every command (--all), or one command's arguments and flags"),
            ("worktrees", "each worktree's work item and state (merged, stale, missing); clean removes the merged ones"),
            ("metrics", "summarize gate events: loop speed, DORA, autonomy, guard denials"),
            ("digest", "a status rollup since a date or tag: the team view, or the client's RAG view (--client)"),
        ),
    ),
    (
        "Author",
        (
            ("new", "create a Spec, Epic, Initiative, Proposal, runbook, postmortem, or a doc a Spec links"),
            ("import", "write a short Spec from Spec Kit, OpenSpec, Kiro, or BMAD files, or suggested Specs from issues"),
            ("describe", "print a Change Request block for this branch's change, when it needs one (--commit records it)"),
            ("revise", "reopen an approved Spec: record what was wrong, so its owners change it and it is approved again"),
            ("test", "run the tests (green on head, red on base) and write evidence"),
            ("proposal", "a proposal's tables (matrix), or an accepted one as an Initiative and Epics (convert)"),
        ),
    ),
    (
        "Decide",
        (
            ("approve", "record a person's Spec approval or Merge approval on this machine"),
            ("explore", "one page comparing two or three directions, their trade-offs, and the rounds, for a person to pick one"),
        ),
    ),
    (
        "Check",
        (
            ("gate", "run every gate rule: a local preflight, a CI run, or any context; --paths forecasts the route before any code"),
            ("validate", "validate the repository, or the files given"),
            ("record", "check an agent change record (verify), or export gate records and events (export)"),
        ),
    ),
    (
        "Autopilot",
        (
            ("autopilot", "run the AIDD loop between your decisions: start, next, note, status, stop"),
            ("context", "the minimal context pack for a step: paths, a reason each, and token estimates"),
        ),
    ),
    (
        "Operate",
        (
            ("land", "land this branch on the local trunk once the gate passes"),
            ("publish", "take the work off this machine: push it, open its PR/MR, and carry your recorded decisions there"),
            ("goal", "open the goal branch of a small goal that is batched (open), or see each goal and open branch (list)"),
            ("integrate", "the team's step: merge a finished Spec's branch into its goal branch, with no person asked"),
            ("sync", "merge the goal into a Spec's branch, or the default branch into the goal"),
            ("observe", "after release: watch a Spec's rollback trigger, or a metric's control band (--band)"),
            ("release-notes", "release notes from the Specs landed since a tag, grouped as Keep a Changelog"),
        ),
    ),
    (
        "Maintainers and harnesses",
        (
            ("eval", "run the example suite, the agent evals, or the standards check"),
            ("mcp", "serve aidd to agents as MCP tools over stdio"),
            ("hook", "agent harness hooks: pre-tool, session-start, prompt-submit, stop, pre-compact"),
            ("gen-docs", "maintainers: regenerate the generated blocks in the docs and the skill"),
            ("hash", "plumbing: the Spec hash the gate compares at the approved commit and the head, and the Spec approval page (--summary --html)"),
        ),
    ),
)
HIDDEN_GROUP = COMMAND_GROUPS[-1][0]

# When to use each command: the "Which command when" table in docs/CLI.md, and the everyday rows in README.md (`aidd gen-docs`). The everyday commands come
# first, in the order of the loop, each row as (what you type, the commands it names, when); then every other command
# by its group in COMMAND_GROUPS, with the phrase in WHEN. tests/test_command_guide.py fails on a command with neither.
EVERYDAY: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "`aidd gate --paths`",
        ("gate",),
        "before the first edit: see the route the planned paths need, its lane, and its first step (a Spec, or the fast lane)",
    ),
    ("`aidd new spec`", ("new",), "when the route needs a Spec: start the Spec from its template"),
    (
        "`aidd approve spec`",
        ("approve",),
        "Spec approval from your own terminal; at the agent's prompt, typing `approve <ID>` records the same",
    ),
    (
        "`aidd test`",
        ("test",),
        "once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file",
    ),
    ("`aidd gate`", ("gate",), "before you ask for Merge approval: run every gate rule on this branch; CI runs it on every pull request or merge request"),
    ("`aidd land`", ("land",), "land a passing branch on the local trunk and record the Merge approval; at the prompt, `land it`"),
    (
        "`aidd publish`",
        ("publish",),
        "take the branch off this machine: push it, open its pull request on GitHub, and carry your approvals there; at the prompt, `publish`",
    ),
    ("`aidd list`", ("list",), "to see all open work and who holds each step; `--branch` for the change in hand"),
)
# A command an older aidd had, and the commands that do its work now: said instead of "not an aidd command".
RETIRED_COMMANDS = {
    "guard": "what changed outside the agent's session is part of your next decision now: say it again (such as `land it`), "
    "and aidd records it with those changes and lists each one, with how to put it back",
    "ship": "`aidd land` lands this branch on the local trunk, `aidd publish` takes it off this machine, and on a pull request a person's `merge it` merges it",
}
# The everyday commands a person types: the README's short table (`aidd gen-docs`), and all that `aidd --help` lists.
# An agent runs the others before and while it builds (`aidd gate --paths`, `aidd new spec`, `aidd test`), and the
# README says so in one sentence.
README_FORMS: tuple[str, ...] = ("`aidd gate`", "`aidd land`", "`aidd publish`", "`aidd list`")
EVERYDAY_COMMANDS: tuple[str, ...] = tuple(dict.fromkeys(n for form, names, _ in EVERYDAY if form in README_FORMS for n in names))
WHEN: dict[str, str] = {
    "init": "once in each repository: write the config, the skill, and the CI workflows",
    "upgrade": "after you install a new aidd: bring the repository's aidd files up to it",
    "self-update": "to update the CLI now; it also checks once a day by itself, after a command you run at a terminal",
    "uninstall": "to remove aidd from a repository",
    "doctor": "after `init` or `upgrade`, or when something looks wrong: check the wiring",
    "standard": "to see the choices the packs leave open, or to adopt one of aidd's opinionated standards (`add`)",
    "stack": "to adopt a set of opinionated standards that go together, such as `python-cli` (`add`)",
    "log": "to read one Spec's history: its status changes, its approvals, and its Assisted-by trailers",
    "owners": "to see who decides and who does the work in the repository; `--changed` lists only the standards and project rules for some paths",
    "metrics": "every week, or at a retrospective: see where changes wait, the DORA metrics, and agent autonomy",
    "digest": "for a status report since a date or a tag: for the team, or for a client (`--client`)",
    "new": "to start other work or a document: an Epic, an Initiative, a Proposal, an exploration, an ADR, a runbook",
    "import": "to start from a plan in another planning tool, or from tracker issues",
    "describe": "to raise a change's route, declare a risk or a scope, or carry an emergency: print a Change Request block",
    "extensions": "to see which plugins from aidd's registry fit this repository, and the line a person runs to install each (`suggest`)",
    "revise": "when an approved Spec turns out wrong before it lands: record why and reopen it for its owners and a new approval",
    "proposal": "to make a proposal's tables (`matrix`), or to turn an accepted proposal into an Initiative and Epics (`convert`)",
    "explore": "when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it)",
    "worktrees": "to see what each worktree holds and whether it is merged or stale, and to remove the merged ones (`clean`)",
    "validate": "to check the whole repository, or the files you name",
    "record": "to check an agent change record (`verify`), or to export gate records and events (`export`)",
    "goal": "once you agree to a plan: open the goal branch of each small goal that is batched",
    "integrate": "on a goal: once a Spec is verified and reviewed, land its branch in the goal branch (the release asks the person)",
    "sync": "on a goal: after a sibling Spec integrates, or the default branch moves, merge the newer work in",
    "observe": "after a release: watch a Spec's rollback trigger, or a metric's control band",
    "release-notes": "at a release: write the release notes from the Specs that landed",
    "config": "to see what this repository sets and what you may want to set; `--all` lists every setting, its value here, and where it comes from",
    "help": "to find a command: the everyday ones, every one (`--all`), or one command's arguments and flags (`aidd help <command>`)",
    "eval": "maintainers: run the example suite, the agent evals, or the standards check",
    "gen-docs": "maintainers: after a change to a schema or to the help, regenerate the generated blocks",
    "mcp": "harnesses: serve aidd to agents as MCP tools; `aidd init` wires it",
    "hook": "harnesses: the agent hooks that `aidd init` wires; you do not run them yourself",
    "hash": "plumbing: what the gate compares to see that the approved Spec and its tests still read the same; nobody approves with it",
    "autopilot": "run the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide",
    "context": "experimental: before a role's step, list what it reads by path, with a token estimate each",
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
    "aidd hash": "aidd hash SPEC-1",
    "aidd approve": "aidd approve spec SPEC-1",
    "aidd explore": "aidd explore specs/SPEC-12/explore/split-bill",
    "aidd digest": "aidd digest --since v1.0.0",
    "aidd log": "aidd log SPEC-1",
    "aidd import": "aidd import speckit specs/001-feature",
    "aidd proposal": "aidd proposal convert proposals/PROP-1/proposal.md",
    "aidd autopilot next": "aidd autopilot next --session <id>",
    "aidd observe": "aidd observe SPEC-1",
}
# What a missing positional argument is, in words, for the error (argparse names it by its dest).
MISSING: dict[str, str] = {
    "kind": "what to create (spec, epic, initiative, proposal, or a document)",
    "what": "what to approve (spec or merge)",
    "spec": "the Spec (its id, such as SPEC-1, or its path)",
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
            if prog == "aidd" and m.group(1) in RETIRED_COMMANDS:
                lines = [f"aidd: `aidd {m.group(1)}` is retired: {RETIRED_COMMANDS[m.group(1)]}"]
            elif prog == "aidd":
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
        return super().parse_known_args(args, namespace)

    def format_help(self) -> str:
        action = next((a for a in self._actions if isinstance(a, argparse._SubParsersAction)), None)
        if action is None or self.prog != "aidd":
            return super().format_help()
        import textwrap

        grouped = {n for _, rows in COMMAND_GROUPS for n, _ in rows}
        # Installed aidd.commands extensions, with the help they registered.
        helps = {a.dest: a.help or "" for a in action._choices_actions}
        extra = tuple((n, helps.get(n) or p.description or "") for n, p in sorted(action.choices.items()) if n not in grouped)
        purpose = {n: text for _, rows in COMMAND_GROUPS for n, text in rows}
        if self.show_all:
            shown = (*COMMAND_GROUPS, *((("Extensions", extra),) if extra else ()))
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
    revisions `aidd mcp` speaks and the tools it lists. docsgen sits below the CLI, so `aidd gen-docs` hands them to it."""
    from aidd.cli import mcp_tools  # only gen-docs reads the tools, so building the parser never loads them

    return docsgen.CliFacts(
        parser=build_parser(),
        command_groups=COMMAND_GROUPS,
        hidden_group=HIDDEN_GROUP,
        everyday=EVERYDAY,
        readme=README_FORMS,
        when=WHEN,
        mcp_supported=mcp_protocol.SUPPORTED,
        mcp_protocol=mcp_protocol.PROTOCOL,
        exit_codes=arguments.EXIT_CODES,
        mcp_tools=tuple(str(tool["name"]) for tool in mcp_tools.TOOLS),
    )


def build_parser(*, plugins: bool = False) -> argparse.ArgumentParser:
    """The CLI. With `plugins`, installed `aidd.commands` extensions add their subcommands, unless discovery is sealed;
    `main` asks for them only when the command it runs is not one of ext.PROTECTED."""
    # No abbreviation anywhere (_Parser): `--al` is not `--all`, and `--conf` is not `--confirmed`.
    p = _Parser(prog="aidd", description="aidd: route, prove, and gate AI-driven change.", epilog=EPILOG, formatter_class=_Help)
    p.add_argument("--version", action="version", version=f"aidd {__version__}")
    p.add_argument("--all", action="store_true", help="with --help: list every command, by group")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def cmd(name: str, help_text: str, func, into=None, short: str = "") -> argparse.ArgumentParser:
        # The top-level overview comes from _Parser.format_help, so a command is added without `help=` (argparse would
        # list it again); an action of a command group (`into`) lists itself in the group's help with `short`.
        if into is not None:
            s = into.add_parser(name, help=short, description=help_text, formatter_class=_Help)
        else:
            s = sub.add_parser(name, description=help_text, formatter_class=_Help)
        s.set_defaults(func=Handler(func) if isinstance(func, str) else func)
        return s

    def flag(parser, name: str, help_text: str) -> None:
        parser.add_argument(name, action="store_true", help=help_text)

    for group in grammar.GROUPS:
        group.register(cmd, flag)

    if plugins and not extensions.sealed():
        extensions.register_commands(sub, set(sub.choices))
    return p
