"""`aidd status`: the open work and each item's next step; one item with what stands behind it; a path's trace; or the product scope."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from aidd import config, risk, testing, workitems
from aidd.cli import arguments
from aidd.cli.commands import risk_answers
from aidd.kernel import git_reads
from aidd.kernel.text import did_you_mean


@git_reads.shared_reads()
def cmd_status(args) -> int:
    """`aidd status`: the open work and each item's next step; with an id, that item alone and what stands behind it; with a
    path, what stands behind the path."""
    product = args.id == workitems.PRODUCT_TARGET  # the word, never the folder of that name: `product/` is the path
    arguments.enter_repo(args, *(() if product else ("id",)))  # a path typed in a subfolder is read from there, never from the repository's top
    cfg = arguments.config_or_none_quiet(args)
    if product:
        return _status_of_product(args, cfg)
    if args.id and (not workitems.WORK_ID.fullmatch(args.id) or Path(args.id).exists()):
        if not Path(args.id).exists() and (hint := did_you_mean(args.id, [workitems.PRODUCT_TARGET])):
            print(f"note: no path {args.id} here. {hint}", file=sys.stderr)
        if args.who or args.all_branches or args.html or args.development_team:
            raise ValueError("`aidd status <path>` takes only --commits and --json; name a work item id for the rest")
        return _status_of_path(args, cfg)
    if args.commits is not None and not args.id:
        print("note: --commits reads the commits behind a path, a Spec, or an Intent, so it does nothing here", file=sys.stderr)
    answer: dict
    if cfg is None and not Path(config.CONFIG_PATH).is_file():
        if args.id:
            # No config, so no open work to pick from; what stands behind the item still reads from its file.
            if not args.json:
                print(f"note: {workitems.STEP_MEANINGS['setup.missing']}: {workitems.step_words('setup.missing', '')}", file=sys.stderr)
            return _status_of_path(args, cfg)
        answer = {
            "items": [],
            "due": [],
            "next": {
                "code": "setup.missing",
                "who": "person",
                "what": workitems.STEP_MEANINGS["setup.missing"],
                "words": workitems.step_words("setup.missing", ""),
            },
        }
    else:
        shown = workitems.Shown(keep=_development_team_keep(cfg, args.development_team), teams=_team_rule(cfg))
        if args.all_branches:
            answer = workitems.all_branches_work(Path("."), cfg, include_done=bool(args.id), shown=shown)
        else:
            answer = workitems.open_work(Path("."), cfg, include_done=bool(args.id), shown=shown)
            workitems.add_branch_facts(Path("."), answer)
        _add_last_run(answer, here=f"worktree:{Path('.').resolve()}" if args.all_branches else None)
        _add_running_roles(answer)
    if args.id:
        _keep_one_item(args, answer, cfg)
    if args.json:
        found = [*([args.config_finding] if getattr(args, "config_finding", None) else []), *workitems.status_findings(answer)]
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer | {"findings": found}, indent=2))
        return 0
    if args.html:
        return _write_page(args, answer, cfg)
    print(workitems.status_text(answer, who=args.who, pick=not args.id) + _digest(cfg, args), end="")
    print(workitems.running_roles_text(answer.get("running_roles", [])), end="")
    if args.id:
        print("".join(workitems.history_text(i["history"]) for i in answer["items"]), end="")
        if "trace" in answer:
            print("behind it:\n" + workitems.trace_text(answer["trace"]), end="")
    return 0


def _digest(cfg, args) -> str:
    """Under a delegation, what was decided for the person, after the open work; "" otherwise, or for one item."""
    if cfg is None or not cfg.get("delegation") or args.id:
        return ""
    from aidd import delegation

    block = cfg.get("delegation") or {}
    note = delegation.not_yet_on_default_note(".", block)
    return (note + "\n" if note else "") + delegation.digest_text(".", str(block.get("default_branch") or "HEAD"))


def _keep_one_item(args, answer: dict, cfg: config.Config | None) -> None:
    """`aidd status <ID>`: that item alone, with its history and, for a Spec or an Intent this worktree holds, what stands
    behind it. An item only another branch holds has no trace here, since the trace reads this worktree's files."""
    if not any(i["id"] == args.id for i in answer["items"]) and (holder := workitems.holder_of(answer["items"], args.id)):
        print(f"note: {args.id} is a slice of {holder}, so this shows {holder}", file=sys.stderr)
        args.id = holder
    answer["items"] = [i for i in answer["items"] if i["id"] == args.id]
    dups = [d for d in answer.get("duplicate_ids", []) if d["id"] == args.id]
    if dups:
        answer["duplicate_ids"] = dups
    else:
        answer.pop("duplicate_ids", None)
    if not answer["items"] and not dups:
        raise ValueError(f"no Spec, Intent, or proposal has the id {args.id}; run `aidd status` to see open work, or `aidd new` to create one")
    answer["due"] = []
    if owed := [e for e in answer.pop("explorations", []) if e.get("item") == args.id]:
        answer["explorations"] = owed
    answer.pop("next", None)
    answer.pop("root_blocker", None)
    here = f"worktree:{Path('.').resolve()}"
    held = False
    for item in answer["items"]:
        # A version another branch holds links its own docs, which this worktree's file may not say.
        local = not item.get("places") or here in item["places"]
        held = held or local
        item["history"] = workitems.work_item_history(Path("."), item["id"], item["path"], docs=local)
    if answer["items"] and answer["items"][0]["type"] in workitems.WORK_TYPES and held:
        answer["trace"] = _trace(args, cfg)
    elif args.commits is not None:
        print(f"note: --commits reads the commits behind a Spec or an Intent this worktree holds, so it does nothing for {args.id}", file=sys.stderr)


