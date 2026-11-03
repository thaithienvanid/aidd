"""The Setup commands: init, upgrade, self-update, uninstall, doctor, and standard."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from aidd import config, knowledge, setup
from aidd.cli import arguments
from aidd.kernel import documents, git
from aidd.kernel.processes import assignment_problem, split_command

# The environment an agent's shell carries: a question is never asked there.
AGENT_ENV = ("CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE", "ANTIGRAVITY_AGENT", "AI_AGENT", "AIDD_AGENT", "CODEX_SANDBOX", "OPENCODE")
# What `aidd eval standards` measures, printed with its counts.
STANDARDS_BASIS = (
    "A checked entry names its source and a sentence read there on its date. That proves the source was read, "
    "not that the practice matches the edition. So the count is not that many independent verifications."
)
# What `aidd eval packs` measures, printed with its counts.
PACKS_BASIS = (
    "tokens are estimated at four characters a token. The caps are 2,200 a pack, 1,700 a practice skill, and 1,600 a reference. "
    "A pack has at most two references, and a practice skill three. A description has at most 250 characters (the aidd-team router 460)"
)
RERUN_NEXT = (
    "aidd was already set up here, so init kept your config and filled in only what was missing.\n"
    "Next: run `aidd doctor`, look over `git status`, and commit anything init changed as an ordinary change."
)
_KEPT_EXISTING = re.compile(r"kept     (\S+) \(exists; --force replaces it\)")


def _at_a_persons_terminal() -> bool:
    """Whether a person, not an agent, a pipe, or CI, runs this at an interactive terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("CI") and not any(os.environ.get(v) for v in AGENT_ENV)


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
    return out


def _existing_config(root: Path) -> dict | None:
    """The config init keeps (it never replaces one without --force), read for its profile and approvers."""
    path = root / config.CONFIG_PATH
    if not path.is_file():
        return None
    try:
        data = documents.parse_yaml(path.read_text(encoding="utf-8"), str(path))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
    kept = None if args.force else _existing_config(root)
    if args.profile is None and kept is not None and kept.get("profile") in config.PROFILES:
        args.profile = kept["profile"]
    if args.profile is None and _at_a_persons_terminal():
        args.profile = _ask(f"Profile ({', '.join(config.PROFILES)}): solo is one person deciding, team is several", "solo")
        if args.profile not in config.PROFILES:
            print(f"error: no profile `{args.profile}`; choose one of {', '.join(config.PROFILES)}", file=sys.stderr)
            return 2
    args.profile = args.profile or "solo"
    args.ref = setup.full_ref(args.ref) if args.ref else args.ref
    setup.pin_workflow("", args.ref)  # a bad --ref stops here, before init writes anything
    detected_test = next((t["test"] for t in found["tests"] if t["path"] == "."), None) if not args.test else None
    if kept is None and detected_test:
        print(f"detected the test command: {' '.join(detected_test)} (pass --test to choose another)")
    elif kept is None and not args.test:
        print(
            "found no test command: bound a smoke test in `tests`, which checks that every tracked Python file parses and that no file\n"
            "holds a conflict marker. Replace it with your real suite later, or now with --test"
        )
    harnesses = None if not args.harness else [h for h in args.harness if h != "none"]
    wired = harnesses if harnesses is not None else setup.detect_harnesses(root)
    actions = setup.init(
        root,
        setup.InitOptions(
            profile=args.profile,
            ci=args.ci,
            links=list(dict.fromkeys(args.link or [])),
            skill=not args.no_skill,
            force=args.force,
            approvers=arguments.approvers(args.approvers),
            specialists=arguments.specialists(args.specialist),
            test=split_command(args.test) if args.test else (detected_test or setup.SMOKE_TEST),
            team=args.team,
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
        ),
    )
    for line in _shown(actions):
        print(line)
    if agents := setup.agents_to_restart(actions, root, wired):
        print(f"\n{setup.restart_notice(agents)}")
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
        actions = setup.upgrade(Path(args.path), ref=setup.full_ref(args.ref) if args.ref else args.ref, yes=args.yes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in actions:
        print(line)
    if not args.yes and not actions[0].startswith("nothing to update"):
        print("\ndry run: nothing changed. Run again with --yes, then `aidd doctor`, and commit it as one change.")
    print("\nThe CLI itself: `aidd self-update`.")
    print("The Claude Code plugins: `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`, `aidd-cli@aidd`, and `aidd-team@aidd`.")
    return 0


def cmd_self_update(args) -> int:
    code, lines = setup.self_update(check_only=args.check, main=args.main)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


def cmd_uninstall(args) -> int:
    for line in setup.uninstall(Path(args.path), links=args.link or [], yes=args.yes):
        print(line)
    return 0


def cmd_doctor(args) -> int:
    results = setup.doctor(Path(args.path), execute=True)
    if args.json:
        shown = {"schema_version": arguments.JSON_SCHEMA_VERSION, "passed": not any(level == "fail" for level, _ in results)}
        shown["checks"] = [{"level": level, "message": msg} for level, msg in results]
        print(json.dumps(shown, indent=2))
        return 0 if shown["passed"] else 1
    for level, msg in results:
        print(f"[{level:4}] {msg}")
    return 1 if any(level == "fail" for level, _ in results) else 0


def cmd_standard(args) -> int:
    """`aidd standard [add]`: the open choices and the library, or its stacks (`--stacks`); or a copy of library
    standards, or of a stack's (`--stack`), in this repository."""
    arguments.enter_repo(args)
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
        print(f"  {s['id']}: fills {', '.join(s['fills'])}; {tool}; {s['trust']}" + (f" [{', '.join(marks)}]" if marks else ""))
    return 0


__all__ = ["cmd_doctor", "cmd_init", "cmd_self_update", "cmd_standard", "cmd_uninstall", "cmd_upgrade", "git"]
