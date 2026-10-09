"""aidd: the command line."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import __version__, docs, evals, ext, gates, gitutil, globs, http, inputs, localctx, metrics, model, packs, repo, report, resources, rules, runner
from . import config as cfgmod
from .util import TRAILER, agent_coauthors, norm, red_ok, split_command
from .verify import verify

# Where `aidd hook pre-tool` logs its denials (guard.GUARD_LOG), relative to the repository's top level.
GUARD_LOG_DEFAULT = ".aidd/work/guard.jsonl"
# The version of `aidd owners --json` (schemas/owners.schema.json): a new key keeps it, a renamed or removed one bumps it.
OWNERS_SCHEMA_VERSION = "1"
# The version of the other --json objects: `gate --json` (schemas/record.schema.json), `assess --json`
# (schemas/assess.schema.json), `list --json`, `standard list --json`, `stack list --json`, `log --json`, and
# `observe --band --json`, `eval packs --json`, and `record export --format json`. A new key keeps it; a renamed or
# removed one bumps it. `metrics --json` carries metrics.SCHEMA_VERSION.
JSON_SCHEMA_VERSION = "1"

EXIT = {"pass": 0, "fail": 1, "pending": 3}
# What a green `aidd eval standards` proves, printed with the count so nobody reads it as more.
STANDARDS_BASIS = (
    "A checked entry names its source and a sentence read there on its date. That proves the source was read, "
    "not that the practice matches the edition. So the count is not that many independent verifications."
)
# What `aidd eval packs` measures, printed with its counts.
PACKS_BASIS = (
    "tokens are estimated at four characters a token. The caps are 2,000 a pack, 1,500 a practice skill, and 1,500 a reference. "
    "A pack has at most two references, and a practice skill three. A description has at most 250 characters (the aidd-team router 460)"
)
VOCAB = resources.load_json("common.schema.json")["$defs"]
TYPES = VOCAB["type"]["enum"]
DIMENSIONS = VOCAB["dimension"]["enum"]
EPILOG = """The loop: assess (the route and its lane) -> spec lane: new spec, then Spec approval (hash --line, or approve spec)
  -> Implement and Verify, repeated until green (test) -> gate -> review -> Merge approval (approve merge) -> ship -> observe.
  The fast lane skips the Spec: describe prints the Change Request block. list shows all open work and who holds each step.
Exit codes: 0 pass or ok, 1 fail, 3 pending (a local gate; `gate github` exits 0 and `gate gitlab` exits 1 on pending unless --pending-ok), 2 error.
Docs: https://github.com/thaithienvanid/aidd"""

# The top-level help, by what a person is doing. Every command is in exactly one group (docs._subcommands reads them);
# the last group, the maintainer and harness commands, shows only with `aidd --help --all`.
COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Setup",
        (
            ("init", "adopt aidd in a repository"),
            ("upgrade", "bring the repository's aidd files up to this aidd (a dry run unless --yes)"),
            ("uninstall", "reverse `aidd init` (list what it would remove, or remove it with --yes)"),
            ("doctor", "check that the repository is wired correctly"),
            ("standard", "list the open choices and aidd's library standards, or add a copy of one (add)"),
            ("stack", "list the stacks, or add one: its standards and its [project.stack] entries (add)"),
        ),
    ),
    (
        "Understand",
        (
            ("assess", "this change: its route and lane, its next steps, and its overlaps; --paths before any code"),
            ("list", "all open work and who holds each step (--mine, --waiting-on-me, --agent, --blocked)"),
            ("log", "one Spec's history from git"),
            ("owners", "who decides and who does the work"),
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
            ("gate", "run every gate rule: a local preflight, a CI run, or any context"),
            ("validate", "validate the repository, or the files given"),
            ("record", "check an agent change record (verify), or export gate records and events (export)"),
        ),
    ),
    (
        "Autopilot (experimental)",
        (
            ("autopilot", "run the AIDD loop between your decisions: start, next, note, status, stop"),
            ("context", "the minimal context pack for a step: paths, a reason each, and token estimates"),
        ),
    ),
    (
        "Operate",
        (
            ("ship", "merge this branch into the base branch once the gate passes (local-first)"),
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

# When to use each command: the "Which command when" table in README.md (`aidd gen-docs`). The everyday commands come
# first, in the order of the loop, each row as (what you type, the commands it names, when); then every other command
# by its group in COMMAND_GROUPS, with the phrase in WHEN. tests/test_command_guide.py fails on a command with neither.
EVERYDAY: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "`aidd assess`",
        ("assess",),
        "before the first edit (`aidd assess --paths`), or on a branch (`aidd assess`): see the change's route, its lane, and its next step",
    ),
    ("`aidd new spec`", ("new",), "when the route needs a Spec: start the Spec from its template"),
    (
        "`aidd hash --line`, or `aidd approve spec`",
        ("hash", "approve"),
        "to get Spec approval: an Approver posts the line; with no platform, a person approves at the terminal",
    ),
    ("`aidd test`", ("test",), "after each step: run the tests, red on the base and green on the head"),
    ("`aidd gate`", ("gate",), "before you ask for Merge approval: run every gate rule on this branch; CI runs it on every pull request or merge request"),
    ("`aidd ship`", ("ship",), "with no platform: merge a passing branch and record the Merge approval"),
    ("`aidd list`", ("list",), "to see all open work and who holds each step"),
)
WHEN: dict[str, str] = {
    "init": "once in each repository: write the config, the skill, and the CI workflows",
    "upgrade": "after you install a new aidd: bring the repository's aidd files up to it",
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
    "proposal": "to make a proposal's tables (`matrix`), or to turn an accepted proposal into an Initiative and Epics (`convert`)",
    "explore": "when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it)",
    "validate": "to check the whole repository, or the files you name",
    "record": "to check an agent change record (`verify`), or to export gate records and events (`export`)",
    "observe": "after a release: watch a Spec's rollback trigger, or a metric's control band",
    "release-notes": "at a release: write the release notes from the Specs that shipped",
    "eval": "maintainers: run the example suite, the agent evals, or the standards check",
    "gen-docs": "maintainers: after a change to a schema or to the help, regenerate the generated blocks",
    "mcp": "harnesses: serve aidd to agents as MCP tools; `aidd init` wires it",
    "hook": "harnesses: the agent hooks that `aidd init` wires; you do not run them yourself",
    "autopilot": "experimental: run the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide",
    "context": "experimental: before a role's step, list what it reads by path, with a token estimate each",
}
PASS_ENV_HELP = (
    "pass this credential-like variable to the command (repeatable); by default every *TOKEN*, *SECRET*, *PASSWORD*, *_KEY, "
    "and *CREDENTIAL* variable is dropped"
)


