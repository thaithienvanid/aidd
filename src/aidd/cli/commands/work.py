"""The Work commands: status, risk, records, trace, recall, new, test, validate, explore, and prototype."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from aidd import config, recall, records, risk, testing, workitems
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
    elif args.all_branches:
        answer = workitems.all_branches_work(Path("."), cfg, include_done=bool(args.id), keep=_delivery_team_keep(cfg, args.delivery_team))
    else:
        answer = workitems.open_work(Path("."), cfg, include_done=bool(args.id), keep=_delivery_team_keep(cfg, args.delivery_team))
    if args.id:
        answer["items"] = [i for i in answer["items"] if i["id"] == args.id]
        if not answer["items"]:
            raise ValueError(f"no Spec, Epic, Initiative, or proposal has the id {args.id}")
        answer["due"] = []
        answer.pop("next", None)
        here = f"worktree:{Path('.').resolve()}"
        for item in answer["items"]:
            # A version another branch holds links its own docs, which this worktree's file may not say.
            local = not item.get("places") or here in item["places"]
            item["history"] = workitems.work_item_history(Path("."), item["id"], item["path"], docs=local)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
        return 0
    if args.html:
        from aidd import views

        now = dt.datetime.now()
        page = views.status_page(answer, title=f"The open work in {Path.cwd().name}", as_of=f"{now.day} {now:%B %Y} at {now:%H:%M}")
        target = views.write(views.default_path("status", "work"), page)
        print(f"wrote {arguments.repo_relative(target)}: open it in a browser; it only reads, and a decision stays in the chat")
        return 0
    print(workitems.status_text(answer, mine="person" if args.mine else None), end="")
    if args.id:
        print("".join(workitems.history_text(i["history"]) for i in answer["items"]), end="")
    return 0


def _delivery_team_keep(cfg: config.Config | None, name: str | None):
    """With `--delivery-team`, what keeps that team's work items: its Epics and the Specs under them, and the Specs whose
    Task scope touches its areas, as `aidd risk --paths` reads the scope."""
    if not name:
        return None
    team, rules = config.delivery_team(cfg, name), risk.rule_set(cfg)

    def scope_areas(scope: list[str]) -> set[str]:
        return {a for p in risk.planned_paths(scope) for a in risk.areas_of(rules, p)}

    return lambda data: workitems.in_delivery_team(data, team, scope_areas)


def cmd_records(args) -> int:
    """`aidd records [add|push|pull]`: the records, newest first; one record written, after an answered ask or a reported
    action; or the records shared through a remote's `refs/aidd/records`."""
    if args.records_command == "add":
        if not (args.record_type and args.by and args.data):
            raise ValueError(
                "name the record: `aidd records add --type decision --by <harness>/<model> --data '<json>'`, such as "
                "`--by claude-code/claude-opus-5-5`; `--data -` reads the JSON from stdin"
            )
        if args.by.startswith("person:"):
            raise ValueError("an agent writes a record as itself: give `--by <harness>/<model>`, never a person's name")
        raw = sys.stdin.read() if args.data == "-" else args.data
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--data is not JSON: {exc}") from None
        if not isinstance(data, dict):
            raise ValueError("--data is the record's data: a JSON object, such as the decision's question, covers, and answer")
        record, path = records.add_record(args.record_type, data, by="agent:" + args.by.removeprefix("agent:"), subject=args.subject)
        print(f"Recorded {record['type']} {record['id']} in {path}")
        return 0
    if args.records_command in ("push", "pull"):
        # Push and pull run only from their exact words, `records push [remote]`, so the shapes a harness's ask rule
        # matches are the only ones that push. A rule is a net, never a control: SECURITY.md says so.
        words = getattr(args, "words", None)
        if words is not None and (words[:2] != ["records", args.records_command] or len(words) > 3 or any(w.startswith("-") for w in words)):
            raise ValueError(f"`aidd records {args.records_command}` takes only a remote, after it: `aidd records {args.records_command} origin`")
        args.remote = args.remote or "origin"
    elif args.remote:
        raise ValueError(f"unexpected {args.remote!r}: only `aidd records push` and `pull` take a remote")
    if args.records_command == "pull":
        added, refused = records.pull_records(args.remote)
        for line in refused:
            print(f"aidd: skipped {documents.one_line(line, 300)}", file=sys.stderr)
        print(f"Pulled {len(added)} record(s) from {args.remote}." if added else f"{args.remote} has no record this clone lacks.")
        return 0
    if args.records_command == "push":
        print(f"Pushing to {records.push_url(args.remote)}", file=sys.stderr)
        pulled, held = records.push_records(args.remote)
        print(
            f"Pushed {held} record(s) to {args.remote}'s refs/aidd/records" + (f", after pulling {pulled}." if pulled else ".")
            if held
            else "No records to push yet."
        )
        return 0
    found, unreadable = records.read_records(record_type=args.record_type, subject=args.subject)
    pulled_here = records.pulled_ids()
    if args.json:
        shown = sorted(pulled_here & {r["id"] for r in found})
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION, "records": found, "pulled": shown, "unreadable": unreadable}, indent=2))
        return 0
    for r in found:
        data = r["data"]  # a record of a newer type, or another's, may hold any shape: read only what is there
        question = data.get("question") if isinstance(data.get("question"), dict) else {}
        answer = data.get("answer") if isinstance(data.get("answer"), dict) else {}
        what = question.get("text") or data.get("said") or ""
        parts = [
            r.get("at", ""),
            r["type"],
            r.get("subject"),
            data.get("action"),
            answer.get("outcome"),
            f"by {r.get('by')}",
            r.get("written_with") == "mcp" and "through the MCP tool",
            answer.get("by") and f"answered by {answer['by']}",
            r["id"] in pulled_here and "pulled from a remote",
        ]
        line = "  ".join(documents.one_line(x, 80) for x in parts if x)  # a pulled record's fields are another's text
        print(f"{line}: {documents.one_line(what, 100)}" if what else line)
    if not found:
        print("No records yet. The agent writes one after each ask you answer and each action it reports (`aidd records add`).")
    if unreadable:
        print(
            f"aidd: {len(unreadable)} file(s) in {records.records_dir()} do not read as a record, so they were skipped: {documents.one_line(unreadable[0])}",
            file=sys.stderr,
        )
    return 0


