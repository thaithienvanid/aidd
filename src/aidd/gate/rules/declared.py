"""The declared part of a change: the base branch's config, the Change Request block and the Spec it names, the
platform's facts, and a standard change's class.
"""

from __future__ import annotations

import hashlib

from aidd import __version__, config, workitems
from aidd.gate import routing
from aidd.gate.rules import gate_run
from aidd.kernel import documents, globs


def bot_standard_change(cfg: config.Config, ctx: dict) -> dict | None:
    """A block for a bot PR that has none: every author must belong to one configured standard class."""
    system = {config.normalize_identity(x) for x in cfg.get("identities", "system_accounts", default=list(gate_run.DEFAULT_SYSTEM_ACCOUNTS))}
    people = {config.normalize_identity(c[k]) for c in ctx["commits"] for k in ("author", "committer") if c.get(k)} - system
    people.add(config.normalize_identity(ctx["change"]["author"]))
    for entry in cfg.get("standard_changes", default=[]):
        if people <= {config.normalize_identity(a) for a in entry["authors"]}:
            return {
                "route": "standard",
                "standard_change": entry["name"],
                "type": entry.get("type", "deps"),
                "confidence": "high",
                "scope": list(entry["paths"]),
                "rollback": "Revert the change.",
                "assisted_by": [],
                "risk": {
                    "summary": f"Pre-approved standard change class {entry['name']}.",
                    "dimensions": list(entry.get("dimensions", ["third_party"])),
                    "reversible": True,
                },
            }
    return None


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("-")[0].split("+")[0].split(".")[:3])
    except ValueError:
        return (0,)


def gate_config(run: gate_run.GateRun) -> None:
    """Config comes from the base branch. A base without one never passes: an administrator merges the first config."""
    ctx, add = run.ctx, run.add
    run.record.update(
        change=ctx["change"]["id"], platform=ctx.get("platform"), head_sha=run.head, base_sha=ctx["base_sha"], trusted=bool(ctx.get("trusted", False))
    )
    cfg_text = ctx.get("base_config")
    bootstrap = False
    if cfg_text is None:
        cfg_text = ctx["head_files"].get(config.CONFIG_PATH)
        bootstrap = cfg_text is not None
    if cfg_text is None:
        add(
            "config",
            "fail",
            f"no {config.CONFIG_PATH} on the base branch or in this change",
            "run `aidd init` and merge the config first",
            code="config.missing",
        )
        run.stop()
    try:
        run.config = config.load_text(cfg_text, prefetched=ctx.get("extends_texts") or {}, root_preset=ctx.get("org_preset"))
    except (config.ConfigError, documents.DocumentError) as exc:
        add("config", "fail", str(exc), "fix .aidd/config.yaml on the base branch", code="config.invalid")
        run.stop()
    cfg = run.cfg
    parts = [cfg_text, ctx.get("org_preset") or "", *(x for kv in sorted((ctx.get("extends_texts") or {}).items()) for x in kv)]
    run.record["config_sha256"] = hashlib.sha256("".join(f"{len(x)}:{x}" for x in parts).encode("utf-8")).hexdigest()
    if not bootstrap and cfg.get("mode"):
        run.record["config_mode"] = cfg.get("mode")  # a config the change itself adds never sets the mode
    if bootstrap:
        add(
            "config",
            "pending",
            "the base branch has no config, so this change cannot pass the gate",
            "a repository administrator merges the first config outside the gate; later changes are gated",
            code="config.bootstrap",
        )
    for w in cfg.warnings:
        add("config", "warn", w, code="config.warning")
    run.record.update(profile=cfg.profile, tenant=cfg.tenant)
    declared_version = str(cfg.get("aidd_version", default="") or "")
    if declared_version and _version_tuple(declared_version) > _version_tuple(__version__):
        add(
            "config",
            "warn",
            f"the config declares aidd_version {declared_version}, newer than this aidd ({__version__})",
            "upgrade the aidd pins (the workflow refs and the CLI) together with the config, as docs/INSTALL.md describes",
            code="config.newer_version",
        )
    if not cfg.approvers:
        add(
            "config",
            "fail",
            f"profile {cfg.profile} requires owners.approvers",
            'list approvers, for example approvers: ["@org/team"], or your own login under solo; an empty list means no change can merge (the gate fails closed)',
            code="config.no_approvers",
        )


