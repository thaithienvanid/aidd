"""The Work commands: status, risk, new, test, validate, explore, and prototype."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from aidd import config, risk, testing, workitems
from aidd.cli import arguments
from aidd.kernel import documents, git, resources, strict_yaml
from aidd.kernel import text as kernel_text


def cmd_status(args) -> int:
    """`aidd status`: the open work and each item's next step; with an id, that item alone."""
    arguments.enter_repo(args)
    cfg = arguments.config_or_none_quiet()
    answer: dict
    if cfg is None and not Path(config.CONFIG_PATH).is_file():
        answer = {"items": [], "due": [], "next": {"code": "setup.missing", "who": "person", "what": workitems.STEP_MEANINGS["setup.missing"]}}
    else:
        answer = workitems.open_work(Path("."), cfg, include_done=bool(args.id))
    if args.id:
        answer["items"] = [i for i in answer["items"] if i["id"] == args.id]
        if not answer["items"]:
            raise ValueError(f"no Spec, Epic, Initiative, or proposal has the id {args.id}")
        answer["due"] = []
        answer.pop("next", None)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
        return 0
    print(workitems.status_text(answer, mine="person" if args.mine else None), end="")
    return 0


def _tracked() -> list[str]:
    return [p for p in git.run(["ls-files", "-z"], check=False).split("\0") if p]


def cmd_risk(args) -> int:
    """`aidd risk`: the route for planned paths, the level of a command or an action, or every rule in force."""
    given = [bool(args.paths), bool(args.command_line), bool(args.action), bool(args.list)]
    if sum(given) != 1:
        raise ValueError("give one of --paths, --command, --action, or --list (`aidd risk --paths src/billing/charge.py`)")
    arguments.enter_repo(args)
    # A config that exists and does not load is an error here, never the built-in rules alone: the answer would say
    # `allow` or `report` where the repository's own rule says `ask`.
    cfg = arguments.config_or_none()
    rs = risk.rule_set(cfg)
    if args.list:
        answer: dict = {
            "rules": [
                {"action": r.action, "area": r.area, "branch": r.branch, "role": r.role, "level": r.level, "source": r.source, "locked": r.locked}
                for r in rs.rules
            ],
            "areas": {k: {"paths": len(v.get("paths", [])), "route": v.get("route", "minor")} for k, v in rs.areas.items()},
            "actions": sorted(rs.actions),
            "ignored": rs.ignored,
        }
        text = "\n".join(f"{r.label()}  ({r.source}{', locked' if r.locked else ''})" for r in rs.rules) + "\n"
        text += "areas: " + ", ".join(f"{k} ({v['route']})" for k, v in answer["areas"].items()) + "\n"
        text += "".join(f"note: {w}\n" for w in rs.ignored)
    elif args.paths:
        answer = risk.advice(cfg, args.paths, change_type=args.change_type, irreversible=args.irreversible, tracked=_tracked())
        text = f"route: {answer['route']} ({answer['lane']} lane)\n" + "".join(f"  - {r}\n" for r in answer["reasons"])
        text += f"edit: {answer['edit']['level']}" + (f" ({answer['edit']['rule']})" if answer["edit"]["rule"] else "") + "\n"
        if answer["lane"] == "spec":
            text += f"spec approval: {answer['spec_approval']}\n"
        for s in answer["specialists"]:
            text += f"specialist: {s['pool']}" + (f" ({', '.join(s['people'])})" if s["people"] else " (no one named in owners.specialists)") + "\n"
        text += f"next: {answer['step']}\n" + "".join(f"hint: {h}\n" for h in answer["hints"])
        if answer.get("project"):
            text += "\n" + "\n".join(config.project_markdown(answer["project"])) + "\n"
    elif args.command_line:
        answer = risk.command_level(rs, args.command_line, branch=args.branch, role=args.role)
        text = f"level: {answer['level']}\n" + "".join(
            f"  - {a['action']}{' on ' + a['branch'] + ' branch' if a['branch'] else ''}: {a['level']}" + (f" ({a['rule']})" if a["rule"] else "") + "\n"
            for a in answer["actions"]
        )
        if not answer["actions"]:
            text += "  no action's pattern matches it: allow, unless an action's examples describe what it does\n"
    else:
        level, rule = risk.level_of(rs, args.action, area=args.area, branch=args.branch, role=args.role)
        known = args.action in rs.actions
        answer = {"action": args.action, "level": level, "rule": rule.label() if rule else None, "known": known}
        text = f"level: {level}" + (f" ({rule.label()}, {rule.source})" if rule else " (no rule matches)") + "\n"
        if not known:
            text += f"note: {args.action} is not an action aidd knows; `aidd risk --list` lists them\n"
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(text, end="")
    return 0


