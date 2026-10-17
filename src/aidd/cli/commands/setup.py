"""The Setup commands: init, upgrade, uninstall, doctor, standard, and stack."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aidd import gate, knowledge, platforms, setup
from aidd.cli import arguments
from aidd.kernel import git
from aidd.kernel.processes import split_command

# What a green `aidd eval standards` proves, printed with the count so nobody reads it as more.
STANDARDS_BASIS = (
    "A checked entry names its source and a sentence read there on its date. That proves the source was read, "
    "not that the practice matches the edition. So the count is not that many independent verifications."
)
# What `aidd eval packs` measures, printed with its counts.
PACKS_BASIS = (
    "tokens are estimated at four characters a token. The caps are 2,200 a pack, 1,600 a practice skill, and 1,500 a reference. "
    "A pack has at most two references, and a practice skill three. A description has at most 250 characters (the aidd-team router 460)"
)


# The Day-0 commit, as the agent runbook (llms-install.md, step 4) gives it: an agent commits the setup on a branch.
DAY_0_COMMIT = "Commit this setup on the branch `chore/adopt-aidd`. An agent adds its `Assisted-by:` trailer to the commit."
# A repository with no commit has no base branch to branch from: the Day-0 commit is a person's, and the agent stops.
DAY_0_NEW_REPOSITORY = (
    "New repository: a person makes the Day-0 commit, this setup and the project scaffold, on the default branch. "
    "An agent does not commit it: it stops here and hands back."
)


def cmd_init(args) -> int:

    root = Path(args.path)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    found = setup.detect(root)
    if args.dry_run:
        print(setup.detection_markdown(found), end="")
        return 0
    args.approvers = arguments.approvers(args.approvers)
    if not args.approvers and args.profile != "solo":
        # An empty owners.approvers fails every change closed; under solo init names the operator, elsewhere nobody can guess.
        print(
            f"error: profile {args.profile} needs the humans who may approve. Pass --approvers, such as:\n"
            f"  aidd init --profile {args.profile} --approvers @your-org/leads\n"
            "An approver is a user (@alice), a team (@org/team), or email:you@example.com for local-first approvals.\n"
            "`aidd init --dry-run` writes nothing.",
            file=sys.stderr,
        )
        return 2
    links = list(dict.fromkeys(args.link or []))
    setup.pin_workflow("", args.ref)  # a bad --ref stops here, before init writes anything
    # Without --test, the suite detected at the repository root; a monorepo's per-package suites stay a suggestion.
    detected_test = next((t["test"] for t in found["tests"] if t["path"] == "."), None) if not args.test else None
    if detected_test:
        print(f"detected the test command: {' '.join(detected_test)} (pass --test to choose another)")
    elif not args.test:
        # Every change fails `tests` until a suite exists, and adding one later is a config change (major): bind a smoke test now.
        print(
            "found no test command: bound a smoke test in `tests`, so the first change has a suite to pass.\n"
            "The smoke test checks that every tracked Python file parses and that no file holds a conflict marker.\n"
            "Replace it with your real suite later, or now with --test"
        )
    harnesses = None if not args.harness else [h for h in args.harness if h != "none"]
    if harnesses is None and "claude-code" in setup.installed_harnesses() and "claude-code" not in setup.detect_harnesses(root):
        # The hint init would print, asked instead, of a person at a terminal: wire Claude Code now, in one step.
        if _person_says_yes("This machine has Claude Code. Wire it in this repository too (hooks, MCP, the skill)?"):
            harnesses = [*setup.detect_harnesses(root), "claude-code"]
    in_git = bool(git.run(["rev-parse", "--is-inside-work-tree"], str(root), check=False).strip())
    before = set(git.dirty(str(root), untracked=True, check=False)) if in_git else set()
    actions = setup.init(
        root,
        setup.InitOptions(
            profile=args.profile,
            ci=args.ci,
            links=links,
            skill=not args.no_skill,
            force=args.force,
            approvers=args.approvers,
            specialists=arguments.specialists(args.specialist),
            test=split_command(args.test) if args.test else (detected_test or setup.SMOKE_TEST),
            policy=split_command(args.policy) if args.policy else None,
            goal=args.goal,
            enforce=args.enforce,
            agent_hooks=True if args.agent_hooks else (False if args.no_agent_hooks else None),
            team=args.team,
            harnesses=harnesses,
            claude_plugins=args.claude_plugins,
            mods=args.mods,
            ref=args.ref,
            devcontainer=args.devcontainer,
            risk_rules=found["risk_rules"],
            stack=setup.stack_radar(found),
            ui=not found["no_ui"],
            existing_code=found["existing_code"],
            compliance_targets=list(dict.fromkeys(args.compliance_target or [])) or None,
            security_ci=args.security_ci,
            held_commands=found["held_commands"],
            not_held=found["not_held"],
        ),
    )
    for line in actions:
        print(line)
    if setup.wrote_claude_code_files(actions, root):
        print(f"\n{setup.RESTART_NOTICE}")
    if not git.run(["rev-parse", "--verify", "--quiet", "HEAD"], str(root), check=False).strip():
        # Greenfield: nothing is on the default branch yet, so nothing can be gated.
        print(
            f"\n{DAY_0_NEW_REPOSITORY}\n"
            "Then run `aidd doctor`. Every later change goes through a branch.\n"
            "The first Spec usually brings the test runner and the first test."
        )
    elif gate.platform_of(str(root)) == "local" or args.ci == "none":
        print(
            "\nNext: check owners, `tests`, and `risk_rules` in .aidd/config.yaml, and run `aidd doctor`.\n"
            f"{DAY_0_COMMIT}\n"
            "A person then lands that Day-0 commit on the base branch. They run `git merge --ff-only chore/adopt-aidd` there.\n"
            "It is the one change that lands without `aidd ship`. The agent hook keeps agents off the base branch.\n"
            "Every later change goes through a branch, `aidd test`, and `aidd ship`."
        )
    else:
        print(
            "\nNext: check owners and `tests` in .aidd/config.yaml, and run `aidd doctor`.\n"
            f"{DAY_0_COMMIT} Then open the setup PR/MR.\n"
            "A person merges the setup PR/MR."
        )
    if fit := setup.found_to_fit({**found, "risk_rules": []}):
        print(f"It also found {'; '.join(fit)}: `aidd init --dry-run` shows the config it proposes for them.")
    if not args.enforce and args.ci != "none":
        print(
            "The gate starts in advisory mode: it reports on 'aidd/gate (advisory)' and blocks nothing. Read `aidd metrics`\n"
            "for a week or two. Then set `mode: enforce` in .aidd/config.yaml, and require aidd/gate. The base branch's\n"
            "config wins over the CI file's input, on GitHub and GitLab alike."
        )
    if in_git:
        _offer_day0_commit(root, before)
    return 0


DAY_0_BRANCH = "chore/adopt-aidd"


def _person_says_yes(question: str) -> bool:
    """A person at an interactive terminal no agent started answers `question`, Enter meaning yes; an agent's shell,
    a pipe, or CI is never asked, and gets the written steps instead."""
    try:
        platforms.check_terminal("A question during aidd init")
        answer = input(f"{question} [Y/n] ").strip().lower()
    except (platforms.NotAPerson, EOFError):
        return False
    return answer in ("", "y", "yes")


def _offer_day0_commit(root: Path, before: set[str]) -> None:
    """At a person's terminal: commit what init wrote (the paths it changed, never one that was dirty before) as the
    Day-0 commit, on `chore/adopt-aidd` when the repository has a commit, else on its first branch."""
    wrote = sorted(set(git.dirty(str(root), untracked=True, check=False)) - before)
    if not wrote or not _person_says_yes(f"Commit this setup now ({len(wrote)} file{'' if len(wrote) == 1 else 's'})?"):
        return
    cwd = str(root)
    has_head = bool(git.run(["rev-parse", "--verify", "--quiet", "HEAD"], cwd, check=False).strip())
    base = git.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd, check=False).strip() if has_head else ""
    try:
        if has_head and base != DAY_0_BRANCH:
            git.run(["switch", "-c", DAY_0_BRANCH], cwd)
        else:
            base = "<your base branch>"
        git.run(["add", "--", *wrote], cwd)
        git.run(["commit", "-q", "-m", "chore: adopt aidd"], cwd)
    except git.GitError as exc:
        print(f"Not committed: {exc}. Commit the setup yourself, as above.", file=sys.stderr)
        return
    if not has_head:
        print("Committed the Day-0 commit. Every later change goes through a branch.")
    elif gate.platform_of(cwd) == "local":
        print(f"Committed on {DAY_0_BRANCH}. Land it yourself: git switch {base} && git merge --ff-only {DAY_0_BRANCH}")
    else:
        print(f"Committed on {DAY_0_BRANCH}. Push it and open the setup PR/MR: git push -u origin {DAY_0_BRANCH}")


def cmd_upgrade(args) -> int:
    """Bring a repository's aidd files up to this aidd, in one change; a dry run unless --yes."""
    try:
        actions = setup.upgrade(Path(args.path), ref=args.ref, yes=args.yes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in actions:
        print(line)
    if not args.yes and not actions[0].startswith("nothing to update"):
        print("\ndry run: nothing changed. Run again with --yes, then `aidd doctor`, and merge it as one change; it touches")
        print("protected paths, so the gate treats it as major.")
    print("\nThe CLI itself: `aidd self-update`.")
    print("The Claude Code plugins: `claude plugin update aidd@aidd`, `claude plugin update aidd-team@aidd`, and `aidd-mods@aidd`.")
    return 0


def cmd_self_update(args) -> int:
    """Update the CLI to the latest release, verified first; `--main` to the tip of main; `--check` only says what it would do."""
    code, lines = setup.self_update(check_only=args.check, main=args.main)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


def cmd_uninstall(args) -> int:
    for line in setup.uninstall(Path(args.path), links=args.link or [], yes=args.yes):
        print(line)
    return 0


def cmd_standard(args) -> int:
    """`aidd standard list|add`: the open choices and the library, or a copy of library standards in this repository."""
    from aidd import knowledge

    arguments.enter_repo(args)
    if args.standard_command == "add":
        for line in knowledge.add_standards(Path("."), args.ids):
            print(line)
        print("Review the copies and the config as one change. Never edit a copy: `aidd doctor` reports one that changed.")
        return 0
    data = knowledge.standard_rows(arguments.config_or_none())
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print("Open choices (a pack or practice skill leaves them to the team; aidd's default holds until a standard fills one):")
    for c in data["open_choices"]:
        # Where an ecosystem has several options for the choice, name aidd's default among them.
        ecos = [knowledge.standard_ecosystem(sid) for sid in c["filled_by"]]
        names = [
            sid
            + (
                " (default)"
                if ecos.count(knowledge.standard_ecosystem(sid)) > 1 and c["default_by_ecosystem"].get(knowledge.standard_ecosystem(sid)) == sid
                else ""
            )
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
    """`aidd stack list|add`: the library's stacks, or one stack's standards and `project.stack` entries copied here."""
    from aidd import knowledge

    arguments.enter_repo(args)
    if args.stack_command == "add":
        for line in knowledge.add_standards(Path("."), [], stack=args.name):
            print(line)
        print("Review the copies and the config as one change. Never edit a copy: `aidd doctor` reports one that changed.")
        return 0
    data = knowledge.stack_rows(arguments.config_or_none())
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    for s in data["stacks"]:
        extends = f" (extends {s['extends']})" if s["extends"] else ""
        allowed = "" if s["allowed"] else " [not allowed by the company's policy]"
        print(f"{s['name']}{extends}: {s['description']}{allowed}\n  standards: {', '.join(s['standards'])}")
    return 0


def cmd_extensions(args) -> int:
    """`aidd extensions suggest`: the registry's installable extensions that fit the stacks `aidd init --dry-run`
    detects here, with the line a person runs to install each. It installs nothing."""
    arguments.enter_repo(args)
    roles = knowledge.roles()["roles"]
    if args.role and args.role not in roles:
        raise ValueError(f"no such role: {args.role}; one of {', '.join(roles)}")
    stacks = {s["stack"] for s in setup.detect(Path(".")).get("stacks", [])}
    rows = knowledge.suggestions(stacks, args.role)
    if args.json:
        print(json.dumps({"stacks": sorted(stacks), "suggestions": rows}, indent=2))
    else:
        print(knowledge.suggestions_text(rows, stacks), end="")
    return 0


def cmd_doctor(args) -> int:
    if args.json:
        root = Path(args.path)
        results = setup.autopilot_checks(root) if args.autopilot else setup.doctor(root, execute=True)
        shown: dict = {"schema_version": arguments.JSON_SCHEMA_VERSION, "passed": not any(level == "fail" for level, _ in results)}
        shown["checks"] = [{"level": level, "message": msg} for level, msg in results]
        if args.autopilot:
            shown["advisor"] = setup.autopilot_advisor_line(root)
            shown["check_yourself"] = list(setup.AUTOPILOT_CHECKLIST)
        print(json.dumps(shown, indent=2))
        return 0 if shown["passed"] else 1
    if args.autopilot:
        results = setup.autopilot_checks(Path(args.path))
        for level, msg in results:
            print(f"[{level:4}] {msg}")
        print(f"[info] {setup.autopilot_advisor_line(Path(args.path))}")
        print("\n" + setup.AUTOPILOT_CHECKLIST_TITLE)
        for item in setup.AUTOPILOT_CHECKLIST:
            print(f"  [ ] {item}")
        return 1 if any(level == "fail" for level, _ in results) else 0
    results = setup.doctor(Path(args.path), execute=True)
    for level, msg in results:
        print(f"[{level:4}] {msg}")
    return 1 if any(level == "fail" for level, _ in results) else 0
