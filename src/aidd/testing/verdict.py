"""The verdict of an `aidd test` run: which results are good, and the exit code the run ends with.

`aidd test` exits on it and `aidd status` summarizes the last run with it, so the two never disagree. Evidence is the
runner's exit code on a commit; this verdict only reads the evidence file that code wrote.
"""

from __future__ import annotations

from aidd.testing.runner import red_ok


def result_good(result: dict) -> bool:
    """A green result passed; a red result failed with a real exit code (the new behavior's test fails on the base)."""
    return (result["red_green"] == "green" and result["status"] == "passed") or (result["red_green"] == "red" and red_ok(result))


def result_mark(result: dict, *, before_implement: bool) -> str:
    """`ok` for a good result, `..` for a failing green run the runner expected before Implement (the result says so, and so
    does the run, `before_implement`), else `!!`. A caller that excuses nothing, such as a merge, passes False."""
    if result_good(result):
        return "ok"
    return ".." if before_implement and result["red_green"] == "green" and result.get("before_implement") else "!!"


def untested(evidence: dict) -> bool:
    """Whether a full run ran no test because the project's own config says none applies to the paths it changed: every command
    is limited by `when_changed`, and none matches. The run exits 0, and it is no proof: a merge and `aidd status` never read it
    as a pass."""
    return not evidence["results"] and not evidence.get("partial") and bool(evidence.get("untested"))


def ran_nothing(evidence: dict) -> bool:
    """Whether a full run selected no command and that is a failure: nothing is configured, or an applying Spec's commands were
    all skipped, so nothing was proven. A quick check (`--changed`) may select none when nothing it covers changed, and says it
    is partial. A run no test applied to (`untested`) is the project's declared state, so it is no failure."""
    return not evidence["results"] and not evidence.get("partial") and not evidence.get("untested")


def exit_code(evidence: dict, *, no_red: bool = False) -> int:
    """1 when a result is bad, except in the Design stage, where a failing green run is expected before Implement. A full
    run that ran no command because nothing applies it, or that ran in a dirty tree, proves nothing about the head commit,
    so it fails too, unless the config says no test applies to the changed paths; a quick check (`--changed`, `--no-red`) may run
    mid-change. So exit 0 on a full run means every command that applies ran and passed, or none applies."""
    no_red = no_red or bool(evidence.get("no_red"))
    before_implement = bool(evidence.get("before_implement")) and not evidence.get("require_green")  # a gating run excuses nothing
    bad = any(result_mark(r, before_implement=before_implement) == "!!" for r in evidence["results"])
    dirty_full = evidence.get("dirty_tree") and not evidence.get("partial") and not no_red
    return 1 if bad or dirty_full or ran_nothing(evidence) or related_tests_in_full_run(evidence) else 0


def related_tests_in_full_run(evidence: dict) -> bool:
    """Whether evidence that says it is a full run holds a result that ran only a command's related tests. `aidd test` never
    writes one, since only `--changed` narrows, so such a file was made by hand, and it proves nothing about the full command."""
    return not evidence.get("partial") and any(isinstance(r, dict) and r.get("related_tests") for r in evidence["results"])
