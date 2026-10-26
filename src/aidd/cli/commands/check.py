"""The Check commands: gate, validate, and record (verify, export)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from aidd import gate, platforms, tracking, workitems
from aidd.cli import arguments, local_events
from aidd.kernel import extensions, git
from aidd.kernel.processes import split_command


def cmd_validate(args) -> int:
    if not args.paths:
        arguments.enter_repo(args)
        errors, warnings = workitems.check_repo(Path("."))
    else:
        found = [e for p in args.paths for e in workitems.validate_file(Path(p))]
        errors = [e for e in found if not e.startswith("warning: ")]
        warnings = [e for e in found if e.startswith("warning: ")]
    step = workitems.validate_next_step(errors)
    if args.json:
        warned = [w.removeprefix("warning: ") for w in warnings]
        print(
            json.dumps(
                {"schema_version": arguments.JSON_SCHEMA_VERSION, "passed": not errors, "errors": errors, "warnings": warned, "next_step": step or None},
                indent=2,
            )
        )
        return 1 if errors else 0
    for w in warnings:
        print(w if w.startswith("warning: ") else f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    # Every error names the file it is in, but a missing config; the summary says what to do next, so a red validate
    # never leaves you guessing.
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)" + (f": {step}" if step else ""))
    return 1 if errors else 0


# A gate run's options, which a forecast of planned paths has no use for: it judges no change.
_RUN_ONLY = (
    *("platform", "context", "base", "spec", "body_file", "approvals", "no_policy", "mode", "dry_run", "pending_ok"),
    *("post_status", "resolve", "record", "events", "explain", "html"),
)
FORECAST_NOTE = "A forecast: it records nothing. On the branch, the gate computes the route again from the real diff, and can only raise it.\n"


def _forecast(args) -> int:
    """`aidd gate --paths`: the route planned paths need before any code exists, its lane, and the lane's first step. It
    writes no record and posts no status."""
    given = [args.platform if name == "platform" else "--" + name.replace("_", "-") for name in _RUN_ONLY if getattr(args, name) not in (None, False)]
    if given:
        raise ValueError(f"--paths forecasts a planned change, so it takes no {', '.join(given)}: run `aidd gate` on the branch for those")
    arguments.enter_repo(args)
    answer = tracking.forecast(Path("."), paths=args.paths, ctype=args.type, dimensions=args.dimension or [], irreversible=args.irreversible)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(tracking.forecast_markdown(answer) + FORECAST_NOTE, end="")
    return 0


def _branch_lines() -> list[str]:
    """Locally, after the route: the domain packs the change calls for, and the other branches whose Specs overlap this
    branch's. Advice, never a finding: when they cannot be read, the gate's answer stays the same and nothing is printed."""
    try:
        answer = tracking.forecast(Path("."))
    except Exception:  # noqa: BLE001  # advice: the gate's answer never depends on it
        return []
    out = [f"  {line}" for line in tracking.pack_lines(answer.get("route") or {})]
    if found := answer.get("overlaps"):
        out += ["  overlaps with other branches:", *(f"    - {s['what']}: {s['how']}" for s in found)]
    return out


def cmd_gate(args) -> int:
    if args.paths:
        return _forecast(args)
    if args.type or args.dimension or args.irreversible:
        raise ValueError("--type, --dimension, and --irreversible describe planned paths: use them with --paths")
    if args.explain:
        print(gate.explain_rule(args.explain))
        return 0
    # One run asks git the same read-only questions many times (the base, its merge-base, the remotes). Inside memo()
    # each runs once, and any git call that may write, such as a fetch, clears what it kept.
    with git.memo():
        return _gate_run(args)


def _gate_run(args) -> int:
    """`aidd gate` on a change: on GitHub, on GitLab, from a context file, or here on the branch."""
    if args.platform == "github":
        return platforms.github_gate(
            dry_run=args.dry_run,
            events_out=args.events,
            record_out=args.record,
            resolve_only=args.resolve,
            mode=args.mode,
            html_out=arguments.html_arg(args.html),
        )
    if args.platform == "gitlab":
        return platforms.gitlab_gate(
            dry_run=args.dry_run,
            evidence_path=args.evidence,
            events_out=args.events,
            record_out=args.record,
            pending_fails=not args.pending_ok,
            post=args.post_status,
            mode=args.mode,
            html_out=arguments.html_arg(args.html),
        )
    if args.context:
        ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
    else:
        arguments.enter_repo(args, "spec", file_attrs=("body_file", "approvals", "evidence", "record", "events", "html"))
        arguments.base_from_spec(args)
        ctx = platforms.build_local_context(
            base=args.base, body=arguments.body(args), approvals=args.approvals, evidence=args.evidence, run_policy=not args.no_policy
        )
    d = gate.decide(ctx)
    if not args.context and not args.events:
        # A local run on a branch keeps its decision in the git directory, for `aidd metrics`; `--events` writes there instead.
        local_events.record(d)
    if args.html is not None:
        _merge_view(args, ctx, d)
    if args.record:
        Path(args.record).write_text(json.dumps(d.record, indent=2) + "\n", encoding="utf-8")
        # The agent change record: an in-toto statement of this decision, next to the gate record.
        gate.write_change_record(d, ctx if isinstance(ctx, dict) else {}, args.record)
    if args.events:
        with open(args.events, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(gate.decision_event(d, ctx.get("repo") if isinstance(ctx, dict) else None)) + "\n")
    if args.json:
        # The gate record, as `--record` writes it, for a script: nothing else goes to stdout.
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | d.record, indent=2))
        return arguments.EXIT[d.decision]
    print(gate.decision_text(d))
    if not args.context:
        # Locally, the diff a stale Spec approval's fix names, so the Approver sees what changed before approving again.
        for f in d.findings:
            _, sep, cmd = f.fix.partition("what changed since the last approval: git ")
            if f.code == "spec_approval.missing" and sep:
                stat = git.run(split_command(cmd.splitlines()[0]), check=False).rstrip()
                print(
                    "  what changed in the frozen files since the last Spec approval:\n" + "\n".join(f"    {ln}" for ln in stat.splitlines() or ["(nothing)"])
                )
    if not args.context and d.record.get("required_route"):
        # Locally, the route the gate computed from the real diff, and why: the forecast, made again on the real diff.
        print(f"  computed route {d.record['required_route']} ({gate.LANES.get(d.record['required_route'], '?')} lane) from the diff, because:")
        for line in gate.reason_lines({"reasons": d.record.get("route_reasons") or []}):
            print(f"    - {line}")
    if not args.context:
        for line in _branch_lines():
            print(line)
    return arguments.EXIT[d.decision]


def _merge_view(args, ctx: dict, d) -> None:
    """The Merge approval page, beside the gate's report. A view for people: whatever goes wrong here is a warning, and
    the decision (already made) and the exit code stay as they are."""
    from aidd import views

    try:
        head = str(ctx.get("head_sha") or "")
        in_repo = not args.context
        evidence = Path(args.evidence) if in_repo and args.evidence else None
        evidence_dir = evidence.parent if evidence is not None and evidence.is_file() else None
        review = views.review_file(evidence.parent / "review.md") if evidence is not None else None
        since = views.since_last_approval(ctx, "." if in_repo else None) if isinstance(ctx.get("reviews"), list) else ""
        page = views.merge_page(ctx, d, diffs=views.diffs(ctx, ".") if in_repo else {}, review=review, evidence_dir=evidence_dir, since=since)
        out = views.write(args.html or views.default_path("merge", head[:12] or "change"), page)
        print(f"wrote {arguments.repo_relative(out)}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, git.GitError) as exc:
        print(f"warning: the Merge approval page was not written: {exc}", file=sys.stderr)


def cmd_export(args) -> int:
    """Gate records or events as JSON or CSV (or an installed exporter's format), the same bytes for the same inputs."""
    from aidd import tracking

    if args.by_control:
        if args.kind != "records" or args.format != "json" or args.since or args.tenant:
            raise ValueError("--by-control groups gate records as JSON: `aidd record export records PATH... --by-control`, without --since or --tenant")
        text = json.dumps(tracking.records_by_control(Path.cwd(), args.paths), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if not args.out:
            sys.stdout.write(text)
            return 0
        path = Path(args.out) / "controls.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
        return 0
    items = tracking.collect_records(args.kind, args.paths, since=args.since, tenant=args.tenant)
    exporters = None if args.format in tracking.EXPORT_FORMATS else extensions.installed("aidd.exporters")
    out = tracking.render_export(args.kind, items, args.format, exporters)
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


def cmd_record_artifacts(args) -> int:
    """`aidd record artifacts SHA`: write artifacts.json for the files the verifier saved for that head."""
    from aidd import views

    items = views.record_artifacts(Path(args.dir), args.head.lower())
    kinds = ", ".join(f"{n} {k}" for k, n in sorted(Counter(i["kind"] for i in items).items()))
    print(f"wrote {Path(args.dir).as_posix()}/preview/{args.head.lower()}/artifacts.json: {kinds}. The Merge approval page (`aidd gate --html`) shows them")
    return 0


def cmd_verify(args) -> int:
    """Check an agent change record: its shape, subject, tenant, decision, and approvals, then its signature."""

    path = gate.find_change_record(args.target, args.dir)
    try:
        stmt = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"aidd record verify: {path}: not JSON ({exc})")
        return 1
    sha = args.target.lower() if not Path(args.target).is_file() else None
    problems = gate.check(stmt, sha=sha, tenant=args.tenant)
    signature = "unsigned"
    if not problems and (args.bundle or args.online):
        pred = stmt["predicate"]
        # The repository comes from the one who checks, never from the record: a record names whatever repository its writer chose.
        repo = args.repo or platforms.origin_repo(".") or ""
        if not repo:
            problems.append("the signature needs the GitHub repository: pass --repo owner/name (there is no github.com origin remote here)")
        elif pred.get("platform") != "github" or pred.get("repo") != repo:
            problems.append(f"the record names the {pred.get('platform')} repository {pred.get('repo')!r}, not {repo}")
        else:
            branch = args.default_branch or arguments.default_branch(".")
            why = gate.verify_signature(path, stmt, repo=repo, bundle=args.bundle, signer_workflow=args.signer_workflow, default_branch=branch)
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
