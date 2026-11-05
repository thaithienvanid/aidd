"""The Setup commands: init, upgrade, self-update, uninstall, doctor, and standard."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Literal

from aidd import config, knowledge, setup
from aidd.cli import arguments
from aidd.kernel import command_names, documents, git, regular_files
from aidd.kernel.processes import assignment_problem, split_command

# What `aidd eval standards` measures, printed with its counts.
STANDARDS_BASIS = (
    "A checked entry names its source and a sentence read there on its date. That proves the source was read, "
    "not that the practice matches the edition. So the count is not that many independent verifications."
)
# What `aidd eval packs` measures, printed with its counts.
PACKS_BASIS = (
    "tokens are estimated at four characters a token. The limits are 3,000 a pack, 2,500 a practice skill, and 2,500 a reference. "
    "A pack has at most two references, and a practice skill three. A description has at most 250 characters (the aidd-team router 460)"
)
RERUN_NEXT = (
    "aidd was already set up here, so init kept your config and filled in only what was missing.\n"
    "Next: run `aidd doctor`, look over `git status`, and commit anything init changed as an ordinary change."
)
_KEPT_EXISTING = re.compile(r"kept     (\S+) \(exists; --force replaces it\)")


def _at_a_persons_terminal() -> bool:
    """Whether a person, not an agent, a pipe, or CI, runs this at an interactive terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("CI") and not any(os.environ.get(v) for v in config.AGENT_ENV)


def _ask(question: str, default: str) -> str:
    try:
        answer = input(f"{question} [{default}] " if default else f"{question} ").strip()
    except EOFError:
        answer = ""
    return answer or default


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
    # A path or a name read from the repository may hold a control character: each line shows it as a space.
    return ["\n".join(documents.one_line(part, 4000) for part in line.split("\n")) for line in out]


def _existing_config(root: Path) -> dict | None:
    """The config init keeps (it never replaces one without --force), read for its profile and approvers."""
    path = root / config.CONFIG_PATH
    if not path.is_file():
        return None
    try:
        data = documents.parse_yaml(regular_files.repository_text(root, config.CONFIG_PATH, documents.MAX_DOCUMENT_BYTES) or "", str(path))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _profile_in_force(root: Path, existing: dict | None) -> tuple[str | None, str]:
    """The profile the config here has after its parents merge, and, when a parent locks it, the parents that could (`extends`
    paths or URLs): a locked `team` stays `team`, whatever the config itself says. Unmerged (no config, or one that does not
    load), it is the config's own profile and no parent."""
    own = existing.get("profile") if existing else None
    if not existing or not existing.get("extends") and not os.environ.get("AIDD_ORG_PRESET"):
        return own, ""
    try:
        merged = config.load_file(config.CONFIG_PATH, str(root), skip_unread=True)
    except (config.ConfigError, OSError, RuntimeError):
        return own, ""
    held = "profile" in merged.get("locks", default=[]) and "profile" not in (existing.get("locks") or [])
    parents = [str(e.get("path") or e.get("url")) for e in existing.get("extends") or [] if isinstance(e, dict)]
    return merged.profile, (", ".join(parents) or "the org preset") if held else ""


def _take_profile_in_force(args, root: Path, existing: dict | None) -> int | None:
    """Without `--profile`, the profile the config has after its parents merge; with one that a parent's lock contradicts, the
    exit code of a refusal, said on stderr, that names both values and the parents."""
    profile, locked_by = _profile_in_force(root, existing)
    if locked_by and args.profile not in (None, profile):
        print(
            f"error: --profile {args.profile} conflicts with profile {profile}, which a parent config locks ({locked_by}). "
            "Drop --profile, or change the profile in the parent config",
            file=sys.stderr,
        )
        return 2
    if args.profile is None and profile in config.PROFILES:
        args.profile = profile
    return None


def _say_the_test_command(args, fresh: bool, detected: list[str] | None) -> None:
    """Which test command a real run of `init` binds, when it writes a config of its own."""
    if args.dry_run or not fresh:
        return
    if detected:
        print(f"detected the test command: {' '.join(detected)} (pass --test to choose another)")
    elif not args.test:
        print(
            "found no test command: bound a smoke test in `tests`, which checks that every tracked Python file parses and that no file\n"
            "holds a conflict marker. Replace it with your real suite later, or now with --test"
        )


