"""The rules on the diff itself: its route, its scope, its size, the merge queue, the test harness files, and drafts."""

from __future__ import annotations

import fnmatch

from aidd import config
from aidd.gate import routing, rulebook
from aidd.gate.rules import gate_run
from aidd.kernel import globs


def gate_route(run: gate_run.GateRun) -> None:
    """Judge the real diff. A Spec-backed normal change is raised to major; anything else below the minimum fails."""
    add, declared, spec = run.add, run.declared, run.spec
    risk = declared["risk"]
    controls = _config_controls(run)
    preferences = controls == []
    cls = routing.assess_route(
        paths=run.paths,
        cfg=run.cfg,
        ctype=declared["type"],
        risk=risk,
        confidence=declared["confidence"],
        task_count=len(run.tasks),
        changed_lines=run.changed_lines,
        standard_ok=run.standard_ok,
        binary_files=run.binary_files,
        dependencies=run.ctx.get("dependencies_added") or [],
        binary_paths=routing.binary_paths(run.ctx["files"]),
        content=run.ctx.get("content_matches") or [],
        config_preferences=preferences,
    )
    if controls:
        cls.reasons.append(f"{config.CONFIG_PATH} changes what checks read: {', '.join(controls[:5])}")
    run.protected_hit = any(h.rule == "protected" for h in cls.hits)
    run.major_rules = sorted({h.rule for h in cls.hits if h.route == "major" and h.rule != "protected"})
    # The pools a major change needs, and those a matched rule asks itself on any route.
    run.asked_pools = sorted(cls.asked)
    run.pools = sorted(cls.pools | cls.asked)
    run.implied_dimensions = set(cls.dimensions)
    run.record.update(required_route=cls.required_route, route_reasons=cls.reasons, required_pools=run.pools)
    if run.derived:
        # No block and no Spec: the route is the computed minimum, and the fast lane is all a change without a Spec may take.
        run.route = cls.required_route
        run.record["route"] = run.route
        if run.route in ("normal", "major"):
            add(
                "spec",
                "fail",
                f"no Change Request block and no Spec, and the change requires {run.route}: " + "; ".join(cls.reasons),
                rulebook.finding_fix("spec.missing", f"here, a {run.route} Spec"),
                code="spec.missing",
            )
            run.stop()
        return
    undeclared = sorted(cls.dimensions - set(risk["dimensions"]))
    if undeclared:
        # A Spec-backed change gets the implied gates anyway (the overlay below); an inline Change Request block must declare them.
        add(
            "route",
            "warn" if spec else "fail",
            f"risk.dimensions must include {undeclared}, which the changed paths imply",
            rulebook.finding_fix("route.undeclared_dimensions", f"here, {', '.join(undeclared)}" + (", which the gate already applies" if spec else "")),
            code="route.undeclared_dimensions",
        )
    if run.route == "emergency":
        revert = run.ctx.get("revert_of") or {}
        run.exact_revert = bool(revert.get("exact") and revert.get("on_base"))
        if run.exact_revert:
            # Undoing a merged commit exactly restores a state that was already reviewed: the commander's approval is enough.
            run.record["revert_of"] = revert["sha"]
            add(
                "emergency",
                "warn",
                f"an exact revert of {revert['sha'][:12]}, merged on the base branch: the incident commander's approval alone merges it; "
                "the post-incident review still covers it",
                code="emergency.revert",
            )
        elif cls.required_route == "major":
            add(
                "emergency",
                "warn",
                f"outside an emergency this repair would be major: the {', '.join(run.pools)} review still applies, and the post-incident review must cover it",
                code="emergency.would_be_major",
            )
    elif spec is not None and run.route == "normal" and cls.required_route == "major":
        # major is an overlay the gate computes, not a route an author must guess: a Spec-backed
        # change is raised, and the major gates (specialist approval, observe) apply.
        run.route = "major"
        run.record.update(route=run.route, declared_route="normal")
        add(
            "route",
            "warn",
            "raised to major: " + "; ".join(cls.reasons),
            rulebook.finding_fix("route.raised_to_major", f"here, the {', '.join(run.pools)} pool(s)"),
            code="route.raised_to_major",
        )
    elif run.route == "standard" and not run.standard_ok:
        pass  # the standard_change rule already says why; a second route failure is noise
    elif routing.ROUTE_RANK[run.route] < routing.ROUTE_RANK[cls.required_route]:
        need_spec = ", with a Spec" if cls.required_route in ("normal", "major") and spec is None else ""
        add(
            "route",
            "fail",
            f"declared {run.route}, but the change requires {cls.required_route}: " + "; ".join(cls.reasons),
            rulebook.finding_fix("route.too_low", f'here, `route: "{cls.required_route}"`{need_spec}'),
            code="route.too_low",
        )