class _Help(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Show a default only when it says something and the help text does not already explain it."""

    def _get_help_string(self, action):
        text = action.help or ""
        if "default" in text or action.default in (None, "", False, [], argparse.SUPPRESS):
            return text
        return super()._get_help_string(action)


class _Parser(argparse.ArgumentParser):
    """The top-level parser: its help lists the commands by COMMAND_GROUPS, each with its one-line help. The maintainer
    and harness commands (HIDDEN_GROUP) are listed only with `--all`; they work either way."""

    show_all = False

    def parse_known_args(self, args=None, namespace=None):
        if self.prog == "aidd":
            # `--help` prints as soon as argparse reads it, so look for `--all` among the options before the command first.
            words = list(sys.argv[1:] if args is None else args)
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


def _enter_repo(args, *path_attrs: str, file_attrs: tuple[str, ...] = ()) -> None:
    """Run from the repository root. Repo-relative arguments are rebased; file arguments become absolute."""
    top = Path(gitutil.toplevel(check=True))
    cwd = Path.cwd()
    for attr in file_attrs:
        value = getattr(args, attr, None)
        if value:
            setattr(args, attr, str((cwd / value).resolve()))
    for attr in path_attrs:
        value = getattr(args, attr, None)
        if value:
            abs_path = (cwd / inputs.repo_path(value)).resolve()
            setattr(args, attr, abs_path.relative_to(top.resolve()).as_posix() if abs_path.is_relative_to(top.resolve()) else inputs.repo_path(value))
    os.chdir(top)


def _repo_relative(path: Path) -> str:
    """A path as printed after `_enter_repo`: relative to the repository root when it is inside it, else as given."""
    p = path.resolve()
    here = Path.cwd().resolve()
    return p.relative_to(here).as_posix() if p.is_relative_to(here) else str(path)


def _body(args) -> str | None:
    if getattr(args, "body_file", None):
        return Path(args.body_file).read_text(encoding="utf-8")
    if getattr(args, "spec", None):
        return localctx.spec_block(args.spec)
    return None


_APPROVER = re.compile(
    r"^(?:(?!email:|agent:)[a-z0-9][a-z0-9_.-]*:(?!//))?"  # an optional tenant
    r"(?:@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?"  # @user or @org/team
    r"|email:[^@\s,]+@[^@\s,]+\.[^@\s,]+"  # email:you@example.com
    r"|[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[bot\])?)$"  # a bare login
)


def _approvers(values: list[str] | None) -> list[str] | None:
    """--approvers as people type it: space or comma separated (`--approvers "@a,@b"`), each a valid identity."""
    if not values:
        return values
    out = [v.strip() for value in values for v in value.split(",") if v.strip()]
    bad = [v for v in out if v.lower().startswith("agent:") or not _APPROVER.match(v)]
    if bad:
        raise ValueError(
            f"--approvers: {', '.join(repr(b) for b in bad)} is not an approver identity; use @user, @org/team, email:you@example.com, or a "
            "login (agents never approve)"
        )
    return list(dict.fromkeys(out))


def _specialists(entries: list[str] | None) -> dict[str, list[str]]:
    """--specialist security=@org/security,@alice -> {"security": ["@org/security", "@alice"]}."""
    out: dict[str, list[str]] = {}
    for entry in entries or []:
        pool, sep, who = entry.partition("=")
        if not sep or not pool.strip() or not who.strip():
            raise ValueError(f"--specialist takes POOL=WHO[,WHO], got {entry!r}")
        out.setdefault(pool.strip(), []).extend(w.strip() for w in who.split(",") if w.strip())
    return out


# The Day-0 commit, as the agent runbook (llms-install.md, step 4) gives it: an agent commits the setup on a branch.
DAY_0_COMMIT = "Commit this setup on the branch `chore/adopt-aidd`. An agent adds its `Assisted-by:` trailer to the commit."
# A repository with no commit has no base branch to branch from: the Day-0 commit is a person's, and the agent stops.
DAY_0_NEW_REPOSITORY = (
    "New repository: a person makes the Day-0 commit, this setup and the project scaffold, on the default branch. "
    "An agent does not commit it: it stops here and hands back."
)


def cmd_init(args) -> int:
    from . import detect

    root = Path(args.path)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    found = detect.detect(root)
    if args.dry_run:
        print(detect.markdown(found), end="")
        return 0
    args.approvers = _approvers(args.approvers)
    if not args.approvers and args.profile != "solo":
        # An empty owners.approvers fails every change closed; under solo init names the operator, elsewhere nobody can guess.
        print(
            f"error: profile {args.profile} needs the people who may approve. Pass --approvers, such as:\n"
            f"  aidd init --profile {args.profile} --approvers @your-org/leads\n"
            "An approver is a user (@alice), a team (@org/team), or email:you@example.com for local-first approvals.\n"
            "`aidd init --dry-run` writes nothing.",
            file=sys.stderr,
        )
        return 2
    links = list(dict.fromkeys(args.link or []))
    repo.pin_workflow("", args.ref)  # a bad --ref stops here, before init writes anything
    # Without --test, the suite detected at the repository root; a monorepo's per-package suites stay a suggestion.
    detected_test = next((t["test"] for t in found["tests"] if t["path"] == "."), None) if not args.test else None
    if detected_test:
        print(f"detected the test command: {' '.join(detected_test)} (pass --test to choose another)")
    elif not args.test:
        # Every change fails `tests` until a suite exists, and adding one later is a config change (major): bind a smoke test now.
        print(
            "found no test command: bound a smoke test in [[tests]], so the first change has a suite to pass.\n"
            "The smoke test checks that every tracked Python file parses and that no file holds a conflict marker.\n"
            "Replace it with your real suite later, or now with --test"
        )
    actions = repo.init(
        root,
        profile=args.profile,
        ci=args.ci,
        links=links,
        skill=not args.no_skill,
        force=args.force,
        approvers=args.approvers,
        specialists=_specialists(args.specialist),
        test=split_command(args.test) if args.test else (detected_test or repo.SMOKE_TEST),
        policy=split_command(args.policy) if args.policy else None,
        goal=args.goal,
        enforce=args.enforce,
        agent_hooks=True if args.agent_hooks else (False if args.no_agent_hooks else None),
        team=args.team,
        harnesses=None if not args.harness else [h for h in args.harness if h != "none"],
        claude_plugins=args.claude_plugins,
        ref=args.ref,
        devcontainer=args.devcontainer,
        risk_rules=found["risk_rules"],
        stack=detect.radar(found),
        ui=not found["no_ui"],
        existing_code=found["existing_code"],
        compliance_targets=list(dict.fromkeys(args.compliance_target or [])) or None,
        security_ci=args.security_ci,
        held_commands=found["held_commands"],
        not_held=found["not_held"],
    )
    for line in actions:
        print(line)
    if repo.wrote_claude_code_files(actions, root):
        print(f"\n{repo.RESTART_NOTICE}")
    if not gitutil.run(["rev-parse", "--verify", "--quiet", "HEAD"], str(root), check=False).strip():
        # Greenfield: nothing is on the default branch yet, so nothing can be gated.
        print(
            f"\n{DAY_0_NEW_REPOSITORY}\n"
            "Then run `aidd doctor`. Every later change goes through a branch.\n"
            "The first Spec usually brings the test runner and the first test."
        )
    elif localctx.platform_of(str(root)) == "local" or args.ci == "none":
        print(
            "\nNext: check owners, [[tests]], and [[risk_rules]] in .aidd/config.toml, and run `aidd doctor`.\n"
            f"{DAY_0_COMMIT}\n"
            "A person then lands that Day-0 commit on the base branch. They run `git merge --ff-only chore/adopt-aidd` there.\n"
            "It is the one change that lands without `aidd ship`. The agent hook keeps agents off the base branch.\n"
            "Every later change goes through a branch, `aidd test`, and `aidd ship`."
        )
    else:
        print(
            "\nNext: check owners and [[tests]] in .aidd/config.toml, and run `aidd doctor`.\n"
            f"{DAY_0_COMMIT} Then open the setup PR/MR.\n"
            "A person merges the setup PR/MR."
        )
    if fit := detect.found_to_fit({**found, "risk_rules": []}):
        print(f"It also found {'; '.join(fit)}: `aidd init --dry-run` shows the config it proposes for them.")
    if not args.enforce and args.ci != "none":
        print(
            "The gate starts in advisory mode: it reports on 'aidd/gate (advisory)' and blocks nothing. Read `aidd metrics`\n"
            "for a week or two. Then set `mode = 'enforce'` in .aidd/config.toml, and require aidd/gate. The base branch's\n"
            "config wins over the CI file's input, on GitHub and GitLab alike."
        )
    return 0


def cmd_upgrade(args) -> int:
    """Bring a repository's aidd files up to this aidd, in one change; a dry run unless --yes."""
    try:
        actions = repo.upgrade(Path(args.path), ref=args.ref, yes=args.yes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in actions:
        print(line)
    if not args.yes and not actions[0].startswith("nothing to update"):
        print("\ndry run: nothing changed. Run again with --yes, then `aidd doctor`, and merge it as one change; it touches")
        print("protected paths, so the gate treats it as major.")
    print("\nThe CLI itself: `uv tool upgrade aidd` or `pipx upgrade aidd` (or the one-line installer with AIDD_REF=<release>).")
    print("The Claude Code plugins: `claude plugin update aidd@aidd` and `claude plugin update aidd-team@aidd`.")
    return 0


def cmd_uninstall(args) -> int:
    for line in repo.uninstall(Path(args.path), links=args.link or [], yes=args.yes):
        print(line)
    return 0


def _count(n: int, noun: str) -> str:
    """`1 stack`, `3 stacks`."""
    return f"{n} {noun}{'' if n == 1 else 's'}"


def cmd_standard(args) -> int:
    """`aidd standard list|add`: the open choices and the library, or a copy of library standards in this repository."""
    from . import standards

    _enter_repo(args)
    if args.standard_command == "add":
        for line in standards.add(Path("."), args.ids):
            print(line)
        print("Review the copies and the config as one change. Never edit a copy: `aidd doctor` reports one that changed.")
        return 0
    data = standards.rows(_config_or_none())
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print("Open choices (a pack or practice skill leaves them to the team; aidd's default holds until a standard fills one):")
    for c in data["open_choices"]:
        # Where an ecosystem has several options for the choice, name aidd's default among them.
        ecos = [standards.ecosystem(sid) for sid in c["filled_by"]]
        names = [
            sid + (" (default)" if ecos.count(standards.ecosystem(sid)) > 1 and c["default_by_ecosystem"].get(standards.ecosystem(sid)) == sid else "")
            for sid in c["filled_by"]
        ]
        print(f"  {c['ref']}: {c['question']} Default: {c['default_answer']}" + (f" Library: {', '.join(names)}." if names else ""))
    print("\nLibrary standards (opinionated; `aidd standard add <id>` copies one):")
    for s in data["standards"]:
        marks = [m for m in (s["status"] if s["status"] != "active" else "", s["policy"], "added" if s["added"] else "") if m]
        tool = f"{s['tool']} {s['checked_version']} (checked {s['checked']})" if s["tool"] else "no tool"
        print(f"  {s['id']}: fills {', '.join(s['fills'])}; {tool}; {s['trust']}" + (f" [{', '.join(marks)}]" if marks else ""))
    return 0


def cmd_stack(args) -> int:
    """`aidd stack list|add`: the library's stacks, or one stack's standards and `[project.stack]` entries copied here."""
    from . import standards

    _enter_repo(args)
    if args.stack_command == "add":
        for line in standards.add(Path("."), [], stack=args.name):
            print(line)
        print("Review the copies and the config as one change. Never edit a copy: `aidd doctor` reports one that changed.")
        return 0
    data = standards.stack_rows(_config_or_none())
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    for s in data["stacks"]:
        extends = f" (extends {s['extends']})" if s["extends"] else ""
        allowed = "" if s["allowed"] else " [not allowed by the company's policy]"
        print(f"{s['name']}{extends}: {s['description']}{allowed}\n  standards: {', '.join(s['standards'])}")
    return 0


def cmd_doctor(args) -> int:
    if args.autopilot:
        from . import autopilotcheck

        results = autopilotcheck.checks(Path(args.path))
        for level, msg in results:
            print(f"[{level:4}] {msg}")
        print(f"[info] {autopilotcheck.advisor_line(Path(args.path))}")
        print("\n" + autopilotcheck.CHECKLIST_TITLE)
        for item in autopilotcheck.CHECKLIST:
            print(f"  [ ] {item}")
        return 1 if any(level == "fail" for level, _ in results) else 0
    results = repo.doctor(Path(args.path), execute=True)
    for level, msg in results:
        print(f"[{level:4}] {msg}")
    return 1 if any(level == "fail" for level, _ in results) else 0


def _config_or_none() -> cfgmod.Config | None:
    if not Path(cfgmod.CONFIG_PATH).is_file():
        return None
    return cfgmod.load_file(cfgmod.CONFIG_PATH)


def _spec_route(args, cfg: cfgmod.Config | None) -> tuple[str, bool]:
    """(route, write) for `aidd new spec`: with --paths, the route computed from the paths (the entry check), raised to
    --route when that is higher; without, --route (default normal). `write` is False when the paths need no Spec: then
    nothing is written, the reason and the `--force` hint go to stderr, and `aidd new` exits 1."""
    chosen = args.route or "normal"
    if args.kind != "spec" or not args.paths:
        return chosen, True
    if cfg is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first, so the route can be computed from the paths")
    tracked = [p for p in gitutil.run(["ls-files", "-z"], check=False).split("\0") if p]
    a = rules.assess_paths(cfg, args.paths, ctype=args.type, dimensions=args.dimension or [], irreversible=args.irreversible, tracked=tracked)
    print(f"route: the minimum for these paths is {a.required_route} ({a.lane} lane)")
    for line in rules.reason_lines(a):
        print(f"  - {line}")
    if a.lane == "fast":
        if not args.force:
            print(
                "no Spec written: these paths need none. The fast lane implements and verifies directly, and `aidd describe` prints "
                "the Change Request block for the PR/MR. A Spec is still yours to choose: `--force` writes one (route normal), and the "
                "gate never lets a change below its minimum, only above it.",
                file=sys.stderr,
            )
            if hint := rules.untested_feature_hint(args.paths, ctype=args.type or "feat", tracked=tracked):
                print(hint, file=sys.stderr)
            return a.required_route, False
        return max(chosen, "normal", key=rules.ROUTE_RANK.__getitem__), True
    route = max(chosen, a.required_route, key=rules.ROUTE_RANK.__getitem__)
    if args.route and rules.ROUTE_RANK[args.route] < rules.ROUTE_RANK[a.required_route]:
        print(f"route {a.required_route}, not --route {args.route}: a Spec's route is never below the computed minimum")
    return route, True


def _new_doc(args, cfg: cfgmod.Config | None) -> int:
    """`aidd new <kind> <topic> --spec ID`: a linked document from its template, and its `[[docs]]` entry in the Spec.
    A feedback log belongs to no Spec: `aidd new feedback <topic>` writes it alone."""
    if args.kind in repo.UNLINKED_DOCS and args.spec:
        raise ValueError(f"a {args.kind} belongs to no one Spec: drop --spec; each entry names its Spec or hypothesis in its row")
    if args.no_link and args.kind in repo.UNLINKED_DOCS:
        raise ValueError(f"--no-link is for a doc a Spec links; a {args.kind} is never linked")
    if args.kind not in repo.UNLINKED_DOCS and not args.spec:
        raise ValueError(f"--spec is required: a {args.kind} doc belongs to the Spec that links it (`aidd new {args.kind} <topic> --spec SPEC-42`)")
    path, spec = repo.new_doc(
        Path("."),
        kind=args.kind,
        topic=args.id,
        spec_id=args.spec,
        area=args.area,
        title=args.title or "",
        docs_dir=cfg.docs_dir if cfg else "docs",
        specs_dir=cfg.specs_dir if cfg else "specs",
        link=not args.no_link,
        prototype=args.prototype,
    )
    print(path.as_posix())
    if spec is not None and args.no_link:
        entry = f'[[docs]]\nkind = "{args.kind}"\npath = "{path.as_posix()}"'
        print(
            f"not linked: {spec.as_posix()} is left to its writer, who adds this entry:\n{entry}{chr(10) + 'frozen = false' if args.kind in repo.LIVING_DOCS else ''}"
        )
        return 0
    if spec is None:
        print("next: add a row per piece of feedback, as it arrives, with its source; a person confirms each; `aidd digest` counts the themes")
        return 0
    if args.kind in repo.LIVING_DOCS:
        print(f"linked from {spec.as_posix()} as a living [[docs]] entry (frozen = false): people fill it after Spec approval")
    else:
        print(f"linked from {spec.as_posix()} as a frozen [[docs]] entry: Spec approval pins it with the Spec")
    print(f"next: replace the TODOs, then `aidd validate {spec.as_posix()}`")
    return 0


def _new_repo_doc(args, cfg: cfgmod.Config | None) -> int:
    """`aidd new design-system`, `architecture`, `data-map`, `vendors`, or `glossary`: the repository's one of each."""
    if args.id or args.spec or args.area or args.no_link:
        raise ValueError(f"a {args.kind} belongs to the repository, not a Spec: run `aidd new {args.kind}` with no id, --spec, or --area")
    paths = repo.new_repo_doc(Path("."), kind=args.kind, title=args.title or "", docs_dir=cfg.docs_dir if cfg else "docs")
    for p in paths:
        print(p.as_posix())
    route = "normal (baseline:design-system)" if args.kind == "design-system" else "minor, a docs change"
    if args.kind == "design-system":
        print("then: `node design/build.mjs` writes design/tokens.css, design/themes/<theme>.css, and DESIGN.md's token front matter")
        print("test: add `node design/build.mjs --check` (the drift test) to [[tests]]")
    print(f"next: replace the TODOs, and commit it as its own change: route {route}")
    if args.kind in repo.LIVING_DOCS:
        print(f'a Spec that changes what it records links it as a living doc: [[docs]] kind = "{args.kind}", frozen = false')
    return 0


def _new_contract(args, cfg: cfgmod.Config | None) -> int:
    """`aidd new contract <proposal id>`: the contract in the proposal's folder, then each change order."""
    if not args.id or args.spec or args.area or args.no_link:
        raise ValueError("a contract belongs to a proposal: `aidd new contract <proposal id>`, with no --spec or --area")
    path = repo.new_contract(Path("."), args.id, proposals_dir=cfg.proposals_dir if cfg else "proposals")
    print(path.as_posix())
    what = "the change order: the delta and the affected Acceptance ids" if path.parent.name == repo.CHANGE_ORDERS else "the statement-of-work base"
    print(f"next: draft {what}; every price, legal term, and the client's decision stay with people")
    return 0


def _new_exploration(args) -> int:
    """`aidd new exploration <folder> --title "<the question>"`: the exploration's front matter and sections."""
    from . import explore

    if not args.id or not args.title:
        raise ValueError('an exploration needs its folder and its question: `aidd new exploration docs/design/SPEC-12 --title "..."`')
    path = explore.new_exploration(Path(args.id), question=args.title, owner=args.owner or "product-designer", timebox=args.timebox)
    print(path.as_posix())
    print(f"next: draw two or three divergent directions (or, for a decision card, write the options with no visuals), then `aidd explore {args.id}`")
    return 0


def cmd_new(args) -> int:
    _enter_repo(args, *(("id",) if args.kind == "exploration" else ()))
    cfg = _config_or_none()
    if args.kind in repo.REPO_DOCS:
        return _new_repo_doc(args, cfg)
    if args.kind == "contract":
        return _new_contract(args, cfg)
    if args.kind == "exploration":
        return _new_exploration(args)
    if not args.id:
        raise ValueError(f"an id is required for a {args.kind}: `aidd new {args.kind} <id>`")
    if args.kind in repo.DOC_TEMPLATES:
        return _new_doc(args, cfg)
    if not args.title:
        raise ValueError(f"--title is required for a {args.kind}")
    if args.area:
        raise ValueError(f"--area names a linked document's folder: use it with {', '.join(sorted(set(repo.DOC_TEMPLATES) - repo.UNLINKED_DOCS))}")
    if args.no_link and not (args.kind == "runbook" and args.spec):
        raise ValueError("--no-link is for a document a Spec links: a linked doc, or a runbook with --spec")
    linked = repo.find_spec(Path("."), cfg.specs_dir if cfg else "specs", args.spec) if args.kind == "runbook" and args.spec else None
    if args.kind != "spec" and (args.paths or args.dimension or args.irreversible):
        raise ValueError("--paths, --dimension, and --irreversible compute a Spec's route: use them with `aidd new spec`")
    if args.route == "emergency" and args.paths:
        raise ValueError("an emergency backfill Spec takes its route from the declared emergency, not from --paths")
    route, write = _spec_route(args, cfg)
    if not write:
        return 1  # nothing written: a script that goes on to edit the Spec must not think it exists
    path = repo.new_object(
        Path("."),
        kind=args.kind,
        id=args.id,
        title=args.title,
        route=route,
        scope=args.paths or None,
        dimensions=args.dimension or None,
        irreversible=args.irreversible,
        full=args.full,
        ctype=args.type,
        owner_team=args.owner_team or (cfg.get("owners", "default_team", default="") if cfg else ""),
        parent=args.parent,
        specs_dir=cfg.specs_dir if cfg else "specs",
        audience=args.audience,
        addressee=args.addressee,
        proposals_dir=cfg.proposals_dir if cfg else "proposals",
        spec=args.spec,
    )
    print(path)
    if linked is not None and args.no_link:
        print(
            f'not linked: {linked.as_posix()} is left to its writer, who adds this entry:\n[[docs]]\nkind = "runbook"\npath = "{path.as_posix()}"\nfrozen = false'
        )
    elif linked is not None:
        # A runbook outlives the change that rolls it out: a living doc, checked to exist, never frozen.
        repo.link_doc(linked, "runbook", path.resolve().relative_to(Path(".").resolve()).as_posix(), frozen=False)
        print(f"linked from {linked.as_posix()} as a living [[docs]] entry (frozen = false)")
    todo = {
        "runbook": "name the service, write steps a person can copy, run it once, record tested_on",
        "postmortem": "fill the timeline, causes, and action items with owners and dates",
        "proposal": "fill the needs and the goal, have a person record go_no_go",
    }.get(args.kind, "fill Context, Acceptance, tasks, and tests, write the test files")
    if args.kind == "spec" and repo.spec_template(route, args.full) == "spec-short":
        scope = "" if args.paths else "the Task's scope, "  # --paths already wrote it
        todo = f"replace the TODOs (Intent, Context, Acceptance, Design, Rollback, {scope}the tests), write the test files"
    print(f"next: {todo}, then `aidd validate {path}`")
    if args.kind == "spec":
        data, _ = model.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        asks = repo.required_docs(data, 0, cfg)
        if asks:
            shown = "; ".join(f"{k} ({'expected' if level == 'warn' else 'suggested'}: {why})" for k, level, why in asks)
            print(f"docs: {shown}; write each with `aidd new <kind> <topic> --spec {args.id}`")
    return 0


def cmd_import(args) -> int:
    """A short Spec from Spec Kit, OpenSpec, Kiro, or BMAD planning files, pointing at them."""
    from . import importers

    if args.tool == "issues":
        return _import_issues(args)
    if not args.path or args.github or args.file or args.label or args.limit is not None:
        raise ValueError(f"`aidd import {args.tool}` takes the plan's path; --github, --file, --label, and --limit are for `aidd import issues`")
    _enter_repo(args, "out", file_attrs=("path",))
    cfg = _config_or_none()
    if cfg is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first, so the route can be computed from the paths")
    path, lines = importers.build(args.tool, Path(args.path), Path("."), cfg, spec_id=args.id, out=args.out, title=args.title, ctype=args.type)
    print(path.as_posix())
    for line in lines:
        print(line)
    return 0


def _import_issues(args) -> int:
    """Suggested Specs from a tracker's issues: GitHub (--github OWNER/REPO) or any tracker's JSON export (--file)."""
    from . import intake

    if bool(args.github) == bool(args.file) or args.path:
        raise ValueError("`aidd import issues` reads --github OWNER/REPO or --file issues.json (one of them)")
    if args.id or args.out or args.title or args.type:
        raise ValueError("--id, --out, --title, and --type are for a plan; an issue brings its own title, and ids follow the Specs folder")
    limit = min(max(args.limit if args.limit is not None else intake.DEFAULT_LIMIT, 1), intake.MAX_LIMIT)
    _enter_repo(args, file_attrs=("file",))
    cfg = _config_or_none()
    if cfg is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first")
    if args.file:
        if args.label:
            raise ValueError("--label filters GitHub issues; filter the file before importing it")
        items = intake.from_file(Path(args.file))
    else:
        items = intake.from_github(args.github, label=args.label, limit=limit)
    for line in intake.write(Path("."), cfg, items, limit=limit):
        print(line)
    return 0


def cmd_digest(args) -> int:
    """A status rollup for the window: the team view, or the client view with a RAG status (--client)."""
    from . import rollup, views

    if args.include_cost and not args.client:
        raise ValueError("--include-cost goes with --client: the team view shows the cost whenever --cost is given")
    if args.blocked_days < 0:
        raise ValueError("--blocked-days is a number of days, 0 or more")
    if args.html is not None and not args.client:
        raise ValueError("--html goes with --client: the page is for the client; the team view is Markdown or --json")
    html_path = _html_arg(args.html)
    args.events = [str(Path(p).resolve()) for p in args.events or []]
    _enter_repo(args, file_attrs=("cost",))
    if _config_or_none() is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first")
    window = rollup.window(Path("."), args.since)
    paths = args.events if args.events else [p for p in (rollup.EVENTS_FILE,) if Path(p).is_file()]
    events = metrics.load(paths, since=window.start.isoformat()) if paths else []
    ledger = metrics.load_ledger(args.cost, since=window.start.isoformat()) if args.cost else None
    d = rollup.digest(Path("."), args.since, client=args.client, events=events, ledger=ledger, include_cost=args.include_cost, blocked_days=args.blocked_days)
    if html_path is not None:
        out = views.write(html_path or views.default_path("digest", f"{d['view']}-{d['generated_on']}"), rollup.digest_page(d))
        print(f"wrote {_repo_relative(out)}", file=sys.stderr)
    print(json.dumps(d, indent=2) if args.json else rollup.digest_markdown(d), end="\n" if args.json else "")
    return 0


def cmd_release_notes(args) -> int:
    """Release notes from the Specs shipped since a tag or date, grouped by Keep a Changelog, for users or developers."""
    from . import rollup

    _enter_repo(args)
    if _config_or_none() is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first")
    d = rollup.release_notes(Path("."), args.since, audience=args.audience)
    print(json.dumps(d, indent=2) if args.json else rollup.release_notes_markdown(d), end="\n" if args.json else "")
    return 0


def cmd_validate(args) -> int:
    if not args.paths:
        _enter_repo(args)
        errors, warnings = repo.check_repo(Path("."))
    else:
        found = [e for p in args.paths for e in repo.validate_file(Path(p))]
        errors = [e for e in found if not e.startswith("warning: ")]
        warnings = [e for e in found if e.startswith("warning: ")]
    for w in warnings:
        print(w if w.startswith("warning: ") else f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


_SPEC_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")


def _spec_by_id(value: str, ref: str | None) -> str:
    """`value` as a Spec or proposal path: itself when it names a file (in the working tree, or in `ref`), else, when it
    is an id (`SPEC-1`, `PROP-3`), the one Spec under the specs folder or proposal under the proposals folder whose id
    it is. Run from the repository root."""
    if Path(value).is_file() or (ref and gitutil.show(ref, value) is not None) or not _SPEC_ID.fullmatch(value) or value.endswith(".md"):
        return value
    cfg = _config_or_none()
    folder = cfg.specs_dir if cfg else "specs"
    proposals = cfg.proposals_dir if cfg else "proposals"
    named = globs.under(folder, f"{value}.md")
    for path in (named, globs.under(proposals, f"{value}/proposal.md")):
        if Path(path).is_file() or (ref and gitutil.show(ref, path) is not None):
            return path
    found = []
    candidates = [(p, "spec") for p in sorted(Path(folder).glob("*.md"))] + [(p, "proposal") for p in sorted(Path(proposals).glob("*/proposal.md"))]
    for p, kind in candidates:
        try:
            data, _ = model.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), str(p))
        except (model.ModelError, OSError):
            continue
        if data.get("kind") == kind and str(data.get("id")) == value:
            found.append(p.as_posix())
    if len(found) == 1:
        return found[0]
    if found:
        raise ValueError(f"{len(found)} files have the id {value} ({', '.join(found)}); name the file")
    raise ValueError(f"no Spec has the id {value} in {folder}/, and no proposal has it in {proposals}/; name the file, such as {named}")


def cmd_hash(args) -> int:
    raw = args.spec
    _enter_repo(args, "spec", file_attrs=("out",))
    if raw and "/" not in raw and "\\" not in raw and not Path(args.spec).is_file():
        args.spec = _spec_by_id(raw, None if args.worktree else args.ref)
    if args.worktree:
        text = Path(args.spec).read_text(encoding="utf-8")
        data, _ = model.split_front_matter(text, args.spec)
        if data.get("kind") == "proposal":
            return _proposal_hash(args, text)
        # Untracked files count too: the hash must match what the gate computes once they are committed.
        files = [
            p
            for p in gitutil.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"]).split("\0")
            if p and globs.match_any(model.frozen_paths(data), p) and Path(p).is_file()
        ]
        tree = gitutil.hash_files(files)
        read = lambda p: Path(p).read_text(encoding="utf-8", errors="replace")  # noqa: E731
    else:
        shown = gitutil.show(args.ref, args.spec)
        if shown is None:
            raise ValueError(f"{args.spec} is not in {args.ref}; commit it first, or pass --worktree")
        text = shown
        data, _ = model.split_front_matter(text, args.spec)
        if data.get("kind") == "proposal":
            _proposal_flags(args)  # refuse a Spec-only flag before any warning
            if gitutil.run(["status", "--porcelain", "--", args.spec], check=False).strip():
                print(f"warning: uncommitted changes to the proposal; this hash is for {args.ref}", file=sys.stderr)
            return _proposal_hash(args, text)
        tree = gitutil.ls_tree(args.ref)
        dirty = gitutil.run(["status", "--porcelain", "--", args.spec, *model.frozen_paths(data)], check=False).strip()
        if dirty:
            print(f"warning: uncommitted changes to the Spec or its tests; this hash is for {args.ref}", file=sys.stderr)
        read = lambda p: gitutil.show(args.ref, p) or ""  # noqa: E731
    h = model.spec_hash(text, tree)
    # The commit makes the approval prove Spec approval came before implementation (gates.spec_approval_proof).
    sha = "" if args.worktree else " " + gitutil.rev_parse(args.ref)
    if args.worktree and args.line:
        print(
            "warning: a --worktree line names no commit, so it cannot prove Spec approval came before implementation; under spec_approval_proof = require it never counts",
            file=sys.stderr,
        )
    line = f"/aidd approve-spec {data.get('id')} {h}{sha}" if args.line else h
    if args.summary:
        from . import digest

        # What the Approver reads before posting the line, in at most 25 lines; the line itself is the last.
        docs = model.frozen_docs(data)
        doc_texts = {p: read(p) for p in tree if globs.match_any(docs, p)}
        print(digest.spec_digest(text, args.spec, line, files=doc_texts))
    else:
        print(line)
    if args.html or args.out:
        _spec_view(args, text, data, h, line, tree, read)
    return 0


def _proposal_flags(args) -> None:
    """Refuse the flags that show what a Spec approval covers: a proposal has none of it."""
    if args.summary or args.html or args.out:
        raise ValueError("--summary, --html, and --out show what a Spec approval covers; on a proposal, use --line or no flag")


def _proposal_hash(args, text: str) -> int:
    """`aidd hash` on a proposal: the hash a person records as `sign_off.hash`, or with --line the whole sign_off line."""
    _proposal_flags(args)
    h = model.proposal_hash(text)
    print(f'sign_off = {{ by = "@you", on = "{dt.date.today().isoformat()}", hash = "{h}" }}' if args.line else h)
    return 0


def _spec_view(args, text: str, data: dict, h: str, line: str, tree: dict[str, str], read) -> None:
    """The Spec approval page: what `--summary` prints, and the frozen files, the route, and what changed since the last
    approval, as one HTML page for the Approver. The approval line on it is the one printed above."""
    from . import views

    line = line if line.startswith("/aidd") else f"/aidd approve-spec {data.get('id')} {h}" + ("" if args.worktree else f" {gitutil.rev_parse(args.ref)}")
    frozen = model.frozen_paths(data)
    files = {p: read(p) for p in sorted(tree) if globs.match_any(frozen, p)}
    route = None
    cfg = _config_or_none_quiet()
    scope = [s for task in data.get("tasks") or [] for s in task.get("scope") or []]
    if cfg is not None and scope:
        risk = data.get("risk") or {}
        tracked = [p for p in gitutil.run(["ls-files", "-z"], check=False).split("\0") if p]
        a = rules.assess_paths(
            cfg,
            scope,
            ctype=str(data.get("type") or "feat"),
            dimensions=list(risk.get("dimensions") or []),
            irreversible=risk.get("reversible") is False,
            tracked=tracked,
        )
        route = rules.summary(a, "the Spec's scope")
    head = "" if args.worktree else gitutil.rev_parse(args.ref)
    earlier = _earlier_spec_approval(str(data.get("id")), h)
    since = None
    if earlier:
        paths = [args.spec, *frozen]
        span = [earlier, head] if head else [earlier]
        since = {
            "commit": earlier,
            "stat": gitutil.run(["diff", "--stat", *span, "--", *paths], check=False).rstrip(),
            "diff": gitutil.run(["diff", "--no-color", "--no-ext-diff", *span, "--", *paths], check=False),
        }
    page = views.spec_page(text, args.spec, line, files=files, spec_hash=h, commit=head or "the working tree", route=route, since=since)
    out = views.write(args.out or views.default_path("spec", str(data.get("id") or Path(args.spec).stem)), page)
    print(f"wrote {_repo_relative(out)}", file=sys.stderr)


def _config_or_none_quiet() -> cfgmod.Config | None:
    try:
        return _config_or_none()
    except (cfgmod.ConfigError, model.ModelError, OSError):
        return None


def _earlier_spec_approval(spec_id: str, h: str) -> str | None:
    """The commit the newest recorded approval of another hash of this Spec names (local approvals), or None."""
    from . import local

    try:
        _, comments, _ = local.load(".")
    except (gitutil.GitError, OSError, ValueError):
        return None
    earlier = [m.group(3) for c in comments for m in gates.APPROVE_SPEC.finditer(c["body"]) if m.group(1) == spec_id and m.group(2) != h and m.group(3)]
    return earlier[-1] if earlier else None


def cmd_explore(args) -> int:
    """An exploration's comparison page (`aidd new exploration` writes the exploration)."""
    from . import explore, views

    _enter_repo(args, "folder", file_attrs=("out",))
    folder = Path(args.folder)
    target = Path(args.out) if args.out else views.default_path("explore", folder.name)
    views.write(target, explore.comparison_page(folder))
    print(f"wrote {_repo_relative(target)}")
    return 0


def cmd_approve(args) -> int:
    """Record a person's approval on this machine, with no platform: a Spec approval or a Merge approval (local.py)."""
    from . import local

    _enter_repo(args, "spec", file_attrs=("evidence",))
    try:
        if args.what == "spec":
            if not args.spec:
                print("error: name the Spec: aidd approve spec specs/<ID>.md", file=sys.stderr)
                return 2
            text = gitutil.show("HEAD", args.spec)
            if text is None and not Path(args.spec).is_file():
                print(f"error: no such Spec: {args.spec}", file=sys.stderr)
                return 2  # a usage error, like a missing argument
            if text is None:
                print(f"error: {args.spec} is not committed; commit the Spec and its tests first", file=sys.stderr)
                return 1  # a failed check: the Spec exists, but not in HEAD
            data, _ = model.split_front_matter(text, args.spec)
            if gitutil.run(["status", "--porcelain", "--", args.spec, *model.frozen_paths(data)], check=False).strip():
                print("error: the Spec or its tests have uncommitted changes; approve what is committed", file=sys.stderr)
                return 1
            head = gitutil.rev_parse("HEAD")
            h = model.spec_hash(text, gitutil.ls_tree("HEAD"))
            command = f"aidd approve spec {args.spec}"
            local.check_terminal(f"Spec approval for {data.get('id')}", command)
            if problem := _local_identity_problem():
                print(f"error: {problem}", file=sys.stderr)
                return 1
            _before_spec_approval(args, data, h, head)
            ids = repo.acceptance_ids(text)
            print(f"Spec {data.get('id')}: {data.get('title')}")
            print(f"Acceptance: {len(ids)} item{'' if len(ids) == 1 else 's'}" + (f" ({', '.join(ids)})" if ids else ""))
            print(f"hash {h}: the Spec and its {len(model.frozen_paths(data))} frozen file pattern(s), at commit {head[:12]}")
            line = local.approve_spec_line(str(data.get("id")), h, head)
            local.require_person(f"Spec approval for {data.get('id')}: its Spec and tests at {head[:12]}", command=command)
        else:
            head = gitutil.rev_parse("HEAD")
            local.check_terminal(f"Merge approval for the head commit {head[:12]}", "aidd approve merge")
            if problem := _local_identity_problem():
                print(f"error: {problem}", file=sys.stderr)
                return 1
            if not _before_merge_approval(args, head):
                return 1
            branch = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
            line = local.approve_merge_line(head, branch=branch, skip_cooloff=args.skip_cooloff)
            local.require_person(f"Merge approval for the head commit {head[:12]}", command="aidd approve merge")
        sha, signed = local.record(line)
    except local.NotAPerson as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {'a signed' if signed else 'an unsigned'} approval ({sha[:12]} on {local.APPROVALS_REF})")
    if not signed:
        print("set up git commit signing with a key that asks for your presence, so an approval cannot be written without you")
    return 0


def _local_identity_problem() -> str | None:
    """Locally, an approval counts as `email:<git user.email>`: why the person at this terminal could never approve here,
    or None. Only where the local gate is the gate: a preflight's approvals come from the platform."""
    if localctx.platform_of(".") != "local":
        return None
    cfg = _config_or_none()
    if cfg is None:
        return None
    email = gitutil.config_value("user.email")
    who = f"email:{email}" if email else ""
    if who and norm(who) in {norm(a) for a in cfg.approvers}:
        return None
    return (
        f"the local gate counts an approval from this machine as {who or 'nobody: git user.email is not set'}, and owners.approvers lists "
        f'{", ".join(cfg.approvers) or "nobody"}, so it would never count. Add "{who or "email:you@example.com"}" to owners.approvers in '
        f"{cfgmod.CONFIG_PATH}, and commit it yourself on the base branch. Only a person may land that commit, never an agent. "
        "Then run this again"
    )


def _base_sha(args) -> str | None:
    """Where HEAD meets the base branch (`--base`, else the default branch), or None when there is none to find."""
    try:
        base = getattr(args, "base", None) or inputs.default_base()
        return gitutil.merge_base(gitutil.rev_parse(base), gitutil.rev_parse("HEAD"))
    except gitutil.GitError:
        return None


def _before_spec_approval(args, data: dict, h: str, head: str) -> None:
    """What the person should see before a Spec approval: whether HEAD already holds implementation (then the approval
    proves it came late), and what changed in the frozen files since the last approval of another hash."""

    frozen = [args.spec, *model.frozen_paths(data)]
    base_sha = _base_sha(args)
    if base_sha:
        changed = [p for p in gitutil.run(["diff", "--name-only", "-z", base_sha, head]).split("\0") if p]
        beyond = [p for p in changed if not globs.match_any(frozen, p)]
        if beyond:
            print(
                f"warning: HEAD already holds implementation ({', '.join(beyond[:5])}{' ...' if len(beyond) > 5 else ''}), so this approval "
                "records that Spec approval came after implementation began. Approve on the commit that holds only the Spec and its tests",
                file=sys.stderr,
            )
    earlier = _earlier_spec_approval(str(data.get("id")), h)
    if earlier:
        print(f"the frozen files changed since the last Spec approval ({earlier[:12]}):")
        print(gitutil.run(["diff", "--stat", earlier, head, "--", *frozen], check=False).rstrip() or "  (no change in the frozen files)")


def _before_merge_approval(args, head: str) -> bool:
    """What the person reads before a Merge approval: the digest, the diffstat, and the gate's state. False (refuse) when a
    rule other than merge_approval fails: approving a head the gate fails for anything else approves nothing useful."""
    from . import digest

    evidence = Path(getattr(args, "evidence", None) or "aidd-evidence/evidence.json")
    ctx = localctx.build(base=getattr(args, "base", None), head=head, evidence=str(evidence) if evidence.is_file() else None, run_policy=True)
    d = verify(ctx)
    print(digest.merge_digest(ctx, cwd=".").strip())
    print(gitutil.run(["diff", "--stat", ctx["base_sha"], head], check=False).rstrip())
    print(report.text(d))
    failing = sorted({f.rule for f in d.findings if f.level == "fail" and f.rule != "merge_approval"})
    if failing:
        print(
            f"error: not approved: the gate fails on {', '.join(failing)} for head {head[:12]}. Fix that first, then run `aidd approve merge` again",
            file=sys.stderr,
        )
        return False
    return True


# What the change declares, which `aidd ship` checks before it runs any test: a failure here stays a failure whatever the
# tests say, so the person learns it in seconds rather than after the suite.
DECLARED_RULES = ("config", "change_request", "spec", "confidence", "route", "scope", "budget", "standard_change")


def cmd_ship(args) -> int:
    """Merge a branch that passes the gate into the base branch, on this machine: the local-first Ship.

    The declared inputs are checked first; then the tests run on exactly what will land (the head, or, when the base
    branch moved, the head merged into the base tip, in a temporary worktree); then the person confirms once, with one
    code, which also records their Merge approval when that is all the gate still waits for."""
    from . import local

    _enter_repo(args, file_attrs=("out", "body_file"))
    branch = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    base = args.base or inputs.default_base(".").removeprefix("origin/")
    if branch in (base, "HEAD"):
        print(f"error: switch to the branch to ship; this is {branch}", file=sys.stderr)
        return 2
    if gitutil.run(["status", "--porcelain", "--untracked-files=no"]).strip():
        print("error: the working tree has uncommitted changes; commit or stash them first", file=sys.stderr)
        return 1
    head = gitutil.rev_parse("HEAD")
    body = _body(args) if args.body_file else None
    early = verify(localctx.build(base=base, head=head, body=body, run_policy=False))
    declared = [f for f in early.findings if f.level == "fail" and f.rule in DECLARED_RULES]
    if declared:
        for f in declared:
            print(f"  [FAIL] {f.rule}: {f.message}" + (f"\n        fix: {f.fix}" if f.fix else ""))
        print("Not shipped: the change's declaration fails, so no test ran; fix it and run `aidd ship` again", file=sys.stderr)
        return 1
    base_tip = gitutil.rev_parse(base)
    merged: tuple[str, str] | None = None  # (the merge commit tested, its tree) when the base moved
    try:
        if gitutil.ok(["merge-base", "--is-ancestor", base_tip, head]):
            # The tests run here, on this exact head: evidence on disk is a file an agent could have written.
            ev, notes = runner.run_tests(base=base, body=body, out_dir=args.out, pass_env=args.pass_env or ())
        else:
            merged = local.merged_commit(base_tip, head, message=args.message or _ship_message(early.record, branch, head))
            print(f"{base} moved to {base_tip[:12]}: testing {head[:12]} merged into it ({merged[0][:12]}), which is what will land")
            ev, notes = local.run_in_worktree(
                merged[0], lambda tmp: runner.run_tests(repo=tmp, base=base_tip, body=body, out_dir=args.out, pass_env=args.pass_env or ())
            )
    except (RuntimeError, gitutil.GitError) as exc:
        print(f"Not shipped: {exc}", file=sys.stderr)
        return 1
    for n in notes:
        print(f"note: {n}")
    ctx = localctx.build(base=base, head=head, body=body, run_policy=True)
    if gitutil.rev_parse("HEAD") != head or gitutil.rev_parse(base) != base_tip or ev["head_sha"] != (merged[0] if merged else head):
        print(f"Not shipped: {branch} or {base} moved while the tests ran; run `aidd ship` again", file=sys.stderr)
        return 1
    if merged:
        # The tested commit is the head merged into the base tip: the gate checks it as it checks a merge-queue entry.
        ctx["merge_group"] = {"sha": merged[0], "base_sha": base_tip, "stacked": False, "tree": merged[1], "merged_tree": merged[1]}
    ctx["evidence"] = ev
    d = verify(ctx)
    approve = (
        d.decision != "pass" and _only_merge_approval_missing(d) and verify(_with_own_approval(ctx, local, skip_cooloff=args.skip_cooloff)).decision == "pass"
    )
    if d.decision != "pass" and not approve:
        state = "fails" if d.decision == "fail" else "is pending"
        print(f"Not shipped: the local gate {state} (details below)", file=sys.stderr, flush=True)
        print(report.text(d))
        if _only_merge_approval_missing(d) and (problem := _local_identity_problem()):
            print(f"note: {problem}")
        return 1
    print(report.text(d))
    # What lands, for the person to read before the code: the diffstat against the base.
    print(gitutil.run(["diff", "--stat", ctx["base_sha"], head], check=False).rstrip())
    what = f"Ship {branch} at {head[:12]} into {base}" + (" as one squashed commit" if args.squash else "")
    try:
        local.require_person(
            f"{what}, recording the Merge approval of {head[:12]}" if approve else what, command="aidd ship" + (" --squash" if args.squash else "")
        )
        if approve:
            local.record(local.approve_merge_line(head, branch=branch, skip_cooloff=args.skip_cooloff))
            reviews, comments, notes = local.load(
                ".",
                require_signed=bool(d.config and d.config.gates.get("local_approvals") == "signed"),
                signers=local.base_signers(d.config, base_tip),
                signers_file=local.signers_path(d.config),
            )
            ctx.update(reviews=localctx.this_branchs(".", reviews, base_tip, head), comments=comments, notes=notes)
            d = verify(ctx)
            if d.decision != "pass":
                print(report.text(d))
                print("Not shipped: the Merge approval was recorded, but the gate still does not pass", file=sys.stderr)
                return 1
        message = args.message or _ship_message(ctx, branch, head)
        new = local.ship(branch, base, squash=args.squash, message=message, head=head, merged=merged, base_tip=base_tip)
    except (local.NotAPerson, RuntimeError, gitutil.GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"shipped {branch} at {head[:12]} into {base} at {new[:12]}" + (" (the tested merge with the moved base)" if merged else ""))
    return 0


def _only_merge_approval_missing(d) -> bool:
    """Whether the gate waits for nothing but Merge approval: every finding that is not a warning is merge_approval's."""
    blocking = [f for f in d.findings if f.level != "warn"]
    return bool(blocking) and all(f.rule == "merge_approval" and f.level == "pending" for f in blocking)


def _with_own_approval(ctx: dict, local, *, skip_cooloff: bool = False) -> dict:
    """The context as it would be once the person running `aidd ship` approves the head: would their approval be enough?"""
    email = gitutil.config_value("user.email")
    review = {
        "user": f"email:{email}" if email else "local",
        "state": "approved",
        "commit_sha": ctx["head_sha"],
        "submitted_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "verified": local.signing("."),
    }
    if skip_cooloff:
        review["cooloff_skipped"] = True
    return {**ctx, "reviews": [*ctx["reviews"], review]}


def _ship_message(ctx_or_record: dict, branch: str, head: str | None = None) -> str:
    """The Spec's title and id when the branch carries one Spec; else the newest commit's subject that is not a Change Request block
    commit (commits are newest first)."""
    ctx = ctx_or_record
    body = (ctx.get("change") or {}).get("body") if isinstance(ctx.get("change"), dict) else None
    spec = ctx.get("spec") if body is None else (model.parse_change_block(body or "")[0] or {}).get("spec")
    head = head or ctx.get("head_sha")
    text = gitutil.show(head, spec) if spec and head else None
    if text:
        try:
            data, _ = model.split_front_matter(text, str(spec))
        except model.ModelError:
            data = {}
        if data.get("title"):
            return f"{data['title']} ({data.get('id', branch)})"
    commits = ctx.get("commits")
    if commits is None and head:
        base_sha = ctx.get("base_sha")
        commits = gitutil.commits(base_sha, head) if base_sha else []
    plain = [c for c in commits or [] if c.get("message", "").strip() and model.parse_change_block(c["message"]) == (None, [])]
    subject = next((c["message"].splitlines()[0] for c in plain[:1]), "")
    return subject or f"Ship {branch}"


_CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\([^)\n]*\))?!?:\s")