def gate_change_request(run: gate_run.GateRun) -> None:
    """The declared part: one Change Request block, and the Spec it names."""
    ctx, add = run.ctx, run.add
    cr, errs = workitems.parse_change_block(ctx["change"]["body"])
    if cr is None and not errs:
        cr = bot_standard_change(run.cfg, ctx)
        if cr is None:
            if ctx.get("platform") == "local":
                # On one machine the description is the branch's commits: name them, and the one command that fixes it.
                where = "this branch's commits have no Change Request block (```yaml aidd)"
                fix = '`aidd describe --commit` adds one in a new commit; a change that needs a Spec takes `aidd new spec "<title>"` first'
            else:
                where = "the PR/MR description has no Change Request block (```yaml aidd)"
                fix = f"add one (`aidd describe` prints a starting point), for example:\n{gate_run.BLOCK_EXAMPLE}"
            add("change_request", "fail", where, fix, code="change_request.no_block")
            run.stop()
        add(
            "change_request",
            "warn",
            f"no Change Request block: treated as standard change {cr['standard_change']!r}, because every author belongs to that class",
            code="change_request.standard_by_default",
        )
    for e in errs:
        add("change_request", "fail", e, "fix the block in the PR/MR description; `aidd describe` writes a valid one", code="change_request.invalid")
    if errs:
        run.stop()
    assert cr is not None  # no block and no errors was handled above
    if run.member is not None:
        # One Spec of a goal's change: judged as a change of that Spec, its trace_id the Spec's own.
        cr = {"spec": run.member}
        run.goal_paths = _goal_paths(run, [m for m in run.members if m != run.member])
    run.cr = cr
    if "spec" in cr:
        spec_path = cr["spec"]
        run.spec_text = ctx["head_files"].get(spec_path)
        if run.spec_text is None:
            add("spec", "fail", f"{spec_path} is not in the head commit", "commit the Spec file at that path", code="spec.not_at_head")
            run.stop()
        try:
            loaded, _body, serrs = workitems.load_object(run.spec_text, spec_path)
        except documents.DocumentError as exc:
            add("spec", "fail", str(exc), f"fix the Spec's front matter, then run `aidd validate {spec_path}`", code="spec.unparsable")
            run.stop()
        if loaded.get("kind") != "spec":
            serrs = serrs or [f"{spec_path}: kind must be spec"]
        for e in serrs:
            add("spec", "fail", e, f"fix the Spec, then run `aidd validate {spec_path}` until it shows 0 errors", code="spec.invalid")
        if serrs:
            run.stop()
        extra = sorted(set(cr) - {"spec", "trace_id"})
        if extra:
            add(
                "change_request",
                "fail",
                f"with spec set, the block holds only spec and trace_id; move {extra} into the Spec",
                "keep only spec and trace_id in the block; the Spec holds the rest",
                code="change_request.extra_keys",
            )
        if cr.get("trace_id") and cr["trace_id"] != loaded.get("trace_id", loaded["id"]):
            add(
                "change_request",
                "fail",
                f"trace_id {cr['trace_id']!r} differs from the Spec trace_id {loaded.get('trace_id', loaded['id'])!r}",
                "copy the Spec's trace_id into the block, or take trace_id out of the block",
                code="change_request.trace_id_mismatch",
            )
        if run.member is not None and (loaded.get("tests") or {}).get("commands"):
            # As `aidd test` ran it for the goal: each command named for its Spec.
            commands = [workitems.goal_command(str(loaded["id"]), c) for c in loaded["tests"]["commands"]]
            loaded = {**loaded, "tests": {**loaded["tests"], "commands": commands}}
        run.spec = loaded
        run.declared = loaded
    else:
        if cr["route"] in ("normal", "major"):
            add("spec", "fail", f"route {cr['route']} needs a Spec file", 'write specs/<ID>.md and set spec: "specs/<ID>.md" in the block', code="spec.missing")
            run.stop()
        run.scope_declared = "scope" in cr
        run.declared = workitems.with_defaults(cr, routing.changed_paths(ctx["files"]))
    declared, spec = run.declared, run.spec
    run.route = declared["route"]
    run.tasks = spec["tasks"] if spec else [{"id": "inline", "title": "inline", "scope": list(declared["scope"])}]
    tests_decl = declared.get("tests")
    run.test_files = list(tests_decl["files"]) if tests_decl else []
    # The design files and the frozen docs: approved with the Spec, so never implementation scope or budget.
    run.design_files = workitems.design_paths(spec or {})
    run.threat_models = workitems.threat_models(spec or {}, run.cfg.docs_dir)
    run.record.update(
        spec=cr.get("spec"),
        spec_id=spec["id"] if spec else None,
        trace_id=declared.get("trace_id", spec["id"] if spec else None),
        owner_team=spec.get("owner_team") if spec else None,
        route=run.route,
        type=declared["type"],
        confidence=declared["confidence"],
        risk=declared["risk"],
        rollback=declared["rollback"],
        residual_risk=declared.get("residual_risk"),
        assisted_by=declared["assisted_by"],
        scope=sorted({s for task in run.tasks for s in task["scope"]}),
        scope_declared=run.scope_declared,
    )
    if declared["confidence"] == "low":
        add("confidence", "fail", "confidence is low", "answer the open_questions, then run `aidd gate --paths` again", code="confidence.low")
    if not spec and cr.get("route") == "emergency" and cr.get("backfill"):
        _check_backfill(run, cr)
    if not spec and run.scope_declared:
        # An inline Change Request block has no human before the diff, so its scope must be narrow and its tests separate.
        for pattern in list(declared["scope"]) + list(run.test_files):
            if globs.is_catch_all(pattern):
                add(
                    "scope",
                    "fail",
                    f"{pattern!r} matches every path, so it declares no scope",
                    "name the files or directories the change touches",
                    code="scope.catch_all",
                )
        for pattern in declared["scope"]:
            for tf in run.test_files:
                if globs.overlap(pattern, tf):
                    add("scope", "fail", f"scope {pattern!r} overlaps test file {tf!r}", "keep test files out of the scope", code="scope.overlaps_test")
    elif not spec:
        for tf in run.test_files:
            if globs.is_catch_all(tf):
                add("scope", "fail", f"{tf!r} matches every path, so it names no test file", "name the test files or directories", code="scope.test_catch_all")


