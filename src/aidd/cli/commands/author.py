"""The Author commands: new, import, describe, test, and proposal."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from aidd import config, gate, setup, workitems
from aidd.cli import arguments, local_events
from aidd.cli.commands import operate
from aidd.kernel import documents, git, strict_yaml
from aidd.kernel import text as kernel_text


def _spec_route(args, cfg: config.Config | None) -> tuple[str, bool]:
    """(route, write) for `aidd new spec`: with --paths, the route computed from the paths (as `aidd gate --paths` gives it), raised to
    --route when that is higher; without, --route (default normal). `write` is False when the paths need no Spec: then
    nothing is written, the reason and the `--force` hint go to stderr, and `aidd new` exits 1."""
    chosen = args.route or "normal"
    if args.kind != "spec" or not args.paths:
        return chosen, True
    if cfg is None:
        raise ValueError(f"no {config.CONFIG_PATH}: `aidd init` first, so the route can be computed from the paths")
    tracked = [p for p in git.run(["ls-files", "-z"], check=False).split("\0") if p]
    a = gate.assess_paths(cfg, args.paths, ctype=args.type, dimensions=args.dimension or [], irreversible=args.irreversible, tracked=tracked)
    print(f"route: the minimum for these paths is {a.required_route} ({a.lane} lane)")
    for line in gate.reason_lines(a):
        print(f"  - {line}")
    if a.lane == "fast":
        if not args.force:
            print(
                "No Spec written: these paths need none (the fast lane: build, verify, then `aidd describe --commit`).\n"
                "Want one anyway? Add `--force`: it writes the Spec on the normal route.",
                file=sys.stderr,
            )
            if hint := gate.untested_feature_hint(args.paths, ctype=args.type or "feat", tracked=tracked):
                print(hint, file=sys.stderr)
            return a.required_route, False
        return max(chosen, "normal", key=gate.ROUTE_RANK.__getitem__), True
    route = max(chosen, a.required_route, key=gate.ROUTE_RANK.__getitem__)
    if args.route and gate.ROUTE_RANK[args.route] < gate.ROUTE_RANK[a.required_route]:
        print(f"route {a.required_route}, not --route {args.route}: a Spec's route is never below the computed minimum")
    return route, True


def _new_doc(args, cfg: config.Config | None) -> int:
    """`aidd new <kind> <topic> --spec ID`: a linked document from its template, and its `docs` entry in the Spec.
    A feedback log belongs to no Spec: `aidd new feedback <topic>` writes it alone."""
    if args.kind in workitems.UNLINKED_DOCS and args.spec:
        raise ValueError(f"a {args.kind} belongs to no one Spec: drop --spec; each entry names its Spec or hypothesis in its row")
    if args.no_link and args.kind in workitems.UNLINKED_DOCS:
        raise ValueError(f"--no-link is for a doc a Spec links; a {args.kind} is never linked")
    if args.kind not in workitems.UNLINKED_DOCS and not args.spec:
        raise ValueError(f"--spec is required: a {args.kind} doc belongs to the Spec that links it (`aidd new {args.kind} <topic> --spec SPEC-42`)")
    docs_dir = cfg.docs_dir if cfg else "docs"
    model = Path(docs_dir) / workitems.THREAT_MODELS / f"{kernel_text.slug(args.id or '')}.md"
    existing = args.kind == "threat-model" and model.is_file()
    path, spec = workitems.new_doc(
        Path("."),
        workitems.NewDoc(
            kind=args.kind,
            topic=args.id,
            spec_id=args.spec,
            area=args.area,
            title=args.title or "",
            docs_dir=docs_dir,
            specs_dir=cfg.specs_dir if cfg else "specs",
            link=not args.no_link,
            prototype=args.prototype,
        ),
    )
    print(path.as_posix())
    if spec is not None and args.no_link:
        entry = {"kind": args.kind, "path": path.as_posix()} | ({"frozen": False} if args.kind in workitems.LIVING_DOCS else {})
        print(f"not linked: {spec.as_posix()} is left to its writer, who adds this item to its `docs` list:\n{strict_yaml.dump({'docs': [entry]}).rstrip()}")
        return 0
    if spec is None:
        print("next: add a row per piece of feedback, as it arrives, with its source; a person confirms each; `aidd digest` counts the themes")
        return 0
    if args.kind == "threat-model":
        print(
            f"{'the component already has its threat model: linked again' if existing else 'linked'} from {spec.as_posix()} as a living `docs` "
            "entry (frozen: false). Put this Spec's delta (the threat ids it adds, changes, or retires) in its Design, and update the model "
            "in the same change: Spec approval freezes the delta, and Merge approval reviews the model"
        )
    elif args.kind in workitems.LIVING_DOCS:
        print(f"linked from {spec.as_posix()} as a living `docs` entry (frozen: false): humans fill it after Spec approval")
    else:
        print(f"linked from {spec.as_posix()} as a frozen `docs` entry: Spec approval pins it with the Spec")
    print(f"next: replace the TODOs, then `aidd validate {spec.as_posix()}`")
    return 0


def _new_repo_doc(args, cfg: config.Config | None) -> int:
    """`aidd new design-system`, `architecture`, `data-map`, `vendors`, `glossary`, or `agents`: the repository's one of each."""
    if args.id or args.spec or args.area or args.no_link:
        raise ValueError(f"a {args.kind} belongs to the repository, not a Spec: run `aidd new {args.kind}` with no id, --spec, or --area")
    paths = workitems.new_repo_doc(Path("."), kind=args.kind, title=args.title or "", docs_dir=cfg.docs_dir if cfg else "docs")
    for p in paths:
        print(p.as_posix())
    route = {"design-system": "normal (baseline:design-system)", "agents": "major: AGENTS.md steers the agents, so a person agrees to it"}.get(
        args.kind, "minor, a docs change"
    )
    if args.kind == "design-system":
        print("then: `node design/build.mjs` writes design/tokens.css, design/themes/<theme>.css, and DESIGN.md's token front matter")
        print("test: add `node design/build.mjs --check` (the drift test) to the config's `tests` list")
    print(f"next: replace the TODOs, and commit it as its own change: route {route}")
    if args.kind in workitems.LIVING_DOCS:
        print(f"a Spec that changes what it records links it as a living doc: a `docs` item with kind: {args.kind}, frozen: false")
    return 0


