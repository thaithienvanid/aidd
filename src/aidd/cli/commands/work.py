"""The Work commands: risk, new, agree, test, explore, and prototype (status, and records with recall, have modules of their own)."""

from __future__ import annotations

import datetime as dt
import json
import re
import shlex
import sys
from pathlib import Path

from aidd import config, risk, setup, workitems
from aidd.cli import arguments
from aidd.cli.commands import risk_answers
from aidd.kernel import command_names, documents, git, git_reads, resources, strict_yaml
from aidd.kernel import text as kernel_text

# The modes of `aidd risk`, by the attribute that holds each flag's value, in the order the usage line gives them.
RISK_MODES = {"paths": "--paths", "command_line": "--command", "action": "--action", "list": "--list", "suggest": "--suggest"}
# Each qualifier flag, by its attribute: the modes it goes with, what it means, and what else a person does. A qualifier given
# with another mode would be ignored without a word, so it is an error that says so.
RISK_QUALIFIERS: dict[str, tuple[str, tuple[str, ...], str, str]] = {
    "change_type": ("--change-type", ("--paths",), "is the change type of planned paths", ""),
    "dimension": ("--dimension", ("--paths",), "is a risk dimension of planned paths", ""),
    "irreversible": ("--irreversible", ("--paths",), "says a planned change cannot be reverted", ""),
    "area": ("--area", ("--action",), "is the area an action touches", ""),
    "branch": ("--branch", ("--command", "--action"), "is the branch a command or an action reaches", ""),
    "folder": ("--folder", ("--command",), "names the folder a --command runs in", "or run aidd risk there"),
    "role": ("--role", ("--command", "--action"), "is the aidd-team role that acts", ""),
    "route": ("--route", ("--action",), "narrows the rule of an --action", ""),
}


def _refuse_stray_flags(args) -> None:
    """`aidd risk` answers one mode, and each qualifier goes with its own modes: two modes, or a qualifier beside a mode it does
    not go with, is an error that names both, never an answer to the part that was read."""
    modes = [flag for attr, flag in RISK_MODES.items() if getattr(args, attr, None)]
    every = ", ".join(RISK_MODES.values()).replace(", --suggest", ", or --suggest")
    if not modes:
        raise ValueError(f"give one of {every} (`aidd risk --paths src/billing/charge.py`)")
    if len(modes) > 1:
        raise ValueError(f"give only one of {every}; you gave {' and '.join(modes)} (`aidd risk --paths src/billing/charge.py`)")
    for attr, (flag, goes_with, meaning, otherwise) in RISK_QUALIFIERS.items():
        value = getattr(args, attr, None)
        if value and not isinstance(value, arguments.Default) and modes[0] not in goes_with:
            goes = " or ".join(goes_with)
            raise ValueError(f"{flag} {meaning}, so it goes with {goes} only, and you gave {modes[0]}: drop {flag}, {otherwise or f'or give {goes}'}")
    _refuse_a_stray_route(args)


def _refuse_a_stray_route(args) -> None:
    """`--route` narrows the `spec.approve` rule alone, so it goes with `--action spec.approve` and nothing else."""
    if args.route and args.action != "spec.approve":
        raise ValueError(
            "--route narrows `--action spec.approve` only, the one rule that takes a route: drop --route, or run `aidd risk --action spec.approve --route normal`"
        )


def _refuse_unknown_names(rs: risk.RuleSet, args) -> None:
    """An action, area, or role no rule can name reads as `allow`, the lowest level, so `--action pr.mrge` is an error that
    names the closest action, never an answer."""
    from aidd import knowledge

    for kind, name, valid, step in (
        ("action", args.action, rs.actions, "`aidd risk --list` lists every action, and a config adds one under `risks.actions`."),
        ("area", args.area, rs.areas, "`aidd risk --list` lists every area, and a config adds one under `risks.areas`."),
        ("role", args.role, [*knowledge.roles()["roles"], *(r.role for r in rs.rules if r.role)], "`aidd explain --list` lists the team's roles."),
    ):
        if name and (why := risk.unknown_name(kind, name, valid, step)):
            raise ValueError(f"--{kind} {why}")


