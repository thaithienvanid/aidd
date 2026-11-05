"""`aidd status`: the open work and each item's next step; one item with what stands behind it; or a path's trace."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from aidd import config, risk, testing, workitems
from aidd.cli import arguments


def cmd_status(args) -> int:
    """`aidd status`: the open work and each item's next step; with an id, that item alone and what stands behind it; with a
    path, what stands behind the path."""
    arguments.enter_repo(args, "id")  # a path typed in a subfolder is read from there, never from the repository's top
    cfg = arguments.config_or_none_quiet()
    if args.id and (not workitems.WORK_ID.fullmatch(args.id) or Path(args.id).exists()):
        if args.mine or args.all_branches or args.html or args.delivery_team:
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
        shown = workitems.Shown(keep=_delivery_team_keep(cfg, args.delivery_team), teams=_team_rule(cfg))
        if args.all_branches:
            answer = workitems.all_branches_work(Path("."), cfg, include_done=bool(args.id), shown=shown)
        else:
            answer = workitems.open_work(Path("."), cfg, include_done=bool(args.id), shown=shown)
            workitems.add_branch_facts(Path("."), answer)
        _add_last_run(answer, cfg, here=f"worktree:{Path('.').resolve()}" if args.all_branches else None)
    if args.id:
        _keep_one_item(args, answer, cfg)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
        return 0
    if args.html:
        return _write_page(args, answer)
    print(workitems.status_text(answer, mine="person" if args.mine else None, pick=not args.id) + _digest(cfg, args), end="")
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

    return delegation.digest_text(".", str((cfg.get("delegation") or {}).get("default_branch") or "HEAD"))


def _keep_one_item(args, answer: dict, cfg: config.Config | None) -> None:
    """`aidd status <ID>`: that item alone, with its history and, for a Spec or an Intent this worktree holds, what stands
    behind it. An item only another branch holds has no trace here, since the trace reads this worktree's files."""
    if not any(i["id"] == args.id for i in answer["items"]) and (holder := workitems.holder_of(answer["items"], args.id)):
        print(f"note: {args.id} is {holder[1]} of {holder[0]}, so this shows {holder[0]}", file=sys.stderr)
        args.id = holder[0]
    answer["items"] = [i for i in answer["items"] if i["id"] == args.id]
    if not answer["items"]:
        raise ValueError(f"no Spec, Intent, or proposal has the id {args.id}")
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
    if answer["items"][0]["type"] in ("spec", "intent") and held:
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
            | risk.advice(cfg, list(dict.fromkeys([*paths, *getattr(getattr(args, "planned", None), "every", [])])), tracked=arguments.tracked_files())
        ),
    )
    return {"schema_version": arguments.JSON_SCHEMA_VERSION} | answer


def _status_of_path(args, cfg: config.Config | None) -> int:
    """`aidd status <path>`: what stands behind a repository path (schemas/trace.schema.json)."""
    answer = _trace(args, cfg)
    if args.json:
        print(json.dumps(answer, indent=2))
    else:
        print(workitems.trace_text(answer), end="")
    return 0


def _write_page(args, answer: dict) -> int:
    """`aidd status --html`: the open work, or one item, as one page in .aidd/views/."""
    from aidd import views

    raw = {} if args.all_branches else workitems.raw_emergencies(Path("."), arguments.config_or_none_quiet())
    for item in answer["items"]:  # the page keeps each good field of an emergency that `--json` leaves out whole
        if item.get("path") in raw:
            item["emergency"] = raw[item["path"]]
    if not args.id:  # the page's history is derived: each item's newest 5, in one pass, never a key `--json` carries
        newest = workitems.work_items_history(Path("."), [i["id"] for i in answer["items"]])
        for item in answer["items"]:
            item["history"] = newest.get(item["id"], [])
    page = views.status_page(answer, title=f"The open work in {Path.cwd().name}", written=dt.datetime.now(), project=Path.cwd().name)
    target = views.write(views.default_path("status", _page_name(args)), page)
    print(f"wrote {arguments.repo_relative(target)}: open it in a browser; it only reads, and a decision stays in the chat")
    return 0


def _page_name(args) -> str:
    """The name of the page a run writes (`status-<name>.html`): the item's id for one item, else `work` with the team and
    `all-branches` a run was filtered by, so a run with a filter never overwrites another page."""
    if args.id:
        return str(args.id)
    return "-".join(["work", *([str(args.delivery_team).lower()] if args.delivery_team else []), *(["all-branches"] if args.all_branches else [])])


def _add_last_run(answer: dict, cfg: config.Config | None, here: str | None) -> None:
    """The summary of this worktree's last `aidd test` run, on the one Spec the run tested. With `--all-branches` (`here` names
    this worktree), only on the version of that Spec this worktree holds."""
    found, note = testing.last_run_summary(cfg)
    if note:
        print(f"note: {note}", file=sys.stderr)
    if found is None:
        return
    path, summary = found
    for item in answer["items"]:
        if item["path"] == path and (here is None or here in item.get("places", [])):
            item["evidence"] = summary


def _team_rule(cfg: config.Config | None):
    """The rule that names the delivery teams whose work an item is, in the config's order, or None when the config names
    none: an Intent of the team, a Spec under one, a Spec whose `owner_team` names the team, or a Spec whose Task scope
    touches its areas, as `aidd risk --paths` reads the scope. `--delivery-team` and the answer's `delivery_teams` share it."""
    names = workitems.team_names(cfg)
    if not names:
        return None
    teams, rules = {n: config.delivery_team(cfg, n) for n in names}, risk.rule_set(cfg)

    def scope_areas(scope: list[str]) -> set[str]:
        return {a for p in risk.planned_paths(scope) for a in risk.areas_of(rules, p)}

    return lambda data: [n for n, team in teams.items() if workitems.in_delivery_team(data, team, scope_areas, name=n)]


def _delivery_team_keep(cfg: config.Config | None, name: str | None):
    """With `--delivery-team`, what keeps that team's work items, by the rule `_team_rule` gives."""
    if not name:
        return None
    config.delivery_team(cfg, name)  # a team the config does not name is an error that names the teams
    rule = _team_rule(cfg)
    return lambda data: name in rule(data)