def _init_options(args, root: Path, found: dict) -> tuple[setup.InitOptions, dict | None] | int:
    """What `aidd init` was asked for, checked the same for a real run and a dry run, and the config it keeps (none under
    `--force`); or the exit code of a refusal, said on stderr. Only a real run asks the profile at a terminal."""
    if args.test and (why := assignment_problem(split_command(args.test))):
        print(f"error: the --test command cannot start: {why}", file=sys.stderr)
        return 2
    environments = arguments.environments(args.environment, args.own_environment)  # a bad one stops here, before init prints or writes anything
    harnesses = arguments.harnesses(args.harness)  # so does a bad --harness
    existing = _existing_config(root)
    kept = None if args.force else existing
    given = {n for n, flag in (("profile", args.profile), ("approvers", args.approvers), ("specialists", args.specialist), ("test", args.test)) if flag}
    given |= {n for n, flag in (("environments", args.environment or args.own_environment), ("delegate", args.delegate)) if flag}
    given |= {"compliance_targets"} if args.compliance_target else set()
    if (refused := _take_profile_in_force(args, root, existing)) is not None:
        return refused
    if args.profile is None and not args.dry_run and _at_a_persons_terminal():
        args.profile = _ask(f"Profile ({', '.join(config.PROFILES)}): solo is one person deciding, team is several", "solo")
        given.add("profile")
        if args.profile not in config.PROFILES:
            print(f"error: no profile `{args.profile}`; choose one of {', '.join(config.PROFILES)}", file=sys.stderr)
            return 2
    args.profile = args.profile or "solo"
    args.ref = setup.full_ref(args.ref) if args.ref else args.ref
    setup.pin_workflow("", args.ref)  # a bad --ref stops here, before init writes anything
    detected_test = next((t["test"] for t in found["tests"] if t["path"] == "."), None) if not args.test else None
    _say_the_test_command(args, kept is None, detected_test)
    ci = args.ci or ("github" if found["remotes"] else "none")
    if args.security_ci and ci == "none":
        why = "you gave --ci none" if args.ci else "this repository has no git remote, so init writes no CI files"
        print(f"note: {why}, so --security-ci writes nothing. Add `--ci github` or `--ci gitlab` to write the security CI.", file=sys.stderr)
    options = setup.InitOptions(
        profile=args.profile,
        ci=ci,
        links=list(dict.fromkeys(args.link or [])),
        skill=not args.no_skill,
        force=args.force,
        approvers=arguments.approvers(args.approvers),
        specialists=arguments.specialists(args.specialist),
        test=split_command(args.test) if args.test else (detected_test or setup.SMOKE_TEST),
        aidd_team=args.aidd_team,
        harnesses=harnesses,
        claude_plugins=args.claude_plugins,
        ref=args.ref,
        devcontainer=args.devcontainer,
        risk_areas=found["risk_areas"],
        stack=setup.stack_radar(found),
        ui=not found["no_ui"],
        existing_code=found["existing_code"],
        compliance_targets=list(dict.fromkeys(args.compliance_target or [])) or None,
        security_ci=args.security_ci,
        delegate=args.delegate,
        environments=environments,
        detected=found,
        given=frozenset(given),
    )
    return options, kept


def _existing_root(path: str | None, command: Literal["upgrade", "uninstall", "doctor"]) -> Path:
    """The folder a command works on when it needs a repository that is already there: `arguments.setup_root`, and a directory."""
    root = arguments.setup_root(path, command)
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory: name the repository's top folder, or leave the path out to use the repository you are in")
    if command != "doctor" and git.repository_top(str(root)) is None:  # a folder in no repository is no root to write into; doctor says so itself
        raise arguments.NoRepositoryError(git.no_repository_problem(command))
    return root


def cmd_init(args) -> int:
    root = arguments.setup_root(args.path, "init")  # absolute: the safe reader and writer take paths under an absolute root
    if not root.is_dir():
        typed = ["--approvers"] * bool(args.approvers) + ["--specialist"] * bool(args.specialist)
        print(f"error: {root} is not a directory.{arguments.stray_person_hint(args.path or '.', typed)}", file=sys.stderr)
        return 2
    if git.repository_top(str(root)) is None:  # no repository: a real run would write a setup that every other command refuses
        if not args.dry_run:
            raise arguments.NoRepositoryError(git.no_repository_problem("init"))
        print(f"note: {git.no_repository_problem('init')}", file=sys.stderr)
    found = setup.detect(root)
    prepared = _init_options(args, root, found)
    if isinstance(prepared, int):
        return prepared
    options, kept = prepared
    if args.dry_run:  # the real init, with every write held: the same lines and the same config as a real run
        plan = setup.plan_init(root, options)
        print(setup.detection_markdown(found, plan.config, _shown(setup.dry_run_lines(plan.actions)), plan.config_heading), end="")
        return 0
    wired = options.harnesses if options.harnesses is not None else setup.init_harnesses(root)
    actions = setup.init(root, options)
    for line in _shown(actions):
        print(line)
    if args.ci is None and not found["remotes"]:
        print("no CI: this repository has no git remote, so init wrote no CI files. Add them later with `aidd init --ci github` or `--ci gitlab`")
    if agents := setup.agents_to_restart(actions, root, wired):
        print(f"\n{setup.restart_notice(agents, actions)}")
    if kept is not None:
        print(f"\n{RERUN_NEXT}")
    else:
        print(
            "\nNext: check `tests` and `risks` in .aidd/config.yaml, run `aidd doctor`, and commit the setup as its own change.\n"
            "From then on, agents ask before each risky step: `aidd risk --list` shows which, and the config changes them."
        )
    if kept is None and (fit := setup.found_to_fit({**found, "risk_areas": []})):
        print(f"It also found {'; '.join(fit)}: `aidd init --dry-run` shows the config it proposes for them.")
    return 0