@git_reads.shared_reads()
def cmd_risk(args) -> int:
    """`aidd risk`: the route for planned paths, the level of a command or an action, or every rule in force."""
    _refuse_stray_flags(args)
    where, outside = arguments.enter_where_it_runs(args)
    note = "this folder is in no git repository, so {}. For the exact answer, run aidd risk inside the repository the change touches{}."
    unknown = "the branch and the repository's own rules are unknown"
    if outside and args.suggest:
        raise ValueError("aidd risk --suggest reads the decision records a clone holds, and this folder is in no git repository: run it inside one")
    # A config that exists and does not load is an error here, never the built-in rules alone: the answer would say
    # `allow` or `report` where the repository's own rule says `ask`.
    cfg = arguments.config_or_none()
    rs = risk.rule_set(cfg)
    _refuse_unknown_names(rs, args)
    if args.list:
        answer, text = risk_answers.rules_list(rs)
    elif args.suggest:
        answer = risk.rule_suggestions(rs)
        text = "".join(
            f"{risk.Rule(s['action'], 'ask', s['area'], s['branch'], s['role']).label()} ({s['source']}): {s['ask_count']} asks, every one accepted, "
            "by the records an agent wrote in this clone, which nothing verifies. "
            f"To stop asking, a person may add {_rule_yaml(s)} to risks.rules in .aidd/config.yaml.\n"
            for s in answer["suggestions"]
        ) or (
            f"No rule to suggest yet. A suggestion needs {answer['min_asks']} asks of one rule, every one accepted, for an action a person can "
            "undo; `aidd records --type decision` lists the asks.\n"
        )
    elif args.paths:
        answer = risk_answers.cap_area_paths(
            risk.advice(cfg, args.paths, change_type=args.change_type, declared=_declared(args), tracked=arguments.tracked_files()),
            (cfg or config.EMPTY).max_paths_shown,
        )
        if planned := getattr(args, "planned", None):  # the next step names the paths from the top, so it means the same from anywhere
            answer["next"]["what"] = answer["next"]["what"].replace(risk.shown_paths(args.paths), risk.shown_paths(_step_paths(args, cfg, planned, answer)))
        answer["hints"] += [note.format("a glob stands for no tracked file", "")] if outside else []
        answer["hints"] += _two_readings_hint(args, cfg) + _pack_hint(answer, outside)
        text = f"route: {answer['route']} ({config.route_words()[answer['route']]})\n" + "".join(f"  - {r}\n" for r in answer["reasons"])
        text += f"edit: {answer['edit']['level']}" + (f" ({answer['edit']['rule']}, {answer['edit']['source']})" if answer["edit"]["rule"] else "") + "\n"
        if answer["route"] in config.SPEC_FIRST_ROUTES:
            text += f"spec approval: {answer['spec_approval']}\n"
        solo = ((cfg or config.EMPTY).profile) == "solo"
        for s in answer["specialists"]:
            nobody = " (you decide it, as the one person the solo profile has)" if solo else " (no one named in owners.specialists)"
            text += f"specialist: {s['pool']}" + (f" ({', '.join(documents.one_line(x) for x in s['people'])})" if s["people"] else nobody) + "\n"
        text += f"next: {answer['next']['what']}\n" + "".join(f"hint: {h}\n" for h in answer["hints"])
        if answer.get("project"):
            text += "\n" + "\n".join(config.project_markdown(answer["project"])) + "\n"
    elif args.command_line:
        answer = risk.command_level(rs, args.command_line, branch=args.branch, role=args.role, cwd=where)
        answer["notes"] = [*answer.get("notes", []), *risk.command_notes(rs, answer), *risk_answers.trunk_note(answer, where)]
        if not answer["actions"]:
            answer["notes"].append(risk_answers.NO_ACTION_NOTE)
        if args.folder and where is None:
            answer["notes"] += [risk_answers.folder_note(args.folder)]
        elif outside:
            answer["notes"] += [note.format(f"{unknown}: a command only its config names reads as no action", ", or give --folder <it>")]
        text = f"level: {answer['level']}\n" + "".join(
            f"  - {a['action']}{' on ' + a['branch'] + ' branch' if a['branch'] else ''}{' to ' + a['environment'] if a['environment'] else ''}: {a['level']}"
            + (f" ({a['rule']}, {a['source']})" if a["rule"] else " (no rule matches)")
            + "\n"
            for a in answer["actions"]
        )
        text += "".join(f"note: {n}\n" for n in answer["notes"])
    else:
        level, rule = risk.level_on_any_branch(rs, args.action, area=args.area, branch=args.branch, role=args.role, route=args.route)
        answer = {"action": args.action, "level": level, "rule": rule.label() if rule else None, "source": rule.source if rule else None}
        answer |= {"reason": rule.reason} if rule and rule.reason else {}
        text = f"level: {level}" + (f" ({rule.label()}, {rule.source})" if rule else " (no rule matches)") + "\n"
        text += f"why: {documents.one_line(rule.reason)}\n" if rule and rule.reason else ""  # a config's text: one line
        notes = risk_answers.action_notes(rs, args, rule, level)
        answer |= {"notes": notes + [note.format(unknown, "")]} if outside else ({"notes": notes} if notes else {})
        text += "".join(f"note: {n}\n" for n in answer.get("notes", []))
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        # Each value above came from a committed file or an argument, and a fetched branch's file is another's text: every line prints as one safe line.
        print("\n".join(documents.one_line(line, 4000) for line in text.split("\n")), end="")
    return 0