def cmd_trace(args) -> int:
    """`aidd trace`: what stands behind a path or a work item, from git and aidd's files; the route is `aidd risk --paths` over its paths."""
    arguments.enter_repo(args, "target")
    cfg = arguments.config_or_none()
    answer = workitems.trace(
        Path("."),
        cfg,
        args.target,
        commits=args.commits,
        route=lambda paths: {"schema_version": arguments.JSON_SCHEMA_VERSION} | risk.advice(cfg, paths, tracked=_tracked()),
    )
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(workitems.trace_text(answer), end="")
    return 0


def cmd_recall(args) -> int:
    """`aidd recall`: the lines of the team's writing that hold every word; a cache of the files, never evidence or a yes."""
    arguments.enter_repo(args)
    answer = recall.search(Path("."), arguments.config_or_none_quiet(), args.recall_words, limit=args.limit)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(recall.search_text(answer), end="")
    return 0


def _tracked() -> list[str]:
    return [p for p in git.run(["ls-files", "-z"], check=False).split("\0") if p]


def cmd_risk(args) -> int:
    """`aidd risk`: the route for planned paths, the level of a command or an action, or every rule in force."""
    given = [bool(args.paths), bool(args.command_line), bool(args.action), bool(args.list), bool(args.suggest)]
    if sum(given) != 1:
        raise ValueError("give one of --paths, --command, --action, --list, or --suggest (`aidd risk --paths src/billing/charge.py`)")
    arguments.enter_repo(args)
    # A config that exists and does not load is an error here, never the built-in rules alone: the answer would say
    # `allow` or `report` where the repository's own rule says `ask`.
    cfg = arguments.config_or_none()
    rs = risk.rule_set(cfg)
    if args.list:
        answer: dict = {
            "rules": [
                {"action": r.action, "area": r.area, "branch": r.branch, "role": r.role, "level": r.level, "source": r.source, "locked": r.locked}
                | ({"environment": r.environment} if r.environment else {})
                for r in rs.rules
            ],
            "areas": {k: {"paths": len(v.get("paths", [])), "route": v.get("route", "minor")} for k, v in rs.areas.items()},
            "actions": sorted(rs.actions),
            "ignored": rs.ignored,
        }
        text = "\n".join(f"{r.label()}  ({r.source}{', locked' if r.locked else ''})" for r in rs.rules) + "\n"
        text += "areas: " + ", ".join(f"{k} ({v['route']})" for k, v in answer["areas"].items()) + "\n"
        text += "".join(f"note: {w}\n" for w in rs.ignored)
    elif args.suggest:
        answer = risk.rule_suggestions(rs)
        text = "".join(
            f"{risk.Rule(s['action'], 'ask', s['area'], s['branch'], s['role']).label()} ({s['source']}): {s['asks']} asks, every one accepted, "
            "by the records an agent wrote in this clone, which nothing verifies. "
            f"To stop asking, a person may add {_rule_yaml(s)} to risks.rules in .aidd/config.yaml.\n"
            for s in answer["suggestions"]
        ) or (
            f"No rule to suggest yet. A suggestion needs {answer['min_asks']} asks of one rule, every one accepted, for an action a person can "
            "undo; `aidd records --type decision` lists the asks.\n"
        )
    elif args.paths:
        answer = risk.advice(cfg, args.paths, change_type=args.change_type, irreversible=args.irreversible, tracked=_tracked())
        text = f"route: {answer['route']} ({answer['lane']} lane)\n" + "".join(f"  - {r}\n" for r in answer["reasons"])
        text += f"edit: {answer['edit']['level']}" + (f" ({answer['edit']['rule']}, {answer['edit']['source']})" if answer["edit"]["rule"] else "") + "\n"
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
            f"  - {a['action']}{' on ' + a['branch'] + ' branch' if a['branch'] else ''}{' to ' + a['environment'] if a['environment'] else ''}: {a['level']}"
            + (f" ({a['rule']}, {a['source']})" if a["rule"] else "")
            + "\n"
            for a in answer["actions"]
        )
        if not answer["actions"]:
            text += "  no action's pattern matches it: allow, unless an action's examples describe what it does\n"
    else:
        level, rule = risk.level_of(rs, args.action, area=args.area, branch=args.branch, role=args.role)
        known = args.action in rs.actions
        answer = {"action": args.action, "level": level, "rule": rule.label() if rule else None, "source": rule.source if rule else None, "known": known}
        text = f"level: {level}" + (f" ({rule.label()}, {rule.source})" if rule else " (no rule matches)") + "\n"
        if not known:
            text += f"note: {args.action} is not an action aidd knows; `aidd risk --list` lists them\n"
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(text, end="")
    return 0


