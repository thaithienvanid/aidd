"""`aidd validate`: the config and every work item checked against its schema and past it, with the warnings a person
reads.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from aidd import config
from aidd.kernel import documents, processes, regular_files
from aidd.kernel.documents import markdown_section
from aidd.workitems import (
    authoring,
    backlog,
    commit_text,
    criteria,
    delegated_yes,
    doc_checks,
    due_dates,
    guide_checks,
    handoff_notes,
    intent_checks,
    intent_paths,
    intents,
    interfaces,
    living_docs,
    living_work,
    orca_payload,
    placeholders,
    product_checks,
    product_scope,
    proposal_checks,
    releases,
    repo_reads,
    saved_requests,
    spec_file,
    spec_warnings,
    status,
    triage,
    work_list,
)
from aidd.workitems import objects as workitems_objects

MAX_VALIDATE_FILES = 1000
MAX_VALIDATE_DEPTH = 10


def _walk_bounded(root: Path, max_files: int = MAX_VALIDATE_FILES, max_depth: int = MAX_VALIDATE_DEPTH) -> tuple[list[Path], bool]:
    found: list[Path] = []
    stopped = False
    root_parts_len = len(root.resolve().parts)
    for dirpath, dirnames, filenames in os.walk(root):
        dpath = Path(dirpath).resolve()
        depth = len(dpath.parts) - root_parts_len
        if depth >= max_depth:
            dirnames.clear()
            stopped = True
            continue
        dirnames.sort()
        for fn in sorted(filenames):
            if len(found) >= max_files:
                return found, True
            found.append(Path(dirpath) / fn)
    return found, stopped


# A finding's prefix says its level; one with neither prefix is an error. A warning is worth fixing, and a note says an
# expected state, such as a planned Spec's placeholders. Neither fails `aidd validate`.
WARNING, NOTE = "warning: ", "note: "


def is_error(finding: str) -> bool:
    """Whether a finding of `validate_file` is an error: neither a warning nor a note."""
    return not finding.startswith((WARNING, NOTE))


# The one error `aidd validate` gives that names no file to fix: the repository has not adopted aidd.
NO_CONFIG = f"no {config.CONFIG_PATH}: run `aidd init` to adopt this repository"


def validate_next_step(errors: list[str]) -> str | None:
    """What `aidd validate` says after its errors, or None with none. Every error but `NO_CONFIG` names the file it is
    in, so the summary names a file step only when one of those is there, and sends you to `aidd init` when the config
    is missing: never round to `aidd validate` with nothing to fix."""
    if not errors:
        return None
    steps = ["run `aidd init` to adopt this repository"] if NO_CONFIG in errors else []
    if any(e != NO_CONFIG for e in errors):
        steps.append("fix each file named above")
    return ", ".join(steps) + ", then run `aidd validate` again"


def cross_file_skipped_note(paths: list[str]) -> str | None:
    """One note when `aidd validate` checked named files and skipped cross-file checks that apply to one of them."""
    if any(workitems_objects.is_object(Path(p)) for p in paths):
        return f"{NOTE}cross-file checks were skipped for single-file validation; run `aidd validate` to check across files"
    return None


def validate_file(path: Path, label: str | None = None) -> list[str]:
    """Each finding names the file by `label`, else by the path in forward slashes, on every OS."""
    shown = label or path.as_posix()
    raw = str(path)
    found = _validate_file(path)
    return [e.replace(raw, shown) for e in found] if raw != shown else found


def _validate_file(path: Path) -> list[str]:
    if path.is_dir() and not path.is_symlink():
        files, stopped = _walk_bounded(path)
        errs = [
            e
            for f in files
            if (
                (f.name == "config.yaml" and f.parent.name == ".aidd")
                or (f.suffix == ".md" and (saved_requests.saved_request_of(f) is not None or workitems_objects.is_object(f)))
            )
            and f.name.lower() != "readme.md"
            and "assets" not in f.parts
            for e in validate_file(f)
        ]
        if stopped:
            errs.append(f"warning: {path}: directory walk reached bound and stopped early")
        return errs
    if (request := saved_requests.saved_request_of(path)) is not None:
        # A saved request is a person's words, never a work item: only the credential check reads it.
        return saved_requests.request_findings(*request)
    text, problem = _named_text(path)
    if text is None:
        return [f"{path}: {problem}"]
    if path.name.endswith(".orca.json"):
        return orca_payload.payload_problems(str(path), text)
    if path.suffix == ".json":
        return [f"{path}: aidd validate reads JSON only as an Orca payload, in a file named <name>.orca.json"]
    if path.suffix in (".yaml", ".yml"):
        try:
            cfg = config.load_text(text, read=lambda p: workitems_objects.read_document(path.parent.parent, p)[0], where=str(path))
        except (config.ConfigError, documents.DocumentError, RuntimeError) as exc:
            return str(exc).splitlines()
        out = [f"warning: {w}" for w in cfg.warnings]
        errors, warnings = config.project_findings(cfg)
        out += [f"{path}: {e}" for e in errors] + [f"warning: {path}: {w}" for w in warnings]
        out += [f"{path}: {e}" for e in command_problems(cfg.get("tests", default=[]))]
        if path.parent.name == ".aidd":
            from aidd.kernel.repo_paths import inside

            out += [
                f"warning: {path}: `docs.exemplars` names {rel}, which is not a file in the repository; name a Spec that exists, or remove it"
                for rel in cfg.get("docs", "exemplars", default=[]) or []
                if inside(path.parent.parent, rel) is None
            ]
        return out
    try:
        data, _, errs = spec_file.load_object(text, str(path))
    except documents.DocumentError as exc:
        return [str(exc)]
    if data.get("type") == "exploration":
        return _exploration_checks(path, text)
    try:
        return _object_checks(path, text, data, errs)
    except (AttributeError, TypeError, KeyError):
        # The checks read the fields the schema describes. When the schema already rejected one (a string `risk`
        # where a table belongs), they stop there: the schema errors, and whatever they found first, are the report.
        if any(not e.startswith("warning: ") for e in errs):
            return errs
        raise


def _named_text(path: Path) -> tuple[str | None, str]:
    """The UTF-8 text of the file `aidd validate` was given, or None and why not. It reads a regular file only, never
    through a link or from a device, which a read could hang on, and at most a document's cap. A missing file raises,
    as any other command's missing file does."""
    root = regular_files.working_root(path)
    rel = regular_files.relative(root, path)
    raw, why = regular_files.regular_file_bytes(root, rel, documents.MAX_DOCUMENT_BYTES)  # inside `root`, through no link out
    if raw is None and why != regular_files.NOT_REGULAR:
        raise OSError(f"{path}: {why}")
    if raw is None:
        linked = path.is_symlink() or regular_files.link_on_the_way(root, rel)
        return None, workitems_objects.REFUSED[regular_files.LINK if linked else regular_files.NOT_REGULAR]
    if len(raw) > documents.MAX_DOCUMENT_BYTES:
        return None, workitems_objects.REFUSED[regular_files.TOO_LARGE]
    try:
        return raw.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "not UTF-8 text"