def _pack_hint(answer: dict, outside: bool) -> list[str]:
    """The hints for the domain packs the matched areas bring: load an installed one by name, and add one that is missing; the MCP tool runs this too."""
    return [] if outside else setup.pack_hint(Path(git.repository_top() or "."), [a["area"] for a in answer["areas"]])


def _rule_yaml(s: dict) -> str:
    """A suggested rule as a config line reads it: `{action: git.push, branch: shared, level: report}`, with a value
    YAML would read as something else quoted, such as `*`."""

    def value(text: str) -> str:
        return text if re.fullmatch(r"[A-Za-z0-9_.-]+", text) else json.dumps(text)

    narrow = "".join(f", {k}: {value(s[k])}" for k in ("area", "branch", "role") if s[k])
    return f"`{{action: {value(s['action'])}{narrow}, level: report}}`"


def _declared(args) -> risk.DeclaredRisk:
    """The risk `--dimension` and `--irreversible` declare, of `aidd risk --paths` and `aidd new spec` alike."""
    return risk.DeclaredRisk(tuple(args.dimension or ()), args.irreversible)


def _level_of(args, cfg: config.Config | None, paths: list[str]) -> tuple[str, str]:
    """The route and the edit level `aidd risk --paths` gives for these paths."""
    a = risk.advice(cfg, paths, change_type=args.change_type, declared=_declared(args), tracked=arguments.tracked_files())
    return a["route"], a["edit"]["level"]


def _step_paths(args, cfg: config.Config | None, planned: arguments.PlannedPaths, answer: dict) -> list[str]:
    """The paths the next step names, as the repository's top reads them: the typed folder's reading, else the top's,
    else every reading, whichever first routes as the answer did, so running the step from the top never routes lower."""
    want = (answer["route"], answer["edit"]["level"])
    for paths in (planned.here, planned.top):
        if paths == planned.every or _level_of(args, cfg, paths) == want:
            return paths
    return planned.every


def _two_readings_hint(args, cfg: config.Config | None) -> list[str]:
    """A hint when the planned paths, typed in a subfolder, route one way from there and another from the top. The
    answer routes on both, so the stricter wins; the hint names both readings."""
    planned = getattr(args, "planned", None)
    if planned is None or not planned.differ():
        return []
    here, top = _level_of(args, cfg, planned.here), _level_of(args, cfg, planned.top)
    if here == top:
        return []
    return [
        f"a path typed in a subfolder reads two ways: {', '.join(planned.here)} from here routes {here[0]} (edit {here[1]}), "
        f"and {', '.join(planned.top)} from the repository's top routes {top[0]} (edit {top[1]}); this answer takes the stricter"
    ]