def _new_contract(args, cfg: config.Config | None) -> int:
    """`aidd new contract <proposal id>`: the contract in the proposal's folder, then each change order."""
    if not args.id or args.spec or args.area or args.no_link:
        raise ValueError("a contract belongs to a proposal: `aidd new contract <proposal id>`, with no --spec or --area")
    path = workitems.new_contract(Path("."), args.id, proposals_dir=cfg.proposals_dir if cfg else "proposals")
    print(path.as_posix())
    what = "the change order: the delta and the affected Acceptance ids" if path.parent.name == workitems.CHANGE_ORDERS else "the statement-of-work base"
    print(f"next: draft {what}; every price, legal term, and the client's decision stay with humans")
    return 0


def _new_exploration(args, cfg) -> int:
    """`aidd new exploration <folder> --title "<the question>"`: the exploration's front matter and sections. A folder
    that is not an exploration's home is refused before anything is written, naming the folder it belongs in."""

    specs_dir = cfg.specs_dir if cfg else "specs"
    if not args.id or not args.title:
        raise ValueError(f'an exploration needs its folder and its question: `aidd new exploration {specs_dir}/SPEC-12/explore/<slug> --title "..."`')
    if home := workitems.exploration_misplaced(Path(args.id), specs_dir):
        raise ValueError(f"{workitems.EXPLORATION_HOME}: `aidd new exploration {home} --title {json.dumps(args.title)}`")
    path = workitems.new_exploration(Path(args.id), question=args.title, owner=args.owner or "product-designer", timebox=args.timebox)
    print(path.as_posix())
    print(f"next: draw two or three divergent directions (or, for a decision card, write the options with no visuals), then `aidd explore {args.id}`")
    return 0


