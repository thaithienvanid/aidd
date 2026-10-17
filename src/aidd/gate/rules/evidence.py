"""The test evidence rules: which tests apply, the status checks, a green result on this exact head, red before
green, and the Spec phase.
"""

from __future__ import annotations

import re

from aidd import workitems
from aidd.gate import routing
from aidd.gate.rules import gate_run
from aidd.kernel import json_schema

NO_OP = {"true", ":", "exit", "echo", "/bin/true", "/usr/bin/true"}
_NO_OP_ARGS = {"true", ":", "pass", "exit 0", "exit 0;", "; true", "noop"}
_NO_OP_WRAPPERS = {"sh", "bash", "zsh", "/bin/sh", "/bin/bash", "env", "nohup", "time", "nice", "python", "python3", "make"}


def is_no_op_command(cmd: list[str]) -> bool:
    if not cmd or cmd[0].strip() in NO_OP:
        return True
    return (cmd[0].strip() in _NO_OP_WRAPPERS or len(cmd) == 1) and any(arg.strip() in _NO_OP_ARGS for arg in cmd[1:])


def gate_tests_declared(run: gate_run.GateRun) -> None:
    """Which tests apply to this diff, and whether the repository has any at all."""
    cfg, add, spec = run.cfg, run.add, run.spec
    config_cmds = cfg.get("tests", default=[])
    declared_cmds = (run.declared.get("tests") or {}).get("commands", [])
    run.required, dupes = routing.required_tests(config_cmds, declared_cmds, "spec" if spec else "change_request", run.paths, route=run.route)
    for dup in dupes:
        add("tests", "fail", f"test name {dup!r} is declared twice (config and Spec)", "give every test command a unique name", code="tests.duplicate_name")
    status_names = cfg.get("evidence", "status_checks", default=[])
    if not config_cmds and not declared_cmds and not status_names:
        add(
            "tests",
            "fail",
            "no tests: the config has no `tests` or evidence.status_checks, and the change declares none",
            "characterization: name one command that proves today's behavior, in the config or the Spec",
            code="tests.none",
        )
    elif not run.required and not status_names:
        add("tests", "warn", "no test applies to this diff: every command's when_changed misses the changed paths", code="tests.none_applies")
    if not spec and run.route == "minor" and not config_cmds and not status_names and declared_cmds:
        # Nobody reviews an inline Change Request block before the diff, so its own commands cannot stand in for a suite.
        add(
            "tests",
            "fail",
            "a minor change needs the repository suite (`tests`) or evidence.status_checks; inline tests only add to it",
            "bind the repository suite in the config, or write a Spec (its tests are reviewed at Spec approval)",
            code="tests.minor_without_suite",
        )
    for c in declared_cmds:
        if is_no_op_command(c.get("command", [])):
            add("tests", "fail", f"{c['name']}: {c['command']} proves nothing", "run a command that fails when the behavior is wrong", code="tests.no_op")
    if spec and workitems.tests_with(spec):
        _tests_with(run)


def _tests_with(run: gate_run.GateRun) -> None:
    """`tests.mode: with`: Spec approval never saw the test files, so the change must stay new code with nothing to
    break by what the gate computes from the diff: below major, with no risk dimension. What the Spec declares (its type, its risk, a command covering each
    Acceptance item) is checked where the Spec loads (`spec.invalid`); red-on-base and
    green-on-head hold as for any Spec."""
    why = [f"the gate computed route {run.route}"] if run.route in ("major", "emergency") else []
    if run.implied_dimensions:
        why.append(f"the changed paths imply the risk dimensions {', '.join(sorted(run.implied_dimensions))}")
    if why:
        run.add(
            "tests",
            "fail",
            f"tests.mode is with, but {'; '.join(why)}: its tests must come first, frozen by Spec approval",
            "set `tests.mode: first` (or remove it), write and commit the tests, and ask for Spec approval again",
            code="tests.with_not_allowed",
        )


def gate_status_checks(run: gate_run.GateRun) -> None:
    """Existing CI as evidence: named check runs must succeed on this head."""
    names = run.cfg.get("evidence", "status_checks", default=[])
    if not names:
        return
    states = run.ctx.get("status_checks") or {}
    run.record["status_checks"] = {name: states.get(name, "missing") for name in names}
    for name in names:
        state = states.get(name, "missing")
        if state in ("success", "neutral"):
            continue
        if state == "skipped":
            run.add(
                "tests", "pending", f"check run {name!r} is skipped on head {run.head[:12]}", "the check did not run on this head", code="tests.check_skipped"
            )
        elif state in ("pending", "queued", "in_progress", "missing"):
            run.add("tests", "pending", f"check run {name!r} is {state} on head {run.head[:12]}", "wait for your CI", code="tests.check_waiting")
        else:
            run.add("tests", "fail", f"check run {name!r} is {state} on head {run.head[:12]}", "fix the change until your CI passes", code="tests.check_failed")