def _spec_route(args, cfg: config.Config | None) -> tuple[str, list[str] | None]:
    """(route, scope) for `aidd new spec`: with --paths, the route computed from the paths (as `aidd risk --paths` gives
    it), raised to --route when that is higher, and the Task's scope; without, --route (default normal), raised to the route
    --dimension and --irreversible give, as `aidd validate` holds it. A no-Spec change gets a Spec too when one is asked for, on the
    normal route, with a note."""
    chosen = args.route or "normal"
    if args.type != "spec" or not args.paths:
        declared = _declared(args) if args.type == "spec" and chosen != "emergency" else risk.DeclaredRisk()
        need = config.route_of_risk(declared.dimensions, declared.irreversible)
        if config.ROUTE_RANK[need] > config.ROUTE_RANK[chosen]:
            print(f"route: {need}, the least route for the declared risk ({config.route_words()[need]})")
            chosen = need
        return chosen, None
    a = risk.advice(cfg, args.paths, change_type=args.change_type, declared=_declared(args), tracked=arguments.tracked_files())
    planned = getattr(args, "planned", None)
    typed = planned.here if planned else args.paths  # the typed folder's reading, from the repository's top
    over = workitems.scope_over_acceptance_tests(typed)
    scope = workitems.folder_scope([p for p in typed if p not in over], {p for hit in a["areas"] for p in hit["paths"]})
    print(f"route: the least route for these paths is {a['route']} ({config.route_words()[a['route']]})")
    for line in a["reasons"]:
        print(f"  - {line}")
    for hint in _two_readings_hint(args, cfg):
        print(f"hint: {hint}")
    if planned and planned.differ():
        moved = [(h, t) for h, t in zip(planned.here, planned.top, strict=True) if h != t]
        print(
            f"hint: the scope takes {', '.join(h for h, _ in moved)}, as a shell reads {', '.join(planned.typed)} from this folder; "
            f"to scope {', '.join(t for _, t in moved)} from the repository's top, run aidd new spec there"
        )
    if over:
        print(f"scope: left out {', '.join(over)}: it would hold the acceptance tests Spec approval freezes; name the unit-test folder, such as tests/unit/")
    rank = config.ROUTE_RANK
    if a["route"] == "minor":
        print("these paths need no Spec; writing one on the normal route as asked", file=sys.stderr)
        return max(chosen, "normal", key=rank.__getitem__), scope
    route = max(chosen, a["route"], key=rank.__getitem__)
    if args.route and rank[args.route] < rank[a["route"]]:
        print(f"route {a['route']}, not --route {args.route}: a Spec's route is never below the least route for its paths")
    return route, scope


def _validate_step(path: Path) -> str:
    """`aidd validate` for the file `aidd new` wrote, as a command when its path is a plain name (`command_names`: the Specs
    folder is the config's text), else in words."""
    word = command_names.quoted(path.as_posix())
    return f"`aidd validate -- {word}`" if word else f"validate it by hand: {command_names.NO_COMMAND}"


def _new_doc(args, cfg: config.Config | None) -> int:
    """`aidd new <type> <topic> --spec ID`: a linked document from its template, and its `docs` entry in the Spec.
    A feedback log belongs to no Spec: `aidd new feedback <topic>` writes it alone."""
    if args.type in workitems.UNLINKED_DOCS and args.spec:
        raise ValueError(f"a {args.type} belongs to no one Spec: drop --spec; {config.item_type_rows()[args.type]['without_spec']}")
    if args.no_link and args.type in workitems.UNLINKED_DOCS:
        raise ValueError(f"--no-link is for a doc a Spec links; a {args.type} is never linked")
    if args.type not in workitems.UNLINKED_DOCS and not args.spec:
        raise ValueError(f"--spec is required: a {args.type} doc belongs to the Spec that links it (`aidd new {args.type} <topic> --spec SPEC-42`)")
    docs_dir = (cfg or config.EMPTY).docs_dir
    model = Path(docs_dir) / (workitems.TEST_PLANS if args.living else workitems.THREAT_MODELS) / f"{kernel_text.slug(args.id or '')}.md"
    existing = (args.type == "threat-model" or args.living) and model.is_file()
    path, spec = workitems.new_doc(
        Path("."),
        workitems.NewDoc(
            doc_type=args.type,
            topic=args.id,
            spec_id=args.spec,
            doc_folder=args.doc_folder,
            title=args.title or "",
            docs_dir=docs_dir,
            specs_dir=(cfg or config.EMPTY).specs_dir,
            link=not args.no_link,
            prototype=args.prototype,
            living=args.living,
            profile=cfg.profile if cfg else "",
            full=args.full,
        ),
    )
    print(path.as_posix())
    if spec is not None and args.no_link:
        entry = {"type": args.type, "path": path.as_posix()} | ({"frozen": False} if args.living or args.type in workitems.LIVING_DOCS else {})
        print(f"not linked: {spec.as_posix()} is left to its writer, who adds this item to its `docs` list:\n{strict_yaml.dump({'docs': [entry]}).rstrip()}")
        return 0
    if spec is None:
        print(f"next: {config.item_type_rows()[args.type]['next']}")
        return 0
    if args.type == "threat-model":
        print(
            f"{'the component already has its threat model: linked again' if existing else 'linked'} from {spec.as_posix()} as a living `docs` "
            "entry (frozen: false). Put this Spec's delta (the threat ids it adds, changes, or retires) in its Design, and update the model "
            "in the same change: Spec approval covers the delta, and Merge approval reviews the model"
        )
    elif args.living:
        print(f"{'linked again' if existing else 'linked'} from {spec.as_posix()} as a living `docs` entry (frozen: false): keep the component's plan current")
    elif args.type in workitems.LIVING_DOCS:
        print(f"linked from {spec.as_posix()} as a living `docs` entry (frozen: false): humans fill it after Spec approval")
    else:
        print(f"linked from {spec.as_posix()} as a frozen `docs` entry: Spec approval covers it with the Spec")
    print(f"next: replace the TODOs, then {_validate_step(spec)}")
    return 0


