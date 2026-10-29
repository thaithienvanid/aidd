"""`aidd validate`: the config and every work item checked against its schema and past it, with the warnings a person
reads and the gate never does.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from aidd import config
from aidd.kernel import documents, processes
from aidd.kernel.documents import markdown_section
from aidd.workitems import (
    authoring,
    backlog,
    doc_checks,
    due_dates,
    handoff_notes,
    living_work,
    proposal_checks,
    repo_reads,
    small_goals,
    spec_file,
    spec_warnings,
    triage,
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


def validate_file(path: Path, label: str | None = None) -> list[str]:
    """Each finding names the file by `label`, else by the path in forward slashes, on every OS."""
    shown = label or path.as_posix()
    raw = str(path)
    return [e.replace(raw, shown) for e in _validate_file(path)] if raw != shown else _validate_file(path)


def _validate_file(path: Path) -> list[str]:
    if path.is_dir():
        files, stopped = _walk_bounded(path)
        errs = [
            e
            for f in files
            if ((f.name == "config.yaml" and f.parent.name == ".aidd") or (f.suffix == ".md" and workitems_objects.is_object(f)))
            and f.name.lower() != "readme.md"
            and "assets" not in f.parts
            for e in validate_file(f)
        ]
        if stopped:
            errs.append(f"warning: {path}: directory walk reached bound and stopped early")
        return errs
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{path}: not UTF-8 text"]
    if path.suffix in (".yaml", ".yml"):
        try:
            cfg = config.load_text(
                text, read=lambda p: (path.parent.parent / p).read_text(encoding="utf-8") if (path.parent.parent / p).is_file() else None, where=str(path)
            )
        except (config.ConfigError, documents.DocumentError, RuntimeError) as exc:
            return str(exc).splitlines()
        out = [f"warning: {w}" for w in cfg.warnings + config.advice(cfg)]
        errors, warnings = config.project_findings(cfg)
        out += [f"{path}: {e}" for e in errors] + [f"warning: {path}: {w}" for w in warnings]
        out += [f"{path}: {e}" for e in command_problems(cfg.get("tests", default=[]))]
        if path.name == "config.yaml" and not cfg.approvers:
            out.append(f"{path}: profile {cfg.profile} requires owners.approvers (solo too); {config.EMPTY_APPROVERS}")
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
    try:
        return _object_checks(path, text, data, errs)
    except (AttributeError, TypeError, KeyError):
        # The checks read the fields the schema describes. When the schema already rejected one (a string `risk`
        # where a table belongs), they stop there: the schema errors, and whatever they found first, are the report.
        if any(not e.startswith("warning: ") for e in errs):
            return errs
        raise


def command_problems(commands: object) -> list[str]:
    """Each test command that cannot start, because its program is a shell's `NAME=value`, by its name."""
    found = []
    for c in commands if isinstance(commands, list) else []:
        argv = c.get("command") if isinstance(c, dict) else None
        if isinstance(argv, list) and (why := processes.assignment_problem([str(a) for a in argv])):
            found.append(f"the test command `{documents.one_line(c.get('name'), 60)}` cannot start: {why}")
    return found


def unready_for_approval(text: str, label: str) -> list[str]:
    """Why a Spec, as committed, is not ready for anyone to approve: placeholders left in what the gate runs or scopes,
    as `aidd new spec` writes them. From the text alone, so it holds for a Spec on any branch, and `aidd approve` and
    `next` ask the same question; an approval of a stub would freeze the stub. `aidd validate` reports the rest, and
    spec_approval_problems adds it where a person approves."""
    try:
        data, _, _ = spec_file.load_object(text, label)
    except documents.DocumentError as exc:
        return [str(exc)]
    out: list[str] = []
    tests = data.get("tests") or {}
    executable = [a for c in tests.get("commands", []) or [] for a in c.get("command", []) or []]
    executable += [s for task in data.get("tasks", []) or [] for s in task.get("scope", []) or []]
    executable += list(tests.get("files", []) or [])
    if any("TODO" in str(x) for x in executable) and data.get("route") != "emergency":
        out.append(f"{label}: test commands, tests.files, or a Task's scope still hold TODO placeholders")
    return out


def spec_approval_problems(text: str, label: str) -> list[str]:
    """Why a person's Spec approval would not hold: unready_for_approval, then each error `aidd validate` reports from
    the text. A Spec the team must still change would void the approval with its fix, and ask the person again."""
    try:
        _, _, errors = spec_file.load_object(text, label)
    except documents.DocumentError as exc:
        return [str(exc)]
    return list(dict.fromkeys(unready_for_approval(text, label) + [e for e in errors if not e.startswith("warning: ")]))


