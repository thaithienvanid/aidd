"""The command line's grammar, one function for each command: its arguments and flags, in the order the usage line and
`--help` show them. `parser.py` lists the commands by help group (`COMMAND_GROUPS`), and `build_parser` calls the function
that `ADD_COMMAND` names for each one."""

from __future__ import annotations

import argparse

from aidd import config, recall, workitems
from aidd.cli import arguments


def add_init(cmd, flag) -> None:
    s = cmd("init", "adopt aidd in a repository", "setup:cmd_init")
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--dry-run", "print what init finds (stacks, tests, sensitive areas, CI) and the config it proposes; write nothing")
    s.add_argument("--profile", choices=list(config.PROFILES), help="solo (one person decides) or team (default: the config init keeps, else asked, else solo)")
    s.add_argument(
        "--ci", choices=["github", "gitlab", "none"], default=None, help="CI templates to install (default: github with a git remote, none without one)"
    )
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
    flag(
        s,
        "--delegate",
        "decide for me inside limits: write a standing delegation, so aidd-team:delegate answers the delegable asks on a passing check "
        "(Claude Code only; every other harness keeps asking)",
    )
    s.add_argument("--merge-deploys", choices=["yes", "no", "unsure"], help="with --delegate: whether merging to the default branch deploys anything")
    s.add_argument("--link", action="append", metavar="DIR", help="extra agent skill directory to link, besides .claude/skills (repeatable)")
    flag(s, "--no-skill", "do not vendor the skill (agents load the plugin instead)")
    flag(s, "--force", "overwrite existing files and upgrade the vendored skill")


def add_upgrade(cmd, flag) -> None:
    s = cmd(
        "upgrade",
        "bring a repository's aidd files up to this aidd: the skill, the team files, the text between aidd's marks in AGENTS.md, each agent's ask rules, the CI pins, aidd_version, "
        "the config fields this aidd removed, which stay as comments, and the work items an older aidd wrote above the Spec, folded into Intents; a dry run unless --yes",
        "setup:cmd_upgrade",
    )
    s.add_argument("path", nargs="?", default=".", help="repository root")
    s.add_argument("--ref", metavar="SHA_OR_TAG", help="pin the CI files to this aidd commit or release; default: this aidd's")
    flag(s, "--yes", "make the changes")
    flag(
        s,
        "--collapse-unstarted",
        "turn each Spec nobody started (a draft with no approval, no revision, and no branch ahead) into its slice line in its Intent, with `drafted_in` naming the commit that holds it",
    )


def add_self_update(cmd, flag) -> None:
    s = cmd(
        "self-update",
        "update the aidd CLI to the latest release of thaithienvanid/aidd, the way it was installed (uv, pipx, or the one-line installer), "
        "from the release's wheel once it matches the release's SHA256SUMS, or to the tip of main while no release exists; AIDD_NO_UPDATE_CHECK=1 turns the daily check off",
        "setup:cmd_self_update",
    )
    flag(s, "--check", "say what it would update to; change nothing")
    flag(s, "--main", "update to the tip of main even when a release exists: unreleased code, with no release to verify it against")


def add_uninstall(cmd, flag) -> None:
    s = cmd("uninstall", "reverse `aidd init`: list what it would remove, or remove it with --yes", "setup:cmd_uninstall")
    s.add_argument("path", nargs="?", default=".", help="the repository (default: the current directory)")
    flag(s, "--yes", "remove the files; without it, only list them")
    s.add_argument("--link", action="append", metavar="DIR", help="extra skill link directories given to `aidd init --link` (repeatable)")


def add_doctor(cmd, flag) -> None:
    s = cmd("doctor", "check that a repository is wired correctly", "setup:cmd_doctor")
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--json", "print each check as JSON (schemas/doctor.schema.json)")


def add_standard(cmd, flag) -> None:
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


def add_status(cmd, flag) -> None:
    s = cmd("status", "the open work: each Spec, Intent, and proposal with its status and its next step, and who takes it", "status:cmd_status")
    s.add_argument(
        "id",
        nargs="?",
        metavar="ID|PATH",
        help="one work item, such as SPEC-3, including a finished one, with what stands behind it; or a repository path: the Specs "
        "whose Task scope covers it, the open Specs in flight there, their tests, docs, and interfaces, the route, and the last commits",
    )
    s.add_argument(
        "--commits",
        type=int,
        default=None,
        metavar="N",
        help=f"with a path, a Spec, or an Intent: the most commits to read, from 1 to {workitems.MAX_COMMITS} (default {workitems.DEFAULT_COMMITS})",
    )
    flag(s, "--mine", "only what waits on a person")
    flag(s, "--all-branches", "the open work in every worktree and in every local and fetched branch, each item with the places that hold it")
    s.add_argument(
        "--delivery-team",
        metavar="NAME",
        help="only one delivery team's work (`delivery_teams` in the config): its Intents, their Specs, the Specs whose `owner_team` names it, and the Specs whose Task scope touches its areas",
    )
    flag(s, "--json", "print it as JSON (schemas/status.schema.json)")
    flag(
        s,
        "--html",
        "write it as one page to .aidd/views/status-work.html: what needs you, a board by loop step or status group, the tree, search, and a page for each item, each with the words to copy (a filtered run writes its own file)",
    )