def _new_repo_doc(args, cfg: config.Config | None) -> int:
    """`aidd new design-system`, `architecture`, `data-map`, `vendors`, `glossary`, `vulnerability-policy`, or `agents`: the
    repository's one of each."""
    if args.id or args.spec or args.doc_folder or args.no_link:
        raise ValueError(f"a {args.type} belongs to the repository, not a Spec: run `aidd new {args.type}` with no id, --spec, or --doc-folder")
    paths = workitems.new_repo_doc(Path("."), doc_type=args.type, title=args.title or "", docs_dir=(cfg or config.EMPTY).docs_dir)
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
    if not args.id or args.spec or args.doc_folder or args.no_link:
        raise ValueError("a contract belongs to a proposal: `aidd new contract <proposal id>`, with no --spec or --doc-folder")
    path = workitems.new_contract(Path("."), args.id, proposals_dir=(cfg or config.EMPTY).proposals_dir)
    print(path.as_posix())
    what = "the change order: the delta and the affected Acceptance ids" if path.parent.name == workitems.CHANGE_ORDERS else "the statement-of-work base"
    print(f"next: draft {what}; every price, legal term, and the client's decision stay with humans")
    return 0


def _new_exploration(args, cfg) -> int:
    """`aidd new exploration <folder> --title "<the question>"`: the exploration's front matter and sections. A folder
    that is not an exploration's home is refused before anything is written, naming the folder it belongs in."""

    specs_dir = (cfg or config.EMPTY).specs_dir
    # The Specs folder is the config's text, so it joins a printed command only as a plain name; the title is quoted whole.
    plain = command_names.quoted(specs_dir)
    if not args.id or not args.title:
        shown = (
            f'`aidd new exploration {plain}/SPEC-12/explore/<slug> --title "..."`'
            if plain
            else f'`aidd new exploration <folder> --title "..."` ({command_names.NO_COMMAND})'
        )
        raise ValueError(f"an exploration needs its folder and its question: {shown}")
    if home := workitems.exploration_misplaced(Path(args.id), specs_dir):
        # `home` holds parts of the folder the person typed, with `<ID>` or `<slug>` as a whole part where it named none: a
        # command only when every other part is a plain name
        parts = [  # "" for a part that is no plain name
            "<ID>" if part == "<ID>" else "<slug>" if part == "<slug>" else command_names.quoted(part) or "" for part in home.split("/")
        ]
        shown = (
            f"`aidd new exploration {'/'.join(parts)} --title {shlex.quote(args.title)}`"
            if all(parts)
            else f"{documents.one_line(home)} ({command_names.NO_COMMAND})"
        )
        raise ValueError(f"{workitems.EXPLORATION_HOME}: {shown}")
    path = workitems.new_exploration(Path(args.id), question=args.title, role=args.role or "product-designer", timebox=args.timebox)
    print(path.as_posix())
    print(
        f"next: draw two or three divergent directions (or, for a decision card, write the options with no visuals), then `aidd explore {command_names.quoted(args.id) or '<folder>'}`"
    )
    return 0