def _glossary_warnings(path: Path, text: str) -> list[str]:
    """The Spec's lines that use a word the repository glossary (`aidd new glossary`, under the docs folder) says to
    avoid. No glossary, no warning; one that cannot be read says so."""
    root = spec_warnings.repo_root_of(path)
    if root is None:
        return []
    cfg = repo_reads.config_at(root)
    rel = authoring.REPO_DOCS["glossary"][0][0].replace("{docs}", cfg.docs_dir if cfg else "docs")
    if not (root / rel).is_file():
        return []
    try:
        glossary = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"warning: {path}: the glossary {rel} cannot be read ({exc.strerror}), so its Avoid words were not checked; fix its permissions"]
    return spec_warnings.glossary_warnings(path, text, rel, glossary)


def _object_checks(path: Path, text: str, data: dict, errs: list[str]) -> list[str]:
    """The checks past the schema, appending to `errs` (the schema's findings) as they go."""
    # A placeholder in what the gate executes or scopes is an error; elsewhere it is a reminder.
    tests = data.get("tests") or {}
    executable = [a for c in tests.get("commands", []) for a in c.get("command", [])]
    executable += [s for task in data.get("tasks", []) for s in task.get("scope", [])]
    executable += list(tests.get("files", []))
    errs += [f"{path}: {e}" for e in command_problems(tests.get("commands", []))]
    if any("TODO" in str(x) for x in executable):
        if data.get("route") == "emergency":
            # A backfill stub committed with the repair; `aidd validate` holds its review_due.
            errs.append(f"warning: {path}: emergency backfill Spec still holds TODO placeholders; finish it by review_due")
        else:
            errs.append(f"{path}: test commands, tests.files, or a Task's scope still hold TODO placeholders")
    elif "TODO" in text:
        errs.append(f"warning: {path}: still contains TODO placeholders")
    if data.get("kind") == "spec" and data.get("route") in ("normal", "major"):
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
                ("Pre-mortem", "references/loop.md requires one"),
            ):
                for rel, body in techs if not markdown_section(text, heading) else []:
                    if not markdown_section(body, heading):
                        errs.append(f"warning: {path}: the tech spec {rel} has no '## {heading}' section with content; {advice}")
        errs += spec_warnings.intent_and_conflict_warnings(path, text, data)
    if data.get("kind") in backlog.WORK_KINDS and data:
        errs += validate(path, text, data, spec_warnings.repo_root_of(path))
    if data.get("kind") == "proposal" and not any(not e.startswith("warning: ") for e in errs):
        errs += proposal_checks.proposal_findings(path, text, data)
    if data.get("kind") == "initiative":
        errs += spec_warnings.evidence_warnings(path, text)
    if data.get("kind") == "spec" and not any(not e.startswith("warning: ") for e in errs):
        errs += spec_warnings.consistency_warnings(path, data)
        errs += spec_warnings.coverage_warnings(path, text, data)
        errs += spec_warnings.vague_warnings(path, text)
        errs += spec_warnings.budget_warnings(path, text, data)
        errs += _glossary_warnings(path, text)
        errs += spec_warnings.size_warnings(path, text, data)
        errs += doc_checks.doc_findings(path, text, data)
        errs += spec_warnings.after_ship_warnings(path, text, data)
        root = spec_warnings.repo_root_of(path)
        cfg = repo_reads.config_at(root)
        errs += living_work.same_change_warnings(path, data, root, specs_dir=cfg.specs_dir if cfg else "specs", docs_dir=cfg.docs_dir if cfg else "docs")
        if hint := config.hold_hint(text, data, repo_reads.config_at(spec_warnings.repo_root_of(path))):
            errs.append(f"warning: {path}: {hint}")
        if hint := config.cost_hint(data, repo_reads.config_at(spec_warnings.repo_root_of(path)), spec_warnings.listed_files(path, data)):
            errs.append(f"warning: {path}: {hint}")
        errs += [
            f"warning: {path}: {hint}"
            for hint in config.theme_hint(repo_reads.config_at(spec_warnings.repo_root_of(path)), doc_checks.design_specs(path, data))
        ]
    return errs


