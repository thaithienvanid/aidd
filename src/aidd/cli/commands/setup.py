"""The Setup commands: init, upgrade, uninstall, doctor, standard, and stack."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from aidd import config, gate, knowledge, platforms, setup
from aidd.cli import arguments
from aidd.kernel import documents, git
from aidd.kernel.processes import assignment_problem, split_command

# What a green `aidd eval standards` proves, printed with the count so nobody reads it as more.
STANDARDS_BASIS = (
    "A checked entry names its source and a sentence read there on its date. That proves the source was read, "
    "not that the practice matches the edition. So the count is not that many independent verifications."
)
# What `aidd eval packs` measures, printed with its counts.
PACKS_BASIS = (
    "tokens are estimated at four characters a token. The caps are 2,200 a pack, 1,700 a practice skill, and 1,600 a reference. "
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
    if args.test and (why := assignment_problem(split_command(args.test))):
        print(f"error: the --test command cannot start: {why}", file=sys.stderr)
        return 2
    if not args.force and (why := _committed_config_gone(root)):
        print(f"error: {why}", file=sys.stderr)
        return 2
    person = _at_a_persons_terminal()
    kept = None if args.force else _existing_config(root)
    if (code := _settle_profile_and_approvers(args, root, kept, person)) is not None:
        return code
    links = list(dict.fromkeys(args.link or []))
    args.ref = setup.full_ref(args.ref) if args.ref else args.ref  # a short SHA pins in full
    setup.pin_workflow("", args.ref)  # a bad --ref stops here, before init writes anything
    # Without --test, the suite detected at the repository root; a monorepo's per-package suites stay a suggestion.
    detected_test = next((t["test"] for t in found["tests"] if t["path"] == "."), None) if not args.test else None
    if kept is not None:
        pass  # the config stays as it is: its `tests` are the ones that count
    elif detected_test:
        print(f"detected the test command: {' '.join(detected_test)} (pass --test to choose another)")
    elif not args.test:
        # Every change fails `tests` until a suite exists, and adding one later is a config change (major): bind a smoke test now.
        print(
            "found no test command: bound a smoke test in `tests`, so the first change has a suite to pass.\n"
            "The smoke test checks that every tracked Python file parses and that no file holds a conflict marker.\n"
            "Replace it with your real suite later, or now with --test"
        )
    harnesses = None if not args.harness else [h for h in args.harness if h != "none"]
    plugin_on = f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled()
    if harnesses is None and not plugin_on and "claude-code" in setup.installed_harnesses() and "claude-code" not in setup.detect_harnesses(root):
        # The hint init would print, asked instead, of a person at a terminal: wire Claude Code now, in one step.
        if _person_says_yes("This machine has Claude Code. Wire it in this repository too (hooks, MCP, the skill)?"):
            harnesses = [*setup.detect_harnesses(root), "claude-code"]
    in_git = bool(git.run(["rev-parse", "--is-inside-work-tree"], str(root), check=False).strip())
    has_head = in_git and bool(git.run(["rev-parse", "--verify", "--quiet", "HEAD"], str(root), check=False).strip())
    current, base = _branches(root) if has_head else ("", "")
    if kept is None and has_head and current != base and not current.startswith(DAY_0_BRANCH):
        print(f"note     you are on `{current or 'a detached HEAD'}`; aidd lands work on `{base}` (`aidd land` merges there), so the setup belongs there")
    before = set(git.dirty(str(root), untracked=True, check=False)) if in_git else set()
    wired = harnesses if harnesses is not None else setup.detect_harnesses(root)  # as init reads them, before it writes
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
            claude_hooks=True if args.claude_hooks else (False if args.no_claude_hooks else None),
            team=args.team,
            harnesses=harnesses,
            claude_plugins=args.claude_plugins,
            mods=args.mods,
            ref=args.ref,
            devcontainer=args.devcontainer,
            orca=args.orca,
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
    for line in _shown(actions):
        print(line)
    if agents := setup.agents_to_restart(actions, root, wired):
        print(f"\n{setup.restart_notice(agents)}")
    local = not gate.trunk_on_platform(str(root)) or args.ci == "none"
    if not has_head:
        # Greenfield: nothing is on the default branch yet, so nothing can be gated.
        print(
            f"\n{DAY_0_NEW_REPOSITORY}\n"
            "Then run `aidd doctor`. Every later change goes through a branch.\n"
            "The first Spec usually brings the test runner and the first test."
        )
    elif kept is not None:
        print(f"\n{RERUN_NEXT}")
    elif person:
        print("\n" + _next_steps(local, current, base))
    elif local:
        print(
            "\nNext: check owners, `tests`, and `risk_rules` in .aidd/config.yaml, and run `aidd doctor`.\n"
            f"{DAY_0_COMMIT}\n"
            "A person then lands that Day-0 commit on the base branch. They run `git merge --ff-only chore/adopt-aidd` there.\n"
            "It is the one change that lands without `aidd land`. The agent hook keeps agents off the base branch.\n"
            "Every later change goes through a branch, `aidd test`, and `aidd land`."
        )
    else:
        print(
            "\nNext: check owners and `tests` in .aidd/config.yaml, and run `aidd doctor`.\n"
            f"{DAY_0_COMMIT} Then open the setup PR/MR.\n"
            "A person merges the setup PR/MR."
        )
    if kept is None and (fit := setup.found_to_fit({**found, "risk_rules": []})):
        print(f"It also found {'; '.join(fit)}: `aidd init --dry-run` shows the config it proposes for them.")
    if kept is None and not args.enforce and args.ci != "none" and config.profile_mode(args.profile) == "advisory":
        print(
            "The gate starts in advisory mode: it reports on 'aidd/gate (advisory)' and blocks nothing.\n"
            "Read `aidd metrics` for a week or two. Then set `mode: enforce` in .aidd/config.yaml, and require aidd/gate.\n"
            "The base branch's config wins over the CI file's input, on GitHub and GitLab alike."
        )
    if in_git and kept is None:
        _offer_day0_commit(root, before, current, base, args.ci)
    return 0


DAY_0_BRANCH = "chore/adopt-aidd"
# Init run again where aidd is already set up: the config stays, and init only fills in what is missing.
RERUN_NEXT = (
    "aidd was already set up here, so init kept your config and filled in only what was missing.\n"
    "Next: run `aidd doctor`, look over `git status`, and commit anything init changed as an ordinary change."
)
# `aidd init`'s lines for a file it kept because it exists, folded into one line when there are several.
_KEPT_EXISTING = re.compile(r"kept     (\S+) \(exists; --force replaces it\)")


def _shown(actions: list[str]) -> list[str]:
    """Init's lines as a person reads them: each line once, and the files it kept because they exist on one line."""
    out: list[str] = []
    kept: list[str] = []
    at = -1
    for line in dict.fromkeys(actions):
        if m := _KEPT_EXISTING.fullmatch(line):
            at = len(out) if at < 0 else at
            kept.append(m.group(1))
            continue
        out.append(line)
    if len(kept) == 1:
        out.insert(at, f"kept     {kept[0]} (exists; --force replaces it)")
    elif kept:
        out.insert(at, f"kept     {len(kept)} files that exist (--force replaces them): {', '.join(kept)}")
    return out