def _spec_route(args, cfg: config.Config | None) -> tuple[str, list[str] | None]:
    """(route, scope) for `aidd new spec`: with --paths, the route computed from the paths (as `aidd risk --paths` gives
    it), raised to --route when that is higher, and the Task's scope; without, --route (default normal). A fast-lane
    change gets a Spec too when one is asked for, on the normal route, with a note."""
    chosen = args.route or "normal"
    if args.kind != "spec" or not args.paths:
        return chosen, None
    a = risk.advice(cfg, args.paths, change_type=args.change_type, irreversible=args.irreversible, tracked=_tracked())
    scope = workitems.folder_scope(args.paths, {p for hit in a["areas"] for p in hit["paths"]})
    print(f"route: the least route for these paths is {a['route']} ({a['lane']} lane)")
    for line in a["reasons"]:
        print(f"  - {line}")
    rank = config.ROUTE_RANK
    if a["lane"] == "fast":
        print("these paths need no Spec (the fast lane); writing one on the normal route as asked", file=sys.stderr)
        return max(chosen, "normal", key=rank.__getitem__), scope
    route = max(chosen, a["route"], key=rank.__getitem__)
    if args.route and rank[args.route] < rank[a["route"]]:
        print(f"route {a['route']}, not --route {args.route}: a Spec's route is never below the least route for its paths")
    return route, scope


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
        print("next: add a row per piece of feedback, as it arrives, with its source; a person confirms each")
        return 0
    if args.kind == "threat-model":
        print(
            f"{'the component already has its threat model: linked again' if existing else 'linked'} from {spec.as_posix()} as a living `docs` "
            "entry (frozen: false). Put this Spec's delta (the threat ids it adds, changes, or retires) in its Design, and update the model "
            "in the same change: Spec approval covers the delta, and Merge approval reviews the model"
        )
    elif args.kind in workitems.LIVING_DOCS:
        print(f"linked from {spec.as_posix()} as a living `docs` entry (frozen: false): humans fill it after Spec approval")
    else:
        print(f"linked from {spec.as_posix()} as a frozen `docs` entry: Spec approval covers it with the Spec")
    print(f"next: replace the TODOs, then `aidd validate {spec.as_posix()}`")
    return 0


def _new_repo_doc(args, cfg: config.Config | None) -> int:
    """`aidd new design-system`, `architecture`, `data-map`, `vendors`, `glossary`, `vulnerability-policy`, or `agents`: the
    repository's one of each."""
    if args.id or args.spec or args.area or args.no_link:
        raise ValueError(f"a {args.kind} belongs to the repository, not a Spec: run `aidd new {args.kind}` with no id, --spec, or --area")
    paths = workitems.new_repo_doc(Path("."), kind=args.kind, title=args.title or "", docs_dir=cfg.docs_dir if cfg else "docs")
    for p in paths:
        print(p.as_posix())
    route = {"design-system": "normal (the project_config area)", "agents": "normal: AGENTS.md steers the agents, so a person agrees to it"}.get(
        args.kind, "minor, a docs change"
    )
    if args.kind == "design-system":
        print("then: `node design/build.mjs` writes design/tokens.css, design/themes/<theme>.css, and DESIGN.md's token front matter")
        print("test: add `node design/build.mjs --check` (the drift test) to the config's `tests` list")
    if args.kind == "vulnerability-policy":
        print("then: serve security.txt (RFC 9116) with Contact and Expires; `aidd doctor` checks it when project.compliance targets cra")
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