def cmd_new(args) -> int:
    arguments.enter_repo(args, *(("id",) if args.kind == "exploration" else ()))
    cfg = arguments.config_or_none()
    if args.kind in workitems.REPO_DOCS:
        return _new_repo_doc(args, cfg)
    if args.kind == "contract":
        return _new_contract(args, cfg)
    if args.kind == "exploration":
        return _new_exploration(args, cfg)
    if args.kind in workitems.ID_PREFIXES:
        # `aidd new spec "Add a discount"`: a first word that is no id is the title, and the id is the next free one.
        if args.id and not workitems.WORK_ID.fullmatch(args.id) and args.title is None:
            args.title, args.id = args.id, None
        if not args.id:
            folder = (cfg.proposals_dir if cfg else "proposals") if args.kind == "proposal" else (cfg.specs_dir if cfg else "specs")
            args.id = workitems.next_id(Path("."), workitems.ID_PREFIXES[args.kind], folder)
    if not args.id:
        raise ValueError(f"an id is required for a {args.kind}: `aidd new {args.kind} <id>`")
    if args.kind in workitems.DOC_TEMPLATES:
        return _new_doc(args, cfg)
    if not args.title:
        raise ValueError(f"--title is required for a {args.kind}")
    if args.area:
        raise ValueError(f"--area names a linked document's folder: use it with {', '.join(sorted(set(workitems.DOC_TEMPLATES) - workitems.UNLINKED_DOCS))}")
    if args.no_link and not (args.kind == "runbook" and args.spec):
        raise ValueError("--no-link is for a document a Spec links: a linked doc, or a runbook with --spec")
    linked = workitems.find_spec_by_id(Path("."), cfg.specs_dir if cfg else "specs", args.spec) if args.kind == "runbook" and args.spec else None
    if args.kind != "spec" and (args.paths or args.dimension or args.irreversible):
        raise ValueError("--paths, --dimension, and --irreversible compute a Spec's route: use them with `aidd new spec`")
    if args.route == "emergency" and args.paths:
        raise ValueError("an emergency backfill Spec takes its route from the declared emergency, not from --paths")
    route, write = _spec_route(args, cfg)
    if not write:
        return 1  # nothing written: a script that goes on to edit the Spec must not think it exists
    path = workitems.new_object(
        Path("."),
        workitems.NewObject(
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
            base=args.base,
        ),
    )
    print(path)
    if linked is not None and args.no_link:
        print(
            f"not linked: {linked.as_posix()} is left to its writer, who adds this item to its `docs` list:\n"
            + strict_yaml.dump({"docs": [{"kind": "runbook", "path": path.as_posix(), "frozen": False}]}).rstrip()
        )
    elif linked is not None:
        # A runbook outlives the change that rolls it out: a living doc, checked to exist, never frozen.
        workitems.link_doc(linked, "runbook", path.resolve().relative_to(Path(".").resolve()).as_posix(), frozen=False)
        print(f"linked from {linked.as_posix()} as a living `docs` entry (frozen: false)")
    todo = {
        "runbook": "name the service, write steps a person can copy, run it once, record tested_on",
        "postmortem": "fill the timeline, causes, and action items with owners and dates",
        "proposal": "fill the needs and the goal, have a person record go_no_go",
    }.get(args.kind, "fill Context, Acceptance, tasks, and tests, write the test files")
    if args.kind == "spec" and workitems.spec_template(route, args.full) == "spec-short":
        scope = "" if args.paths else "the Task's scope, "  # --paths already wrote it
        todo = f"replace the TODOs (Intent, Context, Acceptance, Design, Rollback, {scope}the tests), write the test files"
    print(f"next: {todo}, then `aidd validate {path}`")
    if args.kind == "spec":
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        asks = workitems.required_docs(data, 0, cfg)
        if asks:
            shown = "; ".join(f"{k} ({'expected' if level == 'warn' else 'suggested'}: {why})" for k, level, why in asks)
            print(f"docs: {shown}; write each with `aidd new <kind> <topic> --spec {args.id}`")
    return 0