def _at_a_persons_terminal() -> bool:
    """Whether a person, not an agent, a pipe, or CI, runs this init at an interactive terminal."""
    try:
        platforms.check_terminal("aidd init")
    except platforms.NotAPerson:
        return False
    return True


def _existing_config(root: Path) -> dict | None:
    """The config init keeps (it never replaces one without --force), read for its profile and approvers; None when
    there is none. A config it cannot read is kept all the same, and reads as empty."""
    path = root / config.CONFIG_PATH
    if not path.is_file():
        return None
    try:
        data = documents.parse_yaml(path.read_text(encoding="utf-8"), str(path))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _committed_config_gone(root: Path) -> str | None:
    """Why init stops: the config is deleted from the working tree while HEAD still holds it, with its settings. A
    new one would drop them; restoring keeps them."""
    path = config.CONFIG_PATH
    if (root / path).exists() or not git.run(["rev-parse", "--verify", "--quiet", f"HEAD:{path}"], str(root), check=False).strip():
        return None
    return (
        f"{path} is deleted here, but the last commit holds it, with your settings (profile, tests, goal).\n"
        f"Bring it back with `git restore --source=HEAD --staged --worktree {path}`, then run `aidd init` again.\n"
        "`aidd init --force` writes a new one instead."
    )


def _settle_profile_and_approvers(args, root: Path, kept: dict | None, person: bool) -> int | None:
    """The profile and approvers init uses: the flags, else the config it keeps, else, for a person at a terminal, their
    answers, else the `team` profile. None to go on, or the exit code of a stop."""
    owners = (kept or {}).get("owners")
    listed = owners.get("approvers") if isinstance(owners, dict) else None
    if args.profile is None and kept is not None and kept.get("profile") in config.profiles()["order"]:
        args.profile = kept["profile"]
    if args.profile is None and person:
        order = config.profiles()["order"]
        answer = _ask(f"Profile ({', '.join(order)})?", "solo")
        if answer not in order:
            print(f"error: no profile `{answer}`; choose one of {', '.join(order)}", file=sys.stderr)
            return 2
        args.profile = answer
    args.profile = args.profile or "team"
    args.approvers = arguments.approvers(args.approvers)
    if not args.approvers and isinstance(listed, list):
        args.approvers = [str(a) for a in listed]
    if not args.approvers and args.profile != "solo" and person:
        login, email = config.operator_login(root), config.operator_email(root)
        suggested = f"@{login}" if login else f"email:{email}" if email else ""
        answer = _ask("Who may approve? (@user, @org/team, or email:you@example.com)", suggested)
        args.approvers = arguments.approvers(answer.split()) if answer else None
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
    return None


def _ask(question: str, default: str) -> str:
    """A person's answer at the terminal, or `default` on Enter."""
    try:
        answer = input(f"{question} [{default}] " if default else f"{question} ").strip()
    except EOFError:
        answer = ""
    return answer or default