def _goal_paths(run: gate_run.GateRun, others: list[str]) -> list[str]:
    """What a goal's change holds beyond this Spec that is not this Spec's to implement: each other Spec of the goal
    with its Task scopes, test files, and design files, and the plan items (an Initiative or an Epic directly in the
    specs folder). An unreadable Spec adds only its own path: its own run reports it."""
    out: list[str] = []
    for path in others:
        out.append(path)
        try:
            data = workitems.load_object(run.ctx["head_files"].get(path) or "", path)[0]
        except documents.DocumentError:
            continue
        out += [s for t in data.get("tasks") or [] if isinstance(t, dict) for s in t.get("scope") or [] if isinstance(s, str)]
        out += [s for s in (data.get("tests") or {}).get("files") or [] if isinstance(s, str)]
        out += workitems.design_paths(data) + workitems.threat_models(data, run.cfg.docs_dir)
    for path, text in run.ctx["head_files"].items():
        try:
            in_folder = globs.match_any(workitems.plan_paths(run.cfg.specs_dir), path)
            if in_folder and documents.split_front_matter(text, path)[0].get("kind") in ("initiative", "epic"):
                out.append(path)
        except (documents.DocumentError, ValueError):
            continue
    return out


def _check_backfill(run: gate_run.GateRun, cr: dict) -> None:
    """An emergency commits its backfill Spec stub, so the review debt is visible to `aidd validate`."""
    path = cr["backfill"]
    text = run.ctx["head_files"].get(path)
    fix = f"commit the stub: aidd new spec <ID> --route emergency, at {path}, with the same review_due"
    if text is None:
        run.add("emergency", "fail", f"the backfill Spec {path} is not in the head commit", fix, code="emergency.backfill_missing")
        return
    try:
        data, _ = documents.split_front_matter(text, path)
    except documents.DocumentError as exc:
        run.add("emergency", "fail", str(exc), fix, code="emergency.backfill_unparsable")
        return
    due = str((data.get("emergency") or {}).get("review_due", ""))
    if data.get("kind") != "spec" or data.get("route") != "emergency" or due != str(cr["emergency"]["review_due"]):
        run.add(
            "emergency",
            "fail",
            f"{path} must be a Spec with route emergency and review_due {cr['emergency']['review_due']}",
            fix,
            code="emergency.backfill_mismatch",
        )


