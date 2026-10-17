"""The commands for maintainers and harnesses: eval, mcp, hook, and gen-docs."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
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


def cmd_hook(args) -> int:
    from aidd import guard

    if args.event in ("pre-tool", "pre-edit"):
        return guard.pre_tool_hook()
    from aidd.cli.commands import typed_decisions

    with git.system_only():  # the session hooks read git as the guard does
        # The prompt hook records what the person typed when it is a decision (`approve SPEC-1`), in this process.
        return guard.run_session_hook(args.event, on_prompt=typed_decisions.record)


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
    if args.paths:
        raise ValueError(f"unexpected arguments {' '.join(args.paths)!r}: only `aidd eval report` takes files")
    if args.suite in ("examples", "standards", "packs") and (args.repeat != 1 or args.control or args.record or args.model_label):
        raise ValueError("--repeat, --control, --record, and --model-label measure an agent: use them with routing, roles, or tasks")
    if args.repeat < 1:
        raise ValueError("--repeat must be at least 1")
    if args.suite == "examples":
        return _eval_examples(args, root)
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


def _eval_examples(args, root: Path) -> int:
    """`aidd eval examples`: the conformance suite, or its resolved cases with --materialize."""
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


def _eval_standards_online(args) -> int:
    """`aidd eval standards --online`: read every source again, and the release feeds of the library's tools."""
    from aidd import knowledge

    result = knowledge.check_online(
        knowledge.evidence_entries(), timeout_seconds=args.timeout, max_seconds=args.max_seconds, max_bytes=args.max_bytes, concurrency=args.concurrency
    )
    # The release feeds of the library's tools: a newer major than a standard's checked_version is flagged.
    result["releases"] = knowledge.check_releases(
        knowledge.release_entries(), timeout_seconds=args.timeout, max_seconds=args.max_seconds, max_bytes=args.max_bytes
    )
    print(json.dumps(result, indent=2) if args.json else knowledge.markdown(result), end="\n" if args.json else "")
    return knowledge.exit_code(result, args.strict)


def _eval_standards(args) -> int:
    """`aidd eval standards`: the registry's dates, evidence, and extensions, then the library's files."""
    from aidd import knowledge

    today = dt.date.today()
    if getattr(args, "unreviewed", False):
        return _unreviewed()
    if getattr(args, "due", None) is not None:
        soon = knowledge.due_soon(today, args.due)
        print(f"{len(soon)} entries come due for review within {args.due} days:")
        for s in soon:
            print(f"- {s['due_on']}: {s.get('id') or s['name']} ({s.get('where')}); {s.get('source') or 'no source'}")
        return 0
    stale = knowledge.stale_standards(today, args.max_days)
    for s in stale:
        print(
            f"[!!] {s['where']}: {docsgen.standard_text(s)} {'checked' if s.get('checked') else 'reviewed'} {knowledge.dated_on(s)}, "
            f"{s['age_days']} days ago: {s['why']}"
        )
    entries = knowledge.dated_entries()
    emerging = sum(1 for s in entries if s.get("maturity") == "emerging")
    cadence = f"within {args.max_days} days" if args.max_days is not None else "within their review cadence or by their review_due"
    print(f"{len(entries)} standards ({emerging} marked emerging); {len(stale)} not checked {cadence}")
    soon = knowledge.due_soon(today, 90)
    if soon:
        print(f"{len(soon)} entries come due for review within 90 days, the first on {soon[0]['due_on']} ({soon[0].get('id') or soon[0]['name']})")
    print(setup.STANDARDS_BASIS)
    tiers = knowledge.trust_counts(entries)
    print(
        f"Registry trust: {tiers[knowledge.TIER_AGENT]} {knowledge.TIER_AGENT}, {tiers[knowledge.TIER_PERSON]} {knowledge.TIER_PERSON} (`--unreviewed` lists them)"
    )
    problems = _registry_problems()
    library = _library_problems(today)
    return 0 if not (stale or problems or library) else 1


# What a person reviews first: a law, a regulation, or a rule a regulator enforces, where an error costs most.
_LEGAL = re.compile(
    r"\b(?:Regulation|Directive|Act|Law|Rule|Code of Practice|CFR|U\.S\.C|GDPR|HIPAA|PCI|COPPA|FERPA|CCPA|CPRA|FedRAMP|"
    r"Accessibility|Section 508|ADA|MiCA|PSD|DORA|NIS ?2|CRA|eIDAS|AI Act)\b"
)


def _unreviewed() -> int:
    """`aidd eval standards --unreviewed`: each registry entry no person has reviewed, the laws and regulations first,
    and how a person records a review. Exit 0: a list, never a failure."""
    from aidd import knowledge

    pending = [s for s in knowledge.dated_entries() if knowledge.trust_tier(s) == knowledge.TIER_AGENT]
    legal = [s for s in pending if _LEGAL.search(f"{s.get('name', '')} {s.get('edition', '')}")]
    rest = [s for s in pending if s not in legal]
    print(f"{len(pending)} registry entries are checked by an agent only; {len(legal)} name a law or a regulation, so a person reviews those first.")
    for title, group in (("Laws and regulations", legal), ("Everything else", rest)):
        print(f"\n{title} ({len(group)}):")
        for s in group:
            print(f"- {s.get('id')}: {s.get('name')} ({s.get('edition')}); {s.get('source') or 'no source'}; {s.get('where')}")
    print(
        "\nTo record a review: read the entry's source, then in schemas/roles.json set its `checked_by` to your identity "
        "(`@login` or `email:you@example.com`), its `checked` to today, and its `evidence` to a sentence you read there. "
        "Run `aidd gen-docs` and `aidd eval standards`, and commit the change through the gate."
    )
    return 0


def _registry_problems() -> bool:
    """Print what the registry's entries get wrong beyond their dates; True when there is any."""
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
    return bool(bulk or moved or unsourced or unevidenced or unpinned)


def _library_problems(today: dt.date) -> list[str]:
    """Print the library of opinionated standards and stacks: its problems, its size, and who checked it."""
    from aidd import knowledge

    # The generic checks over every file (standards.library_problems).
    library = knowledge.library_problems(today=today)
    for line in library:
        print(f"[!!] library: {line}")
    print(
        f"{arguments.counted(len(knowledge.standards_library()), 'library standard')} and {arguments.counted(len(knowledge.stacks()), 'stack')}; {len(library)} problem(s) in the library"
    )
    # Who checked each library standard (`checked_by`): an agent's check until a person reviews it.
    tiers = knowledge.trust_counts([s.meta for s in knowledge.standards_library().values()])
    print(f"Library trust: {tiers[knowledge.TIER_AGENT]} {knowledge.TIER_AGENT}, {tiers[knowledge.TIER_PERSON]} {knowledge.TIER_PERSON}")
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
    print(f"{len(found)} problem(s); {setup.PACKS_BASIS}")
    return 1 if found else 0


def _eval_agent(args, root: Path) -> int:
    """`aidd eval routing|roles|tasks --cmd`: measure an agent on the scenarios."""
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