def cmd_import(args) -> int:
    """A short Spec from Spec Kit, OpenSpec, Kiro, or BMAD planning files, pointing at them."""

    if args.tool == "issues":
        return _import_issues(args)
    if not args.path or args.github or args.file or args.label or args.limit is not None:
        raise ValueError(f"`aidd import {args.tool}` takes the plan's path; --github, --file, --label, and --limit are for `aidd import issues`")
    arguments.enter_repo(args, "out", file_attrs=("path",))
    cfg = arguments.config_or_none()
    if cfg is None:
        raise ValueError(f"no {config.CONFIG_PATH}: `aidd init` first, so the route can be computed from the paths")
    path, lines = setup.build_imported_spec(args.tool, Path(args.path), Path("."), cfg, spec_id=args.id, out=args.out, title=args.title, ctype=args.type)
    print(path.as_posix())
    for line in lines:
        print(line)
    return 0


def _import_issues(args) -> int:
    """Suggested Specs from a tracker's issues: GitHub (--github OWNER/REPO) or any tracker's JSON export (--file)."""

    if bool(args.github) == bool(args.file) or args.path:
        raise ValueError("`aidd import issues` reads --github OWNER/REPO or --file issues.json (one of them)")
    if args.id or args.out or args.title or args.type:
        raise ValueError("--id, --out, --title, and --type are for a plan; an issue brings its own title, and ids follow the Specs folder")
    limit = min(max(args.limit if args.limit is not None else setup.DEFAULT_ISSUE_LIMIT, 1), setup.MAX_ISSUE_LIMIT)
    arguments.enter_repo(args, file_attrs=("file",))
    cfg = arguments.config_or_none()
    if cfg is None:
        raise ValueError(f"no {config.CONFIG_PATH}: `aidd init` first")
    if args.file:
        if args.label:
            raise ValueError("--label filters GitHub issues; filter the file before importing it")
        items = setup.issues_from_file(Path(args.file))
    else:
        items = setup.issues_from_github(args.github, label=args.label, limit=limit)
    for line in setup.write_issue_specs(Path("."), cfg, items, limit=limit):
        print(line)
    return 0


# Where a Spec is past change: a new Spec changes what it shipped.
_CLOSED = frozenset({"shipped", "done", "rolled_back", "cancelled"})