def add_risk(cmd, flag) -> None:
    s = cmd(
        "risk",
        "advice before an action: the route for planned paths (--paths), the level of a shell command (--command) or an action (--action), "
        "or every risk rule in force (--list); a level is allow, report, or ask",
        "work:cmd_risk",
    )
    s.add_argument(
        "--paths", nargs="+", metavar="PATH", help="planned paths or globs: the route, whether a Spec comes first, the edit's level, and the first step"
    )
    s.add_argument("--command", dest="command_line", metavar="LINE", help='a shell command line, such as "git push --force origin main"')
    s.add_argument("--action", metavar="ID", help="an action, such as pr.merge (`aidd risk --list` lists them)")
    flag(s, "--list", "every rule in force, the areas, and the actions, with where each rule comes from")
    flag(s, "--suggest", "the ask rules that got a yes every time, at least 10 times in the records, for actions a person can undo: rules to consider lowering")
    s.add_argument("--change-type", default="feat", choices=arguments.CHANGE_TYPES, help="with --paths: the change type")
    flag(s, "--irreversible", "with --paths: a revert would not restore the prior state (makes the route major)")
    s.add_argument("--area", help="with --action: the area it touches, such as payments")
    s.add_argument("--branch", choices=["own", "default", "shared"], help="with --command or --action: the branch it reaches (default: read from git)")
    s.add_argument(
        "--folder",
        metavar="PATH",
        help="with --command: the folder it runs in, when that is not this one, whose branch is read from git; no git checkout there asks",
    )
    s.add_argument("--role", help="with --command or --action: the aidd-team role that acts")
    flag(s, "--json", "print it as JSON (schemas/risk.schema.json)")


def add_delegate(cmd, flag) -> None:
    s = cmd(
        "delegate",
        "a standing delegation: `check` says whether a delegated ask may go to the delegate, recomputed from git, the default branch's "
        "config, and the platform (exit 0 eligible, 1 defer); `packet` is what the delegate reads; `hook` is Claude Code's hook; `stop` "
        "turns the delegation off in this clone",
        "delegate:cmd_delegate",
    )
    s.add_argument(
        "delegate_command",
        choices=["check", "packet", "hook", "stop"],
        metavar="check|packet|hook|stop",
        help="check: whether the ask may go to aidd-team:delegate; packet: what the delegate reads; hook: Claude Code's PermissionRequest "
        "and PreToolUse hook, on stdin; stop: every delegated ask goes to the person",
    )
    s.add_argument("--action", metavar="ID", help="the delegated action, such as pr.merge")
    s.add_argument("--command", dest="command_line", metavar="LINE", help="the exact command the action runs; the check gives it back with its trailers")
    s.add_argument("--head", metavar="SHA", help="the full commit id of the head the action covers")
    s.add_argument("--spec", metavar="ID", help="with spec.approve: the Spec, such as SPEC-4")
    s.add_argument("--cwd", metavar="DIR", help="the folder the command runs in (default: this one)")
    flag(s, "--json", "print it as JSON (schemas/delegate-check.schema.json)")


def add_records(cmd, flag) -> None:
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


def add_recall(cmd, flag) -> None:
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


# The types `aidd new --help` names: the work items, then the six documents a Spec links most, one for each role that
# writes most (the architect's three, the security engineer's, the designer's, and the SRE's). `--list` names the rest.
NEW_WORK_ITEMS = ("spec", "intent", "proposal")
NEW_COMMON_DOCS = ("tech-spec", "adr", "api", "threat-model", "design-spec", "runbook")


def new_types() -> list[str]:
    """Every type `aidd new` writes, in the order its choices list them."""
    return [*NEW_WORK_ITEMS, "runbook", "postmortem", *(k for k in workitems.DOC_TYPES_NEW if k != "runbook"), "product-prototype"]