def _new_product_prototype(args, cfg: config.Config | None) -> int:
    """`aidd new product-prototype`: the product designer's whole-product prototype, started once in `<docs>/design/app/`."""
    if args.id or args.spec or args.doc_folder or args.no_link:
        raise ValueError("the product prototype belongs to the repository, not a Spec: run `aidd new product-prototype` with no id, --spec, or --doc-folder")
    if args.force:
        raise ValueError("--force never overwrites the product prototype, a person's work: move docs/design/app/ aside first to start over")
    docs = (cfg or config.EMPTY).docs_dir
    product = args.title or Path.cwd().name
    for p in resources.team_tool("prototype").new_product_prototype(Path("."), docs_dir=docs, product=product):
        print(p.as_posix())
    print("next: list the flows and the navigation in sitemap.json, draw one file per flow in flows/, then `aidd prototype` to open it")
    print("each Spec with a design then updates its flow here in the same change, and `aidd validate` warns when it does not")
    return 0


def cmd_prototype(args) -> int:
    """`aidd prototype`: aidd-team's prototype tool on the product prototype, or on one prototype file, the file never
    changed. `--check` only checks; `--components` prints the component contract; `--screens` prints the screens; `--shots`
    prints the fidelity pass's views; `--stories` checks Storybook's index.json against the contract."""
    if sum(map(bool, (args.check, args.components, args.screens, args.shots, args.stories))) > 1:
        raise ValueError("--check checks the design; --components, --screens, --shots, and --stories read it: give one of them")
    reading = arguments.prototype_reading(args)  # refuses an option that sizes --shots without it
    if args.serve and args.check:
        raise ValueError("--serve serves the page and --check only checks it: run `aidd prototype --check` first, then --serve")
    if (args.lan or args.port != 8765) and not args.serve:
        raise ValueError("--lan and --port go with --serve: add --serve to serve the page")
    arguments.enter_repo(args, "file", "new_design", file_attrs=("stories",), outside_ok=True)
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
        print(f"next: sketch the direction in it, then `aidd prototype {command_names.quoted(args.new_design) or '<file>'}` to see it")
        return 0
    cfg = arguments.config_or_none()
    docs = (cfg or config.EMPTY).docs_dir
    if not args.file and not tool.product_prototype_dir(Path("."), docs).is_dir():
        raise ValueError(
            f"no product prototype in {docs}/design/app/: name a design file, such as `aidd prototype --check <file>`, or start one with `aidd new product-prototype`"
        )
    if args.serve:
        return int(tool.serve_design(Path("."), args.file, docs, lan=args.lan, port=args.port))
    if reading:
        return tool.main(["--docs", docs, *reading, *([args.file] if args.file else [])])
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
        print(
            f"wrote no page: fix the problems above in {where}, then run `aidd prototype{' ' + (command_names.quoted(args.file) or '<file>') if args.file else ''}` again"
        )
    if out and problems:
        print(tool.problems_line(len(problems), where))
    if args.check:
        print("the prototype is consistent" if not problems else tool.problems_line(len(problems), where))
    return 1 if problems else 0