def gate_facts(run: gate_run.GateRun) -> None:
    """Facts from the platform: the diff, and who authored the change."""
    ctx, cfg, add = run.ctx, run.cfg, run.add
    files = ctx["files"]
    run.paths = routing.changed_paths(files)
    reviewed: list[str] = []
    if run.spec:
        # The Spec and its tests were reviewed at Spec approval; the budget measures what is left to review at Merge approval.
        # Tests written with the code (`tests.mode: with`) were not, so Merge approval reviews them and they count.
        tests = [] if workitems.tests_with(run.spec) else run.test_files
        reviewed += [run.cr["spec"], *tests, *run.design_files]
    if run.cr.get("backfill"):
        reviewed.append(run.cr["backfill"])
    reviewed += routing.proposal_only(run.paths, cfg)
    run.changed_lines = routing.budget_lines(files, cfg, reviewed)
    run.binary_files = routing.counted_binaries(files, cfg)
    run.record.update(changed_paths=run.paths, changed_files=len(files), changed_lines=run.changed_lines, binary_files=run.binary_files)
    if ctx.get("commits_truncated"):
        add(
            "authors",
            "fail",
            "the platform returned only part of the commit list, so authors cannot be verified",
            "split the change, or squash it below the platform's commit limit",
            code="authors.truncated",
        )
    system = {config.normalize_identity(x) for x in cfg.get("identities", "system_accounts", default=list(gate_run.DEFAULT_SYSTEM_ACCOUNTS))}
    run.bots = {run.local(x) for x in cfg.get("identities", "bots", default=[])}
    authors = {run.local(c[k]) for c in ctx["commits"] for k in ("author", "committer") if c.get(k)}
    # A co-author wrote part of the change too, so they may not approve it.
    authors |= {config.normalize_identity(x) for c in ctx["commits"] for x in config.human_coauthors(c.get("message") or "", run.bots)}
    run.authors = (authors - system) | {run.local(ctx["change"]["author"])}
    run.record["authors"] = sorted(run.authors)
    # A commit email the platform cannot map to an account might belong to an Approver,
    # so separation of duties cannot be proven for it.
    unlinked = sorted(o for o in run.authors if o.startswith("email:") and o not in run.bots)
    if unlinked and not run.solo and not ctx.get("committer_approval_blocked"):
        level = "fail" if run.g["unlinked_authors"] == "fail" else "warn"
        add(
            "authors",
            level,
            f"commit author(s) {', '.join(unlinked[:5])} are not linked to a platform account, so an Approver may have written them",
            "link the email to its account, list agent emails in identities.bots, or rewrite the commits",
            code="authors.unlinked",
        )


def gate_standard_change(run: gate_run.GateRun) -> None:
    if run.route != "standard":
        return
    cfg, add = run.cfg, run.add
    name = run.cr.get("standard_change")
    entry = next((e for e in cfg.get("standard_changes", default=[]) if e["name"] == name), None)
    if not run.g["standard_changes"]:
        add(
            "standard_change",
            "fail",
            f"profile {cfg.profile} does not allow standard changes",
            "use the route `aidd gate --paths` computes, with a Spec when it needs one",
            code="standard_change.not_allowed",
        )
    elif entry is None:
        add(
            "standard_change",
            "fail",
            f"no standard_changes entry named {name!r} in the config",
            "set standard_change to a configured class, or use another route",
            code="standard_change.unknown_class",
        )
    else:
        problems = routing.standard_match(entry, paths=run.paths, identities=run.authors, changed_lines=run.changed_lines)
        unsigned = [c["sha"][:10] for c in run.ctx["commits"] if c.get("verified") is not True]
        if unsigned:
            problems.append(f"commits without a platform-verified signature: {', '.join(unsigned[:5])}")
        for p in problems:
            add(
                "standard_change",
                "fail",
                f"{name}: {p}",
                f"change the PR/MR so it fits {name}, or use the route `aidd gate --paths` computes",
                code="standard_change.mismatch",
            )
        too_big = _update_type_problem(run, entry)
        if too_big:
            add(
                "standard_change",
                "fail",
                f"{name}: {too_big}",
                "take the update through a normal change, or widen the class's update_types in the base branch's config",
                code="standard_change.update_type",
            )
        run.standard_ok = not problems and not too_big


def allowed_update_types(entry: dict) -> list[str] | None:
    """The update types a standard class takes: its `update_types`, else patch and minor for a third_party class, else any."""
    if "update_types" in entry:
        return list(entry["update_types"])
    return ["patch", "minor"] if "third_party" in entry.get("dimensions", ["third_party"]) else None


def _update_type_problem(run: gate_run.GateRun, entry: dict) -> str | None:
    """Why the change's dependency updates exceed its class, or None. The worst of what the diff's manifests show
    (the adapter's `dependency_updates`) and what Dependabot's metadata declares; unknown counts as major, and so does
    a context without `dependency_updates`."""
    from aidd.gate import dependency_updates

    allowed = allowed_update_types(entry)
    if allowed is None:
        return None
    ctx = run.ctx
    texts = [ctx["change"].get("body") or ""] + [c.get("message") or "" for c in ctx["commits"]]
    declared = dependency_updates.dependabot_types(texts)
    found = ctx.get("dependency_updates")
    shown = [f"{u['name'] or u['file']} {u['from'] or '-'} -> {u['to'] or '-'} ({u['update_type']})" for u in found or []]
    kinds = [u["update_type"] for u in found or []] + declared
    if found is None and not declared:
        kinds, shown = ["unknown"], ["the adapter read no dependency versions from the diff"]
    beyond = [k for k in (k if k in dependency_updates.UPDATE_TYPES else "major" for k in kinds) if k not in allowed]
    if not beyond:
        return None
    detail = "; ".join(shown[:5]) or f"Dependabot declares {', '.join(sorted(set(declared)))}"
    return (
        f"the class takes {', '.join(allowed) or 'no'} updates, and this change holds a {max(beyond, key=dependency_updates.UPDATE_TYPES.index)} one: {detail}"
    )