def new_type_groups() -> list[tuple[str, list[str]]]:
    """Every type `aidd new` writes, grouped by what it is, in the order `aidd new --list` prints them."""
    return [
        ("work items", list(NEW_WORK_ITEMS)),
        ("operations", ["runbook", "postmortem"]),
        ("documents a Spec links", [k for k in workitems.DOC_TEMPLATES if k not in workitems.UNLINKED_DOCS]),
        ("living documents that stand alone", [k for k in workitems.DOC_TEMPLATES if k in workitems.UNLINKED_DOCS]),
        ("the repository's one of each", [*workitems.REPO_DOCS, "product-prototype"]),
        ("a proposal's contract", ["contract"]),
        ("a choice between directions", ["exploration"]),
    ]


class _ListTypes(argparse.Action):
    """`aidd new --list`: print every type and stop, as `--help` does, so the type stays a required argument."""

    def __init__(self, option_strings, dest, **kwargs) -> None:
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        lines = [f"{group}: {', '.join(types)}" for group, types in new_type_groups()]
        print("\n".join([*lines, "`aidd help new` gives the flags each type takes."]))
        parser.exit(0)


def add_new(cmd, flag) -> None:
    s = cmd(
        "new",
        "create a work item or a document from its template. A document a Spec links is added to the Spec's `docs`; `aidd new --list` lists every type",
        "work:cmd_new",
    )
    s.add_argument(
        "type",
        choices=new_types(),
        metavar="TYPE",
        help=f"a work item ({', '.join(NEW_WORK_ITEMS)}), or a document a Spec links, most often {', '.join(NEW_COMMON_DOCS)}; `--list` lists every type",
    )
    s.add_argument(
        "id",
        nargs="?",
        help='such as SPEC-42, or for a Spec, Intent, or Proposal its title (`aidd new spec "Add a discount"`), which takes the next '
        "free id; for a linked document, its topic, such as rate-limits; a contract's proposal id; an exploration's folder; none for a repository document",
    )
    s.add_argument(
        "--title",
        help="a Spec's, Intent's, Proposal's, runbook's, or postmortem's title (or give it in place of the id); an exploration's question; a document's default is its topic",
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
        help="spec: the paths or globs the change will touch; computes the route (as `aidd risk --paths` does) and writes them as the Task's scope, all but one that would hold the acceptance tests, such as a bare tests/",
    )
    s.add_argument("--dimension", action="append", choices=arguments.DIMENSIONS, help="spec: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "spec: a revert would not restore the prior state (forces major)")
    flag(s, "--force", "product-prototype: refused; a linked document: write it again")
    flag(
        s,
        "--full",
        "spec and design-spec: every section. A Spec adds Problem, Goals, Non-goals, and Learn; by default a normal Spec is the "
        "short one (Intent, Context, Acceptance, Design, Concerns, Policy conflicts, Rollback), and so is a major one on the solo profile; "
        "alternatives and the pre-mortem live in the tech spec it links. On solo, a design spec is its light variant by default",
    )
    s.add_argument("--owner-team", default="", help="default: owners.default_owner_team from the config")
    s.add_argument("--parent", default="", help="the parent's id: the Intent whose slice a Spec delivers")
    _add_new_document_flags(s, flag)
    s.add_argument("--list", action=_ListTypes, help="list every type `aidd new` writes, grouped by what it is, and write nothing")


def _add_new_document_flags(s, flag) -> None:
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


def add_test(cmd, flag) -> None:
    s = cmd("test", "run the tests (green on head, red on base) and write evidence", "work:cmd_test")
    s.add_argument("--base", help="the base branch to compare with (default: the default branch)")
    s.add_argument("--spec", help="the Spec whose tests to run, by path or id (default: the one Spec in the diff)")
    s.add_argument("--out", default=config.EVIDENCE_DIR, help="where evidence.json and logs go")
    flag(s, "--no-red", "skip red runs (the final run on the head should include them)")
    flag(s, "--red-in-place", "CI only: run red in this checkout, keeping installed dependencies")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=arguments.PASS_ENV_HELP)
    flag(s, "--changed", "run only the commands the working tree's changes select, green only; the evidence is marked partial")
    flag(s, "--watch", "run --changed now and again whenever a file changes, until Ctrl-C (exit 0)")


def add_validate(cmd, flag) -> None:
    s = cmd("validate", "validate the repository, or the files given", "reading:cmd_validate")
    s.add_argument("paths", nargs="*", metavar="PATH", help="files or folders (default: the whole repository)")
    flag(s, "--json", "print the errors and warnings as JSON (schemas/validate.schema.json)")


def add_explain(cmd, flag) -> None:
    s = cmd(
        "explain",
        "say what one of aidd's words means and why it matters: an action, an area, a route, a lane, a stage, a loop step, a gate, a decision, a role, "
        "a document type, a status, or a profile, read from the data that owns it",
        "reading:cmd_explain",
    )
    s.add_argument("word", nargs="*", metavar="WORD", help="the word, such as pr.merge, major, Specify, verifier, tech-spec, in_progress, or solo")
    flag(s, "--list", "list every word it knows, by kind")
    flag(s, "--json", "print it as JSON (schemas/explain.schema.json)")