def gate_evidence(run: gate_run.GateRun) -> None:
    """Every applicable command has a green result on this exact head and base."""
    ctx, add, head, record = run.ctx, run.add, run.head, run.record
    record["tests"] = []
    if not run.required:
        return
    ev = ctx.get("evidence")
    if ev is None:
        add("tests", "pending", f"no test evidence for head {head[:12]} yet", "wait for aidd-tests, or run `aidd test`", code="tests.no_evidence")
        return
    if ev.get("invalid"):
        add(
            "tests",
            "fail",
            f"evidence: {ev['invalid']}",
            "re-run aidd-tests; if it repeats, the test job is writing a corrupt artifact",
            code="tests.evidence_invalid",
        )
        return
    everrs = json_schema.validate(ev, "evidence.schema.json")
    if everrs:
        for e in everrs:
            add("tests", "fail", f"evidence: {e}", "run the tests again with `aidd test`, which writes valid evidence", code="tests.evidence_schema")
        return
    if ev.get("partial"):
        add(
            "tests",
            "pending",
            "the evidence is partial: `aidd test --changed` ran only the commands the working-tree diff selects",
            "run `aidd test` without --changed; in CI, wait for aidd-tests",
            code="tests.evidence_partial",
        )
        return
    # In a merge queue the tests re-run on the merge-group commit, against the commit the entry was built on.
    group = ctx.get("merge_group")
    want_head, want_base = (group["sha"], group["base_sha"]) if group else (head, ctx["base_sha"])
    what = "merge-group commit" if group else "head"
    if ev["head_sha"] != want_head:
        add(
            "tests",
            "pending",
            f"evidence is for {ev['head_sha'][:12]}, the {what} is {want_head[:12]}",
            f"wait for a run on the current {what}",
            code="tests.evidence_other_head",
        )
        return
    if ev["base_sha"] != want_base:
        add(
            "tests",
            "pending",
            f"evidence ran against base {ev['base_sha'][:12]}, the change's base is {want_base[:12]}",
            "re-run aidd-tests for this pull request" + (" in the merge queue" if group else ""),
            code="tests.evidence_other_base",
        )
        return
    rank: dict[str | None, int] = {"failed": 2, "timeout": 2, "not_started": 1, "passed": 0}

    def badness(r: dict) -> tuple[int, bool]:
        return rank.get(r.get("status"), 0), r.get("exit") != 0

    seen_results: set[tuple[str, str]] = set()
    run.green, run.red = {}, {}
    for r in ev["results"]:
        name, phase = r["name"], r["red_green"]
        if (name, phase) in seen_results:
            add(
                "tests",
                "fail",
                f"duplicate test result {name!r} in phase {phase!r}",
                "each test command must have at most one result per phase",
                code="tests.duplicate_result",
            )
        seen_results.add((name, phase))
        target = run.green if phase == "green" else run.red if phase == "red" else None
        if target is not None and (name not in target or badness(r) > badness(target[name])):
            target[name] = r
    run.evidence_ok = True
    if ev.get("runner"):
        record["evidence_runner"] = dict(ev["runner"])
    for c, src in run.required:
        r = run.green.get(c["name"])
        if r is None:
            add("tests", "fail", f"{c['name']}: no result on head", "re-run aidd-tests", code="tests.no_result")
            continue
        entry = {
            "name": c["name"],
            "source": src,
            "command": r["command"],
            "exit": r.get("exit"),
            "status": r["status"],
            "duration_seconds": r.get("duration_seconds"),
        }
        red = run.red.get(c["name"])
        if red is not None:
            entry.update(red_exit=red.get("exit"), red_status=red["status"])
        record["tests"].append(entry)
        retried = len(r.get("attempts") or []) - 1
        if retried > 0 and r["status"] == "passed" and r.get("exit") == 0:
            entry["flaky"] = True
        if r["command"] != c["command"]:
            add(
                "tests",
                "fail",
                f"{c['name']}: the runner ran {r['command']}, the declaration says {c['command']}",
                "run the declared command with `aidd test`, or correct the command in the Spec",
                code="tests.command_mismatch",
            )
        elif retried > int(c.get("retries", 0) or 0):
            add(
                "tests",
                "fail",
                f"{c['name']}: ran {retried + 1} times, but the declaration allows {int(c.get('retries', 0) or 0)} retr(ies)",
                "set retries on the command in the config (a person reviews that), or fix the flake",
                code="tests.retries_exceeded",
            )
        elif retried > 0 and entry.get("flaky"):
            add(
                "tests",
                "warn",
                f"{c['name']}: passed on attempt {retried + 1} of {retried + 1} after failing: flaky, counted green",
                "fix the flake; `aidd metrics` counts flaky runs",
                code="tests.flaky",
            )
        elif (r["status"] != "passed" or r.get("exit") != 0) and run.spec_phase:
            run.spec_failures.append(f"{c['name']}: {r['status']} (exit {r.get('exit')})")
        elif r["status"] != "passed" or r.get("exit") != 0:
            add(
                "tests",
                "fail",
                f"{c['name']}: {r['status']} (exit {r.get('exit')})",
                "an implementation error or a flake retries in Implement (at most 3); a wrong Spec returns to Specify",
                code="tests.failed",
            )