def cmd_new(args) -> int:
    arguments.enter_repo(args, "paths", *(("id",) if args.type == "exploration" else ()), outside_ok=True)
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
            folder = ((cfg or config.EMPTY).proposals_dir) if args.type == "proposal" else ((cfg or config.EMPTY).specs_dir)
            args.id = workitems.next_id(Path("."), workitems.ID_PREFIXES[args.type], folder)
    if not args.id:
        raise ValueError(f"an id is required for a {args.type}: `aidd new {args.type} <id>`")
    if args.type in workitems.DOC_TEMPLATES:
        return _new_doc(args, cfg)
    if not args.title and not (args.type == "spec" and workitems.find_slice(Path("."), (cfg or config.EMPTY).specs_dir, args.id)):
        took = ""
        if typed := getattr(getattr(args, "planned", None), "typed", None):  # --paths takes every word after it, the title too
            took = f'. --paths took {", ".join(repr(p) for p in typed)}: put the title first, as `aidd new {args.type} "<title>" --paths {command_names.quoted(typed[0]) or "<path>"}`'
        raise ValueError(f"--title is required for a {args.type}, unless it is a slice an Intent lists{took}")
    if args.doc_folder:
        raise ValueError(
            f"--doc-folder names a linked document's folder: use it with {', '.join(sorted(set(workitems.DOC_TEMPLATES) - workitems.UNLINKED_DOCS))}"
        )
    if args.no_link and not (args.type == "runbook" and args.spec):
        raise ValueError("--no-link is for a document a Spec links: a linked doc, or a runbook with --spec")
    linked = workitems.find_spec_by_id(Path("."), (cfg or config.EMPTY).specs_dir, args.spec) if args.type == "runbook" and args.spec else None
    if args.type != "spec" and (args.paths or args.dimension or args.irreversible):
        raise ValueError("--paths, --dimension, and --irreversible compute a Spec's route: use them with `aidd new spec`")
    if args.route == "emergency" and args.paths:
        raise ValueError("an emergency backfill Spec takes its route from the declared emergency, not from --paths")
    arguments.check_new_team_flags(args.type, args.owner_team, args.delivery_team, cfg)
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
            profile=cfg.profile if cfg else "",
            ctype=args.change_type,
            delivery_team=args.delivery_team,
            parent=args.parent,
            specs_dir=(cfg or config.EMPTY).specs_dir,
            audience=args.audience,
            addressee=args.addressee,
            proposals_dir=(cfg or config.EMPTY).proposals_dir,
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
        here = Path(".").resolve()
        workitems.link_doc(linked.resolve(), "runbook", path.resolve().relative_to(here).as_posix(), root=here, frozen=False)
        print(f"linked from {linked.as_posix()} as a living `docs` entry (frozen: false)")
    todo = config.item_type_rows()[args.type].get("next", "fill Context, Acceptance, tasks, and tests, write the test files")
    if args.type == "spec" and workitems.spec_template(route, args.full, cfg.profile if cfg else "") == "spec-short":
        to_fill = "" if args.paths else "the Task's scope, "  # --paths already wrote it
        todo = f"replace the TODOs (Request, Context, Acceptance, Design, Rollback, {to_fill}the tests), write the test files"
    print(f"next: {todo}, then {_validate_step(path)}")
    if args.type == "spec":
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))  # aidd's own: the Spec this command just wrote
        asks = workitems.required_docs(data, cfg)
        if asks:
            shown = "; ".join(f"{k}{' --living' if living else ''} ({'expected' if level == 'warn' else 'suggested'}: {why})" for k, level, why, living in asks)
            print(f"docs: {shown}; write each with `aidd new <type> <topic> --spec {command_names.quoted(args.id) or '<ID>'}`")
    return 0


def cmd_agree(args) -> int:
    """`aidd agree <ID>...`: the person's agreement to each Intent, set by aidd and committed as them, in one commit. It
    runs only at a terminal. Like the ask rules' patterns, that is a net: it stops an agent's plain shell call, not one that
    makes a pseudo-terminal (`pty.spawn`, `script`). Branch protection and the person's own review are what hold."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError(
            "Run this in your own terminal: your agreement is yours to record. Paste the same command into a terminal of yours, "
            "in the repository, or say yes in the chat and the agent asks to commit it"
        )
    arguments.enter_repo(args)
    cfg = arguments.config_or_none()
    root = Path(".").resolve()
    sha, who, paths = workitems.record_agreement(root, workitems.open_work(root, cfg), args.ids)
    print(f"Recorded your agreement to {', '.join(dict.fromkeys(args.ids))} as {who}, in commit {sha[:12]}: {', '.join(paths)}")
    return 0


def cmd_explore(args) -> int:
    """An exploration's comparison page (`aidd new exploration` writes the exploration)."""
    from aidd import views

    arguments.enter_repo(args, "folder", file_attrs=("out",), outside_ok=True)
    folder = Path(args.folder)
    item = folder.parent.parent.name if folder.parent.name == "explore" else ""
    name = f"{item}-{folder.name}" if workitems.WORK_ID.fullmatch(item) else folder.name
    target = Path(args.out) if args.out else views.default_path("explore", name)
    views.write(target, views.comparison_page(folder, written=dt.datetime.now(), project=Path.cwd().name))
    print(f"wrote {arguments.repo_relative(target)}")
    return 0