def cmd_revise(args) -> int:
    """`aidd revise <ID> "<why>"`: reopen an approved Spec. It adds a `revisions` entry (the day, what was wrong, the
    approved hash) to the Spec and commits it alone, with the Spec's own `assisted_by` trailers. The entry changes the
    hash, so the approval stops holding at HEAD and in the working tree, the guard opens the frozen files to their
    owners, and the next Spec approval freezes them again."""
    called_from = Path.cwd()  # a path argument is read from here, as the guard reads it
    arguments.enter_repo(args)
    cfg = config.load_file(config.CONFIG_PATH)
    why = " ".join(args.why.split())
    if not why or len(why) > 300:
        raise ValueError("say what was wrong in one sentence of 300 characters at most")
    top = Path.cwd().resolve()
    target = workitems.revise_target(args.spec, top=top, cwd=called_from, specs_dir=cfg.specs_dir)
    if not target.is_relative_to(top) or not target.is_file():
        raise ValueError(f"no such Spec: {args.spec}; name its id (`{cfg.specs_dir}/<ID>.md`) or its path")
    rel = target.relative_to(top).as_posix()
    path = Path(rel)
    text = path.read_text(encoding="utf-8")
    data = documents.split_front_matter(text, rel)[0]
    sid = str(data.get("id"))
    obs = workitems.Observer(Path("."), cfg)
    if not workitems.approval_holds(obs, rel, data):
        raise ValueError(f"{sid} has no Spec approval that holds: it is a draft, so change it directly and ask for approval when it is ready")
    here = git.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    try:
        base = git.default_base().removeprefix("origin/")
    except git.GitError:
        base = None
    if here in ("HEAD", base):
        # Only `aidd ship` moves the base branch; a revision is a commit on the Spec's own branch.
        raise ValueError(f"revise {sid} on its own branch (`spec/{sid}`), not on {'a detached HEAD' if here == 'HEAD' else here}")
    status = obs.status(obs.worktree(rel, text, data), data)
    if status in _CLOSED:
        raise ValueError(f"{sid} is {status}: what it shipped stays as approved. Write a new Spec for the change (`aidd new spec`)")
    committed = git.show("HEAD", rel)
    if committed is None or git.run(["--literal-pathspecs", "status", "--porcelain", "--", rel], check=False).strip():
        raise ValueError(f"{rel} has changes that are not committed: the revision is recorded on its own commit, so commit or set them aside first")
    was = workitems.spec_hash(committed, git.ls_tree("HEAD"))
    path.write_text(workitems.add_revision(text, why=why, on=dt.date.today().isoformat(), was=was), encoding="utf-8")
    trailers = "\n".join(f"Assisted-by: {x}" for x in data.get("assisted_by") or []) or "Assisted-by: none"
    git.run(["--literal-pathspecs", "commit", "-q", "-F", "-", "--", rel], input=f"docs(spec): revise {sid}\n\n{why}\n\n{trailers}\n")
    print(f"{sid} is a draft again: {why}")
    print(
        f"recorded in commit {git.rev_parse('HEAD')[:12]}; its approval of {was} no longer holds, so the Spec, its tests, its design files, and its frozen docs are open to their owners"
    )
    print(f"next: change what was wrong, `aidd validate {rel}`, then ask for Spec approval again; the card shows why")
    return 0


def _agent_id(coauthor: str) -> str:
    """An agent a `Co-authored-by` trailer names, as one word for `assisted_by`: its name in lower case with dashes,
    such as `claude-opus-5.5` for "Claude Opus 5.5 <noreply@anthropic.com>", or its address when it has no name."""
    name = coauthor.split("<", 1)[0].strip()
    return "-".join(name.lower().split()) if name else coauthor.strip("<> ")