def _rule_yaml(s: dict) -> str:
    """A suggested rule as a config line reads it: `{action: git.push, branch: shared, level: report}`, with a value
    YAML would read as something else quoted, such as `*`."""

    def value(v: str) -> str:
        return v if re.fullmatch(r"[A-Za-z0-9_.-]+", v) else json.dumps(v)

    narrow = "".join(f", {k}: {value(s[k])}" for k in ("area", "branch", "role") if s[k])
    return f"`{{action: {value(s['action'])}{narrow}, level: report}}`"


def _spec_route(args, cfg: config.Config | None) -> tuple[str, list[str] | None]:
    """(route, scope) for `aidd new spec`: with --paths, the route computed from the paths (as `aidd risk --paths` gives
    it), raised to --route when that is higher, and the Task's scope; without, --route (default normal). A fast-lane
    change gets a Spec too when one is asked for, on the normal route, with a note."""
    chosen = args.route or "normal"
    if args.type != "spec" or not args.paths:
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
    """`aidd new <type> <topic> --spec ID`: a linked document from its template, and its `docs` entry in the Spec.
    A feedback log belongs to no Spec: `aidd new feedback <topic>` writes it alone."""
    if args.type in workitems.UNLINKED_DOCS and args.spec:
        why = {"feedback": "each entry names its Spec or hypothesis in its row", "srs": "its topic is an Initiative, an Epic, or `product`"}
        raise ValueError(f"a {args.type} belongs to no one Spec: drop --spec; {why.get(args.type, 'it covers its subject across every Spec')}")
    if args.no_link and args.type in workitems.UNLINKED_DOCS:
        raise ValueError(f"--no-link is for a doc a Spec links; a {args.type} is never linked")
    if args.type not in workitems.UNLINKED_DOCS and not args.spec:
        raise ValueError(f"--spec is required: a {args.type} doc belongs to the Spec that links it (`aidd new {args.type} <topic> --spec SPEC-42`)")
    docs_dir = cfg.docs_dir if cfg else "docs"
    model = Path(docs_dir) / workitems.THREAT_MODELS / f"{kernel_text.slug(args.id or '')}.md"
    existing = args.type == "threat-model" and model.is_file()
    path, spec = workitems.new_doc(
        Path("."),
        workitems.NewDoc(
            doc_type=args.type,
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
        entry = {"type": args.type, "path": path.as_posix()} | ({"frozen": False} if args.type in workitems.LIVING_DOCS else {})
        print(f"not linked: {spec.as_posix()} is left to its writer, who adds this item to its `docs` list:\n{strict_yaml.dump({'docs': [entry]}).rstrip()}")
        return 0
    if spec is None:
        print(f"next: {workitems.UNLINKED_NEXT[args.type]}")
        return 0
    if args.type == "threat-model":
        print(
            f"{'the component already has its threat model: linked again' if existing else 'linked'} from {spec.as_posix()} as a living `docs` "
            "entry (frozen: false). Put this Spec's delta (the threat ids it adds, changes, or retires) in its Design, and update the model "
            "in the same change: Spec approval covers the delta, and Merge approval reviews the model"
        )
    elif args.type in workitems.LIVING_DOCS:
        print(f"linked from {spec.as_posix()} as a living `docs` entry (frozen: false): humans fill it after Spec approval")
    else:
        print(f"linked from {spec.as_posix()} as a frozen `docs` entry: Spec approval covers it with the Spec")
    print(f"next: replace the TODOs, then `aidd validate {spec.as_posix()}`")
    return 0


def _new_repo_doc(args, cfg: config.Config | None) -> int:
    """`aidd new design-system`, `architecture`, `data-map`, `vendors`, `glossary`, `vulnerability-policy`, or `agents`: the
    repository's one of each."""
    if args.id or args.spec or args.area or args.no_link:
        raise ValueError(f"a {args.type} belongs to the repository, not a Spec: run `aidd new {args.type}` with no id, --spec, or --area")
    paths = workitems.new_repo_doc(Path("."), doc_type=args.type, title=args.title or "", docs_dir=cfg.docs_dir if cfg else "docs")
    for p in paths:
        print(p.as_posix())
    route = {"design-system": "normal (the project_config area)", "agents": "normal: AGENTS.md steers the agents, so a person agrees to it"}.get(
        args.type, "minor, a docs change"
    )
    if args.type == "design-system":
        print("then: `node design/build.mjs` writes design/tokens.css, design/themes/<theme>.css, and DESIGN.md's token front matter")
        print("test: add `node design/build.mjs --check` (the drift test) to the config's `tests` list")
    if args.type == "vulnerability-policy":
        print("then: serve security.txt (RFC 9116) with Contact and Expires; `aidd doctor` checks it when project.compliance targets cra")
    print(f"next: replace the TODOs, and commit it as its own change: route {route}")
    if args.type in workitems.LIVING_DOCS:
        print(f"a Spec that changes what it records links it as a living doc: a `docs` item with type: {args.type}, frozen: false")
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
    if args.serve and args.check:
        raise ValueError("--serve serves the page and --check only checks it: run `aidd prototype --check` first, then --serve")
    if (args.lan or args.port != 8765) and not args.serve:
        raise ValueError("--lan and --port go with --serve: add --serve to serve the page")
    arguments.enter_repo(args, "file", "new_design", file_attrs=("stories",))
    tool = resources.team_tool("prototype")
    if args.example:
        page = tool.view_example(Path("."))
        print(f"wrote {page.as_posix()}: open it in a browser; it is a way to learn, never a start\n{tool.file_url(page)}")
        print("next: `aidd new design-spec <topic> --spec <ID> --prototype` starts a design of your own")
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
        raise ValueError(
            f"no product prototype in {docs}/design/app/: name a design file, such as `aidd prototype --check <file>`, or start one with `aidd new product-prototype`"
        )
    if args.serve:
        return int(tool.serve_design(Path("."), args.file, docs, lan=args.lan, port=args.port))
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
    arguments.enter_repo(args, *(("id",) if args.type == "exploration" else ()))
    cfg = arguments.config_or_none()
    if args.type in workitems.REPO_DOCS:
        return _new_repo_doc(args, cfg)
    if args.type == "product-prototype":
        return _new_product_prototype(args, cfg)
    if args.type == "contract":
        return _new_contract(args, cfg)
    if args.type == "exploration":
        return _new_exploration(args, cfg)
    if args.type in workitems.ID_PREFIXES:
        # `aidd new spec "Add a discount"`: a first word that is no id is the title, and the id is the next free one.
        if args.id and not workitems.WORK_ID.fullmatch(args.id) and args.title is None:
            args.title, args.id = args.id, None
        if not args.id:
            folder = (cfg.proposals_dir if cfg else "proposals") if args.type == "proposal" else (cfg.specs_dir if cfg else "specs")
            args.id = workitems.next_id(Path("."), workitems.ID_PREFIXES[args.type], folder)
    if not args.id:
        raise ValueError(f"an id is required for a {args.type}: `aidd new {args.type} <id>`")
    if args.type in workitems.DOC_TEMPLATES:
        return _new_doc(args, cfg)
    if not args.title:
        raise ValueError(f"--title is required for a {args.type}")
    if args.area:
        raise ValueError(f"--area names a linked document's folder: use it with {', '.join(sorted(set(workitems.DOC_TEMPLATES) - workitems.UNLINKED_DOCS))}")
    if args.no_link and not (args.type == "runbook" and args.spec):
        raise ValueError("--no-link is for a document a Spec links: a linked doc, or a runbook with --spec")
    linked = workitems.find_spec_by_id(Path("."), cfg.specs_dir if cfg else "specs", args.spec) if args.type == "runbook" and args.spec else None
    if args.type != "spec" and (args.paths or args.dimension or args.irreversible):
        raise ValueError("--paths, --dimension, and --irreversible compute a Spec's route: use them with `aidd new spec`")
    if args.route == "emergency" and args.paths:
        raise ValueError("an emergency backfill Spec takes its route from the declared emergency, not from --paths")
    route, scope = _spec_route(args, cfg)
    path = workitems.new_object(
        Path("."),
        workitems.NewObject(
            item_type=args.type,
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
            + strict_yaml.dump({"docs": [{"type": "runbook", "path": path.as_posix(), "frozen": False}]}).rstrip()
        )
    elif linked is not None:
        # A runbook outlives the change that rolls it out: a living doc, checked to exist, never frozen.
        workitems.link_doc(linked, "runbook", path.resolve().relative_to(Path(".").resolve()).as_posix(), frozen=False)
        print(f"linked from {linked.as_posix()} as a living `docs` entry (frozen: false)")
    todo = {
        "runbook": "name the service, write steps a person can copy, run it once, record tested_on",
        "postmortem": "fill the timeline, causes, and action items with owners and dates",
        "proposal": "fill the needs and the goal, have a person record go_no_go",
    }.get(args.type, "fill Context, Acceptance, tasks, and tests, write the test files")
    if args.type == "spec" and workitems.spec_template(route, args.full) == "spec-short":
        to_fill = "" if args.paths else "the Task's scope, "  # --paths already wrote it
        todo = f"replace the TODOs (Intent, Context, Acceptance, Design, Rollback, {to_fill}the tests), write the test files"
    print(f"next: {todo}, then `aidd validate {path}`")
    if args.type == "spec":
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))
        asks = workitems.required_docs(data, 0, cfg)
        if asks:
            shown = "; ".join(f"{k} ({'expected' if level == 'warn' else 'suggested'}: {why})" for k, level, why in asks)
            print(f"docs: {shown}; write each with `aidd new <type> <topic> --spec {args.id}`")
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