def _branches(root: Path) -> tuple[str, str]:
    """(the branch checked out, the base branch aidd lands work on): the remote's default branch, then main or
    master; with none of them, the branch checked out is the base."""
    current = git.run(["branch", "--show-current"], str(root), check=False).strip()
    try:
        base = git.default_base(str(root)).removeprefix("origin/")
    except git.GitError:
        base = current or "main"
    return current, base


def _next_steps(local: bool, current: str, base: str) -> str:
    """What a person at their terminal does after init, in order."""
    if current != base and not current.startswith(DAY_0_BRANCH):
        commit = f"Commit the setup on `{base}`: switch there first (`git switch {base}`)."
    elif local:
        commit = (
            f"Commit the setup on `{base}`: init offers it now. It is the one change that lands without `aidd land`;"
            " every later change goes through a branch, `aidd test`, and `aidd land`."
        )
    else:
        commit = "Commit the setup on a branch and open its pull request: init offers it now. A person merges it."
    return f"Next:\n  1. Check owners, `tests`, and `risk_rules` in .aidd/config.yaml.\n  2. Run `aidd doctor`.\n  3. {commit}"


def _person_says_yes(question: str) -> bool:
    """A person at an interactive terminal no agent started answers `question`, Enter meaning yes; an agent's shell,
    a pipe, or CI is never asked, and gets the written steps instead."""
    try:
        platforms.check_terminal("A question during aidd init")
        answer = input(f"{question} [Y/n] ").strip().lower()
    except (platforms.NotAPerson, EOFError):
        return False
    return answer in ("", "y", "yes")


def _free_branch(cwd: str) -> str:
    """`chore/adopt-aidd`, or the first of `chore/adopt-aidd-2`, `-3`, ... that no branch has taken."""
    name, n = DAY_0_BRANCH, 2
    while git.run(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], cwd, check=False).strip():
        name, n = f"{DAY_0_BRANCH}-{n}", n + 1
    return name


def _offer_day0_commit(root: Path, before: set[str], current: str, base: str, ci: str) -> None:
    """At a person's terminal: commit what init wrote (the paths it changed, never one that was dirty before) as the
    Day-0 commit. With no platform, on the base branch itself, since no check runs between a setup branch and its
    fast-forward; with one, on a new branch for its pull request. Off the base branch, it is not offered."""
    wrote = sorted(set(git.dirty(str(root), untracked=True, check=False)) - before)
    if not wrote:
        return
    cwd = str(root)
    has_head = bool(base)
    local = not gate.trunk_on_platform(cwd) or ci == "none"
    on_setup_branch = current.startswith(DAY_0_BRANCH)
    if has_head and current != base and not on_setup_branch:
        if _at_a_persons_terminal():
            print(f"Not committed: this is `{current or 'a detached HEAD'}`, not `{base}`. Commit the setup on `{base}`.")
        return
    target = current if not has_head or on_setup_branch or local else _free_branch(cwd)
    where = f"`{target}`" if target == current and target else f"a new branch `{target}`" if target else "the first commit"
    if not _person_says_yes(f"Commit this setup on {where} now ({len(wrote)} file{'' if len(wrote) == 1 else 's'})?"):
        return
    try:
        if has_head and target != current:
            git.run(["switch", "-c", target], cwd)
        git.run(["add", "--", *wrote], cwd)
        git.run(["commit", "-q", "-m", "chore: adopt aidd"], cwd)
    except git.GitError as exc:
        print(f"Not committed: {exc}. Commit the setup yourself.", file=sys.stderr)
        return
    if not has_head:
        print("Committed the Day-0 commit. Every later change goes through a branch.")
    elif local and target == base:
        print(f"Committed on {base}. Every later change goes through a branch, `aidd test`, and `aidd land`.")
    elif local:
        print(f"Committed on {target}. Land it: git switch {base} && git merge --ff-only {target}")
    else:
        opener = "glab mr create --fill" if ci == "gitlab" else "gh pr create --fill"
        print(f"Committed on {target}. Push it and open the setup pull request:\n  git push -u origin {target}\n  {opener}")


def cmd_upgrade(args) -> int:
    """Bring a repository's aidd files up to this aidd, in one change; a dry run unless --yes."""
    try:
        actions = setup.upgrade(Path(args.path), ref=setup.full_ref(args.ref) if args.ref else args.ref, yes=args.yes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in actions:
        print(line)
    if not args.yes and not actions[0].startswith("nothing to update"):
        print("\ndry run: nothing changed. Run again with --yes, then `aidd doctor`, and merge it as one change; it touches")
        print("protected paths, so the gate treats it as major.")
    print("\nThe CLI itself: `aidd self-update`.")
    print(
        "The Claude Code plugins: `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`, `aidd-cli@aidd`, `aidd-team@aidd`, and `aidd-mods@aidd`."
    )
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
    rows, kits = knowledge.suggestions(stacks, args.role), knowledge.toolsets(args.role)
    if args.json:
        print(json.dumps({"stacks": sorted(stacks), "suggestions": rows, "toolsets": kits}, indent=2))
    else:
        print(knowledge.suggestions_text(rows, stacks) + knowledge.toolsets_text(kits), end="")
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