def cmd_describe(args) -> int:
    """Print a starting Change Request block for the current branch; with --commit, record it in an empty commit instead."""
    arguments.enter_repo(args)
    arguments.base_from_spec(args)
    cfg = config.load_file(config.CONFIG_PATH)
    base = args.base or git.default_base()
    base_sha = git.merge_base(git.rev_parse(base), git.rev_parse("HEAD"))
    files = git.numstat(base_sha, "HEAD")
    if not files:
        raise ValueError(f"no changes between {base} and HEAD")
    paths = gate.changed_paths(files)
    commits = git.commits(base_sha, "HEAD")
    subjects = [c["message"].splitlines()[0] for c in commits if c.get("message", "").strip()]
    ctype = args.type or operate.conventional_type(subjects) or ("docs" if all(p.endswith((".md", ".rst", ".txt")) for p in paths) else "feat")
    a = gate.assess_route(
        paths=paths,
        cfg=cfg,
        ctype=ctype,
        risk={"dimensions": [], "reversible": True},
        confidence="high",
        task_count=1,
        changed_lines=sum(f["additions"] + f["deletions"] for f in files),
        binary_files=gate.counted_binaries(files, cfg),
        dependencies=gate.dependencies_added(".", base_sha, "HEAD", files),
        binary_paths=gate.binary_paths(files),
        content=gate.content_matches(".", cfg, base_sha, "HEAD", files),
    )
    bots = {b.lower() for b in cfg.get("identities", "bots", default=[])}
    # The `Assisted-by` values, which the gate requires each to be listed; with none, one id per agent a
    # `Co-authored-by` trailer names (as Claude Code writes by default), never its display name and address.
    declared = {m.strip() for c in commits for m in config.TRAILER.findall(c["message"]) if m.strip().lower() != "none"}
    assisted = sorted(declared or {_agent_id(x) for c in commits for x in config.agent_coauthors(c["message"], bots)})
    specs = workitems.find_specs_in_diff(files, cfg.specs_dir, lambda p: git.show("HEAD", p))
    spec = specs[0] if specs else None
    on_goal = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip().startswith(workitems.GOAL_PREFIX)
    if len(specs) > 1 or (specs and on_goal):
        # A goal's change: its Specs ship together with its plan, each judged as its own change, with one Merge approval.
        block = "\n".join(["```yaml aidd", strict_yaml.dump({"specs": specs}).rstrip("\n"), "```"])
    elif spec:
        block = f"```yaml aidd\nspec: {strict_yaml.scalar(spec)}\n```"
    elif a.required_route in ("normal", "major"):
        print(f"# The diff's minimum route is {a.required_route} ({a.lane} lane), because:")
        for line in gate.reason_lines(a):
            print(f"#   - {line}")
        print("# That needs a Spec:")
        print(f'#   aidd new spec <ID> --title "..." --type {ctype} --paths {" ".join(paths[:5])}{" ..." if len(paths) > 5 else ""}')
        print("# then put this block in the PR/MR description" + (" (or run `aidd describe --commit` once the Spec is committed)" if args.commit else "") + ":")
        print('```yaml aidd\nspec: "specs/<ID>.md"\n```')
        return 1 if args.commit else 0
    else:
        block = "\n".join(
            [
                "```yaml aidd",
                strict_yaml.dump({"route": a.required_route, "type": ctype, "scope": paths, "assisted_by": assisted}).rstrip("\n"),
                "```",
            ]
        )
    if not args.commit:
        print(f"# The diff's minimum route is {a.required_route} ({a.lane} lane), because:")
        for line in gate.reason_lines(a):
            print(f"#   - {line}")
        print(block)
        return 0
    # Local-first, with no PR/MR description: the block lives in an empty commit on the branch, where `aidd test`,
    # `aidd gate`, and `aidd ship` read it (the newest one wins). The trailers declare who wrote the branch, as the block does.
    trailers = "\n".join(f"Assisted-by: {x}" for x in assisted) or "Assisted-by: none"
    message = f"chore: aidd change request ({'spec' if spec else a.required_route})\n\n{block}\n\n{trailers}\n"
    git.run(["commit", "--allow-empty", "-q", "-F", "-"], input=message)
    print(block)
    print(f"recorded the block in commit {git.rev_parse('HEAD')[:12]}; `aidd test`, `aidd gate`, and `aidd ship` read it from there")
    return 0


def cmd_test(args) -> int:
    arguments.enter_repo(args, "spec", file_attrs=("body_file", "out", "html"))
    if args.merge_group:
        args.base = _merge_group_base(args.base)
    arguments.base_from_spec(args)
    changed = args.changed or args.watch

    def once() -> int:
        ev, notes = gate.run_tests(
            base=args.base,
            spec=args.spec,
            body=arguments.body(args) if args.body_file else None,
            out_dir=args.out,
            red=not args.no_red,
            red_in_place=args.red_in_place,
            pass_env=args.pass_env or (),
            changed=changed,
        )
        code = _print_test_results(ev, notes, args.out)
        if not args.watch and not args.merge_group:
            # This machine's record of the run, for the suite runs per head (`aidd metrics`); CI keeps its own.
            local_events.record_test(ev, code == 0)
        return code

    if not args.watch:
        return once()
    out = Path(args.out).resolve()
    exclude = out.relative_to(Path.cwd().resolve()).as_posix() if out.is_relative_to(Path.cwd().resolve()) else None

    def announce() -> None:
        print(f"\n--- {dt.datetime.now():%H:%M:%S} aidd test --changed ---")
        try:
            once()
        except (ValueError, OSError, LookupError, git.GitError, RuntimeError) as exc:
            print(f"aidd: {exc}", file=sys.stderr)  # keep watching: the next save may fix it
        print(f"watching for changes every {args.interval:g}s; Ctrl-C to stop")

    return gate.watch_tests(announce, interval_seconds=args.interval, exclude=exclude)