def _config_controls(run: gate_run.GateRun) -> list[str] | None:
    """What the change's edit of `.aidd/config.yaml` changes beyond preference keys (routing.config_controls_changed),
    or None when it does not edit the config. An empty list means preferences only: then the config file routes like a
    doc, and a warning says so."""
    if config.CONFIG_PATH not in run.paths:
        return None
    controls = routing.config_controls_changed(run.ctx.get("base_config"), run.ctx["head_files"].get(config.CONFIG_PATH))
    if not controls:
        run.add(
            "route",
            "warn",
            f"{config.CONFIG_PATH} changes only preference keys, which steer no check, so it does not make the change major",
            code="route.config_preferences_only",
        )
    return controls


def gate_scope(run: gate_run.GateRun) -> None:
    """Every changed path sits inside some Task's scope, a test or design file, a frozen doc, a living threat model the
    Spec links, the Spec, or scope_exclude_paths; in a goal's change, also the goal's other work (GateRun.goal_paths)."""
    allowed = [s for task in run.tasks for s in task["scope"]] + run.test_files + run.design_files + run.threat_models
    allowed += run.cfg.get("scope_exclude_paths", default=[])
    allowed += [run.cr[key] for key in ("spec", "backfill") if run.cr.get(key)] + run.goal_paths
    outside = [p for p in run.paths if not globs.match_any(allowed, p)]
    if outside:
        shown = ", ".join(outside[:10]) + (" ..." if len(outside) > 10 else "")
        run.add(
            "scope",
            "fail",
            f"{len(outside)} changed path(s) outside the scope: {shown}",
            code="scope.outside",
        )
    # Plan adherence: a Task whose scope no changed path touches was not delivered, or the plan was wrong.
    # Either way the Approver should know before Merge approval; it warns rather than fails, because a Task can
    # legitimately end up needing no change. In the Spec phase nothing is implemented yet, so it says nothing.
    if run.spec:
        frozen = [run.cr["spec"], *run.test_files, *run.design_files, *run.threat_models] + ([run.cr["backfill"]] if run.cr.get("backfill") else [])
        run.spec_phase = routing.spec_phase(run.paths, frozen, [t["scope"] for t in run.tasks])
        run.record["phase"] = "spec" if run.spec_phase else "implementation"
        untouched = [t["id"] for t in run.tasks if not any(globs.match_any(t["scope"], p) for p in run.paths)]
        run.record["plan"] = {"tasks": len(run.tasks), "untouched_tasks": untouched}
        if untouched and not run.spec_phase:
            run.add(
                "scope",
                "warn",
                f"Task(s) {', '.join(untouched)} changed nothing in their scope: the plan and the diff disagree",
                code="scope.untouched_task",
            )


def gate_changed_lines(run: gate_run.GateRun) -> None:
    limit = None if run.route in ("standard", "emergency") else run.g["max_changed_lines"].get(run.route)
    if limit is not None and run.changed_lines > limit:
        run.add(
            "changed_lines",
            "fail",
            f"{run.changed_lines} changed lines exceed the {run.route} route's changed-line limit of {limit}",
            code="changed_lines.over_limit",
        )