def _new_product_prototype(args, cfg: config.Config | None) -> int:
    """`aidd new product-prototype`: the product designer's whole-product prototype, started once in `<docs>/design/app/`."""
    if args.id or args.spec or args.area or args.no_link:
        raise ValueError("the product prototype belongs to the repository, not a Spec: run `aidd new product-prototype` with no id, --spec, or --area")
    if args.force:
        raise ValueError("--force never overwrites the product prototype, a person's work: move docs/design/app/ aside first to start over")
    docs = cfg.docs_dir if cfg else "docs"
    product = args.title or Path.cwd().name
    for p in resources.team_tool("prototype").new_product_prototype(Path("."), docs_dir=docs, product=product):
        print(p.as_posix())
    print("next: list the flows and the navigation in sitemap.json, draw one file per flow in flows/, then `aidd prototype` to open it")
    print("each Spec with a design then updates its flow here in the same change, and `aidd validate` warns when it does not")
    return 0


def cmd_prototype(args) -> int:
    """`aidd prototype`: aidd-team's prototype tool on the product prototype, or on one prototype file, the file never
    changed. `--check` only checks; `--components` prints the component contract; `--screens` prints the screens;
    `--stories` checks Storybook's index.json against the contract."""
    if sum(map(bool, (args.check, args.components, args.screens, args.stories))) > 1:
        raise ValueError("--check checks the design; --components, --screens, and --stories read it: give one of them")
    arguments.enter_repo(args, "file", "new_design", file_attrs=("stories",))
    tool = resources.team_tool("prototype")
    if args.example:
        page = tool.view_example(Path("."))
        print(f"wrote {page.as_posix()}: open it in a browser; it is a way to learn, never a start\n{tool.file_url(page)}")
        if args.open:
            print(tool.open_page(page))
        return 0
    if args.new_design:
        print(tool.new_design(Path("."), args.new_design, args.title).as_posix())
        print(f"next: sketch the direction in it, then `aidd prototype {args.new_design}` to see it")
        return 0
    cfg = arguments.config_or_none()
    docs = cfg.docs_dir if cfg else "docs"
    if not args.file and not tool.product_prototype_dir(Path("."), docs).is_dir():
        raise ValueError(f"no product prototype in {docs}/design/app/: `aidd new product-prototype` starts one")
    if args.components or args.screens or args.stories:
        command = ["stories", args.stories] if args.stories else ["screens" if args.screens else "components"]
        return tool.main(["--docs", docs, *command, *([args.file] if args.file else [])])
    if args.file and args.check:
        problems, ok = tool.check_design_file(Path("."), args.file)
        print("\n".join(f"problem: {problem}" for problem in problems) or ok)
        if problems:
            print(tool.problems_line(len(problems), args.file))
        return 1 if problems else 0
    if args.file:
        out, problems = tool.build_design_file(Path("."), args.file)
    else:
        out, problems = tool.build_product_prototype(Path("."), docs, write=not args.check)
    where = args.file or f"{docs}/design/app/"
    for problem in problems:
        print(f"problem: {problem}")
    if out:
        print(f"wrote {out.as_posix()}: open it in a browser" + (f"; {args.file} is unchanged" if args.file else "") + f"\n{tool.file_url(out)}")
        if args.open:
            print(tool.open_page(out))
    elif not args.check:
        print(f"wrote no page: fix the problems above in {where}, then run `aidd prototype{' ' + args.file if args.file else ''}` again")
    if out and problems:
        print(tool.problems_line(len(problems), where))
    if args.check:
        print("the prototype is consistent" if not problems else tool.problems_line(len(problems), where))
    return 1 if problems else 0