def conventional_type(subjects: list[str]) -> str | None:
    """The change type the newest Conventional Commit subject names (`fix(cart)!: ...` is fix), when it is one aidd knows."""
    for s in subjects:
        m = _CONVENTIONAL.match(s)
        if m and m["type"] in TYPES:
            return m["type"]
    return None


def cmd_describe(args) -> int:
    """Print a starting Change Request block for the current branch; with --commit, record it in an empty commit instead."""
    _enter_repo(args)
    cfg = cfgmod.load_file(cfgmod.CONFIG_PATH)
    base = args.base or inputs.default_base()
    base_sha = gitutil.merge_base(gitutil.rev_parse(base), gitutil.rev_parse("HEAD"))
    files = gitutil.numstat(base_sha, "HEAD")
    if not files:
        raise ValueError(f"no changes between {base} and HEAD")
    paths = rules.changed_paths(files)
    commits = gitutil.commits(base_sha, "HEAD")
    subjects = [c["message"].splitlines()[0] for c in commits if c.get("message", "").strip()]
    ctype = args.type or conventional_type(subjects) or ("docs" if all(p.endswith((".md", ".rst", ".txt")) for p in paths) else "feat")
    a = rules.assess(
        paths=paths,
        cfg=cfg,
        ctype=ctype,
        risk={"dimensions": [], "reversible": True},
        confidence="high",
        task_count=1,
        changed_lines=sum(f["additions"] + f["deletions"] for f in files),
        binary_files=rules.counted_binaries(files, cfg),
        dependencies=inputs.dependencies_added(".", base_sha, "HEAD", files),
        binary_paths=rules.binary_paths(files),
    )
    bots = {b.lower() for b in cfg.get("identities", "bots", default=[])}
    assisted = sorted(
        {m.strip() for c in commits for m in TRAILER.findall(c["message"]) if m.strip().lower() != "none"}
        | {x for c in commits for x in agent_coauthors(c["message"], bots)}
    )
    spec = localctx.find_spec_in_diff(files, cfg.specs_dir, lambda p: gitutil.show("HEAD", p))
    if spec:
        block = f"```toml aidd\nspec = {json.dumps(spec)}\n```"
    elif a.required_route in ("normal", "major"):
        print(f"# The diff's minimum route is {a.required_route} ({a.lane} lane), because:")
        for line in rules.reason_lines(a):
            print(f"#   - {line}")
        print("# That needs a Spec:")
        print(f'#   aidd new spec <ID> --title "..." --type {ctype} --paths {" ".join(paths[:5])}{" ..." if len(paths) > 5 else ""}')
        print("# then put this block in the PR/MR description" + (" (or run `aidd describe --commit` once the Spec is committed)" if args.commit else "") + ":")
        print('```toml aidd\nspec = "specs/<ID>.md"\n```')
        return 1 if args.commit else 0
    else:
        block = "\n".join(
            [
                "```toml aidd",
                f'route = "{a.required_route}"',
                f'type = "{ctype}"',
                f"scope = {json.dumps(paths)}",
                f"assisted_by = {json.dumps(assisted)}",
                "```",
            ]
        )
    if not args.commit:
        print(f"# The diff's minimum route is {a.required_route} ({a.lane} lane), because:")
        for line in rules.reason_lines(a):
            print(f"#   - {line}")
        print(block)
        return 0
    # Local-first, with no PR/MR description: the block lives in an empty commit on the branch, where `aidd test`,
    # `aidd gate`, and `aidd ship` read it (the newest one wins). The trailers declare who wrote the branch, as the block does.
    trailers = "\n".join(f"Assisted-by: {x}" for x in assisted) or "Assisted-by: none"
    message = f"chore: aidd change request ({'spec' if spec else a.required_route})\n\n{block}\n\n{trailers}\n"
    gitutil.run(["commit", "--allow-empty", "-q", "-F", "-"], input=message)
    print(block)
    print(f"recorded the block in commit {gitutil.rev_parse('HEAD')[:12]}; `aidd test`, `aidd gate`, and `aidd ship` read it from there")
    return 0