def _exploration_checks(path: Path, text: str) -> list[str]:
    """An exploration is no work item, so it gets the checks `aidd validate` runs on it for the repository: its schema
    and its spike, as warnings, because `aidd explore` refuses what the schema rejects."""
    from aidd.workitems import explorations

    data, found = explorations.front_matter_warnings(str(path), path)
    found += explorations.spike_hints(str(path), data, dt.date.today())
    found += [f"{path}: still contains TODO placeholders; replace each TODO with the real text"] if status.PLACEHOLDER in text else []
    return [f"warning: {f}" for f in found]


def command_problems(commands: object) -> list[str]:
    """Each test command that cannot start, because its program is a shell's `NAME=value`, by its name."""
    found = []
    for c in commands if isinstance(commands, list) else []:
        argv = c.get("command") if isinstance(c, dict) else None
        if isinstance(argv, list) and (why := processes.assignment_problem([str(a) for a in argv])):
            found.append(f"the test command `{documents.one_line(c.get('name'), 60)}` cannot start: {why}")
    return found


def _glossary_warnings(path: Path, text: str) -> list[str]:
    """The Spec's lines that use a word the repository glossary (`aidd new glossary`, under the docs folder) says to
    avoid. No glossary, no warning; one that cannot be read says so."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    cfg = repo_reads.config_at(root)
    rel = authoring.REPO_DOCS["glossary"][0][0].replace("{docs}", (cfg or config.EMPTY).docs_dir)
    if not os.path.lexists(root / rel):
        return []
    glossary, why = workitems_objects.read_document(root, rel)
    if glossary is None:
        return [f"warning: {path}: the glossary {rel} is {why.removeprefix('a path ')}, so its Avoid words were not checked"]
    return spec_warnings.glossary_warnings(path, text, rel, glossary)


def _object_checks(path: Path, text: str, data: dict, errs: list[str]) -> list[str]:
    """The checks past the schema, appending to `errs` (the schema's findings) as they go."""
    # A placeholder in what the runner executes or a Task scopes is an error; elsewhere it is a reminder.
    tests = data.get("tests") or {}
    executable = [a for c in tests.get("commands", []) for a in c.get("command", [])]
    executable += [s for task in data.get("tasks", []) for s in task.get("scope", [])]
    executable += list(tests.get("files", []))
    errs += [f"{path}: {e}" for e in command_problems(tests.get("commands", []))]
    if any(status.PLACEHOLDER in str(x) for x in executable):
        if data.get("route") == "emergency":
            # A backfill Spec committed with the repair, still to be written; `aidd validate` holds its backfill_due.
            errs.append(f"warning: {path}: emergency backfill Spec still holds TODO placeholders; finish it by backfill_due")
        elif data.get("type") == "spec" and status.is_planned(data, status.spec_status(data)):
            # A planned Spec is expected to hold its placeholders: Specify fills them, and Spec approval waits for that,
            # because a Spec that asks for approval is `ready`, never planned, so this stays an error there.
            errs.append(f"{NOTE}{path}: planned, not specified yet: Specify fills in its tests and its Tasks' scope before Spec approval")
        else:
            errs.append(f"{path}: test commands, tests.files, or a Task's scope still hold TODO placeholders")
    elif status.PLACEHOLDER in text:
        errs.append(f"warning: {path}: still contains TODO placeholders")
    if data.get("type") == "spec":
        errs += route_findings(path, data)
    if data.get("type") == "spec" and data.get("route") in config.SPEC_FIRST_ROUTES:
        if data.get("route") == "major":
            # Only a major Spec carries the full template's sections (a normal one may be the short Spec). A diagram is one
            # view chosen because it answers a question, so prose that answers it is enough; a Design with neither is not.
            # A linked tech spec carries the diagram, the alternatives, and the pre-mortem as well as the Spec can; with
            # neither, the required-docs matrix says so (`doc_checks.doc_findings`).
            techs = doc_checks.tech_specs(path, data)
            design = markdown_section(text, "Design")
            if (
                not doc_checks.has_diagram(design)
                and len(design.split()) < doc_checks.DESIGN_PROSE_WORDS
                and not any(doc_checks.has_diagram(t) for _, t in techs)
            ):
                shape = "add one so a human reads the change's shape before the words at Spec approval"
                errs.append(f"warning: {path}: the Design section of a major Spec has no diagram (a ```mermaid block or an image) and little prose; {shape}")
            for heading, advice in (
                ("Alternatives considered", "say what else you weighed, including doing nothing"),
                ("Pre-mortem", "references/graph.md requires one"),
            ):
                for rel, body in techs if not markdown_section(text, heading) else []:
                    if not markdown_section(body, heading):
                        errs.append(f"warning: {path}: the tech spec {rel} has no '## {heading}' section with content; {advice}")
        errs += spec_warnings.intent_and_conflict_warnings(path, text, data)
    if data.get("type") in backlog.WORK_TYPES and data:
        errs += validate(path, text, data, spec_warnings.repo_root_of(path))
    errs += [f"warning: {path}: {w}" for w in intent_checks.document_team_warnings(data, spec_warnings.repo_root_of(path))]
    if data.get("type") == "proposal" and not any(not e.startswith("warning: ") for e in errs):
        errs += proposal_checks.proposal_findings(path, text, data)
    if data.get("type") == "release" and not any(not e.startswith(WARNING) for e in errs):
        errs += releases.file_findings(spec_warnings.repo_root_of(path), path, data)
    if data.get("type") in (*product_scope.HOLDING, product_scope.ORDER):
        errs[:] = product_checks.without_placeholder_errors(path, data, errs)
        if product_checks.placeholders(data):
            errs[:] = [e for e in errs if e != f"warning: {path}: still contains TODO placeholders"]
        errs += product_checks.file_findings(path, text, data, spec_warnings.repo_root_of(path))
    if data.get("type") == "intent":
        errs += spec_warnings.evidence_warnings(path, text)
        errs += intent_checks.approval_warnings(path, data, spec_warnings.repo_root_of(path))
    # A planned Spec's note stops these as an error does: they read sections Specify has not written yet.
    if data.get("type") == "spec" and not any(not e.startswith(WARNING) for e in errs):
        errs += spec_warnings.consistency_warnings(path, data)
        errs += spec_warnings.coverage_warnings(path, text, data)
        errs += spec_warnings.budget_warnings(path, text, data)
        errs += _glossary_warnings(path, text)
        errs += spec_warnings.size_warnings(path, text, data)
        errs += doc_checks.doc_findings(path, text, data)
        errs += spec_warnings.after_ship_warnings(path, text, data)
        errs += spec_warnings.open_question_warnings(path, data)
        root = spec_warnings.repo_root_of(path)
        cfg = repo_reads.config_at(root)
        errs += living_work.same_change_warnings(path, data, root, specs_dir=(cfg or config.EMPTY).specs_dir, docs_dir=(cfg or config.EMPTY).docs_dir)
        errs += living_work.unplanned_change_warnings(path, data, root, specs_dir=(cfg or config.EMPTY).specs_dir)
        errs += living_work.merged_drift_warnings(path, data, root, specs_dir=(cfg or config.EMPTY).specs_dir)
        if hint := config.hold_hint(text, data, repo_reads.config_at(spec_warnings.repo_root_of(path))):
            errs.append(f"warning: {path}: {hint}")
        if hint := config.cost_hint(data, repo_reads.config_at(spec_warnings.repo_root_of(path)), spec_warnings.listed_files(path, data)):
            errs.append(f"warning: {path}: {hint}")
        errs += [
            f"warning: {path}: {hint}"
            for hint in config.theme_hint(repo_reads.config_at(spec_warnings.repo_root_of(path)), doc_checks.design_specs(path, data))
        ]
    return errs


def route_findings(path: Path, data: dict) -> list[str]:
    """A Spec whose stored route is below the route its declared risk gives (`config.route_of_risk`): an error while the work is
    open, since the route decides the steps still to come, and a warning once it ended, since none are left. An emergency is
    below no route."""
    risk: dict = data["risk"] if isinstance(data.get("risk"), dict) else {}
    dimensions = [d for d in risk.get("dimensions") or [] if isinstance(d, str)] if isinstance(risk.get("dimensions"), list) else []
    irreversible = risk.get("irreversible") is True
    need, route = config.route_of_risk(dimensions, irreversible), data.get("route")
    if route not in config.ROUTE_RANK or config.ROUTE_RANK[route] >= config.ROUTE_RANK[need]:
        return []
    why = ", ".join([*(f"`{d}`" for d in dimensions if config.route_of_risk([d], False) == need), *(["`irreversible: true`"] if irreversible else [])])
    said = f"{path}: route {route} is below {need}, the route its risk gives ({why})"
    if status.spec_status(data) in status.TERMINAL:
        return [f"warning: {said}; the work ended, so no step is left to route, and the next Spec with this risk takes {need}"]
    step = f"set `route: {need}`"
    if status.spec_status(data) in status.PAST_APPROVAL:
        step += ", which changes an approved Spec, so the person who approved it approves it again (`spec.revise`)"
    return [f"{said}: {step}, or take out the risk it does not have"]


def check_repo(root: Path, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    today = today or dt.date.today()
    errors: list[str] = []
    warnings: list[str] = []
    specs_dir, proposals_dir, docs_dir, product_dir = "specs", "proposals", "docs", "product"
    cfg = config.EMPTY  # the config as loaded, else the defaults
    cfg_path = root / config.CONFIG_PATH

    def rel(path: Path) -> str:
        """A repository path as a finding names it: from the root, in forward slashes."""
        return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()

    if cfg_path.is_file():
        for e in validate_file(cfg_path, rel(cfg_path)):
            (errors if is_error(e) else warnings).append(e)
        try:
            cfg = config.load_file(config.CONFIG_PATH, str(root))
            specs_dir, proposals_dir, docs_dir, product_dir = cfg.specs_dir, cfg.proposals_dir, cfg.docs_dir, cfg.product_dir
        except (config.ConfigError, documents.DocumentError, RuntimeError):
            pass
    else:
        errors.append(NO_CONFIG)
    ids: dict[str, str] = {}
    item_types: dict[str, str] = {}
    objects: list[tuple[str, dict]] = []
    texts: dict[str, str] = {}
    work_folders = intent_paths.work_folders(specs_dir, product_dir)
    found = [workitems_objects.work_files(root, d) for d in (*work_folders, proposals_dir, *workitems_objects.OPS_DIRS.values())]
    # A link or a device where a work item could be is an error, never a file dropped without a word.
    errors += [f"{rel(path)}: {why}" for _, refused in found for path, why in refused]
    for path in [path for files, _ in found for path in files]:
        p = rel(path)
        errs = validate_file(path, p)
        for e in errs:
            (errors if is_error(e) else warnings).append(e)
        text, _ = workitems_objects.read_document(root, p)
        try:
            if text is None:
                continue
            texts[p] = text
            data, _ = documents.split_front_matter(text, p)
        except documents.DocumentError:
            continue
        objects.append((p, data))
        oid = data.get("id")
        if oid in ids:
            errors.append(f"{p}: id {oid} is also used by {ids[oid]}")
        elif oid:
            ids[oid] = p
            item_types[oid] = str(data.get("type"))
    errors += backlog.relation_errors(objects)
    for e in saved_requests.credential_findings(root, specs_dir, MAX_VALIDATE_FILES):
        (errors if is_error(e) else warnings).append(e)
    found_errors, found_warnings = intent_checks.intent_findings(objects)
    errors += found_errors
    errors += intent_checks.from_findings(objects)
    warnings += found_warnings
    warnings += interfaces.unprovided_warnings(objects)
    warnings += _measure_notes(root, objects)
    derived = spec_warnings.statuses(objects, frozenset(work_list.approved_versions(root, objects)))
    warnings += spec_warnings.status_warnings(objects, derived)
    product_found = _product_findings(root, cfg, objects, derived, today)
    errors += [e for e in product_found if is_error(e)]
    warnings += [e for e in product_found if not is_error(e)]
    # A removal counts once its Spec has merged, so a draft that removes a flag or a deprecation never silences it.
    flags_pending = due_dates.pending_removals(objects, derived, "removes_flags")
    for p, _, flag in due_dates.overdue_flags(objects, today, derived):
        how = due_dates.flag_cleanup(flag, flags_pending.get(str(flag.get("name"))))
        warnings.append(f"{p}: flag {flag.get('name')} was due for removal on {flag.get('cleanup_due')} (owner {flag.get('owner')}); {how}")
    deps_pending = due_dates.pending_removals(objects, derived, "removes_deprecations")
    for p, _, dep in due_dates.overdue_deprecations(objects, today, derived):
        how = due_dates.deprecation_removal(dep, deps_pending.get(str(dep.get("what"))))
        warnings.append(f"{p}: deprecation {dep.get('what')!r} passed its sunset on {dep.get('sunset')}; {how}")
    warnings += due_dates.renewal_warnings(root, objects, today, docs_dir)
    improvement_log = authoring.REPO_DOCS["improvement-log"][0][0].replace("{docs}", docs_dir)
    if (text := workitems_objects.read_document(root, improvement_log)[0]) is not None:
        warnings += living_docs.overdue_improvements(improvement_log, text, today)
    warnings += living_docs.index_warnings(root, repo_reads.config_at(root), docs_dir)
    warnings += placeholders.repo_doc_warnings(root, docs_dir)
    warnings += guide_checks.guide_warnings(root)
    warnings += delegated_yes.commit_warnings(root) + [w for p, data in objects for w in delegated_yes.spec_warnings(root, str(p), data)]
    for p, data in objects:
        if data.get("type") == "proposal":
            for step in ("go_no_go", "sign_off", "outcome"):
                who = str((data.get(step) or {}).get("by", ""))
                if who and config.is_agent(who):
                    errors.append(f"{p}: {step}.by {who} is an agent account; a person decides a proposal")
        if data.get("type") == "intent":
            who = str((data.get("go_no_go") or {}).get("by", ""))
            if who and config.is_agent(who):
                errors.append(f"{p}: go_no_go.by {who} is an agent account; a person decides whether an Intent goes ahead")
        if data.get("type") in ("proposal", "intent"):
            warnings += due_dates.overdue_raid_entries(p, data, today)
            for entry in data.get("decisions") or []:
                who = str(entry.get("by", "")) if isinstance(entry, dict) else ""
                if who and config.is_agent(who):
                    errors.append(f"{p}: decisions {entry.get('id')}.by {who} is an agent account; a person decides scope")
        if data.get("type") == "postmortem" and data.get("spec") and data["spec"] != status.PLACEHOLDER:
            if data["spec"] not in ids:
                warnings.append(f"{p}: spec {data['spec']} is not in {specs_dir}/; name the emergency change's backfill Spec")
        if data.get("type") == "postmortem":
            warnings += due_dates.overdue_actions(p, data, today)
            errors += due_dates.target_errors(p, data)
        if data.get("type") == "spec":
            errors += due_dates.deprecation_errors(p, data)
        if wait := due_dates.passed_wait(p, texts[p], today):
            warnings.append(wait)
        parent = data.get("parent")
        if parent and parent not in ids:
            warnings.append(
                f"{p}: parent {parent} is not in {specs_dir}/ or {intent_paths.intents_folder(product_dir)}/ (fine if the parent lives outside the repository)"
            )
        elif parent and (why := workitems_objects.parent_type_error(str(data.get("type")), parent, item_types[parent])):
            # Unlike a missing parent, which may live outside the repository, a parent of another type is wrong for certain.
            errors.append(f"{p}: {why}")
        em = data.get("emergency")
        if data.get("route") == "emergency" and isinstance(em, dict) and em.get("backfill_due") is not None:
            if due_dates.backfill_due(data) is None:
                errors.append(f"{p}: emergency.backfill_due {em['backfill_due']!r} is not a date")
                continue
            if due_dates.backfill_overdue(data, today):
                errors.append(f"{p}: post-incident review was due {due_dates.backfill_due(data)}; record outcome.learn_ref")
            elif far := due_dates.backfill_horizon_warning(p, data, today):
                warnings.append(far)
        # A Spec's `outcome` is a block of what happened after the release; an Intent's is one sentence, so only a mapping is read.
        out = data["outcome"] if isinstance(data.get("outcome"), dict) else {}
        if data.get("route") == "major" and out.get("released_on") and not out.get("observe_result"):
            warnings.append(f"{p}: released major change has no outcome.observe_result")
        # `hypothesis` is frozen by Spec approval and `outcome.hypothesis_result` records what the metric did. One without
        # the other means the claim in the changelog is not being kept: a result nobody predicted, or
        # a prediction nobody measured.
        if out.get("hypothesis_result") and not data.get("hypothesis"):
            warnings.append(f"{p}: outcome.hypothesis_result records a metric no hypothesis predicted; add the hypothesis before Spec approval next time")
        if data.get("hypothesis") and out.get("released_on") and not out.get("hypothesis_result"):
            warnings.append(f"{p}: a released change with a hypothesis has no outcome.hypothesis_result; Learn records what the metric did")
    from aidd.workitems import explorations

    rel_errors, rel_warnings = releases.repo_findings(root, objects, cfg)
    errors += rel_errors
    warnings += rel_warnings
    warnings += explorations.hints(root, repo_reads.config_at(root), today)
    warnings += commit_text.branch_assisted_by_warnings(root)
    return errors, warnings


def _measure_notes(root: Path, objects: list[tuple[str, dict]]) -> list[str]:
    """A note for each criterion whose `measure_on` aidd ignores because it is earlier than the last release of the Intent's work, and for
    each part of its work whose release day cannot be read here (built in another repository, or its commit is not in this clone)."""
    work = [d for _, d in objects if d.get("type") in backlog.WORK_TYPES]
    specs = {str(d["id"]): d for d in work if d.get("type") == "spec" and d.get("id")}
    states, _, children = intents.intent_statuses(work, {i: status.spec_status(d) for i, d in specs.items()})
    lines = intents.planned_spec_lines(work)
    known = criteria.Work(states, specs, lines, criteria.merged_days_of(str(root), work))
    out = []
    for p, d in objects:
        if d.get("type") == "intent" and criteria.criteria_of(d):
            kids = children.get(str(d.get("id")), [])
            last = criteria.last_release(kids, known)
            out += [f"{NOTE}{p}: {note}" for note in [*criteria.notes(d, last), *criteria.unread_days(kids, known)]]
    return out


def _product_findings(root: Path, cfg: config.Config, objects: list[tuple[str, dict]], derived: dict[str, str], today: dt.date) -> list[str]:
    """What `aidd validate` says of the product scope: each file of it, by name, that the walk of the work items did not read, and
    what the files and the Intents (`objects`, with the statuses `derived` from them) owe each other. `cfg` is the config `check_repo`
    already loaded, for `product_dir` and `limits.max_intent_specs`."""
    scope = product_scope.read(root, cfg.product_dir)
    read_already = {p for p, _ in objects}
    found = [e for f in scope.files.values() if f.path not in read_already for e in validate_file(root / f.path, f.path)]
    intents = [(p, d) for p, d in objects if d.get("type") == "intent"]
    return found + product_checks.scope_findings(scope, product_checks.Repository(root, intents, derived, today, cfg.max_intent_specs))


def validate(path: Path, text: str, data: dict, root: Path | None) -> list[str]:
    """One work item's triage and owner errors, and its warnings about handoffs and who said yes, for `aidd validate`."""
    from aidd import knowledge

    errs: list[str] = []
    cfg = repo_reads.config_at(root)
    if data.get("type") == "spec" and (data.get("suggested_by") or data.get("triage")):
        proactive = knowledge.proactive_roles(cfg) if cfg is not None or root is not None else None
        errs += [f"{path}: {e}" for e in triage.triage_errors(data, proactive=proactive)]
        t = data.get("triage")
        if isinstance(t, dict) and t.get("decision") == "declined" and not t.get("reason"):
            errs.append(f"warning: {path}: triage declined with no triage.reason; say why in one sentence, so a later triage of the same idea reads it first")
    errs += [f"{path}: {e}" for e in triage.owner_errors(data)]
    errs += [f"{path}: {e}" for e in intent_checks.development_team_problems(data, cfg)]
    if data.get("type") == "spec" and root is not None and cfg is not None:
        errs += [f"warning: {path}: {w}" for w in unlinked_in_folder(root, cfg, data)]
    said_yes = [("approved_by", data.get("approved_by"))] if data.get("type") == "spec" else []
    said_yes += [("revisions[].by", r.get("by")) for r in data.get("revisions") or [] if isinstance(r, dict)] if said_yes else []
    errs += [f"warning: {path}: {p}" for field, by in said_yes if isinstance(by, str) and (p := config.approved_by_problem(by, field))]
    errs += intent_checks.approval_problems(path, data)
    errs += intent_checks.criteria_problems(path, data)
    if data.get("type") == "intent" and root is not None and (found := intent_checks.place_problem(path, root, cfg)):
        errs.append(found)
    return errs + handoff_notes.handoff_warnings(str(path), text)


def unlinked_in_folder(root: Path, cfg: config.Config, data: dict) -> list[str]:
    """The files in a Spec's own folder (`specs/<ID>/`) that it does not link (`docs`, design files included):
    a role writes its document there before linking it, and links it before Spec approval. Its explorations are not
    linked. `aidd validate` warns about each unlinked one."""
    from aidd.kernel import globs

    folder = root / cfg.specs_dir / str(data.get("id") or "")
    if not data.get("id") or not folder.is_dir():
        return []
    linked = [d["path"] for d in data.get("docs") or [] if isinstance(d, dict) and isinstance(d.get("path"), str)]
    files, _ = _walk_bounded(folder)
    out = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        if "/explore/" in f"/{p.relative_to(folder).as_posix()}" or globs.match_any(linked, rel):
            continue
        out.append(
            f"{rel} sits in {data['id']}'s folder, but the Spec does not link it. Add it to `docs` before Spec approval (frozen by default; "
            "`frozen: false` keeps it living, and `type: design-files` takes a glob of mockups and flows), or move it out"
        )
    return out