def cmd_new(args) -> int:
    arguments.enter_repo(args, *(("id",) if args.kind == "exploration" else ()))
    cfg = arguments.config_or_none()
    if args.kind in workitems.REPO_DOCS:
        return _new_repo_doc(args, cfg)
    if args.kind == "product-prototype":
        return _new_product_prototype(args, cfg)
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
    route, scope = _spec_route(args, cfg)
    path = workitems.new_object(
        Path("."),
        workitems.NewObject(
            item_type=args.kind,
            id=args.id,
            title=args.title,
            route=route,
            scope=scope or None,
            dimensions=args.dimension or None,
            irreversible=args.irreversible,
            full=args.full,
            ctype=args.change_type,
            owner_team=args.owner_team or (cfg.get("owners", "default_owner_team", default="") if cfg else ""),
            parent=args.parent,
            specs_dir=cfg.specs_dir if cfg else "specs",
            audience=args.audience,
            addressee=args.addressee,
            proposals_dir=cfg.proposals_dir if cfg else "proposals",
            spec=args.spec,
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
        to_fill = "" if args.paths else "the Task's scope, "  # --paths already wrote it
        todo = f"replace the TODOs (Intent, Context, Acceptance, Design, Rollback, {to_fill}the tests), write the test files"
    print(f"next: {todo}, then `aidd validate {path}`")
    if args.kind == "spec":
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        asks = workitems.required_docs(data, 0, cfg)
        if asks:
            shown = "; ".join(f"{k} ({'expected' if level == 'warn' else 'suggested'}: {why})" for k, level, why in asks)
            print(f"docs: {shown}; write each with `aidd new <kind> <topic> --spec {args.id}`")
    return 0


def cmd_test(args) -> int:
    arguments.enter_repo(args, "spec", file_attrs=("out",))
    changed = args.changed or args.watch

    def once() -> int:
        ev, notes = testing.run_tests(
            base=args.base,
            spec=arguments.spec_by_id(args.spec) if args.spec else None,
            out_dir=args.out,
            red=not args.no_red,
            red_in_place=args.red_in_place,
            pass_env=args.pass_env or (),
            changed=changed,
        )
        return _print_test_results(ev, notes, args.out, no_red=args.no_red)

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
        print("watching for changes every second; Ctrl-C to stop")

    return testing.watch_tests(announce, exclude=exclude)


def _print_test_results(ev: dict, notes: list[str], out: str, *, no_red: bool = False) -> int:
    """Each result, then the notes and where the evidence is. Exit 1 when a result is bad, except in the Spec phase,
    where a failing green run is expected before Implement (marked `..`) and the red runs are early proof."""
    bad = False
    spec_phase = bool(ev.get("spec_phase"))
    for r in ev["results"]:
        good = (r["red_green"] == "green" and r["status"] == "passed") or (r["red_green"] == "red" and testing.red_ok(r))
        expected = not good and spec_phase and r["red_green"] == "green"
        bad |= not good and not expected
        mark = "ok" if good else ".." if expected else "!!"
        flaky = f" after {len(r['attempts'])} attempts (flaky)" if r.get("flaky") else ""
        print(f"[{mark}] {r['red_green']:5} {r['name']}: {r['status']} (exit {r['exit']}){flaky} log {arguments.repo_relative(Path(out) / r.get('log', ''))}")
    for n in notes:
        print(f"note: {n}")
    if ev["head_sha"] == ev["base_sha"]:
        print("note: this branch has no commit of its own yet, so nothing here proves a change; commit the work, then run `aidd test` again")
    partial = " (partial: a quick check, not the change's evidence)" if ev.get("partial") else ""
    print(f"evidence: {arguments.repo_relative(Path(out) / 'evidence.json')}  head {ev['head_sha'][:12]}  base {ev['base_sha'][:12]}{partial}")
    # A full run in a dirty tree proves nothing about the head commit, and its exit code is the evidence: so it fails.
    # A quick check (`--changed`, `--no-red`) may run mid-change.
    dirty_full = ev.get("dirty_tree") and not ev.get("partial") and not no_red
    return 1 if bad or dirty_full else 0


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
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)" + (f": {step}" if step else ""))
    return 1 if errors else 0


def cmd_explore(args) -> int:
    """An exploration's comparison page (`aidd new exploration` writes the exploration)."""
    from aidd import views

    arguments.enter_repo(args, "folder", file_attrs=("out",))
    folder = Path(args.folder)
    item = folder.parent.parent.name if folder.parent.name == "explore" else ""
    name = f"{item}-{folder.name}" if workitems.WORK_ID.fullmatch(item) else folder.name
    target = Path(args.out) if args.out else views.default_path("explore", name)
    views.write(target, views.comparison_page(folder))
    print(f"wrote {arguments.repo_relative(target)}")
    return 0