def cmd_test(args) -> int:
    _enter_repo(args, "spec", file_attrs=("body_file", "out", "html"))
    if args.merge_group:
        args.base = _merge_group_base(args.base)
    changed = args.changed or args.watch

    def once() -> int:
        ev, notes = runner.run_tests(
            base=args.base,
            spec=args.spec,
            body=_body(args) if args.body_file else None,
            out_dir=args.out,
            red=not args.no_red,
            red_in_place=args.red_in_place,
            pass_env=args.pass_env or (),
            changed=changed,
        )
        return _print_test_results(ev, notes, args.out)

    if not args.watch:
        return once()
    out = Path(args.out).resolve()
    exclude = out.relative_to(Path.cwd().resolve()).as_posix() if out.is_relative_to(Path.cwd().resolve()) else None

    def announce() -> None:
        print(f"\n--- {dt.datetime.now():%H:%M:%S} aidd test --changed ---")
        try:
            once()
        except (ValueError, OSError, LookupError, gitutil.GitError, RuntimeError) as exc:
            print(f"aidd: {exc}", file=sys.stderr)  # keep watching: the next save may fix it
        print(f"watching for changes every {args.interval:g}s; Ctrl-C to stop")

    return runner.watch(announce, interval=args.interval, exclude=exclude)


def _merge_group_base(base: str | None) -> str:
    """In a merge_group run: the commit the queue entry was built on, computed as the gate computes it."""
    from . import github

    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise ValueError("--merge-group reads the merge_group event from GITHUB_EVENT_PATH; run it in a merge_group workflow")
    group = github.merge_group_of(json.loads(Path(path).read_text(encoding="utf-8")))
    if group is None:
        raise ValueError("--merge-group: this event is not a merge_group event")
    head = gitutil.rev_parse("HEAD")
    if head != group.sha:
        raise ValueError(f"--merge-group: the checkout is {head[:12]}, not the merge-group commit {group.sha[:12]}")
    parent, stacked = github.queue_parent(".", head, group.named_parent, gitutil.rev_parse(base or f"origin/{group.base_ref}"))
    print(f"merge queue: pull request #{group.number}, built on {parent[:12]}" + (" (a previous queue entry)" if stacked else ""))
    return parent


def _print_test_results(ev: dict, notes: list[str], out: str) -> int:
    """Each result, then the notes and where the evidence is. Exit 1 when a result is bad, except in the Spec phase,
    where a failing green run is expected before Implement (marked `..`) and the red runs are early proof."""
    bad = False
    spec_phase = bool(ev.get("spec_phase"))
    for r in ev["results"]:
        good = (r["red_green"] == "green" and r["status"] == "passed") or (r["red_green"] == "red" and red_ok(r))
        expected = not good and spec_phase and r["red_green"] == "green"
        bad |= not good and not expected
        mark = "ok" if good else ".." if expected else "!!"
        flaky = f" after {len(r['attempts'])} attempts (flaky)" if r.get("flaky") else ""
        print(f"[{mark}] {r['red_green']:5} {r['name']}: {r['status']} (exit {r['exit']}){flaky} log {_repo_relative(Path(out) / r.get('log', ''))}")
    for n in notes:
        print(f"note: {n}")
    partial = " (partial: the gate does not accept it)" if ev.get("partial") else ""
    print(f"evidence: {_repo_relative(Path(out) / 'evidence.json')}  head {ev['head_sha'][:12]}  base {ev['base_sha'][:12]}{partial}")
    return 1 if bad else 0


def cmd_gate(args) -> int:
    if args.explain:
        from . import rulebook

        print(rulebook.explain(args.explain))
        return 0
    if args.platform == "github":
        from . import github

        return github.gate(
            dry_run=args.dry_run, events_out=args.events, record_out=args.record, resolve_only=args.resolve, mode=args.mode, html_out=_html_arg(args.html)
        )
    if args.platform == "gitlab":
        from . import gitlab

        return gitlab.gate(
            dry_run=args.dry_run,
            evidence_path=args.evidence,
            events_out=args.events,
            record_out=args.record,
            pending_fails=not args.pending_ok,
            post=args.post_status,
            mode=args.mode,
            html_out=_html_arg(args.html),
        )
    if args.context:
        ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
    else:
        _enter_repo(args, "spec", file_attrs=("body_file", "approvals", "evidence", "record", "events", "html"))
        ctx = localctx.build(base=args.base, body=_body(args), approvals=args.approvals, evidence=args.evidence, run_policy=not args.no_policy)
    d = verify(ctx)
    if args.html is not None:
        _merge_view(args, ctx, d)
    if args.record:
        from . import changerecord

        Path(args.record).write_text(json.dumps(d.record, indent=2) + "\n", encoding="utf-8")
        # The agent change record: an in-toto statement of this decision, next to the gate record.
        changerecord.write(d, ctx if isinstance(ctx, dict) else {}, args.record)
    if args.events:
        with open(args.events, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.event(d, ctx.get("repo") if isinstance(ctx, dict) else None)) + "\n")
    if args.json:
        # The decision record, as `--record` writes it, for a script: nothing else goes to stdout.
        print(json.dumps({"schema_version": JSON_SCHEMA_VERSION} | d.record, indent=2))
        return EXIT[d.decision]
    print(report.markdown(d) if args.markdown else report.text(d))
    if not args.markdown and not args.context:
        # Locally, the diff a stale Spec approval's fix names, so the Approver sees what changed before approving again.
        for f in d.findings:
            _, sep, cmd = f.fix.partition("what changed since the last approval: git ")
            if f.code == "spec_approval.missing" and sep:
                stat = gitutil.run(split_command(cmd.splitlines()[0]), check=False).rstrip()
                print(
                    "  what changed in the frozen files since the last Spec approval:\n" + "\n".join(f"    {ln}" for ln in stat.splitlines() or ["(nothing)"])
                )
    if not args.markdown and not args.context and d.record.get("required_route"):
        # Locally, the route the gate computed from the real diff, and why: the entry check, repeated.
        print(f"  computed route {d.record['required_route']} ({rules.LANES.get(d.record['required_route'], '?')} lane) from the diff, because:")
        for line in rules.reason_lines({"reasons": d.record.get("route_reasons") or []}):
            print(f"    - {line}")
    return EXIT[d.decision]


def _html_arg(value: str | None) -> str | None:
    """`--html` alone means the default page path (""); absent means no page (None). A given PATH is made absolute."""
    return None if value is None else str(Path(value).resolve()) if value else ""


