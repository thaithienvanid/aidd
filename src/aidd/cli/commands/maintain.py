"""The commands for maintainers and harnesses: eval, mcp, and gen-docs."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import shutil
from pathlib import Path

from aidd import docsgen, evals
from aidd.cli import arguments, parser
from aidd.cli.commands import setup
from aidd.kernel import git, resources
from aidd.kernel.processes import split_command


def cmd_mcp(args) -> int:
    from aidd.cli import mcp_server

    top = git.toplevel()
    return mcp_server.serve(root=top or os.getcwd())


def cmd_gen_docs(args) -> int:
    root = resources.repo_root()
    if root is None:
        raise RuntimeError("gen-docs maintains the aidd source repository; run it from a source checkout")
    stale = docsgen.gen_docs(root, check=args.check, cli=parser.cli_facts())
    for p in stale:
        print(("stale: " if args.check else "updated: ") + str(p.relative_to(root)))
    if args.check and stale:
        print("run `aidd gen-docs` and commit the result")
        return 1
    return 0


def cmd_eval(args) -> int:
    """`aidd eval <suite>`: the flag checks every suite shares, then the suite's own function."""
    root = Path(args.root) if args.root else (resources.repo_root() or Path("."))
    if (args.online or args.strict) and args.suite != "standards":
        raise ValueError("--online and --strict go with the standards suite: aidd eval standards --online")
    if args.json and args.suite not in ("standards", "packs"):
        raise ValueError("--json prints `aidd eval standards --online` or `aidd eval packs`; the other suites print lines")
    if args.suite == "standards" and (args.strict or args.json) and not args.online:
        raise ValueError("--strict and --json read the online standards check: add --online")
    if args.suite == "report":
        return _eval_report(args)
    if args.suite == "transcript":
        return _eval_transcript(args)
    if args.paths:
        raise ValueError(f"unexpected arguments {' '.join(args.paths)!r}: only `aidd eval report` and `aidd eval transcript` take files")
    if args.suite in ("standards", "packs") and (args.repeat != 1 or args.without_aidd or args.record or args.model_label):
        raise ValueError("--repeat, --without-aidd, --record, and --model-label measure an agent: use them with routing, roles, or tasks")
    if args.repeat < 1:
        raise ValueError("--repeat must be at least 1")
    if args.suite == "standards":
        return _eval_standards_online(args) if args.online else _eval_standards(args)
    if args.suite == "packs":
        return _eval_packs(args)
    return _eval_agent(args, root)


def _eval_report(args) -> int:
    """`aidd eval report FILE...`: the runs recorded with --record, as one table."""
    if not args.paths:
        raise ValueError("report reads the JSON-lines files written with --record: aidd eval report evals-results.jsonl")
    print(evals.report([Path(x) for x in args.paths]))
    return 0


def _eval_transcript(args) -> int:
    """`aidd eval transcript FILE`: a recorded run's files opened, tool calls, and usage, as JSON. It reads, and runs nothing."""
    if len(args.paths) != 1:
        raise ValueError("transcript reads one recorded event stream: aidd eval transcript run.jsonl")
    print(json.dumps(dataclasses.asdict(evals.read_transcript(Path(args.paths[0]))), indent=2))
    return 0


def _eval_standards_online(args) -> int:
    """`aidd eval standards --online`: read every source again, and the release feeds of the library's tools."""
    from aidd import knowledge

    result = knowledge.check_online(
        knowledge.evidence_entries(), timeout_seconds=args.timeout, max_seconds=args.max_seconds, max_bytes=args.max_bytes, concurrency=args.concurrency
    )
    # The release feeds of the library's tools: a newer major than a standard's checked_version is flagged.
    result["releases"] = knowledge.check_releases(
        knowledge.release_entries() + knowledge.pinned_command_entries(), timeout_seconds=args.timeout, max_seconds=args.max_seconds, max_bytes=args.max_bytes
    )
    print(json.dumps(result, indent=2) if args.json else knowledge.markdown(result), end="\n" if args.json else "")
    return knowledge.exit_code(result, args.strict)


def _eval_standards(args) -> int:
    """`aidd eval standards`: the registry's dates, evidence, and extensions, then the library's files."""
    from aidd import knowledge

    today = dt.date.today()
    if getattr(args, "due", None) is not None:
        soon = knowledge.due_soon(today, args.due)
        print(f"{len(soon)} entries come due for review within {args.due} days:")
        for s in soon:
            print(f"- {s['due_on']}: {s.get('id') or s['name']} ({s.get('where')}); {s.get('source') or 'no source'}")
        return 0
    stale = knowledge.stale_standards(today)
    for s in stale:
        print(f"[!!] {s['where']}: {docsgen.standard_text(s)} checked {knowledge.dated_on(s)}, {s['age_days']} days ago: {s['why']}")
    entries = knowledge.dated_entries()
    emerging = sum(1 for s in entries if s.get("maturity") == "emerging")
    print(
        f"{len(entries)} dated applications: {_types_text(entries)} ({emerging} marked emerging); {len(stale)} not checked "
        "within their review cadence or by their review_due"
    )
    soon = knowledge.due_soon(today, 90)
    if soon:
        print(f"{len(soon)} entries come due for review within 90 days, the first on {soon[0]['due_on']} ({soon[0].get('id') or soon[0]['name']})")
    print(setup.STANDARDS_BASIS)
    for line in knowledge.pinned_command_lines():
        print(line)
    problems = _registry_problems()
    library = _library_problems(today)
    return 0 if not (stale or problems or library) else 1


def _by_type(entries: list[dict]) -> dict[str, list[dict]]:
    """Dated entries by type: a registry standard (it has an id), an extension, or a practice skill's own date."""
    out: dict[str, list[dict]] = {"registry": [], "extension": [], "skill": []}
    for s in entries:
        out["registry" if s.get("id") else "extension" if s["where"].startswith("extension ") else "skill"].append(s)
    return out