def gate_red_green(run: gate_run.GateRun) -> None:
    """New behavior failed on the base commit, for the right reason, with the declared command."""
    if not run.evidence_ok:
        return
    add = run.add
    # A Spec whose optional Spec approval was recorded is bound: its tests must prove new behavior, as on a required route.
    level = "fail" if run.g["red_green"] == "require" or run.spec_bound else "warn"
    new_behavior = [c for c, _ in run.required if c.get("new_behavior")]
    ctype = run.declared["type"]
    if run.spec and run.route in ("normal", "major") and ctype in routing.NEW_BEHAVIOR_TYPES and not new_behavior:
        add(
            "red_green",
            level,
            f"a {ctype} change needs at least one test command with new_behavior: true",
            "write a test that fails on the base commit and passes with the change",
            code="red_green.no_new_behavior",
        )
    for c in new_behavior:
        r = run.red.get(c["name"])
        if r is None:
            add("red_green", level, f"{c['name']}: no red run against the base commit", "run `aidd test` without --no-red", code="red_green.no_red_run")
        elif r.get("attempts"):
            add(
                "red_green",
                level,
                f"{c['name']}: the red run was retried ({len(r['attempts'])} attempts); a retry could turn a flaky test red",
                "run red once: `aidd test` never retries it",
                code="red_green.red_retried",
            )
        elif r["command"] != c["command"]:
            add(
                "red_green",
                level,
                f"{c['name']}: the red run used {r['command']}, the declaration says {c['command']}",
                "run red again with the declared command (`aidd test` runs it), or correct the command in the Spec",
                code="red_green.red_command_mismatch",
            )
        elif r["status"] == "passed":
            add(
                "red_green",
                level,
                f"{c['name']}: passes on the base commit, so it does not prove new behavior",
                "tighten the test",
                code="red_green.passes_on_base",
            )
        elif not red_ok(r):
            pytest_exit = r.get("exit") in PYTEST_NOT_RED and runs_pytest(r.get("command"))
            why = " (pytest: no test ran to a failure; it hit an internal or usage error, or collected nothing)" if pytest_exit else ""
            add(
                "red_green",
                level,
                f"{c['name']}: red run was {r['status']} (exit {r.get('exit')}){why}; it must fail by assertion",
                "make the test fail fast on base" + (": check the command collects the new test" if pytest_exit else ""),
                code="red_green.red_not_assertion",
            )


def gate_spec_phase(run: gate_run.GateRun) -> None:
    """The Spec phase waits for Spec approval: its tests are expected to fail on head until Implement, so a failure is
    early proof, not a broken change, and nothing here can pass until a Task changes something."""
    if not run.spec_phase:
        return
    failing = f"; failing on head as expected before implementation: {'; '.join(run.spec_failures[:5])}" if run.spec_failures else ""
    untouched = ", ".join((run.record.get("plan") or {}).get("untouched_tasks", []))
    then = f"implement Task(s) {untouched}, and the tests must pass on that head"
    if run.spec_approved:
        state, fix = "; Spec approval recorded", then
    elif run.route in run.g["spec_approval_routes"]:
        state, fix = "", f"get Spec approval first; then {then}"
    else:
        state, fix = "", f"{then} (Spec approval is optional on route {run.route} under profile {run.cfg.profile})"
    run.add("tests", "pending", f"Spec phase: the change holds only the Spec and the files it freezes{state}{failing}", fix, code="tests.spec_phase")


# pytest's exit codes that mean no test ran to a failure: 3 internal error, 4 usage error, 5 no tests collected
# (docs.pytest.org, "Exit codes"). Exit 2 (interrupted, as by a collection error) stays red: a test that imports the
# module it will prove, before that module exists, is the usual first red, and the tester's rule accepts a missing module.
PYTEST_NOT_RED = (3, 4, 5)


def runs_pytest(command: object) -> bool:
    """Whether a test command runs pytest: `pytest` or `py.test` as a program, or `-m pytest`, in any wrapper."""
    if not isinstance(command, list):
        return False
    words = [str(w) for w in command]
    progs = [re.split(r"[\\/]", w)[-1].lower().removesuffix(".exe") for w in words]
    return any(p in ("pytest", "py.test") for p in progs) or any(w == "-m" and progs[i + 1 : i + 2] == ["pytest"] for i, w in enumerate(words))


def red_ok(result: dict) -> bool:
    """A red run proves new behavior only when it failed with a real exit code: not a timeout, not a missing command,
    and, for pytest, not an exit that says no test failed (PYTEST_NOT_RED). Other runners keep every other exit code."""
    code = result.get("exit")
    if result.get("status") != "failed" or code in (None, 126, 127):
        return False
    return not (code in PYTEST_NOT_RED and runs_pytest(result.get("command")))