def _merge_group_base(base: str | None) -> str:
    """In a merge_group run: the commit the queue entry was built on, computed as the gate computes it."""
    from aidd import platforms

    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise ValueError("--merge-group reads the merge_group event from GITHUB_EVENT_PATH; run it in a merge_group workflow")
    group = platforms.merge_group_of(json.loads(Path(path).read_text(encoding="utf-8")))
    if group is None:
        raise ValueError("--merge-group: this event is not a merge_group event")
    head = git.rev_parse("HEAD")
    if head != group.sha:
        raise ValueError(f"--merge-group: the checkout is {head[:12]}, not the merge-group commit {group.sha[:12]}")
    parent, stacked = platforms.queue_parent(".", head, group.named_parent, git.rev_parse(base or f"origin/{group.base_ref}"))
    print(f"merge queue: pull request #{group.number}, built on {parent[:12]}" + (" (a previous queue entry)" if stacked else ""))
    return parent


def _print_test_results(ev: dict, notes: list[str], out: str) -> int:
    """Each result, then the notes and where the evidence is. Exit 1 when a result is bad, except in the Spec phase,
    where a failing green run is expected before Implement (marked `..`) and the red runs are early proof."""
    bad = False
    spec_phase = bool(ev.get("spec_phase"))
    for r in ev["results"]:
        good = (r["red_green"] == "green" and r["status"] == "passed") or (r["red_green"] == "red" and gate.red_ok(r))
        expected = not good and spec_phase and r["red_green"] == "green"
        bad |= not good and not expected
        mark = "ok" if good else ".." if expected else "!!"
        flaky = f" after {len(r['attempts'])} attempts (flaky)" if r.get("flaky") else ""
        print(f"[{mark}] {r['red_green']:5} {r['name']}: {r['status']} (exit {r['exit']}){flaky} log {arguments.repo_relative(Path(out) / r.get('log', ''))}")
    for n in notes:
        print(f"note: {n}")
    if ev["head_sha"] == ev["base_sha"]:
        print("note: this branch has no commit of its own yet, so nothing here proves a change; commit the work, then run `aidd test` again")
    partial = " (partial: the gate does not accept it)" if ev.get("partial") else ""
    print(f"evidence: {arguments.repo_relative(Path(out) / 'evidence.json')}  head {ev['head_sha'][:12]}  base {ev['base_sha'][:12]}{partial}")
    return 1 if bad else 0


def cmd_proposal(args) -> int:
    """Render a proposal's tables, or turn an accepted proposal into an Initiative and Epics."""

    given = args.file
    arguments.enter_repo(args, file_attrs=("file",))
    if re.fullmatch(r"PROP-\d+", given) and not Path(args.file).is_file():
        cfg = arguments.config_or_none_quiet()
        args.file = f"{cfg.proposals_dir if cfg else 'proposals'}/{given}/proposal.md"
    try:
        data = workitems.load_proposal(Path(args.file))
    except FileNotFoundError:
        print(f"aidd: {given}: no such file", file=sys.stderr)
        return 2
    except (documents.DocumentError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2  # bad input: a missing file, or one that is not a valid proposal
    if args.action == "matrix":
        print(workitems.proposal_matrix(data), end="")
        return 0
    if args.action in ("decide", "sign-off"):
        from aidd.cli.commands import proposal_decisions

        return proposal_decisions.proposal_decision(args, data)
    cfg = arguments.config_or_none()
    try:
        written = workitems.convert_proposal(data, Path(cfg.specs_dir if cfg else "specs"), cfg.get("owners", "default_team", default="") if cfg else "")
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote    {path.as_posix()}")
    print("next: the product manager ranks the Epics and writes Spec stubs under them (`/aidd-team:plan`)")
    return 0