def add_explore(cmd, flag) -> None:
    s = cmd(
        "explore",
        "render an exploration's one comparison page: two or three divergent directions side by side, the trade-offs under each, and "
        "each round's screenshots; the owning role writes the pick and its reason in the Spec, DESIGN.md, or an ADR",
        "work:cmd_explore",
    )
    s.add_argument("folder", help="the exploration's folder, such as specs/SPEC-12/explore/split-bill")
    s.add_argument("--out", metavar="PATH", help="where to write the page (default: .aidd/views/explore-<folder>.html)")


def add_prototype(cmd, flag) -> None:
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


def add_eval(cmd, flag) -> None:
    s = cmd(
        "eval",
        "run an agent routing eval, the role evals, the standards check, the pack and practice template check, or your own agent tasks; report and compare recorded runs; "
        "read a repository's work history (work)",
        "maintain:cmd_eval",
    )
    s.add_argument("suite", choices=["routing", "roles", "standards", "packs", "tasks", "report", "transcript", "compare", "work"])
    s.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="report: JSON-lines files written with --record, printed as one markdown table; transcript: one recorded event stream, read as JSON; "
        "compare: two such files, A then B, whose latest runs it compares",
    )
    s.add_argument(
        "--root",
        help="routing, roles: the aidd source checkout (default: this installation's source, if any); tasks, work: your repository (default: .)",
    )
    s.add_argument("--scenarios", help="directory of scenario .yaml files")
    s.add_argument("--agent-command", help='agent command that reads a prompt on stdin, such as "claude -p"')
    s.add_argument(
        "--case", action="append", metavar="ID", help="routing, roles, tasks: run only the case with this id; repeat it for more (default: every case)"
    )
    flag(s, "--no-embed", "routing: ask the agent to load the skill by name instead of embedding its text")
    flag(s, "--with-skills", "roles: also send the aidd skill and the skills each agent file preloads, the full material, to compare with the agent file alone")
    s.add_argument(
        "--min-accuracy", type=float, default=0.9, help="fail below this mean pass@1: the share of correct routes, passed role scenarios, or passed tasks"
    )
    s.add_argument("--repeat", type=int, default=1, metavar="K", help="routing, roles, tasks: run each scenario K times; report pass@1 and pass^K")
    s.add_argument("--max-output-tokens", type=int, metavar="N", help="routing, roles, tasks: stop a trial past N output tokens; it is not scored")
    s.add_argument("--min-pass-k", type=float, metavar="SHARE", help="routing, roles, tasks, with --repeat 2+: also fail below this share of pass^K cases")
    flag(
        s,
        "--without-aidd",
        "routing, roles: also run every scenario without the aidd material (the skill reference, the role playbook) and report the lift; it never blocks",
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
        "packs: print each pack's and practice skill's estimated size, and the problems, as JSON; work: print the reading as JSON",
    )
    s.add_argument("--timeout", type=float, default=15.0, metavar="SECONDS", help="standards --online: each request's timeout")
    s.add_argument("--max-seconds", type=float, default=600.0, metavar="SECONDS", help="standards --online: the whole run's time cap")
    s.add_argument("--max-bytes", type=int, default=3_000_000, metavar="N", help="standards --online: the most bytes read from one page")
    s.add_argument("--concurrency", type=int, default=2, choices=[1, 2], help="standards --online: requests in flight (one per host)")


def add_mcp(cmd, flag) -> None:
    cmd(
        "mcp",
        "serve aidd to agents as MCP tools over stdio: the risk level of an action, the open work, validation, records, and a search of what the team wrote",
        "maintain:cmd_mcp",
    )


def add_gen_docs(cmd, flag) -> None:
    s = cmd("gen-docs", "maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills", "maintain:cmd_gen_docs")
    flag(s, "--check", "fail when any generated block is stale")


# `help` is added by parser.py, beside `cmd_help`: parser.py imports this module, so this module cannot import it back.
ADD_COMMAND = {
    "init": add_init,
    "upgrade": add_upgrade,
    "self-update": add_self_update,
    "uninstall": add_uninstall,
    "doctor": add_doctor,
    "standard": add_standard,
    "status": add_status,
    "risk": add_risk,
    "records": add_records,
    "delegate": add_delegate,
    "recall": add_recall,
    "new": add_new,
    "test": add_test,
    "validate": add_validate,
    "explain": add_explain,
    "explore": add_explore,
    "prototype": add_prototype,
    "eval": add_eval,
    "mcp": add_mcp,
    "gen-docs": add_gen_docs,
}