def _types_text(entries: list[dict]) -> str:
    """The dated entries counted by type. One registry standard counts once for each role, pack, and practice skill that
    applies it, so its applications and its distinct standards are two numbers."""
    by_type = _by_type(entries)
    ids = len({s["id"] for s in by_type["registry"]})
    return f"{ids} registry standards applied {len(by_type['registry'])} times, {len(by_type['extension'])} extensions, and {len(by_type['skill'])} practice skills"


def _registry_problems() -> bool:
    """Print what the registry's entries get wrong beyond their dates; True when there is any."""
    bulk = evals.bulk_checked_dates()
    for day, count in bulk:
        print(
            f"[!!] {count} entries share the checked date {day} without evidence that confirms each one (a sentence from the page read). "
            f"One bulk edit is not {count} confirmations: re-check them per source"
        )
    moved = evals.stale_id_citations()
    for s in moved:
        print(f"[!!] {s['id']}: cites {s['token']}, but {s['moved_by']} records {s['old']} moved to {s['new']}; cite the current ID")
    unsourced = evals.unsourced_standards()
    for s in unsourced:
        print(f"[!!] {s['id']}: names edition {s['edition']!r} but no source to check it against")
    unevidenced = evals.unevidenced_standards()
    for s in unevidenced:
        print(f"[!!] {s['id']}: names edition {s['edition']!r} but no evidence; add the sentence that was read")
    unpinned = evals.unpinned_extensions()
    for x in unpinned:
        print(f"[!!] {x['where']}: {x['name']} ({x['type']}) has no {' and no '.join(x['missing'])}")
    return bool(bulk or moved or unsourced or unevidenced or unpinned)


def _library_problems(today: dt.date) -> list[str]:
    """Print the library of opinionated standards and stacks: its problems and its size."""
    from aidd import knowledge

    # The generic checks over every file (library_checks.library_problems).
    library = knowledge.library_problems(today=today)
    for line in library:
        print(f"[!!] library: {line}")
    print(
        f"{arguments.counted(len(knowledge.standards_library()), 'library standard')} and {arguments.counted(len(knowledge.stacks()), 'stack')}; {len(library)} problem(s) in the library"
    )
    return library


def _eval_packs(args) -> int:
    """`aidd eval packs`: each pack's and practice skill's size and problems, and the descriptions an agent loads."""
    sizes, found = docsgen.pack_sizes_and_problems()
    listed = docsgen.pack_descriptions()
    if args.json:
        report = {"schema_version": arguments.JSON_SCHEMA_VERSION, "sizes": sizes, "problems": found, "descriptions": listed}
        print(json.dumps(report, indent=2))
        return 1 if found else 0
    for p in found:
        print(f"[!!] {p['where']}: {p['problem']}")
    for entry_type in ("pack", "practice"):
        mine = [s for s in sizes if s["type"] == entry_type]
        skill, refs = sum(s["tokens"] for s in mine), sum(sum(s["references"].values()) for s in mine)
        print(f"{len(mine)} {entry_type}s: about {skill} tokens in SKILL.md files and {refs} in references")
    longest = max(listed, key=lambda d: d["chars"], default={"name": "none", "chars": 0})
    print(
        f"{len(listed)} descriptions: {sum(d['chars'] for d in listed):,} characters in all "
        f"({sum(d['type'] == 'skill' for d in listed)} skills, {sum(d['type'] == 'command' for d in listed)} commands); "
        f"the longest is {longest['name']} ({longest['chars']})"
    )
    print(f"{len(found)} problem(s); {setup.PACKS_BASIS}")
    return 1 if found else 0


def _eval_agent(args, root: Path) -> int:
    """`aidd eval routing|roles|tasks --agent-command`: measure an agent on the scenarios."""
    if not args.agent_command:
        raise ValueError(f'--agent-command is required for the {args.suite} suite, for example --agent-command "claude -p"')
    words = split_command(args.agent_command)
    if not words:
        raise ValueError("--agent-command is empty")
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
            lambda material: evals.run_roles(scenarios, args.agent_command, material=material),
            lambda r: f"{r['id']} ({r['role']})" + ("" if r["ok"] else ": " + "; ".join(r["misses"])),
            noun="scenario(s)",
            metric="passed",
            cases=scenarios,
            repo=resources.repo_root(),
        )
    return _measure(
        args,
        lambda material: evals.run_routing(scenarios, args.agent_command, embed=not args.no_embed, material=material),
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
        lambda material: evals.run_tasks(scenarios, args.agent_command, repo=repo),
        lambda r: r["id"] + ("" if r["ok"] else ": " + "; ".join(r["misses"])),
        noun="task(s)",
        metric="passed",
        control=False,
        cases=scenarios,
        repo=repo,
    )


def _measure(args, run, detail, *, noun: str, metric: str, cases: Path, repo: Path | None, control: bool = True, options: dict | None = None) -> int:
    """Run an agent suite --repeat times (and again without the aidd material for --without-aidd), print it, record it, and fail below the mean pass@1 asked for.

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
    if args.without_aidd and not control:
        print("control: not applicable to tasks; a task carries no instructions of its own, the repository's configuration is the agent's material")
    elif args.without_aidd:
        baseline = evals.measure(lambda: run(False), k)
        base = evals.summary(baseline)["mean_pass_at_1"]
        print(f"control without the aidd material: mean pass@1 {base:.1%}; lift {(mean - base) * 100:+.1f} points (reported, never gating)")
    if args.record:
        line = evals.record_line(
            suite=args.suite,
            cmd=args.agent_command,
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