def _trace(args, cfg) -> dict:
    """What stands behind `args.id`, a path or a work item, from git and aidd's files; the route is `aidd risk --paths` over its paths."""
    answer = workitems.trace(
        Path("."),
        cfg,
        args.id,
        commits=workitems.DEFAULT_COMMITS if args.commits is None else args.commits,
        # Every reading of the path a person typed routes, so a subfolder never reads a path safer than git prints it.
        route=lambda paths: (
            {"schema_version": arguments.JSON_SCHEMA_VERSION}
            | risk_answers.cap_area_paths(
                risk.advice(cfg, list(dict.fromkeys([*paths, *getattr(getattr(args, "planned", None), "every", [])])), tracked=arguments.tracked_files()),
                (cfg or config.EMPTY).max_paths_shown,
            )
        ),
    )
    return {"schema_version": arguments.JSON_SCHEMA_VERSION} | answer


def _status_of_product(args, cfg: config.Config | None) -> int:
    """`aidd status product`: the product scope's files, items, and Intents, and what no Intent carries (schemas/product-status.schema.json)."""
    if args.html:
        raise ValueError("`aidd status product` has no page yet: read it here, or run `aidd status product --json` for a script")
    if args.who or args.all_branches or args.development_team or args.commits is not None:
        raise ValueError("`aidd status product` takes only --json: it shows the whole product scope of this worktree")
    answer = workitems.product_status(Path("."), cfg)
    if args.json:
        answer["findings"] = [*([args.config_finding] if getattr(args, "config_finding", None) else []), *answer["findings"]]
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(workitems.product_status_text(answer), end="")
    return 0


def _status_of_path(args, cfg: config.Config | None) -> int:
    """`aidd status <path>`: what stands behind a repository path (schemas/trace.schema.json)."""
    answer = _trace(args, cfg)
    if args.json:
        print(json.dumps(answer, indent=2))
    else:
        print(workitems.trace_text(answer), end="")
    return 0


def _write_page(args, answer: dict, cfg: config.Config | None) -> int:
    """`aidd status --html`: the open work, or one item, as one page in .aidd/views/."""
    from aidd import views

    raw = {} if args.all_branches else workitems.raw_emergencies(Path("."), cfg)
    for item in answer["items"]:  # the page keeps each good field of an emergency that `--json` leaves out whole
        if item.get("path") in raw:
            item["emergency"] = raw[item["path"]]
    if not args.id:  # the page's history is derived: each item's newest 5, in one pass, never a key `--json` carries
        newest = workitems.work_items_history(Path("."), [i["id"] for i in answer["items"]])
        for item in answer["items"]:
            item["history"] = newest.get(item["id"], [])
    page = views.status_page(
        answer,
        title=f"The open work in {Path.cwd().name}",
        written=dt.datetime.now(),
        project=Path.cwd().name,
        retry_limit=(cfg or config.EMPTY).max_task_retries,
    )
    target = views.write(views.default_path("status", _page_name(args)), page)
    print(f"wrote {arguments.repo_relative(target)}: open it in a browser; it only reads, and a decision stays in the chat")
    return 0


def _page_name(args) -> str:
    """The name of the page a run writes (`status-<name>.html`): the item's id for one item, else `work` with the team and
    `all-branches` a run was filtered by, so a run with a filter never overwrites another page."""
    if args.id:
        return str(args.id)
    return "-".join(["work", *([str(args.development_team).lower()] if args.development_team else []), *(["all-branches"] if args.all_branches else [])])


def _add_last_run(answer: dict, here: str | None) -> None:
    """The summary of this worktree's last `aidd test` run, on each Spec the run tested. With `--all-branches` (`here` names
    this worktree), only on the version of that Spec this worktree holds."""
    found, note = testing.last_run_summary()
    if note:
        print(f"note: {note}", file=sys.stderr)
    if found is None:
        return
    paths, summary = found
    for item in answer["items"]:
        if item["path"] in paths and (here is None or here in item.get("places", [])):
            item["last_test_run"] = summary


def _add_running_roles(answer: dict) -> None:
    """The roles still running, from their status files in this checkout (`workitems.running_roles`), when there are any."""
    if roles := workitems.running_roles(Path(".")):
        answer["running_roles"] = roles


def _team_rule(cfg: config.Config | None):
    """The rule that names the development teams whose work an item is, in the config's order, or None when the config names
    none: an Intent or a Spec whose `development_team` names the team, a Spec under such an Intent, or a Spec whose Task scope
    touches its areas, as `aidd risk --paths` reads the scope. `--development-team` and the answer's `development_teams` share it."""
    names = workitems.team_names(cfg)
    if not names:
        return None
    teams, rules = {n: config.development_team(cfg, n) for n in names}, risk.rule_set(cfg)

    def scope_areas(scope: list[str]) -> set[str]:
        return {a for p in risk.planned_paths(scope) for a in risk.areas_of(rules, p)}

    return lambda data, parent: [n for n, team in teams.items() if workitems.in_development_team(data, team, scope_areas, name=n, parent=parent)]


def _development_team_keep(cfg: config.Config | None, name: str | None):
    """With `--development-team`, what keeps that team's work items, by the rule `_team_rule` gives."""
    if not name:
        return None
    config.development_team(cfg, name)  # a team the config does not name is an error that names the teams
    rule = _team_rule(cfg)
    return lambda data, parent: name in rule(data, parent)