def cmd_upgrade(args) -> int:
    """Bring a repository's aidd files up to this aidd, in one change; a dry run unless --yes."""
    try:
        actions = setup.upgrade(_existing_root(args.path, "upgrade"), ref=setup.full_ref(args.ref) if args.ref else args.ref, yes=args.yes, only=args.only)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in actions:
        print(documents.one_line(line, 2000))  # a file name in a line can hold control characters
    if not args.yes and not actions[0].startswith("nothing to update"):
        print("\ndry run: nothing changed. Run again with --yes, then `aidd doctor`, and commit it as one change.")
    if not args.only:  # the CLI and the plugins are not the ask rules
        print("\nThe CLI itself: `aidd self-update`.")
        print(
            "The Claude Code plugins: `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`, `aidd-cli@aidd`, `aidd-team@aidd`, and `aidd-packs@aidd`."
        )
    if left := [a for a in actions if a.startswith(setup.UPGRADE_PROBLEM)]:
        sys.stdout.flush()
        print(
            f"aidd upgrade wrote what it could, and {len(left)} problem(s) remain (the `problem` lines above). Fix each one, then run `aidd validate`.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_self_update(args) -> int:
    code, lines = setup.self_update(dry_run=args.dry_run, main=args.main)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


def cmd_uninstall(args) -> int:
    for line in setup.uninstall(_existing_root(args.path, "uninstall"), links=args.link or [], yes=args.yes):
        print(line)
    return 0


def cmd_doctor(args) -> int:
    results = setup.doctor(_existing_root(args.path, "doctor"), execute=True)
    if args.json:
        shown = {"schema_version": arguments.JSON_SCHEMA_VERSION, "passed": not any(result == "fail" for result, _ in results)}
        shown["checks"] = [{"result": result, "message": msg} for result, msg in results]
        shown["findings"] = setup.doctor_findings(results)
        print(json.dumps(shown, indent=2))
        return 0 if shown["passed"] else 1
    for result, msg in results:
        print(f"[{result:4}] {msg}")
    return 1 if any(result == "fail" for result, _ in results) else 0


def cmd_standard(args) -> int:
    """`aidd standard [add]`: the open choices and the library, or its stacks (`--stacks`); or a copy of library
    standards, or of a stack's (`--stack`), in this repository."""
    if (args.stack or args.ids) and args.standard_command != "add":  # they name what to copy, and a list would ignore them without a word
        # what the person typed is text, so it joins the command only as a plain name (kernel.command_names), else as a placeholder
        flag = "--stack" if args.stack else "an id"
        named = f"--stack {command_names.quoted(args.stack) or '<name>'}" if args.stack else " ".join(command_names.quoted(i) or "<id>" for i in args.ids)
        raise ValueError(
            f"{flag} names what `add` copies, so it goes with add: run `aidd standard add {named}`. "
            "`aidd standard --stacks` lists the stacks, and `aidd standard` the standards"
        )
    arguments.enter_repo(args, outside_ok=args.standard_command != "add")  # the library reads no repository; a copy goes into one
    if args.standard_command == "add":
        if not args.ids and not args.stack:
            raise ValueError("name what to add: library ids, such as python/ruff-lint-format, or `--stack <name>`, such as python-cli")
        for line in knowledge.add_standards(Path("."), args.ids, stack=args.stack):
            print(line)
        print("Review the copies and the config as one change. Never edit a copy: `aidd doctor` reports one that changed.")
        return 0
    if args.stacks:
        data = knowledge.stack_rows(arguments.config_or_none())
        if args.json:
            print(json.dumps(data, indent=2))
            return 0
        for s in data["stacks"]:
            extends = f" (extends {s['extends']})" if s["extends"] else ""
            allowed = "" if s["allowed"] else " [not allowed by the company's policy]"
            print(f"{s['name']}{extends}: {s['description']}{allowed}\n  standards: {', '.join(s['standards'])}")
        return 0
    data = knowledge.standard_rows(arguments.config_or_none())
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print("Open choices (a pack or practice skill leaves them to the team; aidd's default holds until a standard fills one):")
    for c in data["open_choices"]:
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
        print(f"  {s['id']}: fills {', '.join(s['fills'])}; {tool}" + (f" [{', '.join(marks)}]" if marks else ""))
    return 0


__all__ = ["cmd_doctor", "cmd_init", "cmd_self_update", "cmd_standard", "cmd_uninstall", "cmd_upgrade", "git"]
