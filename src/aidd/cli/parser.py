"""The command line's grammar: the top-level parser and its grouped help, the groups' registrars
(aidd.cli.grammar), and the facts the generated docs restate.
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys

from aidd import __version__, docsgen
from aidd.cli import grammar, mcp_protocol
from aidd.kernel import extensions

EPILOG = """The loop: Plan -> Specify (new spec) -> Spec approval (hash --line, or approve spec) -> Implement and Verify, repeated
  until green (test) -> Review (gate) -> Merge approval (approve merge) -> Ship (ship) -> Learn (observe).
  Before the first edit, gate --paths gives the route and its lane. The fast lane skips Specify and Spec approval: describe
  prints its Change Request block. list shows all open work and who holds each step.
Exit codes: 0 pass or ok, 1 fail, 3 pending (a local gate; `gate github` exits 0 and `gate gitlab` exits 1 on pending unless --pending-ok), 2 error.
Docs: https://github.com/thaithienvanid/aidd"""

# The top-level help, by what a person is doing. Every command is in exactly one group (docsgen._subcommands reads them);
# the last group, the maintainer and harness commands, shows only with `aidd --help --all`.
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
            ("describe", "print the Change Request block for this branch's change (--commit records it)"),
            ("revise", "reopen an approved Spec: record what was wrong, so its owners change it and it is approved again"),
            ("test", "run the tests (green on head, red on base) and write evidence"),
            ("proposal", "a proposal's tables (matrix), or an accepted one as an Initiative and Epics (convert)"),
        ),
    ),
    (
        "Decide",
        (
            ("hash", "print a Spec hash, or the approval line an Approver posts (--line); a proposal's sign-off hash"),
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
            ("ship", "merge this branch into the base branch once the gate passes (local-first)"),
            ("goal", "open the goal branch of a small goal that ships batched (open), or see each goal and open branch (list)"),
            ("integrate", "the team's step: merge a finished Spec's branch into its goal branch, with no person asked"),
            ("sync", "merge the goal into a Spec's branch, or the default branch into the goal"),
            ("observe", "after release: watch a Spec's rollback trigger, or a metric's control band (--band)"),
            ("release-notes", "release notes from the Specs shipped since a tag, grouped as Keep a Changelog"),
        ),
    ),
    (
        "Maintainers and harnesses",
        (
            ("eval", "run the example suite, the agent evals, or the standards check"),
            ("mcp", "serve aidd to agents as MCP tools over stdio"),
            ("hook", "agent harness hooks: pre-tool, session-start, prompt-submit, stop, pre-compact"),
            ("gen-docs", "maintainers: regenerate the generated blocks in the docs and the skill"),
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
        "`aidd hash --line`, or `aidd approve spec`",
        ("hash", "approve"),
        "to get Spec approval: an Approver posts the line; with no platform, a person approves at the terminal",
    ),
    (
        "`aidd test`",
        ("test",),
        "once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file",
    ),
    ("`aidd gate`", ("gate",), "before you ask for Merge approval: run every gate rule on this branch; CI runs it on every pull request or merge request"),
    ("`aidd ship`", ("ship",), "with no platform: merge a passing branch and record the Merge approval"),
    ("`aidd list`", ("list",), "to see all open work and who holds each step; `--branch` for the change in hand"),
)
# The everyday commands a person types, the README's short table (`aidd gen-docs`). An agent runs the others before
# and while it builds (`aidd gate --paths`, `aidd new spec`, `aidd test`), and the README says so in one sentence.
README_FORMS: tuple[str, ...] = ("`aidd hash --line`, or `aidd approve spec`", "`aidd gate`", "`aidd ship`", "`aidd list`")
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
    "describe": "on the fast lane: print the Change Request block for the change description",
    "extensions": "to see which plugins from aidd's registry fit this repository, and the line a person runs to install each (`suggest`)",
    "revise": "when an approved Spec turns out wrong before it ships: record why and reopen it for its owners and a new approval",
    "proposal": "to make a proposal's tables (`matrix`), or to turn an accepted proposal into an Initiative and Epics (`convert`)",
    "explore": "when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it)",
    "worktrees": "to see what each worktree holds and whether it is merged or stale, and to remove the merged ones (`clean`)",
    "validate": "to check the whole repository, or the files you name",
    "record": "to check an agent change record (`verify`), or to export gate records and events (`export`)",
    "goal": "once you agree to a plan: open the goal branch of each small goal that ships batched",
    "integrate": "on a goal: once a Spec is verified and reviewed, land its branch in the goal branch (the release asks the person)",
    "sync": "on a goal: after a sibling Spec integrates, or the default branch moves, merge the newer work in",
    "observe": "after a release: watch a Spec's rollback trigger, or a metric's control band",
    "release-notes": "at a release: write the release notes from the Specs that shipped",
    "eval": "maintainers: run the example suite, the agent evals, or the standards check",
    "gen-docs": "maintainers: after a change to a schema or to the help, regenerate the generated blocks",
    "mcp": "harnesses: serve aidd to agents as MCP tools; `aidd init` wires it",
    "hook": "harnesses: the agent hooks that `aidd init` wires; you do not run them yourself",
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
    "aidd hash": "aidd hash SPEC-1 --line",
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
    """The top-level parser: its help lists the commands by COMMAND_GROUPS, each with its one-line help. The maintainer
    and harness commands (HIDDEN_GROUP) are listed only with `--all`; they work either way. An error is one or two
    lines that say what to type (clig.dev): a close match for a mistyped word, an example for a missing argument."""

    show_all = False
    _words: list[str] = []

    def error(self, message: str):
        import difflib
        import re

        prog, lines = self.prog, [f"{self.prog}: {message}"]
        # Python 3.15's argparse adds its own guess (", maybe you meant 'x'?"); aidd gives its own, so it reads past it.
        if m := re.search(r"invalid choice: '([^']*)'(?:, maybe you meant '[^']*'\?)? \(choose from (.*)\)", message):
            choices = re.findall(r"'([^']*)'", m.group(2))
            close = difflib.get_close_matches(m.group(1), choices, n=1, cutoff=0.75)  # a typo, never a guess ("next" is not "context")
            if prog == "aidd":
                lines = [f"aidd: '{m.group(1)}' is not an aidd command." + (f" Did you mean `aidd {close[0]}`?" if close else " `aidd --help` lists them.")]
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
            command = next((w for w in self._words if not w.startswith("-")), "")
            sub = next((a.choices.get(command) for a in self._actions if isinstance(a, argparse._SubParsersAction)), None)
            if sub is not None:
                prog = sub.prog
                options = [o for a in sub._actions for o in a.option_strings]
                bad = message.split(": ", 1)[1].split()
                close = difflib.get_close_matches(bad[0].split("=", 1)[0], options, n=1, cutoff=0.75)
                lines = [f"{prog}: unknown option {' '.join(bad)}." + (f" Did you mean `{close[0]}`?" if close else "")]
        if "--help" not in lines[0]:
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
        shown = [(t, rows) for t, rows in COMMAND_GROUPS if self.show_all or t != HIDDEN_GROUP]
        width = max(len(n) for _, rows in (*COMMAND_GROUPS, ("", extra)) for n, _ in rows) + 2
        wrap = max(shutil.get_terminal_size((100, 24)).columns, 60) - width - 4
        lines = [self.format_usage().rstrip(), "", self.description or "", ""]
        for title, rows in (*shown, *((("Extensions", extra),) if extra else ())):
            lines.append(f"{title}:")
            for name, text in rows:
                chunks = textwrap.wrap(text, wrap) or [""]
                lines.append(f"  {name.ljust(width)}{chunks[0]}")
                lines += [f"  {' ' * width}{c}" for c in chunks[1:]]
            lines.append("")
        if not self.show_all:
            hidden = len(COMMAND_GROUPS[-1][1])
            lines += [f"{HIDDEN_GROUP}: {hidden} more commands, listed by `aidd --help --all`.", ""]
        lines += [
            "options:",
            "  -h, --help  show this help message and exit",
            "  --all       with --help: also list the maintainer and harness commands",
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
    revisions `aidd mcp` speaks. docsgen sits below the CLI, so `aidd gen-docs` hands them to it."""

    return docsgen.CliFacts(
        parser=build_parser(),
        command_groups=COMMAND_GROUPS,
        hidden_group=HIDDEN_GROUP,
        everyday=EVERYDAY,
        readme=README_FORMS,
        when=WHEN,
        mcp_supported=mcp_protocol.SUPPORTED,
        mcp_protocol=mcp_protocol.PROTOCOL,
    )


def build_parser(*, plugins: bool = False) -> argparse.ArgumentParser:
    """The CLI. With `plugins`, installed `aidd.commands` extensions add their subcommands, unless discovery is sealed;
    `main` asks for them only when the command it runs is not one of ext.PROTECTED."""
    # allow_abbrev=False: `--al` is not `--all`. It binds the top-level options only; each command keeps its own abbreviations.
    p = _Parser(prog="aidd", description="aidd: route, prove, and gate AI-driven change.", epilog=EPILOG, formatter_class=_Help, allow_abbrev=False)
    p.add_argument("--version", action="version", version=f"aidd {__version__}")
    p.add_argument("--all", action="store_true", help="with --help: also list the maintainer and harness commands")
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