def gate_merge_queue(run: gate_run.GateRun) -> None:
    """A merge queue entry merges exactly the approved head merged into the commit it was built on, and nothing else.

    Approvals stay bound to `head_sha`, so the entry's commit's tree must be what merging that head into
    `merge_queue.base_sha` gives. A stacked entry also carries earlier entries' changes, which only their own gate
    runs judged, so it passes only when the platform merges a group once every entry in it passed.
    """
    group = run.ctx.get("merge_queue")
    if not group:
        return
    run.record["merge_queue_sha"] = group["sha"]
    if group["merged_tree"] is None:
        run.add(
            "merge_queue",
            "fail",
            f"the approved head {run.head[:12]} does not merge cleanly into {group['base_sha'][:12]}, the commit the queue entry was built on",
            code="merge_queue.conflict",
        )
    elif group["tree"] != group["merged_tree"]:
        run.add(
            "merge_queue",
            "fail",
            f"the queue entry's commit {group['sha'][:12]} is not the approved head {run.head[:12]} merged into {group['base_sha'][:12]}: "
            "it holds changes nobody approved, or lacks approved ones",
            code="merge_queue.diff_mismatch",
        )
    if group["stacked"] and group.get("all_green") is not True:
        run.add(
            "merge_queue",
            "fail",
            f"the entry is built on another queue entry ({group['base_sha'][:12]}), and the queue is not confirmed to merge only groups whose "
            "every entry passed. A failing entry ahead could then merge with this one",
            code="merge_queue.stacked_unverified",
        )


# Files that change how tests run without being tests: runner configuration a path can name. pyproject.toml and
# package.json can hold it too, but they change for other reasons far more often, so they are left out.
TEST_HARNESS_FILES = (
    "conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "jest.config.*",
    "vitest.config.*",
    "vitest.workspace.*",
    "playwright.config.*",
    "cypress.config.*",
    "karma.conf.*",
    ".mocharc*",
    "phpunit.xml",
    "phpunit.xml.dist",
)


def test_harness_paths(paths: list[str], commands: list[list[str]]) -> list[str]:
    """The changed paths that configure or run the tests: a runner's configuration file (TEST_HARNESS_FILES), or a file a
    test command names in its argv (a runner script such as `scripts/test.sh`)."""
    named = {_repo_arg(a) for cmd in commands for a in cmd if isinstance(a, str) and not a.startswith("-")}
    return [p for p in paths if p in named or any(fnmatch.fnmatchcase(p.rsplit("/", 1)[-1], h) for h in TEST_HARNESS_FILES)]


def _repo_arg(arg: str) -> str:
    """A command argument as a repository path: without a leading ./"""
    return arg[2:] if arg.startswith("./") else arg


def gate_harness(run: gate_run.GateRun) -> None:
    """On a Spec-backed change, a changed file that configures or runs the tests is frozen only when tests.files lists it."""
    if not run.spec:
        return
    commands = [c.get("command", []) for c in [*run.cfg.get("tests", default=[]), *(run.declared.get("tests") or {}).get("commands", [])]]
    for path in test_harness_paths(run.paths, commands):
        if globs.match_any(run.test_files, path):
            continue
        run.add(
            "tests",
            "warn",
            f"{path} configures or runs the tests, and the Spec's tests.files does not list it. So Spec approval does not freeze it: "
            "a later edit could weaken the tests without voiding the approval",
            rulebook.finding_fix("tests.setup_unfrozen", f"here, {path}"),
            code="tests.setup_unfrozen",
        )


# The head branch of free work (an explore branch), where the guard holds no edit; the same prefix the guard reads.
EXPLORE_PREFIXES = ("explore/",)


def gate_explore(run: gate_run.GateRun) -> None:
    """An explore branch is free work: the guard holds no edit there, so nothing merges from it as it is."""
    branch = str(run.ctx["change"].get("head_ref") or "")
    if branch.startswith(EXPLORE_PREFIXES):
        run.add(
            "explore",
            "fail",
            f"{branch} is an explore branch: free work, with no Spec or scope check while it was written, so it never merges as it is",
            code="explore.branch",
        )


def gate_draft(run: gate_run.GateRun) -> None:
    if run.ctx["change"].get("draft"):
        run.add("draft", "pending", "the change is a draft", code="draft.is_draft")