def _merge_view(args, ctx: dict, d) -> None:
    """The Merge approval page, beside the gate's report. A view for people: whatever goes wrong here is a warning, and
    the decision (already made) and the exit code stay as they are."""
    from . import digest, views

    try:
        head = str(ctx.get("head_sha") or "")
        in_repo = not args.context
        evidence = Path(args.evidence) if in_repo and args.evidence else None
        evidence_dir = evidence.parent if evidence is not None and evidence.is_file() else None
        review = views.review_file(evidence.parent / "review.md") if evidence is not None else None
        since = digest._since_last_approval(ctx, "." if in_repo else None) if isinstance(ctx.get("reviews"), list) else ""
        page = views.merge_page(ctx, d, diffs=views.diffs(ctx, ".") if in_repo else {}, review=review, evidence_dir=evidence_dir, since=since)
        out = views.write(args.html or views.default_path("merge", head[:12] or "change"), page)
        print(f"wrote {_repo_relative(out)}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, gitutil.GitError) as exc:
        print(f"warning: the Merge approval page was not written: {exc}", file=sys.stderr)


def cmd_observe(args) -> int:
    """Run a Spec's observe command once, or poll it for the window (--window); --write records outcome.observe_result.
    Never rolls back. With --band METRIC, judge a metric series against its control band instead (`_observe_band`)."""
    if args.band:
        if args.window is not None:
            raise ValueError("--window polls a Spec's observe command; with --band, --baseline sets how many values make the baseline")
        return _observe_band(args, metric=args.band, series_arg=args.target, baseline=args.baseline)
    if args.baseline is not None or args.json or args.diagnose_sigma or args.propose_sigma:
        raise ValueError("--baseline, --diagnose-sigma, --propose-sigma, and --json judge a metric: use them with --band METRIC")
    if args.write not in (None, "auto"):
        raise ValueError(f"--write {args.write}: a Spec id names the draft Spec a band breach writes; use it with --band METRIC")
    args.spec = args.target
    _enter_repo(args, "spec")
    path = Path(args.spec)
    text = path.read_text(encoding="utf-8")
    data, _ = model.split_front_matter(text, args.spec)
    obs = data.get("observe")
    if not obs:
        raise ValueError(f"{args.spec} has no observe block")
    cfg = _config_or_none()
    command = obs.get("command") or (cfg.observe_command if cfg else None)
    print(f"window: {obs['window']}  rollback trigger: {obs['rollback_trigger']}")
    if obs.get("signals"):
        print(f"signals: {obs['signals']}")
    if not command:
        print("no observe command: a human watches the signals for the window")
        if args.window:
            print("error: --window polls the observe command; set observe.command in the Spec or the config", file=sys.stderr)
            return 2
        return 0
    from .util import run_bounded, scrub_credentials

    # The command may come from the Spec, which the change wrote, and runs where release credentials
    # live: it sees none of them unless the operator passes one by name.
    env = {
        **scrub_credentials(dict(os.environ), keep=args.pass_env or ()),
        "AIDD_SPEC_ID": str(data.get("id")),
        "AIDD_WINDOW": obs["window"],
        "AIDD_ROLLBACK_TRIGGER": obs["rollback_trigger"],
    }

    def check() -> int | None:
        # A timeout kills the command's whole process group, so a watcher it started cannot linger.
        code, _, _ = run_bounded(command, env=env, timeout=args.timeout, capture=False)
        return code

    if args.window:
        from . import observe

        length = obs["window"] if args.window == "spec" else args.window
        window_s, every_s = observe.seconds(length), observe.seconds(args.every)
        print(f"watching for {length}: the observe command every {args.every}; the trigger fires after {args.consecutive} failed check(s) in a row")
        # A check that timed out counts as unhealthy (124, as timeout(1) reports it).
        w = observe.watch_window(lambda: 124 if (c := check()) is None else c, window_s=window_s, every_s=every_s, consecutive=args.consecutive)
        result = w.result
        if result == "pass":
            print(f"observe: pass: the {length} window ended after {w.checks} check(s), {w.failures} unhealthy; the rollback trigger never fired")
        else:
            print(f"observe: ROLLBACK TRIGGER FIRED after {w.checks} check(s): {obs['rollback_trigger']}")
            print("aidd never rolls back: run your rollback now, then record it (outcome.rolled_back) and go to Learn")
    else:
        code = check()
        result = "pass" if code == 0 else "fail"
        print(f"observe: {result} (exit {code})" + ("" if result == "pass" else f"; if this persists, roll back: {obs['rollback_trigger']}"))
    if args.write:
        path.write_text(model.set_outcome(text, "observe_result", result), encoding="utf-8")
        print(f"wrote outcome.observe_result = {result!r} to {path}")
    return 0 if result == "pass" else 1


def _observe_band(args, *, metric: str, series_arg: str, baseline: int | None) -> int:
    """Judge a metric series against its control band; with --write, turn a breach into a draft Spec to triage."""
    from . import bands

    series = Path(series_arg).resolve()
    _enter_repo(args)
    band = bands.band_from_config(_config_or_none(), metric)
    band = bands.Band(
        band.metric,
        baseline or band.window,
        args.diagnose_sigma or band.diagnose_sigma,
        args.propose_sigma or band.propose_sigma,
    )
    reading = bands.assess(bands.load_series(series), band)
    breach = reading.tier in ("diagnose", "propose")
    written = None
    if breach and args.write:
        cfg = _config_or_none()
        spec_id = args.write if args.write not in ("auto", True) else f"OBS-{metric}-{dt.date.today():%Y%m%d}".replace("_", "-")
        written = repo.new_object(
            Path("."),
            kind="spec",
            id=spec_id,
            title=f"{metric} breached its control band ({reading.tier})",
            route="normal",
            ctype="fix",
            owner_team=(cfg.get("owners", "default_team", default="") if cfg else ""),
            specs_dir=cfg.specs_dir if cfg else "specs",
        )
        # A breach is work nobody asked for: an agent suggests it (the SRE when it may), and a person triages it.
        from .owners import proactive_roles

        may = proactive_roles(cfg)
        role = "sre" if "sre" in may or not may else may[0]
        text = written.read_text(encoding="utf-8").replace('kind = "spec"\n', f'kind = "spec"\nsuggested_by = "agent:{role}"\n', 1)
        head, sep, body = text.partition("\n+++\n")
        written.write_text(head + sep + "\n" + bands.intent_text(reading, series.name, cfg.get("goal") if cfg else None) + body, encoding="utf-8")
    if args.json:
        print(json.dumps({"schema_version": JSON_SCHEMA_VERSION} | reading.as_dict() | {"spec": str(written) if written else None}, indent=2))
    else:
        print(f"{reading.metric}: {reading.tier}" + (f" ({reading.note})" if reading.note else f", {reading.sigma} sigma"))
        for rule in reading.rules:
            print(f"  rule {rule}")
        if written:
            print(f"wrote {written}: a draft Spec for the service owner to triage")
    return 1 if breach else 0


def cmd_proposal(args) -> int:
    """Render a proposal's tables, or turn an accepted proposal into an Initiative and Epics."""
    from . import proposal

    given = args.file
    _enter_repo(args, file_attrs=("file",))
    try:
        data = proposal.load(Path(args.file))
    except FileNotFoundError:
        print(f"aidd: {given}: no such file", file=sys.stderr)
        return 2
    except (model.ModelError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2  # bad input: a missing file, or one that is not a valid proposal
    if args.action == "matrix":
        print(proposal.matrix(data), end="")
        return 0
    cfg = _config_or_none()
    try:
        written = proposal.convert(data, Path(cfg.specs_dir if cfg else "specs"), cfg.get("owners", "default_team", default="") if cfg else "")
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote    {path.as_posix()}")
    print("next: the product manager ranks the Epics and writes Spec stubs under them (`/aidd-team:plan`)")
    return 0


def cmd_log(args) -> int:
    """One Spec's history: status transitions, approvals, and Assisted-by trailers."""
    from . import speclog

    records = [str(Path(r).resolve()) for r in args.record or []]  # before entering the root: relative to where it ran
    _enter_repo(args, *(("spec",) if args.spec.endswith(".md") else ()))
    log = speclog.build(Path("."), args.spec, records)
    print(json.dumps({"schema_version": JSON_SCHEMA_VERSION} | log, indent=2) if args.json else speclog.markdown(log), end="\n" if args.json else "")
    return 0


def _list_filters(args):
    from . import nextstep

    return nextstep.Filters(
        all=True, mine=args.mine, agent=args.agent, blocked=args.blocked, waiting_on_me=args.waiting_on_me, label=args.label, priority=args.priority
    )


def cmd_assess(args) -> int:
    """This change: its route (the higher of what the diff needs and what the change declares), then its next steps,
    then the other branches it overlaps; with --paths, the route planned paths need before any code exists."""
    from . import nextstep

    if not args.paths and (args.type or args.dimension or args.irreversible):
        raise ValueError("--type, --dimension, and --irreversible describe planned paths: use them with --paths")
    _enter_repo(args)
    answer = nextstep.assess(Path("."), paths=args.paths, ctype=args.type, dimensions=args.dimension or [], irreversible=args.irreversible)
    shown = {"schema_version": JSON_SCHEMA_VERSION} | answer
    print(json.dumps(shown, indent=2) if args.json else nextstep.assess_markdown(answer), end="\n" if args.json else "")
    return 0


def cmd_list(args) -> int:
    """All open work, from the base branch and every open branch, and who holds each step."""
    from . import nextstep

    if args.html is not None and args.repos:
        raise ValueError("--html renders one repository's decisions: run it in that repository, without REPO")
    if args.events and not args.upkeep:
        raise ValueError("--events goes with --upkeep: the gate events that name flaky tests")
    if args.upkeep:
        if args.repos or args.html is not None:
            raise ValueError("--upkeep lists one repository's upkeep: run it in that repository, without REPO or --html")
        from . import upkeep

        events = [str(Path(e).resolve()) for e in args.events or []]  # as given, before the move to the top
        _enter_repo(args)
        found = upkeep.items(Path("."), events=events)
        shown = {"schema_version": JSON_SCHEMA_VERSION, "items": found}
        print(json.dumps(shown, indent=2) if args.json else upkeep.markdown(found), end="\n" if args.json else "")
        return 0
    if not args.repos:
        _enter_repo(args, file_attrs=("html",))
        steps = nextstep.plan(Path("."), filters=_list_filters(args))
        if args.html is not None:
            from . import views

            title = "Decisions waiting on you" if args.waiting_on_me else "Open work"
            out = views.write(
                args.html or views.default_path("decisions", "waiting-on-me" if args.waiting_on_me else "list"), views.decision_page(steps, title)
            )
            print(f"wrote {_repo_relative(out)}", file=sys.stderr)
        shown = {"schema_version": JSON_SCHEMA_VERSION, "steps": steps}
        print(json.dumps(shown, indent=2) if args.json else nextstep.markdown(steps), end="" if not args.json else "\n")
        return 0
    # A project in several repositories: each one answers for itself, from its own root.
    everything: dict[str, list[dict]] = {}
    here = os.getcwd()
    for path in args.repos:
        top = gitutil.toplevel(path) if Path(path).is_dir() else ""
        if not top:
            everything[path] = [nextstep._step(f"{path} is not a git repository", nextstep.AUTHOR, "check the path")]
            continue
        os.chdir(top)
        try:
            everything[path] = nextstep.plan(Path(top), filters=_list_filters(args))
        finally:
            os.chdir(here)
    if args.json:
        print(json.dumps({"schema_version": JSON_SCHEMA_VERSION, "repos": everything}, indent=2))
    else:
        print("\n".join(f"## {path}\n\n{nextstep.markdown(steps)}" for path, steps in everything.items()), end="")
    return 0


def cmd_owners(args) -> int:
    """Who decides and who does the work: the humans who approve and every agent role, with the team's goal."""
    from . import owners

    _enter_repo(args)
    r = owners.build(_config_or_none(), changed=args.changed, root=Path("."))
    # The JSON carries the version of its shape (schemas/owners.schema.json), like `aidd metrics --json`.
    print(json.dumps({"schema_version": OWNERS_SCHEMA_VERSION} | r, indent=2) if args.json else owners.markdown(r))
    return 0


AUTOPILOT = "autopilot (experimental): runs the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide"


def _autopilot_limits():
    from . import autopilot

    return autopilot.Limits.of(_config_or_none_quiet())


def cmd_autopilot(args) -> int:
    """Autopilot (experimental): its lease and journal, kept in the git directory, and its next action."""
    from . import autopilot, nextstep
    from . import lease as leasemod

    _enter_repo(args)
    root = Path(".")
    if args.action == "start":
        held, what = leasemod.take(root, work=args.work, session_id=args.session, timebox=args.timebox or _autopilot_limits().timebox)
        print(what)
        print(f"session: {held['session_id']}")
        return 0
    if args.action == "next":
        action = autopilot.next_action(root, work=args.work, session=args.session, goal=args.goal)
        print(json.dumps(action, indent=2) if args.json else autopilot.markdown(action), end="\n" if args.json else "")
        return 0
    if args.action == "note":
        if (args.cost is None) != (args.currency is None):
            raise ValueError("--cost and --currency go together, such as --cost 0.42 --currency USD")
        cost = {"amount": args.cost, "currency": args.currency} if args.cost is not None else None
        leasemod.check_spend(args.tokens, cost)
        merged = None
        if leasemod.parse_note(args.text)[0] == "learn.retro":
            merged = autopilot.merged_count(nextstep.open_work(root)[1])
        entry = leasemod.note(root, args.text, session_id=args.session, spec=args.spec, tokens=args.tokens, cost=cost, merged=merged)
        print(f"noted {entry['code']} {entry['result']} for {entry.get('spec') or entry['work']}")
        return 0
    if args.action == "status":
        shown = leasemod.show(root)
        print(json.dumps(shown, indent=2) if args.json else leasemod.markdown(shown), end="\n" if args.json else "")
        return 0
    gone = leasemod.release(root, session_id=args.session)
    print(f"stopped autopilot on {gone['work']} (session {gone['session_id']})" if gone else "autopilot holds no lease")
    return 0


def cmd_context(args) -> int:
    """The minimal context pack for one step of a Spec (experimental)."""
    from . import contextpack

    raw = args.spec
    _enter_repo(args, "spec")
    if "/" not in raw and "\\" not in raw and not Path(args.spec).is_file():
        args.spec = raw  # an id, such as SPEC-1
    pack = contextpack.build(Path("."), args.spec, role=args.role, step=args.step)
    print(json.dumps(pack, indent=2) if args.json else contextpack.markdown(pack), end="\n" if args.json else "")
    return 0


def cmd_mcp(args) -> int:
    from . import mcp

    top = gitutil.toplevel()
    return mcp.serve(root=top or os.getcwd())


def cmd_hook(args) -> int:
    if args.event in ("pre-tool", "pre-edit"):
        from . import guard

        return guard.pre_tool_hook()
    from . import hooks

    with gitutil.system_only():  # the session hooks read git as the guard does
        return hooks.run(args.event)


def cmd_gen_docs(args) -> int:
    root = resources.repo_root()
    if root is None:
        raise RuntimeError("gen-docs maintains the aidd source repository; run it from a source checkout")
    stale = docs.gen_docs(root, check=args.check)
    for p in stale:
        print(("stale: " if args.check else "updated: ") + str(p.relative_to(root)))
    if args.check and stale:
        print("run `aidd gen-docs` and commit the result")
        return 1
    return 0


def cmd_eval(args) -> int:
    root = Path(args.root) if args.root else (resources.repo_root() or Path("."))
    if (args.online or args.strict) and args.suite != "standards":
        raise ValueError("--online and --strict go with the standards suite: aidd eval standards --online")
    if args.json and args.suite not in ("standards", "packs"):
        raise ValueError("--json prints `aidd eval standards --online` or `aidd eval packs`; the other suites print lines")
    if args.suite == "standards" and (args.strict or args.json) and not args.online:
        raise ValueError("--strict and --json read the online standards check: add --online")
    if args.suite == "report":
        if not args.paths:
            raise ValueError("report reads the JSON-lines files written with --record: aidd eval report evals-results.jsonl")
        print(evals.report([Path(x) for x in args.paths]))
        return 0
    if args.paths:
        raise ValueError(f"unexpected arguments {' '.join(args.paths)!r}: only `aidd eval report` takes files")
    if args.suite in ("examples", "standards", "packs") and (args.repeat != 1 or args.control or args.record or args.model_label):
        raise ValueError("--repeat, --control, --record, and --model-label measure an agent: use them with routing, roles, or tasks")
    if args.repeat < 1:
        raise ValueError("--repeat must be at least 1")
    if args.suite == "examples":
        if not (root / "examples").is_dir():
            raise RuntimeError(f"no examples/ under {root}; pass --root <aidd source checkout>")
        if args.materialize:
            n = evals.materialize(root, Path(args.materialize))
            print(f"wrote {n} resolved cases to {args.materialize}")
            return 0
        results = evals.run_examples(root)
        for r in results:
            print(f"[{'ok' if r['ok'] else '!!'}] {r['case']}: got {r['got']}" + ("" if r["ok"] else f" want {r['want']}"))
        return 0 if all(r["ok"] for r in results) else 1
    if args.suite == "standards" and args.online:
        from . import knowledge

        result = knowledge.check_online(
            knowledge.evidence_entries(), timeout=args.timeout, max_seconds=args.max_seconds, max_bytes=args.max_bytes, concurrency=args.concurrency
        )
        # The release feeds of the library's tools: a newer major than a standard's checked_version is flagged.
        result["releases"] = knowledge.check_releases(knowledge.release_entries(), timeout=args.timeout, max_seconds=args.max_seconds, max_bytes=args.max_bytes)
        print(json.dumps(result, indent=2) if args.json else knowledge.markdown(result), end="\n" if args.json else "")
        return knowledge.exit_code(result, args.strict)
    if args.suite == "standards":
        from . import knowledge

        today = dt.date.today()
        stale = evals.stale_standards(today, args.max_days)
        for s in stale:
            print(
                f"[!!] {s['where']}: {docs.standard_text(s)} {'checked' if s.get('checked') else 'reviewed'} {evals.dated(s)}, "
                f"{s['age_days']} days ago: {s['why']}"
            )
        entries = evals.standards()
        emerging = sum(1 for s in entries if s.get("maturity") == "emerging")
        cadence = f"within {args.max_days} days" if args.max_days is not None else "within their review cadence or by their review_due"
        print(f"{len(entries)} standards ({emerging} marked emerging); {len(stale)} not checked {cadence}")
        soon = evals.due_soon(today, 90)
        if soon:
            print(f"{len(soon)} entries come due for review within 90 days, the first on {soon[0]['due_on']} ({soon[0].get('id') or soon[0]['name']})")
        print(STANDARDS_BASIS)
        bad_stewards, unset = knowledge.steward_findings()
        for line in bad_stewards:
            print(f"[!!] {line}")
        if unset:
            noun = "pack or skill names" if len(unset) == 1 else "packs and skills name"
            print(
                f"warning: {len(unset)} {noun} no steward ({', '.join(s['kind'] + ':' + s['id'] for s in unset)}); "
                "set `steward` on the pack in schemas/roles.json, or `metadata.steward` in the skill's front matter"
            )
        bulk = evals.bulk_checked_dates()
        for day, count in bulk:
            print(
                f"[!!] {count} entries share the checked date {day} without evidence that confirms each one (a sentence from the page read). "
                f"One bulk edit is not {count} confirmations: re-check them per source, or mark a practice `reviewed`"
            )
        moved = evals.stale_id_citations()
        for s in moved:
            print(f"[!!] {s['id']}: cites {s['token']}, but {s['moved_by']} records {s['old']} moved to {s['new']}; cite the current ID")
        unsourced = evals.unsourced_standards()
        for s in unsourced:
            print(f"[!!] {s['id']}: names edition {s['edition']!r} but no source to check it against")
        unevidenced = evals.unevidenced_standards()
        for s in unevidenced:
            print(f"[!!] {s['id']}: checked {s['checked']} with no source and evidence; add what was read, or mark a practice `reviewed`")
        unpinned = evals.unpinned_extensions()
        for x in unpinned:
            print(f"[!!] {x['where']}: {x['name']} ({x['kind']}) has no {' and no '.join(x['missing'])}")
        from . import standards

        # The library of opinionated standards and stacks: the generic checks over every file (standards.library_problems).
        library = standards.library_problems(today=today)
        for line in library:
            print(f"[!!] library: {line}")
        print(
            f"{_count(len(standards.library()), 'library standard')} and {_count(len(standards.stacks()), 'stack')}; {len(library)} problem(s) in the library"
        )
        # Who checked each library standard (`checked_by`): an agent's check until a person reviews it.
        tiers = standards.trust_counts([s.meta for s in standards.library().values()])
        print(f"Library trust: {tiers[standards.TIER_AGENT]} {standards.TIER_AGENT}, {tiers[standards.TIER_PERSON]} {standards.TIER_PERSON}")
        ok = not (stale or bulk or moved or unsourced or unevidenced or unpinned or bad_stewards or library)
        return 0 if ok else 1
    if args.suite == "packs":
        sizes, found = packs.sizes_and_problems()
        listed = packs.descriptions()
        if args.json:
            report = {"schema_version": JSON_SCHEMA_VERSION, "sizes": sizes, "problems": found, "descriptions": listed}
            print(json.dumps(report, indent=2))
            return 1 if found else 0
        for p in found:
            print(f"[!!] {p['where']}: {p['problem']}")
        for kind in ("pack", "practice"):
            mine = [s for s in sizes if s["kind"] == kind]
            skill, refs = sum(s["tokens"] for s in mine), sum(sum(s["references"].values()) for s in mine)
            print(f"{len(mine)} {kind}s: about {skill} tokens in SKILL.md files and {refs} in references")
        longest = max(listed, key=lambda d: d["chars"], default={"name": "none", "chars": 0})
        print(
            f"{len(listed)} descriptions: {sum(d['chars'] for d in listed):,} characters in all "
            f"({sum(d['kind'] == 'skill' for d in listed)} skills, {sum(d['kind'] == 'command' for d in listed)} commands); "
            f"the longest is {longest['name']} ({longest['chars']})"
        )
        print(f"{len(found)} problem(s); {PACKS_BASIS}")
        return 1 if found else 0
    if not args.cmd:
        raise ValueError(f'--cmd is required for the {args.suite} suite, for example --cmd "claude -p"')
    words = split_command(args.cmd)
    if not words:
        raise ValueError("--cmd is empty")
    if shutil.which(words[0]) is None:
        raise RuntimeError(f"cannot run {words[0]!r}: not found on PATH")
    if args.suite == "tasks":
        return _eval_tasks(args)
    scenarios = Path(args.scenarios) if args.scenarios else root / "evals" / args.suite
    if not evals.load_scenarios(scenarios):
        raise RuntimeError(f"no scenarios in {scenarios}; pass --scenarios <dir> (they ship in the source repository)")
    if args.suite == "roles":
        return _measure(
            args,
            lambda material: evals.run_roles(scenarios, args.cmd, material=material),
            lambda r: f"{r['id']} ({r['role']})" + ("" if r["ok"] else ": " + "; ".join(r["misses"])),
            noun="scenario(s)",
            metric="passed",
            cases=scenarios,
            repo=resources.repo_root(),
        )
    return _measure(
        args,
        lambda material: evals.run_routing(scenarios, args.cmd, embed=not args.no_embed, material=material),
        lambda r: f"{r['id']}: want {r['want']}, got {r['got']}  {r['reason']}",
        noun="scenario(s)",
        metric="accuracy",
        options={"embed": not args.no_embed},
        cases=scenarios,
        repo=resources.repo_root(),
    )


def _eval_tasks(args) -> int:
    """Your own agent configuration on your own tasks: the repository is --root or the current directory, never aidd's source."""
    repo = Path(args.root or ".").resolve()
    scenarios = Path(args.scenarios) if args.scenarios else repo / "evals" / "tasks"
    tasks = evals.load_scenarios(scenarios) if scenarios.is_dir() else []
    if not tasks:
        template = resources.data_dir("templates") / "evals"
        raise RuntimeError(
            f"no tasks in {scenarios}; start from the template: mkdir -p {scenarios.parent} && cp -R {template}/tasks {scenarios} ({template}/README.md says how)"
        )
    return _measure(
        args,
        lambda material: evals.run_tasks(scenarios, args.cmd, repo=repo),
        lambda r: r["id"] + ("" if r["ok"] else ": " + "; ".join(r["misses"])),
        noun="task(s)",
        metric="passed",
        control=False,
        cases=scenarios,
        repo=repo,
    )


def _measure(args, run, detail, *, noun: str, metric: str, cases: Path, repo: Path | None, control: bool = True, options: dict | None = None) -> int:
    """Run an agent suite --repeat times (and again without the aidd material for --control), print it, record it, and gate on mean pass@1.

    `run(material)` is one trial of every scenario. The control only reports: it never decides the exit code. A record
    names the head of `repo`, the repository that holds the material (aidd's source checkout for routing and roles, None
    for an installed aidd; the measured repository for tasks), whether the hashed files differ from it, and the
    material hash of `cases`. All three are taken before the first trial.
    """
    embed = bool((options or {}).get("embed", True))
    material = evals.material_sha256(args.suite, cases, embed=embed) if args.record else None
    # A tasks run measures the repository's own configuration, HEAD plus its uncommitted tracked changes: any of them makes it dirty.
    files = evals.material_files(args.suite, cases, embed=embed)
    head, dirty = evals.repo_state(repo, files, all_tracked=args.suite == "tasks", ignore=Path(args.record)) if args.record else (None, None)
    k = args.repeat
    results = evals.measure(lambda: run(True), k)
    for r in results:
        mark = "ok" if r["pass_all"] else ("~~" if r["passed"] else "!!")
        print(f"[{mark}] {detail(r)}" + (f"  (passed {r['passed']}/{k})" if k > 1 else ""))
    stats = evals.summary(results)
    mean = stats["mean_pass_at_1"]
    if k == 1:
        print(f"{metric} {mean:.1%} over {len(results)} {noun}; threshold {args.min_accuracy:.0%}")
    else:
        print(
            f"mean pass@1 {mean:.1%} over {len(results)} {noun}, {k} trials each; pass^{k} {stats['pass_k_share']:.1%}; "
            f"threshold {args.min_accuracy:.0%} on mean pass@1"
        )
    judged = [r for r in results if r.get("judgment")]
    if judged:
        label = metric if k == 1 else "mean pass@1"
        print(f"judgment-only {label} {sum(r['pass_at_1'] for r in judged) / len(judged):.1%} over {len(judged)} scenario(s)")
    baseline = None
    if args.control and not control:
        print("control: not applicable to tasks; a task carries no instructions of its own, the repository's configuration is the agent's material")
    elif args.control:
        baseline = evals.measure(lambda: run(False), k)
        base = evals.summary(baseline)["mean_pass_at_1"]
        print(f"control without the aidd material: mean pass@1 {base:.1%}; lift {(mean - base) * 100:+.1f} points (reported, never gating)")
    if args.record:
        line = evals.record_line(
            suite=args.suite,
            cmd=args.cmd,
            model=args.model_label,
            repeat=k,
            results=results,
            threshold=args.min_accuracy,
            control=baseline,
            options=options,
            head=head,
            dirty=dirty,
            material=material,
            cases=evals.cases_path(cases),
        )
        evals.append_record(Path(args.record), line)
        print(f"recorded to {args.record}")
    return 0 if mean >= args.min_accuracy else 1


def cmd_metrics(args) -> int:
    if args.flaky and (args.autopilot or args.guard or args.target_wait is not None):
        raise ValueError("--flaky goes alone, not with --autopilot, --guard, or --target-wait")
    if args.autopilot:
        return _metrics_autopilot(args)
    if args.guard:
        if args.guard == GUARD_LOG_DEFAULT:
            # The hook keeps its log at the repository's top level, wherever this runs from.
            try:
                args.guard = str(Path(gitutil.toplevel(check=True)) / GUARD_LOG_DEFAULT)
            except (gitutil.GitError, OSError):
                pass
        counts = metrics.guard_denials(metrics.load([args.guard], since=args.since) if Path(args.guard).is_file() else [])
        print(json.dumps(counts, indent=2) if args.json else metrics.guard_markdown(counts, args.guard), end="\n" if args.json else "")
        return 0
    if not args.events:
        raise ValueError("metrics needs one or more event files, or --guard [PATH]")
    if args.suggest_standard_changes and not args.autonomy:
        raise ValueError("--suggest-standard-changes goes with --autonomy")
    if args.cost and (args.by or args.dora or args.autonomy):
        raise ValueError("--cost goes with the summary, not with --by, --dora, or --autonomy")
    if args.flaky and (args.by or args.dora or args.autonomy or args.cost or args.specs or args.render):
        raise ValueError("--flaky goes alone, not with --by, --dora, --autonomy, --cost, --specs, or --render")
    events = metrics.gate_events(metrics.load(args.events, since=args.since))
    if args.tenant:
        events = [e for e in events if e.get("tenant") == args.tenant]
    if args.flaky:
        out = metrics.flaky(events)
        print(json.dumps(out, indent=2) if args.json else metrics.flaky_markdown(out), end="\n" if args.json else "")
        return 0
    cfg = _config_or_none()
    targets = cfg.get("targets", default={}) if cfg else {}
    if args.by:
        groups = metrics.grouped(events, args.by, args.target_wait, targets)
        shown = {"schema_version": metrics.SCHEMA_VERSION, "by": args.by, "groups": groups}
        print(json.dumps(shown, indent=2) if args.json else metrics.markdown_grouped(groups, args.by))
        return 0
    if args.dora:
        rows = metrics.dora(events, Path(args.specs) if args.specs else None, targets)
        table = {"schema_version": metrics.SCHEMA_VERSION, "rows": rows}
        print(json.dumps(table, indent=2) if args.json else metrics.dora_markdown(rows), end="" if not args.json else "\n")
        return 1 if any(r["met"] is False for r in rows) else 0
    if args.autonomy:
        rows = metrics.autonomy(events, **(cfg.get("agents", "autonomy", default={}) if cfg else {}))
        if args.suggest_standard_changes:
            proposals = metrics.propose_standard_changes(events, rows, TYPES)
            out = {"schema_version": metrics.SCHEMA_VERSION, "proposals": proposals}
            print(json.dumps(out, indent=2) if args.json else metrics.proposals_text(proposals), end="\n" if args.json else "")
            return 0
        print(json.dumps({"schema_version": metrics.SCHEMA_VERSION, "rows": rows}, indent=2) if args.json else metrics.autonomy_markdown(rows))
        return 0
    s = metrics.summarize(events, args.target_wait, targets)
    if args.specs:
        s |= metrics.delivery_outcomes(Path(args.specs))
    if args.cost:
        cap = cfg.get("agents", "max_cost_per_change") if cfg else None
        s["cost"] = metrics.cost(events, metrics.load_ledger(args.cost, since=args.since), targets, s["first_pass_share"], cap)
        for o in s["cost"]["over_cap"]:  # a warning per change, never the exit code
            print(
                f"warning: change {o['change']} cost {o['amount']} {o['currency']}, over [agents] max_cost_per_change ({s['cost']['cap']['amount']} {s['cost']['cap']['currency']})",
                file=sys.stderr,
            )
    if args.render:
        renderers = ext.installed("aidd.renderers")
        if args.render not in renderers:
            raise ValueError(f"no renderer {args.render!r}; installed: {', '.join(sorted(renderers)) or 'none'}")
        print(renderers[args.render](s), end="")
    else:
        print(json.dumps(s, indent=2) if args.json else metrics.markdown(s))
    # A missed loop-speed target fails the run, like a DORA target; cost is display only and never sets the exit code.
    return 1 if any(r["met"] is False for r in s["loop_speed"]) else 0


def _metrics_autopilot(args) -> int:
    """`aidd metrics --autopilot` (experimental): the autopilot runs' own measures, from the run events in the
    git directory (and any event files given) and the guard's log."""
    from . import lease as leasemod

    if args.autonomy:
        raise ValueError("--autopilot goes without --autonomy: --autonomy is the stage of each agent, --autopilot the runs' measures")
    paths = list(args.events or [])
    try:
        top = Path(gitutil.toplevel(check=True))
        mine = leasemod.store(top) / leasemod.EVENTS_FILE
        if mine.is_file():
            paths.append(str(mine))
        guard = Path(args.guard) if args.guard else top / GUARD_LOG_DEFAULT
    except (gitutil.GitError, OSError, ValueError):
        guard = Path(args.guard) if args.guard else Path(GUARD_LOG_DEFAULT)
    events = metrics.load(paths, since=args.since) if paths else []
    denials = metrics.load([str(guard)], since=args.since) if guard.is_file() else []
    out = metrics.runs(events, denials)
    print(json.dumps(out, indent=2) if args.json else metrics.runs_markdown(out), end="\n" if args.json else "")
    return 0


def cmd_export(args) -> int:
    """Gate records or events as JSON or CSV (or an installed exporter's format), the same bytes for the same inputs."""
    from . import export

    if args.by_control:
        if args.kind != "records" or args.format != "json" or args.since or args.tenant:
            raise ValueError("--by-control groups gate records as JSON: `aidd record export records PATH... --by-control`, without --since or --tenant")
        text = json.dumps(export.by_control(Path.cwd(), args.paths), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if not args.out:
            sys.stdout.write(text)
            return 0
        path = Path(args.out) / "controls.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
        return 0
    items = export.collect(args.kind, args.paths, since=args.since, tenant=args.tenant)
    out = export.render(args.kind, items, args.format)
    if not args.out:
        if isinstance(out, bytes):
            sys.stdout.buffer.write(out)
        else:
            sys.stdout.write(out)
        return 0
    path = Path(args.out) / f"{args.kind}.{args.format}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(out, bytes):
        path.write_bytes(out)
    else:
        path.write_text(out, encoding="utf-8", newline="\n")
    print(f"wrote {path} ({len(items)} {args.kind})")
    return 0


def _default_branch(root: str) -> str:
    """The origin's default branch (`refs/remotes/origin/HEAD`), or main."""
    try:
        head = gitutil.run(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], root, check=False).strip()
    except (gitutil.GitError, OSError):
        head = ""
    return head.removeprefix("origin/") or "main"


def cmd_verify(args) -> int:
    """Check an agent change record: its shape, subject, tenant, decision, and approvals, then its signature."""
    from . import changerecord

    path = changerecord.find(args.target, args.dir)
    try:
        stmt = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"aidd record verify: {path}: not JSON ({exc})")
        return 1
    sha = args.target.lower() if not Path(args.target).is_file() else args.sha
    problems = changerecord.check(stmt, sha=sha, tenant=args.tenant)
    signature = "unsigned"
    if not problems and (args.bundle or args.online):
        from . import github

        pred = stmt["predicate"]
        # The repository comes from the one who checks, never from the record: a record names whatever repository its writer chose.
        repo = args.repo or github.origin_repo(".") or ""
        if not repo:
            problems.append("the signature needs the GitHub repository: pass --repo owner/name (there is no github.com origin remote here)")
        elif pred.get("platform") != "github" or pred.get("repo") != repo:
            problems.append(f"the record names the {pred.get('platform')} repository {pred.get('repo')!r}, not {repo}")
        else:
            branch = args.default_branch or _default_branch(".")
            why = changerecord.verify_signature(path, stmt, repo=repo, bundle=args.bundle, signer_workflow=args.signer_workflow, default_branch=branch)
            if why:
                problems.append(f"signature: {why}")
            else:
                signature = "signed"
    head = (stmt.get("predicate") or {}).get("head_sha") if isinstance(stmt, dict) and isinstance(stmt.get("predicate"), dict) else None
    print(f"aidd record verify: {path}  head {str(head)[:12]}  signature {signature}")
    for p in problems:
        print(f"  [FAIL] {p}")
    if problems:
        return 1
    if signature == "unsigned":
        print(
            "  unsigned: nothing proves who wrote this file; pass --bundle or --online to check its attestation"
            + ("" if args.allow_unsigned else ", or --allow-unsigned")
        )
        return 0 if args.allow_unsigned else 1
    print("  verified: the record is signed, names the head, passed, and humans approved")
    return 0


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
        s.set_defaults(func=func)
        return s

    def flag(parser, name: str, help_text: str) -> None:
        parser.add_argument(name, action="store_true", help=help_text)

    base_help = "base branch to compare against (default: origin/HEAD, then origin/main, origin/master, main, master)"

    # ---- Setup ----
    s = cmd("init", "adopt aidd in a repository", cmd_init)
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--dry-run", "print what init finds (stacks, tests, sensitive areas, owners, CI) and the config it proposes; write nothing")
    s.add_argument("--profile", choices=resources.profiles()["order"], default="team", help="gate strictness")
    s.add_argument("--ci", choices=["github", "gitlab", "none"], default="github", help="CI templates to install")
    s.add_argument(
        "--ref",
        metavar="SHA_OR_TAG",
        help="pin the CI files' aidd action and workflow to this commit SHA or release tag (default: the commit this aidd runs "
        "from, when it is a git checkout)",
    )
    s.add_argument("--approvers", nargs="+", metavar="WHO", help="owners.approvers, such as @org/team")
    s.add_argument(
        "--specialist", action="append", metavar="POOL=WHO", help="a specialist Approver pool (owners.specialists), such as security=@org/security (repeatable)"
    )
    s.add_argument("--test", metavar="COMMAND", help='the repository suite, such as "npm test"')
    s.add_argument("--goal", metavar="SENTENCE", help='the goal every agent steers by, such as "make onboarding succeed on the first try"')
    flag(s, "--team", "also install the aidd-team roles: Claude Code agents, commands, and domain-pack skills, and an AGENTS.md section for other harnesses")
    hooks = s.add_mutually_exclusive_group()
    flag(
        hooks,
        "--agent-hooks",
        "wire Claude Code's guard hook (.claude/settings.json) and the aidd MCP server (.mcp.json) even when Claude Code is not detected",
    )
    flag(hooks, "--no-agent-hooks", "do not wire the hook and the MCP server even when Claude Code is detected")
    s.add_argument(
        "--harness",
        action="append",
        choices=[*repo.HARNESSES, "none"],
        metavar="AGENT",
        help="the coding agents to wire instead of detecting them: " + ", ".join(repo.HARNESSES) + ", or none (repeatable)",
    )
    flag(s, "--claude-plugins", "install the aidd plugins for this user through the `claude` CLI instead of repository files for Claude Code")
    flag(s, "--enforce", "install the gate in enforce mode; by default it starts advisory, reporting on 'aidd/gate (advisory)' without blocking")
    s.add_argument("--policy", metavar="COMMAND", help='policy.command, such as "./scripts/aidd-policy" (org and regulated need one)')
    flag(
        s,
        "--devcontainer",
        "also write .devcontainer/: a dev container for agents that denies outbound traffic except to an allow-list (a starting point; aidd sandboxes nothing)",
    )
    s.add_argument(
        "--compliance-target",
        action="append",
        choices=["soc2", "iso27001", "gdpr", "hipaa", "pci-dss", "fedramp", "other"],
        help="a framework or law the product answers to, for [project.compliance] targets; any target turns compliance on: the enterprise-controls defaults and the security CI (repeatable)",
    )
    flag(
        s,
        "--security-ci",
        "also write the security CI when compliance is off: on GitHub .github/workflows/aidd-security.yml (dependency scan, SAST, SBOM, "
        "secret scan), on GitLab .gitlab/aidd-security.gitlab-ci.yml (secret scan)",
    )
    s.add_argument("--link", action="append", metavar="DIR", help="extra agent skill directory to link, besides .claude/skills (repeatable)")
    flag(s, "--no-skill", "do not vendor the skill (agents load the plugin instead)")
    flag(s, "--force", "overwrite existing files and upgrade the vendored skill")

    s = cmd(
        "upgrade",
        "bring a repository's aidd files up to this aidd: the skill, the team files, the CI pins, and aidd_version; a dry run unless --yes",
        cmd_upgrade,
    )
    s.add_argument("path", nargs="?", default=".", help="repository root")
    s.add_argument("--ref", metavar="SHA_OR_TAG", help="pin the CI files to this aidd commit or release; default: this aidd's")
    flag(s, "--yes", "make the changes")

    s = cmd("uninstall", "reverse `aidd init`: list what it would remove, or remove it with --yes", cmd_uninstall)
    s.add_argument("path", nargs="?", default=".", help="the repository (default: the current directory)")
    flag(s, "--yes", "remove the files; without it, only list them")
    s.add_argument("--link", action="append", metavar="DIR", help="extra skill link directories given to `aidd init --link` (repeatable)")

    s = cmd("doctor", "check that a repository is wired correctly", cmd_doctor)
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(
        s,
        "--autopilot",
        "experimental: check the settings for autopilot runs that aidd can see (the hooks level, the guard, held commands, "
        "credential-like variable names), then list what only you can check (the sandbox, the permission mode)",
    )

    s = cmd(
        "standard",
        "the choices the domain packs and practice skills leave open, each with aidd's default, and aidd's library of opinionated "
        "standards that fill them; `add` copies one into docs/standards/ with its [[standards]] entry and its [[tests]], following "
        "[standards_policy]",
        None,
    )
    actions = s.add_subparsers(dest="standard_command", required=True, metavar="ACTION")
    s = cmd(
        "list",
        "the open choices and the library standards, with the company's policy and what this repository has",
        cmd_standard,
        into=actions,
        short="the open choices and the library standards",
    )
    flag(s, "--json", "print JSON")
    s = cmd(
        "add",
        "copy library standards into this repository, all or nothing: each file into docs/standards/, a [[standards]] entry that records "
        "its id, aidd's version, and its hash, and its [[tests]] (std.<group>.<topic>.<name>)",
        cmd_standard,
        into=actions,
        short="copy library standards into this repository",
    )
    s.add_argument("ids", nargs="+", metavar="ID", help="library ids, such as python/ruff-lint-format (`aidd standard list` lists them)")

    s = cmd(
        "stack",
        "stacks: opinionated standards that go together, plus the [project.stack] entries they bring; `add` copies a stack's standards, "
        "as `aidd standard add` does, and merges its entries into [project.stack]",
        None,
    )
    actions = s.add_subparsers(dest="stack_command", required=True, metavar="ACTION")
    s = cmd("list", "the library's stacks and their standards", cmd_stack, into=actions, short="the library's stacks")
    flag(s, "--json", "print JSON")
    s = cmd("add", "copy one stack's standards into this repository and merge its [project.stack] entries", cmd_stack, into=actions, short="adopt one stack")
    s.add_argument("name", metavar="NAME", help="the stack, such as python-cli (`aidd stack list` lists them)")

    # ---- Understand ----
    s = cmd(
        "assess",
        "this change's route (the higher of what its diff needs and what its Spec or Change Request block declares) and lane, then its "
        "next steps and who takes each, then the other branches it overlaps; --paths previews the route before any code",
        cmd_assess,
    )
    s.add_argument(
        "--paths",
        nargs="+",
        metavar="GLOB",
        help="the paths or globs the change will touch, before any code exists: the route they need and the lane's first step",
    )
    s.add_argument("--type", choices=TYPES, help="--paths: the change type (default feat)")
    s.add_argument("--dimension", action="append", choices=DIMENSIONS, help="--paths: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "--paths: a revert would not restore the prior state (forces major)")
    flag(s, "--json", "print the route, the steps, and the overlaps as JSON")

    def list_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("repos", nargs="*", metavar="REPO", help="the repositories of a project, such as api web infra; default: this one")
        flag(s, "--json", "print the steps as JSON")
        flag(s, "--mine", "only work you own (`owner`), with a Task assigned to you, or that you added (git user.email/name, GitHub login)")
        s.add_argument("--agent", nargs="?", const="", metavar="ROLE", help="only Specs with a todo Task assigned to an agent (to agent:ROLE when given)")
        flag(s, "--blocked", "only blocked work: blocked_on set, blocked_by unfinished work, or a Task out of retries")
        flag(s, "--waiting-on-me", "the Approver inbox: approvals waiting on you, and a warning past max_open_per_approver")
        s.add_argument("--label", metavar="LABEL", help="only Specs with this label")
        s.add_argument(
            "--priority", choices=["urgent", "high", "medium", "low"], metavar="LEVEL", help="only work at this priority or higher (urgent, high, medium, low)"
        )

    s = cmd(
        "list",
        "all open work, one copy of each item from the base branch and every open branch, with its derived status, its next "
        "step, and who holds it: the agent, the author, an Approver, a triager, or a decision maker",
        cmd_list,
    )
    list_args(s)
    s.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write the decision page (experimental): every step listed, with who decides, how, and the page or command for each, as "
        "one self-contained HTML page (default aidd-evidence/views/decisions-<view>.html). With --waiting-on-me, every decision waiting "
        "on you. It never approves",
    )
    flag(
        s,
        "--upkeep",
        "the upkeep that is due instead of the open work: library standards past review, feature flags past cleanup, emergency "
        "backfills, flaky tests (with --events), waivers ending within 30 days, runbooks past their drill, and doctor warnings, "
        "each with the command or skill that takes it (schemas/upkeep.schema.json)",
    )
    s.add_argument("--events", action="append", metavar="PATH", help="with --upkeep: gate events (JSON lines) that name flaky tests (repeatable)")

    s = cmd("log", "one Spec's history from git: status transitions with time in state, approvals, and Assisted-by trailers", cmd_log)
    s.add_argument("spec", help="the Spec, such as specs/SPEC-1.md or SPEC-1")
    s.add_argument(
        "--record",
        action="append",
        metavar="PATH",
        help="a gate record from `aidd gate --record` (repeatable; default aidd-evidence/record.json when it exists)",
    )
    flag(s, "--json", "print the log as JSON")

    s = cmd("owners", "who decides and who does the work: the Approvers, the specialist Approver pools, and every agent role", cmd_owners)
    flag(s, "--json", "print the owners as JSON")
    s.add_argument(
        "--changed",
        nargs="+",
        metavar="PATH",
        help="the paths the change touches: each role lists only the standards whose when_changed matches them",
    )

    s = cmd("metrics", "summarize gate events", cmd_metrics)
    s.add_argument("--tenant", metavar="TENANT", help="only the events of this tenant (the `tenant` their config names)")
    s.add_argument("events", nargs="*", help="JSON-lines files written with --events, from any number of repositories")
    s.add_argument(
        "--guard",
        nargs="?",
        const=GUARD_LOG_DEFAULT,
        metavar="PATH",
        help="count the guard's denials by reason and by role, from the log `aidd hook pre-tool` keeps (default .aidd/work/guard.jsonl at the repository's top level)",
    )
    s.add_argument("--since", metavar="DATE", help="only events at or after this ISO date or time, such as the last retrospective")
    s.add_argument(
        "--by",
        choices=list(metrics.GROUPS),
        help="one summary per repo, org (the organization or company that owns the repository), team (the Spec's owner_team), profile, route, "
        "or author. `aidd metrics --by author` serves agent autonomy and a person's self-review, never ranking or appraising people",
    )
    s.add_argument(
        "--target-wait", type=float, metavar="MINUTES", help="name the approvals and checks whose median wait is above this many minutes (a day is 1440)"
    )
    flag(s, "--autonomy", "gradual release: per agent and change type, how its changes fared and the stage of autonomy the evidence supports")
    flag(s, "--dora", "the five DORA software delivery metrics against the [targets] in the config; exit 1 when one misses")
    flag(
        s,
        "--flaky",
        "per test: on how many heads it ran, and how often it passed on a re-run after failing on the same head; "
        "a rate over 5%% is over the limit (display only, exit 0)",
    )
    s.add_argument("--specs", metavar="DIR", help="add the change fail rate and recovery days from the Specs' outcome (DORA stability)")
    s.add_argument(
        "--cost",
        metavar="LEDGER",
        help="join a host-exported cost ledger (JSON lines: ts, amount, currency, agent, spec, branch, sha) to the changes; display only, never a gate",
    )
    flag(
        s,
        "--suggest-standard-changes",
        "with --autonomy: print a [[standard_changes]] entry for each class that meets the thresholds, for a person to merge",
    )
    flag(
        s,
        "--autopilot",
        "experimental: the autopilot runs' measures from the run events in the git directory (and the event files given): "
        "human decisions per change, decision wait, agent steps per decision, rework, cost per change, and guard denials during runs",
    )
    s.add_argument("--render", metavar="NAME", help="print the summary with an installed aidd.renderers extension instead")
    flag(s, "--json", "print JSON")

    s = cmd(
        "digest",
        "a status rollup since a date or a git ref, from what aidd already knows: what shipped, what is in progress, who it waits "
        "on, what is blocked, the risks, the overdue items, feedback themes, and the gate metrics; --client for the client's view: "
        "a RAG status with its rules, milestones, what shipped in plain words, what we need from them, and next steps",
        cmd_digest,
    )
    s.add_argument("--since", required=True, metavar="DATE_OR_REF", help="an ISO date (2026-09-01) or a git ref, such as the last release tag")
    flag(s, "--client", "the client's view; it never holds internal cost data unless --include-cost")
    s.add_argument("--events", nargs="+", metavar="PATH", help="gate events (`aidd gate --events`) for the metrics (default aidd-events.jsonl when it exists)")
    s.add_argument(
        "--cost", metavar="LEDGER", help="join a cost ledger to the changes: shown in the team view, and in the client view only with --include-cost"
    )
    flag(s, "--include-cost", "with --client: show the cost to the client too")
    s.add_argument("--blocked-days", type=int, default=5, metavar="N", help="the client view is red when an item has been blocked for more than N days")
    s.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="with --client: also write the client status as one self-contained HTML page (default aidd-evidence/views/digest-client-<date>.html)",
    )
    flag(s, "--json", "print JSON (schemas/digest.schema.json)")

    # ---- Author ----
    s = cmd(
        "new",
        "create a Spec, Epic, Initiative (a solo founder's brief too), Proposal, runbook, postmortem, or feedback log from the template; or a document a Spec links "
        "(tech-spec, test-plan, adr, threat-model, authz, design-spec (--prototype for its HTML prototype), api, slo, compliance, analytics, migration, acceptance), "
        "written from its template and added to the Spec's [[docs]]; or the repository's one design-system (DESIGN.md, design/tokens.json, and design/build.mjs), architecture overview "
        "(docs/architecture/README.md), data-map, vendors register, or glossary (docs/GLOSSARY.md); or a proposal's contract, then each change order (`aidd new contract <proposal id>`); "
        "or an exploration (`aidd new exploration <folder> --title <question>`), rendered by `aidd explore`",
        cmd_new,
    )
    # The kinds besides the Spec, its containers, the proposal, and the postmortem come from repo.DOC_KINDS_NEW; runbook
    # stays beside postmortem in the help.
    s.add_argument(
        "kind",
        choices=["spec", "epic", "initiative", "proposal", "runbook", "postmortem", *(k for k in repo.DOC_KINDS_NEW if k != "runbook")],
    )
    s.add_argument(
        "id",
        nargs="?",
        help="such as SPEC-42; for a linked document, its topic, such as rate-limits; a contract's proposal id; an exploration's folder; none for a repository document",
    )
    s.add_argument(
        "--title", help="required for a Spec, Epic, Initiative, Proposal, runbook, or postmortem; an exploration's question; a document's default is its topic"
    )
    s.add_argument(
        "--route",
        choices=["normal", "major", "emergency"],
        help="a Spec is normal (the default; the gate raises it when needed), major, or an emergency backfill; with --paths, the "
        "computed route wins when it is higher",
    )
    s.add_argument("--type", default="feat", choices=TYPES, help="the change type")
    s.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        help="spec: the paths or globs the change will touch; computes the route (and says when no Spec is needed) and writes them as the Task's scope",
    )
    s.add_argument("--dimension", action="append", choices=DIMENSIONS, help="spec: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "spec: a revert would not restore the prior state (forces major)")
    flag(s, "--force", "spec: write a Spec even when the paths are on the fast lane")
    flag(
        s,
        "--full",
        "spec: every section (adds Problem, Goals, Non-goals, and Learn); by default a normal Spec is the short one (Intent, "
        "Context, Acceptance, Design, Policy conflicts, Rollback), and a major Spec is full; alternatives and the pre-mortem "
        "live in the tech spec it links",
    )
    s.add_argument("--owner-team", default="", help="default: owners.default_team from the config")
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
        help="a linked document's folder under <docs dir>/specs/ (a prototype's under <docs dir>/design/), such as checkout (default: the Spec id)",
    )
    flag(s, "--no-link", "a linked document: write it and print its [[docs]] entry, leaving the Spec to its writer to link it")
    flag(
        s,
        "--prototype",
        "ui: write the HTML prototype instead of the design spec, as prototype.html in the design folder: every screen of the flow, "
        "its states, themes, and frames, deep links, and wireframe and feedback modes",
    )
    s.add_argument("--owner", default="", help="exploration: the role that owns it (default product-designer; architect for an architecture question)")
    s.add_argument(
        "--timebox",
        default="45 minutes",
        help="exploration: minutes or a cost, or a spike's end date (YYYY-MM-DD); when it runs out, the owner stops and presents",
    )

    s = cmd(
        "import",
        "write a short Spec from another planning tool's files (Spec Kit, OpenSpec, Kiro, BMAD): Intent, Acceptance ids, "
        "Tasks with the paths it names, and the computed route; it links the plan instead of copying it. `issues`: one suggested Spec per new issue of a "
        "tracker (--github or --file), its text quoted as data, waiting for a person's triage; an issue already imported is skipped",
        cmd_import,
    )
    s.add_argument("tool", choices=["speckit", "openspec", "kiro", "bmad", "issues"])
    s.add_argument(
        "path",
        nargs="?",
        help="Spec Kit: specs/NNN-feature/; OpenSpec: openspec/changes/<change>/; Kiro: .kiro/specs/<feature>/; BMAD: one story file; none for issues",
    )
    s.add_argument(
        "--github", metavar="OWNER/REPO", help="issues: the repository's open issues (GITHUB_TOKEN or GH_TOKEN when set; public repositories without one)"
    )
    s.add_argument("--file", metavar="PATH", help="issues: a JSON array exported from any tracker, each {title, body, url, labels}, or GitHub's shape")
    s.add_argument("--label", metavar="LABEL", help="issues: only GitHub issues with this label")
    s.add_argument("--limit", type=int, metavar="N", help="issues: at most this many new Specs (default 30, at most 500)")
    s.add_argument("--id", metavar="ID", help="the Spec id (default: SPEC-<n>, one past the highest in the Specs folder)")
    s.add_argument("--out", metavar="DIR", help="where to write it (default: the config's Specs folder)")
    s.add_argument("--title", help="the Spec's title (default: the source's)")
    s.add_argument("--type", choices=TYPES, help="the change type (default: feat; fix for a Kiro bugfix spec)")

    s = cmd("describe", "print the Change Request block that describes the current branch's change, with the reasons for its route", cmd_describe)
    s.add_argument("--base", help=base_help)
    s.add_argument(
        "--type", choices=TYPES, help="the change type (default: the newest Conventional Commit subject's type, else docs for doc-only diffs, else feat)"
    )
    flag(
        s,
        "--commit",
        "local-first, with no PR/MR description: record the block in an empty commit on the branch, where `aidd test`, `aidd gate`, "
        "and `aidd ship` read it (the newest such commit wins)",
    )

    s = cmd("test", "run the tests (green on head, red on base) and write evidence", cmd_test)
    s.add_argument("--base", help=base_help)
    s.add_argument("--spec", help="the Spec whose tests to run (default: the one Spec in the diff)")
    s.add_argument("--body-file", help="PR/MR description holding the Change Request block")
    s.add_argument("--out", default="aidd-evidence", help="where evidence.json and logs go")
    flag(s, "--no-red", "skip red runs (the gate will still require them)")
    flag(s, "--red-in-place", "CI only: run red in this checkout, keeping installed dependencies")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=PASS_ENV_HELP)
    flag(
        s,
        "--changed",
        "local: run only the commands the working tree's changes against the base select (a matching when_changed, a Spec command when "
        "a path is in a Task's scope or its test files, a config command without when_changed), green only; the evidence is marked partial "
        "and the gate never accepts it",
    )
    flag(s, "--watch", "local: run --changed now and again whenever a file changes, until Ctrl-C (exit 0)")
    s.add_argument("--interval", type=float, default=1.0, metavar="SECONDS", help="--watch: how often to look for changes")
    flag(s, "--merge-group", "CI, in a merge_group run: test the merge-group commit against the commit the queue entry was built on (as the gate computes it)")

    s = cmd("proposal", "a proposal's tables for the document you send (matrix), or an accepted proposal as an Initiative and Epics (convert)", cmd_proposal)
    s.add_argument("action", choices=["matrix", "convert"])
    s.add_argument("file", help="the proposal, such as proposals/PROP-1/proposal.md")

    # ---- Decide ----
    s = cmd(
        "explore",
        "render an exploration's one comparison page: two or three divergent directions side by side (stacked on a phone), "
        "the trade-offs under each, each round's screenshots beside the round before with the feedback each change answers, "
        "and a choice to copy. The page records nothing and approves nothing: the owning role writes the pick and its reason "
        "in the Spec's Design section, DESIGN.md, or an ADR",
        cmd_explore,
    )
    s.add_argument("folder", help="the exploration's folder, such as docs/design/SPEC-12 or docs/architecture/explore/queues")
    s.add_argument("--out", metavar="PATH", help="where to write the page (default: aidd-evidence/views/explore-<folder>.html)")

    s = cmd(
        "hash",
        "print the Spec hash of a Spec and its frozen test and design files, or the approval line an Approver posts; for a proposal, the hash its sign-off records",
        cmd_hash,
    )
    s.add_argument("spec", help="path to the Spec file or the proposal, or its id (SPEC-1, PROP-3)")
    s.add_argument("--ref", default="HEAD", help="commit to hash; the gate hashes the PR head")
    flag(s, "--worktree", "hash the working tree instead of a commit")
    flag(s, "--line", "print the whole approval line (/aidd approve-spec ID HASH COMMIT), or a proposal's sign_off line, instead of the bare hash")
    flag(
        s,
        "--summary",
        "print a phone-sized summary of what the hash approves first (intent, Acceptance ids and text, scope, risk, rollback, "
        "frozen test files), at most 25 lines, ending with the hash or, with --line, the approval line",
    )
    flag(
        s,
        "--html",
        "also write the Spec approval page: one self-contained HTML page with the intent, Acceptance against the tests, the route "
        "and why, the risk and rollback, each frozen file and doc, the diagrams, what changed since the last approval, and the "
        "approval line to copy (default aidd-evidence/views/spec-<ID>.html). It never approves",
    )
    s.add_argument("--out", metavar="PATH", help="--html: write the page here instead")

    s = cmd("approve", "local-first: record a person's Spec approval or Merge approval on this machine, with no platform", cmd_approve)
    s.add_argument("what", choices=["spec", "merge"])
    s.add_argument("spec", nargs="?", help="for spec: the Spec, such as specs/SPEC-1.md")
    s.add_argument("--base", help=base_help)
    s.add_argument(
        "--evidence",
        help="merge: the evidence `aidd test` wrote, whose results the digest and the gate state show (default aidd-evidence/evidence.json)",
    )
    flag(s, "--skip-cooloff", "merge, local-first: skip the route's cool-off, on record (the gate warns and the record names you)")

    # ---- Autopilot (experimental) ----
    s = cmd(
        "autopilot",
        AUTOPILOT + ". Its lease and one-line journal live in the git directory: one live lease per piece of work, stale after its timebox. "
        "At Spec approval it asks, unless a local approval exists, on GitLab, with no GitHub token, in a fork workflow, or with no "
        "[project] repo (set it, or run `aidd init` again)",
        None,
    )
    auto = s.add_subparsers(dest="action", metavar="ACTION", required=True)
    session_help = "the session that holds the lease, the one `start` printed (required: a lone lease may be another session's)"
    a = cmd(
        "start",
        "start autopilot on a piece of work for a session; a live lease of another session refuses it, a stale one is replaced, and starting again "
        "after the run ended (a plan ready, a limit, nothing open) begins a new run",
        cmd_autopilot,
        into=auto,
        short="start autopilot on a piece of work",
    )
    a.add_argument("--work", default="all", metavar="WORK", help="a Spec, Epic, or Initiative id, a label, or all")
    a.add_argument("--session", metavar="ID", help="the harness session's id (default: a new one, printed)")
    a.add_argument("--timebox", metavar="DURATION", help="how long the run may last, such as 90m or 2h (default: [autopilot] timebox, else 2h)")
    a = cmd(
        "next",
        "the one next action, decided by the engine from the open work, the step-to-flow map, the lease and journal, and the "
        "[autopilot] limits: run a team command, ask a person (with the decision page), or stop (with why)",
        cmd_autopilot,
        into=auto,
        short="the one next action",
    )
    a.add_argument("--work", metavar="WORK", help="the run's work: a Spec, Epic, or Initiative id, a label, or all (default: the lease's)")
    a.add_argument("--session", metavar="ID", required=True, help=session_help)
    a.add_argument("--goal", metavar="TEXT", help="with nothing planned for the work: the goal to plan (or propose, for client work)")
    flag(a, "--json", "print the action as JSON (schemas/autopilot-next.schema.json)")
    a = cmd(
        "note",
        'record a step\'s result in the journal, as "<code> <result>", with the head it ran on; the result is ok, fail, waiting, or blocked',
        cmd_autopilot,
        into=auto,
        short="note a step's result",
    )
    a.add_argument("text", metavar="NOTE", help='"<code> <result>", such as "spec.in_progress ok"; any words after them are kept as data')
    a.add_argument("--session", metavar="ID", required=True, help=session_help)
    a.add_argument("--spec", metavar="ID", help="the Spec the step was about (default: the lease's work)")
    a.add_argument("--tokens", type=int, metavar="N", help="the tokens the step used, zero or more (self-reported)")
    a.add_argument("--cost", type=float, metavar="AMOUNT", help="what the step cost, zero or more, with --currency (self-reported)")
    a.add_argument("--currency", metavar="CODE", help="the ISO 4217 currency of --cost, such as USD")
    a = cmd("status", "print every lease, whether its timebox ended, and the journal's last lines", cmd_autopilot, into=auto, short="the lease and journal")
    flag(a, "--json", "print them as JSON (schemas/autopilot-status.schema.json)")
    a = cmd("stop", "stop autopilot: remove the session's lease", cmd_autopilot, into=auto, short="stop autopilot")
    a.add_argument("--session", metavar="ID", required=True, help=session_help)

    s = cmd(
        "context",
        "experimental: the minimal context pack for a step of a Spec, as paths with a one-line reason and a token estimate each: the "
        "summary, the Task, the linked docs, the exemplar Specs on the Specify step, the latest handoff note, and the standards for its paths. "
        "It never prints a file's contents",
        cmd_context,
    )
    s.add_argument("spec", help="the Spec, such as specs/SPEC-1.md or SPEC-1")
    s.add_argument("--role", metavar="ROLE", help="only this role's Tasks and standards, such as developer")
    s.add_argument("--step", metavar="CODE", help="the step code the pack is for, such as spec.in_progress (recorded in the pack)")
    flag(s, "--json", "print the pack as JSON (schemas/context-pack.schema.json)")

    # ---- Check ----
    s = cmd("gate", "run every gate rule: locally as a preflight, in CI for a platform, or against any context", cmd_gate)
    s.add_argument("platform", nargs="?", choices=["github", "gitlab"], help="CI entry point: gather a trusted context and report aidd/gate")
    s.add_argument("--context", help="context.json from any CI adapter (schemas/context.schema.json)")
    s.add_argument("--base", help=base_help)
    s.add_argument("--spec", help="local: the Spec this change implements (default: the one Spec in the diff)")
    s.add_argument("--body-file", help="local: PR/MR description holding the Change Request block")
    s.add_argument("--approvals", help='local: JSON for dry runs, {"reviews": [...], "comments": [...]}')
    s.add_argument("--evidence", default="aidd-evidence/evidence.json", help="local and GitLab: evidence from `aidd test`")
    flag(s, "--no-policy", "local: do not run the Policy command")
    flag(s, "--markdown", "print the PR summary instead of text")
    flag(s, "--json", "print the decision record as JSON (schemas/record.schema.json, with schema_version), nothing else")
    s.add_argument(
        "--mode",
        choices=["enforce", "advisory"],
        help="CI: advisory reports on 'aidd/gate (advisory)' and never blocks. The base branch's config `mode` wins; AIDD_MODE never relaxes the gate, and on GitLab neither does this flag (default: enforce)",
    )
    flag(s, "--dry-run", "CI: decide without posting a status")
    flag(s, "--pending-ok", "GitLab: exit 0 while approvals are pending")
    flag(s, "--post-status", "GitLab: also post an external status (needs an api-scope token)")
    flag(s, "--resolve", "GitHub: only print the pull request numbers this event concerns, and the head commit a run judges")
    s.add_argument("--record", metavar="PATH", help="write the derived change record here")
    s.add_argument("--events", metavar="PATH", help="append one gate event (a JSON line) here")
    s.add_argument("--explain", metavar="RULE", help="print what a rule checks and how to satisfy it, then exit")
    s.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write the Merge approval page: the decision and its findings with fixes, Acceptance against the evidence, the "
        "review report's findings, what the verifier recorded, the scope and budget, and the diff file by file, as one "
        "self-contained HTML page (default aidd-evidence/views/merge-<head>.html). The gate never reads it",
    )

    s = cmd("validate", "validate files or directories; with none, the whole repository, including overdue emergency reviews", cmd_validate)
    s.add_argument("paths", nargs="*", help="config .toml files, object .md files, or directories")

    record = cmd(
        "record",
        "the records the gate writes: check an agent change record (verify), or export gate records and events (export)",
        None,
    )
    records = record.add_subparsers(dest="record_command", required=True, metavar="ACTION")
    s = cmd(
        "verify",
        "check an agent change record (the in-toto statement `aidd gate --record` writes): its subject, tenant, decision, and human "
        "approvals, and, with --bundle or --online, its signature through `gh attestation verify`",
        cmd_verify,
        into=records,
        short="check an agent change record: its subject, tenant, decision, approvals, and signature",
    )
    s.add_argument("target", metavar="SHA|PATH", help="a change record file, or a head commit SHA whose record is in --dir")
    s.add_argument("--dir", default="aidd-evidence", help="where to look for the record of a SHA")
    s.add_argument("--sha", metavar="SHA", help="with a PATH: the head commit the record must name")
    s.add_argument("--tenant", metavar="TENANT", help="the tenant the record must belong to")
    s.add_argument("--bundle", metavar="PATH", help="a Sigstore bundle (from `gh attestation download`) to verify the signature against")
    flag(s, "--online", "fetch and verify the attestation from GitHub with `gh attestation verify`")
    s.add_argument(
        "--repo", metavar="OWNER/NAME", help="the GitHub repository that signed it (default: this checkout's github.com origin); the record must name it"
    )
    s.add_argument(
        "--signer-workflow", metavar="WORKFLOW", help="the workflow the signature must come from (default: OWNER/NAME/.github/workflows/aidd-gate.yml)"
    )
    s.add_argument("--default-branch", metavar="BRANCH", help="the branch the signing workflow ran from (default: origin/HEAD, else main)")
    flag(s, "--allow-unsigned", "exit 0 for a record that holds but is not signed (it still prints unsigned)")

    s = cmd(
        "export",
        "export gate records or gate events as JSON or CSV, deterministically, for a log store or a spreadsheet",
        cmd_export,
        into=records,
        short="export gate records or gate events as JSON or CSV",
    )
    s.add_argument("kind", choices=["records", "events"])
    s.add_argument("paths", nargs="+", metavar="PATH", help="record files (--record) or event files (--events), or directories holding them")
    s.add_argument("--since", metavar="DATE", help="events only: those at or after this ISO date or time")
    s.add_argument("--format", default="json", metavar="FORMAT", help="json, csv, or the name of an installed aidd.exporters extension")
    s.add_argument("--tenant", metavar="TENANT", help="only the records or events of this tenant (the `tenant` their config names)")
    s.add_argument("--out", metavar="DIR", help="write DIR/<kind>.<format> instead of printing")
    flag(
        s,
        "--by-control",
        "records only, as JSON: group the records and the Specs' linked docs by the control ids their compliance docs declare "
        "(schemas/control-evidence.schema.json; run it at the repository root)",
    )

    # ---- Operate ----
    s = cmd("ship", "local-first: merge the current branch into the base branch once the gate passes, keeping its history or squashing it", cmd_ship)
    s.add_argument("--base", help="the base branch; default: the repository's default branch")
    flag(s, "--squash", "one commit on the base branch, keeping every Assisted-by trailer")
    s.add_argument("--message", help="the merge or squash commit message; default: the Spec's title, or the newest commit's subject")
    s.add_argument(
        "--body-file",
        help="the change description holding the Change Request block (default: the newest branch commit that holds one, else the Spec in the diff)",
    )
    s.add_argument("--out", default="aidd-evidence", help="where the tests ship runs on the head write their evidence and logs")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=PASS_ENV_HELP)
    flag(s, "--skip-cooloff", "skip the route's cool-off, on record: locally it starts at a committer date, so it is a reminder, not a control")

    s = cmd(
        "release-notes",
        "release notes from the Specs shipped since a tag or a date: each one's title, intent, and flags, grouped as Added, Changed, "
        "Deprecated, Removed, Fixed, and Security (Keep a Changelog), for users or for developers",
        cmd_release_notes,
    )
    s.add_argument("--since", required=True, metavar="TAG_OR_DATE", help="the last release's tag (or any git ref), or an ISO date")
    s.add_argument(
        "--audience",
        choices=["users", "developers"],
        default="users",
        help="users: the changes they notice (feat, fix, perf, security); developers: every change",
    )
    flag(s, "--json", "print JSON (schemas/release-notes.schema.json)")

    s = cmd(
        "observe",
        "after release: run a Spec's observe command once, or poll it for the observe window (--window); exit 0 healthy (the window "
        "ended with the rollback trigger never firing), 1 unhealthy (the trigger fired), 2 error. It never rolls back. With --band "
        "METRIC, judge a metric series against its control band instead (no model); exit 1 when an agent may diagnose or suggest a change",
        cmd_observe,
    )
    s.add_argument("target", metavar="SPEC|SERIES", help="the Spec file, such as specs/SPEC-42.md; with --band, the metric series file")
    s.add_argument(
        "--window",
        nargs="?",
        const="spec",
        metavar="DURATION",
        help="poll until the Spec's observe.window ends, or this long (such as 90s, 30m, 24h); stop as soon as the rollback trigger fires",
    )
    s.add_argument("--every", default="5m", metavar="DURATION", help="--window: how often to run the observe command, such as 30s or 5m")
    s.add_argument("--consecutive", type=int, default=1, metavar="N", help="--window: the rollback trigger fires after this many unhealthy checks in a row")
    s.add_argument(
        "--write",
        nargs="?",
        const="auto",
        metavar="SPEC_ID",
        help="record outcome.observe_result in the Spec (a bookkeeping field Spec approval ignores); with --band, on a breach, write a "
        "draft Spec with the evidence (default id OBS-<metric>-<date>)",
    )
    s.add_argument("--timeout", type=int, default=600, help="seconds before the command counts as failed")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=PASS_ENV_HELP)
    s.add_argument(
        "--band",
        metavar="METRIC",
        help="judge SERIES (values, oldest first: JSON lines with a value field, CSV ending in the value, or one number per line) "
        "against this metric's control band; a matching [[observe.bands]] entry sets the thresholds",
    )
    s.add_argument("--baseline", type=int, metavar="N", help="--band: how many recent values make the baseline (default 30)")
    s.add_argument("--diagnose-sigma", type=float, help="--band: standard deviations at which an agent may diagnose read-only (default 2)")
    s.add_argument("--propose-sigma", type=float, help="--band: standard deviations at which an agent may suggest a change (default 3)")
    flag(s, "--json", "--band: print the reading as JSON")

    # ---- Maintainers and harnesses ----
    s = cmd(
        "eval",
        "run the example suite, an agent routing eval, the role evals, the standards check, the pack and practice template check, "
        "or your own agent tasks; report recorded runs",
        cmd_eval,
    )
    s.add_argument("suite", choices=["examples", "routing", "roles", "standards", "packs", "tasks", "report"])
    s.add_argument("paths", nargs="*", metavar="PATH", help="report: JSON-lines files written with --record, printed as one markdown table")
    s.add_argument(
        "--root", help="examples, routing, roles: the aidd source checkout (default: this installation's source, if any); tasks: your repository (default: .)"
    )
    s.add_argument("--scenarios", help="directory of scenario .toml files")
    s.add_argument("--cmd", help='agent command that reads a prompt on stdin, such as "claude -p"')
    flag(s, "--no-embed", "routing: rely on the harness loading the skill instead of embedding routes.md")
    s.add_argument(
        "--min-accuracy", type=float, default=0.9, help="fail below this mean pass@1: the share of correct routes, passed role scenarios, or passed tasks"
    )
    s.add_argument("--repeat", type=int, default=1, metavar="K", help="routing, roles, tasks: run each scenario K times; report pass@1 and pass^K")
    flag(
        s,
        "--control",
        "routing, roles: also run every scenario without the aidd material (the skill reference, the role playbook) and report the lift; never gates",
    )
    s.add_argument("--record", metavar="PATH", help="routing, roles, tasks: append this run to a JSON-lines file (read it with `aidd eval report`)")
    s.add_argument("--model-label", metavar="TEXT", help="the model name to record with the run, as you name it (aidd never infers it)")
    s.add_argument(
        "--max-days",
        type=int,
        help="standards: fail when an entry was last checked more than this many days ago, for every entry "
        "(default: each entry's cadence: its review_every_days, else 90 days emerging and 365 established)",
    )
    flag(
        s,
        "--online",
        "standards: fetch each evidence URL again and report whether its quote is still there (ok, moved, missing, unreachable); never edits the registry",
    )
    flag(s, "--strict", "standards --online: exit 1 when an entry is moved or missing (never for unreachable)")
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
    s.add_argument(
        "--materialize",
        metavar="DIR",
        help="examples: write every case and mutation as a resolved context plus its expectation, for another gate implementation to run",
    )

    cmd("mcp", "serve aidd to agents as MCP tools over stdio (assess, check_edit, validate, approval_line, describe, gate)", cmd_mcp)
    s = cmd(
        "hook",
        "agent harness hooks; pre-tool (pre-edit, its earlier name, still works) reads a Claude Code PreToolUse event and denies edits outside "
        "the active Spec; session-start adds "
        "`aidd assess` to a new session; prompt-submit adds the next step to each prompt (UserPromptSubmit); stop reminds the agent "
        "to run `aidd test` (Stop and SubagentStop); pre-compact saves the state of the work in the git directory",
        cmd_hook,
    )
    s.add_argument("event", choices=["pre-tool", "pre-edit", "session-start", "prompt-submit", "stop", "pre-compact"])

    s = cmd("gen-docs", "maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills", cmd_gen_docs)
    flag(s, "--check", "fail when any generated block is stale")

    if plugins and not ext.sealed():
        ext.register_commands(sub, set(sub.choices))
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    # A protected command (the gate, the test runner, approvals, ship, the hooks, the MCP server) never discovers
    # extensions: seal discovery before its parser is built, so no plugin module is imported in this process.
    command = ext.command_of(argv)
    if command in ext.PROTECTED:
        ext.seal()
    args = build_parser(plugins=command not in ext.PROTECTED).parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, LookupError, gitutil.GitError, http.HttpError, RuntimeError) as exc:
        print(f"aidd: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # a bug must never look like a gate decision (exit 1)
        print(f"aidd: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