def check_repo(root: Path, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    today = today or dt.date.today()
    errors: list[str] = []
    warnings: list[str] = []
    specs_dir, proposals_dir, docs_dir, bots = "specs", "proposals", "docs", set()
    cfg_path = root / config.CONFIG_PATH

    def rel(p: Path) -> str:
        """A repository path as a finding names it: from the root, in forward slashes."""
        return p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()

    if cfg_path.is_file():
        for e in validate_file(cfg_path, rel(cfg_path)):
            (warnings if e.startswith("warning: ") else errors).append(e)
        try:
            cfg = config.load_file(config.CONFIG_PATH, str(root))
            specs_dir, proposals_dir, docs_dir = cfg.specs_dir, cfg.proposals_dir, cfg.docs_dir
            bots = {b.lower().lstrip("@") for b in cfg.get("identities", "bots", default=[])}
        except (config.ConfigError, documents.DocumentError, RuntimeError):
            pass
    else:
        errors.append(NO_CONFIG)
    ids: dict[str, str] = {}
    kinds: dict[str, str] = {}
    objects: list[tuple[str, dict]] = []
    texts: dict[str, str] = {}
    ops = [p for d in workitems_objects.OPS_DIRS.values() for p in workitems_objects.object_files(root, d)]
    for path in workitems_objects.object_files(root, specs_dir) + workitems_objects.object_files(root, proposals_dir) + ops:
        p = rel(path)
        errs = validate_file(path, p)
        for e in errs:
            (warnings if e.startswith("warning: ") else errors).append(e)
        try:
            texts[p] = path.read_text(encoding="utf-8")
            data, _ = documents.split_front_matter(texts[p], p)
        except documents.DocumentError:
            continue
        objects.append((p, data))
        oid = data.get("id")
        if oid in ids:
            errors.append(f"{p}: id {oid} is also used by {ids[oid]}")
        elif oid:
            ids[oid] = p
            kinds[oid] = str(data.get("kind"))
    errors += backlog.relation_errors(objects)
    found_errors, found_warnings = small_goals.small_goal_checks(objects)
    errors += found_errors
    warnings += found_warnings
    derived = spec_warnings.derived_statuses(root, specs_dir, objects, texts)
    warnings += spec_warnings.status_warnings(objects, derived)
    # A removal counts once its Spec has landed, so a draft that removes a flag or a deprecation never silences it.
    flags_pending = due_dates.pending_removals(objects, derived, "removes_flags")
    for p, _, flag in due_dates.overdue_flags(objects, today, derived):
        how = due_dates.flag_cleanup(flag, flags_pending.get(str(flag.get("name"))))
        warnings.append(f"{p}: flag {flag.get('name')} was due for removal on {flag.get('cleanup_due')} (owner {flag.get('owner')}); {how}")
    deps_pending = due_dates.pending_removals(objects, derived, "removes_deprecations")
    for p, _, dep in due_dates.overdue_deprecations(objects, today, derived):
        how = due_dates.deprecation_removal(dep, deps_pending.get(str(dep.get("what"))))
        warnings.append(f"{p}: deprecation {dep.get('what')!r} passed its sunset on {dep.get('sunset')}; {how}")
    warnings += due_dates.renewal_warnings(root, objects, today, docs_dir)
    for p, data in objects:
        if data.get("kind") == "proposal":
            for step in ("go_no_go", "sign_off", "outcome"):
                who = str((data.get(step) or {}).get("by", ""))
                if who and config.is_agent(who, bots):
                    errors.append(f"{p}: {step}.by {who} is an agent account; a person decides a proposal")
        if data.get("kind") == "initiative":
            who = str((data.get("go_no_go") or {}).get("by", ""))
            if who and config.is_agent(who, bots):
                errors.append(f"{p}: go_no_go.by {who} is an agent account; a person decides whether an Initiative goes ahead")
        if data.get("kind") in ("proposal", "initiative"):
            for entry in data.get("decisions") or []:
                who = str(entry.get("by", "")) if isinstance(entry, dict) else ""
                if who and config.is_agent(who, bots):
                    errors.append(f"{p}: decisions {entry.get('id')}.by {who} is an agent account; a person decides scope")
        if data.get("kind") == "postmortem" and data.get("spec") and data["spec"] != "TODO":
            if data["spec"] not in ids:
                warnings.append(f"{p}: spec {data['spec']} is not in {specs_dir}/; name the emergency change's backfill Spec")
        if data.get("kind") == "postmortem":
            warnings += due_dates.overdue_actions(p, data, today)
            errors += due_dates.target_errors(p, data)
        if data.get("kind") == "spec":
            errors += due_dates.deprecation_errors(p, data)
        parent = data.get("parent")
        if parent and parent not in ids:
            warnings.append(f"{p}: parent {parent} is not in {specs_dir}/ (fine if the parent lives outside the repository)")
        elif parent and (why := workitems_objects.parent_kind_error(str(data.get("kind")), parent, kinds[parent])):
            # Unlike a missing parent, which may live outside the repository, a parent of another kind is wrong for certain.
            errors.append(f"{p}: {why}")
        em = data.get("emergency")
        if data.get("route") == "emergency" and isinstance(em, dict) and em.get("review_due") is not None:
            try:
                due = dt.date.fromisoformat(str(em["review_due"]))
            except ValueError:
                errors.append(f"{p}: emergency.review_due {em['review_due']!r} is not a date")
                continue
            outcome = data.get("outcome")
            learn_ref = outcome.get("learn_ref") if isinstance(outcome, dict) else None
            if due < today and not learn_ref:
                errors.append(f"{p}: post-incident review was due {due}; record outcome.learn_ref")
        out = data.get("outcome") or {}
        if data.get("route") == "major" and out.get("released_on") and not out.get("observe_result"):
            warnings.append(f"{p}: released major change has no outcome.observe_result")
        # `hypothesis` is frozen by Spec approval and `outcome.result` records what the metric did. One without
        # the other means the claim in the changelog is not being kept: a result nobody predicted, or
        # a prediction nobody measured.
        if out.get("result") and not data.get("hypothesis"):
            warnings.append(f"{p}: outcome.result records a metric no hypothesis predicted; add the hypothesis before Spec approval next time")
        if data.get("hypothesis") and out.get("released_on") and not out.get("result"):
            warnings.append(f"{p}: a released change with a hypothesis has no outcome.result; Learn records what the metric did")
    from aidd.workitems import explorations

    warnings += explorations.hints(root, repo_reads.config_at(root), today)
    return errors, warnings


def validate(path: Path, text: str, data: dict, root: Path | None) -> list[str]:
    """One work item's triage and owner errors and handoff warnings, for `aidd validate`."""
    from aidd import knowledge

    errs: list[str] = []
    cfg = repo_reads.config_at(root)
    bots = triage.bots_of(cfg)
    if data.get("kind") == "spec" and (data.get("suggested_by") or data.get("triage")):
        proactive = knowledge.proactive_roles(cfg) if cfg is not None or root is not None else None
        errs += [f"{path}: {e}" for e in triage.triage_errors(data, bots, proactive)]
        t = data.get("triage")
        if isinstance(t, dict) and t.get("decision") == "declined" and not t.get("reason"):
            errs.append(f"warning: {path}: triage declined with no triage.reason; say why in one sentence, so a later triage of the same idea reads it first")
    errs += [f"{path}: {e}" for e in triage.owner_errors(data, bots)]
    if data.get("kind") == "spec" and root is not None and cfg is not None:
        errs += [f"warning: {path}: {w}" for w in unlinked_in_folder(root, cfg, data)]
    return errs + handoff_notes.handoff_warnings(str(path), text)


def unlinked_in_folder(root: Path, cfg: config.Config, data: dict) -> list[str]:
    """The files in a Spec's own folder (`specs/<ID>/`) that it neither links (`docs`) nor lists (`design.files`):
    a role writes its document there before linking it, and links it before Spec approval. Its explorations are not
    linked. The gate's scope rule fails a change to an unlinked one."""
    from aidd.kernel import globs

    folder = root / cfg.specs_dir / str(data.get("id") or "")
    if not data.get("id") or not folder.is_dir():
        return []
    linked = [d["path"] for d in data.get("docs") or [] if isinstance(d, dict) and isinstance(d.get("path"), str)]
    linked += [p for p in (data.get("design") or {}).get("files", []) if isinstance(p, str)]
    files, _ = _walk_bounded(folder)
    out = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        if "/explore/" in f"/{p.relative_to(folder).as_posix()}" or globs.match_any(linked, rel):
            continue
        out.append(
            f"{rel} sits in {data['id']}'s folder, but the Spec does not link it. Add it to `docs` (frozen by default; "
            "`frozen: false` keeps it living) or to `design.files` before Spec approval, or move it out"
        )
    return out
